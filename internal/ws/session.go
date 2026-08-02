package ws

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"

	llmclient "github.com/mugen64/bibi-core/internal/llm"
	llmpb "github.com/mugen64/bibi-core/internal/llm/pb"
	sttclient "github.com/mugen64/bibi-core/internal/stt"
	sttpb "github.com/mugen64/bibi-core/internal/stt/pb"
	ttsclient "github.com/mugen64/bibi-core/internal/tts"
)

const (
	writeWait      = 10 * time.Second
	pongWait       = 60 * time.Second
	pingPeriod     = (pongWait * 9) / 10
	maxMessageSize = 1 << 20
)

type ControlMessage struct {
	Type        string `json:"type"`
	Text        string `json:"text,omitempty"`
	Code        string `json:"code,omitempty"`
	Message     string `json:"message,omitempty"`
	SampleRate  int32  `json:"sample_rate,omitempty"`
	Channels    int32  `json:"channels,omitempty"`
	SampleWidth int32  `json:"sample_width,omitempty"`
}

type outboundMessage struct {
	frameType int
	data      []byte
}

// ttsJob is tagged with the turn it belongs to, so the worker can
// silently drop stale jobs left over from an interrupted turn instead
// of synthesizing audio nobody wants anymore.
type ttsJob struct {
	turn uint64
	text string
}

type Session struct {
	conn      *websocket.Conn
	send      chan outboundMessage
	sttClient *sttclient.Client
	sttStream *sttclient.Stream
	llmClient *llmclient.Client
	ttsClient *ttsclient.Client
	history   []llmclient.ChatMessage
	ttsQueue  chan ttsJob

	// currentTurn increments on every new utterance. Any in-flight work
	// tagged with an older turn is stale and should be abandoned - this
	// is the core mechanism barge-in relies on.
	currentTurn uint64

	// mu guards activeLLMStream/activeTTSStream, which are read/written
	// from multiple goroutines (forwardTranscripts triggers new LLM
	// streams, ttsWorker sets/clears the active TTS stream, and
	// interruptCurrentTurn reads both to cancel them).
	mu              sync.Mutex
	activeLLMStream *llmclient.Stream
	activeTTSStream *ttsclient.Stream

	ctx    context.Context
	cancel context.CancelFunc
	logger *slog.Logger
}

func NewSession(conn *websocket.Conn, sttClient *sttclient.Client, llmClient *llmclient.Client, ttsClient *ttsclient.Client) *Session {
	ctx, cancel := context.WithCancel(context.Background())
	s := &Session{
		conn:      conn,
		send:      make(chan outboundMessage, 32),
		sttClient: sttClient,
		llmClient: llmClient,
		ttsClient: ttsClient,
		ttsQueue:  make(chan ttsJob, 32),
		ctx:       ctx,
		cancel:    cancel,
		logger:    slog.With("component", "ws_session"),
	}
	go s.ttsWorker()
	return s
}

func (s *Session) Run() {
	go s.writePump()
	s.readPump()
	s.cancel()
}

func (s *Session) readPump() {
	defer func() {
		close(s.send)
		s.conn.Close()
	}()

	s.conn.SetReadLimit(maxMessageSize)
	s.conn.SetReadDeadline(time.Now().Add(pongWait))
	s.conn.SetPongHandler(func(string) error {
		s.conn.SetReadDeadline(time.Now().Add(pongWait))
		return nil
	})

	for {
		msgType, data, err := s.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				s.logger.Warn("unexpected close", "error", err)
			} else {
				s.logger.Info("connection closed")
			}
			return
		}

		switch msgType {
		case websocket.BinaryMessage:
			s.handleAudioChunk(data)
		case websocket.TextMessage:
			s.handleControlMessage(data)
		}
	}
}

func (s *Session) handleAudioChunk(data []byte) {
	if s.sttStream == nil {
		s.logger.Warn("audio received before stream started, dropping")
		s.sendError("no_active_stream", `send {"type":"start"} before audio`)
		return
	}

	err := s.sttStream.SendAudio(data, 16000, 1, 2, false)
	if err != nil {
		if errors.Is(err, sttclient.ErrStreamClosed) {
			// Trailing audio chunk arrived just after end_utterance -
			// harmless timing artifact, not worth surfacing to the user.
			s.logger.Debug("dropped audio chunk after stream closed")
			return
		}
		s.logger.Error("failed to send audio to stt", "error", err)
		s.sendError("stt_send_failed", err.Error())
	}
}

func (s *Session) handleControlMessage(data []byte) {
	var msg ControlMessage
	if err := json.Unmarshal(data, &msg); err != nil {
		s.sendError("bad_request", "malformed control message")
		return
	}

	switch msg.Type {
	case "start":
		s.beginNewTurn()
	case "end_utterance":
		s.endUtterance()
	default:
		s.sendError("unknown_message_type", "unrecognized control message type: "+msg.Type)
	}
}

// beginNewTurn handles BOTH the first "start" of a session and any
// subsequent "start" that arrives while a previous response is still
// in flight (barge-in). interruptCurrentTurn is a no-op if nothing is
// active, so this is safe to call unconditionally.
func (s *Session) beginNewTurn() {
	newTurn := atomic.AddUint64(&s.currentTurn, 1)
	s.interruptCurrentTurn(newTurn)
	s.startStream()
}

// interruptCurrentTurn cancels any in-flight LLM/TTS work from the
// previous turn, drains queued-but-unsynthesized sentences, and tells
// the client to stop playing anything already buffered.
func (s *Session) interruptCurrentTurn(newTurn uint64) {
	s.mu.Lock()
	llmStream := s.activeLLMStream
	ttsStream := s.activeTTSStream
	s.activeLLMStream = nil
	s.activeTTSStream = nil
	s.mu.Unlock()

	interrupted := false

	if llmStream != nil {
		llmStream.Close() // cancels the gRPC context - Python side sees context.cancelled()
		interrupted = true
	}
	if ttsStream != nil {
		ttsStream.Close()
		interrupted = true
	}

	// Drain any sentences queued but not yet picked up by ttsWorker.
	// Non-blocking - stop as soon as the queue is empty.
drain:
	for {
		select {
		case <-s.ttsQueue:
			interrupted = true
		default:
			break drain
		}
	}

	if interrupted {
		s.logger.Info("turn interrupted", "new_turn", newTurn)
		s.sendJSON(ControlMessage{Type: "interrupted"})
	}
}

func (s *Session) startStream() {
	if s.sttStream != nil {
		s.sttStream.Close()
	}

	stream, err := s.sttClient.OpenStream(s.ctx)
	if err != nil {
		s.logger.Error("failed to open stt stream", "error", err)
		s.sendError("stt_unavailable", "could not start transcription")
		return
	}
	s.sttStream = stream

	go s.forwardTranscripts(stream)
}

func (s *Session) forwardTranscripts(stream *sttclient.Stream) {
	turn := atomic.LoadUint64(&s.currentTurn)

	for event := range stream.Events {
		switch event.Type {
		case sttpb.TranscriptEvent_PARTIAL:
			s.sendJSON(ControlMessage{Type: "partial_transcript", Text: joinSegments(event)})
		case sttpb.TranscriptEvent_FINAL:
			text := joinSegments(event)
			s.sendJSON(ControlMessage{Type: "final_transcript", Text: text})
			s.startLLMChat(text, turn)
		case sttpb.TranscriptEvent_ERROR:
			s.sendError(event.ErrorCode, event.ErrorMessage)
		}
	}
}

func (s *Session) startLLMChat(prompt string, turn uint64) {
	// If a barge-in happened between the transcript arriving and this
	// call, currentTurn has already moved on - don't start a response
	// for a turn that's already stale.
	if atomic.LoadUint64(&s.currentTurn) != turn {
		return
	}

	stream, err := s.llmClient.StartChat(s.ctx, prompt, s.history)
	if err != nil {
		s.logger.Error("failed to start llm stream", "error", err)
		s.sendError("llm_unavailable", "could not start chat response")
		return
	}

	s.mu.Lock()
	s.activeLLMStream = stream
	s.mu.Unlock()

	go s.forwardLLMEvents(stream, prompt, turn)
}

func (s *Session) forwardLLMEvents(stream *llmclient.Stream, prompt string, turn uint64) {
	var fullResponse string

	for event := range stream.Events {
		if atomic.LoadUint64(&s.currentTurn) != turn {
			// Barge-in happened mid-generation. The stream's context is
			// already cancelled by interruptCurrentTurn - just stop
			// consuming, don't queue any more TTS, don't touch history.
			return
		}

		switch event.Type {
		case llmpb.ChatEvent_CHUNK:
			fullResponse += event.Text
			s.sendJSON(ControlMessage{Type: "llm_chunk", Text: event.Text})

			select {
			case s.ttsQueue <- ttsJob{turn: turn, text: event.Text}:
			default:
				s.logger.Warn("tts queue full, dropping chunk")
			}

		case llmpb.ChatEvent_DONE:
			s.mu.Lock()
			s.activeLLMStream = nil
			s.mu.Unlock()

			s.history = append(s.history,
				llmclient.ChatMessage{Role: "user", Content: prompt},
				llmclient.ChatMessage{Role: "assistant", Content: fullResponse},
			)

		case llmpb.ChatEvent_ERROR:
			s.sendError(event.ErrorCode, event.ErrorMessage)
		}
	}
}

func (s *Session) ttsWorker() {
	for {
		select {
		case <-s.ctx.Done():
			return
		case job, ok := <-s.ttsQueue:
			if !ok {
				return
			}
			if atomic.LoadUint64(&s.currentTurn) != job.turn {
				continue // stale - dropped by interruptCurrentTurn's drain in the common case, but check again defensively
			}
			s.synthesizeAndSend(job)
		}
	}
}

func (s *Session) synthesizeAndSend(job ttsJob) {
	stream, err := s.ttsClient.Synthesize(s.ctx, job.text, "")
	if err != nil {
		s.logger.Error("failed to start tts stream", "error", err)
		s.sendError("tts_unavailable", "could not synthesize speech")
		return
	}

	s.mu.Lock()
	s.activeTTSStream = stream
	s.mu.Unlock()

	formatSent := false

	for chunk := range stream.Events {
		if atomic.LoadUint64(&s.currentTurn) != job.turn {
			return
		}

		// Announce format before the first chunk of this sentence's
		// audio, so the client knows how to interpret the raw PCM
		// bytes that follow. Sent per-sentence rather than once per
		// session in case different sentences ever use different
		// voices - cheap (one small JSON message) relative to the
		// audio itself.
		if !formatSent {
			s.sendJSON(ControlMessage{
				Type:        "audio_format",
				SampleRate:  chunk.SampleRate,
				Channels:    chunk.Channels,
				SampleWidth: chunk.SampleWidth,
			})
			formatSent = true
		}

		select {
		case s.send <- outboundMessage{frameType: websocket.BinaryMessage, data: chunk.Data}:
		case <-s.ctx.Done():
			return
		}
	}

	s.mu.Lock()
	if s.activeTTSStream == stream {
		s.activeTTSStream = nil
	}
	s.mu.Unlock()
}

func (s *Session) endUtterance() {
	if s.sttStream == nil {
		return
	}
	if err := s.sttStream.CloseSend(); err != nil {
		s.logger.Warn("failed to close stt send side", "error", err)
	}
}

func (s *Session) sendJSON(msg ControlMessage) {
	data, err := json.Marshal(msg)
	if err != nil {
		s.logger.Error("failed to marshal outgoing message", "error", err)
		return
	}
	select {
	case s.send <- outboundMessage{frameType: websocket.TextMessage, data: data}:
	default:
		s.logger.Warn("send buffer full, dropping message")
	}
}

func (s *Session) sendError(code, message string) {
	s.sendJSON(ControlMessage{Type: "error", Code: code, Message: message})
}

func joinSegments(event *sttpb.TranscriptEvent) string {
	text := ""
	for _, seg := range event.Segments {
		text += seg.Text
	}
	return text
}

func (s *Session) writePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		s.conn.Close()
	}()

	for {
		select {
		case msg, ok := <-s.send:
			s.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				s.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			if err := s.conn.WriteMessage(msg.frameType, msg.data); err != nil {
				s.logger.Error("write failed", "error", err)
				return
			}

		case <-ticker.C:
			s.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := s.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

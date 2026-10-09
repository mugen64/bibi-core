package ws

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"

	llmclient "github.com/mugen64/bibi-core/internal/llm"
	sttclient "github.com/mugen64/bibi-core/internal/stt"
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
	Voice       string `json:"voice,omitempty"`

	// Turn lets the client tell which turn a message belongs to, so it
	// can discard anything tagged with a turn older than the most
	// recent "interrupted" message it saw (a barge-in can still let a
	// handful of already-buffered messages from the previous turn
	// through server-side - see forwardTranscripts).
	Turn uint64 `json:"turn,omitempty"`
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

// audioFormatInfo is the PCM format incoming mic audio is in, as
// declared by the client on "start". Falls back to defaultAudioFormat
// for any field the client left unset.
type audioFormatInfo struct {
	SampleRate  int32
	Channels    int32
	SampleWidth int32
}

var defaultAudioFormat = audioFormatInfo{SampleRate: 16000, Channels: 1, SampleWidth: 2}

// audioFrame is one unit of work for audioSendWorker - either a chunk
// of mic audio, or (closeSend set) the end-of-utterance marker that
// must be sent last and in order relative to any already-queued audio.
type audioFrame struct {
	data           []byte
	format         audioFormatInfo
	endOfUtterance bool
	closeSend      bool
}

type Session struct {
	conn       *websocket.Conn
	send       chan outboundMessage
	sttClient  *sttclient.Client
	sttStream  atomic.Pointer[sttclient.Stream]
	llmClient  *llmclient.Client
	ttsClient  *ttsclient.Client
	ttsQueue   chan ttsJob
	audioQueue chan audioFrame

	// voice is read by ttsWorker's goroutine and written by readPump's
	// goroutine on "set_voice", so it's atomic rather than plain-field.
	// Empty string means "use the TTS service's default".
	voice atomic.Pointer[string]

	// audioFormat is read by audioSendWorker's goroutine and written by
	// readPump's goroutine on "start", so it's atomic too.
	audioFormat atomic.Pointer[audioFormatInfo]

	// currentTurn increments on every new utterance. Any in-flight work
	// tagged with an older turn is stale and should be abandoned - this
	// is the core mechanism barge-in relies on.
	currentTurn atomic.Uint64

	// mu guards activeLLMStream/activeTTSStream/history, all read and
	// written from multiple goroutines: forwardTranscripts reads history
	// to build the next prompt's context and triggers new LLM streams,
	// forwardLLMEvents appends to history and clears activeLLMStream when
	// a turn completes, ttsWorker sets/clears the active TTS stream, and
	// interruptCurrentTurn reads both stream pointers to cancel them.
	mu              sync.Mutex
	activeLLMStream *llmclient.Stream
	activeTTSStream *ttsclient.Stream
	history         []llmclient.ChatMessage

	ctx    context.Context
	cancel context.CancelFunc
	logger *slog.Logger
}

func NewSession(conn *websocket.Conn, sttClient *sttclient.Client, llmClient *llmclient.Client, ttsClient *ttsclient.Client) *Session {
	ctx, cancel := context.WithCancel(context.Background())
	s := &Session{
		conn:       conn,
		send:       make(chan outboundMessage, 32),
		sttClient:  sttClient,
		llmClient:  llmClient,
		ttsClient:  ttsClient,
		ttsQueue:   make(chan ttsJob, 32),
		audioQueue: make(chan audioFrame, 64),
		ctx:        ctx,
		cancel:     cancel,
		logger:     slog.With("component", "ws_session"),
	}
	go s.ttsWorker()
	go s.audioSendWorker()
	return s
}

func (s *Session) Run() {
	go s.writePump()
	s.readPump()
	s.cancel()
}

func (s *Session) readPump() {
	// s.send is never closed here - it has multiple writer goroutines
	// (sendJSON is called from forwardTranscripts, forwardLLMEvents,
	// ttsWorker, and interruptCurrentTurn), and closing a channel out
	// from under concurrent writers panics on their next send even
	// inside a select/default. s.ctx is the single shutdown signal
	// instead; every writer selects on s.ctx.Done() too.
	defer s.conn.Close()

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

// handleAudioChunk is called directly from readPump's loop, so it must
// never block - it only enqueues; audioSendWorker does the actual
// (potentially slow) gRPC send on its own goroutine. Otherwise a
// wedged STT backend would stall the entire read loop, including the
// ability to process a "start" barge-in message.
func (s *Session) handleAudioChunk(data []byte) {
	if s.sttStream.Load() == nil {
		s.logger.Warn("audio received before stream started, dropping")
		s.sendError("no_active_stream", `send {"type":"start"} before audio`)
		return
	}

	select {
	case s.audioQueue <- audioFrame{data: data, format: s.getAudioFormat()}:
	default:
		s.logger.Warn("audio queue full, dropping chunk")
	}
}

// audioSendWorker is the only goroutine that calls sttStream.SendAudio,
// decoupling the (potentially blocking) gRPC send from readPump.
func (s *Session) audioSendWorker() {
	for {
		select {
		case <-s.ctx.Done():
			return
		case frame := <-s.audioQueue:
			stream := s.sttStream.Load()
			if stream == nil {
				continue // "start" not called yet, or the stream failed to open
			}
			err := stream.SendAudio(frame.data, frame.format.SampleRate, frame.format.Channels, frame.format.SampleWidth, frame.endOfUtterance)
			if err != nil {
				switch {
				case errors.Is(err, sttclient.ErrStreamClosed), stream.Closed(), s.sttStream.Load() != stream:
					// Benign: this stream was closed (possibly
					// concurrently with this very Send() call racing
					// past its own closed-check, which is why the error
					// isn't always the ErrStreamClosed sentinel) and/or
					// superseded by a newer "start". Either way it's
					// abandoned, so there's nothing useful to tell the
					// client.
					s.logger.Debug("dropped audio chunk for a closed/superseded stream", "error", err)
				default:
					s.logger.Error("failed to send audio to stt", "error", err)
					s.sendError("stt_send_failed", err.Error())
				}
				continue
			}
			if frame.closeSend {
				if err := stream.CloseSend(); err != nil {
					s.logger.Warn("failed to close stt send side", "error", err)
				}
			}
		}
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
		s.setAudioFormat(msg)
		s.beginNewTurn()
	case "end_utterance":
		s.endUtterance()
	case "set_voice":
		s.voice.Store(&msg.Voice)
	default:
		s.sendError("unknown_message_type", "unrecognized control message type: "+msg.Type)
	}
}

// setAudioFormat records the PCM format the client declares its mic
// audio will be sent in, falling back to defaultAudioFormat for any
// field left unset (zero).
func (s *Session) setAudioFormat(msg ControlMessage) {
	f := defaultAudioFormat
	if msg.SampleRate > 0 {
		f.SampleRate = msg.SampleRate
	}
	if msg.Channels > 0 {
		f.Channels = msg.Channels
	}
	if msg.SampleWidth > 0 {
		f.SampleWidth = msg.SampleWidth
	}
	s.audioFormat.Store(&f)
}

func (s *Session) getAudioFormat() audioFormatInfo {
	if f := s.audioFormat.Load(); f != nil {
		return *f
	}
	return defaultAudioFormat
}

// getVoice returns the client's selected voice, or "" (the TTS service's
// default) if none has been set yet.
func (s *Session) getVoice() string {
	if v := s.voice.Load(); v != nil {
		return *v
	}
	return ""
}

// beginNewTurn handles BOTH the first "start" of a session and any
// subsequent "start" that arrives while a previous response is still
// in flight (barge-in). interruptCurrentTurn is a no-op if nothing is
// active, so this is safe to call unconditionally.
func (s *Session) beginNewTurn() {
	newTurn := s.currentTurn.Add(1)
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
		s.sendJSON(ControlMessage{Type: "interrupted", Turn: newTurn})
	}
}

func (s *Session) startStream() {
	if old := s.sttStream.Load(); old != nil {
		old.Close()
	}

	stream, err := s.sttClient.OpenStream(s.ctx)
	if err != nil {
		s.logger.Error("failed to open stt stream", "error", err)
		s.sendError("stt_unavailable", "could not start transcription")
		s.sttStream.Store(nil) // ensure handleAudioChunk's nil-check fires again
		return
	}
	s.sttStream.Store(stream)

	go s.forwardTranscripts(stream)
}

func (s *Session) forwardTranscripts(stream *sttclient.Stream) {
	turn := s.currentTurn.Load()

	for event := range stream.Events {
		if s.currentTurn.Load() != turn {
			continue // stale - a barge-in landed while a few events were already buffered; drop instead of forwarding as if current
		}

		switch event.Type {
		case sttclient.EventPartial:
			s.sendJSON(ControlMessage{Type: "partial_transcript", Text: event.Text, Turn: turn})
		case sttclient.EventFinal:
			s.sendJSON(ControlMessage{Type: "final_transcript", Text: event.Text, Turn: turn})
			s.startLLMChat(event.Text, turn)
		case sttclient.EventError:
			s.sendError(event.ErrorCode, event.ErrorMessage)
		}
	}
}

func (s *Session) startLLMChat(prompt string, turn uint64) {
	// If a barge-in happened between the transcript arriving and this
	// call, currentTurn has already moved on - don't start a response
	// for a turn that's already stale.
	if s.currentTurn.Load() != turn {
		return
	}

	s.mu.Lock()
	historySnapshot := append([]llmclient.ChatMessage(nil), s.history...)
	s.mu.Unlock()

	stream, err := s.llmClient.StartChat(s.ctx, prompt, historySnapshot)
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
	var fullResponse strings.Builder

	for event := range stream.Events {
		if s.currentTurn.Load() != turn {
			// Barge-in happened mid-generation. The stream's context is
			// already cancelled by interruptCurrentTurn - just stop
			// consuming, don't queue any more TTS, don't touch history.
			return
		}

		switch event.Type {
		case llmclient.ChatEventChunk:
			fullResponse.WriteString(event.Text)

			select {
			case s.ttsQueue <- ttsJob{turn: turn, text: event.Text}:
			default:
				s.logger.Warn("tts queue full, dropping chunk")
			}

		case llmclient.ChatEventDone:
			s.mu.Lock()
			s.activeLLMStream = nil
			s.history = append(s.history,
				llmclient.ChatMessage{Role: "user", Content: prompt},
				llmclient.ChatMessage{Role: "assistant", Content: fullResponse.String()},
			)
			s.mu.Unlock()

		case llmclient.ChatEventError:
			s.sendError(event.ErrorCode, event.ErrorMessage)
		}
	}
}

func (s *Session) ttsWorker() {
	for {
		select {
		case <-s.ctx.Done():
			s.logger.Info("session cancelled")
			return
		case job, ok := <-s.ttsQueue:
			if !ok {
				s.logger.Info("session is closed exiting worker")
				return
			}
			if s.currentTurn.Load() != job.turn {
				continue // stale - dropped by interruptCurrentTurn's drain in the common case, but check again defensively
			}
			s.synthesizeAndSend(job)
		}
	}
}

func (s *Session) synthesizeAndSend(job ttsJob) {
	stream, err := s.ttsClient.Synthesize(s.ctx, job.text, s.getVoice())
	if err != nil {
		s.logger.Error("failed to start tts stream", "error", err)
		s.sendError("tts_unavailable", "could not synthesize speech")
		return
	}

	// Re-check the turn right as we're about to publish this stream.
	// ttsWorker only checked it was current BEFORE the network round
	// trip above - a barge-in landing during that call is invisible to
	// interruptCurrentTurn until the stream is actually stored here, so
	// re-checking under the same lock closes that window.
	s.mu.Lock()
	if s.currentTurn.Load() != job.turn {
		s.mu.Unlock()
		stream.Close()
		return
	}
	s.activeTTSStream = stream
	s.mu.Unlock()

	formatSent := false

	for chunk := range stream.Events {
		if s.currentTurn.Load() != job.turn {
			return
		}

		if chunk.Type == ttsclient.EventError {
			s.sendError(chunk.ErrorCode, chunk.ErrorMessage)
			return
		}

		// Send this sentence's text together with the format
		// announcement, right before its first chunk of audio, so the
		// client shows text roughly in step with what's about to be
		// spoken instead of racing far ahead of the (comparatively
		// slow) TTS pipeline. Sent per-sentence rather than once per
		// session in case different sentences ever use different
		// voices - cheap (small JSON messages) relative to the audio
		// itself.
		if !formatSent {
			s.sendJSON(ControlMessage{Type: "llm_chunk", Text: job.text, Turn: job.turn})
			s.sendJSON(ControlMessage{
				Type:        "audio_format",
				SampleRate:  chunk.SampleRate,
				Channels:    chunk.Channels,
				SampleWidth: chunk.SampleWidth,
				Turn:        job.turn,
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
	if s.sttStream.Load() == nil {
		return
	}

	// Explicitly signal end-of-utterance so the STT service flushes any
	// buffered audio as a FINAL transcript. CloseSend() alone just ends
	// the gRPC stream (Python sees a normal iterator exit) - it does
	// NOT set end_of_utterance on the last-seen chunk, so FINAL would
	// never fire without this. Enqueued (not sent directly) to preserve
	// ordering relative to any audio chunks already queued, and this
	// send is deliberately blocking (no "drop on full" default) since
	// silently dropping it means FINAL never fires.
	frame := audioFrame{format: s.getAudioFormat(), endOfUtterance: true, closeSend: true}
	select {
	case s.audioQueue <- frame:
	case <-s.ctx.Done():
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
	case <-s.ctx.Done():
	default:
		s.logger.Warn("send buffer full, dropping message")
	}
}

func (s *Session) sendError(code, message string) {
	s.sendJSON(ControlMessage{Type: "error", Code: code, Message: message})
}

func (s *Session) writePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		s.conn.Close()
	}()

	for {
		select {
		case <-s.ctx.Done():
			s.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := s.conn.WriteMessage(websocket.CloseMessage,
				websocket.FormatCloseMessage(websocket.CloseNormalClosure, "")); err != nil {
				s.logger.Debug("failed to send close frame", "error", err)
			}
			return

		case msg := <-s.send:
			s.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := s.conn.WriteMessage(msg.frameType, msg.data); err != nil {
				s.logger.Error("write failed", "error", err)
				return
			}

		case <-ticker.C:
			s.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := s.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				s.logger.Warn("ping failed", "error", err)
				return
			}
		}
	}
}

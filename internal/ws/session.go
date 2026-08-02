package ws

import (
	"context"
	"encoding/json"
	"log/slog"
	"strings"
	"time"

	"github.com/gorilla/websocket"

	sttclient "github.com/mugen64/bibi-core/internal/stt"
	sttpb "github.com/mugen64/bibi-core/internal/stt/pb"

	llmclient "github.com/mugen64/bibi-core/internal/llm"
	llmpb "github.com/mugen64/bibi-core/internal/llm/pb"

	ttsclient "github.com/mugen64/bibi-core/internal/tts"
)

const (
	writeWait      = 10 * time.Second
	pongWait       = 60 * time.Second
	pingPeriod     = (pongWait * 9) / 10
	maxMessageSize = 1 << 20 // 1MB - generous for a few seconds of PCM audio
)

// ControlMessage is the JSON envelope for text frames in both directions.
type ControlMessage struct {
	Type    string `json:"type"`
	Text    string `json:"text,omitempty"`
	Code    string `json:"code,omitempty"`
	Message string `json:"message,omitempty"`
}

// Session wraps one client's WebSocket connection and owns its lifecycle.
type Session struct {
	conn      *websocket.Conn
	send      chan outboundMessage // outgoing frames (JSON or binary), queued for the write pump
	sttClient *sttclient.STTClient
	sttStream *sttclient.STTStream
	llmClient *llmclient.Client
	ttsClient *ttsclient.Client
	history   []llmclient.ChatMessage // running conversation, in-memory per session
	ttsQueue  chan string             // sentence chunks awaiting synthesis, processed in order
	ctx       context.Context
	cancel    context.CancelFunc
	logger    *slog.Logger
}

type outboundMessage struct {
	frameType int // websocket.TextMessage or websocket.BinaryMessage
	data      []byte
}

func NewSession(conn *websocket.Conn, sttClient *sttclient.STTClient, llmClient *llmclient.Client, ttsClient *ttsclient.Client) *Session {
	ctx, cancel := context.WithCancel(context.Background())
	s := &Session{
		conn:      conn,
		send:      make(chan outboundMessage, 32),
		sttClient: sttClient,
		llmClient: llmClient,
		ttsClient: ttsClient,
		ttsQueue:  make(chan string, 32),
		ctx:       ctx,
		cancel:    cancel,
		logger:    slog.With("component", "ws_session"),
	}
	go s.ttsWorker() // one worker, processes the queue strictly in order
	return s
}

func (s *Session) Run() {
	go s.writePump()
	s.readPump()
	s.cancel() // ensure any open STT stream is torn down on disconnect
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
		s.sendError("no_active_stream", "send {\"type\":\"start\"} before audio")
		return
	}

	// ASSUMPTION: 16kHz mono 16-bit PCM. Adjust if your client sends
	// something else, or negotiate this in the "start" message instead
	// of hardcoding it.
	err := s.sttStream.SendAudio(data, 16000, 1, 2, false)
	if err != nil {
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
		s.startSTTStream()
	case "end_utterance":
		s.endUtterance()
	default:
		s.sendError("unknown_message_type", "unrecognized control message type: "+msg.Type)
	}
}

func (s *Session) startSTTStream() {
	if s.sttStream != nil {
		s.sttStream.Close() // replace any stale stream
	}

	stream, err := s.sttClient.OpenStream(s.ctx)
	if err != nil {
		s.logger.Error("failed to open stt stream", "error", err)
		s.sendError("stt_unavailable", "could not start transcription")
		return
	}
	s.sttStream = stream

	// Dedicated goroutine forwards transcript events from the STT
	// service back to the client over the WebSocket, as they arrive.
	go s.forwardTranscripts(stream)
}

func (s *Session) forwardTranscripts(stream *sttclient.STTStream) {
	for event := range stream.Events {
		switch event.Type {
		case sttpb.TranscriptEvent_PARTIAL:
			s.sendJSON(ControlMessage{Type: "partial_transcript", Text: joinSegments(event)})
		case sttpb.TranscriptEvent_FINAL:
			text := joinSegments(event)
			s.sendJSON(ControlMessage{Type: "final_transcript", Text: text})
			s.startLLMChat(text)
		case sttpb.TranscriptEvent_ERROR:
			s.sendError(event.ErrorCode, event.ErrorMessage)
		}
	}
}

func joinSegments(event *sttpb.TranscriptEvent) string {
	text := ""
	for _, seg := range event.Segments {
		text += seg.Text
	}
	return text
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

func (s *Session) startLLMChat(prompt string) {
	stream, err := s.llmClient.StartChat(s.ctx, prompt, s.history)
	if err != nil {
		s.logger.Error("failed to start llm stream", "error", err)
		s.sendError("llm_unavailable", "could not start chat response")
		return
	}

	go s.forwardLLMEvents(stream, prompt)
}

func (s *Session) forwardLLMEvents(stream *llmclient.Stream, prompt string) {
	var fullResponse strings.Builder

	for event := range stream.Events {
		switch event.Type {
		case llmpb.ChatEvent_CHUNK:
			fullResponse.WriteString(event.Text)
			s.sendJSON(ControlMessage{Type: "llm_chunk", Text: event.Text})

			// Queue this sentence for TTS. Non-blocking send with a
			// fallback log rather than blocking forwardLLMEvents if
			// the tts worker is somehow backed up.
			select {
			case s.ttsQueue <- event.Text:
			default:
				s.logger.Warn("tts queue full, dropping chunk")
			}

		case llmpb.ChatEvent_DONE:
			s.history = append(s.history,
				llmclient.ChatMessage{Role: "user", Content: prompt},
				llmclient.ChatMessage{Role: "assistant", Content: fullResponse.String()},
			)

		case llmpb.ChatEvent_ERROR:
			s.sendError(event.ErrorCode, event.ErrorMessage)
		}
	}
}

// ttsWorker is the ONLY goroutine that calls ttsClient.Synthesize. By
// pulling from ttsQueue one item at a time and fully draining each
// stream's audio before moving to the next, sentence playback order
// is guaranteed regardless of how fast each individual TTS call runs.
func (s *Session) ttsWorker() {
	for {
		select {
		case <-s.ctx.Done():
			return
		case text, ok := <-s.ttsQueue:
			if !ok {
				return
			}
			s.synthesizeAndSend(text)
		}
	}
}

func (s *Session) synthesizeAndSend(text string) {
	stream, err := s.ttsClient.Synthesize(s.ctx, text, "" /* voice - default for now */)
	if err != nil {
		s.logger.Error("failed to start tts stream", "error", err)
		s.sendError("tts_unavailable", "could not synthesize speech")
		return
	}

	// Drain this sentence's audio fully before returning to the loop -
	// this is what enforces ordering against the next queued sentence.
	for chunk := range stream.Events {
		select {
		case s.send <- outboundMessage{frameType: websocket.BinaryMessage, data: chunk.Data}:
		case <-s.ctx.Done():
			return
		}
	}
}

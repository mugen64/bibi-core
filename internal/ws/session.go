package ws

import (
	"encoding/json"
	"log/slog"
	"time"

	"github.com/gorilla/websocket"
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
	conn   *websocket.Conn
	send   chan []byte // outgoing frames (JSON or binary), queued for the write pump
	logger *slog.Logger
}

func NewSession(conn *websocket.Conn) *Session {
	return &Session{
		conn:   conn,
		send:   make(chan []byte, 32),
		logger: slog.With("component", "ws_session"),
	}
}

// Run starts the read and write pumps and blocks until the connection closes.
// Call this in a goroutine per connection.
func (s *Session) Run() {
	go s.writePump()
	s.readPump() // blocks until connection closes or errors
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
	// Placeholder for now - next step wires this into the STT gRPC stream.
	s.logger.Info("received audio chunk", "bytes", len(data))
}

func (s *Session) handleControlMessage(data []byte) {
	var msg ControlMessage
	if err := json.Unmarshal(data, &msg); err != nil {
		s.logger.Warn("malformed control message", "error", err)
		s.sendError("bad_request", "malformed control message")
		return
	}

	s.logger.Info("received control message", "type", msg.Type)

	switch msg.Type {
	case "start":
		// Next step: open the STT gRPC stream here
	case "end_utterance":
		// Next step: signal STT that the utterance is complete,
		// trigger the LLM call with the final transcript
	default:
		s.sendError("unknown_message_type", "unrecognized control message type: "+msg.Type)
	}
}

// sendJSON queues a control message to the client.
func (s *Session) sendJSON(msg ControlMessage) {
	data, err := json.Marshal(msg)
	if err != nil {
		s.logger.Error("failed to marshal outgoing message", "error", err)
		return
	}
	select {
	case s.send <- data:
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
		case data, ok := <-s.send:
			s.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				s.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			// Control messages are JSON text; TTS audio (later) will be
			// binary - for now everything routed through send is JSON.
			if err := s.conn.WriteMessage(websocket.TextMessage, data); err != nil {
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

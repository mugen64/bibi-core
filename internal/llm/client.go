package llm

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"sync/atomic"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/keepalive"

	llmpb "github.com/mugen64/bibi-core/internal/llm/pb"
)

// Client holds the long-lived connection to the LLM service.
type Client struct {
	conn        *grpc.ClientConn
	client      llmpb.LLMChatClient
	idleTimeout time.Duration
}

func NewClient(addr string, idleTimeout time.Duration) (*Client, error) {
	conn, err := grpc.NewClient(addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithKeepaliveParams(keepalive.ClientParameters{
			Time:    20 * time.Second,
			Timeout: 5 * time.Second,
			// PermitWithoutStream deliberately left false (the default):
			// grpcio's server-side enforcement policy treats pings sent
			// with no active RPC as abusive and responds with a GoAway
			// ("too_many_pings") - confirmed against the real Python
			// services. What we actually need (detecting a dead
			// connection during an in-flight stream) doesn't require it.
		}),
	)
	if err != nil {
		return nil, fmt.Errorf("dial llm service: %w", err)
	}
	return &Client{
		conn:        conn,
		client:      llmpb.NewLLMChatClient(conn),
		idleTimeout: idleTimeout,
	}, nil
}

func (c *Client) Close() error {
	return c.conn.Close()
}

// ChatMessage mirrors llmpb.ChatMessage, kept here so callers outside
// this package don't need to import the generated pb types directly.
type ChatMessage struct {
	Role    string
	Content string
}

type ChatEventType int

const (
	ChatEventChunk ChatEventType = iota
	ChatEventDone
	ChatEventError
)

// ChatEvent mirrors llmpb.ChatEvent, but can also carry a terminal
// error that didn't come from the Python service itself (e.g. the
// stream died or went idle) - callers only ever need to look at this
// one type, never the generated pb type.
type ChatEvent struct {
	Type         ChatEventType
	Text         string
	ErrorCode    string
	ErrorMessage string
}

// Stream wraps ONE StreamChat call. Server-streaming only, so there's
// just a recv side to manage - no Send() needed once the request is issued.
type Stream struct {
	stream         llmpb.LLMChat_StreamChatClient
	Events         chan ChatEvent
	cancel         context.CancelFunc
	logger         *slog.Logger
	idleTimeout    time.Duration
	closedByCaller atomic.Bool
}

// StartChat sends the prompt + history and opens the streaming response.
// Pass the parent context from the WebSocket session so client
// disconnects cancel the in-flight LLM generation too.
func (c *Client) StartChat(ctx context.Context, prompt string, history []ChatMessage) (*Stream, error) {
	ctx, cancel := context.WithCancel(ctx)

	pbHistory := make([]*llmpb.ChatMessage, len(history))
	for i, m := range history {
		pbHistory[i] = &llmpb.ChatMessage{Role: m.Role, Content: m.Content}
	}

	stream, err := c.client.StreamChat(ctx, &llmpb.ChatRequest{
		Prompt:              prompt,
		ConversationHistory: pbHistory,
	})
	if err != nil {
		cancel()
		return nil, fmt.Errorf("start llm stream: %w", err)
	}

	s := &Stream{
		stream:      stream,
		Events:      make(chan ChatEvent, 16),
		cancel:      cancel,
		logger:      slog.With("component", "llm_stream"),
		idleTimeout: c.idleTimeout,
	}

	go s.recvPump()
	return s, nil
}

// recvPump is the ONLY goroutine allowed to call stream.Recv(). It
// forwards every ChatEvent onto the Events channel until the server
// closes the stream, an error occurs, or the backend goes idle for
// longer than idleTimeout (a wedged Python service would otherwise
// stall this stream forever).
func (s *Stream) recvPump() {
	defer close(s.Events)

	type recvResult struct {
		event *llmpb.ChatEvent
		err   error
	}

	for {
		recvCh := make(chan recvResult, 1)
		go func() {
			event, err := s.stream.Recv()
			recvCh <- recvResult{event, err}
		}()

		select {
		case res := <-recvCh:
			if res.err != nil {
				switch {
				case res.err == io.EOF:
					s.logger.Info("llm stream closed by server")
				case s.closedByCaller.Load():
					s.logger.Info("llm stream closed by caller")
				default:
					s.logger.Warn("llm stream recv error", "error", res.err)
					s.emitError("llm_stream_error", res.err.Error())
				}
				return
			}

			select {
			case s.Events <- mapChatEvent(res.event):
			case <-s.stream.Context().Done():
				return
			}

		case <-time.After(s.idleTimeout):
			s.logger.Warn("llm stream idle timeout, cancelling")
			s.cancel()
			s.emitError("llm_timeout", "llm service did not respond in time")
			return

		case <-s.stream.Context().Done():
			return
		}
	}
}

// emitError is a best-effort, non-blocking send so a caller that's
// already stopped reading Events can never hang this goroutine's exit.
func (s *Stream) emitError(code, msg string) {
	select {
	case s.Events <- ChatEvent{Type: ChatEventError, ErrorCode: code, ErrorMessage: msg}:
	default:
	}
}

func mapChatEvent(e *llmpb.ChatEvent) ChatEvent {
	switch e.Type {
	case llmpb.ChatEvent_DONE:
		return ChatEvent{Type: ChatEventDone}
	case llmpb.ChatEvent_ERROR:
		return ChatEvent{Type: ChatEventError, ErrorCode: e.ErrorCode, ErrorMessage: e.ErrorMessage}
	default: // CHUNK
		return ChatEvent{Type: ChatEventChunk, Text: e.Text}
	}
}

// Close cancels the stream (e.g. client disconnected, or barge-in
// should stop generation early).
func (s *Stream) Close() {
	s.closedByCaller.Store(true)
	s.cancel()
}

func (c *Client) HealthCheck(ctx context.Context) (*llmpb.HealthResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()

	resp, err := c.client.HealthCheck(ctx, &llmpb.HealthRequest{})
	if err != nil {
		return nil, fmt.Errorf("llm health check: %w", err)
	}
	return resp, nil
}

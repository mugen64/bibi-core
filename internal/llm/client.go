package llm

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	llmpb "github.com/mugen64/bibi-core/internal/llm/pb"
)

// Client holds the long-lived connection to the LLM service.
type Client struct {
	conn   *grpc.ClientConn
	client llmpb.LLMChatClient
}

func NewClient(addr string) (*Client, error) {
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, fmt.Errorf("dial llm service: %w", err)
	}
	return &Client{
		conn:   conn,
		client: llmpb.NewLLMChatClient(conn),
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

// Stream wraps ONE StreamChat call. Server-streaming only, so there's
// just a recv side to manage - no Send() needed once the request is issued.
type Stream struct {
	stream llmpb.LLMChat_StreamChatClient
	Events chan *llmpb.ChatEvent
	cancel context.CancelFunc
	logger *slog.Logger
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
		stream: stream,
		Events: make(chan *llmpb.ChatEvent, 16),
		cancel: cancel,
		logger: slog.With("component", "llm_stream"),
	}

	go s.recvPump()
	return s, nil
}

func (s *Stream) recvPump() {
	defer close(s.Events)
	for {
		event, err := s.stream.Recv()
		if err != nil {
			if err == io.EOF {
				s.logger.Info("llm stream closed by server")
			} else {
				s.logger.Warn("llm stream recv error", "error", err)
			}
			return
		}
		s.Events <- event
	}
}

// Close cancels the stream (e.g. client disconnected, or barge-in
// should stop generation early).
func (s *Stream) Close() {
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

package stt

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"sync/atomic"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/keepalive"

	sttpb "github.com/mugen64/bibi-core/internal/stt/pb"
)

var ErrStreamClosed = errors.New("stt stream already closed")

type Client struct {
	conn        *grpc.ClientConn
	client      sttpb.SpeechToTextClient
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
		return nil, fmt.Errorf("dial stt service: %w", err)
	}
	return &Client{
		conn:        conn,
		client:      sttpb.NewSpeechToTextClient(conn),
		idleTimeout: idleTimeout,
	}, nil
}

func (c *Client) Close() error {
	return c.conn.Close()
}

type EventType int

const (
	EventPartial EventType = iota
	EventFinal
	EventError
)

// TranscriptEvent mirrors sttpb.TranscriptEvent, but can also carry a
// terminal error that didn't come from the Python service itself (e.g.
// the stream died or went idle) - callers only ever need to look at
// this one type, never the generated pb type.
type TranscriptEvent struct {
	Type         EventType
	Text         string
	ErrorCode    string
	ErrorMessage string
}

// Stream wraps ONE bidirectional transcription call, scoped to a
// single WebSocket session/utterance. Same read/write-pump idea as the
// WebSocket session - one goroutine only ever calls stream.Recv(),
// callers push outgoing audio via SendAudio().
type Stream struct {
	stream      sttpb.SpeechToText_StreamTranscribeClient
	Events      chan TranscriptEvent
	cancel      context.CancelFunc
	logger      *slog.Logger
	idleTimeout time.Duration
	// closed is "the caller intentionally ended this stream" - set by
	// both CloseSend() (graceful half-close) and Close() (hard abort),
	// and doubles as the signal recvPump uses to suppress a synthetic
	// error event for an intentional shutdown.
	closed atomic.Bool
}

// OpenStream starts a new bidirectional call. Pass the parent context
// from the WebSocket connection so that if the client disconnects,
// this stream is cancelled automatically too.
func (c *Client) OpenStream(ctx context.Context) (*Stream, error) {
	ctx, cancel := context.WithCancel(ctx)

	stream, err := c.client.StreamTranscribe(ctx)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("open stt stream: %w", err)
	}

	s := &Stream{
		stream:      stream,
		Events:      make(chan TranscriptEvent, 16),
		cancel:      cancel,
		logger:      slog.With("component", "stt_stream"),
		idleTimeout: c.idleTimeout,
	}

	go s.recvPump()
	return s, nil
}

// SendAudio pushes one audio chunk into the stream. Safe to call
// repeatedly as new mic data arrives from the WebSocket.
func (s *Stream) SendAudio(data []byte, sampleRate, channels, sampleWidth int32, endOfUtterance bool) error {
	if s.closed.Load() {
		return ErrStreamClosed
	}
	return s.stream.Send(&sttpb.AudioChunkMsg{
		Data:           data,
		SampleRate:     sampleRate,
		Channels:       channels,
		SampleWidth:    sampleWidth,
		EndOfUtterance: endOfUtterance,
	})
}

// recvPump is the ONLY goroutine allowed to call stream.Recv(). It
// forwards every TranscriptEvent onto the Events channel until the
// server closes the stream, an error occurs, or the backend goes idle
// for longer than idleTimeout (a wedged Python service would otherwise
// stall this stream forever).
func (s *Stream) recvPump() {
	defer close(s.Events)

	type recvResult struct {
		event *sttpb.TranscriptEvent
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
					s.logger.Info("stt stream closed by server")
				case s.closed.Load():
					s.logger.Info("stt stream closed by caller")
				default:
					s.logger.Warn("stt stream recv error", "error", res.err)
					s.emitError("stt_stream_error", res.err.Error())
				}
				return
			}

			select {
			case s.Events <- mapTranscriptEvent(res.event):
			case <-s.stream.Context().Done():
				return
			}

		case <-time.After(s.idleTimeout):
			s.logger.Warn("stt stream idle timeout, cancelling")
			s.cancel()
			s.emitError("stt_timeout", "stt service did not respond in time")
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
	case s.Events <- TranscriptEvent{Type: EventError, ErrorCode: code, ErrorMessage: msg}:
	default:
	}
}

func mapTranscriptEvent(e *sttpb.TranscriptEvent) TranscriptEvent {
	switch e.Type {
	case sttpb.TranscriptEvent_FINAL:
		return TranscriptEvent{Type: EventFinal, Text: joinSegments(e)}
	case sttpb.TranscriptEvent_ERROR:
		return TranscriptEvent{Type: EventError, ErrorCode: e.ErrorCode, ErrorMessage: e.ErrorMessage}
	default: // PARTIAL
		return TranscriptEvent{Type: EventPartial, Text: joinSegments(e)}
	}
}

func joinSegments(event *sttpb.TranscriptEvent) string {
	var text strings.Builder
	for _, seg := range event.Segments {
		text.WriteString(seg.Text)
	}
	return text.String()
}

// CloseSend signals "no more audio coming" without tearing down the
// stream - lets the server finish emitting any final transcript first.
func (s *Stream) CloseSend() error {
	s.closed.Store(true)
	return s.stream.CloseSend()
}

// Close cancels the stream immediately (e.g. client disconnected).
func (s *Stream) Close() {
	s.closed.Store(true)
	s.cancel()
}

// Closed reports whether CloseSend or Close has been called on this
// stream. SendAudio's own closed-check and a concurrent Close() aren't
// perfectly atomic relative to each other, so a Send() that raced past
// the check can still return a raw transport error instead of
// ErrStreamClosed - callers that want to treat "this stream is gone"
// uniformly regardless of which error came back should check this too.
func (s *Stream) Closed() bool {
	return s.closed.Load()
}

// HealthCheck queries the underlying service's health. Takes its own
// short timeout so a hung/unreachable service doesn't stall the
// gateway's aggregated /health endpoint.
func (c *Client) HealthCheck(ctx context.Context) (*sttpb.HealthResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()

	resp, err := c.client.HealthCheck(ctx, &sttpb.HealthRequest{})
	if err != nil {
		return nil, fmt.Errorf("stt health check: %w", err)
	}
	return resp, nil
}

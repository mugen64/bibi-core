package tts

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

	ttspb "github.com/mugen64/bibi-core/internal/tts/pb"
)

type Client struct {
	conn        *grpc.ClientConn
	client      ttspb.TextToSpeechClient
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
		return nil, fmt.Errorf("dial tts service: %w", err)
	}
	return &Client{
		conn:        conn,
		client:      ttspb.NewTextToSpeechClient(conn),
		idleTimeout: idleTimeout,
	}, nil
}

func (c *Client) Close() error {
	return c.conn.Close()
}

type EventType int

const (
	EventAudio EventType = iota
	EventError
)

// AudioChunk mirrors ttspb.AudioChunkMsg, but can also carry a
// terminal error that didn't come from the Python service itself (e.g.
// the stream died or went idle) - kept here so callers outside this
// package don't need to import generated pb types directly.
type AudioChunk struct {
	Type         EventType
	Data         []byte
	SampleRate   int32
	Channels     int32
	SampleWidth  int32
	ErrorCode    string
	ErrorMessage string
}

type Stream struct {
	stream         ttspb.TextToSpeech_StreamSynthesizeClient
	Events         chan *AudioChunk
	cancel         context.CancelFunc
	logger         *slog.Logger
	idleTimeout    time.Duration
	closedByCaller atomic.Bool
}

// Synthesize sends one chunk of text and opens the streaming audio
// response. voice can be "" to use the service's default.
func (c *Client) Synthesize(ctx context.Context, text, voice string) (*Stream, error) {
	ctx, cancel := context.WithCancel(ctx)

	var voicePtr *string
	if voice != "" {
		voicePtr = &voice
	}

	stream, err := c.client.StreamSynthesize(ctx, &ttspb.SynthesizeRequest{
		Text:  text,
		Voice: voicePtr,
	})
	if err != nil {
		cancel()
		return nil, fmt.Errorf("start tts stream: %w", err)
	}

	s := &Stream{
		stream:      stream,
		Events:      make(chan *AudioChunk, 16),
		cancel:      cancel,
		logger:      slog.With("component", "tts_stream"),
		idleTimeout: c.idleTimeout,
	}

	go s.recvPump()
	return s, nil
}

// recvPump is the ONLY goroutine allowed to call stream.Recv(). It
// forwards every AudioChunk onto the Events channel until the server
// closes the stream, an error occurs, or the backend goes idle for
// longer than idleTimeout (a wedged Python service would otherwise
// stall this stream forever).
func (s *Stream) recvPump() {
	defer close(s.Events)

	type recvResult struct {
		msg *ttspb.AudioChunkMsg
		err error
	}

	for {
		recvCh := make(chan recvResult, 1)
		go func() {
			msg, err := s.stream.Recv()
			recvCh <- recvResult{msg, err}
		}()

		select {
		case res := <-recvCh:
			if res.err != nil {
				switch {
				case res.err == io.EOF:
					s.logger.Info("tts stream closed by server")
				case s.closedByCaller.Load():
					s.logger.Info("tts stream closed by caller")
				default:
					s.logger.Warn("tts stream recv error", "error", res.err)
					s.emitError("tts_stream_error", res.err.Error())
				}
				return
			}

			chunk := &AudioChunk{
				Type:        EventAudio,
				Data:        res.msg.Data,
				SampleRate:  res.msg.SampleRate,
				Channels:    res.msg.Channels,
				SampleWidth: res.msg.SampleWidth,
			}
			select {
			case s.Events <- chunk:
			case <-s.stream.Context().Done():
				return
			}

		case <-time.After(s.idleTimeout):
			s.logger.Warn("tts stream idle timeout, cancelling")
			s.cancel()
			s.emitError("tts_timeout", "tts service did not respond in time")
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
	case s.Events <- &AudioChunk{Type: EventError, ErrorCode: code, ErrorMessage: msg}:
	default:
	}
}

func (s *Stream) Close() {
	s.closedByCaller.Store(true)
	s.cancel()
}

func (c *Client) HealthCheck(ctx context.Context) (*ttspb.HealthResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()

	resp, err := c.client.HealthCheck(ctx, &ttspb.HealthRequest{})
	if err != nil {
		return nil, fmt.Errorf("tts health check: %w", err)
	}
	return resp, nil
}

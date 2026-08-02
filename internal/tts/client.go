package tts

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	ttspb "github.com/mugen64/bibi-core/internal/tts/pb"
)

type Client struct {
	conn   *grpc.ClientConn
	client ttspb.TextToSpeechClient
}

func NewClient(addr string) (*Client, error) {
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, fmt.Errorf("dial tts service: %w", err)
	}
	return &Client{
		conn:   conn,
		client: ttspb.NewTextToSpeechClient(conn),
	}, nil
}

func (c *Client) Close() error {
	return c.conn.Close()
}

// AudioChunk mirrors ttspb.AudioChunkMsg, kept here so callers outside
// this package don't need to import generated pb types directly.
type AudioChunk struct {
	Data        []byte
	SampleRate  int32
	Channels    int32
	SampleWidth int32
}

type Stream struct {
	stream ttspb.TextToSpeech_StreamSynthesizeClient
	Events chan *AudioChunk
	cancel context.CancelFunc
	logger *slog.Logger
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
		stream: stream,
		Events: make(chan *AudioChunk, 16),
		cancel: cancel,
		logger: slog.With("component", "tts_stream"),
	}

	go s.recvPump()
	return s, nil
}

func (s *Stream) recvPump() {
	defer close(s.Events)
	for {
		msg, err := s.stream.Recv()
		if err != nil {
			if err == io.EOF {
				s.logger.Info("tts stream closed by server")
			} else {
				s.logger.Warn("tts stream recv error", "error", err)
			}
			return
		}
		s.Events <- &AudioChunk{
			Data:        msg.Data,
			SampleRate:  msg.SampleRate,
			Channels:    msg.Channels,
			SampleWidth: msg.SampleWidth,
		}
	}
}

func (s *Stream) Close() {
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

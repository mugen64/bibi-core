package stt

import (
	"context"
	"fmt"
	"io"
	"log/slog"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	sttpb "github.com/mugen64/bibi-core/internal/stt/pb"
)

type Client struct {
	conn   *grpc.ClientConn
	client sttpb.SpeechToTextClient
}

func NewClient(addr string) (*Client, error) {
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, fmt.Errorf("dial stt service: %w", err)
	}
	return &Client{
		conn:   conn,
		client: sttpb.NewSpeechToTextClient(conn),
	}, nil
}

func (c *Client) Close() error {
	return c.conn.Close()
}

// STTStream wraps ONE bidirectional transcription call, scoped to a
// single WebSocket session/utterance. Same read/write-pump idea as the
// WebSocket session - one goroutine only ever calls stream.Recv(),
// callers push outgoing audio via SendAudio().
type STTStream struct {
	stream sttpb.SpeechToText_StreamTranscribeClient
	Events chan *sttpb.TranscriptEvent
	cancel context.CancelFunc
	logger *slog.Logger
}

// OpenStream starts a new bidirectional call. Pass the parent context
// from the WebSocket connection so that if the client disconnects,
// this stream is cancelled automatically too.
func (c *Client) OpenStream(ctx context.Context) (*STTStream, error) {
	ctx, cancel := context.WithCancel(ctx)

	stream, err := c.client.StreamTranscribe(ctx)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("open stt stream: %w", err)
	}

	s := &STTStream{
		stream: stream,
		Events: make(chan *sttpb.TranscriptEvent, 16),
		cancel: cancel,
		logger: slog.With("component", "stt_stream"),
	}

	go s.recvPump()
	return s, nil
}

// SendAudio pushes one audio chunk into the stream. Safe to call
// repeatedly as new mic data arrives from the WebSocket.
func (s *STTStream) SendAudio(data []byte, sampleRate, channels, sampleWidth int32, endOfUtterance bool) error {
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
// server closes the stream or an error occurs.
func (s *STTStream) recvPump() {
	defer close(s.Events)
	for {
		event, err := s.stream.Recv()
		if err != nil {
			if err == io.EOF {
				s.logger.Info("stt stream closed by server")
			} else {
				s.logger.Warn("stt stream recv error", "error", err)
			}
			return
		}
		s.Events <- event
	}
}

// CloseSend signals "no more audio coming" without tearing down the
// stream - lets the server finish emitting any final transcript first.
func (s *STTStream) CloseSend() error {
	return s.stream.CloseSend()
}

// Close cancels the stream immediately (e.g. client disconnected).
func (s *STTStream) Close() {
	s.cancel()
}

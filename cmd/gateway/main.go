package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"fmt"

	"github.com/mugen64/bibi-core/internal/config"
	"github.com/mugen64/bibi-core/internal/health"
	llmclient "github.com/mugen64/bibi-core/internal/llm"
	"github.com/mugen64/bibi-core/internal/proxy"
	sttclient "github.com/mugen64/bibi-core/internal/stt"
	ttsclient "github.com/mugen64/bibi-core/internal/tts"

	"github.com/mugen64/bibi-core/internal/ws"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	cfg, err := config.Load("gateway.toml")
	if err != nil {
		slog.Error("failed to load config", "error", err)
		os.Exit(1)
	}

	sttClient, err := sttclient.NewClient(cfg.Services.STTAddr)
	if err != nil {
		slog.Error("failed to connect to stt service", "error", err)
		os.Exit(1)
	}
	defer sttClient.Close()

	llmClient, err := llmclient.NewClient(cfg.Services.LLMAddr)
	if err != nil {
		slog.Error("failed to connect to llm service", "error", err)
		os.Exit(1)
	}
	defer llmClient.Close()

	ttsClient, err := ttsclient.NewClient(cfg.Services.TTSAddr)
	if err != nil {
		slog.Error("failed to connect to tts service", "error", err)
		os.Exit(1)
	}
	defer ttsClient.Close()

	healthAggregator := health.NewAggregator(sttClient, llmClient, ttsClient)

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler(healthAggregator))
	mux.HandleFunc("/ws", ws.NewHandler(sttClient, llmClient, ttsClient))

	mux.Handle("/api/stt/", proxy.NewServiceProxy("stt", cfg.Services.STTHTTPAddr, "/api/stt"))
	mux.Handle("/api/llm/", proxy.NewServiceProxy("llm", cfg.Services.LLMHTTPAddr, "/api/llm"))
	mux.Handle("/api/tts/", proxy.NewServiceProxy("tts", cfg.Services.TTSHTTPAddr, "/api/tts"))

	addr := cfg.Server.Host + ":" + itoa(cfg.Server.Port)
	srv := &http.Server{
		Addr:    addr,
		Handler: mux,
	}

	// Run server in a goroutine so we can listen for shutdown signals
	// on the main goroutine below.
	go func() {
		slog.Info("gateway listening", "addr", addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("server error", "error", err)
			os.Exit(1)
		}
	}()

	// Graceful shutdown: wait for SIGINT/SIGTERM, then give in-flight
	// requests (e.g. an active streaming dictation session) time to
	// finish before killing the process.
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	slog.Info("shutting down gracefully")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		slog.Error("forced shutdown", "error", err)
	}
}

func healthHandler(agg *health.Aggregator) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		report := agg.Check(r.Context())

		w.Header().Set("Content-Type", "application/json")
		if report.Status != "ok" {
			w.WriteHeader(http.StatusServiceUnavailable)
		} else {
			w.WriteHeader(http.StatusOK)
		}
		json.NewEncoder(w).Encode(report)
	}
}

func itoa(i int) string {
	return fmt.Sprintf("%d", i)
}

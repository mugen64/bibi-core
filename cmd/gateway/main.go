package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

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

	if err := run(); err != nil {
		slog.Error("gateway exited with error", "error", err)
		os.Exit(1)
	}
}

// run contains all of the gateway's startup/serve/shutdown logic.
// Returning an error here (instead of calling os.Exit at each failure
// site) guarantees every defer - most importantly, closing the three
// gRPC client connections - actually runs on every exit path.
func run() error {
	cfg, err := config.Load("gateway.toml")
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}

	idleTimeout := time.Duration(cfg.Services.StreamIdleTimeoutSeconds) * time.Second

	sttClient, err := sttclient.NewClient(cfg.Services.STTAddr, idleTimeout)
	if err != nil {
		return fmt.Errorf("connect to stt service: %w", err)
	}
	defer sttClient.Close()

	llmClient, err := llmclient.NewClient(cfg.Services.LLMAddr, idleTimeout)
	if err != nil {
		return fmt.Errorf("connect to llm service: %w", err)
	}
	defer llmClient.Close()

	ttsClient, err := ttsclient.NewClient(cfg.Services.TTSAddr, idleTimeout)
	if err != nil {
		return fmt.Errorf("connect to tts service: %w", err)
	}
	defer ttsClient.Close()

	healthAggregator := health.NewAggregator(sttClient, llmClient, ttsClient)

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler(healthAggregator))
	mux.HandleFunc("/", indexHandler())
	mux.HandleFunc("/assistant", assistantHandler())
	mux.Handle("/assets/", http.StripPrefix("/assets/", http.FileServer(http.Dir("site/assets"))))

	mux.HandleFunc("/ws", ws.NewHandler(sttClient, llmClient, ttsClient, cfg.Server.AllowedOrigins))

	mux.Handle("/api/stt/", proxy.NewServiceProxy("stt", cfg.Services.STTHTTPAddr, "/api/stt"))
	mux.Handle("/api/llm/", proxy.NewServiceProxy("llm", cfg.Services.LLMHTTPAddr, "/api/llm"))
	mux.Handle("/api/tts/", proxy.NewServiceProxy("tts", cfg.Services.TTSHTTPAddr, "/api/tts"))

	addr := cfg.Server.Host + ":" + strconv.Itoa(cfg.Server.Port)
	srv := &http.Server{
		Addr:              addr,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      60 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	// Run server in a goroutine so we can listen for shutdown signals
	// on the main goroutine below. Its error is reported through
	// serveErr instead of os.Exit, so the caller's defers still run.
	serveErr := make(chan error, 1)
	go func() {
		slog.Info("gateway listening", "addr", addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			serveErr <- err
			return
		}
		serveErr <- nil
	}()

	// Graceful shutdown: wait for SIGINT/SIGTERM, then give in-flight
	// requests (e.g. an active streaming dictation session) time to
	// finish before killing the process.
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case err := <-serveErr:
		if err != nil {
			return fmt.Errorf("server error: %w", err)
		}
		return nil
	case <-quit:
		slog.Info("shutting down gracefully")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		return fmt.Errorf("shutdown: %w", err)
	}

	if err := <-serveErr; err != nil {
		return fmt.Errorf("server error during shutdown: %w", err)
	}
	return nil
}

func indexHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		http.ServeFile(w, r, "site/index.html")
	}
}

func assistantHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/assistant" {
			http.NotFound(w, r)
			return
		}
		http.ServeFile(w, r, "site/assistant.html")
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
		if err := json.NewEncoder(w).Encode(report); err != nil {
			slog.Error("failed to write health response", "error", err)
		}
	}
}

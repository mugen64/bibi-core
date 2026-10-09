package config

import (
	"errors"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"

	"github.com/BurntSushi/toml"
)

type Config struct {
	Server   ServerConfig   `toml:"server"`
	Services ServicesConfig `toml:"services"`
}

type ServerConfig struct {
	Host string `toml:"host"`
	Port int    `toml:"port"`

	// Origins allowed to open a /ws connection. Empty means "allow any
	// origin" - an explicit, documented default suited to local dev,
	// not an accidental one.
	AllowedOrigins []string `toml:"allowed_origins"`
}

type ServicesConfig struct {
	STTAddr     string `toml:"stt_addr"`      // gRPC
	LLMAddr     string `toml:"llm_addr"`      // gRPC
	TTSAddr     string `toml:"tts_addr"`      // gRPC
	STTHTTPAddr string `toml:"stt_http_addr"` // HTTP - proxied
	LLMHTTPAddr string `toml:"llm_http_addr"`
	TTSHTTPAddr string `toml:"tts_http_addr"`

	// How long a gRPC stream (STT/LLM/TTS) may go without any message
	// from the backend before the gateway gives up and surfaces an
	// error to the client. Resets on every message received, so a
	// long-but-progressing response is never cut off.
	StreamIdleTimeoutSeconds int `toml:"stream_idle_timeout_seconds"`
}

func Load(path string) (*Config, error) {
	cfg := defaults()

	data, err := os.ReadFile(path)
	switch {
	case err == nil:
		if err := toml.Unmarshal(data, cfg); err != nil {
			return nil, fmt.Errorf("parse config %q: %w", path, err)
		}
	case os.IsNotExist(err):
		// No config file yet - keep built-in defaults so `go run .`
		// works before you've written a config.toml.
	default:
		return nil, fmt.Errorf("read config %q: %w", path, err)
	}

	applyEnvOverrides(cfg)

	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("invalid config: %w", err)
	}
	return cfg, nil
}

// applyEnvOverrides lets deployment env vars win over gateway.toml,
// without requiring the file to exist or be edited at all.
func applyEnvOverrides(cfg *Config) {
	if v := os.Getenv("GATEWAY_SERVER_HOST"); v != "" {
		cfg.Server.Host = v
	}
	if v := os.Getenv("GATEWAY_SERVER_PORT"); v != "" {
		if p, err := strconv.Atoi(v); err == nil {
			cfg.Server.Port = p
		}
	}
	if v := os.Getenv("GATEWAY_SERVER_ALLOWED_ORIGINS"); v != "" {
		cfg.Server.AllowedOrigins = strings.Split(v, ",")
	}
	if v := os.Getenv("GATEWAY_STT_ADDR"); v != "" {
		cfg.Services.STTAddr = v
	}
	if v := os.Getenv("GATEWAY_LLM_ADDR"); v != "" {
		cfg.Services.LLMAddr = v
	}
	if v := os.Getenv("GATEWAY_TTS_ADDR"); v != "" {
		cfg.Services.TTSAddr = v
	}
	if v := os.Getenv("GATEWAY_STT_HTTP_ADDR"); v != "" {
		cfg.Services.STTHTTPAddr = v
	}
	if v := os.Getenv("GATEWAY_LLM_HTTP_ADDR"); v != "" {
		cfg.Services.LLMHTTPAddr = v
	}
	if v := os.Getenv("GATEWAY_TTS_HTTP_ADDR"); v != "" {
		cfg.Services.TTSHTTPAddr = v
	}
	if v := os.Getenv("GATEWAY_STREAM_IDLE_TIMEOUT_SECONDS"); v != "" {
		if s, err := strconv.Atoi(v); err == nil {
			cfg.Services.StreamIdleTimeoutSeconds = s
		}
	}
}

// Validate reports every problem found at once, rather than just the
// first, so a misconfigured deployment gets a complete picture.
func (c *Config) Validate() error {
	var errs []error

	if c.Server.Host == "" {
		errs = append(errs, errors.New("server.host must not be empty"))
	}
	if c.Server.Port <= 0 || c.Server.Port > 65535 {
		errs = append(errs, fmt.Errorf("server.port must be between 1 and 65535, got %d", c.Server.Port))
	}

	addrs := []struct{ name, value string }{
		{"services.stt_addr", c.Services.STTAddr},
		{"services.llm_addr", c.Services.LLMAddr},
		{"services.tts_addr", c.Services.TTSAddr},
		{"services.stt_http_addr", c.Services.STTHTTPAddr},
		{"services.llm_http_addr", c.Services.LLMHTTPAddr},
		{"services.tts_http_addr", c.Services.TTSHTTPAddr},
	}
	for _, a := range addrs {
		if a.value == "" {
			errs = append(errs, fmt.Errorf("%s must not be empty", a.name))
			continue
		}
		if _, _, err := net.SplitHostPort(a.value); err != nil {
			errs = append(errs, fmt.Errorf("%s: invalid host:port %q: %w", a.name, a.value, err))
		}
	}

	if c.Services.StreamIdleTimeoutSeconds <= 0 {
		errs = append(errs, fmt.Errorf("services.stream_idle_timeout_seconds must be positive, got %d", c.Services.StreamIdleTimeoutSeconds))
	}

	return errors.Join(errs...)
}

func defaults() *Config {
	return &Config{
		Server: ServerConfig{Host: "0.0.0.0", Port: 8080},
		Services: ServicesConfig{
			STTAddr: "localhost:50051",
			LLMAddr: "localhost:50053",
			TTSAddr: "localhost:50050",

			STTHTTPAddr: "localhost:5001",
			LLMHTTPAddr: "localhost:5003",
			TTSHTTPAddr: "localhost:5000",

			StreamIdleTimeoutSeconds: 30,
		},
	}
}

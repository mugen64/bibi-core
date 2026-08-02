package config

import (
	"os"

	"github.com/BurntSushi/toml"
)

type Config struct {
	Server   ServerConfig   `toml:"server"`
	Services ServicesConfig `toml:"services"`
}

type ServerConfig struct {
	Host string `toml:"host"`
	Port int    `toml:"port"`
}

type ServicesConfig struct {
	STTAddr     string `toml:"stt_addr"`      // gRPC
	LLMAddr     string `toml:"llm_addr"`      // gRPC
	TTSAddr     string `toml:"tts_addr"`      // gRPC
	STTHTTPAddr string `toml:"stt_http_addr"` // HTTP - proxied
	LLMHTTPAddr string `toml:"llm_http_addr"`
	TTSHTTPAddr string `toml:"tts_http_addr"`
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		// Fall back to defaults if no config file exists yet -
		// keeps `go run .` working before you've written a config.toml
		return defaults(), nil
	}

	var cfg Config
	if err := toml.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
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
		},
	}
}

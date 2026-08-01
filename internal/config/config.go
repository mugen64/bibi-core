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
	STTAddr string `toml:"stt_addr"` // e.g. "localhost:50051" once gRPC is wired up
	LLMAddr string `toml:"llm_addr"`
	TTSAddr string `toml:"tts_addr"`
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
			STTAddr: "localhost:5001",
			LLMAddr: "localhost:5003",
			TTSAddr: "localhost:5000",
		},
	}
}

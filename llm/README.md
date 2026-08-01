# llm service

Talks to a local Ollama instance, streams responses, and chunks tokens
into sentence-sized pieces before they leave this service - so downstream
consumers (the Go gateway → TTS) always receive TTS-ready text, never
raw tokens.

## Run standalone

```bash
uv sync
uv run python main.py
```

Requires Ollama running locally (`ollama serve`) with the model set in
`config.toml` already pulled (`ollama pull llama3.1`).

## Test it

```bash
curl -N -X POST http://localhost:8002/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a short story about a robot."}'
```

You should see newline-delimited JSON chunks stream in as Ollama generates,
each one a complete sentence/clause rather than individual tokens.

## Config

See `config.toml`:
- `[ollama]` - host, model, temperature, context window
- `[chunking]` - sentence-boundary detection tuning (when to flush a
  chunk to the caller)
- `[server]` - host/port for this service

## Notes

- `engines/chunker.py` is the sentence-boundary logic - handles abbreviations
  (`Dr.`, `Mr.`) and decimal numbers (`3.14`) so they don't get mistaken for
  sentence endings. Tune `boundary_chars` / `max_chunk_chars` /
  `min_chunk_chars` in config if chunking feels too eager or too laggy.
- `/chat/stream` is HTTP+NDJSON for now for easy local testing with curl.
  Once `proto/llm.proto` is defined, this becomes a gRPC streaming endpoint
  instead - the Go gateway will consume that rather than this HTTP route.

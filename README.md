# bibi-core

A real-time voice assistant pipeline: live dictation → LLM response → spoken
reply, with support for interrupting the assistant mid-response (barge-in).

```
Browser/Client
    │  WebSocket
    ▼
Go Gateway  ──gRPC──►  stt/ (whisper.cpp)
                ├──gRPC──►  llm/ (Ollama)
                └──gRPC──►  tts/ (Piper)
```
The Go gateway (`cmd/gateway`) is the single entry point. It orchestrates three
independent Python services over gRPC and exposes everything to clients over
one WebSocket connection, plus proxied REST access to each service's own
endpoints.

See [docs/architecture.md](docs/architecture.md) for the full system design,
proto contracts, and internals. This README covers running the project and
using the gateway's routes.

## Running it

Each service is an independent `uv` project; the gateway is a Go binary. Start
all four, each in its own terminal:

```bash
cd stt && uv sync && uv run python main.py
cd llm && uv sync && uv run python main.py
cd tts && uv sync && uv run python main.py
go run ./cmd/gateway
```
The `llm/` service expects Ollama running locally with the configured model
already pulled:

```bash
ollama serve
ollama pull llama3.1   # or whatever model is set in llm/config.toml
```
Confirm everything's up:

```bash
curl http://localhost:8080/health
{"status":"ok","stt":{"healthy":true},"llm":{"healthy":true},"tts":{"healthy":true}}
```
If any service is down or unreachable, this returns HTTP `503` with `
"status":"degraded"` and per-service error detail.

## Gateway routes

The gateway runs on `:8080` by default (`gateway.toml`).

### `GET /health`

Aggregated health across all three backend services (checked concurrently). See
above for the response shape.

### `WS /ws`

The main pipeline. Connect, then exchange:

**Binary frames (client → gateway only):** raw PCM audio, 16-bit mono 16kHz.

**Text frames (JSON, both directions):**

Client sends:

```json
{"type": "start"}
```
Begins a new utterance. Send this before streaming any audio. If a previous
response (LLM generation or TTS playback) is still in flight, sending `start`
again interrupts it - this is how barge-in works: just start talking again.

```json
{"type": "end_utterance"}
```
Signals you're done speaking. Triggers the final transcript, which kicks off
the LLM call.

Gateway sends back, in order, as they become available:

```json
{"type": "partial_transcript", "text": "..."}
{"type": "final_transcript",   "text": "..."}
{"type": "llm_chunk",          "text": "..."}
{"type": "interrupted"}
{"type": "error", "code": "...", "message": "..."}
```
Synthesized speech streams back as **binary frames**, interleaved with these
messages in playback order. On `{"type": "interrupted"}`, stop playing any audio
you've already buffered client-side - the gateway can stop sending new audio,
but can't recall bytes already delivered.

**Typical exchange:**

```
client → {"type": "start"}
client → <binary PCM chunks...>
gateway → {"type": "partial_transcript", "text": "how's"}
gateway → {"type": "partial_transcript", "text": "how's the weather"}
client → {"type": "end_utterance"}
gateway → {"type": "final_transcript", "text": "how's the weather today"}
gateway → {"type": "llm_chunk", "text": "Let me check that for you."}
gateway → <binary audio...>
gateway → {"type": "llm_chunk", "text": "It looks sunny and warm today."}
gateway → <binary audio...>
```
### `GET/POST /api/stt/*`, `/api/llm/*`, `/api/tts/*`

Reverse-proxied to each service's own REST API - useful for one-off calls that
don't need the full streaming pipeline (listing available models/voices,
one-shot file transcription, etc). Requests are forwarded as-is with the 
`/api/{service}` prefix stripped.

```bash
# List available whisper models
curl http://localhost:8080/api/stt/models
# List available Piper voices
curl http://localhost:8080/api/tts/voices
# One-shot transcription of a WAV file (no streaming)
curl -X POST http://localhost:8080/api/stt/transcribe \
  -F "file=@sample.wav;type=audio/wav"
# One-shot text-to-speech, returns a WAV file
curl -X POST http://localhost:8080/api/tts/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello there", "format": "wav"}' \
  --output out.wav
# One-shot LLM chat (non-streaming HTTP fallback)
curl -X POST http://localhost:8080/api/llm/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me a short story"}'
```
Note: WebSocket upgrade requests are **not** proxied through `/api/*` \- each
service's own standalone WebSocket routes (`stt: /transcribe-stream`, `tts:
/tts-stream`) exist for direct, single-service testing only and aren't reachable
through the gateway. Use `/ws` for the real pipeline.

## Config

Gateway: `gateway.toml` (server host/port, backend service addresses - both gRPC
and HTTP - for stt/llm/tts).

Each Python service: `\<service>/config.toml` (model/voice selection, its own
host/ports).

## Regenerating protobuf code

After changing anything in `proto/`:

```bash
./scripts/proto-gen.sh
```
See [docs/architecture.md](docs/architecture.md#regenerating-protobuf-code) for
prerequisites.



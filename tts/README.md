# tts service

Synthesizes speech from text via Piper, exposed over both HTTP and gRPC
(the gRPC side is what the Go gateway talks to; HTTP is for local
testing/manual use).

## Run standalone

```bash
uv sync
uv run python main.py
```

Requires at least one Piper voice present under `voices/` (an `.onnx`
model plus its matching `.onnx.json` config). A few are already checked
into `voices/`.

## Test it

```bash
curl -X POST http://localhost:5000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello there.", "voice": "en_US-lessac-medium.onnx", "format": "wav"}' \
  --output out.wav

curl http://localhost:5000/voices
```

`/tts-stream` is a WebSocket route that streams raw PCM chunks as they're
synthesized, for lower-latency playback than waiting for the full `/tts`
response.

## Config

See `config.toml`:
- `[engine]` - `provider`: which `TTSEngine` implementation to use
  (`piper`, or `mock` for local dev/testing without any voice files -
  see `engines/mock_engine.py`)
- `[voices]` - voice directory, default voice, `max_loaded` (how many
  Piper voices to keep warm in memory at once - least-recently-used
  ones get evicted once that cap is exceeded)
- `[piper]` - Piper-specific tuning (sample rate)
- `[server]` - host/port/log_level for this service

## Notes

- `engine_manager.py` is a small LRU cache over loaded voice engines,
  keyed by voice name, with ref-counting so a voice actively mid-stream
  is never evicted. `acquire_engine()` is the sync entry point (used by
  the thread-pooled `/tts` route); `aacquire_engine()` is the async-safe
  equivalent (used by the websocket route and the gRPC servicer) - it
  offloads a cold voice load to a thread so it never blocks the event
  loop.
- Adding a new TTS backend means writing a class that implements
  `engines/base.py`'s `TTSEngine` and registering it in
  `engines/factory.py` - nothing else needs to change.
- `output/` holds the streaming sinks (`HttpAudioSink` for the websocket
  route, `HostAudioSink` for local playback via `play_stream.py`,
  `BufferSink` for accumulating into memory). All of them consume an
  **async** iterable of `AudioChunk`s - wrap a provider's (sync)
  `engine.stream()` generator with `utils/async_io.iter_in_thread()`
  before handing it to a sink.
- `utils/text.py`'s `strip_markdown()` runs before synthesis so Piper
  doesn't vocalize symbols like `*` or `#` when the input is LLM output.

## Tests

```bash
uv run pytest
```

Covers `strip_markdown`, the `engine_manager` cache/eviction/ref-counting
logic (via the `mock` provider, no real voice files needed), the
provider factory, and the output sinks.

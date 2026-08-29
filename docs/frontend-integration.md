# Frontend integration guide

This guide describes the public client-facing API exposed by the bibi-core Go
gateway. Frontends should connect to the gateway, not directly to the Python
STT, LLM, or TTS services.

## Choose the right API

| Product | Recommended API | Why |
| --- | --- | --- |
| Real-time voice assistant | `WS /ws` | One connection handles live transcription, LLM responses, streamed speech, conversation history, and interruption. |
| Voice note taker | `POST /api/stt/transcribe` | Transcribes a completed WAV recording without generating an assistant response. |
| Text chat | `POST /api/llm/chat/stream` | Streams sentence-sized text as NDJSON. |
| Text-to-speech player | `POST /api/tts/tts` | Returns a complete, browser-playable WAV file. |

The gateway defaults to `http://localhost:8080`. In production, use HTTPS and
WSS, for example `https://api.example.com` and `wss://api.example.com/ws`.
Browser microphone capture requires HTTPS or `localhost`.

## Current security and browser constraints

- The API currently has no authentication. Do not expose it publicly without
  adding authentication, TLS, rate limiting, and request-size controls at the
  gateway or an upstream proxy.
- REST routes do not currently emit CORS headers. Serve the frontend from the
  same origin as the gateway, reverse-proxy `/api` and `/ws` through the
  frontend's origin, or add an intentional CORS policy to the gateway.
- The WebSocket currently accepts connections from any browser origin. Lock
  this down before a public deployment.
- The gateway limits each incoming WebSocket message to 1 MiB. Send frequent
  audio frames rather than one large frame.
- WebSocket conversation history lives only for the lifetime of that socket.
  Reconnecting starts a new conversation.

## Health check

`GET /health` returns HTTP `200` when all services are ready and HTTP `503`
when one or more are degraded.

```json
{
  "status": "ok",
  "stt": { "healthy": true },
  "llm": { "healthy": true },
  "tts": { "healthy": true }
}
```

Each unhealthy service can also include an `error` string. Use this endpoint
for readiness UI, but handle failures during a live session too.

## Real-time voice assistant

### Connection and audio contract

Connect to `WS /ws` and set `binaryType` to `arraybuffer` in a browser.

Client-to-server binary frames must contain headerless raw PCM with this exact
format:

- signed 16-bit little-endian samples;
- mono (one channel);
- 16,000 Hz sample rate;
- no WAV, WebM, Opus, MP3, or other container/header.

The gateway sends two kinds of frames on the same connection:

- text frames contain JSON control/events;
- binary frames contain headerless PCM assistant speech.

An `audio_format` event announces how to decode the binary speech that follows.
Do not assume the output sample rate is the same as the 16 kHz microphone input.

### Turn lifecycle

```text
Client                         Gateway
  |--- {"type":"start"} -------->|
  |--- binary PCM frames -------->|
  |<-- partial_transcript --------|
  |--- {"type":"end_utterance"}>|
  |<-- final_transcript ----------|
  |<-- llm_chunk -----------------|
  |<-- audio_format --------------|
  |<-- binary PCM frames ---------|
```

1. Send `start` immediately before audio for each utterance.
2. Stream small PCM frames while the user speaks. Frames around 20–100 ms are a
   sensible client target; the API does not require one exact duration.
3. Send `end_utterance` once when speech ends. This flushes the final transcript
   and starts the LLM/TTS response.
4. Queue output audio frames in arrival order; playing every frame immediately
   can cause overlapping or choppy audio.
5. Reuse the connection for later turns to preserve conversation history.

### Client-to-gateway messages

Start an utterance:

```json
{"type":"start"}
```

End an utterance:

```json
{"type":"end_utterance"}
```

Select a voice for subsequent synthesized speech. Values come from
`GET /api/tts/voices`. An empty voice selects the server default.

```json
{"type":"set_voice","voice":"en_US-lessac-medium.onnx"}
```

The server does not currently acknowledge these messages.

### Gateway-to-client messages

Partial speech recognition; replace the current partial text rather than
appending every event:

```json
{"type":"partial_transcript","text":"take a note about"}
```

Final recognition result:

```json
{"type":"final_transcript","text":"Take a note about tomorrow's meeting."}
```

One sentence-sized LLM response chunk. Display chunks in order:

```json
{"type":"llm_chunk","text":"I've captured that note."}
```

Format for subsequent binary output audio:

```json
{"type":"audio_format","sample_rate":22050,"channels":1,"sample_width":2}
```

`sample_width` is bytes per sample. The current TTS implementation emits
signed little-endian PCM. An `audio_format` event is sent before the first
audio frame of each synthesized LLM chunk, so retain the most recently received
format until another one arrives.

Interruption notification:

```json
{"type":"interrupted"}
```

Error event:

```json
{"type":"error","code":"stt_unavailable","message":"could not start transcription"}
```

Known gateway-generated error codes include `bad_request`,
`unknown_message_type`, `no_active_stream`, `stt_send_failed`,
`stt_unavailable`, `llm_unavailable`, and `tts_unavailable`. Backend services
may supply additional codes, so clients must also support unknown error codes.

There is currently no `assistant_done` or `turn_done` event. Treat playback as
temporarily complete when the queued audio drains, but do not use that as a
durable protocol-level completion signal.

### Barge-in

To interrupt an assistant that is generating or speaking, stop local playback
and send a new `start` followed by the new microphone audio. The gateway
cancels its active LLM/TTS work and normally emits `interrupted`.

Always clear already-buffered audio upon `interrupted`; the server cannot
recall audio bytes already delivered to the client. It is also good UX to stop
local playback as soon as the user begins the new utterance instead of waiting
for the round trip.

### Minimal browser client

This example shows the protocol mechanics. A production client should move
capture into an `AudioWorklet`, use a better resampler, add reconnection with
backoff, and expose clear microphone/error states.

```js
const gateway = location.origin; // or "https://api.example.com"
const wsUrl = gateway.replace(/^http/, "ws") + "/ws";
const ws = new WebSocket(wsUrl);
ws.binaryType = "arraybuffer";

let output = { sampleRate: 22050, channels: 1, sampleWidth: 2 };
let playbackContext;
let playAt = 0;
const playing = new Set();

ws.onmessage = async ({ data }) => {
  if (typeof data === "string") {
    const event = JSON.parse(data);

    if (event.type === "audio_format") {
      output = {
        sampleRate: event.sample_rate,
        channels: event.channels,
        sampleWidth: event.sample_width,
      };
    } else if (event.type === "interrupted") {
      for (const source of playing) try { source.stop(); } catch {}
      playing.clear();
      if (playbackContext) playAt = playbackContext.currentTime;
    } else if (event.type === "partial_transcript") {
      renderPartial(event.text); // replace the previous partial
    } else if (event.type === "final_transcript") {
      renderFinal(event.text);
    } else if (event.type === "llm_chunk") {
      appendAssistantText(event.text);
    } else if (event.type === "error") {
      showError(event.code, event.message);
    }
    return;
  }

  // Current output is PCM16 mono. Reject unexpected formats explicitly.
  if (output.sampleWidth !== 2 || output.channels !== 1) {
    throw new Error("Unsupported TTS audio format");
  }
  playbackContext ||= new AudioContext();
  const pcm = new Int16Array(data);
  const buffer = playbackContext.createBuffer(1, pcm.length, output.sampleRate);
  const samples = buffer.getChannelData(0);
  for (let i = 0; i < pcm.length; i++) samples[i] = pcm[i] / 32768;

  const source = playbackContext.createBufferSource();
  source.buffer = buffer;
  source.connect(playbackContext.destination);
  const start = Math.max(playAt, playbackContext.currentTime);
  source.start(start);
  playAt = start + buffer.duration;
  playing.add(source);
  source.onended = () => playing.delete(source);
};

function beginUtterance() {
  ws.send(JSON.stringify({ type: "start" }));
}

function sendPcm16Chunk(chunk) {
  // chunk must be an Int16Array containing 16 kHz mono PCM.
  if (ws.bufferedAmount < 512 * 1024) ws.send(chunk.buffer);
}

function endUtterance() {
  ws.send(JSON.stringify({ type: "end_utterance" }));
}
```

When capturing browser audio, `getUserMedia()` normally supplies floating-point
audio at the device's native sample rate (often 44.1 or 48 kHz). Downmix it to
mono, resample to 16 kHz, clamp samples to `[-1, 1]`, and convert them to a
little-endian `Int16Array` before sending. Do not send `MediaRecorder` output:
it is usually WebM/Opus and is not accepted by `/ws`.

## Voice note taker

Record a note, encode it as a WAV file, then upload it as multipart form data.
Only `audio/wav` and `audio/x-wav` are accepted.

```js
async function transcribeNote(wavBlob, model) {
  const form = new FormData();
  form.append("file", wavBlob, "note.wav");

  const url = new URL("/api/stt/transcribe", location.origin);
  if (model) url.searchParams.set("model", model);

  const response = await fetch(url, { method: "POST", body: form });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "Transcription failed");

  return {
    text: body.data.segments.map((segment) => segment.text).join(""),
    segments: body.data.segments,
  };
}
```

Success response:

```json
{
  "status": 200,
  "message": "Transciption succeeded",
  "data": {
    "segments": [
      {"start_ms":0,"end_ms":1420,"score":0.91,"text":"First sentence."}
    ]
  }
}
```

`score` can be `null`. The top-level HTTP status is authoritative; the nested
`status` field is part of the current response envelope. List valid model names
with `GET /api/stt/models`:

```json
{"status":200,"message":"2 available models","data":["base.en","small.en"]}
```

The current real-time `/ws` protocol cannot operate in transcription-only mode.
If a note-taking UI needs live partial transcripts without LLM/TTS, that should
be added as a gateway feature rather than connecting production clients to the
STT service's internal test WebSocket.

## Standalone REST APIs

### LLM

`POST /api/llm/chat` returns all chunks in one JSON response:

```json
{
  "prompt": "Summarize these notes",
  "conversation_history": [
    {"role":"user","content":"Earlier message"},
    {"role":"assistant","content":"Earlier response"}
  ]
}
```

```json
{
  "status": 200,
  "message": "OK",
  "data": [
    {"type":"chunk","text":"Here is the summary."},
    {"type":"done"}
  ]
}
```

`POST /api/llm/chat/stream` accepts the same request but returns
`application/x-ndjson`. Each line is one JSON value:

```jsonl
{"type":"chunk","text":"First sentence. "}
{"type":"chunk","text":"Second sentence."}
{"type":"done"}
```

A stream that fails after HTTP headers have been sent emits an in-band error
line: `{"type":"error","code":"...","message":"..."}`. Parse incrementally
with `response.body.getReader()`; `EventSource` is not appropriate because this
is NDJSON, not server-sent events.

### Text to speech

List voices with `GET /api/tts/voices`. The response uses the same
`{status,message,data}` envelope, with `data` containing voice file names.

Create speech with `POST /api/tts/tts`:

```json
{
  "text": "Read this aloud.",
  "voice": "en_US-lessac-medium.onnx",
  "format": "wav"
}
```

The response is `audio/wav`, not JSON:

```js
const response = await fetch("/api/tts/tts", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text, voice, format: "wav" }),
});
if (!response.ok) throw new Error(await response.text());
const audioUrl = URL.createObjectURL(await response.blob());
const audio = new Audio(audioUrl);
audio.onended = () => URL.revokeObjectURL(audioUrl);
await audio.play();
```

`text` must contain 1–5,000 characters, `voice` must be a non-empty listed
voice name, and `format` currently supports only `wav`.

## Error handling and reconnection checklist

- Check `response.ok` before trusting a REST body. FastAPI validation and route
  errors commonly use `{"detail": ...}` rather than the success envelope.
- Treat HTTP `502` from `/api/{service}/*` as a backend service outage.
- Render WebSocket `error` events without closing the socket automatically;
  whether a turn can continue depends on the error.
- On socket close, stop capture and playback and discard only in-flight partial
  state. Reconnect with capped exponential backoff.
- Do not replay an interrupted or disconnected utterance automatically unless
  the user explicitly chooses to retry it.
- Monitor `WebSocket.bufferedAmount` and pause/drop capture frames if the client
  is outpacing the network.
- Resume or create `AudioContext` from a user gesture where required by browser
  autoplay policy.

## Current API gaps to consider before public frontend integrations

These are implementation gaps, not client responsibilities:

- authentication and authorization;
- explicit REST CORS and WebSocket origin policy;
- protocol version negotiation;
- a `turn_done` event and client-generated turn IDs;
- transcription-only mode on the main streaming WebSocket;
- server-side voice activity detection/end-of-speech;
- reconnect/resume semantics and persisted conversation IDs;
- declared upload-duration/size limits for note files;
- structured capabilities discovery (supported input/output formats).

The repository's working browser implementation is
[`site/assistant.html`](../site/assistant.html). It demonstrates microphone
resampling, PCM conversion, voice selection, ordered playback, barge-in, and
reconnection behavior against the current protocol.

# Gemini Live Native Audio

## Purpose

The Intelligence Voice Core uses one short-lived, backend-owned Gemini Live
connection per operator voice session. It streams signed 16-bit mono PCM in
both directions and plays Gemini's native audio as it arrives. Browser speech
synthesis and Web Speech text-to-speech are not used.

The browser never receives a Gemini API key, provider model identifier, voice
identifier, or upstream provider WebSocket URL. It communicates only with the
Aegis session API and the Aegis WebSocket gateway.

## Required backend configuration

Keep these values in the FastAPI backend environment only. Do not add any of
them to `NEXT_PUBLIC_*` variables or frontend `.env` files.

```dotenv
GEMINI_API_KEY=server-only-secret
GEMINI_LIVE_ENABLED=true
GEMINI_LIVE_MODEL=your-enabled-native-audio-live-model
GEMINI_LIVE_VOICE=your-enabled-prebuilt-voice
GEMINI_LIVE_INPUT_SAMPLE_RATE=16000
GEMINI_LIVE_OUTPUT_SAMPLE_RATE=24000
GEMINI_LIVE_SESSION_TTL_SECONDS=120
GEMINI_LIVE_MAX_SESSION_SECONDS=900
```

`GEMINI_LIVE_MODEL` and `GEMINI_LIVE_VOICE` are validated when Gemini Live
connects. If native audio cannot be created, the gateway returns the typed
`NATIVE_AUDIO_UNAVAILABLE` or connection error state; it does not use a
browser TTS fallback.

## Transport contract

1. The authenticated dashboard calls `POST /api/intelligence/live/sessions`.
   The response has a one-time connection token in a WebSocket subprotocol,
   not in a URL or permanent credential.
2. The browser connects to `WS /ws/intelligence/live/{sessionId}` using
   `aegis-live-v1` plus that short-lived token.
3. Browser microphone chunks are JSON envelopes only while voice mode is
   explicitly enabled. They contain base64 signed 16-bit mono PCM using
   `inputSampleRate`. They remain in memory and are not logged or persisted.
4. Aegis emits `session_ready`, `state`, `transcript`, `tool_activity`,
   `citations`, `turn_complete`, `interrupted`, and `error` JSON events.
5. Gemini output is sent as binary WebSocket frames: signed 16-bit mono PCM at
   `outputSampleRate`. The frame belongs to the one authenticated voice
   session; adjacent events carry its active turn identifier for audit UI.

The browser constructs and resumes its `AudioContext` during the explicit
Enable Voice / Hold-to-talk gesture. It queues native PCM frames immediately
and marks the interface as speaking only after playback has been scheduled.

## Safety and grounding

- The microphone is off by default.
- Stop, Escape, route exit, unmount, permission denial, connection failure,
  and provider failure stop capture, output playback, buffers, tracks, and
  the short-lived session.
- Speaking over Aegis stops local queued output after a short sustained
  microphone-activity window. Silent hands-free PCM frames cannot cancel
  playback. A typed `interrupt` event precedes the new microphone audio over
  the existing session; Gemini Live VAD handles provider-side interruption.
- Only `LiveToolRegistry`'s read-only, audited allowlist is registered with
  Gemini. Tools return typed current data, source timestamps, and citations.
- No raw microphone or output audio is written to database, audit records, or
  application logs.

## Manual verification

1. Start the backend with the server-only settings above and open
   `/intelligence`.
2. Enable voice, grant microphone permission, and ask: "How many cameras are
   online right now?"
3. Confirm a binary PCM frame reaches the browser WebSocket, native audio is
   heard without another play action, and the state becomes `Aegis speaking`.
4. Confirm the transcript and evidence citation identify the actual camera
   runtime source.
5. Speak while Aegis is responding. Audio must stop immediately and the core
   must return to listening for the new request.
6. Press Escape. Confirm microphone access, playback, and WebSocket activity
   stop immediately.

Known limitation: provider-side cancellation is VAD-driven because the SDK
does not expose a stable generic cancel-turn call in this gateway. The
browser-side interruption is immediate; the next PCM input tells the
persistent Gemini Live session to begin the new turn.

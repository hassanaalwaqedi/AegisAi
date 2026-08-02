# Gemini Live Voice Intelligence Copilot

The Intelligence Center can use Gemini Live as AegisAI's conversational layer
for authorised human operators. It is a read-only, evidence-grounded feature:
Gemini never receives database access, a camera object, a backend route, or an
API key. It can only invoke the typed Aegis tool allowlist described below.

## Configuration

Set these variables in the backend environment (`.env` for local development).
Do not put `GEMINI_API_KEY` in `frontend/.env.local`, a `NEXT_PUBLIC_*`
variable, a browser bundle, or a WebSocket URL.

| Variable | Required | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | yes | Server-only Gemini credential. |
| `GEMINI_LIVE_ENABLED` | yes | Explicitly enables Live voice; defaults to `false`. |
| `GEMINI_LIVE_MODEL` | yes | Native-audio Live model. Default: `gemini-3.1-flash-live-preview`. |
| `GEMINI_LIVE_VOICE` | yes | Configurable prebuilt Live voice. Default: `Kore`. |
| `GEMINI_LIVE_SESSION_TTL_SECONDS` | no | Browser connection-token lifetime; default `120`. |
| `GEMINI_LIVE_MAX_SESSION_SECONDS` | no | Maximum active voice session; default `900`. |
| `GEMINI_LIVE_TRANSCRIPT_RETENTION_SECONDS` | no | Completed transcript retention in gateway memory. Default `0` clears it on close. |
| `GEMINI_LIVE_TOOL_AUDIT_RETENTION_SECONDS` | no | Process-memory tool-audit retention. Default `3600`. |
| `NEXT_PUBLIC_AEGIS_LIVE_WS_URL` | deployment-dependent | Public FastAPI WebSocket origin, such as `wss://api.example.com`. It is not a credential. |

Install the official server SDK after pulling the change:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

The capability endpoint is deliberately unavailable unless Live is enabled,
the backend has a key, the SDK is installed, and a nonempty model and voice
are configured. Gemini validates the model and voice when the session opens;
the UI reports a clear connection error if the configured account does not
support them.

## Architecture and data flow

```text
Browser microphone (16 kHz PCM)
  -> short-lived authenticated Aegis WebSocket
  -> FastAPI Live gateway
  -> Gemini Live native-audio session
  -> read-only typed Aegis tools
  -> cited tool result + safe UI command
  -> Gemini native audio (24 kHz PCM), transcripts, citations
  -> browser playback and Intelligence Center
```

The browser first calls `POST /api/intelligence/live/sessions` through the
existing dashboard server proxy. The proxy attaches the server-side Aegis API
key; the browser never sees it. The response contains a random, single-use,
short-lived `connectionToken`. The browser offers that token in the
`Sec-WebSocket-Protocol` handshake alongside `aegis-live-v1` when connecting to
`WS /ws/intelligence/live/{session_id}`. The gateway validates the token before
accepting the socket. Permanent credentials are never placed in a WebSocket
query string.

The gateway validates the request origin, applies a maximum session duration,
cleans up on disconnect, and stops the browser capture path on Stop, Escape,
route exit, tab cleanup, or gateway error. It does not log or retain raw
microphone bytes. Input audio is 16-bit little-endian PCM at 16 kHz; Gemini
native audio output is played as 16-bit PCM at 24 kHz.

## API surface

All HTTP endpoints require the existing Aegis API-key authentication. The
dashboard uses its same-origin server proxy for these requests.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/intelligence/live/capabilities` | Truthful Live configuration state. |
| `POST` | `/api/intelligence/live/sessions` | Create a short-lived session token. |
| `DELETE` | `/api/intelligence/live/sessions/{session_id}` | Idempotently stop and invalidate a session. |
| `WS` | `/ws/intelligence/live/{session_id}` | Audio, transcript, state, citations, and safe-command event envelopes. |

The WebSocket events are versioned (`version: "1.0"`). Browser input is
limited to `audio`, `text`, `audio_end`, `stop`, and `ping`. Server output is
limited to state changes, PCM audio, transcripts, citations, safe UI commands,
interruption, errors, and pong. Incoming audio chunk size is bounded; raw audio
is never written to logs.

## Supported read-only tools

Gemini can invoke only these server-authorised tools:

- `get_intelligence_context`
- `get_live_camera_status`
- `get_active_risk_alerts`
- `get_recent_events`
- `get_track_details`
- `get_risk_explanation`
- `search_live_evidence`
- `get_pipeline_health`
- `open_authorised_evidence`

Each result includes availability, observed timestamp, degraded reason when
needed, and resolvable evidence citations. Unknown tools, unknown evidence IDs,
arbitrary navigation, destructive actions, camera controls, exports,
configuration, incident management, patrol, automation, and knowledge-graph
operations are rejected. Tool audit records include correlation ID,
API-key-authenticated operator boundary, session ID, arguments, availability,
latency, and evidence IDs. The current platform has no per-user/RBAC identity;
the session boundary is explicitly recorded as API-key-authenticated until
RBAC is added.

The only UI commands are enum values mapped by the browser to existing Aegis
views: Cameras, Tracks, Semantic Evidence, Events/Risk, and the current Health
panel. Gemini cannot emit a URL, JavaScript, route string, or mutation.

## Operator experience

Hands-free Voice is off by default. An operator must press **Enable
hands-free** and grant microphone permission. The page shows `Voice off`,
`Listening`, `Thinking`, `Aegis speaking`, or `Connection error`, plus a live
waveform. Speaking while Aegis is responding stops local native-audio playback
immediately and sends new PCM input to Gemini Live for barge-in. **Stop** and
`Escape` immediately stop microphone capture and native playback.

**Hold to talk** uses the same authenticated Live session without continuous
capture. Browsers without AudioWorklet fall back to a push-to-talk
ScriptProcessor PCM path; browsers without microphone/AudioContext support
receive an explicit typed-command fallback message. Browser `speechSynthesis`
and browser speech recognition are not used for primary Aegis voice responses.

## Local verification

1. Configure a valid Gemini key and an account-supported Live model/voice in
   the backend `.env`, then set `GEMINI_LIVE_ENABLED=true`.
2. Start FastAPI and the frontend. For local Next development, use
   `NEXT_PUBLIC_AEGIS_LIVE_WS_URL=ws://127.0.0.1:8080` in
   `frontend/.env.local` if the endpoint differs from the default local URL.
3. Open `/intelligence`, wait for the Intelligence context, and enable
   Hands-free Voice.
4. Ask: “How many cameras are online right now?” Verify the count and camera
   names against the CameraManager runtime view and inspect the citations and
   timestamps below the transcript.
5. Ask about active risk alerts, a current track, semantic evidence, and
   pipeline health. An unavailable source must produce a clear unavailable or
   degraded explanation rather than a guessed answer.
6. Press Escape during microphone capture and during Aegis audio. Confirm that
   capture and playback stop immediately.

## Current limitations

- Gemini Live model and voice availability is account and region dependent;
  the gateway reports a connection failure when provider validation rejects a
  configured value.
- Native-audio Live provider sessions are externally limited in duration; the
  gateway additionally caps a session at `GEMINI_LIVE_MAX_SESSION_SECONDS`.
- Transcripts are visible during the active session. They are cleared at close
  by default and there is no new durable transcript database table in this
  change. Configure retention only after aligning it with deployment policy.
- There is no existing end-user login or RBAC implementation in this
  repository. Live tools enforce the current API-key auth boundary and are
  deliberately read-only pending that work.
- A real Gemini account, a working camera runtime, and optional semantic
  engine are required for the complete manual acceptance test. Tests use
  injected typed context fixtures and never manufacture operational results.

# Public live avatar demo

DeckFM's live avatar (Azure Voice Live + real-time WebRTC avatar) is normally
**admin-only** (`/ws/voice`): an earlier deployment that let anonymous visitors
stream Voice Live ran up a runaway bill. The *public live demo* lets anonymous
visitors watch the avatar **narrate a deck an admin has already chosen**, with
hard, server-side cost and abuse guardrails. It is **off by default**.

## How it works

1. An admin publishes a deck and switches **Live demo on** for it on the
   Decks page (`POST /api/decks/{deck_id}/live-demo {"enabled": true}`).
   Only published decks can be live demos; unpublishing a deck switches the
   live demo off.
2. The SPA calls `GET /api/demo/config` (anonymous) →
   `{"enabled": bool, "session_seconds": int, "remaining_today"?: int}`.
3. On `/decks/<deck_id>/present`, a visitor who is not an admin sees
   **▶ Try the live demo** (instead of "Sign in to try the live avatar") when
   the demo is enabled and the deck is a live demo. The Home and Decks pages show
   a *Try the live avatar demo →* link and a *Live demo* badge.
4. The browser opens `wss://<host>/ws/voice/demo?deck_id=<uuid>` and negotiates
   WebRTC exactly like the admin flow. The visitor can only press
   **Present this slide**, **Present all** (auto-advances after each narration)
   and **Stop** — no avatar/voice/language picker, no Q&A, no free text, no
   microphone, no uploads.

### Message flow

```
Browser                         DeckFM backend                         Azure Voice Live
  | WS /ws/voice/demo?deck_id=…   |                                        |
  |------------------------------>| kill switch, UUID, Origin, deck        |
  |                               | published+live_demo  (else 4403,       |
  |                               | before accept)                         |
  |                               | capacity (1013) / daily+per-IP (4429)  |
  |<----------- accept -----------|                                        |
  |                               |--- connect (managed identity) -------->|
  |<-- proxy.connected -----------|--- session.update (server-side only) ->|
  |<-- session.updated (ICE) -----|<---------------------------------------|
  |-- session.avatar.connect ---->|  (SDP offer, ≤20 KB, once) ----------->|
  |<-- server SDP answer ---------|<---------------------------------------|
  |== WebRTC avatar video/audio (browser ⇄ Azure) =========================|
  |-- {"type":"demo.speak",       |  look up stored notes (→ body → title),|
  |    "slide":n} --------------->|  truncate to 2,000 chars, then send:   |
  |                               |--- conversation.item.create ---------->|
  |                               |--- response.create ------------------->|
  |<-- demo.speaking {chars} -----|                                        |
  |<-- response.* events ---------|<---------------------------------------|
  |-- response.cancel ----------->|--------------------------------------->|
  |   (anything else: dropped)    |                                        |
  |<-- close 4408 at DEMO_SESSION_SECONDS; Azure socket closed too ---------|
```

The narration messages are exactly what the admin frontend sends for a slide
(`"Please say the following exactly as written: <text>"` as a user
`input_text` item, then `response.create`), so lip-sync and timing behave the
same.

## Guardrails

| Guardrail | Where | Default |
|---|---|---|
| Kill switch `PUBLIC_DEMO_ENABLED` | every `/ws/voice/demo` handshake + `/api/demo/config` | `false` |
| Deck allowlist: published **and** `live_demo` | before `accept()` → 4403 | admin choice |
| Same-origin `Origin` check (`ALLOWED_ORIGINS` additive) | before `accept()` → 4403 | same-origin |
| Global concurrency `DEMO_MAX_CONCURRENT` (separate from `MAX_VOICE_SESSIONS`, so the owner can still use the admin avatar) | after `accept()` → 1013 | `1` |
| Daily sessions, global `DEMO_DAILY_SESSIONS` | after `accept()` → 4429 | `20` / UTC day |
| Daily sessions per client IP `DEMO_DAILY_SESSIONS_PER_IP` | after `accept()` → 4429 | `3` / UTC day (IPs stored only as salted hashes) |
| Daily streaming minutes `DEMO_DAILY_MINUTES` | after `accept()` → 4429 | `60` min / UTC day (seconds recorded at session end) |
| Hard session timeout `DEMO_SESSION_SECONDS` | server timer → 4408 | `180` s |
| Narrations per session `DEMO_MAX_SPEAKS` | message filter | 2 × slides, max 40 |
| `demo.speak` rate limit | message filter | ≥ 1 s apart |
| Narration length | server truncation | 2,000 chars |
| Session config 100 % server-side | `build_demo_session_config` | deck language, registry default avatar (or `?avatar=` restricted to the public avatar catalog), allowlisted voice, fixed "read verbatim" instructions, `turn_detection: none`, no input audio, `max_response_output_tokens: 4096` |
| Strict client→server allowlist | `DemoMessageFilter` | SDP offer, `demo.speak`, `response.cancel` only |
| Azure socket torn down when either side leaves | `handle_demo_proxy` | — |
| Custom avatar character names redacted from server events | `redact_server_message` | — |

Close codes after `accept()` are readable by browsers and mapped to friendly
messages: 1013 "The demo avatar is busy, try again in a minute", 4429 "Daily
demo limit reached — come back tomorrow", 4408 "Demo time limit reached",
4403 "Demo not available for this deck" (a pre-accept refusal surfaces as 1006
in browsers and is shown with the same message).

### Implementation notes

- Daily counters are **durable**: one Cosmos DB document per UTC day (`demo-quota-<day>`,
updated with etag optimistic concurrency), so restarts, redeploys and scale-to-zero
cannot reset the budget. If Cosmos is unavailable the demo **fails closed** (1013).
Only the concurrency slot is in-process (the app is capped at one replica).
- **Client IP** for the per-IP quota is the **rightmost** `X-Forwarded-For`
  entry (else the socket peer). Azure Container Apps ingress *appends* the real
  peer to any client-supplied value and documents that only the rightmost IP is
  set by the platform, so left-hand entries are attacker-controlled and
  ignored. If you put another proxy/CDN (Front Door, App Gateway) in front, the
  rightmost entry becomes that proxy's address and the per-IP quota degrades to
  a global one — revisit before doing so. The global daily cap and concurrency
  cap do not depend on the IP.
- A quota unit is consumed when a session is accepted, even if the visitor
  leaves immediately or Azure fails to connect (conservative).

## Threat model

| Threat | Mitigation |
|---|---|
| Runaway Voice Live / avatar spend by anonymous users | kill switch off by default; 1 concurrent session; 180 s hard cap; 20 sessions/day; Azure socket closed when the browser leaves; budget alerts (`BUDGET_*`). |
| One visitor monopolising the demo | 3 sessions per IP per day; 1 s narration rate limit; narration cap per session. |
| Prompt injection / free-form use of the LLM ("make the avatar say X") | the client can never send text: `demo.speak` carries only a slide index; the server reads admin-authored stored notes. `session.update`, `conversation.item.create`, `response.create` and audio buffers from the client are dropped. Instructions are fixed server-side. |
| Voice input / eavesdropping | no microphone track (recv-only WebRTC), `turn_detection: none`, no input transcription, input audio messages dropped. |
| Narrating private content | only decks that are published **and** explicitly marked Live demo; unpublishing clears the flag. Note: a live-demo deck's speaker notes become audible (and appear in the realtime transcript events) to anyone — only enable it on decks whose notes are public. |
| Cross-site WebSocket hijacking | same-origin `Origin` check before `accept()`. |
| Leaking Azure details | error messages to demo clients are generic; custom avatar character names are redacted; credentials never leave the server. |
| IP spoofing via `X-Forwarded-For` | only the platform-appended rightmost entry is trusted; global caps hold regardless. |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PUBLIC_DEMO_ENABLED` | `false` | Kill switch. |
| `DEMO_MAX_CONCURRENT` | `1` | Concurrent anonymous demo sessions (global). |
| `DEMO_SESSION_SECONDS` | `180` | Hard cap per session. |
| `DEMO_DAILY_SESSIONS` | `20` | Sessions per UTC day, global. `0` blocks all sessions. |
| `DEMO_DAILY_SESSIONS_PER_IP` | `3` | Sessions per UTC day per client IP. |
| `DEMO_DAILY_MINUTES` | `60` | Hard cap on total demo streaming minutes per UTC day (all visitors). |
| `DEMO_MAX_SPEAKS` | `0` | Narrations per session; `0`/unset = 2 × slide count; never above 40. |

All are read per call, so a config change (new revision) takes effect
immediately; flipping `PUBLIC_DEMO_ENABLED=false` blocks new sessions at once.

## Cost estimate

Worst-case avatar minutes per day:

```
min(DEMO_DAILY_MINUTES, DEMO_DAILY_SESSIONS × DEMO_SESSION_SECONDS / 60) + one in-flight session
(defaults: min(60, 20 × 180 / 60) = 60 min/day, ≤ 63 min worst case)
```

Multiply by your region's real-time avatar + Voice Live (model + TTS) per-minute
price to get a daily ceiling, and × 30 for a monthly ceiling. Concurrency is 1,
so at most one demo avatar is billed at any moment. Narration tokens are small
(≤ 2,000 chars × ≤ 40 narrations per session). Keep the optional Azure budget
(`BUDGET_CONTACT_EMAILS`, `BUDGET_AMOUNT`) enabled as a backstop.

## Enable it

```bash
azd env set PUBLIC_DEMO_ENABLED true
# optional tuning
azd env set DEMO_DAILY_SESSIONS 10
azd env set DEMO_SESSION_SECONDS 120
azd provision            # or: azd up
```

Then, signed in as an admin, open **Decks**, publish a deck and
click **Live demo off** to switch it to **Live demo on**. Anonymous visitors now
see *Try the live avatar demo →* on the Home/Decks pages.

To stop everything immediately: `azd env set PUBLIC_DEMO_ENABLED false` and
re-provision (or edit the Container App environment variable in the portal).

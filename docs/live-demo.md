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
   `{"enabled": bool, "session_seconds": int, "remaining_today"?: int, "qa": {"enabled": bool, "max_questions": int, "max_audio_seconds": int}}`
   (`session_seconds` is the effective cap: `DEMO_QA_SESSION_SECONDS` when demo
   Q&A is on, else `DEMO_SESSION_SECONDS`).
3. On `/decks/<deck_id>/present`, a visitor who is not an admin sees
   **▶ Try the live demo** (instead of "Sign in to try the live avatar") when
   the demo is enabled and the deck is a live demo. The Home and Decks pages show
   a *Watch the live demo* button and a *Live demo* badge.
4. The browser opens `wss://<host>/ws/voice/demo?deck_id=<uuid>` and negotiates
   WebRTC exactly like the admin flow. The visitor can only press
   **Present this slide**, **Present all** (auto-advances after each narration)
   and **Stop** — no avatar/voice/language picker, no free text, no uploads.
   When `DEMO_QA_ENABLED=true` the visitor can also **raise a hand** and ask a
   spoken question about the deck (see [Raise-hand Q&A](#raise-hand-qa));
   otherwise there is no microphone at all.

### Message flow

```
Browser                         DeckFM backend                         Azure Voice Live
  | WS /ws/voice/demo?deck_id=…   |                                        |
  |------------------------------>| kill switch, UUID, Origin, deck        |
  |                               | published+live_demo  (else 4403,       |
  |                               | before accept)                         |
  |                               | capacity (1013) / daily+per-IP (4429)  |
  |<----------- accept -----------|                                        |
  |<-- demo.started {session_seconds, remaining_ms, narration_chars[]}     |
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
  |<-- demo.speaking {chars,      |                                        |
  |     remaining, remaining_ms} -|                                        |
  |<-- response.* events ---------|<---------------------------------------|
  |-- response.cancel ----------->|--------------------------------------->|
  |   (anything else: dropped)    |                                        |
  |<-- close 4408 at the session cap; Azure socket closed too -------------|
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
| Hard session timeout `DEMO_SESSION_SECONDS` (`DEMO_QA_SESSION_SECONDS` when demo Q&A is on) | server timer → 4408 | `180` s (`300` s) |
| Narrations per session `DEMO_MAX_SPEAKS` | message filter | 2 × slides, max 40 |
| `demo.speak` rate limit | message filter | ≥ 1 s apart |
| Narration length | server truncation | 2,000 chars |
| Session config 100 % server-side | `build_demo_session_config` | deck language, registry default avatar (or `?avatar=` restricted to the public avatar catalog), allowlisted voice, fixed "read verbatim" instructions, `turn_detection: none`, no input audio, `max_response_output_tokens: 4096` |
| Strict client→server allowlist | `DemoMessageFilter` | SDP offer, `demo.speak`, `response.cancel`, plus `qa.begin` (after_slide) / `qa.audio` / `qa.commit` / `qa.cancel` / `qa.resume` handled by the backend (never forwarded) |
| Demo Q&A (`DEMO_QA_ENABLED`) | `QaSession` + `DemoQuota` | off; 2 questions/session, 15 s audio, 40/day global, 6/day per IP, ≥ 30 s of session left |
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
- **Validating the chain:** set `LOG_FORWARDING_CHAIN=true` on a revision
  (`az containerapp update --set-env-vars`), open a demo WebSocket with an
  invalid `deck_id` (rejected before any session/quota logic), read the
  `Forwarding chain:` log line, then remove the variable. It logs raw IPs, so
  keep it off otherwise. Note that managed corporate devices may reach Azure
  through Microsoft's secure-access edge, so ACA sees rotating Microsoft
  egress IPs rather than the home line — `DEMO_QUOTA_EXEMPT_IPS` only matches
  devices that connect directly (signed-in admins use the admin avatar and
  are never subject to demo quotas).
- A quota unit is consumed when a session is accepted, even if the visitor
  leaves immediately or Azure fails to connect (conservative).

## Raise-hand Q&A

Optional (`DEMO_QA_ENABLED=true`, default off) for the demo; always available
to signed-in admins on `/ws/voice` when a deck is bound. The visitor raises a
hand, the avatar says a short localized invite ("Go ahead, I'm listening."),
the browser records the question (energy VAD, ≤ 15 s) and streams it to the
backend; the backend transcribes it (Speech short-audio REST, managed identity
→ STS token), answers **only from the deck** (gpt-4.1, JSON mode, whole deck
with the current slide first, ≤ 12k chars, temperature 0.2) and the avatar
speaks the answer. `qa.*` / `context.*` messages are handled by the backend and
are never forwarded to Voice Live; the avatar only ever speaks server-generated
text.

```
Browser                              DeckFM backend                       Azure
  |-- qa.begin {request_id, slide} ->| enabled? deck? one in flight?      |
  |                                  | ≥30 s left? session + daily quota  |
  |<-- qa.ready {max_audio_ms,       |--- speak(invite) ----------------->| (avatar)
  |    max_audio_bytes,              |                                    |
  |    remaining_questions} ---------|                                    |
  |-- qa.audio {seq, audio(b64)} x N>| strict base64, seq, ≤16 KB/frame,  |
  |-- qa.commit -------------------->| ≤480 KB total, ≤40 frames/s        |
  |                                  |--- STT (10 s timeout) ------------->| (Speech)
  |<-- qa.transcript {text} ---------|--- grounded answer (10 s) -------->| (OpenAI)
  |<-- qa.answer {text,              |--- speak(answer) ----------------->| (avatar)
  |    source_slides, grounded} -----|                                    |
  |-- qa.resume -------------------->| (ack only, no paid call)           |
  |   then demo.speak {next slide} as usual (normal narration budget)     |
```

- Demo messages accepted: `qa.begin` (`mode` `after_slide` only), `qa.audio`,
  `qa.commit`, `qa.cancel`, `qa.resume`. Dropped: `qa.text`, `context.switch`,
  `mode: "now"` and everything listed in the allowlist above.
- Admin extras: `session.update` may carry `session.deck_id` (catalog deck) or
  `session.presentation_id` (Live upload) — the backend loads title/body/notes
  server-side; `context.switch {deck_id}` → `context.switched {deck_id,
  slide_count}` for playlists; typed `qa.text` (≤ 500 chars) and
  `mode: "now"`. Unknown deck → `qa.unavailable {reason: "no_deck"}`.
- Every `qa.*` server message in the demo carries `remaining_ms` (also
  `demo.speaking`), and `demo.started {session_seconds, remaining_ms,
  narration_chars}` is sent at accept so the client can show the session clock
  and estimate how many slides fit (`narration_chars` = length of each slide's
  narration in slide order — counts only, never text).
- Listening timeout: after `qa.ready`, if no `qa.commit` / `qa.text` /
  `qa.cancel` arrives within `max_audio_ms` + 10 s, or frames stop for 8 s
  once recording started, the question is cancelled with
  `qa.error {code: "no_speech"}` (the question stays consumed).
- Admin "Ask now": the client sends `response.cancel` then
  `output_audio_buffer.clear` (forwarded to Voice Live on `/ws/voice` only;
  dropped in the demo).
- Errors: `qa.error {request_id, code, message}` with `code` in `no_speech`,
  `too_long`, `limit`, `rate`, `stt_failed`, `answer_failed`, `bad_state`,
  `disabled`, `time_low` (`bad_deck` for `context.switch`); messages are
  user-safe and never contain upstream text.
- Limits: demo 2 questions/session (`DEMO_QA_MAX_QUESTIONS`), 40/day global
  and 6/day per IP (durable, same `demo-quota-<day>` Cosmos doc, fails closed);
  admin 10/session plus one unit of `DAILY_GENERATION_QUOTA` per question.
  A question is reserved at `qa.begin` and stays consumed if cancelled.
  Answers: demo ≤ 3 sentences / 600 chars, admin ≤ 5 / 900; not covered →
  fixed localized "This isn't covered in this presentation."
- Disconnect or the session cap cancels in-flight STT/LLM work and discards
  the audio. Logs contain counts and codes only (never audio or transcripts).
- The identity needs a Cognitive Services data-plane role (e.g. *Cognitive
  Services User*) on the AI Services resource for STT, and access to the chat
  deployment (`AZURE_OPENAI_CHAT_DEPLOYMENT`).
- Session config also enables `output_audio_timestamp_types: ["word"]`; the
  resulting `response.audio_timestamp.delta` events are forwarded to the
  browser to estimate the audible end of each turn.

## Threat model

| Threat | Mitigation |
|---|---|
| Runaway Voice Live / avatar spend by anonymous users | kill switch off by default; 1 concurrent session; 180 s hard cap; 20 sessions/day; Azure socket closed when the browser leaves; budget alerts (`BUDGET_*`). |
| One visitor monopolising the demo | 3 sessions per IP per day; 1 s narration rate limit; narration cap per session. |
| Prompt injection / free-form use of the LLM ("make the avatar say X") | the client can never send text: `demo.speak` carries only a slide index; the server reads admin-authored stored notes. `session.update`, `conversation.item.create`, `response.create` and audio buffers from the client are dropped. Instructions are fixed server-side. |
| Voice input / eavesdropping | no microphone track (recv-only WebRTC), `turn_detection: none`, no input transcription, Voice Live input-audio messages dropped. With demo Q&A on, question audio goes only to the backend (`qa.audio`, ≤ 15 s), is transcribed once and discarded; it is never logged nor sent to Voice Live. |
| Prompt injection through a spoken question | the question is answered by a separate, tool-less, history-less call that sees the deck and the question as delimited untrusted data and must answer only from the deck (else a fixed "not covered" sentence); the avatar speaks only that server-generated answer (≤ 3 sentences / 600 chars) or a fixed invite string. `qa.text`, `context.switch` and `mode: "now"` are dropped in the demo. |
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
| `DEMO_QUOTA_EXEMPT_IPS` | *(empty)* | Comma-separated client IPs/CIDRs (e.g. the owner's home IP) that skip the daily quotas. Matched on the same trusted client IP as the per-IP quota (not spoofable); exempt sessions don't consume the shared budget but still obey `DEMO_MAX_CONCURRENT` and `DEMO_SESSION_SECONDS`. Set it in the azd env, never commit it. |
| `DEMO_QA_ENABLED` | `false` | Raise-hand voice Q&A in the demo. |
| `DEMO_QA_MAX_QUESTIONS` | `2` | Questions per demo session (each `qa.begin` counts, even if cancelled). |
| `DEMO_QA_SESSION_SECONDS` | `300` | Session cap used instead of `DEMO_SESSION_SECONDS` when demo Q&A is on. |
| `DEMO_QA_DAILY_MAX` | `40` | Demo questions per UTC day, global (durable, fails closed). |
| `DEMO_QA_DAILY_PER_IP` | `6` | Demo questions per UTC day per client IP (exempt IPs skip it). |

All are read per call, so a config change (new revision) takes effect
immediately; flipping `PUBLIC_DEMO_ENABLED=false` blocks new sessions at once.

## Cost estimate

Worst-case avatar minutes per day:

```
min(DEMO_DAILY_MINUTES, DEMO_DAILY_SESSIONS × DEMO_SESSION_SECONDS / 60) + one in-flight session
(defaults: min(60, 20 × 180 / 60) = 60 min/day, ≤ 63 min worst case;
 with demo Q&A on the session cap is 300 s: min(60, 20 × 300 / 60) = 60 min/day, ≤ 65 min)
```

Demo Q&A adds at most `DEMO_QA_DAILY_MAX` (40) questions/day, each one
short-audio STT request (≤ 15 s) and one small gpt-4.1 call (≤ ~12k chars of
deck context in, ≤ 220 tokens out), plus the spoken invite/answer on the
already-billed avatar session.

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
see *Watch the live demo* on the Home/Decks pages.

To stop everything immediately: `azd env set PUBLIC_DEMO_ENABLED false` and
re-provision (or edit the Container App environment variable in the portal).

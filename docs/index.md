# DeckFM — Documentation Index

A quick, opinionated map of what's in `docs/`. Start with whichever bucket matches what you're trying to do.

---

## 🧭 By feature

| Feature | What it does | Where |
|---|---|---|
| **Live** | Live avatar presenter over a single PowerPoint (WebRTC, real-time Q&A grounded in the slides) | [architecture.md](architecture.md), [diagrams/images/deck-present-sequence.png](diagrams/images/deck-present-sequence.png) |
| **Decks, Search & Playlists** | Multi-deck catalog with hybrid search, playlists with progress tracking and AI playlist recommendation | [decks-search-playlists.md](decks-search-playlists.md) |
| **Public live demo** | Anonymous, narration-only live avatar on decks an admin marked *Live demo*, with hard cost guardrails | [live-demo.md](live-demo.md) |
| **Video** | Narrated avatar video generated from a PowerPoint (batch, multilingual; MP4 / SRT / SCORM) | [video.md](video.md) |
| **Podcast** | Two-avatar podcast-style video generated from any document | [podcast.md](podcast.md) |

---

## 🏗 By topic

| Topic | Doc |
|---|---|
| Component architecture, data flows, API contract | [architecture.md](architecture.md) |
| Azure infra deep dive (Bicep, RBAC, security, CI/CD) | [deep-dive-azure.md](deep-dive-azure.md) |
| Parallel "copilot" deployment | [deploy-copilot.md](deploy-copilot.md) |
| Microsoft Teams Static Tab embedding | [teams-integration.md](teams-integration.md) |
| Public live demo — guardrails, threat model, cost ceiling | [live-demo.md](live-demo.md) |
| Security model, vulnerability reporting, operator checklist | [../SECURITY.md](../SECURITY.md) · [README › Security model](../README.md#-security-model) |

---

## 🖼 Diagrams

PNGs are rendered from draw.io sources in [`diagrams/`](diagrams/).

| Diagram | PNG | Source |
|---|---|---|
| Azure architecture (end-to-end) | [azure-architecture.png](diagrams/images/azure-architecture.png) | [azure-architecture.drawio](diagrams/azure-architecture.drawio) |
| Live presenter · slide Q&A sequence | [live-qa-sequence.png](diagrams/images/live-qa-sequence.png) | [live-qa-sequence.drawio](diagrams/live-qa-sequence.drawio) |
| Deck ingestion sequence | [deck-ingestion-sequence.png](diagrams/images/deck-ingestion-sequence.png) | [deck-ingestion-sequence.drawio](diagrams/deck-ingestion-sequence.drawio) |
| Deck presentation sequence | [deck-present-sequence.png](diagrams/images/deck-present-sequence.png) | [deck-present-sequence.drawio](diagrams/deck-present-sequence.drawio) |
| Video · batch sequence (v1) | [video-batch-sequence.png](diagrams/images/video-batch-sequence.png) | [video-batch-sequence.drawio](diagrams/video-batch-sequence.drawio) (superseded by Mermaid in `video.md`) |
| Agent-chat sequence | [agent-chat-sequence.png](diagrams/images/agent-chat-sequence.png) | [agent-chat-sequence.drawio](diagrams/agent-chat-sequence.drawio) |

> **Note:** the video generator uses a **slide-first pipeline** (one batch-avatar job *per slide* + ffmpeg compose). The current flow is documented with Mermaid diagrams directly inside [video.md](video.md). The older draw.io sequence remains for historical context.

---

## 🚢 Deployment quick links

- All features ship in a single Container App provisioned with `azd up` (see [README › Azure Deployment](../README.md#️-azure-deployment))
- Build & roll: `azd deploy`, or manually `az acr build -r <acr-name> -t ai-presenter:<tag> .` + `az containerapp update -n ca-<token> -g <resource-group> --image ...`
- Auth: `azd up` requires `AUTH_CLIENT_ID`, `AUTH_CLIENT_SECRET` and `ALLOWED_OBJECT_IDS` (Microsoft Entra ID Easy Auth + allowlist); keep `AUTH_MODE=easyauth` in Azure.
- Public live demo: off by default; enable with `azd env set PUBLIC_DEMO_ENABLED true` (see [live-demo.md](live-demo.md#enable-it)).
- Common pitfall: policy-managed enterprise subscriptions may ship storage with `publicNetworkAccess=Disabled`. See [video.md §8](video.md#8-deployment-topology).

---

## 🔍 Looking for…

- **Where is the decks / search / playlists code?** → `demos/backend/routers/decks.py` + `routers/playlists.py` + `services/deck_search.py` + `demos/frontend/src/pages/{HomePage,DecksPage,DeckPresentPage,SearchPage,PlaylistsPage,PlaylistPlayerPage}.tsx`
- **Where is the Live page?** → `demos/frontend/src/pages/LivePage.tsx` + the `/api/upload`, `/api/presentations`, `/ws/voice` endpoints in `demos/backend/app.py`
- **Where is the video code?** → `demos/backend/routers/video.py` + `services/video_*.py` + `demos/frontend/src/pages/Video*.tsx`
- **Where is the podcast code?** → `demos/backend/routers/podcast.py` + `services/podcast_*.py` + `demos/frontend/src/pages/Podcast*.tsx`
- **Where is the public live demo code?** → `/ws/voice/demo` + `/api/demo/config` in `demos/backend/app.py`, `handle_demo_proxy` in `services/voice_proxy.py`, `demos/frontend/src/services/demo.ts`
- **Where are the E2E test scripts?** → `tests/e2e_full.py` (decks / search / playlists + smoke, 30 checks) and `tests/e2e_render.py` (video + podcast full render, 10 checks) — run against local dev (`run-local.ps1`, `AUTH_MODE=disabled`), target set with `AI_PRESENTER_BASE_URL`
- **Where are the fixture decks?** → `tests/fixtures/samples/` — 9 decks, 3 thematic groups (Safety FR, Sustainability EN, AI ES); regenerate with `python tests/fixtures/samples/_generate.py`. `tests/fixtures/decks/` — 6 single-topic decks; regenerate with `python scripts/make_multideck_test.py`
- **How do I add a new language?** → extend `LANGS` in `scripts/video_multilang_run.py` and `VOICES`/`LANGUAGES` in `demos/backend/routers/video.py`
- **Where are the voice → avatar rules?** → `demos/backend/services/video_render.py` → `avatar_for_voice()`

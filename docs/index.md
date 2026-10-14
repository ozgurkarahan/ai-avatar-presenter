# AI Presenter — Documentation Index

A quick, opinionated map of what's in `docs/`. Start with whichever bucket matches what you're trying to do.

---

## 🧭 By use case

| # | Use case | Where |
|---|---|---|
| **UC1 legacy** | Live avatar presenter over a single PowerPoint (WebRTC, real-time Q&A) | [architecture.md](architecture.md), [diagrams/images/uc1-silver-runtime-sequence.png](diagrams/images/uc1-silver-runtime-sequence.png) |
| **UC1 Learning Hub** | Multi-deck corpus with hybrid search + Learning Paths + AI recommendation | [**uc1-learning-hub.md**](uc1-learning-hub.md) ← new |
| **UC2** | Automated static video generation from a PowerPoint (batch, multilingual) | [**uc2-static-video.md**](uc2-static-video.md) |
| **UC3** | Podcast-style dual-avatar video from any document | [uc3-podcast-design.md](uc3-podcast-design.md) |

---

## 🏗 By topic

| Topic | Doc |
|---|---|
| Component architecture, data flows, API contract | [architecture.md](architecture.md) |
| Azure infra deep dive (Bicep, RBAC, security, CI/CD) | [deep-dive-azure.md](deep-dive-azure.md) |
| Parallel "copilot" deployment | [deploy-copilot.md](deploy-copilot.md) |
| Microsoft Teams Static Tab embedding | [teams-integration.md](teams-integration.md) |
| Feasibility assessment (original study) | [feasibility.md](feasibility.md) |
| Security model, vulnerability reporting, operator checklist | [../SECURITY.md](../SECURITY.md) · [README › Security model](../README.md#-security-model) |

---

## 🖼 Diagrams

PNGs are rendered from draw.io sources in [`diagrams/`](diagrams/).

| Diagram | PNG | Source |
|---|---|---|
| Azure architecture (end-to-end) | [azure-architecture.png](diagrams/images/azure-architecture.png) | [azure-architecture.drawio](diagrams/azure-architecture.drawio) |
| UC1 Bronze · VoiceRAG sequence | [uc1-bronze-voicerag-sequence.png](diagrams/images/uc1-bronze-voicerag-sequence.png) | drawio |
| UC1 Silver · ingestion sequence | [uc1-silver-ingestion-sequence.png](diagrams/images/uc1-silver-ingestion-sequence.png) | drawio |
| UC1 Silver · runtime sequence | [uc1-silver-runtime-sequence.png](diagrams/images/uc1-silver-runtime-sequence.png) | drawio |
| UC2 · batch video sequence (v1) | [uc2-batch-video-sequence.png](diagrams/images/uc2-batch-video-sequence.png) | drawio (superseded by Mermaid in `uc2-static-video.md`) |
| Agent-chat sequence | [agent-chat-sequence.png](diagrams/images/agent-chat-sequence.png) | drawio |

> **Note:** UC2 was migrated to a **slide-first pipeline** (one batch-avatar job *per slide* + ffmpeg compose). The new flow is documented with Mermaid diagrams directly inside [uc2-static-video.md](uc2-static-video.md). The older draw.io sequence remains for historical context.

---

## 🚢 Deployment quick links

- UC1/UC2/UC3 combined deploy: single Container App provisioned with `azd up` (see [README › Azure Deployment](../README.md#️-azure-deployment))
- Build & roll: `azd deploy`, or manually `az acr build -r <acr-name> -t ai-presenter:<tag> .` + `az containerapp update -n ca-<token> -g <resource-group> --image ...`
- Auth: `azd up` requires `AUTH_CLIENT_ID`, `AUTH_CLIENT_SECRET` and `ALLOWED_OBJECT_IDS` (Microsoft Entra ID Easy Auth + allowlist); keep `AUTH_MODE=easyauth` in Azure.
- Common pitfall: policy-managed enterprise subscriptions may ship storage with `publicNetworkAccess=Disabled`. See [uc2-static-video.md §8](uc2-static-video.md#8-deployment-topology).

---

## 🔍 Looking for…

- **Where is the UC1 Learning Hub code?** → `demos/backend/routers/uc1.py` + `routers/uc1_paths.py` + `services/uc1_search.py` + `demos/frontend/src/pages/Uc1*.tsx`
- **Where is the UC2 code?** → `demos/backend/routers/static_video.py` + `services/static_*.py` + `demos/frontend/src/pages/StaticVideo*.tsx`
- **Where is the UC3 code?** → `demos/backend/routers/podcast.py` + `services/podcast_*.py` + `demos/frontend/src/pages/PodcastPage.tsx`
- **Where are the E2E test scripts?** → `tests/e2e_full.py` (UC1 + smoke, 30 checks) and `tests/e2e_render.py` (UC2 + UC3 full render, 10 checks) — run against local dev (`run-local.ps1`, `AUTH_MODE=disabled`), target set with `AI_PRESENTER_BASE_URL`
- **Where are the fixture decks?** → `tests/fixtures/samples/` — 9 decks, 3 thematic groups (Safety FR, Sustainability EN, AI ES); regenerate with `python tests/fixtures/samples/_generate.py`. `tests/fixtures/uc1/` — 6 single-topic decks; regenerate with `python scripts/make_multideck_test.py`
- **How do I add a new language?** → extend `LANGS` in `scripts/uc2_multilang_run.py` and `VOICES`/`LANGUAGES` in `demos/backend/routers/static_video.py`
- **Where are the voice → avatar rules?** → `demos/backend/services/static_render.py` → `avatar_for_voice()`

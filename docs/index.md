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
| Feasibility assessment (historical) | [feasibility.md](feasibility.md) |

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

- Live UC1/UC2/UC3 combined deploy: `rg-ai-presenter-sub2` in swedencentral
- Build & roll: `az acr build -r <acr> -t ai-presenter:<tag> .` + `az containerapp update --image ...`
- Common pitfall: MCAPS subs ship storage with `publicNetworkAccess=Disabled`. See [uc2-static-video.md §8](uc2-static-video.md#8-deployment-topology).

---

## 🔍 Looking for…

- **Where is the UC1 Learning Hub code?** → `demos/backend/routers/uc1.py` + `routers/uc1_paths.py` + `services/uc1_search.py` + `demos/frontend/src/pages/Uc1*.tsx`
- **Where is the UC2 code?** → `demos/backend/routers/static_video.py` + `services/static_*.py` + `demos/frontend/src/pages/StaticVideo*.tsx`
- **Where is the UC3 code?** → `demos/backend/routers/podcast.py` + `services/podcast_*.py` + `demos/frontend/src/pages/PodcastPage.tsx`
- **Where are the E2E test scripts?** → `tests/e2e_rfi.py` (UC1 + smoke, 30 checks) and `tests/e2e_render.py` (UC2 + UC3 full render, 10 checks)
- **Where are the fixture decks?** → `tests/fixtures/rfi/` — 9 decks, 3 thematic groups (Safety FR, Sustainability EN, AI ES); regenerate with `python tests/fixtures/rfi/_generate.py`
- **How do I add a new language?** → extend `LANGS` in `scripts/uc2_multilang_run.py` and `VOICES`/`LANGUAGES` in `demos/backend/routers/static_video.py`
- **Where are the voice → avatar rules?** → `demos/backend/services/static_render.py` → `avatar_for_voice()`

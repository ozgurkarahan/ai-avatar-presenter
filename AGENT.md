# AI Presenter

## Overview

AI Presenter: AI-powered avatar presentation assistant that reads PowerPoint speaker notes with multilingual text-to-speech. Upload a PowerPoint deck and an AI avatar autonomously presents it — translating speaker notes into the target language and delivering them via a realistic TTS avatar, without needing a live presenter.

The repo now covers all three use cases of Saint-Gobain **RFI 559** in a single app:
- **UC1 legacy Live Avatar** at `/`
- **UC1 Learning Hub** at `/uc1` — deck catalog + hybrid Azure AI Search + Learning Paths + AI path recommendation
- **UC2 Static Video** at `/video` — batch avatar MP4 pipeline
- **UC3 Podcast** at `/podcast` — dual-avatar conversational format

## Use Cases

### V1 — Core Avatar Presenter (legacy `/`)
1. **Async mode**: Upload a PPT in advance, select target language and avatar, system generates a video of the avatar presenting each slide using speaker notes (translated to target language)
2. **Real-time mode**: Upload PPT on the fly, configure language, avatar begins speaking immediately as user navigates slides
3. **Slide Q&A**: While viewing a slide, user can ask questions about the content being shown — AI answers based on slide content and speaker notes
4. **Multilingual**: Avatar speaks in a chosen language regardless of the source language of the speaker notes (translation + TTS)

### V2 — Teams Integration
5. **Teams embedding**: Integrate the avatar presenter into Microsoft Teams for live meeting scenarios

### V3 — UC1 Learning Hub (`/uc1`)
6. **Multi-deck corpus**: Decks ingested into Azure AI Search (index `uc1-decks`, Sweden Central Free SKU), hybrid vector + keyword retrieval across languages
7. **Learning Paths**: Cosmos-persisted multi-deck sequences; per-step progress tracking (resume slide index); path player auto-connects avatar and auto-presents each deck without re-clicking between steps
8. **AI path recommendation**: `POST /api/uc1/paths/recommend` uses GPT-4.1 JSON mode to pick a coherent, pedagogically-ordered deck sequence from the full catalog for any topic + target language, without persistence

### V4 — UC2 Static Video (`/video`) & UC3 Podcast (`/podcast`)
9. **UC2**: Slide-first render pipeline (1 batch-avatar job per slide → ffmpeg compose → MP4 + SRT)
10. **UC3**: Document → GPT-4.1 dual-speaker dialogue → parallel TTS → ffmpeg compose → MP3/MP4

## Key Technologies

| Service | Purpose |
|---------|---------|
| Azure AI Speech | Text-to-speech with avatar rendering (VoiceLive API + WebRTC, Batch Avatar, DragonHD voices) |
| Azure OpenAI | Translation (GPT-4.1), slide Q&A (RAG), embeddings (text-embedding-3-small), script generation, path recommendation |
| Azure AI Search | UC1 Learning Hub corpus (hybrid vector + keyword, index `uc1-decks`) |
| Azure Cosmos DB | Presentation store + UC1 Learning Paths (container partitioned by `/id`) |
| Azure Blob Storage | Slide images, PPTX source files, rendered media |
| LibreOffice (headless) | PPTX → PDF conversion for slide image rendering |
| Poppler (pdf2image) | PDF → PNG conversion for individual slide images |
| ffmpeg | Video/audio compose for UC2 + UC3 |
| python-pptx | Extract slide text, titles, speaker notes |
| FastAPI + Uvicorn | Backend REST API + WebSocket proxy |
| **Teams SDK** | `@microsoft/teams-js` — context detection, theme adaptation    |
| React 19 + Vite 8 | Frontend SPA — SlideViewer, AvatarPanel, UC1 Learning Hub, Paths, Podcast, Static Video |

## Key Paths

| Path | Description |
|------|-------------|
| `demos/backend/` | FastAPI backend — app.py, config.py, services/, routers/, Dockerfile |
| `demos/backend/routers/uc1.py` | UC1 Learning Hub API (ingest, list, search via Azure AI Search) |
| `demos/backend/routers/uc1_paths.py` | UC1 Learning Paths CRUD + progress + AI `POST /recommend` (GPT-4.1 JSON mode) |
| `demos/backend/routers/podcast.py` | UC3 dual-avatar podcast (ingest, script stream SSE, render, library) |
| `demos/backend/routers/static_video.py` | UC2 batch-avatar MP4 (ingest, script stream NDJSON, render, library) |
| `demos/backend/services/uc1_search.py` | Azure AI Search client for UC1 (hybrid vector + keyword) |
| `demos/backend/services/pptx_parser.py` | PPT parsing + LibreOffice → PDF → PNG image rendering |
| `demos/backend/services/voice_proxy.py` | WebSocket proxy for VoiceLive avatar API |
| `demos/backend/services/qa.py` | In-memory numpy vector search for slide Q&A (legacy UC1) |
| `demos/backend/services/storage.py` | PresentationStore (Cosmos container `presentations`, partitioned by `/id`) |
| `demos/frontend/` | React frontend |
| `demos/frontend/src/main.tsx` | Router — `/`, `/uc1*`, `/video*`, `/podcast*` |
| `demos/frontend/src/pages/Uc1*.tsx` | UC1 Hub (decks list, learn search, paths list/player, present) |
| `demos/frontend/src/components/AvatarPanel.tsx` | WebRTC avatar panel — supports `autoStart` prop for path player zero-click between decks |
| `demos/frontend/src/components/LanguageSelector.tsx` | Language picker with `variant: 'dark' \| 'light'` (dark = purple banners, light = white cards) |
| `demos/frontend/src/services/uc1Api.ts` | UC1 API client (decks, search, paths, recommend) |
| `demos/frontend/src/services/teams.ts` | Microsoft Teams SDK integration helpers |
| `tests/e2e_rfi.py` | End-to-end runner — reset DB + upload 9 RFI fixtures + UC1/UC2/UC3 smoke (30 checks) |
| `tests/e2e_render.py` | Full render E2E for UC2 (MP4) + UC3 (MP3) (10 checks) |
| `tests/fixtures/rfi/` | 9 coherent fixture decks in 3 thematic groups (Safety FR, Sustainability EN, AI ES) |
| `tests/test_uc1_paths_api.py` | pytest for UC1 paths API incl. AI recommend |
| `tests/uc1-learning-paths.spec.ts` | Playwright UI regressions for Learning Paths |
| `scripts/package-teams-app.ps1` | Package Teams app for sideloading |
| `docs/` | Architecture docs, UC1 Learning Hub design, UC2/UC3 design, Teams integration |
| `run-local.ps1` | One-command local dev startup (backend + frontend) |

## Deliverables

- [x] Feasibility assessment (Azure services, architecture)
- [x] Architecture diagram
- [x] PoC demo: PPT upload → slide image rendering → avatar presents with TTS
- [x] Multilingual TTS demonstration (10 DragonHD languages via GPT-4.1 translation)
- [x] Slide Q&A demonstration (in-memory numpy RAG)
- [x] Teams integration — Static Tab (iframe embed) with Teams SDK theme support
- [x] UC1 Learning Hub with Azure AI Search hybrid retrieval
- [x] UC1 Learning Paths with Cosmos persistence + progress + zero-click path player
- [x] UC1 AI path recommendation (GPT-4.1 JSON mode, catalog-validated)
- [x] UC2 Static Video full render pipeline (validated E2E on prod: 5.9 MB mp4 in 370s)
- [x] UC3 Podcast full render pipeline (validated E2E on prod: 854 KB mp3 in 265s)
- [x] E2E test suites — `tests/e2e_rfi.py` (30/30) + `tests/e2e_render.py` (10/10)

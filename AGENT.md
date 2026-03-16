# AI Presenter

## Overview

AI Presenter: AI-powered avatar presentation assistant that reads PowerPoint speaker notes with multilingual text-to-speech. Upload a PowerPoint deck and an AI avatar autonomously presents it — translating speaker notes into the target language and delivering them via a realistic TTS avatar, without needing a live presenter.

## Use Cases

### V1 — Core Avatar Presenter
1. **Async mode**: Upload a PPT in advance, select target language and avatar, system generates a video of the avatar presenting each slide using speaker notes (translated to target language)
2. **Real-time mode**: Upload PPT on the fly, configure language, avatar begins speaking immediately as user navigates slides
3. **Slide Q&A**: While viewing a slide, user can ask questions about the content being shown — AI answers based on slide content and speaker notes
4. **Multilingual**: Avatar speaks in a chosen language regardless of the source language of the speaker notes (translation + TTS)

### V2 — Teams Integration
5. **Teams embedding**: Integrate the avatar presenter into Microsoft Teams for live meeting scenarios

## Key Technologies

| Service | Purpose |
|---------|---------|
| Azure AI Speech | Text-to-speech with avatar rendering (VoiceLive API + WebRTC) |
| Azure OpenAI | Translation (GPT-4.1), slide Q&A (RAG), embeddings (text-embedding-3-small) |
| LibreOffice (headless) | PPTX → PDF conversion for slide image rendering |
| Poppler (pdf2image) | PDF → PNG conversion for individual slide images |
| python-pptx | Extract slide text, titles, speaker notes |
| FastAPI + Uvicorn | Backend REST API + WebSocket proxy |
| **Teams SDK** | `@microsoft/teams-js` — context detection, theme adaptation    |
| React 19 + Vite 8 | Frontend SPA with slide viewer, avatar panel, Q&A chat |

## Key Paths

| Path | Description |
|------|-------------|
| `demos/backend/` | FastAPI backend — app.py, config.py, services/, Dockerfile |
| `demos/backend/services/pptx_parser.py` | PPT parsing + LibreOffice → PDF → PNG image rendering |
| `demos/backend/services/voice_proxy.py` | WebSocket proxy for VoiceLive avatar API |
| `demos/backend/services/qa.py` | In-memory numpy vector search for slide Q&A |
| `demos/frontend/` | React frontend — slide viewer, avatar panel, Q&A chat |
| `demos/frontend/src/components/SlideViewer.tsx` | Slide display (images when available, text fallback) |
| `demos/frontend/src/components/AvatarPanel.tsx` | WebRTC avatar video/audio panel |
| `demos/frontend/src/services/teams.ts` | Microsoft Teams SDK integration helpers |
| `demos/frontend/public/teams/` | Teams app manifest and icons |
| `scripts/package-teams-app.ps1` | Package Teams app for sideloading |
| `docs/` | Architecture docs, feasibility analysis, Teams integration |
| `run-local.ps1` | One-command local dev startup (backend + frontend) |
| `.copilot-instructions.md` | Technical context for Copilot assistance |

## Deliverables

- [x] Feasibility assessment (Azure services, architecture)
- [x] Architecture diagram
- [x] PoC demo: PPT upload → slide image rendering → avatar presents with TTS
- [x] Multilingual TTS demonstration (EN/FR/ES via GPT-4.1 translation)
- [x] Slide Q&A demonstration (in-memory numpy RAG)
- [x] Teams integration — Static Tab (iframe embed) with Teams SDK theme support

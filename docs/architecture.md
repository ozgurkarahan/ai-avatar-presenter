# AI Presenter — Architecture Document

## System Overview

The AI Presenter is a web-based application that allows users to upload PowerPoint presentations and have an AI avatar present them with multilingual text-to-speech. The system supports real-time presentation (avatar speaks as user navigates slides) and batch generation (pre-render full presentation video).

---

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                             │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  PPT Upload   │  │ Slide Viewer │  │  Avatar Display          │  │
│  │  Component    │  │ + Navigator  │  │  (WebRTC via VoiceLive)  │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
│         │                 │                        │                │
│  ┌──────┴─────────────────┴────────────────────────┴─────────────┐  │
│  │              Q&A Chat Panel                                   │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│         Azure Speech SDK JS  │  REST API (fetch)                    │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI on App Service)                  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                     API Router (app.py)                          │ │
│  │                                                                  │ │
│  │  POST /api/upload          → PPT Parser Service                  │ │
│  │  GET  /api/presentations   → List uploaded presentations         │ │
│  │  GET  /api/slides/{id}     → Get slide data (text, notes, image) │ │
│  │  POST /api/translate       → Translation Service                 │ │
│  │  GET  /api/avatar/token    → Get Speech SDK auth token           │ │
│  │  POST /api/avatar/batch    → Batch Avatar Synthesis              │ │
│  │  POST /api/qa              → Slide Q&A Service                   │ │
│  └──────────┬──────────┬──────────┬──────────┬─────────────────────┘ │
│             │          │          │          │                        │
│  ┌──────────▼───┐ ┌───▼────────┐ ┌▼─────────▼──┐ ┌──────────────┐  │
│  │ PPT Parser   │ │ Translation│ │ Avatar       │ │ Q&A (RAG)    │  │
│  │ Service      │ │ Service    │ │ Service      │ │ Service      │  │
│  │              │ │            │ │              │ │              │  │
│  │ python-pptx  │ │ GPT-4.1   │ │ VoiceLive    │ │ Embeddings + │  │
│  │ + LibreOffice│ │ chat API  │ │ WebSocket    │ │ numpy vector │  │
│  │ + pdf2image  │ │ translate  │ │ + WebRTC     │ │ + GPT-4.1    │  │
│  └──────┬───────┘ └─────┬─────┘ └──────┬──────┘ └──────┬───────┘  │
│         │               │              │               │            │
└─────────┼───────────────┼──────────────┼───────────────┼────────────┘
          │               │              │               │
          ▼               ▼              ▼               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        AZURE SERVICES                                │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ Azure AI Speech   │  │ Azure OpenAI      │  │ In-Memory        │   │
│  │ (Sweden Central)  │  │ (Sweden Central)  │  │ Vector Store     │   │
│  │                   │  │                   │  │                   │   │
│  │ • TTS Neural      │  │ • GPT-4.1         │  │ • numpy cosine    │   │
│  │   Voices          │  │   (translation,   │  │   similarity      │   │
│  │ • VoiceLive       │  │    Q&A generation) │  │ • text-embedding- │   │
│  │   Avatar API      │  │ • text-embedding-  │  │   3-small vectors │   │
│  │ • WebRTC          │  │   3-small          │  │                   │   │
│  │   streaming       │  │   (RAG embeddings) │  │                   │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘   │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ Azure Blob       │  │ Azure Container  │  │ LibreOffice +    │   │
│  │ Storage           │  │ Apps             │  │ Poppler          │   │
│  │                   │  │                   │  │                   │   │
│  │ • PPT files       │  │ • FastAPI backend │  │ • PPTX → PDF     │   │
│  │ • Generated       │  │ • React static    │  │ • PDF → PNG      │   │
│  │   videos          │  │   files           │  │   slide images   │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Data Flows

### Flow 1: Upload & Parse PowerPoint

```
User → [Upload .pptx] → Frontend → POST /api/upload → Backend
  → python-pptx extracts:
    • Slide count
    • Per-slide: title, body text, speaker notes
  → LibreOffice headless renders slides to images:
    • soffice --headless --convert-to pdf {file.pptx}
    • pdf2image.convert_from_path(pdf, poppler_path=...)
    • Each PIL Image → saved as PNG to data/slides/{id}/{index}.png
  → Store slide images on disk (data/slides/)
  → Index slide content in vector store (in-memory numpy embeddings)
  → Return presentation ID + slide metadata (including image_url) to Frontend
```

### Flow 2: Real-Time Avatar Presentation

```
User → [Selects slide + language] → Frontend
  → Frontend connects WebSocket to /ws/voice (backend proxy)
  → Backend connects to Azure VoiceLive API:
    wss://{resource}.cognitiveservices.azure.com/voice-live/realtime
  → Backend sends session.update with AvatarConfig (lisa/casual-sitting)
  → Azure returns ICE servers (TURN credentials)
  → Frontend sets up WebRTC RTCPeerConnection with ICE servers
  → Frontend sends SDP offer via session.avatar.connect
  → Azure returns SDP answer, WebRTC connects
  → Avatar video + audio streams to browser
  → User navigates to next slide → repeat
```

### Flow 3: Batch Video Generation

```
User → [Click "Generate Video"] → Frontend → POST /api/avatar/batch → Backend
  → For each slide:
    1. Get speaker notes
    2. Translate if target language ≠ source (via GPT-4o)
    3. Build SSML with voice for target language
    4. Call Azure Speech Batch Avatar API
    5. Poll for completion, download MP4
  → Stitch slide videos (or return individual)
  → Store in Blob Storage
  → Return download URL to Frontend
```

### Flow 4: Slide Q&A

```
User → [Types question about current slide] → Frontend → POST /api/qa → Backend
  → Generate embedding for question (Azure OpenAI text-embedding-3-small)
  → Search in-memory numpy vector store (cosine similarity, filtered by presentation)
  → Retrieve top-k relevant slide chunks
  → Build prompt: system context + slide chunks + user question
  → Call GPT-4.1 for answer
  → Return answer to Frontend (optionally, avatar speaks it)
```

### Flow 5: Translation

```
Backend → Translation Service
  → Input: speaker notes text + target language (fr-FR / es-ES)
  → Call Azure OpenAI GPT-4o:
    System: "You are a professional translator. Translate the following text to {language}. Preserve formatting and tone."
    User: "{speaker notes text}"
  → Return translated text
```

---

## API Contract

### `POST /api/upload`
Upload a PowerPoint file. Renders slides as PNG images via LibreOffice.
- **Request**: `multipart/form-data` with `.pptx` file
- **Response**: `{ "id": "uuid", "filename": "...", "slide_count": 12, "slides": [...] }`

### `GET /api/presentations`
List all uploaded presentations.
- **Response**: `[{ "id": "uuid", "filename": "...", "slide_count": 12, "created_at": "..." }]`

### `GET /api/slides/{presentation_id}/{filename}`
Serve a rendered slide PNG image.
- **Response**: `image/png` binary data (327-854KB per slide)

### `GET /api/slides/{presentation_id}`
Get all slides for a presentation.
- **Response**: `{ "slides": [{ "index": 0, "title": "...", "body": "...", "notes": "...", "image_url": "/api/slides/{id}/0.png" }] }`

### `POST /api/translate`
Translate text to target language.
- **Request**: `{ "text": "...", "target_language": "fr-FR" }`
- **Response**: `{ "translated_text": "...", "source_language": "en-US" }`

### `GET /api/avatar/token`
Get a Speech SDK authentication token for the frontend.
- **Response**: `{ "token": "...", "region": "westeurope" }`

### `POST /api/avatar/batch`
Generate batch avatar video for a presentation.
- **Request**: `{ "presentation_id": "uuid", "target_language": "fr-FR", "avatar": "lisa" }`
- **Response**: `{ "job_id": "uuid", "status": "processing" }`

### `GET /api/avatar/batch/{job_id}`
Check batch generation status.
- **Response**: `{ "status": "completed", "video_url": "..." }`

### `POST /api/qa`
Ask a question about slide content.
- **Request**: `{ "presentation_id": "uuid", "slide_index": 3, "question": "What is the main point?" }`
- **Response**: `{ "answer": "...", "source_slides": [3] }`

---

## Voice Configuration

| Language | Voice Name | Gender | Style |
|----------|-----------|--------|-------|
| English (US) | `en-US-AvaMultilingualNeural` | Female | Conversational |
| French (FR) | `fr-FR-DeniseNeural` | Female | Conversational |
| Spanish (ES) | `es-ES-ElviraNeural` | Female | Conversational |

Alternative multilingual approach: Use `en-US-AvaMultilingualNeural` for all languages (it supports multilingual synthesis from a single voice).

---

## Avatar Configuration

For the PoC, use Microsoft's standard prebuilt avatars:

| Avatar | Description | Use Case |
|--------|------------|----------|
| `lisa` | Professional female | Default presenter |
| `harry` | Professional male | Alternative presenter |

Standard avatars require no Microsoft approval and are available immediately in supported regions.

---

## Deployment Architecture

```
Resource Group: rg-<environment-name>
Region: Sweden Central (swedencentral)

├── Azure AI Speech / AIServices (S0)
│   └── Endpoint: https://<your-ai-services>.cognitiveservices.azure.com
│   └── VoiceLive API (avatar WebRTC streaming)
│
├── Azure OpenAI (S0)
│   ├── Deployment: gpt-4.1 (chat + translation + Q&A)
│   └── Deployment: text-embedding-3-small (RAG embeddings)
│
├── In-Memory Vector Store (numpy)
│   └── Cosine similarity search over slide embeddings
│   └── Ephemeral — resets on container restart
│
├── Azure Storage Account (Standard LRS)
│   ├── Container: presentations (PPT files)
│   └── Container: videos (generated avatar videos)
│
└── Azure Container Apps (target deployment)
    ├── Python 3.12 + FastAPI + React static build
    ├── LibreOffice (libreoffice-impress) for slide rendering
    ├── Poppler (poppler-utils) for PDF → PNG
    └── fonts-liberation for proper text rendering
```

---

## Security Considerations (PoC Scope)

- Speech SDK tokens issued by backend (short-lived, not exposing keys to client)
- Blob Storage access via backend only (no public container access)
- Azure OpenAI accessed via backend only (key stored in App Service config)
- CORS configured for App Service domain only
- No user authentication for PoC (single-tenant demo)

---

## Directory Structure

```
ai-presenter - Copilot/
├── AGENT.md                    ← Project overview & deliverables
├── run-local.ps1               ← One-command local dev startup
├── docs/
│   ├── feasibility.md
│   ├── architecture.md         ← this document
│   └── teams-integration.md    ← V2 analysis
├── demos/
│   ├── backend/
│   │   ├── app.py              ← FastAPI app (REST + WebSocket)
│   │   ├── config.py           ← Azure service configuration
│   │   ├── requirements.txt    ← Python dependencies
│   │   ├── Dockerfile          ← Container build (LibreOffice + poppler)
│   │   ├── .env                ← Local dev environment variables
│   │   ├── data/
│   │   │   ├── uploads/        ← Uploaded PPTX files
│   │   │   └── slides/         ← Rendered PNG slide images
│   │   └── services/
│   │       ├── pptx_parser.py  ← PPT parsing + LibreOffice image rendering
│   │       ├── voice_proxy.py  ← WebSocket proxy for VoiceLive avatar API
│   │       ├── translation.py  ← GPT-4.1 translation
│   │       └── qa.py           ← Slide Q&A (numpy RAG)
│   └── frontend/
│       ├── package.json
│       ├── vite.config.ts      ← Proxy config for /api and /ws
│       ├── src/
│       │   ├── App.tsx
│       │   ├── components/
│       │   │   ├── PptUpload.tsx
│       │   │   ├── SlideViewer.tsx    ← Slide display (PNG images + text fallback)
│       │   │   ├── AvatarPanel.tsx    ← WebRTC avatar video/audio
│       │   │   ├── LanguageSelector.tsx
│       │   │   └── QaChat.tsx
│       │   └── services/
│       │       └── api.ts
│       └── public/
├── infra/
│   ├── main.bicep              ← All Azure resources
│   ├── main.parameters.json
│   └── modules/
│       ├── speech.bicep
│       ├── openai.bicep
│       ├── storage.bicep
│       └── appservice.bicep
└── azure.yaml                  ← azd configuration
```

# 🎙️ AI Presenter

**An AI-powered avatar presentation assistant** — upload a PowerPoint, and let an AI avatar present your slides with natural text-to-speech, multilingual support, and interactive Q&A.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=white)](https://react.dev/)
[![Azure](https://img.shields.io/badge/Azure-AI%20Services-0078D4.svg?logo=microsoftazure&logoColor=white)](https://azure.microsoft.com/)

---

## ✨ Features

- **📂 PowerPoint Upload** — Upload `.pptx` files; slides are automatically parsed and rendered as images
- **🧑‍💼 AI Avatar Presenter** — A photorealistic avatar narrates each slide using Azure AI Speech (VoiceLive)
- **🌍 Multilingual TTS** — Translate and present in English, French, or Spanish via GPT-4.1 translation
- **❓ Slide Q&A** — Ask questions about slide content using RAG with in-memory vector search (numpy + embeddings)
- **🎥 Real-Time Streaming** — Avatar delivered via WebRTC for low-latency video/audio
- **🖼️ Slide Rendering** — High-quality PNG generation from PPTX via LibreOffice headless + Poppler
- **🚀 One-Click Deployment** — Deploy to Azure Container Apps with `azd up`
- **📎 Teams Integration** — Embed the app as a Microsoft Teams Static Tab with theme support (dark/light/contrast)

---

## 🏗️ Architecture

```
┌──────────────────┐       ┌──────────────────────┐       ┌─────────────────────────┐
│                  │       │                      │       │    Azure Services       │
│   Browser        │       │   FastAPI Backend     │       │                         │
│   (React SPA)    │◄─────►│   (Python 3.12)      │──────►│  Azure AI Speech        │
│                  │ HTTP  │                      │       │   ├─ VoiceLive Avatar    │
│  ┌────────────┐  │  &    │  ┌────────────────┐  │       │   └─ Text-to-Speech     │
│  │SlideViewer │  │ WS    │  │ PPTX Parser    │  │       │                         │
│  │AvatarPanel │  │       │  │ Translation    │  │       │  Azure OpenAI           │
│  │QA Chat     │  │       │  │ Avatar Service │  │       │   ├─ GPT-4.1            │
│  │Language    │  │       │  │ QA (RAG)       │  │       │   └─ text-embedding-    │
│  │ Selector   │  │       │  │ Voice Proxy    │  │       │       3-small           │
│  └────────────┘  │       │  └────────────────┘  │       │                         │
└──────────────────┘       └──────────────────────┘       └─────────────────────────┘
                                     │
                           ┌─────────┴─────────┐
                           │  LibreOffice       │
                           │  PPTX → PDF → PNG  │
                           │  (Poppler)         │
                           └───────────────────┘
```

---

## 🛠️ Tech Stack

| Layer            | Technology                                                  |
| ---------------- | ----------------------------------------------------------- |
| **Frontend**     | React 19, TypeScript, Vite 8                                |
| **Backend**      | Python 3.12, FastAPI, Uvicorn, Gunicorn                     |
| **AI / Speech**  | Azure AI Speech (VoiceLive Avatar API, TTS)                 |
| **AI / LLM**    | Azure OpenAI — GPT-4.1, text-embedding-3-small              |
| **Slide Render** | LibreOffice Impress (headless) → PDF → pdf2image (Poppler)  |
| **Vector Search**| In-memory numpy cosine similarity                           |
| **Auth**         | Azure AD / Managed Identity (`DefaultAzureCredential`)      |
| **Infra**        | Azure Container Apps, Bicep IaC, Azure Developer CLI (`azd`)|
| **Teams**        | `@microsoft/teams-js` SDK, Static Tab manifest (v1.17)      |
| **Containerization** | Docker (multi-stage build)                              |

---

## 📋 Prerequisites

| Requirement                  | Version  | Notes                                          |
| ---------------------------- | -------- | ---------------------------------------------- |
| **Python**                   | 3.12+    | Required                                       |
| **Node.js**                  | 18+      | Required for frontend build                    |
| **Azure CLI**                | Latest   | Required — `az login` before running            |
| **Azure Subscription**       | —        | With AI Speech & OpenAI resources provisioned  |
| **LibreOffice**              | 7.x+     | Optional — needed for PPTX → PNG rendering     |
| **Poppler**                  | Latest   | Optional — needed for PDF → PNG conversion     |
| **Azure Developer CLI (azd)**| Latest   | Optional — needed for `azd up` deployment      |

---

## 🚀 Quick Start

### Windows (recommended)

The included PowerShell script starts both backend and frontend with a single command:

```powershell
# 1. Clone the repository
git clone https://github.com/<your-org>/ai-presenter.git
cd ai-presenter

# 2. Copy and configure environment variables
cp demos/backend/.env.example demos/backend/.env
# Edit demos/backend/.env with your Azure credentials

# 3. Run the local development script
./run-local.ps1

# Skip dependency installation on subsequent runs
./run-local.ps1 -SkipInstall
```

This will:
- Create a Python virtual environment and install dependencies
- Install Node.js packages and build the frontend
- Start the FastAPI backend on **http://localhost:8000**
- Start the Vite dev server on **http://localhost:5173**
- Open your browser automatically

### Manual Setup (macOS / Linux)

```bash
# Backend
cd demos/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # configure your Azure credentials
uvicorn app:app --reload --port 8000

# Frontend (in a new terminal)
cd demos/frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

> **Swagger UI** is available at **http://localhost:8000/docs**

---

## 🔐 Environment Variables

Create a `.env` file in `demos/backend/` (see `.env.example`):

| Variable                           | Required | Default          | Description                                      |
| ---------------------------------- | -------- | ---------------- | ------------------------------------------------ |
| `AZURE_SPEECH_KEY`                 | Yes*     | —                | Azure AI Speech API key                          |
| `AZURE_SPEECH_REGION`              | Yes      | `swedencentral`  | Azure region for Speech service                  |
| `AZURE_SPEECH_ENDPOINT`            | Yes      | —                | Full endpoint URL for AI Speech                  |
| `AZURE_SPEECH_RESOURCE_ID`         | Yes      | —                | Full ARM resource ID for Speech service          |
| `AZURE_OPENAI_ENDPOINT`            | Yes      | —                | Azure OpenAI endpoint URL                        |
| `AZURE_OPENAI_KEY`                 | Yes*     | —                | Azure OpenAI API key                             |
| `AZURE_OPENAI_CHAT_DEPLOYMENT`     | Yes      | `gpt-4.1`       | Chat model deployment name                       |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`| Yes      | `text-embedding-3-small` | Embedding model deployment name          |
| `AZURE_USE_MANAGED_IDENTITY`       | No       | `true`           | Use `DefaultAzureCredential` instead of keys     |
| `LIBREOFFICE_PATH`                 | No       | `soffice`        | Path to LibreOffice binary                       |

> **\*** Not required when `AZURE_USE_MANAGED_IDENTITY=true` and running in Azure with Managed Identity.

---

## 🐳 Docker

The project uses a multi-stage Dockerfile: Node.js builds the frontend, Python serves everything.

```bash
# Build the image
docker build -t ai-presenter .

# Run the container
docker run -p 8000:8000 \
  -e AZURE_SPEECH_KEY=<your-key> \
  -e AZURE_SPEECH_REGION=swedencentral \
  -e AZURE_SPEECH_ENDPOINT=https://<name>.cognitiveservices.azure.com/ \
  -e AZURE_SPEECH_RESOURCE_ID=/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<name> \
  -e AZURE_OPENAI_ENDPOINT=https://<name>.openai.azure.com/ \
  -e AZURE_OPENAI_KEY=<your-key> \
  -e AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4.1 \
  -e AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small \
  ai-presenter
```

The container includes LibreOffice and Poppler for full slide rendering support. The app runs on port **8000** with Gunicorn (4 workers).

---

## ☁️ Azure Deployment

Deploy to Azure Container Apps using the [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/):

```bash
# Authenticate
azd auth login

# Provision infrastructure and deploy
azd up
```

The Bicep templates in `infra/` provision:
- **Azure Container App** with managed identity
- **Role assignments** for AI Speech and OpenAI access
- References to **existing Azure AI Services** and **Azure OpenAI** resources

> Configure deployment parameters in `infra/main.parameters.json` before running `azd up`.

For parallel deployments (e.g., copilot instance), see [docs/deploy-copilot.md](docs/deploy-copilot.md).

---

## 📎 Teams Integration

The app can be embedded in Microsoft Teams as a **Static Tab**:

```powershell
# Package the Teams app (after deploying to Azure)
.\scripts\package-teams-app.ps1 -Hostname "<your-container-app-fqdn>"
```

Then sideload `teams-app-package.zip` in Teams:
1. Open **Teams → Apps → Manage your apps → Upload an app**
2. Select **Upload a custom app** and choose the generated `.zip`
3. The app appears as a personal tab — "AI Presenter"

**Teams features:**
- Automatic theme adaptation (light, dark, high-contrast)
- Compact layout optimized for Teams tab viewport
- CSP headers configured for Teams iframe embedding

---

## 📡 API Reference

| Method | Endpoint                       | Description                              |
| ------ | ------------------------------ | ---------------------------------------- |
| `POST` | `/api/upload`                  | Upload a `.pptx` file for processing     |
| `GET`  | `/api/presentations`           | List all uploaded presentations          |
| `GET`  | `/api/slides/{id}`             | Get slide data for a presentation        |
| `GET`  | `/api/slides/{id}/{n}.png`     | Serve a rendered slide image (PNG)       |
| `POST` | `/api/translate`               | Translate text to a target language       |
| `GET`  | `/api/avatar/token`            | Get Speech SDK authentication token      |
| `POST` | `/api/avatar/batch`            | Start batch avatar video synthesis       |
| `GET`  | `/api/avatar/batch/{job_id}`   | Check batch synthesis job status         |
| `POST` | `/api/qa`                      | Ask a question about slide content (RAG) |
| `WS`   | `/ws/voice`                    | WebSocket proxy for VoiceLive avatar     |
| `GET`  | `/api/health`                  | Health check endpoint                    |

> Full interactive API documentation is available at `/docs` (Swagger UI) when the server is running.

---

## 📁 Project Structure

```
ai-presenter/
├── demos/
│   ├── backend/                  # FastAPI backend
│   │   ├── app.py               # Main application & API routes
│   │   ├── config.py            # Configuration management
│   │   ├── requirements.txt     # Python dependencies
│   │   ├── .env.example         # Environment variable template
│   │   ├── data/
│   │   │   ├── uploads/         # Uploaded PPTX files
│   │   │   └── slides/          # Rendered PNG slide images
│   │   └── services/
│   │       ├── pptx_parser.py   # PPTX parsing & slide rendering
│   │       ├── translation.py   # Azure OpenAI translation
│   │       ├── avatar.py        # Azure Speech avatar service
│   │       ├── voice_proxy.py   # WebSocket voice proxy
│   │       └── qa.py            # RAG-based slide Q&A
│   └── frontend/                 # React SPA
│       ├── src/
│       │   ├── main.tsx         # React entry point
│       │   ├── App.tsx          # Root component
│       │   ├── components/
│       │   │   ├── PptUpload.tsx       # File upload UI
│       │   │   ├── SlideViewer.tsx     # Slide display & navigation
│       │   │   ├── AvatarPanel.tsx     # Avatar video panel
│       │   │   ├── LanguageSelector.tsx # Language picker
│       │   │   └── QaChat.tsx          # Q&A chat interface
│       │   └── services/
│       │       ├── api.ts       # API client
│       │       └── teams.ts     # Teams SDK integration helpers
│       ├── public/
│       │   └── teams/           # Teams app manifest & icons
│       ├── package.json
│       └── vite.config.ts
├── infra/                        # Azure Bicep IaC
│   ├── main.bicep               # Main template
│   ├── main.parameters.json     # Deployment parameters
│   ├── main.parameters.copilot.json  # Copilot instance parameters
│   └── modules/
│       ├── containerapp.bicep   # Container App definition
│       ├── existing-ai.bicep    # AI service references
│       └── roles.bicep          # RBAC role assignments
├── scripts/
│   └── package-teams-app.ps1    # Teams app packaging script
├── docs/                         # Documentation
│   ├── architecture.md
│   ├── deep-dive-azure.md
│   ├── deploy-copilot.md        # Copilot instance deployment guide
│   ├── feasibility.md
│   └── teams-integration.md
├── Dockerfile                    # Multi-stage Docker build
├── azure.yaml                    # Azure Developer CLI config
├── run-local.ps1                 # Local development script (Windows)
├── LICENSE                       # MIT License
└── README.md                     # This file
```

---

## 📚 Documentation

Detailed technical documentation is available in the [`docs/`](docs/) directory:

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Component architecture, data flows, API contract, deployment topology |
| [Deep Dive: Azure Deployment](docs/deep-dive-azure.md) | Full technical walkthrough — infrastructure, Bicep modules, security, CI/CD |
| [Teams Integration](docs/teams-integration.md) | Feasibility analysis and architecture options for Teams embedding |
| [Deploy Copilot Instance](docs/deploy-copilot.md) | Guide for deploying a parallel "copilot" instance to Azure |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Built with ❤️ using Azure AI Services, FastAPI & React
</p>

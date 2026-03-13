# AI Presenter — Feasibility Assessment

## Executive Summary

This document assesses the feasibility of building an AI-powered avatar presentation assistant for organizational training. The system would accept PowerPoint files, read speaker notes aloud via a photorealistic AI avatar, support multilingual text-to-speech, and allow viewers to ask questions about slide content.

**Verdict: Fully feasible using Azure AI services.** All four V1 use cases can be implemented with generally available Azure services. The V2 Teams integration is feasible but significantly more complex.

---

## Use Case Assessment

### UC1 — Async Mode (Upload PPT → Generate Presentation Video)

| Aspect | Assessment |
|--------|-----------|
| **Feasibility** | ✅ Fully feasible |
| **Approach** | Upload PPT → extract speaker notes (python-pptx) → translate if needed (Azure OpenAI GPT-4o) → generate avatar video per slide (Azure AI Speech batch API) → stitch into final presentation video |
| **Azure Service** | Azure AI Speech — Batch Avatar Synthesis (REST API) |
| **Output** | MP4 (H.264/AAC) or WebM (VP9/Opus), 1920×1080 @ 25fps |
| **Latency** | Minutes for a full deck (depends on total speech duration) |
| **Quality** | High — photorealistic standard avatars, neural TTS voices |

**Key details:**
- Batch API accepts SSML or plain text, returns MP4 video of the avatar speaking.
- Standard avatars are available immediately (no Microsoft approval).
- Supports background image/video customization (can overlay the avatar on a slide).
- Video per slide can be generated in parallel, then stitched.

### UC2 — Real-Time Mode (Live Avatar as User Navigates Slides)

| Aspect | Assessment |
|--------|-----------|
| **Feasibility** | ✅ Fully feasible |
| **Approach** | User uploads PPT → navigates slides in web UI → avatar speaks current slide's notes in real-time via WebRTC stream in the browser |
| **Azure Service** | Azure AI Speech SDK (JavaScript) — Real-Time Avatar Synthesis |
| **Output** | WebRTC video stream rendered in browser |
| **Latency** | Sub-second (streaming synthesis) |
| **Quality** | Good — slightly lower fidelity than batch, but interactive |

**Key details:**
- The JavaScript Speech SDK handles the WebRTC connection to Azure's avatar rendering service.
- Microsoft provides an official Flask + JS sample: [Azure-Samples/cognitive-services-speech-sdk/samples/python/web/avatar](https://github.com/Azure-Samples/cognitive-services-speech-sdk/tree/master/samples/python/web/avatar).
- The avatar appears as a video element in the browser — no plugins required.
- Session management needed: start/stop avatar sessions, handle speech queue.

### UC3 — Slide Q&A (Ask Questions About Current Slide)

| Aspect | Assessment |
|--------|-----------|
| **Feasibility** | ✅ Fully feasible |
| **Approach** | RAG pipeline: extract all slide text + notes → generate embeddings → index in Azure AI Search → user asks question → retrieve relevant chunks → GPT-4o generates answer |
| **Azure Services** | Azure OpenAI (embeddings + GPT-4o), Azure AI Search |
| **Latency** | 1-3 seconds per question |
| **Quality** | High — grounded in actual slide content, reduces hallucination |

**Key details:**
- Lightweight RAG: each slide becomes a document chunk (title + body + notes).
- Azure AI Search free tier supports up to 50MB and 3 indexes — sufficient for PoC.
- Can scope answers to the currently displayed slide or search across all slides.
- Optional: have the avatar speak the Q&A answer (combining UC2 + UC3).

### UC4 — Multilingual TTS

| Aspect | Assessment |
|--------|-----------|
| **Feasibility** | ✅ Fully feasible |
| **Approach** | Detect source language → translate notes via Azure OpenAI GPT-4o → synthesize speech with a voice matching the target language |
| **Azure Service** | Azure OpenAI (translation), Azure AI Speech (TTS with language-specific neural voices) |
| **Supported languages** | EN (en-US), FR (fr-FR), ES (es-ES) — all have high-quality neural voices |
| **Quality** | Excellent — Azure neural voices are near-human quality |

**Key details:**
- Azure AI Speech supports 500+ voices across 150+ languages.
- The avatar's lip-sync works with any supported language/voice.
- GPT-4o handles translation inline (no separate Translator service needed for PoC).
- Voice selection per language: e.g., `en-US-AvaMultilingualNeural`, `fr-FR-DeniseNeural`, `es-ES-ElviraNeural`.

### UC5 — Teams Integration (V2)

| Aspect | Assessment |
|--------|-----------|
| **Feasibility** | ⚠️ Feasible but complex — recommended as V2 |
| **Approach** | Bot Framework bot joins Teams meeting via ACS interop → injects avatar video as camera stream → receives meeting audio for potential Q&A interaction |
| **Azure Services** | Azure Communication Services, Azure Bot Service, Teams Real-Time Media Platform |
| **Complexity** | High — requires bot registration, ACS setup, real-time media handling, Teams app publishing |

**Key details:**
- ACS provides full Teams meeting interop (join, audio/video streaming).
- The Real-Time Media Platform allows programmatic injection of video frames.
- Requires Bot Framework registration in Azure, Teams admin consent, and app sideloading or publishing.
- Recommend: build V1 web app first, then architect Teams integration based on lessons learned.

---

## Azure Services Mapping

| Service | SKU / Tier | Purpose | Estimated Monthly Cost (PoC) |
|---------|-----------|---------|------------------------------|
| Azure AI Speech | S0 | TTS + Avatar (batch & real-time) | ~$50-100 (usage-based) |
| Azure OpenAI | S0 | GPT-4o (translation, Q&A), Embeddings | ~$20-50 (usage-based) |
| Azure AI Search | Free (F) | RAG vector index for slide Q&A | $0 |
| Azure Blob Storage | Standard LRS | PPT file storage | < $1 |
| Azure App Service | B1 (Basic) | Host backend + frontend | ~$13/month |
| **Total estimate** | | | **~$85-165/month** |

---

## Technical Risks & Mitigations

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|-----------|-----------|
| 1 | Avatar feature region restrictions | Cannot deploy to preferred region | Medium | Deploy to West Europe or East US 2 (confirmed support) |
| 2 | Real-time avatar latency spikes | Poor demo experience | Low | Pre-translate notes; use batch mode as fallback |
| 3 | PPT slide image rendering | Need visual slide display, not just text | Medium | Use LibreOffice headless for server-side conversion, or render text-only in UI |
| 4 | Azure OpenAI token limits | Large presentations may hit limits | Low | Chunk per slide; process sequentially |
| 5 | Custom avatar requirements | Client may want branded avatar | Low (PoC) | Use standard avatars for PoC; document custom avatar onboarding path |

---

## Recommendations

1. **Start with real-time mode** (UC2) as the primary demo — it's the most impressive for stakeholders.
2. **Add batch mode** (UC1) as a secondary feature for pre-rendering videos.
3. **Deploy to West Europe or Sweden Central** — confirmed avatar support.
4. **Use standard avatars** — no approval process needed, available immediately.
5. **Keep Q&A lightweight** — scope to slide-level chunks, no need for complex document intelligence.
6. **Defer Teams integration to V2** — document the path but focus PoC on the web experience.

---

## Conclusion

All V1 use cases are achievable with generally available Azure services. The tech stack (Python + FastAPI + React + Azure AI Speech + Azure OpenAI) is well-supported with official samples and documentation. The PoC can be deployed with azd + Bicep for reproducible infrastructure. Estimated timeline: feasibility + architecture docs first, then iterative development of the web application.

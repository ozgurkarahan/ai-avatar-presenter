"""AI Presenter — FastAPI Backend Application."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import load_config, AzureConfig
from services.pptx_parser import parse_pptx, PresentationData
from services.translation import get_openai_client, translate_text, detect_language
from services.avatar import get_speech_token, submit_batch_synthesis, get_batch_synthesis_status
from services.voice_proxy import handle_voice_proxy
from services.qa import index_presentation, answer_question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory to store rendered slide images
SLIDES_DIR = Path(__file__).resolve().parent / "data" / "slides"

# In-memory store for presentations (sufficient for PoC)
presentations: dict[str, PresentationData] = {}
config: Optional[AzureConfig] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config
    config = load_config()
    logger.info("AI Presenter backend started. Region: %s", config.speech_region)
    yield


app = FastAPI(
    title="AI Presenter",
    description="AI-powered avatar presentation assistant with multilingual TTS",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request/Response Models ---


class TranslateRequest(BaseModel):
    text: str
    target_language: str  # e.g., "fr-FR", "es-ES"


class TranslateResponse(BaseModel):
    translated_text: str
    source_language: str


class BatchAvatarRequest(BaseModel):
    presentation_id: str
    target_language: str = "en-US"
    avatar: str = "lisa"


class BatchAvatarResponse(BaseModel):
    job_id: str
    status: str


class QaRequest(BaseModel):
    presentation_id: str
    question: str
    slide_index: Optional[int] = None


class QaResponse(BaseModel):
    answer: str
    source_slides: list[int]


class SlideResponse(BaseModel):
    index: int
    title: str
    body: str
    notes: str
    image_url: Optional[str] = None


class PresentationResponse(BaseModel):
    id: str
    filename: str
    slide_count: int
    slides: list[SlideResponse]


class PresentationListItem(BaseModel):
    id: str
    filename: str
    slide_count: int


# --- Health Check ---


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ai-presenter"}


# --- Upload & Parse ---


@app.post("/api/upload", response_model=PresentationResponse)
async def upload_presentation(file: UploadFile = File(...)):
    """Upload and parse a PowerPoint file."""
    if not file.filename or not file.filename.endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only .pptx files are supported")

    content = await file.read()
    try:
        presentation = parse_pptx(content, file.filename, config.libreoffice_path if config else "soffice")
    except Exception as e:
        logger.error("Failed to parse PPTX: %s", e)
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    # Save rendered slide images to disk and set image_url on each slide
    if presentation.slide_images:
        slides_dir = SLIDES_DIR / presentation.id
        slides_dir.mkdir(parents=True, exist_ok=True)
        for idx, png_bytes in presentation.slide_images:
            (slides_dir / f"{idx}.png").write_bytes(png_bytes)
        for slide in presentation.slides:
            slide.image_url = f"/api/slides/{presentation.id}/{slide.index}.png"
        presentation.slide_images = []  # free memory
        logger.info("Saved %d slide images for %s", presentation.slide_count, presentation.id)

    presentations[presentation.id] = presentation

    # Index for Q&A in background (best-effort for PoC)
    try:
        if config and config.openai_endpoint:
            openai_client = get_openai_client(config)
            index_presentation(config, openai_client, presentation)
            logger.info("Indexed presentation %s for Q&A", presentation.id)
    except Exception as e:
        logger.warning("Failed to index for Q&A (non-blocking): %s", e)

    return PresentationResponse(
        id=presentation.id,
        filename=presentation.filename,
        slide_count=presentation.slide_count,
        slides=[
            SlideResponse(
                index=s.index, title=s.title, body=s.body, notes=s.notes,
                image_url=s.image_url,
            )
            for s in presentation.slides
        ],
    )


# --- List & Get Presentations ---


@app.get("/api/presentations", response_model=list[PresentationListItem])
async def list_presentations():
    """List all uploaded presentations."""
    return [
        PresentationListItem(id=p.id, filename=p.filename, slide_count=p.slide_count)
        for p in presentations.values()
    ]


@app.get("/api/slides/{presentation_id}", response_model=PresentationResponse)
async def get_slides(presentation_id: str):
    """Get all slides for a presentation."""
    if presentation_id not in presentations:
        raise HTTPException(status_code=404, detail="Presentation not found")
    p = presentations[presentation_id]
    return PresentationResponse(
        id=p.id,
        filename=p.filename,
        slide_count=p.slide_count,
        slides=[
            SlideResponse(index=s.index, title=s.title, body=s.body, notes=s.notes,
                          image_url=s.image_url)
            for s in p.slides
        ],
    )


@app.get("/api/slides/{presentation_id}/{filename}")
async def get_slide_image(presentation_id: str, filename: str):
    """Serve rendered slide images from disk."""
    file_path = SLIDES_DIR / presentation_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Slide image not found")
    return FileResponse(file_path, media_type="image/png")


# --- Translation ---


@app.post("/api/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest):
    """Translate text to target language."""
    if not config:
        raise HTTPException(status_code=503, detail="Service not configured")

    openai_client = get_openai_client(config)
    source_lang = detect_language(openai_client, req.text, config.openai_chat_deployment)
    translated = translate_text(
        openai_client, req.text, req.target_language, config.openai_chat_deployment
    )
    return TranslateResponse(translated_text=translated, source_language=source_lang)


# --- Avatar ---


@app.get("/api/avatar/token")
async def avatar_token():
    """Get a Speech SDK token for real-time avatar rendering in the browser."""
    if not config:
        raise HTTPException(status_code=503, detail="Service not configured")
    try:
        token_data = get_speech_token(config)
        return token_data
    except Exception as e:
        logger.error("Failed to get speech token: %s", e)
        raise HTTPException(status_code=502, detail="Failed to get speech token")


@app.websocket("/ws/voice")
async def voice_websocket(ws: WebSocket):
    """WebSocket proxy for Azure Voice Live API — real-time avatar streaming."""
    if not config:
        await ws.close(code=1011, reason="Service not configured")
        return

    await ws.accept()
    logger.info("Voice WebSocket client connected")

    try:
        # Wait for initial session.update from client with avatar config
        first_msg = await ws.receive_text()
        msg = json.loads(first_msg)

        avatar_character = "lisa"
        avatar_style = "casual-sitting"
        language = "en-US"
        instructions = None

        if msg.get("type") == "session.update":
            session = msg.get("session", {})
            avatar = session.get("avatar", {})
            avatar_character = avatar.get("character", avatar_character)
            avatar_style = avatar.get("style", avatar_style)
            language = session.get("language", language)
            instructions = session.get("instructions")

        await handle_voice_proxy(
            client_ws=ws,
            config=config,
            avatar_character=avatar_character,
            avatar_style=avatar_style,
            language=language,
            instructions=instructions,
        )
    except WebSocketDisconnect:
        logger.info("Voice WebSocket client disconnected")
    except Exception as e:
        logger.error("Voice WebSocket error: %s", e)
        try:
            await ws.close(code=1011, reason=str(e)[:120])
        except Exception:
            pass


@app.post("/api/avatar/batch", response_model=BatchAvatarResponse)
async def start_batch_avatar(req: BatchAvatarRequest):
    """Start a batch avatar video generation job."""
    if not config:
        raise HTTPException(status_code=503, detail="Service not configured")

    if req.presentation_id not in presentations:
        raise HTTPException(status_code=404, detail="Presentation not found")

    presentation = presentations[req.presentation_id]
    texts = [s.notes or s.body or s.title for s in presentation.slides]

    # Translate if needed
    if req.target_language != "en-US":
        openai_client = get_openai_client(config)
        translated_texts = []
        for text in texts:
            if text:
                translated = translate_text(
                    openai_client, text, req.target_language, config.openai_chat_deployment
                )
                translated_texts.append(translated)
            else:
                translated_texts.append("")
        texts = translated_texts

    job_id = submit_batch_synthesis(config, texts, req.target_language, req.avatar)
    return BatchAvatarResponse(job_id=job_id, status="submitted")


@app.get("/api/avatar/batch/{job_id}")
async def check_batch_status(job_id: str):
    """Check the status of a batch avatar generation job."""
    if not config:
        raise HTTPException(status_code=503, detail="Service not configured")
    status = get_batch_synthesis_status(config, job_id)
    return {
        "job_id": status.job_id,
        "status": status.status,
        "video_url": status.video_url,
        "error": status.error,
    }


# --- Q&A ---


@app.post("/api/qa", response_model=QaResponse)
async def slide_qa(req: QaRequest):
    """Ask a question about slide content."""
    if not config:
        raise HTTPException(status_code=503, detail="Service not configured")

    if req.presentation_id not in presentations:
        raise HTTPException(status_code=404, detail="Presentation not found")

    openai_client = get_openai_client(config)
    result = answer_question(
        config, openai_client, req.question, req.presentation_id, req.slide_index
    )
    return QaResponse(answer=result["answer"], source_slides=result["source_slides"])


# --- Static Files (Frontend SPA) ---

from fastapi.responses import FileResponse

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for any non-API route."""
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

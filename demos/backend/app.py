"""AI Presenter — FastAPI Backend Application."""

from __future__ import annotations

import asyncio
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
from services.storage import PresentationStore

# All supported target languages (en-US is the source, no translation needed)
SUPPORTED_LANGUAGES = [
    "fr-FR", "es-ES", "de-DE", "ja-JP", "zh-CN",
    "it-IT", "pt-BR", "ko-KR", "ar-SA",
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory to store rendered slide images
SLIDES_DIR = Path(__file__).resolve().parent / "data" / "slides"

# In-memory store for presentations (sufficient for PoC)
presentations: dict[str, PresentationData] = {}
config: Optional[AzureConfig] = None
store: Optional[PresentationStore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, store
    config = load_config()
    store = PresentationStore(config)
    logger.info("AI Presenter backend started. Region: %s", config.speech_region)
    if store.available:
        logger.info("Persistence enabled (Cosmos DB + Blob Storage)")
    elif store.cosmos_available:
        logger.info("Persistence partially enabled (Cosmos DB only — Blob Storage unavailable)")
    else:
        logger.info("Persistence disabled — using in-memory store only")
    yield


app = FastAPI(
    title="AI Presenter",
    description="AI-powered avatar presentation assistant with multilingual TTS",
    version="0.1.0",
    lifespan=lifespan,
)

# UC3 — Podcast dual-avatar router
from routers.podcast import router as podcast_router
app.include_router(podcast_router)

# UC2 — Static video (single-narrator slide-first)
from routers.static_video import router as static_video_router
app.include_router(static_video_router)

# UC1 Learning Hub — multi-deck search + present
from routers.uc1 import router as uc1_router
app.include_router(uc1_router)

from routers.uc1_paths import router as uc1_paths_router
app.include_router(uc1_paths_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Allow Teams to iframe the app by setting permissive CSP/frame headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TeamsIframeMiddleware(BaseHTTPMiddleware):
    """Allow Microsoft Teams to embed the app in an iframe."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        # Broad frame-ancestors to support all Teams clients (desktop, web, mobile)
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
        if "X-Frame-Options" in response.headers:
            del response.headers["X-Frame-Options"]
        return response


app.add_middleware(TeamsIframeMiddleware)


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
    avatar: str = "st_gobain_female"


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
    video_url: Optional[str] = None
    translated_notes: dict[str, str] = {}


class PresentationResponse(BaseModel):
    id: str
    filename: str
    slide_count: int
    pptx_url: Optional[str] = None
    slides: list[SlideResponse]


class PresentationListItem(BaseModel):
    id: str
    filename: str
    slide_count: int


class TranslateNotesRequest(BaseModel):
    target_language: str  # e.g., "fr-FR"


class TranslatedSlide(BaseModel):
    index: int
    translated_notes: str


class TranslateNotesResponse(BaseModel):
    presentation_id: str
    target_language: str
    translated_slides: list[TranslatedSlide]
    cached: bool


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

    # Validate file content is a real PPTX (ZIP with [Content_Types].xml)
    import zipfile, io as _io
    if not content[:4] == b"PK\x03\x04":
        raise HTTPException(
            status_code=400,
            detail="Invalid file: not a valid .pptx file. Please upload a PowerPoint (.pptx) file, not .ppt or other formats.",
        )
    try:
        with zipfile.ZipFile(_io.BytesIO(content)) as zf:
            if "[Content_Types].xml" not in zf.namelist():
                raise HTTPException(
                    status_code=400,
                    detail="Invalid file: ZIP archive does not contain PowerPoint data. Please upload a .pptx file.",
                )
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="Invalid file: corrupted or incomplete .pptx file. Please re-export from PowerPoint and try again.",
        )

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
            # Upload to Blob Storage if available
            if store and store.available:
                store.upload_slide_image(presentation.id, idx, png_bytes)
        for slide in presentation.slides:
            # Use Blob Storage URL when available, fallback to local API
            if store and store.available:
                blob_url = store.get_slide_image_url(presentation.id, slide.index)
                slide.image_url = blob_url or f"/api/slides/{presentation.id}/{slide.index}.png"
            else:
                slide.image_url = f"/api/slides/{presentation.id}/{slide.index}.png"
        presentation.slide_images = []  # free memory
        logger.info("Saved %d slide images for %s", presentation.slide_count, presentation.id)

    # Save extracted embedded videos to disk and set video_url on slides
    if presentation.slide_videos:
        slides_dir = SLIDES_DIR / presentation.id
        slides_dir.mkdir(parents=True, exist_ok=True)
        slide_map = {s.index: s for s in presentation.slides}
        for idx, video_bytes, ext in presentation.slide_videos:
            video_filename = f"{idx}{ext}"
            (slides_dir / video_filename).write_bytes(video_bytes)
            if idx in slide_map:
                slide_map[idx].video_url = f"/api/slides/{presentation.id}/{video_filename}"
                logger.info("Saved embedded video for slide %d (%s, %d bytes)", idx + 1, ext, len(video_bytes))
        presentation.slide_videos = []  # free memory

    # Upload original PPTX to Blob Storage for Office Online viewing
    if store and store.available:
        store.upload_pptx(presentation.id, presentation.filename, content)
        pptx_url = store.get_pptx_url(presentation.id, presentation.filename)
        presentation.pptx_url = pptx_url
        logger.info("Uploaded PPTX to Blob Storage for %s", presentation.id)

    # Free raw PPTX bytes from memory
    presentation.pptx_bytes = None

    presentations[presentation.id] = presentation

    # Log extracted notes for debugging
    notes_found = sum(1 for s in presentation.slides if s.notes)
    logger.info(
        "Parsed %s: %d slides, %d with speaker notes",
        presentation.filename, presentation.slide_count, notes_found,
    )
    for s in presentation.slides:
        if s.notes:
            logger.info("  Slide %d notes (%d chars): %s", s.index + 1, len(s.notes), s.notes[:120])
        else:
            logger.info("  Slide %d: no speaker notes", s.index + 1)

    # Persist metadata to Cosmos DB (use cosmos_available — works even if Blob is unreachable)
    if store and store.cosmos_available:
        cosmos_doc = {
            "id": presentation.id,
            "filename": presentation.filename,
            "slide_count": presentation.slide_count,
            "notes_count": notes_found,
            "pptx_url": presentation.pptx_url,
            "slides": [
                {
                    "index": s.index,
                    "title": s.title,
                    "body": s.body,
                    "notes": s.notes,
                    "image_url": s.image_url,
                    "video_url": s.video_url,
                    "translated_notes": {},
                }
                for s in presentation.slides
            ],
        }
        store.save_presentation(cosmos_doc)

    # Index for Q&A in background (best-effort for PoC)
    try:
        if config and config.openai_endpoint:
            openai_client = get_openai_client(config)
            index_presentation(config, openai_client, presentation)
            logger.info("Indexed presentation %s for Q&A", presentation.id)
    except Exception as e:
        logger.warning("Failed to index for Q&A (non-blocking): %s", e)

    # Batch-translate notes for ALL supported languages in background
    if config and config.openai_endpoint and notes_found > 0:
        asyncio.create_task(_batch_translate_all_languages(presentation.id))

    return PresentationResponse(
        id=presentation.id,
        filename=presentation.filename,
        slide_count=presentation.slide_count,
        pptx_url=presentation.pptx_url,
        slides=[
            SlideResponse(
                index=s.index, title=s.title, body=s.body, notes=s.notes,
                image_url=s.image_url, video_url=s.video_url, translated_notes={},
            )
            for s in presentation.slides
        ],
    )


# --- List & Get Presentations ---


@app.get("/api/presentations", response_model=list[PresentationListItem])
async def list_presentations():
    """List all uploaded presentations (from Cosmos DB if available, else in-memory)."""
    # Try Cosmos DB first
    if store and store.cosmos_available:
        cosmos_items = store.list_presentations()
        if cosmos_items:
            return [
                PresentationListItem(
                    id=item["id"],
                    filename=item["filename"],
                    slide_count=item["slide_count"],
                )
                for item in cosmos_items
            ]
    # Fallback to in-memory
    return [
        PresentationListItem(id=p.id, filename=p.filename, slide_count=p.slide_count)
        for p in presentations.values()
    ]


@app.get("/api/slides/{presentation_id}", response_model=PresentationResponse)
async def get_slides(presentation_id: str):
    """Get all slides for a presentation (from memory, then Cosmos DB)."""
    # Check in-memory first
    if presentation_id in presentations:
        p = presentations[presentation_id]
        # Fetch translated_notes from Cosmos DB so the frontend always gets cached translations
        tn_map: dict[int, dict[str, str]] = {}
        if store and store.cosmos_available:
            doc = store.get_presentation(presentation_id)
            if doc:
                tn_map = {s["index"]: s.get("translated_notes", {}) for s in doc.get("slides", [])}
        # Regenerate fresh SAS URLs (stored SAS may have expired)
        effective_pptx_url = store.get_pptx_url(p.id, p.filename) if (store and store.available) else p.pptx_url
        def _fresh_image_url(s: any) -> str:
            if store and store.available:
                return store.get_slide_image_url(p.id, s.index) or s.image_url or f"/api/slides/{p.id}/{s.index}.png"
            return s.image_url or f"/api/slides/{p.id}/{s.index}.png"
        return PresentationResponse(
            id=p.id,
            filename=p.filename,
            slide_count=p.slide_count,
            pptx_url=effective_pptx_url,
            slides=[
                SlideResponse(index=s.index, title=s.title, body=s.body, notes=s.notes,
                              image_url=_fresh_image_url(s),
                              video_url=s.video_url,
                              translated_notes=tn_map.get(s.index, {}))
                for s in p.slides
            ],
        )
    # Try Cosmos DB
    if store and store.cosmos_available:
        doc = store.get_presentation(presentation_id)
        if doc:
            # Rehydrate into in-memory cache
            from services.pptx_parser import PresentationData, SlideData
            slides = [
                SlideData(
                    index=s["index"], title=s["title"], body=s["body"],
                    notes=s["notes"], image_url=s.get("image_url"),
                    video_url=s.get("video_url"),
                )
                for s in doc["slides"]
            ]
            pd = PresentationData(
                id=doc["id"], filename=doc["filename"],
                slide_count=doc["slide_count"], slides=slides,
                pptx_url=doc.get("pptx_url"),
            )
            presentations[doc["id"]] = pd
            # Regenerate fresh SAS URLs for slide images (stored SAS may have expired)
            if store and store.available:
                for s in pd.slides:
                    sas_url = store.get_slide_image_url(pd.id, s.index)
                    if sas_url:
                        s.image_url = sas_url
            # Only expose pptx_url if Blob Storage is reachable; regenerate to avoid expired SAS
            effective_pptx_url = store.get_pptx_url(pd.id, pd.filename) if (store and store.available) else None
            # Build translated_notes from Cosmos doc
            tn_map = {s["index"]: s.get("translated_notes", {}) for s in doc["slides"]}
            blob_ok = store and store.available
            return PresentationResponse(
                id=pd.id, filename=pd.filename, slide_count=pd.slide_count,
                pptx_url=effective_pptx_url,
                slides=[
                    SlideResponse(index=s.index, title=s.title, body=s.body,
                                  notes=s.notes,
                                  image_url=s.image_url if blob_ok else f"/api/slides/{pd.id}/{s.index}.png",
                                  video_url=s.video_url,
                                  translated_notes=tn_map.get(s.index, {}))
                    for s in pd.slides
                ],
            )
    raise HTTPException(status_code=404, detail="Presentation not found")


@app.get("/api/slides/{presentation_id}/{filename}")
async def get_slide_image(presentation_id: str, filename: str):
    """Serve rendered slide images and extracted video files."""
    import mimetypes
    file_path = SLIDES_DIR / presentation_id / filename
    if file_path.exists():
        media_type, _ = mimetypes.guess_type(str(file_path))
        return FileResponse(file_path, media_type=media_type or "application/octet-stream")
    # Try downloading from Blob Storage and cache locally (PNG images only)
    if store and store.cosmos_available and store.available and filename.endswith(".png"):
        slide_index = int(filename.replace(".png", ""))
        data = store.download_slide_image(presentation_id, slide_index)
        if data:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(data)
            return FileResponse(file_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Slide image not found")


# --- Delete & Share ---


@app.delete("/api/presentations/{presentation_id}")
async def delete_presentation(presentation_id: str):
    """Delete a presentation and its slide images from Cosmos DB, Blob Storage, and local disk."""
    deleted_any = False

    # Remove from in-memory store
    if presentation_id in presentations:
        del presentations[presentation_id]
        deleted_any = True

    # Remove from Cosmos DB + Blob Storage
    if store and store.available:
        store.delete_presentation(presentation_id)
        store.delete_slide_images(presentation_id)
        deleted_any = True

    # Remove local disk cache
    slides_dir = SLIDES_DIR / presentation_id
    if slides_dir.exists():
        import shutil
        shutil.rmtree(slides_dir, ignore_errors=True)
        deleted_any = True

    if not deleted_any:
        raise HTTPException(status_code=404, detail="Presentation not found")

    logger.info("Deleted presentation %s", presentation_id)
    return {"status": "deleted", "id": presentation_id}


@app.post("/api/presentations/{presentation_id}/share")
async def share_presentation(presentation_id: str):
    """Share a presentation (placeholder — not yet implemented)."""
    if presentation_id not in presentations:
        if not (store and store.cosmos_available and store.get_presentation(presentation_id)):
            raise HTTPException(status_code=404, detail="Presentation not found")
    # TODO: implement sharing logic (generate shareable link, etc.)
    return {"status": "not_implemented", "message": "Sharing is not yet available."}


# --- Pre-translate Notes ---

# Track background translation progress per presentation
_translation_progress: dict[str, dict] = {}


async def _batch_translate_all_languages(presentation_id: str):
    """Background task: translate notes into all supported languages and cache in Cosmos."""
    _translation_progress[presentation_id] = {
        "total": len(SUPPORTED_LANGUAGES),
        "completed": 0,
        "languages_done": [],
        "status": "in_progress",
    }
    logger.info("Starting batch translation for %s (%d languages)", presentation_id, len(SUPPORTED_LANGUAGES))

    for lang in SUPPORTED_LANGUAGES:
        try:
            # Reuse the existing translate-notes logic internally
            req = TranslateNotesRequest(target_language=lang)
            await translate_notes(presentation_id, req)
            _translation_progress[presentation_id]["completed"] += 1
            _translation_progress[presentation_id]["languages_done"].append(lang)
            logger.info("Batch translate %s: %s done", presentation_id, lang)
        except Exception as e:
            logger.warning("Batch translate %s failed for %s: %s", presentation_id, lang, e)
            _translation_progress[presentation_id]["completed"] += 1

    _translation_progress[presentation_id]["status"] = "completed"
    logger.info("Batch translation complete for %s", presentation_id)


@app.get("/api/presentations/{presentation_id}/translations-status")
async def translations_status(presentation_id: str):
    """Check status of background batch translation for a presentation."""
    progress = _translation_progress.get(presentation_id)
    if progress:
        return progress

    # If no background task tracked, check Cosmos for existing translations
    if store and store.cosmos_available:
        doc = store.get_presentation(presentation_id)
        if doc:
            # Count which languages already have cached translations
            all_langs = set()
            for slide in doc.get("slides", []):
                all_langs.update(slide.get("translated_notes", {}).keys())
            return {
                "total": len(SUPPORTED_LANGUAGES),
                "completed": len(all_langs),
                "languages_done": sorted(all_langs),
                "status": "completed" if len(all_langs) >= len(SUPPORTED_LANGUAGES) else "unknown",
            }

    return {"total": len(SUPPORTED_LANGUAGES), "completed": 0, "languages_done": [], "status": "not_started"}


@app.post("/api/presentations/{presentation_id}/translate-notes", response_model=TranslateNotesResponse)
async def translate_notes(presentation_id: str, req: TranslateNotesRequest):
    """Pre-translate all slide notes for a language and cache in Cosmos DB.

    First call translates via Azure OpenAI and stores results in Cosmos DB.
    Subsequent calls for the same language return cached translations instantly.
    """
    if not config or not config.openai_endpoint:
        raise HTTPException(status_code=503, detail="Translation service not configured")

    target_lang = req.target_language

    # Load slides from Cosmos or in-memory
    cosmos_doc = None
    if store and store.cosmos_available:
        cosmos_doc = store.get_presentation(presentation_id)

    p = presentations.get(presentation_id)
    if not cosmos_doc and not p:
        raise HTTPException(status_code=404, detail="Presentation not found")

    # Build working list of slides (prefer Cosmos as it has cached translations)
    if cosmos_doc:
        slides_data = cosmos_doc.get("slides", [])
    else:
        slides_data = [
            {"index": s.index, "notes": s.notes, "translated_notes": {}}
            for s in p.slides
        ]
        # Try to build cosmos_doc from in-memory so translations can be persisted
        if store and store.cosmos_available:
            cosmos_doc = {
                "id": p.id,
                "filename": p.filename,
                "slide_count": p.slide_count,
                "pptx_url": p.pptx_url,
                "notes_count": sum(1 for s in p.slides if s.notes),
                "slides": slides_data,
            }
            store.save_presentation(cosmos_doc)

    # Separate cached vs. needs-translation
    to_translate = []
    result_map: dict[int, str] = {}

    for sd in slides_data:
        notes = sd.get("notes", "")
        if not notes.strip():
            continue
        cached = sd.get("translated_notes", {}).get(target_lang)
        if cached:
            result_map[sd["index"]] = cached
        else:
            to_translate.append(sd)

    all_cached = len(to_translate) == 0

    # Translate missing notes concurrently
    if to_translate:
        openai_client = get_openai_client(config)
        loop = asyncio.get_event_loop()

        async def _translate_one(slide_doc: dict) -> tuple[int, str]:
            translated = await loop.run_in_executor(
                None,
                translate_text,
                openai_client,
                slide_doc["notes"],
                target_lang,
                config.openai_chat_deployment,
            )
            return slide_doc["index"], translated

        results = await asyncio.gather(*[_translate_one(sd) for sd in to_translate])
        new_translations = dict(results)
        result_map.update(new_translations)

        # Persist new translations in Cosmos DB
        if cosmos_doc and store and store.cosmos_available:
            for slide_doc in cosmos_doc["slides"]:
                idx = slide_doc["index"]
                if idx in new_translations:
                    if "translated_notes" not in slide_doc:
                        slide_doc["translated_notes"] = {}
                    slide_doc["translated_notes"][target_lang] = new_translations[idx]
            store.save_presentation(cosmos_doc)
            logger.info(
                "Cached %d translated notes (%s) for %s",
                len(new_translations), target_lang, presentation_id,
            )

    return TranslateNotesResponse(
        presentation_id=presentation_id,
        target_language=target_lang,
        translated_slides=[
            TranslatedSlide(index=idx, translated_notes=text)
            for idx, text in sorted(result_map.items())
        ],
        cached=all_cached,
    )


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

        avatar_character = ""
        avatar_style = ""
        language = "en-US"
        instructions = None
        voice_name = None

        if msg.get("type") == "session.update":
            session = msg.get("session", {})
            avatar = session.get("avatar", {})
            avatar_character = avatar.get("character", avatar_character)
            avatar_style = avatar.get("style", avatar_style)
            language = session.get("language", language)
            instructions = session.get("instructions")
            voice = session.get("voice")
            if isinstance(voice, str) and voice.strip():
                voice_name = voice.strip()
            elif isinstance(voice, dict):
                candidate = voice.get("name")
                if isinstance(candidate, str) and candidate.strip():
                    voice_name = candidate.strip()

        await handle_voice_proxy(
            client_ws=ws,
            config=config,
            avatar_character=avatar_character,
            avatar_style=avatar_style,
            language=language,
            instructions=instructions,
            voice_name=voice_name,
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


# --- Agent Chat (Function-Calling) ---


class AgentChatMessage(BaseModel):
    role: str = "user"
    content: str


class AgentChatRequest(BaseModel):
    messages: list[AgentChatMessage]
    presentation_id: Optional[str] = None
    slide_index: Optional[int] = None


# Tool definitions for Azure OpenAI function calling
AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "translate_slide_notes",
            "description": "Translate presentation slide text to a target language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Source text to translate"},
                    "target_language": {"type": "string", "description": "BCP-47 code like 'fr-FR', 'es-ES', 'en-US'"},
                },
                "required": ["text", "target_language"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_text_language",
            "description": "Detect the language of a given text. Returns a BCP-47 code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to analyze"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_about_slides",
            "description": "Answer a question about presentation slides based on provided slide content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_context": {"type": "string", "description": "Slide content (title, body, notes)"},
                    "question": {"type": "string", "description": "User's question about the slides"},
                },
                "required": ["slide_context", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_avatar_speech_ssml",
            "description": "Generate SSML markup for avatar text-to-speech.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text the avatar should speak"},
                    "language": {"type": "string", "description": "BCP-47 language code"},
                },
                "required": ["text", "language"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_slide_for_presentation",
            "description": "Translate speaker notes and generate SSML for the avatar. Use when asked to present a slide in a specific language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_title": {"type": "string"},
                    "slide_body": {"type": "string"},
                    "slide_notes": {"type": "string"},
                    "target_language": {"type": "string", "description": "BCP-47 code for the output"},
                },
                "required": ["slide_title", "slide_body", "slide_notes", "target_language"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """\
You are the AI Presenter Assistant — an AI-powered avatar presentation helper.

## Your Capabilities (via tools)
- **translate_slide_notes**: Translate text (e.g., speaker notes) to French, Spanish, or English.
- **detect_text_language**: Detect the language of a given text.
- **ask_about_slides**: Answer questions about slide content when given the slide text.
- **generate_avatar_speech_ssml**: Generate SSML markup for avatar text-to-speech.
- **prepare_slide_for_presentation**: All-in-one: translate speaker notes and generate SSML for the avatar.

## Behavioral Guidelines
1. When the user asks to present a slide, use **prepare_slide_for_presentation**.
2. When the user asks a question about slides, use **ask_about_slides** with the slide content as context.
3. When the user asks for translation only, use **translate_slide_notes**.
4. Always be concise. If a tool returns JSON, extract the relevant fields for the user.
5. If the user does not specify a language, default to English (en-US).
"""


def _execute_tool_call(name: str, arguments: dict) -> str:
    """Execute one of the registered agent tools and return the result."""
    from agent_tools import (
        translate_slide_notes,
        detect_text_language,
        ask_about_slides,
        generate_avatar_speech_ssml,
        prepare_slide_for_presentation,
    )
    dispatch = {
        "translate_slide_notes": lambda a: translate_slide_notes(a["text"], a["target_language"]),
        "detect_text_language": lambda a: detect_text_language(a["text"]),
        "ask_about_slides": lambda a: ask_about_slides(a["slide_context"], a["question"]),
        "generate_avatar_speech_ssml": lambda a: generate_avatar_speech_ssml(a["text"], a["language"]),
        "prepare_slide_for_presentation": lambda a: prepare_slide_for_presentation(
            a["slide_title"], a["slide_body"], a["slide_notes"], a["target_language"]
        ),
    }
    fn = dispatch.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return fn(arguments)
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e)
        return json.dumps({"error": str(e)})




def _run_agent_sync(openai_client, model: str, messages: list[dict]) -> str:
    """Run the function-calling loop synchronously (called via to_thread)."""
    for _ in range(5):
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=AGENT_TOOLS_SCHEMA,
            tool_choice="auto",
            temperature=0.3,
            max_completion_tokens=2048,
        )
        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            messages.append(choice.message.model_dump())
            for tc in choice.message.tool_calls:
                args = json.loads(tc.function.arguments)
                result = _execute_tool_call(tc.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            return choice.message.content or ""

    return "I ran into an issue processing your request. Please try again."


@app.post("/api/agent/chat")
async def agent_chat(req: AgentChatRequest):
    """Multi-turn agent chat with function-calling tools.

    Uses Azure OpenAI function calling to let the LLM decide which tools
    to invoke (translate, Q&A, SSML generation, etc.) based on user intent.
    """
    if not config:
        raise HTTPException(status_code=503, detail="Service not configured")

    openai_client = get_openai_client(config)

    # Build message list for the LLM
    messages: list[dict] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]

    # Inject slide context if available
    if req.presentation_id and req.presentation_id in presentations:
        p = presentations[req.presentation_id]
        if req.slide_index is not None and req.slide_index < len(p.slides):
            s = p.slides[req.slide_index]
            context_msg = (
                f"[Current slide context — Slide {s.index + 1}]\n"
                f"Title: {s.title}\nBody: {s.body}\nNotes: {s.notes}"
            )
            messages.append({"role": "system", "content": context_msg})

    # Append conversation history from the client
    for m in req.messages:
        messages.append({"role": m.role, "content": m.content})

    # Run sync OpenAI calls in a thread to avoid blocking the event loop
    reply = await asyncio.to_thread(
        _run_agent_sync, openai_client, config.openai_chat_deployment, messages
    )
    return {"reply": reply}


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


# --- Teams Tab Configuration Page (for meeting tabs) ---

from fastapi.responses import HTMLResponse


@app.get("/teams-config", response_class=HTMLResponse)
async def teams_config():
    """Serve the Teams tab configuration page for meeting/channel tabs."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head>
    <title>AI Presenter — Tab Configuration</title>
    <script src="https://res.cdn.office.net/teams-js/2.7.1/js/MicrosoftTeams.min.js"></script>
</head>
<body style="font-family:Segoe UI,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f5f5f5;">
    <div style="text-align:center;">
        <h2>AI Presenter</h2>
        <p>Click Save to add AI Presenter to this meeting.</p>
    </div>
    <script>
        (async () => {
            await microsoftTeams.app.initialize();
            microsoftTeams.pages.config.registerOnSaveHandler((saveEvent) => {
                microsoftTeams.pages.config.setConfig({
                    suggestedDisplayName: "AI Presenter",
                    entityId: "presenter-meeting",
                    contentUrl: window.location.origin,
                    websiteUrl: window.location.origin
                });
                saveEvent.notifySuccess();
            });
            microsoftTeams.pages.config.setValidityState(true);
        })();
    </script>
</body>
</html>""")


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
        # Prevent Teams from caching the SPA shell
        return FileResponse(
            os.path.join(STATIC_DIR, "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

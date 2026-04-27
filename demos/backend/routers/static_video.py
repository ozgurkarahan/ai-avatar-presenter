"""UC2 router — FastAPI endpoints for the static-video generator.

Mounted under /api/static-video by app.py. PoC-only: jobs and scripts live
in process memory. Long-running renders are dispatched as BackgroundTasks.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse

from config import AzureConfig, load_config
from services.scorm_packager import build_scorm_package
from services.static_models import (
    IngestResponse,
    JobOutputs,
    JobProgress,
    JobState,
    LanguageOption,
    LibraryItem,
    LibrarySummary,
    NarrationPatch,
    ScriptPatch,
    ScriptRequest,
    SlideNarration,
    StaticDocument,
    StaticJob,
    StaticScript,
    VoiceOption,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/static-video", tags=["static-video"])

# ---------------------------------------------------------------------------
# In-memory stores (PoC)
# ---------------------------------------------------------------------------
DOCUMENTS: dict[str, StaticDocument] = {}
SCRIPTS: dict[str, StaticScript] = {}
JOBS: dict[str, StaticJob] = {}
_JOB_FILES: dict[str, dict[str, Path]] = {}

_LIBRARY = None


def _get_library(cfg: AzureConfig):
    global _LIBRARY
    if _LIBRARY is None:
        from services.static_library import StaticVideoLibrary
        _LIBRARY = StaticVideoLibrary(cfg)
    return _LIBRARY


# ---------------------------------------------------------------------------
# Catalog — 8 DragonHD languages (same set as UC3)
# ---------------------------------------------------------------------------
LANGUAGES: list[LanguageOption] = [
    LanguageOption(code="en-US", name="English (US)"),
    LanguageOption(code="fr-FR", name="French"),
    LanguageOption(code="es-ES", name="Spanish"),
    LanguageOption(code="de-DE", name="German"),
    LanguageOption(code="it-IT", name="Italian"),
    LanguageOption(code="pt-BR", name="Portuguese (Brazil)"),
    LanguageOption(code="zh-CN", name="Chinese (Simplified)"),
    LanguageOption(code="ja-JP", name="Japanese"),
]

VOICES: list[VoiceOption] = [
    VoiceOption(id="en-US-Andrew:DragonHDLatestNeural", display_name="Andrew (HD)",
                language="en-US", gender="male"),
    VoiceOption(id="en-US-Ava:DragonHDLatestNeural", display_name="Ava (HD)",
                language="en-US", gender="female"),
    VoiceOption(id="fr-FR-Remy:DragonHDLatestNeural", display_name="Rémy (HD)",
                language="fr-FR", gender="male"),
    VoiceOption(id="fr-FR-Vivienne:DragonHDLatestNeural", display_name="Vivienne (HD)",
                language="fr-FR", gender="female"),
    VoiceOption(id="es-ES-Tristan:DragonHDLatestNeural", display_name="Tristán (HD)",
                language="es-ES", gender="male"),
    VoiceOption(id="es-ES-Ximena:DragonHDLatestNeural", display_name="Ximena (HD)",
                language="es-ES", gender="female"),
    VoiceOption(id="de-DE-Florian:DragonHDLatestNeural", display_name="Florian (HD)",
                language="de-DE", gender="male"),
    VoiceOption(id="de-DE-Seraphina:DragonHDLatestNeural", display_name="Seraphina (HD)",
                language="de-DE", gender="female"),
    VoiceOption(id="it-IT-Alessio:DragonHDLatestNeural", display_name="Alessio (HD)",
                language="it-IT", gender="male"),
    VoiceOption(id="it-IT-Isabella:DragonHDLatestNeural", display_name="Isabella (HD)",
                language="it-IT", gender="female"),
    VoiceOption(id="pt-BR-Macerio:DragonHDLatestNeural", display_name="Macério (HD)",
                language="pt-BR", gender="male"),
    VoiceOption(id="pt-BR-Thalita:DragonHDLatestNeural", display_name="Thalita (HD)",
                language="pt-BR", gender="female"),
    VoiceOption(id="zh-CN-Xiaochen:DragonHDLatestNeural", display_name="晓辰 Xiaochen (HD)",
                language="zh-CN", gender="female"),
    VoiceOption(id="zh-CN-Yunfan:DragonHDLatestNeural", display_name="云帆 Yunfan (HD)",
                language="zh-CN", gender="male"),
    VoiceOption(id="ja-JP-Masaru:DragonHDLatestNeural", display_name="Masaru (HD)",
                language="ja-JP", gender="male"),
    VoiceOption(id="ja-JP-Nanami:DragonHDLatestNeural", display_name="Nanami (HD)",
                language="ja-JP", gender="female"),
]


def get_cfg() -> AzureConfig:
    return load_config()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Catalog endpoints
# ---------------------------------------------------------------------------
@router.get("/languages", response_model=list[LanguageOption])
def list_languages() -> list[LanguageOption]:
    return LANGUAGES


@router.get("/voices", response_model=list[VoiceOption])
def list_voices(language: Optional[str] = None) -> list[VoiceOption]:
    if language:
        return [v for v in VOICES if v.language == language]
    return VOICES


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------
_ALLOWED_SUFFIXES = {".pptx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
    cfg: AzureConfig = Depends(get_cfg),
) -> IngestResponse:
    """Ingest a PPTX / PDF / single image into a normalized slide list."""
    from services.static_ingest import ingest as do_ingest

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            400,
            f"Unsupported file type '{suffix}'. UC2 accepts: .pptx, .pdf, .png, .jpg, .jpeg",
        )

    tmp_dir = Path("data/uploads/static_video")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}{suffix}"
    tmp_path.write_bytes(await file.read())

    try:
        doc = await asyncio.to_thread(do_ingest, str(tmp_path), file.filename)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("uc2 ingest failed")
        raise HTTPException(500, f"Ingestion failed: {e}")

    DOCUMENTS[doc.doc_id] = doc
    return IngestResponse(
        doc_id=doc.doc_id,
        title=doc.title,
        source_kind=doc.source_kind,
        slides=doc.slides,
    )


# ---------------------------------------------------------------------------
# Script — streaming generate, get, patch
# ---------------------------------------------------------------------------
@router.post("/script/{doc_id}")
async def generate_script(
    doc_id: str,
    req: ScriptRequest,
    cfg: AzureConfig = Depends(get_cfg),
):
    """Stream NDJSON: one SlideNarration per line + a final `done` event."""
    from services.static_script import generate_script_stream

    doc = DOCUMENTS.get(doc_id)
    if not doc:
        raise HTTPException(404, f"Document {doc_id} not found")

    async def gen():
        narrations: list[SlideNarration] = []
        try:
            async for narration in generate_script_stream(cfg, doc, req):
                narrations.append(narration)
                yield json.dumps({"event": "narration", "data": narration.model_dump()}) + "\n"
            script = StaticScript(
                doc_id=doc.doc_id,
                language=req.language,
                style=req.style,
                focus=req.focus,
                voice=req.voice,
                narrations=sorted(narrations, key=lambda n: n.slide_index),
            )
            SCRIPTS[doc.doc_id] = script
            yield json.dumps({"event": "done", "data": script.model_dump()}) + "\n"
        except Exception as e:  # noqa: BLE001
            log.exception("uc2 script stream failed")
            yield json.dumps({"event": "error", "data": {"message": str(e)}}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.get("/script/{doc_id}", response_model=StaticScript)
def get_script(doc_id: str) -> StaticScript:
    script = SCRIPTS.get(doc_id)
    if not script:
        raise HTTPException(404, f"Script for document {doc_id} not found")
    return script


@router.patch("/script/{doc_id}", response_model=StaticScript)
def patch_script(doc_id: str, patch: ScriptPatch) -> StaticScript:
    script = SCRIPTS.get(doc_id)
    if not script:
        raise HTTPException(404, f"Script for document {doc_id} not found")

    by_idx: dict[int, SlideNarration] = {n.slide_index: n for n in script.narrations}
    for p in patch.patches:
        existing = by_idx.get(p.slide_index)
        if existing is None:
            continue  # silently skip unknown slide indices
        if p.narration is not None:
            existing.narration = p.narration
        if p.speaking_style is not None:
            existing.speaking_style = p.speaking_style
        if p.voice is not None:
            existing.voice = p.voice
    script.narrations = sorted(by_idx.values(), key=lambda n: n.slide_index)
    SCRIPTS[doc_id] = script
    return script


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
@router.post("/render/{doc_id}")
async def start_render(
    doc_id: str,
    bg: BackgroundTasks,
    cfg: AzureConfig = Depends(get_cfg),
) -> dict:
    script = SCRIPTS.get(doc_id)
    if not script:
        raise HTTPException(404, f"No script for document {doc_id}; generate one first")
    doc = DOCUMENTS.get(doc_id)
    if not doc:
        raise HTTPException(404, f"Document {doc_id} not found")

    job_id = f"sv-{uuid.uuid4().hex[:8]}"
    job = StaticJob(
        job_id=job_id,
        doc_id=doc_id,
        state=JobState.queued,
        progress=JobProgress(stage="queued", total=len(script.narrations)),
        outputs=JobOutputs(),
        created_at=_now(),
        updated_at=_now(),
    )
    JOBS[job_id] = job
    bg.add_task(_run_render_job, job_id, cfg)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}", response_model=StaticJob)
def get_job(job_id: str) -> StaticJob:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@router.get("/jobs/{job_id}/file/{kind}")
def download_job_file(job_id: str, kind: str):
    """Serve the rendered mp4/mp3/srt/thumb/scorm from local disk (pre-publish)."""
    files = _JOB_FILES.get(job_id)

    # Lazy-generate SCORM package on first request
    if kind == "scorm" and files:
        scorm_path = files.get("scorm")
        if not scorm_path or not scorm_path.exists():
            mp4_path = files.get("mp4")
            srt_path = files.get("srt")
            if not mp4_path or not mp4_path.exists() or not srt_path or not srt_path.exists():
                raise HTTPException(404, "MP4/SRT not available for SCORM packaging")
            job = JOBS.get(job_id)
            if not job:
                raise HTTPException(404, f"Job {job_id} not found")
            doc = DOCUMENTS.get(job.doc_id)
            script = SCRIPTS.get(job.doc_id)
            title = (doc.title if doc else job.doc_id) or job.doc_id
            language = script.language if script else "en-US"
            scorm_path = build_scorm_package(
                title=title,
                language=language,
                media_path=mp4_path,
                srt_path=srt_path,
                out_dir=mp4_path.parent,
                thumbnail_path=files.get("thumb"),
            )
            files["scorm"] = scorm_path

    if not files or kind not in files:
        raise HTTPException(404, "File not found")
    p = files[kind]
    if not p or not p.exists():
        raise HTTPException(404, "File not found on disk")
    media = {
        "mp4": "video/mp4",
        "mp3": "audio/mpeg",
        "srt": "application/x-subrip",
        "thumb": "image/jpeg",
        "scorm": "application/zip",
    }.get(kind, "application/octet-stream")
    dl_name = p.name
    if kind == "scorm":
        _job = JOBS.get(job_id)
        _doc = DOCUMENTS.get(_job.doc_id) if _job else None
        label = (_doc.title if _doc and _doc.title else job_id)
        dl_name = f"{label}-scorm.zip"
    return FileResponse(p, media_type=media, filename=dl_name)


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------
@router.get("/library", response_model=list[LibrarySummary])
def list_library(cfg: AzureConfig = Depends(get_cfg)) -> list[LibrarySummary]:
    lib = _get_library(cfg)
    if not lib.available:
        return []
    return [LibrarySummary(**item) for item in lib.list()]


@router.get("/library/{job_id}", response_model=LibraryItem)
def get_library_item(job_id: str, cfg: AzureConfig = Depends(get_cfg)) -> LibraryItem:
    lib = _get_library(cfg)
    if not lib.available:
        raise HTTPException(503, "Library storage not available")
    item = lib.get(job_id)
    if not item:
        raise HTTPException(404, f"Library item {job_id} not found")
    return LibraryItem(**{
        "job_id": item["job_id"],
        "title": item["title"],
        "document_title": item.get("document_title", ""),
        "created_at": item["created_at"],
        "duration_sec": item.get("duration_sec"),
        "language": item.get("language", "en-US"),
        "voice": item.get("voice", ""),
        "slide_count": item.get("slide_count", 0),
        "thumbnail_url": item.get("thumbnail_url"),
        "video_url": item.get("video_url"),
        "audio_url": item.get("audio_url"),
        "srt_url": item.get("srt_url"),
        "scorm_url": item.get("scorm_url"),
    })


@router.delete("/library/{job_id}")
def delete_library_item(job_id: str, cfg: AzureConfig = Depends(get_cfg)) -> dict:
    lib = _get_library(cfg)
    if not lib.available:
        raise HTTPException(503, "Library storage not available")
    ok = lib.delete(job_id)
    if not ok:
        raise HTTPException(404, "Not found or delete failed")
    return {"deleted": job_id}


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
async def _run_render_job(job_id: str, cfg: AzureConfig) -> None:
    from services.static_render import render_static
    from services.static_compose import compose_static
    from services.static_library import StaticLibraryFiles

    job = JOBS[job_id]
    script = SCRIPTS[job.doc_id]
    doc = DOCUMENTS.get(job.doc_id)

    def _update(state: JobState, stage: str, *, completed: int = 0, total: int | None = None,
                percent: int | None = None, message: str = "", error: Optional[str] = None) -> None:
        job.state = state
        job.progress.stage = stage
        job.progress.completed = completed
        job.progress.total = total if total is not None else len(script.narrations)
        if percent is not None:
            job.progress.percent = max(0, min(100, percent))
        job.progress.message = message
        job.error = error
        job.updated_at = _now()

    try:
        total = len(script.narrations)
        _update(JobState.rendering, "rendering", total=total, percent=5,
                message="Submitting batch avatar jobs…")

        def _progress(done: int, tot: int) -> None:
            # Render dominates 5..75%
            pct = 5 + int((done / max(1, tot)) * 70)
            _update(JobState.rendering, "rendering", completed=done, total=tot,
                    percent=pct, message=f"Synthesized {done}/{tot} slides")

        clips = await asyncio.to_thread(render_static, cfg, script, _progress)

        _update(JobState.composing, "composing", completed=len(clips), percent=78,
                message="Compositing slides + avatar PiP…")
        out_dir = Path("data/static_video/out") / job.job_id
        result = await asyncio.to_thread(compose_static, clips, doc, script, out_dir)

        # Local download URLs (pre-publish fallback)
        job.outputs = JobOutputs(
            video_url=f"/api/static-video/jobs/{job.job_id}/file/mp4",
            audio_url=f"/api/static-video/jobs/{job.job_id}/file/mp3",
            srt_url=f"/api/static-video/jobs/{job.job_id}/file/srt",
            thumbnail_url=f"/api/static-video/jobs/{job.job_id}/file/thumb" if result.thumbnail else None,
            duration_sec=result.duration_sec,
        )
        _JOB_FILES[job.job_id] = {
            "mp4": result.mp4,
            "mp3": result.mp3,
            "srt": result.srt,
            **({"thumb": result.thumbnail} if result.thumbnail else {}),
        }
        _update(JobState.publishing, "publishing", completed=len(clips), percent=92,
                message="Uploading to library…")

        # Publish to blob — failure doesn't fail the job, just flags archive.
        job.archive_state = "archiving"
        try:
            lib = _get_library(cfg)
            if lib.available:
                title = (doc.title if doc else script.doc_id) or script.doc_id
                scorm_path = await asyncio.to_thread(
                    build_scorm_package,
                    title=title,
                    language=script.language,
                    media_path=result.mp4,
                    srt_path=result.srt,
                    out_dir=out_dir,
                    thumbnail_path=result.thumbnail,
                )
                _JOB_FILES[job.job_id]["scorm"] = scorm_path
                manifest = await asyncio.to_thread(
                    lib.publish,
                    job.job_id,
                    StaticLibraryFiles(
                        mp4=result.mp4, mp3=result.mp3, srt=result.srt,
                        thumb=result.thumbnail, scorm=scorm_path,
                    ),
                    title=title,
                    document_title=(doc.title if doc else ""),
                    language=script.language,
                    voice=script.voice,
                    slide_count=len(script.narrations),
                    duration_sec=result.duration_sec,
                    created_at=job.created_at,
                )
                job.archive_state = "published" if manifest else "failed"
            else:
                job.archive_state = "failed"
        except Exception:  # noqa: BLE001
            log.exception("Static library archive failed for %s", job_id)
            job.archive_state = "failed"

        _update(JobState.done, "done", completed=len(clips), percent=100, message="Ready")
    except Exception as e:  # noqa: BLE001
        log.exception("uc2 render job %s failed", job_id)
        _update(JobState.failed, "failed", error=str(e))

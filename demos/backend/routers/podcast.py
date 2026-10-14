"""
UC3 podcast router — FastAPI endpoints for the dual-avatar podcast generator.

This is a PoC/demo surface. Jobs are held in memory; replace with Cosmos in
production. Long-running render work is kicked off with asyncio background
tasks.

Routes are mounted under /api/podcast by app.py.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse

from auth import Principal, get_principal, require_admin
from config import AzureConfig, load_config
from security import (
    DAILY_QUOTA,
    MAX_NARRATION_CHARS,
    MAX_TURNS_PER_SCRIPT,
    PENDING_RENDERS,
    PODCAST_JOB_RE,
    PODCAST_SCRIPT_RE,
    acquire_render_slot,
    read_upload_limited,
    require_id,
    safe_filename,
)
from services import avatar_registry
from services.scorm_packager import build_scorm_package
from services.voice_catalog import HD_VOICES, is_allowed_voice
from services.podcast_models import (
    AvatarOption,
    Document,
    IngestResponse,
    JobOutputs,
    JobProgress,
    JobState,
    LibraryItem,
    LibrarySummary,
    PodcastJob,
    PublishRequest,
    RenderRequest,
    Script,
    ScriptPatch,
    ScriptRequest,
    VoiceOption,
)

logger = logging.getLogger(__name__)
# Everything on `router` is admin-only (default deny). Anonymous library
# reads (published items only) live on `public_router`.
router = APIRouter(prefix="/api/podcast", tags=["podcast"], dependencies=[Depends(require_admin)])
public_router = APIRouter(prefix="/api/podcast", tags=["podcast-public"])

# ---------------------------------------------------------------------------
# In-memory stores (PoC only)
# ---------------------------------------------------------------------------
DOCUMENTS: dict[str, Document] = {}
SCRIPTS: dict[str, Script] = {}
JOBS: dict[str, PodcastJob] = {}
_JOB_FILES: dict[str, dict[str, Path]] = {}

_LIBRARY = None  # lazy singleton


def _get_library(cfg: AzureConfig):
    global _LIBRARY
    if _LIBRARY is None:
        from services.podcast_library import PodcastLibrary
        _LIBRARY = PodcastLibrary(cfg)
    return _LIBRARY


# ---------------------------------------------------------------------------
# Catalog data — curated for the demo
# ---------------------------------------------------------------------------
def _avatars() -> list[AvatarOption]:
    return [AvatarOption(**item) for item in avatar_registry.catalog()]


VOICES: list[VoiceOption] = [
    VoiceOption(id=vid, display_name=name, language=lang, gender=gender, hd=True)
    for vid, name, lang, gender in HD_VOICES
]


def get_cfg() -> AzureConfig:
    return load_config()


# ---------------------------------------------------------------------------
# Catalog endpoints
# ---------------------------------------------------------------------------
@router.get("/avatars", response_model=list[AvatarOption])
def list_avatars() -> list[AvatarOption]:
    return _avatars()


@router.get("/voices", response_model=list[VoiceOption])
def list_voices(language: Optional[str] = None) -> list[VoiceOption]:
    if language:
        return [v for v in VOICES if v.language == language]
    return VOICES


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None, max_length=2048),
    cfg: AzureConfig = Depends(get_cfg),
    principal: Principal = Depends(require_admin),
) -> IngestResponse:
    """Ingest an uploaded PPTX/PDF/DOCX/TXT/MD file (or, if enabled, a URL)."""
    from services.podcast_ingest import ALLOWED_FILE_SUFFIXES, ingest_file, ingest_url
    from services.url_safety import UnsafeURLError, url_ingest_enabled

    if not file and not url:
        raise HTTPException(400, "Provide either a file upload or a url form field")
    if not file and not url_ingest_enabled():
        raise HTTPException(400, "URL ingestion is disabled; upload a file instead")

    original_name = ""
    if file:
        original_name = file.filename or ""
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_FILE_SUFFIXES:
            raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_FILE_SUFFIXES))}")
        content = await read_upload_limited(file)

    # Count against the daily quota only once the request is well-formed.
    DAILY_QUOTA.consume(principal.user_id)

    try:
        if file:
            tmp_dir = Path("data/uploads/podcast"); tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"{uuid.uuid4().hex}{suffix}"
            tmp_path.write_bytes(content)
            doc = await asyncio.to_thread(ingest_file, tmp_path)
            # Preserve the original filename as the display title (ingest sees
            # the uuid-renamed temp file).
            if original_name:
                doc.title = Path(safe_filename(original_name)).stem[:200]
        else:
            doc = await asyncio.to_thread(ingest_url, url)
    except UnsafeURLError as e:
        raise HTTPException(400, f"URL not allowed: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:  # noqa: BLE001
        logger.exception("ingest failed")
        raise HTTPException(500, "Ingestion failed")

    DOCUMENTS[doc.id] = doc
    return IngestResponse(document=doc)


# ---------------------------------------------------------------------------
# Script generation (streaming)
# ---------------------------------------------------------------------------
@router.post("/script/stream")
async def stream_script(
    req: ScriptRequest,
    cfg: AzureConfig = Depends(get_cfg),
    principal: Principal = Depends(require_admin),
):
    """Stream GPT-4.1 script generation as Server-Sent Events."""
    from services.podcast_script import generate_script_stream  # lazy import

    doc = DOCUMENTS.get(req.document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    DAILY_QUOTA.consume(principal.user_id)

    async def gen():
        try:
            turns = []
            async for turn in generate_script_stream(cfg, doc, req):
                turns.append(turn)
                yield f"event: turn\ndata: {turn.model_dump_json()}\n\n"
            script = Script(
                id=f"scr-{uuid.uuid4().hex[:8]}",
                document_id=doc.id,
                language=req.language,
                style=req.style,
                length=req.length,
                turns=turns,
            )
            SCRIPTS[script.id] = script
            yield f"event: done\ndata: {{\"script_id\": \"{script.id}\"}}\n\n"
        except Exception:  # noqa: BLE001
            logger.exception("script stream failed")
            yield 'event: error\ndata: {"message": "Script generation failed"}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.patch("/scripts/{script_id}", response_model=Script)
def patch_script(script_id: str, patch: ScriptPatch) -> Script:
    require_id(script_id, PODCAST_SCRIPT_RE, "Script")
    script = SCRIPTS.get(script_id)
    if not script:
        raise HTTPException(404, "Script not found")
    _check_turns(patch.turns)
    script.turns = patch.turns
    SCRIPTS[script_id] = script
    return script


@router.get("/scripts/{script_id}", response_model=Script)
def get_script(script_id: str) -> Script:
    require_id(script_id, PODCAST_SCRIPT_RE, "Script")
    script = SCRIPTS.get(script_id)
    if not script:
        raise HTTPException(404, "Script not found")
    return script


def _check_turns(turns: list) -> None:
    if len(turns) > MAX_TURNS_PER_SCRIPT:
        raise HTTPException(400, f"Too many turns (max {MAX_TURNS_PER_SCRIPT})")
    for t in turns:
        if len(t.text or "") > MAX_NARRATION_CHARS:
            raise HTTPException(400, f"Turn text too long (max {MAX_NARRATION_CHARS} characters)")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/render", response_model=PodcastJob)
async def start_render(
    req: RenderRequest,
    bg: BackgroundTasks,
    cfg: AzureConfig = Depends(get_cfg),
    principal: Principal = Depends(require_admin),
) -> PodcastJob:
    script = SCRIPTS.get(req.script_id)
    if not script:
        raise HTTPException(404, "Script not found")
    _check_turns(script.turns)
    for role in (req.roles.interviewer, req.roles.expert):
        if not is_allowed_voice(role.voice):
            raise HTTPException(400, "Unsupported voice")
        if not avatar_registry.is_known(role.avatar):
            raise HTTPException(400, "Unknown avatar")
    acquire_render_slot()
    try:
        DAILY_QUOTA.consume(principal.user_id)
    except HTTPException:
        PENDING_RENDERS.release()
        raise
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    job = PodcastJob(
        id=job_id,
        script_id=script.id,
        roles=req.roles,
        layout=req.layout,
        music=req.music,
        intro=req.intro,
        state=JobState.queued,
        progress=JobProgress(stage="queued", total=len(script.turns)),
        outputs=JobOutputs(),
        created_at=_now(),
        updated_at=_now(),
    )
    JOBS[job_id] = job
    bg.add_task(_run_render_job, job_id, cfg)
    return job


@router.get("/jobs/{job_id}", response_model=PodcastJob)
def get_job(job_id: str) -> PodcastJob:
    require_id(job_id, PODCAST_JOB_RE, "Job")
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@router.get("/jobs", response_model=list[PodcastJob])
def list_jobs(limit: int = 20) -> list[PodcastJob]:
    limit = max(1, min(100, limit))
    return sorted(JOBS.values(), key=lambda j: j.created_at, reverse=True)[:limit]


@router.get("/jobs/{job_id}/file/{kind}")
def download_job_file(job_id: str, kind: str):
    """Serve the rendered mp4/mp3/srt/scorm from local disk (PoC)."""
    require_id(job_id, PODCAST_JOB_RE, "Job")
    if kind not in {"mp4", "mp3", "srt", "scorm"}:
        raise HTTPException(404, "File not found")
    files = _JOB_FILES.get(job_id)
    if not files:
        raise HTTPException(404, "File not found")

    # Lazy-generate SCORM package on first request
    if kind == "scorm" and (not files.get("scorm") or not files["scorm"].exists()):
        mp3_path = files.get("mp3")
        srt_path = files.get("srt")
        if not mp3_path or not srt_path:
            raise HTTPException(404, "MP3 or SRT not available for SCORM packaging")
        job = JOBS.get(job_id)
        script = SCRIPTS.get(job.script_id) if job else None
        doc = DOCUMENTS.get(script.document_id) if script else None
        title = (doc.title if doc else job_id) or job_id
        language = script.language if script else "en-US"
        files["scorm"] = build_scorm_package(
            title=title,
            language=language,
            media_path=mp3_path,
            srt_path=srt_path,
            out_dir=mp3_path.parent,
        )

    if kind not in files:
        raise HTTPException(404, "File not found")
    p = files[kind]
    if not p.exists():
        raise HTTPException(404, "File not found on disk")
    media = {"mp4": "video/mp4", "mp3": "audio/mpeg", "srt": "application/x-subrip",
             "scorm": "application/zip"}[kind]
    filename = p.name
    if kind == "scorm":
        job = JOBS.get(job_id)
        script = SCRIPTS.get(job.script_id) if job else None
        doc = DOCUMENTS.get(script.document_id) if script else None
        safe = "".join(c if c.isalnum() or c in " -_" else "" for c in (doc.title if doc else job_id))[:60].strip()
        filename = f"{safe or job_id}-scorm.zip"
    return FileResponse(p, media_type=media, filename=filename)


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------
def _public_item(item: dict) -> dict:
    """Anonymous DTO: no audio/subtitles/SCORM/script, video + thumbnail only."""
    return {
        "job_id": item.get("job_id"),
        "title": item.get("title") or "",
        "created_at": item.get("created_at") or "",
        "duration_sec": item.get("duration_sec"),
        "language": item.get("language") or "en-US",
        "thumbnail_url": item.get("thumbnail_url"),
        "video_url": item.get("mp4_url"),
        "mp4_url": item.get("mp4_url"),
        "mp3_url": None,
        "audio_url": None,
        "srt_url": None,
        "scorm_url": None,
        "script": None,
    }


def _full_item(item: dict) -> dict:
    return LibraryItem(**{
        "job_id": item["job_id"],
        "title": item.get("title") or "",
        "document_title": item.get("document_title") or "",
        "created_at": item.get("created_at") or "",
        "duration_sec": item.get("duration_sec"),
        "language": item.get("language") or "en-US",
        "style": item.get("style") or "casual",
        "speaker_names": item.get("speaker_names") or [],
        "turn_count": item.get("turn_count") or 0,
        "thumbnail_url": item.get("thumbnail_url"),
        "published": bool(item.get("published")),
        "mp4_url": item.get("mp4_url"),
        "mp3_url": item.get("mp3_url"),
        "srt_url": item.get("srt_url"),
        "scorm_url": item.get("scorm_url"),
    }).model_dump()


@public_router.get("/library")
def list_library(
    cfg: AzureConfig = Depends(get_cfg),
    principal: Principal = Depends(get_principal),
) -> list[dict]:
    """Archived podcasts (newest first).

    Admins see every item (with its `published` flag); anonymous callers
    only see published items as public DTOs. Media URLs are minted by
    `GET /library/{job_id}` when the user opens the player.
    """
    lib = _get_library(cfg)
    if not lib.available:
        return []
    if principal.is_admin:
        return [LibrarySummary(**{**item, "title": item.get("title") or "",
                                  "document_title": item.get("document_title") or "",
                                  "created_at": item.get("created_at") or "",
                                  "language": item.get("language") or "en-US",
                                  "style": item.get("style") or "casual"}).model_dump()
                for item in lib.list()]
    return [_public_item(item) for item in lib.list(published_only=True)]


@public_router.get("/library/{job_id}")
def get_library_item(
    job_id: str,
    cfg: AzureConfig = Depends(get_cfg),
    principal: Principal = Depends(get_principal),
) -> dict:
    """A library item with fresh signed URLs (public DTO for anonymous callers)."""
    require_id(job_id, PODCAST_JOB_RE, "Library item")
    lib = _get_library(cfg)
    if not lib.available:
        raise HTTPException(503, "Library storage not available")
    if principal.is_admin:
        item = lib.get(job_id)
        if not item:
            raise HTTPException(404, "Library item not found")
        return _full_item(item)
    item = lib.get(job_id, public=True)
    if not item:
        raise HTTPException(404, "Library item not found")
    return _public_item(item)


@router.post("/library/{job_id}/publish")
def publish_library_item(job_id: str, body: PublishRequest, cfg: AzureConfig = Depends(get_cfg)) -> dict:
    """Admin: show/hide a library item to anonymous viewers."""
    require_id(job_id, PODCAST_JOB_RE, "Library item")
    lib = _get_library(cfg)
    if not lib.available:
        raise HTTPException(503, "Library storage not available")
    item = lib.set_published(job_id, body.published)
    if not item:
        raise HTTPException(404, "Library item not found")
    return _full_item(item)


@router.delete("/library/{job_id}")
def delete_library_item(job_id: str, cfg: AzureConfig = Depends(get_cfg)) -> dict:
    require_id(job_id, PODCAST_JOB_RE, "Library item")
    lib = _get_library(cfg)
    if not lib.available:
        raise HTTPException(503, "Library storage not available")
    ok = lib.delete(job_id)
    if not ok:
        raise HTTPException(404, "Not found or delete failed")
    return {"deleted": job_id}


async def _run_render_job(job_id: str, cfg: AzureConfig) -> None:
    try:
        await _render_job_body(job_id, cfg)
    finally:
        PENDING_RENDERS.release()


async def _render_job_body(job_id: str, cfg: AzureConfig) -> None:
    from services.podcast_render import render_podcast
    from services.podcast_compose import compose_podcast
    from services.podcast_library import LibraryFiles

    job = JOBS[job_id]
    script = SCRIPTS[job.script_id]
    doc = DOCUMENTS.get(script.document_id)

    def _update(state: JobState, stage: str, completed: int = 0,
                message: str = "", error: Optional[str] = None) -> None:
        job.state = state
        job.progress.stage = stage
        job.progress.completed = completed
        job.progress.total = len(script.turns)
        job.progress.message = message
        job.error = error
        job.updated_at = _now()

    try:
        _update(JobState.rendering, "rendering", message="Submitting batch avatar jobs…")
        clips = await asyncio.to_thread(
            render_podcast,
            cfg, script, job.roles,
            lambda done: _update(JobState.rendering, "rendering", completed=done),
            script.language,
        )
        _update(JobState.composing, "composing", completed=len(clips), message="Compositing final video…")
        out_dir = Path("data/podcast/out") / job.id
        result = await asyncio.to_thread(
            compose_podcast,
            clips, doc, script, job.roles, out_dir,
            job.music, job.intro,
        )
        job.outputs = JobOutputs(
            mp4_url=f"/api/podcast/jobs/{job.id}/file/mp4",
            mp3_url=f"/api/podcast/jobs/{job.id}/file/mp3",
            srt_url=f"/api/podcast/jobs/{job.id}/file/srt",
        )
        # Persist file locations for the local download route.
        _JOB_FILES[job.id] = {
            "mp4": result.mp4,
            "mp3": result.mp3,
            "srt": result.srt,
        }

        # Archive to blob library (fire-and-forget semantics — failure doesn't
        # fail the job, just marks archive_state=failed for UI feedback).
        job.archive_state = "archiving"
        job.updated_at = _now()
        try:
            lib = _get_library(cfg)
            if lib.available:
                title = (doc.title if doc else script.id) or script.id
                scorm_path = await asyncio.to_thread(
                    build_scorm_package,
                    title=title,
                    language=script.language,
                    media_path=result.mp3,
                    srt_path=result.srt,
                    out_dir=out_dir,
                )
                _JOB_FILES[job.id]["scorm"] = scorm_path
                manifest = await asyncio.to_thread(
                    lib.publish,
                    job.id,
                    LibraryFiles(mp4=result.mp4, mp3=result.mp3, srt=result.srt, scorm=scorm_path),
                    title=title,
                    document_title=(doc.title if doc else ""),
                    language=script.language,
                    style=script.style,
                    speaker_names=[job.roles.interviewer.display_name,
                                   job.roles.expert.display_name],
                    turn_count=len(script.turns),
                    created_at=job.created_at,
                )
                if manifest:
                    job.archive_state = "published"
                    job.library_job_id = job.id
                else:
                    job.archive_state = "failed"
            else:
                job.archive_state = "failed"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Library archive failed for %s", job_id)
            job.archive_state = "failed"
        finally:
            job.updated_at = _now()

        _update(JobState.done, "done", completed=len(clips), message="Ready")
    except Exception:  # noqa: BLE001
        logger.exception("render job %s failed", job_id)
        _update(JobState.failed, "failed", error="Render failed; see server logs")

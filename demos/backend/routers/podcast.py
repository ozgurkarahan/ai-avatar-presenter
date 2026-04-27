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

from config import AzureConfig, load_config
from services.scorm_packager import build_scorm_package
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
    RenderRequest,
    Script,
    ScriptPatch,
    ScriptRequest,
    VoiceOption,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/podcast", tags=["podcast"])

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
AVATARS: list[AvatarOption] = [
    AvatarOption(id="harry", display_name="Harry", default_style="business",
                 thumbnail_url="/static/avatars/harry.png"),
    AvatarOption(id="lisa", display_name="Lisa", default_style="graceful-sitting",
                 thumbnail_url="/static/avatars/lisa.png"),
]

VOICES: list[VoiceOption] = [
    # English (US)
    VoiceOption(id="en-US-Andrew:DragonHDLatestNeural", display_name="Andrew (HD)",
                language="en-US", gender="male", hd=True),
    VoiceOption(id="en-US-Ava:DragonHDLatestNeural", display_name="Ava (HD)",
                language="en-US", gender="female", hd=True),
    # French (FR)
    VoiceOption(id="fr-FR-Remy:DragonHDLatestNeural", display_name="Rémy (HD)",
                language="fr-FR", gender="male", hd=True),
    VoiceOption(id="fr-FR-Vivienne:DragonHDLatestNeural", display_name="Vivienne (HD)",
                language="fr-FR", gender="female", hd=True),
    # Spanish (ES)
    VoiceOption(id="es-ES-Tristan:DragonHDLatestNeural", display_name="Tristán (HD)",
                language="es-ES", gender="male", hd=True),
    VoiceOption(id="es-ES-Ximena:DragonHDLatestNeural", display_name="Ximena (HD)",
                language="es-ES", gender="female", hd=True),
    # German (DE)
    VoiceOption(id="de-DE-Florian:DragonHDLatestNeural", display_name="Florian (HD)",
                language="de-DE", gender="male", hd=True),
    VoiceOption(id="de-DE-Seraphina:DragonHDLatestNeural", display_name="Seraphina (HD)",
                language="de-DE", gender="female", hd=True),
    # Italian (IT)
    VoiceOption(id="it-IT-Alessio:DragonHDLatestNeural", display_name="Alessio (HD)",
                language="it-IT", gender="male", hd=True),
    VoiceOption(id="it-IT-Isabella:DragonHDLatestNeural", display_name="Isabella (HD)",
                language="it-IT", gender="female", hd=True),
    # Portuguese (Brazil)
    VoiceOption(id="pt-BR-Macerio:DragonHDLatestNeural", display_name="Macério (HD)",
                language="pt-BR", gender="male", hd=True),
    VoiceOption(id="pt-BR-Thalita:DragonHDLatestNeural", display_name="Thalita (HD)",
                language="pt-BR", gender="female", hd=True),
    # Chinese (Mandarin, Simplified)
    VoiceOption(id="zh-CN-Xiaochen:DragonHDLatestNeural", display_name="晓辰 Xiaochen (HD)",
                language="zh-CN", gender="female", hd=True),
    VoiceOption(id="zh-CN-Yunfan:DragonHDLatestNeural", display_name="云帆 Yunfan (HD)",
                language="zh-CN", gender="male", hd=True),
    # Japanese
    VoiceOption(id="ja-JP-Masaru:DragonHDLatestNeural", display_name="Masaru (HD)",
                language="ja-JP", gender="male", hd=True),
    VoiceOption(id="ja-JP-Nanami:DragonHDLatestNeural", display_name="Nanami (HD)",
                language="ja-JP", gender="female", hd=True),
]


def get_cfg() -> AzureConfig:
    return load_config()


# ---------------------------------------------------------------------------
# Catalog endpoints
# ---------------------------------------------------------------------------
@router.get("/avatars", response_model=list[AvatarOption])
def list_avatars() -> list[AvatarOption]:
    return AVATARS


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
    url: Optional[str] = Form(None),
    cfg: AzureConfig = Depends(get_cfg),
) -> IngestResponse:
    """Ingest a PPTX/PDF/DOCX/TXT/MD file or a URL into a Document."""
    from services.podcast_ingest import ingest  # lazy import

    if not file and not url:
        raise HTTPException(400, "Provide either a file upload or a url form field")

    try:
        if file:
            original_name = file.filename or ""
            suffix = Path(original_name).suffix.lower() or ".txt"
            tmp_dir = Path("data/uploads/podcast"); tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"{uuid.uuid4().hex}{suffix}"
            tmp_path.write_bytes(await file.read())
            doc = ingest(str(tmp_path))
            # Preserve the original filename as the display title (ingest sees
            # the uuid-renamed temp file).
            if original_name:
                doc.title = Path(original_name).stem
        else:
            doc = ingest(url)
    except Exception as e:  # noqa: BLE001
        logger.exception("ingest failed")
        raise HTTPException(500, f"Ingestion failed: {e}")

    DOCUMENTS[doc.id] = doc
    return IngestResponse(document=doc)


# ---------------------------------------------------------------------------
# Script generation (streaming)
# ---------------------------------------------------------------------------
@router.post("/script/stream")
async def stream_script(req: ScriptRequest, cfg: AzureConfig = Depends(get_cfg)):
    """Stream GPT-4.1 script generation as Server-Sent Events."""
    from services.podcast_script import generate_script_stream  # lazy import

    doc = DOCUMENTS.get(req.document_id)
    if not doc:
        raise HTTPException(404, f"Document {req.document_id} not found")

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
        except Exception as e:  # noqa: BLE001
            logger.exception("script stream failed")
            safe = str(e).replace("\"", "'")
            yield f"event: error\ndata: {{\"message\": \"{safe}\"}}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.patch("/scripts/{script_id}", response_model=Script)
def patch_script(script_id: str, patch: ScriptPatch) -> Script:
    script = SCRIPTS.get(script_id)
    if not script:
        raise HTTPException(404, f"Script {script_id} not found")
    script.turns = patch.turns
    SCRIPTS[script_id] = script
    return script


@router.get("/scripts/{script_id}", response_model=Script)
def get_script(script_id: str) -> Script:
    script = SCRIPTS.get(script_id)
    if not script:
        raise HTTPException(404, f"Script {script_id} not found")
    return script


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/render", response_model=PodcastJob)
async def start_render(req: RenderRequest, bg: BackgroundTasks, cfg: AzureConfig = Depends(get_cfg)) -> PodcastJob:
    script = SCRIPTS.get(req.script_id)
    if not script:
        raise HTTPException(404, f"Script {req.script_id} not found")
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
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@router.get("/jobs", response_model=list[PodcastJob])
def list_jobs(limit: int = 20) -> list[PodcastJob]:
    return sorted(JOBS.values(), key=lambda j: j.created_at, reverse=True)[:limit]


@router.get("/jobs/{job_id}/file/{kind}")
def download_job_file(job_id: str, kind: str):
    """Serve the rendered mp4/mp3/srt/scorm from local disk (PoC)."""
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
@router.get("/library", response_model=list[LibrarySummary])
def list_library(cfg: AzureConfig = Depends(get_cfg)) -> list[LibrarySummary]:
    """Return all previously-generated podcasts (newest first).

    Each card has a thumbnail SAS URL only; full media URLs are minted by
    `GET /library/{job_id}` when the user opens the player.
    """
    lib = _get_library(cfg)
    if not lib.available:
        return []
    return [LibrarySummary(**item) for item in lib.list()]


@router.get("/library/{job_id}", response_model=LibraryItem)
def get_library_item(job_id: str, cfg: AzureConfig = Depends(get_cfg)) -> LibraryItem:
    """Return a full library item with fresh signed URLs for mp4/mp3/srt."""
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
        "style": item.get("style", "casual"),
        "speaker_names": item.get("speaker_names", []),
        "turn_count": item.get("turn_count", 0),
        "thumbnail_url": item.get("thumbnail_url"),
        "mp4_url": item.get("mp4_url"),
        "mp3_url": item.get("mp3_url"),
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


async def _run_render_job(job_id: str, cfg: AzureConfig) -> None:
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
    except Exception as e:  # noqa: BLE001
        logger.exception("render job %s failed", job_id)
        _update(JobState.failed, "failed", error=str(e))

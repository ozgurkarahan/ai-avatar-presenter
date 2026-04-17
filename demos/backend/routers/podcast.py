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
from services.podcast_models import (
    AvatarOption,
    Document,
    IngestResponse,
    JobOutputs,
    JobProgress,
    JobState,
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
    VoiceOption(id="en-US-Andrew:DragonHDLatestNeural", display_name="Andrew (HD)",
                language="en-US", gender="male", hd=True),
    VoiceOption(id="en-US-Ava:DragonHDLatestNeural", display_name="Ava (HD)",
                language="en-US", gender="female", hd=True),
    VoiceOption(id="fr-FR-Vivienne:DragonHDLatestNeural", display_name="Vivienne (HD)",
                language="fr-FR", gender="female", hd=True),
    VoiceOption(id="fr-FR-Remy:DragonHDLatestNeural", display_name="Remy (HD)",
                language="fr-FR", gender="male", hd=True),
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
            suffix = Path(file.filename or "").suffix.lower() or ".txt"
            tmp_dir = Path("data/uploads/podcast"); tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"{uuid.uuid4().hex}{suffix}"
            tmp_path.write_bytes(await file.read())
            doc = ingest(str(tmp_path))
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
    """Serve the rendered mp4/mp3/srt from local disk (PoC)."""
    files = _JOB_FILES.get(job_id)
    if not files or kind not in files:
        raise HTTPException(404, "File not found")
    p = files[kind]
    if not p.exists():
        raise HTTPException(404, "File not found on disk")
    media = {"mp4": "video/mp4", "mp3": "audio/mpeg", "srt": "application/x-subrip"}[kind]
    return FileResponse(p, media_type=media, filename=p.name)


async def _run_render_job(job_id: str, cfg: AzureConfig) -> None:
    from services.podcast_render import render_podcast
    from services.podcast_compose import compose_podcast

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
        # Persist file locations for the download route.
        _JOB_FILES[job.id] = {"mp4": result.mp4, "mp3": result.mp3, "srt": result.srt}
        _update(JobState.done, "done", completed=len(clips), message="Ready")
    except Exception as e:  # noqa: BLE001
        logger.exception("render job %s failed", job_id)
        _update(JobState.failed, "failed", error=str(e))

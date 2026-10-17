"""Video — narrated slide-video generation — Pydantic models.

================================================================================
VIDEO API CONTRACT (mirror this in the frontend)
================================================================================
Prefix: /api/video

  POST   /ingest                 multipart file (pptx|pdf|png|jpg|jpeg)
                                 -> IngestResponse { doc_id, slides[] }
  POST   /script/{doc_id}        ScriptRequest { language, style?, focus?, audience_level?, voice }
                                 -> NDJSON stream: {"event":"narration","data":SlideNarration},
                                    final line {"event":"done","data":VideoScript}
  GET    /script/{doc_id}        -> VideoScript
  PATCH  /script/{doc_id}        ScriptPatch { patches:[{slide_index, narration?}] }
                                 -> VideoScript
  POST   /render/{doc_id}        -> { job_id }
  GET    /jobs/{job_id}          -> VideoJob (state, progress, outputs)
  GET    /library                -> [LibrarySummary]
  GET    /library/{job_id}       -> LibraryItem (SAS-minted video/audio/srt/scorm/thumb)
  DELETE /library/{job_id}       -> { deleted }
  GET    /voices?language=xx-XX  -> [VoiceOption]
  GET    /languages              -> [{ code, name }]  (8 DragonHD langs)

Script shape is SLIDE-FIRST, not turn-based: exactly one SlideNarration per
normalized input slide. PDF -> one slide per page. Single image -> 1 slide.
================================================================================
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from services.podcast_models import AudienceLevel


SourceKind = Literal["pptx", "pdf", "image"]


# -----------------------------------------------------------------------------
# Ingest
# -----------------------------------------------------------------------------

class SlideRef(BaseModel):
    index: int
    image_ref: str = Field(..., description="Local path or blob URL to the slide PNG/JPG")
    title: Optional[str] = None
    preview_text: str = ""


class VideoDocument(BaseModel):
    doc_id: str
    title: str
    source_kind: SourceKind
    slides: list[SlideRef]


class IngestResponse(BaseModel):
    doc_id: str
    title: str
    source_kind: SourceKind
    slides: list[SlideRef]


# -----------------------------------------------------------------------------
# Script
# -----------------------------------------------------------------------------

Style = Literal["casual", "formal", "explainer", "marketing"]


class SlideNarration(BaseModel):
    slide_index: int
    slide_image_ref: str
    title: Optional[str] = None
    narration: str
    voice: str
    speaking_style: Optional[str] = None
    duration_hint_s: Optional[float] = None


class VideoScript(BaseModel):
    doc_id: str
    language: str = "en-US"
    style: Optional[Style] = "explainer"
    focus: Optional[str] = None
    audience_level: Optional[AudienceLevel] = None
    voice: str
    narrations: list[SlideNarration] = Field(default_factory=list)


class ScriptRequest(BaseModel):
    language: str = Field("en-US", max_length=16)
    style: Optional[Style] = "explainer"
    focus: Optional[str] = Field(None, max_length=500)
    audience_level: Optional[AudienceLevel] = None
    voice: str = Field(..., max_length=100)


class NarrationPatch(BaseModel):
    slide_index: int = Field(..., ge=0, le=1000)
    narration: Optional[str] = Field(None, max_length=3000)
    speaking_style: Optional[str] = Field(None, max_length=64)
    voice: Optional[str] = Field(None, max_length=100)


class ScriptPatch(BaseModel):
    patches: list[NarrationPatch] = Field(..., max_length=200)


# -----------------------------------------------------------------------------
# Render / Jobs
# -----------------------------------------------------------------------------

class JobState(str, Enum):
    queued = "queued"
    rendering = "rendering"
    composing = "composing"
    publishing = "publishing"
    done = "done"
    failed = "failed"


class JobProgress(BaseModel):
    stage: str = "queued"
    percent: int = 0
    completed: int = 0
    total: int = 0
    message: str = ""


class JobOutputs(BaseModel):
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    srt_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_sec: Optional[float] = None


ArchiveState = Literal["none", "archiving", "published", "failed"]


class VideoJob(BaseModel):
    job_id: str
    doc_id: str
    state: JobState = JobState.queued
    progress: JobProgress = Field(default_factory=JobProgress)
    outputs: JobOutputs = Field(default_factory=JobOutputs)
    error: Optional[str] = None
    created_at: str
    updated_at: str
    archive_state: ArchiveState = "none"


# -----------------------------------------------------------------------------
# Library
# -----------------------------------------------------------------------------

class LibrarySummary(BaseModel):
    job_id: str
    title: str
    document_title: str = ""
    created_at: str
    duration_sec: Optional[float] = None
    language: str = "en-US"
    voice: str = ""
    audience_level: Optional[AudienceLevel] = None
    slide_count: int = 0
    thumbnail_url: Optional[str] = None
    published: bool = False


class LibraryItem(LibrarySummary):
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    srt_url: Optional[str] = None
    scorm_url: Optional[str] = None


# -----------------------------------------------------------------------------
# Voice catalog
# -----------------------------------------------------------------------------

class VoiceOption(BaseModel):
    id: str
    display_name: str
    language: str
    gender: Literal["male", "female", "neutral"]
    hd: bool = True


class LanguageOption(BaseModel):
    code: str
    name: str


class PublishRequest(BaseModel):
    published: bool

"""Pydantic models shared by UC3 podcast endpoints and services."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Ingestion
# -----------------------------------------------------------------------------

SourceKind = Literal["pptx", "pdf", "docx", "txt", "md", "url"]


class Section(BaseModel):
    heading: str = ""
    text: str


class Document(BaseModel):
    id: str
    title: str
    source_kind: SourceKind
    sections: list[Section] = []
    # PPTX only
    slide_images: list[str] = Field(
        default_factory=list, description="Ordered blob URLs or local paths (PPTX only)"
    )
    slide_titles: list[str] = Field(default_factory=list)
    slide_notes: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    document: Document


# -----------------------------------------------------------------------------
# Script
# -----------------------------------------------------------------------------

Speaker = Literal["interviewer", "expert"]
Style = Literal["casual", "formal", "debate", "explainer"]
Length = Literal["short", "medium", "long"]  # ~3 / ~6 / ~10 min


class WordTiming(BaseModel):
    word: str
    start_sec: float
    end_sec: float


class DialogueTurn(BaseModel):
    idx: int
    speaker: Speaker
    text: str
    # When source document is a PPTX, GPT assigns the slide that should be
    # visible while this turn is spoken. 0-based index into Document.slide_images.
    slide_idx: Optional[int] = None
    # Populated after render, from the batch avatar WebVTT output.
    word_timings: list[WordTiming] = Field(default_factory=list)


class Script(BaseModel):
    id: str
    document_id: str
    language: str = "en-US"
    style: Style = "casual"
    length: Length = "medium"
    turns: list[DialogueTurn]


class ScriptRequest(BaseModel):
    document_id: str
    language: str = "en-US"
    style: Style = "casual"
    length: Length = "medium"
    num_turns: int = Field(8, ge=4, le=16)
    focus: Optional[str] = Field(None, description="Optional topic focus or angle")


class ScriptPatch(BaseModel):
    turns: list[DialogueTurn]


# -----------------------------------------------------------------------------
# Render
# -----------------------------------------------------------------------------


class RoleConfig(BaseModel):
    display_name: str
    avatar: str  # 'harry', 'lisa', ...
    voice: str  # e.g. 'en-US-Ava:DragonHDLatestNeural'


class RenderRoles(BaseModel):
    interviewer: RoleConfig
    expert: RoleConfig


Layout = Literal["split_screen_with_slides", "split_screen_only"]


class RenderRequest(BaseModel):
    script_id: str
    roles: RenderRoles
    layout: Layout = "split_screen_with_slides"
    music: bool = True
    intro: bool = True
    background_image: Optional[str] = None


class JobState(str, Enum):
    queued = "queued"
    rendering = "rendering"
    composing = "composing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class JobProgress(BaseModel):
    stage: str = "queued"
    completed: int = 0
    total: int = 0
    message: str = ""


class JobOutputs(BaseModel):
    mp4_url: Optional[str] = None
    mp3_url: Optional[str] = None
    srt_url: Optional[str] = None
    duration_sec: Optional[float] = None


class PodcastJob(BaseModel):
    id: str
    script_id: str
    roles: RenderRoles
    layout: Layout
    music: bool
    intro: bool
    state: JobState = JobState.queued
    progress: JobProgress = Field(default_factory=JobProgress)
    outputs: JobOutputs = Field(default_factory=JobOutputs)
    error: Optional[str] = None
    created_at: str
    updated_at: str


# -----------------------------------------------------------------------------
# Voices / avatars catalog
# -----------------------------------------------------------------------------


class VoiceOption(BaseModel):
    id: str  # e.g. 'en-US-Ava:DragonHDLatestNeural'
    display_name: str
    language: str
    gender: Literal["male", "female", "neutral"]
    hd: bool = False
    style_list: list[str] = Field(default_factory=list)


class AvatarOption(BaseModel):
    id: str
    display_name: str
    default_style: str  # e.g. 'graceful-sitting'
    thumbnail_url: str

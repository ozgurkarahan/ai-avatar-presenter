"""UC1 Learning Paths router.

Endpoints under /api/uc1/paths:
- POST   /                       — create path
- GET    /                       — list paths
- GET    /{path_id}              — detail (hydrated with denorm deck_title, slide_count)
- PUT    /{path_id}              — update
- DELETE /{path_id}              — delete
- POST   /{path_id}/progress     — record progress (monotonic, set-union)
- GET    /{path_id}/progress     — read progress + resume pointer
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import AzureConfig, load_config
from services.storage import PresentationStore

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/uc1/paths", tags=["uc1-paths"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class PathStepIn(BaseModel):
    deck_id: str
    order: int
    required: bool = True


class PathStep(PathStepIn):
    deck_title: str = ""
    slide_count: int = 0


class PathCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    steps: list[PathStepIn]


class PathUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list[PathStepIn]] = None


class PathSummary(BaseModel):
    id: str
    title: str
    description: str = ""
    status: str = "active"
    step_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class PathDetail(PathSummary):
    steps: list[PathStep] = []


class ProgressIn(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    deck_id: str
    slide_index: int = Field(..., ge=0)
    completed: bool = False


class ProgressOut(BaseModel):
    user_id: str
    path_id: str
    last_deck_id: str = ""
    last_slide_index: int = 0
    completed_slides: dict[str, list[int]] = {}
    updated_at: str = ""
    total_slides: int = 0
    completed_count: int = 0
    percent: float = 0.0
    resume_deck_id: str = ""
    resume_slide_index: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _cfg() -> AzureConfig:
    return load_config()


def _store(cfg: AzureConfig) -> PresentationStore:
    store = PresentationStore(cfg)
    if not store.cosmos_available:
        raise HTTPException(status_code=503, detail="Cosmos DB unavailable")
    return store


def _validate_steps(steps: list[PathStepIn]) -> None:
    if not steps:
        raise HTTPException(status_code=400, detail="Path must have at least one step")
    orders = [s.order for s in steps]
    if len(set(orders)) != len(orders):
        raise HTTPException(status_code=400, detail="Duplicate step orders not allowed")
    deck_ids = [s.deck_id for s in steps]
    if len(set(deck_ids)) != len(deck_ids):
        raise HTTPException(status_code=400, detail="Duplicate deck_ids not allowed in steps")


def _hydrate_steps(store: PresentationStore, steps: list[PathStepIn]) -> list[dict]:
    """Replace deck_id with denormalized {deck_title, slide_count}. Rejects unknown decks."""
    out: list[dict] = []
    for s in sorted(steps, key=lambda x: x.order):
        deck = store.get_presentation(s.deck_id)
        if not deck or deck.get("source") != "uc1":
            raise HTTPException(status_code=400, detail=f"Unknown deck {s.deck_id}")
        title = (deck.get("filename") or s.deck_id).rsplit(".", 1)[0]
        out.append({
            "deck_id": s.deck_id,
            "order": s.order,
            "required": s.required,
            "deck_title": title,
            "slide_count": int(deck.get("slide_count") or 0),
        })
    return out


def _doc_to_summary(doc: dict) -> PathSummary:
    return PathSummary(
        id=doc["id"],
        title=doc.get("title", ""),
        description=doc.get("description", ""),
        status=doc.get("status", "active"),
        step_count=len(doc.get("steps", [])),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


def _doc_to_detail(doc: dict) -> PathDetail:
    steps = [PathStep(**s) for s in sorted(doc.get("steps", []), key=lambda x: x.get("order", 0))]
    return PathDetail(
        id=doc["id"],
        title=doc.get("title", ""),
        description=doc.get("description", ""),
        status=doc.get("status", "active"),
        step_count=len(steps),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
        steps=steps,
    )


def _total_slides(steps: list[dict]) -> int:
    return sum(int(s.get("slide_count") or 0) for s in steps)


def _build_progress_out(
    user_id: str, path_id: str, progress_doc: Optional[dict], path_doc: dict,
) -> ProgressOut:
    steps = path_doc.get("steps", [])
    total = _total_slides(steps)
    if progress_doc is None:
        first_deck = steps[0]["deck_id"] if steps else ""
        return ProgressOut(
            user_id=user_id, path_id=path_id,
            total_slides=total,
            resume_deck_id=first_deck,
        )
    completed = progress_doc.get("completed_slides", {}) or {}
    completed_count = sum(len(v) for v in completed.values())

    # Resume logic: last_deck_id + last_slide_index; clamp to valid range
    last_deck_id = progress_doc.get("last_deck_id") or (steps[0]["deck_id"] if steps else "")
    last_slide_index = int(progress_doc.get("last_slide_index") or 0)
    step = next((s for s in steps if s["deck_id"] == last_deck_id), steps[0] if steps else None)
    if step:
        slide_count = int(step.get("slide_count") or 0)
        if last_slide_index >= max(1, slide_count):
            last_slide_index = 0  # fell out of range → restart this step
    return ProgressOut(
        user_id=user_id, path_id=path_id,
        last_deck_id=progress_doc.get("last_deck_id", ""),
        last_slide_index=int(progress_doc.get("last_slide_index") or 0),
        completed_slides=completed,
        updated_at=progress_doc.get("updated_at", ""),
        total_slides=total,
        completed_count=completed_count,
        percent=round(100.0 * completed_count / total, 1) if total else 0.0,
        resume_deck_id=last_deck_id,
        resume_slide_index=last_slide_index,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.post("", response_model=PathDetail)
def create_path(body: PathCreate, cfg: AzureConfig = Depends(_cfg)) -> PathDetail:
    _validate_steps(body.steps)
    store = _store(cfg)
    hydrated = _hydrate_steps(store, body.steps)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"path_{uuid.uuid4().hex[:12]}",
        "source": "uc1-path",
        "title": body.title.strip(),
        "description": body.description.strip(),
        "status": "active",
        "steps": hydrated,
        "created_at": now,
        "updated_at": now,
    }
    if not store.save_uc1_path(doc):
        raise HTTPException(status_code=500, detail="Failed to save path")
    return _doc_to_detail(doc)


@router.get("", response_model=list[PathSummary])
def list_paths(cfg: AzureConfig = Depends(_cfg)) -> list[PathSummary]:
    store = _store(cfg)
    docs = store.list_uc1_paths()
    return [_doc_to_summary(d) for d in docs]


@router.get("/{path_id}", response_model=PathDetail)
def get_path(path_id: str, cfg: AzureConfig = Depends(_cfg)) -> PathDetail:
    store = _store(cfg)
    doc = store.get_uc1_path(path_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Path not found")
    if doc.get("status") == "broken":
        raise HTTPException(status_code=410, detail="Path is broken (referenced deck was deleted)")
    return _doc_to_detail(doc)


@router.put("/{path_id}", response_model=PathDetail)
def update_path(path_id: str, body: PathUpdate, cfg: AzureConfig = Depends(_cfg)) -> PathDetail:
    store = _store(cfg)
    doc = store.get_uc1_path(path_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Path not found")
    if body.title is not None:
        doc["title"] = body.title.strip()
    if body.description is not None:
        doc["description"] = body.description.strip()
    if body.steps is not None:
        _validate_steps(body.steps)
        doc["steps"] = _hydrate_steps(store, body.steps)
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    if not store.save_uc1_path(doc):
        raise HTTPException(status_code=500, detail="Failed to save path")
    return _doc_to_detail(doc)


@router.delete("/{path_id}")
def delete_path(path_id: str, cfg: AzureConfig = Depends(_cfg)) -> dict:
    store = _store(cfg)
    if not store.get_uc1_path(path_id):
        raise HTTPException(status_code=404, detail="Path not found")
    if not store.delete_uc1_path(path_id):
        raise HTTPException(status_code=500, detail="Failed to delete path")
    return {"path_id": path_id, "deleted": True}


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------
@router.post("/{path_id}/progress", response_model=ProgressOut)
def post_progress(path_id: str, body: ProgressIn, cfg: AzureConfig = Depends(_cfg)) -> ProgressOut:
    store = _store(cfg)
    path_doc = store.get_uc1_path(path_id)
    if not path_doc:
        raise HTTPException(status_code=404, detail="Path not found")
    if path_doc.get("status") == "broken":
        raise HTTPException(status_code=410, detail="Path is broken")

    steps = path_doc.get("steps", [])
    step = next((s for s in steps if s["deck_id"] == body.deck_id), None)
    if not step:
        raise HTTPException(status_code=400, detail="deck_id is not part of this path")

    # Read current, merge monotonically
    current = store.get_progress(body.user_id, path_id) or {}
    completed = dict(current.get("completed_slides") or {})
    current_deck_completed = set(completed.get(body.deck_id, []))
    if body.completed:
        current_deck_completed.add(int(body.slide_index))
    completed[body.deck_id] = sorted(current_deck_completed)

    # Monotonic last_slide_index per deck (but stored as one last_deck/slide for resume)
    new_last_deck = body.deck_id
    new_last_slide = int(body.slide_index)
    if current.get("last_deck_id") == body.deck_id:
        new_last_slide = max(int(current.get("last_slide_index") or 0), new_last_slide)

    doc = {
        "id": f"{body.user_id}:{path_id}",
        "user_id": body.user_id,
        "path_id": path_id,
        "last_deck_id": new_last_deck,
        "last_slide_index": new_last_slide,
        "completed_slides": completed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    saved = store.upsert_progress(doc)
    if saved is None:
        raise HTTPException(status_code=500, detail="Failed to save progress")
    return _build_progress_out(body.user_id, path_id, saved, path_doc)


@router.get("/{path_id}/progress", response_model=ProgressOut)
def get_progress(path_id: str, user_id: str, cfg: AzureConfig = Depends(_cfg)) -> ProgressOut:
    store = _store(cfg)
    path_doc = store.get_uc1_path(path_id)
    if not path_doc:
        raise HTTPException(status_code=404, detail="Path not found")
    progress = store.get_progress(user_id, path_id)
    return _build_progress_out(user_id, path_id, progress, path_doc)

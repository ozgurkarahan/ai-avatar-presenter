"""Playlists router — ordered sequences of decks with per-user progress.

Endpoints under /api/playlists:
- POST   /                           — create playlist
- GET    /                           — list playlists
- GET    /{playlist_id}              — detail (hydrated with denorm deck_title, slide_count)
- PUT    /{playlist_id}              — update
- DELETE /{playlist_id}              — delete
- POST   /{playlist_id}/progress     — record progress (monotonic, set-union)
- GET    /{playlist_id}/progress     — read progress + resume pointer
- POST   /recommend                  — AI-suggested playlist (not saved)

All routes are admin-only. Progress is keyed by the signed-in principal's
object id (``local-dev`` when AUTH_MODE=disabled) — never by request input.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import Principal, require_admin
from config import AzureConfig, load_config
from security import DAILY_QUOTA, PLAYLIST_ID_RE, UUID_RE, is_valid, require_id
from services.storage import PresentationStore, deck_title

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/playlists", tags=["playlists"], dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class PlaylistStepIn(BaseModel):
    deck_id: str = Field(..., max_length=64)
    order: int = Field(..., ge=0, le=1000)
    required: bool = True


class PlaylistStep(PlaylistStepIn):
    deck_title: str = ""
    slide_count: int = 0


class PlaylistCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    steps: list[PlaylistStepIn] = Field(..., max_length=50)


class PlaylistUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    steps: Optional[list[PlaylistStepIn]] = Field(None, max_length=50)


class PlaylistSummary(BaseModel):
    id: str
    title: str
    description: str = ""
    status: str = "active"
    step_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class PlaylistDetail(PlaylistSummary):
    steps: list[PlaylistStep] = []


class ProgressIn(BaseModel):
    # Accepted for backward compatibility but IGNORED: the user id is always
    # derived from the authenticated principal.
    user_id: Optional[str] = Field(None, max_length=64)
    deck_id: str = Field(..., max_length=64)
    slide_index: int = Field(..., ge=0, le=10000)
    completed: bool = False


class ProgressOut(BaseModel):
    user_id: str
    playlist_id: str
    last_deck_id: str = ""
    last_slide_index: int = 0
    completed_slides: dict[str, list[int]] = {}
    updated_at: str = ""
    total_slides: int = 0
    completed_count: int = 0
    percent: float = 0.0
    resume_deck_id: str = ""
    resume_slide_index: int = 0


class RecommendRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    max_steps: int = Field(4, ge=2, le=8)
    language: Optional[str] = Field(None, max_length=16)


class RecommendedStep(BaseModel):
    deck_id: str
    deck_title: str
    slide_count: int
    order: int
    rationale: str = ""


class RecommendResponse(BaseModel):
    title: str
    description: str
    steps: list[RecommendedStep]
    explanation: str = ""


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


def _validate_steps(steps: list[PlaylistStepIn]) -> None:
    if not steps:
        raise HTTPException(status_code=400, detail="Playlist must have at least one step")
    orders = [s.order for s in steps]
    if len(set(orders)) != len(orders):
        raise HTTPException(status_code=400, detail="Duplicate step orders not allowed")
    deck_ids = [s.deck_id for s in steps]
    if len(set(deck_ids)) != len(deck_ids):
        raise HTTPException(status_code=400, detail="Duplicate deck_ids not allowed in steps")


def _hydrate_steps(store: PresentationStore, steps: list[PlaylistStepIn]) -> list[dict]:
    """Replace deck_id with denormalized {deck_title, slide_count}. Rejects unknown decks."""
    out: list[dict] = []
    for s in sorted(steps, key=lambda x: x.order):
        if not is_valid(s.deck_id, UUID_RE):
            raise HTTPException(status_code=400, detail="Unknown deck")
        deck = store.get_presentation(s.deck_id)
        if not deck or deck.get("source") != "deck":
            raise HTTPException(status_code=400, detail="Unknown deck")
        title = deck_title({"id": s.deck_id, **deck})
        out.append({
            "deck_id": s.deck_id,
            "order": s.order,
            "required": s.required,
            "deck_title": title,
            "slide_count": int(deck.get("slide_count") or 0),
        })
    return out


def _doc_to_summary(doc: dict) -> PlaylistSummary:
    return PlaylistSummary(
        id=doc["id"],
        title=doc.get("title", ""),
        description=doc.get("description", ""),
        status=doc.get("status", "active"),
        step_count=len(doc.get("steps", [])),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


def _doc_to_detail(doc: dict) -> PlaylistDetail:
    steps = [PlaylistStep(**s) for s in sorted(doc.get("steps", []), key=lambda x: x.get("order", 0))]
    return PlaylistDetail(
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
    user_id: str, playlist_id: str, progress_doc: Optional[dict], playlist_doc: dict,
) -> ProgressOut:
    steps = playlist_doc.get("steps", [])
    total = _total_slides(steps)
    if progress_doc is None:
        first_deck = steps[0]["deck_id"] if steps else ""
        return ProgressOut(
            user_id=user_id, playlist_id=playlist_id,
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
        user_id=user_id, playlist_id=playlist_id,
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
@router.post("", response_model=PlaylistDetail)
def create_playlist(body: PlaylistCreate, cfg: AzureConfig = Depends(_cfg)) -> PlaylistDetail:
    _validate_steps(body.steps)
    store = _store(cfg)
    hydrated = _hydrate_steps(store, body.steps)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"pl_{uuid.uuid4().hex[:12]}",
        "source": "playlist",
        "title": body.title.strip(),
        "description": body.description.strip(),
        "status": "active",
        "steps": hydrated,
        "created_at": now,
        "updated_at": now,
    }
    if not store.save_playlist(doc):
        raise HTTPException(status_code=500, detail="Failed to save playlist")
    return _doc_to_detail(doc)


@router.get("", response_model=list[PlaylistSummary])
def list_playlists(cfg: AzureConfig = Depends(_cfg)) -> list[PlaylistSummary]:
    store = _store(cfg)
    docs = store.list_playlists()
    return [_doc_to_summary(d) for d in docs]


@router.get("/{playlist_id}", response_model=PlaylistDetail)
def get_playlist(playlist_id: str, cfg: AzureConfig = Depends(_cfg)) -> PlaylistDetail:
    require_id(playlist_id, PLAYLIST_ID_RE, "Playlist")
    store = _store(cfg)
    doc = store.get_playlist(playlist_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if doc.get("status") == "broken":
        raise HTTPException(status_code=410, detail="Playlist is broken (referenced deck was deleted)")
    return _doc_to_detail(doc)


@router.put("/{playlist_id}", response_model=PlaylistDetail)
def update_playlist(playlist_id: str, body: PlaylistUpdate, cfg: AzureConfig = Depends(_cfg)) -> PlaylistDetail:
    require_id(playlist_id, PLAYLIST_ID_RE, "Playlist")
    store = _store(cfg)
    doc = store.get_playlist(playlist_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if body.title is not None:
        doc["title"] = body.title.strip()
    if body.description is not None:
        doc["description"] = body.description.strip()
    if body.steps is not None:
        _validate_steps(body.steps)
        doc["steps"] = _hydrate_steps(store, body.steps)
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    if not store.save_playlist(doc):
        raise HTTPException(status_code=500, detail="Failed to save playlist")
    return _doc_to_detail(doc)


@router.delete("/{playlist_id}")
def delete_playlist(playlist_id: str, cfg: AzureConfig = Depends(_cfg)) -> dict:
    require_id(playlist_id, PLAYLIST_ID_RE, "Playlist")
    store = _store(cfg)
    if not store.get_playlist(playlist_id):
        raise HTTPException(status_code=404, detail="Playlist not found")
    if not store.delete_playlist(playlist_id):
        raise HTTPException(status_code=500, detail="Failed to delete playlist")
    return {"playlist_id": playlist_id, "deleted": True}


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------
@router.post("/{playlist_id}/progress", response_model=ProgressOut)
def post_progress(
    playlist_id: str,
    body: ProgressIn,
    cfg: AzureConfig = Depends(_cfg),
    principal: Principal = Depends(require_admin),
) -> ProgressOut:
    require_id(playlist_id, PLAYLIST_ID_RE, "Playlist")
    user_id = principal.user_id
    store = _store(cfg)
    playlist_doc = store.get_playlist(playlist_id)
    if not playlist_doc:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if playlist_doc.get("status") == "broken":
        raise HTTPException(status_code=410, detail="Playlist is broken")

    steps = playlist_doc.get("steps", [])
    step = next((s for s in steps if s["deck_id"] == body.deck_id), None)
    if not step:
        raise HTTPException(status_code=400, detail="deck_id is not part of this playlist")

    # Read current, merge monotonically
    current = store.get_progress(user_id, playlist_id) or {}
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
        "id": f"{user_id}:{playlist_id}",
        "user_id": user_id,
        "playlist_id": playlist_id,
        "last_deck_id": new_last_deck,
        "last_slide_index": new_last_slide,
        "completed_slides": completed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    saved = store.upsert_progress(doc)
    if saved is None:
        raise HTTPException(status_code=500, detail="Failed to save progress")
    return _build_progress_out(user_id, playlist_id, saved, playlist_doc)


@router.get("/{playlist_id}/progress", response_model=ProgressOut)
def get_progress(
    playlist_id: str,
    user_id: Optional[str] = None,  # ignored; kept for backward compatibility
    cfg: AzureConfig = Depends(_cfg),
    principal: Principal = Depends(require_admin),
) -> ProgressOut:
    require_id(playlist_id, PLAYLIST_ID_RE, "Playlist")
    user_id = principal.user_id
    store = _store(cfg)
    playlist_doc = store.get_playlist(playlist_id)
    if not playlist_doc:
        raise HTTPException(status_code=404, detail="Playlist not found")
    progress = store.get_progress(user_id, playlist_id)
    return _build_progress_out(user_id, playlist_id, progress, playlist_doc)


# ---------------------------------------------------------------------------
# AI recommendation
# ---------------------------------------------------------------------------
import json as _json
from services.translation import get_openai_client as _get_openai_client

_RECOMMEND_SYSTEM_PROMPT = """You are an instructional designer. Given a catalog of training decks and a learner's topic of interest, propose an ORDERED playlist of 2-N decks that forms a coherent progression from introduction to advanced.

Rules:
- Use ONLY deck_ids from the catalog provided. Never invent a deck_id.
- Order matters: earlier steps should provide foundations for later ones.
- If fewer than 2 decks in the catalog are relevant to the topic, return an empty steps array.
- Keep rationales short (≤ 120 chars each).
- The playlist title must be concise (≤ 60 chars) and specific to the topic.

Return STRICT JSON with this exact schema (no markdown, no prose):
{
  "title": "...",
  "description": "...",
  "explanation": "1-2 sentences on why this ordering",
  "steps": [
    {"deck_id": "<from catalog>", "rationale": "..."}
  ]
}"""


@router.post("/recommend", response_model=RecommendResponse)
def recommend_playlist(
    req: RecommendRequest,
    cfg: AzureConfig = Depends(_cfg),
    principal: Principal = Depends(require_admin),
) -> RecommendResponse:
    """Ask the LLM to propose an ordered playlist for the given topic.
    Does NOT save — caller reviews and POSTs to / to create."""
    store = _store(cfg)
    decks = store.list_decks()
    if req.language:
        decks = [d for d in decks if d.get("language") == req.language]
    if not decks:
        raise HTTPException(status_code=400, detail="No decks in catalog to recommend from")
    DAILY_QUOTA.consume(principal.user_id)

    def _title(d: dict) -> str:
        return deck_title({"id": "deck", **d})

    catalog_lines = [
        f'- deck_id="{d["id"]}" title="{_title(d)}" language={d.get("language", "?")} slides={d.get("slide_count", 0)}'
        for d in decks
    ]
    user_prompt = (
        f"Learner topic: {req.topic}\n"
        f"Max steps: {req.max_steps}\n"
        f"Language filter: {req.language or 'any'}\n\n"
        f"Available decks:\n" + "\n".join(catalog_lines)
    )

    client = _get_openai_client(cfg)
    if client is None:
        raise HTTPException(status_code=503, detail="OpenAI client not configured")

    try:
        resp = client.chat.completions.create(
            model=cfg.openai_chat_deployment,
            messages=[
                {"role": "system", "content": _RECOMMEND_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        data = _json.loads(raw)
    except _json.JSONDecodeError as e:
        log.error("LLM returned non-JSON: %s", e)
        raise HTTPException(status_code=502, detail="LLM returned invalid JSON")
    except Exception:
        log.exception("LLM recommendation failed")
        raise HTTPException(status_code=502, detail="LLM request failed")

    # Validate + hydrate
    deck_map = {d["id"]: d for d in decks}
    steps_raw = data.get("steps") or []
    out_steps: list[RecommendedStep] = []
    used: set[str] = set()
    for i, s in enumerate(steps_raw[: req.max_steps]):
        did = s.get("deck_id")
        if not did or did not in deck_map or did in used:
            continue
        used.add(did)
        deck = deck_map[did]
        out_steps.append(RecommendedStep(
            deck_id=did,
            deck_title=_title(deck),
            slide_count=int(deck.get("slide_count") or 0),
            order=len(out_steps),
            rationale=str(s.get("rationale", ""))[:200],
        ))

    if len(out_steps) < 2:
        raise HTTPException(
            status_code=404,
            detail=f"Not enough relevant decks found for topic '{req.topic}'. Try a broader topic or upload more decks.",
        )

    return RecommendResponse(
        title=str(data.get("title") or f"Playlist: {req.topic}")[:100],
        description=str(data.get("description") or "")[:500],
        steps=out_steps,
        explanation=str(data.get("explanation") or "")[:500],
    )

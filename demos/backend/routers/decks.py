"""Decks catalog — FastAPI router.

Endpoints:
- POST   /api/decks/upload                — upload a .pptx, parse, render, index in AI Search
- GET    /api/decks                       — list all decks
- GET    /api/decks/{deck_id}             — full deck with slides (for the Present page)
- DELETE /api/decks/{deck_id}             — delete from cosmos + blob + AI Search
- POST   /api/decks/{deck_id}/publish     — show/hide a deck to anonymous viewers
- POST   /api/decks/{deck_id}/live-demo   — allow/deny the anonymous live avatar demo
- POST   /api/search                      — cross-deck hybrid semantic search

Anonymous callers may only list/view *published* decks (titles + slide
images); everything else is admin-only.
"""
from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth import Principal, get_principal, require_admin
from config import AzureConfig, load_config
from security import DAILY_QUOTA, UUID_RE, read_upload_limited, require_id, safe_filename
from services.pptx_parser import parse_pptx
from services.storage import PUBLIC_SAS_MINUTES, PresentationStore
from services.translation import get_openai_client
from services.deck_search import DeckSlide, get_deck_search

log = logging.getLogger(__name__)
# Admin-only (default deny); anonymous published-deck reads are on public_router.
router = APIRouter(prefix="/api", tags=["decks"], dependencies=[Depends(require_admin)])
public_router = APIRouter(prefix="/api", tags=["decks-public"])

# Where slide PNGs are served from (mirrors the layout used by the legacy /api/upload).
SLIDES_DIR = Path(__file__).resolve().parent.parent / "slides_cache"
SLIDES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class DeckSummary(BaseModel):
    deck_id: str
    title: str
    slide_count: int
    language: str = "en-US"
    uploaded_at: str = ""
    tags: list[str] = []
    published: bool = False
    # Anonymous visitors may run the narration-only live avatar demo on it.
    live_demo: bool = False


class SlidePayload(BaseModel):
    index: int
    title: str
    body: str = ""
    notes: str = ""
    image_url: str = ""


class DeckDetail(DeckSummary):
    # Aliases for frontend compatibility with existing `Presentation` shape.
    id: str = ""
    filename: str = ""
    slides: list[SlidePayload]


class UploadResponse(BaseModel):
    deck_id: str
    title: str
    slide_count: int
    indexed_slides: int


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=500)
    top_k: int = 5
    language: Optional[str] = Field(None, max_length=16)


class PublishRequest(BaseModel):
    published: bool


class LiveDemoRequest(BaseModel):
    enabled: bool


class SearchResultItem(BaseModel):
    deck_id: str
    deck_title: str
    slide_index: int
    slide_title: str
    snippet: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResultItem]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_cfg() -> AzureConfig:
    return load_config()


def _store(cfg: AzureConfig) -> Optional[PresentationStore]:
    try:
        s = PresentationStore(cfg)
        return s
    except Exception:
        log.exception("Could not initialise PresentationStore for decks")
        return None


def _deck_title_from_filename(filename: str) -> str:
    return filename.rsplit(".", 1)[0] if filename else "Untitled"


def _doc_to_summary(doc: dict) -> DeckSummary:
    return DeckSummary(
        deck_id=doc["id"],
        title=_deck_title_from_filename(doc.get("filename") or doc["id"]),
        slide_count=int(doc.get("slide_count") or 0),
        language=doc.get("language") or "en-US",
        uploaded_at=doc.get("uploaded_at") or "",
        tags=doc.get("tags") or [],
        published=doc.get("published") is True,
        live_demo=doc.get("published") is True and doc.get("live_demo") is True,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/decks/upload", response_model=UploadResponse)
async def upload_deck(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None, max_length=16),
    cfg: AzureConfig = Depends(get_cfg),
    principal: Principal = Depends(require_admin),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only .pptx files are supported")

    content = await read_upload_limited(file)
    if not content or content[:4] != b"PK\x03\x04":
        raise HTTPException(status_code=400, detail="Not a valid .pptx file")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            if "[Content_Types].xml" not in zf.namelist():
                raise HTTPException(status_code=400, detail="Invalid .pptx archive")
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Corrupted .pptx file")
    DAILY_QUOTA.consume(principal.user_id)

    # Parse + render slides
    try:
        presentation = parse_pptx(content, safe_filename(file.filename, "deck.pptx"), cfg.libreoffice_path or "soffice")
    except Exception:
        log.exception("PPTX parse failed")
        raise HTTPException(status_code=400, detail="Failed to parse .pptx")

    store = _store(cfg)

    # Save rendered PNGs locally + to blob, set image_url on each slide
    if presentation.slide_images:
        out_dir = SLIDES_DIR / presentation.id
        out_dir.mkdir(parents=True, exist_ok=True)
        for idx, png in presentation.slide_images:
            (out_dir / f"{idx}.png").write_bytes(png)
            if store and store.available:
                try:
                    store.upload_slide_image(presentation.id, idx, png)
                except Exception:
                    log.warning("Blob upload failed for slide %d", idx)
        for slide in presentation.slides:
            blob_url = None
            if store and store.available:
                try:
                    blob_url = store.get_slide_image_url(presentation.id, slide.index)
                except Exception:
                    blob_url = None
            slide.image_url = blob_url or f"/api/slides/{presentation.id}/{slide.index}.png"
        presentation.slide_images = []

    # Persist metadata in Cosmos under source='deck'
    lang = (language or "").strip() or "en-US"
    tags: list[str] = []
    uploaded_at = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": presentation.id,
        "source": "deck",
        "filename": presentation.filename,
        "slide_count": presentation.slide_count,
        "language": lang,
        "uploaded_at": uploaded_at,
        "tags": tags,
        "published": False,
        "live_demo": False,
        "slides": [
            {
                "index": s.index,
                "title": s.title,
                "body": s.body,
                "notes": s.notes,
                "image_url": s.image_url,
                "video_url": s.video_url,
            }
            for s in presentation.slides
        ],
    }
    if store and store.cosmos_available:
        try:
            store.save_presentation(doc)
        except Exception:
            log.exception("Could not save deck %s to Cosmos", presentation.id)

    # Index in AI Search (hybrid semantic + keyword)
    indexed = 0
    try:
        openai_client = get_openai_client(cfg)
        search = get_deck_search(cfg, openai_client)
        if search:
            deck_title = _deck_title_from_filename(presentation.filename)
            slides_for_index = [
                DeckSlide(
                    deck_id=presentation.id,
                    deck_title=deck_title,
                    slide_index=s.index,
                    slide_title=s.title or f"Slide {s.index + 1}",
                    body=s.body or "",
                    notes=s.notes or "",
                    language=lang,
                )
                for s in presentation.slides
            ]
            indexed = search.index_deck(slides_for_index)
            log.info("Decks: indexed %d slides for deck %s", indexed, presentation.id)
        else:
            log.warning("AI Search not configured — deck %s not searchable", presentation.id)
    except Exception:
        log.exception("AI Search indexing failed for deck %s", presentation.id)

    return UploadResponse(
        deck_id=presentation.id,
        title=_deck_title_from_filename(presentation.filename),
        slide_count=presentation.slide_count,
        indexed_slides=indexed,
    )


@public_router.get("/decks", response_model=list[DeckSummary])
def list_decks(
    cfg: AzureConfig = Depends(get_cfg),
    principal: Principal = Depends(get_principal),
) -> list[DeckSummary]:
    """Admins see every deck; anonymous callers only published ones."""
    store = _store(cfg)
    if not store or not store.cosmos_available:
        return []
    try:
        docs = store.list_decks()
    except Exception:
        log.exception("list_decks failed")
        return []
    out: list[DeckSummary] = []
    for d in docs:
        if not isinstance(d, dict) or not d.get("id"):
            continue
        if not principal.is_admin and d.get("published") is not True:
            continue
        out.append(_doc_to_summary(d))
    return out


@public_router.get("/decks/{deck_id}", response_model=DeckDetail)
def get_deck(
    deck_id: str,
    cfg: AzureConfig = Depends(get_cfg),
    principal: Principal = Depends(get_principal),
) -> DeckDetail:
    """Full deck for admins; titles + slide images only for anonymous callers."""
    require_id(deck_id, UUID_RE, "Deck")
    store = _store(cfg)
    if not store or not store.cosmos_available:
        raise HTTPException(status_code=503, detail="Storage unavailable")
    doc = store.get_presentation(deck_id)
    if not doc or doc.get("source") != "deck":
        raise HTTPException(status_code=404, detail="Deck not found")
    public = not principal.is_admin
    if public and doc.get("published") is not True:
        raise HTTPException(status_code=404, detail="Deck not found")

    blob_ok = bool(store.available)

    def _image_url(s: dict, i: int) -> str:
        idx = int(s.get("index", i))
        if blob_ok:
            minutes = PUBLIC_SAS_MINUTES if public else 24 * 60
            try:
                url = store.get_slide_image_url(deck_id, idx, expiry_minutes=minutes)
            except Exception:
                url = None
            if url:
                return url
        if public:
            return f"/api/slides/{deck_id}/{idx}.png"
        return s.get("image_url") or f"/api/slides/{deck_id}/{idx}.png"

    slides = [
        SlidePayload(
            index=int(s.get("index", i)),
            title=s.get("title") or f"Slide {i + 1}",
            body="" if public else (s.get("body") or ""),
            notes="" if public else (s.get("notes") or ""),
            image_url=_image_url(s, i),
        )
        for i, s in enumerate(doc.get("slides") or [])
        if isinstance(s, dict)
    ]
    summary = _doc_to_summary(doc)
    return DeckDetail(
        **summary.model_dump(),
        id=deck_id,
        filename=doc.get("filename") or deck_id,
        slides=slides,
    )


@router.post("/decks/{deck_id}/publish", response_model=DeckSummary)
def publish_deck(deck_id: str, body: PublishRequest, cfg: AzureConfig = Depends(get_cfg)) -> DeckSummary:
    """Admin: show/hide a deck to anonymous viewers."""
    require_id(deck_id, UUID_RE, "Deck")
    store = _store(cfg)
    if not store or not store.cosmos_available:
        raise HTTPException(status_code=503, detail="Storage unavailable")
    doc = store.set_deck_published(deck_id, body.published)
    if not doc:
        raise HTTPException(status_code=404, detail="Deck not found")
    return _doc_to_summary(doc)


@router.post("/decks/{deck_id}/live-demo", response_model=DeckSummary)
def set_live_demo(deck_id: str, body: LiveDemoRequest, cfg: AzureConfig = Depends(get_cfg)) -> DeckSummary:
    """Admin: allow (or stop) anonymous visitors running the live avatar demo
    on this deck. Only published decks can be live demos."""
    require_id(deck_id, UUID_RE, "Deck")
    store = _store(cfg)
    if not store or not store.cosmos_available:
        raise HTTPException(status_code=503, detail="Storage unavailable")
    current = store.get_presentation(deck_id)
    if not current or current.get("source") != "deck":
        raise HTTPException(status_code=404, detail="Deck not found")
    if body.enabled and current.get("published") is not True:
        raise HTTPException(status_code=409, detail="Publish the deck before enabling the live demo")
    try:
        doc = store.set_deck_live_demo(deck_id, body.enabled)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not doc:
        raise HTTPException(status_code=404, detail="Deck not found")
    return _doc_to_summary(doc)


@router.delete("/decks/{deck_id}")
def delete_deck(deck_id: str, force: bool = False, cfg: AzureConfig = Depends(get_cfg)) -> dict:
    require_id(deck_id, UUID_RE, "Deck")
    store = _store(cfg)
    broken_playlists: list[str] = []
    if store and store.cosmos_available:
        refs = store.playlists_referencing_deck(deck_id)
        if refs and not force:
            titles = ", ".join(p.get("title", p.get("id", "")) for p in refs)
            raise HTTPException(
                status_code=409,
                detail=f"Deck is referenced by {len(refs)} playlist(s): {titles}. Use ?force=true to delete and break those playlists.",
            )
        # force=true → mark each referencing playlist as broken
        for p in refs:
            p["status"] = "broken"
            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            try:
                store.save_playlist(p)
                broken_playlists.append(p["id"])
            except Exception:
                log.exception("Failed to mark playlist %s broken", p.get("id"))

    if store:
        try:
            store.delete_presentation(deck_id)
        except Exception:
            log.exception("Cosmos delete failed for %s", deck_id)
        try:
            store.delete_slide_images(deck_id)
        except Exception:
            log.exception("Blob delete failed for %s", deck_id)

    removed = 0
    try:
        openai_client = get_openai_client(cfg)
        search = get_deck_search(cfg, openai_client)
        if search:
            removed = search.delete_deck(deck_id)
    except Exception:
        log.exception("Search delete failed for %s", deck_id)

    return {"deck_id": deck_id, "removed_chunks": removed, "broken_playlists": broken_playlists}


@router.post("/search", response_model=SearchResponse)
def search_decks(
    req: SearchRequest,
    cfg: AzureConfig = Depends(get_cfg),
    principal: Principal = Depends(require_admin),
) -> SearchResponse:
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Empty query")
    DAILY_QUOTA.consume(principal.user_id)
    openai_client = get_openai_client(cfg)
    search = get_deck_search(cfg, openai_client)
    if not search:
        raise HTTPException(status_code=503, detail="Search not configured")
    top_k = max(1, min(20, req.top_k))
    try:
        hits = search.search(req.query, top_k=top_k, language=req.language)
    except Exception:
        log.exception("Deck search failed")
        raise HTTPException(status_code=500, detail="Search failed")
    return SearchResponse(
        results=[
            SearchResultItem(
                deck_id=h.deck_id,
                deck_title=h.deck_title,
                slide_index=h.slide_index,
                slide_title=h.slide_title,
                snippet=h.snippet,
                score=h.score,
            )
            for h in hits
        ]
    )

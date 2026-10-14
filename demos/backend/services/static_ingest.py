"""UC2 ingest — PPTX / PDF / single image → normalized slide list.

Non-visual inputs (DOCX/TXT/URL) are explicitly out of scope for UC2.
"""
from __future__ import annotations

import io
import logging
import shutil
import uuid
from pathlib import Path

from services.static_models import SlideRef, StaticDocument

log = logging.getLogger(__name__)


def ingest(path: str | Path, original_name: str | None = None) -> StaticDocument:
    p = Path(path)
    ext = p.suffix.lower()
    title = Path(original_name or p.name).stem

    if ext == ".pptx":
        return _ingest_pptx(p, title)
    if ext == ".pdf":
        return _ingest_pdf(p, title)
    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return _ingest_image(p, title)
    raise ValueError(f"Unsupported file type for UC2: {ext}. Allowed: .pptx, .pdf, .png, .jpg, .jpeg")


# ---------------------------------------------------------------------------
# PPTX
# ---------------------------------------------------------------------------

def _ingest_pptx(p: Path, title: str) -> StaticDocument:
    from services.pptx_parser import parse_pptx

    data = parse_pptx(p.read_bytes(), p.name)

    img_dir = p.parent / f"{p.stem}_slides_{data.id[:8]}"
    img_dir.mkdir(parents=True, exist_ok=True)
    image_paths: dict[int, Path] = {}
    for idx, png in data.slide_images:
        out = img_dir / f"slide_{idx:03d}.png"
        out.write_bytes(png)
        image_paths[idx] = out

    slides: list[SlideRef] = []
    for sl in data.slides:
        image_ref = str(image_paths.get(sl.index, ""))
        preview_parts = [part for part in (sl.title, sl.body, sl.notes) if part]
        preview_text = "\n".join(preview_parts).strip()[:600]
        slides.append(SlideRef(
            index=sl.index,
            image_ref=image_ref,
            title=sl.title or f"Slide {sl.index + 1}",
            preview_text=preview_text,
        ))

    return StaticDocument(
        doc_id=data.id,
        title=title,
        source_kind="pptx",
        slides=slides,
    )


# ---------------------------------------------------------------------------
# PDF — one slide per page
# ---------------------------------------------------------------------------

def _ingest_pdf(p: Path, title: str) -> StaticDocument:
    from pypdf import PdfReader

    doc_id = str(uuid.uuid4())
    img_dir = p.parent / f"{p.stem}_pdf_{doc_id[:8]}"
    img_dir.mkdir(parents=True, exist_ok=True)

    # Render pages to PNG using pdf2image / poppler.
    page_images: list[Path] = []
    try:
        from pdf2image import convert_from_path
        from services.pptx_parser import _find_poppler  # reuse poppler discovery
        kwargs = {"dpi": 150, "fmt": "png"}
        poppler = _find_poppler()
        if poppler:
            kwargs["poppler_path"] = poppler
        images = convert_from_path(str(p), **kwargs)
        for i, img in enumerate(images):
            out = img_dir / f"slide_{i:03d}.png"
            img.save(out, format="PNG")
            page_images.append(out)
    except Exception as exc:  # noqa: BLE001
        log.warning("pdf2image failed, falling back to text-only slides: %s", exc)

    # Text per page for preview.
    reader = PdfReader(str(p))
    slides: list[SlideRef] = []
    for i, page in enumerate(reader.pages):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:  # noqa: BLE001
            text = ""
        # Use first non-empty line as title.
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "") or f"Page {i + 1}"
        img_ref = str(page_images[i]) if i < len(page_images) else ""
        slides.append(SlideRef(
            index=i,
            image_ref=img_ref,
            title=first_line[:120],
            preview_text=text[:600],
        ))

    if not slides:
        raise ValueError("PDF contained no extractable pages")

    return StaticDocument(
        doc_id=doc_id,
        title=title,
        source_kind="pdf",
        slides=slides,
    )


# ---------------------------------------------------------------------------
# Single image — one slide
# ---------------------------------------------------------------------------

def _ingest_image(p: Path, title: str) -> StaticDocument:
    doc_id = str(uuid.uuid4())
    img_dir = p.parent / f"{p.stem}_img_{doc_id[:8]}"
    img_dir.mkdir(parents=True, exist_ok=True)
    dest = img_dir / f"slide_000{p.suffix.lower()}"
    shutil.copyfile(p, dest)
    slide = SlideRef(index=0, image_ref=str(dest), title=title, preview_text="")
    return StaticDocument(
        doc_id=doc_id,
        title=title,
        source_kind="image",
        slides=[slide],
    )

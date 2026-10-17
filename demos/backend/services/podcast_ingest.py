"""Multi-format document ingestion for podcast generation.

Normalizes PPTX / PDF / DOCX / TXT / MD / URL inputs into a `Document`
that downstream services (script generation, composition) consume.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

from services.podcast_models import Document, Section

log = logging.getLogger(__name__)


class _SectionDeleted:
    pass


# Document/Section are imported from podcast_models.


# ---------------------------------------------------------------------------
# Format-specific ingesters
# ---------------------------------------------------------------------------

def ingest_pptx(path: str | Path, libreoffice_path: str | None = None) -> Document:
    """Parse a PPTX, render slide images, return a Document.

    ``libreoffice_path`` is forwarded to :func:`pptx_parser.parse_pptx` so the
    podcast renders slides with the same LibreOffice binary as the Decks
    upload path (rendering parity).
    """
    from services.pptx_parser import parse_pptx

    p = Path(path)
    data = parse_pptx(p.read_bytes(), p.name, libreoffice_path or "soffice")

    sections: list[Section] = []
    slide_titles: list[str] = []
    slide_notes: list[str] = []
    for sl in data.slides:
        heading = sl.title or f"Slide {sl.index + 1}"
        body = "\n".join(part for part in (sl.body, sl.notes) if part)
        sections.append(Section(heading=heading, text=body))
        slide_titles.append(sl.title or "")
        slide_notes.append(sl.notes or "")

    # Persist rendered PNGs alongside the source so compose can reference them.
    # The list stays index-aligned with the slides (turn.slide_idx indexes it);
    # a slide the renderer skipped becomes "" and compose uses its fallback.
    img_dir = p.parent / f"{p.stem}_slides_{data.id[:8]}"
    img_dir.mkdir(parents=True, exist_ok=True)
    by_idx: dict[int, str] = {}
    for idx, png in data.slide_images:
        out = img_dir / f"slide_{idx:03d}.png"
        out.write_bytes(png)
        by_idx[idx] = str(out)
    count = max([len(data.slides)] + [i + 1 for i in by_idx])
    slide_images = [by_idx.get(i, "") for i in range(count)] if by_idx else []
    missing = [i + 1 for i in range(count) if i not in by_idx]
    if missing:
        log.warning(
            "pptx %s: no rendered image for slide(s) %s — podcast will use a fallback slide",
            p.name, missing,
        )

    return Document(
        id=data.id,
        title=p.stem,
        sections=sections,
        slide_images=slide_images,
        slide_titles=slide_titles,
        slide_notes=slide_notes,
        source_kind="pptx",
    )


def ingest_pdf(path: str | Path) -> Document:
    """One section per PDF page."""
    from pypdf import PdfReader

    p = Path(path)
    reader = PdfReader(str(p))
    sections: list[Section] = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            log.warning("pdf page %d extract failed: %s", i, exc)
            text = ""
        sections.append(Section(heading=f"Page {i + 1}", text=text.strip()))

    title = (reader.metadata.title if reader.metadata and reader.metadata.title else p.stem) or p.stem
    return Document(id=str(uuid.uuid4()), title=str(title), sections=sections, source_kind="pdf")


def ingest_docx(path: str | Path) -> Document:
    """Treat each Heading paragraph as a section boundary."""
    from docx import Document as DocxDocument

    p = Path(path)
    doc = DocxDocument(str(p))

    sections: list[Section] = []
    current = Section(heading=p.stem, text="")
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        style = (para.style.name if para.style else "") or ""
        if style.lower().startswith("heading"):
            if current.text or current.heading != p.stem:
                sections.append(current)
            current = Section(heading=text, text="")
        else:
            current.text = f"{current.text}\n{text}".strip() if current.text else text
    if current.text or not sections:
        sections.append(current)

    return Document(id=str(uuid.uuid4()), title=p.stem, sections=sections, source_kind="docx")


def ingest_text(path: str | Path) -> Document:
    """Plain text or markdown — split on top-level markdown headings if present."""
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    kind = "md" if p.suffix.lower() in {".md", ".markdown"} else "txt"

    sections: list[Section] = []
    if kind == "md" and re.search(r"^#{1,6}\s", raw, flags=re.MULTILINE):
        chunks = re.split(r"(?m)^(?=#{1,6}\s)", raw)
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            lines = chunk.splitlines()
            heading = lines[0].lstrip("# ").strip()
            body = "\n".join(lines[1:]).strip()
            sections.append(Section(heading=heading, text=body))
    else:
        sections.append(Section(heading=p.stem, text=raw.strip()))

    return Document(id=str(uuid.uuid4()), title=p.stem, sections=sections, source_kind=kind)


def ingest_url(url: str) -> Document:
    """Fetch a URL (SSRF-validated, see services.url_safety) and extract the main body.

    Callers must check :func:`services.url_safety.url_ingest_enabled` first.
    """
    from html import unescape

    from services.url_safety import fetch_url

    final_url, html = fetch_url(url)

    from readability import Document as ReadabilityDocument

    rd = ReadabilityDocument(html)
    title = rd.short_title() or urlparse(final_url).netloc
    summary_html = rd.summary(html_partial=True)
    text = re.sub(r"<[^>]+>", " ", summary_html)
    text = unescape(re.sub(r"\s+", " ", text)).strip()

    return Document(
        id=str(uuid.uuid4()),
        title=title,
        sections=[Section(heading=title, text=text)],
        source_kind="url",
    )


# ---------------------------------------------------------------------------
# Dispatcher (uploaded files only — never arbitrary local paths or URLs)
# ---------------------------------------------------------------------------

ALLOWED_FILE_SUFFIXES = {".pptx", ".pdf", ".docx", ".txt", ".md", ".markdown"}


def ingest_file(path: str | Path, libreoffice_path: str | None = None) -> Document:
    """Ingest a server-side uploaded file, picking the ingester by extension.

    Only the allowlisted extensions are accepted; there is no URL or
    content-sniffing fallback. ``libreoffice_path`` is only used for PPTX.
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".pptx":
        return ingest_pptx(p, libreoffice_path=libreoffice_path)
    if ext == ".pdf":
        return ingest_pdf(p)
    if ext == ".docx":
        return ingest_docx(p)
    if ext in {".md", ".markdown", ".txt"}:
        return ingest_text(p)
    raise ValueError(f"Unsupported file type: {ext or '(none)'}")

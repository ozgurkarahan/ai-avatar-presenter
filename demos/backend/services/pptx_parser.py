"""Parse PPTX files: extract text, notes, and render slides to PNG via LibreOffice."""

from __future__ import annotations

import io
import logging
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pptx import Presentation

log = logging.getLogger(__name__)


@dataclass
class SlideData:
    index: int
    title: str
    body: str
    notes: str
    image_url: Optional[str] = None


@dataclass
class PresentationData:
    id: str
    filename: str
    slide_count: int
    slides: list[SlideData] = field(default_factory=list)
    slide_images: list[tuple[int, bytes]] = field(default_factory=list)


def parse_pptx(file_bytes: bytes, filename: str, libreoffice_path: str = "soffice") -> PresentationData:
    """Parse a .pptx file, extract slide text/notes, and render slide images."""
    prs = Presentation(io.BytesIO(file_bytes))
    slides: list[SlideData] = []

    for i, slide in enumerate(prs.slides):
        title = _extract_title(slide)
        body = _extract_body(slide)
        notes = _extract_notes(slide)
        slides.append(SlideData(index=i, title=title, body=body, notes=notes))

    slide_images = _render_slides(file_bytes, len(slides), libreoffice_path)

    presentation_id = str(uuid.uuid4())
    return PresentationData(
        id=presentation_id,
        filename=filename,
        slide_count=len(slides),
        slides=slides,
        slide_images=slide_images,
    )


def _render_slides(file_bytes: bytes, slide_count: int, libreoffice_path: str) -> list[tuple[int, bytes]]:
    """Render slides to PNG via LibreOffice headless + pdf2image (same as reference)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pptx_path = tmpdir_path / "presentation.pptx"
        pptx_path.write_bytes(file_bytes)

        try:
            result = subprocess.run(
                [
                    libreoffice_path, "--headless", "--convert-to", "pdf",
                    "--outdir", str(tmpdir_path), str(pptx_path),
                ],
                capture_output=True,
                timeout=120,
                encoding="utf-8",
                errors="replace",
            )
            log.info("LibreOffice exit code: %d", result.returncode)

            pdf_files = list(tmpdir_path.glob("*.pdf"))
            if pdf_files:
                from pdf2image import convert_from_path
                poppler_path = _find_poppler()
                kwargs = {"dpi": 150, "fmt": "png"}
                if poppler_path:
                    kwargs["poppler_path"] = poppler_path
                images = convert_from_path(str(pdf_files[0]), **kwargs)
                slide_images = []
                for i, img in enumerate(images):
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    slide_images.append((i, buf.getvalue()))
                return slide_images
        except Exception as e:
            log.warning("LibreOffice rendering failed: %s", e)

        # Fallback: placeholder images
        return _fallback_placeholders(slide_count)


def _find_poppler() -> str | None:
    """Find poppler binaries path on Windows."""
    import shutil
    import sys

    if shutil.which("pdftoppm"):
        return None  # Already on PATH

    if sys.platform == "win32":
        candidates = list(Path(r"C:\tools\poppler").rglob("pdftoppm.exe"))
        if candidates:
            return str(candidates[0].parent)

    return None


def _fallback_placeholders(slide_count: int) -> list[tuple[int, bytes]]:
    """Generate simple placeholder PNGs when no renderer is available."""
    from PIL import Image, ImageDraw, ImageFont

    results = []
    for i in range(slide_count):
        img = Image.new("RGB", (960, 540), color=(240, 240, 240))
        draw = ImageDraw.Draw(img)
        text = f"Slide {i + 1}"
        try:
            font = ImageFont.truetype("LiberationSans-Regular.ttf", 48)
        except OSError:
            try:
                font = ImageFont.truetype("arial.ttf", 48)
            except OSError:
                font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (960 - bbox[2] + bbox[0]) // 2
        y = (540 - bbox[3] + bbox[1]) // 2
        draw.text((x, y), text, fill=(100, 100, 100), font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        results.append((i, buf.getvalue()))
    return results


def _extract_title(slide) -> str:
    """Extract the title from a slide."""
    if slide.shapes.title and slide.shapes.title.has_text_frame:
        return slide.shapes.title.text_frame.text.strip()
    return ""


def _extract_body(slide) -> str:
    """Extract all body text (non-title) from a slide."""
    texts: list[str] = []
    for shape in slide.shapes:
        if shape == slide.shapes.title:
            continue
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if text:
                texts.append(text)
    return "\n".join(texts)


def _extract_notes(slide) -> str:
    """Extract speaker notes from a slide."""
    if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
        return slide.notes_slide.notes_text_frame.text.strip()
    return ""

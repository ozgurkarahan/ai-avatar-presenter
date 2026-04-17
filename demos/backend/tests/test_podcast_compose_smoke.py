"""Smoke test for podcast_compose: synthesize 3 dummy clips and compose.

Marked slow — skipped unless ffmpeg is on PATH. Should complete in <30s.
Run with: pytest -m slow demos/backend/tests/test_podcast_compose_smoke.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Make `services.*` importable when pytest is run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.slow

FFMPEG = shutil.which("ffmpeg")


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not on PATH")
def test_compose_smoke(tmp_path: Path) -> None:
    from services.podcast_compose import compose_podcast
    from services.podcast_ingest import Document, Section
    from services.podcast_render import (
        ClipManifest, DialogueTurn, RenderRoles, RoleConfig, Script,
    )

    # 1) Three tiny dummy avatar clips via lavfi (1 s each, with audio).
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    clip_paths = []
    for i in range(3):
        out = clips_dir / f"turn_{i:03d}.webm"
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=red@0.0:s=480x270:r=25:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "300k",
            "-c:a", "libopus",
            str(out),
        ], check=True, capture_output=True)
        clip_paths.append(out)

    # 2) Two dummy slide images.
    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    slide_paths = []
    for i in range(2):
        out = slides_dir / f"slide_{i:03d}.png"
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=#1F2937:s=1920x810:d=0.04",
            "-frames:v", "1", str(out),
        ], check=True, capture_output=True)
        slide_paths.append(str(out))

    document = Document(
        id="doc-smoke",
        title="Smoke Test",
        sections=[Section(heading=f"S{i}", text=f"body {i}") for i in range(2)],
        slide_images=slide_paths,
        slide_titles=["Intro", "Detail"],
        slide_notes=["", ""],
        source_kind="pptx",
    )
    script = Script(
        id="scr-smoke", document_id="doc-smoke",
        turns=[
            DialogueTurn(idx=0, speaker="interviewer", text="Hello and welcome.", slide_idx=0),
            DialogueTurn(idx=1, speaker="expert", text="Glad to be here today.", slide_idx=0),
            DialogueTurn(idx=2, speaker="interviewer", text="Tell us more.", slide_idx=1),
        ],
    )
    roles = RenderRoles(
        interviewer=RoleConfig(avatar="harry", voice="x", display_name="Dr. Harry Chen"),
        expert=RoleConfig(avatar="lisa", voice="y", display_name="Dr. Lisa Patel"),
    )
    clips = [
        ClipManifest(turn_idx=i, speaker=t.speaker, blob_url=str(clip_paths[i]),
                     duration_sec=1.0, word_timings=[])
        for i, t in enumerate(script.turns)
    ]

    result = compose_podcast(
        clips=clips,
        document=document,
        script=script,
        roles=roles,
        out_dir=tmp_path / "out",
        music=False,        # no music file in test env
        intro=False,        # keep it short
    )

    assert result.mp4.exists() and result.mp4.stat().st_size > 1000
    assert result.mp3.exists() and result.mp3.stat().st_size > 100
    assert result.srt.exists()
    srt = result.srt.read_text(encoding="utf-8")
    assert "Dr. Harry Chen" in srt and "Dr. Lisa Patel" in srt

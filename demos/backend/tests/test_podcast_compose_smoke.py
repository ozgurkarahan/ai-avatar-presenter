"""Smoke tests for podcast_compose (real ffmpeg renders).

* ``test_compose_smoke`` synthesizes 3 dummy clips and runs the full pipeline.
* ``test_segment_*`` render single 1.5 s segments with synthetic 16:9, 4:3 and
  portrait slides plus a green-screen "photo" avatar and a transparent VP9
  "prebuilt" avatar, then sample pixels to check the geometry contract
  (slide contained with pillar-boxing, per-speaker chroma key, tiles on top).

Marked slow — skipped unless ffmpeg is on PATH.
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
    assert _probe_size(result.mp4) == (1920, 1080)


# ---------------------------------------------------------------------------
# Geometry smoke: real ffmpeg render of single segments, pixel-sampled.
# ---------------------------------------------------------------------------

BG = (11, 18, 32)        # podcast_compose.BG_COLOR #0B1220
TILE_BG = (22, 33, 58)   # podcast_compose.TILE_BG_COLOR #16213A


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                   check=True, capture_output=True)


def _probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def _frame(video: Path, at: float, out_png: Path):
    from PIL import Image

    _ff("-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", str(out_png))
    return Image.open(out_png).convert("RGB")


def _close(px, ref, tol=24) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(px, ref))


def _is_white(px) -> bool:
    return all(c > 225 for c in px)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("podcast_geometry")
    # Slides: 16:9 red, 4:3 white, portrait white.
    slides = {
        "wide": (d / "wide.png", "1920x1080", "red"),
        "four_three": (d / "four_three.png", "1024x768", "white"),
        "portrait": (d / "portrait.png", "720x1280", "white"),
    }
    for path, size, color in slides.values():
        _ff("-f", "lavfi", "-i", f"color=c={color}:s={size}:d=0.04", "-frames:v", "1", str(path))
    # Photo avatar: 512x512 green screen with a skin-toned "head" + speech.
    photo = d / "photo.mp4"
    _ff("-f", "lavfi", "-i", "color=c=0x00FF00:s=512x512:r=25:d=1.5",
        "-f", "lavfi", "-i", "sine=frequency=330:duration=1.5",
        "-vf", "drawbox=x=156:y=60:w=200:h=380:color=0xC08060:t=fill",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(photo))
    # Prebuilt avatar: 16:9 transparent stage with an opaque testsrc "person".
    webm = d / "prebuilt.webm"
    _ff("-f", "lavfi", "-i", "testsrc=s=200x320:r=25:d=1.5",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
        "-vf", "format=yuva420p,pad=960:540:380:10:color=black@0.0",
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-deadline", "realtime",
        "-cpu-used", "8", "-b:v", "500k", "-c:a", "libopus", "-shortest", str(webm))
    return {"dir": d, "slides": {k: v[0] for k, v in slides.items()}, "photo": photo, "webm": webm}


def _roles():
    from services.podcast_render import RenderRoles, RoleConfig

    return RenderRoles(
        interviewer=RoleConfig(avatar="photo_x", voice="x", display_name="Ann Interviewer"),
        expert=RoleConfig(avatar="lisa", voice="y", display_name="Bob Expert"),
    )


def _render(media, slide_key: str, *, active: str, layout: str = "split_screen_with_slides"):
    from services import avatar_registry
    from services import podcast_compose as pc

    d = media["dir"]
    idle_png = d / f"idle_{active}.png"
    # Idle speaker still: extracted from that speaker's own clip.
    if active == "interviewer":
        clip, idle_src = media["photo"], media["webm"]
        clip_chroma, idle_chroma = True, False
    else:
        clip, idle_src = media["webm"], media["photo"]
        clip_chroma, idle_chroma = False, True
    pc._extract_frame(idle_src, idle_png, at_sec=0.1)
    crop_of = {
        "interviewer": avatar_registry.PODCAST_CROP_PHOTO,
        "expert": avatar_registry.PODCAST_CROP_PREBUILT,
    }
    idle_speaker = "expert" if active == "interviewer" else "interviewer"
    out = d / f"seg_{slide_key}_{active}_{layout}.mp4"
    pc._render_segment(
        clip_path=clip,
        idle_frame=idle_png,
        slide_path=media["slides"][slide_key] if slide_key else None,
        duration=1.5,
        active_speaker=active,
        roles=_roles(),
        out=out,
        chroma_key=clip_chroma,
        idle_chroma_key=idle_chroma,
        active_crop=crop_of[active],
        idle_crop=crop_of[idle_speaker],
        layout=layout,
        slide_counter="1 / 3",
    )
    return out


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not on PATH")
def test_segment_wide_slide_fills_slide_region(media):
    seg = _render(media, "wide", active="interviewer")
    assert _probe_size(seg) == (1920, 1080)
    img = _frame(seg, 0.7, media["dir"] / "wide.png.frame.png")
    red = lambda px: px[0] > 200 and px[1] < 60 and px[2] < 60  # noqa: E731
    # 16:9 slide exactly fills 1280x720 at (320,360).
    for x, y in ((330, 370), (960, 720), (1590, 1070)):
        assert red(img.getpixel((x, y))), (x, y, img.getpixel((x, y)))
    # Gutters stay background.
    for x, y in ((100, 700), (1820, 700)):
        assert _close(img.getpixel((x, y)), BG), (x, y, img.getpixel((x, y)))


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not on PATH")
def test_segment_four_three_slide_is_pillarboxed(media):
    seg = _render(media, "four_three", active="expert")
    img = _frame(seg, 0.7, media["dir"] / "43.frame.png")
    # 1024x768 → 960x720 centred: x 480..1440 white, 320..480 / 1440..1600 bars.
    assert _is_white(img.getpixel((960, 720)))
    assert _is_white(img.getpixel((500, 380)))
    assert _is_white(img.getpixel((1420, 1060)))
    for x in (340, 460, 1460, 1580):
        assert _close(img.getpixel((x, 720)), BG), (x, img.getpixel((x, 720)))


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not on PATH")
def test_segment_portrait_slide_is_contained(media):
    seg = _render(media, "portrait", active="interviewer")
    img = _frame(seg, 0.7, media["dir"] / "portrait.frame.png")
    # 720x1280 → 405x720 centred: x ≈ 757..1162.
    assert _is_white(img.getpixel((960, 720)))
    assert _is_white(img.getpixel((960, 365)))
    assert _is_white(img.getpixel((960, 1075)))
    for x in (700, 1220):
        assert _close(img.getpixel((x, 720)), BG), (x, img.getpixel((x, 720)))


def _green_ratio(img, box) -> float:
    x0, y0, x1, y1 = box
    n = g = 0
    for y in range(y0, y1, 6):
        for x in range(x0, x1, 6):
            r, gg, b = img.getpixel((x, y))
            n += 1
            if gg > 150 and r < 100 and b < 100:
                g += 1
    return g / max(1, n)


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not on PATH")
@pytest.mark.parametrize("active", ["interviewer", "expert"])
def test_segment_avatar_tiles_keyed_per_speaker(media, active):
    from services import podcast_compose as pc

    seg = _render(media, "wide", active=active)
    img = _frame(seg, 0.7, media["dir"] / f"tiles_{active}.frame.png")
    # The photo speaker (interviewer, left tile) is keyed whether active or
    # idle: no green screen survives in its tile.
    assert _green_ratio(img, (8, 8, 552, 352)) < 0.01
    # Its "head" is visible, large, and centred in the tile.
    head = img.getpixel((280, 200))
    assert head[0] > 60 and head[0] > head[2], head
    # Prebuilt (expert, right tile): transparent stage → tile background in
    # the corners (alpha honoured), opaque content in the centre.
    corner = img.getpixel((1380, 40))
    if pc._has_decoder("libvpx-vp9"):
        assert _close(corner, TILE_BG, tol=12), corner
    centre = img.getpixel((1640, 200))
    assert not _close(centre, TILE_BG, tol=10), centre
    # Active tile frame is clay.
    fx = 1 if active == "interviewer" else 1361
    frame_px = img.getpixel((fx, 180))
    assert frame_px[0] > 140 and frame_px[2] < 80, frame_px
    # Nothing is drawn over the slide region by the avatars.
    assert img.getpixel((960, 720))[0] > 200


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not on PATH")
def test_segment_split_screen_only(media):
    seg = _render(media, None, active="interviewer", layout="split_screen_only")
    assert _probe_size(seg) == (1920, 1080)
    img = _frame(seg, 0.7, media["dir"] / "only.frame.png")
    assert _green_ratio(img, (8, 8, 952, 892)) < 0.01
    head = img.getpixel((480, 450))
    assert head[0] > 60 and head[0] > head[2], head
    # Caption/label strip at the bottom stays background.
    assert _close(img.getpixel((40, 1040)), BG)

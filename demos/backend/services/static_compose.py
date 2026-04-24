"""UC2 ffmpeg composition — slide-first with avatar picture-in-picture.

For each slide:
  [slide image] scaled to 1920x1080 as full-frame background
  [avatar WebM] 360x360 PiP in the bottom-right with a rounded/circular mask
  [subtitles]   burnt-in ASS karaoke timed to the narration

Per-segment render then concat via concat FILTER (never -c copy — that
produces audible clicks at AAC frame boundaries).

Final outputs: final.mp4 (H.264+AAC), final.mp3, final.srt, plus a
thumbnail JPEG picked from the first slide.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from services.static_models import SlideNarration, StaticDocument, StaticScript
from services.static_render import SlideClip

log = logging.getLogger(__name__)

VIDEO_W = 1920
VIDEO_H = 1080
FPS = 25

# Layout: "anchor" — slide on the left, avatar in a dedicated right panel
# with its own studio backdrop. Replaces the previous PIP-over-slide which
# hid content in the bottom-right corner and kept the avatar small.
#
#   +-----------------------------+----------+
#   |                             |          |
#   |         SLIDE 1344px        |  AVATAR  |
#   |       (letterbox #F5F5F0)   |  576px   |
#   |                             | (#1E293B)|
#   |                             |          |
#   +-----------------------------+----------+
#
# H1.5 2026-04-24: client called out "avatar too small" + "background
# always the same" on 2026-04-23. This layout more than doubles the
# avatar surface (560x560 vs 360x360, +2.4x area) and introduces a
# contrasting studio backdrop distinct from the slide.
SLIDE_W = 1344           # left column width
AVATAR_COL_W = VIDEO_W - SLIDE_W   # 576 right column
AVATAR_SIZE = 560        # circular avatar inside right column
SLIDE_BG = "0xF5F5F0"    # warm neutral behind letterboxed slide
AVATAR_BG = "0x1E293B"   # dark slate behind avatar — studio feel


def _find_font() -> Optional[str]:
    for c in [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
    ]:
        if Path(c).exists():
            return c
    return None


_FONT = _find_font()


def _font_arg() -> str:
    if not _FONT:
        return ""
    p = _FONT.replace("\\", "/").replace(":", "\\:")
    return f":fontfile='{p}'"


@dataclass
class StaticComposeResult:
    mp4: Path
    mp3: Path
    srt: Path
    thumbnail: Optional[Path]
    duration_sec: float


def compose_static(
    clips: list[SlideClip],
    document: StaticDocument,
    script: StaticScript,
    out_dir: Path,
) -> StaticComposeResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not clips:
        raise ValueError("compose_static requires at least one clip")

    _require_tool("ffmpeg")
    _require_tool("ffprobe")

    clips_sorted = sorted(clips, key=lambda c: c.slide_index)
    narr_by_idx = {n.slide_index: n for n in script.narrations}
    slide_ref_by_idx = {s.index: s for s in document.slides}

    # 1) Probe durations.
    durations = [_probe_duration(Path(c.blob_url)) for c in clips_sorted]

    # 2) Resolve slide image path per clip (fallback to black card).
    fallback = out_dir / "_fallback_slide.png"
    if not fallback.exists():
        _make_fallback_slide(fallback, document.title)

    slide_paths: list[Path] = []
    for clip in clips_sorted:
        ref = slide_ref_by_idx.get(clip.slide_index)
        p = Path(ref.image_ref) if ref and ref.image_ref else None
        slide_paths.append(p if (p and p.exists()) else fallback)

    # 3) ASS karaoke subs.
    ass_path = out_dir / "subs.ass"
    _write_ass(ass_path, clips_sorted, durations, narr_by_idx)

    # 4) Render each segment.
    segment_paths: list[Path] = []
    for i, (clip, dur) in enumerate(zip(clips_sorted, durations)):
        seg_out = out_dir / f"seg_{i:03d}.mp4"
        _render_segment(
            clip_path=Path(clip.blob_url),
            slide_path=slide_paths[i],
            duration=dur,
            out=seg_out,
        )
        segment_paths.append(seg_out)

    # 5) Concat segments + burn subs + loudnorm.
    body = out_dir / "_body.mp4"
    _concat(segment_paths, body)

    final_mp4 = out_dir / "final.mp4"
    _finalize(body, ass_path, final_mp4)

    final_mp3 = out_dir / "final.mp3"
    _extract_mp3(final_mp4, final_mp3)

    final_srt = out_dir / "final.srt"
    _write_srt(final_srt, clips_sorted, durations, narr_by_idx)

    total_dur = float(sum(durations))

    # 6) Thumbnail from the first slide image (not the video — faster + sharper).
    thumb_path = out_dir / "thumb.jpg"
    if not _make_thumbnail(slide_paths[0], thumb_path):
        thumb_path = None  # type: ignore[assignment]

    return StaticComposeResult(
        mp4=final_mp4,
        mp3=final_mp3,
        srt=final_srt,
        thumbnail=thumb_path,
        duration_sec=total_dur,
    )


# ---------------------------------------------------------------------------
# Per-segment
# ---------------------------------------------------------------------------

def _render_segment(
    clip_path: Path,
    slide_path: Path,
    duration: float,
    out: Path,
) -> None:
    """One 1920x1080 MP4 segment: anchor layout (slide left, avatar right panel).

    Slide is letterboxed to the 1344-wide left column with a warm neutral
    background, avatar is rendered at 560x560 with a circular soft mask
    centered in a 576-wide dark slate right column. The two columns are
    stacked horizontally. Keeps audio from the avatar clip.
    """
    # Inputs:
    #   0 = slide image (looped)
    #   1 = avatar WebM (has audio)
    inputs = [
        "-loop", "1", "-t", f"{duration:.3f}", "-i", str(slide_path),
        "-i", str(clip_path),
    ]

    half = AVATAR_SIZE // 2
    edge = half - 4  # solid inside this radius; feather over the last 4px
    fc = (
        # Left column: slide fit-and-pad into 1344x1080 with warm neutral bg.
        f"[0:v]scale={SLIDE_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,"
        f"pad={SLIDE_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color={SLIDE_BG},"
        f"setsar=1,fps={FPS}[slide];"
        # Right column backdrop: solid studio colour.
        f"color=c={AVATAR_BG}:s={AVATAR_COL_W}x{VIDEO_H}:r={FPS},format=yuv420p[rpanel];"
        # Avatar: scale-crop to AVATAR_SIZE square. Combine the WebM's own
        # alpha (character silhouette, transparent background) with a soft
        # circular mask — keeps the character fully opaque but also carves
        # the avatar into a circle over the studio panel.
        f"[1:v]scale={AVATAR_SIZE}:{AVATAR_SIZE}:force_original_aspect_ratio=increase,"
        f"crop={AVATAR_SIZE}:{AVATAR_SIZE},format=yuva420p,"
        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
        f"a='alpha(X,Y)*"
        f"if(lte(hypot(X-{half},Y-{half}),{edge}),1,"
        f"if(lte(hypot(X-{half},Y-{half}),{half}),"
        f"({half}-hypot(X-{half},Y-{half}))/4,0))',"
        f"setsar=1,fps={FPS}[pip];"
        # Avatar centred in the right panel.
        f"[rpanel][pip]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1[rightcol];"
        # Horizontal stack: slide | right panel.
        f"[slide][rightcol]hstack=inputs=2[vout];"
        f"[1:a]anull[aout]"
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-r", str(FPS),
        "-t", f"{duration:.3f}",
        str(out),
    ]
    _run(cmd)


def _concat(parts: list[Path], out: Path) -> None:
    """Concat via filter (re-encode) — never -c copy (AAC boundary clicks)."""
    if len(parts) == 1:
        shutil.copyfile(parts[0], out)
        return
    inputs: list[str] = []
    for p in parts:
        inputs += ["-i", str(p)]
    n = len(parts)
    stream_refs = "".join(f"[{i}:v][{i}:a]" for i in range(n))
    fc = f"{stream_refs}concat=n={n}:v=1:a=1[vout][aout]"
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-r", str(FPS),
        str(out),
    ])


def _finalize(src: Path, ass_path: Path, out: Path) -> None:
    ass_arg = ass_path.resolve().as_posix().replace(":", "\\:")
    fc_video = f"[0:v]subtitles='{ass_arg}'[vout]"
    fc_audio = "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-filter_complex", f"{fc_video};{fc_audio}",
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out),
    ])


def _extract_mp3(src: Path, out: Path) -> None:
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(out),
    ])


def _make_thumbnail(slide_path: Path, out: Path) -> bool:
    try:
        _run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(slide_path),
            "-vf", "scale=640:-2",
            "-frames:v", "1", "-q:v", "3",
            str(out),
        ])
        return out.exists() and out.stat().st_size > 0
    except Exception:  # noqa: BLE001
        return False


def _make_fallback_slide(out: Path, title: str) -> None:
    vf = (
        f"drawtext=text='{_esc(title)}':fontcolor=white:fontsize=72{_font_arg()}:"
        "x=(w-text_w)/2:y=(h-text_h)/2"
    )
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=#0B1220:s={VIDEO_W}x{VIDEO_H}:d=0.04",
        "-vf", vf,
        "-frames:v", "1", str(out),
    ])


# ---------------------------------------------------------------------------
# Subtitles (ASS karaoke + SRT)
# ---------------------------------------------------------------------------

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,34,&H00FFFFFF&,&H0000C8FF&,&H00000000&,&H80000000&,1,0,0,0,100,100,0,0,1,3,1,2,80,656,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _chunk_text(text: str, max_chars: int = 80) -> list[str]:
    """Split text into subtitle-friendly chunks by sentence, then by max_chars."""
    import re
    # Split by sentence boundaries (. ! ? followed by space or end)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        # If adding this sentence would exceed max_chars, flush current
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip() if current else sentence
    if current:
        chunks.append(current.strip())

    # Second pass: if any chunk still exceeds max_chars, split at word boundaries
    final: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final.append(chunk)
        else:
            words = chunk.split()
            line = ""
            for word in words:
                if line and len(line) + len(word) + 1 > max_chars:
                    final.append(line.strip())
                    line = word
                else:
                    line = f"{line} {word}".strip() if line else word
            if line:
                final.append(line.strip())

    return final if final else [text.strip()]


def _write_ass(path, clips, durations, narr_by_idx):
    lines = [ASS_HEADER]
    cursor = 0.0
    for clip, dur in zip(clips, durations):
        n = narr_by_idx.get(clip.slide_index)
        text = (n.narration if n else "").strip()
        if not text:
            cursor += dur
            continue

        chunks = _chunk_text(text)
        total_words = len(text.split())
        chunk_cursor = cursor

        for chunk in chunks:
            chunk_words = chunk.split()
            # Time proportional to word count
            chunk_dur = dur * (len(chunk_words) / max(1, total_words))
            per = max(0.001, chunk_dur / max(1, len(chunk_words)))
            kara = "".join(f"{{\\k{int(per * 100)}}}{_ass_esc(w)} " for w in chunk_words)
            start_ts = _ass_time(chunk_cursor)
            end_ts = _ass_time(chunk_cursor + chunk_dur)
            lines.append(f"Dialogue: 0,{start_ts},{end_ts},Karaoke,,0,0,0,,{kara.strip()}")
            chunk_cursor += chunk_dur

        cursor += dur
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_srt(path, clips, durations, narr_by_idx):
    out_lines: list[str] = []
    cursor = 0.0
    cue_num = 0
    for clip, dur in zip(clips, durations):
        narr = narr_by_idx.get(clip.slide_index)
        text = (narr.narration if narr else "").strip()
        if not text:
            cursor += dur
            continue

        chunks = _chunk_text(text)
        total_words = len(text.split())
        chunk_cursor = cursor

        for chunk in chunks:
            cue_num += 1
            chunk_words = chunk.split()
            chunk_dur = dur * (len(chunk_words) / max(1, total_words))
            out_lines.append(str(cue_num))
            out_lines.append(f"{_srt_time(chunk_cursor)} --> {_srt_time(chunk_cursor + chunk_dur)}")
            out_lines.append(chunk)
            out_lines.append("")
            chunk_cursor += chunk_dur

        cursor += dur
    path.write_text("\n".join(out_lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tiny utilities
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("ffmpeg failed: %s\nSTDERR: %s", " ".join(cmd[:3]), proc.stderr[-2000:])
        raise RuntimeError(f"ffmpeg/ffprobe failed: {proc.stderr[-500:]}")


def _require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"required tool missing on PATH: {name}")


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout)
    return float(data.get("format", {}).get("duration", 0.0) or 0.0)


_DRAWTEXT_ESC = str.maketrans({
    "\\": "\\\\", ":": "\\:", "'": "\u2019", "%": "\\%",
})


def _esc(text: str) -> str:
    return (text or "").translate(_DRAWTEXT_ESC)


def _ass_esc(word: str) -> str:
    return re.sub(r"[{}\\]", "", word)


def _ass_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _srt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


__all__ = ["compose_static", "StaticComposeResult"]

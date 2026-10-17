"""ffmpeg composition for the podcast.

Builds a single 1920x1080 25 fps video following the geometry contract
documented in ``docs/podcast.md`` ("Video layout"):

``split_screen_with_slides`` (default)
  * interviewer tile 560x360 at (0,0), expert tile 560x360 at (1360,0) —
    head-and-shoulders crop of each avatar; the active speaker plays its live
    clip inside a 4 px clay frame, the idle speaker is a dimmed still
  * centre label zone (560,0,800,96): "Name · Role" for both speakers, the
    active one highlighted with a clay accent bar
  * centre caption zone (560,96,800,264): karaoke captions (ASS ``\\k``),
    centred and wrapped to ≤3 lines so they never cover a face or the slide
  * slide contained — never stretched or cropped — into 1280x720 at
    (320,360); dark gutters left/right with an "n / N" slide counter

``split_screen_only``
  * two 960x900 tiles, labels at y 900..960, captions at y 960..1080

Plus an optional 2 s branded intro + 2 s outro, background music ducked to
-25 dB (graceful skip if the file is missing) and loudnorm
I=-16:TP=-1.5:LRA=11. Exports final.mp4 (H.264+AAC), final.mp3, final.srt.
"""

from __future__ import annotations

import functools
import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from services import avatar_registry
from services.podcast_ingest import Document
from services.podcast_render import ClipManifest, DialogueTurn, RenderRoles, Script

log = logging.getLogger(__name__)

VIDEO_W = 1920
VIDEO_H = 1080
FPS = 25
MUSIC_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "music" / "background.mp3"
INTRO_SEC = 2.0
OUTRO_SEC = 2.0

BG_COLOR = "#0B1220"          # canvas, gutters and slide letter/pillar-box
TILE_BG_COLOR = "#16213A"     # avatar tile panel
ACCENT_COLOR = "#B8461E"      # clay: active frame + label accent
FRAME_PX = 4
IDLE_DIM = 0.55               # brightness multiplier of the idle still

DEFAULT_LAYOUT = "split_screen_with_slides"


def _find_font() -> Optional[str]:
    """Pick a usable TTF for drawtext (Windows ffmpeg lacks fontconfig defaults)."""
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


_FONT = _find_font()


def _font_arg() -> str:
    """':fontfile=...' suffix for drawtext, or empty when none found."""
    if not _FONT:
        return ""
    p = _FONT.replace("\\", "/").replace(":", "\\:")
    return f":fontfile='{p}'"

# Neutral brand palette (placeholder).
BRAND_PRIMARY = "&H00C8412B&"   # ASS color = AABBGGRR
BRAND_SECONDARY = "&H00FFFFFF&"


# ---------------------------------------------------------------------------
# Layout geometry (contract v1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


@dataclass(frozen=True)
class LayoutGeometry:
    name: str
    interviewer_tile: Rect
    expert_tile: Rect
    label_zone: Rect
    caption_zone: Rect
    slide: Optional[Rect]
    caption_font_size: int
    caption_max_chars: int     # per line, sized so a line fits the zone width
    caption_max_lines: int

    def tile(self, speaker: str) -> Rect:
        return self.interviewer_tile if speaker == "interviewer" else self.expert_tile


LAYOUTS: dict[str, LayoutGeometry] = {
    "split_screen_with_slides": LayoutGeometry(
        name="split_screen_with_slides",
        interviewer_tile=Rect(0, 0, 560, 360),
        expert_tile=Rect(1360, 0, 560, 360),
        label_zone=Rect(560, 0, 800, 96),
        caption_zone=Rect(560, 96, 800, 264),
        slide=Rect(320, 360, 1280, 720),
        # Arial Bold 34 px ≈ 18.5 px/char → 40 chars ≈ 740 px (< 760 px usable).
        caption_font_size=34,
        caption_max_chars=40,
        caption_max_lines=3,
    ),
    "split_screen_only": LayoutGeometry(
        name="split_screen_only",
        interviewer_tile=Rect(0, 0, 960, 900),
        expert_tile=Rect(960, 0, 960, 900),
        label_zone=Rect(0, 900, 1920, 60),
        caption_zone=Rect(80, 960, 1760, 120),
        slide=None,
        caption_font_size=34,
        caption_max_chars=72,
        caption_max_lines=2,
    ),
}


def get_layout(name: Optional[str]) -> LayoutGeometry:
    """Resolve a ``podcast_models.Layout`` value (unknown → default)."""
    if name and name in LAYOUTS:
        return LAYOUTS[name]
    if name:
        log.warning("unknown podcast layout %r — using %s", name, DEFAULT_LAYOUT)
    return LAYOUTS[DEFAULT_LAYOUT]


@dataclass(frozen=True)
class SpeakerVisual:
    """How one speaker's avatar footage must be keyed and framed."""
    chroma_key: bool = False
    crop: tuple[float, float, float, float] = avatar_registry.PODCAST_CROP_PREBUILT


@dataclass
class ComposeResult:
    mp4: Path
    mp3: Path
    srt: Path


def compose_podcast(
    clips: list[ClipManifest],
    document: Optional[Document],
    script: Script,
    roles: RenderRoles,
    out_dir: Path,
    music: bool = True,
    intro: bool = True,
    music_path: Optional[Path] = None,
    layout: str = DEFAULT_LAYOUT,
) -> ComposeResult:
    """Run the full compose pipeline. Returns paths of the three deliverables."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not clips:
        raise ValueError("compose_podcast requires at least one clip")

    _require_tool("ffmpeg")
    _require_tool("ffprobe")

    geo = get_layout(layout)
    clips_sorted = sorted(clips, key=lambda c: c.turn_idx)
    turn_by_idx = {t.idx: t for t in script.turns}

    # 1) Probe each clip's actual duration so SRT timing is exact.
    durations = [_probe_duration(Path(c.blob_url)) for c in clips_sorted]

    # 2) Resolve a slide image (+ "n / N" counter) per turn.
    slides = _resolve_slides(document, script, out_dir) if geo.slide else {}

    # 2b) Per-speaker framing: chroma flag + head-and-shoulders crop. The idle
    #     tile must use the idle speaker's own chroma flag, not the active one.
    visuals = {
        speaker: _speaker_visual(roles, speaker, clips_sorted)
        for speaker in ("interviewer", "expert")
    }

    # 2c) One neutral still frame per speaker — used as the idle visual so the
    #     off-mic avatar doesn't keep gesturing/lip-syncing during the other
    #     speaker's turn.
    idle_frames: dict[str, Optional[Path]] = {}
    for speaker in ("interviewer", "expert"):
        idle_frames[speaker] = None
        for clip in clips_sorted:
            if clip.speaker == speaker:
                fp = out_dir / f"_idle_{speaker}.png"
                try:
                    _extract_frame(Path(clip.blob_url), fp, at_sec=0.1)
                    idle_frames[speaker] = fp
                except Exception as exc:  # noqa: BLE001
                    log.warning("idle frame extract failed for %s: %s", speaker, exc)
                break

    # 3) Render the ASS karaoke subtitle file. Account for the intro-card
    #    offset so karaoke timing stays synced with spoken audio after concat.
    ass_path = out_dir / "subs.ass"
    ass_offset = INTRO_SEC if intro else 0.0
    _write_ass(ass_path, clips_sorted, durations, turn_by_idx, roles,
               offset=ass_offset, layout=geo.name)

    # 4) Build per-turn segment videos, then concat. A single monolithic
    #    filtergraph for N turns blows past ffmpeg's stack on long podcasts;
    #    rendering per-segment + concat is more robust for a demo.
    fallback_slide: Optional[Path] = None
    segment_paths: list[Path] = []
    for i, (clip, dur) in enumerate(zip(clips_sorted, durations)):
        turn = turn_by_idx.get(clip.turn_idx)
        active_speaker = turn.speaker if turn else clip.speaker
        idle_speaker = "expert" if active_speaker == "interviewer" else "interviewer"
        slide_path: Optional[Path] = None
        counter: Optional[str] = None
        if geo.slide:
            slide_path, counter = slides.get(clip.turn_idx, (None, None))
            if slide_path is None:
                if fallback_slide is None:
                    fallback_slide = _fallback_slide(document, out_dir)
                slide_path = fallback_slide
        seg_out = out_dir / f"seg_{i:03d}.mp4"
        _render_segment(
            clip_path=Path(clip.blob_url),
            idle_frame=idle_frames.get(idle_speaker),
            slide_path=slide_path,
            duration=dur,
            active_speaker=active_speaker,
            roles=roles,
            out=seg_out,
            lead_in=0.0,
            chroma_key=bool(getattr(clip, "chroma_key", visuals[active_speaker].chroma_key)),
            idle_chroma_key=visuals[idle_speaker].chroma_key,
            active_crop=visuals[active_speaker].crop,
            idle_crop=visuals[idle_speaker].crop,
            layout=geo.name,
            slide_counter=counter,
        )
        segment_paths.append(seg_out)

    # 5) Optional intro / outro cards.
    extras: list[Path] = []
    if intro:
        intro_card = out_dir / "intro.mp4"
        _render_card(intro_card, "DeckFM", INTRO_SEC)
        extras.append(intro_card)

    body_concat = out_dir / "body.mp4"
    _concat(extras + segment_paths, body_concat)

    if intro:
        outro_card = out_dir / "outro.mp4"
        _render_card(outro_card, "Thanks for listening", OUTRO_SEC)
        full_concat = out_dir / "full.mp4"
        _concat([body_concat, outro_card], full_concat)
    else:
        full_concat = body_concat

    # 6) Burn karaoke subtitles + (optional) music + loudnorm onto final.
    final_mp4 = out_dir / "final.mp4"
    _finalize(full_concat, ass_path, final_mp4, music_path if music else None)

    final_mp3 = out_dir / "final.mp3"
    _extract_mp3(final_mp4, final_mp3)

    final_srt = out_dir / "final.srt"
    _write_srt(
        final_srt,
        clips_sorted,
        durations,
        turn_by_idx,
        roles,
        offset=ass_offset,
    )

    return ComposeResult(mp4=final_mp4, mp3=final_mp3, srt=final_srt)


def _speaker_visual(roles: RenderRoles, speaker: str, clips: list[ClipManifest]) -> SpeakerVisual:
    """Chroma flag + crop rect for ``speaker`` from its clips and the registry."""
    role = getattr(roles, speaker)
    first = next((c for c in clips if c.speaker == speaker), None)
    avatar_id = role.avatar
    if first is not None and "avatar_id" in getattr(first, "model_fields_set", set()):
        avatar_id = first.avatar_id
    if not avatar_registry.is_known(avatar_id):
        chroma = bool(first.chroma_key) if first is not None else False
        crop = avatar_registry.PODCAST_CROP_PHOTO if chroma else avatar_registry.PODCAST_CROP_PREBUILT
        return SpeakerVisual(chroma_key=chroma, crop=crop)
    entry = avatar_registry.get(avatar_id)
    chroma = bool(first.chroma_key) if first is not None else entry.chroma_key
    crop = avatar_registry.podcast_crop_for(entry)
    if entry.podcast_crop is None and chroma != entry.chroma_key:
        # The clip was rendered differently from the registry kind — frame it
        # by what was actually rendered (green-screen portrait vs 16:9 stage).
        crop = avatar_registry.PODCAST_CROP_PHOTO if chroma else avatar_registry.PODCAST_CROP_PREBUILT
    return SpeakerVisual(chroma_key=chroma, crop=crop)


# ---------------------------------------------------------------------------
# Per-segment composition
# ---------------------------------------------------------------------------

def _clamp_crop(crop) -> tuple[float, float, float, float]:
    """Clamp a normalized (x, y, w, h) rect into the unit square."""
    try:
        x, y, w, h = (float(v) for v in crop)
    except (TypeError, ValueError):
        return avatar_registry.PODCAST_CROP_PREBUILT
    x = min(max(x, 0.0), 0.95)
    y = min(max(y, 0.0), 0.95)
    w = min(max(w, 0.05), 1.0 - x)
    h = min(max(h, 0.05), 1.0 - y)
    return (x, y, w, h)


def _crop_filter(crop) -> str:
    """ffmpeg crop on a normalized rect, rounded down to even pixel values."""
    x, y, w, h = _clamp_crop(crop)
    return (
        f"crop=w=trunc(iw*{w:.4f}/2)*2:h=trunc(ih*{h:.4f}/2)*2:"
        f"x=trunc(iw*{x:.4f}/2)*2:y=trunc(ih*{y:.4f}/2)*2"
    )


def _chroma_filter(enabled: bool) -> str:
    # Photo avatars come in as mp4 with a #00FF00 background — strip the
    # green before any other filter so crop/scale/pad see a clean alpha layer.
    if not enabled:
        return ""
    return (
        "chromakey=0x00ff00:0.22:0.12,"
        "despill=type=green:mix=0.6:expand=0.3:brightness=0,"
    )


def _tile_chain(src: str, out: str, visual: SpeakerVisual, tile: Rect,
                *, dim: bool, pre: str = "") -> str:
    """chromakey/despill → crop → scale(decrease) → pad → [dim] → yuva420p."""
    dim_f = (
        f"colorchannelmixer=rr={IDLE_DIM}:gg={IDLE_DIM}:bb={IDLE_DIM},"
        if dim else ""
    )
    return (
        f"{src}{pre}{_chroma_filter(visual.chroma_key)}{_crop_filter(visual.crop)},"
        f"scale={tile.w}:{tile.h}:force_original_aspect_ratio=decrease,setsar=1,"
        f"format=rgba,pad={tile.w}:{tile.h}:(ow-iw)/2:oh-ih:color=black@0,"
        f"{dim_f}format=yuva420p,fps={FPS}{out};"
    )


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def _drawtext(text: str, x: str, y: int | str, size: int, color: str) -> str:
    return (
        f"drawtext=text='{_esc(text)}':x={x}:y={y}:fontsize={size}:"
        f"fontcolor={color}{_font_arg()}"
    )


def _label_filters(geo: LayoutGeometry, active_speaker: str,
                   names: dict[str, str]) -> list[str]:
    """drawbox/drawtext filters for the speaker name labels."""
    roles = {"interviewer": "Interviewer", "expert": "Expert"}
    lz = geo.label_zone
    parts: list[str] = []
    if geo.slide is not None:
        # Both names in the centre label zone, each next to its own tile.
        for speaker in ("interviewer", "expert"):
            active = speaker == active_speaker
            name = _truncate(names.get(speaker, ""), 22)
            name_size, role_size = (32, 22) if active else (26, 20)
            name_color = "white" if active else "#94A3B8"
            role_color = "#F2B8A0" if active else "#64748B"
            if speaker == "interviewer":
                x = str(lz.x + 28)
                bar_x = lz.x + 10
            else:
                x = f"{lz.x + lz.w - 28}-text_w"
                bar_x = lz.x + lz.w - 16
            if active:
                parts.append(
                    f"drawbox=x={bar_x}:y={lz.y + 14}:w=6:h=68:color={ACCENT_COLOR}:t=fill"
                )
            parts.append(_drawtext(name, x, lz.y + 14, name_size, name_color))
            parts.append(_drawtext(roles[speaker], x, lz.y + 56, role_size, role_color))
    else:
        # One "Name · Role" line centred under each tile.
        for speaker in ("interviewer", "expert"):
            active = speaker == active_speaker
            tile = geo.tile(speaker)
            label = f"{_truncate(names.get(speaker, ''), 40)} \u00b7 {roles[speaker]}"
            size = 30 if active else 26
            color = "white" if active else "#94A3B8"
            parts.append(_drawtext(label, f"{tile.x}+({tile.w}-text_w)/2", lz.y + 12, size, color))
            if active:
                parts.append(
                    f"drawbox=x={tile.cx - 90}:y={lz.y + 50}:w=180:h=4:color={ACCENT_COLOR}:t=fill"
                )
    return parts


def _build_segment_filter(
    *,
    active_speaker: str,
    total_dur: float,
    active: SpeakerVisual,
    idle: SpeakerVisual,
    names: dict[str, str],
    layout: str = DEFAULT_LAYOUT,
    lead_in: float = 0.0,
    has_idle: bool = True,
    slide_counter: Optional[str] = None,
) -> str:
    """Pure builder of the per-segment ``-filter_complex`` graph.

    Input indices: with slides ``0`` = slide still, ``1`` = active clip (video
    + audio), ``2`` = idle still; without slides (``split_screen_only``) the
    slide input is absent and the others shift down by one. Outputs
    ``[vout]`` and ``[aout]``.
    """
    geo = get_layout(layout)
    idle_speaker = "expert" if active_speaker == "interviewer" else "interviewer"
    base = 1 if geo.slide else 0
    act_in, idle_in = f"[{base}:v]", f"[{base + 1}:v]"
    act_a = f"[{base}:a]"
    a_tile, i_tile = geo.tile(active_speaker), geo.tile(idle_speaker)

    parts: list[str] = []
    canvas = (
        f"color=c={BG_COLOR}:s={VIDEO_W}x{VIDEO_H}:r={FPS}:d={total_dur:.3f},format=yuv420p"
    )
    for t in (geo.interviewer_tile, geo.expert_tile):
        canvas += f",drawbox=x={t.x}:y={t.y}:w={t.w}:h={t.h}:color={TILE_BG_COLOR}:t=fill"
    parts.append(f"{canvas}[bg];")

    if geo.slide:
        s = geo.slide
        parts.append(
            f"[0:v]scale={s.w}:{s.h}:force_original_aspect_ratio=decrease,"
            f"pad={s.w}:{s.h}:(ow-iw)/2:(oh-ih)/2:color={BG_COLOR},setsar=1,"
            f"fps={FPS}[slide];"
        )

    # Prepend a cloned frame to the active avatar if lead_in > 0 so its
    # lip-sync stays aligned with the (delayed) audio.
    pre = f"tpad=start_duration={lead_in:.3f}:start_mode=clone," if lead_in > 0 else ""
    parts.append(_tile_chain(act_in, "[av_a]", active, a_tile, dim=False, pre=pre))
    if has_idle:
        parts.append(_tile_chain(idle_in, "[av_i]", idle, i_tile, dim=True))

    cur = "[bg]"
    if geo.slide:
        parts.append(f"{cur}[slide]overlay=x={geo.slide.x}:y={geo.slide.y}[c_s];")
        cur = "[c_s]"
    parts.append(f"{cur}[av_a]overlay=x={a_tile.x}:y={a_tile.y}[c_a];")
    cur = "[c_a]"
    if has_idle:
        parts.append(f"{cur}[av_i]overlay=x={i_tile.x}:y={i_tile.y}[c_i];")
        cur = "[c_i]"

    deco = [
        f"drawbox=x={a_tile.x}:y={a_tile.y}:w={a_tile.w}:h={a_tile.h}:"
        f"color={ACCENT_COLOR}:t={FRAME_PX}"
    ]
    deco += _label_filters(geo, active_speaker, names)
    if geo.slide and slide_counter:
        gx = geo.slide.x + geo.slide.w   # right gutter
        deco.append(_drawtext(
            slide_counter, f"{gx}+({VIDEO_W - gx}-text_w)/2", VIDEO_H - 64, 28, "#94A3B8",
        ))
    parts.append(f"{cur}{','.join(deco)}[vout];")

    if lead_in > 0:
        ms = int(lead_in * 1000)
        parts.append(f"{act_a}adelay={ms}|{ms}[aout]")
    else:
        parts.append(f"{act_a}anull[aout]")
    return "".join(parts)


def _render_segment(
    clip_path: Path,
    idle_frame: Optional[Path],
    slide_path: Optional[Path],
    duration: float,
    active_speaker: str,
    roles: RenderRoles,
    out: Path,
    lead_in: float = 0.0,
    chroma_key: bool = False,
    *,
    idle_chroma_key: Optional[bool] = None,
    active_crop: Optional[tuple[float, float, float, float]] = None,
    idle_crop: Optional[tuple[float, float, float, float]] = None,
    layout: str = DEFAULT_LAYOUT,
    slide_counter: Optional[str] = None,
) -> None:
    """Render a single dialogue segment to MP4 (see module docstring for layout).

    The idle speaker is a STATIC still (dimmed) — looping its previous video
    would make it appear to gesture/lip-sync during the active turn. If
    ``lead_in > 0`` leading silence is added so the first word isn't clipped.
    """
    geo = get_layout(layout)
    total_dur = duration + lead_in
    has_idle = bool(idle_frame and idle_frame.exists())

    inputs: list[str] = []
    if geo.slide:
        if slide_path is None:
            raise ValueError("slide_path is required for layout " + geo.name)
        inputs += ["-loop", "1", "-t", f"{total_dur:.3f}", "-i", str(slide_path)]
    inputs += [*_decoder_args(clip_path), "-i", str(clip_path)]
    if has_idle:
        inputs += ["-loop", "1", "-t", f"{total_dur:.3f}", "-i", str(idle_frame)]

    active = SpeakerVisual(
        chroma_key=chroma_key,
        crop=active_crop or avatar_registry.PODCAST_CROP_PREBUILT,
    )
    idle = SpeakerVisual(
        chroma_key=chroma_key if idle_chroma_key is None else idle_chroma_key,
        crop=idle_crop or avatar_registry.PODCAST_CROP_PREBUILT,
    )
    fc = _build_segment_filter(
        active_speaker=active_speaker,
        total_dur=total_dur,
        active=active,
        idle=idle,
        names={
            "interviewer": roles.interviewer.display_name,
            "expert": roles.expert.display_name,
        },
        layout=geo.name,
        lead_in=lead_in,
        has_idle=has_idle,
        slide_counter=slide_counter,
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-r", str(FPS),
        "-t", f"{total_dur:.3f}",
        str(out),
    ]
    _run(cmd)


@functools.lru_cache(maxsize=None)
def _has_decoder(name: str) -> bool:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-decoders"], capture_output=True, text=True, timeout=30,
        )
    except Exception:  # noqa: BLE001
        return False
    return any(line.split()[1:2] == [name] for line in proc.stdout.splitlines() if line.strip())


def _probe_video_codec(path: Path) -> str:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:  # noqa: BLE001
        return ""
    return (proc.stdout or "").strip().splitlines()[0].strip() if proc.stdout.strip() else ""


def _decoder_args(video: Path) -> list[str]:
    """Force libvpx-vp9 for VP9 WebM so the avatar's alpha channel survives.

    ffmpeg's native vp9 decoder silently drops the alpha plane, which turns
    the transparent stage of prebuilt avatars into opaque black.
    """
    if Path(video).suffix.lower() != ".webm":
        return []
    if _probe_video_codec(Path(video)) == "vp9" and _has_decoder("libvpx-vp9"):
        return ["-c:v", "libvpx-vp9"]
    return []


def _extract_frame(video: Path, out_png: Path, at_sec: float = 0.1) -> Path:
    """Grab one frame from `video` at `at_sec` seconds, save as PNG (keeps alpha)."""
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_sec:.3f}", *_decoder_args(video), "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(out_png),
    ])
    return out_png


# ---------------------------------------------------------------------------
# Concat / finalize / extract
# ---------------------------------------------------------------------------

def _concat(parts: list[Path], out: Path) -> None:
    """Concatenate MP4 segments with FULL re-encode.

    The concat *demuxer* with `-c copy` produces clicks at AAC frame
    boundaries AND can desync when segments have slightly different PTS
    origins. Using the concat *filter* (via `-filter_complex`) resamples
    timestamps from zero and eliminates both artifacts.

    Cost: re-encode time (≈1× realtime). For a <10-min podcast this is
    acceptable and far preferable to audible noise.
    """
    if len(parts) == 1:
        shutil.copyfile(parts[0], out)
        return

    inputs: list[str] = []
    for p in parts:
        inputs += ["-i", str(p)]

    n = len(parts)
    # [0:v][0:a][1:v][1:a]...concat=n=N:v=1:a=1[vout][aout]
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


def _finalize(src: Path, ass_path: Path, out: Path, music_path: Optional[Path]) -> None:
    """Burn subtitles, mix music, normalize loudness."""
    ass_arg = ass_path.resolve().as_posix().replace(":", "\\:")
    fc_video = f"[0:v]subtitles='{ass_arg}'[vout]"

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if music_path and Path(music_path).exists():
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        fc_audio = (
            "[1:a]volume=-25dB,aloop=loop=-1:size=2e9[mus];"
            "[0:a][mus]amix=inputs=2:duration=first:dropout_transition=2[mix];"
            "[mix]loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
        )
    else:
        fc_audio = "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]"

    cmd += [
        "-filter_complex", f"{fc_video};{fc_audio}",
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out),
    ]
    _run(cmd)


def _extract_mp3(src: Path, out: Path) -> None:
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(out),
    ])


def _render_card(out: Path, title: str, duration: float) -> None:
    """Black card with brand title text — placeholder for real intro art."""
    fc = (
        f"color=c={BG_COLOR}:s={VIDEO_W}x{VIDEO_H}:r={FPS}:d={duration:.3f},"
        f"drawtext=text='{_esc(title)}':fontcolor=#C8412B:fontsize=96{_font_arg()}:"
        "x=(w-text_w)/2:y=(h-text_h)/2-40,"
        f"drawtext=text='AI Avatar Podcast':fontcolor=white:fontsize=36{_font_arg()}:"
        "x=(w-text_w)/2:y=(h-text_h)/2+80[v]"
    )
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-filter_complex", fc,
        "-map", "[v]", "-map", "0:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-r", str(FPS),
        str(out),
    ])


# ---------------------------------------------------------------------------
# Slide resolution
# ---------------------------------------------------------------------------

def _resolve_slides(
    document: Optional[Document], script: Script, out_dir: Path,
) -> dict[int, tuple[Optional[Path], Optional[str]]]:
    """Map turn idx → (slide image path or None for fallback, "n / N" counter)."""
    images = list(document.slide_images) if document else []
    total = len(images)
    resolved: dict[int, tuple[Optional[Path], Optional[str]]] = {}
    warned: set[int] = set()
    for turn in sorted(script.turns, key=lambda t: t.idx):
        if not images:
            resolved[turn.idx] = (None, None)
            continue
        slide_idx = turn.slide_idx if turn.slide_idx is not None else 0
        idx = max(0, min(slide_idx, total - 1))
        raw = images[idx]
        p = Path(raw) if raw else None
        if p is not None and p.is_file():
            resolved[turn.idx] = (p, f"{idx + 1} / {total}")
        else:
            if idx not in warned:
                log.warning("podcast compose: slide %d image missing (%r) — using fallback slide",
                            idx + 1, raw)
                warned.add(idx)
            resolved[turn.idx] = (None, None)
    return resolved


def _fallback_slide(document: Optional[Document], out_dir: Path) -> Path:
    out = out_dir / "_fallback_slide.png"
    if not out.exists():
        _make_fallback_slide(out, (document.title if document else "") or "DeckFM")
    return out


def _make_fallback_slide(out: Path, title: str) -> None:
    """Title card rendered at the slide's native 1280x720 (16:9)."""
    s = LAYOUTS[DEFAULT_LAYOUT].slide
    assert s is not None
    vf = (
        f"drawtext=text='{_esc(_truncate(title, 40))}':fontcolor=white:fontsize=56{_font_arg()}:"
        "x=(w-text_w)/2:y=(h-text_h)/2"
    )
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=#1E293B:s={s.w}x{s.h}:d=0.04",
        "-vf", vf,
        "-frames:v", "1", str(out),
    ])


# ---------------------------------------------------------------------------
# Subtitles — ASS karaoke + SRT
# ---------------------------------------------------------------------------

def _ass_header(layout: str = DEFAULT_LAYOUT) -> str:
    """ASS header whose margins confine text to the layout's caption zone."""
    geo = get_layout(layout)
    cz = geo.caption_zone
    margin_l = cz.x + 20
    margin_r = VIDEO_W - (cz.x + cz.w) + 20
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_W}
PlayResY: {VIDEO_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,{geo.caption_font_size},&H00FFFFFF&,&H0000C8FF&,&H00000000&,&H80000000&,1,0,0,0,100,100,0,0,1,3,1,5,{margin_l},{margin_r},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


# Back-compat: the default-layout header.
ASS_HEADER = _ass_header(DEFAULT_LAYOUT)


def _chunk_text(text: str, max_chars: int = 80) -> list[str]:
    """Split text into subtitle-friendly chunks by sentence, then by max_chars."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip() if current else sentence
    if current:
        chunks.append(current.strip())

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


def _greedy_wrap(pieces: list[str], max_chars: int) -> list[list[str]]:
    lines: list[list[str]] = []
    cur: list[str] = []
    cur_len = 0
    for w in pieces:
        add = len(w) + (1 if cur else 0)
        if cur and cur_len + add > max_chars:
            lines.append(cur)
            cur, cur_len = [w], len(w)
        else:
            cur.append(w)
            cur_len += add
    if cur:
        lines.append(cur)
    return lines


def _wrap_words(words: list[str], max_chars: int) -> list[list[str]]:
    """Balanced word wrap into lines of ≤ max_chars (over-long words are split).

    Uses the greedy line count, then the narrowest width that keeps that count
    so lines come out even (no lone trailing word).
    """
    pieces: list[str] = []
    for w in words:
        while len(w) > max_chars:
            pieces.append(w[:max_chars])
            w = w[max_chars:]
        if w:
            pieces.append(w)
    greedy = _greedy_wrap(pieces, max_chars)
    n = len(greedy)
    if n <= 1:
        return greedy
    longest = max(len(p) for p in pieces)
    for width in range(max(longest, len(" ".join(pieces)) // n), max_chars):
        lines = _greedy_wrap(pieces, width)
        if len(lines) <= n:
            return lines
    return greedy


def _caption_blocks(text: str, max_chars: int, max_lines: int) -> list[list[list[str]]]:
    """Wrap ``text`` and group the lines into on-screen events of ≤ max_lines."""
    words = [_ass_esc(w) for w in text.split()]
    words = [w for w in words if w]
    lines = _wrap_words(words, max_chars)
    return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]


def _write_ass(path, clips, durations, turn_by_idx, roles, offset=0.0,
               layout: str = DEFAULT_LAYOUT):
    geo = get_layout(layout)
    cz = geo.caption_zone
    pos = f"{{\\an5\\pos({cz.cx},{cz.cy})}}"
    lines = [_ass_header(geo.name)]
    cursor = offset
    for clip, dur in zip(clips, durations):
        turn = turn_by_idx.get(clip.turn_idx)
        text = (turn.text if turn else "").strip()
        if not text:
            cursor += dur
            continue

        chunks = _chunk_text(text)
        total_words = len(text.split())
        chunk_cursor = cursor

        for chunk in chunks:
            chunk_dur = dur * (len(chunk.split()) / max(1, total_words))
            blocks = _caption_blocks(chunk, geo.caption_max_chars, geo.caption_max_lines)
            block_words_total = sum(len(ln) for b in blocks for ln in b) or 1
            block_cursor = chunk_cursor
            for block in blocks:
                n_words = sum(len(ln) for ln in block)
                block_dur = chunk_dur * (n_words / block_words_total)
                per = max(0.001, block_dur / max(1, n_words))
                kara = "\\N".join(
                    " ".join(f"{{\\k{int(per * 100)}}}{w}" for w in ln) for ln in block
                )
                start_ts = _ass_time(block_cursor)
                end_ts = _ass_time(block_cursor + block_dur)
                lines.append(f"Dialogue: 0,{start_ts},{end_ts},Karaoke,,0,0,0,,{pos}{kara}")
                block_cursor += block_dur
            chunk_cursor += chunk_dur

        cursor += dur
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_srt(path, clips, durations, turn_by_idx, roles, offset=0.0):
    out_lines: list[str] = []
    cursor = offset
    cue_num = 0
    for clip, dur in zip(clips, durations):
        turn = turn_by_idx.get(clip.turn_idx)
        text = (turn.text if turn else "").strip()
        speaker_label = (
            roles.interviewer.display_name if clip.speaker == "interviewer"
            else roles.expert.display_name
        )
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
            out_lines.append(f"{speaker_label}: {chunk}")
            out_lines.append("")
            chunk_cursor += chunk_dur

        cursor += dur
    path.write_text("\n".join(out_lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tiny utilities
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> None:
    log.debug("$ %s", " ".join(cmd))
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


# Re-expose for tests
__all__ = ["compose_podcast", "ComposeResult", "MUSIC_DEFAULT", "LAYOUTS", "get_layout"]

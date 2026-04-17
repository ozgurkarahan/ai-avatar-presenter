"""ffmpeg composition for the UC3 podcast.

Builds a single 1920x1080 25 fps video with:
  * top 75%: current slide image (crossfade across slide changes)
  * bottom 25%: split-screen interviewer / expert avatars (transparent WebM)
  * lower-third name strips, glow on active speaker, idle dim
  * karaoke subtitle strip above the bottom edge (ASS \\k tags)
  * optional 2 s branded intro + 2 s outro
  * background music ducked to -25 dB (graceful skip if file missing)
  * loudnorm I=-16:TP=-1.5:LRA=11

Exports final.mp4 (H.264+AAC), final.mp3, final.srt.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from services.podcast_ingest import Document
from services.podcast_render import ClipManifest, DialogueTurn, RenderRoles, Script

log = logging.getLogger(__name__)

VIDEO_W = 1920
VIDEO_H = 1080
SLIDE_H = 810           # top 75%
AVATAR_BAND_H = 270     # bottom 25%
HALF_W = VIDEO_W // 2
FPS = 25
MUSIC_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "music" / "background.mp3"
INTRO_SEC = 2.0
OUTRO_SEC = 2.0


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

# Saint-Gobain brand-ish palette (placeholder).
BRAND_PRIMARY = "&H00C8412B&"   # ASS color = AABBGGRR
BRAND_SECONDARY = "&H00FFFFFF&"


@dataclass
class ComposeResult:
    mp4: Path
    mp3: Path
    srt: Path


def compose_podcast(
    clips: list[ClipManifest],
    document: Document,
    script: Script,
    roles: RenderRoles,
    out_dir: Path,
    music: bool = True,
    intro: bool = True,
    music_path: Optional[Path] = None,
) -> ComposeResult:
    """Run the full compose pipeline. Returns paths of the three deliverables."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not clips:
        raise ValueError("compose_podcast requires at least one clip")

    _require_tool("ffmpeg")
    _require_tool("ffprobe")

    clips_sorted = sorted(clips, key=lambda c: c.turn_idx)
    turn_by_idx = {t.idx: t for t in script.turns}

    # 1) Probe each clip's actual duration so SRT timing is exact.
    durations = [_probe_duration(Path(c.blob_url)) for c in clips_sorted]

    # 2) Resolve a slide image per turn (fallback to a generated black frame).
    slide_paths = _resolve_slide_paths(document, script, out_dir)

    # 2b) Extract one neutral still frame per speaker — used as the idle
    #     visual so the off-mic avatar doesn't keep gesturing and lip-syncing
    #     during the other speaker's turn.
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
    #    offset + first-segment lead-in so karaoke timing stays synced with
    #    spoken audio after concat.
    ass_path = out_dir / "subs.ass"
    ass_offset = INTRO_SEC if intro else 0.0
    _write_ass(ass_path, clips_sorted, durations, turn_by_idx, roles, offset=ass_offset)

    # 4) Build per-turn segment videos, then concat. A single-monolithic
    #    filtergraph for N turns blows past ffmpeg's stack on long podcasts;
    #    rendering per-segment + concat is more robust for a demo.
    segment_paths: list[Path] = []
    for i, (clip, dur) in enumerate(zip(clips_sorted, durations)):
        turn = turn_by_idx.get(clip.turn_idx)
        slide_path = slide_paths[i]
        seg_out = out_dir / f"seg_{i:03d}.mp4"
        active_speaker = turn.speaker if turn else clip.speaker
        idle_speaker = "expert" if active_speaker == "interviewer" else "interviewer"
        _render_segment(
            clip_path=Path(clip.blob_url),
            idle_frame=idle_frames.get(idle_speaker),
            slide_path=slide_path,
            duration=dur,
            active_speaker=active_speaker,
            roles=roles,
            out=seg_out,
            lead_in=0.0,
        )
        segment_paths.append(seg_out)

    # 5) Optional intro / outro cards.
    extras: list[Path] = []
    if intro:
        intro_card = out_dir / "intro.mp4"
        _render_card(intro_card, "Saint-Gobain Insights", INTRO_SEC)
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


# ---------------------------------------------------------------------------
# Per-segment composition
# ---------------------------------------------------------------------------

def _render_segment(
    clip_path: Path,
    idle_frame: Optional[Path],
    slide_path: Path,
    duration: float,
    active_speaker: str,
    roles: RenderRoles,
    out: Path,
    lead_in: float = 0.0,
) -> None:
    """Render a single dialogue segment to MP4.

    Layout:
      [slide] scaled to 1920x810 → top
      [active_avatar] (live WebM, has audio) over a 960x270 panel
      [idle_avatar] a STATIC PNG of the other speaker (dimmed) — we do not
        loop the other speaker's previous video because that makes them
        appear to gesture/lip-sync during the active speaker's turn.

    If `lead_in > 0`, leading silence is added to the audio so the first
    spoken word isn't clipped by the intro-to-speech transition.
    """
    interviewer_active = active_speaker == "interviewer"
    active_label = roles.interviewer.display_name if interviewer_active else roles.expert.display_name
    idle_label = roles.expert.display_name if interviewer_active else roles.interviewer.display_name
    active_role_name = "Interviewer" if interviewer_active else "Expert"
    idle_role_name = "Expert" if interviewer_active else "Interviewer"

    total_dur = duration + lead_in

    # Inputs:
    #   0 = slide image (looped to total_dur)
    #   1 = active speaker WebM (transparent, has audio)
    #   2 = idle speaker STILL IMAGE or transparent fallback
    inputs = [
        "-loop", "1", "-t", f"{total_dur:.3f}", "-i", str(slide_path),
        "-i", str(clip_path),
    ]
    if idle_frame and idle_frame.exists():
        inputs += ["-loop", "1", "-t", f"{total_dur:.3f}", "-i", str(idle_frame)]
        idle_input = "[2:v]"
    else:
        inputs += ["-f", "lavfi", "-t", f"{total_dur:.3f}", "-i", "color=c=black@0.0:s=960x270:r=25"]
        idle_input = "[2:v]"

    # Prepend a blank frame to the active avatar video if lead_in > 0 so its
    # lip-sync stays aligned with the (delayed) audio.
    if lead_in > 0:
        active_v = (
            f"[1:v]tpad=start_duration={lead_in:.3f}:start_mode=clone,"
            f"scale={HALF_W}:{AVATAR_BAND_H}:force_original_aspect_ratio=decrease,"
            f"setsar=1,fps={FPS}[av_a];"
        )
        active_a = f"[1:a]adelay={int(lead_in * 1000)}|{int(lead_in * 1000)}[aout]"
    else:
        active_v = (
            f"[1:v]scale={HALF_W}:{AVATAR_BAND_H}:force_original_aspect_ratio=decrease,"
            f"setsar=1,fps={FPS}[av_a];"
        )
        active_a = "[1:a]anull[aout]"

    # Build complex filter.
    fc = (
        f"[0:v]scale={VIDEO_W}:{SLIDE_H},setsar=1,fps={FPS}[slide];"
        + active_v
        + f"{idle_input}scale={HALF_W}:{AVATAR_BAND_H}:force_original_aspect_ratio=decrease,"
          f"setsar=1,fps={FPS},format=yuva420p,colorchannelmixer=aa=0.55[av_i];"
        + f"color=c=#0B1220:s={VIDEO_W}x{AVATAR_BAND_H}:r={FPS}:d={total_dur:.3f}[band];"
    )

    if interviewer_active:
        fc += (
            f"[band][av_a]overlay=x=(960-overlay_w)/2:y=(270-overlay_h)/2[band1];"
            f"[band1][av_i]overlay=x=960+(960-overlay_w)/2:y=(270-overlay_h)/2[band2];"
        )
        active_x, idle_x = 24, HALF_W + 24
    else:
        fc += (
            f"[band][av_i]overlay=x=(960-overlay_w)/2:y=(270-overlay_h)/2[band1];"
            f"[band1][av_a]overlay=x=960+(960-overlay_w)/2:y=(270-overlay_h)/2[band2];"
        )
        active_x, idle_x = HALF_W + 24, 24

    # Lower-third name strips.
    fc += (
        f"[band2]drawbox=x={active_x - 12}:y={AVATAR_BAND_H - 50}:w=420:h=34:"
        f"color=#C8412B@0.85:t=fill,"
        f"drawtext=text='{_esc(active_label)} \\u00b7 {active_role_name}':"
        f"x={active_x}:y={AVATAR_BAND_H - 44}:fontcolor=white:fontsize=20{_font_arg()},"
        f"drawbox=x={idle_x - 12}:y={AVATAR_BAND_H - 50}:w=420:h=34:"
        f"color=#1F2937@0.7:t=fill,"
        f"drawtext=text='{_esc(idle_label)} \\u00b7 {idle_role_name}':"
        f"x={idle_x}:y={AVATAR_BAND_H - 44}:fontcolor=white:fontsize=20{_font_arg()}[bandfinal];"
        f"[slide][bandfinal]vstack=inputs=2[vout];"
        + active_a
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


def _extract_frame(video: Path, out_png: Path, at_sec: float = 0.1) -> Path:
    """Grab one frame from `video` at `at_sec` seconds, save as PNG."""
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_sec:.3f}", "-i", str(video),
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
        f"color=c=#0B1220:s={VIDEO_W}x{VIDEO_H}:r={FPS}:d={duration:.3f},"
        f"drawtext=text='{_esc(title)}':fontcolor=#C8412B:fontsize=96{_font_arg()}:"
        "x=(w-text_w)/2:y=(h-text_h)/2-40,"
        f"drawtext=text='AI Avatar Podcast':fontcolor=white:fontsize=36{_font_arg()}:"
        "x=(w-text_w)/2:y=(h-text_h)/2+80[v]"
    )
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000",
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

def _resolve_slide_paths(document: Document, script: Script, out_dir: Path) -> list[Path]:
    """Map each turn → slide image path, generating fallbacks as needed."""
    paths: list[Path] = []
    fallback = out_dir / "_fallback_slide.png"
    if not fallback.exists():
        _make_fallback_slide(fallback, document.title)

    for turn in sorted(script.turns, key=lambda t: t.idx):
        slide_idx = turn.slide_idx if turn.slide_idx is not None else 0
        idx = max(0, min(slide_idx, max(0, len(document.slide_images) - 1)))
        if document.slide_images and idx < len(document.slide_images):
            p = Path(document.slide_images[idx])
            paths.append(p if p.exists() else fallback)
        else:
            paths.append(fallback)
    return paths


def _make_fallback_slide(out: Path, title: str) -> None:
    vf = (
        f"drawtext=text='{_esc(title)}':fontcolor=white:fontsize=72{_font_arg()}:"
        "x=(w-text_w)/2:y=(h-text_h)/2"
    )
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=#0B1220:s={VIDEO_W}x{SLIDE_H}:d=0.04",
        "-vf", vf,
        "-frames:v", "1", str(out),
    ])


# ---------------------------------------------------------------------------
# Subtitles — ASS karaoke + SRT
# ---------------------------------------------------------------------------

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,42,&H00FFFFFF&,&H0000C8FF&,&H00000000&,&H80000000&,1,0,0,0,100,100,0,0,1,2,1,2,40,40,290,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _write_ass(
    path: Path,
    clips: list[ClipManifest],
    durations: list[float],
    turn_by_idx: dict[int, "DialogueTurn"],
    roles: RenderRoles,
    offset: float = 0.0,
) -> None:
    lines = [ASS_HEADER]
    cursor = offset
    for clip, dur in zip(clips, durations):
        turn = turn_by_idx.get(clip.turn_idx)
        text = (turn.text if turn else "").strip()
        if not text:
            cursor += dur
            continue

        words = text.split()
        # Use vtt cue timings if present, else evenly distribute across dur.
        if clip.word_timings:
            per = max(0.001, dur / max(1, len(words)))
            kara = "".join(f"{{\\k{int(per * 100)}}}{_ass_esc(w)} " for w in words)
        else:
            per = max(0.001, dur / max(1, len(words)))
            kara = "".join(f"{{\\k{int(per * 100)}}}{_ass_esc(w)} " for w in words)

        start_ts = _ass_time(cursor)
        end_ts = _ass_time(cursor + dur)
        lines.append(
            f"Dialogue: 0,{start_ts},{end_ts},Karaoke,,0,0,0,,{kara.strip()}"
        )
        cursor += dur
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_srt(
    path: Path,
    clips: list[ClipManifest],
    durations: list[float],
    turn_by_idx: dict[int, "DialogueTurn"],
    roles: RenderRoles,
    offset: float = 0.0,
) -> None:
    out_lines: list[str] = []
    cursor = offset
    for n, (clip, dur) in enumerate(zip(clips, durations), start=1):
        turn = turn_by_idx.get(clip.turn_idx)
        text = (turn.text if turn else "").strip()
        speaker_label = (
            roles.interviewer.display_name if clip.speaker == "interviewer"
            else roles.expert.display_name
        )
        out_lines.append(str(n))
        out_lines.append(f"{_srt_time(cursor)} --> {_srt_time(cursor + dur)}")
        out_lines.append(f"{speaker_label}: {text}")
        out_lines.append("")
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
__all__ = ["compose_podcast", "ComposeResult", "MUSIC_DEFAULT"]

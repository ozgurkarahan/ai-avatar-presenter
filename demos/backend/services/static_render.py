"""UC2 per-slide batch avatar synthesis.

For each SlideNarration we submit ONE batch avatar synthesis job with a
single SSML input and transparent-WebM/VP9 output, so the avatar can be
composited as a picture-in-picture over the slide in static_compose.

Jobs are submitted SERIALLY with 429/Retry-After back-off because Azure
throttles concurrent batch synthesis jobs at ~5 per resource. Polling
runs concurrently afterwards.
"""
from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests
from pydantic import BaseModel, Field

from config import AzureConfig
from services.avatar import (
    AVATAR_MAP,
    VOICE_MAP,
    _get_speech_auth_header,
    _get_speech_base_url,
    build_ssml,
    style_for,
)
from services.static_models import SlideNarration, StaticScript

log = logging.getLogger(__name__)


# Default avatar for UC2 single-narrator picture-in-picture.
# H1.5 2026-04-24: lisa/casual-sitting — most photo-realistic standard
# avatar in Azure's catalog, with 14 presenter-friendly gestures.
# Replaces max/business (too 3D-stylized, client feedback 2026-04-23).
DEFAULT_AVATAR = "lisa"

# Gender-based avatar matching. Used as a *fallback* when the caller
# hasn't explicitly chosen an avatar.
_MALE_VOICE_NAMES = {
    "Andrew", "Remy", "Tristan", "Florian", "Alessio",
    "Macerio", "Yunfan", "Masaru",
}
_FEMALE_VOICE_NAMES = {
    "Ava", "Vivienne", "Ximena", "Seraphina", "Isabella",
    "Thalita", "Xiaochen", "Nanami",
}

# H1.5: lisa (casual-sitting) = most natural female; harry (business) =
# natural male counterpart with welcome/hello/thanks gestures. Both chosen
# over max/meg to favor photo-realism over gesture variety.
_MALE_DEFAULT = "harry"
_FEMALE_DEFAULT = "lisa"


def avatar_for_voice(voice: str, fallback: str = DEFAULT_AVATAR) -> str:
    """Return an avatar whose gender matches the voice.

    Used as the *default* resolver when the caller doesn't pass an
    explicit avatar choice. Male voice -> harry, female voice -> lisa.
    Unknown voice -> fallback (DEFAULT_AVATAR).
    """
    if not voice:
        return fallback
    for name in _MALE_VOICE_NAMES:
        if name in voice:
            return _MALE_DEFAULT
    for name in _FEMALE_VOICE_NAMES:
        if name in voice:
            return _FEMALE_DEFAULT
    return fallback


class SlideClip(BaseModel):
    slide_index: int
    blob_url: str  # local path after download
    duration_sec: float = 0.0
    word_timings: list[dict] = Field(default_factory=list)


@dataclass
class _SlideJob:
    narration: SlideNarration
    job_id: str
    video_url: Optional[str] = None
    vtt_url: Optional[str] = None
    duration_sec: float = 0.0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# HTTP helper — mirrors podcast_render._request_with_429_retry
# ---------------------------------------------------------------------------

def _request_with_429_retry(
    method: str,
    url: str,
    *,
    headers: dict,
    json_body: Optional[dict] = None,
    timeout: int = 30,
    max_retries: int = 6,
) -> requests.Response:
    delay = 5.0
    last: Optional[requests.Response] = None
    for attempt in range(max_retries):
        r = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
        last = r
        if r.status_code != 429:
            r.raise_for_status()
            return r
        ra = r.headers.get("Retry-After")
        try:
            wait = float(ra) if ra else delay
        except ValueError:
            wait = delay
        wait = max(wait, 2.0)
        log.warning("429 from %s (attempt %d/%d) — sleeping %.1fs", url, attempt + 1, max_retries, wait)
        time.sleep(wait)
        delay = min(delay * 1.7, 60.0)
    assert last is not None
    last.raise_for_status()
    return last


# ---------------------------------------------------------------------------
# Submit / poll
# ---------------------------------------------------------------------------

def _submit_slide(cfg: AzureConfig, n: SlideNarration, language: str,
                  avatar: Optional[str] = None, *, intro: bool = False) -> _SlideJob:
    job_id = str(uuid.uuid4())
    base = _get_speech_base_url(cfg)
    url = f"{base}/avatar/batchsyntheses/{job_id}?api-version=2024-08-01"

    voice = n.voice or VOICE_MAP.get(language, VOICE_MAP["en-US"])
    # If the caller didn't pick an avatar, fall back to gender-matched
    # default (female voice -> lisa, male voice -> harry). If the caller
    # *did* pass an explicit avatar, respect it verbatim.
    resolved_avatar = avatar if avatar else avatar_for_voice(voice)
    avatar_char = AVATAR_MAP.get(resolved_avatar, resolved_avatar)
    # Only inject an intro gesture on the very first slide. build_ssml
    # looks up a docs-verified gesture per (character, style) — unknown
    # pairs are silently skipped, so this is safe for all characters.
    intro_gesture = avatar_char if intro else None
    ssml = build_ssml(n.narration, language, voice=voice,
                      intro_gesture_for=intro_gesture)

    payload = {
        "inputKind": "SSML",
        "inputs": [{"content": ssml}],
        "avatarConfig": {
            "talkingAvatarCharacter": avatar_char,
            "talkingAvatarStyle": style_for(avatar_char),
            "videoFormat": "webm",
            "videoCodec": "vp9",
            "subtitleType": "soft_embedded",
            "backgroundColor": "#00000000",
        },
    }
    headers = {**_get_speech_auth_header(cfg), "Content-Type": "application/json"}
    _request_with_429_retry("PUT", url, headers=headers, json_body=payload, timeout=30)
    log.info("uc2: submitted slide=%d job=%s avatar=%s intro=%s",
             n.slide_index, job_id, avatar_char, intro)
    return _SlideJob(narration=n, job_id=job_id)


def _poll_slide(cfg: AzureConfig, sj: _SlideJob, timeout: int, interval: int) -> _SlideJob:
    base = _get_speech_base_url(cfg)
    url = f"{base}/avatar/batchsyntheses/{sj.job_id}?api-version=2024-08-01"
    headers = _get_speech_auth_header(cfg)

    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 429:
            ra = r.headers.get("Retry-After")
            try:
                wait = float(ra) if ra else float(interval)
            except ValueError:
                wait = float(interval)
            time.sleep(max(wait, 2.0))
            continue
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "unknown")
        if status == "Succeeded":
            outputs = data.get("outputs", {}) or {}
            sj.video_url = outputs.get("result")
            sj.vtt_url = (
                outputs.get("subtitles")
                or outputs.get("destinationUrl")
                or outputs.get("webvttUrl")
            )
            props = data.get("properties", {}) or {}
            sj.duration_sec = float(
                props.get("durationInMilliseconds", 0) or 0
            ) / 1000.0
            return sj
        if status == "Failed":
            sj.error = (data.get("properties", {}) or {}).get("error", {}).get("message", "failed")
            return sj
        time.sleep(interval)

    sj.error = "timeout"
    return sj


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(1 << 16):
                if chunk:
                    f.write(chunk)
    return dest


def _parse_webvtt(vtt_text: str) -> list[dict]:
    out: list[dict] = []
    cur_start = cur_end = None
    cur_text: list[str] = []
    for raw in vtt_text.splitlines():
        line = raw.strip()
        if "-->" in line:
            if cur_start is not None and cur_text:
                out.append({"start": cur_start, "end": cur_end, "text": " ".join(cur_text).strip()})
            cur_text = []
            try:
                lhs, rhs = [s.strip() for s in line.split("-->", 1)]
                cur_start = _vtt_ts(lhs)
                cur_end = _vtt_ts(rhs.split(" ", 1)[0])
            except Exception:
                cur_start = cur_end = None
        elif line and not line.startswith(("WEBVTT", "NOTE")):
            cur_text.append(line)
    if cur_start is not None and cur_text:
        out.append({"start": cur_start, "end": cur_end, "text": " ".join(cur_text).strip()})
    return out


def _vtt_ts(s: str) -> float:
    parts = s.split(":")
    if len(parts) == 3:
        h, m, rest = parts
        return int(h) * 3600 + int(m) * 60 + float(rest.replace(",", "."))
    if len(parts) == 2:
        m, rest = parts
        return int(m) * 60 + float(rest.replace(",", "."))
    return float(s)


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def render_static(
    cfg: AzureConfig,
    script: StaticScript,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    work_dir: Optional[Path] = None,
    timeout: int = 900,
    poll_interval: int = 5,
    avatar: Optional[str] = None,
) -> list[SlideClip]:
    """Render every SlideNarration into a transparent-WebM clip."""
    work_dir = Path(work_dir) if work_dir else Path("data/static_video") / uuid.uuid4().hex[:8]
    work_dir.mkdir(parents=True, exist_ok=True)

    narrations = sorted(script.narrations, key=lambda n: n.slide_index)
    total = len(narrations)
    if total == 0:
        raise ValueError("StaticScript has no narrations to render")

    # Submit SERIALLY to stay under the 5-concurrent-jobs quota.
    pending: list[_SlideJob] = []
    first_idx = narrations[0].slide_index
    for n in narrations:
        is_intro = n.slide_index == first_idx
        pending.append(_submit_slide(cfg, n, script.language, avatar=avatar, intro=is_intro))

    # Poll concurrently.
    finished: list[_SlideJob] = []
    done = 0
    with ThreadPoolExecutor(max_workers=min(8, total)) as pool:
        futs = [pool.submit(_poll_slide, cfg, sj, timeout, poll_interval) for sj in pending]
        for f in futs:
            finished.append(f.result())
            done += 1
            if progress_cb:
                try:
                    progress_cb(done, total)
                except Exception:  # noqa: BLE001
                    pass

    clips: list[SlideClip] = []
    failed: list[tuple[int, str]] = []
    for sj in sorted(finished, key=lambda t: t.narration.slide_index):
        if sj.error or not sj.video_url:
            failed.append((sj.narration.slide_index, sj.error or "no video url"))
            continue
        local = _download(sj.video_url, work_dir / f"slide_{sj.narration.slide_index:03d}.webm")
        word_timings: list[dict] = []
        if sj.vtt_url:
            try:
                vtt_local = _download(sj.vtt_url, work_dir / f"slide_{sj.narration.slide_index:03d}.vtt")
                word_timings = _parse_webvtt(vtt_local.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("vtt fetch failed for slide %d: %s", sj.narration.slide_index, exc)
        clips.append(SlideClip(
            slide_index=sj.narration.slide_index,
            blob_url=str(local),
            duration_sec=sj.duration_sec,
            word_timings=word_timings,
        ))

    if failed:
        details = "; ".join(f"slide {i}: {err}" for i, err in failed)
        raise RuntimeError(f"{len(failed)}/{total} slide renders failed: {details}")

    return clips

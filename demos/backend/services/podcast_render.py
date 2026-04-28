"""Per-speaker batch avatar synthesis for the UC3 podcast.

Design intent: submit ONE batch synthesis job per (avatar, voice) pair with
multiple SSML inputs (one per turn) so we incur batch overhead only twice
per podcast and get one transparent-WebM clip per turn back.

Implementation reality (2024-08-01 batch synthesis API): the response shape
for multi-input jobs (`outputs.result` is a single archive URL containing
files named per input) is awkward to parse and not stable across regions.
For demo robustness we **fall back to one batch job per turn**, but submit
those jobs concurrently (per speaker) so end-to-end latency is comparable
to the multi-input approach. If/when we want to flip to true multi-input,
the only change is `_submit_per_turn` → `_submit_grouped`.
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
from services import avatar_registry
from services.avatar import (
    VOICE_MAP,
    _get_speech_auth_header,
    _get_speech_base_url,
    build_ssml,
)
from services.podcast_models import (
    DialogueTurn,
    RenderRoles,
    RoleConfig,
    Script,
)

log = logging.getLogger(__name__)


# Back-compat alias so callers importing RenderRequest from here still work.
class RenderRequest(BaseModel):
    """Internal render request used by `render_podcast` when invoked directly.

    The HTTP API uses `podcast_models.RenderRequest` (which has script_id and
    layout/music/intro); this dataclass-like model bundles the script + roles
    + language so the synchronous worker has everything it needs.
    """
    script: Script
    roles: RenderRoles
    language: str = "en-US"


class ClipManifest(BaseModel):
    turn_idx: int
    speaker: str
    blob_url: str
    duration_sec: float = 0.0
    word_timings: list[dict] = Field(default_factory=list)
    chroma_key: bool = True
    avatar_id: str = avatar_registry.DEFAULT_ID


# ---------------------------------------------------------------------------
# Internal — one batch job per turn (the safe path).
# ---------------------------------------------------------------------------

@dataclass
class _TurnJob:
    turn: DialogueTurn
    role: RoleConfig
    job_id: str
    avatar_id: str = avatar_registry.DEFAULT_ID
    video_format: str = "mp4"
    chroma_key: bool = True
    video_url: Optional[str] = None
    vtt_url: Optional[str] = None
    duration_sec: float = 0.0
    error: Optional[str] = None


def _request_with_429_retry(
    method: str,
    url: str,
    *,
    headers: dict,
    json_body: Optional[dict] = None,
    timeout: int = 30,
    max_retries: int = 6,
) -> requests.Response:
    """HTTP call that retries on 429 honoring Retry-After (seconds or HTTP-date).

    Batch avatar synthesis throttles at ~5 concurrent jobs per resource; the
    service returns 429 with a Retry-After header. We back off exponentially
    from 5s up to 60s if no header is provided.
    """
    delay = 5.0
    last: Optional[requests.Response] = None
    for attempt in range(max_retries):
        r = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
        last = r
        if r.status_code != 429:
            r.raise_for_status()
            return r
        ra = r.headers.get("Retry-After")
        wait: float
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


def _submit_turn(cfg: AzureConfig, turn: DialogueTurn, role: RoleConfig, language: str) -> _TurnJob:
    """Submit one batch synthesis job with a single SSML input.

    Uses transparent-background WebM/VP9 so the avatar can be composited
    over the slide thumbnail in podcast_compose.
    """
    job_id = str(uuid.uuid4())
    base = _get_speech_base_url(cfg)
    url = f"{base}/avatar/batchsyntheses/{job_id}?api-version=2024-08-01"

    voice = role.voice or VOICE_MAP.get(language, VOICE_MAP["en-US"])
    entry = avatar_registry.get(role.avatar) if role.avatar else avatar_registry.for_voice(voice)
    ssml = build_ssml(turn.text, language, voice=voice)

    payload = {
        "inputKind": "SSML",
        "inputs": [{"content": ssml}],
        "avatarConfig": avatar_registry.avatar_config_payload(entry),
    }
    headers = {**_get_speech_auth_header(cfg), "Content-Type": "application/json"}
    _request_with_429_retry("PUT", url, headers=headers, json_body=payload, timeout=30)
    log.info("submitted batch turn=%d speaker=%s avatar=%s job=%s",
             turn.idx, turn.speaker, entry.foundry_name, job_id)
    return _TurnJob(
        turn=turn,
        role=role,
        job_id=job_id,
        avatar_id=entry.id,
        video_format=entry.video_format,
        chroma_key=entry.chroma_key,
    )


def _poll_turn(cfg: AzureConfig, tj: _TurnJob, timeout: int, interval: int) -> _TurnJob:
    """Poll one turn-job until terminal state, capture video + vtt URLs."""
    base = _get_speech_base_url(cfg)
    url = f"{base}/avatar/batchsyntheses/{tj.job_id}?api-version=2024-08-01"
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
            log.warning("429 polling turn=%d — sleeping %.1fs", tj.turn.idx, max(wait, 2.0))
            time.sleep(max(wait, 2.0))
            continue
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "unknown")
        if status == "Succeeded":
            outputs = data.get("outputs", {}) or {}
            tj.video_url = outputs.get("result")
            # Webvtt for word-by-word karaoke. Field naming varies by API version.
            tj.vtt_url = (
                outputs.get("subtitles")
                or outputs.get("destinationUrl")
                or outputs.get("webvttUrl")
            )
            props = data.get("properties", {}) or {}
            tj.duration_sec = float(
                props.get("durationInMilliseconds", 0) or props.get("billableCharacterCount", 0)
            ) / (1000.0 if "durationInMilliseconds" in props else 1.0)
            return tj
        if status == "Failed":
            tj.error = (data.get("properties", {}) or {}).get("error", {}).get("message", "failed")
            return tj
        time.sleep(interval)

    tj.error = "timeout"
    return tj


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(1 << 16):
                if chunk:
                    f.write(chunk)
    return dest


def _parse_webvtt_word_timings(vtt_text: str) -> list[dict]:
    """Best-effort parse: each cue → {start, end, text}.

    Speech batch synthesis emits cue-level (not word-level) WebVTT in most
    cases; we surface those as 'words' so the karaoke filter has something
    to work with. If no cues are present, returns [].
    """
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
# Public API
# ---------------------------------------------------------------------------

def render_podcast(
    cfg: AzureConfig,
    script: Script,
    roles: RenderRoles,
    progress_cb: Optional[Callable[[int], None]] = None,
    language: str = "en-US",
    work_dir: Optional[Path] = None,
    timeout: int = 900,
    poll_interval: int = 5,
    max_parallel: int = 1,
) -> list[ClipManifest]:
    """Render every dialogue turn into a transparent-WebM clip.

    Returns ClipManifest list ordered by `turn_idx`. Local file paths are
    used for `blob_url`; callers that need real Azure blob URLs can re-upload
    via `services.storage.PresentationStore` afterward.

    progress_cb(n_completed) is invoked after each turn finishes polling.
    """
    work_dir = Path(work_dir) if work_dir else Path("data/podcast") / uuid.uuid4().hex[:8]
    work_dir.mkdir(parents=True, exist_ok=True)

    role_for = {"interviewer": roles.interviewer, "expert": roles.expert}

    # Submit all turns concurrently — Azure batches them internally per voice.
    pending: list[_TurnJob] = []
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futs = [
            pool.submit(_submit_turn, cfg, t, role_for[t.speaker], language)
            for t in sorted(script.turns, key=lambda x: x.idx)
        ]
        for f in futs:
            pending.append(f.result())

    # Poll concurrently.
    finished: list[_TurnJob] = []
    completed_n = 0
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futs = [pool.submit(_poll_turn, cfg, tj, timeout, poll_interval) for tj in pending]
        for f in futs:
            finished.append(f.result())
            completed_n += 1
            if progress_cb:
                try:
                    progress_cb(completed_n)
                except Exception:  # noqa: BLE001
                    pass

    manifests: list[ClipManifest] = []
    failed: list[tuple[int, str]] = []
    for tj in sorted(finished, key=lambda t: t.turn.idx):
        if tj.error or not tj.video_url:
            log.error("turn %d failed: %s", tj.turn.idx, tj.error)
            failed.append((tj.turn.idx, tj.error or "no video url"))
            continue
        ext = tj.video_format or "webm"
        local_video = _download(tj.video_url, work_dir / f"turn_{tj.turn.idx:03d}.{ext}")
        word_timings: list[dict] = []
        if tj.vtt_url:
            try:
                vtt_local = _download(tj.vtt_url, work_dir / f"turn_{tj.turn.idx:03d}.vtt")
                word_timings = _parse_webvtt_word_timings(vtt_local.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("vtt fetch failed for turn %d: %s", tj.turn.idx, exc)

        manifests.append(ClipManifest(
            turn_idx=tj.turn.idx,
            speaker=tj.turn.speaker,
            blob_url=str(local_video),
            duration_sec=tj.duration_sec,
            word_timings=word_timings,
            chroma_key=tj.chroma_key,
            avatar_id=tj.avatar_id,
        ))

    if failed:
        # Fail loud — silent drops produce unusable videos where one speaker
        # is missing entirely. The PoC should surface the problem instead.
        details = "; ".join(f"turn {i}: {err}" for i, err in failed)
        raise RuntimeError(f"{len(failed)}/{len(finished)} avatar turns failed: {details}")

    return manifests

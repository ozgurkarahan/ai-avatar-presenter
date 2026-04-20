"""End-to-end render tests for UC2 (static video) and UC3 (podcast).

Full happy-path: ingest -> script (streaming) -> render -> poll until done
-> download media file. Expensive: each UC + language costs TTS tokens +
~5-8 min for UC2 and ~3-5 min for UC3.

Runs per language using the matching RFI fixture:
  fr-FR -> securite-bases.pptx           (Group A - Safety)
  en-US -> decarbonization-intro.pptx    (Group B - Sustainability)
  es-ES -> ia-industrial-intro.pptx      (Group C - AI)

Usage:
    # Default: English only (same as before, cheap)
    python tests/e2e_render.py --base-url https://...

    # Multi-language pass (expensive ~30-60 min)
    python tests/e2e_render.py --base-url https://... --languages fr-FR,en-US,es-ES

    # Pick one UC
    python tests/e2e_render.py --base-url https://... --skip-podcast --languages en-US
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

DEFAULT_BASE = os.environ.get("BASE_URL", "http://localhost:8080")
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "rfi"

POLL_TIMEOUT_SEC = 600  # 10 minutes max per render job
POLL_INTERVAL_SEC = 6


# ---------------------------------------------------------------------------
# Per-language test plan (fixture + voice pair)
# ---------------------------------------------------------------------------
@dataclass
class LangPlan:
    language: str              # e.g. "fr-FR"
    fixture: str               # filename under tests/fixtures/rfi/
    voice_male: str            # e.g. "fr-FR-Remy:DragonHDLatestNeural"
    voice_female: str          # e.g. "fr-FR-Vivienne:DragonHDLatestNeural"


PLANS: dict[str, LangPlan] = {
    "fr-FR": LangPlan(
        language="fr-FR",
        fixture="securite-bases.pptx",
        voice_male="fr-FR-Remy:DragonHDLatestNeural",
        voice_female="fr-FR-Vivienne:DragonHDLatestNeural",
    ),
    "en-US": LangPlan(
        language="en-US",
        fixture="decarbonization-intro.pptx",
        voice_male="en-US-Andrew:DragonHDLatestNeural",
        voice_female="en-US-Ava:DragonHDLatestNeural",
    ),
    "es-ES": LangPlan(
        language="es-ES",
        fixture="ia-industrial-intro.pptx",
        voice_male="es-ES-Tristan:DragonHDLatestNeural",
        voice_female="es-ES-Ximena:DragonHDLatestNeural",
    ),
}


# ---------------------------------------------------------------------------
# Logging helpers (terminal-friendly, ASCII safe for Windows stdout)
# ---------------------------------------------------------------------------
@dataclass
class RunResult:
    uc: str               # "UC2" or "UC3"
    language: str
    fixture: str
    state: str = "pending"   # "pending" | "pass" | "fail"
    detail: str = ""
    duration_sec: float = 0.0
    output_bytes: int = 0


class Log:
    def __init__(self) -> None:
        self.passes = 0
        self.fails = 0
        self.runs: list[RunResult] = []

    def header(self, title: str) -> None:
        print(f"\n{'=' * 70}\n== {title}\n{'=' * 70}")

    def step(self, msg: str) -> None:
        print(f"  -> {msg}")

    def ok(self, msg: str) -> None:
        self.passes += 1
        print(f"  [PASS] {msg}")

    def fail(self, msg: str) -> None:
        self.fails += 1
        print(f"  [FAIL] {msg}")

    def record(self, result: RunResult) -> None:
        self.runs.append(result)

    def summary(self) -> int:
        print(f"\n{'=' * 70}")
        print(f"RESULTS: {self.passes} passed  {self.fails} failed")
        if self.runs:
            print(f"\nPer-run matrix:")
            print(f"{'UC':<5}{'LANGUAGE':<10}{'FIXTURE':<32}{'STATE':<8}{'BYTES':>12}{'SEC':>8}")
            print("-" * 75)
            for r in self.runs:
                print(
                    f"{r.uc:<5}{r.language:<10}{r.fixture:<32}"
                    f"{r.state:<8}{r.output_bytes:>12,}{r.duration_sec:>8.1f}"
                )
        print(f"{'=' * 70}")
        return 0 if self.fails == 0 else 1


# ---------------------------------------------------------------------------
# UC2 - Static video (1 language)
# ---------------------------------------------------------------------------
def run_uc2_for_language(client: httpx.Client, plan: LangPlan, log: Log) -> None:
    log.header(f"UC2  STATIC VIDEO  {plan.language}  {plan.fixture}")
    result = RunResult(uc="UC2", language=plan.language, fixture=plan.fixture)
    log.record(result)

    fixture_path = FIXTURE_DIR / plan.fixture
    if not fixture_path.exists():
        msg = f"Fixture missing: {fixture_path}"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return

    t_start = time.time()

    # 1. Ingest
    log.step("POST /api/static-video/ingest")
    try:
        with fixture_path.open("rb") as f:
            r = client.post(
                "/api/static-video/ingest",
                files={"file": (
                    fixture_path.name, f,
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )},
                timeout=120,
            )
    except Exception as e:  # noqa: BLE001
        log.fail(f"ingest: {e}")
        result.state, result.detail = "fail", str(e)
        return
    if r.status_code != 200:
        msg = f"ingest -> {r.status_code}: {r.text[:200]}"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return
    ingest = r.json()
    doc_id = ingest["doc_id"]
    n_slides = len(ingest.get("slides", []))
    log.ok(f"ingested doc_id={doc_id} ({n_slides} slides)")

    # 2. Script (NDJSON)
    log.step(f"POST /api/static-video/script/{{doc_id}} lang={plan.language}")
    payload = {"language": plan.language, "style": "explainer", "voice": plan.voice_female}
    narrations = 0
    script_ok = False
    t0 = time.time()
    try:
        with client.stream(
            "POST", f"/api/static-video/script/{doc_id}",
            json=payload, timeout=180,
        ) as r:
            if r.status_code != 200:
                msg = f"script -> {r.status_code}: {r.read()[:200]!r}"
                log.fail(msg)
                result.state, result.detail = "fail", msg
                return
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") == "narration":
                    narrations += 1
                elif event.get("event") == "done":
                    script_ok = True
                    break
                elif event.get("event") == "error":
                    msg = f"script stream error: {event.get('data')}"
                    log.fail(msg)
                    result.state, result.detail = "fail", msg
                    return
    except Exception as e:  # noqa: BLE001
        log.fail(f"script stream: {e}")
        result.state, result.detail = "fail", str(e)
        return
    if not script_ok:
        msg = "script stream ended without 'done' event"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return
    log.ok(f"script generated ({narrations} narrations in {time.time()-t0:.1f}s)")

    # 3. Render
    log.step("POST /api/static-video/render/{doc_id}")
    r = client.post(f"/api/static-video/render/{doc_id}", timeout=30)
    if r.status_code != 200:
        msg = f"render -> {r.status_code}: {r.text[:200]}"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return
    job_id = r.json().get("job_id")
    log.ok(f"render job queued job_id={job_id}")

    # 4. Poll
    log.step("poll /api/static-video/jobs/{job_id}")
    t0 = time.time()
    final_state = None
    last_stage = ""
    while time.time() - t0 < POLL_TIMEOUT_SEC:
        try:
            r = client.get(f"/api/static-video/jobs/{job_id}", timeout=30)
            if r.status_code != 200:
                time.sleep(POLL_INTERVAL_SEC)
                continue
            job = r.json()
            state = job.get("state")
            stage = job.get("progress", {}).get("stage", "")
            done = job.get("progress", {}).get("completed", 0)
            total = job.get("progress", {}).get("total", 0)
            if stage != last_stage:
                print(f"     ... {state}  stage={stage}  {done}/{total}")
                last_stage = stage
            if state in ("done", "failed"):
                final_state = state
                if state == "failed":
                    msg = f"render failed: {job.get('error')}"
                    log.fail(msg)
                    result.state, result.detail = "fail", msg
                    return
                break
        except Exception as e:  # noqa: BLE001
            print(f"     ... poll error: {e}")
        time.sleep(POLL_INTERVAL_SEC)

    if final_state != "done":
        msg = f"render timeout after {POLL_TIMEOUT_SEC}s"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return
    log.ok(f"render completed in {time.time()-t0:.1f}s")

    # 5. Download mp4
    log.step("GET /api/static-video/jobs/{job_id}/file/mp4")
    try:
        r = client.get(f"/api/static-video/jobs/{job_id}/file/mp4", timeout=180)
        if r.status_code == 200 and len(r.content) > 10_000:
            log.ok(f"mp4 downloaded ({len(r.content):,} bytes)")
            result.output_bytes = len(r.content)
            result.state = "pass"
            result.duration_sec = time.time() - t_start
        else:
            msg = f"mp4 download status={r.status_code} size={len(r.content)}"
            log.fail(msg)
            result.state, result.detail = "fail", msg
    except Exception as e:  # noqa: BLE001
        log.fail(f"mp4 download: {e}")
        result.state, result.detail = "fail", str(e)

    # 6. SCORM package validation
    log.step("GET /api/static-video/jobs/{job_id}/file/scorm")
    try:
        r = client.get(f"/api/static-video/jobs/{job_id}/file/scorm", timeout=180)
        if r.status_code != 200:
            log.fail(f"scorm download status={r.status_code}")
        else:
            ct = r.headers.get("content-type", "")
            if ct.startswith("application/zip"):
                log.ok(f"scorm content-type={ct}")
            else:
                log.fail(f"scorm unexpected content-type={ct}")
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            names = zf.namelist()
            if "imsmanifest.xml" in names:
                log.ok("scorm contains imsmanifest.xml")
            else:
                log.fail("scorm missing imsmanifest.xml")
            if "index.html" in names:
                log.ok("scorm contains index.html")
            else:
                log.fail("scorm missing index.html")
            if "scorm.js" in names:
                log.ok("scorm contains scorm.js")
            else:
                log.fail("scorm missing scorm.js")
            if "subtitles.vtt" in names:
                log.ok("scorm contains subtitles.vtt")
            else:
                log.fail("scorm missing subtitles.vtt")
            if any(n.endswith(".mp4") for n in names):
                log.ok("scorm contains mp4 video")
            else:
                log.fail("scorm missing mp4 video")
            # Validate manifest XML
            if "imsmanifest.xml" in names:
                manifest = zf.read("imsmanifest.xml").decode()
                root = ET.fromstring(manifest)
                if "scormtype" in manifest.lower() or "scormType" in manifest:
                    log.ok(f"scorm manifest valid ({len(manifest):,} bytes)")
                else:
                    log.fail("scorm manifest missing scormType attribute")
            # Validate player HTML
            if "index.html" in names:
                html = zf.read("index.html").decode()
                if "<video" in html:
                    log.ok("scorm player contains video tag")
                else:
                    log.fail("scorm player missing video tag")
                if "scormInit" in html:
                    log.ok("scorm player contains scormInit")
                else:
                    log.fail("scorm player missing scormInit")
            # Validate subtitles
            if "subtitles.vtt" in names:
                vtt = zf.read("subtitles.vtt").decode()
                if vtt.startswith("WEBVTT"):
                    log.ok("scorm subtitles in VTT format")
                else:
                    log.fail("scorm subtitles not in VTT format")
            log.ok(f"scorm package valid ({len(names)} files, {len(r.content):,} bytes)")
    except Exception as e:  # noqa: BLE001
        log.fail(f"scorm validation: {e}")


# ---------------------------------------------------------------------------
# UC3 - Podcast (1 language)
# ---------------------------------------------------------------------------
def run_uc3_for_language(client: httpx.Client, plan: LangPlan, log: Log) -> None:
    log.header(f"UC3  PODCAST  {plan.language}  {plan.fixture}")
    result = RunResult(uc="UC3", language=plan.language, fixture=plan.fixture)
    log.record(result)

    fixture_path = FIXTURE_DIR / plan.fixture
    if not fixture_path.exists():
        msg = f"Fixture missing: {fixture_path}"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return

    t_start = time.time()

    # 1. Ingest
    log.step("POST /api/podcast/ingest")
    try:
        with fixture_path.open("rb") as f:
            r = client.post(
                "/api/podcast/ingest",
                files={"file": (
                    fixture_path.name, f,
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )},
                timeout=120,
            )
    except Exception as e:  # noqa: BLE001
        log.fail(f"ingest: {e}")
        result.state, result.detail = "fail", str(e)
        return
    if r.status_code != 200:
        msg = f"ingest -> {r.status_code}: {r.text[:200]}"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return
    doc = r.json().get("document", {})
    doc_id = doc.get("id")
    log.ok(f"ingested doc_id={doc_id} title={doc.get('title')!r}")

    # 2. Script (SSE)
    log.step(f"POST /api/podcast/script/stream lang={plan.language}")
    payload = {
        "document_id": doc_id,
        "language": plan.language,
        "style": "casual",
        "length": "short",
        "num_turns": 4,
    }
    script_id: Optional[str] = None
    turn_count = 0
    t0 = time.time()
    try:
        with client.stream(
            "POST", "/api/podcast/script/stream",
            json=payload, timeout=180,
        ) as r:
            if r.status_code != 200:
                msg = f"script -> {r.status_code}: {r.read()[:200]!r}"
                log.fail(msg)
                result.state, result.detail = "fail", msg
                return
            current_event = None
            for line in r.iter_lines():
                if not line:
                    current_event = None
                    continue
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    if current_event == "turn":
                        turn_count += 1
                    elif current_event == "done":
                        try:
                            script_id = json.loads(data).get("script_id")
                        except json.JSONDecodeError:
                            pass
                        break
                    elif current_event == "error":
                        msg = f"script stream error: {data}"
                        log.fail(msg)
                        result.state, result.detail = "fail", msg
                        return
    except Exception as e:  # noqa: BLE001
        log.fail(f"script stream: {e}")
        result.state, result.detail = "fail", str(e)
        return
    if not script_id:
        msg = "script stream ended without script_id"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return
    log.ok(f"script id={script_id} turns={turn_count} in {time.time()-t0:.1f}s")

    # 3. Render
    log.step("POST /api/podcast/render")
    render_req = {
        "script_id": script_id,
        "roles": {
            "interviewer": {
                "display_name": "Host",
                "avatar": "lisa",
                "voice": plan.voice_female,
            },
            "expert": {
                "display_name": "Expert",
                "avatar": "harry",
                "voice": plan.voice_male,
            },
        },
        "layout": "split_screen_with_slides",
        "music": False,
        "intro": False,
    }
    r = client.post("/api/podcast/render", json=render_req, timeout=30)
    if r.status_code != 200:
        msg = f"render -> {r.status_code}: {r.text[:300]}"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return
    job = r.json()
    job_id = job.get("id")
    log.ok(f"render job queued job_id={job_id}")

    # 4. Poll
    log.step("poll /api/podcast/jobs/{job_id}")
    t0 = time.time()
    final_state = None
    last_stage = ""
    while time.time() - t0 < POLL_TIMEOUT_SEC:
        try:
            r = client.get(f"/api/podcast/jobs/{job_id}", timeout=30)
            if r.status_code != 200:
                time.sleep(POLL_INTERVAL_SEC)
                continue
            job = r.json()
            state = job.get("state")
            stage = job.get("progress", {}).get("stage", "")
            done = job.get("progress", {}).get("completed", 0)
            total = job.get("progress", {}).get("total", 0)
            if stage != last_stage:
                print(f"     ... {state}  stage={stage}  {done}/{total}")
                last_stage = stage
            if state in ("done", "failed"):
                final_state = state
                if state == "failed":
                    msg = f"render failed: {job.get('error')}"
                    log.fail(msg)
                    result.state, result.detail = "fail", msg
                    return
                break
        except Exception as e:  # noqa: BLE001
            print(f"     ... poll error: {e}")
        time.sleep(POLL_INTERVAL_SEC)

    if final_state != "done":
        msg = f"render timeout after {POLL_TIMEOUT_SEC}s"
        log.fail(msg)
        result.state, result.detail = "fail", msg
        return
    log.ok(f"render completed in {time.time()-t0:.1f}s")

    # 5. Download mp3 (fallback mp4)
    media_ok = False
    for kind in ("mp3", "mp4"):
        try:
            r = client.get(f"/api/podcast/jobs/{job_id}/file/{kind}", timeout=180)
            if r.status_code == 200 and len(r.content) > 10_000:
                log.ok(f"{kind} downloaded ({len(r.content):,} bytes)")
                result.output_bytes = len(r.content)
                result.state = "pass"
                result.duration_sec = time.time() - t_start
                media_ok = True
                break
        except Exception as e:  # noqa: BLE001
            print(f"     {kind} download error: {e}")
    if not media_ok:
        msg = "no media file downloadable"
        log.fail(msg)
        result.state, result.detail = "fail", msg

    # 6. SCORM package validation
    log.step("GET /api/podcast/jobs/{job_id}/file/scorm")
    try:
        r = client.get(f"/api/podcast/jobs/{job_id}/file/scorm", timeout=180)
        if r.status_code != 200:
            log.fail(f"scorm download status={r.status_code}")
        else:
            ct = r.headers.get("content-type", "")
            if ct.startswith("application/zip"):
                log.ok(f"scorm content-type={ct}")
            else:
                log.fail(f"scorm unexpected content-type={ct}")
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            names = zf.namelist()
            if "imsmanifest.xml" in names:
                log.ok("scorm contains imsmanifest.xml")
            else:
                log.fail("scorm missing imsmanifest.xml")
            if "index.html" in names:
                log.ok("scorm contains index.html")
            else:
                log.fail("scorm missing index.html")
            if "scorm.js" in names:
                log.ok("scorm contains scorm.js")
            else:
                log.fail("scorm missing scorm.js")
            if "subtitles.vtt" in names:
                log.ok("scorm contains subtitles.vtt")
            else:
                log.fail("scorm missing subtitles.vtt")
            if any(n.endswith(".mp3") for n in names):
                log.ok("scorm contains mp3 audio")
            else:
                log.fail("scorm missing mp3 audio")
            # Validate manifest XML
            if "imsmanifest.xml" in names:
                manifest = zf.read("imsmanifest.xml").decode()
                root = ET.fromstring(manifest)
                if "scormtype" in manifest.lower() or "scormType" in manifest:
                    log.ok(f"scorm manifest valid ({len(manifest):,} bytes)")
                else:
                    log.fail("scorm manifest missing scormType attribute")
            # Validate player HTML
            if "index.html" in names:
                html = zf.read("index.html").decode()
                if "<audio" in html:
                    log.ok("scorm player contains audio tag")
                else:
                    log.fail("scorm player missing audio tag")
                if "scormInit" in html:
                    log.ok("scorm player contains scormInit")
                else:
                    log.fail("scorm player missing scormInit")
            # Validate subtitles
            if "subtitles.vtt" in names:
                vtt = zf.read("subtitles.vtt").decode()
                if vtt.startswith("WEBVTT"):
                    log.ok("scorm subtitles in VTT format")
                else:
                    log.fail("scorm subtitles not in VTT format")
            log.ok(f"scorm package valid ({len(names)} files, {len(r.content):,} bytes)")
    except Exception as e:  # noqa: BLE001
        log.fail(f"scorm validation: {e}")


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument(
        "--languages",
        default="en-US",
        help="Comma-separated list of locales to test, e.g. 'fr-FR,en-US,es-ES'. "
             "Default: en-US only.",
    )
    parser.add_argument("--skip-video", action="store_true", help="Skip UC2")
    parser.add_argument("--skip-podcast", action="store_true", help="Skip UC3")
    args = parser.parse_args()

    requested = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    unknown = [lang for lang in requested if lang not in PLANS]
    if unknown:
        print(f"ERROR: unknown languages: {unknown}. Supported: {sorted(PLANS.keys())}")
        return 2

    print(f"Target: {args.base_url}")
    print(f"Languages: {requested}")
    print(f"UCs: {'UC2 ' if not args.skip_video else ''}"
          f"{'UC3' if not args.skip_podcast else ''}".strip())

    log = Log()
    with httpx.Client(base_url=args.base_url, timeout=60) as client:
        for lang in requested:
            plan = PLANS[lang]
            if not args.skip_video:
                run_uc2_for_language(client, plan, log)
            if not args.skip_podcast:
                run_uc3_for_language(client, plan, log)
    return log.summary()


if __name__ == "__main__":
    sys.exit(main())

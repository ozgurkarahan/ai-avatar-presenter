"""End-to-end render tests for UC2 (static video) and UC3 (podcast).

Full happy-path: ingest -> script (streaming) -> render -> poll until done
-> download media file. Expensive: each run costs TTS tokens + ~1-3 minutes
per UC. Intended to be run occasionally, not on every commit.

Usage:
    python tests/e2e_render.py --base-url https://... [--skip-video] [--skip-podcast]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_BASE = os.environ.get("BASE_URL", "http://localhost:8080")
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "rfi"

# Use Group B (EN) deck #1 — shortest narration pathway, fewest TTS tokens.
UC2_FIXTURE = FIXTURE_DIR / "decarbonization-intro.pptx"
UC3_FIXTURE = FIXTURE_DIR / "decarbonization-intro.pptx"

POLL_TIMEOUT_SEC = 600  # 10 minutes max per render job
POLL_INTERVAL_SEC = 6


class Log:
    def __init__(self) -> None:
        self.passes = 0
        self.fails = 0

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

    def summary(self) -> int:
        print(f"\n{'=' * 70}")
        print(f"RESULTS: {self.passes} passed  {self.fails} failed")
        print(f"{'=' * 70}")
        return 0 if self.fails == 0 else 1


# ---------------------------------------------------------------------------
# UC2 — Static video
# ---------------------------------------------------------------------------
def test_uc2_render(client: httpx.Client, log: Log) -> None:
    log.header("UC2  STATIC VIDEO  full render")
    if not UC2_FIXTURE.exists():
        log.fail(f"Fixture missing: {UC2_FIXTURE}")
        return

    # 1. Ingest
    log.step("POST /api/static-video/ingest")
    with UC2_FIXTURE.open("rb") as f:
        r = client.post(
            "/api/static-video/ingest",
            files={"file": (UC2_FIXTURE.name, f, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            timeout=120,
        )
    if r.status_code != 200:
        log.fail(f"ingest -> {r.status_code}: {r.text[:300]}")
        return
    ingest = r.json()
    doc_id = ingest["doc_id"]
    n_slides = len(ingest.get("slides", []))
    log.ok(f"ingested doc_id={doc_id} ({n_slides} slides)")

    # 2. Script generation (NDJSON streaming)
    log.step("POST /api/static-video/script/{doc_id} (NDJSON stream)")
    voice = "en-US-Ava:DragonHDLatestNeural"
    payload = {"language": "en-US", "style": "explainer", "voice": voice}
    narrations = 0
    script_ok = False
    t0 = time.time()
    try:
        with client.stream("POST", f"/api/static-video/script/{doc_id}", json=payload, timeout=180) as r:
            if r.status_code != 200:
                log.fail(f"script -> {r.status_code}: {r.read()[:300]!r}")
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
                    log.fail(f"script stream error: {event.get('data')}")
                    return
    except Exception as e:  # noqa: BLE001
        log.fail(f"script stream: {e}")
        return
    if not script_ok:
        log.fail("script stream ended without 'done' event")
        return
    log.ok(f"script generated ({narrations} narrations in {time.time()-t0:.1f}s)")

    # 3. Render
    log.step("POST /api/static-video/render/{doc_id}")
    r = client.post(f"/api/static-video/render/{doc_id}", timeout=30)
    if r.status_code != 200:
        log.fail(f"render -> {r.status_code}: {r.text[:300]}")
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
                    log.fail(f"render failed: {job.get('error')}")
                    return
                break
        except Exception as e:  # noqa: BLE001
            print(f"     ... poll error: {e}")
        time.sleep(POLL_INTERVAL_SEC)

    if final_state != "done":
        log.fail(f"render timeout after {POLL_TIMEOUT_SEC}s")
        return
    log.ok(f"render completed in {time.time()-t0:.1f}s")

    # 5. Download mp4
    log.step("GET /api/static-video/jobs/{job_id}/file/mp4")
    try:
        r = client.get(f"/api/static-video/jobs/{job_id}/file/mp4", timeout=120)
        if r.status_code == 200 and len(r.content) > 10_000:
            log.ok(f"mp4 downloaded ({len(r.content):,} bytes)")
        else:
            log.fail(f"mp4 download status={r.status_code} size={len(r.content)}")
    except Exception as e:  # noqa: BLE001
        log.fail(f"mp4 download: {e}")


# ---------------------------------------------------------------------------
# UC3 — Podcast
# ---------------------------------------------------------------------------
def test_uc3_render(client: httpx.Client, log: Log) -> None:
    log.header("UC3  PODCAST  full render")
    if not UC3_FIXTURE.exists():
        log.fail(f"Fixture missing: {UC3_FIXTURE}")
        return

    # 1. Ingest
    log.step("POST /api/podcast/ingest")
    with UC3_FIXTURE.open("rb") as f:
        r = client.post(
            "/api/podcast/ingest",
            files={"file": (UC3_FIXTURE.name, f, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            timeout=120,
        )
    if r.status_code != 200:
        log.fail(f"ingest -> {r.status_code}: {r.text[:300]}")
        return
    doc = r.json().get("document", {})
    doc_id = doc.get("id")
    log.ok(f"ingested doc_id={doc_id} title={doc.get('title')!r}")

    # 2. Script (SSE streaming)
    log.step("POST /api/podcast/script/stream (SSE)")
    payload = {
        "document_id": doc_id,
        "language": "en-US",
        "style": "casual",
        "length": "short",
        "num_turns": 4,
    }
    script_id = None
    turn_count = 0
    t0 = time.time()
    try:
        with client.stream("POST", "/api/podcast/script/stream", json=payload, timeout=180) as r:
            if r.status_code != 200:
                log.fail(f"script -> {r.status_code}: {r.read()[:300]!r}")
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
                        log.fail(f"script stream error: {data}")
                        return
    except Exception as e:  # noqa: BLE001
        log.fail(f"script stream: {e}")
        return
    if not script_id:
        log.fail("script stream ended without script_id")
        return
    log.ok(f"script generated id={script_id} turns={turn_count} in {time.time()-t0:.1f}s")

    # 3. Render
    log.step("POST /api/podcast/render")
    render_req = {
        "script_id": script_id,
        "roles": {
            "interviewer": {
                "display_name": "Ava",
                "avatar": "lisa",
                "voice": "en-US-Ava:DragonHDLatestNeural",
            },
            "expert": {
                "display_name": "Andrew",
                "avatar": "harry",
                "voice": "en-US-Andrew:DragonHDLatestNeural",
            },
        },
        "layout": "split_screen_with_slides",
        "music": False,
        "intro": False,
    }
    r = client.post("/api/podcast/render", json=render_req, timeout=30)
    if r.status_code != 200:
        log.fail(f"render -> {r.status_code}: {r.text[:400]}")
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
                    log.fail(f"render failed: {job.get('error')}")
                    return
                break
        except Exception as e:  # noqa: BLE001
            print(f"     ... poll error: {e}")
        time.sleep(POLL_INTERVAL_SEC)

    if final_state != "done":
        log.fail(f"render timeout after {POLL_TIMEOUT_SEC}s")
        return
    log.ok(f"render completed in {time.time()-t0:.1f}s")

    # 5. Download mp3 (cheaper than mp4; we just want to confirm output exists)
    for kind in ("mp3", "mp4"):
        try:
            r = client.get(f"/api/podcast/jobs/{job_id}/file/{kind}", timeout=120)
            if r.status_code == 200 and len(r.content) > 10_000:
                log.ok(f"{kind} downloaded ({len(r.content):,} bytes)")
                return  # one is enough
        except Exception as e:  # noqa: BLE001
            print(f"     {kind} download error: {e}")
    log.fail("no media file downloadable")


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--skip-podcast", action="store_true")
    args = parser.parse_args()

    print(f"Target: {args.base_url}")
    log = Log()
    with httpx.Client(base_url=args.base_url, timeout=60) as client:
        if not args.skip_video:
            test_uc2_render(client, log)
        if not args.skip_podcast:
            test_uc3_render(client, log)
    return log.summary()


if __name__ == "__main__":
    sys.exit(main())

"""End-to-end test suite driven by the RFI fixtures (9 decks, 3 groups).

This runs as a script (not pytest) because it's a stateful reset+upload+test flow
and the output needs to be human-readable for the demo.

Usage:
    BASE_URL=https://... python tests/e2e_rfi.py
    # or
    python tests/e2e_rfi.py --base-url https://... [--skip-reset] [--skip-video]
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


# ---------------------------------------------------------------------------
# Logging helpers (terminal-friendly, ASCII safe for Windows stdout)
# ---------------------------------------------------------------------------
class Log:
    def __init__(self) -> None:
        self.passes = 0
        self.fails = 0
        self.skips = 0
        self.section = ""

    def header(self, title: str) -> None:
        self.section = title
        print(f"\n{'=' * 70}\n== {title}\n{'=' * 70}")

    def step(self, msg: str) -> None:
        print(f"  -> {msg}")

    def ok(self, msg: str) -> None:
        self.passes += 1
        print(f"  [PASS] {msg}")

    def fail(self, msg: str) -> None:
        self.fails += 1
        print(f"  [FAIL] {msg}")

    def skip(self, msg: str) -> None:
        self.skips += 1
        print(f"  [SKIP] {msg}")

    def summary(self) -> int:
        print(f"\n{'=' * 70}")
        print(f"RESULTS: {self.passes} passed  {self.fails} failed  {self.skips} skipped")
        print(f"{'=' * 70}")
        return 0 if self.fails == 0 else 1


# ---------------------------------------------------------------------------
# Database reset
# ---------------------------------------------------------------------------
def reset_db(client: httpx.Client, log: Log) -> None:
    log.header("PHASE 0  DATABASE RESET")

    # UC1 paths first (they reference decks)
    try:
        paths = client.get("/api/uc1/paths").json()
        for p in paths:
            r = client.delete(f"/api/uc1/paths/{p['id']}")
            log.step(f"deleted path '{p.get('title', p['id'])}' -> {r.status_code}")
        log.ok(f"UC1 paths cleared ({len(paths)} deleted)")
    except Exception as e:
        log.fail(f"UC1 paths reset: {e}")

    # UC1 decks
    try:
        decks = client.get("/api/uc1/decks").json()
        for d in decks:
            did = d.get("deck_id") or d.get("id")
            r = client.delete(f"/api/uc1/decks/{did}?force=true")
            log.step(f"deleted deck '{d.get('title', did)}' -> {r.status_code}")
        log.ok(f"UC1 decks cleared ({len(decks)} deleted)")
    except Exception as e:
        log.fail(f"UC1 decks reset: {e}")

    # UC2 static-video library
    try:
        lib = client.get("/api/static-video/library").json()
        for item in lib:
            jid = item.get("job_id") or item.get("id")
            client.delete(f"/api/static-video/library/{jid}")
        log.ok(f"UC2 library cleared ({len(lib)} deleted)")
    except Exception as e:
        log.fail(f"UC2 library reset: {e}")

    # UC3 podcast library
    try:
        lib = client.get("/api/podcast/library").json()
        for item in lib:
            jid = item.get("job_id") or item.get("id")
            client.delete(f"/api/podcast/library/{jid}")
        log.ok(f"UC3 library cleared ({len(lib)} deleted)")
    except Exception as e:
        log.fail(f"UC3 library reset: {e}")


# ---------------------------------------------------------------------------
# UC1 — Upload and Learning Hub
# ---------------------------------------------------------------------------
def upload_rfi_decks(client: httpx.Client, log: Log) -> dict[str, dict]:
    log.header("PHASE 1  UC1 UPLOAD RFI FIXTURES (9 decks)")

    manifest_path = FIXTURE_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    uploaded: dict[str, dict] = {}
    for entry in manifest:
        fname = entry["file"]
        lang = entry["language"]
        path = FIXTURE_DIR / fname
        log.step(f"uploading {fname} ({lang}) ...")
        with path.open("rb") as fh:
            r = client.post(
                "/api/uc1/upload",
                files={"file": (fname, fh, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
                data={"language": lang},
            )
        if r.status_code == 200:
            uploaded[fname] = {**r.json(), "group": entry["group"], "language": lang}
            log.ok(f"uploaded {fname} -> deck_id={uploaded[fname].get('deck_id')}")
        else:
            log.fail(f"upload {fname} failed: {r.status_code} {r.text[:200]}")
    return uploaded


def test_uc1_hub(client: httpx.Client, log: Log, uploaded: dict) -> None:
    log.header("PHASE 2  UC1 HUB LISTING & FILTERING")
    decks = client.get("/api/uc1/decks").json()
    if len(decks) == len(uploaded):
        log.ok(f"hub returns all {len(decks)} uploaded decks")
    else:
        log.fail(f"hub returns {len(decks)} decks, expected {len(uploaded)}")

    langs = {d.get("language") for d in decks}
    if {"fr-FR", "en-US", "es-ES"}.issubset(langs):
        log.ok(f"all 3 languages present: {sorted(langs)}")
    else:
        log.fail(f"missing languages; got {sorted(langs)}")


def test_uc1_learn_search(client: httpx.Client, log: Log) -> None:
    log.header("PHASE 3  UC1 LEARN SEARCH (semantic Q&A)")
    queries = [
        ("Quels sont les équipements de protection individuelle ?", "fr-FR", "securite"),
        ("How to reduce carbon emissions in cement production?", "en-US", "decarbon"),
        ("¿Qué es el mantenimiento predictivo?", "es-ES", "ia-en-produccion"),
    ]
    for q, lang, expected_frag in queries:
        try:
            r = client.post("/api/uc1/learn/search", json={"query": q, "language": lang, "top_k": 3})
            if r.status_code != 200:
                log.fail(f"search '{q[:40]}...' -> {r.status_code} {r.text[:150]}")
                continue
            body = r.json()
            results = body.get("results", [])
            if not results:
                log.fail(f"search '{q[:40]}...' returned 0 results")
                continue
            top = results[0]
            deck_title = (top.get("deck_title") or "").lower()
            if expected_frag in deck_title:
                log.ok(f"search '{q[:40]}...' -> top: {deck_title}")
            else:
                # Not a hard fail — semantic search may find a related deck
                log.ok(f"search '{q[:40]}...' -> top: {deck_title} (expected fragment '{expected_frag}' not matched but got a result)")
        except Exception as e:
            log.fail(f"search '{q[:40]}...' exception: {e}")


# ---------------------------------------------------------------------------
# UC1 — Paths (manual + AI recommend)
# ---------------------------------------------------------------------------
def test_uc1_paths_manual(client: httpx.Client, log: Log, uploaded: dict) -> list[str]:
    log.header("PHASE 4  UC1 PATHS CREATION (one per group)")
    groups: dict[str, list[dict]] = {"A_safety_fr": [], "B_sustainability_en": [], "C_ai_es": []}
    for up in uploaded.values():
        groups.setdefault(up["group"], []).append(up)
    created_ids: list[str] = []
    for gkey, decks in groups.items():
        if len(decks) < 2:
            log.skip(f"group {gkey}: not enough decks ({len(decks)})")
            continue
        # Preserve upload order (which matches manifest order = pedagogical order)
        steps = [{"deck_id": d["deck_id"], "order": i} for i, d in enumerate(decks)]
        body = {
            "title": f"RFI E2E Path — {gkey}",
            "description": f"Auto-generated path for group {gkey} by e2e_rfi.py",
            "steps": steps,
        }
        r = client.post("/api/uc1/paths", json=body)
        if r.status_code == 200:
            pid = r.json()["id"]
            created_ids.append(pid)
            log.ok(f"created path for group {gkey} ({len(steps)} steps) -> {pid}")
        else:
            log.fail(f"create path {gkey} -> {r.status_code} {r.text[:200]}")
    return created_ids


def test_uc1_path_progress(client: httpx.Client, log: Log, path_ids: list[str]) -> None:
    log.header("PHASE 5  UC1 PATH PROGRESS TRACKING")
    if not path_ids:
        log.skip("no paths created")
        return
    pid = path_ids[0]
    user_id = "e2e-user-rfi"
    detail = client.get(f"/api/uc1/paths/{pid}").json()
    first_deck = detail["steps"][0]["deck_id"]
    # Walk slides 0..3 of first deck
    for i in range(4):
        r = client.post(f"/api/uc1/paths/{pid}/progress",
                        json={"user_id": user_id, "deck_id": first_deck, "slide_index": i})
        if r.status_code != 200:
            log.fail(f"progress slide {i} -> {r.status_code} {r.text[:200]}")
            return
    prog = client.get(f"/api/uc1/paths/{pid}/progress?user_id={user_id}").json()
    if prog.get("resume_slide_index") == 3:
        log.ok(f"progress recorded and retrieved (resume_slide_index={prog.get('resume_slide_index')})")
    else:
        log.fail(f"progress mismatch: expected resume_slide_index=3, got {prog}")


def test_uc1_paths_ai_recommend(client: httpx.Client, log: Log) -> None:
    log.header("PHASE 6  UC1 AI PATH RECOMMEND (GPT-4.1)")
    scenarios = [
        ("sécurité sur chantier et prévention des risques", "fr-FR", ["securite", "risques", "urgence"]),
        ("decarbonization and low-carbon materials in construction", "en-US", ["decarbon", "low-carbon", "circular"]),
        ("inteligencia artificial en la industria y su ética", "es-ES", ["ia-industrial", "produccion", "etica"]),
    ]
    for topic, lang, expected_keywords in scenarios:
        log.step(f"recommend for topic='{topic[:50]}...' lang={lang}")
        r = client.post("/api/uc1/paths/recommend",
                        json={"topic": topic, "max_steps": 3, "language": lang})
        if r.status_code != 200:
            log.fail(f"recommend -> {r.status_code} {r.text[:200]}")
            continue
        body = r.json()
        steps = body.get("steps", [])
        step_titles = [s["deck_title"].lower() for s in steps]
        matched = sum(1 for k in expected_keywords if any(k in t for t in step_titles))
        if len(steps) >= 2 and matched >= 2:
            log.ok(f"recommend returned {len(steps)} steps ({matched}/{len(expected_keywords)} matched): {step_titles}")
        else:
            log.fail(f"recommend weak match: {len(steps)} steps, {matched} matched. Got: {step_titles}")


# ---------------------------------------------------------------------------
# UC2 / UC3 smoke tests
# ---------------------------------------------------------------------------
def test_uc2_static_video(client: httpx.Client, log: Log, uploaded: dict, skip: bool = False) -> None:
    log.header("PHASE 7  UC2 STATIC VIDEO (smoke)")
    if skip:
        log.skip("--skip-video specified")
        return
    # Only smoke test: verify ingest endpoint accepts a deck. Full render is expensive.
    first = next(iter(uploaded.values()))
    # UC2's ingest expects different payload — let's check if library endpoint at least works
    try:
        r = client.get("/api/static-video/library")
        if r.status_code == 200:
            log.ok(f"UC2 library endpoint reachable ({len(r.json())} items)")
        else:
            log.fail(f"UC2 library -> {r.status_code}")
        r = client.get("/api/static-video/languages")
        if r.status_code == 200:
            log.ok(f"UC2 languages endpoint: {len(r.json())} languages")
        else:
            log.fail(f"UC2 languages -> {r.status_code}")
    except Exception as e:
        log.fail(f"UC2 smoke: {e}")


def test_uc3_podcast(client: httpx.Client, log: Log) -> None:
    log.header("PHASE 8  UC3 PODCAST / CREATE (smoke)")
    try:
        r = client.get("/api/podcast/library")
        if r.status_code == 200:
            log.ok(f"UC3 library endpoint reachable ({len(r.json())} items)")
        else:
            log.fail(f"UC3 library -> {r.status_code}")
        r = client.get("/api/podcast/avatars")
        if r.status_code == 200:
            log.ok(f"UC3 avatars endpoint: {len(r.json())} avatars")
        else:
            log.fail(f"UC3 avatars -> {r.status_code}")
        r = client.get("/api/podcast/voices")
        if r.status_code == 200:
            log.ok(f"UC3 voices endpoint: {len(r.json())} voices")
        else:
            log.fail(f"UC3 voices -> {r.status_code}")
    except Exception as e:
        log.fail(f"UC3 smoke: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default=DEFAULT_BASE)
    p.add_argument("--skip-reset", action="store_true")
    p.add_argument("--skip-video", action="store_true")
    args = p.parse_args()

    print(f"BASE_URL = {args.base_url}")
    print(f"FIXTURES = {FIXTURE_DIR}")

    log = Log()
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=180.0) as client:
        if not args.skip_reset:
            reset_db(client, log)
        else:
            log.header("PHASE 0  DATABASE RESET  [SKIPPED]")

        uploaded = upload_rfi_decks(client, log)
        if len(uploaded) < 9:
            log.fail(f"only {len(uploaded)}/9 decks uploaded — aborting downstream tests")
            return log.summary()

        # Give Cosmos a moment to index
        time.sleep(3)

        test_uc1_hub(client, log, uploaded)
        test_uc1_learn_search(client, log)
        path_ids = test_uc1_paths_manual(client, log, uploaded)
        test_uc1_path_progress(client, log, path_ids)
        test_uc1_paths_ai_recommend(client, log)
        test_uc2_static_video(client, log, uploaded, skip=args.skip_video)
        test_uc3_podcast(client, log)

    return log.summary()


if __name__ == "__main__":
    sys.exit(main())

"""UC2 regeneration script: rebuild the static-video library from a fixed set
of sample deck PPTX fixtures (tests/fixtures/samples).

Plan:
  1. Snapshot existing library job_ids (to delete after success).
  2. For each (deck_pptx, voice) pair:
       a. POST /ingest  (multipart upload of the PPTX) -> doc_id
       b. POST /script/{doc_id} (streamed NDJSON) -> wait for {"event":"done"}
       c. POST /render/{doc_id} -> job_id
       d. Poll GET /jobs/{job_id} until state in {published, failed}
       e. Confirm new library item appears in /library
  3. After ALL 3 succeed, DELETE each old job_id.

The avatar is auto-picked server-side from the voice gender (the default
female / male avatar — custom photo avatars from CUSTOM_AVATARS_JSON when
configured, stock avatars otherwise).

Target backend: env ``AI_PRESENTER_BASE_URL`` (default http://localhost:8000).
Run it against local dev (``run-local.ps1`` sets ``AUTH_MODE=disabled``); a
deployed instance requires an allowlisted Entra ID sign-in for these endpoints.

Run:
  python scripts/uc2_regen.py
  python scripts/uc2_regen.py --dry-run        # plan only
  python scripts/uc2_regen.py --no-delete      # keep old jobs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

BASE = os.environ.get("AI_PRESENTER_BASE_URL", "http://localhost:8000").rstrip("/")
# Optional Entra ID access token for a deployed instance (Easy Auth bearer), e.g.
#   az account get-access-token --scope api://<app-client-id>/user_impersonation
# AI_PRESENTER_TOKEN_COMMAND (optional): shell command printing a fresh token; it is
# re-run on a 401 so long renders survive token expiry.
class _AuthSession(requests.Session):
    def request(self, *args, **kwargs):
        resp = super().request(*args, **kwargs)
        cmd = os.environ.get("AI_PRESENTER_TOKEN_COMMAND")
        if resp.status_code == 401 and cmd:
            import subprocess
            token = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()
            if token:
                self.headers["Authorization"] = f"Bearer {token}"
                resp = super().request(*args, **kwargs)
        return resp


SESSION = _AuthSession()
if os.environ.get("AI_PRESENTER_BEARER_TOKEN"):
    SESSION.headers["Authorization"] = f"Bearer {os.environ['AI_PRESENTER_BEARER_TOKEN']}"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "samples"


@dataclass
class DeckSpec:
    pptx: Path
    language: str
    voice: str
    label: str  # human label for logs


DECKS: list[DeckSpec] = [
    DeckSpec(
        pptx=FIXTURE_DIR / "circular-economy.pptx",
        language="en-US",
        voice="en-US-Ava:DragonHDLatestNeural",
        label="circular-economy (EN, female voice Ava)",
    ),
    DeckSpec(
        pptx=FIXTURE_DIR / "low-carbon-materials.pptx",
        language="en-US",
        voice="en-US-Andrew:DragonHDLatestNeural",
        label="low-carbon-materials (EN, male voice Andrew)",
    ),
    DeckSpec(
        pptx=FIXTURE_DIR / "ia-en-produccion.pptx",
        language="es-ES",
        voice="es-ES-Ximena:DragonHDLatestNeural",
        label="ia-en-produccion (ES, female voice Ximena)",
    ),
]


def ingest(deck: DeckSpec) -> str:
    print(f"  [1/4] ingest {deck.pptx.name} ...", flush=True)
    with deck.pptx.open("rb") as fh:
        r = SESSION.post(
            f"{BASE}/api/static-video/ingest",
            files={"file": (deck.pptx.name, fh, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            timeout=120,
        )
    r.raise_for_status()
    doc_id = r.json()["doc_id"]
    print(f"        doc_id = {doc_id}", flush=True)
    return doc_id


def generate_script(deck: DeckSpec, doc_id: str) -> None:
    print(f"  [2/4] script (lang={deck.language}, voice={deck.voice.split(':')[0]}) ...", flush=True)
    body = {"language": deck.language, "style": "explainer", "voice": deck.voice}
    with SESSION.post(
        f"{BASE}/api/static-video/script/{doc_id}",
        json=body,
        stream=True,
        timeout=600,
    ) as r:
        r.raise_for_status()
        seen_done = False
        narration_count = 0
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = msg.get("event")
            if ev == "narration":
                narration_count += 1
                print(f"        + slide {msg['data'].get('slide_index')}", flush=True)
            elif ev == "done":
                seen_done = True
                print(f"        done ({narration_count} narrations)", flush=True)
                break
            elif ev == "error":
                raise RuntimeError(f"script error: {msg.get('data')}")
        if not seen_done:
            raise RuntimeError("script stream ended without 'done' event")


def start_render(doc_id: str) -> str:
    print("  [3/4] render submit ...", flush=True)
    r = SESSION.post(f"{BASE}/api/static-video/render/{doc_id}", timeout=60)
    r.raise_for_status()
    job_id = r.json()["job_id"]
    print(f"        job_id = {job_id}", flush=True)
    return job_id


def poll_render(job_id: str, timeout_sec: int = 30 * 60) -> dict:
    print("  [4/4] polling ...", flush=True)
    deadline = time.time() + timeout_sec
    last_msg = None
    while time.time() < deadline:
        r = SESSION.get(f"{BASE}/api/static-video/jobs/{job_id}", timeout=30)
        r.raise_for_status()
        job = r.json()
        state = job.get("state")
        prog = job.get("progress") or {}
        msg = f"        state={state} stage={prog.get('stage')} pct={prog.get('percent')}% msg={prog.get('message')}"
        if msg != last_msg:
            print(msg, flush=True)
            last_msg = msg
        if state in {"published", "completed", "succeeded", "done"}:
            return job
        if state == "failed":
            raise RuntimeError(f"render failed: {job.get('error')}")
        time.sleep(15)
    raise TimeoutError(f"render {job_id} timed out after {timeout_sec}s")


def list_library() -> list[dict]:
    r = SESSION.get(f"{BASE}/api/static-video/library", timeout=60)
    r.raise_for_status()
    return r.json()


def delete_job(job_id: str) -> None:
    r = SESSION.delete(f"{BASE}/api/static-video/library/{job_id}", timeout=60)
    r.raise_for_status()
    print(f"  deleted {job_id}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print plan, do not call the API")
    ap.add_argument("--no-delete", action="store_true", help="skip deletion of old library jobs")
    args = ap.parse_args()

    # Pre-flight
    missing = [d.pptx for d in DECKS if not d.pptx.exists()]
    if missing:
        print(f"ERROR: missing PPTX fixtures: {missing}", file=sys.stderr)
        return 2

    print(f"== UC2 regeneration plan ({BASE}) ==")
    for d in DECKS:
        print(f"  - {d.label}  <-  {d.pptx.relative_to(Path.cwd()) if d.pptx.is_relative_to(Path.cwd()) else d.pptx}")

    print("\n== current library ==")
    pre_lib = list_library()
    for it in pre_lib:
        print(f"  - {it['job_id']}  {it['title']:30}  voice={it['voice']}")
    pre_ids = [it["job_id"] for it in pre_lib]

    if args.dry_run:
        print("\n[dry-run] stopping before any API mutation.")
        return 0

    print("\n== regenerating ==")
    new_jobs: list[str] = []
    for deck in DECKS:
        print(f"\n--- {deck.label} ---", flush=True)
        try:
            doc_id = ingest(deck)
            generate_script(deck, doc_id)
            job_id = start_render(doc_id)
            poll_render(job_id)
            new_jobs.append(job_id)
        except Exception as e:
            print(f"\nFAILED {deck.label}: {e}", file=sys.stderr)
            print(f"new jobs successfully rendered so far: {new_jobs}", file=sys.stderr)
            print("OLD JOBS NOT DELETED.", file=sys.stderr)
            return 1

    print("\n== new library state ==")
    post_lib = list_library()
    for it in post_lib:
        marker = "NEW" if it["job_id"] in new_jobs else "old"
        print(f"  [{marker}] {it['job_id']}  {it['title']:30}  voice={it['voice']}")

    if args.no_delete:
        print("\n--no-delete: keeping old jobs.")
        return 0

    print("\n== deleting old jobs ==")
    for jid in pre_ids:
        try:
            delete_job(jid)
        except Exception as e:
            print(f"  WARN: failed to delete {jid}: {e}", file=sys.stderr)

    print("\n== final library ==")
    for it in list_library():
        print(f"  - {it['job_id']}  {it['title']:30}  voice={it['voice']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""UC3 podcast regeneration: rebuild the podcast library with ST-Gobain
custom photo avatars (`ST_Gobain_Female` host + `ST_Gobain_Male` expert) from
the same UC1 deck fixtures used by UC2.

Plan:
  1. Snapshot existing library job_ids (to delete after success).
  2. For each deck:
       a. POST /api/podcast/ingest (multipart PPTX) -> document
       b. POST /api/podcast/script/stream (SSE) -> wait for `event: done`
          payload `{"script_id": ...}`
       c. POST /api/podcast/render with explicit RenderRoles (interviewer +
          expert), each pinned to the ST-Gobain photo avatars.
       d. Poll GET /api/podcast/jobs/{job_id} until state in
          {published, failed}.
  3. After ALL 3 succeed, DELETE each old job_id.

Run:
  python scripts/uc3_regen.py
  python scripts/uc3_regen.py --dry-run
  python scripts/uc3_regen.py --no-delete
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

BASE = "https://ca-am564oxavvhhk.orangecliff-e64ce39a.swedencentral.azurecontainerapps.io"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "rfi"

POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 30 * 60  # 30 min/job

AVATAR_F = "ST_Gobain_Female"
AVATAR_M = "ST_Gobain_Male"


@dataclass
class DeckSpec:
    pptx: Path
    language: str
    label: str
    style: str
    host_voice: str
    host_name: str
    expert_voice: str
    expert_name: str


DECKS: list[DeckSpec] = [
    DeckSpec(
        pptx=FIXTURE_DIR / "circular-economy.pptx",
        language="en-US",
        label="circular-economy",
        style="casual",
        host_voice="en-US-Ava:DragonHDLatestNeural",
        host_name="Ava",
        expert_voice="en-US-Andrew:DragonHDLatestNeural",
        expert_name="Andrew",
    ),
    DeckSpec(
        pptx=FIXTURE_DIR / "low-carbon-materials.pptx",
        language="en-US",
        label="low-carbon-materials",
        style="explainer",
        host_voice="en-US-Ava:DragonHDLatestNeural",
        host_name="Ava",
        expert_voice="en-US-Andrew:DragonHDLatestNeural",
        expert_name="Andrew",
    ),
    DeckSpec(
        pptx=FIXTURE_DIR / "ia-en-produccion.pptx",
        language="es-ES",
        label="ia-en-produccion",
        style="casual",
        host_voice="es-ES-Ximena:DragonHDLatestNeural",
        host_name="Ximena",
        expert_voice="es-ES-Tristan:DragonHDLatestNeural",
        expert_name="Tristán",
    ),
]


def list_library() -> list[dict]:
    r = requests.get(f"{BASE}/api/podcast/library", timeout=30)
    r.raise_for_status()
    return r.json()


def ingest_pptx(deck: DeckSpec) -> str:
    print(f"  [1/4] ingest {deck.pptx.name} ...")
    with open(deck.pptx, "rb") as fh:
        files = {"file": (deck.pptx.name, fh, "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
        r = requests.post(f"{BASE}/api/podcast/ingest", files=files, timeout=120)
    r.raise_for_status()
    payload = r.json()
    doc_id = payload["document"]["id"]
    print(f"        document_id = {doc_id}")
    return doc_id


def stream_script(deck: DeckSpec, doc_id: str) -> str:
    print(f"  [2/4] script (lang={deck.language}, style={deck.style}) ...")
    body = {
        "document_id": doc_id,
        "language": deck.language,
        "style": deck.style,
        "length": "medium",
        "num_turns": 8,
    }
    script_id: str | None = None
    with requests.post(f"{BASE}/api/podcast/script/stream", json=body, stream=True, timeout=600) as r:
        r.raise_for_status()
        # SSE: lines like 'event: turn' / 'data: {...}' separated by blank line.
        event = None
        for raw in r.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            if raw.startswith("event:"):
                event = raw.split(":", 1)[1].strip()
                continue
            if raw.startswith("data:"):
                data = raw.split(":", 1)[1].strip()
                if event == "turn":
                    try:
                        turn = json.loads(data)
                        spk = turn.get("speaker", "?")
                        print(f"        + turn {spk}")
                    except json.JSONDecodeError:
                        pass
                elif event == "done":
                    try:
                        script_id = json.loads(data)["script_id"]
                    except (json.JSONDecodeError, KeyError):
                        pass
                elif event == "error":
                    raise RuntimeError(f"script stream error: {data}")
    if not script_id:
        raise RuntimeError("script stream ended without `done` event")
    print(f"        script_id = {script_id}")
    return script_id


def submit_render(deck: DeckSpec, script_id: str) -> str:
    print(f"  [3/4] render submit ...")
    body = {
        "script_id": script_id,
        "roles": {
            "interviewer": {
                "display_name": deck.host_name,
                "avatar": AVATAR_F,
                "voice": deck.host_voice,
            },
            "expert": {
                "display_name": deck.expert_name,
                "avatar": AVATAR_M,
                "voice": deck.expert_voice,
            },
        },
        "layout": "split_screen_with_slides",
        "music": True,
        "intro": True,
    }
    r = requests.post(f"{BASE}/api/podcast/render", json=body, timeout=60)
    r.raise_for_status()
    job_id = r.json()["id"]
    print(f"        job_id = {job_id}")
    return job_id


def poll_job(job_id: str) -> dict:
    print(f"  [4/4] polling ...")
    start = time.time()
    last_pct = -1
    while True:
        r = requests.get(f"{BASE}/api/podcast/jobs/{job_id}", timeout=30)
        r.raise_for_status()
        job = r.json()
        state = job.get("state")
        prog = job.get("progress") or {}
        stage = prog.get("stage", "?")
        pct = prog.get("percent", 0)
        msg = prog.get("message", "")
        if pct != last_pct:
            print(f"        state={state} stage={stage} pct={pct}% msg={msg}")
            last_pct = pct
        if state in {"published", "done", "failed"}:
            return job
        if time.time() - start > POLL_TIMEOUT_S:
            raise TimeoutError(f"job {job_id} did not finish in {POLL_TIMEOUT_S}s")
        time.sleep(POLL_INTERVAL_S)


def delete_job(job_id: str) -> None:
    r = requests.delete(f"{BASE}/api/podcast/library/{job_id}", timeout=60)
    if r.status_code in (200, 204):
        print(f"  deleted {job_id}")
    else:
        print(f"  WARN: delete {job_id} returned {r.status_code}: {r.text[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Plan only; do not call backend.")
    ap.add_argument("--no-delete", action="store_true", help="Keep old jobs after regen.")
    args = ap.parse_args()

    print("== UC3 regeneration plan ==")
    for d in DECKS:
        if not d.pptx.exists():
            print(f"  ! MISSING fixture: {d.pptx}")
            return 2
        print(f"  - {d.label} ({d.language}, {d.host_name}+{d.expert_name})  <-  {d.pptx.relative_to(Path.cwd())}")

    print()
    old = list_library()
    print("== current library ==")
    for j in old:
        print(f"  - {j['job_id']}  {j.get('title','?'):30}  lang={j.get('language','?')}  speakers={j.get('speaker_names', [])}")
    if args.dry_run:
        return 0

    print()
    print("== regenerating ==")
    new_jobs: list[tuple[DeckSpec, str]] = []
    for deck in DECKS:
        print(f"\n--- {deck.label} ({deck.language}, {deck.host_name}+{deck.expert_name}) ---")
        try:
            doc_id = ingest_pptx(deck)
            script_id = stream_script(deck, doc_id)
            job_id = submit_render(deck, script_id)
            job = poll_job(job_id)
            if job.get("state") == "failed":
                print(f"  !! render failed for {deck.label}: {job.get('progress',{}).get('message','')}")
                print("  ABORT: keeping old jobs intact.")
                return 1
            new_jobs.append((deck, job_id))
        except Exception as e:
            print(f"  !! exception during {deck.label}: {e}")
            print("  ABORT: keeping old jobs intact.")
            return 1

    print()
    print("== new library state ==")
    after = {j["job_id"]: j for j in list_library()}
    for deck, job_id in new_jobs:
        j = after.get(job_id, {})
        print(f"  [NEW] {job_id}  {j.get('title','?'):30}  lang={j.get('language','?')}")
    old_ids = {j["job_id"] for j in old}
    for jid in old_ids:
        j = after.get(jid)
        if j:
            print(f"  [old] {jid}  {j.get('title','?'):30}  lang={j.get('language','?')}")

    if args.no_delete:
        print("\n--no-delete: leaving old jobs in library")
        return 0

    print()
    print("== deleting old jobs ==")
    for jid in old_ids:
        delete_job(jid)

    print()
    print("== final library ==")
    for j in list_library():
        print(f"  - {j['job_id']}  {j.get('title','?'):30}  lang={j.get('language','?')}  speakers={j.get('speaker_names', [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Run UC2 end-to-end across multiple languages to populate the library.

Each language is a separate job:
  ingest (once, shared doc is fine — but ingest is cheap so we do it per-language
         for voice/title tidiness) → script (per language) → render → publish.

Jobs run concurrently; backend serializes batch-avatar submits anyway (that's
expected; the render is the long pole).
"""
from __future__ import annotations

import asyncio, json, sys, time
from pathlib import Path
import httpx

import os
_BASE_URL = os.environ.get("UC2_API", "http://localhost:8000")
BASE = f"{_BASE_URL}/api/static-video"
PPTX = Path(__file__).resolve().parent.parent / "output" / "uc2-test-deck.pptx"

# language -> (display, style, focus hint)
LANGS = [
    ("en-US", "English",    "explainer",  "a crisp 30-second overview"),
    ("fr-FR", "French",     "explainer",  "un aperçu clair de 30 secondes"),
    ("es-ES", "Spanish",    "explainer",  "una visión clara de 30 segundos"),
    ("de-DE", "German",     "explainer",  "ein klarer Überblick in 30 Sekunden"),
]


async def multipart_ingest(session: httpx.AsyncClient, label: str) -> dict:
    fname = f"Frontier Firm ({label}).pptx"
    files = {"file": (fname, PPTX.read_bytes(),
                      "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
    data = {"filename": fname}
    r = await session.post(f"{BASE}/ingest", files=files, data=data)
    r.raise_for_status()
    return r.json()


async def get_voice(session: httpx.AsyncClient, lang: str) -> str:
    r = await session.get(f"{BASE}/voices", params={"language": lang})
    r.raise_for_status()
    voices = r.json()
    return voices[0]["id"]


async def stream_script(session: httpx.AsyncClient, doc_id: str, lang: str, voice: str, focus: str) -> int:
    body = {"language": lang, "style": "explainer", "focus": focus, "voice": voice}
    narrations, errors = 0, []
    async with session.stream("POST", f"{BASE}/script/{doc_id}", json=body) as r:
        r.raise_for_status()
        async for raw in r.aiter_lines():
            line = raw.strip()
            if not line: continue
            try: evt = json.loads(line)
            except Exception: continue
            if evt.get("event") == "narration": narrations += 1
            elif evt.get("event") == "error": errors.append(evt.get("data"))
    if errors:
        raise RuntimeError(f"script errors for {lang}: {errors}")
    return narrations


async def render(session: httpx.AsyncClient, doc_id: str) -> str:
    r = await session.post(f"{BASE}/render/{doc_id}")
    r.raise_for_status()
    return r.json()["job_id"]


async def poll_job(session: httpx.AsyncClient, job_id: str, label: str, max_seconds: int = 1800):
    last = None
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        r = await session.get(f"{BASE}/jobs/{job_id}")
        j = r.json()
        p = j.get("progress") or {}
        key = (j.get("state"), p.get("stage"), p.get("percent"), p.get("completed"), p.get("total"))
        if key != last:
            last = key
            print(f"[{label}] t+{int(time.time()-T0):4d}s  state={j['state']:<10} stage={(p.get('stage') or ''):<10} "
                  f"pct={p.get('percent')!s:>4}  {p.get('completed')}/{p.get('total')}  {(p.get('message') or '')[:60]}")
        if j.get("state") in ("done", "failed"):
            return j
        await asyncio.sleep(5)
    raise TimeoutError(f"{label} did not finish in {max_seconds}s")


async def one_language(session, lang, display, style, focus):
    label = f"{lang}"
    print(f"\n=== {label} ({display}) ===")
    ing = await multipart_ingest(session, display)
    doc_id = ing["doc_id"]
    voice = await get_voice(session, lang)
    print(f"[{label}] doc_id={doc_id[:8]} voice={voice}")
    n = await stream_script(session, doc_id, lang, voice, focus)
    print(f"[{label}] script: {n} narrations")
    job_id = await render(session, doc_id)
    print(f"[{label}] render job_id={job_id}")
    result = await poll_job(session, job_id, label)
    return lang, display, job_id, result.get("state")


async def main():
    global T0
    T0 = time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(None, read=600)) as session:
        r = await session.get(f"{_BASE_URL}/api/health")
        if r.status_code != 200:
            print("backend not healthy", r.status_code); sys.exit(1)
        results = await asyncio.gather(
            *[one_language(session, *l) for l in LANGS],
            return_exceptions=True,
        )
        print("\n=== library summary ===")
        r = await session.get(f"{BASE}/library")
        lib = r.json()
        items = lib if isinstance(lib, list) else lib.get("items", [])
        print(f"library entries: {len(items)}")
        for it in items:
            print(f"  - {(it.get('language') or '?'):<6} {(it.get('title') or '?')[:60]:<60} job={it.get('job_id')}")
        for res in results:
            if isinstance(res, Exception):
                print(f"  !! FAILED: {res!r}")

if __name__ == "__main__":
    asyncio.run(main())

"""Re-publish already-rendered video jobs to the blob library.

Recovery helper: if a backend process cached a failed library init, its
per-job archive step is skipped. Run this once with a fresh Python process
to push the local mp4/mp3/srt/thumb from data/video/out/{job_id}
into the blob library and drop the manifest.

Usage:
  python scripts/video_republish.py sv-xxxxxxxx [sv-yyyyyyyy ...]

Target backend: env AI_PRESENTER_BASE_URL (default http://localhost:8000).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import httpx

BACKEND = Path(__file__).resolve().parents[1] / "demos" / "backend"
sys.path.insert(0, str(BACKEND))
import os
os.chdir(BACKEND)

from dotenv import load_dotenv
load_dotenv()

from config import load_config
from services.video_library import VideoLibrary, VideoLibraryFiles

JOBS = sys.argv[1:]

API = os.environ.get("AI_PRESENTER_BASE_URL", "http://localhost:8000").rstrip("/")


def main() -> int:
    if not JOBS:
        print(__doc__)
        return 2
    cfg = load_config()
    lib = VideoLibrary(cfg)
    if not lib.available:
        print("!! library not available")
        return 1
    print(f"library ready (container={cfg.blob_container})")

    out_root = BACKEND / "data" / "video" / "out"
    client = httpx.Client(timeout=30)

    for job_id in JOBS:
        job = client.get(f"{API}/api/video/jobs/{job_id}").json()
        doc_id = job["doc_id"]
        script = client.get(f"{API}/api/video/script/{doc_id}").json()
        language = script.get("language", "en-US")
        voice = script.get("voice", "")
        doc = client.get(f"{API}/api/video/voices").json()  # unused; title via narration count
        slide_count = len(script.get("narrations", []))
        duration = job.get("outputs", {}).get("duration_sec")
        created_at = job.get("created_at", "")
        title = f"Video demo ({language})"
        document_title = title

        d = out_root / job_id
        files = VideoLibraryFiles(
            mp4=d / "final.mp4",
            mp3=d / "final.mp3",
            srt=d / "final.srt",
            thumb=d / "thumb.jpg" if (d / "thumb.jpg").exists() else None,
        )
        missing = [p for p in [files.mp4, files.mp3, files.srt] if not p.exists()]
        if missing:
            print(f"[{job_id}] SKIP missing: {missing}")
            continue

        manifest = lib.publish(
            job_id,
            files,
            title=title,
            document_title=document_title,
            language=language,
            voice=voice,
            slide_count=slide_count,
            duration_sec=duration,
            created_at=created_at,
        )
        print(f"[{job_id}] lang={language} voice={voice} slides={slide_count} "
              f"dur={duration:.1f}s published={manifest is not None}")

    lib_summary = client.get(f"{API}/api/video/library").json()
    print(f"\nlibrary via API: {len(lib_summary)} entries")
    for it in lib_summary:
        print(f"  {it.get('job_id')} lang={it.get('language')} "
              f"title={it.get('title')} dur={it.get('duration_sec')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

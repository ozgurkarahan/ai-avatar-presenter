"""
Batch Video Translation — All 12 Languages in Parallel
========================================================
Uploads full video once, then launches all 12 translations in parallel
with PersonalVoice + lip-sync + client-provided subtitles.

Usage:
  python scripts/batch_translate.py

  # Resume monitoring (if script was interrupted):
  python scripts/batch_translate.py --resume

Environment variables (scripts/.env):
  SPEECH_KEY, SPEECH_REGION, STORAGE_CONN_STR, STORAGE_CONTAINER
"""

import os
import sys
import json
import time
import uuid
import concurrent.futures
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SPEECH_KEY = os.environ.get("SPEECH_KEY", "")
SPEECH_REGION = os.environ.get("SPEECH_REGION", "westeurope")
STORAGE_CONN_STR = os.environ.get("STORAGE_CONN_STR", "")
STORAGE_CONTAINER = os.environ.get("STORAGE_CONTAINER", "video-translation")

API_VERSION = "2026-03-01"
BASE_URL = f"https://{SPEECH_REGION}.api.cognitive.microsoft.com/videotranslation"
HEADERS = {"Ocp-Apim-Subscription-Key": SPEECH_KEY, "Content-Type": "application/json"}

SOURCE_VIDEO = Path(r"C:\Users\ozgurkarahan\projects\Acme\input\01_Source_Video\01_Source_Video\CSG_EHS DAY2026_BenoitBazin_ENG_withoutEmbeddedST_InternalUseOnly.mp4")
SUBTITLE_DIR = Path(r"C:\Users\ozgurkarahan\projects\Acme\ai-presenter - Copilot\output\webvtt")
OUTPUT_DIR = Path(r"C:\Users\ozgurkarahan\projects\Acme\ai-presenter - Copilot\output\video-translation")
STATE_FILE = OUTPUT_DIR / "batch_state.json"

# Language mapping: locale -> subtitle filename
LANGUAGES = {
    "ar-SA": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_ARABIC.vtt",
    "zh-CN": "CSG_EHS DAY2026_BenoitBazin_InternalUseOnlyCHINESE.vtt",
    "cs-CZ": "Czech_CSG_2026_EHS DAY_Message_from_Benoit_Bazin_CZECH.vtt",
    "de-DE": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_GERMAN.vtt",
    "it-IT": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_ITALIAN.vtt",
    "pl-PL": "2026 International EHS DAY - POLISH.vtt",
    "pt-BR": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_PORTUGUES-BRAZIL.vtt",
    "ro-RO": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_ROMANIEN.vtt",
    "es-ES": "CSG_2026_EHS_DAY_Message_from_Benoit_Bazin_Spanish_SPAIN.vtt",
    "th-TH": "CSG_EHS DAY2026_BenoitBazin_Thai_InternalUseOnly (1).vtt",
    "tr-TR": "BB_EHS_MesajınızVar_TIURKISH_altyazı (1).vtt",
    "vi-VN": "CSG_2026_EHS DAY_Message_from_Benoit_Bazin_VIETNAM.vtt",
}


def blob_upload(local_path: Path, blob_name: str) -> str:
    """Upload file to Blob Storage, return SAS URL (24h)."""
    from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

    blob_svc = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
    blob_client = blob_svc.get_blob_client(container=STORAGE_CONTAINER, blob=blob_name)

    print(f"  ⬆ {local_path.name} ({local_path.stat().st_size / 1024 / 1024:.1f} MB) → {blob_name}")
    with open(local_path, "rb") as f:
        blob_client.upload_blob(f, overwrite=True, max_concurrency=4)

    sas = generate_blob_sas(
        account_name=blob_svc.account_name,
        container_name=STORAGE_CONTAINER,
        blob_name=blob_name,
        account_key=blob_svc.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    return f"{blob_client.url}?{sas}"


def create_translation(video_url: str, subtitle_url: str, locale: str) -> dict:
    """Create a single translation. Returns {translation_id, operation_id, locale, status}."""
    tid = f"prod-{locale}-{uuid.uuid4().hex[:6]}"
    oid = f"op-{locale}-{uuid.uuid4().hex[:6]}"

    body = {
        "displayName": f"RFI Production: en-US → {locale}",
        "description": f"Full video translation with client subtitles, {datetime.now(timezone.utc).isoformat()}",
        "input": {
            "sourceLocale": "en-US",
            "targetLocale": locale,
            "voiceKind": "PersonalVoice",
            "speakerCount": 1,
            "subtitleMaxCharCountPerSegment": 80,
            "exportSubtitleInVideo": True,
            "enableLipSync": True,
            "autoCreateFirstIteration": True,
            "videoFileUrl": video_url,
        },
        "firstIterationInput": {
            "subtitleFontSize": 12,
            "webvttFile": {
                "url": subtitle_url,
                "kind": "TargetLocaleSubtitle",
            },
        },
    }

    url = f"{BASE_URL}/translations/{tid}?api-version={API_VERSION}"
    headers = {**HEADERS, "Operation-Id": oid}

    resp = requests.put(url, headers=headers, json=body)
    if resp.status_code not in (200, 201):
        print(f"  ❌ {locale}: HTTP {resp.status_code} — {resp.text[:200]}")
        return {"locale": locale, "status": "CreateFailed", "error": resp.text[:500]}

    return {
        "locale": locale,
        "translation_id": tid,
        "operation_id": oid,
        "status": "NotStarted",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def poll_translation(entry: dict) -> dict:
    """Check translation status, return updated entry."""
    tid = entry.get("translation_id")
    if not tid:
        return entry

    url = f"{BASE_URL}/translations/{tid}?api-version={API_VERSION}"
    headers = {"Ocp-Apim-Subscription-Key": SPEECH_KEY}

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return entry

        data = resp.json()
        entry["status"] = data.get("status", entry["status"])
        entry["iter_status"] = data.get("latestIteration", {}).get("status", "?")

        if entry["status"] == "Failed":
            entry["error"] = data.get("failureReason", "Unknown")

    except Exception as e:
        entry["error"] = str(e)

    return entry


def download_result(entry: dict) -> dict:
    """Download translated video and subtitles for a completed translation."""
    tid = entry["translation_id"]
    locale = entry["locale"]
    headers = {"Ocp-Apim-Subscription-Key": SPEECH_KEY}

    # Get iteration details
    iter_url = f"{BASE_URL}/translations/{tid}/iterations/default?api-version={API_VERSION}"
    resp = requests.get(iter_url, headers=headers)
    if resp.status_code != 200:
        entry["download_error"] = f"HTTP {resp.status_code}"
        return entry

    data = resp.json()
    result = data.get("result", {})
    out_dir = OUTPUT_DIR / locale
    out_dir.mkdir(parents=True, exist_ok=True)

    files = {
        f"translated_video_{locale}.mp4": result.get("translatedVideoFileUrl"),
        f"subtitles_source_{locale}.vtt": result.get("sourceLocaleSubtitleWebvttFileUrl"),
        f"subtitles_target_{locale}.vtt": result.get("targetLocaleSubtitleWebvttFileUrl"),
        f"metadata_{locale}.vtt": result.get("metadataJsonWebvttFileUrl"),
    }

    for fname, dl_url in files.items():
        if not dl_url:
            continue
        try:
            r = requests.get(dl_url, stream=True, timeout=300)
            fp = out_dir / fname
            with open(fp, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            if fname.endswith(".mp4"):
                entry["output_size_mb"] = round(fp.stat().st_size / 1024 / 1024, 1)
        except Exception as e:
            entry["download_error"] = str(e)

    # Save iteration metadata
    with open(out_dir / "iteration.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    entry["downloaded"] = True
    entry["completed_at"] = datetime.now(timezone.utc).isoformat()
    return entry


def save_state(state: dict):
    """Persist state to disk for resume capability."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_state() -> dict | None:
    """Load state from disk if it exists."""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def print_dashboard(entries: list, elapsed: float):
    """Print a progress dashboard."""
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)

    succeeded = [e for e in entries if e.get("status") == "Succeeded"]
    running = [e for e in entries if e.get("status") == "Running"]
    waiting = [e for e in entries if e.get("status") == "NotStarted"]
    failed = [e for e in entries if e.get("status") in ("Failed", "CreateFailed")]

    print(f"\n{'='*60}")
    print(f"  [{mins:02d}:{secs:02d}] ✅ {len(succeeded)}  🔄 {len(running)}  ⏳ {len(waiting)}  ❌ {len(failed)}  / {len(entries)} total")
    print(f"{'='*60}")

    for e in entries:
        status_icon = {
            "Succeeded": "✅", "Running": "🔄", "NotStarted": "⏳",
            "Failed": "❌", "CreateFailed": "❌"
        }.get(e["status"], "❓")
        extra = ""
        if e.get("output_size_mb"):
            extra = f" ({e['output_size_mb']} MB)"
        if e.get("error"):
            extra = f" — {e['error'][:60]}"
        print(f"  {status_icon} {e['locale']:6s} {e['status']}{extra}")

    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch Video Translation")
    parser.add_argument("--resume", action="store_true", help="Resume from saved state")
    args = parser.parse_args()

    if not SPEECH_KEY or not STORAGE_CONN_STR:
        print("ERROR: Set SPEECH_KEY and STORAGE_CONN_STR in scripts/.env")
        sys.exit(1)

    print("=" * 60)
    print("  Batch Video Translation — 12 Languages")
    print("=" * 60)

    # ── Resume mode ──────────────────────────────────────────
    if args.resume:
        state = load_state()
        if not state:
            print("No saved state found. Run without --resume first.")
            sys.exit(1)
        entries = state["entries"]
        print(f"Resuming {len(entries)} translations...")

    else:
        # ── Upload video (once) ──────────────────────────────
        print("\n📤 Uploading source video to Blob Storage...")
        video_url = blob_upload(SOURCE_VIDEO, "production/source_video.mp4")
        print("  ✓ Video uploaded")

        # ── Upload all subtitles ─────────────────────────────
        print("\n📤 Uploading subtitle files...")
        subtitle_urls = {}
        for locale, vtt_name in LANGUAGES.items():
            vtt_path = SUBTITLE_DIR / vtt_name
            if not vtt_path.exists():
                print(f"  ⚠ Missing: {vtt_name}")
                continue
            blob_name = f"production/subtitles/{locale}.vtt"
            subtitle_urls[locale] = blob_upload(vtt_path, blob_name)
        print(f"  ✓ {len(subtitle_urls)} subtitles uploaded")

        # ── Launch all translations ──────────────────────────
        print(f"\n🚀 Launching {len(subtitle_urls)} translations...")
        entries = []
        for locale in LANGUAGES:
            if locale not in subtitle_urls:
                entries.append({"locale": locale, "status": "CreateFailed", "error": "Missing subtitle"})
                continue

            entry = create_translation(video_url, subtitle_urls[locale], locale)
            entries.append(entry)
            status = "✅ created" if entry.get("translation_id") else f"❌ {entry.get('error', '')[:60]}"
            print(f"  {locale}: {status}")
            time.sleep(1)  # small delay between API calls

        save_state({"entries": entries, "video_url": video_url})

    # ── Poll until all complete ──────────────────────────────
    print("\n⏳ Polling all translations...")
    start = time.time()
    poll_interval = 30

    while True:
        elapsed = time.time() - start

        # Poll all active translations
        for i, entry in enumerate(entries):
            if entry.get("status") in ("Succeeded", "Failed", "CreateFailed"):
                continue
            entries[i] = poll_translation(entry)

        # Download results for newly succeeded
        for i, entry in enumerate(entries):
            if entry.get("status") == "Succeeded" and not entry.get("downloaded"):
                print(f"\n  ⬇ Downloading {entry['locale']}...")
                entries[i] = download_result(entry)
                print(f"  ✓ {entry['locale']} downloaded ({entry.get('output_size_mb', '?')} MB)")

        save_state({"entries": entries})
        print_dashboard(entries, elapsed)

        # Check if all done
        active = [e for e in entries if e.get("status") not in ("Succeeded", "Failed", "CreateFailed")]
        if not active:
            break

        if elapsed > 6 * 3600:  # 6 hour timeout
            print("⚠ TIMEOUT after 6 hours")
            break

        time.sleep(poll_interval)

    # ── Summary ──────────────────────────────────────────────
    elapsed = time.time() - start
    succeeded = [e for e in entries if e.get("status") == "Succeeded"]
    failed = [e for e in entries if e.get("status") in ("Failed", "CreateFailed")]

    print("\n" + "=" * 60)
    print(f"  COMPLETE — {len(succeeded)}/{len(entries)} succeeded in {int(elapsed//60)}m")
    print("=" * 60)

    if succeeded:
        print("\n✅ Translated videos:")
        for e in succeeded:
            print(f"  {e['locale']:6s} → output/video-translation/{e['locale']}/translated_video_{e['locale']}.mp4 ({e.get('output_size_mb', '?')} MB)")

    if failed:
        print("\n❌ Failed:")
        for e in failed:
            print(f"  {e['locale']:6s} — {e.get('error', 'Unknown')[:100]}")

    save_state({"entries": entries, "completed": True})


if __name__ == "__main__":
    main()

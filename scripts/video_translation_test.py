"""
Video Translation Feasibility Test — Azure AI Speech Video Translation API
===========================================================================
Translates video with lip-sync and voice cloning using Azure Speech Video Translation.
Supports providing client subtitle files (SRT/WebVTT) as target-language text.

Usage:
  # Auto-translate (no subtitle file):
  python scripts/video_translation_test.py --video clip.mp4 --target-locale de-DE

  # With client subtitle (uses their exact text for TTS):
  python scripts/video_translation_test.py --video clip.mp4 --subtitle german.vtt --target-locale de-DE

  # Convert SRT to WebVTT first:
  python scripts/convert_srt.py input.srt output.vtt

Notes:
  - Subtitle must be WebVTT format (.vtt), not SRT. Use convert_srt.py to convert.
  - Lip-sync requires PersonalVoice (auto-selected when lip-sync is enabled).
  - The API uses the subtitle text as-is for TTS synthesis (kind=TargetLocaleSubtitle).

Environment variables (or .env file in scripts/):
  SPEECH_KEY          - Azure Speech resource key
  SPEECH_REGION       - Azure Speech resource region (e.g. westeurope)
  STORAGE_CONN_STR    - Azure Blob Storage connection string
  STORAGE_CONTAINER   - Blob container name (default: video-translation)
"""

import os
import sys
import json
import time
import uuid
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests

# ---------------------------------------------------------------------------
# Optional: load .env
# ---------------------------------------------------------------------------
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

HEADERS = {
    "Ocp-Apim-Subscription-Key": SPEECH_KEY,
    "Content-Type": "application/json",
}

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "video-translation"


def blob_upload(local_path: Path, blob_name: str) -> str:
    """Upload a file to Azure Blob Storage and return a SAS URL (read, 24h)."""
    from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

    blob_service = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
    blob_client = blob_service.get_blob_client(container=STORAGE_CONTAINER, blob=blob_name)

    print(f"  Uploading {local_path.name} → {STORAGE_CONTAINER}/{blob_name} ...")
    with open(local_path, "rb") as f:
        blob_client.upload_blob(f, overwrite=True)

    sas_token = generate_blob_sas(
        account_name=blob_service.account_name,
        container_name=STORAGE_CONTAINER,
        blob_name=blob_name,
        account_key=blob_service.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    sas_url = f"{blob_client.url}?{sas_token}"
    print(f"  SAS URL ready (24h expiry)")
    return sas_url


def create_translation(video_url: str, subtitle_url: str | None,
                       source_locale: str, target_locale: str,
                       enable_lip_sync: bool = True) -> tuple[str, str]:
    """Create a translation with auto-first-iteration. Returns (translation_id, operation_id)."""
    translation_id = f"test-{target_locale}-{uuid.uuid4().hex[:8]}"
    operation_id = f"op-{uuid.uuid4().hex[:8]}"

    # Lip-sync requires PersonalVoice
    voice_kind = "PersonalVoice" if enable_lip_sync else "PlatformVoice"

    body = {
        "displayName": f"Feasibility test: {source_locale} → {target_locale}",
        "description": f"60s clip lip-sync test, {datetime.now(timezone.utc).isoformat()}",
        "input": {
            "sourceLocale": source_locale,
            "targetLocale": target_locale,
            "voiceKind": voice_kind,
            "speakerCount": 1,
            "subtitleMaxCharCountPerSegment": 80,
            "exportSubtitleInVideo": True,
            "enableLipSync": enable_lip_sync,
            "autoCreateFirstIteration": True,
            "videoFileUrl": video_url,
        },
        "firstIterationInput": {
            "subtitleFontSize": 12,
        },
    }

    # If a target-language subtitle file is provided, pass it as TargetLocaleSubtitle
    if subtitle_url:
        body["firstIterationInput"]["webvttFile"] = {
            "url": subtitle_url,
            "kind": "TargetLocaleSubtitle",
        }

    url = f"{BASE_URL}/translations/{translation_id}?api-version={API_VERSION}"
    headers = {**HEADERS, "Operation-Id": operation_id}

    print(f"\n[1/4] Creating translation: {translation_id}")
    print(f"  Lip-sync: {enable_lip_sync}")
    print(f"  Source: {source_locale} → Target: {target_locale}")

    resp = requests.put(url, headers=headers, json=body)
    if resp.status_code not in (200, 201):
        print(f"  ERROR: {resp.status_code} — {resp.text}")
        sys.exit(1)

    data = resp.json()
    print(f"  Status: {data.get('status')}")
    print(f"  Expires: {data.get('expiresDateTime', 'N/A')}")
    return translation_id, operation_id


def poll_operation(operation_id: str, timeout_minutes: int = 30) -> str:
    """Poll operation status until Succeeded or Failed. Returns final status."""
    url = f"{BASE_URL}/operations/{operation_id}?api-version={API_VERSION}"
    start = time.time()
    poll_interval = 15  # seconds

    print(f"\n[2/4] Polling operation {operation_id} (timeout: {timeout_minutes}min)...")

    while True:
        elapsed = time.time() - start
        if elapsed > timeout_minutes * 60:
            print(f"  TIMEOUT after {timeout_minutes} minutes")
            return "Timeout"

        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"  Poll error: {resp.status_code} — {resp.text}")
            time.sleep(poll_interval)
            continue

        data = resp.json()
        status = data.get("status", "Unknown")
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        print(f"  [{mins:02d}:{secs:02d}] Status: {status}")

        if status in ("Succeeded", "Failed", "Canceled"):
            return status

        time.sleep(poll_interval)


def get_iteration_result(translation_id: str) -> dict:
    """Get the first iteration result with download URLs."""
    # List iterations to find the auto-created one
    url = f"{BASE_URL}/translations/{translation_id}/iterations?api-version={API_VERSION}"
    print(f"\n[3/4] Fetching iteration results...")

    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"  ERROR: {resp.status_code} — {resp.text}")
        return {}

    data = resp.json()
    iterations = data.get("value", [])
    if not iterations:
        print("  No iterations found")
        return {}

    iteration = iterations[0]
    iteration_id = iteration["id"]
    print(f"  Iteration: {iteration_id}, Status: {iteration.get('status')}")

    # Get full iteration details
    detail_url = f"{BASE_URL}/translations/{translation_id}/iterations/{iteration_id}?api-version={API_VERSION}"
    resp2 = requests.get(detail_url, headers=HEADERS)
    if resp2.status_code != 200:
        print(f"  ERROR getting details: {resp2.status_code} — {resp2.text}")
        return iteration

    return resp2.json()


def download_results(iteration_data: dict, output_dir: Path):
    """Download translated video and subtitles."""
    output_dir.mkdir(parents=True, exist_ok=True)
    result = iteration_data.get("result", {})

    files_to_download = {
        "translated_video.mp4": result.get("translatedVideoFileUrl"),
        "subtitles_source.vtt": result.get("sourceLocaleSubtitleWebvttFileUrl"),
        "subtitles_target.vtt": result.get("targetLocaleSubtitleWebvttFileUrl"),
        "metadata.json": result.get("metadataJsonWebvttFileUrl"),
    }

    print(f"\n[4/4] Downloading results to {output_dir}/")
    for filename, url in files_to_download.items():
        if not url:
            print(f"  ⏭ {filename}: no URL")
            continue
        print(f"  ⬇ {filename}...")
        resp = requests.get(url, stream=True)
        if resp.status_code == 200:
            filepath = output_dir / filename
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"    ✓ {size_mb:.1f} MB → {filepath}")
        else:
            print(f"    ✗ HTTP {resp.status_code}")

    # Save full iteration data for reference
    meta_path = output_dir / "iteration_response.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(iteration_data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Iteration metadata → {meta_path}")


def main():
    parser = argparse.ArgumentParser(description="Video Translation Lip-Sync Test")
    parser.add_argument("--video", type=Path, required=True, help="Path to video clip")
    parser.add_argument("--subtitle", type=Path, default=None, help="Path to target-language WebVTT file")
    parser.add_argument("--source-locale", default="en-US", help="Source language (default: en-US)")
    parser.add_argument("--target-locale", default="de-DE", help="Target language (default: de-DE)")
    parser.add_argument("--no-lipsync", action="store_true", help="Disable lip-sync")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in minutes (default: 30)")
    args = parser.parse_args()

    # Validate
    if not SPEECH_KEY:
        print("ERROR: SPEECH_KEY not set"); sys.exit(1)
    if not STORAGE_CONN_STR:
        print("ERROR: STORAGE_CONN_STR not set"); sys.exit(1)
    if not args.video.exists():
        print(f"ERROR: Video file not found: {args.video}"); sys.exit(1)

    print("=" * 60)
    print("Azure Video Translation — Lip-Sync Feasibility Test")
    print("=" * 60)
    print(f"Video:     {args.video}")
    print(f"Subtitle:  {args.subtitle or 'auto-generate'}")
    print(f"Direction: {args.source_locale} → {args.target_locale}")
    print(f"Lip-sync:  {not args.no_lipsync}")
    print(f"Region:    {SPEECH_REGION}")
    print(f"Timeout:   {args.timeout} min")
    print("=" * 60)

    start_time = time.time()

    # Upload video
    print("\n📤 Uploading files to Blob Storage...")
    video_blob = f"test/{args.video.name}"
    video_url = blob_upload(args.video, video_blob)

    subtitle_url = None
    if args.subtitle and args.subtitle.exists():
        sub_blob = f"test/{args.subtitle.name}"
        subtitle_url = blob_upload(args.subtitle, sub_blob)

    # Create translation
    translation_id, operation_id = create_translation(
        video_url=video_url,
        subtitle_url=subtitle_url,
        source_locale=args.source_locale,
        target_locale=args.target_locale,
        enable_lip_sync=not args.no_lipsync,
    )

    # Poll until done
    final_status = poll_operation(operation_id, timeout_minutes=args.timeout)

    if final_status != "Succeeded":
        print(f"\n❌ Translation {final_status}. Check Azure portal for details.")
        # Still try to get partial info
        get_iteration_result(translation_id)
        sys.exit(1)

    # Download results
    iteration_data = get_iteration_result(translation_id)
    download_results(iteration_data, OUTPUT_DIR / args.target_locale)

    elapsed = time.time() - start_time
    print(f"\n✅ Done in {int(elapsed // 60)}m {int(elapsed % 60)}s")
    print(f"📂 Results: {OUTPUT_DIR / args.target_locale}")


if __name__ == "__main__":
    main()

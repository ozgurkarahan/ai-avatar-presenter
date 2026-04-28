"""Test Azure Speech batch avatar synthesis with the *Clara* photo avatar.

Uses the new Foundry resource `ai-custom-avatar-resource` in swedencentral
and AAD bearer auth (local-auth disabled by MCAPS policy).
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import requests

REGION = "swedencentral"
RESOURCE = "ai-custom-avatar-resource"
# AAD token written to %TEMP%/foundry_token.txt by the calling shell
TOKEN = Path(os.environ["TEMP"], "foundry_token.txt").read_text().strip()

BASE = f"https://{RESOURCE}.cognitiveservices.azure.com"
# Try standard batch synthesis path
JOB_ID = str(uuid.uuid4())
API = "2024-08-01"
URL = f"{BASE}/avatar/batchsyntheses/{JOB_ID}?api-version={API}"

def list_avatars():
    """Try to list supported avatars/voices via the catalog endpoints."""
    for path in [
        "/avatar/batchsyntheses?api-version=2024-08-01",
        "/avatar/voices?api-version=2024-08-01",
        "/avatars?api-version=2024-08-01",
    ]:
        url = f"{BASE}{path}"
        r = requests.get(url, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=15)
        print(f"GET {path} -> {r.status_code}: {r.text[:300]}")


SSML = """<speak version='1.0' xml:lang='en-US' xmlns:mstts='https://www.w3.org/2001/mstts'>
  <voice name='en-US-AvaMultilingualNeural'>
    Hello, I am Clara, testing the new photo avatar from Microsoft Foundry.
  </voice>
</speak>"""

# Try Clara as a photo avatar character — exact character/style names TBD.
PAYLOADS = [
    {
        "label": "clara photo (lowercase)",
        "body": {
            "inputKind": "SSML",
            "inputs": [{"content": SSML}],
            "avatarConfig": {
                "talkingAvatarCharacter": "clara",
                "talkingAvatarStyle": "casual",
                "videoFormat": "webm",
                "videoCodec": "vp9",
                "subtitleType": "soft_embedded",
                "backgroundColor": "#00000000",
            },
        },
    },
    {
        "label": "Clara photo (capitalized)",
        "body": {
            "inputKind": "SSML",
            "inputs": [{"content": SSML}],
            "avatarConfig": {
                "talkingAvatarCharacter": "Clara",
                "talkingAvatarStyle": "casual",
                "videoFormat": "webm",
                "videoCodec": "vp9",
                "subtitleType": "soft_embedded",
                "backgroundColor": "#00000000",
            },
        },
    },
]

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}


def submit(label: str, body: dict) -> str | None:
    job_id = str(uuid.uuid4())
    url = f"{BASE}/avatar/batchsyntheses/{job_id}?api-version={API}"
    print(f"\n--- {label} ---")
    print(f"PUT {url}")
    r = requests.put(url, headers=HEADERS, json=body, timeout=30)
    print(f"status={r.status_code}")
    print(f"body: {r.text[:1500]}")
    if r.ok:
        return job_id
    return None


def poll(job_id: str, timeout: int = 600) -> None:
    url = f"{BASE}/avatar/batchsyntheses/{job_id}?api-version={API}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        print(f"[poll] status={status}")
        if status in ("Succeeded", "Failed"):
            import json
            print(json.dumps(data, indent=2)[:3000])
            return
        time.sleep(8)
    print("[poll] timeout")


if __name__ == "__main__":
    succeeded_job = None
    for p in PAYLOADS:
        job = submit(p["label"], p["body"])
        if job:
            succeeded_job = job
            break
    if succeeded_job:
        poll(succeeded_job)
    else:
        print("\n[done] no payload accepted by the API — see errors above.")
        sys.exit(1)

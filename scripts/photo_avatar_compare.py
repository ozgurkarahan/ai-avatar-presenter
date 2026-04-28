"""UC2 side-by-side compare: Clara (photo) vs Lisa (video) batch synth.

Renders the same narration on both avatars from the new
ai-custom-avatar-resource in swedencentral, downloads both clips,
and composites each over a slide background using ffmpeg, producing
two MP4s for direct visual compare.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

# --- config ---
RESOURCE = "ai-custom-avatar-resource"
BASE = f"https://{RESOURCE}.cognitiveservices.azure.com"
API = "2024-08-01"
TOKEN = Path(os.environ["TEMP"], "foundry_token.txt").read_text().strip()
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
HG = {"Authorization": f"Bearer {TOKEN}"}

# Slide and output
ROOT = Path(__file__).resolve().parents[1]
SLIDE = ROOT / "demos/backend/data/slides/1ab6cee3-546d-4234-81e8-44948005d74b/1.png"
OUT = ROOT / "data/photo_avatar_test"
OUT.mkdir(parents=True, exist_ok=True)

NARRATION = (
    "Welcome. Today we will explore how Saint-Gobain is decarbonizing the "
    "building materials industry. From low-carbon glass to recycled gypsum, "
    "every product line plays a role in reaching net zero by twenty-fifty."
)
VOICE = "en-US-AvaMultilingualNeural"


def submit(label: str, payload: dict) -> str:
    jid = str(uuid.uuid4())
    url = f"{BASE}/avatar/batchsyntheses/{jid}?api-version={API}"
    r = requests.put(url, headers=H, json=payload, timeout=30)
    print(f"[submit:{label}] status={r.status_code} jid={jid}")
    if not r.ok:
        print(r.text[:500])
        raise SystemExit(1)
    return jid


def poll(label: str, jid: str, timeout: int = 600) -> dict:
    url = f"{BASE}/avatar/batchsyntheses/{jid}?api-version={API}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = requests.get(url, headers=HG, timeout=15).json()
        s = d.get("status")
        print(f"[poll:{label}] {s}")
        if s == "Succeeded":
            return d
        if s == "Failed":
            print(json.dumps(d, indent=2)[:1500])
            raise SystemExit(2)
        time.sleep(8)
    raise SystemExit(3)


def download(url: str, dest: Path) -> Path:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for ch in r.iter_content(1 << 16):
                f.write(ch)
    print(f"[dl] {dest.name} {dest.stat().st_size:,}B")
    return dest


def build_payload_photo(character: str) -> dict:
    return {
        "synthesisConfig": {"voice": VOICE},
        "customVoices": {},
        "inputKind": "PlainText",
        "inputs": [{"content": NARRATION}],
        "avatarConfig": {
            "photoAvatarBaseModel": "vasa-1",
            "talkingAvatarCharacter": character,
            "talkingAvatarStyle": "",
            "customized": False,
            "videoFormat": "mp4",
            "videoCodec": "h264",
            "subtitleType": "soft_embedded",
            "backgroundColor": "#00FF00FF",  # green for chroma key
            "useBuiltInVoice": False,
        },
    }


def build_payload_video(character: str, style: str) -> dict:
    return {
        "synthesisConfig": {"voice": VOICE},
        "customVoices": {},
        "inputKind": "PlainText",
        "inputs": [{"content": NARRATION}],
        "avatarConfig": {
            "talkingAvatarCharacter": character,
            "talkingAvatarStyle": style,
            "customized": False,
            "videoFormat": "webm",
            "videoCodec": "vp9",
            "subtitleType": "soft_embedded",
            "backgroundColor": "#00000000",  # transparent
            "useBuiltInVoice": False,
        },
    }


def render_one(label: str, payload: dict, ext: str) -> Path:
    jid = submit(label, payload)
    d = poll(label, jid)
    dest = OUT / f"{label}.{ext}"
    download(d["outputs"]["result"], dest)
    return dest


def composite(label: str, avatar_clip: Path, photo: bool) -> Path:
    """Composite avatar over slide. 1920x1080 background, avatar in
    bottom-right corner. Photo avatar uses chroma key (green) since
    it's not transparent; video avatar already has alpha."""
    out = OUT / f"compare_{label}.mp4"
    if photo:
        # Chroma-key the green background, scale to 480px tall,
        # overlay bottom-right.
        filt = (
            "[0:v]scale=1920:1080,setsar=1[bg];"
            "[1:v]chromakey=0x00ff00:0.10:0.05,scale=-1:520[fg];"
            "[bg][fg]overlay=W-w-40:H-h-40[outv]"
        )
    else:
        filt = (
            "[0:v]scale=1920:1080,setsar=1[bg];"
            "[1:v]scale=-1:720[fg];"
            "[bg][fg]overlay=W-w-40:H-h-40[outv]"
        )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(SLIDE),
        "-i", str(avatar_clip),
        "-filter_complex", filt,
        "-map", "[outv]", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(out),
    ]
    print(f"[ffmpeg:{label}] {' '.join(cmd)}")
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[done] {out} {out.stat().st_size:,}B")
    return out


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found in PATH")
    if not SLIDE.exists():
        raise SystemExit(f"slide missing: {SLIDE}")

    # Submit both jobs in parallel.
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_clara = pool.submit(render_one, "clara_photo", build_payload_photo("clara"), "mp4")
        f_lisa = pool.submit(render_one, "lisa_video", build_payload_video("lisa", "casual-sitting"), "webm")
        clara_clip = f_clara.result()
        lisa_clip = f_lisa.result()

    composite("clara_photo", clara_clip, photo=True)
    composite("lisa_video", lisa_clip, photo=False)


if __name__ == "__main__":
    main()

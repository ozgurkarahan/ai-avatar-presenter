"""Regenerate the Apr-24 17:12 decarbonization-intro UC2 video using
the new Clara photo avatar.

Source: blob static-videos/sv-0560f488 (subtitles.srt → narrations,
deck db708195-86d6-4a32-bc53-527340b151b7 → slide PNGs).

Output: data/clara_regen/clara_decarbonization.mp4
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

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data/clara_regen"
SLIDES = WORK / "slides"

RESOURCE = "ai-custom-avatar-resource"
BASE = f"https://{RESOURCE}.cognitiveservices.azure.com"
API = "2024-08-01"
TOKEN = Path(os.environ["TEMP"], "foundry_token.txt").read_text().strip()
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
HG = {"Authorization": f"Bearer {TOKEN}"}

# Voice — match the original (Ava DragonHD) since photo avatar should
# accept any standard voice.
VOICE = "en-US-AvaMultilingualNeural"

# Narrations split from subtitles.srt at logical slide boundaries.
NARRATIONS: list[str] = [
    # slide 0 (intro)
    "Welcome to our introduction to decarbonization for industry. "
    "Today, we'll talk about why decarbonization matters, how emissions "
    "are categorized into different scopes, and how everyone — no matter "
    "your role — can help drive change. Let's get started by understanding "
    "the science behind the urgency.",
    # slide 1 (climate science)
    "The science is clear and urgent. Global temperatures have already "
    "risen by 1.2 degrees since 1900, and atmospheric CO2 has reached "
    "levels not seen in three million years. Industry alone contributes "
    "about thirty percent of global emissions, which is why the Paris "
    "Agreement aims to keep warming below 1.5 degrees. This context "
    "shows just how important our actions are.",
    # slide 2 (three scopes)
    "Building on that, let's break down where emissions come from. "
    "Companies report emissions in three scopes: scope 1 is what we emit "
    "directly, like from our factories or trucks; scope 2 covers indirect "
    "emissions from the electricity we purchase; and scope 3 includes "
    "everything else in our value chain, like our suppliers and even how "
    "our products are used. Often, scope 3 actually makes up the biggest "
    "part of our footprint.",
    # slide 3 (four levers)
    "So what does this mean in practice? Companies can act using four "
    "main levers: make our plants more energy efficient, shift to "
    "renewable electricity, choose low-carbon raw materials, and design "
    "products so they stay in use longer or can be recycled. Even small "
    "changes in these areas can add up to a meaningful impact.",
    # slide 4 (wrap-up)
    "To wrap up, this session is just the beginning of your "
    "decarbonization journey. Coming up, we'll take a closer look at "
    "low-carbon materials and the circular economy, with practical steps "
    "your team can take. Together, we can make a real difference for our "
    "company and the planet.",
]


def submit(idx: int, text: str) -> str:
    jid = str(uuid.uuid4())
    url = f"{BASE}/avatar/batchsyntheses/{jid}?api-version={API}"
    payload = {
        "synthesisConfig": {"voice": VOICE},
        "customVoices": {},
        "inputKind": "PlainText",
        "inputs": [{"content": text}],
        "avatarConfig": {
            "photoAvatarBaseModel": "vasa-1",
            "talkingAvatarCharacter": "clara",
            "talkingAvatarStyle": "",
            "customized": False,
            "videoFormat": "mp4",
            "videoCodec": "h264",
            "subtitleType": "soft_embedded",
            "backgroundColor": "#00FF00FF",  # green for chroma key
            "useBuiltInVoice": False,
        },
    }
    r = requests.put(url, headers=H, json=payload, timeout=30)
    if not r.ok:
        print(f"[submit slide {idx}] FAILED status={r.status_code} {r.text[:300]}")
        raise SystemExit(1)
    print(f"[submit slide {idx}] jid={jid}")
    return jid


def poll(idx: int, jid: str, timeout: int = 900) -> str:
    url = f"{BASE}/avatar/batchsyntheses/{jid}?api-version={API}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = requests.get(url, headers=HG, timeout=15).json()
        s = d.get("status")
        if s in ("Succeeded", "Failed"):
            print(f"[poll slide {idx}] {s}")
            if s == "Succeeded":
                return d["outputs"]["result"]
            print(json.dumps(d, indent=2)[:1500])
            raise SystemExit(2)
        time.sleep(8)
    raise SystemExit(3)


def download(url: str, dest: Path) -> Path:
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for ch in r.iter_content(1 << 16):
                f.write(ch)
    print(f"[dl] {dest.name} {dest.stat().st_size:,}B")
    return dest


def render_slide(idx: int, text: str) -> Path:
    jid = submit(idx, text)
    url = poll(idx, jid)
    dest = WORK / f"clara_clip_{idx}.mp4"
    return download(url, dest)


def composite_slide(idx: int, slide_png: Path, avatar_clip: Path) -> Path:
    """Slide background full-screen 1920x1080, Clara head bottom-right
    PiP via chroma key. Avatar 520px tall, 40px margin."""
    out = WORK / f"slide_{idx}.mp4"
    filt = (
        "[0:v]scale=1920:1080,setsar=1[bg];"
        "[1:v]chromakey=0x00ff00:0.10:0.05,scale=-1:520[fg];"
        "[bg][fg]overlay=W-w-40:H-h-40[outv]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(slide_png),
        "-i", str(avatar_clip),
        "-filter_complex", filt,
        "-map", "[outv]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "25",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[comp] {out.name} {out.stat().st_size:,}B")
    return out


def concat(parts: list[Path], out: Path) -> Path:
    list_file = WORK / "concat.txt"
    list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts))
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[final] {out.name} {out.stat().st_size:,}B")
    return out


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found")
    WORK.mkdir(parents=True, exist_ok=True)

    # Render Clara clips for all 5 slides in parallel.
    with ThreadPoolExecutor(max_workers=5) as pool:
        clips = list(pool.map(lambda x: render_slide(*x), enumerate(NARRATIONS)))

    # Composite each slide.
    parts: list[Path] = []
    for idx, clip in enumerate(clips):
        slide_png = SLIDES / f"{idx}.png"
        if not slide_png.exists():
            raise SystemExit(f"missing slide {slide_png}")
        parts.append(composite_slide(idx, slide_png, clip))

    final = WORK / "clara_decarbonization.mp4"
    concat(parts, final)
    print(f"\nDONE -> {final}")


if __name__ == "__main__":
    main()

"""Re-submit just slide 3 (stuck), then composite + concat all slides."""
import os
import subprocess
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data/clara_regen"
SLIDES = WORK / "slides"

BASE = "https://ai-custom-avatar-resource.cognitiveservices.azure.com"
API = "2024-08-01"
TOKEN = Path(os.environ["TEMP"], "foundry_token.txt").read_text().strip()
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
HG = {"Authorization": f"Bearer {TOKEN}"}

SLIDE3_TEXT = (
    "So what does this mean in practice? Companies can act using four "
    "main levers: make our plants more energy efficient, shift to "
    "renewable electricity, choose low-carbon raw materials, and design "
    "products so they stay in use longer or can be recycled. Even small "
    "changes in these areas can add up to a meaningful impact."
)


def render_slide3() -> Path:
    jid = str(uuid.uuid4())
    url = f"{BASE}/avatar/batchsyntheses/{jid}?api-version={API}"
    payload = {
        "synthesisConfig": {"voice": "en-US-AvaMultilingualNeural"},
        "customVoices": {},
        "inputKind": "PlainText",
        "inputs": [{"content": SLIDE3_TEXT}],
        "avatarConfig": {
            "photoAvatarBaseModel": "vasa-1",
            "talkingAvatarCharacter": "clara",
            "talkingAvatarStyle": "",
            "customized": False,
            "videoFormat": "mp4",
            "videoCodec": "h264",
            "subtitleType": "soft_embedded",
            "backgroundColor": "#00FF00FF",
            "useBuiltInVoice": False,
        },
    }
    r = requests.put(url, headers=H, json=payload, timeout=30)
    r.raise_for_status()
    print(f"[resubmit slide 3] jid={jid}")

    deadline = time.time() + 600
    while time.time() < deadline:
        d = requests.get(url, headers=HG, timeout=15).json()
        s = d.get("status")
        print(f"[poll slide 3] {s}")
        if s == "Succeeded":
            dest = WORK / "clara_clip_3.mp4"
            with requests.get(d["outputs"]["result"], stream=True, timeout=120) as resp:
                resp.raise_for_status()
                with dest.open("wb") as f:
                    for ch in resp.iter_content(1 << 16):
                        f.write(ch)
            print(f"[dl] {dest.name} {dest.stat().st_size:,}B")
            return dest
        if s == "Failed":
            raise SystemExit(f"failed: {d}")
        time.sleep(8)
    raise SystemExit("timeout")


def composite_slide(idx: int) -> Path:
    out = WORK / f"slide_{idx}.mp4"
    slide_png = SLIDES / f"{idx}.png"
    avatar_clip = WORK / f"clara_clip_{idx}.mp4"
    filt = (
        "[0:v]scale=1920:1080,setsar=1[bg];"
        "[1:v]chromakey=0x00ff00:0.22:0.12,"
        "despill=type=green:mix=0.6:expand=0.3:brightness=0,"
        "scale=-1:520[fg];"
        "[bg][fg]overlay=W-w-40:H-h-40:format=auto[outv]"
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


def concat(parts, out: Path) -> Path:
    list_file = WORK / "concat.txt"
    list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts))
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[final] {out.name} {out.stat().st_size:,}B")
    return out


if __name__ == "__main__":
    if not (WORK / "clara_clip_3.mp4").exists():
        render_slide3()
    parts = [composite_slide(i) for i in range(5)]
    final = WORK / "clara_decarbonization.mp4"
    concat(parts, final)
    print(f"\nDONE -> {final}")

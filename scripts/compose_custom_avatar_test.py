"""Composite ST_Gobain_Female and ST_Gobain_Male photo-avatar test clips onto a slide bg.

Picks the first slide of the decarbonization deck (already downloaded in data/clara_regen/slides/0.png)
and overlays each avatar with the same chroma-key+despill chain we use for Clara.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLIDE = ROOT / "data/clara_regen/slides/0.png"
TEST = ROOT / "data/photo_avatar_test"

CHROMA = (
    "[0:v]scale=1920:1080,setsar=1[bg];"
    "[1:v]chromakey=0x00ff00:0.22:0.12,"
    "despill=type=green:mix=0.6:expand=0.3:brightness=0,"
    "scale=-1:520[fg];"
    "[bg][fg]overlay=W-w-40:H-h-40:format=auto[outv]"
)


def comp(src: Path, dst: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(SLIDE),
        "-i", str(src),
        "-filter_complex", CHROMA,
        "-map", "[outv]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "25",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[ok] {dst.name} {dst.stat().st_size:,}B")


for av in ("ST_Gobain_Female", "ST_Gobain_Male"):
    src = TEST / f"custom_{av}.mp4"
    dst = TEST / f"composed_{av}.mp4"
    if src.exists():
        comp(src, dst)

"""Test ST_Gobain_Female and ST_Gobain_Male custom photo avatars."""
import os, time, uuid, json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/photo_avatar_test"
OUT.mkdir(parents=True, exist_ok=True)

BASE = "https://ai-custom-avatar-resource.cognitiveservices.azure.com"
API = "2024-08-01"
TOKEN = Path(os.environ["TEMP"], "foundry_token.txt").read_text().strip()
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
HG = {"Authorization": f"Bearer {TOKEN}"}

TEXT = (
    "Welcome. I'm here to introduce Saint-Gobain's approach to "
    "decarbonization, and how every team can contribute to a more "
    "sustainable industry."
)

AVATARS = ["ST_Gobain_Male"]


def variants(name: str):
    """Try a few payload shapes — first to succeed wins."""
    return [
        # Shape A: photo + customized
        {
            "label": "photo+customized",
            "avatarConfig": {
                "photoAvatarBaseModel": "vasa-1",
                "talkingAvatarCharacter": name,
                "talkingAvatarStyle": "",
                "customized": True,
                "videoFormat": "mp4",
                "videoCodec": "h264",
                "backgroundColor": "#00FF00FF",
            },
        },
        # Shape B: customized without baseModel (treat as standard custom)
        {
            "label": "customized-only",
            "avatarConfig": {
                "talkingAvatarCharacter": name,
                "talkingAvatarStyle": "",
                "customized": True,
                "videoFormat": "mp4",
                "videoCodec": "h264",
                "backgroundColor": "#00FF00FF",
            },
        },
        # Shape C: photo + customized + style="default"
        {
            "label": "photo+customized+default-style",
            "avatarConfig": {
                "photoAvatarBaseModel": "vasa-1",
                "talkingAvatarCharacter": name,
                "talkingAvatarStyle": "default",
                "customized": True,
                "videoFormat": "mp4",
                "videoCodec": "h264",
                "backgroundColor": "#00FF00FF",
            },
        },
    ]


def submit(name: str, cfg: dict) -> tuple[str, str]:
    jid = str(uuid.uuid4())
    url = f"{BASE}/avatar/batchsyntheses/{jid}?api-version={API}"
    payload = {
        "synthesisConfig": {"voice": "en-US-AvaMultilingualNeural"},
        "customVoices": {},
        "inputKind": "PlainText",
        "inputs": [{"content": TEXT}],
        "avatarConfig": cfg,
    }
    r = requests.put(url, headers=H, json=payload, timeout=30)
    return jid, f"{r.status_code} {r.text[:300]}"


def poll(jid: str) -> dict:
    url = f"{BASE}/avatar/batchsyntheses/{jid}?api-version={API}"
    deadline = time.time() + 300
    while time.time() < deadline:
        d = requests.get(url, headers=HG, timeout=15).json()
        s = d.get("status")
        print(f"  [poll] {s}")
        if s in ("Succeeded", "Failed"):
            return d
        time.sleep(8)
    return {"status": "Timeout"}


for av in AVATARS:
    print(f"\n=== {av} ===")
    for v in variants(av):
        cfg = v.copy()
        label = cfg.pop("label")
        print(f"-- try {label}")
        jid, resp = submit(av, cfg["avatarConfig"])
        print(f"   submit: {resp[:200]}")
        if not resp.startswith("201") and not resp.startswith("200"):
            continue
        result = poll(jid)
        if result.get("status") == "Succeeded":
            outurl = result["outputs"]["result"]
            dest = OUT / f"custom_{av}.mp4"
            with requests.get(outurl, stream=True, timeout=120) as resp2:
                resp2.raise_for_status()
                with dest.open("wb") as f:
                    for ch in resp2.iter_content(1 << 16):
                        f.write(ch)
            print(f"   [OK] saved {dest.name} {dest.stat().st_size:,}B")
            break
        else:
            err = result.get("properties", {}).get("error") or result
            print(f"   [FAIL] {result.get('status')}: {json.dumps(err)[:300]}")
    else:
        print(f"   !! all variants failed for {av}")

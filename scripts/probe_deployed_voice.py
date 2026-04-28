"""Probe the deployed backend's /api/voice WS to reproduce the failure."""
import asyncio, json, sys
import websockets

URL = "wss://ca-am564oxavvhhk.orangecliff-e64ce39a.swedencentral.azurecontainerapps.io/ws/voice"

async def main():
    async with websockets.connect(URL, max_size=4*1024*1024) as ws:
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "language": "en-US",
                "voice": {"name": "en-US-Ava:DragonHDLatestNeural"},
                "avatar": {"character": "st_gobain_female"},
            },
        }))
        for i in range(15):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
            except asyncio.TimeoutError:
                print("[timeout]"); break
            if isinstance(msg, bytes):
                print(f"[{i}] BIN {len(msg)}B"); continue
            try:
                d = json.loads(msg)
            except Exception:
                print(f"[{i}] RAW {msg[:120]}"); continue
            t = d.get("type")
            print(f"[{i}] {t}")
            if t == "error":
                print("  ERROR:", json.dumps(d.get("error"), indent=2))
            elif t == "session.updated":
                print("  avatar:", d.get("session", {}).get("avatar"))
                return

asyncio.run(main())

"""Test concurrent avatar sessions — does running 2 at once cause resource_exhausted?"""
import asyncio, json
import websockets
from azure.identity import DefaultAzureCredential

HOST = "ai-custom-avatar-resource.cognitiveservices.azure.com"
URL = f"wss://{HOST}/voice-live/realtime?api-version=2025-10-01&model=gpt-4.1"
PAYLOAD = {
    "type": "session.update",
    "session": {
        "modalities": ["text", "audio", "avatar"],
        "voice": {"name": "en-US-Ava:DragonHDLatestNeural", "type": "azure-standard"},
        "avatar": {"character": "ST_Gobain_Female", "customized": True, "photoAvatarBaseModel": "vasa-1"},
    },
}

async def one(label, hold_seconds=15):
    cred = DefaultAzureCredential()
    token = cred.get_token("https://ai.azure.com/.default").token
    try:
        async with websockets.connect(URL, additional_headers={"Authorization": f"Bearer {token}"}) as ws:
            await ws.send(json.dumps(PAYLOAD))
            got_ice = False
            err = None
            t0 = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - t0 < hold_seconds:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(msg)
                t = d.get("type")
                if t == "session.updated":
                    av = d.get("session", {}).get("avatar", {})
                    if av.get("ice_servers"):
                        got_ice = True
                        print(f"[{label}] ✅ ice_servers OK")
                elif t == "error":
                    err = d.get("error")
                    print(f"[{label}] ❌ {err.get('code')}: {err.get('message')}")
                    return ("error", err)
            return ("ok" if got_ice else "no_ice", None)
    except Exception as e:
        print(f"[{label}] EXC {e}")
        return ("exc", str(e))

async def main():
    # Sequential baseline
    print("=== Sequential ===")
    await one("seq1", 5)
    await asyncio.sleep(1)
    await one("seq2", 5)
    print("\n=== Concurrent (2 sessions) ===")
    r = await asyncio.gather(one("a", 20), one("b", 20))
    print("results:", r)
    print("\n=== Concurrent (3 sessions) ===")
    r = await asyncio.gather(one("x", 20), one("y", 20), one("z", 20))
    print("results:", r)

asyncio.run(main())

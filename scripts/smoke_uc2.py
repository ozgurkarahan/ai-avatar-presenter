"""UC2 end-to-end smoke test."""
import json, sys, time, urllib.request
from pathlib import Path

BASE = "http://localhost:8765/api/static-video"

def get(path):
    with urllib.request.urlopen(f"{BASE}{path}") as r:
        return json.loads(r.read())

def post_json(path, body):
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(body).encode(),
        headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return r.read().decode(), r.status

def post_multipart(path, file_path, filename):
    import uuid
    boundary = uuid.uuid4().hex
    data = []
    data.append(f"--{boundary}".encode())
    data.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode())
    data.append(b"Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation")
    data.append(b"")
    data.append(Path(file_path).read_bytes())
    data.append(f"--{boundary}".encode())
    data.append(b'Content-Disposition: form-data; name="filename"')
    data.append(b"")
    data.append(filename.encode())
    data.append(f"--{boundary}--".encode())
    body = b"\r\n".join(data)
    req = urllib.request.Request(f"{BASE}{path}", data=body, method="POST",
        headers={"content-type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def stream(path, body):
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(body).encode(),
        headers={"content-type": "application/json"}, method="POST")
    lines = []
    with urllib.request.urlopen(req) as r:
        for raw in r:
            line = raw.decode().strip()
            if line:
                lines.append(json.loads(line))
    return lines

print("=" * 60)
print("1) GET /languages")
langs = get("/languages")
print(f"   -> {len(langs)} languages: {[l.get('code') for l in langs[:3]]}...")

print("2) GET /voices?language=en-US")
voices = get("/voices?language=en-US")
print(f"   -> {len(voices)} voices; first: {voices[0] if voices else None}")
voice_id = voices[0]["id"] if voices else None

print("3) POST /ingest (multipart PPTX)")
pptx = r"C:\Users\ozgurkarahan\projects\cowork\ip\Identity Propagation for AI Agents v4.pptx"
ing = post_multipart("/ingest", pptx, "Identity Propagation for AI Agents v4.pptx")
doc_id = ing["doc_id"]
slides = ing["slides"]
print(f"   -> doc_id={doc_id} title={ing.get('title')} slides={len(slides)}")
print(f"   -> slide 0: index={slides[0]['index']} title={slides[0].get('title')!r} preview={slides[0].get('preview_text','')[:60]!r}")

print("4) POST /script/{doc_id} (NDJSON stream)")
events = stream(f"/script/{doc_id}", {
    "language": "en-US",
    "style": "explainer",
    "voice": voice_id,
    "focus": "a 60-second exec summary"
})
narrations = [e for e in events if e.get("event") == "narration"]
done = [e for e in events if e.get("event") == "done"]
errors = [e for e in events if e.get("event") == "error"]
print(f"   -> {len(narrations)} narration events, {len(done)} done, {len(errors)} error")
if narrations:
    first = narrations[0]["data"]
    print(f"   -> slide 0 narration ({len(first.get('narration',''))} chars): {first.get('narration','')[:120]!r}...")

print("5) GET /script/{doc_id}")
script = get(f"/script/{doc_id}")
print(f"   -> language={script['language']} voice={script['voice']} narrations={len(script['narrations'])}")

print("6) PATCH /script/{doc_id}  (edit slide 0 narration)")
req = urllib.request.Request(f"{BASE}/script/{doc_id}",
    data=json.dumps({"patches": [{"slide_index": 0, "narration": "EDITED_FOR_TEST"}]}).encode(),
    headers={"content-type":"application/json"}, method="PATCH")
with urllib.request.urlopen(req) as r:
    patched = json.loads(r.read())
print(f"   -> slide 0 now: {patched['narrations'][0]['narration'][:40]!r}")
assert patched["narrations"][0]["narration"] == "EDITED_FOR_TEST"

print("7) POST /render/{doc_id}  (kick off)")
body, _ = post_json(f"/render/{doc_id}", {})
render = json.loads(body)
job_id = render.get("job_id")
print(f"   -> job_id={job_id}")

print("8) Poll /jobs/{job_id}  (up to 30s to see stage progression)")
seen_stages = []
deadline = time.time() + 30
while time.time() < deadline:
    job = get(f"/jobs/{job_id}")
    stage = job.get("progress",{}).get("stage") or job.get("state")
    pct = job.get("progress",{}).get("percent")
    msg = job.get("progress",{}).get("message","")
    state = job.get("state")
    if stage not in seen_stages:
        seen_stages.append(stage)
        print(f"   -> state={state} stage={stage} pct={pct} msg={msg[:60]!r}")
    if state in ("done","failed"):
        print(f"   FINAL: state={state}")
        break
    time.sleep(2)
else:
    print(f"   (still in progress after 30s — stages seen: {seen_stages})")

print("=" * 60)
print("SMOKE TEST COMPLETE")

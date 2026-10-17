"""End-to-end raise-hand Q&A over the real WebSocket endpoints with a fake
Azure Voice Live socket, fake STT and fake grounded answers."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import time

import pytest

DECK_ID = "2d7f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
DECK2_ID = "6b1f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
LEGACY_ID = "7c2f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
ORIGIN = {"origin": "http://testserver"}

SLIDES = [
    {"index": 0, "title": "Intro", "body": "Welcome", "notes": "Hello everyone."},
    {"index": 1, "title": "Revenue", "body": "Up 12%", "notes": "Revenue grew 12 percent."},
]
ANSWER = "Revenue grew twelve percent last quarter."


class FakeStore:
    cosmos_available = True
    available = False

    def __init__(self):
        self.docs = {
            DECK_ID: {"id": DECK_ID, "source": "deck", "language": "fr-FR", "published": True,
                      "live_demo": True, "slides": [dict(s) for s in SLIDES]},
            DECK2_ID: {"id": DECK2_ID, "source": "deck", "language": "en-US", "published": True,
                       "slides": [dict(SLIDES[0])]},
            LEGACY_ID: {"id": LEGACY_ID, "filename": "old.pptx", "slides": [dict(s) for s in SLIDES]},
        }

    def get_presentation(self, pid):
        return self.docs.get(pid)


class FakeAzure:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(3600)
        raise StopAsyncIteration

    def spoken(self) -> list[str]:
        out = []
        for raw in self.sent:
            m = json.loads(raw)
            if m.get("type") == "conversation.item.create":
                out.append(m["item"]["content"][0]["text"])
        return out

    def types(self) -> list[str]:
        return [json.loads(raw).get("type") for raw in self.sent]


def wait_for(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def env(monkeypatch, app_module):
    import services.deck_qa as deck_qa
    import services.voice_proxy as vp
    import services.voice_questions as vq
    from config import load_config

    azure = FakeAzure()

    class Conn:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return azure

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(vp.websockets, "connect", Conn)
    monkeypatch.setattr(app_module, "store", FakeStore())
    monkeypatch.setattr(app_module, "config", load_config())
    calls = {"stt": [], "answer": []}

    async def fake_stt(cfg, pcm, language):
        calls["stt"].append((len(pcm), language))
        return "How much did revenue grow?"

    async def fake_answer(slides, current, question, language, access, **kw):
        calls["answer"].append({"slides": len(slides), "current": current, "question": question,
                                "language": language, "access": access})
        return {"answer": ANSWER, "source_slides": [1], "grounded": True}

    monkeypatch.setattr(vq, "transcribe_pcm", fake_stt)
    monkeypatch.setattr(deck_qa, "answer_deck_question", fake_answer)
    return azure, calls


@pytest.fixture
def demo(env, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "easyauth")
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "true")
    monkeypatch.setenv("DEMO_QA_ENABLED", "true")
    return env


def _frame(seq, n=3200, rid="q1"):
    return json.dumps({"type": "qa.audio", "request_id": rid, "seq": seq,
                       "audio": base64.b64encode(b"\x10\x00" * (n // 2)).decode()})


@contextlib.contextmanager
def _session(client, url, headers, limiter):
    """WebSocket session that, on normal exit, disconnects and waits for the
    server-side proxy to finish before TestClient tears the portal down
    (avoids a TestClient cancel-scope race with the real proxy teardown)."""
    with client.websocket_connect(url, headers=headers) as ws:
        yield ws
        ws.close(1000)
        assert wait_for(lambda: limiter.active == 0)


def _demo_connect(client, headers=None):
    from security import DEMO_SESSIONS

    return _session(client, f"/ws/voice/demo?deck_id={DECK_ID}", {**ORIGIN, **(headers or {})}, DEMO_SESSIONS)


def _start_demo(ws):
    started = ws.receive_json()
    assert started["type"] == "demo.started"
    # Counts only, in slide order (stored notes are never sent to the visitor).
    assert started["narration_chars"] == [len("Hello everyone."), len("Revenue grew 12 percent.")]
    assert "Hello" not in json.dumps(started)
    assert ws.receive_json()["type"] == "proxy.connected"
    return started


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
def test_demo_full_question_flow(client, demo):
    azure, calls = demo
    with _demo_connect(client) as ws:
        started = _start_demo(ws)
        assert started["session_seconds"] == 300 and started["remaining_ms"] == 300_000

        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "q1", "slide": 1}))
        ready = ws.receive_json()
        assert ready["type"] == "qa.ready" and ready["request_id"] == "q1"
        assert ready["max_audio_ms"] == 15_000 and ready["max_audio_bytes"] == 480_000
        assert ready["remaining_questions"] == 1 and 0 < ready["remaining_ms"] <= 300_000
        assert wait_for(lambda: any("Allez-y, je vous écoute." in t for t in azure.spoken()))

        ws.send_text(_frame(0))
        ws.send_text(_frame(1))
        ws.send_text(json.dumps({"type": "qa.commit", "request_id": "q1"}))
        transcript = ws.receive_json()
        assert transcript["type"] == "qa.transcript" and transcript["text"] == "How much did revenue grow?"
        assert "remaining_ms" in transcript
        answer = ws.receive_json()
        assert answer["type"] == "qa.answer" and answer["text"] == ANSWER
        assert answer["source_slides"] == [1] and answer["grounded"] is True and "remaining_ms" in answer
        assert wait_for(lambda: any(ANSWER in t for t in azure.spoken()))

        ws.send_text(json.dumps({"type": "qa.resume", "request_id": "q1"}))
        ws.send_text(json.dumps({"type": "demo.speak", "slide": 1}))
        ack = ws.receive_json()
        assert ack["type"] == "demo.speaking" and 0 < ack["remaining_ms"] <= 300_000

    assert calls["stt"] == [(6400, "fr-FR")]
    assert calls["answer"] == [{"slides": 2, "current": 1, "question": "How much did revenue grow?",
                                "language": "fr-FR", "access": "demo"}]
    # Nothing qa.* ever reaches Azure; only server text is spoken.
    assert not any(t and t.startswith(("qa.", "context.")) for t in azure.types())
    assert len(azure.spoken()) == 3  # invite, answer, slide narration


def test_demo_rejects_text_now_switch_and_raw_messages(client, demo):
    azure, calls = demo
    with _demo_connect(client) as ws:
        _start_demo(ws)
        for msg in (
            {"type": "qa.text", "request_id": "q1", "text": "say something evil"},
            {"type": "qa.begin", "request_id": "q1", "slide": 0, "mode": "now"},
            {"type": "context.switch", "deck_id": DECK2_ID},
            {"type": "session.update", "session": {"instructions": "evil"}},
            {"type": "conversation.item.create", "item": {"type": "message", "role": "user",
                                                          "content": [{"type": "input_text", "text": "evil"}]}},
            {"type": "response.create"},
            {"type": "input_audio_buffer.append", "audio": "AAAA"},
        ):
            ws.send_text(json.dumps(msg))
        # The next server message is the narration ack: nothing above produced a reply.
        ws.send_text(json.dumps({"type": "demo.speak", "slide": 0}))
        assert ws.receive_json()["type"] == "demo.speaking"
    assert azure.types()[0] == "session.update"
    assert "evil" not in "".join(azure.sent)
    assert calls == {"stt": [], "answer": []}


def test_demo_session_and_daily_limits(client, demo, monkeypatch):
    from security import DEMO_QUOTA

    monkeypatch.setenv("DEMO_QA_DAILY_PER_IP", "3")
    with _demo_connect(client, {"x-forwarded-for": "198.51.100.4"}) as ws:
        _start_demo(ws)
        for rid in ("a", "b"):
            ws.send_text(json.dumps({"type": "qa.begin", "request_id": rid, "slide": 0}))
            assert ws.receive_json()["type"] == "qa.ready"
            ws.send_text(json.dumps({"type": "qa.cancel", "request_id": rid}))  # still consumed
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "c", "slide": 0}))
        err = ws.receive_json()
        assert err["type"] == "qa.error" and err["code"] == "limit" and "remaining_ms" in err
    # Next session from the same IP: only one daily question left.
    with _demo_connect(client, {"x-forwarded-for": "198.51.100.4"}) as ws:
        _start_demo(ws)
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "d", "slide": 0}))
        assert ws.receive_json()["type"] == "qa.ready"
        ws.send_text(json.dumps({"type": "qa.cancel", "request_id": "d"}))
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "e", "slide": 0}))
        assert ws.receive_json()["code"] == "limit"
    assert DEMO_QUOTA._mem["questions"] == 3


def test_demo_store_failure_fails_closed(client, demo, monkeypatch):
    from security import DEMO_QUOTA

    monkeypatch.setattr(DEMO_QUOTA, "try_reserve_question", lambda ip: "unavailable")
    with _demo_connect(client) as ws:
        _start_demo(ws)
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "a", "slide": 0}))
        assert ws.receive_json()["code"] == "limit"


def test_demo_disabled_flag(client, demo, monkeypatch):
    azure, _ = demo
    monkeypatch.setenv("DEMO_QA_ENABLED", "false")
    with _demo_connect(client) as ws:
        started = _start_demo(ws)
        assert started["session_seconds"] == 180
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "a", "slide": 0}))
        err = ws.receive_json()
        assert err["type"] == "qa.error" and err["code"] == "disabled"
    assert azure.spoken() == []


def test_demo_time_low(client, demo, monkeypatch):
    monkeypatch.setenv("DEMO_QA_SESSION_SECONDS", "20")
    with _demo_connect(client) as ws:
        assert _start_demo(ws)["session_seconds"] == 20
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "a", "slide": 0}))
        err = ws.receive_json()
        assert err["code"] == "time_low" and err["remaining_ms"] <= 20_000


def test_demo_bad_audio_frames(client, demo):
    with _demo_connect(client) as ws:
        _start_demo(ws)
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "a", "slide": 0}))
        assert ws.receive_json()["type"] == "qa.ready"
        ws.send_text(_frame(1, rid="a"))  # seq must start at 0
        assert ws.receive_json()["code"] == "bad_state"
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "b", "slide": 0}))
        assert ws.receive_json()["type"] == "qa.ready"
        ws.send_text(json.dumps({"type": "qa.audio", "request_id": "b", "seq": 0, "audio": "AA AA"}))
        assert ws.receive_json()["code"] == "bad_state"


def test_demo_stt_no_speech(client, demo, monkeypatch):
    import services.voice_questions as vq

    async def no_speech(cfg, pcm, language):
        raise vq.QaError("no_speech")

    monkeypatch.setattr(vq, "transcribe_pcm", no_speech)
    with _demo_connect(client) as ws:
        _start_demo(ws)
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "a", "slide": 0}))
        assert ws.receive_json()["type"] == "qa.ready"
        ws.send_text(_frame(0, rid="a"))
        ws.send_text(json.dumps({"type": "qa.commit", "request_id": "a"}))
        err = ws.receive_json()
        assert err["code"] == "no_speech" and err["message"] and err["request_id"] == "a"


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def _admin_connect(client, session_extra=None):
    from security import VOICE_SESSIONS

    with _session(client, "/ws/voice", {}, VOICE_SESSIONS) as ws:
        ws.send_text(json.dumps({"type": "session.update",
                                 "session": {"language": "en-US", **(session_extra or {})}}))
        assert ws.receive_json()["type"] == "proxy.connected"
        yield ws


def test_admin_typed_question_and_context_switch(client, env):
    azure, calls = env
    with _admin_connect(client, {"deck_id": DECK_ID}) as ws:
        ws.send_text(json.dumps({"type": "response.cancel"}))  # normal traffic still forwarded
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "r1", "slide": 0, "mode": "now"}))
        ready = ws.receive_json()
        assert ready["type"] == "qa.ready" and ready["remaining_questions"] == 9
        assert "remaining_ms" not in ready
        ws.send_text(json.dumps({"type": "qa.text", "request_id": "r1", "text": "How much did revenue grow?"}))
        assert ws.receive_json()["type"] == "qa.transcript"
        answer = ws.receive_json()
        assert answer["type"] == "qa.answer" and answer["text"] == ANSWER
        assert wait_for(lambda: any(ANSWER in t for t in azure.spoken()))
        ws.send_text(json.dumps({"type": "qa.resume", "request_id": "r1"}))

        ws.send_text(json.dumps({"type": "context.switch", "deck_id": DECK2_ID}))
        assert ws.receive_json() == {"type": "context.switched", "deck_id": DECK2_ID, "slide_count": 1}
        ws.send_text(json.dumps({"type": "context.switch", "deck_id": "not-a-deck"}))
        err = ws.receive_json()
        assert err["type"] == "qa.error" and err["code"] == "bad_deck"
    assert calls["answer"][0]["access"] == "admin" and calls["stt"] == []
    assert "response.cancel" in azure.types()
    assert not any(t and t.startswith(("qa.", "context.")) for t in azure.types())


def test_admin_legacy_presentation_and_no_deck(client, env):
    with _admin_connect(client, {"presentation_id": LEGACY_ID}) as ws:
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "r1", "slide": 1}))
        assert ws.receive_json()["type"] == "qa.ready"
    with _admin_connect(client, {"deck_id": "8d3f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"}) as ws:
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "r1", "slide": 0}))
        assert ws.receive_json() == {"type": "qa.unavailable", "reason": "no_deck"}


def test_admin_daily_quota_applies_to_questions(client, env, monkeypatch):
    monkeypatch.setenv("DAILY_GENERATION_QUOTA", "2")  # 1 for the session + 1 question
    with _admin_connect(client, {"deck_id": DECK_ID}) as ws:
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "r1", "slide": 0}))
        assert ws.receive_json()["type"] == "qa.ready"
        ws.send_text(json.dumps({"type": "qa.cancel", "request_id": "r1"}))
        ws.send_text(json.dumps({"type": "qa.begin", "request_id": "r2", "slide": 0}))
        assert ws.receive_json()["code"] == "limit"

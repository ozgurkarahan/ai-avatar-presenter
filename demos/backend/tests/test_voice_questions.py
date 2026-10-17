"""Voice Q&A building blocks: PCM / frame validation, the speech-to-text call,
the durable daily question quota, the demo filter allow/deny matrix and the
session state machine (cancellation on disconnect)."""
from __future__ import annotations

import asyncio
import base64
import json
import struct

import httpx
import pytest

from config import load_config
from services import voice_questions as vq
from services.voice_questions import AudioCollector, QaError, QaOptions, QaSession


class Clock:
    def __init__(self, t: float = 100.0):
        self.t = t

    def __call__(self):
        return self.t


def _b64(n: int) -> str:
    return base64.b64encode(b"\x01\x00" * (n // 2)).decode()


# ---------------------------------------------------------------------------
# PCM / frames
# ---------------------------------------------------------------------------
def test_pcm_to_wav_header():
    wav = vq.pcm_to_wav(b"\x00\x01" * 100)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE" and wav[36:40] == b"data"
    assert struct.unpack("<I", wav[4:8])[0] == 36 + 200
    channels, rate = struct.unpack("<HI", wav[22:28])
    assert channels == 1 and rate == 16000
    assert struct.unpack("<H", wav[34:36])[0] == 16
    assert len(wav) == 44 + 200


@pytest.mark.parametrize("audio", [
    None, 5, "", "!!!!", "AAAA\n", "AA AA", "AAA", "data:audio/pcm;base64,AAAA",
    _b64(16_386),                  # decoded > 16384
    base64.b64encode(b"\x01").decode(),   # odd byte count
    "A" * (vq.MAX_FRAME_B64_CHARS + 4),
])
def test_decode_frame_rejects(audio):
    with pytest.raises(QaError) as exc:
        vq.decode_frame(audio)
    assert exc.value.code == "bad_state"


def test_decode_frame_accepts_max_frame():
    assert len(vq.decode_frame(_b64(16_384))) == 16_384


def test_collector_strict_seq_and_total():
    clock = Clock()
    col = AudioCollector(max_bytes=8, clock=clock)
    col.add(0, _b64(4))
    with pytest.raises(QaError) as exc:
        col.add(2, _b64(2))
    assert exc.value.code == "bad_state"
    with pytest.raises(QaError):
        col.add(True, _b64(2))
    col.add(1, _b64(4))
    with pytest.raises(QaError) as exc:
        col.add(2, _b64(2))
    assert exc.value.code == "too_long"
    assert col.size == 8 and len(col.pcm()) == 8
    col.clear()
    assert col.pcm() == b""


def test_collector_default_limits_15_seconds():
    assert vq.MAX_AUDIO_BYTES == 480_000 and vq.MAX_AUDIO_MS == 15_000 and vq.MAX_FRAME_BYTES == 16_384


def test_collector_rate_bucket():
    clock = Clock()
    col = AudioCollector(rate=40, clock=clock)
    for seq in range(40):                 # burst of 40 frames is fine
        col.add(seq, _b64(2))
    with pytest.raises(QaError) as exc:   # the 41st in the same instant is not
        col.add(40, _b64(2))
    assert exc.value.code == "rate"
    clock.t += 0.05                       # refills 2 tokens
    col.add(40, _b64(2))


def test_invites_localised_with_english_fallback():
    assert vq.invite_text("fr-FR") == "Allez-y, je vous écoute."
    assert vq.invite_text("pt-BR").startswith("Pode falar")
    assert vq.invite_text("ko-KR") == vq.invite_text(None) == "Go ahead, I'm listening."
    for lang in ("en", "fr", "es", "de", "it", "pt", "zh", "ja"):
        assert vq.INVITES[lang]


# ---------------------------------------------------------------------------
# transcribe_pcm (mocked HTTP)
# ---------------------------------------------------------------------------
@pytest.fixture
def stt_cfg(monkeypatch):
    vq.reset_token_cache()
    monkeypatch.setattr(vq, "_aad_token", lambda: "aad-token")
    cfg = load_config()
    cfg.speech_endpoint = "https://res.cognitiveservices.azure.com/"
    cfg.speech_region = "swedencentral"
    cfg.speech_key = ""
    yield cfg
    vq.reset_token_cache()


def _transport(stt_response, calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/sts/v1.0/issuetoken":
            assert request.headers["authorization"] == "Bearer aad-token"
            return httpx.Response(200, text="speech-jwt")
        return stt_response(request)
    return httpx.MockTransport(handler)


def test_transcribe_success_uses_sts_token_and_caches_it(stt_cfg):
    calls: list[httpx.Request] = []
    ok = lambda req: httpx.Response(200, json={"RecognitionStatus": "Success", "DisplayText": "Quel\u00a0prix ?"})
    t = _transport(ok, calls)
    text = asyncio.run(vq.transcribe_pcm(stt_cfg, b"\x00\x00" * 1600, "fr-FR", transport=t))
    assert text == "Quel prix ?"
    stt = calls[-1]
    assert stt.url.host == "swedencentral.stt.speech.microsoft.com"
    assert stt.url.params["language"] == "fr-FR" and stt.url.params["format"] == "simple"
    assert stt.headers["authorization"] == "Bearer speech-jwt"
    assert stt.headers["content-type"] == "audio/wav; codecs=audio/pcm; samplerate=16000"
    assert stt.content[:4] == b"RIFF"
    # Second call reuses the cached STS token (no new issuetoken request).
    asyncio.run(vq.transcribe_pcm(stt_cfg, b"\x00\x00" * 1600, "fr-FR", transport=t))
    assert sum(1 for c in calls if c.url.path == "/sts/v1.0/issuetoken") == 1


def test_transcribe_key_path(stt_cfg):
    stt_cfg.speech_key = "k3y"
    calls: list[httpx.Request] = []
    ok = lambda req: httpx.Response(200, json={"RecognitionStatus": "Success", "DisplayText": "Hi"})
    asyncio.run(vq.transcribe_pcm(stt_cfg, b"\x00\x00", "xx-XX", transport=_transport(ok, calls)))
    assert len(calls) == 1 and calls[0].headers["ocp-apim-subscription-key"] == "k3y"
    assert calls[0].url.params["language"] == "en-US"


@pytest.mark.parametrize("body", [
    {"RecognitionStatus": "NoMatch"},
    {"RecognitionStatus": "InitialSilenceTimeout"},
    {"RecognitionStatus": "Success", "DisplayText": "  "},
])
def test_transcribe_no_speech(stt_cfg, body):
    t = _transport(lambda req: httpx.Response(200, json=body), [])
    with pytest.raises(QaError) as exc:
        asyncio.run(vq.transcribe_pcm(stt_cfg, b"\x00\x00", "en-US", transport=t))
    assert exc.value.code == "no_speech"


def test_transcribe_401_is_stt_failed_and_drops_token(stt_cfg):
    t = _transport(lambda req: httpx.Response(401, text="nope"), [])
    with pytest.raises(QaError) as exc:
        asyncio.run(vq.transcribe_pcm(stt_cfg, b"\x00\x00", "en-US", transport=t))
    assert exc.value.code == "stt_failed"
    assert vq._sts_cache == {}


def test_transcribe_timeout_is_stt_failed(stt_cfg):
    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)
    with pytest.raises(QaError) as exc:
        asyncio.run(vq.transcribe_pcm(stt_cfg, b"\x00\x00", "en-US", transport=_transport(boom, [])))
    assert exc.value.code == "stt_failed"


def test_transcribe_sts_failure_and_missing_endpoint(stt_cfg):
    def handler(request):
        return httpx.Response(403, text="forbidden")
    with pytest.raises(QaError) as exc:
        asyncio.run(vq.transcribe_pcm(stt_cfg, b"\x00\x00", "en-US", transport=httpx.MockTransport(handler)))
    assert exc.value.code == "stt_failed"
    stt_cfg.speech_endpoint = ""
    with pytest.raises(QaError) as exc:
        asyncio.run(vq.transcribe_pcm(stt_cfg, b"\x00\x00", "en-US", transport=httpx.MockTransport(handler)))
    assert exc.value.code == "stt_failed"


def test_transcribe_truncates_and_rejects_empty_audio(stt_cfg):
    t = _transport(lambda req: httpx.Response(200, json={"RecognitionStatus": "Success", "DisplayText": "a" * 900}), [])
    assert len(asyncio.run(vq.transcribe_pcm(stt_cfg, b"\x00\x00", "en-US", transport=t))) == 500
    with pytest.raises(QaError) as exc:
        asyncio.run(vq.transcribe_pcm(stt_cfg, b"", "en-US", transport=t))
    assert exc.value.code == "no_speech"


# ---------------------------------------------------------------------------
# Durable daily question quota (same Cosmos doc / etag mechanism)
# ---------------------------------------------------------------------------
def _quota(store):
    from security import DemoQuota

    q = DemoQuota()
    q.set_store(store)
    return q


def test_question_quota_per_ip_and_global(monkeypatch):
    from test_demo_quota_durable import FakeStore

    monkeypatch.setenv("DEMO_QA_DAILY_MAX", "3")
    monkeypatch.setenv("DEMO_QA_DAILY_PER_IP", "2")
    store = FakeStore()
    q = _quota(store)
    assert q.try_reserve_question("198.51.100.1") is None
    assert q.try_reserve_question("198.51.100.1") is None
    assert q.try_reserve_question("198.51.100.1") == "ip"
    assert _quota(store).try_reserve_question("198.51.100.2") is None   # survives "restart"
    assert q.try_reserve_question("198.51.100.3") == "global"
    doc = next(iter(store.docs.values()))[0]
    assert doc["questions"] == 3 and doc["id"].startswith("demo-quota-")
    assert "198.51.100.1" not in json.dumps(store.docs)
    # Sessions budget untouched by question reservations.
    assert doc["total"] == 0


def test_question_quota_fails_closed_and_retries(monkeypatch):
    from test_demo_quota_durable import FakeStore

    store = FakeStore()
    store.conflicts_to_inject = 2
    assert _quota(store).try_reserve_question("192.0.2.1") is None
    store.conflicts_to_inject = 100
    assert _quota(store).try_reserve_question("192.0.2.1") == "busy"
    store.conflicts_to_inject = 0
    store.fail = True
    assert _quota(store).try_reserve_question("192.0.2.1") == "unavailable"


def test_question_quota_in_memory(monkeypatch):
    from security import DemoQuota

    monkeypatch.setenv("DEMO_QA_DAILY_PER_IP", "1")
    q = DemoQuota()
    assert q.try_reserve_question("192.0.2.9") is None
    assert q.try_reserve_question("192.0.2.9") == "ip"
    assert q.try_consume("192.0.2.9") is None   # sessions are a separate counter


def test_effective_session_seconds(monkeypatch):
    from security import effective_demo_session_seconds

    assert effective_demo_session_seconds() == 180
    monkeypatch.setenv("DEMO_QA_ENABLED", "true")
    assert effective_demo_session_seconds() == 300


# ---------------------------------------------------------------------------
# Demo filter allow/deny matrix + admin interception
# ---------------------------------------------------------------------------
def _flt():
    from services.voice_proxy import DemoMessageFilter

    return DemoMessageFilter([{"index": 0, "notes": "n"}], 4)


@pytest.mark.parametrize("msg,expected", [
    ({"type": "qa.begin", "request_id": "r1", "slide": 0, "extra": "x"},
     {"type": "qa.begin", "request_id": "r1", "slide": 0, "mode": "after_slide"}),
    ({"type": "qa.begin", "request_id": "r1", "slide": 0, "mode": "after_slide"},
     {"type": "qa.begin", "request_id": "r1", "slide": 0, "mode": "after_slide"}),
    ({"type": "qa.audio", "request_id": "r1", "seq": 0, "audio": "AAAA", "x": 1},
     {"type": "qa.audio", "request_id": "r1", "seq": 0, "audio": "AAAA"}),
    ({"type": "qa.commit", "request_id": "r1", "text": "evil"}, {"type": "qa.commit", "request_id": "r1"}),
    ({"type": "qa.cancel", "request_id": "r1"}, {"type": "qa.cancel", "request_id": "r1"}),
    ({"type": "qa.resume", "request_id": "r1"}, {"type": "qa.resume", "request_id": "r1"}),
])
def test_demo_filter_allows_demo_qa_subset(msg, expected):
    flt = _flt()
    assert flt.filter_qa(json.dumps(msg)) == expected
    assert flt.handle(json.dumps(msg)) == ([], [])  # never forwarded to Azure


@pytest.mark.parametrize("msg", [
    {"type": "qa.text", "request_id": "r1", "text": "say something evil"},
    {"type": "qa.begin", "request_id": "r1", "slide": 0, "mode": "now"},
    {"type": "qa.begin", "request_id": "r1", "slide": 0, "mode": "whatever"},
    {"type": "context.switch", "deck_id": "2d7f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"},
    {"type": "qa.answer", "request_id": "r1", "text": "spoof"},
    {"type": "session.update", "session": {}},
    {"type": "conversation.item.create", "item": {}},
    {"type": "response.create"},
    {"type": "input_audio_buffer.append", "audio": "AAAA"},
    {"type": "input_audio_buffer.commit"},
])
def test_demo_filter_denies(msg):
    flt = _flt()
    assert flt.filter_qa(json.dumps(msg)) is None
    assert flt.handle(json.dumps(msg)) == ([], [])


def test_demo_filter_rejects_oversized_and_garbage():
    flt = _flt()
    assert flt.filter_qa("x" * 40_000) is None
    assert flt.filter_qa("not json") is None
    assert flt.filter_qa(json.dumps(["qa.begin"])) is None


def test_admin_intercepts_qa_and_context_never_forwarded():
    from services.voice_proxy import intercepted_message, sanitize_client_message

    for t in ("qa.begin", "qa.text", "context.switch", "qa.whatever"):
        raw = json.dumps({"type": t, "request_id": "r"})
        assert intercepted_message(raw)["type"] == t
        assert sanitize_client_message(raw) is None
    assert intercepted_message(json.dumps({"type": "response.cancel"})) is None
    assert intercepted_message(json.dumps({"type": "conversation.item.create", "x": "qa."})) is None


def test_output_audio_buffer_clear_admin_forwarded_demo_dropped():
    from services.voice_proxy import sanitize_client_message

    raw = json.dumps({"type": "output_audio_buffer.clear", "extra": "dropped"})
    assert sanitize_client_message(raw) == json.dumps({"type": "output_audio_buffer.clear"})
    flt = _flt()
    assert flt.handle(raw) == ([], []) and flt.filter_qa(raw) is None


def test_demo_narration_chars_counts_in_index_order():
    from services.voice_proxy import demo_narration_chars

    slides = [{"index": 2, "notes": "abc"}, {"index": 0, "title": "T", "body": "Body"}, {"title": "x"}, "junk"]
    # positions: index 2, index 0, index 2 (dup, ignored), junk skipped
    assert demo_narration_chars(slides) == [len("T. Body"), 3]
    assert demo_narration_chars([]) == []


def test_session_config_requests_word_timestamps():
    from services.voice_proxy import build_demo_session_config, build_session_config

    assert build_session_config()["output_audio_timestamp_types"] == ["word"]
    assert build_demo_session_config("en-US")[0]["output_audio_timestamp_types"] == ["word"]


def test_word_timestamp_events_are_forwarded_to_the_browser():
    from services.voice_proxy import _forward_azure_to_client

    evt = json.dumps({"type": "response.audio_timestamp.delta", "audio_offset_ms": 120,
                      "audio_duration_ms": 300, "text": "Hello", "timestamp_type": "word"})

    class Azure:
        def __init__(self):
            self.items = [evt, json.dumps({"type": "response.audio_timestamp.done"})]

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    class Client:
        out: list = []

        async def send_text(self, data):
            self.out.append(data)

    client = Client()
    asyncio.run(_forward_azure_to_client(Azure(), client))
    assert client.out[0] == evt and len(client.out) == 2


# ---------------------------------------------------------------------------
# QaSession state machine (unit)
# ---------------------------------------------------------------------------
SLIDES = [{"index": 0, "title": "Intro", "notes": "Hello"}, {"index": 1, "title": "Revenue", "body": "Up 12%"}]


def _session(opts=None, clock=None):
    sent: list[dict] = []
    spoken: list[str] = []

    async def send(m):
        sent.append(m)

    async def speak(t):
        spoken.append(t)

    opts = opts or QaOptions(access="admin", slides=SLIDES, language="en-US")
    return QaSession(opts, cfg=load_config(), send_client=send, speak=speak,
                     clock=clock or Clock()), sent, spoken


def test_disconnect_cancels_inflight_stt(monkeypatch):
    started = asyncio.Event()
    cancelled = []

    async def slow_stt(cfg, pcm, language):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    monkeypatch.setattr(vq, "transcribe_pcm", slow_stt)

    async def run():
        s, sent, spoken = _session()
        await s.handle({"type": "qa.begin", "request_id": "r1", "slide": 0})
        await s.handle({"type": "qa.audio", "request_id": "r1", "seq": 0, "audio": _b64(320)})
        await s.handle({"type": "qa.commit", "request_id": "r1"})
        await asyncio.wait_for(started.wait(), 2)
        task = s._task
        s.close()
        await asyncio.gather(task, return_exceptions=True)
        return s, sent

    s, sent = asyncio.run(run())
    assert cancelled == [True]
    assert s.state == "idle" and s.audio is None
    assert [m["type"] for m in sent] == ["qa.ready"]


def test_one_in_flight_and_session_limit(monkeypatch):
    async def run():
        s, sent, _ = _session(QaOptions(access="admin", slides=SLIDES, max_questions=2))
        await s.handle({"type": "qa.begin", "request_id": "a", "slide": 0})
        await s.handle({"type": "qa.begin", "request_id": "b", "slide": 0})
        await s.handle({"type": "qa.cancel", "request_id": "a"})
        await s.handle({"type": "qa.begin", "request_id": "c", "slide": 1, "mode": "now"})
        await s.handle({"type": "qa.cancel", "request_id": "c"})
        await s.handle({"type": "qa.begin", "request_id": "d", "slide": 0})
        return sent

    sent = asyncio.run(run())
    assert [(m["type"], m.get("code")) for m in sent] == [
        ("qa.ready", None), ("qa.error", "bad_state"), ("qa.ready", None), ("qa.error", "limit")]
    assert sent[0]["remaining_questions"] == 1 and sent[2]["remaining_questions"] == 0
    assert "remaining_ms" not in sent[0]  # admin: no demo clock


def test_audio_errors_reset_question(monkeypatch):
    async def run():
        s, sent, _ = _session()
        await s.handle({"type": "qa.audio", "request_id": "r1", "seq": 0, "audio": _b64(2)})  # before begin
        await s.handle({"type": "qa.begin", "request_id": "r1", "slide": 0})
        await s.handle({"type": "qa.audio", "request_id": "r1", "seq": 1, "audio": _b64(2)})  # bad seq
        await s.handle({"type": "qa.commit", "request_id": "r1"})                               # now idle
        await s.handle({"type": "qa.begin", "request_id": "r2", "slide": 0})
        await s.handle({"type": "qa.commit", "request_id": "r2"})                               # no audio
        await s.handle({"type": "qa.begin", "request_id": "bad id!", "slide": 0})
        await s.handle({"type": "qa.begin", "request_id": "r3", "slide": "1"})
        return sent

    codes = [(m["type"], m.get("code")) for m in asyncio.run(run())]
    assert codes == [("qa.error", "bad_state"), ("qa.ready", None), ("qa.error", "bad_state"),
                     ("qa.error", "bad_state"), ("qa.ready", None), ("qa.error", "no_speech"),
                     ("qa.error", "bad_state"), ("qa.error", "bad_state")]


def test_daily_reservation_refusal_and_store_error():
    async def refuse():
        return "ip"

    async def broken():
        raise RuntimeError("cosmos down")

    async def run(reserve):
        s, sent, spoken = _session(QaOptions(access="demo", slides=SLIDES, max_questions=2, reserve_daily=reserve))
        await s.handle({"type": "qa.begin", "request_id": "r1", "slide": 0})
        return s, sent, spoken

    for reserve in (refuse, broken):
        s, sent, spoken = asyncio.run(run(reserve))
        assert sent[0]["code"] == "limit" and spoken == [] and s.state == "idle"


def test_demo_time_low_and_remaining_ms():
    clock = Clock(1000.0)
    opts = QaOptions(access="demo", slides=SLIDES, max_questions=2, deadline=1029.5)

    async def run():
        s, sent, spoken = _session(opts, clock)
        await s.handle({"type": "qa.begin", "request_id": "r1", "slide": 0})
        return sent, spoken

    sent, spoken = asyncio.run(run())
    assert sent[0]["code"] == "time_low" and sent[0]["remaining_ms"] == 29_500 and spoken == []


def test_unavailable_without_deck_and_context_switch():
    async def loader(deck_id):
        return SLIDES if deck_id == "2d7f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b" else None

    async def run():
        s, sent, _ = _session(QaOptions(access="admin", slides=None, deck_loader=loader))
        await s.handle({"type": "qa.begin", "request_id": "r1", "slide": 0})
        await s.handle({"type": "context.switch", "deck_id": "nope"})
        await s.handle({"type": "context.switch", "deck_id": "2d7f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"})
        await s.handle({"type": "qa.begin", "request_id": "r2", "slide": 0})
        return sent

    sent = asyncio.run(run())
    assert sent[0] == {"type": "qa.unavailable", "reason": "no_deck"}
    assert sent[1]["type"] == "qa.error" and sent[1]["code"] == "bad_deck"
    assert sent[2] == {"type": "context.switched", "deck_id": "2d7f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b",
                       "slide_count": 2}
    assert sent[3]["type"] == "qa.ready"


# ---------------------------------------------------------------------------
# Listening watchdog
# ---------------------------------------------------------------------------
def test_listen_timeout_without_commit(monkeypatch):
    monkeypatch.setattr(vq, "MAX_AUDIO_MS", 50)
    monkeypatch.setattr(vq, "LISTEN_GRACE_SECONDS", 0.05)

    async def run():
        s, sent, _ = _session(QaOptions(access="admin", slides=SLIDES, max_questions=3))
        await s.handle({"type": "qa.begin", "request_id": "r1", "slide": 0})
        await asyncio.sleep(0.3)
        state = s.state
        await s.handle({"type": "qa.begin", "request_id": "r2", "slide": 0})  # slot released
        return s, sent, state

    s, sent, state = asyncio.run(run())
    assert state == "idle"
    assert [(m["type"], m.get("code"), m.get("request_id")) for m in sent] == [
        ("qa.ready", None, "r1"), ("qa.error", "no_speech", "r1"), ("qa.ready", None, "r2")]
    assert s.used == 2  # the timed-out question stays consumed


def test_listen_timeout_when_frames_stop(monkeypatch):
    monkeypatch.setattr(vq, "FRAME_IDLE_SECONDS", 0.1)

    async def run():
        s, sent, _ = _session()
        await s.handle({"type": "qa.begin", "request_id": "r1", "slide": 0})
        await asyncio.sleep(0.2)            # no frames yet: invite playing, no idle timeout
        assert s.state == "listening"
        await s.handle({"type": "qa.audio", "request_id": "r1", "seq": 0, "audio": _b64(320)})
        await asyncio.sleep(0.3)            # frames stopped > FRAME_IDLE_SECONDS
        return s, sent

    s, sent = asyncio.run(run())
    assert s.state == "idle" and s.audio is None
    assert sent[-1]["code"] == "no_speech"


def test_watchdog_stopped_by_commit_and_cancel(monkeypatch):
    monkeypatch.setattr(vq, "MAX_AUDIO_MS", 50)
    monkeypatch.setattr(vq, "LISTEN_GRACE_SECONDS", 0.05)

    async def stt(cfg, pcm, language):
        return "q?"

    async def answer(*a, **k):
        return {"answer": "A.", "source_slides": [0], "grounded": True}

    monkeypatch.setattr(vq, "transcribe_pcm", stt)
    monkeypatch.setattr(vq.deck_qa, "answer_deck_question", answer)

    async def run():
        s, sent, _ = _session()
        await s.handle({"type": "qa.begin", "request_id": "r1", "slide": 0})
        await s.handle({"type": "qa.cancel", "request_id": "r1"})
        await s.handle({"type": "qa.begin", "request_id": "r2", "slide": 0})
        await s.handle({"type": "qa.audio", "request_id": "r2", "seq": 0, "audio": _b64(320)})
        await s.handle({"type": "qa.commit", "request_id": "r2"})
        await asyncio.sleep(0.3)
        return s, sent

    s, sent = asyncio.run(run())
    assert [m["type"] for m in sent] == ["qa.ready", "qa.ready", "qa.transcript", "qa.answer"]
    assert s.state == "answered"

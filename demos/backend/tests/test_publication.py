"""Publication boundary: anonymous callers only see published items as public DTOs."""
from __future__ import annotations

import pytest

UUID_PUB = "0b5f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
UUID_PRIV = "1c6f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"

VIDEO_PUBLIC_KEYS = {
    "job_id", "title", "created_at", "duration_sec", "language", "thumbnail_url", "video_url",
    "audio_url", "srt_url", "scorm_url", "script",
}
PODCAST_PUBLIC_KEYS = VIDEO_PUBLIC_KEYS | {"mp4_url", "mp3_url"}


class FakeLibrary:
    """Mimics VideoLibrary / PodcastLibrary without blob storage."""

    def __init__(self, kind: str):
        self.kind = kind
        self.available = True
        pfx = "sv-" if kind == "video" else "job-"
        self.items = {
            f"{pfx}0000aaaa": {"job_id": f"{pfx}0000aaaa", "title": "Public", "created_at": "2026-01-02",
                               "duration_sec": 12.5, "language": "en-US", "published": True,
                               "document_title": "secret doc", "voice": "en-US-Ava:DragonHDLatestNeural",
                               "speaker_names": ["A", "B"]},
            f"{pfx}0000bbbb": {"job_id": f"{pfx}0000bbbb", "title": "Private", "created_at": "2026-01-01",
                               "duration_sec": 3.0, "language": "fr-FR", "published": False},
        }
        self.sas_minutes: list[int] = []
        self.published_calls: list = []

    def list(self, *, published_only: bool = False):
        out = []
        for it in self.items.values():
            if published_only and not it["published"]:
                continue
            out.append({**it, "thumbnail_url": "https://blob/thumb?sas"})
        return out

    def get(self, job_id, *, public: bool = False):
        it = self.items.get(job_id)
        if not it:
            return None
        if public and not it["published"]:
            return None
        full = {**it, "thumbnail_url": "https://blob/thumb?sas"}
        if self.kind == "video":
            full.update(video_url="https://blob/video?sas", audio_url=None if public else "https://blob/a",
                        srt_url=None if public else "https://blob/s", scorm_url=None if public else "https://blob/z")
        else:
            full.update(mp4_url="https://blob/video?sas", mp3_url=None if public else "https://blob/a",
                        srt_url=None if public else "https://blob/s", scorm_url=None if public else "https://blob/z")
        return full

    def set_published(self, job_id, published):
        if job_id not in self.items:
            return None
        self.published_calls.append((job_id, published))
        self.items[job_id]["published"] = published
        return self.get(job_id)

    def delete(self, job_id):
        return self.items.pop(job_id, None) is not None


@pytest.fixture
def video_lib(monkeypatch):
    import routers.video as sv

    lib = FakeLibrary("video")
    monkeypatch.setattr(sv, "_get_library", lambda cfg: lib)
    return lib


@pytest.fixture
def podcast_lib(monkeypatch):
    import routers.podcast as pc

    lib = FakeLibrary("podcast")
    monkeypatch.setattr(pc, "_get_library", lambda cfg: lib)
    return lib


# ---------------------------------------------------------------------------
# Video library
# ---------------------------------------------------------------------------
def test_video_anonymous_list_only_published(client, easyauth, video_lib):
    r = client.get("/api/video/library")
    assert r.status_code == 200
    items = r.json()
    assert [i["job_id"] for i in items] == ["sv-0000aaaa"]
    assert set(items[0]) == VIDEO_PUBLIC_KEYS
    assert items[0]["audio_url"] is None and items[0]["srt_url"] is None and items[0]["scorm_url"] is None
    assert "document_title" not in items[0] and "voice" not in items[0]


def test_video_anonymous_detail(client, easyauth, video_lib):
    r = client.get("/api/video/library/sv-0000aaaa")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == VIDEO_PUBLIC_KEYS
    assert body["video_url"] and body["audio_url"] is None and body["scorm_url"] is None
    assert client.get("/api/video/library/sv-0000bbbb").status_code == 404


def test_video_admin_sees_everything(client, easyauth, video_lib):
    r = client.get("/api/video/library", headers=easyauth())
    assert {i["job_id"]: i["published"] for i in r.json()} == {"sv-0000aaaa": True, "sv-0000bbbb": False}
    r = client.get("/api/video/library/sv-0000bbbb", headers=easyauth())
    assert r.status_code == 200 and r.json()["audio_url"] and r.json()["published"] is False


def test_video_publish_flow(client, easyauth, video_lib):
    assert client.post("/api/video/library/sv-0000bbbb/publish", json={"published": True}).status_code == 401
    r = client.post("/api/video/library/sv-0000bbbb/publish", json={"published": True}, headers=easyauth())
    assert r.status_code == 200 and r.json()["published"] is True
    assert video_lib.published_calls == [("sv-0000bbbb", True)]
    assert len(client.get("/api/video/library").json()) == 2
    assert client.post("/api/video/library/sv-0000cccc/publish", json={"published": True},
                       headers=easyauth()).status_code == 404


# ---------------------------------------------------------------------------
# Podcast library
# ---------------------------------------------------------------------------
def test_podcast_anonymous_list_and_detail(client, easyauth, podcast_lib):
    items = client.get("/api/podcast/library").json()
    assert [i["job_id"] for i in items] == ["job-0000aaaa"]
    assert set(items[0]) == PODCAST_PUBLIC_KEYS
    assert "speaker_names" not in items[0]
    body = client.get("/api/podcast/library/job-0000aaaa").json()
    assert set(body) == PODCAST_PUBLIC_KEYS
    assert body["mp4_url"] == body["video_url"] and body["mp4_url"]
    assert body["mp3_url"] is None and body["srt_url"] is None and body["scorm_url"] is None
    assert client.get("/api/podcast/library/job-0000bbbb").status_code == 404


def test_podcast_publish_admin_only(client, easyauth, podcast_lib):
    from _helpers import OTHER_OID

    assert client.post("/api/podcast/library/job-0000bbbb/publish", json={"published": True},
                       headers=easyauth(oid=OTHER_OID)).status_code == 403
    r = client.post("/api/podcast/library/job-0000bbbb/publish", json={"published": True}, headers=easyauth())
    assert r.status_code == 200 and r.json()["published"] is True


# ---------------------------------------------------------------------------
# Library classes: unpublished hidden, 15-minute SAS, video/thumb only
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["video", "podcast"])
def test_library_public_get_uses_short_sas(kind):
    from config import load_config

    if kind == "video":
        from services.video_library import PUBLIC_SAS_MINUTES, VideoLibrary as Lib
        job, video_key, extra = "sv-0123abcd", "video_url", ("audio_url", "srt_url", "scorm_url")
    else:
        from services.podcast_library import PUBLIC_SAS_MINUTES, PodcastLibrary as Lib
        job, video_key, extra = "job-0123abcd", "mp4_url", ("mp3_url", "srt_url", "scorm_url")

    lib = Lib(load_config())
    lib._initialised = True
    lib._blob = object()
    manifest = {"job_id": job, "title": "t", "video_blob": "v", "thumbnail_blob": "t",
                "audio_blob": "a", "subtitle_blob": "s", "scorm_blob": "z"}
    lib._read_json_blob = lambda name: dict(manifest)  # type: ignore[assignment]
    minted: list[tuple[str, int]] = []
    lib._sas = lambda blob, minutes=24 * 60: minted.append((blob, minutes)) or f"sas:{blob}"  # type: ignore[assignment]

    assert lib.get(job, public=True) is None  # published flag absent => false
    manifest["published"] = True
    item = lib.get(job, public=True)
    assert item[video_key] == "sas:v"
    assert all(item[k] is None for k in extra)
    assert {b for b, _ in minted} == {"v", "t"}
    assert all(m == PUBLIC_SAS_MINUTES == 15 for _, m in minted)
    assert lib.get("../" + job, public=True) is None


# ---------------------------------------------------------------------------
# Decks catalog
# ---------------------------------------------------------------------------
class FakeStore:
    cosmos_available = True
    available = False

    def __init__(self):
        slides = [{"index": 0, "title": "Intro", "body": "BODY-TEXT", "notes": "SECRET-NOTES",
                   "image_url": "https://blob/0.png?old-sas"}]
        self.docs = {
            UUID_PUB: {"id": UUID_PUB, "source": "deck", "filename": "Public.pptx", "slide_count": 1,
                       "published": True, "pptx_url": "https://blob/x.pptx", "slides": slides},
            UUID_PRIV: {"id": UUID_PRIV, "source": "deck", "filename": "Private.pptx", "slide_count": 1,
                        "slides": slides},
        }

    def list_decks(self):
        return [{k: v for k, v in d.items() if k != "slides"} for d in self.docs.values()]

    def get_presentation(self, pid):
        return self.docs.get(pid)

    def set_deck_published(self, pid, published):
        d = self.docs.get(pid)
        if not d:
            return None
        d["published"] = published
        return d


@pytest.fixture
def decks_store(monkeypatch):
    import routers.decks as decks

    st = FakeStore()
    monkeypatch.setattr(decks, "_store", lambda cfg: st)
    return st


def test_decks_anonymous_list_only_published(client, easyauth, decks_store):
    decks = client.get("/api/decks").json()
    assert [d["deck_id"] for d in decks] == [UUID_PUB]
    admin = client.get("/api/decks", headers=easyauth()).json()
    assert {d["deck_id"] for d in admin} == {UUID_PUB, UUID_PRIV}


def test_decks_anonymous_detail_has_no_notes_body_or_pptx(client, easyauth, decks_store):
    r = client.get(f"/api/decks/{UUID_PUB}")
    assert r.status_code == 200
    text = r.text
    assert "SECRET-NOTES" not in text and "BODY-TEXT" not in text
    assert "pptx_url" not in r.json() and "old-sas" not in text
    slide = r.json()["slides"][0]
    assert slide["title"] == "Intro" and slide["image_url"] == f"/api/slides/{UUID_PUB}/0.png"
    assert client.get(f"/api/decks/{UUID_PRIV}").status_code == 404
    admin = client.get(f"/api/decks/{UUID_PRIV}", headers=easyauth()).json()
    assert admin["slides"][0]["notes"] == "SECRET-NOTES"


def test_decks_publish(client, easyauth, decks_store):
    assert client.post(f"/api/decks/{UUID_PRIV}/publish", json={"published": True}).status_code == 401
    r = client.post(f"/api/decks/{UUID_PRIV}/publish", json={"published": True}, headers=easyauth())
    assert r.status_code == 200 and r.json()["published"] is True
    assert len(client.get("/api/decks").json()) == 2


# ---------------------------------------------------------------------------
# Legacy /api/presentations — admin only, tolerant of malformed items
# ---------------------------------------------------------------------------
def test_presentations_list_skips_malformed_items(client, app_module, monkeypatch):
    class Store:
        cosmos_available = True
        available = False

        def list_presentations(self):
            return [
                {"id": UUID_PUB, "slide_count": 3},                       # no filename
                {"id": UUID_PRIV, "filename": "deck.pptx", "slide_count": None},
                {"id": "pl_0123456789ab", "title": "a playlist"},         # not a presentation
                {"filename": "orphan.pptx"},                              # no id
            ]

    monkeypatch.setattr(app_module, "store", Store())
    r = client.get("/api/presentations")
    assert r.status_code == 200
    assert r.json() == [
        {"id": UUID_PUB, "filename": UUID_PUB, "slide_count": 3},
        {"id": UUID_PRIV, "filename": "deck.pptx", "slide_count": 0},
    ]

"""maintenance.content — operator CLI for seeding/rendering/purging content.

Fully offline: the Cosmos store, blob libraries, OpenAI script generators and
render workers are replaced with in-memory fakes.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from maintenance import content as mc
from services import avatar_registry
from services.podcast_models import DialogueTurn
from services.video_models import SlideNarration

CUSTOM = json.dumps([
    {"id": "photo_female", "display_name": "Sofia", "character": "F_char",
     "gender": "female", "thumbnail": "photo_female.png", "default": True},
    {"id": "photo_male", "display_name": "Lucas", "character": "M_char",
     "gender": "male", "thumbnail": "photo_male.png"},
])

OLD_DECKS = {
    "climate-action": "340f50b9-c198-4453-aef4-e89295647ab6",
    "transition-energetique": "0f26e968-a26e-417e-a73f-c40a47ec3e16",
}


class FakeStore:
    cosmos_available = True
    available = True

    def __init__(self):
        self.docs: dict[str, dict] = {}

    def get_presentation(self, pid):
        d = self.docs.get(pid)
        return dict(d) if d else None

    def list_decks(self):
        return [dict(d) for d in self.docs.values() if d.get("source") == "deck"]

    def save_presentation(self, doc):
        self.docs[doc["id"]] = dict(doc)
        return True

    def set_deck_published(self, deck_id, published):
        from services.storage import PresentationStore
        return PresentationStore.set_deck_published(self, deck_id, published)  # type: ignore[arg-type]

    def set_deck_live_demo(self, deck_id, enabled):
        from services.storage import PresentationStore
        return PresentationStore.set_deck_live_demo(self, deck_id, enabled)  # type: ignore[arg-type]

    def delete_presentation(self, pid):
        return self.docs.pop(pid, None) is not None

    def delete_slide_images(self, pid):
        return True

    def list_playlists(self):
        return [dict(d) for d in self.docs.values() if d.get("source") == "playlist"]

    def get_playlist(self, pid):
        d = self.docs.get(pid)
        return dict(d) if d and d.get("source") == "playlist" else None

    def save_playlist(self, doc):
        self.docs[doc["id"]] = dict(doc)
        return True

    def delete_playlist(self, pid):
        return self.docs.pop(pid, None) is not None

    def playlists_referencing_deck(self, deck_id):
        return [p for p in self.list_playlists() if any(s["deck_id"] == deck_id for s in p.get("steps", []))]


class FakeLibrary:
    available = True

    def __init__(self, prefix):
        self.prefix = prefix
        self.items: dict[str, dict] = {}

    def add(self, job_id, title, published=True, **extra):
        self.items[job_id] = {"job_id": job_id, "title": title, "published": published,
                              "thumbnail_url": "https://x/thumb?sig=SECRET", **extra}

    def list(self, published_only=False):
        return [dict(i) for i in self.items.values() if i["published"] or not published_only]

    def set_published(self, job_id, published):
        if job_id not in self.items:
            return None
        self.items[job_id]["published"] = published
        return dict(self.items[job_id])

    def delete(self, job_id):
        return self.items.pop(job_id, None) is not None


@pytest.fixture
def env(monkeypatch, tmp_path):
    from routers import decks as dr
    from routers import playlists as plr
    from routers import podcast as pr
    from routers import video as vr

    avatar_registry.reload(CUSTOM)
    monkeypatch.chdir(tmp_path)
    store = FakeStore()
    plib, vlib = FakeLibrary("podcast"), FakeLibrary("video")
    monkeypatch.setattr(dr, "_store", lambda cfg: store)
    monkeypatch.setattr(plr, "_store", lambda cfg: store)
    monkeypatch.setattr(pr, "_get_library", lambda cfg: plib)
    monkeypatch.setattr(vr, "_get_library", lambda cfg: vlib)

    uploads: list[tuple[str, str]] = []

    def fake_ingest(content, filename, language, cfg):
        assert content[:4] == b"PK\x03\x04"
        deck_id = str(uuid.uuid4())
        store.docs[deck_id] = {
            "id": deck_id, "source": "deck", "filename": filename, "slide_count": 5,
            "language": language or "en-US", "published": False, "live_demo": False,
            "slides": [{"index": 0, "title": "t", "notes": "n"}],
        }
        uploads.append((filename, language))
        return dr.UploadResponse(deck_id=deck_id, title=filename.rsplit(".", 1)[0], slide_count=5,
                                 indexed_slides=5)

    translations: list[tuple[str, str]] = []

    async def fake_translate(deck_id, lang, cfg, *, charge=None):
        assert charge is None
        translations.append((deck_id, lang))
        return dr.TranslateDeckNotesResponse(deck_id=deck_id, target_language=lang,
                                             translated_notes={"0": "x"}, cached=False)

    monkeypatch.setattr(dr, "ingest_deck_bytes", fake_ingest)
    monkeypatch.setattr(dr, "translate_deck_notes_for", fake_translate)

    class Env:
        pass

    e = Env()
    e.store, e.plib, e.vlib, e.uploads, e.translations = store, plib, vlib, uploads, translations
    from config import load_config

    e.cfg = load_config()
    return e


def _deck_ids(store):
    return {d["filename"].rsplit(".", 1)[0]: d["id"] for d in store.list_decks()}


def test_seed_uploads_publishes_translates_and_is_idempotent(env):
    report = asyncio.run(mc.seed(env.cfg))
    assert [u[0] for u in env.uploads] == [s.file for s in mc.SEED_DECKS]
    assert dict(env.uploads)["ai-enablement-demo-beginner-fr.pptx"] == "fr-FR"
    assert dict(env.uploads)["ai-enablement-2-practitioner.pptx"] == "en-US"
    ids = _deck_ids(env.store)
    for spec in mc.SEED_DECKS:
        doc = env.store.docs[ids[spec.title]]
        assert doc["published"] is True
        assert doc["live_demo"] is spec.live_demo
    assert {t for _, t in env.translations} == {"fr-FR", "en-US"}
    assert (ids["ai-enablement-demo-beginner-fr"], "en-US") in env.translations
    playlists = env.store.list_playlists()
    assert len(playlists) == 1 and playlists[0]["title"] == mc.PLAYLIST_TITLE
    steps = sorted(playlists[0]["steps"], key=lambda s: s["order"])
    assert [s["deck_title"] for s in steps] == list(mc.PLAYLIST_STEPS)
    assert report["playlist"]["action"] == "created"

    # Second run: nothing new is uploaded or created.
    again = asyncio.run(mc.seed(env.cfg))
    assert len(env.uploads) == len(mc.SEED_DECKS)
    assert {d["action"] for d in again["decks"]} == {"exists"}
    assert again["playlist"]["action"] == "exists"
    assert len(env.store.list_playlists()) == 1


def test_seed_dry_run_writes_nothing(env):
    report = asyncio.run(mc.seed(env.cfg, dry_run=True))
    assert env.uploads == [] and env.translations == [] and env.store.docs == {}
    assert {d["action"] for d in report["decks"]} == {"would upload"}
    assert report["playlist"]["action"] == "would create"


def _fake_podcast_pipeline(monkeypatch, env, *, fail=False):
    from routers import podcast as pr
    from services import podcast_ingest, podcast_script
    from services.podcast_models import Document, JobState

    seen: dict = {}

    def fake_ingest_file(path, lo):
        return Document(id=str(uuid.uuid4()), title="tmp", source_kind="pptx", slide_images=["a.png"])

    async def fake_script(cfg, doc, req):
        seen["req"] = req
        for i in range(4):
            yield DialogueTurn(idx=i, speaker="interviewer" if i % 2 == 0 else "expert", text=f"line {i}",
                               slide_idx=0)

    async def fake_render(job_id, cfg):
        job = pr.JOBS[job_id]
        seen["job"] = job
        seen["doc_title"] = pr.DOCUMENTS[pr.SCRIPTS[job.script_id].document_id].title
        if fail:
            job.state = JobState.failed
            return
        env.plib.add(job_id, seen["doc_title"], published=False)
        job.archive_state = "published"
        job.state = JobState.done

    monkeypatch.setattr(podcast_ingest, "ingest_file", fake_ingest_file)
    monkeypatch.setattr(podcast_script, "generate_script_stream", fake_script)
    monkeypatch.setattr(pr, "_render_job_body", fake_render)
    return seen


def test_render_podcast_uses_photo_avatars_and_spec(env, monkeypatch):
    seen = _fake_podcast_pipeline(monkeypatch, env)
    out = asyncio.run(mc.render_podcast(env.cfg, "expert"))
    job = seen["job"]
    assert job.roles.interviewer.display_name == "Sofia" and job.roles.interviewer.avatar == "photo_female"
    assert job.roles.expert.display_name == "Lucas" and job.roles.expert.avatar == "photo_male"
    assert job.roles.interviewer.voice.startswith("en-US-Ava") and job.roles.expert.voice.startswith("en-US-Andrew")
    assert job.layout == "split_screen_with_slides"
    req = seen["req"]
    assert (req.language, req.style, req.audience_level, req.length) == ("en-US", "debate", "expert", "medium")
    assert seen["doc_title"] == "ai-enablement-3-expert"
    assert out["action"] == "rendered" and env.plib.items[out["job_id"]]["published"] is True

    # Idempotent: an item with the same title is reused, not re-rendered.
    seen.clear()
    again = asyncio.run(mc.render_podcast(env.cfg, "expert"))
    assert again["action"] == "exists" and "job" not in seen


def test_render_podcast_french_voices(env, monkeypatch):
    seen = _fake_podcast_pipeline(monkeypatch, env)
    asyncio.run(mc.render_podcast(env.cfg, "demo-fr"))
    roles = seen["job"].roles
    assert roles.interviewer.voice.startswith("fr-FR-Vivienne") and roles.expert.voice.startswith("fr-FR-Remy")
    assert seen["req"].language == "fr-FR" and seen["req"].audience_level == "beginner"


def test_render_podcast_failure_does_not_publish(env, monkeypatch):
    _fake_podcast_pipeline(monkeypatch, env, fail=True)
    with pytest.raises(mc.MaintenanceError):
        asyncio.run(mc.render_podcast(env.cfg, "beginner"))
    assert env.plib.items == {}


def test_render_podcast_requires_photo_avatars(env, monkeypatch):
    avatar_registry.reload("")
    _fake_podcast_pipeline(monkeypatch, env)
    with pytest.raises(mc.MaintenanceError, match="photo_female"):
        asyncio.run(mc.render_podcast(env.cfg, "beginner"))


def _fake_video_pipeline(monkeypatch, env):
    from routers import video as vr
    from services import video_ingest, video_script
    from services.video_models import JobState, SlideRef, VideoDocument

    seen: dict = {}

    def fake_ingest(path, original_name=None):
        return VideoDocument(doc_id=str(uuid.uuid4()), title=original_name.rsplit(".", 1)[0], source_kind="pptx",
                             slides=[SlideRef(index=0, image_ref="a.png")])

    async def fake_script(cfg, doc, req):
        seen["req"] = req
        yield SlideNarration(slide_index=0, slide_image_ref="a.png", narration="hello", voice=req.voice)

    async def fake_render(job_id, cfg):
        job = vr.JOBS[job_id]
        seen["script"] = vr.SCRIPTS[job.doc_id]
        env.vlib.add(job_id, vr.DOCUMENTS[job.doc_id].title, published=False)
        job.archive_state = "published"
        job.state = JobState.done

    monkeypatch.setattr(video_ingest, "ingest", fake_ingest)
    monkeypatch.setattr(video_script, "generate_script_stream", fake_script)
    monkeypatch.setattr(vr, "_render_job_body", fake_render)
    return seen


def test_render_video_french_male_presenter(env, monkeypatch):
    seen = _fake_video_pipeline(monkeypatch, env)
    out = asyncio.run(mc.render_video(env.cfg, "demo-fr"))
    script = seen["script"]
    assert script.voice.startswith("fr-FR-Remy") and script.language == "fr-FR"
    assert script.audience_level == "beginner"
    assert avatar_registry.for_voice(script.voice).id == "photo_male"
    assert out["title"] == "ai-enablement-demo-beginner-fr"
    assert env.vlib.items[out["job_id"]]["published"] is True


def test_render_video_aborts_when_voice_maps_to_other_avatar(env, monkeypatch):
    _fake_video_pipeline(monkeypatch, env)
    monkeypatch.setitem(mc.VIDEOS, "demo-en", mc.VideoSpec(
        "ai-enablement-demo-beginner.pptx", "en-US", "photo_male", "female", "beginner"))
    with pytest.raises(mc.MaintenanceError, match="resolves to avatar"):
        asyncio.run(mc.render_video(env.cfg, "demo-en"))
    assert env.vlib.items == {}


def _seed_all_new(env):
    asyncio.run(mc.seed(env.cfg))
    for spec in mc.PODCASTS.values():
        env.plib.add(f"job-{uuid.uuid4().hex[:8]}", spec.title)
    for spec in mc.VIDEOS.values():
        env.vlib.add(f"sv-{uuid.uuid4().hex[:8]}", spec.title)


def _add_old(env):
    for title, deck_id in OLD_DECKS.items():
        env.store.docs[deck_id] = {"id": deck_id, "source": "deck", "filename": f"{title}.pptx",
                                   "slide_count": 3, "language": "en-US", "published": True, "live_demo": True}
    env.store.docs["pl_0123456789ab"] = {
        "id": "pl_0123456789ab", "source": "playlist", "title": "Sustainability path", "status": "active",
        "steps": [{"deck_id": OLD_DECKS["climate-action"], "order": 0, "deck_title": "climate-action"}]}
    env.plib.add("job-22d144ee", "circular-economy")
    env.vlib.add("sv-b89d3ed5", "circular-economy")


def _purge(env, tmp_path, **kw):
    args = dict(deck_titles=list(OLD_DECKS), podcast_ids=["job-22d144ee"], video_ids=["sv-b89d3ed5"],
                record=tmp_path / "deleted.json", allow_missing=set())
    args.update(kw)
    return mc.purge(env.cfg, **args)


def test_purge_refuses_until_new_content_is_published(env, tmp_path):
    _add_old(env)
    asyncio.run(mc.seed(env.cfg))
    with pytest.raises(mc.MaintenanceError, match="not ready"):
        _purge(env, tmp_path)
    assert OLD_DECKS["climate-action"] in env.store.docs and "job-22d144ee" in env.plib.items


def test_purge_dry_run_then_delete(env, tmp_path):
    _add_old(env)
    _seed_all_new(env)
    dry = _purge(env, tmp_path, dry_run=True)
    assert {d["title"] for d in dry["decks"]} == set(OLD_DECKS)
    assert [p["id"] for p in dry["playlists"]] == ["pl_0123456789ab"]
    assert OLD_DECKS["climate-action"] in env.store.docs

    result = _purge(env, tmp_path)
    assert result["errors"] == [] and result["not_found"] == []
    for deck_id in OLD_DECKS.values():
        assert deck_id not in env.store.docs
    assert "pl_0123456789ab" not in env.store.docs
    assert "job-22d144ee" not in env.plib.items and "sv-b89d3ed5" not in env.vlib.items
    titles = {d["filename"].rsplit(".", 1)[0] for d in env.store.list_decks()}
    assert titles == {s.title for s in mc.SEED_DECKS}
    assert [p["title"] for p in env.store.list_playlists()] == [mc.PLAYLIST_TITLE]
    record = json.loads((tmp_path / "deleted.json").read_text(encoding="utf-8"))
    assert {d["deck_id"] for d in record["decks"]} == set(OLD_DECKS.values())
    assert "sig=" not in json.dumps(record)


def test_purge_protects_new_decks(env, tmp_path):
    _seed_all_new(env)
    with pytest.raises(mc.MaintenanceError, match="refusing"):
        _purge(env, tmp_path, deck_titles=["ai-enablement-1-beginner"])


def test_purge_allow_missing(env, tmp_path):
    _add_old(env)
    asyncio.run(mc.seed(env.cfg))
    for spec in mc.PODCASTS.values():
        env.plib.add(f"job-{uuid.uuid4().hex[:8]}", spec.title)
    for name, spec in mc.VIDEOS.items():
        if name != "practitioner":
            env.vlib.add(f"sv-{uuid.uuid4().hex[:8]}", spec.title)
    result = _purge(env, tmp_path, allow_missing={"video:practitioner"})
    assert result["errors"] == []


def test_inventory_has_no_signed_urls(env):
    _seed_all_new(env)
    inv = mc.inventory(env.cfg)
    assert "sig=" not in json.dumps(inv)
    assert len(inv["podcasts"]) == len(mc.PODCASTS) and len(inv["videos"]) == len(mc.VIDEOS)


def test_specs_match_requirements():
    assert {n: (s.style, s.audience_level, s.language) for n, s in mc.PODCASTS.items()} == {
        "beginner": ("explainer", "beginner", "en-US"),
        "practitioner": ("casual", "practitioner", "en-US"),
        "expert": ("debate", "expert", "en-US"),
        "demo-fr": ("casual", "beginner", "fr-FR"),
    }
    assert {n: (s.avatar, s.language) for n, s in mc.VIDEOS.items()} == {
        "demo-en": ("photo_female", "en-US"),
        "demo-fr": ("photo_male", "fr-FR"),
        "practitioner": ("photo_female", "en-US"),
    }
    from services.voice_catalog import is_allowed_voice
    assert all(is_allowed_voice(v) for by_gender in mc.VOICES.values() for v in by_gender.values())
    for spec in mc.SEED_DECKS:
        assert mc._deck_path(spec.file).is_file()


def test_cli_dry_run_seed(env, monkeypatch, capsys):
    monkeypatch.setattr(mc, "_cfg", lambda: env.cfg)
    assert mc.main(["seed", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would upload" in out and env.store.docs == {}


def test_publish_all_continues_past_a_failed_item(env, monkeypatch):
    calls: list[str] = []

    async def fake_podcast(cfg, name, *, dry_run=False, deck_dir=None):
        calls.append(f"podcast:{name}")
        if name == "practitioner":
            raise mc.MaintenanceError("boom")
        return {"name": name, "action": "rendered"}

    async def fake_video(cfg, name, *, dry_run=False, deck_dir=None):
        calls.append(f"video:{name}")
        return {"name": name, "action": "rendered"}

    monkeypatch.setattr(mc, "render_podcast", fake_podcast)
    monkeypatch.setattr(mc, "render_video", fake_video)
    summary = asyncio.run(mc.publish_all(env.cfg, skip={"video:practitioner"}))
    assert summary["seed"]["playlist"]["action"] == "created"
    assert calls == [f"podcast:{n}" for n in mc.PODCASTS] + ["video:demo-en", "video:demo-fr"]
    assert [e["item"] for e in summary["errors"]] == ["podcast:practitioner"]
    assert summary["videos"][-1] == {"name": "practitioner", "action": "skipped"}


def test_logtail_redacts_signed_urls(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("ok line\nGET https://acct.blob.core.windows.net/c/v.mp4?sv=2024&sig=ABC123 failed\n"
                   "api key=SuperSecret1 here\n", encoding="utf-8")
    out = "\n".join(mc.logtail(log, 10))
    assert "ABC123" not in out and "SuperSecret1" not in out
    assert "https://acct.blob.core.windows.net/c/v.mp4?<redacted>" in out and "ok line" in out
    assert mc.logtail(tmp_path / "missing.log", 5)[0].startswith("(no log")


def test_background_flag_parses():
    args = mc.build_parser().parse_args(["--background", "/tmp/all.log", "all", "--skip", "video:practitioner"])
    assert str(args.background).replace("\\", "/").endswith("tmp/all.log")
    assert args.cmd == "all" and args.skip == ["video:practitioner"]

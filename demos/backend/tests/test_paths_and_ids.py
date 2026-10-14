"""Path traversal, identifier validation, OData escaping and safe deletes."""
from __future__ import annotations

from pathlib import Path

import pytest

UUID = "0b5f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"


@pytest.fixture
def spa(tmp_path, monkeypatch, app_module):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    (static / "robots.txt").write_text("User-agent: *", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOP-SECRET", encoding="utf-8")
    monkeypatch.setattr(app_module, "STATIC_DIR", str(static))
    return static


TRAVERSALS = [
    "/..%2Fsecret.txt",
    "/..%2F..%2Fapp.py",
    "/%2e%2e/secret.txt",
    "/%2e%2e%2fsecret.txt",
    "/..%252Fsecret.txt",
    "/%252e%252e%252fsecret.txt",
    "/..%5Csecret.txt",
    "/..\\secret.txt",
    "/assets/..%2F..%2Fsecret.txt",
    "/assets/%2e%2e/%2e%2e/secret.txt",
    "/C:/Windows/win.ini",
    "/c:%5Cwindows%5Cwin.ini",
    "/%00index.html",
    "/....//secret.txt",
]


@pytest.mark.parametrize("path", TRAVERSALS)
def test_spa_traversal_returns_404(client, spa, path):
    r = client.get(path)
    assert r.status_code == 404, (path, r.status_code)
    assert "TOP-SECRET" not in r.text and "SPA" not in r.text


def test_spa_absolute_path_returns_404(client, spa):
    r = client.get("http://testserver//proc/self/environ")
    assert r.status_code == 404
    r = client.get("http://testserver//etc/passwd")
    assert r.status_code == 404


def test_spa_serves_real_files_and_client_routes(client, spa):
    assert client.get("/robots.txt").text == "User-agent: *"
    r = client.get("/learn/paths")
    assert r.status_code == 200 and "SPA" in r.text
    assert "no-store" in r.headers["cache-control"]
    assert client.get("/").status_code == 200
    # Missing file with an extension -> 404, never index.html
    assert client.get("/favicon.ico").status_code == 404
    assert client.get("/api/does-not-exist").status_code == 404


def test_safe_join_unit(tmp_path):
    from security import safe_join

    base = tmp_path / "base"
    base.mkdir()
    (base / "ok.txt").write_text("x")
    assert safe_join(base, "ok.txt") == (base / "ok.txt").resolve()
    for bad in ["../x", "a/../../x", "/etc/passwd", "..\\x", "C:\\x", "c:x", "%2e%2e/x", "a\x00b", ".", "", "a/./b"]:
        assert safe_join(base, bad) is None, bad


# ---------------------------------------------------------------------------
# /api/slides/{presentation_id}/{filename}
# ---------------------------------------------------------------------------
@pytest.fixture
def slides(tmp_path, monkeypatch, app_module):
    slides_dir = tmp_path / "slides"
    (slides_dir / UUID).mkdir(parents=True)
    (slides_dir / UUID / "0.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (slides_dir / UUID / "1.html").write_text("<script>alert(1)</script>")
    (tmp_path / "secret.png").write_bytes(b"secret")
    monkeypatch.setattr(app_module, "SLIDES_DIR", slides_dir)
    return slides_dir


@pytest.mark.parametrize("path", [
    f"/api/slides/{UUID}/..%2F..%2Fsecret.png",
    f"/api/slides/{UUID}/%2e%2e%2f%2e%2e%2fsecret.png",
    f"/api/slides/{UUID}/..%252F..%252Fsecret.png",
    f"/api/slides/{UUID}/..%5C..%5Csecret.png",
    "/api/slides/..%2F..%2F/secret.png",
    "/api/slides/..%5C/secret.png",
    "/api/slides/not-a-uuid/0.png",
    f"/api/slides/{UUID}/1.html",
    f"/api/slides/{UUID}/0.svg",
    f"/api/slides/{UUID}/.png",
])
def test_slide_route_traversal_404(client, slides, path):
    r = client.get(path)
    assert r.status_code == 404, (path, r.status_code)
    assert b"secret" not in r.content and b"<script>" not in r.content


def test_slide_route_serves_valid_png_with_fixed_type(client, slides):
    r = client.get(f"/api/slides/{UUID}/0.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_slide_route_anonymous_needs_published_deck(client, slides, easyauth, app_module, monkeypatch):
    class Store:
        cosmos_available = True
        available = False

        def __init__(self, published):
            self.published = published

        def get_presentation(self, pid):
            return {"id": pid, "source": "uc1", "published": self.published}

    monkeypatch.setattr(app_module, "store", Store(False))
    assert client.get(f"/api/slides/{UUID}/0.png").status_code == 401
    monkeypatch.setattr(app_module, "store", Store(True))
    assert client.get(f"/api/slides/{UUID}/0.png").status_code == 200


# ---------------------------------------------------------------------------
# Identifier validation on deletes and lookups
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method,path", [
    ("delete", "/api/presentations/not-a-uuid"),
    ("delete", "/api/presentations/static-videos"),
    ("delete", "/api/static-video/library/static-videos"),
    ("delete", "/api/static-video/library/sv-XYZ"),
    ("delete", "/api/podcast/library/podcast-library"),
    ("delete", "/api/podcast/library/job-1234"),
    ("delete", "/api/uc1/decks/%2E%2E"),
    ("delete", "/api/uc1/decks/abc"),
    ("delete", "/api/uc1/paths/bad-id"),
    ("get", "/api/uc1/paths/path_XYZ"),
    ("get", "/api/static-video/jobs/../x"),
    ("get", "/api/podcast/jobs/job-zzzzzzzz"),
    ("get", "/api/avatar/batch/not-a-uuid"),
    ("get", "/api/slides/not-a-uuid"),
])
def test_invalid_ids_404(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 404, (path, r.status_code, r.text)


def test_id_patterns_match_generated_formats():
    import uuid

    from security import PATH_ID_RE, PODCAST_JOB_RE, STATIC_JOB_RE, UUID_RE, is_valid

    assert is_valid(str(uuid.uuid4()), UUID_RE)
    assert is_valid(f"sv-{uuid.uuid4().hex[:8]}", STATIC_JOB_RE)
    assert is_valid(f"job-{uuid.uuid4().hex[:8]}", PODCAST_JOB_RE)
    assert is_valid(f"path_{uuid.uuid4().hex[:12]}", PATH_ID_RE)
    assert not is_valid("sv-12345678/", STATIC_JOB_RE)
    assert not is_valid("", UUID_RE)


def test_library_delete_never_uses_root_prefix():
    from config import load_config
    from services.podcast_library import PodcastLibrary
    from services.static_library import StaticVideoLibrary

    for lib_cls, bad in ((StaticVideoLibrary, ["", "/", "..", "sv-", "x/../"]),
                         (PodcastLibrary, ["", "/", "..", "job-", "x/../"])):
        lib = lib_cls(load_config())

        def boom():  # would only be reached after validation
            raise AssertionError("blob access attempted for invalid id")

        lib._ensure_init = boom  # type: ignore[assignment]
        for job_id in bad:
            assert lib.delete(job_id) is False


def test_library_delete_uses_exact_job_prefix():
    from config import load_config
    from services.static_library import StaticVideoLibrary

    deleted, prefixes = [], []

    class Container:
        def list_blobs(self, name_starts_with):
            prefixes.append(name_starts_with)
            return [type("B", (), {"name": name_starts_with + "video.mp4"})()]

        def delete_blob(self, name):
            deleted.append(name)

    class Blob:
        def get_container_client(self, _):
            return Container()

    lib = StaticVideoLibrary(load_config())
    lib._initialised = True
    lib._blob = Blob()
    assert lib.delete("sv-0123abcd") is True
    assert prefixes == ["static-videos/sv-0123abcd/"]
    assert deleted == ["static-videos/sv-0123abcd/video.mp4"]


def test_storage_delete_slide_images_rejects_bad_ids():
    from config import load_config
    from services.storage import PresentationStore

    store = PresentationStore(load_config())

    def boom():
        raise AssertionError("blob access attempted for invalid id")

    store._ensure_init = boom  # type: ignore[assignment]
    for bad in ["", "static-videos", "podcast-library", "../x", "*"]:
        assert store.delete_slide_images(bad) is False


# ---------------------------------------------------------------------------
# OData escaping (AI Search)
# ---------------------------------------------------------------------------
def test_odata_literal_doubles_quotes():
    from services.uc1_search import odata_literal

    assert odata_literal("abc") == "'abc'"
    assert odata_literal("x' or deck_id ne '") == "'x'' or deck_id ne '''"


def test_search_filters_are_escaped():
    from services.uc1_search import Uc1SearchService

    calls = []

    class FakeSearch:
        def search(self, **kwargs):
            calls.append(kwargs)
            return []

        def delete_documents(self, ids):
            return []

    svc = object.__new__(Uc1SearchService)
    svc._search_client = FakeSearch()
    svc._openai = None
    svc._embed = lambda text: None  # type: ignore[assignment]

    svc.delete_deck("a' or 1 eq 1 or deck_id eq 'b")
    assert calls[-1]["filter"] == "deck_id eq 'a'' or 1 eq 1 or deck_id eq ''b'"
    svc.search("q", language="en-US' or language ne '")
    assert calls[-1]["filter"] == "language eq 'en-US'' or language ne '''"


def test_search_uses_aad_when_no_key(monkeypatch):
    import services.uc1_search as mod

    seen = {}

    class FakeIndexClient:
        def __init__(self, endpoint, cred):
            seen["cred"] = cred

        def get_index(self, name):
            return object()

    monkeypatch.setattr(mod, "SearchIndexClient", FakeIndexClient)
    monkeypatch.setattr(mod, "SearchClient", lambda *a, **k: object())

    class FakeCred:
        pass

    import azure.identity

    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", FakeCred)
    mod.Uc1SearchService("https://s.example", "", "idx", None, "emb")
    assert isinstance(seen["cred"], FakeCred)
    mod.Uc1SearchService("https://s.example", "k", "idx", None, "emb")
    assert isinstance(seen["cred"], mod.AzureKeyCredential)

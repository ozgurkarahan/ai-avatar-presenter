"""Smoke tests for the video router.

Covers the static endpoints that don't depend on Azure or ffmpeg:
  - GET /api/video/languages  returns 8 DragonHD languages
  - GET /api/video/voices      returns ≥16 voice options
  - GET /api/video/voices?language=fr-FR filters correctly
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make `routers.*` / `services.*` importable when pytest is run from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client() -> TestClient:
    from routers.video import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_languages_returns_eight_dragonhd_langs(client: TestClient) -> None:
    r = client.get("/api/video/languages")
    assert r.status_code == 200
    data = r.json()
    codes = [row["code"] for row in data]
    assert codes == [
        "en-US", "fr-FR", "es-ES", "de-DE",
        "it-IT", "pt-BR", "zh-CN", "ja-JP",
    ]


def test_voices_all(client: TestClient) -> None:
    r = client.get("/api/video/voices")
    assert r.status_code == 200
    voices = r.json()
    assert len(voices) >= 16
    assert all("DragonHDLatestNeural" in v["id"] for v in voices)


def test_voices_filter_by_language(client: TestClient) -> None:
    r = client.get("/api/video/voices", params={"language": "fr-FR"})
    assert r.status_code == 200
    voices = r.json()
    assert voices and all(v["language"] == "fr-FR" for v in voices)


def test_get_script_not_found(client: TestClient) -> None:
    r = client.get("/api/video/script/does-not-exist")
    assert r.status_code == 404


def test_ingest_returns_servable_slide_image_urls(client: TestClient, tmp_path, monkeypatch) -> None:
    """Wizard thumbnails: ingest returns API URLs (not server paths) that serve the PNGs."""
    import uuid

    import routers.video as rv
    from services.video_models import SlideRef, VideoDocument

    monkeypatch.chdir(tmp_path)
    doc_id = str(uuid.uuid4())
    img_dir = tmp_path / "data" / "uploads" / "video" / "x_slides_1"
    img_dir.mkdir(parents=True)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    (img_dir / "slide_000.png").write_bytes(png)
    (tmp_path / "secret.png").write_bytes(png)
    doc = VideoDocument(doc_id=doc_id, title="Deck", source_kind="pptx", slides=[
        SlideRef(index=0, image_ref="data/uploads/video/x_slides_1/slide_000.png", title="One"),
        SlideRef(index=1, image_ref="", title="Text only"),
        SlideRef(index=2, image_ref=str(tmp_path / "secret.png"), title="Outside"),
    ])
    monkeypatch.setattr("services.video_ingest.ingest", lambda path, name: doc)
    monkeypatch.setattr(rv.DAILY_QUOTA, "consume", lambda *_: None)

    r = client.post("/api/video/ingest", files={"file": ("deck.pptx", b"PK", "application/octet-stream")})
    assert r.status_code == 200, r.text
    refs = [s["image_ref"] for s in r.json()["slides"]]
    assert refs[0] == f"/api/video/documents/{doc_id}/slides/0/image"
    assert refs[1] == ""
    assert "uploads" not in "".join(refs)

    img = client.get(refs[0])
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content == png
    # The renderer still gets the local path.
    assert rv.DOCUMENTS[doc_id].slides[0].image_ref.endswith("slide_000.png")
    # Text-only slide, a path outside the upload dir, an unknown slide / document.
    assert client.get(f"/api/video/documents/{doc_id}/slides/1/image").status_code == 404
    assert client.get(f"/api/video/documents/{doc_id}/slides/2/image").status_code == 404
    assert client.get(f"/api/video/documents/{doc_id}/slides/9/image").status_code == 404
    assert client.get(f"/api/video/documents/{uuid.uuid4()}/slides/0/image").status_code == 404

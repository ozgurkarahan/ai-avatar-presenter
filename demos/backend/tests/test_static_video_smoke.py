"""Smoke tests for UC2 static-video router.

Covers the static endpoints that don't depend on Azure or ffmpeg:
  - GET /api/static-video/languages  returns 8 DragonHD languages
  - GET /api/static-video/voices      returns ≥16 voice options
  - GET /api/static-video/voices?language=fr-FR filters correctly
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
    from routers.static_video import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_languages_returns_eight_dragonhd_langs(client: TestClient) -> None:
    r = client.get("/api/static-video/languages")
    assert r.status_code == 200
    data = r.json()
    codes = [row["code"] for row in data]
    assert codes == [
        "en-US", "fr-FR", "es-ES", "de-DE",
        "it-IT", "pt-BR", "zh-CN", "ja-JP",
    ]


def test_voices_all(client: TestClient) -> None:
    r = client.get("/api/static-video/voices")
    assert r.status_code == 200
    voices = r.json()
    assert len(voices) >= 16
    assert all("DragonHDLatestNeural" in v["id"] for v in voices)


def test_voices_filter_by_language(client: TestClient) -> None:
    r = client.get("/api/static-video/voices", params={"language": "fr-FR"})
    assert r.status_code == 200
    voices = r.json()
    assert voices and all(v["language"] == "fr-FR" for v in voices)


def test_get_script_not_found(client: TestClient) -> None:
    r = client.get("/api/static-video/script/does-not-exist")
    assert r.status_code == 404

"""Shared pytest fixtures for the decks / playlists API tests.

Drives a live backend via the AI_PRESENTER_BASE_URL env var (default
http://localhost:8000 — local dev started with run-local.ps1, AUTH_MODE=disabled).
Uploads all 6 test decks once per session and tears them down at the end.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import httpx
import pytest

BASE_URL = os.environ.get("AI_PRESENTER_BASE_URL", "http://localhost:8000").rstrip("/")

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "decks"

# filename → (language, topic-specific query, expected top deck title substring)
FIXTURES = [
    ("climate-action.pptx",        "en-US", "carbon neutral net-zero emissions",     "climate-action"),
    ("ai-ethics.pptx",             "en-US", "bias fairness machine learning",         "ai-ethics"),
    ("cloud-security.pptx",        "en-US", "zero trust identity cloud",              "cloud-security"),
    ("medical-devices.pptx",       "en-US", "medical device MDR classification",      "medical-devices"),
    ("transition-energetique.pptx","fr-FR", "transition énergétique hydrogène",       "transition-energetique"),
    ("innovacion-industrial.pptx", "es-ES", "innovación industrial gemelos digitales","innovacion-industrial"),
]


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def client(base_url) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=base_url, timeout=180.0) as c:
        yield c


@pytest.fixture(scope="session")
def uploaded_decks(client) -> Iterator[dict[str, dict]]:
    """Upload all 6 fixtures once. Yields {filename: upload_response}. Tears down at end."""
    uploaded: dict[str, dict] = {}
    for filename, language, _query, _deck_title in FIXTURES:
        path = FIXTURE_DIR / filename
        with path.open("rb") as fh:
            r = client.post(
                "/api/decks/upload",
                files={"file": (filename, fh, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
                data={"language": language},
            )
        assert r.status_code == 200, f"upload {filename} failed: {r.status_code} {r.text}"
        uploaded[filename] = r.json()
    yield uploaded
    # Teardown — force=true so any referencing test playlists don't block deletion
    for resp in uploaded.values():
        try:
            client.delete(f"/api/decks/{resp['deck_id']}?force=true")
        except Exception:
            pass

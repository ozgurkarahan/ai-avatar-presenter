"""Shared pytest setup for the backend tests.

Tests run fully offline: Azure endpoints loaded from a developer `.env` are
blanked so no Cosmos / Blob / Search / OpenAI client can be constructed, and
every test starts in AUTH_MODE=disabled unless it opts into easyauth.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for _p in (BACKEND_DIR, TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import config  # noqa: E402  (loads .env once; we override below)

_OFFLINE_ENV = {
    "AZURE_USE_MANAGED_IDENTITY": "false",
    "AZURE_COSMOS_ENDPOINT": "",
    "AZURE_COSMOS_KEY": "",
    "AZURE_BLOB_CONNECTION_STRING": "",
    "AZURE_BLOB_ACCOUNT_NAME": "",
    "AZURE_SEARCH_ENDPOINT": "",
    "AZURE_SEARCH_KEY": "",
    "AZURE_OPENAI_ENDPOINT": "",
    "AZURE_OPENAI_KEY": "",
    "AZURE_SPEECH_ENDPOINT": "",
    "AZURE_SPEECH_KEY": "",
    "AUTH_MODE": "disabled",
    "AUTH_TENANT_ID": "",
    "ALLOWED_OBJECT_IDS": "",
    "ALLOWED_ORIGINS": "",
    "ENABLE_URL_INGEST": "false",
    "CUSTOM_AVATARS_JSON": "",
}
os.environ.update(_OFFLINE_ENV)

from _helpers import ADMIN_OID, TENANT, principal_headers  # noqa: E402


def pytest_configure(config):  # noqa: D401
    config.addinivalue_line("markers", "slow: slow tests requiring ffmpeg")


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    for k, v in _OFFLINE_ENV.items():
        monkeypatch.setenv(k, v)
    from security import DAILY_QUOTA, PENDING_RENDERS, VOICE_SESSIONS
    from services import avatar_registry

    DAILY_QUOTA.reset()
    PENDING_RENDERS.reset()
    VOICE_SESSIONS.reset()
    avatar_registry.reload("")
    yield
    DAILY_QUOTA.reset()
    PENDING_RENDERS.reset()
    VOICE_SESSIONS.reset()
    avatar_registry.reload("")


@pytest.fixture
def easyauth(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "easyauth")
    monkeypatch.setenv("AUTH_TENANT_ID", TENANT)
    monkeypatch.setenv("ALLOWED_OBJECT_IDS", f"{ADMIN_OID}, 12345678-0000-0000-0000-000000000000")
    return principal_headers


@pytest.fixture
def app_module():
    import app as app_mod

    return app_mod


@pytest.fixture
def client(app_module):
    from fastapi.testclient import TestClient

    # No context manager: the lifespan (which builds real Azure clients) is skipped.
    return TestClient(app_module.app)

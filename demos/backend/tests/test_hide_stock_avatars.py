"""HIDE_STOCK_AVATARS: only custom (photo) avatars are offered; legacy stock ids alias to them."""
from __future__ import annotations

import json

import pytest

CUSTOM = json.dumps([
    {"id": "photo_female", "display_name": "Sofia", "character": "F_char",
     "gender": "female", "thumbnail": "photo_female.png", "default": True},
    {"id": "photo_male", "display_name": "Lucas", "character": "M_char",
     "gender": "male", "thumbnail": "photo_male.png"},
])


@pytest.fixture
def registry(monkeypatch):
    from services import avatar_registry

    yield avatar_registry
    monkeypatch.delenv("HIDE_STOCK_AVATARS", raising=False)
    monkeypatch.delenv("CUSTOM_AVATARS_JSON", raising=False)
    avatar_registry.reload()


def test_hidden_stock_only_custom_in_catalog(monkeypatch, registry):
    monkeypatch.setenv("HIDE_STOCK_AVATARS", "true")
    registry.reload(CUSTOM)
    ids = {a["id"] for a in registry.public_catalog()}
    assert ids == {"photo_female", "photo_male"}
    assert registry.DEFAULT_ID == "photo_female"


def test_hidden_stock_ids_alias_to_same_gender_custom(monkeypatch, registry):
    monkeypatch.setenv("HIDE_STOCK_AVATARS", "true")
    registry.reload(CUSTOM)
    assert registry.get("lisa").id == "photo_female"
    assert registry.get("harry").id == "photo_male"
    assert registry.is_known("max")
    assert registry.for_voice("en-US-Andrew:DragonHDLatestNeural").id == "photo_male"
    assert registry.for_voice("en-US-Ava:DragonHDLatestNeural").id == "photo_female"
    assert registry.get("unknown").id == "photo_female"


def test_hidden_flag_without_custom_keeps_stock(monkeypatch, registry):
    monkeypatch.setenv("HIDE_STOCK_AVATARS", "true")
    registry.reload("")
    assert "lisa" in registry.all_ids() and registry.DEFAULT_ID == "lisa"


def test_hidden_default_falls_back_to_custom_female(monkeypatch, registry):
    monkeypatch.setenv("HIDE_STOCK_AVATARS", "1")
    registry.reload(json.dumps([
        {"id": "photo_male", "character": "m", "gender": "male"},
        {"id": "photo_female", "character": "f", "gender": "female"},
    ]))
    assert registry.DEFAULT_ID == "photo_female"
    assert registry.get("lori").id == "photo_female"


def test_flag_off_unchanged(registry):
    registry.reload(CUSTOM)
    assert {"lisa", "harry", "photo_female"} <= set(registry.all_ids())

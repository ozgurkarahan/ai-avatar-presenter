"""Avatar registry — single source of truth for all avatar metadata.

Every render path (UC1 live Voice Live, UC2 batch video, UC3 podcast)
consumes this module so the rest of the codebase never hard-codes an
avatar identity.

Two kinds of avatars are available:

* **Stock video avatars** (lisa, harry, max, meg, jeff, lori) — always
  available. They emit transparent webm/vp9 and support gestures.
* **Custom avatars** — loaded only from the ``CUSTOM_AVATARS_JSON``
  environment variable (JSON array)::

      [{"id": "photo_female", "display_name": "Photo Female",
        "character": "<Speech talkingAvatarCharacter>", "gender": "female",
        "thumbnail": "photo_female.png", "default": true, "kind": "photo"}]

  ``character`` is the server-only Speech ``talkingAvatarCharacter`` and is
  never returned by any API. ``thumbnail`` is a file name under
  ``static/avatars/``. ``kind`` is ``photo`` (default) or ``video``.

Photo avatars (custom photo avatars built on the vasa-1 base model) are
512x512 head-only with no transparency. They are emitted as mp4/h264 with a
green background that the compositor chroma-keys away, use an empty style
and do not support gestures.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AvatarEntry:
    """Configuration for one avatar identity.

    Attributes
    ----------
    id : str
        Stable lower-snake-case identifier used by API + UI.
    foundry_name : str
        Exact (case-sensitive) name passed as ``talkingAvatarCharacter``
        to the Speech Avatar API. Server-side only — never exposed.
    display_name : str
        Human-readable label for the picker.
    gender : str
        ``female`` or ``male`` — used to pick a default avatar from a voice.
    customized : bool
        ``True`` for tenant-uploaded custom avatars (photo or video).
    photo_base_model : str
        ``vasa-1`` for photo avatars, ``""`` otherwise.
    default_style : str
        ``talkingAvatarStyle``; must be ``""`` for photo avatars.
    supports_gestures : bool
        Whether ``<bookmark mark='gesture.*'/>`` injection is allowed in
        SSML. Photo avatars do not support gestures.
    video_format : str
        ``mp4`` (photo) or ``webm`` (video avatar with alpha).
    video_codec : str
        ``h264`` for mp4, ``vp9`` for webm.
    background_color : str
        ``#00FF00FF`` for chroma-key on photo avatars,
        ``#00000000`` (transparent) for webm video avatars.
    chroma_key : bool
        ``True`` when compositors must chroma-key the output (photo avatars);
        ``False`` when alpha is already present (video avatars).
    thumbnail_url : str
        Static asset path served by the backend (may be empty).
    """

    id: str
    foundry_name: str
    display_name: str
    gender: str
    customized: bool
    photo_base_model: str
    default_style: str
    supports_gestures: bool
    video_format: str
    video_codec: str
    background_color: str
    chroma_key: bool
    thumbnail_url: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


def _stock(id_: str, display: str, gender: str, style: str) -> AvatarEntry:
    return AvatarEntry(
        id=id_,
        foundry_name=id_,
        display_name=display,
        gender=gender,
        customized=False,
        photo_base_model="",
        default_style=style,
        supports_gestures=True,
        video_format="webm",
        video_codec="vp9",
        background_color="#00000000",
        chroma_key=False,
        thumbnail_url="",
    )


# Styles mirror services.avatar.AVATAR_STYLES (docs-verified pairs).
_STOCK: list[AvatarEntry] = [
    _stock("lisa", "Lisa", "female", "casual-sitting"),
    _stock("harry", "Harry", "male", "business"),
    _stock("max", "Max", "male", "business"),
    _stock("meg", "Meg", "female", "business"),
    _stock("jeff", "Jeff", "male", "business"),
    _stock("lori", "Lori", "female", "casual"),
]

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_THUMB_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.(png|jpg|jpeg|webp)$")
THUMBNAIL_URL_PREFIX = "/static/avatars/"


def _custom_entry(raw: dict) -> Optional[tuple[AvatarEntry, bool]]:
    """Validate one CUSTOM_AVATARS_JSON item. Returns (entry, is_default)."""
    if not isinstance(raw, dict):
        return None
    avatar_id = str(raw.get("id") or "").strip().lower()
    character = raw.get("character")
    if not _ID_RE.fullmatch(avatar_id) or not isinstance(character, str) or not character.strip():
        log.warning("Ignoring custom avatar with invalid id/character (id=%r)", avatar_id)
        return None
    gender = str(raw.get("gender") or "").strip().lower()
    if gender not in {"female", "male"}:
        gender = "female"
    display = str(raw.get("display_name") or avatar_id).strip()[:80] or avatar_id
    thumb = str(raw.get("thumbnail") or "").strip()
    thumbnail_url = f"{THUMBNAIL_URL_PREFIX}{thumb}" if _THUMB_RE.fullmatch(thumb) else ""
    kind = str(raw.get("kind") or "photo").strip().lower()
    if kind == "video":
        entry = AvatarEntry(
            id=avatar_id,
            foundry_name=character.strip(),
            display_name=display,
            gender=gender,
            customized=True,
            photo_base_model="",
            default_style=str(raw.get("style") or "").strip(),
            supports_gestures=False,
            video_format="webm",
            video_codec="vp9",
            background_color="#00000000",
            chroma_key=False,
            thumbnail_url=thumbnail_url,
        )
    else:
        entry = AvatarEntry(
            id=avatar_id,
            foundry_name=character.strip(),
            display_name=display,
            gender=gender,
            customized=True,
            photo_base_model="vasa-1",
            default_style="",
            supports_gestures=False,
            video_format="mp4",
            video_codec="h264",
            background_color="#00FF00FF",
            chroma_key=True,
            thumbnail_url=thumbnail_url,
        )
    return entry, bool(raw.get("default") is True)


# ---------------------------------------------------------------------------
# Registry state (rebuilt by reload())
# ---------------------------------------------------------------------------
_ENTRIES: dict[str, AvatarEntry] = {}
_CUSTOM_IDS: list[str] = []
_ALIAS_INDEX: dict[str, str] = {}
DEFAULT_ID: str = "lisa"


def reload(raw_json: Optional[str] = None) -> None:
    """(Re)build the registry from stock avatars + ``CUSTOM_AVATARS_JSON``."""
    global DEFAULT_ID
    raw_json = os.environ.get("CUSTOM_AVATARS_JSON", "") if raw_json is None else raw_json

    entries: dict[str, AvatarEntry] = {}
    custom_ids: list[str] = []
    explicit_default: Optional[str] = None

    items: list = []
    if raw_json and raw_json.strip():
        try:
            parsed = json.loads(raw_json)
            items = parsed if isinstance(parsed, list) else []
            if not isinstance(parsed, list):
                log.warning("CUSTOM_AVATARS_JSON must be a JSON array; ignoring")
        except json.JSONDecodeError:
            log.warning("CUSTOM_AVATARS_JSON is not valid JSON; ignoring")

    stock_ids = {e.id for e in _STOCK}
    for raw in items:
        res = _custom_entry(raw)
        if not res:
            continue
        entry, is_default = res
        if entry.id in stock_ids or entry.id in entries:
            log.warning("Ignoring duplicate custom avatar id %s", entry.id)
            continue
        entries[entry.id] = entry
        custom_ids.append(entry.id)
        if is_default and explicit_default is None:
            explicit_default = entry.id

    for e in _STOCK:
        entries[e.id] = e

    alias_index: dict[str, str] = {}
    for e in entries.values():
        alias_index[e.id.lower()] = e.id
        for a in e.aliases:
            alias_index[a.lower()] = e.id

    _ENTRIES.clear()
    _ENTRIES.update(entries)
    _CUSTOM_IDS[:] = custom_ids
    _ALIAS_INDEX.clear()
    _ALIAS_INDEX.update(alias_index)
    DEFAULT_ID = explicit_default or next(e.id for e in _STOCK if e.gender == "female")
    if custom_ids:
        log.info("Avatar registry: %d custom avatar(s) loaded, default=%s", len(custom_ids), DEFAULT_ID)


reload()


def all_entries() -> list[AvatarEntry]:
    """Return all registered avatars (custom first, then stock)."""
    return list(_ENTRIES.values())


def all_ids() -> list[str]:
    return list(_ENTRIES.keys())


def is_known(avatar_id: Optional[str]) -> bool:
    return bool(avatar_id) and avatar_id.strip().lower() in _ALIAS_INDEX  # type: ignore[union-attr]


def get(avatar_id: Optional[str]) -> AvatarEntry:
    """Resolve an avatar id (or alias) to a registry entry.

    Unknown / falsy values fall back to the default entry, so a caller can
    never select an avatar outside the registry.
    """
    if avatar_id:
        key = avatar_id.strip().lower()
        if key in _ALIAS_INDEX:
            return _ENTRIES[_ALIAS_INDEX[key]]
    return _ENTRIES[DEFAULT_ID]


# ---------------------------------------------------------------------------
# Voice → default avatar inference
# ---------------------------------------------------------------------------
# Substring patterns (case-insensitive). Curated to match Azure HD voices.
_FEMALE_VOICE_TOKENS: tuple[str, ...] = (
    "ava", "lisa", "lori", "meg", "elvira", "denise", "vivienne", "ximena",
    "seraphina", "isabella", "thalita", "xiaochen", "nanami", "jenny",
    "aria", "emma", "sara", "yan",
)
_MALE_VOICE_TOKENS: tuple[str, ...] = (
    "andrew", "harry", "jeff", "max", "thomas", "remy", "tristan",
    "florian", "alessio", "macerio", "yunfan", "masaru", "guy",
    "davis", "tony",
)


def gender_from_voice(voice: Optional[str]) -> Optional[str]:
    """Best-effort gender inference from an Azure voice id."""
    if not voice:
        return None
    v = voice.lower()
    if any(tok in v for tok in _FEMALE_VOICE_TOKENS):
        return "female"
    if any(tok in v for tok in _MALE_VOICE_TOKENS):
        return "male"
    return None


def for_voice(voice: Optional[str], fallback: Optional[str] = None) -> AvatarEntry:
    """Pick an avatar matching the gender of ``voice``.

    Preference: the registry default (if the gender matches), then the first
    custom avatar of that gender, then the first stock avatar of that gender.
    Falls back to ``fallback`` (default: registry default) when the voice
    gender cannot be inferred.
    """
    gender = gender_from_voice(voice)
    if gender:
        default = _ENTRIES[DEFAULT_ID]
        if default.gender == gender:
            return default
        for cid in _CUSTOM_IDS:
            if _ENTRIES[cid].gender == gender:
                return _ENTRIES[cid]
        for e in _STOCK:
            if e.gender == gender:
                return _ENTRIES[e.id]
    return get(fallback or DEFAULT_ID)


# ---------------------------------------------------------------------------
# Avatar API payload helpers (server-side only)
# ---------------------------------------------------------------------------
def avatar_config_payload(entry: AvatarEntry) -> dict:
    """Build the ``avatarConfig`` block for a batch synthesis PUT request."""
    cfg: dict = {
        "talkingAvatarCharacter": entry.foundry_name,
        "talkingAvatarStyle": entry.default_style,
        "customized": entry.customized,
        "videoFormat": entry.video_format,
        "videoCodec": entry.video_codec,
        "subtitleType": "soft_embedded",
        "backgroundColor": entry.background_color,
    }
    if entry.photo_base_model:
        cfg["photoAvatarBaseModel"] = entry.photo_base_model
    return cfg


def voice_live_session_avatar(entry: AvatarEntry) -> dict:
    """Build the ``session.avatar`` block for the Voice Live realtime API."""
    block: dict = {
        "character": entry.foundry_name,
        "customized": entry.customized,
    }
    if entry.default_style:
        block["style"] = entry.default_style
    if entry.photo_base_model:
        # Voice Live API uses snake_case `model` + `type` discriminator,
        # not the legacy Speech SDK `photoAvatarBaseModel` camelCase field.
        block["type"] = "photo-avatar"
        block["model"] = entry.photo_base_model
    return block


# ---------------------------------------------------------------------------
# Public catalog (never includes the Speech character name)
# ---------------------------------------------------------------------------
def public_catalog() -> list[dict]:
    """Shape returned by ``GET /api/avatars``."""
    return [
        {
            "id": e.id,
            "display_name": e.display_name,
            "gender": e.gender,
            "thumbnail_url": e.thumbnail_url,
            "is_default": e.id == DEFAULT_ID,
        }
        for e in _ENTRIES.values()
    ]


def catalog() -> Iterable[dict]:
    """Public catalog plus ``default_style`` (used by the podcast picker)."""
    for item in public_catalog():
        yield {**item, "default_style": _ENTRIES[item["id"]].default_style}

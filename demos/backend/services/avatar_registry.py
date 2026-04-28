"""Avatar registry — single source of truth for all avatar metadata.

Every render path (UC1 live Voice Live, UC2 batch video, UC3 podcast)
consumes this module so the rest of the codebase never hard-codes an
avatar identity. Adding a new avatar = adding one entry here.

Photo avatars (Foundry custom photo avatars built on the vasa-1 base
model) are 512x512 head-only with no transparency. They are emitted as
mp4/h264 with a green background that the compositor chroma-keys away.
Video avatars (lisa/harry/etc) emit transparent webm/vp9 instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class AvatarEntry:
    """Configuration for one avatar identity.

    Attributes
    ----------
    id : str
        Stable lower-snake-case identifier used by API + UI.
    foundry_name : str
        Exact (case-sensitive) name passed as ``talkingAvatarCharacter``
        to the Speech Avatar API.
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
        Static asset path served by the backend.
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


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_ENTRIES: dict[str, AvatarEntry] = {
    "st_gobain_female": AvatarEntry(
        id="st_gobain_female",
        foundry_name="ST_Gobain_Female",
        display_name="ST-Gobain Female",
        gender="female",
        customized=True,
        photo_base_model="vasa-1",
        default_style="",
        supports_gestures=False,
        video_format="mp4",
        video_codec="h264",
        background_color="#00FF00FF",
        chroma_key=True,
        thumbnail_url="/static/avatars/st_gobain_female.png",
        aliases=("ST_Gobain_Female", "stgobain_female", "stgobainfemale", "sg-female"),
    ),
    "st_gobain_male": AvatarEntry(
        id="st_gobain_male",
        foundry_name="ST_Gobain_Male",
        display_name="ST-Gobain Male",
        gender="male",
        customized=True,
        photo_base_model="vasa-1",
        default_style="",
        supports_gestures=False,
        video_format="mp4",
        video_codec="h264",
        background_color="#00FF00FF",
        chroma_key=True,
        thumbnail_url="/static/avatars/st_gobain_male.png",
        aliases=("ST_Gobain_Male", "stgobain_male", "stgobainmale", "sg-male"),
    ),
}

# Build alias index once for O(1) lookup.
_ALIAS_INDEX: dict[str, str] = {}
for _entry in _ENTRIES.values():
    _ALIAS_INDEX[_entry.id.lower()] = _entry.id
    _ALIAS_INDEX[_entry.foundry_name.lower()] = _entry.id
    for _alias in _entry.aliases:
        _ALIAS_INDEX[_alias.lower()] = _entry.id

DEFAULT_ID = "st_gobain_female"


def all_entries() -> list[AvatarEntry]:
    """Return all registered avatars in insertion order."""
    return list(_ENTRIES.values())


def all_ids() -> list[str]:
    return list(_ENTRIES.keys())


def get(avatar_id: str | None) -> AvatarEntry:
    """Resolve any input (id / foundry_name / alias / legacy id) to an entry.

    Unknown / falsy values fall back to the default entry. Legacy IDs from
    the previous catalog (``lisa``, ``harry``, ...) all map by gender to a
    sensible ST-Gobain default so older saved jobs / API clients keep
    working without raising.
    """
    if avatar_id:
        key = avatar_id.strip().lower()
        if key in _ALIAS_INDEX:
            return _ENTRIES[_ALIAS_INDEX[key]]
        # Legacy gender-based fallback for old catalog ids.
        if key in {"harry", "jeff", "max", "thomas"}:
            return _ENTRIES["st_gobain_male"]
        if key in {"lisa", "lori", "meg"}:
            return _ENTRIES["st_gobain_female"]
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


def gender_from_voice(voice: str | None) -> str | None:
    """Best-effort gender inference from an Azure voice id.

    Returns ``"female"`` or ``"male"``, or ``None`` when the voice cannot
    be classified.
    """
    if not voice:
        return None
    v = voice.lower()
    if any(tok in v for tok in _FEMALE_VOICE_TOKENS):
        return "female"
    if any(tok in v for tok in _MALE_VOICE_TOKENS):
        return "male"
    return None


def for_voice(voice: str | None, fallback: str = DEFAULT_ID) -> AvatarEntry:
    """Pick an avatar to match the gender of ``voice``.

    Falls back to ``fallback`` (default: female) when the voice gender
    cannot be inferred.
    """
    gender = gender_from_voice(voice)
    if gender == "male":
        return _ENTRIES["st_gobain_male"]
    if gender == "female":
        return _ENTRIES["st_gobain_female"]
    return get(fallback)


# ---------------------------------------------------------------------------
# Avatar API payload helpers
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
# Convenience iterators for catalog endpoints
# ---------------------------------------------------------------------------
def catalog() -> Iterable[dict]:
    """Yield UI-friendly dicts for /api/podcast/avatars and similar."""
    for e in _ENTRIES.values():
        yield {
            "id": e.id,
            "display_name": e.display_name,
            "gender": e.gender,
            "thumbnail_url": e.thumbnail_url,
            "default_style": e.default_style,
        }

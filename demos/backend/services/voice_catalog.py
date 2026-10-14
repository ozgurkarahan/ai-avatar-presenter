"""Allowlist of Azure TTS voices accepted from API clients.

Voice ids are interpolated into SSML (``<voice name="...">``) and the Voice
Live session config, so anything a client sends must come from this list.
"""
from __future__ import annotations

from typing import Optional

# (id, display_name, language, gender)
HD_VOICES: list[tuple[str, str, str, str]] = [
    ("en-US-Andrew:DragonHDLatestNeural", "Andrew (HD)", "en-US", "male"),
    ("en-US-Ava:DragonHDLatestNeural", "Ava (HD)", "en-US", "female"),
    ("fr-FR-Remy:DragonHDLatestNeural", "Rémy (HD)", "fr-FR", "male"),
    ("fr-FR-Vivienne:DragonHDLatestNeural", "Vivienne (HD)", "fr-FR", "female"),
    ("es-ES-Tristan:DragonHDLatestNeural", "Tristán (HD)", "es-ES", "male"),
    ("es-ES-Ximena:DragonHDLatestNeural", "Ximena (HD)", "es-ES", "female"),
    ("de-DE-Florian:DragonHDLatestNeural", "Florian (HD)", "de-DE", "male"),
    ("de-DE-Seraphina:DragonHDLatestNeural", "Seraphina (HD)", "de-DE", "female"),
    ("it-IT-Alessio:DragonHDLatestNeural", "Alessio (HD)", "it-IT", "male"),
    ("it-IT-Isabella:DragonHDLatestNeural", "Isabella (HD)", "it-IT", "female"),
    ("pt-BR-Macerio:DragonHDLatestNeural", "Macério (HD)", "pt-BR", "male"),
    ("pt-BR-Thalita:DragonHDLatestNeural", "Thalita (HD)", "pt-BR", "female"),
    ("zh-CN-Xiaochen:DragonHDLatestNeural", "晓辰 Xiaochen (HD)", "zh-CN", "female"),
    ("zh-CN-Yunfan:DragonHDLatestNeural", "云帆 Yunfan (HD)", "zh-CN", "male"),
    ("ja-JP-Masaru:DragonHDLatestNeural", "Masaru (HD)", "ja-JP", "male"),
    ("ja-JP-Nanami:DragonHDLatestNeural", "Nanami (HD)", "ja-JP", "female"),
]

# Legacy neural voices used as language defaults by services.avatar.VOICE_MAP.
_LEGACY_VOICES = {
    "en-US-AvaMultilingualNeural",
    "fr-FR-DeniseNeural",
    "es-ES-ElviraNeural",
}

ALLOWED_VOICE_IDS: frozenset[str] = frozenset({v[0] for v in HD_VOICES} | _LEGACY_VOICES)


def is_allowed_voice(voice: Optional[str]) -> bool:
    return isinstance(voice, str) and voice in ALLOWED_VOICE_IDS

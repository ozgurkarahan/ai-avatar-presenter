"""WebSocket proxy for Azure Voice Live API — avatar real-time streaming.

Replicates the azure-ai-voicelive SDK pattern using raw websockets,
avoiding the aiohttp build dependency on Windows ARM64.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import websockets
from azure.identity import DefaultAzureCredential

from config import AzureConfig
from services import avatar_registry
from services.voice_catalog import is_allowed_voice

logger = logging.getLogger(__name__)

VOICE_API_VERSION = "2025-10-01"
COGNITIVE_DOMAIN = "cognitiveservices.azure.com"

# Avatars always come from the registry: an empty / unknown id resolves to
# the registry default (gender-matched to the voice when none is given).
DEFAULT_AVATAR_CHARACTER = ""
DEFAULT_AVATAR_STYLE = ""
DEFAULT_VOICE_NAME = "en-US-Ava:DragonHDLatestNeural"
DEFAULT_VOICE_TYPE = "azure-standard"

# Per-language configuration for the avatar session.
# DragonHD has native voice personas for 6 locales (see docs). For other
# languages en-US-Ava is multilingual and works as a fallback.
# Source: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/high-definition-voices
VOICE_CONFIG: Dict[str, Dict[str, str]] = {
    # --- Native DragonHD voices (best quality for these locales) ---
    "en-US": {"voice": "en-US-Ava:DragonHDLatestNeural",       "name": "English"},
    "fr-FR": {"voice": "fr-FR-Vivienne:DragonHDLatestNeural",   "name": "French"},
    "es-ES": {"voice": "es-ES-Ximena:DragonHDLatestNeural",     "name": "Spanish"},
    "de-DE": {"voice": "de-DE-Seraphina:DragonHDLatestNeural",  "name": "German"},
    "ja-JP": {"voice": "ja-JP-Nanami:DragonHDLatestNeural",     "name": "Japanese"},
    "zh-CN": {"voice": "zh-CN-Xiaochen:DragonHDLatestNeural",   "name": "Chinese"},
    # --- Fallback: en-US-Ava is multilingual DragonHD ---
    "it-IT": {"voice": "en-US-Ava:DragonHDLatestNeural",        "name": "Italian"},
    "pt-BR": {"voice": "en-US-Ava:DragonHDLatestNeural",        "name": "Portuguese"},
    "ko-KR": {"voice": "en-US-Ava:DragonHDLatestNeural",        "name": "Korean"},
    "ar-SA": {"voice": "en-US-Ava:DragonHDLatestNeural",        "name": "Arabic"},
}


def _build_wss_url(config: AzureConfig, model: str, api_version: str = VOICE_API_VERSION) -> str:
    """Build the Azure Voice Live WebSocket URL."""
    endpoint = config.speech_endpoint.rstrip("/")
    host = endpoint.replace("https://", "").replace("http://", "")
    return (
        f"wss://{host}/voice-live/realtime"
        f"?api-version={api_version}"
        f"&model={model}"
    )


def _get_auth_headers(config: AzureConfig) -> Dict[str, str]:
    """Get authentication headers for the WebSocket connection."""
    if config.use_managed_identity:
        credential = DefaultAzureCredential()
        # VoiceLive SDK uses https://ai.azure.com/.default scope
        token = credential.get_token("https://ai.azure.com/.default")
        return {"Authorization": f"Bearer {token.token}"}
    if config.speech_key:
        return {"api-key": config.speech_key}
    return {}


def build_session_config(
    language: str = "en-US",
    avatar_character: str = DEFAULT_AVATAR_CHARACTER,
    avatar_style: str = DEFAULT_AVATAR_STYLE,
    voice_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the session.update payload with avatar config.

    If an allowlisted voice_name is provided by the caller, it wins over the
    language default — this lets the frontend voice picker take effect in
    the realtime session. Otherwise we fall back to the native DragonHD
    persona for the requested language. Instructions are always server-side;
    ``avatar_style`` is ignored (the registry owns styles).
    """
    if language not in VOICE_CONFIG:
        language = "en-US"
    lang_cfg = VOICE_CONFIG[language]
    resolved_voice = voice_name if is_allowed_voice(voice_name) else lang_cfg["voice"]
    lang_name = lang_cfg["name"]

    # Session-level instructions lock the avatar into the target language
    default_instructions = (
        f"You are a professional presentation assistant. "
        f"You MUST speak exclusively in {lang_name}. "
        f"Use a native {lang_name} accent and natural pronunciation. "
        f"Read all text exactly as provided, in {lang_name}. "
        f"Do not translate or add commentary unless asked."
    )

    # Resolve to a registry entry (handles legacy ids via aliases). When
    # the caller passes nothing, gender-match against the resolved voice.
    if avatar_character:
        entry = avatar_registry.get(avatar_character)
    else:
        entry = avatar_registry.for_voice(resolved_voice)

    session: Dict[str, Any] = {
        "modalities": ["text", "audio", "avatar"],
        "turn_detection": {"type": "azure_semantic_vad"},
        "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
        "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
        "voice": {
            "name": resolved_voice,
            "type": DEFAULT_VOICE_TYPE,
        },
        "avatar": avatar_registry.voice_live_session_avatar(entry),
        "instructions": default_instructions,
    }

    logger.info(
        "Session config: lang=%s, voice=%s, avatar=%s",
        language, resolved_voice, entry.id,
    )
    return session


async def handle_voice_proxy(
    client_ws: Any,
    config: AzureConfig,
    avatar_character: str = DEFAULT_AVATAR_CHARACTER,
    avatar_style: str = DEFAULT_AVATAR_STYLE,
    language: str = "en-US",
    voice_name: Optional[str] = None,
) -> None:
    """Handle a WebSocket proxy connection between client and Azure Voice API.

    Args:
        client_ws: The client-side WebSocket (from FastAPI)
        config: Azure configuration
        avatar_character: Avatar character name
        avatar_style: Avatar style
        language: Language code
        voice_name: Optional voice id (must be allowlisted)
    """
    model = config.openai_chat_deployment or "gpt-4o"
    wss_url = _build_wss_url(config, model)
    headers = _get_auth_headers(config)

    logger.info("Connecting to Azure Voice API: %s", wss_url[:80])

    try:
        async with websockets.connect(
            wss_url,
            additional_headers=headers,
            max_size=4 * 1024 * 1024,  # 4MB
            ping_interval=30,
        ) as azure_ws:
            logger.info("Connected to Azure Voice API")

            # Send proxy.connected to client
            await client_ws.send_json({"type": "proxy.connected", "message": "Connected to Azure Voice API"})

            # Send initial session config
            session_config = build_session_config(
                language=language,
                avatar_character=avatar_character,
                avatar_style=avatar_style,
                voice_name=voice_name,
            )
            await azure_ws.send(json.dumps({
                "type": "session.update",
                "session": session_config,
            }))
            logger.info("Sent session config")

            # Bidirectional forwarding
            entry = avatar_registry.get(avatar_character or None)
            redact = {entry.foundry_name: entry.id} if entry.customized and entry.foundry_name != entry.id else {}
            await asyncio.gather(
                _forward_client_to_azure(client_ws, azure_ws),
                _forward_azure_to_client(azure_ws, client_ws, redact),
            )

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error("Azure Voice API rejected connection: %s", e)
        try:
            await client_ws.send_json({"type": "error", "error": {"message": f"Azure connection failed: {e}"}})
        except Exception:
            pass
    except Exception as e:
        logger.error("Voice proxy error: %s", e)
        try:
            await client_ws.send_json({"type": "error", "error": {"message": str(e)}})
        except Exception:
            pass


# Client → Azure message types the browser legitimately sends. Anything else
# (notably ``session.update``, which could override server-side instructions,
# voice or avatar) is dropped.
ALLOWED_CLIENT_TYPES = frozenset({
    "conversation.item.create",
    "response.create",
    "response.cancel",
    "session.avatar.connect",
    "input_audio_buffer.append",
    "input_audio_buffer.commit",
    "input_audio_buffer.clear",
})
MAX_CLIENT_MESSAGE_BYTES = 256 * 1024
MAX_CLIENT_TEXT_CHARS = 8_000


def sanitize_client_message(data: str) -> Optional[str]:
    """Return the message to forward to Azure, or ``None`` to drop it."""
    if not isinstance(data, str) or len(data) > MAX_CLIENT_MESSAGE_BYTES:
        return None
    try:
        msg = json.loads(data)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(msg, dict):
        return None
    msg_type = msg.get("type")
    if msg_type not in ALLOWED_CLIENT_TYPES:
        return None
    if msg_type == "response.create":
        resp = msg.get("response")
        if isinstance(resp, dict):
            # Never let the client override instructions / voice / tools.
            msg = {"type": "response.create"}
            if isinstance(resp.get("modalities"), list):
                msg["response"] = {"modalities": resp["modalities"]}
    elif msg_type == "conversation.item.create":
        item = msg.get("item")
        if not isinstance(item, dict) or item.get("role") not in {"user", None}:
            return None
        total = 0
        for part in item.get("content") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                total += len(part["text"])
        if total > MAX_CLIENT_TEXT_CHARS:
            return None
    return json.dumps(msg)


async def _forward_client_to_azure(client_ws: Any, azure_ws: Any) -> None:
    """Forward allowlisted messages from browser client to Azure Voice API."""
    try:
        while True:
            data = await client_ws.receive_text()
            safe = sanitize_client_message(data)
            if safe is None:
                logger.info("Client→Azure: dropped disallowed message (len=%s)", len(data))
                continue
            logger.debug("Client→Azure: len=%s", len(safe))
            await azure_ws.send(safe)
    except Exception as e:
        logger.info("Client→Azure forwarding ended: %s: %s", type(e).__name__, e)


def redact_server_message(message: str, redact: Optional[Dict[str, str]]) -> str:
    """Replace server-only custom avatar character names with their neutral ids."""
    for secret, public in (redact or {}).items():
        if secret and secret in message:
            message = message.replace(secret, public)
    return message


async def _forward_azure_to_client(azure_ws: Any, client_ws: Any, redact: Optional[Dict[str, str]] = None) -> None:
    """Forward messages from Azure Voice API to browser client."""
    try:
        async for message in azure_ws:
            if isinstance(message, str):
                # Log message types at INFO level for debugging auto-navigation
                try:
                    msg_data = json.loads(message)
                    msg_type = msg_data.get("type", "unknown")
                    logger.debug("Azure→Client: type=%s", msg_type)
                except (json.JSONDecodeError, AttributeError):
                    logger.debug("Azure→Client: (non-JSON) len=%s", len(message))
                await client_ws.send_text(redact_server_message(message, redact))
            else:
                # Binary message
                await client_ws.send_bytes(message)
    except Exception as e:
        logger.debug("Azure→Client forwarding ended: %s", e)

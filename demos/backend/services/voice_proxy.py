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

logger = logging.getLogger(__name__)

VOICE_API_VERSION = "2025-05-01-preview"
COGNITIVE_DOMAIN = "cognitiveservices.azure.com"

DEFAULT_AVATAR_CHARACTER = "lisa"
DEFAULT_AVATAR_STYLE = "casual-sitting"
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
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        return {"Authorization": f"Bearer {token.token}"}
    if config.speech_key:
        return {"api-key": config.speech_key}
    return {}


def build_session_config(
    language: str = "en-US",
    avatar_character: str = DEFAULT_AVATAR_CHARACTER,
    avatar_style: str = DEFAULT_AVATAR_STYLE,
    voice_name: Optional[str] = None,
    instructions: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the session.update payload with avatar config.

    If voice_name is provided by the caller, it wins over the language
    default — this lets the frontend voice picker actually take effect
    in the realtime session. Otherwise we fall back to the native
    DragonHD persona for the requested language.
    """
    lang_cfg = VOICE_CONFIG.get(language, VOICE_CONFIG["en-US"])
    resolved_voice = voice_name if voice_name else lang_cfg["voice"]
    lang_name = lang_cfg["name"]

    # Session-level instructions lock the avatar into the target language
    default_instructions = (
        f"You are a professional presentation assistant. "
        f"You MUST speak exclusively in {lang_name}. "
        f"Use a native {lang_name} accent and natural pronunciation. "
        f"Read all text exactly as provided, in {lang_name}. "
        f"Do not translate or add commentary unless asked."
    )

    session: Dict[str, Any] = {
        "modalities": ["text", "audio", "avatar"],
        "turn_detection": {"type": "azure_semantic_vad"},
        "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
        "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
        "voice": {
            "name": resolved_voice,
            "type": DEFAULT_VOICE_TYPE,
        },
        "avatar": {
            "character": avatar_character,
            "style": avatar_style if avatar_style else None,
            "customized": False,
        },
        "instructions": instructions or default_instructions,
    }

    logger.info(
        "Session config: lang=%s, voice=%s, avatar=%s/%s",
        language, resolved_voice, avatar_character, avatar_style,
    )
    return session


async def handle_voice_proxy(
    client_ws: Any,
    config: AzureConfig,
    avatar_character: str = DEFAULT_AVATAR_CHARACTER,
    avatar_style: str = DEFAULT_AVATAR_STYLE,
    language: str = "en-US",
    instructions: Optional[str] = None,
    voice_name: Optional[str] = None,
) -> None:
    """Handle a WebSocket proxy connection between client and Azure Voice API.

    Args:
        client_ws: The client-side WebSocket (from FastAPI)
        config: Azure configuration
        avatar_character: Avatar character name
        avatar_style: Avatar style
        language: Language code
        instructions: Optional system instructions for the LLM
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
                instructions=instructions,
            )
            await azure_ws.send(json.dumps({
                "type": "session.update",
                "session": session_config,
            }))
            logger.info("Sent session config with avatar: %s/%s", avatar_character, avatar_style)

            # Bidirectional forwarding
            await asyncio.gather(
                _forward_client_to_azure(client_ws, azure_ws),
                _forward_azure_to_client(azure_ws, client_ws),
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


async def _forward_client_to_azure(client_ws: Any, azure_ws: Any) -> None:
    """Forward messages from browser client to Azure Voice API."""
    try:
        while True:
            data = await client_ws.receive_text()
            logger.debug("Client→Azure: %s", data[:100])
            await azure_ws.send(data)
    except Exception as e:
        logger.debug("Client→Azure forwarding ended: %s", e)


async def _forward_azure_to_client(azure_ws: Any, client_ws: Any) -> None:
    """Forward messages from Azure Voice API to browser client."""
    try:
        async for message in azure_ws:
            if isinstance(message, str):
                # Log message types at INFO level for debugging auto-navigation
                try:
                    msg_data = json.loads(message)
                    msg_type = msg_data.get("type", "unknown")
                    logger.info("Azure→Client: type=%s payload=%s", msg_type, message[:400])
                except (json.JSONDecodeError, AttributeError):
                    logger.debug("Azure→Client: (non-JSON) %s", message[:80])
                await client_ws.send_text(message)
            else:
                # Binary message
                await client_ws.send_bytes(message)
    except Exception as e:
        logger.debug("Azure→Client forwarding ended: %s", e)

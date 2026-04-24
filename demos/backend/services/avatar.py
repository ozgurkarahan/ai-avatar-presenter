"""Avatar TTS orchestration service using Azure AI Speech."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

import requests
from azure.identity import DefaultAzureCredential

from config import AzureConfig

# Voice mapping per language
VOICE_MAP = {
    "en-US": "en-US-AvaMultilingualNeural",
    "fr-FR": "fr-FR-DeniseNeural",
    "es-ES": "es-ES-ElviraNeural",
}

AVATAR_MAP = {
    "lisa": "lisa",
    "harry": "harry",
    "jeff": "jeff",
    "lori": "lori",
    "max": "max",
    "meg": "meg",
}

# Azure Batch Avatar Synthesis: each character supports a specific set of styles.
# Mismatched style -> 400 "style X is not supported for avatar character Y".
# Ref: https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech-avatar/standard-avatars
AVATAR_STYLES = {
    "lisa": "casual-sitting",
    "harry": "business",
    "jeff": "business",
    "lori": "casual",
    "max": "business",
    "meg": "business",
}

# Docs-verified intro gestures per (character, style). Used when the caller
# asks for an opening gesture on slide 1. Entries are pulled directly from
# the Azure standard-avatar docs, so any value here is known to render.
# Missing keys -> no gesture injected (safe fallback).
AVATAR_INTRO_GESTURES: dict[tuple[str, str], str] = {
    ("lisa", "casual-sitting"): "show-front-1",
    ("lisa", "graceful-sitting"): "wave-left-1",
    ("lisa", "technical-sitting"): "wave-left-1",
    ("harry", "business"): "hello",
    ("harry", "casual"): "hello",
    ("harry", "youthful"): "hello",
    ("jeff", "business"): "here",
    ("lori", "casual"): "hello",
    ("lori", "graceful"): "welcome",
    ("lori", "formal"): "hi",
    ("max", "business"): "welcome",
    ("max", "casual"): "hello",
    ("meg", "business"): "say-hi",
    ("meg", "casual"): "say-hi",
    ("meg", "formal"): "say-hi",
}

# H1.5 2026-04-24: Lisa casual-sitting is the most photo-realistic standard
# avatar in Azure's catalog (per docs + public demos) and ships with
# presenter-friendly gestures (show-front-1..9, think-twice, thumbsup).
# Harry/business is the male counterpart with welcome/hello/thanks gestures.
# We previously defaulted to Max (more gestures, but noticeably 3D-stylized)
# — client feedback 2026-04-23 called this out as "not natural enough".
DEFAULT_AVATAR = "lisa"
DEFAULT_AVATAR_STYLE = "casual-sitting"


def style_for(avatar: str) -> str:
    """Pick a valid talkingAvatarStyle for the given character."""
    return AVATAR_STYLES.get(avatar, DEFAULT_AVATAR_STYLE)


@dataclass
class AvatarJobStatus:
    job_id: str
    status: str
    video_url: Optional[str] = None
    error: Optional[str] = None


def _get_speech_auth_header(config: AzureConfig) -> dict:
    """Get authorization header for Speech REST APIs."""
    if config.use_managed_identity:
        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        return {"Authorization": f"Bearer {token.token}"}
    return {"Ocp-Apim-Subscription-Key": config.speech_key}


def _get_speech_base_url(config: AzureConfig) -> str:
    """Get the base URL for Speech REST APIs."""
    if config.use_managed_identity and config.speech_endpoint:
        return config.speech_endpoint.rstrip("/")
    return f"https://{config.speech_region}.api.cognitive.microsoft.com"


def _fetch_relay_token(base_url: str, auth_header: dict) -> dict | None:
    """Fetch ICE/TURN relay credentials for WebRTC avatar streaming."""
    url = f"{base_url}/tts/cognitiveservices/avatar/relay/token/v1"
    try:
        response = requests.get(url, headers=auth_header, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "urls": data.get("Urls", []),
            "username": data.get("Username", ""),
            "credential": data.get("Password", ""),
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Relay token fetch failed: %s", e)
        return None


def get_speech_token(config: AzureConfig) -> dict:
    """Get a short-lived speech token + TURN relay credentials for real-time avatar.

    For AAD auth: exchanges AAD token for speech JWT, then uses the JWT
    to fetch TURN relay credentials (relay endpoint supports JWT auth).
    """
    if config.use_managed_identity:
        credential = DefaultAzureCredential()
        aad_token = credential.get_token("https://cognitiveservices.azure.com/.default")
        base_url = config.speech_endpoint.rstrip("/")

        # Exchange AAD token for a short-lived speech JWT
        token_url = f"{base_url}/sts/v1.0/issueToken"
        headers = {"Authorization": f"Bearer {aad_token.token}", "Content-Length": "0"}
        response = requests.post(token_url, headers=headers, timeout=10)
        response.raise_for_status()
        speech_jwt = response.text

        # Fetch TURN relay token using the speech JWT (AAD token doesn't work for this endpoint)
        relay = _fetch_relay_token(base_url, {"Authorization": f"Bearer {speech_jwt}"})

        # Extract custom domain host for WSS endpoint
        from urllib.parse import urlparse
        host = urlparse(config.speech_endpoint).hostname

        # Build aad# token format for SDK Entra auth (aad#resourceId#aadToken)
        resource_id = config.speech_resource_id or ""
        aad_auth_token = f"aad#{resource_id}#{aad_token.token}" if resource_id else None

        return {
            "token": speech_jwt,
            "aad_token": aad_auth_token,
            "region": config.speech_region,
            "endpoint": config.speech_endpoint,
            "wss_url": f"wss://{host}/tts/cognitiveservices/websocket/v1?enableTalkingAvatar=true",
            "ice_servers": relay,
            "auth_type": "aad",
        }

    # Key-based auth path
    token_url = (
        f"https://{config.speech_region}.api.cognitive.microsoft.com"
        "/sts/v1.0/issueToken"
    )
    headers = {"Ocp-Apim-Subscription-Key": config.speech_key}
    response = requests.post(token_url, headers=headers, timeout=10)
    response.raise_for_status()
    speech_token = response.text

    # Fetch TURN relay with subscription key
    relay = _fetch_relay_token(
        f"https://{config.speech_region}.tts.speech.microsoft.com",
        {"Ocp-Apim-Subscription-Key": config.speech_key},
    )

    return {
        "token": speech_token,
        "region": config.speech_region,
        "ice_servers": relay,
        "auth_type": "key",
    }


def build_ssml(
    text: str,
    language: str,
    voice: Optional[str] = None,
    *,
    intro_gesture_for: Optional[str] = None,
) -> str:
    """Build SSML for avatar synthesis.

    Includes a 250 ms leading <break> because Azure batch avatar synthesis
    consistently clips the first ~100 ms of spoken audio; the explicit pause
    preserves the first word (e.g. "Today", "Hello").

    Args:
        text: Narration plain text. Special XML chars are escaped.
        language: BCP-47 locale (e.g. "en-US").
        voice: Explicit voice name (overrides VOICE_MAP).
        intro_gesture_for: Character name (e.g. "lisa", "harry", "max").
            If set AND the (character, style) pair has a docs-verified
            gesture in AVATAR_INTRO_GESTURES, inject the bookmark right
            after the leading pause. Unknown pairs -> no gesture (safe).
            Callers should pass this ONLY on the first slide of a deck.
    """
    voice_name = voice or VOICE_MAP.get(language, VOICE_MAP["en-US"])
    safe_text = _xml_escape(text or "")
    gesture = ""
    if intro_gesture_for:
        style = AVATAR_STYLES.get(intro_gesture_for, "")
        gesture_name = AVATAR_INTRO_GESTURES.get((intro_gesture_for, style))
        if gesture_name:
            gesture = f"<bookmark mark='gesture.{gesture_name}'/>"
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="{language}">'
        f'<voice name="{voice_name}">'
        f'<break time="250ms"/>{gesture}{safe_text}'
        f"</voice></speak>"
    )


def submit_batch_synthesis(
    config: AzureConfig,
    texts: list[str],
    language: str,
    avatar: str = DEFAULT_AVATAR,
) -> str:
    """Submit a batch avatar synthesis job."""
    job_id = str(uuid.uuid4())
    avatar_char = AVATAR_MAP.get(avatar, DEFAULT_AVATAR)
    base_url = _get_speech_base_url(config)

    url = f"{base_url}/avatar/batchsyntheses/{job_id}?api-version=2024-08-01"

    combined_text = " ".join(texts)
    ssml = build_ssml(combined_text, language)

    payload = {
        "inputKind": "SSML",
        "inputs": [{"content": ssml}],
        "avatarConfig": {
            "talkingAvatarCharacter": avatar_char,
            "talkingAvatarStyle": style_for(avatar_char),
            "videoFormat": "mp4",
            "videoCodec": "h264",
            "subtitleType": "soft_embedded",
            "backgroundColor": "#FFFFFFFF",
        },
    }

    headers = {**_get_speech_auth_header(config), "Content-Type": "application/json"}
    response = requests.put(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return job_id


def get_batch_synthesis_status(config: AzureConfig, job_id: str) -> AvatarJobStatus:
    """Check the status of a batch synthesis job."""
    base_url = _get_speech_base_url(config)
    url = f"{base_url}/avatar/batchsyntheses/{job_id}?api-version=2024-08-01"

    headers = _get_speech_auth_header(config)
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    data = response.json()
    status = data.get("status", "unknown")
    video_url = None
    error = None

    if status == "Succeeded":
        outputs = data.get("outputs", {})
        video_url = outputs.get("result")
        status = "succeeded"
    elif status == "Failed":
        error = data.get("properties", {}).get("error", {}).get("message", "Unknown error")
        status = "failed"
    elif status in ("NotStarted", "Running"):
        status = "running"

    return AvatarJobStatus(
        job_id=job_id, status=status, video_url=video_url, error=error
    )


def wait_for_batch_synthesis(
    config: AzureConfig, job_id: str, timeout: int = 600, poll_interval: int = 5
) -> AvatarJobStatus:
    """Poll until a batch synthesis job completes or times out."""
    start = time.time()
    while time.time() - start < timeout:
        status = get_batch_synthesis_status(config, job_id)
        if status.status in ("succeeded", "failed"):
            return status
        time.sleep(poll_interval)
    return AvatarJobStatus(job_id=job_id, status="timeout", error="Job timed out")

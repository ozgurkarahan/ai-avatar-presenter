"""Expose existing AI Presenter services as callable tools for the agent."""

from __future__ import annotations

import json
from typing import Optional

try:
    from agent_framework.core import tool
except ImportError:
    # Allow the module to work without agent-framework installed
    def tool(fn):  # type: ignore
        return fn

from config import load_config, AzureConfig
from services.translation import get_openai_client, translate_text, detect_language
from services.avatar import build_ssml

_config: Optional[AzureConfig] = None


def _get_config() -> AzureConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


@tool
def translate_slide_notes(text: str, target_language: str) -> str:
    """Translate presentation slide text to the target language.

    Args:
        text: The source text to translate (e.g. speaker notes).
        target_language: BCP-47 code like 'fr-FR', 'es-ES', 'en-US'.

    Returns:
        The translated text.
    """
    cfg = _get_config()
    client = get_openai_client(cfg)
    return translate_text(client, text, target_language, cfg.openai_chat_deployment)


@tool
def detect_text_language(text: str) -> str:
    """Detect the language of a given text.

    Args:
        text: Text to analyze.

    Returns:
        A BCP-47 language code (e.g. 'en-US', 'fr-FR').
    """
    cfg = _get_config()
    client = get_openai_client(cfg)
    return detect_language(client, text, cfg.openai_chat_deployment)


@tool
def ask_about_slides(slide_context: str, question: str) -> str:
    """Answer a question about presentation slides based on provided slide content.

    Use this when the user asks a question about what is on a slide.
    The slide_context should contain the slide title, body, and speaker notes.

    Args:
        slide_context: The slide content (title, body, notes) to answer from.
        question: The user's question about the slides.

    Returns:
        A concise answer based on the slide content.
    """
    cfg = _get_config()
    client = get_openai_client(cfg)
    response = client.chat.completions.create(
        model=cfg.openai_chat_deployment,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an AI assistant helping users understand presentation slides. "
                    "Answer the user's question based on the slide content provided below. "
                    "If the answer cannot be found in the slides, say so. "
                    "Be concise and informative.\n\n"
                    f"Slide content:\n{slide_context}"
                ),
            },
            {"role": "user", "content": question},
        ],
        temperature=0.3,
        max_completion_tokens=1024,
    )
    content = response.choices[0].message.content
    return content.strip() if content else "I couldn't generate an answer."


@tool
def generate_avatar_speech_ssml(text: str, language: str) -> str:
    """Generate SSML markup for avatar text-to-speech.

    Use this to prepare text for the AI avatar to speak aloud.

    Args:
        text: The text the avatar should speak.
        language: BCP-47 language code (e.g. 'en-US', 'fr-FR', 'es-ES').

    Returns:
        SSML string ready for Azure Speech synthesis.
    """
    return build_ssml(text, language)


@tool
def prepare_slide_for_presentation(
    slide_title: str,
    slide_body: str,
    slide_notes: str,
    target_language: str,
) -> str:
    """Prepare a slide for avatar presentation: translate notes and generate SSML.

    This is a convenience tool that chains translation + SSML generation.
    Use it when the user asks the avatar to present a slide in a specific language.

    Args:
        slide_title: The slide title text.
        slide_body: The slide body text.
        slide_notes: The speaker notes to narrate.
        target_language: BCP-47 language code for the output (e.g. 'fr-FR').

    Returns:
        JSON with translated_text and ssml keys.
    """
    narration = slide_notes or slide_body or slide_title
    if not narration.strip():
        return json.dumps({"error": "No text available for this slide"})

    cfg = _get_config()
    client = get_openai_client(cfg)

    # Translate if not already in the target language
    detected = detect_language(client, narration, cfg.openai_chat_deployment)
    if detected.split("-")[0] != target_language.split("-")[0]:
        narration = translate_text(client, narration, target_language, cfg.openai_chat_deployment)

    ssml = build_ssml(narration, target_language)
    return json.dumps({
        "translated_text": narration,
        "ssml": ssml,
        "language": target_language,
    })


ALL_TOOLS = [
    translate_slide_notes,
    detect_text_language,
    ask_about_slides,
    generate_avatar_speech_ssml,
    prepare_slide_for_presentation,
]

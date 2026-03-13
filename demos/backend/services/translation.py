"""Translation service using Azure OpenAI GPT-4o."""

from __future__ import annotations

from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

from config import AzureConfig

LANGUAGE_NAMES = {
    "en-US": "English",
    "fr-FR": "French",
    "es-ES": "Spanish",
}

SYSTEM_PROMPT = (
    "You are a professional translator. Translate the following text to {language}. "
    "Preserve the original formatting, tone, and meaning. "
    "Return only the translated text, nothing else."
)


def get_openai_client(config: AzureConfig) -> AzureOpenAI:
    if config.use_managed_identity:
        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        return AzureOpenAI(
            azure_endpoint=config.openai_endpoint,
            azure_ad_token=token.token,
            api_version="2024-08-01-preview",
        )
    return AzureOpenAI(
        azure_endpoint=config.openai_endpoint,
        api_key=config.openai_key,
        api_version="2024-08-01-preview",
    )


def translate_text(
    client: AzureOpenAI,
    text: str,
    target_language: str,
    deployment: str,
) -> str:
    """Translate text to target language using GPT-4o.

    Args:
        client: Azure OpenAI client.
        text: Source text to translate.
        target_language: Target language code (e.g., 'fr-FR', 'es-ES').
        deployment: Azure OpenAI deployment name.

    Returns:
        Translated text.
    """
    if not text.strip():
        return ""

    lang_name = LANGUAGE_NAMES.get(target_language, target_language)

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(language=lang_name)},
            {"role": "user", "content": text},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    return response.choices[0].message.content.strip()


def detect_language(
    client: AzureOpenAI,
    text: str,
    deployment: str,
) -> str:
    """Detect the language of a text using GPT-4o.

    Returns a language code like 'en-US', 'fr-FR', 'es-ES'.
    """
    if not text.strip():
        return "en-US"

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {
                "role": "system",
                "content": (
                    "Detect the language of the following text. "
                    "Respond with only the BCP-47 language code (e.g., en-US, fr-FR, es-ES)."
                ),
            },
            {"role": "user", "content": text[:500]},
        ],
        temperature=0,
        max_tokens=10,
    )

    return response.choices[0].message.content.strip()

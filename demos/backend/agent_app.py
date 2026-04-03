"""AI Presenter Agent — Microsoft Agent Framework entry point.

Run standalone:
    python agent_app.py

This starts an HTTP server (default port 8080) that exposes the agent
as a deployable web service compatible with Azure AI Foundry hosted agents.
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv(override=False)  # Foundry runtime env vars take precedence

from azure.identity.aio import DefaultAzureCredential
from agent_framework.azure import AzureAIClient
from azure.ai.agentserver.agentframework import from_agent_framework

from agent_tools import ALL_TOOLS

INSTRUCTIONS = """\
You are the AI Presenter Assistant — an AI-powered avatar presentation helper.

## Your Capabilities (via tools)
- **translate_slide_notes**: Translate text (e.g., speaker notes) to French, Spanish, or English.
- **detect_text_language**: Detect the language of a given text.
- **ask_about_slides**: Answer questions about slide content when given the slide text.
- **generate_avatar_speech_ssml**: Generate SSML markup for avatar text-to-speech.
- **prepare_slide_for_presentation**: All-in-one: translate speaker notes and generate SSML for the avatar.

## Behavioral Guidelines
1. When the user asks to present a slide, use **prepare_slide_for_presentation** with the slide
   title, body, and notes. Return the translated text and SSML.
2. When the user asks a question about slides, use **ask_about_slides** with the slide content
   as context.
3. When the user asks for translation only, use **translate_slide_notes**.
4. Always be concise. If a tool returns JSON, extract the relevant fields for the user.
5. If the user does not specify a language, default to English (en-US).
6. When multiple slides are involved, process them one at a time and summarize.
"""


async def main():
    credential = DefaultAzureCredential()

    async with AzureAIClient(
        project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT"),
        model_deployment_name=os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4.1"),
        credential=credential,
    ).as_agent(
        name="ai-presenter",
        instructions=INSTRUCTIONS,
        tools=ALL_TOOLS,
    ) as agent:
        # HTTP server mode — deployable as a web service on Foundry
        await from_agent_framework(agent).run_async()


if __name__ == "__main__":
    asyncio.run(main())

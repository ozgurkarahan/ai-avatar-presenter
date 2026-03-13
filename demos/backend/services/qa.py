"""Slide Q&A service using RAG (in-memory vector search + Azure OpenAI)."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from openai import AzureOpenAI

from config import AzureConfig
from services.pptx_parser import PresentationData

logger = logging.getLogger(__name__)

# In-memory vector store: {doc_id: {"embedding": [...], "metadata": {...}}}
_vector_store: dict[str, dict] = {}

QA_SYSTEM_PROMPT = (
    "You are an AI assistant helping users understand presentation slides. "
    "Answer the user's question based on the slide content provided below. "
    "If the answer cannot be found in the slides, say so. "
    "Be concise and informative.\n\n"
    "Slide content:\n{context}"
)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))


def generate_embedding(
    client: AzureOpenAI, text: str, deployment: str
) -> list[float]:
    """Generate an embedding vector for the given text."""
    response = client.embeddings.create(model=deployment, input=text)
    return response.data[0].embedding


def index_presentation(
    config: AzureConfig,
    openai_client: AzureOpenAI,
    presentation: PresentationData,
) -> None:
    """Index all slides of a presentation into the in-memory vector store."""
    for slide in presentation.slides:
        content = f"Title: {slide.title}\n\nContent: {slide.body}\n\nSpeaker Notes: {slide.notes}"
        embedding = generate_embedding(
            openai_client, content, config.openai_embedding_deployment
        )
        doc_id = f"{presentation.id}-{slide.index}"
        _vector_store[doc_id] = {
            "embedding": embedding,
            "document": content,
            "metadata": {
                "presentationId": presentation.id,
                "slideIndex": slide.index,
                "title": slide.title,
                "body": slide.body,
                "notes": slide.notes,
            },
        }
    logger.info("Indexed %d slides for presentation %s", len(presentation.slides), presentation.id)


def search_slides(
    config: AzureConfig,
    openai_client: AzureOpenAI,
    query: str,
    presentation_id: str,
    slide_index: Optional[int] = None,
    top_k: int = 3,
) -> list[dict]:
    """Search for relevant slides using cosine similarity."""
    query_embedding = generate_embedding(
        openai_client, query, config.openai_embedding_deployment
    )

    scored = []
    for doc_id, doc in _vector_store.items():
        meta = doc["metadata"]
        if meta["presentationId"] != presentation_id:
            continue
        if slide_index is not None and meta["slideIndex"] != slide_index:
            continue
        score = _cosine_similarity(query_embedding, doc["embedding"])
        scored.append((score, meta))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [meta for _, meta in scored[:top_k]]


def answer_question(
    config: AzureConfig,
    openai_client: AzureOpenAI,
    question: str,
    presentation_id: str,
    slide_index: Optional[int] = None,
) -> dict:
    """Answer a question about slide content using RAG.

    Returns:
        Dict with 'answer' and 'source_slides' keys.
    """
    results = search_slides(
        config, openai_client, question, presentation_id, slide_index
    )

    if not results:
        return {
            "answer": "I couldn't find relevant information in the slides to answer your question.",
            "source_slides": [],
        }

    context_parts = []
    source_slides = []
    for r in results:
        idx = r["slideIndex"]
        source_slides.append(idx)
        context_parts.append(
            f"[Slide {idx + 1}] {r['title']}\n{r['body']}\nNotes: {r['notes']}"
        )
    context = "\n\n---\n\n".join(context_parts)

    response = openai_client.chat.completions.create(
        model=config.openai_chat_deployment,
        messages=[
            {
                "role": "system",
                "content": QA_SYSTEM_PROMPT.format(context=context),
            },
            {"role": "user", "content": question},
        ],
        temperature=0.3,
        max_tokens=1024,
    )

    return {
        "answer": response.choices[0].message.content.strip(),
        "source_slides": sorted(set(source_slides)),
    }

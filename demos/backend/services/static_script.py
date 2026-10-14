"""UC2 script generation — GPT-4.1 streaming, one SlideNarration per slide.

Output shape is slide-first (NOT turn-based). We prompt the model to return
a JSON object { narrations: [{slide_index, narration, speaking_style?,
duration_hint_s?}, ...] } and stream each narration object to the client
as it is produced (NDJSON), so the UI can show a per-slide "typing" effect.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Optional

from config import AzureConfig
from services.static_models import (
    ScriptRequest,
    SlideNarration,
    StaticDocument,
)
from services.translation import get_openai_client

log = logging.getLogger(__name__)


LANGUAGE_NAMES = {
    "en-US": "English",
    "fr-FR": "French",
    "es-ES": "Spanish",
    "de-DE": "German",
    "it-IT": "Italian",
    "pt-BR": "Brazilian Portuguese",
    "zh-CN": "Mandarin Chinese (Simplified)",
    "ja-JP": "Japanese",
}

STYLE_DIRECTIVES = {
    "casual":    "Warm, conversational tone. Use contractions. Sound like a knowledgeable colleague presenting.",
    "formal":    "Polished, measured tone. Precise vocabulary. Suitable for executive or investor audiences.",
    "explainer": "Clear pedagogical framing. Short sentences. Name the key idea then elaborate with one concrete example.",
    "marketing": "Energetic, benefit-forward. Lead with the outcome the viewer gets. End with a subtle call-to-action.",
}


def _build_slide_outline(doc: StaticDocument, max_chars: int = 8000) -> str:
    parts: list[str] = []
    for sl in doc.slides:
        parts.append(f"[slide {sl.index}] {sl.title or ''}")
        if sl.preview_text:
            parts.append(f"    content: {sl.preview_text.strip()[:500]}")
    text = "\n".join(parts)
    return text[:max_chars]


def _build_system_prompt(req: ScriptRequest, doc: StaticDocument) -> str:
    language = LANGUAGE_NAMES.get(req.language, req.language)
    style = STYLE_DIRECTIVES.get(req.style or "explainer", STYLE_DIRECTIVES["explainer"])
    focus = f"\n\nAngle / focus to emphasize: {req.focus}" if req.focus else ""
    n = len(doc.slides)
    return (
        f"You are scripting a single-narrator voiceover for a {n}-slide presentation in {language}.\n"
        f"Produce EXACTLY ONE narration paragraph per slide, 2–5 sentences each, that the viewer hears "
        f"while that slide is on screen.\n\n"
        f"LANGUAGE: Write natural, idiomatic {language} as a native speaker would — native turns of phrase, "
        f"contractions and elisions that sound spoken rather than literally translated. Do NOT mix in English "
        f"words unless they are true borrowings. Proper nouns may stay as-is.\n\n"
        f"Style: {style}\n"
        f"Flow: each narration should feel like it continues naturally from the previous slide — use occasional "
        f"bridge phrases (\"Building on that...\", \"So what does this mean in practice?\"). The first slide "
        f"opens the talk; the last slide closes it.\n"
        f"Avoid reading bullet points verbatim — paraphrase and add the why.{focus}\n\n"
        f"Output format: a JSON object with key `narrations`, which is an array of EXACTLY {n} objects, one "
        f"per slide, in slide order. Each object has:\n"
        f"  - `slide_index` (0-based int, must match the input slide),\n"
        f"  - `narration` (the spoken paragraph, prose only, no stage directions, no markdown),\n"
        f"  - `speaking_style` (optional short hint like \"enthusiastic\", \"calm\", \"authoritative\"),\n"
        f"  - `duration_hint_s` (optional estimated seconds to read aloud at normal pace).\n"
        f"Return ONLY the JSON object, no prose before or after."
    )


async def generate_script_stream(
    cfg: AzureConfig,
    doc: StaticDocument,
    req: ScriptRequest,
) -> AsyncIterator[SlideNarration]:
    """Yield one SlideNarration per slide, in order, as GPT emits them."""
    client = get_openai_client(cfg)
    deployment = cfg.openai_chat_deployment or "gpt-4.1"

    system_prompt = _build_system_prompt(req, doc)
    user_prompt = (
        f"Document title: {doc.title}\n"
        f"Slide count: {len(doc.slides)}\n\n"
        f"Slides:\n{_build_slide_outline(doc)}\n\n"
        f"Generate the narrations now."
    )

    stream = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_completion_tokens=4096,
        response_format={"type": "json_object"},
        stream=True,
    )

    # Build slide_index -> SlideRef map for filling blanks on patch.
    ref_by_idx = {s.index: s for s in doc.slides}
    buf = ""
    emitted: set[int] = set()
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta.content or ""
        except (IndexError, AttributeError):
            delta = ""
        if not delta:
            continue
        buf += delta
        for obj in _extract_narrations(buf, emitted):
            yield _coerce_narration(obj, ref_by_idx, req)

    # Final pass for any leftover not caught mid-stream.
    try:
        final = json.loads(buf)
        items = final.get("narrations", []) if isinstance(final, dict) else []
        for i, t in enumerate(items):
            idx = int(t.get("slide_index", i))
            if idx in emitted:
                continue
            emitted.add(idx)
            yield _coerce_narration(t, ref_by_idx, req)
    except json.JSONDecodeError:
        log.warning("final static-script JSON parse failed; %d narrations already emitted", len(emitted))


def _coerce_narration(obj: dict, ref_by_idx: dict, req: ScriptRequest) -> SlideNarration:
    idx = int(obj.get("slide_index", 0))
    ref = ref_by_idx.get(idx)
    dur = obj.get("duration_hint_s")
    try:
        dur = float(dur) if dur is not None else None
    except (TypeError, ValueError):
        dur = None
    return SlideNarration(
        slide_index=idx,
        slide_image_ref=(ref.image_ref if ref else ""),
        title=(ref.title if ref else None),
        narration=str(obj.get("narration", "")).strip(),
        voice=req.voice,
        speaking_style=(str(obj.get("speaking_style")) if obj.get("speaking_style") else None),
        duration_hint_s=dur,
    )


def _extract_narrations(buf: str, emitted: set[int]):
    """Yield completed narration dicts from an in-progress JSON buffer.

    Same greedy brace-walker the UC3 streamer uses, adapted for the
    `narrations` array.
    """
    start = buf.find('"narrations"')
    if start == -1:
        return
    arr_start = buf.find("[", start)
    if arr_start == -1:
        return
    i = arr_start + 1
    while i < len(buf):
        while i < len(buf) and buf[i] in " \n\r\t,":
            i += 1
        if i >= len(buf) or buf[i] == "]":
            return
        if buf[i] != "{":
            i += 1
            continue
        depth = 0
        j = i
        in_str = False
        esc = False
        while j < len(buf):
            c = buf[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        if j >= len(buf) or depth != 0:
            return
        obj_str = buf[i : j + 1]
        try:
            obj = json.loads(obj_str)
        except json.JSONDecodeError:
            return
        idx = int(obj.get("slide_index", len(emitted)))
        if idx not in emitted:
            emitted.add(idx)
            yield obj
        i = j + 1

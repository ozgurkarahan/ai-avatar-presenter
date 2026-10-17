"""
Generate docs/samples/ai-agents-sample.pptx — a 5-slide demo deck for the podcast.

Theme: AI agents connected to tools through the Model Context Protocol (MCP) —
a realistic, vendor-neutral technology story that works well for a dual-avatar
podcast demo (Interviewer + Expert). Each slide has a title, bullet-friendly
content, and speaker notes that the script-generation prompt can use.

Run: python scripts/generate_sample_pptx.py
Output: docs/samples/ai-agents-sample.pptx
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

OUT = Path(__file__).resolve().parent.parent / "docs" / "samples" / "ai-agents-sample.pptx"

# Deep blue + cyan accent
BRAND_BLUE = RGBColor(0x00, 0x33, 0x66)
BRAND_ACCENT = RGBColor(0x00, 0x9B, 0xDC)
SLATE = RGBColor(0x33, 0x41, 0x55)
CLOUD = RGBColor(0xF1, 0xF5, 0xF9)

SLIDES = [
    {
        "title": "AI Agents — From Answers to Actions",
        "subtitle": "Oz Radio — Demo · Innovation Podcast",
        "bullets": [
            "Agents plan, call tools and observe results",
            "Connected to data and apps through MCP",
            "Humans stay in control of sensitive steps",
        ],
        "notes": (
            "This is the opening slide. Introduce AI agents as the next step after "
            "chat assistants. Frame the conversation around moving from answering "
            "questions to completing multi-step tasks safely on behalf of users."
        ),
    },
    {
        "title": "How an Agent Loop Works",
        "bullets": [
            "The model reads the goal, instructions and context",
            "It chooses a tool and fills in the arguments",
            "The harness runs the tool and returns the result",
            "The loop repeats until the goal is met or a limit is hit",
        ],
        "notes": (
            "This is the technical depth slide. The expert should explain the plan, act, "
            "observe loop. Keep the metaphor accessible — compare it to a new colleague "
            "who follows a checklist and reports back after each step."
        ),
    },
    {
        "title": "Why It Matters — MCP and Context",
        "bullets": [
            "MCP: one open standard to expose tools and data",
            "Build a server once, reuse it across AI clients",
            "Context engineering keeps each step grounded",
            "Least-privilege access by design",
        ],
        "notes": (
            "The interviewer should ask why a protocol matters here. Expert explains that "
            "the Model Context Protocol lets teams expose a tool once and reuse it from many "
            "AI clients, and grounds it in a relatable example such as a ticketing system."
        ),
    },
    {
        "title": "Deployment Case Study — Support Desk Agent",
        "bullets": [
            "Three MCP tools: search knowledge base, read ticket, draft reply",
            "Retrieval-augmented answers with citations",
            "Every outgoing reply approved by a human agent",
            "Quality tracked on a golden set before each release",
        ],
        "notes": (
            "Talk about a realistic deployment. Keep it concrete — one team, a few tools, "
            "measured outcomes. The interviewer should pivot from 'how it works' to "
            "'what it delivers' here."
        ),
    },
    {
        "title": "What's Next — Responsible AI at Scale",
        "bullets": [
            "Small and open-weight models for routine steps",
            "Voice agents with speech-to-text and text-to-speech",
            "Continuous evaluation and observability",
            "Clear governance for every agent in production",
        ],
        "notes": (
            "Wrap up with the forward-looking story. The expert should describe how agents "
            "become dependable services through evaluation, observability and governance. "
            "End on a confident, inviting note about what this means "
            "for the way teams will work."
        ),
    },
]


def _add_title_bar(slide, text: str) -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(1.1))
    shape.fill.solid()
    shape.fill.fore_color.rgb = BRAND_BLUE
    shape.line.fill.background()

    tf = shape.text_frame
    tf.margin_left = Inches(0.6)
    tf.margin_top = Inches(0.25)
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)


def _add_accent_bar(slide) -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(1.1), Inches(13.33), Inches(0.08))
    shape.fill.solid()
    shape.fill.fore_color.rgb = BRAND_ACCENT
    shape.line.fill.background()


def _add_bullets(slide, bullets: list[str]) -> None:
    box = slide.shapes.add_textbox(Inches(0.8), Inches(1.6), Inches(11.5), Inches(5))
    tf = box.text_frame
    tf.word_wrap = True
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f"•  {b}"
        p.font.size = Pt(22)
        p.font.color.rgb = SLATE
        p.space_after = Pt(14)


def _add_footer(slide, n: int, total: int) -> None:
    box = slide.shapes.add_textbox(Inches(0.4), Inches(7.0), Inches(12.5), Inches(0.4))
    tf = box.text_frame
    p = tf.paragraphs[0]
    p.text = f"Oz Radio — Demo   ·   Slide {n} of {total}"
    p.font.size = Pt(10)
    p.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)


def build() -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]

    # Cover slide
    cover = SLIDES[0]
    s = prs.slides.add_slide(blank_layout)
    # Full-bleed blue background
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(7.5))
    bg.fill.solid()
    bg.fill.fore_color.rgb = BRAND_BLUE
    bg.line.fill.background()
    # Accent stripe
    stripe = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(4.6), Inches(13.33), Inches(0.06))
    stripe.fill.solid()
    stripe.fill.fore_color.rgb = BRAND_ACCENT
    stripe.line.fill.background()
    # Title
    tbox = s.shapes.add_textbox(Inches(0.8), Inches(2.4), Inches(11.5), Inches(1.8))
    p = tbox.text_frame.paragraphs[0]
    p.text = cover["title"]
    p.font.size = Pt(44)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    # Subtitle
    sbox = s.shapes.add_textbox(Inches(0.8), Inches(4.8), Inches(11.5), Inches(0.6))
    p = sbox.text_frame.paragraphs[0]
    p.text = cover["subtitle"]
    p.font.size = Pt(20)
    p.font.color.rgb = BRAND_ACCENT
    # Notes
    s.notes_slide.notes_text_frame.text = cover["notes"]

    # Content slides
    total = len(SLIDES)
    for i, data in enumerate(SLIDES[1:], start=2):
        s = prs.slides.add_slide(blank_layout)
        bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = CLOUD
        bg.line.fill.background()
        _add_title_bar(s, data["title"])
        _add_accent_bar(s)
        _add_bullets(s, data["bullets"])
        _add_footer(s, i, total)
        s.notes_slide.notes_text_frame.text = data["notes"]

    prs.core_properties.author = "Oz Radio"
    prs.core_properties.last_modified_by = "Oz Radio"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"Created: {out} ({out.stat().st_size:,} bytes, {len(SLIDES)} slides)")

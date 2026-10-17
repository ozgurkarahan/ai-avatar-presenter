"""Generate a sample PPT with speaker notes for the podcast smoke test.

Run: python tests/fixtures/build_sample_podcast_pptx.py
Output: tests/fixtures/innovation-sample.pptx
"""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

OUT = Path(__file__).parent / "innovation-sample.pptx"

SLIDES = [
    {
        "title": "AI in Production: From Demo to Dependable",
        "bullets": [
            "Models are only one part of an AI product",
            "Context and tools decide answer quality",
            "Reliability is engineered, not assumed",
        ],
        "notes": (
            "Welcome to this introduction to AI in production. "
            "A convincing demo takes an afternoon, but a dependable AI product takes careful engineering, "
            "from the model you choose to the context you feed it and the tools it is allowed to call. "
            "In this short session we look at the building blocks that turn a prototype into a service people trust, "
            "combining quality, safety and cost control."
        ),
    },
    {
        "title": "Four Building Blocks of an AI Application",
        "bullets": [
            "Models: large, small and open-weight",
            "Context: instructions, documents and memory",
            "Tools: APIs and data exposed through MCP",
            "Speech: speech-to-text and text-to-speech",
        ],
        "notes": (
            "A modern AI application can be seen as four complementary building blocks. "
            "Models range from large language models to small and open-weight models that run closer to the data. "
            "Context engineering assembles instructions, retrieved documents and memory for each request. "
            "Tools let the model act, often exposed through the Model Context Protocol. "
            "And speech services turn the experience into a natural spoken conversation."
        ),
    },
    {
        "title": "Grounding with Retrieval",
        "bullets": [
            "Retrieval-augmented generation (RAG)",
            "Hybrid search and semantic reranking",
            "Every answer cites its sources",
        ],
        "notes": (
            "Grounding is the engine of answer quality. "
            "Retrieval-augmented generation searches your own documents, "
            "combining keyword and vector search with semantic reranking to find the best passages. "
            "The model then answers from those passages and cites them, "
            "which makes hallucinations easier to spot and answers easier to verify."
        ),
    },
    {
        "title": "Agents and the Harness Around Them",
        "bullets": [
            "Agents plan, call tools and observe results",
            "The harness adds memory, limits and logging",
            "Humans approve sensitive actions",
        ],
        "notes": (
            "Agents take AI from answering to acting. "
            "An agent plans a task, calls tools, observes the results and loops until the goal is reached. "
            "The harness around it provides memory, step limits, guardrails and detailed logging, "
            "while a human stays in the loop for sensitive actions, "
            "from sending an email to changing a record."
        ),
    },
    {
        "title": "Key Takeaways",
        "bullets": [
            "Pick the smallest model that does the job",
            "Measure quality on every release",
            "Design for responsible AI from day one",
        ],
        "notes": (
            "So what should you remember. "
            "Choosing the smallest model that does the job is one of the most powerful levers we have. "
            "Whether you are building a support assistant, a coding agent or a voice experience, "
            "measure quality on every release and design for responsible AI from day one. "
            "Thank you for listening."
        ),
    },
]


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    blank = prs.slide_layouts[6]  # fully blank layout

    for s in SLIDES:
        slide = prs.slides.add_slide(blank)

        title_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12), Inches(1.2))
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = s["title"]
        p.font.size = Pt(36)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0x0A, 0x2E, 0x5C)

        body_box = slide.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(11.8), Inches(5))
        bf = body_box.text_frame
        bf.word_wrap = True
        for i, b in enumerate(s["bullets"]):
            para = bf.paragraphs[0] if i == 0 else bf.add_paragraph()
            para.text = f"\u2022 {b}"
            para.font.size = Pt(22)
            para.font.color.rgb = RGBColor(0x1F, 0x2A, 0x3D)
            para.space_after = Pt(14)

        notes_tf = slide.notes_slide.notes_text_frame
        notes_tf.text = s["notes"]

    prs.core_properties.author = "Oz Radio"
    prs.core_properties.last_modified_by = "Oz Radio"
    prs.save(OUT)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, {len(SLIDES)} slides)")


if __name__ == "__main__":
    build()

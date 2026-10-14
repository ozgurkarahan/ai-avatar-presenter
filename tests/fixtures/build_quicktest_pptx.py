"""Build a *tiny* 2-slide PPT for fast UC3 podcast iteration (~30s total speech)."""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

OUT = Path(__file__).parent / "quicktest.pptx"

SLIDES = [
    {
        "title": "Low-Carbon Buildings in 30 Seconds",
        "bullets": ["Buildings drive ~37% of energy-related CO2", "Insulation and smart glazing cut demand"],
        "notes": "Buildings account for roughly a third of global energy-related emissions, so better insulation and smart glazing are among the fastest levers to cut them.",
    },
    {
        "title": "A 2030 Ambition",
        "bullets": ["Net zero by 2050", "-33% CO2 by 2030"],
        "notes": "A typical industrial roadmap commits to net-zero carbon emissions by 2050, with a 33 percent reduction in CO2 by 2030.",
    },
]


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    for s in SLIDES:
        slide = prs.slides.add_slide(blank)
        t = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12), Inches(1.2)).text_frame
        t.word_wrap = True
        p = t.paragraphs[0]
        p.text = s["title"]; p.font.size = Pt(36); p.font.bold = True
        p.font.color.rgb = RGBColor(0x0A, 0x2E, 0x5C)

        b = slide.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(11.8), Inches(5)).text_frame
        b.word_wrap = True
        for i, line in enumerate(s["bullets"]):
            par = b.paragraphs[0] if i == 0 else b.add_paragraph()
            par.text = f"\u2022 {line}"; par.font.size = Pt(22)
            par.font.color.rgb = RGBColor(0x1F, 0x2A, 0x3D); par.space_after = Pt(14)

        slide.notes_slide.notes_text_frame.text = s["notes"]

    prs.core_properties.author = "AI Avatar Presenter"
    prs.core_properties.last_modified_by = "AI Avatar Presenter"
    prs.save(OUT)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, {len(SLIDES)} slides)")


if __name__ == "__main__":
    build()

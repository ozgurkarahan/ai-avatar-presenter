"""Generate a sample PPT with speaker notes for UC3 podcast smoke test.

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
        "title": "Sustainable Construction: Shaping a Low-Carbon Future",
        "bullets": [
            "Buildings drive over a third of energy-related CO2",
            "Materials innovation is the biggest lever",
            "Sustainability at the core of every product",
        ],
        "notes": (
            "Welcome to this introduction to sustainable construction. "
            "Buildings account for more than a third of global energy-related emissions, "
            "from the materials used to build them to the energy used to heat and cool them. "
            "In this short session we look at how materials innovation can shape the habitat and industries of tomorrow, "
            "combining performance, well-being and care for the planet."
        ),
    },
    {
        "title": "Four Families of Building Solutions",
        "bullets": [
            "High-performance materials for industry",
            "Construction products (boards, insulation, mortars)",
            "Glazing for buildings and mobility",
            "Distribution networks for professionals",
        ],
        "notes": (
            "The building-materials sector can be seen as four complementary families of solutions. "
            "High-performance materials serve industries such as aerospace, healthcare and mobility. "
            "Construction products deliver boards, insulation and mortars for energy-efficient buildings. "
            "Glazing solutions provide innovative glass for both buildings and vehicles. "
            "And distribution networks bring these solutions to professionals through local branches."
        ),
    },
    {
        "title": "Innovation & R&D at Scale",
        "bullets": [
            "Cross-disciplinary research centers",
            "Thousands of researchers, hundreds of patents per year",
            "Partnerships with universities and start-ups",
        ],
        "notes": (
            "Innovation is the engine of growth in this sector. "
            "Leading manufacturers run cross-disciplinary research centers and collaborate with universities, "
            "employing thousands of researchers who file hundreds of patents every year. "
            "Open innovation programmes connect them with start-ups, "
            "accelerating breakthroughs in low-carbon materials and digital construction."
        ),
    },
    {
        "title": "A 2030 Ambition",
        "bullets": [
            "Net-zero carbon emissions by 2050",
            "-33% CO2 by 2030 vs a 2017 baseline",
            "Circular economy across all product lines",
        ],
        "notes": (
            "A credible climate plan sets the direction for the decade ahead. "
            "Many industrial players have committed to net-zero carbon emissions by 2050, "
            "with an intermediate target of around minus 33 percent CO2 by 2030 compared to a 2017 baseline. "
            "Circular economy principles are being embedded across every product family, "
            "from recycled glass to reusable boards."
        ),
    },
    {
        "title": "Key Takeaways",
        "bullets": [
            "Materials science is a climate lever",
            "Measure carbon on every project",
            "Design for reuse from day one",
        ],
        "notes": (
            "So what should you remember. "
            "Materials science is one of the most powerful climate levers we have. "
            "Whether you are building a hospital, a data center or an electric vehicle, "
            "measure the carbon impact of every project and design for reuse from day one. "
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

    prs.core_properties.author = "AI Avatar Presenter"
    prs.core_properties.last_modified_by = "AI Avatar Presenter"
    prs.save(OUT)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, {len(SLIDES)} slides)")


if __name__ == "__main__":
    build()

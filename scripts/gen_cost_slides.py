"""RFI559 Cost Estimation — simplified, numbers-first slides.

200 videos/year, batch-first training platform.
Azure pay-as-you-go pricing, April 2026, West Europe.
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
import os

W = Inches(13.333)
H = Inches(7.5)
DBLUE = RGBColor(0x00, 0x33, 0x66)
ABLUE = RGBColor(0x00, 0x78, 0xD4)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DK = RGBColor(0x33, 0x33, 0x33)
MD = RGBColor(0x66, 0x66, 0x66)
GRN = RGBColor(0x10, 0x7C, 0x10)
ORG = RGBColor(0xCA, 0x50, 0x10)
BG = RGBColor(0xF5, 0xF7, 0xFA)

prs = Presentation()
prs.slide_width = W
prs.slide_height = H


def bg(sl, c=BG):
    sl.background.fill.solid()
    sl.background.fill.fore_color.rgb = c


def box(sl, l, t, w, h, fc, txt="", fs=12, tc=WHITE, b=False,
        al=PP_ALIGN.CENTER, sh=MSO_SHAPE.ROUNDED_RECTANGLE):
    s = sl.shapes.add_shape(sh, l, t, w, h)
    s.fill.solid(); s.fill.fore_color.rgb = fc; s.line.fill.background()
    if txt:
        tf = s.text_frame; tf.word_wrap = True
        tf.paragraphs[0].alignment = al
        r = tf.paragraphs[0].add_run()
        r.text = txt; r.font.size = Pt(fs); r.font.color.rgb = tc; r.font.bold = b
    return s


def txt(sl, l, t, w, h, text, fs=14, c=DK, b=False, al=PP_ALIGN.LEFT):
    tb = sl.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.alignment = al
    r = p.add_run(); r.text = text; r.font.size = Pt(fs); r.font.color.rgb = c; r.font.bold = b
    return tb


def mtxt(sl, l, t, w, h, lines):
    tb = sl.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    for i, c in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run(); r.text = c.get("t", "")
        r.font.size = Pt(c.get("s", 12)); r.font.color.rgb = c.get("c", DK)
        r.font.bold = c.get("b", False); p.alignment = c.get("a", PP_ALIGN.LEFT)
        p.space_after = Pt(c.get("sa", 4))
    return tb


def tbl(sl, l, t, w, h, data, cw=None, hc=ABLUE):
    rows, cols = len(data), len(data[0])
    ts = sl.shapes.add_table(rows, cols, l, t, w, h)
    table = ts.table
    if cw:
        for i, c in enumerate(cw): table.columns[i].width = c
    for r in range(rows):
        for c in range(cols):
            cell = table.cell(r, c)
            cell.text = str(data[r][c])
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(11)
                if r == 0:
                    p.font.bold = True; p.font.color.rgb = WHITE; p.alignment = PP_ALIGN.CENTER
                else:
                    p.font.color.rgb = DK
                    p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT
            if r == 0:
                cell.fill.solid(); cell.fill.fore_color.rgb = hc
            elif r % 2 == 0:
                cell.fill.solid(); cell.fill.fore_color.rgb = RGBColor(0xF0, 0xF4, 0xF8)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    return ts


# ═══════════════════════════════════════════════════════════════
# SLIDE 1 — TITLE
# ═══════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
bg(sl, DBLUE)
box(sl, Inches(0), Inches(0), W, Inches(1), ABLUE, sh=MSO_SHAPE.RECTANGLE)
txt(sl, Inches(0.5), Inches(0.15), Inches(12), Inches(0.7),
    "MICROSOFT  \u00d7  SAINT-GOBAIN", 18, WHITE, True)
txt(sl, Inches(1.5), Inches(2.0), Inches(10), Inches(1.2),
    "RFI559 \u2014 AI Avatar Solution", 40, WHITE, True)
txt(sl, Inches(1.5), Inches(3.2), Inches(10), Inches(0.8),
    "Azure Cost Estimation", 28, RGBColor(0x80, 0xC0, 0xFF))
mtxt(sl, Inches(1.5), Inches(4.5), Inches(10), Inches(2), [
    {"t": "200 training videos/year  \u2022  Up to 5,000 learners", "s": 16,
     "c": RGBColor(0xCC, 0xDD, 0xEE)},
    {"t": "", "s": 8, "sa": 12},
    {"t": "Pay-as-you-go pricing  \u2022  West Europe  \u2022  April 2026",
     "s": 13, "c": RGBColor(0x88, 0xAA, 0xCC)},
])
print("Slide 1: Title")

# ═══════════════════════════════════════════════════════════════
# SLIDE 2 — AZURE UNIT PRICES
# ═══════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
bg(sl)
box(sl, Inches(0), Inches(0), W, Inches(0.9), DBLUE, sh=MSO_SHAPE.RECTANGLE)
txt(sl, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
    "Azure Service Pricing (Pay-As-You-Go)", 24, WHITE, True)

tbl(sl, Inches(0.3), Inches(1.1), Inches(12.7), Inches(5.0), [
    ["Azure Service", "Unit", "Price", "Role in Solution"],
    ["Batch Avatar Synthesis", "per minute of video", "$0.50", "Render training videos (one-time per content)"],
    ["VoiceLive Avatar (real-time)", "per minute of streaming", "$0.50", "Live interactive Q&A sessions"],
    ["Custom Avatar Hosting", "per model per hour", "$0.60", "Custom executive avatar (Phase 3)"],
    ["Azure OpenAI \u2014 GPT-4.1 (input)", "per 1K tokens", "$0.002", "Translation, Q&A, agent chat"],
    ["Azure OpenAI \u2014 GPT-4.1 (output)", "per 1K tokens", "$0.008", "Generated responses"],
    ["text-embedding-3-small", "per 1M tokens", "$0.02", "RAG slide search (negligible)"],
    ["Azure AI Translator", "per 1M characters", "$10.00", "37-language translation"],
    ["Cosmos DB Serverless", "per 1M RUs / per GB", "$0.25 / $0.25", "Metadata & translation cache"],
    ["Blob Storage (Std LRS Hot)", "per GB/month", "$0.018", "Videos, slides, PPTX files"],
    ["Container Apps (Consumption)", "per vCPU-second", "$0.000024", "Application hosting"],
    ["Container Registry (Basic)", "per month", "$5.00", "Docker image storage"],
    ["Log Analytics", "first 5 GB/month", "Free", "Container logs & monitoring"],
], cw=[Inches(2.8), Inches(2.2), Inches(1.5), Inches(6.2)])

txt(sl, Inches(0.3), Inches(6.3), Inches(12), Inches(0.4),
    "Key: a 10-min training video costs $5 to render. Once stored, unlimited viewers watch at ~$0.",
    12, ABLUE, True)
print("Slide 2: Unit Prices")

# ═══════════════════════════════════════════════════════════════
# SLIDE 3 — MONTHLY COST BY PHASE (THE MAIN SLIDE)
# ═══════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
bg(sl)
box(sl, Inches(0), Inches(0), W, Inches(0.9), DBLUE, sh=MSO_SHAPE.RECTANGLE)
txt(sl, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
    "Monthly Azure Cost by Phase", 24, WHITE, True)

tbl(sl, Inches(0.3), Inches(1.1), Inches(12.7), Inches(5.0), [
    ["Azure Service", "Phase 1: PoC", "", "Phase 2: Production", "", "Phase 3: Enterprise", ""],
    ["", "Usage", "Cost", "Usage", "Cost", "Usage", "Cost"],
    ["Batch Avatar Synthesis", "50 min (5 videos)", "$25", "120 min (12 videos)", "$60", "170 min (17 videos)", "$85"],
    ["VoiceLive Avatar (Q&A)", "50 min", "$25", "200 min", "$100", "500 min", "$250"],
    ["UC3 Podcast (dual avatar)", "\u2014", "\u2014", "\u2014", "\u2014", "100 min (5 eps)", "$100"],
    ["Custom Avatar Hosting", "\u2014", "\u2014", "\u2014", "\u2014", "1 model 24/7", "$432"],
    ["Azure OpenAI GPT-4.1", "~300K tok", "$2", "~2M tok", "$10", "~10M tok", "$50"],
    ["Azure AI Translator", "\u2014", "\u2014", "~5M chars", "$50", "~20M chars", "$200"],
    ["Container Apps", "1 vCPU, 2GB", "$35", "2 vCPU, 4GB", "$155", "2 vCPU x3 regions", "$470"],
    ["AI Search", "\u2014", "\u2014", "Basic", "$73", "Standard S1", "$245"],
    ["Cosmos DB + Blob + ACR + Logs", "minimal", "$6", "minimal", "$7", "moderate", "$31"],
    ["", "", "", "", "", "", ""],
    ["MONTHLY TOTAL", "", "$93", "", "$455", "", "$1,863"],
    ["ANNUAL TOTAL", "", "$1,116", "", "$5,460", "", "$22,356"],
], cw=[Inches(2.5), Inches(1.3), Inches(0.8), Inches(1.3), Inches(0.8),
       Inches(1.5), Inches(0.8)], hc=DBLUE)

box(sl, Inches(0.3), Inches(6.3), Inches(4.0), Inches(0.9), GRN,
    "Phase 1:  $93/month\n50 learners  \u2022  5 videos/mo", 13, WHITE, True)
box(sl, Inches(4.5), Inches(6.3), Inches(4.0), Inches(0.9), ABLUE,
    "Phase 2:  $455/month\n500 learners  \u2022  12 videos/mo", 13, WHITE, True)
box(sl, Inches(8.7), Inches(6.3), Inches(4.3), Inches(0.9), ORG,
    "Phase 3:  $1,863/month\n5,000 learners  \u2022  17 videos/mo", 13, WHITE, True)
print("Slide 3: Monthly Cost")

# ═══════════════════════════════════════════════════════════════
# SLIDE 4 — COST PER VIDEO & PER LEARNER
# ═══════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
bg(sl)
box(sl, Inches(0), Inches(0), W, Inches(0.9), DBLUE, sh=MSO_SHAPE.RECTANGLE)
txt(sl, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
    "Unit Economics", 24, WHITE, True)

box(sl, Inches(0.3), Inches(1.2), Inches(6.2), Inches(0.5), ABLUE,
    "Cost to Produce One 10-min Training Video", 14, WHITE, True)

tbl(sl, Inches(0.3), Inches(1.8), Inches(6.2), Inches(2.5), [
    ["Component", "Calculation", "Cost"],
    ["Avatar rendering", "10 min \u00d7 $0.50/min", "$5.00"],
    ["GPT-4.1 (script/translation)", "~5K tokens", "$0.03"],
    ["Embeddings (Q&A index)", "~5K tokens", "< $0.01"],
    ["Cosmos DB + Blob storage", "writes + 200 MB", "< $0.01"],
    ["", "", ""],
    ["Total per video", "", "$5.03"],
], cw=[Inches(2.5), Inches(2.0), Inches(1.7)])

mtxt(sl, Inches(0.5), Inches(4.5), Inches(5.8), Inches(1.5), [
    {"t": "Same video in 37 languages:", "s": 13, "b": True, "c": DBLUE},
    {"t": "37 \u00d7 $5 = $185  (one-time render cost)", "s": 14, "b": True, "c": GRN},
    {"t": "", "s": 6, "sa": 4},
    {"t": "Traditional video dubbing: $2,000\u2013$5,000 per language", "s": 11, "c": MD},
])

box(sl, Inches(6.8), Inches(1.2), Inches(6.2), Inches(0.5), ABLUE,
    "Cost per Learner per Month", 14, WHITE, True)

tbl(sl, Inches(6.8), Inches(1.8), Inches(6.2), Inches(2.5), [
    ["Metric", "Phase 1", "Phase 2", "Phase 3"],
    ["Learners", "50", "500", "5,000"],
    ["Monthly Azure cost", "$93", "$455", "$1,863"],
    ["Per learner / month", "$1.86", "$0.91", "$0.37"],
    ["Per learner / year", "$22.32", "$10.92", "$4.47"],
    ["", "", "", ""],
    ["Videos produced / year", "~60", "~140", "200"],
], cw=[Inches(1.8), Inches(1.3), Inches(1.3), Inches(1.3)])

box(sl, Inches(6.8), Inches(4.5), Inches(6.2), Inches(1.2), RGBColor(0xE3, 0xF2, 0xFD),
    sh=MSO_SHAPE.ROUNDED_RECTANGLE)
mtxt(sl, Inches(7.0), Inches(4.6), Inches(5.8), Inches(1.0), [
    {"t": "Viewers are free", "s": 16, "b": True, "c": DBLUE},
    {"t": "Once a video is rendered, 10 or 10,000 learners watch it at no additional Azure cost.",
     "s": 11, "c": DK},
])

box(sl, Inches(0.3), Inches(6.3), Inches(12.7), Inches(0.8), DBLUE,
    "AI Avatar video: $5  |  Traditional production: $5,000\u2013$15,000  |  1,000x cost reduction",
    14, WHITE, True)
print("Slide 4: Unit Economics")

# ═══════════════════════════════════════════════════════════════
# SLIDE 5 — ANNUAL SUMMARY + ASSUMPTIONS
# ═══════════════════════════════════════════════════════════════
sl = prs.slides.add_slide(prs.slide_layouts[6])
bg(sl)
box(sl, Inches(0), Inches(0), W, Inches(0.9), DBLUE, sh=MSO_SHAPE.RECTANGLE)
txt(sl, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
    "Annual Azure Cost Summary", 24, WHITE, True)

tbl(sl, Inches(0.3), Inches(1.2), Inches(7.5), Inches(4.5), [
    ["", "Phase 1: PoC", "Phase 2: Prod", "Phase 3: Enterprise"],
    ["Scope", "UC1 Silver + UC2", "UC1 All + UC2", "UC1 + UC2 + UC3"],
    ["Learners", "50", "500", "5,000"],
    ["Videos / year", "~60", "~140", "200"],
    ["Languages", "10", "37", "37"],
    ["Avatars", "Standard", "Standard", "Standard + Custom"],
    ["Regions", "1", "1", "3"],
    ["", "", "", ""],
    ["Monthly Azure cost", "$93", "$455", "$1,863"],
    ["Annual Azure cost", "$1,116", "$5,460", "$22,356"],
    ["Per learner / year", "$22", "$11", "$4.50"],
], cw=[Inches(1.8), Inches(1.7), Inches(1.7), Inches(2.3)], hc=DBLUE)

box(sl, Inches(8.2), Inches(1.2), Inches(4.8), Inches(0.5), MD,
    "Assumptions", 13, WHITE, True)
mtxt(sl, Inches(8.4), Inches(1.8), Inches(4.4), Inches(4.5), [
    {"t": "Content", "s": 12, "b": True, "c": DBLUE},
    {"t": "\u2022 200 new training videos per year total", "s": 10, "c": DK},
    {"t": "\u2022 ~10 min average per video", "s": 10, "c": DK},
    {"t": "\u2022 ~10 slides per presentation", "s": 10, "c": DK},
    {"t": "", "s": 6, "sa": 4},
    {"t": "Usage", "s": 12, "b": True, "c": DBLUE},
    {"t": "\u2022 Learners watch pre-rendered batch videos", "s": 10, "c": DK},
    {"t": "\u2022 ~10-20% use live Q&A (5 min avg)", "s": 10, "c": DK},
    {"t": "\u2022 Videos replayable unlimited times", "s": 10, "c": DK},
    {"t": "", "s": 6, "sa": 4},
    {"t": "Pricing", "s": 12, "b": True, "c": DBLUE},
    {"t": "\u2022 Azure pay-as-you-go (no commitments)", "s": 10, "c": DK},
    {"t": "\u2022 West Europe region", "s": 10, "c": DK},
    {"t": "\u2022 April 2026 published rates", "s": 10, "c": DK},
    {"t": "", "s": 6, "sa": 4},
    {"t": "Not included", "s": 12, "b": True, "c": ORG},
    {"t": "\u2022 Implementation / development costs", "s": 10, "c": DK},
    {"t": "\u2022 Network egress (<1%)", "s": 10, "c": DK},
    {"t": "\u2022 Entra ID / M365 licensing", "s": 10, "c": DK},
])

print("Slide 5: Annual Summary")

# ─── SAVE ─────────────────────────────────────────────────────
out_path = os.path.join("docs", "RFI559-Cost-Estimation.pptx")
prs.save(out_path)
print(f"\nSaved: {out_path}")
print(f"Total slides: {len(prs.slides)}")


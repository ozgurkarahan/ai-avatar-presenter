"""Generate RFI Cost Estimation PowerPoint slides."""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
import os

# ─── Constants ───────────────────────────────────────────────────────
WIDTH = Inches(13.333)
HEIGHT = Inches(7.5)
DARK_BLUE = RGBColor(0x00, 0x33, 0x66)
AZURE_BLUE = RGBColor(0x00, 0x78, 0xD4)
LIGHT_BLUE = RGBColor(0xDE, 0xEC, 0xF9)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK_GRAY = RGBColor(0x33, 0x33, 0x33)
MED_GRAY = RGBColor(0x66, 0x66, 0x66)
GREEN = RGBColor(0x10, 0x7C, 0x10)
ORANGE = RGBColor(0xCA, 0x50, 0x10)
RED = RGBColor(0xC5, 0x00, 0x00)
ACCENT_TEAL = RGBColor(0x00, 0x80, 0x80)
BG_LIGHT = RGBColor(0xF5, 0xF7, 0xFA)

prs = Presentation()
prs.slide_width = WIDTH
prs.slide_height = HEIGHT


def add_bg(slide, color=BG_LIGHT):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_shape(slide, left, top, w, h, fill_color, text="", font_size=12,
              font_color=WHITE, bold=False, align=PP_ALIGN.CENTER,
              shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    s = slide.shapes.add_shape(shape, left, top, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = fill_color
    s.line.fill.background()
    if text:
        tf = s.text_frame
        tf.word_wrap = True
        tf.paragraphs[0].alignment = align
        run = tf.paragraphs[0].add_run()
        run.text = text
        run.font.size = Pt(font_size)
        run.font.color.rgb = font_color
        run.font.bold = bold
    return s


def add_text(slide, left, top, w, h, text, font_size=14, color=DARK_GRAY,
             bold=False, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(left, top, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.color.rgb = color
    run.font.bold = bold
    return tb


def add_multi_text(slide, left, top, w, h, lines, default_size=12,
                   default_color=DARK_GRAY):
    tb = slide.shapes.add_textbox(left, top, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, cfg in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        run = p.add_run()
        run.text = cfg.get("text", "")
        run.font.size = Pt(cfg.get("size", default_size))
        run.font.color.rgb = cfg.get("color", default_color)
        run.font.bold = cfg.get("bold", False)
        p.alignment = cfg.get("align", PP_ALIGN.LEFT)
        p.space_after = Pt(cfg.get("space_after", 4))
    return tb


def add_table(slide, left, top, w, h, rows, cols, data,
              col_widths=None, header_color=AZURE_BLUE):
    tbl_shape = slide.shapes.add_table(rows, cols, left, top, w, h)
    table = tbl_shape.table
    if col_widths:
        for i, cw in enumerate(col_widths):
            table.columns[i].width = cw
    for r in range(rows):
        for c in range(cols):
            cell = table.cell(r, c)
            cell.text = str(data[r][c]) if r < len(data) and c < len(data[r]) else ""
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.size = Pt(10)
                if r == 0:
                    paragraph.font.bold = True
                    paragraph.font.color.rgb = WHITE
                    paragraph.alignment = PP_ALIGN.CENTER
                else:
                    paragraph.font.color.rgb = DARK_GRAY
                    paragraph.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT
            if r == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = header_color
            elif r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(0xF0, 0xF4, 0xF8)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    return tbl_shape


# ═══════════════════════════════════════════════════════════════════
# SLIDE 1 — TITLE
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK_BLUE)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(1.0), AZURE_BLUE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.7),
         "MICROSOFT  \u00d7  ACME", 18, WHITE, True)
add_text(slide, Inches(1.5), Inches(2.0), Inches(10), Inches(1.2),
         "RFI \u2014 AI Avatar Solution", 40, WHITE, True)
add_text(slide, Inches(1.5), Inches(3.2), Inches(10), Inches(0.8),
         "Progressive Cost Estimation", 28, RGBColor(0x80, 0xC0, 0xFF))
add_multi_text(slide, Inches(1.5), Inches(4.5), Inches(10), Inches(2.0), [
    {"text": "From Proof of Concept to Enterprise Scale", "size": 16,
     "color": RGBColor(0xCC, 0xDD, 0xEE)},
    {"text": "", "size": 8, "space_after": 12},
    {"text": "Azure AI Services  \u2022  Azure OpenAI  \u2022  VoiceLive Avatar  \u2022  Container Apps",
     "size": 13, "color": RGBColor(0x88, 0xAA, 0xCC)},
    {"text": "", "size": 8, "space_after": 12},
    {"text": "April 2026 \u2014 Pricing estimates based on current Azure published rates",
     "size": 11, "color": RGBColor(0x88, 0x99, 0xAA)},
    {"text": "All prices in USD, West Europe region, subject to enterprise agreement discounts",
     "size": 11, "color": RGBColor(0x88, 0x99, 0xAA)},
])
print("Slide 1: Title")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 2 — PROGRESSIVE APPROACH
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), DARK_BLUE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Progressive Deployment Approach", 24, WHITE, True)

phases = [
    ("Phase 1: PoC / Pilot", "3\u20136 months", [
        "UC1 Silver \u2014 Avatar over PPT",
        "UC2 \u2014 Batch video generation",
        "10 languages (DragonHD voices)",
        "50 pilot users",
        "Standard Microsoft avatars",
        "Single Azure region",
    ], GREEN),
    ("Phase 2: Production", "6\u201312 months", [
        "UC1 Basic + Silver + Gold",
        "UC2 + SCORM/LMS output",
        "37 languages (full RFI scope)",
        "500 users \u2014 SGChat integration",
        "M365 Copilot connector",
        "Multi-region HA (2 regions)",
    ], AZURE_BLUE),
    ("Phase 3: Enterprise", "12+ months", [
        "UC1 + UC2 + UC3 Podcast",
        "Custom avatar (executive)",
        "Full LMS/SCORM ecosystem",
        "5,000+ users \u2014 global rollout",
        "Custom voices & branding",
        "Multi-region (3+ regions)",
    ], ORANGE),
]

for i, (title, timeline, items, color) in enumerate(phases):
    x = Inches(0.5 + i * 4.2)
    add_shape(slide, x, Inches(1.3), Inches(3.8), Inches(0.7), color,
              title, 16, WHITE, True)
    add_text(slide, x, Inches(2.05), Inches(3.8), Inches(0.35),
             timeline, 12, MED_GRAY)
    for j, item in enumerate(items):
        add_multi_text(slide, x + Inches(0.2), Inches(2.5 + j * 0.38),
                       Inches(3.5), Inches(0.35), [
            {"text": f"\u2192  {item}", "size": 11, "color": DARK_GRAY}
        ])

for i in range(2):
    x = Inches(4.35 + i * 4.2)
    add_text(slide, x, Inches(1.4), Inches(0.5), Inches(0.5),
             "\u25b6", 28, MED_GRAY)

add_multi_text(slide, Inches(0.5), Inches(5.2), Inches(12), Inches(2.0), [
    {"text": "Cost Driver Insight", "size": 14, "bold": True, "color": DARK_BLUE},
    {"text": "The dominant cost component across all phases is VoiceLive Avatar streaming (~80-90% of variable costs).",
     "size": 12, "color": DARK_GRAY},
    {"text": "Infrastructure (Container Apps, Cosmos DB, Blob Storage) remains minimal due to serverless/consumption pricing.",
     "size": 12, "color": MED_GRAY},
    {"text": "OpenAI costs (GPT-4.1 + embeddings) are highly competitive and scale linearly with session count.",
     "size": 12, "color": MED_GRAY},
])
print("Slide 2: Progressive Approach")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 3 — AZURE SERVICE UNIT PRICING
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), DARK_BLUE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Azure Service Unit Pricing Reference", 24, WHITE, True)

pricing_data = [
    ["Azure Service", "SKU / Tier", "Unit", "Unit Price", "Notes"],
    ["VoiceLive Avatar (real-time)", "Standard", "per minute", "$0.50",
     "Dominant cost \u2014 real-time WebRTC avatar"],
    ["Batch Avatar Synthesis", "Standard", "per minute", "$0.50",
     "Async video generation from text"],
    ["Custom Avatar Hosting", "Custom", "per model/hour", "$0.60",
     "Phase 3 only \u2014 custom executive avatar"],
    ["Azure OpenAI \u2014 GPT-4.1", "S0", "per 1K input tokens", "$0.002",
     "Translation, Q&A, Agent chat"],
    ["Azure OpenAI \u2014 GPT-4.1", "S0", "per 1K output tokens", "$0.008",
     "Responses, generated text"],
    ["OpenAI \u2014 text-embedding-3-small", "S0", "per 1M input tokens", "$0.02",
     "RAG embeddings (negligible cost)"],
    ["Azure AI Translator", "S1", "per 1M characters", "$10.00",
     "Phase 2+ for 37-language expansion"],
    ["Azure Cosmos DB (Serverless)", "Serverless", "per 1M RUs", "$0.25",
     "Metadata, translations cache"],
    ["Azure Cosmos DB (Serverless)", "Serverless", "per GB/month", "$0.25",
     "Storage for slide data"],
    ["Azure Blob Storage", "Standard LRS Hot", "per GB/month", "$0.018",
     "Slide images, PPTX, videos"],
    ["Azure Container Apps", "Consumption", "per vCPU-second", "$0.000024",
     "Free tier: 180K vCPU-sec/mo"],
    ["Azure Container Apps", "Consumption", "per GiB-second", "$0.000003",
     "Free tier: 360K GiB-sec/mo"],
    ["Azure Container Registry", "Basic", "per month", "$5.00",
     "10 GB included storage"],
    ["Log Analytics", "\u2014", "per GB ingested", "Free 5GB",
     "First 5 GB/month free"],
]

add_table(slide, Inches(0.3), Inches(1.1), Inches(12.7), Inches(5.8),
          len(pricing_data), 5, pricing_data,
          col_widths=[Inches(3.0), Inches(1.5), Inches(2.0), Inches(1.7), Inches(4.5)])

add_text(slide, Inches(0.3), Inches(7.0), Inches(12), Inches(0.4),
         "* All prices USD, West Europe region, April 2026. Subject to change. "
         "Enterprise agreements may include volume discounts.",
         9, MED_GRAY)
print("Slide 3: Unit Pricing")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 4 — PHASE 1 COST BREAKDOWN
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), GREEN,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Phase 1: PoC / Pilot \u2014 Monthly Cost Estimate", 24, WHITE, True)

add_shape(slide, Inches(0.3), Inches(1.1), Inches(4.8), Inches(2.5),
          RGBColor(0xE8, 0xF5, 0xE9), shape=MSO_SHAPE.ROUNDED_RECTANGLE)
add_multi_text(slide, Inches(0.5), Inches(1.2), Inches(4.4), Inches(2.3), [
    {"text": "Assumptions", "size": 14, "bold": True, "color": GREEN},
    {"text": "\u2022 50 pilot users (internal Acme)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 ~200 sessions/month (4 per user)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 ~10 min avg avatar time per session", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 10 batch videos/month (10 min avg)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 10 languages (DragonHD voices)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 Standard Microsoft avatars", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 Single region (West Europe)", "size": 11, "color": DARK_GRAY},
])

phase1_data = [
    ["Service", "Usage/Month", "Unit Cost", "Monthly Cost", "% of Total"],
    ["VoiceLive Avatar (real-time)", "2,000 min", "$0.50/min", "$1,000", "79.2%"],
    ["Batch Avatar Synthesis", "100 min", "$0.50/min", "$50", "4.0%"],
    ["Azure OpenAI GPT-4.1", "~2M tokens", "$0.002-0.008/1K", "$12", "0.9%"],
    ["OpenAI Embeddings", "~1.5M tokens", "$0.02/1M", "$0.03", "<0.1%"],
    ["Container Apps (1vCPU, 2GB)", "24/7 after free tier", "$0.000024/s", "$35", "2.8%"],
    ["Cosmos DB Serverless", "~2M RUs + 1 GB", "$0.25/1M RU", "$1", "<0.1%"],
    ["Blob Storage (Hot LRS)", "~2 GB", "$0.018/GB", "$0.04", "<0.1%"],
    ["Container Registry (Basic)", "1 registry", "$5/month", "$5", "0.4%"],
    ["Log Analytics", "~1 GB logs", "Free 5GB", "$0", "0%"],
    ["", "", "", "", ""],
    ["TOTAL", "", "", "$1,103", "100%"],
]

add_table(slide, Inches(5.3), Inches(1.1), Inches(7.7), Inches(4.8),
          len(phase1_data), 5, phase1_data,
          col_widths=[Inches(2.4), Inches(1.3), Inches(1.5), Inches(1.2), Inches(1.3)])

add_multi_text(slide, Inches(0.5), Inches(4.0), Inches(4.4), Inches(3.0), [
    {"text": "Key Insight", "size": 14, "bold": True, "color": GREEN},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "VoiceLive Avatar streaming represents 83% of total monthly cost.",
     "size": 12, "bold": True, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Infrastructure costs are near-zero thanks to serverless/consumption pricing.",
     "size": 11, "color": MED_GRAY},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Per-user cost: ~$22/user/month", "size": 13, "bold": True, "color": GREEN},
    {"text": "Per-session cost: ~$5.50/session", "size": 13, "bold": True, "color": GREEN},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Annual estimate: ~$13,200", "size": 14, "bold": True, "color": DARK_BLUE},
])
print("Slide 4: Phase 1")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 5 — PHASE 2 COST BREAKDOWN
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), AZURE_BLUE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Phase 2: Production \u2014 Monthly Cost Estimate", 24, WHITE, True)

add_shape(slide, Inches(0.3), Inches(1.1), Inches(4.8), Inches(2.7), LIGHT_BLUE,
          shape=MSO_SHAPE.ROUNDED_RECTANGLE)
add_multi_text(slide, Inches(0.5), Inches(1.2), Inches(4.4), Inches(2.5), [
    {"text": "Assumptions", "size": 14, "bold": True, "color": AZURE_BLUE},
    {"text": "\u2022 500 users (Acme departments)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 ~2,000 sessions/month (4 per user)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 ~10 min avg avatar time per session", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 100 batch videos/month (10 min avg)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 37 languages (full RFI scope)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 UC1 Gold: multi-deck AI selection", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 SGChat + M365 integration", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 2-region deployment (HA)", "size": 11, "color": DARK_GRAY},
])

phase2_data = [
    ["Service", "Usage/Month", "Unit Cost", "Monthly Cost", "% of Total"],
    ["VoiceLive Avatar (real-time)", "20,000 min", "$0.50/min", "$10,000", "81.5%"],
    ["Batch Avatar Synthesis", "1,000 min", "$0.50/min", "$500", "4.1%"],
    ["Azure OpenAI GPT-4.1", "~20M tokens", "$0.002-0.008/1K", "$100", "0.8%"],
    ["OpenAI Embeddings", "~15M tokens", "$0.02/1M", "$0.30", "<0.1%"],
    ["Azure AI Translator", "~50M chars", "$10/1M", "$500", "4.1%"],
    ["Container Apps (2vCPU, 4GB x2)", "24/7, 2 replicas", "$0.000024/s", "$310", "2.5%"],
    ["Cosmos DB Serverless", "~20M RUs + 10 GB", "$0.25/1M RU", "$8", "<0.1%"],
    ["Blob Storage (Hot LRS)", "~50 GB", "$0.018/GB", "$1", "<0.1%"],
    ["Container Registry (Basic)", "1 registry", "$5/month", "$5", "<0.1%"],
    ["Log Analytics", "~5 GB logs", "Free 5GB", "$0", "0%"],
    ["AI Search (Basic) \u2014 UC1 Gold", "1 unit", "$73/month", "$73", "0.6%"],
    ["", "", "", "", ""],
    ["TOTAL", "", "", "$11,497", "100%"],
]

add_table(slide, Inches(5.3), Inches(1.1), Inches(7.7), Inches(5.3),
          len(phase2_data), 5, phase2_data,
          col_widths=[Inches(2.4), Inches(1.3), Inches(1.5), Inches(1.2), Inches(1.3)])

add_multi_text(slide, Inches(0.5), Inches(4.2), Inches(4.4), Inches(3.0), [
    {"text": "Key Insight", "size": 14, "bold": True, "color": AZURE_BLUE},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Cost scales linearly with user count. 10x users = ~10x avatar cost.",
     "size": 12, "bold": True, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Azure AI Translator adds $500/mo for 37-language expansion.",
     "size": 11, "color": MED_GRAY},
    {"text": "AI Search added for UC1 Gold multi-deck retrieval.",
     "size": 11, "color": MED_GRAY},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Per-user cost: ~$23/user/month", "size": 13, "bold": True, "color": AZURE_BLUE},
    {"text": "Per-session cost: ~$5.75/session", "size": 13, "bold": True, "color": AZURE_BLUE},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Annual estimate: ~$138,000", "size": 14, "bold": True, "color": DARK_BLUE},
])
print("Slide 5: Phase 2")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 6 — PHASE 3 COST BREAKDOWN
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), ORANGE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Phase 3: Enterprise Scale \u2014 Monthly Cost Estimate", 24, WHITE, True)

add_shape(slide, Inches(0.3), Inches(1.1), Inches(4.8), Inches(2.7),
          RGBColor(0xFD, 0xF0, 0xE0), shape=MSO_SHAPE.ROUNDED_RECTANGLE)
add_multi_text(slide, Inches(0.5), Inches(1.2), Inches(4.4), Inches(2.5), [
    {"text": "Assumptions", "size": 14, "bold": True, "color": ORANGE},
    {"text": "\u2022 5,000 users (global Acme)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 ~15,000 sessions/month (3 per user)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 ~8 min avg avatar time per session", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 500 batch videos/month (10 min avg)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 UC3: 50 podcasts/month (20 min each)", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 37 languages, custom avatar model", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 Full LMS/SCORM integration", "size": 11, "color": DARK_GRAY},
    {"text": "\u2022 Multi-region (3 regions, active-active)", "size": 11, "color": DARK_GRAY},
])

phase3_data = [
    ["Service", "Usage/Month", "Unit Cost", "Monthly Cost", "% of Total"],
    ["VoiceLive Avatar (real-time)", "120,000 min", "$0.50/min", "$60,000", "79.3%"],
    ["Batch Avatar Synthesis", "5,000 min", "$0.50/min", "$2,500", "3.3%"],
    ["UC3 Podcast (dual avatar)", "1,000 min", "$0.50/min x2", "$1,000", "1.3%"],
    ["Custom Avatar Hosting", "1 model, 24/7", "$0.60/hr", "$432", "0.6%"],
    ["Azure OpenAI GPT-4.1", "~150M tokens", "$0.002-0.008/1K", "$750", "1.0%"],
    ["OpenAI Embeddings", "~100M tokens", "$0.02/1M", "$2", "<0.1%"],
    ["Azure AI Translator", "~300M chars", "$8.22/1M*", "$2,466", "3.3%"],
    ["Container Apps (4vCPU, 8GB x3)", "24/7, 3 replicas x3", "$0.000024/s", "$2,800", "3.7%"],
    ["Cosmos DB Serverless", "~200M RUs + 100GB", "$0.25/1M RU", "$75", "0.1%"],
    ["Blob Storage (Hot LRS)", "~500 GB + videos", "$0.018/GB", "$9", "<0.1%"],
    ["AI Search (Standard S1)", "1 unit x 3 regions", "$245/unit", "$735", "1.0%"],
    ["Container Registry (Std)", "1 registry", "$20/month", "$20", "<0.1%"],
    ["Log Analytics", "~20 GB logs", "$2.76/GB*", "$42", "<0.1%"],
    ["Front Door (CDN + WAF)", "Global routing", "~$35/month", "$35", "<0.1%"],
    ["Key Vault", "RBAC + secrets", "$0.03/10K ops", "$1", "<0.1%"],
    ["", "", "", "", ""],
    ["TOTAL", "", "", "$70,867", "100%"],
]

add_table(slide, Inches(5.3), Inches(1.1), Inches(7.7), Inches(6.0),
          len(phase3_data), 5, phase3_data,
          col_widths=[Inches(2.4), Inches(1.3), Inches(1.5), Inches(1.2), Inches(1.3)])

add_multi_text(slide, Inches(0.5), Inches(4.2), Inches(4.4), Inches(2.8), [
    {"text": "Key Insight", "size": 14, "bold": True, "color": ORANGE},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Per-user cost drops to ~$14/user/month at scale thanks to amortized infra.",
     "size": 12, "bold": True, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Translator volume discount kicks in (250M+ chars).",
     "size": 11, "color": MED_GRAY},
    {"text": "Multi-region adds ~30% to compute costs but provides HA/DR.",
     "size": 11, "color": MED_GRAY},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Per-user cost: ~$14/user/month", "size": 13, "bold": True, "color": ORANGE},
    {"text": "Per-session cost: ~$4.70/session", "size": 13, "bold": True, "color": ORANGE},
    {"text": "", "size": 6, "space_after": 2},
    {"text": "Annual estimate: ~$850,000", "size": 14, "bold": True, "color": DARK_BLUE},
])
print("Slide 6: Phase 3")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 7 — PHASE COMPARISON SUMMARY
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), DARK_BLUE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Progressive Cost Summary \u2014 Phase Comparison", 24, WHITE, True)

summary_data = [
    ["", "Phase 1: PoC", "Phase 2: Production", "Phase 3: Enterprise"],
    ["Users", "50", "500", "5,000"],
    ["Sessions/Month", "200", "2,000", "15,000"],
    ["Use Cases", "UC1 Silver + UC2", "UC1 All + UC2", "UC1 + UC2 + UC3"],
    ["Languages", "10", "37", "37"],
    ["Avatars", "Standard", "Standard", "Standard + Custom"],
    ["Regions", "1", "2", "3"],
    ["", "", "", ""],
    ["Monthly Cost", "$1,103", "$11,497", "$70,867"],
    ["Annual Cost", "$13,236", "$137,964", "$850,404"],
    ["Per-User/Month", "$22.06", "$22.99", "$14.17"],
    ["Per-Session Cost", "$5.52", "$5.75", "$4.72"],
    ["", "", "", ""],
    ["Avatar % of Total", "83%", "86%", "84%"],
    ["Infra % of Total", "3%", "3%", "5%"],
    ["AI/LLM % of Total", "1%", "1%", "1%"],
]

tbl_shape = add_table(slide, Inches(0.5), Inches(1.2), Inches(12.3), Inches(5.5),
                      len(summary_data), 4, summary_data,
                      col_widths=[Inches(2.5), Inches(3.0), Inches(3.4), Inches(3.4)],
                      header_color=DARK_BLUE)

table = tbl_shape.table
colors_list = [GREEN, AZURE_BLUE, ORANGE]
for r in [8, 9, 10, 11]:
    for c in range(1, 4):
        cell = table.cell(r, c)
        for p in cell.text_frame.paragraphs:
            p.font.bold = True
            p.font.size = Pt(12)
            p.font.color.rgb = colors_list[c - 1]

print("Slide 7: Comparison")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 8 — COST SCALING / SESSION ANATOMY
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), DARK_BLUE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Cost Scaling & Unit Economics", 24, WHITE, True)

add_shape(slide, Inches(0.3), Inches(1.2), Inches(6.2), Inches(0.5),
          AZURE_BLUE, "Anatomy of a Single Session Cost", 13, WHITE, True)

session_data = [
    ["Cost Component", "Calculation", "Per Session"],
    ["Avatar streaming (10 min)", "10 min x $0.50/min", "$5.00"],
    ["GPT-4.1 translation", "~5K tokens x $0.002-0.008", "$0.03"],
    ["GPT-4.1 Q&A (2 questions)", "~4K tokens total", "$0.02"],
    ["Embeddings (RAG)", "~5K tokens x $0.02/1M", "$0.0001"],
    ["Cosmos DB reads/writes", "~20 RUs", "$0.000005"],
    ["Blob Storage reads", "~10 images served", "$0.0001"],
    ["Container Apps compute", "~10 min active", "$0.014"],
    ["", "", ""],
    ["TOTAL per Session", "", "$5.06"],
]

add_table(slide, Inches(0.3), Inches(1.8), Inches(6.2), Inches(3.5),
          len(session_data), 3, session_data,
          col_widths=[Inches(2.5), Inches(2.0), Inches(1.7)])

add_shape(slide, Inches(6.8), Inches(1.2), Inches(6.2), Inches(0.5),
          ACCENT_TEAL, "Cost Optimization Levers", 13, WHITE, True)

add_multi_text(slide, Inches(7.0), Inches(1.9), Inches(5.8), Inches(5.0), [
    {"text": "Avatar Time = Cost", "size": 14, "bold": True, "color": ACCENT_TEAL},
    {"text": "Reducing average avatar time from 10 to 7 min saves 30% of total cost.",
     "size": 11, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 6},
    {"text": "Batch over Real-Time", "size": 14, "bold": True, "color": ACCENT_TEAL},
    {"text": "Pre-recorded videos (UC2) can be reused unlimited times. Invest in batch for frequently-used content.",
     "size": 11, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 6},
    {"text": "Smart Translation Caching", "size": 14, "bold": True, "color": ACCENT_TEAL},
    {"text": "Background batch translation on upload means translations are cached in Cosmos DB. Zero cost on repeated access.",
     "size": 11, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 6},
    {"text": "Enterprise Agreement Discounts", "size": 14, "bold": True, "color": ACCENT_TEAL},
    {"text": "Acme EA pricing could reduce avatar costs by 20-40% from published rates.",
     "size": 11, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 6},
    {"text": "Reserved Capacity", "size": 14, "bold": True, "color": ACCENT_TEAL},
    {"text": "Azure AI Services commitment tiers provide significant discounts for predictable workloads.",
     "size": 11, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 6},
    {"text": "Hybrid Avatar Strategy", "size": 14, "bold": True, "color": ACCENT_TEAL},
    {"text": "Use TTS audio-only for low-value interactions (agent chat), reserve avatar for presentations.",
     "size": 11, "color": DARK_GRAY},
])

add_shape(slide, Inches(0.3), Inches(5.5), Inches(6.2), Inches(0.5),
          DARK_BLUE, "Session Cost Breakdown \u2014 99% is Avatar", 12, WHITE, True)
add_shape(slide, Inches(0.5), Inches(6.15), Inches(5.74), Inches(0.35),
          RGBColor(0xFF, 0x6B, 0x35),
          "VoiceLive Avatar \u2014 $5.00 (98.8%)", 10, WHITE, True,
          shape=MSO_SHAPE.RECTANGLE)
add_shape(slide, Inches(6.24), Inches(6.15), Inches(0.15), Inches(0.35),
          AZURE_BLUE, shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(6.6), Inches(5.8), Inches(0.3),
         "Avatar (98.8%)    OpenAI+Infra (1.2%)", 9, MED_GRAY)
print("Slide 8: Unit Economics")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 9 — OPTIMIZATION SCENARIOS
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), DARK_BLUE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Cost Optimization Scenarios (Phase 2 \u2014 500 Users)", 24, WHITE, True)

scenarios_data = [
    ["Scenario", "Monthly Cost", "Savings vs Base", "Per-User", "Notes"],
    ["Baseline (published rates)", "$11,497", "\u2014", "$23.0", "No optimizations"],
    ["EA Discount (20% on Avatar)", "$9,497", "-$2,000 (17%)", "$19.0", "Enterprise agreement pricing"],
    ["EA Discount (40% on Avatar)", "$7,497", "-$4,000 (35%)", "$15.0", "Strong EA negotiation"],
    ["Reduce avatar to 7 min avg", "$8,497", "-$3,000 (26%)", "$17.0", "Optimize content length"],
    ["50% sessions use batch only", "$6,747", "-$4,750 (41%)", "$13.5", "Pre-record common content"],
    ["Audio-only for agent chat", "$10,497", "-$1,000 (9%)", "$21.0", "TTS instead of avatar for Q&A"],
    ["Combined optimistic", "$4,500", "-$7,000 (61%)", "$9.0", "EA + batch + shorter sessions"],
]

add_table(slide, Inches(0.3), Inches(1.2), Inches(12.7), Inches(3.5),
          len(scenarios_data), 5, scenarios_data,
          col_widths=[Inches(2.8), Inches(1.5), Inches(2.0), Inches(1.4), Inches(5.0)])

add_shape(slide, Inches(0.3), Inches(5.0), Inches(12.7), Inches(2.2),
          RGBColor(0xE3, 0xF2, 0xFD), shape=MSO_SHAPE.ROUNDED_RECTANGLE)
add_multi_text(slide, Inches(0.5), Inches(5.1), Inches(12.3), Inches(2.0), [
    {"text": "Recommended Cost Strategy", "size": 16, "bold": True, "color": DARK_BLUE},
    {"text": "", "size": 6, "space_after": 4},
    {"text": "1. Negotiate Enterprise Agreement pricing for AI Speech Services (target: 25-30% discount on avatar)",
     "size": 12, "color": DARK_GRAY},
    {"text": '2. Implement "batch first" strategy \u2014 auto-generate batch videos for all uploaded presentations (reusable at zero marginal cost)',
     "size": 12, "color": DARK_GRAY},
    {"text": "3. Use TTS audio-only for agent chat / Q&A interactions \u2014 reserve VoiceLive for presentation mode only",
     "size": 12, "color": DARK_GRAY},
    {"text": "4. Cache all translations on upload \u2014 Cosmos DB cache eliminates repeat translation costs",
     "size": 12, "color": DARK_GRAY},
    {"text": '5. Monitor & optimize session lengths \u2014 provide "key points summary" mode for shorter interactions',
     "size": 12, "color": DARK_GRAY},
])
print("Slide 9: Optimization")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 10 — TCO 3-YEAR VIEW
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), DARK_BLUE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Total Cost of Ownership (3-Year View)", 24, WHITE, True)

tco_data = [
    ["Cost Category", "Year 1", "Year 2", "Year 3", "3-Year Total"],
    ["", "", "", "", ""],
    ["Phase 1 Azure (6 months)", "$6,618", "\u2014", "\u2014", "$6,618"],
    ["Phase 2 Azure (6mo Y1 + 12mo Y2)", "$68,982", "$137,964", "\u2014", "$206,946"],
    ["Phase 3 Azure (12 months)", "\u2014", "\u2014", "$850,404", "$850,404"],
    ["", "", "", "", ""],
    ["Implementation (one-time)", "", "", "", ""],
    ["Phase 1\u21922 development", "$80,000", "\u2014", "\u2014", "$80,000"],
    ["Phase 2\u21923 development", "\u2014", "$120,000", "\u2014", "$120,000"],
    ["Integration (SGChat, LMS)", "\u2014", "$60,000", "\u2014", "$60,000"],
    ["Custom avatar training", "\u2014", "\u2014", "$30,000", "$30,000"],
    ["", "", "", "", ""],
    ["Support & Operations", "", "", "", ""],
    ["DevOps / SRE (0.5 FTE)", "$50,000", "$50,000", "$50,000", "$150,000"],
    ["", "", "", "", ""],
    ["ANNUAL TOTAL", "$205,600", "$367,964", "$930,404", "$1,503,968"],
]

tco_tbl = add_table(slide, Inches(0.3), Inches(1.2), Inches(12.7), Inches(5.5),
                    len(tco_data), 5, tco_data,
                    col_widths=[Inches(3.5), Inches(2.0), Inches(2.0), Inches(2.0), Inches(3.2)],
                    header_color=DARK_BLUE)

# Bold the total row
table = tco_tbl.table
last_row = len(tco_data) - 1
for c in range(5):
    cell = table.cell(last_row, c)
    for p in cell.text_frame.paragraphs:
        p.font.bold = True
        p.font.size = Pt(11)
        p.font.color.rgb = DARK_BLUE
    cell.fill.solid()
    cell.fill.fore_color.rgb = RGBColor(0xBB, 0xDE, 0xFB)

add_multi_text(slide, Inches(0.3), Inches(6.8), Inches(12), Inches(0.6), [
    {"text": "* Implementation costs are indicative estimates. Actual costs depend on team composition and project management approach.",
     "size": 9, "color": MED_GRAY},
    {"text": "* Azure costs assume published pay-as-you-go rates. Enterprise Agreement discounts can reduce Azure costs by 20-40%.",
     "size": 9, "color": MED_GRAY},
])
print("Slide 10: TCO")

# ═══════════════════════════════════════════════════════════════════
# SLIDE 11 — ASSUMPTIONS & NEXT STEPS
# ═══════════════════════════════════════════════════════════════════
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide)
add_shape(slide, Inches(0), Inches(0), WIDTH, Inches(0.9), DARK_BLUE,
          shape=MSO_SHAPE.RECTANGLE)
add_text(slide, Inches(0.5), Inches(0.15), Inches(12), Inches(0.6),
         "Assumptions, Notes & Next Steps", 24, WHITE, True)

add_shape(slide, Inches(0.3), Inches(1.2), Inches(6.2), Inches(0.5),
          MED_GRAY, "Key Assumptions", 13, WHITE, True)
add_multi_text(slide, Inches(0.5), Inches(1.8), Inches(5.8), Inches(4.5), [
    {"text": "Usage Assumptions", "size": 12, "bold": True, "color": DARK_BLUE},
    {"text": "\u2022 Average 4 sessions per user per month (Phase 1-2), 3 at scale",
     "size": 10, "color": DARK_GRAY},
    {"text": "\u2022 Average 10 minutes of avatar streaming per session",
     "size": 10, "color": DARK_GRAY},
    {"text": "\u2022 10 slides per presentation, ~500 words per slide",
     "size": 10, "color": DARK_GRAY},
    {"text": "\u2022 2 Q&A questions per session on average",
     "size": 10, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 4},
    {"text": "Pricing Assumptions", "size": 12, "bold": True, "color": DARK_BLUE},
    {"text": "\u2022 Azure published pay-as-you-go rates (April 2026)",
     "size": 10, "color": DARK_GRAY},
    {"text": "\u2022 West Europe region (France Central available)",
     "size": 10, "color": DARK_GRAY},
    {"text": "\u2022 No Enterprise Agreement discounts applied",
     "size": 10, "color": DARK_GRAY},
    {"text": "\u2022 No Azure Reserved Instances or Savings Plans",
     "size": 10, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 4},
    {"text": "Not Included", "size": 12, "bold": True, "color": RED},
    {"text": "\u2022 Network egress / bandwidth costs (typically <1%)",
     "size": 10, "color": DARK_GRAY},
    {"text": "\u2022 Azure Entra ID / Microsoft 365 licensing",
     "size": 10, "color": DARK_GRAY},
    {"text": "\u2022 End-user devices / browsers",
     "size": 10, "color": DARK_GRAY},
    {"text": "\u2022 Project management and change management",
     "size": 10, "color": DARK_GRAY},
])

add_shape(slide, Inches(6.8), Inches(1.2), Inches(6.2), Inches(0.5),
          AZURE_BLUE, "Recommended Next Steps", 13, WHITE, True)
add_multi_text(slide, Inches(7.0), Inches(1.8), Inches(5.8), Inches(4.5), [
    {"text": "1. Validate Usage Assumptions", "size": 12, "bold": True, "color": AZURE_BLUE},
    {"text": "Run a 2-week pilot with 10 users to measure actual session lengths and frequency.",
     "size": 10, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 6},
    {"text": "2. Negotiate EA Pricing", "size": 12, "bold": True, "color": AZURE_BLUE},
    {"text": "Engage Microsoft account team for Acme-specific Azure AI Speech pricing.",
     "size": 10, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 6},
    {"text": "3. Run Azure Pricing Calculator", "size": 12, "bold": True, "color": AZURE_BLUE},
    {"text": "Configure exact workload in Azure Pricing Calculator for region-specific estimates.",
     "size": 10, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 6},
    {"text": "4. Cost Monitoring Strategy", "size": 12, "bold": True, "color": AZURE_BLUE},
    {"text": "Implement Azure Cost Management budgets and alerts from day one.",
     "size": 10, "color": DARK_GRAY},
    {"text": "", "size": 6, "space_after": 6},
    {"text": "5. Phased Go/No-Go Gates", "size": 12, "bold": True, "color": AZURE_BLUE},
    {"text": "Each phase has a cost review gate before scaling to the next tier.",
     "size": 10, "color": DARK_GRAY},
])
print("Slide 11: Assumptions")

# ─── SAVE ─────────────────────────────────────────────────────────
out_path = os.path.join("docs", "RFI-Cost-Estimation.pptx")
prs.save(out_path)
print(f"\nSaved: {out_path}")
print(f"Total slides: {len(prs.slides)}")

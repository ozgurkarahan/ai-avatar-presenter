"""Generate 6 distinct test .pptx files for multi-deck search testing.

Each deck covers a different topic with topic-specific vocabulary so we can
assert that a topic-specific query returns slides from the correct deck.

Usage:
    python scripts/make_multideck_test.py [output_dir]

Defaults to ./tests/fixtures/decks/
"""
from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

DECKS = [
    {
        "filename": "ai-fundamentals.pptx",
        "language": "en-US",
        "title": "AI Fundamentals: Models and Language Models",
        "slides": [
            ("Large Language Models",
             "Large language models are trained on vast text corpora to predict the next token and follow natural-language instructions.",
             "Explain tokens, context windows and why instruction tuning makes models helpful."),
            ("Small Language Models",
             "Small language models trade breadth for speed and cost and can run on laptops, phones or edge devices.",
             "Contrast the latency, cost and privacy benefits of on-device inference."),
            ("Open-Weight Models",
             "Open-weight models publish their parameters so teams can self-host, inspect and fine-tune them.",
             "Clarify the difference between open weights and fully open training data and code."),
            ("Speech: STT and TTS",
             "Speech-to-text transcribes spoken audio while neural text-to-speech turns text into natural-sounding voices.",
             "Mention the latency budget of a real-time voice assistant."),
            ("Choosing a Model",
             "Model selection balances quality, latency, cost and licensing against the needs of each task.",
             "Recommend evaluating candidate models on a representative golden dataset."),
        ],
    },
    {
        "filename": "ai-ethics.pptx",
        "language": "en-US",
        "title": "Responsible AI & Ethics",
        "slides": [
            ("Principles of Responsible AI",
             "Fairness, transparency, accountability, privacy and safety are the five pillars of responsible AI deployment.",
             "Tie to the EU AI Act risk-based classification."),
            ("Bias in Machine Learning",
             "Training data reflecting historical inequities can cause models to discriminate against protected groups.",
             "Walk through the COMPAS recidivism study and gender-shaded facial analysis results."),
            ("Explainability & Interpretability",
             "SHAP and LIME let practitioners attribute a model's prediction to individual input features.",
             "Contrast model-agnostic vs model-specific explainers."),
            ("Privacy-Preserving ML",
             "Federated learning and differential privacy enable training on sensitive data without centralising it.",
             "Reference Apple's on-device learning and Google's federated keyboard."),
            ("Governance & AI Audits",
             "Model cards, datasheets and third-party audits operationalise AI governance inside an enterprise.",
             "Suggest adopting NIST AI RMF."),
        ],
    },
    {
        "filename": "cloud-security.pptx",
        "language": "en-US",
        "title": "Cloud Security Fundamentals",
        "slides": [
            ("Shared Responsibility Model",
             "In IaaS the provider secures the hypervisor while the customer secures the operating system and data.",
             "Clarify that SaaS shifts most responsibility to the vendor, but identity stays with the customer."),
            ("Identity & Zero Trust",
             "Zero trust assumes breach and verifies every request with strong authentication and least-privilege access.",
             "Reference NIST SP 800-207 and Azure Conditional Access policies."),
            ("Encryption at Rest and in Transit",
             "TLS 1.3 protects data in motion while customer-managed keys in Key Vault protect data at rest.",
             "Recommend disabling TLS 1.0/1.1 and auditing with Defender for Cloud."),
            ("Network Segmentation",
             "Private endpoints, VNet peering and NSGs replace the legacy perimeter with micro-segmented workloads.",
             "Mention Azure Firewall Premium and IDPS signatures."),
            ("Incident Response in the Cloud",
             "Automated playbooks in Sentinel can quarantine compromised identities within minutes of detection.",
             "Highlight MITRE ATT&CK coverage and Kusto hunt queries."),
        ],
    },
    {
        "filename": "medical-devices.pptx",
        "language": "en-US",
        "title": "Medical Device Regulation",
        "slides": [
            ("EU MDR Classification",
             "Medical devices are classified I, IIa, IIb or III depending on invasiveness, duration of contact and active function.",
             "Mention MDR 2017/745 replacing the old directive."),
            ("Clinical Evaluation",
             "Manufacturers must demonstrate clinical safety and performance through literature review and clinical investigations.",
             "Reference MEDDEV 2.7/1 rev 4 guidance."),
            ("Post-Market Surveillance",
             "Vigilance reporting, PSUR and PMCF studies keep real-world evidence flowing back to the manufacturer.",
             "Cite EUDAMED and UDI requirements."),
            ("Quality Management ISO 13485",
             "ISO 13485 requires risk-based processes for design, production and service of medical devices.",
             "Link to ISO 14971 for risk management."),
            ("Cybersecurity for Connected Devices",
             "FDA and MDCG guidance require secure boot, threat modelling and coordinated vulnerability disclosure.",
             "Highlight SBOM requirements."),
        ],
    },
    {
        "filename": "ia-generative-fr.pptx",
        "language": "fr-FR",
        "title": "L'IA générative en entreprise",
        "slides": [
            ("Qu'est-ce que l'IA générative ?",
             "Les modèles de langage génèrent du texte, du code ou des images à partir d'instructions en langage naturel.",
             "Rappeler la différence entre IA prédictive et IA générative."),
            ("Ingénierie du contexte",
             "L'ingénierie du contexte assemble instructions, documents et mémoire pour guider le modèle de langage.",
             "Montrer qu'un bon contexte réduit les hallucinations davantage qu'une formulation astucieuse."),
            ("Génération augmentée par récupération",
             "Le RAG recherche les passages pertinents dans vos documents et les transmet au modèle pour une réponse sourcée.",
             "Évoquer la recherche hybride et le reclassement sémantique."),
            ("Agents et protocole MCP",
             "Les agents enchaînent raisonnement et appels d'outils ; le protocole MCP standardise l'accès aux outils et aux données.",
             "Insister sur la validation humaine des actions sensibles."),
            ("IA responsable",
             "Transparence, confidentialité des données et supervision humaine encadrent chaque déploiement d'IA générative.",
             "Mentionner le règlement européen sur l'IA (AI Act)."),
        ],
    },
    {
        "filename": "agentes-ia-produccion.pptx",
        "language": "es-ES",
        "title": "Agentes de IA en producción",
        "slides": [
            ("Del chatbot al agente",
             "Un agente de IA planifica, llama a herramientas y observa los resultados hasta completar una tarea.",
             "Contrastar un asistente conversacional con un agente que actúa."),
            ("El arnés del agente",
             "Instrucciones, herramientas bien descritas, memoria y límites de pasos forman el arnés que hace fiable al agente.",
             "Destacar el registro detallado de cada paso."),
            ("Protocolo MCP",
             "El Model Context Protocol conecta los agentes con herramientas y fuentes de datos mediante un estándar abierto.",
             "Mencionar la autenticación y el principio de mínimo privilegio."),
            ("Evaluación y observabilidad",
             "Conjuntos de pruebas, trazas y métricas de calidad permiten detectar regresiones antes de cada despliegue.",
             "Referencia a la evaluación continua con conjuntos dorados."),
            ("IA en producción",
             "Cuotas, control de costes, supervisión humana y planes de reversión permiten operar agentes a escala.",
             "Ejemplos de despliegue progresivo por fases."),
        ],
    },
]


def build_deck(out_path: Path, title: str, slides: list[tuple[str, str, str]]) -> None:
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(5.625)

    # Title slide
    layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = title
    if len(slide.placeholders) > 1:
        slide.placeholders[1].text = "Oz Radio — Demo"

    # Content slides
    content_layout = prs.slide_layouts[1]
    for title_text, body_text, notes_text in slides:
        s = prs.slides.add_slide(content_layout)
        s.shapes.title.text = title_text
        body_ph = s.placeholders[1]
        tf = body_ph.text_frame
        tf.text = body_text
        for p in tf.paragraphs:
            for r in p.runs:
                r.font.size = Pt(18)
        notes_tf = s.notes_slide.notes_text_frame
        notes_tf.text = notes_text

    prs.core_properties.author = "Oz Radio"
    prs.core_properties.last_modified_by = "Oz Radio"
    prs.core_properties.title = title
    prs.save(str(out_path))
    print(f"Wrote {out_path}  ({len(slides) + 1} slides)")


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "decks"
    out_dir.mkdir(parents=True, exist_ok=True)
    for deck in DECKS:
        build_deck(out_dir / deck["filename"], deck["title"], deck["slides"])
    print(f"\nGenerated {len(DECKS)} test decks in {out_dir}")


if __name__ == "__main__":
    main()

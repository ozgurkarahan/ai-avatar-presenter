# End-to-end test fixtures — 9 coherent decks in 3 groups

Purpose: end-to-end test corpus for the **3 use cases** (UC1 Learning Hub/Paths, UC2 Avatar Video Library, UC3 Create/Q&A Library). Each deck has 5 slides with 2-sentence speaker notes (~25-30 s spoken per slide).

Regenerate with:
```bash
python tests/fixtures/rfi/_generate.py
```

## Groups — each forms a natural learning path

### 🛡️ Group A — Safety & Compliance (🇫🇷 FR)
Progression: fundamentals → risk identification → emergency response.

| Order | File | Title |
|---|---|---|
| 1 | `securite-bases.pptx` | Sécurité sur chantier : les fondamentaux |
| 2 | `risques-chantier.pptx` | Identifier et prévenir les risques de chantier |
| 3 | `intervention-urgence.pptx` | Intervention en cas d'urgence |

### 🌱 Group B — Sustainability (🇬🇧 EN)
Progression: why decarbonize → low-carbon materials → circular economy.

| Order | File | Title |
|---|---|---|
| 1 | `decarbonization-intro.pptx` | Decarbonization: Introduction for industry |
| 2 | `low-carbon-materials.pptx` | Low-carbon materials in construction |
| 3 | `circular-economy.pptx` | Circular economy in practice |

### 🤖 Group C — AI / Digital Transformation (🇪🇸 ES)
Progression: intro to industrial AI → AI in production → AI ethics.

| Order | File | Title |
|---|---|---|
| 1 | `ia-industrial-intro.pptx` | Introducción a la IA en la industria |
| 2 | `ia-en-produccion.pptx` | IA aplicada a producción |
| 3 | `etica-ia-empresa.pptx` | Ética de la IA en la empresa |

## Test coverage unlocked

- **UC1 Learning Hub**: 9 decks in 3 languages → test upload, listing, filtering.
- **UC1 Learning Paths**: 3 natural paths creatable (manually and via AI recommend).
- **UC1 AI Recommend**: test topics "sécurité chantier" → group A, "decarbonization" → B, "inteligencia artificial" → C.
- **UC2 Avatar Video Library**: each PPT exercises a different language + can be regenerated in another.
- **UC3 Create / Q&A Library**: coherent corpus for retrieval tests ("Quels matériaux bas carbone ?", "¿Qué es el mantenimiento predictivo?", etc.).

`manifest.json` is regenerated on each run and lists every deck with its group, language, tags, and slide count — consumable by automated e2e tests.

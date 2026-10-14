# End-to-end test fixtures — 9 coherent decks in 3 groups

Purpose: end-to-end test corpus for the decks catalog / playlists, the narrated video library and the podcast library. Each deck has 5 slides with 2-sentence speaker notes (~25-30 s spoken per slide).

Regenerate with:
```bash
python tests/fixtures/samples/_generate.py
```

## Groups — each forms a natural playlist

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

- **Decks catalog**: 9 decks in 3 languages → test upload, listing, filtering.
- **Playlists**: 3 natural playlists creatable (manually and via AI recommend).
- **AI playlist recommendation**: test topics "sécurité chantier" → group A, "decarbonization" → B, "inteligencia artificial" → C.
- **Video library**: each PPT exercises a different language + can be regenerated in another.
- **Podcast library / Q&A**: coherent corpus for retrieval tests ("Quels matériaux bas carbone ?", "¿Qué es el mantenimiento predictivo?", etc.).

`manifest.json` is regenerated on each run and lists every deck with its group, language, tags, and slide count — consumable by automated e2e tests.

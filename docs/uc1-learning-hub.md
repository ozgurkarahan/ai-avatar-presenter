# UC1 · Learning Hub — Design

> **Status:** Delivered 2026-04-19/20 (revision `uc1v10` on `ca-clgsqan6efeuy`).
> Covers Saint-Gobain RFI 559 **Use Case 1 · Silver tier** (multi-deck corpus + Learning Paths).

The UC1 Learning Hub lives at [`/uc1`](https://ca-clgsqan6efeuy.thankfulhill-3503b062.swedencentral.azurecontainerapps.io/uc1) — a dedicated section of the app that complements the legacy single-deck UC1 flow at `/`. The legacy route is intentionally preserved to avoid any regression on the previously demo'd UX.

---

## 1. Scope

The Hub is the UC1 **Silver** experience from the Microsoft RFI response:

> *Avatar overlaid on PPT slides, slide-by-slide presentation, interruptible Q&A, natural language slide navigation, Content Understanding across a corpus of decks.*

On top of Silver, it also delivers an early **Gold**-tier capability: the AI path recommender dynamically selects a sequence of decks from the corpus to cover a learning topic.

### Pages

| Route | Page | Purpose |
|---|---|---|
| `/uc1` | `Uc1HubPage` | Landing — top-level nav into decks / learn / paths |
| `/uc1/decks` | `Uc1DecksPage` | Deck catalog (list, upload, delete) |
| `/uc1/learn` | `Uc1LearnPage` | Hybrid semantic search across the whole corpus |
| `/uc1/paths` | `Uc1PathsListPage` | Learning Paths library + **"✨ Recommend with AI"** modal |
| `/uc1/paths/:pathId` | `Uc1PathPlayerPage` | Path player — avatar auto-presents each deck in sequence |
| `/uc1/present/:deckId` | `Uc1PresentPage` | Single-deck player (shared component with path player) |

---

## 2. Architecture

```
┌──────────────────────────────────┐
│          React SPA (/uc1)         │
│  Hub · Learn · Decks · Paths      │
└─────────────┬────────────────────┘
              │ REST
┌─────────────▼────────────────────┐
│   FastAPI routers                 │
│   - routers/uc1.py                │  → ingest, list, delete, search
│   - routers/uc1_paths.py          │  → paths CRUD, progress, recommend
└──┬────────────────┬───────────────┘
   │                │
   │                └─► Azure OpenAI (GPT-4.1) ── JSON mode ──► path recommendation
   │
   ├─► Azure AI Search ── hybrid (vector + keyword) ──► index `uc1-decks`
   │      (srch-clgsqan6efeuy, Free SKU, swedencentral)
   │
   └─► Azure Cosmos DB
          container `presentations`  → decks (partition key: /id)
          container `paths`          → learning paths + progress
```

---

## 3. Corpus & search

### 3.1 Ingestion

`POST /api/uc1/upload` accepts a `.pptx`, runs the shared PPTX parser (title, bullets, notes, slide PNG), and writes:

1. Slide images + manifest to **Blob Storage** (SAS URL reads).
2. A deck record to the **`presentations`** Cosmos container (partitioned by `/id`).
3. Per-slide documents to **Azure AI Search** index `uc1-decks` with:
   - `content_vector` (1536-dim, `text-embedding-3-small`)
   - `content_text` (keyword)
   - `deck_id`, `slide_index`, `language`, `title`, `notes_en` (auto-translated for cross-language search)

### 3.2 Search

`POST /api/uc1/learn/search` runs a **hybrid** query:

- Vector kNN on `content_vector`
- BM25 keyword on `content_text` + `notes_en`
- Reciprocal rank fusion (server-side via AI Search)

Returns slide-level hits grouped by deck, with highlighted snippet + link to `/uc1/present/:deckId?slide=:n`.

> **Note on field naming:** the UC1 decks endpoint returns `deck_id` — **not** `id`. This is important when writing tests or clients. See `tests/test_uc1_paths_api.py` for the canonical pattern.

---

## 4. Learning Paths

A **Learning Path** is an ordered list of decks the user navigates sequentially. Each step carries its own slide-resume index, so the user can leave and come back.

### 4.1 Data model

```json
{
  "id": "path-abc123",
  "title": "Workplace safety essentials",
  "description": "...",
  "language": "fr-FR",
  "steps": [
    { "deck_id": "securite-bases",     "title": "Bases de la sécurité",  "resume_slide_index": 0 },
    { "deck_id": "risques-chantier",   "title": "Risques sur chantier",  "resume_slide_index": 0 },
    { "deck_id": "intervention-urgence","title": "Intervention d'urgence","resume_slide_index": 0 }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

Stored in Cosmos container `paths` (partition key `/id`). Steps store only `deck_id`; title + slide count are hydrated on read by joining against `presentations`.

### 4.2 Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/uc1/paths` | Create |
| `GET` | `/api/uc1/paths` | List (hydrated) |
| `GET` | `/api/uc1/paths/{id}` | Get |
| `DELETE` | `/api/uc1/paths/{id}` | Delete |
| `POST` | `/api/uc1/paths/{id}/progress` | Update resume slide + completed steps |
| `POST` | `/api/uc1/paths/recommend` | AI recommendation (see below) |

### 4.3 Path player — zero-click between decks

The Path Player (`Uc1PathPlayerPage`) reuses `AvatarPanel` with two props that were added specifically for this flow:

- **`autoStart: true`** — on mount, `AvatarPanel` auto-connects to Speech (instead of waiting for a "Connect avatar" click) and, for each new `presentation.id`, auto-calls `speakSlide(currentSlide)`. A `useRef` keyed on `presentation.id` makes sure the auto-trigger fires exactly once per deck. The user-selected avatar, voice, and language stay stable across the whole path — no re-picking.
- **`<LanguageSelector variant="light">`** — light variant uses dark text + light-gray border so the control is readable on the path player's white card background. The default dark variant assumes a gradient/purple banner (used on `/uc1` and `/` pages).

Both were introduced in revision `uc1v10`. A Playwright regression test (`tests/uc1-learning-paths.spec.ts → "path player language selector is readable on white banner"`) asserts the computed `color` is not `rgb(255, 255, 255)` to prevent a silent regression.

---

## 5. AI path recommendation

`POST /api/uc1/paths/recommend` is a **no-persistence** endpoint that returns an *on-the-fly* suggested path for a topic.

### 5.1 Request

```json
{
  "topic": "sécurité sur chantier et prévention des risques",
  "max_steps": 3,
  "language": "fr-FR"    // optional filter on deck language
}
```

Validation:
- `topic` length 3–500
- `max_steps` 2–8
- `language` optional; if set, the catalog passed to GPT is filtered to that language first

### 5.2 Prompt / response format

The backend:

1. Fetches the full catalog from Cosmos (`presentations`).
2. Optionally filters by `language`.
3. Passes `[{deck_id, title, language, slide_count, summary}]` plus the user topic to **GPT-4.1** with `response_format={"type":"json_object"}` and `temperature=0.2`.
4. Enforces a strict JSON schema (`RecommendResponse` — title, description, steps with deck_id + rationale).
5. Validates every returned `deck_id` against the catalog (rejects hallucinations) and hydrates each step with the real title + slide count.

### 5.3 UI flow

`Uc1PathsListPage` has a **"✨ Recommend with AI"** button that opens `RecommendPathModal`:

1. User enters topic, picks max steps + language.
2. Modal calls `recommendPath()` and shows a preview with per-step rationale.
3. Clicking **"Accept & customize"** prefills `CreatePathModal` with the suggestion so the user can edit before saving.

### 5.4 Validation

Tested end-to-end on `tests/e2e_rfi.py` against the 9 RFI fixture decks. Last run (3 topics, 3 languages):

| Topic | Expected keyword group | GPT-4.1 result |
|---|---|---|
| "sécurité sur chantier et prévention des risques" (`fr-FR`) | `safety` group | `securite-bases → risques-chantier → intervention-urgence` ✅ pedagogically ordered |
| "decarbonization and low-carbon materials" (`en-US`) | `sustainability` group | `decarbonization-intro → low-carbon-materials` ✅ |
| "inteligencia artificial en la industria y su ética" (`es-ES`) | `ai` group | `ia-industrial-intro → ia-en-produccion → etica-ia-empresa` ✅ pedagogically ordered |

---

## 6. Testing

### 6.1 E2E coverage

| Script | Scope | Last run |
|---|---|---|
| `tests/e2e_rfi.py` | Reset all Cosmos containers + UC2 library → upload 9 RFI fixtures → UC1 hub + search + paths + progress + AI recommend → UC2/UC3 smoke | 30/30 passed on `uc1v10` |
| `tests/e2e_render.py` | UC2 + UC3 full render, one language or multi-language sweep | 30/30 passed multi-language (fr-FR / en-US / es-ES × UC2+UC3) |
| `tests/test_uc1_paths_api.py` | pytest — paths CRUD, progress, AI recommend (incl. catalog validation) | 4 passed, 1 skipped (LLM-dependent) |
| `tests/uc1-learning-paths.spec.ts` | Playwright UI — create path, recommend modal, light language selector regression | 9 passed |

### 6.2 Fixtures

`tests/fixtures/rfi/` contains 9 coherent pedagogical decks in 3 thematic groups:

- **Group A — Safety (FR-FR):** `securite-bases`, `risques-chantier`, `intervention-urgence`
- **Group B — Sustainability (EN-US):** `decarbonization-intro`, `low-carbon-materials`, `circular-economy`
- **Group C — AI in industry (ES-ES):** `ia-industrial-intro`, `ia-en-produccion`, `etica-ia-empresa`

Each deck: 5 slides, 2-sentence speaker notes, progresses from intro → deepening → application. Regenerate from `python tests/fixtures/rfi/_generate.py`.

### 6.3 Running locally

```powershell
# Cheap (~1 min) — assumes the target app is up
python tests/e2e_rfi.py --base-url https://ca-clgsqan6efeuy.thankfulhill-3503b062.swedencentral.azurecontainerapps.io

# Expensive (~10 min + TTS tokens) — full UC2/UC3 media render, English only
python tests/e2e_render.py --base-url https://ca-clgsqan6efeuy.thankfulhill-3503b062.swedencentral.azurecontainerapps.io

# Multi-language render sweep (~30 min) — fr-FR (Safety), en-US (Sustainability), es-ES (AI)
python tests/e2e_render.py --base-url https://ca-clgsqan6efeuy.thankfulhill-3503b062.swedencentral.azurecontainerapps.io --languages fr-FR,en-US,es-ES
```

`--skip-reset` preserves existing data when iterating locally. `--skip-video` / `--skip-podcast` in `e2e_render.py` let you run one UC at a time.

---

## 7. Azure resources

| Resource | Name | Purpose |
|---|---|---|
| Azure AI Search | `srch-clgsqan6efeuy` | Free SKU, swedencentral, index `uc1-decks`, hybrid search |
| Cosmos DB (Serverless) | `cosmos-clgsqan6efeuy` | Containers `presentations` (decks) + `paths` (learning paths) |
| Blob Storage | `stclgsqan6efeuy` | Slide PNGs + PPTX sources |
| Azure OpenAI | `oai-*` | `gpt-4.1` (chat + recommend) + `text-embedding-3-small` (indexing) |
| Azure AI Speech | `speech-*` | DragonHD TTS + batch avatar |
| Container App | `ca-clgsqan6efeuy` | FastAPI + React SPA, rev `uc1v10` |
| ACR | `crclgsqan6efeuy` | Container image registry |

RG: `rg-ai-presenter-sub2`. Deploy via `az acr build -r crclgsqan6efeuy -t ai-presenter:uc1-vN --no-logs .` then `az containerapp update --image ...`.

---

## 8. Known limitations / open items

- **Search index rebuild** — there is no one-click "re-index all decks" endpoint; `POST /api/uc1/upload` re-ingests individually. Deleting a deck leaves orphan search docs until a full recrawl.
- **Language filter in recommend** — if the user picks a language that has fewer than `max_steps` decks, the response may be shorter than requested (GPT currently respects "don't invent content").
- **Path progress aggregation** — the player writes back `resume_slide_index` per step but there is no dashboard view of global path completion yet.
- **No auth** — the Hub is currently open; deployment is a PoC on a public Container App URL. For Saint-Gobain production we would put this behind Entra ID + per-user path ownership.
- **UC1 legacy `/` route** — intentionally preserved without changes. Any regression on the original flow blocks a release.

---

## 9. Related docs

- [../README.md](../README.md) — overall project readme + API reference
- [uc2-static-video.md](uc2-static-video.md) — sibling UC2 design
- [uc3-podcast-design.md](uc3-podcast-design.md) — sibling UC3 design
- [deep-dive-azure.md](deep-dive-azure.md) — infrastructure walkthrough

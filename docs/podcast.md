# Podcast — Two-Avatar Podcast Video — Design

**Status:** Implemented PoC — demo-quality, with Blob-backed media library

> **Demo-quality PoC, not production.** This doc has been re-scoped away from production robustness (workers, idempotent manifests, global semaphores, chunk-reduce) toward **demo polish**: split-screen layout with live speaker highlight, scrolling subtitles under each avatar, waveform pulse, premium HD voices, branded intro/outro, sample prompt gallery, streaming script generation. The goal is a convincing end-to-end demo.
**Scope:** podcast-style two-avatar video from any document
**Inspiration:** NotebookLM "Audio Overview"

---

## 1. Goals & Non-Goals

### Goals
- Upload documents (PPTX, PDF, DOCX, TXT, URL) + optional instructions → get a **podcast-style video** with two distinct AI avatars having a conversation.
- Produce four deliverables per job: **MP4** (dual-avatar video), **MP3** (audio-only), **SRT transcript** with speaker labels and timestamps, and a **SCORM ZIP** for LMS upload.
- Preserve per-speaker lip-sync quality by using **one batch job per `(avatar, voice)` pair** with multiple SSML inputs (one per turn of that speaker), yielding one clip per turn while minimizing remote-job overhead and quota pressure.
- Reuse the shared deployment (one resource group, one `azd up`) for easy teardown.
- Ship as a second page (`/podcast`) in the existing React app, sharing the backend and auth of the deck and video features.

### Non-Goals (first release)
- Real-time (streaming) dual-avatar conversations.
- Background music and advanced transitions.
- Custom (trained) avatars.
- Mixing languages within a single podcast.
- Teams embedding — reuse manifest later if needed.

---

## 2. User Flow

1. User navigates to `/podcast`.
2. Uploads one or more documents (drag/drop) and/or pastes a URL.
3. (Optional) Enters instructions: topic focus, conversation style (casual/formal/debate), **audience level** (Any / Beginner / Practitioner / Expert — see §3.2.1), target length (short ~3 min / medium ~6 min / long ~10 min), target language, number of turns.
4. Picks Interviewer avatar + voice and Expert avatar + voice (defaults filled in).
5. Clicks **Generate script** → sees a two-column editable dialogue. Each turn shows speaker label, text area, word count, estimated duration.
6. Edits / reorders / deletes turns if desired. Can regenerate specific turns.
7. Clicks **Render podcast** → backend starts job, UI polls status with stage-level progress (ingesting / scripting / rendering 3/8 / composing / done).
8. On completion, UI shows embedded MP4 player + MP3 download + SRT download + shareable link.

---

## 3. Backend Architecture

### 3.1 New router: `demos/backend/routers/podcast.py`

```
POST   /api/podcast/ingest               → Ingest docs, return document_id + extracted text
POST   /api/podcast/script               → Generate script from document_id + options
PATCH  /api/podcast/script/{script_id}   → Save edited script
POST   /api/podcast/render               → Start render job from script_id + role config
GET    /api/podcast/jobs/{job_id}        → Job status + outputs
GET    /api/podcast/jobs                 → List recent jobs
GET    /api/podcast/library              → Published podcasts
GET    /api/podcast/library/{job_id}     → MP4 / MP3 / SRT / SCORM SAS URLs
DELETE /api/podcast/library/{job_id}     → Delete published item
GET    /api/podcast/voices               → Available voices per language (subset of the live presenter list)
GET    /api/podcast/avatars              → Available pre-built avatars (harry, lisa, …)
```

### 3.2 New services

| Module | Responsibility |
|---|---|
| `services/podcast_ingest.py` | Multi-format parsing: PPTX (reuse `pptx_parser`), PDF (`pypdf`), DOCX (`python-docx`), TXT/MD (plain), URL (`httpx` + `readability-lxml`). Returns normalized `Document`. |
| `services/podcast_script.py` | GPT-4.1 structured output. Prompt builds context from `Document`, respects style / length / language. Returns `Script` (list of `DialogueTurn`). |
| `services/podcast_render.py` | Orchestrator. Groups turns by speaker; submits **one batch synthesis job per speaker** with per-turn SSML inputs; polls; downloads each clip to blob; maintains per-clip manifest (remote job id, status, attempt, blob url, duration). Designed for idempotent re-run. |
| `services/podcast_compose.py` | ffmpeg composition. **Split-screen layout** (see §3.5): both avatars as head-and-shoulders tiles across the top, karaoke captions + speaker labels between them, the current slide below in true 16:9 (contained, never stretched). Per-turn segments are rendered then concatenated; applies `loudnorm`, probes actual durations with `ffprobe` to build SRT. Emits MP4 + MP3 + SRT. |

#### 3.2.1 Audience level

`ScriptRequest.audience_level` (optional: `"beginner" | "practitioner" | "expert"`, default `null`) tunes vocabulary and depth of the dialogue. It is composed with style, focus and language in `_build_system_prompt` as one extra `Audience:` line and never changes the turn / `slide_idx` / output-format rules. Unknown values are rejected with **422**.

| Level | Directive added to the system prompt |
|---|---|
| *Any (default)* → `null` | nothing — the prompt is byte-for-byte the pre-existing one |
| `beginner` | assume no prior AI/technical knowledge; define every term in plain words; everyday analogies; avoid jargon and acronyms (expand if unavoidable); one idea at a time |
| `practitioner` | audience builds or operates solutions; concrete how-to, trade-offs, practical tips, common pitfalls; standard terminology OK |
| `expert` | deep technical audience; architecture, internals, limits, failure modes, evaluation; precise vocabulary; stay strictly within the source — never invent numbers or details |

The level is stored on the saved `Script` (`GET /api/podcast/scripts/{id}`), written to the library `manifest.json` (`audience_level`) and returned by the admin `GET /api/podcast/library` + `/library/{job_id}` responses — the library shows it as a small "*Level* audience" chip. The anonymous public DTO is unchanged. In the UI, the **Audience level** select sits next to **Style** in *Conversation settings*.

### 3.3 Data model — Cosmos DB `podcasts` database

**Three containers, partitioned by `/userId`** (matches access patterns: a user lists their own docs/scripts/jobs). `scriptId` / `documentId` are indexed non-partition fields.

```jsonc
// container "documents"  (PK /userId)
{ "id": "doc-…", "userId": "alice", "sources": [{"kind": "pdf", "name": "…", "blobUrl": "…"}],
  "content": { "title": "…", "sections": [{"heading": "…", "text": "…"}] },
  "tokenCount": 18420, "createdAt": "…" }

// container "scripts"    (PK /userId)
{ "id": "scr-…", "userId": "alice", "documentId": "doc-…",
  "language": "en-US", "style": "casual", "targetDurationSec": 360,
  "turns": [ {"idx": 0, "speaker": "interviewer", "text": "…"}, … ],
  "createdAt": "…", "updatedAt": "…" }

// container "jobs"       (PK /userId)
{ "id": "job-…", "userId": "alice", "scriptId": "scr-…",
  // job config is snapshotted from the script at job creation time (immutable)
  "scriptSnapshot": { /* full turns + roles + layout */ },
  "roles": {
    "interviewer": { "avatar": "harry", "voice": "en-US-Andrew:DragonHDLatestNeural" },
    "expert":      { "avatar": "lisa",  "voice": "en-US-Ava:DragonHDLatestNeural" }
  },
  "layout": "split_screen_with_slides",   // or "split_screen_only" (no slide)
  "state":  "queued|rendering|composing|done|failed|cancelled",
  "progress": { "stage": "rendering", "completed": 3, "total": 8 },
  // per-clip manifest — the source of truth for idempotent retry & resume
  "clips": [
    { "turnIdx": 0, "speaker": "interviewer",
      "remoteJobId": "…", "attempt": 1,
      "status": "queued|submitted|succeeded|failed",
      "blobUrl": "…", "durationSec": 7.23, "checksum": "sha256:…" }
  ],
  // per-speaker remote batch job ids (one job per (avatar, voice) pair)
  "remoteBatchJobs": {
    "interviewer": { "id": "…", "status": "…", "inputsCount": 4 },
    "expert":      { "id": "…", "status": "…", "inputsCount": 4 }
  },
   "outputs": { "mp4Blob": "…", "mp3Blob": "…", "srtBlob": "…", "scormBlob": "…" },
  "error": null, "cancelRequested": false,
  "createdAt": "…", "updatedAt": "…" }
```

Indexing: default indexing on the three containers is fine. Add composite indexes on `(userId ASC, createdAt DESC)` for listings.

### 3.4 Job state machine & idempotency

Ingest and scripting are synchronous endpoints (no long-running state). The **job** covers only rendering + composition:

```
queued → rendering → composing → done
             ↘            ↘
              ↘→  failed  ←↗
    cancelled (set cancelRequested=true; worker transitions to cancelled at next checkpoint)
```

**Worker loop (idempotent / resumable):**

1. **Load job.** If `state ∈ {done, failed, cancelled}` → return.
2. **Honor cancellation.** If `cancelRequested`: best-effort DELETE any live remote batch jobs, set `state=cancelled`, return.
3. **Per-speaker batch submission.** For each speaker in `roles`:
   - If `remoteBatchJobs[speaker].id` is already set and remote status ∈ {Running, Succeeded} → reuse.
   - Otherwise submit one batch avatar synthesis job with one SSML input per turn belonging to that speaker, ordered by `turnIdx`. Persist `remoteJobId` per clip.
4. **Poll until both speakers complete.** Update each clip's `status`, `blobUrl`, `durationSec` as outputs become available. Failed individual inputs → retry that batch job with only the failed inputs (attempt+1). Second failure → mark clip `failed` → job `failed`.
5. **Download clips to our blob.** Idempotent by `checksum`; skip if already present.
6. **Compose.** Skip if `outputs.mp4Blob` already set and checksum matches clip manifest hash (i.e., restart after crash during upload is safe). Run ffmpeg: concat per `turnIdx` order, apply `loudnorm`, probe durations with `ffprobe`, emit MP4 + MP3 + SRT.
7. **Mark `done`.**

**Global render queue:** a single semaphore (implemented as a Cosmos lease doc) caps the number of concurrently rendering jobs across the worker fleet (starting value: 3). New jobs beyond the cap stay in `queued`.

Ingestion + scripting are synchronous REST endpoints (no job row); if their outputs take longer than the request budget we move them to the same worker pattern later.

### 3.5 Composition algorithm — video layout (geometry contract v1)

Output is 1920x1080 @ 25 fps. Each turn is rendered as its own segment (slide still + the active speaker's clip + a still of the idle speaker), then the segments are concatenated with the concat *filter* (full re-encode, no AAC clicks). The AI still chooses `slide_idx` per turn.

**`split_screen_with_slides` (default)**

| Zone | Rect (x, y, w, h) | Content |
|---|---|---|
| Interviewer tile | 0, 0, 560, 360 | head-and-shoulders crop; active = live clip in a 4 px clay (`#B8461E`) frame, idle = first-frame still dimmed to ~55 % |
| Expert tile | 1360, 0, 560, 360 | same for the expert |
| Label zone | 560, 0, 800, 96 | "Name / Role" next to each tile; active speaker larger with a clay accent bar, idle muted |
| Caption zone | 560, 96, 800, 264 | karaoke captions (ASS `\k`), `\an5\pos(960,228)`, wrapped with `\N` to ≤ 40 chars (≈ 760 px) and ≤ 3 lines per event; MarginL/R = 580 so text never leaves the zone |
| Slide | 320, 360, 1280, 720 | `scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2` — never stretched or cropped (4:3 / portrait slides are pillar-boxed) |
| Gutters | 0..320 and 1600..1920 below the tiles | background `#0B1220`; "n / N" slide counter in the right gutter |

**`split_screen_only`** — two 960x900 tiles at (0,0) and (960,0), "Name · Role" labels at y 900..960, captions (≤ 2 lines) at y 960..1080.

**Avatar framing.** Per tile: `chromakey/despill` (only if *that* speaker's clip is a green-screen photo avatar) → `crop` (normalized rect, even pixels) → `scale` to the tile (decrease) → `pad` (bottom-aligned, transparent) → `format=yuva420p` → `overlay`. The chroma flag is resolved per speaker from its own clips, so the idle still never inherits the active clip's flag. VP9 WebM clips are decoded with `libvpx-vp9` so their alpha channel survives. The crop rect comes from `avatar_registry` (`AvatarEntry.podcast_crop`, normalized `[x, y, w, h]`; custom avatars may set `"podcast_crop"` in `CUSTOM_AVATARS_JSON`) with kind fallbacks: prebuilt 16:9 avatars `(0.31, 0.02, 0.38, 0.43)`, photo avatars `(0.06, 0.0, 0.88, 1.0)`; Lisa is tuned to `(0.355, 0.05, 0.306, 0.35)`.

**Slides.** PPTX slides are rendered with the same LibreOffice binary as Decks (`LIBREOFFICE_PATH`, passed through `ingest_file`); `Document.slide_images` stays index-aligned with the slides and a missing image falls back to a 1280x720 title card (a warning is logged). Intro/outro cards stay full-frame.

- **MP3 output:** `ffmpeg -i final.mp4 -vn -acodec libmp3lame -q:a 2 final.mp3`
- **SRT output:** iterate clips; for each, read actual duration via `ffprobe -v quiet -of csv=p=0 -show_entries format=duration` and accumulate. This avoids timing drift introduced by `loudnorm` or re-encoding.

---

## 4. Infrastructure

The podcast generator is deployed by the shared `infra/` Bicep templates (same Container App, Cosmos DB, Blob Storage and AI resources as the deck and video features). An isolated podcast-only resource group was considered in the original design and dropped to keep a single `azd up` deployment. The resource list below is the original design reference.

### 4.1 Resources

| Resource | Purpose | Notes |
|---|---|---|
| Azure OpenAI | GPT-4.1 + embeddings | New deployment; capacity: 50K TPM to start |
| Azure AI Services (Speech) | Batch Avatar Synthesis + TTS | Must be in a region that supports batch synthesis with DragonHD voices (westeurope ✓) |
| Storage Account | Blob: `podcasts/{job_id}/clips/*.mp4`, `podcasts/{job_id}/final.{mp4,mp3,srt}` | Lifecycle: delete after 30 days |
| Cosmos DB (Serverless) | `podcasts` DB, containers: `documents`, `scripts`, `jobs` | Serverless keeps cost tied to usage |
| Container App (web) | API + UI | Reuses root `Dockerfile`; no ffmpeg needed here |
| **Container Apps Job** (new) | Dedicated render worker | Separate image with ffmpeg added; triggered by queue message (Cosmos change feed or Service Bus). Keeps web app responsive; survives crashes via worker restart + idempotent state. |
| ACR | Images for web + worker | Shared |
| Log Analytics | Diagnostics | Shared workspace |

All resources are tagged with the `azd` environment name so they can be found and torn down together.

### 4.2 RBAC

Managed identities on **both** the web Container App and the worker Job need the same roles (since both call Cosmos + Blob; worker additionally calls Speech batch):
- `Cognitive Services OpenAI User` on the OpenAI account (web only)
- `Cognitive Services User` on the AI Services account (worker — batch synthesis REST)
- `Cognitive Services Speech User` on the AI Services account (worker)
- `Storage Blob Data Contributor` on the storage account (both — worker uploads clips; web mints user-delegation SAS for downloads)
- `Cosmos DB Built-in Data Contributor` on the Cosmos account (both; assigned via CLI post-deploy — not ARM-native)

We **download Speech batch output via the signed URL it returns** and re-upload to our own blob, so we don't need a `destinationContainerUrl` path or cross-resource SAS tokens.

---

## 5. Frontend changes

### 5.1 Routing
Install `react-router-dom@7`. Wrap App in `<BrowserRouter>`. Routes:
- `/` → existing single-avatar presenter
- `/podcast` → new `PodcastPage`

Shared top nav with two tabs.

### 5.2 New components
```
src/pages/PodcastPage.tsx
src/components/podcast/DocumentUploader.tsx   // multi-file + URL
src/components/podcast/InstructionsPanel.tsx  // style, length, language, turns
src/components/podcast/RoleConfig.tsx         // avatar/voice pickers x2
src/components/podcast/ScriptEditor.tsx       // two-column dialogue editor
src/components/podcast/RenderControls.tsx     // start render + layout toggle
src/components/podcast/JobStatus.tsx          // progress + final player
```

### 5.3 API client
`src/services/podcast.ts` — typed fetch wrappers for every endpoint.

---

## 6. Security & compliance

- **No secrets in code.** All Azure auth via `DefaultAzureCredential` (existing pattern in `services/avatar.py`).
- **SAS tokens**: minted on demand for video/audio/SRT/SCORM downloads; no long-lived public URLs.
- **Content filtering**: Azure OpenAI default content filter stays on; script output is shown in the editor so users can remove undesired content before render.
- **PII**: Documents uploaded are stored in blob (encrypted at rest) for the lifetime of the job; lifecycle rule deletes after 30 days.
- **Rate limits / abuse**: cap render to N turns per job (e.g. 16) and N jobs per user per day (e.g. 5) to control spend.

---

## 7. Cost model (rough, westeurope)

**Variable cost per 6-minute podcast** (~8 turns, ~1200 spoken words):
| Item | Estimate |
|---|---|
| GPT-4.1 script gen (~15K in + 3K out tokens, incl. chunk-reduce) | ~$0.05 |
| Batch Avatar Synthesis — DragonHD pre-built avatar | ~6 min × ~$0.36/min ≈ $2.16 |
| Blob storage + egress | ~$0.01 |
| Cosmos serverless RU | ~$0.01 |
| **Per-podcast total** | **~$2.25** |

**Fixed (standing) infra cost** for a podcast-only deployment:
| Item | Estimate |
|---|---|
| Container App (web) min-replicas=0 → scale-to-zero, so ~$0 idle | ~$0–5/mo |
| Container Apps Job (worker) — consumption; bills only while running | ~$0–3/mo for 200 jobs |
| Cosmos serverless | ~$2–5/mo |
| Storage (100 podcasts retained × ~200 MB) | ~$1/mo |
| Log Analytics ingest | ~$3–10/mo |
| ACR Basic | ~$5/mo |
| **Fixed total** | **~$15–30/mo (~$200–400/yr)** |

**Example volume (200 podcasts/year):**
- Variable: 200 × $2.25 ≈ **$450/yr**
- Fixed:   ~**$200–400/yr**
- **All-in: ~$650–850/yr**

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Batch Avatar Synthesis quota exhaustion | **Global render semaphore (Cosmos lease)** across worker fleet; one batch job per speaker (not per turn) reduces job count; expose remaining budget in `/voices` |
| ffmpeg missing from container | Added to **worker Dockerfile** (`demos/worker/Dockerfile`) only; web image unchanged. Worker startup smoke-checks `ffmpeg -version` and `ffprobe -version` |
| DragonHD voices not available in selected language | `/voices` endpoint validates per-language availability and falls back to best standard neural voice; UI shows a banner when falling back |
| Long render latency | Per-speaker batch jobs run in parallel; poll with exponential backoff; UI shows stage + clip-level progress |
| Cosmos partition hot-spots | Partition `/userId` spreads load across users; composite indexes `(userId ASC, createdAt DESC)` for listings |
| Audio loudness variance across clips | Single `loudnorm` pass during compose (I=-16 LUFS, TP=-1.5 dBTP, LRA=11) |
| SRT timing drift after loudnorm/re-encode | Timestamps derived from `ffprobe` on actual post-encode clips, not planned durations |
| Long-doc script generation blowing the context window | **Chunk → map-summarize → reduce → script** pipeline (implemented in `services/podcast_script.py` from v1); hard cap total input at 120K tokens |
| Crash / restart during render | Idempotent worker: per-clip manifest (remoteJobId, status, checksum) + idempotent compose step; any restart resumes without re-billing completed clips |
| Cancellation leaking remote billable jobs | Cancel path: DELETE active Speech batch jobs before marking `cancelled` |
| User edits script in dangerous ways (prompt injection via docs) | GPT-4.1 content filter + output schema enforcement (pydantic parse); reject invalid JSON; cap turns per script (16) and total text (8K chars) |

---

## 9. Testing plan

- **Unit**: pydantic schema round-trips, SRT time math, ffmpeg command builder.
- **Integration**: hit Azure OpenAI with a fixture doc → assert script JSON shape.
- **E2E smoke** (`tests/e2e_render.py`): upload a sample deck → generate → render 3-turn podcast → verify MP4/MP3/SRT exist and have non-zero duration. Gate deployment on this.
- **Cost guard**: track token/minute usage in Cosmos; assert smoke test stays under $0.50.

---

## 10. Delivery phases

**Current PoC:** backend router + services, frontend route, render pipeline, library, and Blob-backed MP4 / MP3 / SRT / SCORM deliverables.

**Next polish:** regenerate single turn, voice preview, and slide transitions.

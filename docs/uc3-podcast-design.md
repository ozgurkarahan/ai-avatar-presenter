# UC3 — Podcast-Style Dual-Avatar Video Generation — Design

**Status:** Draft v2 — incorporates rubber-duck critique (2026-04-17)
**Branch:** `feat/uc3-podcast-dual-avatar`
**RFI:** RFI — Acme AI Avatar Solution
**Inspiration:** NotebookLM "Audio Overview"

---

## 1. Goals & Non-Goals

### Goals
- Upload documents (PPTX, PDF, DOCX, TXT, URL) + optional instructions → get a **podcast-style video** with two distinct AI avatars having a conversation.
- Produce three deliverables per job: **MP4** (dual-avatar video), **MP3** (audio-only), **SRT transcript** with speaker labels and timestamps.
- Preserve per-speaker lip-sync quality by using **one batch job per `(avatar, voice)` pair** with multiple SSML inputs (one per turn of that speaker), yielding one clip per turn while minimizing remote-job overhead and quota pressure.
- Keep infrastructure isolated in its own resource group (`uc3-podcast-rg`) for easy teardown.
- Ship as a second page (`/podcast`) in the existing React app, sharing the backend and auth of UC1/UC2.

### Non-Goals (Phase 1)
- Real-time (streaming) dual-avatar conversations.
- SCORM packaging, background music, transitions — Phase 2.
- Custom (trained) avatars.
- Mixing languages within a single podcast.
- Teams embedding — reuse manifest later if needed.

---

## 2. User Flow

1. User navigates to `/podcast`.
2. Uploads one or more documents (drag/drop) and/or pastes a URL.
3. (Optional) Enters instructions: topic focus, conversation style (casual/formal/debate), target length (short ~3 min / medium ~6 min / long ~10 min), target language, number of turns.
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
DELETE /api/podcast/jobs/{job_id}        → Cancel/delete
GET    /api/podcast/voices               → Available voices per language (subset of UC1 list)
GET    /api/podcast/avatars              → Available pre-built avatars (harry, lisa, …)
```

### 3.2 New services

| Module | Responsibility |
|---|---|
| `services/podcast_ingest.py` | Multi-format parsing: PPTX (reuse `pptx_parser`), PDF (`pypdf`), DOCX (`python-docx`), TXT/MD (plain), URL (`httpx` + `readability-lxml`). Returns normalized `Document`. |
| `services/podcast_script.py` | GPT-4.1 structured output. Prompt builds context from `Document`, respects style / length / language. Returns `Script` (list of `DialogueTurn`). |
| `services/podcast_render.py` | Orchestrator. Groups turns by speaker; submits **one batch synthesis job per speaker** with per-turn SSML inputs; polls; downloads each clip to blob; maintains per-clip manifest (remote job id, status, attempt, blob url, duration). Designed for idempotent re-run. |
| `services/podcast_compose.py` | ffmpeg composition. **Phase 1: sequential full-frame concat** (one speaker fills the frame at a time, with a lower-third banner naming the speaker). Applies `loudnorm` audio normalization. Probes actual durations with `ffprobe` to build SRT. Emits MP4 + MP3 + SRT. |

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
  "layout": "sequential",          // Phase 1: only "sequential" is supported
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
  "outputs": { "mp4Blob": "…", "mp3Blob": "…", "srtBlob": "…" },
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

Ingestion + scripting are synchronous REST endpoints (no job row); if their outputs take longer than the request budget we move them to the same worker pattern in Phase 3.

### 3.5 Composition algorithm (Phase 1 = sequential only)

Azure Batch Avatar Synthesis returns one MP4 per clip. Phase 1 renders the active speaker full-frame; a lower-third banner names them. No split-screen in Phase 1 (deferred to Phase 3; it requires transparent-background outputs — WebM/VP9 — and an idle-state visual for the silent avatar).

```
ffmpeg \
  -i turn0.mp4 -i turn1.mp4 … -i turnN.mp4 \
  -filter_complex "\
    [0:v]drawtext=text='Interviewer':…[v0]; \
    [1:v]drawtext=text='Expert':…[v1]; \
    … \
    [v0][0:a][v1][1:a]…concat=n=N+1:v=1:a=1[vout][aout_raw]; \
    [aout_raw]loudnorm=I=-16:TP=-1.5:LRA=11[aout]" \
  -map [vout] -map [aout] -c:v libx264 -c:a aac final.mp4
```

- **MP3 output:** `ffmpeg -i final.mp4 -vn -acodec libmp3lame -q:a 2 final.mp3`
- **SRT output:** iterate clips; for each, read actual duration via `ffprobe -v quiet -of csv=p=0 -show_entries format=duration` and accumulate. This avoids timing drift introduced by `loudnorm` or re-encoding.

---

## 4. Infrastructure (`infra/uc3/`)

New isolated resource group `uc3-podcast-rg` in **westeurope** (matches existing Speech resource region per stored memory).

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

All resources tagged: `project=ai-presenter-uc3`, `SecurityControl=ignore`, `CostControl=ignore` (per MCAPS memo).

### 4.2 RBAC

Managed identities on **both** the web Container App and the worker Job need the same roles (since both call Cosmos + Blob; worker additionally calls Speech batch):
- `Cognitive Services OpenAI User` on the OpenAI account (web only)
- `Cognitive Services User` on the AI Services account (worker — batch synthesis REST)
- `Cognitive Services Speech User` on the AI Services account (worker)
- `Storage Blob Data Contributor` on the storage account (both — worker uploads clips; web mints user-delegation SAS for downloads)
- `Cosmos DB Built-in Data Contributor` on the Cosmos account (both; assigned via CLI post-deploy — not ARM-native)

We **download Speech batch output via the signed URL it returns** and re-upload to our own blob, so we don't need a `destinationContainerUrl` path or cross-resource SAS tokens.

### 4.3 Bicep structure
Mirror existing `infra/` layout but scoped to the new RG:
```
infra/uc3/
  main.bicep              # targetScope = 'subscription', creates RG + modules
  main.parameters.json
  modules/
    openai.bicep
    ai-services.bicep
    storage.bicep
    cosmos.bicep           # database + 3 containers (documents, scripts, jobs), all PK /userId
    containerapp.bicep     # web app (existing image)
    containerjob.bicep     # NEW — render worker with ffmpeg
    roles.bicep            # RBAC for both identities
```

Outputs are written to `.env.uc3` by the deploy script so the backend can target either UC1/UC2 or UC3 resources via an env switch.

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
- **SAS tokens**: minted on demand with 1-hour expiry for video/audio/SRT downloads; no long-lived public URLs.
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

**Fixed (standing) infra cost** for isolated `uc3-podcast-rg`:
| Item | Estimate |
|---|---|
| Container App (web) min-replicas=0 → scale-to-zero, so ~$0 idle | ~$0–5/mo |
| Container Apps Job (worker) — consumption; bills only while running | ~$0–3/mo for 200 jobs |
| Cosmos serverless | ~$2–5/mo |
| Storage (100 podcasts retained × ~200 MB) | ~$1/mo |
| Log Analytics ingest | ~$3–10/mo |
| ACR Basic | ~$5/mo |
| **Fixed total** | **~$15–30/mo (~$200–400/yr)** |

**Acme volume (200 podcasts/year):**
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
- **E2E smoke** (`scripts/uc3_smoke.py`): upload sample PDF → generate → render 3-turn podcast → verify MP4/MP3/SRT exist and have non-zero duration. Gate deployment on this.
- **Cost guard**: track token/minute usage in Cosmos; assert smoke test stays under $0.50.

---

## 10. Delivery phases

**Phase 1 (current — design only):** this doc + plan.md + rubber-duck review + Bicep drafts. No deploy.

**Phase 2 (MVP implementation, on approval):** backend router + services + frontend route + minimal UI. Deploy Bicep. End-to-end smoke.

**Phase 3 (polish):** split-screen / PiP layout (requires transparent-bg WebM/VP9 output from Speech), regenerate single turn, voice preview, SCORM packaging (the RFI marks it "optional LMS-ready package", so it stays deferred), background music / transitions.

// Typed API client for the UC2 /api/static-video/* endpoints.
// Slide-first script model (one narration per slide, NOT turn-based).

export type JobState = 'queued' | 'rendering' | 'composing' | 'done' | 'failed' | 'cancelled';

export interface SlideInfo {
  index: number;
  image_ref: string;
  title: string;
  preview_text: string;
}

export interface IngestResponse {
  doc_id: string;
  slides: SlideInfo[];
  /** Original upload filename — preserved so UI never shows the uuid. */
  filename?: string;
  title?: string;
}

export interface SlideNarration {
  slide_index: number;
  slide_image_ref: string;
  title: string;
  narration: string;
  voice: string;
  speaking_style?: string | null;
  duration_hint_s?: number | null;
}

export interface StaticScript {
  doc_id: string;
  language: string;
  voice: string;
  narrations: SlideNarration[];
  title?: string;
  filename?: string;
}

export interface VoiceOption {
  id: string;
  name: string;
  gender: 'male' | 'female' | 'neutral';
  styles: string[];
}

export interface LanguageOption {
  code: string;
  label: string;
  voices_count: number;
}

export interface JobProgress {
  state: JobState;
  percent: number;
  stage: string;
  message: string;
}

export interface LibrarySummary {
  job_id: string;
  title: string;
  language: string;
  created_at: string;
  thumb_url: string | null;
  duration_s: number | null;
  slide_count: number;
}

export interface LibraryItem extends LibrarySummary {
  video_url: string | null;
  audio_url: string | null;
  srt_url: string | null;
}

export interface ScriptRequest {
  language: string;
  style?: string;
  focus?: string;
  voice: string;
}

const API = '/api/static-video';

// ---- Ingest ----------------------------------------------------------------
export async function ingestFile(file: File): Promise<IngestResponse> {
  const fd = new FormData();
  fd.append('file', file);
  // Preserve the original filename (lesson from UC3: never show uuid as title).
  fd.append('filename', file.name);
  const r = await fetch(`${API}/ingest`, { method: 'POST', body: fd });
  if (!r.ok) throw new Error(await safeText(r));
  const data = await r.json();
  return { filename: file.name, title: stripExt(file.name), ...data };
}

// ---- Script streaming (NDJSON) ---------------------------------------------
export async function streamScript(
  docId: string,
  req: ScriptRequest,
  onItem: (n: SlideNarration) => void,
  onDone: () => void,
  onError: (m: string) => void,
): Promise<() => void> {
  const ctrl = new AbortController();
  (async () => {
    try {
      const r = await fetch(`${API}/script/${docId}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(req),
        signal: ctrl.signal,
      });
      if (!r.ok || !r.body) throw new Error(await safeText(r));
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          try {
            const obj = JSON.parse(line);
            if (obj && typeof obj.slide_index === 'number') {
              onItem(obj as SlideNarration);
            }
          } catch { /* ignore malformed */ }
        }
      }
      if (buf.trim()) {
        try {
          const obj = JSON.parse(buf.trim());
          if (obj && typeof obj.slide_index === 'number') onItem(obj as SlideNarration);
        } catch { /* ignore */ }
      }
      onDone();
    } catch (e: any) {
      if (e?.name !== 'AbortError') onError(String(e?.message ?? e));
    }
  })();
  return () => ctrl.abort();
}

export async function getScript(docId: string): Promise<StaticScript> {
  const r = await fetch(`${API}/script/${docId}`);
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export interface NarrationPatch {
  slide_index: number;
  narration?: string;
  speaking_style?: string;
  voice?: string;
}

export async function patchScript(docId: string, patches: NarrationPatch[]): Promise<StaticScript> {
  const r = await fetch(`${API}/script/${docId}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ patches }),
  });
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

// ---- Render / Job ----------------------------------------------------------
export async function startRender(docId: string): Promise<{ job_id: string }> {
  const r = await fetch(`${API}/render/${docId}`, { method: 'POST' });
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export async function getJob(jobId: string): Promise<JobProgress> {
  const r = await fetch(`${API}/jobs/${jobId}`);
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

// ---- Library ---------------------------------------------------------------
export async function listLibrary(): Promise<LibrarySummary[]> {
  const r = await fetch(`${API}/library`);
  if (!r.ok) throw new Error(await safeText(r));
  const data = await r.json();
  return Array.isArray(data) ? data : (data.items ?? []);
}

export async function getLibraryItem(jobId: string): Promise<LibraryItem> {
  const r = await fetch(`${API}/library/${jobId}`);
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export async function deleteLibraryItem(jobId: string): Promise<void> {
  const r = await fetch(`${API}/library/${jobId}`, { method: 'DELETE' });
  if (!r.ok && r.status !== 204) throw new Error(await safeText(r));
}

// ---- Voices / Languages ----------------------------------------------------
export async function listVoices(language?: string): Promise<VoiceOption[]> {
  const q = language ? `?language=${encodeURIComponent(language)}` : '';
  const r = await fetch(`${API}/voices${q}`);
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export async function listLanguages(): Promise<LanguageOption[]> {
  const r = await fetch(`${API}/languages`);
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

// ---- helpers ---------------------------------------------------------------
async function safeText(r: Response): Promise<string> {
  try { return await r.text(); } catch { return `HTTP ${r.status}`; }
}

function stripExt(name: string): string {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(0, i) : name;
}

export const DRAGONHD_LANGUAGES: { code: string; label: string }[] = [
  { code: 'en-US', label: '🇬🇧 English (US)' },
  { code: 'fr-FR', label: '🇫🇷 Français' },
  { code: 'es-ES', label: '🇪🇸 Español' },
  { code: 'de-DE', label: '🇩🇪 Deutsch' },
  { code: 'it-IT', label: '🇮🇹 Italiano' },
  { code: 'pt-BR', label: '🇧🇷 Português (Brasil)' },
  { code: 'zh-CN', label: '🇨🇳 中文 (简体)' },
  { code: 'ja-JP', label: '🇯🇵 日本語' },
];

/** Fallback DragonHD voice id per language (used when /voices fails). */
export const DEFAULT_VOICE_BY_LANG: Record<string, string> = {
  'en-US': 'en-US-Ava:DragonHDLatestNeural',
  'fr-FR': 'fr-FR-VivienneMultilingualNeural',
  'es-ES': 'es-ES-XimenaMultilingualNeural',
  'de-DE': 'de-DE-SeraphinaMultilingualNeural',
  'it-IT': 'it-IT-IsabellaMultilingualNeural',
  'pt-BR': 'pt-BR-ThalitaMultilingualNeural',
  'zh-CN': 'zh-CN-XiaoxiaoMultilingualNeural',
  'ja-JP': 'ja-JP-MasaruMultilingualNeural',
};

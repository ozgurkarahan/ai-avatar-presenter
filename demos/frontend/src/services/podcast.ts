// Typed API client for the UC3 /api/podcast/* endpoints.

export type SourceKind = 'pptx' | 'pdf' | 'docx' | 'txt' | 'md' | 'url';
export type Speaker = 'interviewer' | 'expert';
export type Style = 'casual' | 'formal' | 'debate' | 'explainer';
export type Length = 'short' | 'medium' | 'long';
export type Layout = 'split_screen_with_slides' | 'split_screen_only';
export type JobState = 'queued' | 'rendering' | 'composing' | 'done' | 'failed' | 'cancelled';

export interface Section { heading: string; text: string; }
export interface Document {
  id: string;
  title: string;
  source_kind: SourceKind;
  sections: Section[];
  slide_images: string[];
  slide_titles: string[];
  slide_notes: string[];
}

export interface WordTiming { word: string; start_sec: number; end_sec: number; }

export interface DialogueTurn {
  idx: number;
  speaker: Speaker;
  text: string;
  slide_idx: number | null;
  word_timings: WordTiming[];
}

export interface Script {
  id: string;
  document_id: string;
  language: string;
  style: Style;
  length: Length;
  turns: DialogueTurn[];
}

export interface VoiceOption {
  id: string; display_name: string; language: string;
  gender: 'male' | 'female' | 'neutral'; hd: boolean; style_list: string[];
}
export interface AvatarOption {
  id: string; display_name: string; default_style: string; thumbnail_url: string;
}

export interface RoleConfig { display_name: string; avatar: string; voice: string; }
export interface RenderRoles { interviewer: RoleConfig; expert: RoleConfig; }

export interface RenderRequest {
  script_id: string;
  roles: RenderRoles;
  layout: Layout;
  music: boolean;
  intro: boolean;
  background_image?: string | null;
}

export interface JobProgress { stage: string; completed: number; total: number; message: string; }
export interface JobOutputs { mp4_url?: string; mp3_url?: string; srt_url?: string; duration_sec?: number; }
export type ArchiveState = 'none' | 'archiving' | 'published' | 'failed';
export interface PodcastJob {
  id: string; script_id: string; roles: RenderRoles; layout: Layout;
  music: boolean; intro: boolean; state: JobState;
  progress: JobProgress; outputs: JobOutputs;
  error: string | null; created_at: string; updated_at: string;
  archive_state?: ArchiveState;
  library_job_id?: string | null;
}

// ---- Library ----------------------------------------------------------
export interface LibrarySummary {
  job_id: string;
  title: string;
  document_title: string;
  created_at: string;
  duration_sec: number | null;
  language: string;
  style: string;
  speaker_names: string[];
  turn_count: number;
  thumbnail_url: string | null;
}
export interface LibraryItem extends LibrarySummary {
  mp4_url: string | null;
  mp3_url: string | null;
  srt_url: string | null;
  scorm_url: string | null;
}

const API = '/api/podcast';

export async function listAvatars(): Promise<AvatarOption[]> {
  const r = await fetch(`${API}/avatars`); if (!r.ok) throw new Error('avatars'); return r.json();
}
export async function listVoices(language?: string): Promise<VoiceOption[]> {
  const q = language ? `?language=${encodeURIComponent(language)}` : '';
  const r = await fetch(`${API}/voices${q}`); if (!r.ok) throw new Error('voices'); return r.json();
}

export async function ingestFile(file: File): Promise<Document> {
  const fd = new FormData(); fd.append('file', file);
  const r = await fetch(`${API}/ingest`, { method: 'POST', body: fd });
  if (!r.ok) throw new Error(await r.text()); return (await r.json()).document;
}
export async function ingestUrl(url: string): Promise<Document> {
  const fd = new FormData(); fd.append('url', url);
  const r = await fetch(`${API}/ingest`, { method: 'POST', body: fd });
  if (!r.ok) throw new Error(await r.text()); return (await r.json()).document;
}

export interface ScriptRequest {
  document_id: string; language?: string; style?: Style; length?: Length;
  num_turns?: number; focus?: string;
}

export async function streamScript(req: ScriptRequest,
  onTurn: (t: DialogueTurn) => void,
  onDone: (scriptId: string) => void,
  onError: (m: string) => void,
): Promise<() => void> {
  const ctrl = new AbortController();
  (async () => {
    try {
      const r = await fetch(`${API}/script/stream`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(req),
        signal: ctrl.signal,
      });
      if (!r.ok || !r.body) throw new Error(await r.text());
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i: number;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
          const lines = chunk.split('\n');
          let ev = 'message', data = '';
          for (const l of lines) {
            if (l.startsWith('event:')) ev = l.slice(6).trim();
            else if (l.startsWith('data:')) data += l.slice(5).trim();
          }
          if (!data) continue;
          try {
            const parsed = JSON.parse(data);
            if (ev === 'turn') onTurn(parsed);
            else if (ev === 'done') onDone(parsed.script_id);
            else if (ev === 'error') onError(parsed.message);
          } catch { /* ignore */ }
        }
      }
    } catch (e: any) { if (e.name !== 'AbortError') onError(String(e)); }
  })();
  return () => ctrl.abort();
}

export async function getScript(id: string): Promise<Script> {
  const r = await fetch(`${API}/scripts/${id}`); if (!r.ok) throw new Error('script');
  return r.json();
}
export async function patchScript(id: string, turns: DialogueTurn[]): Promise<Script> {
  const r = await fetch(`${API}/scripts/${id}`, {
    method: 'PATCH', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ turns }),
  });
  if (!r.ok) throw new Error(await r.text()); return r.json();
}

export async function startRender(req: RenderRequest): Promise<PodcastJob> {
  const r = await fetch(`${API}/render`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!r.ok) throw new Error(await r.text()); return r.json();
}

export async function getJob(id: string): Promise<PodcastJob> {
  const r = await fetch(`${API}/jobs/${id}`); if (!r.ok) throw new Error('job');
  return r.json();
}

// ---- Library ----------------------------------------------------------
export async function listLibrary(): Promise<LibrarySummary[]> {
  const r = await fetch(`${API}/library`);
  if (!r.ok) throw new Error('library');
  return r.json();
}
export async function getLibraryItem(jobId: string): Promise<LibraryItem> {
  const r = await fetch(`${API}/library/${jobId}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
export async function deleteLibraryItem(jobId: string): Promise<void> {
  const r = await fetch(`${API}/library/${jobId}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(await r.text());
}

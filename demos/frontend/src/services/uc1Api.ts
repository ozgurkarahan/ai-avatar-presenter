// Typed API client for UC1 Learning Hub endpoints (/api/uc1/*).
import type { Slide } from './api';

export type SlideInfo = Slide;

export interface Deck {
  deck_id: string;
  title: string;
  slide_count: number;
  language: string;
  uploaded_at: string;
  tags: string[];
}

export interface DeckDetail extends Deck {
  id: string;
  filename: string;
  slides: SlideInfo[];
}

export interface SearchResult {
  deck_id: string;
  deck_title: string;
  slide_index: number;
  slide_title: string;
  snippet: string;
  score: number;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface UploadDeckResponse {
  deck_id: string;
  title: string;
  slide_count: number;
}

const API = '/api/uc1';

async function safeText(r: Response): Promise<string> {
  try { return await r.text(); } catch { return `HTTP ${r.status}`; }
}

export async function uploadDeck(file: File): Promise<UploadDeckResponse> {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(`${API}/upload`, { method: 'POST', body: fd });
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export async function listDecks(): Promise<Deck[]> {
  const r = await fetch(`${API}/decks`);
  if (!r.ok) throw new Error(await safeText(r));
  const data = await r.json();
  return Array.isArray(data) ? data : (data.items ?? []);
}

export async function getDeck(deckId: string): Promise<DeckDetail> {
  const r = await fetch(`${API}/decks/${deckId}`);
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export async function deleteDeck(deckId: string): Promise<void> {
  const r = await fetch(`${API}/decks/${deckId}`, { method: 'DELETE' });
  if (!r.ok && r.status !== 204) throw new Error(await safeText(r));
}

export async function searchDecks(query: string, topK = 5): Promise<SearchResponse> {
  const r = await fetch(`${API}/learn/search`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ query, top_k: topK }),
  });
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

// ---- Voice / Avatar static catalogs ---------------------------------------
// Mirrors demos/backend/routers/static_video.py VOICES.
export interface Uc1Voice {
  id: string;
  display_name: string;
  language: string;
  gender: 'male' | 'female';
}

export const UC1_VOICES: Uc1Voice[] = [
  { id: 'en-US-Andrew:DragonHDLatestNeural',    display_name: 'Andrew (HD)',          language: 'en-US', gender: 'male' },
  { id: 'en-US-Ava:DragonHDLatestNeural',       display_name: 'Ava (HD)',             language: 'en-US', gender: 'female' },
  { id: 'fr-FR-Remy:DragonHDLatestNeural',      display_name: 'Rémy (HD)',            language: 'fr-FR', gender: 'male' },
  { id: 'fr-FR-Vivienne:DragonHDLatestNeural',  display_name: 'Vivienne (HD)',        language: 'fr-FR', gender: 'female' },
  { id: 'es-ES-Tristan:DragonHDLatestNeural',   display_name: 'Tristán (HD)',         language: 'es-ES', gender: 'male' },
  { id: 'es-ES-Ximena:DragonHDLatestNeural',    display_name: 'Ximena (HD)',          language: 'es-ES', gender: 'female' },
  { id: 'de-DE-Florian:DragonHDLatestNeural',   display_name: 'Florian (HD)',         language: 'de-DE', gender: 'male' },
  { id: 'de-DE-Seraphina:DragonHDLatestNeural', display_name: 'Seraphina (HD)',       language: 'de-DE', gender: 'female' },
  { id: 'it-IT-Alessio:DragonHDLatestNeural',   display_name: 'Alessio (HD)',         language: 'it-IT', gender: 'male' },
  { id: 'it-IT-Isabella:DragonHDLatestNeural',  display_name: 'Isabella (HD)',        language: 'it-IT', gender: 'female' },
  { id: 'pt-BR-Macerio:DragonHDLatestNeural',   display_name: 'Macério (HD)',         language: 'pt-BR', gender: 'male' },
  { id: 'pt-BR-Thalita:DragonHDLatestNeural',   display_name: 'Thalita (HD)',         language: 'pt-BR', gender: 'female' },
  { id: 'zh-CN-Xiaochen:DragonHDLatestNeural',  display_name: '晓辰 Xiaochen (HD)',   language: 'zh-CN', gender: 'female' },
  { id: 'zh-CN-Yunfan:DragonHDLatestNeural',    display_name: '云帆 Yunfan (HD)',     language: 'zh-CN', gender: 'male' },
  { id: 'ja-JP-Masaru:DragonHDLatestNeural',    display_name: 'Masaru (HD)',          language: 'ja-JP', gender: 'male' },
  { id: 'ja-JP-Nanami:DragonHDLatestNeural',    display_name: 'Nanami (HD)',          language: 'ja-JP', gender: 'female' },
];

export const UC1_LANGUAGE_LABELS: Record<string, string> = {
  'en-US': '🇬🇧 English (US)',
  'fr-FR': '🇫🇷 Français',
  'es-ES': '🇪🇸 Español',
  'de-DE': '🇩🇪 Deutsch',
  'it-IT': '🇮🇹 Italiano',
  'pt-BR': '🇧🇷 Português (Brasil)',
  'zh-CN': '🇨🇳 中文 (简体)',
  'ja-JP': '🇯🇵 日本語',
};

const MALE_VOICE_NAMES = ['Andrew', 'Remy', 'Tristan', 'Florian', 'Alessio', 'Macerio', 'Yunfan', 'Masaru'];
const FEMALE_VOICE_NAMES = ['Ava', 'Vivienne', 'Ximena', 'Seraphina', 'Isabella', 'Thalita', 'Xiaochen', 'Nanami'];

/** Suggest an avatar matching the voice gender.
 *
 * DEPRECATED (H1 2026-04-24): the UC2 render backend no longer auto-
 * overrides the user-selected avatar based on voice gender, because
 * that silently ignored the UI choice. Kept here only for legacy
 * callers that still invoke it; new code should trust the user's
 * explicit avatar pick.
 */
export function avatarForVoice(voice: string, fallback = 'harry'): string {
  if (!voice) return fallback;
  if (MALE_VOICE_NAMES.some((n) => voice.includes(n))) return 'harry';
  if (FEMALE_VOICE_NAMES.some((n) => voice.includes(n))) return 'max';
  return fallback;
}

export const UC1_AVATARS: { id: string; label: string; style: string }[] = [
  { id: 'harry', label: 'Harry (youthful)',      style: 'youthful' },
  { id: 'max',   label: 'Max (business)',        style: 'business' },
  { id: 'meg',   label: 'Meg (business)',        style: 'business' },
  { id: 'lisa',  label: 'Lisa (casual-sitting)', style: 'casual-sitting' },
];

export function styleForAvatar(avatarId: string): string {
  return UC1_AVATARS.find((a) => a.id === avatarId)?.style ?? 'youthful';
}


// ======================= UC1 Learning Paths ===============================
export interface PathStep {
  order: number;
  deck_id: string;
  deck_title: string;
  slide_count: number;
  required: boolean;
}

export interface PathSummary {
  id: string;
  title: string;
  description: string;
  status: 'active' | 'broken';
  step_count: number;
  created_at: string;
  updated_at: string;
}

export interface PathDetail extends PathSummary {
  steps: PathStep[];
}

export interface PathStepInput {
  deck_id: string;
  order: number;
  required?: boolean;
}

export interface PathCreateInput {
  title: string;
  description?: string;
  steps: PathStepInput[];
}

export interface PathUpdateInput {
  title?: string;
  description?: string;
  steps?: PathStepInput[];
}

export interface PathProgress {
  user_id: string;
  path_id: string;
  last_deck_id: string;
  last_slide_index: number;
  resume_deck_id: string;
  resume_slide_index: number;
  completed_slides: Record<string, number[]>;
  total_slides: number;
  completed_count: number;
  percent: number;
  updated_at: string;
}

export interface ProgressPostInput {
  user_id: string;
  deck_id: string;
  slide_index: number;
  mark_completed?: boolean;
}

export async function listPaths(): Promise<PathSummary[]> {
  const r = await fetch(`${API}/paths`);
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export async function getPath(pathId: string): Promise<PathDetail> {
  const r = await fetch(`${API}/paths/${pathId}`);
  if (!r.ok) {
    const msg = await safeText(r);
    const err = new Error(msg) as Error & { status?: number };
    err.status = r.status;
    throw err;
  }
  return r.json();
}

export async function createPath(body: PathCreateInput): Promise<PathDetail> {
  const r = await fetch(`${API}/paths`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export async function updatePath(pathId: string, body: PathUpdateInput): Promise<PathDetail> {
  const r = await fetch(`${API}/paths/${pathId}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export async function deletePath(pathId: string): Promise<void> {
  const r = await fetch(`${API}/paths/${pathId}`, { method: 'DELETE' });
  if (!r.ok && r.status !== 204) throw new Error(await safeText(r));
}

export async function getProgress(pathId: string, userId: string): Promise<PathProgress> {
  const r = await fetch(`${API}/paths/${pathId}/progress?user_id=${encodeURIComponent(userId)}`);
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

export async function postProgress(pathId: string, body: ProgressPostInput): Promise<PathProgress> {
  const r = await fetch(`${API}/paths/${pathId}/progress`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await safeText(r));
  return r.json();
}

const USER_ID_KEY = 'uc1.userId';
export function getOrCreateUserId(): string {
  try {
    let id = localStorage.getItem(USER_ID_KEY);
    if (!id) {
      id = 'u_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
      localStorage.setItem(USER_ID_KEY, id);
    }
    return id;
  } catch {
    return 'anonymous';
  }
}


// ======================= AI Path Recommendation ===========================
export interface RecommendedStep {
  deck_id: string;
  deck_title: string;
  slide_count: number;
  order: number;
  rationale: string;
}

export interface RecommendResponse {
  title: string;
  description: string;
  steps: RecommendedStep[];
  explanation: string;
}

export async function recommendPath(
  topic: string,
  maxSteps = 4,
  language?: string,
): Promise<RecommendResponse> {
  const r = await fetch(`${API}/paths/recommend`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ topic, max_steps: maxSteps, language }),
  });
  if (!r.ok) {
    const msg = await safeText(r);
    const err = new Error(msg) as Error & { status?: number };
    err.status = r.status;
    throw err;
  }
  return r.json();
}

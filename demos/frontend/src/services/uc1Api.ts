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

/** Match avatar_for_voice() in demos/backend/services/static_render.py. */
export function avatarForVoice(voice: string, fallback = 'lisa'): string {
  if (!voice) return fallback;
  if (MALE_VOICE_NAMES.some((n) => voice.includes(n))) return 'harry';
  if (FEMALE_VOICE_NAMES.some((n) => voice.includes(n))) return 'lisa';
  return fallback;
}

export const UC1_AVATARS: { id: string; label: string; style: string }[] = [
  { id: 'lisa',  label: 'Lisa (casual-sitting)', style: 'casual-sitting' },
  { id: 'harry', label: 'Harry (business)',      style: 'business' },
  { id: 'meg',   label: 'Meg (formal)',          style: 'formal' },
  { id: 'max',   label: 'Max (casual)',          style: 'casual' },
];

export function styleForAvatar(avatarId: string): string {
  return UC1_AVATARS.find((a) => a.id === avatarId)?.style ?? 'casual-sitting';
}

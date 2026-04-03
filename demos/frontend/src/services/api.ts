const API_BASE = '/api';

export interface Slide {
  index: number;
  title: string;
  body: string;
  notes: string;
  image_url?: string;
  video_url?: string;
  translated_notes?: Record<string, string>;
}

export interface Presentation {
  id: string;
  filename: string;
  slide_count: number;
  pptx_url?: string;
  slides: Slide[];
}

export interface TranslateResponse {
  translated_text: string;
  source_language: string;
}

export interface IceServer {
  urls: string[];
  username: string;
  credential: string;
}

export interface AvatarToken {
  token: string;
  aad_token?: string;
  region: string;
  endpoint?: string;
  wss_url?: string;
  ice_servers?: IceServer | null;
  auth_type: 'key' | 'aad';
}

export interface QaResponse {
  answer: string;
  source_slides: number[];
}

export async function uploadPresentation(file: File): Promise<Presentation> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  return res.json();
}

export interface PresentationListItem {
  id: string;
  filename: string;
  slide_count: number;
}

export async function listPresentations(): Promise<PresentationListItem[]> {
  const res = await fetch(`${API_BASE}/presentations`);
  if (!res.ok) throw new Error(`Failed to list presentations: ${res.statusText}`);
  return res.json();
}

export async function getSlides(presentationId: string): Promise<Presentation> {
  const res = await fetch(`${API_BASE}/slides/${presentationId}`);
  if (!res.ok) throw new Error(`Failed to get slides: ${res.statusText}`);
  return res.json();
}

export async function deletePresentation(presentationId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/presentations/${presentationId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete presentation: ${res.statusText}`);
}

export async function sharePresentation(presentationId: string): Promise<{ status: string; message?: string }> {
  const res = await fetch(`${API_BASE}/presentations/${presentationId}/share`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to share presentation: ${res.statusText}`);
  return res.json();
}

export interface TranslatedSlide {
  index: number;
  translated_notes: string;
}

export interface TranslateNotesResponse {
  presentation_id: string;
  target_language: string;
  translated_slides: TranslatedSlide[];
  cached: boolean;
}

export async function translateNotes(presentationId: string, targetLanguage: string): Promise<TranslateNotesResponse> {
  const res = await fetch(`${API_BASE}/presentations/${presentationId}/translate-notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_language: targetLanguage }),
  });
  if (!res.ok) throw new Error(`Failed to pre-translate notes: ${res.statusText}`);
  return res.json();
}

export interface TranslationsStatus {
  total: number;
  completed: number;
  languages_done: string[];
  status: 'in_progress' | 'completed' | 'not_started' | 'unknown';
}

export async function getTranslationsStatus(presentationId: string): Promise<TranslationsStatus> {
  const res = await fetch(`${API_BASE}/presentations/${presentationId}/translations-status`);
  if (!res.ok) throw new Error(`Failed to get translations status: ${res.statusText}`);
  return res.json();
}

export async function translateText(text: string, targetLanguage: string): Promise<TranslateResponse> {
  const res = await fetch(`${API_BASE}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, target_language: targetLanguage }),
  });
  if (!res.ok) throw new Error(`Translation failed: ${res.statusText}`);
  return res.json();
}

export async function getAvatarToken(): Promise<AvatarToken> {
  const res = await fetch(`${API_BASE}/avatar/token`);
  if (!res.ok) throw new Error(`Failed to get avatar token: ${res.statusText}`);
  return res.json();
}

export async function askQuestion(
  presentationId: string,
  question: string,
  slideIndex?: number,
): Promise<QaResponse> {
  const res = await fetch(`${API_BASE}/qa`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      presentation_id: presentationId,
      question,
      slide_index: slideIndex,
    }),
  });
  if (!res.ok) throw new Error(`Q&A failed: ${res.statusText}`);
  return res.json();
}

export interface AgentChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AgentChatResponse {
  reply: string;
}

export async function agentChat(
  messages: AgentChatMessage[],
  presentationId?: string,
  slideIndex?: number,
): Promise<AgentChatResponse> {
  const res = await fetch(`${API_BASE}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages,
      presentation_id: presentationId,
      slide_index: slideIndex,
    }),
  });
  if (!res.ok) throw new Error(`Agent chat failed: ${res.statusText}`);
  return res.json();
}

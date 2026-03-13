const API_BASE = '/api';

export interface Slide {
  index: number;
  title: string;
  body: string;
  notes: string;
  image_url?: string;
}

export interface Presentation {
  id: string;
  filename: string;
  slide_count: number;
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

export async function getSlides(presentationId: string): Promise<Presentation> {
  const res = await fetch(`${API_BASE}/slides/${presentationId}`);
  if (!res.ok) throw new Error(`Failed to get slides: ${res.statusText}`);
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

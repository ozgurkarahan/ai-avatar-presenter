import type { Page, Route } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const AVATAR_DIR = path.join(__dirname, '..', '..', 'demos', 'backend', 'static', 'avatars');

// Shared /api mocks for the regression + screenshot specs (deterministic, no Azure).
export type Role = 'visitor' | 'admin';

const PNG_1PX = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64',
);

export const DECKS = [
  { deck_id: 'deck-live', title: 'climate-action', slide_count: 3, language: 'en-US', uploaded_at: '2026-10-14T21:51:41Z', tags: [], published: true, live_demo: true },
  { deck_id: 'deck-plain', title: 'ai-ethics', slide_count: 3, language: 'en-US', uploaded_at: '2026-10-14T21:51:46Z', tags: [], published: true, live_demo: false },
];

const deckDetail = (id: string) => {
  const d = DECKS.find((x) => x.deck_id === id) ?? DECKS[0];
  return {
    ...d,
    id: d.deck_id,
    filename: `${d.title}.pptx`,
    slides: [0, 1, 2].map((i) => ({ index: i, title: `Slide title ${i + 1}`, body: `Body ${i + 1}`, notes: `Notes ${i + 1}` })),
  };
};

const AVATARS = [
  { id: 'photo_female', display_name: 'Sofia', gender: 'female', thumbnail_url: '/static/avatars/photo_female.png', is_default: true },
  { id: 'photo_male', display_name: 'Lucas', gender: 'male', thumbnail_url: '/static/avatars/photo_male.png', is_default: false },
  { id: 'lisa', display_name: 'Lisa', gender: 'female', thumbnail_url: '', is_default: false },
];

const VIDEO_ITEM = {
  job_id: 'vid-1', title: 'low-carbon-materials', language: 'en-US', created_at: '2026-10-15T00:05:00Z',
  thumbnail_url: null, duration_sec: 98, slide_count: 6, published: true,
};
const PODCAST_ITEM = {
  job_id: 'pod-1', title: 'circular-economy', language: 'en-US', created_at: '2026-10-14T21:52:00Z',
  thumbnail_url: null, duration_sec: 114, speaker_names: ['Sofia', 'Lucas'], published: true,
};
const PLAYLIST = {
  id: 'pl-1', title: 'Security onboarding', description: 'Two decks', status: 'active', step_count: 2,
  created_at: '2026-10-14T00:00:00Z', updated_at: '2026-10-14T00:00:00Z',
};

export const calls: { method: string; path: string; body: string | null }[] = [];

export async function mockApi(page: Page, role: Role) {
  calls.length = 0;
  await page.route('**/static/avatars/**', (r) => {
    // Use the real (git-ignored) deployment avatars when present for realistic screenshots.
    const file = path.join(AVATAR_DIR, path.basename(new URL(r.request().url()).pathname));
    const body = fs.existsSync(file) ? fs.readFileSync(file) : PNG_1PX;
    return r.fulfill({ status: 200, contentType: 'image/png', body });
  });
  await page.route('**/media/**', (r) => r.fulfill({ status: 200, contentType: 'video/mp4', body: '' }));
  await page.route('**/api/**', async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname;
    const m = req.method();
    calls.push({ method: m, path: p, body: req.postData() });
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const admin = role === 'admin';

    if (p === '/api/me') return json({ authenticated: admin, is_admin: admin, name: admin ? 'Admin User' : null, auth_mode: 'easyauth' });
    if (p === '/api/demo/config') return json({ enabled: true, session_seconds: 180 });
    if (p === '/api/avatars') return json(AVATARS);
    if (p === '/api/decks' && m === 'GET') return json(DECKS);
    if (p === '/api/decks/upload' && m === 'POST') return admin ? json({ deck_id: 'deck-new', title: 'new', slide_count: 1 }) : json({ detail: 'forbidden' }, 403);
    const deckMatch = p.match(/^\/api\/decks\/([^/]+)$/);
    if (deckMatch && m === 'GET') return json(deckDetail(deckMatch[1]));
    if (p === '/api/search' && m === 'POST') {
      return json({ results: [{ deck_id: 'deck-plain', deck_title: 'ai-ethics', slide_index: 1, slide_title: 'Bias', snippet: 'Bias and fairness', score: 0.9 }] });
    }
    if (p === '/api/qa' && m === 'POST') return json({ answer: 'Mocked answer', source_slides: [1] });
    if (p === '/api/agent/chat' && m === 'POST') return json({ reply: 'Mocked reply' });
    if (p === '/api/video/library') return json([VIDEO_ITEM]);
    if (p === '/api/video/library/vid-1') return json({ ...VIDEO_ITEM, video_url: '/media/vid-1.mp4' });
    if (p === '/api/podcast/library') return json([PODCAST_ITEM]);
    if (p === '/api/podcast/library/pod-1') return json({ ...PODCAST_ITEM, mp4_url: '/media/pod-1.mp4', video_url: '/media/pod-1.mp4' });
    if (p === '/api/playlists' && m === 'GET') return json([PLAYLIST]);
    if (p === '/api/playlists/pl-1') {
      return json({ ...PLAYLIST, steps: [
        { order: 0, deck_id: 'deck-live', deck_title: 'climate-action', slide_count: 3, required: true },
        { order: 1, deck_id: 'deck-plain', deck_title: 'ai-ethics', slide_count: 3, required: true },
      ] });
    }
    if (p === '/api/playlists/pl-1/progress') {
      return json({ user_id: 'u', playlist_id: 'pl-1', last_deck_id: 'deck-live', last_slide_index: 0, resume_deck_id: 'deck-live',
        resume_slide_index: 0, completed_slides: {}, total_slides: 6, completed_count: 0, percent: 0, updated_at: '2026-10-14T00:00:00Z' });
    }
    if (p.endsWith('/languages')) return json([{ code: 'en-US', name: 'English' }, { code: 'fr-FR', name: 'Français' }]);
    if (m === 'GET') return json([]);
    return json({ detail: 'not mocked' }, 404);
  });
}


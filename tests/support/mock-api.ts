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
  { deck_id: 'deck-live', title: 'ai-fundamentals', slide_count: 3, language: 'en-US', uploaded_at: '2026-10-14T21:51:41Z', tags: [], published: true, live_demo: true },
  { deck_id: 'deck-plain', title: 'ai-ethics', slide_count: 3, language: 'en-US', uploaded_at: '2026-10-14T21:51:46Z', tags: [], published: true, live_demo: false },
];

// Cached FR translations of the speaker notes (admin payload only, like the backend).
export const FR_NOTES = ['Notes FR 1', 'Notes FR 2', 'Notes FR 3'];

const deckDetail = (id: string, admin: boolean) => {
  const d = DECKS.find((x) => x.deck_id === id) ?? DECKS[0];
  return {
    ...d,
    id: d.deck_id,
    filename: `${d.title}.pptx`,
    // Anonymous payload mirrors routers/decks.py PublicSlidePayload: no body, notes or translations.
    slides: [0, 1, 2].map((i) => (admin
      ? { index: i, title: `Slide title ${i + 1}`, body: `Body ${i + 1}`, notes: `Notes ${i + 1}`, translated_notes: { 'fr-FR': FR_NOTES[i] } }
      : { index: i, title: `Slide title ${i + 1}` })),
  };
};

const AVATARS = [
  { id: 'photo_female', display_name: 'Sofia', gender: 'female', thumbnail_url: '/static/avatars/photo_female.png', is_default: true },
  { id: 'photo_male', display_name: 'Lucas', gender: 'male', thumbnail_url: '/static/avatars/photo_male.png', is_default: false },
  { id: 'lisa', display_name: 'Lisa', gender: 'female', thumbnail_url: '', is_default: false },
];

const VIDEO_ITEM = {
  job_id: 'vid-1', title: 'context-engineering-rag', language: 'en-US', created_at: '2026-10-15T00:05:00Z',
  thumbnail_url: null, duration_sec: 98, slide_count: 6, published: true,
};
const PODCAST_ITEM = {
  job_id: 'pod-1', title: 'ai-agents-mcp', language: 'en-US', created_at: '2026-10-14T21:52:00Z',
  thumbnail_url: null, duration_sec: 114, speaker_names: ['Sofia', 'Lucas'], published: true,
};
const PLAYLIST = {
  id: 'pl-1', title: 'Security onboarding', description: 'Two decks', status: 'active', step_count: 2,
  created_at: '2026-10-14T00:00:00Z', updated_at: '2026-10-14T00:00:00Z',
};

export const calls: { method: string; path: string; body: string | null }[] = [];

export interface MockApiOptions {
  /** `qa` block of `/api/demo/config` (omitted → demo Q&A disabled, like the default server). */
  demoQa?: { enabled: boolean; max_questions: number; max_audio_seconds: number };
  demoSessionSeconds?: number;
}

export async function mockApi(page: Page, role: Role, opts: MockApiOptions = {}) {
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
    if (p === '/api/demo/config') {
      return json({ enabled: true, session_seconds: opts.demoSessionSeconds ?? 180, ...(opts.demoQa ? { qa: opts.demoQa } : {}) });
    }
    if (p === '/api/avatars') return json(AVATARS);
    if (p === '/api/decks' && m === 'GET') return json(DECKS);
    if (p === '/api/decks/upload' && m === 'POST') return admin ? json({ deck_id: 'deck-new', title: 'new', slide_count: 1 }) : json({ detail: 'forbidden' }, 403);
    const deckMatch = p.match(/^\/api\/decks\/([^/]+)$/);
    if (deckMatch && m === 'GET') return json(deckDetail(deckMatch[1], admin));
    const translateMatch = p.match(/^\/api\/decks\/([^/]+)\/translate-notes$/);
    if (translateMatch && m === 'POST') {
      if (!admin) return json({ detail: 'Sign-in required' }, 401);
      const lang = JSON.parse(req.postData() || '{}').target_language as string;
      return json({ deck_id: translateMatch[1], target_language: lang, cached: false,
        translated_notes: Object.fromEntries([0, 1, 2].map((i) => [String(i), `Notes ${lang} ${i + 1}`])) });
    }
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
        { order: 0, deck_id: 'deck-live', deck_title: 'ai-fundamentals', slide_count: 3, required: true },
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


// ── Fake Voice Live WebSocket (/ws/voice, /ws/voice/demo) ─────────────────
// Simulates the backend proxy: Voice Live response events (no WebRTC: the test
// drives the avatar data channel / audio levels through window.__deckfmTest)
// plus the qa.* / context.* / demo.* messages of the raise-hand contract.

export interface VoiceMockOptions {
  /** Reply to qa.begin: ready (default), a qa.error code, or qa.unavailable. */
  qaBegin?: 'ready' | 'limit' | 'time_low' | 'unavailable';
  remainingQuestions?: number;
  /** Demo: `demo.started` payload. */
  demoRemainingMs?: number;
  narrationChars?: number[];
  /** Emit word timestamps (enables the fallback completion path). */
  wordTimestamps?: boolean;
  answer?: { text: string; source_slides: number[]; grounded: boolean };
  transcript?: string;
}

export interface VoiceMock {
  /** Every client → server JSON message, in order. */
  sent: any[];
  /** Assistant item ids (= avatar turn ids) of every spoken response, in order. */
  items: string[];
  url: string | null;
  send(msg: object): void;
  close(code: number, reason?: string): void;
  ofType(type: string): any[];
}

export async function mockVoice(page: Page, opts: VoiceMockOptions = {}): Promise<VoiceMock> {
  const mock: VoiceMock = {
    sent: [], items: [], url: null,
    send: () => {},
    close: () => {},
    ofType(type) { return this.sent.filter((m) => m?.type === type); },
  };
  let n = 0;
  await page.routeWebSocket(/\/ws\/voice/, (ws) => {
    mock.url = ws.url();
    const demo = ws.url().includes('/ws/voice/demo');
    const send = (m: object) => ws.send(JSON.stringify(m));
    mock.send = send;
    mock.close = (code, reason) => { void ws.close({ code, reason }); };
    let remaining = opts.remainingQuestions ?? 2;
    const speakTurn = (chars: number) => {
      n += 1;
      const rid = `resp_${n}`;
      const iid = `item_${n}`;
      mock.items.push(iid);
      send({ type: 'response.created', response: { id: rid } });
      send({ type: 'response.output_item.added', response_id: rid, item: { id: iid, role: 'assistant' } });
      if (opts.wordTimestamps) {
        send({ type: 'response.audio_timestamp.delta', response_id: rid, item_id: iid, audio_offset_ms: 0, audio_duration_ms: Math.max(300, chars * 20), text: 'w', timestamp_type: 'word' });
      }
      // Generation finishes long before playback — the client must not treat this as completion.
      send({ type: 'response.done', response: { id: rid, status: 'completed' } });
    };
    send({ type: 'proxy.connected', message: 'Connected to Azure Voice API' });
    if (demo) {
      send({
        type: 'demo.started', session_seconds: 300, remaining_ms: opts.demoRemainingMs ?? 300000,
        ...(opts.narrationChars ? { narration_chars: opts.narrationChars } : {}),
      });
    }
    ws.onMessage((data) => {
      let msg: any;
      try { msg = JSON.parse(String(data)); } catch { return; }
      mock.sent.push(msg);
      const rid = msg.request_id;
      switch (msg.type) {
        case 'session.update':
          send({ type: 'session.updated', session: { id: 'sess_1' } });
          break;
        case 'response.create':
          speakTurn(40);
          break;
        case 'demo.speak':
          send({ type: 'demo.speaking', slide: msg.slide, chars: 130, remaining: 9, remaining_ms: opts.demoRemainingMs ?? 290000 });
          speakTurn(130);
          break;
        case 'context.switch':
          send({ type: 'context.switched', deck_id: msg.deck_id, slide_count: 3 });
          break;
        case 'qa.begin':
          if (opts.qaBegin === 'unavailable') { send({ type: 'qa.unavailable', reason: 'no_deck' }); break; }
          if (opts.qaBegin === 'limit' || opts.qaBegin === 'time_low') {
            send({ type: 'qa.error', request_id: rid, code: opts.qaBegin, message: opts.qaBegin === 'limit' ? 'No more questions in this demo.' : 'Not enough time left for a question.' });
            break;
          }
          remaining -= 1;
          send({ type: 'qa.ready', request_id: rid, max_audio_ms: 15000, max_audio_bytes: 480000, remaining_questions: remaining, ...(demo ? { remaining_ms: 200000 } : {}) });
          speakTurn(25);
          break;
        case 'qa.commit':
        case 'qa.text': {
          const text = msg.type === 'qa.text' ? msg.text : (opts.transcript ?? 'What drives the results?');
          send({ type: 'qa.transcript', request_id: rid, text });
          const a = opts.answer ?? { text: 'The deck says growth comes from new markets.', source_slides: [1], grounded: true };
          send({ type: 'qa.answer', request_id: rid, ...a });
          speakTurn(a.text.length);
          break;
        }
        default:
          break;
      }
    });
  });
  return mock;
}

/** Test hook helpers (window.__deckfmTest is only installed by the Vite dev build). */
export const avatar = {
  async connected(page: Page) {
    await page.waitForFunction(() => !!(window as any).__deckfmTest);
    await page.evaluate(() => (window as any).__deckfmTest.mediaConnected());
  },
  /** Plays a turn to its end: speech heard, TURN_START/TURN_END on the data channel, then silence. */
  async finishTurn(page: Page, itemId: string) {
    await page.evaluate((id) => {
      const t = (window as any).__deckfmTest;
      t.dataChannel({ event: { eventType: 'EVENT_TYPE_TURN_START', turnID: id } });
      t.audioLevel(-20);
      t.dataChannel({ event: { eventType: 'EVENT_TYPE_TURN_END', turnID: id } });
      t.audioLevel(-90);
    }, itemId);
  },
  async startTurn(page: Page, itemId: string) {
    await page.evaluate((id) => {
      const t = (window as any).__deckfmTest;
      t.dataChannel({ event: { eventType: 'EVENT_TYPE_TURN_START', turnID: id } });
      t.audioLevel(-20);
    }, itemId);
  },
};

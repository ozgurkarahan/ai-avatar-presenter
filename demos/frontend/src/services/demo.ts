// Public live-avatar demo (anonymous, narration-only).
// `GET /api/demo/config` tells the SPA whether the kill switch is on; the
// actual guardrails (deck allowlist, quotas, time cap) are enforced server-side.
import { useEffect, useState } from 'react';

export interface DemoQaConfig {
  enabled: boolean;
  max_questions: number;
  max_audio_seconds: number;
}

export interface DemoConfig {
  enabled: boolean;
  /** Effective session cap (larger when demo Q&A is on, per the server). */
  session_seconds: number;
  remaining_today?: number;
  qa: DemoQaConfig;
  loading: boolean;
}

const QA_OFF: DemoQaConfig = { enabled: false, max_questions: 0, max_audio_seconds: 15 };
const DISABLED: DemoConfig = { enabled: false, session_seconds: 180, qa: QA_OFF, loading: false };

function parseQa(raw: any): DemoQaConfig {
  if (!raw || raw.enabled !== true) return QA_OFF;
  const max = Number(raw.max_questions);
  const audio = Number(raw.max_audio_seconds);
  return {
    enabled: true,
    max_questions: Number.isFinite(max) && max > 0 ? Math.floor(max) : 0,
    max_audio_seconds: Number.isFinite(audio) && audio > 0 ? audio : 15,
  };
}

let cache: Promise<DemoConfig> | null = null;

export function loadDemoConfig(): Promise<DemoConfig> {
  if (!cache) {
    cache = fetch('/api/demo/config', { credentials: 'same-origin' })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        const seconds = Number(d?.session_seconds);
        return {
          enabled: d?.enabled === true,
          session_seconds: Number.isFinite(seconds) && seconds > 0 ? seconds : 180,
          remaining_today: typeof d?.remaining_today === 'number' ? d.remaining_today : undefined,
          qa: parseQa(d?.qa),
          loading: false,
        };
      })
      .catch((e) => {
        console.warn('[demo] /api/demo/config failed — demo disabled', e);
        cache = null;
        return DISABLED;
      });
  }
  return cache;
}

export function useDemoConfig(): DemoConfig {
  const [cfg, setCfg] = useState<DemoConfig>({ ...DISABLED, loading: true });
  useEffect(() => {
    let cancelled = false;
    loadDemoConfig().then((c) => { if (!cancelled) setCfg(c); });
    return () => { cancelled = true; };
  }, []);
  return cfg;
}

/** WebSocket close codes used by `/ws/voice/demo` → friendly visitor messages. */
export function demoCloseMessage(code: number, opened: boolean): string | null {
  switch (code) {
    case 1013: return 'The demo avatar is busy, try again in a minute';
    case 4429: return 'Daily demo limit reached — come back tomorrow';
    case 4408: return 'Demo time limit reached';
    case 4403: return 'Demo not available for this deck';
    default:
      // A refused handshake (pre-accept 4403) surfaces in browsers as 1006.
      if (!opened && code === 1006) return 'Demo not available for this deck';
      return null;
  }
}

/** m:ss for countdowns (seconds are rounded up by the caller). */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/**
 * How many slides fit in the remaining demo time, given per-slide narration
 * seconds (from the current slide onwards).
 */
export function slidesThatFit(slideSeconds: number[], secondsLeft: number): number {
  let used = 0;
  let n = 0;
  for (const s of slideSeconds) {
    used += s;
    if (used > secondsLeft) break;
    n += 1;
  }
  return n;
}

export function formatMinutes(seconds: number): string {
  const m = Math.max(1, Math.round(seconds / 60));
  return `${m} minute${m === 1 ? '' : 's'}`;
}

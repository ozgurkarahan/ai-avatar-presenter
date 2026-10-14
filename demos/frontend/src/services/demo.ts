// Public live-avatar demo (anonymous, narration-only).
// `GET /api/demo/config` tells the SPA whether the kill switch is on; the
// actual guardrails (deck allowlist, quotas, time cap) are enforced server-side.
import { useEffect, useState } from 'react';

export interface DemoConfig {
  enabled: boolean;
  session_seconds: number;
  remaining_today?: number;
  loading: boolean;
}

const DISABLED: DemoConfig = { enabled: false, session_seconds: 180, loading: false };

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

export function formatMinutes(seconds: number): string {
  const m = Math.max(1, Math.round(seconds / 60));
  return `${m} minute${m === 1 ? '' : 's'}`;
}

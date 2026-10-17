// Presentation helpers shared by pages (no emoji — icons come from lucide-react).

const LANGUAGE_NAMES: Record<string, string> = {
  'en-US': 'English',
  'en-GB': 'English (UK)',
  'fr-FR': 'Français',
  'es-ES': 'Español',
  'de-DE': 'Deutsch',
  'it-IT': 'Italiano',
  'pt-BR': 'Português',
  'zh-CN': '中文',
  'ja-JP': '日本語',
};

/** "fr-FR" → "Français"; unknown codes are returned unchanged. */
export function languageName(code: string | null | undefined): string {
  if (!code) return '—';
  return LANGUAGE_NAMES[code] ?? code;
}

/** "fr-FR" → "FR". */
export function languageShort(code: string | null | undefined): string {
  if (!code) return '—';
  return (code.split('-')[0] || code).toUpperCase();
}

/**
 * Turns slug-like titles into readable ones: "ai-enablement" → "AI enablement".
 * Titles that already contain spaces or capitals are kept as-is.
 */
export function humanizeTitle(title: string | null | undefined): string {
  const t = (title ?? '').trim();
  if (!t) return 'Untitled';
  if (/\s/.test(t) || /[A-Z]/.test(t)) return t;
  const spaced = t.replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim();
  const words = spaced.split(' ').map((w) => (ACRONYMS.has(w.toLowerCase()) ? w.toUpperCase() : w));
  const out = words.join(' ');
  return out.charAt(0).toUpperCase() + out.slice(1);
}

const ACRONYMS = new Set(['ai', 'ia', 'ki', 'api', 'pdf', 'llm', 'slm', 'mcp', 'rag', 'tts', 'stt', 'ux', 'iot']);

/** 98 → "1:38"; 3725 → "1:02:05"; null → "—". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—';
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function pluralize(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** Two-digit episode number: 1 → "01". */
export function episodeNumber(i: number): string {
  return String(i).padStart(2, '0');
}

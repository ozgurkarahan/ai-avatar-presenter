import type { Slide } from './api';

export type NarrationSource = 'notes' | 'translated_notes' | 'body' | 'title' | 'none';

export interface Narration {
  /** Exactly what the avatar reads aloud for this slide. */
  text: string;
  source: NarrationSource;
  /** A non-English language was requested but no cached translation exists, so the original-language text is read. */
  fallbackOriginal: boolean;
}

type NarrationSlide = Pick<Slide, 'title'> & Partial<Pick<Slide, 'notes' | 'body' | 'translated_notes'>>;

/**
 * Single source of truth for slide narration, shared by the avatar (spoken
 * text) and the slide viewer (displayed speaker notes).
 *
 * Priority: cached translated notes (when `language` differs from the deck's
 * own `sourceLanguage`, default en-US) → notes → body → title.
 */
export function narrationFor(
  slide: NarrationSlide | null | undefined,
  language: string,
  sourceLanguage?: string,
): Narration {
  const source: NarrationSource = slide?.notes ? 'notes' : slide?.body ? 'body' : slide?.title ? 'title' : 'none';
  const original = slide?.notes || slide?.body || slide?.title || '';
  if (!original) return { text: '', source: 'none', fallbackOriginal: false };
  if (language === (sourceLanguage || 'en-US')) return { text: original, source, fallbackOriginal: false };
  const translated = slide?.translated_notes?.[language];
  if (translated) return { text: translated, source: 'translated_notes', fallbackOriginal: false };
  return { text: original, source, fallbackOriginal: language !== sourceLanguage };
}

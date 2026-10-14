// Avatar catalog served by the backend (`GET /api/avatars`, anonymous).
// Ids are opaque; the Speech character name is never exposed to the client.
import { useEffect, useState } from 'react';

export type AvatarGender = 'male' | 'female' | 'neutral' | string;

export interface AvatarInfo {
  id: string;
  display_name: string;
  gender?: AvatarGender | null;
  thumbnail_url?: string | null;
  is_default?: boolean;
  /** Optional hint from the backend (e.g. 'photo' | 'video'); tolerated when absent. */
  kind?: string | null;
}

let cache: Promise<AvatarInfo[]> | null = null;

export function listAvatars(): Promise<AvatarInfo[]> {
  if (!cache) {
    cache = fetch('/api/avatars')
      .then(async (r) => {
        if (!r.ok) throw new Error(`Failed to load avatars (HTTP ${r.status})`);
        const data = await r.json();
        const rows: unknown[] = Array.isArray(data) ? data : (data?.items ?? []);
        return rows.filter((a): a is AvatarInfo =>
          !!a && typeof a === 'object' && typeof (a as AvatarInfo).id === 'string');
      })
      .catch((e) => { cache = null; throw e; });
  }
  return cache;
}

/** `is_default` first, then the first female avatar, then the first avatar. */
export function pickDefaultAvatar(avatars: AvatarInfo[]): AvatarInfo | undefined {
  return avatars.find((a) => a.is_default)
    ?? avatars.find((a) => a.gender === 'female')
    ?? avatars[0];
}

/** Best avatar for a gender: default of that gender, any of that gender, then the global default. */
export function pickAvatarForGender(avatars: AvatarInfo[], gender: string | null | undefined): AvatarInfo | undefined {
  if (gender) {
    const sameGender = avatars.filter((a) => a.gender === gender);
    const hit = sameGender.find((a) => a.is_default) ?? sameGender[0];
    if (hit) return hit;
  }
  return pickDefaultAvatar(avatars);
}

/**
 * Photo avatars are rendered in a 1:1 head-and-shoulders tile; video (stock)
 * avatars keep the wide 16:9 framing.
 */
export function isPhotoAvatar(avatar: AvatarInfo | undefined | null): boolean {
  if (!avatar) return false;
  if (avatar.kind) return avatar.kind.toLowerCase() === 'photo';
  return avatar.id.startsWith('photo_');
}

export function useAvatars(): { avatars: AvatarInfo[]; loading: boolean; error: string | null } {
  const [avatars, setAvatars] = useState<AvatarInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    listAvatars()
      .then((a) => { if (!cancelled) setAvatars(a); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);
  return { avatars, loading, error };
}

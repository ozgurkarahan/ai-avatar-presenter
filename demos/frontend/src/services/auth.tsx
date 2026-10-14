// Auth state for the hybrid exposure model.
// Anonymous visitors can browse published content; only allowlisted
// ("admin") users can run uploads, live avatar, renders, chat, etc.
import React, { createContext, useContext, useEffect, useState } from 'react';

export type AuthMode = 'easyauth' | 'disabled';

export interface AuthState {
  authenticated: boolean;
  is_admin: boolean;
  name: string | null;
  auth_mode: AuthMode;
  loading: boolean;
}

const LOADING_STATE: AuthState = {
  authenticated: false,
  is_admin: false,
  name: null,
  auth_mode: 'easyauth',
  loading: true,
};

const AuthContext = createContext<AuthState>(LOADING_STATE);

let mePromise: Promise<AuthState> | null = null;

async function fetchMe(): Promise<AuthState> {
  try {
    const r = await fetch('/api/me', { credentials: 'same-origin' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    return {
      authenticated: !!d?.authenticated,
      is_admin: !!d?.is_admin,
      name: typeof d?.name === 'string' && d.name ? d.name : null,
      auth_mode: d?.auth_mode === 'disabled' ? 'disabled' : 'easyauth',
      loading: false,
    };
  } catch (e) {
    // Default deny: if identity can't be determined, treat as anonymous.
    console.warn('[auth] /api/me failed — treating visitor as anonymous', e);
    return { ...LOADING_STATE, loading: false };
  }
}

/** Fetches `/api/me` once per page load (shared across all consumers). */
export function loadAuth(): Promise<AuthState> {
  if (!mePromise) mePromise = fetchMe();
  return mePromise;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>(LOADING_STATE);
  useEffect(() => {
    let cancelled = false;
    loadAuth().then((s) => { if (!cancelled) setState(s); });
    return () => { cancelled = true; };
  }, []);
  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

export function signInUrl(): string {
  const here = `${window.location.pathname}${window.location.search}`;
  return `/.auth/login/aad?post_login_redirect_uri=${encodeURIComponent(here)}`;
}

export const SIGN_OUT_URL = '/.auth/logout?post_logout_redirect_uri=/';

export function signIn(): void {
  window.location.href = signInUrl();
}

// ---- Global 401/403 handling ----------------------------------------------
export interface AuthErrorDetail {
  status: 401 | 403;
  url: string;
}

export const AUTH_ERROR_EVENT = 'app:auth-error';

export function emitAuthError(status: 401 | 403, url = ''): void {
  window.dispatchEvent(new CustomEvent<AuthErrorDetail>(AUTH_ERROR_EVENT, { detail: { status, url } }));
}

let interceptorInstalled = false;

/**
 * Wraps `window.fetch` so any 401/403 from `/api/*` raises a global
 * notification (rendered by <AuthToast/>). Responses are passed through
 * untouched so callers keep their own error handling.
 */
export function installAuthErrorInterceptor(): void {
  if (interceptorInstalled || typeof window === 'undefined' || !window.fetch) return;
  interceptorInstalled = true;
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const res = await original(input, init);
    if (res.status === 401 || res.status === 403) {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      let path = url;
      try { path = new URL(url, window.location.origin).pathname; } catch { /* keep raw */ }
      if (path.startsWith('/api/') && path !== '/api/me') {
        emitAuthError(res.status as 401 | 403, path);
      }
    }
    return res;
  };
}

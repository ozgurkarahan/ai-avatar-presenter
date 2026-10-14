import React, { useEffect, useRef, useState } from 'react';
import { AUTH_ERROR_EVENT, type AuthErrorDetail, signIn, useAuth } from '../services/auth';
import { NOT_ENABLED_MESSAGE } from './AuthGate';

/** Global banner for 401/403 responses from the API (see installAuthErrorInterceptor). */
export default function AuthToast() {
  const auth = useAuth();
  const [toast, setToast] = useState<AuthErrorDetail | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const onErr = (e: Event) => {
      const detail = (e as CustomEvent<AuthErrorDetail>).detail;
      if (!detail) return;
      setToast(detail);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setToast(null), 7000);
    };
    window.addEventListener(AUTH_ERROR_EVENT, onErr);
    return () => {
      window.removeEventListener(AUTH_ERROR_EVENT, onErr);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  if (!toast) return null;
  const needsSignIn = toast.status === 401 && !auth.authenticated;
  return (
    <div
      role="alert"
      data-testid="auth-toast"
      style={{
        position: 'fixed', bottom: 20, left: '50%', transform: 'translateX(-50%)', zIndex: 2000,
        background: needsSignIn ? '#003366' : '#9a3412', color: 'white',
        borderRadius: 10, padding: '10px 14px', boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
        display: 'flex', alignItems: 'center', gap: 12, fontSize: 13.5, maxWidth: 'calc(100vw - 32px)',
      }}
    >
      <span aria-hidden>{needsSignIn ? '🔒' : '⛔'}</span>
      <span>
        {needsSignIn
          ? 'Sign in required — this action is only available to signed-in demo users.'
          : toast.status === 401
            ? 'Your session has expired. Please sign in again.'
            : NOT_ENABLED_MESSAGE}
      </span>
      {(needsSignIn || toast.status === 401) && auth.auth_mode !== 'disabled' && (
        <button
          type="button"
          onClick={signIn}
          style={{
            background: 'white', color: '#003366', border: 'none', borderRadius: 6,
            padding: '4px 10px', fontWeight: 700, fontSize: 12.5, cursor: 'pointer',
          }}
        >
          Sign in
        </button>
      )}
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => setToast(null)}
        style={{ background: 'transparent', color: 'white', border: 'none', cursor: 'pointer', fontSize: 15 }}
      >
        ✕
      </button>
    </div>
  );
}

import React from 'react';
import { signIn, useAuth } from '../services/auth';

const palette = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  muted: '#64748b', border: '#e2e8f0', infoBg: '#eff6ff', warnBg: '#fff7ed', warnText: '#9a3412',
};

export const NOT_ENABLED_MESSAGE = "Your account isn't enabled for this demo.";

/** Returns true when the current visitor may use admin-only features. */
export function useIsAdmin(): boolean {
  return useAuth().is_admin;
}

/**
 * Inline call-to-action shown in place of an admin-only control.
 * - anonymous → "Sign in to {action}" + Sign in button
 * - signed in but not allowlisted → "Your account isn't enabled for this demo."
 */
export function GateNotice({ action, compact = false, style, force }: {
  action: string; compact?: boolean; style?: React.CSSProperties;
  /** Override the /api/me-derived state, e.g. after a 4401/4403 WebSocket close. */
  force?: 'signin' | 'forbidden';
}) {
  const auth = useAuth();
  if (!force && (auth.loading || auth.is_admin)) return null;
  const forbidden = force ? force === 'forbidden' : auth.authenticated;
  return (
    <div
      role="note"
      data-testid="auth-gate"
      style={{
        display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
        justifyContent: compact ? 'flex-start' : 'center',
        background: forbidden ? palette.warnBg : palette.infoBg,
        color: forbidden ? palette.warnText : palette.brand,
        border: `1px solid ${palette.border}`, borderRadius: 10,
        padding: compact ? '8px 12px' : '14px 18px', fontSize: compact ? 12.5 : 14,
        ...style,
      }}
    >
      <span aria-hidden>{forbidden ? '⛔' : '🔒'}</span>
      <span style={{ fontWeight: 600 }}>
        {forbidden ? NOT_ENABLED_MESSAGE : `Sign in to ${action}`}
      </span>
      {!forbidden && auth.auth_mode !== 'disabled' && (
        <button
          type="button"
          onClick={signIn}
          style={{
            background: palette.brandLight, color: 'white', border: 'none', borderRadius: 6,
            padding: compact ? '4px 10px' : '6px 14px', fontWeight: 600,
            fontSize: compact ? 12 : 13, cursor: 'pointer',
          }}
        >
          Sign in
        </button>
      )}
    </div>
  );
}

/**
 * Renders children only for admins. Non-admins get <GateNotice/> (or the
 * provided fallback; pass `fallback={null}` to hide entirely).
 */
export function AdminOnly({ children, action = 'use this feature', fallback, compact }: {
  children: React.ReactNode; action?: string; fallback?: React.ReactNode; compact?: boolean;
}) {
  const auth = useAuth();
  if (auth.loading) return null;
  if (auth.is_admin) return <>{children}</>;
  if (fallback !== undefined) return <>{fallback}</>;
  return <GateNotice action={action} compact={compact} />;
}

/**
 * Friendly full-panel replacement for generation pages when the visitor is
 * not an admin. Links point to the public (published) parts of the app.
 */
export function GatedPanel({ icon, title, description, action, links = [] }: {
  icon: string; title: string; description: string; action: string;
  links?: { href: string; label: string }[];
}) {
  return (
    <div
      data-testid="gated-panel"
      style={{
        background: 'white', borderRadius: 16, padding: '40px 32px', textAlign: 'center',
        boxShadow: '0 4px 20px rgba(0, 51, 102, 0.08)', maxWidth: 720, margin: '0 auto',
      }}
    >
      <div style={{ fontSize: 48, marginBottom: 12 }} aria-hidden>{icon}</div>
      <h2 style={{ margin: '0 0 8px', color: palette.brand }}>{title}</h2>
      <p style={{ color: palette.muted, margin: '0 auto 20px', maxWidth: 560, lineHeight: 1.55 }}>{description}</p>
      <GateNotice action={action} />
      {links.length > 0 && (
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap', marginTop: 20 }}>
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              style={{
                background: '#f8fafc', color: palette.brand, border: `1px solid ${palette.border}`,
                borderRadius: 8, padding: '8px 16px', textDecoration: 'none', fontWeight: 600, fontSize: 13,
              }}
            >
              {l.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

/** Small Published / Draft pill shown to admins. */
export function PublishBadge({ published }: { published: boolean | undefined }) {
  const on = !!published;
  return (
    <span
      data-testid="publish-badge"
      style={{
        fontSize: 10.5, fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase',
        padding: '2px 8px', borderRadius: 999,
        background: on ? '#dcfce7' : '#f1f5f9',
        color: on ? '#15803d' : '#475569',
        border: `1px solid ${on ? '#86efac' : '#cbd5e1'}`,
        whiteSpace: 'nowrap',
      }}
    >
      {on ? '● Published' : '○ Draft'}
    </span>
  );
}

/** Admin toggle that publishes / unpublishes an item. */
export function PublishToggle({ published, busy, onToggle }: {
  published: boolean | undefined; busy?: boolean; onToggle: (next: boolean) => void;
}) {
  const on = !!published;
  return (
    <button
      type="button"
      data-testid="publish-toggle"
      disabled={busy}
      onClick={(e) => { e.stopPropagation(); onToggle(!on); }}
      title={on ? 'Hide from anonymous visitors' : 'Make visible to anonymous visitors'}
      style={{
        background: on ? 'white' : palette.brandLight,
        color: on ? palette.brand : 'white',
        border: `1px solid ${on ? palette.border : palette.brandLight}`,
        borderRadius: 6, padding: '4px 10px', fontSize: 12, fontWeight: 600,
        cursor: busy ? 'progress' : 'pointer', opacity: busy ? 0.6 : 1, whiteSpace: 'nowrap',
      }}
    >
      {busy ? '…' : on ? 'Unpublish' : 'Publish'}
    </button>
  );
}

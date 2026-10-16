import React, { useId } from 'react';
import {
  ArrowRight, Ban, CircleCheck, CircleDashed, Clapperboard, Eye, EyeOff, Film, GraduationCap,
  Headphones, ListVideo, Lock, LogIn, Mic, Presentation, Radio, type LucideIcon,
} from 'lucide-react';
import { signIn, useAuth } from '../services/auth';
import { Button, ButtonLink, Chip, buttonClass } from '../ui';
import '../styles/shared/auth-gate.css';

export const NOT_ENABLED_MESSAGE = "Your account isn't enabled for this demo.";

/** Returns true when the current visitor may use admin-only features. */
export function useIsAdmin(): boolean {
  return useAuth().is_admin;
}

const EMOJI_RE = /[\p{Extended_Pictographic}\p{Regional_Indicator}\u{FE0F}\u{200D}\u{20E3}]/gu;

/** Removes emoji (pages still pass legacy emoji labels) and tidies whitespace. */
function stripEmoji(text: string): string {
  return text.replace(EMOJI_RE, '').replace(/\s+/g, ' ').trim();
}

// Legacy emoji `icon` strings (keyed by code point, variation selectors removed) → lucide equivalents.
const LEGACY_ICONS: Record<number, LucideIcon> = {
  0x1F399: Mic, 0x1F3AC: Clapperboard, 0x1F3A7: Headphones, 0x1F6E4: ListVideo,
  0x1F393: GraduationCap, 0x1F39E: Film, 0x1F4DA: Presentation,
};

function legacyIcon(icon: string): LucideIcon {
  const cp = icon.replace(/\u{FE0F}/gu, '').trim().codePointAt(0);
  return (cp !== undefined && LEGACY_ICONS[cp]) || Lock;
}

function linkIcon(href: string): LucideIcon {
  if (href.startsWith('/decks')) return Presentation;
  if (href.startsWith('/video')) return Film;
  if (href.startsWith('/podcast')) return Headphones;
  if (href.startsWith('/playlists')) return ListVideo;
  return ArrowRight;
}

/**
 * Inline call-to-action shown in place of an admin-only control.
 * - anonymous → "Sign in to {action}" + Sign in button
 * - signed in but not allowlisted → "Your account isn't enabled for this demo."
 */
export function GateNotice({ action, compact = false, style, force, className }: {
  action: string; compact?: boolean; style?: React.CSSProperties;
  /** Override the /api/me-derived state, e.g. after a 4401/4403 WebSocket close. */
  force?: 'signin' | 'forbidden';
  className?: string;
}) {
  const auth = useAuth();
  if (!force && (auth.loading || auth.is_admin)) return null;
  const forbidden = force ? force === 'forbidden' : auth.authenticated;
  const Icon = forbidden ? Ban : Lock;
  return (
    <div
      role="note"
      data-testid="auth-gate"
      className={['alert', 'gate-notice', forbidden && 'alert--error', compact && 'gate-notice--compact', className]
        .filter(Boolean).join(' ')}
      style={style}
    >
      <Icon aria-hidden className="gate-notice__icon" />
      <span className="gate-notice__text">
        {forbidden ? NOT_ENABLED_MESSAGE : `Sign in to ${action}`}
      </span>
      {!forbidden && auth.auth_mode !== 'disabled' && (
        <Button size="sm" variant="primary" icon={LogIn} onClick={signIn} className="gate-notice__action">
          Sign in
        </Button>
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
export function GatedPanel({ icon, title, description, action, links = [], eyebrow = 'Demo access' }: {
  /** A lucide icon; legacy emoji strings are mapped to an icon (fallback: Lock). */
  icon?: LucideIcon | string;
  title: string; description: string; action: string;
  links?: { href: string; label: string }[];
  /** Small caps line above the title. */
  eyebrow?: string;
}) {
  const Icon: LucideIcon = typeof icon === 'string' ? legacyIcon(icon) : (icon ?? Lock);
  const titleId = useId();
  return (
    <section data-testid="gated-panel" className="empty gated-panel" aria-labelledby={titleId}>
      <span className="empty__icon"><Icon aria-hidden /></span>
      {eyebrow && <span className="eyebrow">{eyebrow}</span>}
      <h2 id={titleId} className="empty__title gated-panel__title">{stripEmoji(title)}</h2>
      <p className="empty__text gated-panel__text">{description}</p>
      <GateNotice action={action} className="gated-panel__notice" />
      {links.length > 0 && (
        <nav className="gated-panel__links" aria-label="Browse public content">
          {links.map((l) => {
            const label = stripEmoji(l.label);
            const LinkIcon = linkIcon(l.href);
            return l.href.startsWith('/') ? (
              <ButtonLink key={l.href} to={l.href} size="sm" icon={LinkIcon}>{label}</ButtonLink>
            ) : (
              <a key={l.href} href={l.href} className={buttonClass({ size: 'sm' })}>
                <LinkIcon aria-hidden />{label}
              </a>
            );
          })}
        </nav>
      )}
    </section>
  );
}

/** Small Published / Draft pill shown to admins. */
export function PublishBadge({ published }: { published: boolean | undefined }) {
  const on = !!published;
  return (
    <Chip data-testid="publish-badge" tone={on ? 'sage' : 'default'} icon={on ? CircleCheck : CircleDashed}>
      {on ? 'Published' : 'Draft'}
    </Chip>
  );
}

/** Admin toggle that publishes / unpublishes an item. */
export function PublishToggle({ published, busy, onToggle }: {
  published: boolean | undefined; busy?: boolean; onToggle: (next: boolean) => void;
}) {
  const on = !!published;
  return (
    <Button
      size="sm"
      data-testid="publish-toggle"
      busy={busy}
      icon={on ? EyeOff : Eye}
      onClick={(e) => { e.stopPropagation(); onToggle(!on); }}
      title={on ? 'Hide from anonymous visitors' : 'Make visible to anonymous visitors'}
    >
      {on ? 'Unpublish' : 'Publish'}
    </Button>
  );
}

/** "Live demo" pill: anonymous visitors can try the narration-only live avatar on this deck. */
export function LiveDemoBadge({ liveDemo }: { liveDemo: boolean | undefined }) {
  if (!liveDemo) return null;
  return (
    <Chip
      data-testid="live-demo-badge"
      tone="clay"
      icon={Radio}
      title="Visitors can try the live avatar narrating this deck"
    >
      Live demo
    </Chip>
  );
}

/** Admin toggle for the anonymous live avatar demo (only on published items). */
export function LiveDemoToggle({ liveDemo, published, busy, onToggle }: {
  liveDemo: boolean | undefined; published: boolean | undefined; busy?: boolean; onToggle: (next: boolean) => void;
}) {
  const on = !!liveDemo;
  const blocked = !on && !published;
  return (
    <Button
      size="sm"
      data-testid="live-demo-toggle"
      className={['live-demo-toggle', on && 'is-on'].filter(Boolean).join(' ')}
      busy={busy}
      disabled={blocked}
      aria-pressed={on}
      icon={Radio}
      onClick={(e) => { e.stopPropagation(); onToggle(!on); }}
      title={blocked
        ? 'Publish the deck first'
        : on ? 'Stop anonymous visitors from running the live avatar on this deck'
          : 'Let anonymous visitors try the narration-only live avatar on this deck'}
    >
      {on ? 'Live demo on' : 'Live demo off'}
    </Button>
  );
}

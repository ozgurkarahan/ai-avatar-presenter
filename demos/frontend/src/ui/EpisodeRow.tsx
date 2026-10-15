import React from 'react';
import { Link } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';

/**
 * One row of an editorial "episode" list (decks, videos, podcasts, playlists).
 * The title is the primary action and stretches over the whole row; controls in
 * `actions` / `extra` stay independently clickable above it.
 *
 * Extra props (e.g. `data-testid`) are applied to the <li>.
 */
export function EpisodeRow({
  num, title, to, onOpen, openLabel, meta, kind, hosts, duration, actions, extra, titleProps, className, ...rest
}: {
  num?: React.ReactNode;
  title: React.ReactNode;
  /** Router destination for the title… */
  to?: string;
  /** …or a click handler (used when no route exists, e.g. opening a player). */
  onOpen?: () => void;
  /** Accessible label for the title action when the title alone is ambiguous. */
  openLabel?: string;
  meta?: React.ReactNode[];
  kind?: { icon: LucideIcon; label: string };
  hosts?: React.ReactNode;
  duration?: React.ReactNode;
  actions?: React.ReactNode;
  extra?: React.ReactNode;
  titleProps?: Record<string, unknown>;
} & Omit<React.LiHTMLAttributes<HTMLLIElement>, 'title'>) {
  const KindIcon = kind?.icon;
  const titleNode = to ? (
    <Link className="episode-row__title" to={to} aria-label={openLabel} {...titleProps}>{title}</Link>
  ) : onOpen ? (
    <button type="button" className="episode-row__title" onClick={onOpen} aria-label={openLabel} {...titleProps}>{title}</button>
  ) : (
    <span className="episode-row__title" {...titleProps}>{title}</span>
  );
  return (
    <li className={['episode-row', className].filter(Boolean).join(' ')} {...rest}>
      <span className="episode-row__num" aria-hidden>{num}</span>
      <div className="episode-row__body">
        {titleNode}
        {meta && meta.length > 0 && (
          <div className="episode-row__meta">
            {meta.filter(Boolean).map((m, i) => <span key={i}>{m}</span>)}
          </div>
        )}
        {extra && <div className="episode-row__extra">{extra}</div>}
      </div>
      <span className="episode-row__kind">{KindIcon && <KindIcon aria-hidden />}{kind?.label}</span>
      <span className="episode-row__hosts">{hosts}</span>
      <span className="episode-row__dur">{duration}</span>
      <div className="episode-row__actions">{actions}</div>
    </li>
  );
}

export function EpisodeList({ children, label, className }: { children: React.ReactNode; label?: string; className?: string }) {
  return <ol className={['episode-list', className].filter(Boolean).join(' ')} aria-label={label}>{children}</ol>;
}

import React, { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { ChevronDown, Clapperboard, Headphones, Menu, Mic, X } from 'lucide-react';
import { SIGN_OUT_URL, signInUrl, useAuth } from '../services/auth';
import { syncDocumentThemeWithTeams } from '../services/teams';
import { buttonClass } from '../ui';
import '../styles/shell.css';

type NavItem = { to: string; label: string; end?: boolean };

const PRIMARY: NavItem[] = [
  { to: '/', label: 'Home', end: true },
  { to: '/decks', label: 'Decks' },
  { to: '/video/library', label: 'Videos' },
  { to: '/podcast/library', label: 'Podcasts' },
  { to: '/playlists', label: 'Playlists' },
  { to: '/search', label: 'Search' },
];

const CREATE = [
  { to: '/live', label: 'Live presentation', desc: 'Upload a deck; the live avatar presents it with Q&A.', icon: Mic },
  { to: '/video', label: 'Narrated video', desc: 'Render a narrated avatar video from a .pptx.', icon: Clapperboard },
  { to: '/podcast', label: 'Two-host podcast', desc: 'Turn a document into a two-avatar conversation.', icon: Headphones },
];

/** Editorial masthead: wordmark, primary sections, "Create" menu, auth controls, mobile sheet. */
export default function TopNav() {
  const auth = useAuth();
  const locked = !auth.loading && !auth.is_admin;
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const createRef = useRef<HTMLDivElement>(null);
  const createActive = CREATE.some((c) => c.to === pathname);

  useEffect(() => { syncDocumentThemeWithTeams().catch(() => { /* not in Teams */ }); }, []);

  useEffect(() => { setMenuOpen(false); setSheetOpen(false); }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => { if (!createRef.current?.contains(e.target as Node)) setMenuOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    createRef.current?.querySelector<HTMLElement>('.menu__item')?.focus();
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [menuOpen]);

  useEffect(() => {
    if (!sheetOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSheetOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => { document.body.style.overflow = prev; document.removeEventListener('keydown', onKey); };
  }, [sheetOpen]);

  return (
    <header className="masthead">
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="container masthead__inner">
        <Link to="/" className="masthead__brand" aria-label="Oz Radio home">Oz <em>Radio</em></Link>

        <nav className="masthead__nav" aria-label="Main">
          {PRIMARY.map((it) => (
            <NavLink key={it.to} to={it.to} end={it.end} className="masthead__link">{it.label}</NavLink>
          ))}
          <div className="masthead__create" ref={createRef}>
            <button
              type="button"
              className={['masthead__link', createActive && 'is-active'].filter(Boolean).join(' ')}
              aria-haspopup="true"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((o) => !o)}
            >
              Create <ChevronDown aria-hidden />
            </button>
            {menuOpen && (
              <div className="menu" role="menu" aria-label="Create">
                {CREATE.map((c) => (
                  <NavLink key={c.to} to={c.to} end role="menuitem" className="menu__item">
                    <c.icon aria-hidden />
                    <span>
                      {c.label}
                      <small>{locked ? 'Sign-in required' : c.desc}</small>
                    </span>
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        </nav>

        <div className="masthead__actions">
          <AuthControls />
          <button
            type="button"
            className={buttonClass({ variant: 'ghost', iconOnly: true }, 'masthead__menu-btn')}
            aria-label={sheetOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={sheetOpen}
            aria-controls="site-sheet"
            onClick={() => setSheetOpen((o) => !o)}
          >
            {sheetOpen ? <X aria-hidden /> : <Menu aria-hidden />}
          </button>
        </div>
      </div>

      <div id="site-sheet" className="masthead__sheet" data-open={sheetOpen}>
        {sheetOpen && (
          <>
            <nav className="sheet__group" aria-label="Sections">
              <span className="eyebrow">Listen &amp; watch</span>
              {PRIMARY.map((it) => (
                <NavLink key={it.to} to={it.to} end={it.end} className="sheet__link">{it.label}</NavLink>
              ))}
            </nav>
            <nav className="sheet__group" aria-label="Create">
              <span className="eyebrow">Create</span>
              {CREATE.map((c) => (
                <NavLink key={c.to} to={c.to} end className="sheet__link">
                  {c.label}
                  {locked && <small>Sign-in required</small>}
                </NavLink>
              ))}
            </nav>
          </>
        )}
      </div>
    </header>
  );
}

function AuthControls() {
  const auth = useAuth();
  if (auth.loading || auth.auth_mode === 'disabled') {
    return <div data-testid="auth-controls" />;
  }
  return (
    <div className="cluster" style={{ '--cluster-gap': 'var(--sp-3)', flexWrap: 'nowrap' } as React.CSSProperties} data-testid="auth-controls">
      {auth.authenticated ? (
        <>
          <span className="masthead__user" title={auth.is_admin ? 'Signed in — full demo access' : 'Signed in — read-only access'}>
            {auth.name ?? 'Signed in'}{!auth.is_admin && ' · read-only'}
          </span>
          <a href={SIGN_OUT_URL} className={buttonClass({ size: 'sm' })}>Sign out</a>
        </>
      ) : (
        <a
          href={signInUrl()}
          onClick={(e) => { e.preventDefault(); window.location.href = signInUrl(); }}
          className={buttonClass({ size: 'sm', variant: 'primary' })}
        >
          Sign in
        </a>
      )}
    </div>
  );
}

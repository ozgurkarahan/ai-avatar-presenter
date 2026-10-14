import React from 'react';
import { NavLink } from 'react-router-dom';
import { SIGN_OUT_URL, signInUrl, useAuth } from '../services/auth';

type NavItem = { to: string; end?: boolean; icon: string; label: string; desc: string; adminOnly?: boolean };
// `label` (optional) prefixes a group of pills, e.g. "Video:".
type NavGroup = { id: string; label?: string; title: string; items: NavItem[] };

const groups: NavGroup[] = [
  {
    id: 'main',
    title: 'Decks',
    items: [
      { to: '/', end: true, icon: '🏠', label: 'Home', desc: 'Start here — live demo, decks, search and playlists.' },
      { to: '/live', end: true, icon: '🎙️', label: 'Live', desc: 'Upload one deck and let the live avatar present it, with slide Q&A.', adminOnly: true },
      { to: '/decks', icon: '📚', label: 'Decks', desc: 'Upload, browse, publish and present your decks.' },
      { to: '/search', icon: '🔎', label: 'Search', desc: 'Ask anything across all decks; the avatar presents the right slide.', adminOnly: true },
      { to: '/playlists', icon: '📻', label: 'Playlists', desc: 'Chain decks into ordered playlists with progress tracking.', adminOnly: true },
    ],
  },
  {
    id: 'video',
    label: 'Video',
    title: 'Narrated video',
    items: [
      { to: '/video', end: true, icon: '🎬', label: 'Create', desc: 'Build a pre-rendered narrated avatar video from a .pptx.', adminOnly: true },
      { to: '/video/library', icon: '🎞️', label: 'Library', desc: 'Browse and play previously generated videos.' },
    ],
  },
  {
    id: 'podcast',
    label: 'Podcast',
    title: 'Two-avatar podcast',
    items: [
      { to: '/podcast', end: true, icon: '🎧', label: 'Create', desc: 'Convert a document into a two-host podcast conversation.', adminOnly: true },
      { to: '/podcast/library', icon: '📚', label: 'Library', desc: 'Browse previously generated podcasts.' },
    ],
  },
];

const pillStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  color: 'rgba(255,255,255,0.82)',
  textDecoration: 'none',
  padding: '4px 9px',
  borderRadius: 5,
  fontSize: 12.5,
  fontWeight: 500,
  whiteSpace: 'nowrap',
};
const pillActiveStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.22)',
  color: 'white',
  fontWeight: 600,
};
const groupLabelStyle: React.CSSProperties = {
  fontSize: 11.5,
  fontWeight: 700,
  color: 'rgba(255,255,255,0.7)',
  marginRight: 2,
  whiteSpace: 'nowrap',
};
const sepStyle: React.CSSProperties = {
  width: 1,
  height: 18,
  background: 'rgba(255,255,255,0.18)',
  margin: '0 2px',
};

export default function TopNav() {
  const auth = useAuth();
  const locked = !auth.loading && !auth.is_admin;
  return (
    <div
      style={{
        background: 'linear-gradient(135deg, #003366 0%, #005599 100%)',
        padding: '6px 18px',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        flexWrap: 'wrap',
      }}
    >
      <div
        style={{ color: 'white', fontWeight: 700, fontSize: 13, letterSpacing: 0.2, marginRight: 8 }}
        title="AI avatars that present, narrate and podcast your decks"
      >
        DeckFM
      </div>
      {groups.map((g, idx) => (
        <React.Fragment key={g.id}>
          {idx > 0 && <div style={sepStyle} aria-hidden />}
          {g.label && <span style={groupLabelStyle} title={g.title}>{g.label}:</span>}
          {g.items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.end}
              title={`${it.label} — ${it.desc}${locked && it.adminOnly ? ' (sign-in required)' : ''}`}
              style={({ isActive }) => ({ ...pillStyle, ...(isActive ? pillActiveStyle : {}) })}
            >
              <span aria-hidden>{it.icon}</span>
              <span>{it.label}</span>
              {locked && it.adminOnly && <span aria-label="sign-in required" style={{ fontSize: 10, opacity: 0.75 }}>🔒</span>}
            </NavLink>
          ))}
        </React.Fragment>
      ))}
      <AuthControls />
    </div>
  );
}

function AuthControls() {
  const auth = useAuth();
  if (auth.loading || auth.auth_mode === 'disabled') {
    return <div style={{ marginLeft: 'auto' }} />;
  }
  return (
    <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }} data-testid="auth-controls">
      {auth.authenticated ? (
        <>
          <span
            style={{ color: 'rgba(255,255,255,0.9)', fontSize: 12.5, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title={auth.is_admin ? 'Signed in — full demo access' : 'Signed in — read-only access'}
          >
            👤 {auth.name ?? 'Signed in'}{!auth.is_admin && ' (read-only)'}
          </span>
          <a href={SIGN_OUT_URL} style={authBtnStyle}>Sign out</a>
        </>
      ) : (
        <a href={signInUrl()} onClick={(e) => { e.preventDefault(); window.location.href = signInUrl(); }} style={authBtnStyle}>
          Sign in
        </a>
      )}
    </div>
  );
}

const authBtnStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.95)',
  color: '#003366',
  textDecoration: 'none',
  padding: '4px 12px',
  borderRadius: 5,
  fontSize: 12.5,
  fontWeight: 700,
  whiteSpace: 'nowrap',
};

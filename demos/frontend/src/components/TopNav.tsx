import React from 'react';
import { NavLink } from 'react-router-dom';

type NavItem = { to: string; end?: boolean; icon: string; label: string; desc: string };
type NavGroup = { title: string; tag: string; items: NavItem[] };

const groups: NavGroup[] = [
  {
    title: 'AI Presenter',
    tag: 'Legacy',
    items: [
      { to: '/', end: true, icon: '🎙️', label: 'Presenter', desc: 'Original single-deck presenter (kept for compatibility).' },
    ],
  },
  {
    title: 'Learning Hub',
    tag: 'UC1',
    items: [
      { to: '/uc1', end: true, icon: '🏠', label: 'Hub', desc: 'UC1 Learning Hub home — pick Learn or Decks.' },
      { to: '/uc1/learn', icon: '🎓', label: 'Learn', desc: 'Ask anything across all decks; the avatar presents the right slide.' },
      { to: '/uc1/decks', icon: '📚', label: 'Decks', desc: 'Upload, browse, tag, and manage your training decks.' },
    ],
  },
  {
    title: 'Static Video',
    tag: 'UC2',
    items: [
      { to: '/video', end: true, icon: '🎬', label: 'Generate', desc: 'Build a pre-rendered avatar video from a .pptx.' },
      { to: '/video/library', icon: '🎞️', label: 'Library', desc: 'Browse and play previously generated static videos.' },
    ],
  },
  {
    title: 'Podcast',
    tag: 'UC3',
    items: [
      { to: '/podcast', end: true, icon: '🎧', label: 'Create', desc: 'Convert a document into a two-host podcast conversation.' },
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
const tagStyle: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 800,
  letterSpacing: 0.7,
  padding: '2px 5px',
  borderRadius: 3,
  background: 'rgba(255,255,255,0.12)',
  color: 'rgba(255,255,255,0.7)',
  marginRight: 4,
};
const sepStyle: React.CSSProperties = {
  width: 1,
  height: 18,
  background: 'rgba(255,255,255,0.18)',
  margin: '0 2px',
};

export default function TopNav() {
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
      <div style={{ color: 'white', fontWeight: 700, fontSize: 13, letterSpacing: 0.2, marginRight: 8 }}>
        Acme · AI Avatar Suite
      </div>
      {groups.map((g, idx) => (
        <React.Fragment key={g.tag}>
          {idx > 0 && <div style={sepStyle} aria-hidden />}
          <span style={tagStyle} title={g.title}>{g.tag}</span>
          {g.items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.end}
              title={`${it.label} — ${it.desc}`}
              style={({ isActive }) => ({ ...pillStyle, ...(isActive ? pillActiveStyle : {}) })}
            >
              <span aria-hidden>{it.icon}</span>
              <span>{it.label}</span>
            </NavLink>
          ))}
        </React.Fragment>
      ))}
    </div>
  );
}

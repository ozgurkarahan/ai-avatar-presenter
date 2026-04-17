import React from 'react';
import { NavLink } from 'react-router-dom';

type NavItem = {
  to: string;
  end?: boolean;
  icon: string;
  label: string;
  desc: string;
};

type NavGroup = {
  title: string;
  tag: string;
  items: NavItem[];
};

const groups: NavGroup[] = [
  {
    title: 'Live Avatar',
    tag: 'UC1',
    items: [
      {
        to: '/',
        end: true,
        icon: '🎙️',
        label: 'Presenter',
        desc: 'Upload a .pptx and present live with an AI avatar (real-time Q&A, multilingual voices).',
      },
    ],
  },
  {
    title: 'Static Video',
    tag: 'UC2',
    items: [
      {
        to: '/video',
        end: true,
        icon: '🎬',
        label: 'Generate',
        desc: 'Build a pre-rendered avatar video from a .pptx — pick voice, language, avatar style.',
      },
      {
        to: '/video/library',
        icon: '🎞️',
        label: 'Library',
        desc: 'Browse and play previously generated static videos stored in Azure Blob.',
      },
    ],
  },
  {
    title: 'Podcast',
    tag: 'UC3',
    items: [
      {
        to: '/podcast',
        end: true,
        icon: '🎧',
        label: 'Create',
        desc: 'Convert a document into a two-host podcast conversation with AI voices.',
      },
      {
        to: '/podcast/library',
        icon: '📚',
        label: 'Library',
        desc: 'Browse and play previously generated podcasts.',
      },
    ],
  },
];

const tabStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  color: 'rgba(255,255,255,0.82)',
  textDecoration: 'none',
  padding: '6px 12px',
  borderRadius: 8,
  fontSize: 13,
  fontWeight: 600,
  whiteSpace: 'nowrap',
  transition: 'background 0.15s, color 0.15s',
};
const activeStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.22)',
  color: 'white',
  boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
};

const groupBoxStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  padding: '4px 8px 4px 10px',
  background: 'rgba(255,255,255,0.06)',
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 10,
};
const groupLabelStyle: React.CSSProperties = {
  color: 'rgba(255,255,255,0.55)',
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: 0.8,
  textTransform: 'uppercase',
  marginRight: 6,
  userSelect: 'none',
};

export default function TopNav() {
  return (
    <div
      style={{
        background: 'linear-gradient(135deg, #003366 0%, #005599 100%)',
        padding: '10px 28px',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        flexWrap: 'wrap',
      }}
    >
      <div
        style={{
          color: 'white',
          fontWeight: 800,
          fontSize: 15,
          letterSpacing: 0.5,
          marginRight: 8,
        }}
      >
        Acme · AI Avatar Suite
      </div>
      {groups.map((g) => (
        <div key={g.tag} style={groupBoxStyle} title={`${g.tag} — ${g.title}`}>
          <span style={groupLabelStyle}>
            {g.tag} · {g.title}
          </span>
          {g.items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.end}
              title={it.desc}
              style={({ isActive }) => ({ ...tabStyle, ...(isActive ? activeStyle : {}) })}
            >
              <span aria-hidden>{it.icon}</span>
              <span>{it.label}</span>
            </NavLink>
          ))}
        </div>
      ))}
    </div>
  );
}

import React from 'react';
import { useNavigate } from 'react-router-dom';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
};

const cards = [
  {
    to: '/uc1/learn',
    emoji: '🎓',
    title: 'Learn',
    desc: 'Ask anything across all your decks. The AI finds the right slide and the avatar presents it.',
  },
  {
    to: '/uc1/decks',
    emoji: '📚',
    title: 'Decks',
    desc: 'Manage your training decks. Upload, tag, organize.',
  },
  {
    to: '/uc1/paths',
    emoji: '🛤️',
    title: 'Paths',
    desc: 'Build sequenced learning journeys across multiple decks. Track progress, resume anytime.',
  },
];

export default function Uc1HubPage() {
  const navigate = useNavigate();
  return (
    <div style={{ minHeight: 'calc(100vh - 60px)', background: theme.cardAlt, padding: '56px 24px' }}>
      <div style={{ maxWidth: 960, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1.5, color: theme.accent, textTransform: 'uppercase' }}>
            UC1 · Learning Hub
          </div>
          <h1 style={{ margin: '8px 0 12px', fontSize: 38, color: theme.brand, fontWeight: 800 }}>
            Your AI-powered training library
          </h1>
          <p style={{ fontSize: 17, color: theme.muted, maxWidth: 620, margin: '0 auto', lineHeight: 1.55 }}>
            Upload your decks once. Ask questions anytime. The avatar presents the exact slide that answers you.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 24 }}>
          {cards.map((c) => (
            <button
              key={c.to}
              onClick={() => navigate(c.to)}
              style={{
                background: theme.card,
                border: `1px solid ${theme.border}`,
                borderRadius: 16,
                padding: '36px 32px',
                textAlign: 'left',
                cursor: 'pointer',
                boxShadow: theme.shadow,
                transition: 'transform 0.15s, box-shadow 0.15s, border-color 0.15s',
                color: theme.text,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-4px)';
                e.currentTarget.style.borderColor = theme.accent;
                e.currentTarget.style.boxShadow = '0 10px 30px rgba(0, 51, 102, 0.15)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.borderColor = theme.border;
                e.currentTarget.style.boxShadow = theme.shadow;
              }}
            >
              <div style={{ fontSize: 48, marginBottom: 16 }}>{c.emoji}</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: theme.brand, marginBottom: 8 }}>{c.title}</div>
              <div style={{ fontSize: 15, color: theme.muted, lineHeight: 1.5 }}>{c.desc}</div>
              <div style={{ marginTop: 20, fontSize: 13, fontWeight: 600, color: theme.accent }}>
                Open {c.title} →
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

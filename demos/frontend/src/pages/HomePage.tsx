import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../services/auth';
import { useDemoConfig } from '../services/demo';
import { type Deck, listDecks } from '../services/decksApi';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
};

const cards: { to: string; emoji: string; title: string; desc: string; adminOnly?: boolean }[] = [
  {
    to: '/decks',
    emoji: '📚',
    title: 'Decks',
    desc: 'Upload, browse and publish your decks. The live avatar presents any of them, slide by slide.',
  },
  {
    to: '/search',
    emoji: '🔎',
    title: 'Search',
    desc: 'Ask anything across all your decks. The AI finds the right slide and the avatar presents it.',
    adminOnly: true,
  },
  {
    to: '/playlists',
    emoji: '📻',
    title: 'Playlists',
    desc: 'Chain decks into ordered playlists. Progress is tracked so you can resume anytime.',
    adminOnly: true,
  },
  {
    to: '/live',
    emoji: '🎙️',
    title: 'Live',
    desc: 'Drop a single .pptx and let the live avatar present it, with Q&A grounded in the slides.',
    adminOnly: true,
  },
  {
    to: '/video/library',
    emoji: '🎞️',
    title: 'Video',
    desc: 'Narrated avatar videos rendered from your decks, with subtitles and a SCORM package.',
  },
  {
    to: '/podcast/library',
    emoji: '🎧',
    title: 'Podcast',
    desc: 'Two avatars discuss your document in a podcast-style conversation.',
  },
];

export default function HomePage() {
  const navigate = useNavigate();
  const auth = useAuth();
  const locked = !auth.loading && !auth.is_admin;
  const demo = useDemoConfig();
  const [demoDeck, setDemoDeck] = useState<Deck | null>(null);

  // Surface the anonymous live avatar demo when at least one deck allows it.
  useEffect(() => {
    if (!locked || !demo.enabled) return;
    let cancelled = false;
    listDecks()
      .then((ds) => { if (!cancelled) setDemoDeck(ds.find((d) => d.live_demo) ?? null); })
      .catch(() => { /* home stays usable without the demo link */ });
    return () => { cancelled = true; };
  }, [locked, demo.enabled]);
  return (
    <div style={{ minHeight: 'calc(100vh - 60px)', background: theme.cardAlt, padding: '56px 24px' }}>
      <div style={{ maxWidth: 960, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1.5, color: theme.accent, textTransform: 'uppercase' }}>
            DeckFM
          </div>
          <h1 style={{ margin: '8px 0 12px', fontSize: 38, color: theme.brand, fontWeight: 800 }}>
            AI avatars that present, narrate and podcast your decks
          </h1>
          <p style={{ fontSize: 17, color: theme.muted, maxWidth: 620, margin: '0 auto', lineHeight: 1.55 }}>
            Upload your decks once. Ask questions anytime. The avatar presents the exact slide that answers you.
          </p>
        </div>

        {demoDeck && (
          <div style={{ textAlign: 'center', marginTop: -24, marginBottom: 36 }}>
            <button
              type="button"
              data-testid="home-try-live-demo"
              onClick={() => navigate(`/decks/${demoDeck.deck_id}/present`)}
              style={{
                background: '#9a3412', color: 'white', border: 'none', borderRadius: 999,
                padding: '12px 26px', fontSize: 16, fontWeight: 700, cursor: 'pointer',
                boxShadow: '0 6px 18px rgba(154, 52, 18, 0.25)',
              }}
            >
              🎙️ Try the live avatar demo →
            </button>
            <div style={{ fontSize: 12.5, color: theme.muted, marginTop: 8 }}>
              Narration-only · up to {Math.max(1, Math.round(demo.session_seconds / 60))} min · no sign-in needed
            </div>
          </div>
        )}

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
                {locked && c.adminOnly ? '🔒 Sign-in required' : `Open ${c.title} →`}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

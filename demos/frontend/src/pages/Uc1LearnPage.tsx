import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SearchResult, searchDecks } from '../services/uc1Api';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
};

const EXAMPLES = [
  'How do we prevent phishing?',
  'What is GDPR?',
  'Explain our incident response process',
];

export default function Uc1LearnPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(q: string) {
    const qv = q.trim();
    if (!qv) return;
    setQuery(qv);
    setLoading(true);
    setError(null);
    try {
      const r = await searchDecks(qv, 5);
      setResults(r.results || []);
    } catch (e: any) {
      setError(String(e?.message ?? e));
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  function present(r: SearchResult) {
    navigate(`/uc1/present/${r.deck_id}?slide=${r.slide_index}&autoplay=1`);
  }

  return (
    <div style={{ minHeight: 'calc(100vh - 60px)', background: theme.cardAlt, padding: '32px 24px' }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1.5, color: theme.accent, textTransform: 'uppercase' }}>
            UC1 · Learn
          </div>
          <h1 style={{ margin: '6px 0 4px', fontSize: 28, color: theme.brand, fontWeight: 800 }}>
            Ask anything about your training decks
          </h1>
          <p style={{ color: theme.muted, margin: 0 }}>
            We'll find the matching slide and the avatar will present it to you.
          </p>
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); submit(query); }}
          style={{
            display: 'flex', gap: 10, alignItems: 'center',
            background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 12,
            padding: 8, boxShadow: theme.shadow, marginBottom: 20,
          }}
        >
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask anything about your training decks…"
            style={{
              flex: 1, border: 'none', outline: 'none', fontSize: 16,
              padding: '12px 14px', background: 'transparent', color: theme.text,
            }}
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            style={{
              padding: '12px 22px', border: 'none', borderRadius: 8,
              background: theme.brandLight, color: 'white', fontWeight: 600, fontSize: 14,
              cursor: loading ? 'progress' : 'pointer',
              opacity: loading || !query.trim() ? 0.6 : 1,
            }}
          >
            {loading ? 'Searching…' : 'Search'}
          </button>
        </form>

        {error && (
          <div style={{ background: '#fee2e2', color: '#991b1b', padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
            {error}
          </div>
        )}

        {loading && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <div
              style={{
                width: 36, height: 36, borderRadius: '50%',
                border: `3px solid ${theme.border}`, borderTopColor: theme.accent,
                animation: 'uc1-spin 0.8s linear infinite',
              }}
            />
            <style>{'@keyframes uc1-spin { to { transform: rotate(360deg); } }'}</style>
          </div>
        )}

        {!loading && results === null && (
          <div style={{ textAlign: 'center', padding: '32px 16px', color: theme.muted }}>
            <div style={{ fontSize: 14, marginBottom: 12 }}>
              Try: {EXAMPLES.map((e, i) => (
                <React.Fragment key={e}>
                  {i > 0 && ' · '}
                  <button
                    type="button"
                    onClick={() => submit(e)}
                    style={{
                      border: `1px solid ${theme.border}`, background: theme.card,
                      color: theme.brandLight, padding: '4px 10px', borderRadius: 999,
                      fontSize: 13, cursor: 'pointer', margin: '4px 2px',
                    }}
                  >
                    {e}
                  </button>
                </React.Fragment>
              ))}
            </div>
          </div>
        )}

        {!loading && results !== null && results.length === 0 && (
          <div style={{ textAlign: 'center', padding: 40, color: theme.muted, background: theme.card, borderRadius: 12, border: `1px solid ${theme.border}` }}>
            No results. Try rephrasing, or upload more decks in <a href="/uc1/decks" style={{ color: theme.accent }}>Decks</a>.
          </div>
        )}

        {!loading && results && results.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {results.map((r, idx) => (
              <div
                key={`${r.deck_id}-${r.slide_index}-${idx}`}
                style={{
                  background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 12,
                  padding: 18, boxShadow: theme.shadow,
                  display: 'flex', flexDirection: 'column', gap: 8,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <div style={{ fontSize: 12, color: theme.muted, textTransform: 'uppercase', letterSpacing: 0.8, fontWeight: 600 }}>
                    {r.deck_title}
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 700, background: theme.cardAlt, color: theme.brandLight, padding: '2px 8px', borderRadius: 999, border: `1px solid ${theme.border}` }}>
                    Slide {r.slide_index + 1}
                  </span>
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, color: theme.brand, lineHeight: 1.3 }}>
                  {r.slide_title || `Slide ${r.slide_index + 1}`}
                </div>
                <div
                  style={{
                    fontSize: 14, color: theme.text, lineHeight: 1.55,
                    display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical',
                    overflow: 'hidden', textOverflow: 'ellipsis',
                  }}
                >
                  {r.snippet}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
                  <div style={{ fontSize: 11, color: theme.muted }}>
                    score {r.score?.toFixed?.(2) ?? r.score}
                  </div>
                  <button
                    onClick={() => present(r)}
                    style={{
                      padding: '8px 16px', border: 'none', borderRadius: 8,
                      background: theme.brandLight, color: 'white', fontWeight: 600, fontSize: 13, cursor: 'pointer',
                    }}
                  >
                    🎙️ Present this slide
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

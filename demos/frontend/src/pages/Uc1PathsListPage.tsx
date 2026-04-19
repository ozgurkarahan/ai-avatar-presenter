import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Deck, listDecks,
  PathSummary, PathStepInput, listPaths, createPath, deletePath,
} from '../services/uc1Api';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
  danger: '#dc2626',
};

export default function Uc1PathsListPage() {
  const navigate = useNavigate();
  const [paths, setPaths] = useState<PathSummary[] | null>(null);
  const [decks, setDecks] = useState<Deck[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [pp, dd] = await Promise.all([listPaths(), listDecks()]);
      setPaths(pp);
      setDecks(dd);
    } catch (e: any) {
      setError(String(e?.message ?? e));
      setPaths([]);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function handleDelete(id: string, title: string) {
    if (!confirm(`Delete path "${title}"?`)) return;
    setDeleting(id);
    try {
      await deletePath(id);
      await refresh();
    } catch (e: any) {
      setError(`Delete failed: ${e?.message ?? e}`);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div style={{ minHeight: 'calc(100vh - 60px)', background: theme.cardAlt, padding: '40px 24px' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <button
          onClick={() => navigate('/uc1')}
          style={{
            background: 'transparent', border: 'none', color: theme.brandLight,
            cursor: 'pointer', fontSize: 13, marginBottom: 12, padding: 0,
          }}
        >
          ← Back to hub
        </button>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1.5, color: theme.accent, textTransform: 'uppercase' }}>
              UC1 · Learning Paths
            </div>
            <h1 style={{ margin: '4px 0 6px', fontSize: 30, color: theme.brand, fontWeight: 800 }}>
              Sequenced learning journeys
            </h1>
            <p style={{ margin: 0, fontSize: 14, color: theme.muted }}>
              Chain multiple decks into an ordered path. Learners resume where they left off, progress is tracked.
            </p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            disabled={decks.length === 0}
            style={{
              background: theme.brand, color: 'white', border: 'none',
              borderRadius: 8, padding: '10px 18px', fontSize: 14, fontWeight: 600,
              cursor: decks.length === 0 ? 'not-allowed' : 'pointer',
              opacity: decks.length === 0 ? 0.5 : 1,
            }}
          >
            + Create path
          </button>
        </div>

        {error && (
          <div style={{ background: '#fee2e2', color: '#991b1b', padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
            {error}
          </div>
        )}

        {paths === null && <div style={{ color: theme.muted, padding: 40, textAlign: 'center' }}>Loading…</div>}

        {paths && paths.length === 0 && (
          <div style={{ background: theme.card, border: `1px dashed ${theme.border}`, borderRadius: 12, padding: 48, textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>🛤️</div>
            <div style={{ fontSize: 17, fontWeight: 700, color: theme.brand, marginBottom: 6 }}>No learning paths yet</div>
            <div style={{ fontSize: 14, color: theme.muted, marginBottom: 20 }}>
              {decks.length === 0
                ? 'Upload some decks first, then you can chain them into a path.'
                : 'Click “Create path” to combine 2 or more decks into a sequenced learning journey.'}
            </div>
          </div>
        )}

        {paths && paths.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
            {paths.map((p) => (
              <div
                key={p.id}
                style={{
                  background: theme.card, border: `1px solid ${theme.border}`,
                  borderRadius: 12, padding: 20, boxShadow: theme.shadow,
                  display: 'flex', flexDirection: 'column', gap: 10,
                  borderLeftWidth: 4, borderLeftColor: p.status === 'broken' ? theme.danger : theme.accent,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: theme.brand }}>{p.title}</h3>
                  {p.status === 'broken' && (
                    <span style={{ fontSize: 11, fontWeight: 700, color: theme.danger, background: '#fee2e2', padding: '2px 8px', borderRadius: 4 }}>
                      BROKEN
                    </span>
                  )}
                </div>
                {p.description && (
                  <p style={{ margin: 0, fontSize: 13, color: theme.muted, lineHeight: 1.5 }}>{p.description}</p>
                )}
                <div style={{ fontSize: 12, color: theme.muted }}>
                  {p.step_count} deck{p.step_count === 1 ? '' : 's'}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button
                    onClick={() => navigate(`/uc1/paths/${p.id}`)}
                    disabled={p.status === 'broken'}
                    style={{
                      background: p.status === 'broken' ? theme.border : theme.brand,
                      color: p.status === 'broken' ? theme.muted : 'white',
                      border: 'none', borderRadius: 6, padding: '8px 14px',
                      fontSize: 13, fontWeight: 600,
                      cursor: p.status === 'broken' ? 'not-allowed' : 'pointer',
                      flex: 1,
                    }}
                  >
                    {p.status === 'broken' ? 'Unavailable' : 'Open path →'}
                  </button>
                  <button
                    onClick={() => handleDelete(p.id, p.title)}
                    disabled={deleting === p.id}
                    style={{
                      background: 'white', color: theme.danger,
                      border: `1px solid ${theme.border}`, borderRadius: 6,
                      padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                    }}
                  >
                    {deleting === p.id ? '…' : '🗑'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <CreatePathModal
          decks={decks}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); refresh(); }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create-path modal
// ---------------------------------------------------------------------------
function CreatePathModal({
  decks, onClose, onCreated,
}: { decks: Deck[]; onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function toggle(deckId: string) {
    setSelected((s) => s.includes(deckId) ? s.filter((x) => x !== deckId) : [...s, deckId]);
  }
  function move(idx: number, delta: number) {
    const next = [...selected];
    const j = idx + delta;
    if (j < 0 || j >= next.length) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    setSelected(next);
  }

  async function submit() {
    if (!title.trim() || selected.length === 0) {
      setErr('Title and at least one deck are required.');
      return;
    }
    setSaving(true); setErr(null);
    try {
      const steps: PathStepInput[] = selected.map((deck_id, order) => ({ deck_id, order, required: true }));
      await createPath({ title: title.trim(), description: description.trim(), steps });
      onCreated();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: theme.card, borderRadius: 14, padding: 28,
          maxWidth: 620, width: '100%', maxHeight: '88vh', overflowY: 'auto',
          boxShadow: '0 20px 50px rgba(0,0,0,0.3)',
        }}
      >
        <h2 style={{ margin: '0 0 18px', color: theme.brand, fontSize: 22 }}>Create learning path</h2>

        <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: theme.muted, marginBottom: 4 }}>
          TITLE *
        </label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. Security Onboarding"
          style={{ width: '100%', padding: '10px 12px', border: `1px solid ${theme.border}`, borderRadius: 8, fontSize: 14, marginBottom: 14 }}
        />

        <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: theme.muted, marginBottom: 4 }}>
          DESCRIPTION
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Short description…"
          rows={2}
          style={{ width: '100%', padding: '10px 12px', border: `1px solid ${theme.border}`, borderRadius: 8, fontSize: 14, marginBottom: 14, resize: 'vertical' }}
        />

        <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: theme.muted, marginBottom: 8 }}>
          STEPS (in order) *
        </label>

        {selected.length > 0 && (
          <div style={{ marginBottom: 12, border: `1px solid ${theme.border}`, borderRadius: 8, padding: 8, background: theme.cardAlt }}>
            {selected.map((deckId, idx) => {
              const d = decks.find((x) => x.deck_id === deckId);
              return (
                <div key={deckId} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 4px' }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: theme.accent, minWidth: 24 }}>#{idx + 1}</span>
                  <span style={{ flex: 1, fontSize: 13 }}>{d?.title ?? deckId}</span>
                  <button onClick={() => move(idx, -1)} disabled={idx === 0} style={{ border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 16 }}>↑</button>
                  <button onClick={() => move(idx, 1)} disabled={idx === selected.length - 1} style={{ border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 16 }}>↓</button>
                  <button onClick={() => toggle(deckId)} style={{ border: 'none', background: 'transparent', color: theme.danger, cursor: 'pointer', fontSize: 14 }}>✕</button>
                </div>
              );
            })}
          </div>
        )}

        <div style={{ maxHeight: 200, overflowY: 'auto', border: `1px solid ${theme.border}`, borderRadius: 8, padding: 4 }}>
          {decks.filter((d) => !selected.includes(d.deck_id)).map((d) => (
            <button
              key={d.deck_id}
              onClick={() => toggle(d.deck_id)}
              style={{
                display: 'flex', width: '100%', textAlign: 'left',
                alignItems: 'center', gap: 8, padding: '8px 10px',
                border: 'none', background: 'transparent', cursor: 'pointer',
                borderRadius: 6, fontSize: 13,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = theme.cardAlt; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              <span style={{ color: theme.accent, fontWeight: 700 }}>+</span>
              <span style={{ flex: 1 }}>{d.title}</span>
              <span style={{ fontSize: 11, color: theme.muted }}>{d.slide_count} slides · {d.language}</span>
            </button>
          ))}
          {decks.filter((d) => !selected.includes(d.deck_id)).length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: theme.muted, fontSize: 13 }}>
              All decks added.
            </div>
          )}
        </div>

        {err && <div style={{ marginTop: 12, color: theme.danger, fontSize: 13 }}>{err}</div>}

        <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{ background: 'white', color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '10px 18px', fontSize: 14, cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={saving}
            style={{ background: theme.brand, color: 'white', border: 'none', borderRadius: 8, padding: '10px 22px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
          >
            {saving ? 'Creating…' : 'Create path'}
          </button>
        </div>
      </div>
    </div>
  );
}

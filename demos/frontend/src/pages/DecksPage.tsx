import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Deck, deleteDeck, listDecks, publishDeck, setDeckLiveDemo, uploadDeck } from '../services/decksApi';
import { useAuth } from '../services/auth';
import { useDemoConfig } from '../services/demo';
import { GateNotice, LiveDemoBadge, LiveDemoToggle, PublishBadge, PublishToggle } from '../components/AuthGate';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
};

export default function DecksPage() {
  const navigate = useNavigate();
  const [decks, setDecks] = useState<Deck[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const auth = useAuth();
  const isAdmin = auth.is_admin;
  const [publishing, setPublishing] = useState<string | null>(null);
  const [liveBusy, setLiveBusy] = useState<string | null>(null);
  const demo = useDemoConfig();
  const firstLiveDemo = decks?.find((d) => d.live_demo);
  const showDemoCta = !auth.loading && !isAdmin && demo.enabled && !!firstLiveDemo;

  const refresh = useCallback(async () => {
    setError(null);
    try { setDecks(await listDecks()); }
    catch (e: any) { setError(String(e?.message ?? e)); setDecks([]); }
  }, []);

  // Re-fetch once identity is known: admins also see drafts.
  useEffect(() => { if (!auth.loading) refresh(); }, [refresh, auth.loading, auth.is_admin]);

  async function handleTogglePublish(deckId: string, next: boolean) {
    setPublishing(deckId);
    try {
      const updated = await publishDeck(deckId, next);
      const published = typeof updated?.published === 'boolean' ? updated.published : next;
      // Unpublishing also switches the live demo off server-side.
      const live_demo = typeof updated?.live_demo === 'boolean' ? updated.live_demo : (published ? undefined : false);
      setDecks((prev) => prev?.map((d) => (d.deck_id === deckId
        ? { ...d, published, ...(live_demo === undefined ? {} : { live_demo }) }
        : d)) ?? null);
    } catch (e: any) {
      setError(`Publish update failed: ${e?.message ?? e}`);
    } finally {
      setPublishing(null);
    }
  }

  async function handleToggleLiveDemo(deckId: string, next: boolean) {
    setLiveBusy(deckId);
    try {
      const updated = await setDeckLiveDemo(deckId, next);
      const live_demo = typeof updated?.live_demo === 'boolean' ? updated.live_demo : next;
      setDecks((prev) => prev?.map((d) => (d.deck_id === deckId ? { ...d, live_demo } : d)) ?? null);
    } catch (e: any) {
      setError(`Live demo update failed: ${e?.message ?? e}`);
    } finally {
      setLiveBusy(null);
    }
  }

  async function handleFile(file: File) {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadDeck(file);
      await refresh();
    } catch (e: any) {
      setError(`Upload failed: ${e?.message ?? e}`);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  async function handleDelete(deckId: string) {
    if (!confirm('Delete this deck? This cannot be undone.')) return;
    setDeleting(deckId);
    try { await deleteDeck(deckId); await refresh(); }
    catch (e: any) { setError(`Delete failed: ${e?.message ?? e}`); }
    finally { setDeleting(null); }
  }

  return (
    <div style={{ minHeight: 'calc(100vh - 60px)', background: theme.cardAlt, padding: '32px 24px' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1.5, color: theme.accent, textTransform: 'uppercase' }}>
            DeckFM · Decks
          </div>
          <h1 style={{ margin: '6px 0 4px', fontSize: 28, color: theme.brand, fontWeight: 800 }}>Decks</h1>
          <p style={{ color: theme.muted, margin: 0 }}>
            {isAdmin
              ? 'Upload .pptx files to make them searchable and presentable by the avatar. Publish a deck to make it visible to anonymous visitors.'
              : 'Browse the published decks slide by slide.'}
          </p>
        </div>

        {showDemoCta && firstLiveDemo && (
          <button
            type="button"
            data-testid="try-live-demo-cta"
            onClick={() => navigate(`/decks/${firstLiveDemo.deck_id}/present`)}
            style={{
              display: 'flex', alignItems: 'center', gap: 12, width: '100%', textAlign: 'left',
              background: 'linear-gradient(90deg, #fff7ed, #ffffff)', border: '1px solid #fdba74',
              borderRadius: 12, padding: '14px 18px', marginBottom: 16, cursor: 'pointer', color: theme.text,
            }}
          >
            <span style={{ fontSize: 26 }} aria-hidden>🎙️</span>
            <span style={{ flex: 1 }}>
              <span style={{ display: 'block', fontWeight: 700, color: '#9a3412', fontSize: 15 }}>Try the live avatar demo →</span>
              <span style={{ fontSize: 13, color: theme.muted }}>
                Watch the real-time avatar narrate “{firstLiveDemo.title}”. No sign-in needed.
              </span>
            </span>
          </button>
        )}

        {!auth.loading && !isAdmin && (
          <GateNotice action="upload decks and let the live avatar present them" style={{ marginBottom: 24 }} />
        )}

        {/* Upload zone */}
        {isAdmin && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const f = e.dataTransfer.files?.[0];
            if (f) handleFile(f);
          }}
          onClick={() => inputRef.current?.click()}
          style={{
            background: dragOver ? '#f0f9ff' : theme.card,
            border: `2px dashed ${dragOver ? theme.accent : theme.border}`,
            borderRadius: 14,
            padding: '36px 24px',
            textAlign: 'center',
            cursor: uploading ? 'progress' : 'pointer',
            marginBottom: 24,
            transition: 'border-color 0.15s, background 0.15s',
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
            style={{ display: 'none' }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
          <div style={{ fontSize: 42, marginBottom: 8 }}>{uploading ? '⏳' : '📤'}</div>
          <div style={{ fontSize: 17, fontWeight: 600, color: theme.brand }}>
            {uploading ? 'Uploading…' : 'Drop a .pptx here or click to browse'}
          </div>
          <div style={{ fontSize: 13, color: theme.muted, marginTop: 6 }}>
            We'll extract slides, index them for search, and keep them ready to present.
          </div>
        </div>
        )}

        {error && (
          <div style={{ background: '#fee2e2', color: '#991b1b', padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
            {error}
          </div>
        )}

        {/* Deck grid */}
        {decks === null ? (
          <div style={{ color: theme.muted, textAlign: 'center', padding: 40 }}>Loading decks…</div>
        ) : decks.length === 0 ? (
          <div style={{ color: theme.muted, textAlign: 'center', padding: 40, background: theme.card, borderRadius: 12, border: `1px solid ${theme.border}` }}>
            {isAdmin ? 'No decks yet. Upload a .pptx above to get started.' : 'No published decks yet. Check back later.'}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
            {decks.map((d) => (
              <div
                key={d.deck_id}
                style={{
                  background: theme.card,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 12,
                  padding: 18,
                  boxShadow: theme.shadow,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: theme.brand, lineHeight: 1.3, flex: 1, wordBreak: 'break-word' }}>
                    {d.title}
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 600, background: theme.cardAlt, color: theme.muted, padding: '2px 8px', borderRadius: 999, border: `1px solid ${theme.border}`, whiteSpace: 'nowrap' }}>
                    {d.language || '—'}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: theme.muted }}>
                  {d.slide_count} slide{d.slide_count === 1 ? '' : 's'}
                  {d.uploaded_at ? ` · ${new Date(d.uploaded_at).toLocaleDateString()}` : ''}
                </div>
                {isAdmin ? (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <PublishBadge published={d.published} />
                      <LiveDemoBadge liveDemo={d.live_demo} />
                    </span>
                    <span style={{ display: 'flex', gap: 6 }}>
                      <PublishToggle
                        published={d.published}
                        busy={publishing === d.deck_id}
                        onToggle={(next) => handleTogglePublish(d.deck_id, next)}
                      />
                      <LiveDemoToggle
                        liveDemo={d.live_demo}
                        published={d.published}
                        busy={liveBusy === d.deck_id}
                        onToggle={(next) => handleToggleLiveDemo(d.deck_id, next)}
                      />
                    </span>
                  </div>
                ) : demo.enabled && d.live_demo ? (
                  <div><LiveDemoBadge liveDemo={d.live_demo} /></div>
                ) : null}
                {d.tags && d.tags.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {d.tags.map((t) => (
                      <span key={t} style={{ fontSize: 11, background: '#eff6ff', color: theme.brandLight, padding: '2px 7px', borderRadius: 4 }}>
                        #{t}
                      </span>
                    ))}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8, marginTop: 'auto' }}>
                  <button
                    onClick={() => navigate(`/decks/${d.deck_id}/present`)}
                    style={{
                      flex: 1, padding: '8px 12px', border: 'none', borderRadius: 6,
                      background: theme.brandLight, color: 'white', fontWeight: 600, fontSize: 13, cursor: 'pointer',
                    }}
                  >
                    {isAdmin ? '🎙️ Present' : demo.enabled && d.live_demo ? '🎙️ View & try live demo' : '👀 View slides'}
                  </button>
                  {isAdmin && (
                  <button
                    onClick={() => handleDelete(d.deck_id)}
                    disabled={deleting === d.deck_id}
                    style={{
                      padding: '8px 12px', border: `1px solid ${theme.border}`, borderRadius: 6,
                      background: 'white', color: '#c0392b', fontWeight: 600, fontSize: 13,
                      cursor: deleting === d.deck_id ? 'progress' : 'pointer',
                      opacity: deleting === d.deck_id ? 0.6 : 1,
                    }}
                  >
                    {deleting === d.deck_id ? '…' : '🗑'}
                  </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

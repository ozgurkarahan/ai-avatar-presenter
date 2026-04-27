import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LibraryItem, LibrarySummary,
  deleteLibraryItem, getLibraryItem, listLibrary,
} from '../services/staticVideoApi';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
};

function fmtDuration(sec: number | null): string {
  if (!sec || sec <= 0) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec - m * 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

export default function StaticVideoLibraryPage() {
  const [items, setItems] = useState<LibrarySummary[] | null>(null);
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [loadingItem, setLoadingItem] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      const rows = await listLibrary();
      setItems(rows);
    } catch (e: any) {
      setError(String(e?.message ?? e));
      setItems([]);
    }
  }

  useEffect(() => { refresh(); }, []);

  // Auto-open via ?job=<id>
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const jid = q.get('job');
    if (jid) open(jid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function open(jobId: string) {
    setLoadingItem(true);
    try {
      const item = await getLibraryItem(jobId);
      setSelected(item);
    } catch (e: any) {
      setError(`Failed to open: ${e?.message ?? e}`);
    } finally {
      setLoadingItem(false);
    }
  }

  async function remove(jobId: string) {
    if (!confirm('Delete this video permanently?')) return;
    setDeleting(jobId);
    try {
      await deleteLibraryItem(jobId);
      setItems((prev) => prev?.filter((i) => i.job_id !== jobId) ?? null);
      if (selected?.job_id === jobId) setSelected(null);
    } catch (e: any) {
      setError(`Delete failed: ${e?.message ?? e}`);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f7fa', color: theme.text }}>
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '28px 32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0, color: theme.brand }}>
              🎞️ Video Library
            </h1>
            <div style={{ color: theme.muted, fontSize: 14, marginTop: 4 }}>
              Narrated slide videos you've generated. Click any card to play.
            </div>
          </div>
          <button onClick={refresh} style={{
            background: theme.card, color: theme.brand, border: `1px solid ${theme.border}`,
            padding: '8px 16px', borderRadius: 8, cursor: 'pointer', fontWeight: 600,
          }}>↻ Refresh</button>
        </div>

        {error && (
          <div style={{ background: '#fee2e2', color: '#991b1b', padding: 12,
                        borderRadius: 8, marginBottom: 16 }}>{error}</div>
        )}

        {items === null ? (
          <div style={{ color: theme.muted, padding: 40, textAlign: 'center' }}>Loading…</div>
        ) : items.length === 0 ? (
          <EmptyState />
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 20,
          }}>
            {items.map((it) => (
              <Card
                key={it.job_id}
                item={it}
                onOpen={() => open(it.job_id)}
                onDelete={() => remove(it.job_id)}
                deleting={deleting === it.job_id}
              />
            ))}
          </div>
        )}
      </div>

      <AnimatePresence>
        {(selected || loadingItem) && (
          <PlayerModal
            item={selected}
            loading={loadingItem}
            onClose={() => setSelected(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function EmptyState() {
  return (
    <div style={{
      background: theme.card, borderRadius: 16, padding: 48,
      textAlign: 'center', boxShadow: theme.shadow,
    }}>
      <div style={{ fontSize: 52, marginBottom: 16 }}>🎬</div>
      <h2 style={{ margin: 0, color: theme.brand }}>No videos yet</h2>
      <p style={{ color: theme.muted, marginTop: 8 }}>
        Head to the Video Generator tab and create your first one — it will show up here.
      </p>
      <a href="/video" style={{
        display: 'inline-block', marginTop: 16,
        background: theme.brand, color: 'white',
        padding: '10px 22px', borderRadius: 8, textDecoration: 'none', fontWeight: 600,
      }}>
        + Create Video
      </a>
    </div>
  );
}

function Card({ item, onOpen, onDelete, deleting }: {
  item: LibrarySummary; onOpen: () => void; onDelete: () => void; deleting: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4, boxShadow: '0 10px 30px rgba(0,51,102,0.16)' }}
      style={{
        background: theme.card, borderRadius: 14, overflow: 'hidden',
        boxShadow: theme.shadow, cursor: 'pointer', display: 'flex',
        flexDirection: 'column',
      }}
      onClick={onOpen}
    >
      <div style={{
        position: 'relative', aspectRatio: '16 / 9',
        background: `linear-gradient(135deg, ${theme.brand} 0%, ${theme.brandLight} 100%)`,
      }}>
        {item.thumbnail_url ? (
          <img src={item.thumbnail_url} alt=""
               style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            color: 'white', fontSize: 42,
          }}>🎬</div>
        )}
        <div style={{
          position: 'absolute', bottom: 8, right: 8,
          background: 'rgba(0,0,0,0.65)', color: 'white',
          padding: '2px 8px', borderRadius: 6, fontSize: 12, fontWeight: 600,
        }}>
          ⏱ {fmtDuration(item.duration_sec)}
        </div>
        <div style={{
          position: 'absolute', top: 8, left: 8,
          background: 'rgba(0, 51, 102, 0.9)', color: 'white',
          padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: 0.5,
        }}>
          🌍 {item.language}
        </div>
      </div>
      <div style={{ padding: 14, flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6, color: theme.text,
                      display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                      overflow: 'hidden', lineHeight: 1.3, minHeight: '2.6em' }}>
          {item.title}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
          <Chip>🗂 {item.slide_count} slide{item.slide_count === 1 ? '' : 's'}</Chip>
        </div>
        <div style={{ fontSize: 11, color: theme.muted, marginBottom: 8 }}>
          📅 {fmtDate(item.created_at)}
        </div>
        <div style={{ fontSize: 12, color: theme.muted, marginTop: 'auto',
                      display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                      borderTop: `1px solid ${theme.border}`, paddingTop: 8 }}>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            disabled={deleting}
            style={{
              background: 'transparent', border: 'none', color: '#ef4444',
              cursor: deleting ? 'wait' : 'pointer', fontSize: 14, padding: 4,
            }}
            title="Delete"
          >
            {deleting ? '…' : '🗑'}
          </button>
        </div>
      </div>
    </motion.div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span style={{
      background: theme.cardAlt, color: theme.brand,
      padding: '3px 9px', borderRadius: 12, fontSize: 11, fontWeight: 600,
      border: `1px solid ${theme.border}`,
    }}>{children}</span>
  );
}

function PlayerModal({ item, loading, onClose }: {
  item: LibraryItem | null; loading: boolean; onClose: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 20,
      }}
    >
      <motion.div
        initial={{ scale: 0.95, y: 16 }} animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 16 }}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#000', borderRadius: 14, overflow: 'hidden',
          maxWidth: 1100, width: '100%', maxHeight: '92vh',
          display: 'flex', flexDirection: 'column',
          boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        }}
      >
        {loading || !item ? (
          <div style={{ padding: 80, color: 'white', textAlign: 'center' }}>Loading…</div>
        ) : (
          <>
            <div style={{ position: 'relative', background: '#000' }}>
              {item.video_url ? (
                <video
                  src={item.video_url}
                  controls autoPlay
                  style={{ width: '100%', maxHeight: '70vh', display: 'block' }}
                />
              ) : (
                <div style={{ padding: 80, color: 'white', textAlign: 'center' }}>
                  Video unavailable
                </div>
              )}
              <button onClick={onClose} style={{
                position: 'absolute', top: 12, right: 12,
                background: 'rgba(0,0,0,0.7)', color: 'white',
                border: 'none', borderRadius: '50%', width: 36, height: 36,
                cursor: 'pointer', fontSize: 16,
              }}>✕</button>
            </div>
            <div style={{ padding: 18, background: theme.card, color: theme.text }}>
              <h3 style={{ margin: 0, fontSize: 18 }}>{item.title}</h3>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
                <Chip>📅 {fmtDate(item.created_at)}</Chip>
                <Chip>⏱ {fmtDuration(item.duration_sec)}</Chip>
                <Chip>🌍 {item.language}</Chip>
                <Chip>🗂 {item.slide_count} slides</Chip>
              </div>
              <div style={{ marginTop: 14, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                {item.video_url && (
                  <a href={item.video_url} download={`${item.title}.mp4`} style={btn('primary')}>
                    ⬇ Download MP4
                  </a>
                )}
                {item.audio_url && (
                  <a href={item.audio_url} download={`${item.title}.mp3`} style={btn('secondary')}>
                    ⬇ Audio
                  </a>
                )}
                {item.srt_url && (
                  <a href={item.srt_url} download={`${item.title}.srt`} style={btn('secondary')}>
                    ⬇ Subtitles
                  </a>
                )}
                {item.scorm_url && (
                  <a href={item.scorm_url} download={`${item.title}-scorm.zip`} style={btn('secondary')}>
                    📦 SCORM
                  </a>
                )}
              </div>
            </div>
          </>
        )}
      </motion.div>
    </motion.div>
  );
}

function btn(variant: 'primary' | 'secondary'): React.CSSProperties {
  const primary = variant === 'primary';
  return {
    padding: '8px 16px', borderRadius: 8, textDecoration: 'none', fontWeight: 600,
    fontSize: 13,
    background: primary ? theme.brand : theme.cardAlt,
    color: primary ? 'white' : theme.brand,
    border: primary ? 'none' : `1px solid ${theme.border}`,
  };
}

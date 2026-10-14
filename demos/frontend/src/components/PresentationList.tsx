import React, { useEffect, useState } from 'react';
import { listPresentations, getSlides, deletePresentation, sharePresentation, type PresentationListItem, type Presentation } from '../services/api';

interface Props {
  onSelect: (presentation: Presentation) => void;
}

const styles: Record<string, React.CSSProperties> = {
  container: { marginTop: '24px' },
  heading: { fontSize: '16px', fontWeight: 600, marginBottom: '12px' },
  list: { listStyle: 'none', padding: 0, margin: 0 },
  item: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    marginBottom: '8px',
    borderRadius: '8px',
    background: '#f0f4f8',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  itemHover: { background: '#dce6f0' },
  name: { fontWeight: 500, fontSize: '14px' },
  badge: {
    fontSize: '12px',
    color: '#555',
    background: '#e0e0e0',
    borderRadius: '12px',
    padding: '2px 10px',
  },
  actions: {
    display: 'flex',
    gap: '6px',
    alignItems: 'center',
  },
  actionBtn: {
    padding: '4px 10px',
    border: 'none',
    borderRadius: '5px',
    fontSize: '12px',
    cursor: 'pointer',
    fontWeight: 500,
  },
  deleteBtn: {
    background: '#fee2e2',
    color: '#b91c1c',
  },
  shareBtn: {
    background: '#e0edff',
    color: '#1d4ed8',
  },
  empty: { color: '#999', fontSize: '13px', fontStyle: 'italic' as const },
  loading: { color: '#888', fontSize: '13px' },
};

export default function PresentationList({ onSelect }: Props) {
  const [items, setItems] = useState<PresentationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refreshList = () => {
    listPresentations()
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { refreshList(); }, []);

  const handleDelete = async (e: React.MouseEvent, item: PresentationListItem) => {
    e.stopPropagation();
    if (!confirm(`Delete "${item.filename}"? This will remove it from storage permanently.`)) return;
    setDeletingId(item.id);
    try {
      await deletePresentation(item.id);
      setItems((prev) => prev.filter((p) => p.id !== item.id));
    } catch (err) {
      console.error('Failed to delete:', err);
    } finally {
      setDeletingId(null);
    }
  };

  const handleShare = async (e: React.MouseEvent, item: PresentationListItem) => {
    e.stopPropagation();
    try {
      const result = await sharePresentation(item.id);
      alert(result.message || 'Sharing is not yet available.');
    } catch (err) {
      console.error('Failed to share:', err);
    }
  };

  const handleSelect = async (item: PresentationListItem) => {
    setLoadingId(item.id);
    try {
      const presentation = await getSlides(item.id);
      onSelect(presentation);
    } catch (err) {
      console.error('Failed to load presentation:', err);
    } finally {
      setLoadingId(null);
    }
  };

  if (loading) return <div style={styles.loading}>Loading saved presentations...</div>;
  if (items.length === 0) return null;

  return (
    <div style={styles.container}>
      <div style={styles.heading}>Or choose a saved presentation:</div>
      <ul style={styles.list}>
        {items.map((item) => (
          <li
            key={item.id}
            style={hoveredId === item.id ? { ...styles.item, ...styles.itemHover } : styles.item}
            onMouseEnter={() => setHoveredId(item.id)}
            onMouseLeave={() => setHoveredId(null)}
            onClick={() => handleSelect(item)}
          >
            <span style={styles.name}>
              {loadingId === item.id ? 'Loading...' : deletingId === item.id ? 'Deleting...' : item.filename}
            </span>
            <div style={styles.actions}>
              <span style={styles.badge}>{item.slide_count} slides</span>
              <button
                style={{ ...styles.actionBtn, ...styles.shareBtn }}
                onClick={(e) => handleShare(e, item)}
                title="Share presentation"
              >
                🔗 Share
              </button>
              <button
                style={{ ...styles.actionBtn, ...styles.deleteBtn }}
                onClick={(e) => handleDelete(e, item)}
                disabled={deletingId === item.id}
                title="Delete presentation"
              >
                🗑️ Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

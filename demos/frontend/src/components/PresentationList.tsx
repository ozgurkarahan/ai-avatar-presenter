import React, { useEffect, useState } from 'react';
import { Presentation as DeckIcon, Share2, Trash2 } from 'lucide-react';
import { listPresentations, getSlides, deletePresentation, sharePresentation, type PresentationListItem, type Presentation } from '../services/api';
import { Button, Spinner, humanizeTitle, pluralize } from '../ui';
import '../styles/shared/presentation-list.css';

interface Props {
  onSelect: (presentation: Presentation) => void;
}

function deckTitle(filename: string): string {
  return humanizeTitle(filename.replace(/\.pptx$/i, ''));
}

export default function PresentationList({ onSelect }: Props) {
  const [items, setItems] = useState<PresentationListItem[]>([]);
  const [loading, setLoading] = useState(true);
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

  if (loading) return <Spinner label="Loading saved presentations…" />;
  if (items.length === 0) return null;

  return (
    <section className="deck-picker" aria-labelledby="deck-picker-title">
      <h3 id="deck-picker-title" className="eyebrow deck-picker__title">Or choose a saved presentation</h3>
      <ul className="deck-picker__list">
        {items.map((item) => {
          const busy = loadingId === item.id || deletingId === item.id;
          const title = deckTitle(item.filename);
          return (
            <li key={item.id} className={['deck-picker__row', busy && 'is-busy'].filter(Boolean).join(' ')}>
              <button
                type="button"
                className="deck-picker__open"
                onClick={() => handleSelect(item)}
                title={item.filename}
                aria-label={`Open ${title}`}
              >
                <span className="deck-picker__icon" aria-hidden>
                  {busy ? <span className="spinner" /> : <DeckIcon />}
                </span>
                <span className="deck-picker__body">
                  <span className="deck-picker__name">{title}</span>
                  <span className="deck-picker__meta small muted tabular">
                    {loadingId === item.id ? 'Loading…' : deletingId === item.id ? 'Deleting…' : pluralize(item.slide_count, 'slide')}
                  </span>
                </span>
              </button>
              <div className="deck-picker__actions">
                <Button
                  size="sm"
                  variant="ghost"
                  iconOnly
                  icon={Share2}
                  onClick={(e) => handleShare(e, item)}
                  title="Share presentation"
                  aria-label={`Share ${title}`}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  iconOnly
                  icon={Trash2}
                  className="deck-picker__delete"
                  onClick={(e) => handleDelete(e, item)}
                  disabled={deletingId === item.id}
                  title="Delete presentation"
                  aria-label={`Delete ${title}`}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

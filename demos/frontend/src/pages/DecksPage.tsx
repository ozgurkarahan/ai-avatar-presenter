import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Eye, Layers, Mic, Play, Trash2 } from 'lucide-react';
import { Deck, deleteDeck, listDecks, publishDeck, setDeckLiveDemo, uploadDeck } from '../services/decksApi';
import { useAuth } from '../services/auth';
import { useDemoConfig } from '../services/demo';
import { pickDefaultAvatar, useAvatars } from '../services/avatars';
import { GateNotice, LiveDemoBadge, LiveDemoToggle, PublishBadge, PublishToggle } from '../components/AuthGate';
import {
  Alert, Button, Dropzone, EmptyState, EpisodeList, EpisodeRow, HostDisc, HostsMini, LivePill, PageHeader,
  SectionHead, Spinner, episodeNumber, formatDate, humanizeTitle, languageName, pluralize,
} from '../ui';
import '../styles/pages/decks.css';

const PPTX_ACCEPT = '.pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation';
const DECK_KIND = { icon: Mic, label: 'Live presentation' };

export default function DecksPage() {
  const navigate = useNavigate();
  const [decks, setDecks] = useState<Deck[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const auth = useAuth();
  const isAdmin = auth.is_admin;
  const [publishing, setPublishing] = useState<string | null>(null);
  const [liveBusy, setLiveBusy] = useState<string | null>(null);
  const demo = useDemoConfig();
  const { avatars } = useAvatars();
  const host = pickDefaultAvatar(avatars);
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
    <div className="container page decks-page">
      <PageHeader
        eyebrow="Library"
        title="Decks"
        lead={isAdmin
          ? 'Upload .pptx files to make them searchable and presentable by the avatar. Publish a deck to make it visible to anonymous visitors.'
          : 'Browse the published decks slide by slide.'}
      />

      {showDemoCta && firstLiveDemo && (
        <button
          type="button"
          data-testid="try-live-demo-cta"
          className="decks-demo"
          onClick={() => navigate(`/decks/${firstLiveDemo.deck_id}/present`)}
        >
          {host && <HostDisc host={host} size={72} speaking label="" className="decks-demo__disc" />}
          <span className="decks-demo__copy">
            <LivePill>Live demo · no sign-in</LivePill>
            <span className="decks-demo__title">Try the live avatar demo</span>
            <span className="decks-demo__text">
              {host?.display_name ? `Watch ${host.display_name}, the real-time avatar, narrate` : 'Watch the real-time avatar narrate'}
              {' '}<em>{humanizeTitle(firstLiveDemo.title)}</em>.
            </span>
          </span>
          <ArrowRight aria-hidden className="decks-demo__arrow" />
        </button>
      )}

      {!auth.loading && !isAdmin && (
        <GateNotice action="upload decks and let the live avatar present them" className="decks-gate" />
      )}

      {isAdmin && (
        <Dropzone
          className="decks-upload"
          onFile={handleFile}
          accept={PPTX_ACCEPT}
          busy={uploading}
          title="Drop a .pptx here or click to browse"
          busyTitle="Uploading…"
          hint="We'll extract slides, index them for search, and keep them ready to present."
          inputProps={{ 'data-testid': 'deck-upload-input', accept: PPTX_ACCEPT }}
        />
      )}

      {error && <Alert tone="error" className="decks-alert">{error}</Alert>}

      {decks === null ? (
        <div className="decks-state"><Spinner label="Loading decks…" /></div>
      ) : decks.length === 0 ? (
        <EmptyState icon={Layers} title={isAdmin ? 'No decks yet' : 'No published decks yet'}>
          {isAdmin ? 'Upload a .pptx above to get started.' : 'Check back later.'}
        </EmptyState>
      ) : (
        <section aria-labelledby="decks-list-title">
          <SectionHead
            title={<span id="decks-list-title">{isAdmin ? 'All decks' : 'Published decks'}</span>}
            aside={pluralize(decks.length, 'deck')}
          />
          <EpisodeList label="Decks" className="decks-list">
            {decks.map((d, i) => {
              const title = humanizeTitle(d.title);
              const to = `/decks/${d.deck_id}/present`;
              const live = demo.enabled && !!d.live_demo;
              const tags = d.tags && d.tags.length > 0 ? (
                <span className="decks-tags">
                  {d.tags.map((t) => <span key={t} className="decks-tag">#{t}</span>)}
                </span>
              ) : null;
              const extra = isAdmin ? (
                <>
                  <PublishBadge published={d.published} />
                  <LiveDemoBadge liveDemo={d.live_demo} />
                  <span className="decks-toggles">
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
                </>
              ) : live ? <LiveDemoBadge liveDemo={d.live_demo} /> : null;
              return (
                <EpisodeRow
                  key={d.deck_id}
                  data-testid="deck-card"
                  num={episodeNumber(i + 1)}
                  title={title}
                  to={to}
                  titleProps={{ title: d.title }}
                  meta={[
                    pluralize(d.slide_count, 'slide'),
                    languageName(d.language),
                    formatDate(d.uploaded_at),
                    tags,
                  ]}
                  kind={DECK_KIND}
                  hosts={host ? <HostsMini hosts={[host]} /> : null}
                  extra={extra}
                  actions={(
                    <>
                      <Button
                        size="sm"
                        data-testid="deck-open"
                        variant={d.live_demo && (isAdmin || demo.enabled) ? 'primary' : 'outline'}
                        icon={isAdmin ? Mic : live ? Play : Eye}
                        onClick={() => navigate(to)}
                      >
                        {isAdmin ? 'Present' : live ? 'Try live demo' : 'View slides'}
                      </Button>
                      {isAdmin && (
                        <Button
                          size="sm"
                          variant="danger"
                          iconOnly
                          icon={Trash2}
                          aria-label={`Delete deck ${title}`}
                          title="Delete deck"
                          busy={deleting === d.deck_id}
                          onClick={() => handleDelete(d.deck_id)}
                        />
                      )}
                    </>
                  )}
                />
              );
            })}
          </EpisodeList>
        </section>
      )}
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Captions, Download, GraduationCap, Headphones, Layers, Music, Package, Play, Plus, RotateCw, Trash2,
} from 'lucide-react';
import {
  AUDIENCE_LEVEL_LABELS, LibraryItem, LibrarySummary, toAudienceLevel,
  deleteLibraryItem, getLibraryItem, listLibrary, publishLibraryItem,
} from '../services/podcast';
import { useAuth } from '../services/auth';
import { type AvatarInfo, pickDefaultAvatar, useAvatars } from '../services/avatars';
import { GateNotice, PublishBadge, PublishToggle } from '../components/AuthGate';
import {
  Alert, Button, ButtonLink, Chip, EmptyState, EpisodeList, EpisodeRow, HostsMini, Modal, PageHeader, Spinner,
  buttonClass, episodeNumber, formatDate, formatDuration, humanizeTitle, languageName, pluralize,
} from '../ui';
import '../styles/pages/library.css';

const KIND = { icon: Headphones, label: 'Podcast' };

const duration = (sec: number | null | undefined) => (sec && sec > 0 ? formatDuration(sec) : '—');
const styleLabel = (style: string) => style.charAt(0).toUpperCase() + style.slice(1);
const speakersOf = (item: LibrarySummary) => item.speaker_names?.filter(Boolean) ?? [];
function audienceChip(level: unknown) {
  const lvl = toAudienceLevel(level);
  return lvl ? <Chip icon={GraduationCap} data-testid="audience-chip">{AUDIENCE_LEVEL_LABELS[lvl]} audience</Chip> : null;
}

export default function PodcastLibraryPage() {
  const auth = useAuth();
  const isAdmin = auth.is_admin;
  const { avatars } = useAvatars();
  const [publishing, setPublishing] = useState<string | null>(null);
  const [items, setItems] = useState<LibrarySummary[] | null>(null);
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [loadingItem, setLoadingItem] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Fallback pair when speaker names don't match a known avatar: default host + a contrasting co-host.
  const fallbackHosts = useMemo(() => {
    const lead = pickDefaultAvatar(avatars);
    const others = avatars.filter((a) => a.id !== lead?.id);
    const co = others.find((a) => a.gender !== lead?.gender && a.thumbnail_url)
      ?? others.find((a) => a.gender !== lead?.gender)
      ?? others[0];
    return [lead, co];
  }, [avatars]);

  const hostsFor = (item: LibrarySummary) => {
    const named = speakersOf(item)
      .map((name) => avatars.find((a) => a.display_name === name))
      .filter(Boolean) as AvatarInfo[];
    return named.length ? named : fallbackHosts;
  };

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

  // Re-fetch once identity is known: admins also see drafts.
  useEffect(() => { if (!auth.loading) refresh(); }, [auth.loading, auth.is_admin]);

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

  async function togglePublish(jobId: string, next: boolean) {
    setPublishing(jobId);
    try {
      const updated = await publishLibraryItem(jobId, next);
      const published = typeof updated?.published === 'boolean' ? updated.published : next;
      setItems((prev) => prev?.map((i) => (i.job_id === jobId ? { ...i, published } : i)) ?? null);
      setSelected((prev) => (prev && prev.job_id === jobId ? { ...prev, published } : prev));
    } catch (e: any) {
      setError(`Publish update failed: ${e?.message ?? e}`);
    } finally {
      setPublishing(null);
    }
  }

  async function remove(jobId: string) {
    if (!confirm('Delete this podcast permanently?')) return;
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

  const closePlayer = useCallback(() => setSelected(null), []);
  const videoUrl = selected?.mp4_url ?? selected?.video_url ?? null;

  return (
    <div className="container page library">
      <PageHeader
        eyebrow="Library"
        title="Podcasts"
        lead={isAdmin
          ? "All podcasts you've generated. Publish a podcast to make it visible to anonymous visitors."
          : 'Published two-host podcasts: our AI hosts discuss a document together. Pick an episode to play it.'}
        actions={(
          <>
            <Button variant="ghost" icon={RotateCw} onClick={refresh}>Refresh</Button>
            {isAdmin && <ButtonLink to="/podcast" variant="primary" icon={Plus}>Create podcast</ButtonLink>}
          </>
        )}
      />

      {error && <Alert tone="error" className="library__alert">{error}</Alert>}

      {items === null ? (
        <div className="library__loading"><Spinner label="Loading podcasts…" /></div>
      ) : items.length === 0 ? (
        <LibraryEmpty isAdmin={isAdmin} />
      ) : (
        <>
          <div className="library__count eyebrow">{pluralize(items.length, 'episode')}</div>
          <EpisodeList label="Podcasts" className="library-list">
            {items.map((it, i) => {
              const title = humanizeTitle(it.title);
              const speakers = speakersOf(it);
              return (
                <EpisodeRow
                  key={it.job_id}
                  data-testid="library-item"
                  className={['library-row', it.thumbnail_url && 'library-row--thumb', isAdmin && 'library-row--admin'].filter(Boolean).join(' ')}
                  num={episodeNumber(i + 1)}
                  title={title}
                  onOpen={() => open(it.job_id)}
                  meta={[
                    formatDate(it.created_at),
                    languageName(it.language),
                    speakers.length > 0 ? speakers.join(' & ') : null,
                    it.style ? styleLabel(it.style) : null,
                    audienceChip(it.audience_level),
                    isAdmin ? <PublishBadge published={it.published} /> : null,
                  ]}
                  kind={KIND}
                  hosts={<HostsMini hosts={hostsFor(it)} label={speakers.join(' and ') || undefined} />}
                  duration={duration(it.duration_sec)}
                  extra={it.thumbnail_url
                    ? <img className="library-thumb" src={it.thumbnail_url} alt="" loading="lazy" />
                    : undefined}
                  actions={(
                    <>
                      <Button
                        size="sm"
                        iconOnly
                        icon={Play}
                        variant={i === 0 ? 'primary' : 'outline'}
                        aria-label={`Play ${title}`}
                        onClick={() => open(it.job_id)}
                      />
                      {isAdmin && (
                        <>
                          <PublishToggle
                            published={it.published}
                            busy={publishing === it.job_id}
                            onToggle={(next) => togglePublish(it.job_id, next)}
                          />
                          <Button
                            size="sm"
                            iconOnly
                            variant="danger"
                            icon={Trash2}
                            busy={deleting === it.job_id}
                            aria-label={`Delete ${title}`}
                            title="Delete"
                            onClick={(e) => { e.stopPropagation(); remove(it.job_id); }}
                          />
                        </>
                      )}
                    </>
                  )}
                />
              );
            })}
          </EpisodeList>
        </>
      )}

      <Modal
        open={!!(selected || loadingItem)}
        onClose={closePlayer}
        label={selected ? humanizeTitle(selected.title) : 'Loading podcast'}
        variant="stage"
        className="library-player"
      >
        {loadingItem || !selected ? (
          <div className="library-player__status"><Spinner label="Loading podcast…" /></div>
        ) : (
          <>
            <div className="library-player__screen">
              {videoUrl ? (
                <video data-testid="library-player" src={videoUrl} controls autoPlay />
              ) : (
                <div className="library-player__status">Video unavailable</div>
              )}
            </div>
            <div className="library-player__info">
              <div className="eyebrow library-player__eyebrow"><Headphones aria-hidden />Podcast</div>
              <h2 className="library-player__title">{humanizeTitle(selected.title)}</h2>
              {selected.document_title && selected.document_title !== selected.title && (
                <p className="library-player__source">Source: {selected.document_title}</p>
              )}
              <div className="library-player__meta">
                <span>{formatDate(selected.created_at)}</span>
                <span>{duration(selected.duration_sec)}</span>
                <span>{languageName(selected.language)}</span>
                {selected.style && <span>{styleLabel(selected.style)}</span>}
                {audienceChip(selected.audience_level)}
                {typeof selected.turn_count === 'number' && <span>{pluralize(selected.turn_count, 'turn')}</span>}
                {speakersOf(selected).length > 0 && <span>{speakersOf(selected).join(' & ')}</span>}
              </div>
              <div className="library-player__downloads">
                {videoUrl && (
                  <a href={videoUrl} download={`${selected.title}.mp4`} className={buttonClass({ variant: 'primary', size: 'sm' })}>
                    <Download aria-hidden />Download MP4
                  </a>
                )}
                {selected.mp3_url && (
                  <a href={selected.mp3_url} download={`${selected.title}.mp3`} className={buttonClass({ size: 'sm' })}>
                    <Music aria-hidden />Audio MP3
                  </a>
                )}
                {selected.srt_url && (
                  <a href={selected.srt_url} download={`${selected.title}.srt`} className={buttonClass({ size: 'sm' })}>
                    <Captions aria-hidden />Subtitles SRT
                  </a>
                )}
                {selected.scorm_url && (
                  <a href={selected.scorm_url} download={`${selected.title}-scorm.zip`} className={buttonClass({ size: 'sm' })}>
                    <Package aria-hidden />SCORM package
                  </a>
                )}
              </div>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}

function LibraryEmpty({ isAdmin }: { isAdmin: boolean }) {
  if (!isAdmin) {
    return (
      <EmptyState
        icon={Headphones}
        title="No published podcasts yet"
        action={(
          <div className="library__empty-actions">
            <GateNotice action="create your own podcast" />
            <ButtonLink to="/decks" icon={Layers}>Browse decks</ButtonLink>
          </div>
        )}
      >
        Check back later — podcasts appear here once a demo user publishes them.
      </EmptyState>
    );
  }
  return (
    <EmptyState
      icon={Headphones}
      title="No podcasts yet"
      action={<ButtonLink to="/podcast" variant="primary" icon={Plus}>Create podcast</ButtonLink>}
    >
      Head to the podcast studio and generate your first one — it will appear here automatically.
    </EmptyState>
  );
}

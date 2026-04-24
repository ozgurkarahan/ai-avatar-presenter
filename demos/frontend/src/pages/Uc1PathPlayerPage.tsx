import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import SlideViewer from '../components/SlideViewer';
import AvatarPanel from '../components/AvatarPanel';
import LanguageSelector from '../components/LanguageSelector';
import { type Presentation } from '../services/api';
import {
  DeckDetail, getDeck,
  PathDetail, PathProgress,
  getPath, getProgress, postProgress, getOrCreateUserId,
  UC1_VOICES, UC1_LANGUAGE_LABELS, UC1_AVATARS, avatarForVoice,
} from '../services/uc1Api';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc', accentLight: '#e0f2fe',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
  success: '#16a34a', danger: '#dc2626',
};

function deckToPresentation(d: DeckDetail): Presentation {
  return {
    id: d.id ?? d.deck_id,
    filename: d.filename ?? d.title,
    slide_count: d.slide_count ?? d.slides?.length ?? 0,
    slides: d.slides ?? [],
  };
}

export default function Uc1PathPlayerPage() {
  const { pathId = '' } = useParams();
  const navigate = useNavigate();
  const userId = useMemo(() => getOrCreateUserId(), []);

  const [path, setPath] = useState<PathDetail | null>(null);
  const [progress, setProgress] = useState<PathProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gone, setGone] = useState(false);

  const [currentStep, setCurrentStep] = useState(0);
  const [deck, setDeck] = useState<DeckDetail | null>(null);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [language, setLanguage] = useState('en-US');
  const [videoPlaying, setVideoPlaying] = useState(false);
  const [autoPlayVideo, setAutoPlayVideo] = useState(false);
  const [selectedVoice, setSelectedVoice] = useState<string>(UC1_VOICES[1].id);
  const [selectedAvatar, setSelectedAvatar] = useState<string>('harry');
  const [started, setStarted] = useState(false);

  // Load path + progress, and initialize language once from the first deck
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getPath(pathId);
        if (cancelled) return;
        setPath(p);
        const pr = await getProgress(pathId, userId);
        if (cancelled) return;
        setProgress(pr);
        const idx = p.steps.findIndex((s) => s.deck_id === pr.resume_deck_id);
        if (idx >= 0) setCurrentStep(idx);
        // Initialize language & voice from the first step's deck (one-time)
        if (p.steps.length > 0) {
          try {
            const firstDeck = await getDeck(p.steps[0].deck_id);
            if (cancelled) return;
            if (firstDeck.language) {
              setLanguage(firstDeck.language);
              const match = UC1_VOICES.find((v) => v.language === firstDeck.language && v.gender === 'female');
              if (match) {
                setSelectedVoice(match.id);
                setSelectedAvatar(avatarForVoice(match.id, 'lisa'));
              }
            }
          } catch { /* non-fatal */ }
        }
      } catch (e: any) {
        if (e?.status === 410) setGone(true);
        else setError(e?.message ?? String(e));
      }
    })();
    return () => { cancelled = true; };
  }, [pathId, userId]);

  // Load current deck when step changes
  useEffect(() => {
    if (!path) return;
    const step = path.steps[currentStep];
    if (!step) return;
    let cancelled = false;
    setDeck(null);
    getDeck(step.deck_id)
      .then((d) => {
        if (cancelled) return;
        setDeck(d);
        // NOTE: do NOT overwrite language here — the user picks voice/avatar/language
        // once (in the banner) and it must stay stable across all steps of the path.
        // If this step matches resume and user clicked start, jump to resume slide
        if (started && progress && progress.resume_deck_id === step.deck_id) {
          setCurrentSlide(Math.max(0, Math.min(progress.resume_slide_index, (d.slides?.length ?? 1) - 1)));
        } else {
          setCurrentSlide(0);
        }
      })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path?.id, currentStep, started]);

  const recordProgress = useCallback(async (deckId: string, slideIndex: number) => {
    if (!pathId) return;
    try {
      const fresh = await postProgress(pathId, {
        user_id: userId, deck_id: deckId, slide_index: slideIndex,
      });
      setProgress(fresh);
    } catch (e) {
      // non-fatal — keep playing
      console.warn('progress post failed', e);
    }
  }, [pathId, userId]);

  function onSlideChange(idx: number) {
    setCurrentSlide(idx);
    if (deck) recordProgress(deck.deck_id ?? deck.id, idx);
  }

  function onVoiceChange(voiceId: string) {
    setSelectedVoice(voiceId);
    setSelectedAvatar(avatarForVoice(voiceId, selectedAvatar));
    const v = UC1_VOICES.find((x) => x.id === voiceId);
    if (v?.language) setLanguage(v.language);
  }

  function goToStep(idx: number) {
    if (!path) return;
    if (idx < 0 || idx >= path.steps.length) return;
    setCurrentStep(idx);
    setStarted(true);
  }

  const voicesByLang = useMemo(() => {
    const map = new Map<string, typeof UC1_VOICES>();
    UC1_VOICES.forEach((v) => {
      const arr = map.get(v.language) ?? [];
      arr.push(v);
      map.set(v.language, arr);
    });
    return map;
  }, []);

  const presentation = deck ? deckToPresentation(deck) : null;

  if (gone) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: theme.muted }}>
        <div style={{ fontSize: 56, marginBottom: 16 }}>🚧</div>
        <h2 style={{ color: theme.danger }}>Path is broken</h2>
        <p>One of the referenced decks has been deleted.</p>
        <button onClick={() => navigate('/uc1/paths')} style={{ marginTop: 12, padding: '10px 18px', background: theme.brand, color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer' }}>
          ← Back to paths
        </button>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 60, textAlign: 'center' }}>
        <div style={{ background: '#fee2e2', color: '#991b1b', padding: 16, borderRadius: 8, display: 'inline-block' }}>
          {error}
        </div>
      </div>
    );
  }

  if (!path) {
    return <div style={{ padding: 60, textAlign: 'center', color: theme.muted }}>Loading path…</div>;
  }

  const percent = progress?.percent ?? 0;
  const isComplete = progress?.total_slides && progress.completed_count >= progress.total_slides;
  const step = path.steps[currentStep];

  return (
    <div style={{ minHeight: 'calc(100vh - 60px)', background: theme.cardAlt, padding: '20px 24px' }}>
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        <button
          onClick={() => navigate('/uc1/paths')}
          style={{
            background: 'transparent', border: 'none', color: theme.brandLight,
            cursor: 'pointer', fontSize: 13, marginBottom: 12, padding: 0,
          }}
        >
          ← All paths
        </button>

        {/* Header + progress */}
        <div style={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 12, padding: 18, marginBottom: 14, boxShadow: theme.shadow }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
            <div>
              <h1 style={{ margin: '0 0 4px', fontSize: 22, color: theme.brand, fontWeight: 800 }}>{path.title}</h1>
              {path.description && <p style={{ margin: 0, fontSize: 13, color: theme.muted }}>{path.description}</p>}
            </div>
            {isComplete && (
              <div style={{ background: '#dcfce7', color: theme.success, padding: '6px 12px', borderRadius: 6, fontWeight: 700, fontSize: 13 }}>
                ✓ 100% complete
              </div>
            )}
          </div>
          <div style={{ marginTop: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: theme.muted, marginBottom: 4 }}>
              <span>{progress?.completed_count ?? 0} / {progress?.total_slides ?? 0} slides</span>
              <span>{percent.toFixed(0)}%</span>
            </div>
            <div style={{ height: 8, background: theme.cardAlt, borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ width: `${percent}%`, height: '100%', background: theme.accent, transition: 'width 0.3s' }} />
            </div>
          </div>
        </div>

        {/* Stepper */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
          {path.steps.map((s, idx) => {
            const done = (progress?.completed_slides?.[s.deck_id]?.length ?? 0) >= s.slide_count;
            const active = idx === currentStep && started;
            return (
              <button
                key={s.deck_id}
                onClick={() => goToStep(idx)}
                style={{
                  flex: '1 1 180px', minWidth: 180, textAlign: 'left',
                  background: active ? theme.accentLight : theme.card,
                  border: `1px solid ${active ? theme.accent : theme.border}`,
                  borderRadius: 10, padding: 12, cursor: 'pointer',
                  boxShadow: active ? '0 0 0 2px rgba(0, 155, 220, 0.2)' : 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{
                    width: 22, height: 22, borderRadius: '50%',
                    background: done ? theme.success : (active ? theme.accent : theme.border),
                    color: 'white', fontSize: 11, fontWeight: 700,
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {done ? '✓' : idx + 1}
                  </span>
                  <span style={{ fontSize: 11, color: theme.muted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    Step {idx + 1}
                  </span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: theme.brand, lineHeight: 1.3 }}>{s.deck_title}</div>
                <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>{s.slide_count} slides</div>
              </button>
            );
          })}
        </div>

        {/* Avatar + voice + language — always visible so user can configure before starting */}
        <div
          style={{
            background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 12,
            padding: 14, marginBottom: 14, boxShadow: theme.shadow,
            display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap',
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 700, color: theme.accent, textTransform: 'uppercase', letterSpacing: 1 }}>
            Presentation settings
          </div>
          {started && presentation && (
            <span style={{ fontSize: 12, color: theme.muted }}>
              · {step?.deck_title} · Slide {currentSlide + 1} / {presentation.slide_count}
            </span>
          )}

          <div style={{ flex: 1 }} />

          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <span style={{ fontWeight: 600, color: theme.muted }}>Avatar</span>
            <select
              value={selectedAvatar}
              onChange={(e) => setSelectedAvatar(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 13 }}
            >
              {UC1_AVATARS.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
            </select>
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <span style={{ fontWeight: 600, color: theme.muted }}>Voice</span>
            <select
              value={selectedVoice}
              onChange={(e) => onVoiceChange(e.target.value)}
              style={{ padding: '6px 8px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 13, minWidth: 180 }}
            >
              {Array.from(voicesByLang.entries()).map(([lang, vs]) => (
                <optgroup key={lang} label={UC1_LANGUAGE_LABELS[lang] ?? lang}>
                  {vs.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.display_name} · {v.gender === 'male' ? '♂' : '♀'}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>

          <LanguageSelector value={language} onChange={setLanguage} variant="light" />
        </div>

        {/* Start / Resume banner */}
        {!started && step && (
          <div style={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 12, padding: 20, marginBottom: 14, textAlign: 'center', boxShadow: theme.shadow }}>
            <div style={{ fontSize: 14, color: theme.muted, marginBottom: 4 }}>
              {progress && progress.completed_count > 0
                ? `Resume at step ${currentStep + 1}: ${step.deck_title}`
                : `Ready to start with: ${step.deck_title}`}
            </div>
            <div style={{ fontSize: 12, color: theme.muted, marginBottom: 14 }}>
              The avatar, voice and language above will be used for <b>all {path.steps.length} decks</b> in this path.
            </div>
            <button
              onClick={() => setStarted(true)}
              style={{
                background: theme.brand, color: 'white', border: 'none',
                borderRadius: 8, padding: '12px 28px', fontSize: 15, fontWeight: 600, cursor: 'pointer',
              }}
            >
              {progress && progress.completed_count > 0 ? '▶ Resume' : '▶ Start'}
            </button>
          </div>
        )}

        {/* Player */}
        {started && !presentation && (
          <div style={{ color: theme.muted, textAlign: 'center', padding: 60 }}>Loading deck…</div>
        )}
        {started && presentation && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20 }}>
            <div>
              <div style={{ background: theme.card, borderRadius: 12, padding: 16, boxShadow: theme.shadow, border: `1px solid ${theme.border}` }}>
                <SlideViewer
                  presentation={presentation}
                  currentSlide={currentSlide}
                  onSlideChange={onSlideChange}
                  language={language}
                  autoPlayVideo={autoPlayVideo}
                  onVideoPlayingChange={(playing) => {
                    setVideoPlaying(playing);
                    if (playing) setAutoPlayVideo(false);
                  }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 14 }}>
                <button
                  onClick={() => goToStep(currentStep - 1)}
                  disabled={currentStep === 0}
                  style={{
                    background: 'white', color: theme.brand,
                    border: `1px solid ${theme.border}`, borderRadius: 8,
                    padding: '10px 16px', fontSize: 13, fontWeight: 600,
                    cursor: currentStep === 0 ? 'not-allowed' : 'pointer',
                    opacity: currentStep === 0 ? 0.5 : 1,
                  }}
                >
                  ← Previous deck
                </button>
                <button
                  onClick={() => goToStep(currentStep + 1)}
                  disabled={currentStep === path.steps.length - 1}
                  style={{
                    background: theme.brand, color: 'white', border: 'none',
                    borderRadius: 8, padding: '10px 16px', fontSize: 13, fontWeight: 600,
                    cursor: currentStep === path.steps.length - 1 ? 'not-allowed' : 'pointer',
                    opacity: currentStep === path.steps.length - 1 ? 0.5 : 1,
                  }}
                >
                  Next deck →
                </button>
              </div>
            </div>
            <div>
              <div style={{ background: theme.card, borderRadius: 12, padding: 16, boxShadow: theme.shadow, border: `1px solid ${theme.border}` }}>
                <AvatarPanel
                  presentation={presentation}
                  currentSlide={currentSlide}
                  language={language}
                  onSlideChange={onSlideChange}
                  videoPlaying={videoPlaying}
                  onRequestVideoAutoPlay={() => setAutoPlayVideo(true)}
                  selectedAvatar={selectedAvatar}
                  selectedVoice={selectedVoice}
                  autoStart={true}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

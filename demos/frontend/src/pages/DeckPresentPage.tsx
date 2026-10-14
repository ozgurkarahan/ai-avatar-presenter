import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import SlideViewer from '../components/SlideViewer';
import AvatarPanel from '../components/AvatarPanel';
import LanguageSelector from '../components/LanguageSelector';
import { type Presentation } from '../services/api';
import {
  DeckDetail, getDeck,
  DECK_VOICES, DECK_LANGUAGE_LABELS,
  avatarForVoice,
} from '../services/decksApi';
import { isPhotoAvatar, pickAvatarForGender, pickDefaultAvatar, useAvatars } from '../services/avatars';
import { useAuth } from '../services/auth';
import { useDemoConfig } from '../services/demo';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
};

function deckToPresentation(d: DeckDetail): Presentation {
  return {
    id: d.id ?? d.deck_id,
    filename: d.filename ?? d.title,
    slide_count: d.slide_count ?? d.slides?.length ?? 0,
    slides: d.slides ?? [],
  };
}

export default function DeckPresentPage() {
  const { deckId = '' } = useParams();
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const initialSlide = Math.max(0, parseInt(sp.get('slide') ?? '0', 10) || 0);
  const autoplay = sp.get('autoplay') === '1';

  const [deck, setDeck] = useState<DeckDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [currentSlide, setCurrentSlide] = useState(initialSlide);
  const [language, setLanguage] = useState('en-US');
  const [videoPlaying, setVideoPlaying] = useState(false);
  const [autoPlayVideo, setAutoPlayVideo] = useState(autoplay);

  const [selectedVoice, setSelectedVoice] = useState<string>(DECK_VOICES[1].id); // Ava
  const [selectedAvatar, setSelectedAvatar] = useState<string>('');
  const { avatars } = useAvatars();
  const auth = useAuth();
  const isAdmin = auth.is_admin;
  const demo = useDemoConfig();

  // Default avatar from the server catalog (is_default → first female → first).
  useEffect(() => {
    if (avatars.length === 0) return;
    if (avatars.some((a) => a.id === selectedAvatar)) return;
    const g = DECK_VOICES.find((v) => v.id === selectedVoice)?.gender ?? 'female';
    setSelectedAvatar(pickAvatarForGender(avatars, g)?.id ?? '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avatars]);

  useEffect(() => {
    let cancelled = false;
    getDeck(deckId)
      .then((d) => { if (!cancelled) { setDeck(d); if (d.language) setLanguage(d.language); } })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); });
    return () => { cancelled = true; };
  }, [deckId]);

  useEffect(() => {
    // Clamp current slide when deck arrives
    if (deck && currentSlide >= deck.slides.length) setCurrentSlide(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deck]);

  // Auto-pick gender-appropriate avatar when voice changes
  function onVoiceChange(voiceId: string) {
    setSelectedVoice(voiceId);
    setSelectedAvatar(avatarForVoice(voiceId, avatars, selectedAvatar));
    const v = DECK_VOICES.find((x) => x.id === voiceId);
    if (v?.language) setLanguage(v.language);
  }

  const voicesByLang = useMemo(() => {
    const map = new Map<string, typeof DECK_VOICES>();
    DECK_VOICES.forEach((v) => {
      const arr = map.get(v.language) ?? [];
      arr.push(v);
      map.set(v.language, arr);
    });
    return map;
  }, []);

  const presentation = deck ? deckToPresentation(deck) : null;
  // Anonymous narration-only live demo: kill switch on + deck marked "Live demo".
  const demoMode = !auth.loading && !isAdmin && !demo.loading && demo.enabled && deck?.live_demo === true;
  // The demo avatar is chosen server-side (registry default).
  const avatarMode = isPhotoAvatar(
    demoMode ? pickDefaultAvatar(avatars) : avatars.find((a) => a.id === selectedAvatar),
  ) ? 'portrait' : 'wide';

  return (
    <div style={{ minHeight: 'calc(100vh - 60px)', background: theme.cardAlt, padding: '20px 24px' }}>
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        <button
          onClick={() => navigate('/decks')}
          style={{
            background: 'transparent', border: 'none', color: theme.brandLight,
            cursor: 'pointer', fontSize: 13, marginBottom: 12, padding: 0,
          }}
        >
          ← Back to decks
        </button>

        {error && (
          <div style={{ background: '#fee2e2', color: '#991b1b', padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
            {error}
          </div>
        )}

        {!presentation && !error && (
          <div style={{ color: theme.muted, textAlign: 'center', padding: 60 }}>Loading deck…</div>
        )}

        {presentation && (
          <>
            {/* Avatar + voice + language picker */}
            <div
              style={{
                background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 12,
                padding: 14, marginBottom: 14, boxShadow: theme.shadow,
                display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap',
              }}
            >
              <div style={{ fontSize: 15, fontWeight: 700, color: theme.brand, marginRight: 8 }}>
                {deck?.title || presentation.filename}
              </div>
              <span style={{ fontSize: 12, color: theme.muted }}>
                {presentation.slide_count} slide{presentation.slide_count === 1 ? '' : 's'}
              </span>

              <div style={{ flex: 1 }} />

              {!isAdmin && !auth.loading && (
                demoMode ? (
                  <span
                    data-testid="live-demo-available"
                    style={{ fontSize: 12, color: '#9a3412', fontWeight: 700, background: '#fff7ed', border: '1px solid #fdba74', borderRadius: 999, padding: '3px 10px' }}
                  >
                    🎙️ Live avatar demo available
                  </span>
                ) : (
                  <span style={{ fontSize: 12, color: theme.muted, fontWeight: 600 }}>👀 Read-only preview</span>
                )
              )}

              {isAdmin && (<>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: theme.text }}>
                <span style={{ fontWeight: 600, color: theme.muted }}>Avatar</span>
                <select
                  value={selectedAvatar}
                  onChange={(e) => setSelectedAvatar(e.target.value)}
                  style={{ padding: '6px 8px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 13 }}
                >
                  {avatars.length === 0 && <option value="">Default avatar</option>}
                  {avatars.map((a) => (
                    <option key={a.id} value={a.id}>{a.display_name}</option>
                  ))}
                </select>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: theme.text }}>
                <span style={{ fontWeight: 600, color: theme.muted }}>Voice</span>
                <select
                  value={selectedVoice}
                  onChange={(e) => onVoiceChange(e.target.value)}
                  style={{ padding: '6px 8px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 13, minWidth: 200 }}
                >
                  {Array.from(voicesByLang.entries()).map(([lang, vs]) => (
                    <optgroup key={lang} label={DECK_LANGUAGE_LABELS[lang] ?? lang}>
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
              </>)}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.724fr) minmax(0, 1fr)', gap: 20, alignItems: 'start' }}>
              <div>
                <div style={{ background: theme.card, borderRadius: 12, padding: 16, boxShadow: theme.shadow, border: `1px solid ${theme.border}` }}>
                  <SlideViewer
                    presentation={presentation}
                    currentSlide={currentSlide}
                    onSlideChange={setCurrentSlide}
                    language={language}
                    autoPlayVideo={autoPlayVideo}
                    onVideoPlayingChange={(playing) => {
                      setVideoPlaying(playing);
                      if (playing) setAutoPlayVideo(false);
                    }}
                  />
                </div>
              </div>
              <div>
                <div style={{ background: theme.card, borderRadius: 12, padding: 16, boxShadow: theme.shadow, border: `1px solid ${theme.border}` }}>
                  <AvatarPanel
                    key={demoMode ? 'demo' : 'admin'}
                    presentation={presentation}
                    currentSlide={currentSlide}
                    language={language}
                    onSlideChange={setCurrentSlide}
                    videoPlaying={videoPlaying}
                    onRequestVideoAutoPlay={() => setAutoPlayVideo(true)}
                    selectedAvatar={selectedAvatar}
                    selectedVoice={selectedVoice}
                    mode={avatarMode}
                    access={demoMode ? 'demo' : 'admin'}
                    demoSessionSeconds={demo.session_seconds}
                  />
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

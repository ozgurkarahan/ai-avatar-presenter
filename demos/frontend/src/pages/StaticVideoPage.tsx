import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  DRAGONHD_LANGUAGES, DEFAULT_VOICE_BY_LANG,
  IngestResponse, ScriptStyle, SlideInfo, SlideNarration, StaticJob, VoiceOption,
  getJob, getScript, ingestFile, listVoices, patchScript,
  startRender, streamScript,
} from '../services/staticVideoApi';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
};

const SAMPLE_PROMPTS = [
  { emoji: '📊', title: 'Executive Summary', focus: 'Summarize each slide for a C-level audience, highlighting strategic value.' },
  { emoji: '🧪', title: 'Technical Deep-Dive', focus: 'Explain each slide technically to an engineering audience.' },
  { emoji: '🎓', title: 'Classroom Explainer', focus: 'Narrate each slide clearly for students. Use analogies.' },
  { emoji: '🛒', title: 'Customer Pitch', focus: 'Narrate each slide as a persuasive customer-facing pitch.' },
];

type Phase = 'setup' | 'scripting' | 'review' | 'rendering' | 'done';

export default function StaticVideoPage() {
  const [phase, setPhase] = useState<Phase>('setup');
  const [doc, setDoc] = useState<IngestResponse | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);

  const [language, setLanguage] = useState('en-US');
  const [style, setStyle] = useState<ScriptStyle>('explainer');
  const [focus, setFocus] = useState('');
  const [voice, setVoice] = useState<string>(DEFAULT_VOICE_BY_LANG['en-US']);
  const [voices, setVoices] = useState<VoiceOption[]>([]);

  const [narrations, setNarrations] = useState<SlideNarration[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [savingPatch, setSavingPatch] = useState(false);
  const abortRef = useRef<(() => void) | null>(null);

  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<StaticJob | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  // ---- load voices when language changes ---------------------------------
  useEffect(() => {
    listVoices(language).then((vs) => {
      setVoices(vs);
      if (vs.length === 0) {
        setVoice(DEFAULT_VOICE_BY_LANG[language] ?? voice);
        return;
      }
      const ok = vs.some((v) => v.id === voice);
      if (!ok) {
        const female = vs.find((v) => v.gender === 'female');
        setVoice((female ?? vs[0]).id);
      }
    }).catch(() => {
      setVoices([]);
      setVoice(DEFAULT_VOICE_BY_LANG[language] ?? voice);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language]);

  // ---- poll job ----------------------------------------------------------
  useEffect(() => {
    if (!jobId || !job) return;
    if (['done', 'failed'].includes(job.state)) return;
    const t = setTimeout(async () => {
      try { setJob(await getJob(jobId)); }
      catch { /* ignore transient */ }
    }, 2500);
    return () => clearTimeout(t);
  }, [jobId, job]);

  useEffect(() => { if (job?.state === 'done') setPhase('done'); }, [job?.state]);

  // ---- actions -----------------------------------------------------------
  async function handleFile(f: File) {
    setUploadBusy(true);
    try { setDoc(await ingestFile(f)); }
    catch (e: any) { alert(`Upload failed: ${e?.message ?? e}`); }
    finally { setUploadBusy(false); }
  }

  function startScript() {
    if (!doc) return;
    setPhase('scripting');
    setNarrations([]); setScriptError(null); setSelectedIdx(0);
    abortRef.current?.();
    streamScript(
      doc.doc_id,
      { language, style, focus: focus || undefined, voice },
      (n) => setNarrations((prev) => {
        const next = [...prev];
        const existing = next.findIndex((x) => x.slide_index === n.slide_index);
        if (existing >= 0) next[existing] = n; else next.push(n);
        next.sort((a, b) => a.slide_index - b.slide_index);
        return next;
      }),
      async () => {
        try {
          const full = await getScript(doc.doc_id);
          setNarrations(full.narrations);
        } catch { /* use streamed */ }
        setPhase('review');
      },
      (msg) => setScriptError(msg),
    ).then((abort) => { abortRef.current = abort; });
  }

  async function updateSlideNarration(slideIndex: number, text: string) {
    // Local update first (optimistic)
    setNarrations((prev) => prev.map((n) =>
      n.slide_index === slideIndex ? { ...n, narration: text } : n));
  }

  function updateSlideVoice(slideIndex: number, nextVoice: string) {
    setNarrations((prev) => prev.map((n) =>
      n.slide_index === slideIndex ? { ...n, voice: nextVoice } : n));
  }

  async function saveSlidePatch(slideIndex: number, text: string, nextVoice?: string) {
    if (!doc) return;
    setSavingPatch(true);
    try {
      const updated = await patchScript(doc.doc_id, [{
        slide_index: slideIndex,
        narration: text,
        voice: nextVoice,
      }]);
      setNarrations(updated.narrations);
    } catch (e: any) {
      alert(`Save failed: ${e?.message ?? e}`);
    } finally {
      setSavingPatch(false);
    }
  }

  async function regenerateSlide(slideIndex: number) {
    if (!doc) return;
    // Single-slide regen: re-run script stream with a narrow focus instruction.
    setSavingPatch(true);
    try {
      const r = await fetch(`/api/static-video/script/${doc.doc_id}/slide/${slideIndex}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ language, style, focus, voice }),
      });
      if (r.ok) {
        const updated = await r.json();
        if (updated && typeof updated.slide_index === 'number') {
          setNarrations((prev) => prev.map((n) =>
            n.slide_index === slideIndex ? updated : n));
        }
      } else {
        // Fallback: re-stream full script
        alert('Per-slide regeneration unavailable — regenerating the whole script.');
        startScript();
      }
    } catch (e: any) {
      alert(`Regenerate failed: ${e?.message ?? e}`);
    } finally {
      setSavingPatch(false);
    }
  }

  async function kickOffRender() {
    if (!doc) return;
    try {
      const { job_id } = await startRender(doc.doc_id);
      setJobId(job_id);
      setJob(makeQueuedJob(job_id, doc.doc_id, doc.slides.length));
      setPhase('rendering');
      setRenderError(null);
      try {
        setJob(await getJob(job_id));
      } catch (e: any) {
        setRenderError(`Render started, but polling failed: ${e?.message ?? e}`);
      }
    } catch (e: any) {
      setRenderError(String(e?.message ?? e));
      alert(`Render failed to start: ${e?.message ?? e}`);
    }
  }

  const displayTitle = doc?.title ?? doc?.filename ?? '';

  return (
    <div style={{ background: theme.cardAlt, minHeight: 'calc(100vh - 60px)', padding: '32px 0' }}>
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 24px' }}>
        <Hero />
        <AnimatePresence mode="wait">
          {phase === 'setup' && (
            <motion.div key="setup" {...fade}>
              <SetupPhase
                doc={doc} uploadBusy={uploadBusy}
                focus={focus} onFocusChange={setFocus}
                style={style} onStyle={setStyle}
                language={language} onLanguage={setLanguage}
                voice={voice} onVoice={setVoice} voices={voices}
                onFile={handleFile}
                onApplyPrompt={(p) => setFocus(p.focus)}
                onGenerate={startScript}
              />
            </motion.div>
          )}
          {phase === 'scripting' && (
            <motion.div key="scripting" {...fade}>
              <ScriptStreamingView narrations={narrations} error={scriptError} total={doc?.slides.length ?? 0} />
            </motion.div>
          )}
          {phase === 'review' && doc && (
            <motion.div key="review" {...fade}>
              <ScriptReview
                slides={doc.slides}
                narrations={narrations}
                selectedIdx={selectedIdx}
                onSelect={setSelectedIdx}
                voices={voices}
                onNarrationChange={updateSlideNarration}
                onVoiceChange={updateSlideVoice}
                onSavePatch={saveSlidePatch}
                onRegenerate={regenerateSlide}
                savingPatch={savingPatch}
                onRender={kickOffRender}
                onBack={() => setPhase('setup')}
              />
            </motion.div>
          )}
          {phase === 'rendering' && job && (
            <motion.div key="rendering" {...fade}>
              <RenderingView job={job} slideCount={doc?.slides.length ?? 0} error={renderError} />
            </motion.div>
          )}
          {phase === 'done' && (
            <motion.div key="done" {...fade}>
              <DoneView
                jobId={jobId}
                title={displayTitle}
                onNew={() => {
                  setPhase('setup'); setDoc(null); setJob(null); setJobId(null);
                  setNarrations([]); setSelectedIdx(0);
                }}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
const fade = {
  initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 }, transition: { duration: 0.25 },
};

function makeQueuedJob(jobId: string, docId: string, total: number): StaticJob {
  const now = new Date().toISOString();
  return {
    job_id: jobId,
    doc_id: docId,
    state: 'queued',
    progress: {
      stage: 'queued',
      percent: 0,
      completed: 0,
      total,
      message: 'Queued for rendering…',
    },
    outputs: {},
    error: null,
    created_at: now,
    updated_at: now,
    archive_state: 'none',
  };
}

function Hero() {
  return (
    <div style={{
      background: `linear-gradient(135deg, ${theme.brand} 0%, ${theme.brandLight} 60%, ${theme.accent} 100%)`,
      color: 'white', borderRadius: 20, padding: '40px 44px', marginBottom: 24,
      boxShadow: theme.shadow, position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ position: 'absolute', top: -50, right: -50, width: 240, height: 240,
        borderRadius: '50%', background: 'rgba(255,255,255,0.08)' }} />
      <div style={{ fontSize: 12, letterSpacing: 3, textTransform: 'uppercase', opacity: 0.7 }}>
        Acme Insights
      </div>
      <h1 style={{ fontSize: 36, margin: '8px 0', fontWeight: 800, letterSpacing: '-0.5px' }}>
        AI Video Generator
      </h1>
      <p style={{ margin: 0, fontSize: 16, opacity: 0.9, maxWidth: 640 }}>
        Turn any deck into a narrated video. Upload slides, review per-slide
        narration, pick a voice — we render the rest.
      </p>
    </div>
  );
}

// ---- Setup phase ----------------------------------------------------------
interface SetupProps {
  doc: IngestResponse | null;
  uploadBusy: boolean;
  focus: string; onFocusChange: (v: string) => void;
  style: ScriptStyle; onStyle: (s: ScriptStyle) => void;
  language: string; onLanguage: (l: string) => void;
  voice: string; onVoice: (v: string) => void;
  voices: VoiceOption[];
  onFile: (f: File) => void;
  onApplyPrompt: (p: typeof SAMPLE_PROMPTS[number]) => void;
  onGenerate: () => void;
}

function SetupPhase(p: SetupProps) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 420px', gap: 24 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <Card title="1. Slide deck">
          <Uploader doc={p.doc} busy={p.uploadBusy} onFile={p.onFile} />
        </Card>
        <Card title="2. Narration focus (optional)">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginBottom: 12 }}>
            {SAMPLE_PROMPTS.map((sp) => (
              <button key={sp.title} onClick={() => p.onApplyPrompt(sp)}
                style={{ textAlign: 'left', background: theme.cardAlt, border: `1px solid ${theme.border}`,
                  borderRadius: 10, padding: '12px 14px', cursor: 'pointer', fontSize: 13, color: theme.text }}>
                <div style={{ fontSize: 18, marginBottom: 2 }}>{sp.emoji}</div>
                <div style={{ fontWeight: 700, marginBottom: 2 }}>{sp.title}</div>
                <div style={{ color: theme.muted, fontSize: 11, lineHeight: 1.4 }}>{sp.focus}</div>
              </button>
            ))}
          </div>
          <textarea value={p.focus} onChange={(e) => p.onFocusChange(e.target.value)}
            placeholder="Describe the angle — e.g. 'emphasise ROI for retrofit projects'"
            style={{ width: '100%', minHeight: 60, border: `1px solid ${theme.border}`,
              borderRadius: 8, padding: 10, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' }} />
        </Card>
        <Card title="3. Narration settings">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            <Field label="Style">
              <select value={p.style} onChange={(e) => p.onStyle(e.target.value as ScriptStyle)} style={selectStyle}>
                <option value="explainer">Explainer</option>
                <option value="formal">Formal</option>
                <option value="casual">Casual</option>
                <option value="marketing">Marketing</option>
              </select>
            </Field>
            <Field label="Language">
              <select value={p.language} onChange={(e) => p.onLanguage(e.target.value)} style={selectStyle}>
                {DRAGONHD_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>{l.label}</option>
                ))}
              </select>
            </Field>
            <Field label="Voice">
              <select value={p.voice} onChange={(e) => p.onVoice(e.target.value)} style={selectStyle}>
                {p.voices.length === 0 ? (
                  <option value={p.voice}>{p.voice}</option>
                ) : (
                  p.voices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.display_name} · {v.gender}
                    </option>
                  ))
                )}
              </select>
            </Field>
          </div>
        </Card>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <Card title="Preview">
          {p.doc ? (
            <SlidePreviewStrip slides={p.doc.slides} />
          ) : (
            <div style={{ color: theme.muted, fontSize: 13, padding: 24, textAlign: 'center' }}>
              Upload a document to preview its slides here.
            </div>
          )}
        </Card>
        <button disabled={!p.doc} onClick={p.onGenerate}
          style={{
            background: !p.doc ? theme.border : `linear-gradient(135deg, ${theme.brand}, ${theme.accent})`,
            color: 'white', border: 'none', borderRadius: 12, padding: '16px 20px',
            fontSize: 16, fontWeight: 700, cursor: p.doc ? 'pointer' : 'not-allowed',
            boxShadow: p.doc ? theme.shadow : 'none',
          }}>
          ✨ Generate narration
        </button>
        {!p.doc && <div style={{ fontSize: 12, color: theme.muted, textAlign: 'center' }}>
          Upload a document first
        </div>}
      </div>
    </div>
  );
}

function Uploader({ doc, busy, onFile }: {
  doc: IngestResponse | null; busy: boolean; onFile: (f: File) => void;
}) {
  const [drag, setDrag] = useState(false);
  if (doc) {
    return (
      <div style={{ background: theme.cardAlt, borderRadius: 10, padding: 14,
        display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ fontSize: 28 }}>📊</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700 }}>{doc.title ?? doc.filename ?? 'Uploaded deck'}</div>
          <div style={{ fontSize: 12, color: theme.muted }}>
            {doc.slides.length} slide{doc.slides.length === 1 ? '' : 's'} detected
          </div>
        </div>
      </div>
    );
  }
  return (
    <label
      onDragEnter={(e) => { e.preventDefault(); setDrag(true); }}
      onDragOver={(e) => { e.preventDefault(); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false);
        const f = e.dataTransfer.files?.[0]; if (f) onFile(f); }}
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
        border: `2px dashed ${drag ? theme.accent : theme.border}`, borderRadius: 12,
        padding: '28px 16px', cursor: 'pointer', background: drag ? '#eff6ff' : 'transparent',
      }}>
      <div style={{ fontSize: 32 }}>🎬</div>
      <div style={{ fontWeight: 600 }}>Drag a PPTX / PDF / image here</div>
      <div style={{ fontSize: 12, color: theme.muted }}>or click to browse</div>
      <input type="file" accept=".pptx,.pdf,.png,.jpg,.jpeg"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
        style={{ display: 'none' }} />
      {busy && <div style={{ fontSize: 12, color: theme.muted, marginTop: 6 }}>⏳ Processing…</div>}
    </label>
  );
}

function SlidePreviewStrip({ slides }: { slides: SlideInfo[] }) {
  return (
    <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 6 }}>
      {slides.slice(0, 12).map((s) => (
        <div key={s.index} style={{
          minWidth: 120, aspectRatio: '16 / 9', borderRadius: 6,
          background: theme.cardAlt, border: `1px solid ${theme.border}`,
          overflow: 'hidden', position: 'relative', flexShrink: 0,
        }}>
          {s.image_ref ? (
            <img src={s.image_ref} alt={s.title}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <div style={{ padding: 8, fontSize: 10, color: theme.muted }}>
              {s.title || `Slide ${s.index + 1}`}
            </div>
          )}
          <div style={{ position: 'absolute', bottom: 2, left: 4, color: 'white',
            textShadow: '0 1px 2px rgba(0,0,0,0.8)', fontSize: 10, fontWeight: 700 }}>
            {s.index + 1}
          </div>
        </div>
      ))}
      {slides.length > 12 && (
        <div style={{ alignSelf: 'center', color: theme.muted, fontSize: 12, padding: '0 8px' }}>
          +{slides.length - 12} more
        </div>
      )}
    </div>
  );
}

// ---- Scripting ------------------------------------------------------------
function ScriptStreamingView({ narrations, error, total }: {
  narrations: SlideNarration[]; error: string | null; total: number;
}) {
  return (
    <div style={{ background: theme.card, borderRadius: 14, padding: 28, boxShadow: theme.shadow }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
          style={{ width: 20, height: 20, borderRadius: '50%',
            border: `3px solid ${theme.border}`, borderTopColor: theme.accent }} />
        <div style={{ fontWeight: 700, fontSize: 16 }}>Generating narration…</div>
        <div style={{ fontSize: 12, color: theme.muted }}>
          {narrations.length}{total ? ` / ${total}` : ''} slides
        </div>
      </div>
      {error ? (
        <div style={{ color: '#dc2626', fontWeight: 600 }}>Error: {error}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {narrations.map((n) => (
            <motion.div key={n.slide_index}
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              style={{ background: theme.cardAlt, border: `1px solid ${theme.border}`,
                borderRadius: 10, padding: '10px 14px' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: theme.brand, marginBottom: 4 }}>
                Slide {n.slide_index + 1} · {n.title || '—'}
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.5 }}>{n.narration}</div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---- Review (per-slide editor) -------------------------------------------
function ScriptReview({
  slides, narrations, selectedIdx, onSelect,
  voices, onNarrationChange, onVoiceChange, onSavePatch, onRegenerate, savingPatch,
  onRender, onBack,
}: {
  slides: SlideInfo[];
  narrations: SlideNarration[];
  selectedIdx: number;
  onSelect: (i: number) => void;
  voices: VoiceOption[];
  onNarrationChange: (slideIndex: number, text: string) => void;
  onVoiceChange: (slideIndex: number, voice: string) => void;
  onSavePatch: (slideIndex: number, text: string, voice?: string) => Promise<void>;
  onRegenerate: (slideIndex: number) => Promise<void>;
  savingPatch: boolean;
  onRender: () => void;
  onBack: () => void;
}) {
  const currentSlide = slides[selectedIdx];
  const currentNar = useMemo(
    () => narrations.find((n) => n.slide_index === selectedIdx),
    [narrations, selectedIdx],
  );
  const [draft, setDraft] = useState<string>(currentNar?.narration ?? '');
  useEffect(() => { setDraft(currentNar?.narration ?? ''); }, [selectedIdx, currentNar?.narration]);

  const dirty = (currentNar?.narration ?? '') !== draft;

  return (
    <div style={{ background: theme.card, borderRadius: 14, padding: 28, boxShadow: theme.shadow }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <div style={{ fontWeight: 700, fontSize: 20 }}>📝 Review &amp; edit narration</div>
        <div style={{ fontSize: 12, color: theme.muted }}>{narrations.length} slides narrated</div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 10 }}>
          <button onClick={onBack} style={secondaryBtn}>← Back</button>
          <button onClick={onRender} style={primaryBtn}>🎬 Render video</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 20 }}>
        {/* Slide thumbnail list */}
        <div style={{
          maxHeight: 620, overflowY: 'auto', paddingRight: 6,
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          {slides.map((s) => {
            const active = s.index === selectedIdx;
            const nar = narrations.find((n) => n.slide_index === s.index);
            return (
              <button key={s.index} onClick={() => onSelect(s.index)}
                style={{
                  textAlign: 'left', padding: 8, borderRadius: 10,
                  border: `2px solid ${active ? theme.accent : theme.border}`,
                  background: active ? '#eff6ff' : theme.card,
                  cursor: 'pointer', display: 'flex', gap: 10, alignItems: 'center',
                }}>
                <div style={{
                  width: 72, aspectRatio: '16 / 9', borderRadius: 4,
                  background: theme.cardAlt, overflow: 'hidden', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 10, color: theme.muted,
                }}>
                  {s.image_ref ? (
                    <img src={s.image_ref} alt=""
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  ) : (
                    <span>{s.index + 1}</span>
                  )}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: theme.brand, fontWeight: 700 }}>
                    Slide {s.index + 1}
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 600,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.title || nar?.title || '—'}
                  </div>
                  <div style={{ fontSize: 10, color: nar ? '#15803d' : theme.muted, marginTop: 2 }}>
                    {nar ? '✓ narrated' : '…pending'}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Right pane: slide + editor */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {currentSlide && (
            <div style={{
              aspectRatio: '16 / 9', background: '#000', borderRadius: 10,
              overflow: 'hidden', border: `1px solid ${theme.border}`,
            }}>
              {currentSlide.image_ref ? (
                <img src={currentSlide.image_ref} alt={currentSlide.title}
                  style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
              ) : (
                <div style={{ color: 'white', padding: 40, textAlign: 'center' }}>
                  Slide {currentSlide.index + 1} — {currentSlide.title}
                </div>
              )}
            </div>
          )}
          <div>
            <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4, fontWeight: 600 }}>
              Narration — slide {selectedIdx + 1}
            </div>
            <textarea
              value={draft}
              onChange={(e) => { setDraft(e.target.value); onNarrationChange(selectedIdx, e.target.value); }}
              placeholder="Narration text for this slide…"
              style={{ width: '100%', minHeight: 140,
                border: `1px solid ${theme.border}`, borderRadius: 8,
                padding: 12, fontSize: 14, fontFamily: 'inherit', resize: 'vertical',
                lineHeight: 1.5 }}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
              <Field label="Voice">
                <select
                  value={currentNar?.voice ?? ''}
                  onChange={async (e) => {
                    if (!currentNar) return;
                    const nv = e.target.value;
                    onVoiceChange(selectedIdx, nv);
                    try {
                      await onSavePatch(selectedIdx, draft, nv);
                    } catch (err) {
                      alert(`Voice update failed: ${err instanceof Error ? err.message : String(err)}`);
                    }
                  }}
                  style={selectStyle}>
                  {voices.length === 0 ? (
                    <option value={currentNar?.voice ?? ''}>{currentNar?.voice ?? '—'}</option>
                  ) : (
                    voices.map((v) => (
                      <option key={v.id} value={v.id}>{v.display_name} · {v.gender}</option>
                    ))
                  )}
                </select>
              </Field>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                <button
                  onClick={() => onRegenerate(selectedIdx)}
                  disabled={savingPatch}
                  style={{ ...secondaryBtn, cursor: savingPatch ? 'wait' : 'pointer' }}>
                  ♻ Regenerate slide
                </button>
                <button
                  onClick={() => onSavePatch(selectedIdx, draft)}
                  disabled={!dirty || savingPatch}
                  style={{
                    ...primaryBtn,
                    opacity: (!dirty || savingPatch) ? 0.55 : 1,
                    cursor: (!dirty || savingPatch) ? 'not-allowed' : 'pointer',
                  }}>
                  {savingPatch ? 'Saving…' : '💾 Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- Rendering progress ---------------------------------------------------
function RenderingView({ job, slideCount, error }: {
  job: StaticJob; slideCount: number; error: string | null;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(job.progress.percent ?? 0)));
  const failed = job.state === 'failed';
  const done = job.state === 'done';
  const effectiveError = error ?? job.error ?? null;
  return (
    <div style={{ background: theme.card, borderRadius: 14, padding: 32, boxShadow: theme.shadow }}>
      <div style={{ fontWeight: 700, fontSize: 20, marginBottom: 20 }}>
        {done ? '✅ Video ready' : failed ? '❌ Render failed' : '🎬 Rendering your video…'}
      </div>
      <div style={{
        padding: '18px 20px', borderRadius: 10,
        background: failed ? '#fee2e2' : done ? '#dcfce7' : '#eff6ff',
        border: `1px solid ${failed ? '#fca5a5' : done ? '#86efac' : theme.border}`,
        marginBottom: 18,
      }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: theme.brand, textTransform: 'uppercase',
          letterSpacing: 1, marginBottom: 4 }}>
          {job.progress.stage || job.state}
        </div>
        <div style={{ fontSize: 14, color: theme.text }}>
          {job.progress.message || (done ? 'Complete.' : 'Working…')}
        </div>
      </div>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between',
          fontSize: 12, color: theme.muted, marginBottom: 6 }}>
          <span>Progress</span>
          <span>{pct}%</span>
        </div>
        <div style={{ height: 10, background: theme.cardAlt, borderRadius: 99, overflow: 'hidden' }}>
          <motion.div animate={{ width: `${pct}%` }} transition={{ duration: 0.4 }}
            style={{ height: '100%',
              background: `linear-gradient(90deg, ${theme.brand}, ${theme.accent})` }} />
        </div>
      </div>
      {effectiveError && (
        <div style={{ color: '#dc2626', marginTop: 16, fontWeight: 600 }}>{effectiveError}</div>
      )}
      <div style={{ marginTop: 24, fontSize: 12, color: theme.muted }}>
        {slideCount} slides · typical render takes 2–5 minutes.
      </div>
    </div>
  );
}

function DoneView({ jobId, title, onNew }: {
  jobId: string | null; title: string; onNew: () => void;
}) {
  return (
    <div style={{ background: theme.card, borderRadius: 14, padding: 32, boxShadow: theme.shadow,
      textAlign: 'center' }}>
      <div style={{ fontSize: 48, marginBottom: 12 }}>🎉</div>
      <h2 style={{ margin: 0, color: theme.brand }}>Your video is ready</h2>
      <div style={{ color: theme.muted, marginTop: 8 }}>
        {title ? <>&ldquo;{title}&rdquo; has been saved to your library.</> : 'Saved to the library.'}
      </div>
      <div style={{ marginTop: 20, display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
        <a href="/video/library" style={primaryBtn as any}>📚 View in Library</a>
        {jobId && (
          <a href={`/video/library?job=${encodeURIComponent(jobId)}`} style={secondaryBtn as any}>
            ▶ Play now
          </a>
        )}
        <button onClick={onNew} style={secondaryBtn}>+ New video</button>
      </div>
    </div>
  );
}

// ---- shared styles --------------------------------------------------------
function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: theme.card, borderRadius: 14, padding: 20, boxShadow: theme.shadow }}>
      <div style={{ fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase',
        color: theme.brand, fontWeight: 700, marginBottom: 10 }}>{title}</div>
      {children}
    </div>
  );
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4, fontWeight: 600 }}>{label}</div>
      {children}
    </div>
  );
}

const selectStyle: React.CSSProperties = {
  width: '100%', border: `1px solid ${theme.border}`, borderRadius: 8,
  padding: '8px 10px', fontSize: 13, background: 'white',
};
const primaryBtn: React.CSSProperties = {
  background: `linear-gradient(135deg, ${theme.brand}, ${theme.accent})`,
  color: 'white', border: 'none', borderRadius: 10, padding: '10px 18px',
  fontSize: 14, fontWeight: 700, cursor: 'pointer', textDecoration: 'none',
  display: 'inline-block',
};
const secondaryBtn: React.CSSProperties = {
  background: theme.cardAlt, color: theme.text,
  border: `1px solid ${theme.border}`, borderRadius: 10, padding: '10px 18px',
  fontSize: 14, fontWeight: 600, cursor: 'pointer', textDecoration: 'none',
  display: 'inline-block',
};

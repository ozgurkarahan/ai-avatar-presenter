import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AvatarOption, DialogueTurn, Document as PodDoc, JobState, Layout,
  PodcastJob, RoleConfig, Script, Speaker, Style, VoiceOption,
  getJob, ingestFile, ingestUrl, listAvatars, listVoices,
  startRender, streamScript,
} from '../services/podcast';

const theme = {
  brand: '#003366', brandLight: '#005599', accent: '#009bdc',
  text: '#1a1a2e', muted: '#64748b',
  card: '#ffffff', cardAlt: '#f8fafc', border: '#e2e8f0',
  shadow: '0 4px 20px rgba(0, 51, 102, 0.08)',
};

const SAMPLE_PROMPTS = [
  { emoji: '📊', title: 'Executive Summary', focus: 'Summarize the key strategic points for a C-level audience.' },
  { emoji: '🧪', title: 'Product Deep-Dive',  focus: 'Explain the technical mechanics clearly to an engineering audience.' },
  { emoji: '⚖️',  title: 'Balanced Debate',    focus: 'Present the strongest arguments for and against the proposal.' },
  { emoji: '🎓', title: 'Classroom Explainer', focus: 'Make this accessible to a motivated student. Use analogies.' },
];

type Phase = 'setup' | 'scripting' | 'review' | 'rendering' | 'done';

export default function PodcastPage() {
  const [phase, setPhase] = useState<Phase>('setup');
  const [doc, setDoc] = useState<PodDoc | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [focus, setFocus] = useState('');
  const [style, setStyle] = useState<Style>('casual');
  const [numTurns, setNumTurns] = useState(8);
  const [language, setLanguage] = useState('en-US');
  const [avatars, setAvatars] = useState<AvatarOption[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [interviewer, setInterviewer] = useState<RoleConfig>({
    display_name: 'Dr. Harry Chen', avatar: 'harry', voice: 'en-US-Andrew:DragonHDLatestNeural',
  });
  const [expert, setExpert] = useState<RoleConfig>({
    display_name: 'Dr. Lisa Patel', avatar: 'lisa', voice: 'en-US-Ava:DragonHDLatestNeural',
  });
  const [streamingTurns, setStreamingTurns] = useState<DialogueTurn[]>([]);
  const [scriptId, setScriptId] = useState<string | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const [job, setJob] = useState<PodcastJob | null>(null);
  const [music, setMusic] = useState(true);
  const [intro, setIntro] = useState(true);
  const [layout] = useState<Layout>('split_screen_with_slides');

  useEffect(() => { listAvatars().then(setAvatars).catch(() => {}); }, []);
  useEffect(() => { listVoices(language).then(setVoices).catch(() => {}); }, [language]);

  useEffect(() => {
    if (!job || ['done', 'failed', 'cancelled'].includes(job.state)) return;
    const t = setTimeout(async () => {
      try { setJob(await getJob(job.id)); } catch { /* ignore */ }
    }, 2500);
    return () => clearTimeout(t);
  }, [job]);

  useEffect(() => { if (job?.state === 'done') setPhase('done'); }, [job?.state]);

  async function handleFile(f: File) {
    setUploadBusy(true);
    try { setDoc(await ingestFile(f)); }
    catch (e) { alert(`Upload failed: ${e}`); }
    finally { setUploadBusy(false); }
  }
  async function handleUrl() {
    if (!urlInput.trim()) return;
    setUploadBusy(true);
    try { setDoc(await ingestUrl(urlInput.trim())); setUrlInput(''); }
    catch (e) { alert(`URL ingest failed: ${e}`); }
    finally { setUploadBusy(false); }
  }

  function startScript() {
    if (!doc) return;
    setPhase('scripting');
    setStreamingTurns([]); setScriptId(null); setScriptError(null);
    abortRef.current?.();
    streamScript(
      { document_id: doc.id, language, style, length: 'medium', num_turns: numTurns, focus: focus || undefined },
      (t) => setStreamingTurns((prev) => [...prev, t]),
      (id) => { setScriptId(id); setPhase('review'); },
      (msg) => setScriptError(msg),
    ).then((abort) => { abortRef.current = abort; });
  }

  async function kickOffRender() {
    if (!scriptId) return;
    try {
      const j = await startRender({
        script_id: scriptId, roles: { interviewer, expert },
        layout, music, intro,
      });
      setJob(j); setPhase('rendering');
    } catch (e) { alert(`Render failed to start: ${e}`); }
  }

  return (
    <div style={{ background: theme.cardAlt, minHeight: 'calc(100vh - 60px)', padding: '32px 0' }}>
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 24px' }}>
        <Hero />
        <AnimatePresence mode="wait">
          {phase === 'setup' && (
            <motion.div key="setup" {...fade}>
              <SetupPhase {...{
                doc, uploadBusy, urlInput, focus, style, numTurns, language,
                avatars, voices, interviewer, expert,
              }}
                onUrlInput={setUrlInput} onFile={handleFile} onUrl={handleUrl}
                onFocusChange={setFocus} onApplyPrompt={(p) => setFocus(p.focus)}
                onStyle={setStyle} onNumTurns={setNumTurns} onLanguage={setLanguage}
                onInterviewer={setInterviewer} onExpert={setExpert}
                onGenerate={startScript} />
            </motion.div>
          )}
          {phase === 'scripting' && (
            <motion.div key="scripting" {...fade}>
              <ScriptStreamingView turns={streamingTurns} error={scriptError} />
            </motion.div>
          )}
          {phase === 'review' && (
            <motion.div key="review" {...fade}>
              <ScriptReview
                turns={streamingTurns} interviewer={interviewer} expert={expert}
                music={music} intro={intro}
                onMusic={setMusic} onIntro={setIntro}
                onRender={kickOffRender} onBack={() => setPhase('setup')} />
            </motion.div>
          )}
          {phase === 'rendering' && job && (
            <motion.div key="rendering" {...fade}>
              <RenderingView job={job} turns={streamingTurns} />
            </motion.div>
          )}
          {phase === 'done' && job && (
            <motion.div key="done" {...fade}>
              <ResultView job={job} turns={streamingTurns}
                interviewer={interviewer} expert={expert}
                onNew={() => {
                  setPhase('setup'); setDoc(null); setJob(null);
                  setStreamingTurns([]); setScriptId(null);
                }} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

const fade = {
  initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 }, transition: { duration: 0.25 },
};

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
        AI Podcast Generator
      </h1>
      <p style={{ margin: 0, fontSize: 16, opacity: 0.9, maxWidth: 640 }}>
        Transform any document into a dual-host conversation, with two AI avatars
        walking through your slides — in any language, in minutes.
      </p>
    </div>
  );
}

interface SetupProps {
  doc: PodDoc | null; uploadBusy: boolean;
  urlInput: string; onUrlInput: (v: string) => void;
  onFile: (f: File) => void; onUrl: () => void;
  focus: string; onFocusChange: (v: string) => void;
  onApplyPrompt: (p: typeof SAMPLE_PROMPTS[number]) => void;
  style: Style; onStyle: (s: Style) => void;
  numTurns: number; onNumTurns: (n: number) => void;
  language: string; onLanguage: (l: string) => void;
  avatars: AvatarOption[]; voices: VoiceOption[];
  interviewer: RoleConfig; expert: RoleConfig;
  onInterviewer: (r: RoleConfig) => void; onExpert: (r: RoleConfig) => void;
  onGenerate: () => void;
}
function SetupPhase(p: SetupProps) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 420px', gap: 24 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <Card title="1. Source material">
          <Uploader doc={p.doc} busy={p.uploadBusy}
            urlInput={p.urlInput} onUrlInput={p.onUrlInput}
            onFile={p.onFile} onUrl={p.onUrl} />
        </Card>
        <Card title="2. Conversation focus (optional)">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginBottom: 12 }}>
            {SAMPLE_PROMPTS.map((sp) => (
              <button key={sp.title} onClick={() => p.onApplyPrompt(sp)}
                style={{ textAlign: 'left', background: theme.cardAlt, border: `1px solid ${theme.border}`,
                  borderRadius: 10, padding: '12px 14px', cursor: 'pointer', fontSize: 13, color: theme.text,
                  transition: 'all 0.15s' }}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = theme.accent)}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = theme.border)}>
                <div style={{ fontSize: 18, marginBottom: 2 }}>{sp.emoji}</div>
                <div style={{ fontWeight: 700, marginBottom: 2 }}>{sp.title}</div>
                <div style={{ color: theme.muted, fontSize: 11, lineHeight: 1.4 }}>{sp.focus}</div>
              </button>
            ))}
          </div>
          <textarea value={p.focus} onChange={(e) => p.onFocusChange(e.target.value)}
            placeholder="Or describe your own angle — e.g. 'focus on ROI for retrofit customers'"
            style={{ width: '100%', minHeight: 60, border: `1px solid ${theme.border}`,
              borderRadius: 8, padding: 10, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' }} />
        </Card>
        <Card title="3. Conversation settings">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            <Field label="Style">
              <select value={p.style} onChange={(e) => p.onStyle(e.target.value as Style)} style={selectStyle}>
                <option value="casual">Casual</option>
                <option value="formal">Formal</option>
                <option value="debate">Debate</option>
                <option value="explainer">Explainer</option>
              </select>
            </Field>
            <Field label={`Turns: ${p.numTurns}`}>
              <input type="range" min={4} max={16} value={p.numTurns}
                onChange={(e) => p.onNumTurns(Number(e.target.value))} style={{ width: '100%' }} />
            </Field>
            <Field label="Language">
              <select value={p.language} onChange={(e) => p.onLanguage(e.target.value)} style={selectStyle}>
                <option value="en-US">English (US)</option>
                <option value="fr-FR">French (FR)</option>
              </select>
            </Field>
          </div>
        </Card>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <Card title="4. Cast">
          <RolePicker label="Interviewer 🎙️" role={p.interviewer} onChange={p.onInterviewer}
            avatars={p.avatars} voices={p.voices} />
          <div style={{ height: 16 }} />
          <RolePicker label="Expert 🧑‍🏫" role={p.expert} onChange={p.onExpert}
            avatars={p.avatars} voices={p.voices} />
        </Card>
        <button disabled={!p.doc} onClick={p.onGenerate}
          style={{
            background: !p.doc ? theme.border : `linear-gradient(135deg, ${theme.brand}, ${theme.accent})`,
            color: 'white', border: 'none', borderRadius: 12, padding: '16px 20px',
            fontSize: 16, fontWeight: 700, cursor: p.doc ? 'pointer' : 'not-allowed',
            boxShadow: p.doc ? theme.shadow : 'none',
          }}>
          ✨ Generate podcast script
        </button>
        {!p.doc && <div style={{ fontSize: 12, color: theme.muted, textAlign: 'center' }}>
          Upload a document first
        </div>}
      </div>
    </div>
  );
}

const selectStyle: React.CSSProperties = {
  width: '100%', border: `1px solid ${theme.border}`, borderRadius: 8,
  padding: '8px 10px', fontSize: 13, background: 'white',
};

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

function Uploader({ doc, busy, urlInput, onUrlInput, onFile, onUrl }: {
  doc: PodDoc | null; busy: boolean;
  urlInput: string; onUrlInput: (v: string) => void;
  onFile: (f: File) => void; onUrl: () => void;
}) {
  const [drag, setDrag] = useState(false);
  if (doc) {
    return (
      <div style={{ background: theme.cardAlt, borderRadius: 10, padding: 14,
        display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ fontSize: 28 }}>{kindEmoji(doc.source_kind)}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700 }}>{doc.title}</div>
          <div style={{ fontSize: 12, color: theme.muted }}>
            {doc.sections.length} sections
            {doc.slide_images.length > 0 && ` · ${doc.slide_images.length} slides`}
          </div>
        </div>
      </div>
    );
  }
  return (
    <>
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
        <div style={{ fontSize: 32 }}>📄</div>
        <div style={{ fontWeight: 600 }}>Drag a PPTX / PDF / DOCX here</div>
        <div style={{ fontSize: 12, color: theme.muted }}>or click to browse</div>
        <input type="file" accept=".pptx,.pdf,.docx,.txt,.md"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
          style={{ display: 'none' }} />
      </label>
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <input value={urlInput} onChange={(e) => onUrlInput(e.target.value)}
          placeholder="…or paste a URL (article, research page, etc.)"
          style={{ flex: 1, border: `1px solid ${theme.border}`, borderRadius: 8,
            padding: '8px 10px', fontSize: 13 }} />
        <button onClick={onUrl} disabled={busy || !urlInput.trim()}
          style={{ background: theme.brand, color: 'white', border: 'none', borderRadius: 8,
            padding: '8px 14px', fontSize: 13, fontWeight: 600,
            cursor: urlInput.trim() ? 'pointer' : 'not-allowed', opacity: urlInput.trim() ? 1 : 0.5 }}>
          Fetch
        </button>
      </div>
      {busy && <div style={{ fontSize: 12, color: theme.muted, marginTop: 8 }}>⏳ Processing…</div>}
    </>
  );
}
function kindEmoji(k: string) {
  return ({ pptx: '📊', pdf: '📕', docx: '📝', url: '🌐', txt: '📄', md: '📄' } as Record<string, string>)[k] ?? '📄';
}

function RolePicker({ label, role, onChange, avatars, voices }: {
  label: string; role: RoleConfig; onChange: (r: RoleConfig) => void;
  avatars: AvatarOption[]; voices: VoiceOption[];
}) {
  return (
    <div>
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 8, fontWeight: 600 }}>{label}</div>
      <input value={role.display_name} onChange={(e) => onChange({ ...role, display_name: e.target.value })}
        style={{ width: '100%', border: `1px solid ${theme.border}`, borderRadius: 8,
          padding: '8px 10px', fontSize: 13, marginBottom: 8 }}
        placeholder="Display name" />
      <div style={{ display: 'flex', gap: 8 }}>
        {avatars.map((a) => (
          <button key={a.id} onClick={() => onChange({ ...role, avatar: a.id })}
            style={{
              flex: 1, border: `2px solid ${role.avatar === a.id ? theme.accent : theme.border}`,
              borderRadius: 10, padding: 8, background: 'white', cursor: 'pointer',
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
            }}>
            <div style={{ fontSize: 20 }}>{a.id === 'harry' ? '👨‍💼' : '👩‍🏫'}</div>
            <div style={{ fontSize: 11, fontWeight: 600 }}>{a.display_name}</div>
          </button>
        ))}
      </div>
      <select value={role.voice} onChange={(e) => onChange({ ...role, voice: e.target.value })}
        style={{ ...selectStyle, marginTop: 8 }}>
        {voices.map((v) => (
          <option key={v.id} value={v.id}>
            {v.display_name}{v.hd ? ' · HD' : ''} ({v.language})
          </option>
        ))}
      </select>
    </div>
  );
}

function ScriptStreamingView({ turns, error }: { turns: DialogueTurn[]; error: string | null }) {
  return (
    <div style={{ background: theme.card, borderRadius: 14, padding: 28, boxShadow: theme.shadow }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1.2, ease: 'linear' }}
          style={{ width: 20, height: 20, borderRadius: '50%',
            border: `3px solid ${theme.border}`, borderTopColor: theme.accent }} />
        <div style={{ fontWeight: 700, fontSize: 16 }}>Generating script…</div>
        <div style={{ fontSize: 12, color: theme.muted }}>{turns.length} turns so far</div>
      </div>
      {error ? (<div style={{ color: '#dc2626', fontWeight: 600 }}>Error: {error}</div>)
             : (<TurnsList turns={turns} />)}
    </div>
  );
}

function ScriptReview({ turns, interviewer, expert, music, intro, onMusic, onIntro, onRender, onBack }: {
  turns: DialogueTurn[]; interviewer: RoleConfig; expert: RoleConfig;
  music: boolean; intro: boolean;
  onMusic: (b: boolean) => void; onIntro: (b: boolean) => void;
  onRender: () => void; onBack: () => void;
}) {
  return (
    <div style={{ background: theme.card, borderRadius: 14, padding: 28, boxShadow: theme.shadow }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <div style={{ fontWeight: 700, fontSize: 20 }}>📜 Script ready — review &amp; render</div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 12 }}>
          <label style={toggleLabel}><input type="checkbox" checked={intro} onChange={(e) => onIntro(e.target.checked)} /> Intro card</label>
          <label style={toggleLabel}><input type="checkbox" checked={music} onChange={(e) => onMusic(e.target.checked)} /> Background music</label>
        </div>
      </div>
      <TurnsList turns={turns} interviewer={interviewer} expert={expert} />
      <div style={{ marginTop: 24, display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
        <button onClick={onBack} style={secondaryBtn}>← Back to setup</button>
        <button onClick={onRender} style={primaryBtn}>🎬 Render podcast</button>
      </div>
    </div>
  );
}

function TurnsList({ turns, interviewer, expert }: {
  turns: DialogueTurn[]; interviewer?: RoleConfig; expert?: RoleConfig;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {turns.map((t) => (
        <motion.div key={t.idx} initial={{ opacity: 0, x: t.speaker === 'interviewer' ? -10 : 10 }}
          animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.3 }}
          style={{ display: 'flex', gap: 12,
            justifyContent: t.speaker === 'interviewer' ? 'flex-start' : 'flex-end' }}>
          <div style={{
            maxWidth: '72%', background: t.speaker === 'interviewer' ? theme.cardAlt : '#eff6ff',
            border: `1px solid ${theme.border}`, borderRadius: 12, padding: '10px 14px',
            fontSize: 14, lineHeight: 1.5,
          }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: theme.muted,
              textTransform: 'uppercase', letterSpacing: 1, marginBottom: 2 }}>
              {t.speaker === 'interviewer' ? '🎙️ ' : '🧑‍🏫 '}
              {t.speaker === 'interviewer'
                ? (interviewer?.display_name ?? 'Interviewer')
                : (expert?.display_name ?? 'Expert')}
              {t.slide_idx !== null && t.slide_idx !== undefined && (
                <span style={{ marginLeft: 8, background: theme.accent, color: 'white',
                  padding: '1px 6px', borderRadius: 6, fontSize: 9 }}>
                  slide {t.slide_idx + 1}
                </span>
              )}
            </div>
            {t.text}
          </div>
        </motion.div>
      ))}
    </div>
  );
}

const STAGES: Array<{ key: JobState | 'queued'; label: string; emoji: string }> = [
  { key: 'queued', label: 'Queued', emoji: '⏳' },
  { key: 'rendering', label: 'Rendering avatars', emoji: '🎭' },
  { key: 'composing', label: 'Composing video', emoji: '🎬' },
  { key: 'done', label: 'Ready', emoji: '✅' },
];

function RenderingView({ job, turns }: { job: PodcastJob; turns: DialogueTurn[] }) {
  const stageIdx = Math.max(0, STAGES.findIndex((s) => s.key === job.state));
  const pct = job.progress.total ? Math.round(100 * job.progress.completed / job.progress.total) : 0;
  return (
    <div style={{ background: theme.card, borderRadius: 14, padding: 32, boxShadow: theme.shadow }}>
      <div style={{ fontWeight: 700, fontSize: 20, marginBottom: 20 }}>🎬 Building your podcast…</div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        {STAGES.map((s, i) => {
          const active = i === stageIdx;
          const done = i < stageIdx;
          return (
            <div key={s.key} style={{
              flex: 1, padding: '14px 16px', borderRadius: 10,
              background: done ? '#dcfce7' : active ? '#dbeafe' : theme.cardAlt,
              border: `2px solid ${done ? '#22c55e' : active ? theme.accent : theme.border}`,
              transition: 'all 0.3s',
            }}>
              <div style={{ fontSize: 22 }}>{s.emoji}</div>
              <div style={{ fontSize: 12, fontWeight: 700, marginTop: 4 }}>{s.label}</div>
              {active && (
                <motion.div animate={{ opacity: [0.4, 1, 0.4] }}
                  transition={{ repeat: Infinity, duration: 1.4 }}
                  style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>
                  {job.progress.message || 'working…'}
                </motion.div>
              )}
            </div>
          );
        })}
      </div>
      {job.state === 'rendering' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between',
            fontSize: 12, color: theme.muted, marginBottom: 6 }}>
            <span>Avatar clips rendered</span>
            <span>{job.progress.completed} / {job.progress.total}</span>
          </div>
          <div style={{ height: 8, background: theme.cardAlt, borderRadius: 99, overflow: 'hidden' }}>
            <motion.div animate={{ width: `${pct}%` }} transition={{ duration: 0.4 }}
              style={{ height: '100%',
                background: `linear-gradient(90deg, ${theme.brand}, ${theme.accent})` }} />
          </div>
        </div>
      )}
      {job.state === 'failed' && (
        <div style={{ color: '#dc2626', marginTop: 16, fontWeight: 600 }}>❌ {job.error}</div>
      )}
      <div style={{ marginTop: 24, fontSize: 12, color: theme.muted }}>
        Script has {turns.length} turns. This usually takes 2–4 minutes.
      </div>
    </div>
  );
}

function ResultView({ job, turns, interviewer, expert, onNew }: {
  job: PodcastJob; turns: DialogueTurn[];
  interviewer: RoleConfig; expert: RoleConfig;
  onNew: () => void;
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: 24 }}>
      <Card title="🎧 Your podcast">
        {job.outputs.mp4_url ? (
          <video controls autoPlay src={job.outputs.mp4_url}
            style={{ width: '100%', borderRadius: 10, background: 'black', aspectRatio: '16 / 9' }} />
        ) : (
          <div style={{ color: theme.muted }}>Video unavailable.</div>
        )}
        <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
          {job.outputs.mp3_url && (
            <a href={job.outputs.mp3_url} download style={primaryBtn as any}>⬇ Audio (MP3)</a>
          )}
          {job.outputs.srt_url && (
            <a href={job.outputs.srt_url} download style={secondaryBtn as any}>⬇ Transcript (SRT)</a>
          )}
          <a href="/podcast/library" style={{ ...secondaryBtn, marginLeft: 'auto' } as any}>📚 Library</a>
          <button onClick={onNew} style={secondaryBtn}>+ New podcast</button>
        </div>
        {job.archive_state === 'archiving' && (
          <div style={{ marginTop: 10, fontSize: 12, color: theme.muted }}>
            💾 Saving to library…
          </div>
        )}
        {job.archive_state === 'published' && (
          <div style={{ marginTop: 10, fontSize: 12, color: '#15803d' }}>
            ✓ Saved to library — <a href="/podcast/library" style={{ color: theme.brand, fontWeight: 600 }}>view all podcasts</a>
          </div>
        )}
        {job.archive_state === 'failed' && (
          <div style={{ marginTop: 10, fontSize: 12, color: '#b45309' }}>
            ⚠ Could not save to library (video still downloadable above).
          </div>
        )}
      </Card>
      <Card title="Transcript">
        <div style={{ maxHeight: 520, overflow: 'auto', paddingRight: 6 }}>
          <TurnsList turns={turns} interviewer={interviewer} expert={expert} />
        </div>
      </Card>
    </div>
  );
}

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
const toggleLabel: React.CSSProperties = {
  fontSize: 12, color: theme.muted, display: 'flex', alignItems: 'center', gap: 6,
};

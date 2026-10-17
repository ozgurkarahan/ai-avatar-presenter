import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft, BarChart3, CheckCircle2, Clapperboard, Clock, Download, FileText, FlaskConical, Globe,
  GraduationCap, Headphones, Library, Plus, Presentation, Scale, Sparkles, Users, type LucideIcon,
} from 'lucide-react';
import {
  DialogueTurn, Document as PodDoc, JobState, Layout,
  PodcastJob, RoleConfig, Speaker, Style, VoiceOption, AudienceLevel,
  AUDIENCE_LEVELS, AUDIENCE_LEVEL_LABELS, toAudienceLevel,
  getJob, ingestFile, ingestUrl, listVoices,
  startRender, streamScript,
} from '../services/podcast';
import { type AvatarInfo, listAvatars, pickAvatarForGender } from '../services/avatars';
import { useAuth } from '../services/auth';
import { GatedPanel } from '../components/AuthGate';
import {
  Alert, Button, ButtonLink, Checkbox, Chip, Dropzone, Field, HostDisc, Input, LivePill, PageHeader,
  Progress, SectionHead, Select, Spinner, Steps, Textarea, Waveform, buttonClass, languageName, pluralize,
} from '../ui';
import '../styles/pages/podcast-create.css';

const SAMPLE_PROMPTS: { icon: LucideIcon; title: string; focus: string }[] = [
  { icon: BarChart3, title: 'Executive Summary', focus: 'Summarize the key strategic points for a C-level audience.' },
  { icon: FlaskConical, title: 'Product Deep-Dive', focus: 'Explain the technical mechanics clearly to an engineering audience.' },
  { icon: Scale, title: 'Balanced Debate', focus: 'Present the strongest arguments for and against the proposal.' },
  { icon: GraduationCap, title: 'Classroom Explainer', focus: 'Make this accessible to a motivated student. Use analogies.' },
];

const LANGUAGES = ['en-US', 'fr-FR', 'es-ES', 'de-DE', 'it-IT', 'pt-BR', 'zh-CN', 'ja-JP'];

type Phase = 'setup' | 'scripting' | 'review' | 'rendering' | 'done';

const WIZARD_STEPS = ['Source', 'Script', 'Review & cast', 'Render', 'Listen'];
const PHASE_STEP: Record<Phase, number> = { setup: 0, scripting: 1, review: 2, rendering: 3, done: 4 };

function Header({ actions }: { actions?: React.ReactNode }) {
  return (
    <PageHeader
      eyebrow="Create · Two-host podcast"
      title={<>Two hosts, <em>one conversation.</em></>}
      lead="Transform any document into a dual-host conversation, with two AI avatars walking through your slides — in any language, in minutes."
      actions={actions}
    />
  );
}

export default function PodcastPage() {
  const auth = useAuth();
  if (auth.loading || !auth.is_admin) {
    return (
      <div className="container page podcast-create">
        <Header />
        {!auth.loading && (
          <GatedPanel
            icon={Headphones}
            title="Podcast creation is limited to demo users"
            description="Generating a podcast uploads a document, writes a script with an LLM and renders two AI avatars. You can still watch every published podcast in the library."
            action="create your own podcast"
            links={[{ href: '/podcast/library', label: 'Browse the podcast library' }, { href: '/video/library', label: 'Browse the video library' }]}
          />
        )}
      </div>
    );
  }
  return <PodcastGenerator />;
}

function PodcastGenerator() {
  const [phase, setPhase] = useState<Phase>('setup');
  const [doc, setDoc] = useState<PodDoc | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [focus, setFocus] = useState('');
  const [style, setStyle] = useState<Style>('casual');
  const [audienceLevel, setAudienceLevel] = useState<AudienceLevel | null>(null);
  const [numTurns, setNumTurns] = useState(8);
  const [language, setLanguage] = useState('en-US');
  const [avatars, setAvatars] = useState<AvatarInfo[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [interviewer, setInterviewer] = useState<RoleConfig>({
    display_name: 'Dr. Marc Chen', avatar: '', voice: 'en-US-Andrew:DragonHDLatestNeural',
  });
  const [expert, setExpert] = useState<RoleConfig>({
    display_name: 'Dr. Sophie Patel', avatar: '', voice: 'en-US-Ava:DragonHDLatestNeural',
  });
  const [streamingTurns, setStreamingTurns] = useState<DialogueTurn[]>([]);
  const [scriptId, setScriptId] = useState<string | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const [job, setJob] = useState<PodcastJob | null>(null);
  const [music, setMusic] = useState(true);
  const [intro, setIntro] = useState(true);
  const [layout] = useState<Layout>('split_screen_with_slides');

  useEffect(() => {
    listAvatars().then((list) => {
      setAvatars(list);
      const ids = new Set(list.map((a) => a.id));
      const male = pickAvatarForGender(list, 'male');
      const female = pickAvatarForGender(list, 'female');
      setInterviewer((prev) => (ids.has(prev.avatar) ? prev : { ...prev, avatar: male?.id ?? '' }));
      setExpert((prev) => (ids.has(prev.avatar) ? prev : { ...prev, avatar: female?.id ?? '' }));
    }).catch(() => {});
  }, []);
  useEffect(() => {
    listVoices(language).then((vs) => {
      setVoices(vs);
      if (vs.length === 0) return;
      // Auto-swap interviewer/expert voices when the selected language changes,
      // unless the user's current voice already matches the new language.
      const intOk = vs.some(v => v.id === interviewer.voice);
      const expOk = vs.some(v => v.id === expert.voice);
      if (intOk && expOk) return;
      const male = vs.find(v => v.gender === 'male');
      const female = vs.find(v => v.gender === 'female');
      const intPick = male ?? vs[0];
      const expPick = female && female.id !== intPick.id ? female : vs.find(v => v.id !== intPick.id) ?? vs[0];
      if (!intOk) setInterviewer(prev => ({ ...prev, voice: intPick.id }));
      if (!expOk) setExpert(prev => ({ ...prev, voice: expPick.id }));
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language]);

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
      {
        document_id: doc.id, language, style, length: 'medium', num_turns: numTurns, focus: focus || undefined,
        audience_level: audienceLevel,
      },
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

  const cast: Cast = { interviewer, expert, avatars };

  return (
    <div className="container page podcast-create">
      <Header actions={<ButtonLink to="/podcast/library" icon={Library}>Podcast library</ButtonLink>} />
      <div className="pc-steps">
        <Steps steps={WIZARD_STEPS} current={PHASE_STEP[phase]} />
      </div>
      <AnimatePresence mode="wait">
        {phase === 'setup' && (
          <motion.div key="setup" {...fade}>
            <SetupPhase {...{
              doc, uploadBusy, urlInput, focus, style, audienceLevel, numTurns, language,
            }}
              onUrlInput={setUrlInput} onFile={handleFile} onUrl={handleUrl}
              onFocusChange={setFocus} onApplyPrompt={(p) => setFocus(p.focus)}
              onStyle={setStyle} onAudienceLevel={setAudienceLevel}
              onNumTurns={setNumTurns} onLanguage={setLanguage}
              onGenerate={startScript} />
          </motion.div>
        )}
        {phase === 'scripting' && (
          <motion.div key="scripting" {...fade}>
            <ScriptStreamingView turns={streamingTurns} error={scriptError} cast={cast} />
          </motion.div>
        )}
        {phase === 'review' && (
          <motion.div key="review" {...fade}>
            <ScriptReview
              turns={streamingTurns} cast={cast} voices={voices}
              onInterviewer={setInterviewer} onExpert={setExpert}
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
            <ResultView job={job} turns={streamingTurns} cast={cast}
              onNew={() => {
                setPhase('setup'); setDoc(null); setJob(null);
                setStreamingTurns([]); setScriptId(null);
              }} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const fade = {
  initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 }, transition: { duration: 0.25 },
};

interface Cast { interviewer: RoleConfig; expert: RoleConfig; avatars: AvatarInfo[] }

const ROLE_LABEL: Record<Speaker, string> = { interviewer: 'Interviewer', expert: 'Expert' };

function hostFor(cast: Cast, speaker: Speaker) {
  const role = speaker === 'interviewer' ? cast.interviewer : cast.expert;
  const avatar = cast.avatars.find((a) => a.id === role.avatar);
  return { display_name: role.display_name || ROLE_LABEL[speaker], thumbnail_url: avatar?.thumbnail_url ?? null };
}

interface SetupProps {
  doc: PodDoc | null; uploadBusy: boolean;
  urlInput: string; onUrlInput: (v: string) => void;
  onFile: (f: File) => void; onUrl: () => void;
  focus: string; onFocusChange: (v: string) => void;
  onApplyPrompt: (p: typeof SAMPLE_PROMPTS[number]) => void;
  style: Style; onStyle: (s: Style) => void;
  audienceLevel: AudienceLevel | null; onAudienceLevel: (l: AudienceLevel | null) => void;
  numTurns: number; onNumTurns: (n: number) => void;
  language: string; onLanguage: (l: string) => void;
  onGenerate: () => void;
}
function SetupPhase(p: SetupProps) {
  return (
    <div className="pc-setup">
      <div className="pc-setup__main">
        <section className="pc-section">
          <SectionHead title="Source material" aside="Required" />
          <Uploader doc={p.doc} busy={p.uploadBusy}
            urlInput={p.urlInput} onUrlInput={p.onUrlInput}
            onFile={p.onFile} onUrl={p.onUrl} />
        </section>
        <section className="pc-section">
          <SectionHead title="Conversation angle" aside="Optional" />
          <div className="pc-prompts">
            {SAMPLE_PROMPTS.map((sp) => (
              <button
                key={sp.title}
                type="button"
                className="pc-prompt"
                aria-pressed={p.focus === sp.focus}
                onClick={() => p.onApplyPrompt(sp)}
              >
                <span className="pc-prompt__title"><sp.icon aria-hidden />{sp.title}</span>
                <span className="pc-prompt__text">{sp.focus}</span>
              </button>
            ))}
          </div>
          <Field label="Your own angle" hint="Pick a preset above or describe the angle the hosts should take.">
            <Textarea
              value={p.focus}
              onChange={(e) => p.onFocusChange(e.target.value)}
              rows={3}
              placeholder="e.g. focus on when to use open-weight models"
            />
          </Field>
        </section>
      </div>
      <aside className="pc-setup__side">
        <div className="card pc-settings">
          <h2 className="pc-card-title">Conversation settings</h2>
          <Field label="Style">
            <Select value={p.style} onChange={(e) => p.onStyle(e.target.value as Style)}>
              <option value="casual">Casual</option>
              <option value="formal">Formal</option>
              <option value="debate">Debate</option>
              <option value="explainer">Explainer</option>
            </Select>
          </Field>
          <Field label="Audience level" hint="Tunes vocabulary and depth for the listeners.">
            <Select
              value={p.audienceLevel ?? ''}
              onChange={(e) => p.onAudienceLevel(toAudienceLevel(e.target.value))}
            >
              <option value="">Any (default)</option>
              {AUDIENCE_LEVELS.map((lvl) => <option key={lvl} value={lvl}>{AUDIENCE_LEVEL_LABELS[lvl]}</option>)}
            </Select>
          </Field>
          <Field label={<>Turns <span className="pc-range-value tabular">{p.numTurns}</span></>} hint="Between 4 and 16 exchanges.">
            <input
              type="range" min={4} max={16} value={p.numTurns}
              className="pc-range"
              onChange={(e) => p.onNumTurns(Number(e.target.value))}
            />
          </Field>
          <Field label="Language">
            <Select value={p.language} onChange={(e) => p.onLanguage(e.target.value)}>
              {LANGUAGES.map((code) => <option key={code} value={code}>{languageName(code)}</option>)}
            </Select>
          </Field>
          <Button variant="primary" size="lg" block icon={Sparkles} disabled={!p.doc} onClick={p.onGenerate}>
            Generate podcast script
          </Button>
          {!p.doc && <p className="pc-settings__hint">Upload a document first</p>}
        </div>
      </aside>
    </div>
  );
}

const KIND_ICON: Record<string, LucideIcon> = { pptx: Presentation, url: Globe };

function Uploader({ doc, busy, urlInput, onUrlInput, onFile, onUrl }: {
  doc: PodDoc | null; busy: boolean;
  urlInput: string; onUrlInput: (v: string) => void;
  onFile: (f: File) => void; onUrl: () => void;
}) {
  if (doc) {
    const Icon = KIND_ICON[doc.source_kind] ?? FileText;
    return (
      <div className="pc-doc">
        <span className="pc-doc__icon" aria-hidden><Icon /></span>
        <div className="pc-doc__body">
          <div className="pc-doc__title">{doc.title}</div>
          <div className="pc-doc__meta">
            {pluralize(doc.sections.length, 'section')}
            {doc.slide_images.length > 0 && ` · ${pluralize(doc.slide_images.length, 'slide')}`}
          </div>
        </div>
        <Chip tone="sage" icon={CheckCircle2}>Ready</Chip>
      </div>
    );
  }
  return (
    <div className="pc-uploader">
      <Dropzone
        onFile={onFile}
        accept=".pptx,.pdf,.docx,.txt,.md"
        busy={busy}
        busyTitle="Processing…"
        title="Drop a PPTX, PDF or DOCX"
        hint="or click to browse · TXT and Markdown work too"
      />
      <div className="pc-url">
        <Field label="Or fetch a web page" className="pc-url__field">
          <Input
            type="url"
            value={urlInput}
            onChange={(e) => onUrlInput(e.target.value)}
            placeholder="https://… article, research page, etc."
          />
        </Field>
        <Button icon={Globe} onClick={onUrl} disabled={busy || !urlInput.trim()}>Fetch</Button>
      </div>
      {busy && <Spinner label="Processing…" />}
    </div>
  );
}

function RoleCard({ speaker, role, onChange, avatars, voices }: {
  speaker: Speaker; role: RoleConfig; onChange: (r: RoleConfig) => void;
  avatars: AvatarInfo[]; voices: VoiceOption[];
}) {
  const avatar = avatars.find((a) => a.id === role.avatar);
  const voice = voices.find((v) => v.id === role.voice);
  const lead = speaker === 'interviewer';
  return (
    <article className={`pc-host pc-host--${speaker}`} aria-label={ROLE_LABEL[speaker]}>
      <div className="pc-host__portrait">
        <HostDisc
          host={{ display_name: role.display_name || ROLE_LABEL[speaker], thumbnail_url: avatar?.thumbnail_url ?? null }}
          size={120}
          speaking={lead}
          tone={lead ? 'sage' : 'sand'}
          label=""
        />
        <div className="pc-host__id">
          {lead ? <LivePill>Interviewer · leads</LivePill> : <span className="eyebrow">Expert</span>}
          <span className="pc-host__name">{role.display_name || ROLE_LABEL[speaker]}</span>
          <span className="pc-host__meta">
            {[avatar?.display_name, voice?.display_name].filter(Boolean).join(' · ') || 'Choose an avatar and a voice'}
          </span>
        </div>
      </div>
      <div className="pc-host__fields">
        <Field label="Display name">
          <Input
            value={role.display_name}
            onChange={(e) => onChange({ ...role, display_name: e.target.value })}
            placeholder="Display name"
          />
        </Field>
        <Field label="Avatar">
          <Select value={role.avatar} onChange={(e) => onChange({ ...role, avatar: e.target.value })}>
            {!role.avatar && <option value="">Choose an avatar</option>}
            {avatars.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}
          </Select>
        </Field>
        <Field label="Voice">
          <Select value={role.voice} onChange={(e) => onChange({ ...role, voice: e.target.value })}>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.display_name}{v.hd ? ' · HD' : ''} ({v.language})
              </option>
            ))}
          </Select>
        </Field>
      </div>
    </article>
  );
}

function ScriptStreamingView({ turns, error, cast }: { turns: DialogueTurn[]; error: string | null; cast: Cast }) {
  return (
    <section className="pc-panel" aria-live="polite">
      <div className="pc-panel__head">
        {error ? <span className="eyebrow">Script</span> : <Waveform />}
        <h2 className="pc-panel__title">{error ? 'The script could not be written' : 'Writing the script…'}</h2>
        <span className="eyebrow tabular">{pluralize(turns.length, 'turn')} so far</span>
      </div>
      {error
        ? <Alert tone="error" title="Script generation failed">{error}</Alert>
        : (
          <>
            {turns.length === 0 && <Spinner label="The hosts are reading your document…" />}
            <TurnsList turns={turns} cast={cast} />
          </>
        )}
    </section>
  );
}

function ScriptReview({
  turns, cast, voices, onInterviewer, onExpert, music, intro, onMusic, onIntro, onRender, onBack,
}: {
  turns: DialogueTurn[]; cast: Cast; voices: VoiceOption[];
  onInterviewer: (r: RoleConfig) => void; onExpert: (r: RoleConfig) => void;
  music: boolean; intro: boolean;
  onMusic: (b: boolean) => void; onIntro: (b: boolean) => void;
  onRender: () => void; onBack: () => void;
}) {
  return (
    <div className="pc-review">
      <section className="pc-section">
        <SectionHead title="The script" aside={pluralize(turns.length, 'turn')} />
        <TurnsList turns={turns} cast={cast} />
      </section>
      <section className="pc-section">
        <SectionHead title="Cast your hosts" aside="Avatars & voices" />
        <div className="pc-cast">
          <RoleCard speaker="interviewer" role={cast.interviewer} onChange={onInterviewer}
            avatars={cast.avatars} voices={voices} />
          <RoleCard speaker="expert" role={cast.expert} onChange={onExpert}
            avatars={cast.avatars} voices={voices} />
        </div>
      </section>
      <section className="pc-bar" aria-label="Production">
        <div className="pc-bar__options">
          <span className="eyebrow">Production</span>
          <Checkbox label="Intro card" checked={intro} onChange={(e) => onIntro(e.target.checked)} />
          <Checkbox label="Background music" checked={music} onChange={(e) => onMusic(e.target.checked)} />
        </div>
        <div className="pc-bar__actions">
          <Button icon={ArrowLeft} onClick={onBack}>Back to setup</Button>
          <Button variant="primary" icon={Clapperboard} onClick={onRender}>Render podcast</Button>
        </div>
      </section>
    </div>
  );
}

function TurnsList({ turns, cast }: { turns: DialogueTurn[]; cast: Cast }) {
  if (turns.length === 0) return null;
  return (
    <ol className="pc-transcript">
      {turns.map((t) => {
        const host = hostFor(cast, t.speaker);
        return (
          <motion.li
            key={t.idx}
            className={`pc-turn pc-turn--${t.speaker}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <HostDisc host={host} size={36} tone={t.speaker === 'expert' ? 'sand' : 'sage'} label="" />
            <div className="pc-turn__body">
              <div className="pc-turn__who">
                <span className="pc-turn__name">{host.display_name}</span>
                {t.slide_idx !== null && t.slide_idx !== undefined && (
                  <Chip className="pc-turn__slide">Slide {t.slide_idx + 1}</Chip>
                )}
              </div>
              <p className="pc-turn__text">{t.text}</p>
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}

const STAGES: Array<{ key: JobState | 'queued'; label: string; icon: LucideIcon }> = [
  { key: 'queued', label: 'Queued', icon: Clock },
  { key: 'rendering', label: 'Rendering avatars', icon: Users },
  { key: 'composing', label: 'Composing video', icon: Clapperboard },
  { key: 'done', label: 'Ready', icon: CheckCircle2 },
];

function RenderingView({ job, turns }: { job: PodcastJob; turns: DialogueTurn[] }) {
  const stageIdx = Math.max(0, STAGES.findIndex((s) => s.key === job.state));
  const pct = job.progress.total ? Math.round(100 * job.progress.completed / job.progress.total) : 0;
  return (
    <section className="pc-panel" aria-live="polite">
      <div className="pc-panel__head">
        {job.state === 'failed' ? <span className="eyebrow">Render</span> : <Spinner />}
        <h2 className="pc-panel__title">Building your podcast…</h2>
      </div>
      <ol className="pc-stages">
        {STAGES.map((s, i) => {
          const active = i === stageIdx;
          const done = i < stageIdx;
          return (
            <li
              key={s.key}
              className={['pc-stage', active && 'is-active', done && 'is-done'].filter(Boolean).join(' ')}
              aria-current={active ? 'step' : undefined}
            >
              <span className="pc-stage__icon" aria-hidden><s.icon /></span>
              <span className="pc-stage__label">{s.label}</span>
              {active && <LivePill className="pc-stage__msg">{job.progress.message || 'working…'}</LivePill>}
            </li>
          );
        })}
      </ol>
      {job.state === 'rendering' && (
        <div className="pc-progress">
          <div className="pc-progress__row">
            <span>Avatar clips rendered</span>
            <span className="tabular">{job.progress.completed} / {job.progress.total}</span>
          </div>
          <Progress value={pct / 100} label="Avatar clips rendered" />
        </div>
      )}
      {job.state === 'failed' && (
        <Alert tone="error" title="Render failed">{job.error}</Alert>
      )}
      <p className="pc-panel__foot">
        Script has {pluralize(turns.length, 'turn')}. This usually takes 2–4 minutes.
      </p>
    </section>
  );
}

function ResultView({ job, turns, cast, onNew }: {
  job: PodcastJob; turns: DialogueTurn[]; cast: Cast;
  onNew: () => void;
}) {
  return (
    <div className="pc-result">
      <section className="pc-result__main">
        <SectionHead title="Your podcast" aside="Ready" />
        <div className="stage pc-result__stage">
          {job.outputs.mp4_url ? (
            <video controls autoPlay src={job.outputs.mp4_url} className="pc-result__video" />
          ) : (
            <div className="pc-result__video pc-result__video--empty">Video unavailable.</div>
          )}
        </div>
        <div className="pc-result__actions">
          {job.outputs.mp3_url && (
            <a href={job.outputs.mp3_url} download className={buttonClass({ variant: 'primary' })}>
              <Download aria-hidden />Audio (MP3)
            </a>
          )}
          {job.outputs.srt_url && (
            <a href={job.outputs.srt_url} download className={buttonClass({})}>
              <Download aria-hidden />Transcript (SRT)
            </a>
          )}
          <span className="pc-result__spacer" />
          <a href="/podcast/library" className={buttonClass({ variant: 'ghost' })}>
            <Library aria-hidden />Library
          </a>
          <Button icon={Plus} onClick={onNew}>New podcast</Button>
        </div>
        {job.archive_state === 'archiving' && (
          <Spinner label="Saving to library…" />
        )}
        {job.archive_state === 'published' && (
          <Alert tone="success">
            Saved to library as a draft (publish it there to share it publicly) — <a href="/podcast/library">view all podcasts</a>
          </Alert>
        )}
        {job.archive_state === 'failed' && (
          <Alert tone="clay">Could not save to library (video still downloadable above).</Alert>
        )}
      </section>
      <section className="pc-result__side">
        <SectionHead title="Transcript" aside={pluralize(turns.length, 'turn')} />
        <div className="pc-result__transcript">
          <TurnsList turns={turns} cast={cast} />
        </div>
      </section>
    </div>
  );
}

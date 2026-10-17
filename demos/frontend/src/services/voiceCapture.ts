/**
 * Microphone capture for raise-hand voice questions.
 *
 * - Separate from the receive-only avatar peer connection.
 * - AudioWorklet (public/pcm-capture-worklet.js) downsamples to 16 kHz mono PCM16.
 * - Energy VAD: speech starts above RMS 0.008, ends after 1.8 s of silence,
 *   15 s max, 5 s initial-silence cutoff. Timing uses audio time, not timers.
 * - Emits base64 frames (<= 16384 decoded bytes) with a strictly increasing seq.
 */

export type CaptureEndReason = 'silence' | 'max' | 'manual' | 'no_speech' | 'cancelled';

export interface CaptureEnd {
  reason: CaptureEndReason;
  /** Decoded bytes sent through onFrame. */
  bytes: number;
  frames: number;
  heardSpeech: boolean;
}

export interface CaptureCallbacks {
  onFrame: (audioBase64: string, seq: number) => void;
  /** Peak RMS (0..1) roughly every 100 ms, for a level meter. */
  onLevel?: (rms: number) => void;
  onEnd: (end: CaptureEnd) => void;
}

export interface CaptureLimits {
  startRms: number;
  silenceMs: number;
  maxMs: number;
  initialSilenceMs: number;
  /** Target frame size (100 ms of audio = 3200 bytes). */
  frameBytes: number;
  maxFrameBytes: number;
  maxBytes: number;
  preRollMs: number;
  /** Audio kept before speech is detected (sent on a manual Done). */
  maxPreRollMs: number;
}

export const DEFAULT_CAPTURE_LIMITS: CaptureLimits = {
  startRms: 0.008,
  silenceMs: 1800,
  maxMs: 15000,
  initialSilenceMs: 5000,
  frameBytes: 3200,
  maxFrameBytes: 16384,
  maxBytes: 480000,
  preRollMs: 300,
  maxPreRollMs: 3000,
};

const SAMPLE_RATE = 16000;
const BYTES_PER_MS = (SAMPLE_RATE * 2) / 1000;
const WORKLET_URL = '/pcm-capture-worklet.js';

export class MicError extends Error {
  constructor(public code: 'denied' | 'unavailable' | 'unsupported', message: string) {
    super(message);
    this.name = 'MicError';
  }
}

export function micErrorMessage(err: unknown): string {
  if (err instanceof MicError) return err.message;
  return 'The microphone could not be started.';
}

export function bytesToBase64(bytes: Uint8Array): string {
  let bin = '';
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) {
    bin += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + step)));
  }
  return btoa(bin);
}

/**
 * Pure VAD + framing (no audio APIs, unit-testable). Fed 16 kHz PCM16 chunks
 * with their RMS; emits frames via `onFrame`. Normal frames are 100 ms; a final
 * flush (Done / end of speech) uses frames up to `maxFrameBytes` so it never
 * bursts more than a handful of messages.
 */
export class CaptureSegmenter {
  private t = 0;
  private heard = false;
  private lastVoiceAt = 0;
  private speechStartAt = 0;
  private preRoll: Uint8Array[] = [];
  private preRollBytes = 0;
  private pending: Uint8Array[] = [];
  private pendingBytes = 0;
  private sent = 0;
  private seq = 0;
  private ended = false;
  readonly limits: CaptureLimits;

  constructor(limits: Partial<CaptureLimits>, private onFrame: (frame: Uint8Array, seq: number) => void) {
    const l = { ...DEFAULT_CAPTURE_LIMITS, ...limits };
    l.maxFrameBytes = Math.max(2, Math.floor(l.maxFrameBytes / 2) * 2);
    l.frameBytes = Math.min(l.frameBytes, l.maxFrameBytes);
    l.maxPreRollMs = Math.min(l.maxPreRollMs, l.initialSilenceMs);
    this.limits = l;
  }

  get bytesSent(): number { return this.sent; }
  get framesSent(): number { return this.seq; }
  get heardSpeech(): boolean { return this.heard; }

  /** Feed one chunk. Returns the end reason when the question is over (then call `end`). */
  push(bytes: Uint8Array, rms: number): CaptureEndReason | null {
    if (this.ended) return null;
    this.t += bytes.length / BYTES_PER_MS;
    const voiced = rms > this.limits.startRms;
    if (!this.heard) {
      this.preRoll.push(bytes);
      this.preRollBytes += bytes.length;
      const cap = this.limits.maxPreRollMs * BYTES_PER_MS;
      while (this.preRollBytes > cap && this.preRoll.length > 1) this.preRollBytes -= this.preRoll.shift()!.length;
      if (voiced) {
        this.heard = true;
        this.lastVoiceAt = this.t;
        this.speechStartAt = this.t;
        this.promotePreRoll(this.limits.preRollMs);
      } else if (this.t >= this.limits.initialSilenceMs) {
        return 'no_speech';
      }
    } else {
      if (voiced) this.lastVoiceAt = this.t;
      this.queue(bytes);
    }
    if (this.heard && this.t - this.lastVoiceAt >= this.limits.silenceMs) return 'silence';
    if (this.sent + this.pendingBytes >= this.limits.maxBytes || (this.heard && this.t - this.speechStartAt >= this.limits.maxMs)) return 'max';
    this.flush(false);
    return null;
  }

  /** Finish: send what is left (manual Done also sends the pre-roll), or discard. */
  end(reason: CaptureEndReason): void {
    if (this.ended) return;
    this.ended = true;
    if (reason === 'no_speech' || reason === 'cancelled') {
      this.pending = [];
      this.pendingBytes = 0;
      this.preRoll = [];
      return;
    }
    if (reason === 'manual' && !this.heard) this.promotePreRoll(Number.POSITIVE_INFINITY);
    this.flush(true);
  }

  private promotePreRoll(keepMs: number): void {
    const keep = keepMs * BYTES_PER_MS;
    const chunks: Uint8Array[] = [];
    let n = 0;
    for (let i = this.preRoll.length - 1; i >= 0 && n < keep; i--) {
      chunks.unshift(this.preRoll[i]);
      n += this.preRoll[i].length;
    }
    this.preRoll = [];
    this.preRollBytes = 0;
    chunks.forEach((c) => this.queue(c));
  }

  private queue(bytes: Uint8Array): void {
    this.pending.push(bytes);
    this.pendingBytes += bytes.length;
  }

  private flush(final: boolean): void {
    const target = final ? this.limits.maxFrameBytes : this.limits.frameBytes;
    while (this.pendingBytes >= target || (final && this.pendingBytes > 0)) {
      const room = this.limits.maxBytes - this.sent;
      if (room <= 0) { this.pending = []; this.pendingBytes = 0; return; }
      const size = Math.min(target, this.pendingBytes, room);
      const frame = new Uint8Array(size);
      let off = 0;
      while (off < size) {
        const head = this.pending[0];
        const take = Math.min(head.length, size - off);
        frame.set(head.subarray(0, take), off);
        off += take;
        if (take === head.length) this.pending.shift();
        else this.pending[0] = head.subarray(take);
      }
      this.pendingBytes -= size;
      this.sent += size;
      this.onFrame(frame, this.seq++);
    }
  }
}

type Ctor = typeof AudioContext;

export class VoiceCapture {
  private node: AudioWorkletNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private sink: GainNode | null = null;
  private running = false;
  private closed = false;
  private cb: CaptureCallbacks | null = null;
  private seg: CaptureSegmenter | null = null;
  private levelPeak = 0;
  private levelN = 0;

  private constructor(private ctx: AudioContext, private stream: MediaStream) {}

  /**
   * Call synchronously from a click handler: the AudioContext is created
   * before the first await so browsers start it in the running state.
   */
  static async open(): Promise<VoiceCapture> {
    const AC: Ctor | undefined = (window as any).AudioContext ?? (window as any).webkitAudioContext;
    if (!AC || !navigator.mediaDevices?.getUserMedia) {
      throw new MicError('unsupported', 'This browser cannot record audio here. Use a recent browser over HTTPS.');
    }
    const ctx = new AC();
    void ctx.resume().catch(() => {});
    if (!ctx.audioWorklet) {
      void ctx.close().catch(() => {});
      throw new MicError('unsupported', 'This browser cannot record audio here. Use a recent browser over HTTPS.');
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch (e: any) {
      void ctx.close().catch(() => {});
      const name = e?.name ?? '';
      if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') {
        throw new MicError('denied', 'Microphone access was blocked. Allow the microphone for this site to ask a question.');
      }
      throw new MicError('unavailable', 'No microphone was found. Connect one and try again.');
    }
    return new VoiceCapture(ctx, stream);
  }

  get isRunning(): boolean {
    return this.running;
  }

  /** Begin VAD + streaming. Resolves once the worklet is wired. */
  async start(cb: CaptureCallbacks, limits: Partial<CaptureLimits> = {}): Promise<void> {
    if (this.closed || this.running) return;
    this.cb = cb;
    this.seg = new CaptureSegmenter(limits, (frame, seq) => this.cb?.onFrame(bytesToBase64(frame), seq));
    await this.ctx.resume().catch(() => {});
    await this.ctx.audioWorklet.addModule(WORKLET_URL);
    if (this.closed) return;
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, 'deckfm-pcm-capture', { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
    this.sink = this.ctx.createGain();
    this.sink.gain.value = 0;
    this.node.port.onmessage = (e: MessageEvent<{ pcm: ArrayBuffer; rms: number }>) => this.onChunk(e.data);
    this.source.connect(this.node);
    this.node.connect(this.sink);
    this.sink.connect(this.ctx.destination);
    this.running = true;
  }

  /** "Done" button: send what was captured and end. */
  finish(): void {
    if (this.running) this.end('manual');
  }

  /** Discard: nothing more is sent. */
  cancel(): void {
    if (!this.running) { this.close(); return; }
    this.end('cancelled');
  }

  /** Stop the mic tracks and release the audio graph. Idempotent. */
  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.running = false;
    try { this.node?.port.close(); } catch {}
    try { this.source?.disconnect(); } catch {}
    try { this.node?.disconnect(); } catch {}
    try { this.sink?.disconnect(); } catch {}
    this.stream.getTracks().forEach((tr) => tr.stop());
    void this.ctx.close().catch(() => {});
  }

  private onChunk(data: { pcm: ArrayBuffer; rms: number }): void {
    if (!this.running || !data?.pcm || !this.seg) return;
    const rms = Number.isFinite(data.rms) ? data.rms : 0;
    this.levelPeak = Math.max(this.levelPeak, rms);
    if (++this.levelN >= 5) {
      this.cb?.onLevel?.(this.levelPeak);
      this.levelPeak = 0;
      this.levelN = 0;
    }
    const reason = this.seg.push(new Uint8Array(data.pcm), rms);
    if (reason) this.end(reason);
  }

  private end(reason: CaptureEndReason): void {
    if (!this.running || !this.seg) return;
    this.seg.end(reason);
    this.running = false;
    const cb = this.cb;
    const seg = this.seg;
    const result: CaptureEnd = { reason, bytes: seg.bytesSent, frames: seg.framesSent, heardSpeech: seg.heardSpeech };
    this.close();
    cb?.onEnd(result);
  }
}
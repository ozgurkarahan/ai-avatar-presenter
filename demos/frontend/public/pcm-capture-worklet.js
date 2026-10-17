// AudioWorklet for DeckFM voice questions: downsamples the mic input to
// 16 kHz mono PCM16 and posts ~20 ms chunks with their RMS (float domain).
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.pos = 0;
    this.acc = 0;
    this.accN = 0;
    this.out = new Int16Array(320);
    this.outN = 0;
    this.sq = 0;
    this.sqN = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const ch = input[0];
    const chans = input.length;
    for (let i = 0; i < ch.length; i++) {
      let s = 0;
      for (let c = 0; c < chans; c++) s += input[c][i];
      s /= chans;
      this.sq += s * s;
      this.sqN += 1;
      // Box-filter decimation: average every input sample that falls into one output slot.
      this.acc += s;
      this.accN += 1;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const v = Math.max(-1, Math.min(1, this.acc / this.accN));
        this.acc = 0;
        this.accN = 0;
        this.out[this.outN++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        if (this.outN === this.out.length) {
          const rms = Math.sqrt(this.sq / Math.max(1, this.sqN));
          this.port.postMessage({ pcm: this.out.buffer, rms }, [this.out.buffer]);
          this.out = new Int16Array(320);
          this.outN = 0;
          this.sq = 0;
          this.sqN = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('deckfm-pcm-capture', PcmCaptureProcessor);

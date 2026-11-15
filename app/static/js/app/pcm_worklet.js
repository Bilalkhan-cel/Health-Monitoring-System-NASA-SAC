// AudioWorklet: microphone → 16 kHz mono Int16 PCM blocks posted to the main thread.
// Shared by the Mind check-in and the Dr. NOVA microphone.

class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.buffer = [];
    this.position = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    // Linear-interpolation resampler to 16 kHz.
    let peak = 0;
    while (this.position < channel.length - 1) {
      const index = Math.floor(this.position);
      const frac = this.position - index;
      const sample = channel[index] * (1 - frac) + channel[index + 1] * frac;
      const clamped = Math.max(-1, Math.min(1, sample));
      peak = Math.max(peak, Math.abs(clamped));
      this.buffer.push(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff);
      this.position += this.ratio;
    }
    this.position -= channel.length;
    if (this.buffer.length >= 1600) {          // 100 ms blocks
      const block = Int16Array.from(this.buffer);
      this.buffer = [];
      this.port.postMessage({ pcm: block, peak }, [block.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-capture', PcmCapture);

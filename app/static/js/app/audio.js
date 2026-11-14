// Microphone capture via the PCM AudioWorklet + WAV packing. Shared by Mind and Dr. NOVA.

const STATIC = document.querySelector('meta[name="static-root"]')?.content || '/static/';
export const SAMPLE_RATE = 16000;

export async function openMicrophone(onBlock) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const context = new AudioContext();
  await context.audioWorklet.addModule(`${STATIC}js/app/pcm_worklet.js`);
  const source = context.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(context, 'pcm-capture');
  const analyser = context.createAnalyser();
  analyser.fftSize = 512;
  node.port.onmessage = (event) => onBlock(event.data.pcm, event.data.peak);
  source.connect(analyser);
  source.connect(node);
  return {
    analyser,
    context,
    async close() {
      node.port.onmessage = null;
      for (const track of stream.getTracks()) track.stop();
      await context.close();
    },
  };
}

export function rms(block) {
  let sum = 0;
  for (let i = 0; i < block.length; i += 1) sum += (block[i] / 32768) ** 2;
  return Math.sqrt(sum / Math.max(1, block.length));
}

export function encodeWav(blocks) {
  const length = blocks.reduce((total, block) => total + block.length, 0);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const write = (offset, text) => { for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i)); };
  write(0, 'RIFF');
  view.setUint32(4, 36 + length * 2, true);
  write(8, 'WAVE');
  write(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, 'data');
  view.setUint32(40, length * 2, true);
  let offset = 44;
  for (const block of blocks) {
    for (let i = 0; i < block.length; i += 1) {
      view.setInt16(offset, block[i], true);
      offset += 2;
    }
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

export function int16ToBase64(blocks) {
  const length = blocks.reduce((total, block) => total + block.length, 0);
  const bytes = new Uint8Array(length * 2);
  let offset = 0;
  for (const block of blocks) {
    bytes.set(new Uint8Array(block.buffer, block.byteOffset, block.byteLength), offset);
    offset += block.byteLength;
  }
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

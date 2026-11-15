// Daily check-in: record → WAV chunks (cut at ≥ 30 s on the next ≥ 300 ms of silence, max
// 40 s) → background transcription → analysis. A text check-in is the fallback.

import { api, emitDataUpdated } from './api.js';
import { encodeWav, openMicrophone, rms } from './audio.js';
import { chartAvailable, trendChart } from './charts.js';
import { clear, h, prefersReducedMotion, statusPill, toast } from './dom.js';

const root = document.querySelector('[data-mind]');
const $ = (selector) => root.querySelector(selector);
const TARGET_S = Number(root.dataset.target) * 60;
const MAX_S = Number(root.dataset.max) * 60;
const MIN_S = Number(root.dataset.min) || 0;
const PROMPTS = JSON.parse(root.dataset.prompts);
const CHUNK_MIN_S = 30;
const CHUNK_MAX_S = 40;
const SILENCE_RMS = 0.012;
const SILENCE_BLOCKS = 3;      // 3 × 100 ms
const EMOTION_COLORS = { joy: '#2EE59D', neutral: '#8E97A6', surprise: '#3B9EFF', sadness: '#6B7CFF',
  fear: '#FFC53D', anger: '#FF4D6D', disgust: '#B76BFF' };

const state = { mic: null, checkin: null, blocks: [], chunkSamples: 0, seq: 0, quiet: 0, started: 0, paused: false,
  pausedMs: 0, pauseStart: 0, timer: 0, prompt: 0, promptTimer: 0, raf: 0, uploads: [], level: 0, elapsed: 0 };

function show(step) {
  for (const section of root.querySelectorAll('[data-step]')) section.hidden = section.dataset.step !== step;
}

function elapsedSeconds() {
  const paused = state.pausedMs + (state.paused ? Date.now() - state.pauseStart : 0);
  return Math.max(0, (Date.now() - state.started - paused) / 1000);
}

function setPrompt(index) {
  state.prompt = index % PROMPTS.length;
  $('[data-prompt-count]').textContent = `Question ${state.prompt + 1} of ${PROMPTS.length}`;
  $('[data-prompt]').textContent = PROMPTS[state.prompt];
}

function drawWave() {
  state.raf = requestAnimationFrame(drawWave);
  const canvas = $('[data-wave]');
  const ctx = canvas.getContext('2d');
  const size = canvas.clientWidth;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== size * ratio) {
    canvas.width = size * ratio;
    canvas.height = size * ratio;
  }
  const w = canvas.width;
  ctx.clearRect(0, 0, w, w);
  const analyser = state.mic?.analyser;
  const bins = 96;
  const data = new Uint8Array(analyser ? analyser.frequencyBinCount : bins);
  if (analyser && !state.paused) analyser.getByteFrequencyData(data);
  const radius = w * 0.3;
  ctx.lineWidth = Math.max(2, w / 260);
  ctx.lineCap = 'round';
  for (let i = 0; i < bins; i += 1) {
    const value = data[Math.floor((i / bins) * data.length * 0.6)] / 255;
    const angle = (i / bins) * Math.PI * 2 - Math.PI / 2;
    const length = w * 0.02 + value * w * 0.14;
    const alpha = 0.25 + value * 0.75;
    ctx.strokeStyle = `rgba(124, 196, 255, ${alpha})`;
    ctx.beginPath();
    ctx.moveTo(w / 2 + Math.cos(angle) * radius, w / 2 + Math.sin(angle) * radius);
    ctx.lineTo(w / 2 + Math.cos(angle) * (radius + length), w / 2 + Math.sin(angle) * (radius + length));
    ctx.stroke();
  }
  const progress = Math.min(1, elapsedSeconds() / TARGET_S);
  ctx.strokeStyle = 'rgba(242,244,247,0.9)';
  ctx.lineWidth = Math.max(3, w / 160);
  ctx.beginPath();
  ctx.arc(w / 2, w / 2, radius * 0.86, -Math.PI / 2, -Math.PI / 2 + progress * Math.PI * 2);
  ctx.stroke();
}

function tick() {
  const seconds = Math.floor(elapsedSeconds());
  state.elapsed = seconds;
  $('[data-timer]').textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  $('[data-level]').style.width = `${Math.min(100, state.level * 400)}%`;
  const hint = $('[data-done-hint]');
  if (!hint.hidden && seconds >= MIN_S) hint.textContent = "That's enough for a result. Tap I'm done when you're ready.";
  if (seconds >= MAX_S) finishRecording();
}

async function uploadChunk(final = false) {
  if (!state.blocks.length) return;
  const blocks = state.blocks;
  state.blocks = [];
  state.chunkSamples = 0;
  const seq = state.seq;
  state.seq += 1;
  const form = new FormData();
  form.append('checkin_id', state.checkin);
  form.append('seq', seq);
  form.append('audio', encodeWav(blocks), `chunk-${seq}.wav`);
  const upload = api('/mental/chunk', { method: 'POST', body: form }).catch((error) => {
    toast(`A piece of audio did not upload: ${error.message}`);
  });
  state.uploads.push(upload);
  if (final) await upload;
}

function onBlock(block) {
  if (state.paused) return;
  state.level = rms(block);
  state.blocks.push(block);
  state.chunkSamples += block.length;
  const seconds = state.chunkSamples / 16000;
  state.quiet = state.level < SILENCE_RMS ? state.quiet + 1 : 0;
  if ((seconds >= CHUNK_MIN_S && state.quiet >= SILENCE_BLOCKS) || seconds >= CHUNK_MAX_S) uploadChunk();
}

async function pollPreview() {
  if (!state.checkin) return;
  try {
    const status = await api(`/mental/status/${state.checkin}`);
    if (status.preview) $('[data-preview]').textContent = `“…${status.preview.slice(-220)}”`;
    if (status.safety) showSafety();
  } catch {
    /* keep recording */
  }
}

async function startRecording() {
  const error = $('[data-mic-error]');
  const button = $('[data-record]');
  if (state.mic || button.disabled) return;
  button.disabled = true;
  try {
    const reply = await api('/mental/start', { method: 'POST', body: { mode: 'voice' } });
    state.checkin = reply.checkin_id;
    state.mic = await openMicrophone(onBlock);
  } catch (err) {
    button.disabled = false;
    error.hidden = false;
    error.textContent = err.name === 'NotAllowedError'
      ? 'Microphone permission was refused. Allow it in the address bar, or type your check-in instead.'
      : `The microphone could not start (${err.message}). Type your check-in instead.`;
    return;
  }
  error.hidden = true;
  show('recording');
  state.started = Date.now();
  setPrompt(0);
  state.timer = window.setInterval(tick, 250);
  state.promptTimer = window.setInterval(() => { setPrompt(state.prompt + 1); pollPreview(); }, 30000);
  window.setInterval(pollPreview, 8000);
  if (!prefersReducedMotion()) drawWave();
}

function togglePause() {
  state.paused = !state.paused;
  if (state.paused) state.pauseStart = Date.now();
  else state.pausedMs += Date.now() - state.pauseStart;
  $('[data-pause]').textContent = state.paused ? 'Resume' : 'Pause';
  $('[data-listening]').textContent = state.paused ? 'Paused' : 'Listening · only you can hear this';
}

async function finishRecording() {
  if (!state.mic) return;
  // Too short for a result: keep recording and say why, instead of ending and losing it.
  const left = Math.ceil(MIN_S - elapsedSeconds());
  if (left > 0 && !$('[data-mood]').value) {
    const hint = $('[data-done-hint]');
    hint.hidden = false;
    hint.textContent = `Keep talking a little longer: ${left} more second${left === 1 ? '' : 's'} for a result.`;
    return;
  }
  window.clearInterval(state.timer);
  window.clearInterval(state.promptTimer);
  cancelAnimationFrame(state.raf);
  const duration = elapsedSeconds();
  await state.mic.close();
  state.mic = null;
  await uploadChunk(true);
  await Promise.all(state.uploads);
  show('processing');
  await submit({ checkin_id: state.checkin, duration_s: duration, ...rating() });
}

function rating() {
  const mood = $('[data-mood]').value;
  const sleep = $('[data-sleep]').value;
  return { self_mood: mood ? Number(mood) : null, self_sleep: sleep ? Number(sleep) : null };
}

async function submit(body, attempt = 0) {
  try {
    const response = await api('/mental/finish', { method: 'POST', body: { ...body, force: attempt >= 40 } });
    if (response.processing) {
      $('[data-processing]').textContent = `Reading your words… ${response.pending} piece${response.pending === 1 ? '' : 's'} left`;
      window.setTimeout(() => submit(body, attempt + 1), 1500);
      return;
    }
    renderResults(response.results);
  } catch (err) {
    toast(err.message);
    show('intro');
  }
}

async function submitText(event) {
  event.preventDefault();
  const text = new FormData(event.currentTarget).get('text');
  const error = $('[data-text-error]');
  const button = event.currentTarget.querySelector('[type="submit"]');
  if (button.disabled) return;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = 'Saving… reading your words';  // the language models can take a few seconds
  try {
    const reply = await api('/mental/text', { method: 'POST', body: { text, ...rating() } });
    error.hidden = true;
    renderResults(reply.results);
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function showSafety(message) {
  window.clearInterval(state.timer);
  window.clearInterval(state.promptTimer);
  cancelAnimationFrame(state.raf);
  state.mic?.close();
  state.mic = null;
  if (message) $('[data-safety-text]').textContent = message;
  show('safety');
}

function renderResults(results) {
  if (results.safety) {
    showSafety(results.message);
    return;
  }
  if (results.too_short) {
    const note = $('[data-mic-error]');  // stays on screen, unlike a toast
    note.hidden = false;
    note.textContent = results.message;
    show('intro');
    return;
  }
  show('results');
  const status = { NOMINAL: { key: 'good', icon: 'circle-check', label: 'Good' },
    STABLE: { key: 'okay', icon: 'circle-dot', label: 'Okay' },
    CAUTION: { key: 'watch', icon: 'triangle-alert', label: 'Needs attention' } }[results.internal];
  clear($('[data-result-status]')).append(statusPill({ ...status, verdict: `${results.category} mood` }));
  $('[data-result-score]').textContent = Math.round(results.score);
  $('[data-result-confidence]').textContent = `Model confidence ${Math.round(results.confidence * 100)} %`
    + (results.engine === 'word lists' ? ' (simple word lists: the language models are not installed)' : '');
  $('[data-result-summary]').textContent = results.summary;
  const themes = clear($('[data-result-themes]'));
  for (const theme of results.themes) themes.append(h('li', { class: 'tag' }, theme));
  if (!results.themes.length) themes.append(h('li', { class: 'card__meta' }, 'No worries stood out.'));
  const tips = clear($('[data-result-tips]'));
  for (const tip of results.suggestions) {
    const item = h('li', {}, tip.text);
    if (tip.key === 'breathing') {
      item.append(' ', h('button', { class: 'pill pill--ghost pill--small', type: 'button',
        onclick: () => document.getElementById('breathe-dialog').showModal() }, 'Start'));
    }
    tips.append(item);
  }
  const transcript = $('[data-transcript]');
  transcript.hidden = !results.transcript;
  $('[data-transcript-text]').textContent = results.transcript || '';
  transcript.dataset.checkin = results.checkin_id;
  if (chartAvailable()) {
    const emotions = Object.entries(results.emotions).filter(([, value]) => value > 0.01);
    new window.Chart($('[data-emotions]'), {
      type: 'doughnut',
      data: { labels: emotions.map(([name]) => name), datasets: [{ data: emotions.map(([, v]) => Math.round(v * 100)),
        backgroundColor: emotions.map(([name]) => EMOTION_COLORS[name]), borderWidth: 0 }] },
      options: { cutout: '68%', plugins: { legend: { position: 'right', labels: { color: '#A3ABB8', boxWidth: 10 } } } },
    });
    const timeline = results.timeline.map((segment, index) => ({ t: `Part ${index + 1}`,
      v: segment.label === 'positive' ? 1 : segment.label === 'negative' ? -1 : 0,
      status: segment.label === 'negative' ? 'watch' : null }));
    const tone = trendChart($('[data-timeline]'), { points: timeline }, { reference: [0] });
    if (tone) {
      const words = { 1: 'Positive', 0: 'Neutral', '-1': 'Negative' };
      Object.assign(tone.options.scales.y, { min: -1.25, max: 1.25 });
      Object.assign(tone.options.scales.y.ticks, { stepSize: 1, callback: (value) => words[value] ?? '' });
      tone.options.plugins.tooltip.callbacks.label = (item) => words[item.raw] ?? '';
      tone.update();
    }
    trendChart($('[data-trend]'), { points: results.trend }, { unit: '/100', reference: [70, 55] });
  }
  $('[data-emotions-text]').textContent = Object.entries(results.emotions)
    .map(([name, value]) => `${name} ${Math.round(value * 100)} %`).join(', ');
  if (results.xp) toast(`Check-in saved. +${results.xp} XP`);
  emitDataUpdated({ metric: 'wellbeing' });
}

function setupBreathing() {
  const dialog = document.getElementById('breathe-dialog');
  const circle = dialog.querySelector('[data-breathe-circle]');
  const label = dialog.querySelector('[data-breathe-label]');
  let timer = 0;
  dialog.addEventListener('close', () => window.clearTimeout(timer));
  const cycle = (count) => {
    if (!dialog.open || count >= 12) {
      label.textContent = 'Done. Notice how you feel.';
      return;
    }
    label.textContent = 'Breathe in… 4';
    circle.dataset.phase = 'in';
    timer = window.setTimeout(() => {
      label.textContent = 'Breathe out… 6';
      circle.dataset.phase = 'out';
      timer = window.setTimeout(() => cycle(count + 1), 6000);
    }, 4000);
  };
  dialog.querySelector('[data-breathe-start]').addEventListener('click', () => cycle(0));
}

function setup() {
  $('[data-record]')?.addEventListener('click', startRecording);
  $('[data-done]').addEventListener('click', finishRecording);
  $('[data-pause]').addEventListener('click', togglePause);
  $('[data-skip-prompt]').addEventListener('click', () => setPrompt(state.prompt + 1));
  $('[data-text-form]').addEventListener('submit', submitText);
  for (const button of root.querySelectorAll('[data-show]')) {
    button.addEventListener('click', () => show(button.dataset.show));
  }
  $('[data-delete-transcript]').addEventListener('click', async () => {
    const id = $('[data-transcript]').dataset.checkin;
    await api(`/mental/${id}/transcript`, { method: 'DELETE' });
    $('[data-transcript]').hidden = true;
    toast('Transcript deleted.');
  });
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
    $('[data-record]')?.setAttribute('disabled', '');
    $('[data-mic-error]').hidden = false;
    $('[data-mic-error]').textContent = 'This browser cannot record audio here. Type your check-in instead.';
  }
  setupBreathing();
}

setup();

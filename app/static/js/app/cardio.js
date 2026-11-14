// Heart check flow: overview → pre-check → rest countdown + handshake → live session → results.

import { api, emitDataUpdated } from './api.js';
import { bluetoothAvailable, connectStrap } from './ble.js';
import { barLineChart, trendChart } from './charts.js';
import { clear, h, icon, prefersReducedMotion, statusPill, toast } from './dom.js';
import { createHeartbeat } from './ecg_synth.js';
import { connectLive } from './live.js';

const root = document.querySelector('[data-cardio]');
const $ = (selector) => root.querySelector(selector);
const REST = Number(root.dataset.rest);
const DEMO = root.dataset.demo === '1';
const USUAL = root.dataset.usual ? Number(root.dataset.usual) : null;
const CONTEXT_LABEL = { fasting: 'fasting', post_meal: 'after a meal', random: '' };
const WEAR_TEXT = {
  no_device: 'No wearable linked. You can use a Bluetooth chest strap or type your readings.',
  device_offline: 'Wearable not connected. Use the strap or enter readings by hand.',
  no_finger: 'Wearable connected. Place a finger on the sensor when you start.',
  settling: 'Wearable connected. Hold still…',
  poor_signal: 'Wearable connected, weak signal. Keep your hand still.',
  ok: 'Wearable connected and reading.',
};

const state = { step: 'overview', stream: null, restTimer: null, restEnds: 0, glucose: 'random', wave: null,
  strap: null, lastBle: 0, paused: false, finished: false, live: null, trend: null, measuring: false };

function show(step) {
  state.step = step;
  for (const section of root.querySelectorAll('[data-step]')) section.hidden = section.dataset.step !== step;
  window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
}

// ── overview ─────────────────────────────────────────────
async function loadTrend(metric) {
  for (const button of root.querySelectorAll('[data-trend]')) {
    button.setAttribute('aria-pressed', String(button.dataset.trend === metric));
  }
  try {
    const series = await api(`/api/history?metric=${metric}&range=30d`);
    state.trend?.destroy();
    state.trend = trendChart($('[data-trend-canvas]'), series, { unit: series.unit, reference: series.reference,
      label: series.label, second: metric === 'blood_pressure' ? { label: 'Lower number' } : null });
    $('[data-trend-summary]').textContent = series.summary;
  } catch (error) {
    $('[data-trend-summary]').textContent = error.message;
  }
}

function wearLine(snapshot) {
  state.live = snapshot;
  $('[data-wear-line]').textContent = WEAR_TEXT[snapshot.state] || '';
  if (state.step === 'rest') renderHandshake(snapshot);
}

// ── rest + handshake ─────────────────────────────────────
function renderHandshake(snapshot) {
  const list = clear($('[data-handshake]'));
  const online = snapshot && snapshot.device?.online;
  const item = (ok, text) => h('li', { class: ok ? 'is-ok' : 'is-wait' }, icon(ok ? 'circle-check' : 'loader-circle'),
    text);
  if (online) {
    list.append(item(true, 'Wearable connected'));
    list.append(snapshot.finger ? item(true, 'Finger on the sensor') : item(false, 'Waiting for a finger on the sensor'));
    if (snapshot.temp?.state === 'settled') list.append(item(true, 'Temperature probe settled'));
    else if (snapshot.temp?.state === 'warming') list.append(item(false, 'Measuring temperature… keep your arm down'));
    else if (snapshot.temp?.state === 'ambient') list.append(item(false, 'Place the probe under your arm'));
  } else if (!state.strap) {
    list.append(item(false, 'Wearable not connected: use the strap or enter by hand'));
  }
  if (state.strap) list.append(item(true, `${state.strap.name} connected`));
}

function tickRest() {
  const left = Math.max(0, Math.round((state.restEnds - Date.now()) / 1000));
  $('[data-rest-time]').textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
  const ring = $('[data-ring]');
  ring.style.strokeDashoffset = String(339.3 * (left / REST));
  if (left === 0) {
    window.clearInterval(state.restTimer);
    $('[data-start-measure]').disabled = false;
    beginMeasuring(false);
  }
}

async function startSession(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  state.glucose = data.get('glucose_context');
  const error = $('[data-precheck-error]');
  try {
    await api('/cardio/start', { method: 'POST', body: { glucose_context: state.glucose,
      symptoms: data.getAll('symptoms') } });
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
    return;
  }
  error.hidden = true;
  show('rest');
  state.restEnds = Date.now() + REST * 1000;
  tickRest();
  state.restTimer = window.setInterval(tickRest, 1000);
  openStream();
  renderHandshake(state.live);
}

async function beginMeasuring(skip) {
  if (state.measuring) return;
  state.measuring = true;
  window.clearInterval(state.restTimer);
  const modes = state.strap ? { heart_rate: 'ble' } : {};
  try {
    const reply = await api('/cardio/measure', { method: 'POST', body: { skip_rest: skip, modes } });
    show('live');
    if (!reply.rest_verified) $('[data-bpm-note]').textContent = 'Stay still and breathe normally.';
    state.wave ||= createHeartbeat($('[data-wave]'), { reducedMotion: prefersReducedMotion() });
  } catch (err) {
    state.measuring = false;
    toast(err.message);
  }
}

// ── live session ─────────────────────────────────────────
function openStream() {
  state.stream?.close();
  const source = new EventSource('/cardio/stream');
  source.addEventListener('reading', (event) => renderReading(JSON.parse(event.data)));
  source.addEventListener('complete', () => finish());
  source.addEventListener('ended', () => source.close());
  source.onerror = () => { /* EventSource reconnects by itself */ };
  state.stream = source;
}

function vital(label, reading) {
  const status = reading?.status;
  return h('li', { class: 'vital' },
    h('p', { class: 'vital__label' }, label),
    h('p', { class: 'vital__value' }, reading?.value ?? '–', reading?.value ? h('span', { class: 'vital__unit' },
      ` ${reading.unit}`) : null),
    h('p', { class: `vital__verdict${status ? ` is-${status.key}` : ''}` },
      status ? status.verdict : (reading?.value ? '' : 'Waiting for a reading')));
}

function renderReading(payload) {
  if (payload.phase === 'rest') {
    renderHandshake({ device: { online: payload.wearable_state !== 'device_offline' && payload.wearable_state !== 'no_device' },
      finger: payload.finger, temp: { state: payload.temp_state } });
    return;
  }
  const hr = payload.readings.heart_rate;
  $('[data-bpm]').textContent = hr?.value ?? '–';
  const verdict = clear($('[data-bpm-verdict]'));
  if (hr?.status) verdict.append(statusPill(hr.status));
  const heart = $('[data-heart]');
  if (payload.bpm && !prefersReducedMotion()) {
    heart.style.animationDuration = `${60 / payload.bpm}s`;
    heart.classList.add('is-beating');
  } else {
    heart.classList.remove('is-beating');
  }
  state.wave?.setBpm(payload.bpm);
  state.wave?.pushPpg(payload.ppg);
  const note = $('[data-bpm-note]');
  if (payload.waiting_for_finger) note.textContent = 'Place a finger on the sensor. The countdown waits for you.';
  else if (USUAL) note.textContent = `Your usual is ${USUAL}. Stay still and breathe normally.`;
  else note.textContent = 'Stay still and breathe normally.';
  const left = payload.remaining_s ?? 0;
  $('[data-time-left]').textContent = payload.paused ? 'Paused' : `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')} left`;
  $('[data-live-status]').textContent = payload.paused ? 'Heart check paused' : 'Heart check in progress';
  const r = payload.readings;
  const context = CONTEXT_LABEL[state.glucose];
  const vitals = clear($('[data-vitals]'));
  vitals.append(vital('Blood pressure', r.blood_pressure), vital('Temperature', r.temperature_c),
    vital('Oxygen', r.spo2), vital(`Blood sugar${context ? ` · ${context}` : ''}`, r.glucose),
    vital('Breathing', r.respiration));
}

async function togglePause() {
  state.paused = !state.paused;
  try {
    await api('/cardio/pause', { method: 'POST', body: { paused: state.paused } });
    $('[data-pause]').textContent = state.paused ? 'Resume' : 'Pause';
  } catch (err) {
    toast(err.message);
  }
}

async function saveManual(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const message = $('[data-manual-message]');
  const metric = data.get('metric');
  const body = { via: 'hand', metric, value: Number(data.get('value')) };
  if (metric === 'blood_pressure') body.value2 = Number(data.get('value2'));
  try {
    const reply = await api('/cardio/reading', { method: 'POST', body });
    message.hidden = !reply.message;
    if (reply.message) {
      message.textContent = reply.message;
      const button = form.querySelector('button');
      button.disabled = true;
      let wait = reply.min_gap_s || 60;
      button.textContent = `Re-measure in ${wait} s`;
      const timer = window.setInterval(() => {
        wait -= 1;
        button.textContent = wait > 0 ? `Re-measure in ${wait} s` : 'Re-measure';
        if (wait <= 0) {
          window.clearInterval(timer);
          button.disabled = false;
        }
      }, 1000);
    } else {
      toast('Reading saved.');
    }
    form.reset();
  } catch (err) {
    message.textContent = err.message;
    message.hidden = false;
  }
}

async function finish() {
  if (state.finished) return;
  state.finished = true;
  state.stream?.close();
  try {
    const reply = await api('/cardio/end', { method: 'POST', body: {} });
    if (reply.results) renderResults(reply.results);
    else show('overview');
  } catch (err) {
    state.finished = false;
    toast(err.message);
  }
}

// ── results ──────────────────────────────────────────────
function renderResults(results) {
  show('results');
  state.wave?.stop();
  state.strap?.disconnect();
  clear($('[data-result-status]')).append(statusPill(results.overall));
  $('[data-result-title]').textContent = { good: 'Your heart looks good.', okay: 'Your heart looks okay.',
    watch: 'Your heart needs a little attention.', alert: 'Get help now.' }[results.overall.key];
  $('[data-result-text]').textContent = results.explanation;
  const symptoms = $('[data-result-symptoms]');
  symptoms.hidden = !results.symptoms;
  symptoms.textContent = results.symptoms ? `${results.symptoms} Tell your crew medical officer now.` : '';
  $('[data-result-rest]').textContent = results.rest_note || '';
  const rows = clear($('[data-result-rows]'));
  for (const row of results.rows) {
    rows.append(h('li', { class: 'row' }, h('span', { class: 'row__label' }, row.label),
      h('span', { class: 'row__right' }, h('span', { class: 'row__value' }, `${row.value} ${row.unit}`.trim()),
        row.status ? h('span', { class: `verdict is-${row.status.key}` }, row.status.verdict) : null)));
  }
  const messages = clear($('[data-result-messages]'));
  for (const text of results.messages) messages.append(h('li', {}, text));
  const actions = clear($('[data-result-actions]'));
  for (const text of results.actions) actions.append(h('li', {}, text));
  $('[data-result-remeasure]').textContent = results.remeasure;
  barLineChart($('[data-result-chart]'), results.history);
  $('[data-result-chart-text]').textContent = `Average heart rate in your last ${results.history.length} checks: `
    + results.history.map((row) => row.hr ?? 'none').join(', ');
  if (results.xp) toast(`Heart check saved. +${results.xp} XP`);
  emitDataUpdated({ metric: 'heart_rate' });
}

// ── Bluetooth strap ──────────────────────────────────────
function setupStrap() {
  const button = $('[data-ble]');
  const note = $('[data-ble-note]');
  if (!bluetoothAvailable()) {
    note.textContent = 'Bluetooth straps work in Chrome or Edge on this computer. You can still type readings during the check.';
    return;
  }
  button.hidden = false;
  button.addEventListener('click', async () => {
    try {
      state.strap = await connectStrap(async (bpm) => {
        if (Date.now() - state.lastBle < 1000 || state.step !== 'live') return;
        state.lastBle = Date.now();
        try {
          await api('/cardio/reading', { method: 'POST', body: { via: 'strap', metric: 'heart_rate', value: bpm } });
        } catch {
          /* the next beat retries */
        }
      }, () => {
        state.strap = null;
        note.textContent = 'Strap disconnected.';
        renderHandshake(state.live);
      });
      note.textContent = `${state.strap.name} connected.`;
      renderHandshake(state.live);
    } catch (err) {
      note.textContent = err.name === 'NotFoundError' ? 'No strap chosen.' : `Could not connect: ${err.message}`;
    }
  });
}

function setup() {
  for (const button of root.querySelectorAll('[data-go]')) {
    button.addEventListener('click', () => show(button.dataset.go));
  }
  for (const button of root.querySelectorAll('[data-trend]')) {
    button.addEventListener('click', () => loadTrend(button.dataset.trend));
  }
  $('[data-precheck-form]').addEventListener('submit', startSession);
  $('[data-start-measure]').addEventListener('click', () => beginMeasuring(false));
  $('[data-skip-rest]')?.addEventListener('click', () => beginMeasuring(true));
  $('[data-cancel]').addEventListener('click', async () => {
    window.clearInterval(state.restTimer);
    state.stream?.close();
    await api('/cardio/end', { method: 'POST', body: {} }).catch(() => null);
    show('overview');
  });
  $('[data-pause]').addEventListener('click', togglePause);
  $('[data-finish]').addEventListener('click', finish);
  $('[data-manual-form]').addEventListener('submit', saveManual);
  setupStrap();
  connectLive().on('snapshot', wearLine).on('device', wearLine).on('vital', (vital) => {
    state.live = { ...(state.live || {}), ...vital, device: { ...(state.live?.device || {}), online: true } };
    if (state.step === 'overview') wearLine(state.live);
  });
  loadTrend('heart_rate');
  if (!DEMO) $('[data-skip-rest]')?.remove();
}

setup();

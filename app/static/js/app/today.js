// Today page: renders /api/summary into the scores, tasks, twin panel and readings list.
// The first paint uses the JSON embedded in the page; it then refreshes every 30 s and
// whenever an `astro:data-updated` event fires (saved check, new live aggregate).

import { api, emitDataUpdated } from './api.js';
import { clear, h, icon, sparkline, statusPill, toast } from './dom.js';
import { mountTwin } from '../astro3d.js';
import { connectLive } from './live.js';

const SYSTEMS = ['heart', 'mind', 'bones'];
const RANK = { alert: 3, watch: 2, okay: 1, good: 0 };
const START_LABEL = { heart: 'Start heart check', mind: 'Start voice check-in', bones: 'Start exercise' };

const state = {
  summary: JSON.parse(document.getElementById('summary-data').textContent),
  selected: null,
  twin: null,
};

const $ = (selector, root = document) => root.querySelector(selector);

function defaultSystem(summary) {
  let chosen = 'heart';
  let best = -1;
  for (const id of SYSTEMS) {
    const rank = summary.systems[id].status ? RANK[summary.systems[id].status.key] : -1;
    if (rank > best) {
      best = rank;
      chosen = id;
    }
  }
  return chosen;
}

function setStatusClass(node, status, base) {
  node.className = `${base}${status ? ` is-${status.key}` : ''}`;
}

function renderScores(summary) {
  for (const id of SYSTEMS) {
    const card = $(`[data-score="${id}"]`);
    const system = summary.systems[id];
    setStatusClass(card, system.status, 'score');
    $('[data-score-number]', card).textContent = system.score ?? '–';
    $('[data-score-meter]', card).style.width = `${system.score ?? 0}%`;
    const slot = clear($('[data-score-status]', card));
    slot.append(system.status ? statusPill(system.status) : h('span', { class: 'card__meta' }, 'No recent readings'));
    card.setAttribute('aria-pressed', String(state.selected === id));
    card.setAttribute('aria-label', `${system.label}: ${system.score ?? 'no score yet'}`
      + `${system.score != null ? ' out of 100' : ''}, ${system.status ? system.status.label : 'no recent readings'}.`
      + ' Show details.');
  }
  const overall = $('[data-score="overall"]');
  const { readiness } = summary;
  $('[data-score-number]', overall).textContent = readiness.score ?? '–';
  $('[data-score-meter]', overall).style.width = `${readiness.score ?? 0}%`;
  clear($('[data-score-status]', overall)).append(readiness.status
    ? statusPill(readiness.status) : h('span', { class: 'score__caption' }, 'Not enough data yet'));
  overall.setAttribute('aria-label', readiness.score == null
    ? 'Overall: not enough data yet'
    : `Overall: ${readiness.score} out of 100, ${readiness.status ? readiness.status.label : ''}`);
  $('[data-readiness-sentence]').textContent = readiness.sentence;
}

function taskAction(item, isNext) {
  if (item.action === 'water') {
    return h('button', { class: 'pill pill--ghost pill--small', type: 'button', onclick: addWater },
      icon('plus'), '1 glass');
  }
  if (item.action === 'sleep' && item.state !== 'done') {
    return h('button', { class: `pill ${isNext ? 'pill--primary' : 'pill--ghost'} pill--small`, type: 'button',
      onclick: () => $('#sleep-dialog').showModal() }, 'Log sleep');
  }
  if (item.state === 'due' && item.url) {
    return h('a', { class: `pill ${isNext ? 'pill--primary' : 'pill--ghost'} pill--small`, href: item.url }, 'Start');
  }
  return null;
}

function renderTasks(tasks) {
  $('[data-tasks-count]').textContent = `${tasks.done} of ${tasks.total} done`;
  $('[data-tasks-meter]').style.width = `${(tasks.done / tasks.total) * 100}%`;
  const list = clear($('[data-task-list]'));
  let nextMarked = false;
  for (const item of tasks.items) {
    const isNext = !nextMarked && item.state === 'due';
    if (isNext) nextMarked = true;
    const classes = ['task', `is-${item.state}`, isNext ? 'is-next' : ''].join(' ').trim();
    list.append(h('li', { class: classes },
      h('span', { class: 'task__mark', 'aria-hidden': 'true' }, item.state === 'done' ? icon('check') : null),
      h('div', {},
        h('p', { class: 'task__label' }, item.label,
          h('span', { class: 'visually-hidden' }, item.state === 'done' ? ' (done)' : '')),
        item.detail ? h('p', { class: 'task__detail' }, item.detail) : null),
      taskAction(item, isNext)));
  }
  $('[data-streak]').textContent = tasks.streak
    ? `Streak: ${tasks.streak} day${tasks.streak === 1 ? '' : 's'} in a row with 3 or more tasks done.`
    : 'Finish 3 tasks today to start a streak.';
}

function metricByKey(summary) {
  return Object.fromEntries(summary.metrics.map((metric) => [metric.key, metric]));
}

function renderPanel(summary) {
  const id = state.selected;
  const system = summary.systems[id];
  const metrics = metricByKey(summary);
  const panel = $('[data-panel]');
  setStatusClass(panel, system.status, 'card panel');
  $('[data-panel-title]').textContent = system.score != null ? `${system.title} · ${system.score}` : system.title;
  clear($('[data-panel-status]')).append(statusPill(system.status) || '');
  $('[data-panel-headline]').textContent = system.headline;

  const rows = clear($('[data-panel-rows]'));
  for (const key of system.metrics) {
    const metric = metrics[key];
    if (!metric) continue;
    rows.append(h('li', { class: 'row' },
      h('span', { class: 'row__label' }, metric.short),
      h('span', { class: 'row__right' },
        h('span', { class: 'row__value' }, `${metric.value ?? '–'} ${metric.unit}`.trim()),
        metric.status ? h('span', { class: `verdict is-${metric.status.key}` }, metric.status.verdict) : null)));
  }
  if (!rows.children.length) rows.append(h('li', { class: 'row' }, h('span', { class: 'row__label' }, 'No readings yet')));

  const steps = clear($('[data-panel-steps]'));
  for (const step of system.steps) steps.append(h('li', {}, step));

  const start = $('[data-panel-start]');
  start.hidden = !system.start_url;
  if (system.start_url) {
    start.href = system.start_url;
    start.textContent = START_LABEL[id];
  }
  const { mission } = summary;
  const gravity = mission.gravity_g != null ? ` Gravity here is ${mission.gravity_g} g.` : '';
  $('[data-panel-foot]').textContent = `Messages to Earth take ${mission.comms_delay_text}.${gravity}`;
}

function infoPopover(metric) {
  const id = `info-${metric.key}`;
  let pop = document.getElementById(id);
  if (!pop) {
    pop = h('div', { class: 'info-pop', id, popover: 'auto', role: 'dialog', 'aria-label': metric.label },
      h('h3', {}, metric.label),
      h('dl', {},
        h('dt', {}, 'What it is'), h('dd', {}, metric.info.what),
        h('dt', {}, 'Why it matters in space'), h('dd', {}, metric.info.why),
        h('dt', {}, 'Normal range'), h('dd', {}, metric.info.range),
        h('dt', {}, 'What to do'), h('dd', {}, metric.info.do)));
    document.body.append(pop);
  }
  return id;
}

function renderReadings(summary) {
  const list = clear($('[data-readings]'));
  for (const metric of summary.metrics) {
    const statusKey = metric.status?.key;
    const verdict = metric.status
      ? statusPill(metric.status)
      : h('span', { class: 'card__meta' }, metric.value == null ? 'No reading yet' : 'For your information');
    list.append(h('li', { class: `reading${statusKey ? ` is-${statusKey}` : ''}` },
      h('div', {},
        h('div', { class: 'reading__name' }, metric.label,
          h('button', { class: 'info-button', type: 'button', popovertarget: infoPopover(metric),
            'aria-label': `What is ${metric.label.toLowerCase()}?` }, icon('info'))),
        h('p', {}, h('span', { class: 'reading__value' }, metric.value ?? '–'),
          metric.value != null ? h('span', { class: 'reading__unit' }, metric.unit) : null)),
      h('div', { class: 'reading__right' }, verdict, sparkline(metric.spark, statusKey)),
      h('p', { class: 'reading__meta' },
        h('span', {}, metric.updated),
        metric.usual ? h('span', {}, metric.usual) : null,
        metric.note ? h('span', { class: 'verdict is-watch' }, metric.note) : null)));
  }
}

function renderTwin(summary) {
  const systems = {};
  for (const id of SYSTEMS) {
    const system = summary.systems[id];
    systems[id] = { key: system.status?.key, score: system.score, title: system.title,
      word: system.status?.label };
  }
  state.twin?.setStatus(systems);
  for (const pill of document.querySelectorAll('[data-system-pill]')) {
    const id = pill.dataset.systemPill;
    const status = summary.systems[id].status;
    setStatusClass($('[data-pill-dot]', pill), status, 'dot');
    pill.setAttribute('aria-pressed', String(state.selected === id));
  }
}

const LIVE_TEXT = {
  no_device: 'No wearable linked. Connect your sensor to see live readings.',
  device_offline: 'Sensor not connected',
  no_finger: 'Place a finger on the sensor.',
  settling: 'Hold still… reading in a few seconds.',
  poor_signal: 'Weak signal. Keep your hand still.',
};
const TEMP_TEXT = {
  missing: 'Temperature probe not found',
  ambient: 'Place the probe under your arm',
  warming: 'Measuring temperature… keep your arm down',
};

function renderLive(snapshot) {
  const strip = $('[data-live-strip]');
  if (!strip || !snapshot) return;
  state.live = snapshot;
  strip.hidden = false;
  clear(strip);
  const dot = h('span', { class: `pulse-dot${snapshot.hr ? ' is-beating' : ''}`, 'aria-hidden': 'true' });
  if (snapshot.hr) dot.style.animationDuration = `${60 / snapshot.hr}s`;
  if (snapshot.state === 'ok' || (snapshot.hr != null || snapshot.spo2 != null)) {
    const parts = [];
    if (snapshot.hr != null) parts.push(`Heart rate ${snapshot.hr} bpm`);
    if (snapshot.spo2 != null) parts.push(`SpO₂ ${snapshot.spo2} %`);
    if (snapshot.temp?.value_c != null) {
      const fahrenheit = document.querySelector('meta[name="astro-temp-unit"]')?.content === 'F';
      parts.push(fahrenheit ? `Temp ${(snapshot.temp.value_c * 9 / 5 + 32).toFixed(1)} °F` : `Temp ${snapshot.temp.value_c} °C`);
    }
    strip.append(dot, h('span', { class: 'live__values' }, parts.join(' · ') || LIVE_TEXT[snapshot.state] || ''));
  } else {
    let text = LIVE_TEXT[snapshot.state] || '';
    if (snapshot.state === 'device_offline' && snapshot.last) {
      text += `. Last reading ${snapshot.last.hr} bpm, ${Math.round(snapshot.last.age_s / 60)} min ago`;
    }
    strip.append(h('span', { class: 'live__state' }, text));
  }
  if (snapshot.state !== 'no_device' && snapshot.state !== 'device_offline' && TEMP_TEXT[snapshot.temp?.state]) {
    strip.append(h('span', { class: 'live__temp' }, TEMP_TEXT[snapshot.temp.state]));
  }
  if (snapshot.notice) {
    strip.append(h('p', { class: 'live__notice' }, statusPill({ key: 'watch', icon: 'triangle-alert',
      label: 'Needs attention' }), ` ${snapshot.notice.text}`));
  } else if (snapshot.hr != null) {
    const restCheck = state.summary.systems.heart.start_url;
    strip.append(h('p', { class: 'live__hint' }, 'Live · rest 5 min for a resting reading',
      restCheck ? h('a', { class: 'pill pill--ghost pill--small', href: restCheck }, 'Start rest check') : null));
  }
  state.twin?.setHeartRate(snapshot.hr);
}

function render() {
  const { summary } = state;
  renderScores(summary);
  renderTasks(summary.tasks);
  renderPanel(summary);
  renderTwin(summary);
  renderReadings(summary);
  const sleepNote = $('[data-sleep-note]');
  if (sleepNote) {
    const sleep = summary.metrics.find((metric) => metric.key === 'sleep_hours');
    sleepNote.textContent = sleep?.value ? `You slept ${sleep.value}. ${sleep.status?.verdict ?? ''}.` : 'No sleep logged yet.';
  }
  window.dispatchEvent(new CustomEvent('astro:alerts', { detail: { alerts: summary.alerts, protocol: summary.protocol } }));
}

function select(id) {
  state.selected = id;
  state.twin?.select(id);
  render();
}

async function refresh() {
  try {
    state.summary = await api('/api/summary');
    render();
  } catch (error) {
    if (error.status !== 401) toast('Could not refresh. Showing the last readings.');
  }
}

async function addWater() {
  try {
    const result = await api('/api/tasks/hydration/done', { method: 'POST', body: {} });
    toast(`Logged a glass of water. ${(result.water_ml / 1000).toFixed(1)} litres today.`);
    emitDataUpdated({ metric: 'hydration_ml' });
  } catch (error) {
    toast(error.message);
  }
}

function setupSleepForm() {
  const form = $('[data-sleep-form]');
  const error = $('[data-sleep-error]', form);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const hours = Number(data.get('hours')) + Number(data.get('minutes')) / 60;
    if (!(hours > 0 && hours <= 16)) {
      error.textContent = 'Enter between 0 and 16 hours.';
      error.hidden = false;
      return;
    }
    try {
      await api('/api/tasks/sleep_log/done', { method: 'POST', body: { hours, quality: data.get('quality') } });
      error.hidden = true;
      form.closest('dialog').close();
      toast('Sleep saved.');
      emitDataUpdated({ metric: 'sleep_hours' });
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  });
}

async function init() {
  state.selected = defaultSystem(state.summary);
  for (const id of SYSTEMS) $(`[data-score="${id}"]`).addEventListener('click', () => select(id));
  for (const pill of document.querySelectorAll('[data-system-pill]')) {
    pill.addEventListener('click', () => select(pill.dataset.systemPill));
  }
  setupSleepForm();
  render();
  state.twin = await mountTwin($('[data-twin]'), { onSelect: select });
  const hint = $('.twin-stage .card__meta');
  if (hint && state.twin?.hint) hint.textContent = state.twin.hint;
  state.twin.select(state.selected);
  renderTwin(state.summary);
  window.addEventListener('astro:data-updated', refresh);
  const live = connectLive();
  live.on('snapshot', renderLive).on('device', renderLive).on('summary', refresh)
    .on('vital', (vital) => renderLive({ ...(state.live || {}), ...vital,
      device: { ...(state.live?.device || {}), online: true } }));
  window.setInterval(() => { if (!document.hidden) refresh(); }, 30000);
}

init();

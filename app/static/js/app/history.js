// History page: trend chart (metric + range), and the day-detail dialog from the calendar or timeline.

import { api } from './api.js';
import { chartAvailable, trendChart } from './charts.js';
import { clear, h, statusPill } from './dom.js';

const $ = (selector) => document.querySelector(selector);
const state = { metric: 'readiness', range: '30d', chart: null, token: 0 };

async function loadTrend() {
  const token = ++state.token;
  const summary = $('[data-trend-summary]');
  summary.textContent = 'Loading…';
  try {
    const series = await api(`/api/history?metric=${encodeURIComponent(state.metric)}&range=${state.range}`);
    if (token !== state.token) return;
    state.chart?.destroy();
    state.chart = null;
    if (chartAvailable() && series.points.length) {
      state.chart = trendChart($('[data-trend-canvas]'), series, {
        unit: series.unit, reference: series.reference, label: series.label,
        second: state.metric === 'blood_pressure' ? { label: 'Bottom number' } : null,
      });
    }
    summary.textContent = series.summary;
  } catch (err) {
    if (token === state.token) summary.textContent = err.message;
  }
}

function setupTrend() {
  const select = $('[data-trend-metric]');
  select?.addEventListener('change', () => { state.metric = select.value; loadTrend(); });
  for (const button of document.querySelectorAll('[data-range]')) {
    button.addEventListener('click', () => {
      state.range = button.dataset.range;
      for (const other of document.querySelectorAll('[data-range]')) {
        other.setAttribute('aria-pressed', String(other === button));
      }
      loadTrend();
    });
  }
  loadTrend();
}

function renderDay(detail) {
  const body = clear($('[data-day-body]'));
  $('[data-day-title]').textContent = detail.label;
  $('[data-day-readiness]').textContent = detail.readiness === null
    ? 'Not enough data for a readiness score that day.' : `Readiness ${detail.readiness} out of 100.`;
  if (!detail.entries.length && !detail.readings.length) {
    body.append(h('p', { class: 'card__meta' }, 'Nothing was recorded on this day.'));
    return;
  }
  if (detail.entries.length) {
    body.append(h('h3', { class: 'dialog__sub' }, 'Checks'));
    body.append(h('ul', { class: 'day-list' }, detail.entries.map((entry) => h('li', { class: 'entry' },
      h('span', { class: 'entry__time' }, entry.time || ''),
      h('div', { class: 'entry__body' }, h('p', { class: 'entry__title' }, entry.title),
        h('p', { class: 'entry__text' }, entry.text)),
      statusPill(entry.status)))));
  }
  if (detail.readings.length) {
    const shown = detail.readings_total > detail.readings.length
      ? ` (latest ${detail.readings.length} of ${detail.readings_total})` : '';
    body.append(h('h3', { class: 'dialog__sub' }, `Readings${shown}`));
    const table = h('table', { class: 'readings' },
      h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Time'), h('th', { scope: 'col' }, 'Measure'),
        h('th', { scope: 'col' }, 'Value'), h('th', { scope: 'col' }, 'Status'))),
      h('tbody', {}, detail.readings.slice().reverse().map((row) => h('tr', {},
        h('td', {}, row.time), h('td', {}, row.metric), h('td', {}, row.value),
        h('td', {}, statusPill(row.status) || '—')))));
    body.append(h('div', { class: 'readings__wrap' }, table));
  }
}

function setupDays() {
  const dialog = document.getElementById('day-dialog');
  document.addEventListener('click', async (event) => {
    const trigger = event.target.closest('[data-day]');
    if (!trigger || !dialog) return;
    clear($('[data-day-body]')).append(h('p', { class: 'card__meta' }, 'Loading…'));
    $('[data-day-readiness]').textContent = '';
    dialog.showModal();
    try {
      renderDay(await api(`/history/day/${trigger.dataset.day}`));
    } catch (err) {
      clear($('[data-day-body]')).append(h('p', { class: 'form-error' }, err.message));
    }
  });
}

setupTrend();
setupDays();

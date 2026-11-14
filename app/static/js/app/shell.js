// App shell behaviour: rail labels, dialogs, account menu, environment picker, alert bar.

import { api } from './api.js';
import { clear, h } from './dom.js';

const RAIL_KEY = 'astrovital.rail-open';

function readPref(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writePref(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private mode: the preference is simply not remembered */
  }
}

function setupRail() {
  const rail = document.getElementById('rail');
  const toggle = document.querySelector('[data-rail-toggle]');
  if (!rail || !toggle) return;
  const apply = (open) => {
    rail.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    const text = toggle.querySelector('[data-rail-toggle-text]');
    if (text) text.textContent = open ? 'Hide menu labels' : 'Show menu labels';
  };
  apply(readPref(RAIL_KEY) === '1');
  toggle.addEventListener('click', () => {
    const open = !rail.classList.contains('is-open');
    apply(open);
    writePref(RAIL_KEY, open ? '1' : '0');
  });
}

function setupDialogs() {
  document.addEventListener('click', (event) => {
    const opener = event.target.closest('[data-open-dialog]');
    if (opener) {
      document.getElementById(opener.dataset.openDialog)?.showModal();
      return;
    }
    const closer = event.target.closest('[data-close-dialog]');
    if (closer) closer.closest('dialog')?.close();
  });
  for (const dialog of document.querySelectorAll('dialog')) {
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
  }
}

function setupMenu() {
  const menu = document.querySelector('.menu');
  if (!menu) return;
  document.addEventListener('click', (event) => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });
  menu.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      menu.open = false;
      menu.querySelector('summary')?.focus();
    }
  });
}

function setupEnvironment() {
  const form = document.querySelector('[data-env-form]');
  if (!form) return;
  const error = form.querySelector('[data-env-error]');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const environment = new FormData(form).get('environment');
    try {
      await api('/settings/environment', { method: 'POST', body: { environment } });
      window.location.reload();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  });
}

export function showAlerts(alerts, protocol) {
  const bar = document.querySelector('[data-alertbar]');
  if (!bar) return;
  const list = alerts || [];
  bar.hidden = list.length === 0;
  if (!list.length) return;
  bar.querySelector('[data-alertbar-text]').textContent = list[0].text
    + (list.length > 1 ? ` (${list.length - 1} more alert${list.length > 2 ? 's' : ''})` : '');
  const steps = document.querySelector('[data-protocol-steps]');
  if (steps && protocol) {
    clear(steps);
    for (const step of protocol) steps.append(h('li', {}, step));
  }
}

async function pollAlerts() {
  if (document.getElementById('summary-data')) return; // Today renders its own alerts
  try {
    const data = await api('/api/alerts');
    showAlerts(data.alerts, data.protocol);
  } catch {
    /* offline: keep whatever is shown */
  }
}

setupRail();
setupDialogs();
setupMenu();
setupEnvironment();
window.addEventListener('astro:alerts', (event) => showAlerts(event.detail.alerts, event.detail.protocol));
pollAlerts();
window.setInterval(() => { if (!document.hidden) pollAlerts(); }, 30000);

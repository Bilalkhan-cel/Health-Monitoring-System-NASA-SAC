// Notifications page: mark one or all as read, and show times in the viewer's own clock.

import { api } from './api.js';
import { toast } from './dom.js';

function setBell(unread) {
  window.dispatchEvent(new CustomEvent('astro:unread', { detail: { unread } }));
}

function markRow(row) {
  row.classList.remove('is-unread');
  row.querySelector('[data-mark-read]')?.remove();
  row.querySelector('.note__title .visually-hidden')?.remove();
}

for (const time of document.querySelectorAll('[data-local-time]')) {
  const when = new Date(time.getAttribute('datetime'));
  if (!Number.isNaN(when.getTime())) {
    time.textContent = when.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
}

document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-mark-read]');
  const open = event.target.closest('[data-open-note]');
  const row = (button || open)?.closest('[data-note]');
  if (!row) return;
  if (button) {
    button.disabled = true;
    try {
      const data = await api(`/notifications/${row.dataset.note}/read`, { method: 'POST' });
      markRow(row);
      setBell(data.unread);
    } catch (err) {
      button.disabled = false;
      toast(err.message);
    }
  } else if (row.classList.contains('is-unread')) {
    // Opening a notification counts as reading it; the link still follows.
    api(`/notifications/${row.dataset.note}/read`, { method: 'POST' }).catch(() => {});
  }
});

const all = document.querySelector('[data-read-all]');
all?.addEventListener('click', async () => {
  all.disabled = true;
  try {
    await api('/notifications/read-all', { method: 'POST' });
    for (const row of document.querySelectorAll('[data-note].is-unread')) markRow(row);
    setBell(0);
    toast('All caught up.');
  } catch (err) {
    all.disabled = false;
    toast(err.message);
  }
});

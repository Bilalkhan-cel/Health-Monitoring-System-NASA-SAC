// Live wearable feed: EventSource on /api/stream with reconnect backoff (1 → 10 s), a
// fallback to polling /api/live every 3 s after 3 failures, and a pause when the tab has
// been hidden for 60 s. Usage: const live = connectLive(); live.on('vital', cb).

import { api } from './api.js';

const HIDDEN_CLOSE_MS = 60000;

export function connectLive() {
  const handlers = { snapshot: [], vital: [], device: [], summary: [], alert: [], status: [] };
  let source = null;
  let failures = 0;
  let retryTimer = null;
  let pollTimer = null;
  let hiddenTimer = null;
  let stopped = false;

  const emit = (name, data) => { for (const fn of handlers[name] || []) fn(data); };

  const poll = async () => {
    try {
      emit('snapshot', await api('/api/live'));
      emit('status', 'polling');
    } catch {
      emit('status', 'offline');
    }
  };

  const startPolling = () => {
    if (pollTimer) return;
    poll();
    pollTimer = window.setInterval(poll, 3000);
  };

  const stopPolling = () => {
    window.clearInterval(pollTimer);
    pollTimer = null;
  };

  const open = () => {
    if (stopped || source) return;
    source = new EventSource('/api/stream');
    for (const name of ['snapshot', 'vital', 'device', 'summary', 'alert']) {
      source.addEventListener(name, (event) => {
        try {
          emit(name, JSON.parse(event.data));
        } catch {
          /* ignore a malformed message */
        }
      });
    }
    source.onopen = () => {
      failures = 0;
      stopPolling();
      emit('status', 'live');
    };
    source.onerror = () => {
      source?.close();
      source = null;
      failures += 1;
      emit('status', 'reconnecting');
      if (failures >= 3) startPolling();
      const delay = Math.min(10000, 1000 * 2 ** Math.min(failures - 1, 4));
      window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(open, delay);
    };
  };

  const close = () => {
    source?.close();
    source = null;
    stopPolling();
  };

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      hiddenTimer = window.setTimeout(close, HIDDEN_CLOSE_MS);
    } else {
      window.clearTimeout(hiddenTimer);
      open();
    }
  });

  open();
  return {
    on(name, fn) {
      (handlers[name] ||= []).push(fn);
      return this;
    },
    stop() {
      stopped = true;
      close();
    },
  };
}

// Settings: save-on-change preferences, reminders, wearable, privacy delete and the Demo panel.

import { api } from './api.js';
import { toast } from './dom.js';

const $ = (selector, root = document) => root.querySelector(selector);

function saved(name, text, isError = false) {
  const node = $(`[data-saved="${name}"]`);
  if (!node) return;
  node.textContent = text;
  node.classList.toggle('is-error', isError);
  if (!isError) window.setTimeout(() => { if (node.textContent === text) node.textContent = ''; }, 2600);
}

async function post(path, body, name) {
  try {
    const data = await api(path, { method: 'POST', body });
    if (name) saved(name, 'Saved.');
    return data;
  } catch (err) {
    if (name) saved(name, err.message, true);
    else toast(err.message);
    throw err;
  }
}

function savePrefsOnChange(form, name) {
  form?.addEventListener('change', (event) => {
    const input = event.target;
    if (!input.name) return;
    const value = input.type === 'checkbox' ? input.checked : input.value;
    post('/settings', { [input.name]: value }, name).then(() => {
      if (input.name === 'reduced_motion') document.documentElement.classList.toggle('reduce-motion', value);
    }).catch(() => {});
  });
}

savePrefsOnChange($('[data-prefs-form]'), 'prefs');
savePrefsOnChange($('[data-privacy-form]'), 'privacy');

$('[data-reminders-form]')?.addEventListener('submit', (event) => {
  event.preventDefault();
  const reminders = Object.fromEntries(new FormData(event.currentTarget).entries());
  post('/settings', { reminders }, 'reminders').catch(() => {});
});

$('[data-device-form]')?.addEventListener('change', async (event) => {
  const input = event.target;
  const body = input.name === 'wearing' ? { wearing: input.checked } : { [input.name]: input.value };
  try {
    await post('/settings/device', body, 'device');
    if (input.name === 'wearing') window.location.reload();
  } catch {
    if (input.type === 'checkbox') input.checked = !input.checked;
  }
});

$('[data-calibrate-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = $('[data-calibrate-message]', form);
  message.hidden = true;
  try {
    await api('/settings/device', { method: 'POST', body: { reference_c: form.reference_c.value } });
    toast('Temperature calibrated.');
    window.location.reload();
  } catch (err) {
    message.textContent = err.message;
    message.hidden = false;
  }
});

$('[data-delete-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = $('[data-delete-message]', form);
  message.hidden = true;
  try {
    const data = await api('/settings/privacy/delete-mental', { method: 'POST', body: { confirm: form.confirm.value } });
    form.closest('dialog').close();
    const { checkins, chat_messages: chats } = data.deleted;
    toast(`Deleted ${checkins} check-in${checkins === 1 ? '' : 's'} and ${chats} message${chats === 1 ? '' : 's'}.`, 6000);
    form.reset();
  } catch (err) {
    message.textContent = err.message;
    message.hidden = false;
  }
});

// Demo panel
$('[data-sensor-mode]')?.addEventListener('change', (event) => {
  post('/settings/sensor-mode', { mode: event.target.value }, 'mode')
    .then(() => window.setTimeout(() => window.location.reload(), 600)).catch(() => {});
});

for (const button of document.querySelectorAll('[data-scenario]')) {
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const data = await post(`/settings/demo/${button.dataset.scenario}`, {});
      toast(`Scenario running: ${data.title}. Open Today to see it.`, 6000);
    } catch {
      /* the toast already explained */
    } finally {
      button.disabled = false;
    }
  });
}

$('[data-force-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    await post('/settings/demo/force', body, 'force');
  } catch {
    /* message shown inline */
  }
});

$('[data-day-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await post('/settings/demo/day', { day: event.currentTarget.day.value }, 'day');
    window.location.reload();
  } catch {
    /* message shown inline */
  }
});

$('[data-day-reset]')?.addEventListener('click', async () => {
  try {
    await post('/settings/demo/day', { day: 'reset' }, 'day');
    window.location.reload();
  } catch {
    /* message shown inline */
  }
});

// Jump to a section from a link like /settings#reminders, keeping focus on its heading.
if (window.location.hash) {
  const target = document.querySelector(window.location.hash);
  target?.querySelector('h2')?.setAttribute('tabindex', '-1');
  target?.querySelector('h2')?.focus({ preventScroll: true });
}

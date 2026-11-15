// Dr. NOVA page: text chat (OpenHome → fallback LLM → offline rules) plus the voice button.

import { api } from './api.js';
import { h, toast } from './dom.js';
import { startVoice } from './doctor_voice.js';

const root = document.querySelector('[data-doctor]');
const $ = (selector) => root.querySelector(selector);
const list = $('[data-messages]');
const ENGINE_TEXT = { OPENHOME: 'OPENHOME', 'FALLBACK LLM': 'FALLBACK LLM', 'OFFLINE RULES': 'OFFLINE RULES' };
const state = { busy: false, voice: null, speaking: false, player: null };

function setOrb(mode, label) {
  $('[data-orb]').dataset.state = mode;
  $('[data-state-label]').textContent = label;
  $('[data-bars]').classList.toggle('is-on', mode === 'speaking' || mode === 'listening');
  $('[data-stop]').hidden = mode !== 'speaking';
}

function render(role, text) {
  const item = h('li', { class: `msg msg--${role}` });
  if (role === 'assistant') {
    // The agent answers in Markdown: drop bold markers and put numbered steps on their own lines.
    text = text.replace(/\*\*\s*/g, '').replace(/([.:!?])\s+(?=\d\.\s+[A-Z])/g, '$1\n');
  }
  if (role === 'assistant' && /\n\d+\. /.test(text)) {
    const [intro, ...rest] = text.split(/\n\n|\n(?=\d+\. )/);
    item.append(h('p', {}, intro));
    const steps = rest.filter((line) => /^\d+\. /.test(line.trim()));
    if (steps.length) item.append(h('ol', {}, steps.map((line) => h('li', {}, line.replace(/^\d+\.\s*/, '')))));
  } else {
    item.textContent = text;
  }
  list.append(item);
  item.scrollIntoView({ block: 'end', behavior: 'smooth' });
  return item;
}

function speakAloud(text) {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.replace(/\n\d+\. /g, '. '));
  utterance.rate = 1.0;
  utterance.onstart = () => setOrb('speaking', 'Speaking');
  utterance.onend = () => setOrb('idle', 'Ready');
  window.speechSynthesis.speak(utterance);
}

// OpenHome's own voice for a typed question (MP3); the browser voice if it cannot play.
function playReply(base64, text) {
  window.speechSynthesis?.cancel();
  state.player?.pause();
  const player = new Audio(`data:audio/mpeg;base64,${base64}`);
  state.player = player;
  player.onplay = () => setOrb('speaking', 'Speaking');
  player.onended = () => setOrb('idle', 'Ready');
  player.onerror = () => speakAloud(text);
  player.play().catch(() => speakAloud(text));
}

async function ask(message) {
  if (state.busy || !message.trim()) return;
  state.busy = true;
  render('user', message);
  setOrb('thinking', 'Thinking');
  try {
    const reply = await api('/doctor/chat', { method: 'POST', body: { message } });
    render('assistant', reply.reply);
    const engine = $('[data-engine]');
    engine.hidden = false;
    engine.textContent = ENGINE_TEXT[reply.engine] || reply.engine;
    engine.dataset.engine = reply.engine;
    setOrb('idle', 'Ready');
    if (state.voice === null) {
      if (reply.audio) playReply(reply.audio, reply.reply);
      else if (root.dataset.speak === '1') speakAloud(reply.reply);
    }
  } catch (error) {
    render('assistant', `I couldn't answer just now: ${error.message}`);
    setOrb('idle', 'Ready');
  } finally {
    state.busy = false;
  }
}

function setup() {
  $('[data-composer]').addEventListener('submit', (event) => {
    event.preventDefault();
    const input = event.currentTarget.elements.message;
    const message = input.value;
    input.value = '';
    ask(message);
  });
  for (const button of root.querySelectorAll('[data-suggest]')) button.addEventListener('click', () => ask(button.textContent));
  $('[data-new]').addEventListener('click', async () => {
    await api('/doctor/new', { method: 'POST', body: {} });
    list.replaceChildren(h('li', { class: 'msg msg--assistant' },
      `New consultation started. What would you like to check, ${root.dataset.callsign}?`));
  });
  $('[data-stop]').addEventListener('click', () => {
    window.speechSynthesis?.cancel();
    state.player?.pause();
    state.voice?.interrupt();
    setOrb('idle', 'Ready');
  });
  $('[data-mic]').addEventListener('click', async () => {
    const button = $('[data-mic]');
    if (state.voice) {
      state.voice.stop();
      state.voice = null;
      button.setAttribute('aria-pressed', 'false');
      setOrb('idle', 'Ready');
      return;
    }
    try {
      state.voice = await startVoice({
        onState: (mode, label) => setOrb(mode, label),
        onMessage: (role, text, final) => {
          const caption = $('[data-caption]');
          if (!final) {
            caption.textContent = text;
            return;
          }
          caption.textContent = '';
          render(role, text);
        },
        onClosed: () => {
          state.voice = null;
          button.setAttribute('aria-pressed', 'false');
          setOrb('idle', 'Ready');
        },
      });
      button.setAttribute('aria-pressed', 'true');
    } catch (error) {
      toast(error.name === 'NotAllowedError'
        ? 'Microphone permission was refused. Allow it in the address bar, or type your question.'
        : `Voice could not start: ${error.message}`);
    }
  });
  if (root.dataset.ask) ask(root.dataset.ask);
  list.lastElementChild?.scrollIntoView({ block: 'end' });
}

setup();

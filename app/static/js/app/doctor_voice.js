// Dr. NOVA voice: mic → 16 kHz PCM16 → /ws/doctor/voice (Flask adds the OpenHome key),
// captions and MP3 audio back. Half-duplex: the mic is muted while Dr. NOVA speaks, and
// `bot-speak-end` is sent once playback drains. In practice mode there is no audio, so the
// browser reads the replies aloud.

import { api } from './api.js';
import { int16ToBase64, openMicrophone } from './audio.js';

export async function startVoice({ onState, onMessage, onClosed }) {
  await api('/doctor/session', { method: 'POST', body: {} });
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/doctor/voice`);
  let mode = 'mock';
  let speaking = false;
  let pending = [];
  let mic = null;
  let player = null;
  const queue = [];
  let playing = false;
  let stopped = false;
  let pingTimer = 0;

  const send = (type, data) => {
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type, data }));
  };

  const playNext = async () => {
    if (playing) return;
    const next = queue.shift();
    if (!next) {
      if (speaking) {
        speaking = false;
        send('text', 'bot-speak-end');
        onState('listening', 'Listening');
      }
      return;
    }
    playing = true;
    try {
      player ||= new AudioContext();
      const bytes = Uint8Array.from(atob(next), (char) => char.charCodeAt(0));
      const buffer = await player.decodeAudioData(bytes.buffer);
      const source = player.createBufferSource();
      source.buffer = buffer;
      source.connect(player.destination);
      source.onended = () => {
        playing = false;
        playNext();
      };
      source.start();
    } catch {
      playing = false;
      playNext();
    }
  };

  const speakLocally = (text) => {
    if (!('speechSynthesis' in window)) return;
    speaking = true;
    onState('speaking', 'Speaking');
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => {
      speaking = false;
      onState('listening', 'Listening');
    };
    window.speechSynthesis.speak(utterance);
  };

  socket.addEventListener('message', (event) => {
    let frame;
    try {
      frame = JSON.parse(event.data);
    } catch {
      return;
    }
    const { type, data } = frame;
    if (type === 'state') {
      mode = data.mode;
      onState(data.state === 'live' ? 'listening' : 'thinking', data.state === 'live' ? 'Listening'
        : data.state === 'offline' ? 'Offline' : 'Connecting');
    } else if (type === 'message' && data) {
      onMessage(data.role || 'assistant', data.content || '', Boolean(data.final));
      if (data.final && data.role === 'assistant' && mode !== 'live') speakLocally(data.content);
      if (!data.final && data.role === 'assistant') onState('thinking', 'Thinking');
    } else if (type === 'text' && data === 'audio-init') {
      speaking = true;
      send('text', 'bot-speaking');
      onState('speaking', 'Speaking');
    } else if (type === 'text' && data === 'interrupt') {
      queue.length = 0;
    } else if (type === 'audio' && typeof data === 'string') {
      send('ack', 'audio-received');
      queue.push(data);
      playNext();
    } else if (type === 'error-event') {
      onMessage('assistant', `Voice error: ${data?.message || 'unknown'}`, true);
    }
  });

  socket.addEventListener('close', () => {
    window.clearInterval(pingTimer);
    mic?.close();
    if (!stopped) onClosed?.();
  });

  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', () => reject(new Error('the voice connection was refused')), { once: true });
  });

  mic = await openMicrophone((block) => {
    if (speaking) return;               // half-duplex: no echo loop
    pending.push(block);
    if (pending.length >= 2) {          // 200 ms frames, like the OpenHome client
      send('audio', int16ToBase64(pending));
      pending = [];
    }
  });
  pingTimer = window.setInterval(() => send('ping', null), 20000);

  return {
    interrupt() {
      queue.length = 0;
      window.speechSynthesis?.cancel();
      send('text', 'interrupt-event');
      if (speaking) {
        speaking = false;
        send('text', 'bot-speak-end');
      }
    },
    stop() {
      stopped = true;
      window.clearInterval(pingTimer);
      window.speechSynthesis?.cancel();
      mic?.close();
      socket.close();
      api('/doctor/session/end', { method: 'POST', body: {} }).catch(() => null);
    },
  };
}

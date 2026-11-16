// Minimal Chrome DevTools Protocol driver: headless Chrome, a virtual clock injected before any
// page script, and frame-by-frame capture where every frame is a pure function of time.
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';

// Runs in the page before anything else: rAF, performance.now and Date.now follow __step(),
// and so do setTimeout/setInterval once the clock is frozen (warm-up uses real timers).
export const VIRTUAL_CLOCK = `(() => {
  if (window.__vt) return;
  const realNow = performance.now.bind(performance);
  const realDateNow = Date.now;
  const realST = window.setTimeout.bind(window), realCT = window.clearTimeout.bind(window);
  const realSI = window.setInterval.bind(window), realCI = window.clearInterval.bind(window);
  const t0 = realDateNow();
  let now = 0, frozen = false, id = 1;
  const rafs = new Map();
  const timers = new Map();
  performance.now = () => frozen ? now : (now = realNow());
  Date.now = () => t0 + (frozen ? now : realNow());
  window.requestAnimationFrame = (cb) => { const i = id++; rafs.set(i, cb); return i; };
  window.cancelAnimationFrame = (i) => rafs.delete(i);
  window.setTimeout = (cb, ms = 0, ...a) => {
    if (!frozen) return realST(cb, ms, ...a);
    const i = 1e6 + id++; timers.set(i, { at: now + (ms || 0), cb, a }); return i;
  };
  window.clearTimeout = (i) => { timers.delete(i); realCT(i); };
  window.setInterval = (cb, ms = 0, ...a) => {
    if (!frozen) return realSI(cb, ms, ...a);
    const i = 1e6 + id++; timers.set(i, { at: now + ms, cb, a, every: Math.max(ms, 1) }); return i;
  };
  window.clearInterval = (i) => { timers.delete(i); realCI(i); };
  const runRaf = () => {
    const cbs = [...rafs.values()]; rafs.clear();
    for (const cb of cbs) { try { cb(now); } catch (e) { console.error(e); } }
  };
  // While warming up, pump rAF on a real timer so pages load and settle.
  const pump = () => { if (!frozen) { now = realNow(); runRaf(); realST(pump, 16); } };
  realST(pump, 16);
  window.__vt = {
    freeze() { frozen = true; },
    get now() { return now; },
    step(ms) {
      const target = now + ms;
      for (;;) {
        let next = null;
        for (const [i, t] of timers) if (t.at <= target && (!next || t.at < next[1].at)) next = [i, t];
        if (!next) break;
        const [i, t] = next;
        now = Math.max(now, t.at);
        if (t.every) t.at += t.every; else timers.delete(i);
        try { t.cb(...t.a); } catch (e) { console.error(e); }
      }
      now = target;
      runRaf();
    },
  };
})();`;

export async function launch({ width = 1920, height = 1080, port = 9333, userDir }) {
  const proc = spawn(CHROME, [
    '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${userDir}`,
    `--window-size=${width},${height}`, '--hide-scrollbars', '--mute-audio', '--no-first-run',
    '--no-default-browser-check', '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows',
    '--enable-gpu-rasterization', '--ignore-gpu-blocklist', '--use-angle=d3d11', 'about:blank',
  ], { stdio: 'ignore' });
  let targets;
  for (let i = 0; i < 60; i++) {
    try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; } catch { await sleep(250); }
  }
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r, { once: true }));
  let seq = 0;
  const pending = new Map();
  const listeners = [];
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id); pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method) {
      if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
        console.log('[page error]', msg.params.args.map((a) => a.value ?? a.description).join(' '));
      }
      if (msg.method === 'Runtime.exceptionThrown') console.log('[page exception]', msg.params.exceptionDetails.exception?.description);
      for (const l of listeners) l(msg);
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq; pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: VIRTUAL_CLOCK });

  const api = {
    send,
    async eval(expression) {
      const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    },
    async goto(url, settleMs = 1500) {
      const loaded = new Promise((r) => {
        const l = (m) => { if (m.method === 'Page.loadEventFired') { listeners.splice(listeners.indexOf(l), 1); r(); } };
        listeners.push(l);
      });
      await send('Page.navigate', { url });
      await loaded;
      await sleep(settleMs);
    },
    async waitFor(expression, timeout = 30000) {
      const start = Date.now();
      while (Date.now() - start < timeout) {
        if (await api.eval(expression).catch(() => false)) return true;
        await sleep(150);
      }
      throw new Error(`timeout waiting for ${expression}`);
    },
    async shot(path, format = 'jpeg') {
      const r = await send('Page.captureScreenshot', { format, quality: format === 'jpeg' ? 95 : undefined, optimizeForSpeed: false });
      writeFileSync(path, Buffer.from(r.data, 'base64'));
    },
    // Freeze the clock, then for each frame: call window.__frame(t) (if defined), step, capture.
    async record(dir, { frames, fps = 30, start = 0, before } = {}) {
      mkdirSync(dir, { recursive: true });
      await api.eval('window.__vt.freeze(), true');
      for (let f = 0; f < frames; f++) {
        const t = start + f / fps;
        if (before) await before(t, f);
        await api.eval(`(async () => { if (window.__frame) await window.__frame(${t}); window.__vt.step(${1000 / fps}); window.__syncAnims ||= ((seen) => () => { const n = window.__vt.now; for (const a of document.getAnimations()) { if (!seen.has(a)) seen.set(a, n); a.pause(); a.currentTime = n - seen.get(a); } })(new WeakMap()); window.__syncAnims(); await document.fonts.ready; await Promise.all([...document.images].filter(i => !i.complete).map(i => new Promise(r => { i.onload = i.onerror = r; }))); return true; })()`);
        await api.shot(`${dir}/${String(f).padStart(4, '0')}.jpg`);
        if (f % 30 === 0) process.stdout.write(`  ${dir.split('/').pop()} ${f}/${frames}\n`);
      }
    },
    async close() { try { await send('Browser.close'); } catch { /* gone */ } proc.kill(); },
  };
  return api;
}

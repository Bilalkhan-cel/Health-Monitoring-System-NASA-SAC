// Captures every scene from the running app, frame by frame on the virtual clock.
// Usage: node capture.mjs [scene ...] [--stills]   (stills: only a few frames per scene, for checks)
import { readFileSync } from 'node:fs';
import { launch } from './cdp.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:5001';
const FPS = 30;
const OVERLAY = readFileSync(new URL('./overlay.js', import.meta.url), 'utf8');
const args = process.argv.slice(2);
const stills = args.includes('--stills');
const only = args.filter((a) => !a.startsWith('--'));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function login(b, id) {
  await b.send('Network.enable');
  await b.send('Network.clearBrowserCookies');
  await b.goto(`${BASE}/login`, 600);
  await b.eval(`(() => { const i = document.querySelector('input[name=astro_id]'); i.value = '${id}'; i.form.submit(); return true; })()`);
  await wait(2500);
}

// Defines window.__frame(t) in the page from a function written here.
const frameFn = (fn) => `window.__frame = ${fn.toString()}; true`;

async function landingSetup(b) {
  await b.goto(`${BASE}/?q=high`, 500);
  await b.waitFor('document.documentElement.dataset.sceneReady === "1" && !!window.__astroHero');
  await wait(2500);
  await b.eval(`(() => {
    const s = document.createElement('style');
    s.textContent = '.hero{min-height:100vh!important} .hero__caption,.hero__copy .lede,.hero__actions{display:none!important} .hero__copy{transform:translateY(-36px)}';
    document.head.append(s);
    window.ScrollTrigger?.getAll().forEach((x) => x.kill());
    window.gsap?.globalTimeline.getChildren().forEach((c) => { c.progress(1); c.kill(); });
    window.scrollTo(0, 0);
    window.dispatchEvent(new Event('resize'));
    return true; })()`);
  await b.eval(OVERLAY);
  await wait(800);
}

const SCENES = {
  // 1 + 2: hook over the live Earth, then the real hero copy (7.0 s)
  async hero(b) {
    await landingSetup(b);
    await b.eval(`(() => {
      const { root } = window.__ov;
      const hook = document.createElement('div');
      hook.className = 'bo-block headline headline--hero';
      hook.style.cssText = 'left:0;right:0;top:300px;text-align:center;font-size:112px;';
      hook.innerHTML = '<span class="bo-line">Built for when Earth is</span><span class="bo-line bo-second">22 minutes away.</span>';
      root.append(hook);
      window.__hook = [...hook.children];
      window.__hero = ['.hero__copy .tag', '.hero__copy .headline'].map((s) => document.querySelector(s));
      const h = document.querySelector('.hero__copy .headline');
      h.innerHTML = '<span class="bo-line">Beyond Earth.</span><span class="bo-line headline__second">Always in health.</span>';
      window.__heroLines = [...h.children];
      return true; })()`);
    await b.eval(frameFn((t) => {
      const { line, ease, ramp } = window.__ov;
      // Camera descends toward the Earth for the whole shot.
      window.__astroHero.setProgress(0.36 * (1 - ease.inOut(ramp(t, 0, 6.6))));
      line(window.__hook[0], t, 0.25, 3.1, { dist: 40 });
      line(window.__hook[1], t, 0.5, 3.15, { dist: 40 });
      const [tag] = window.__hero;
      line(tag, t, 3.55, Infinity, { dist: 18, dur: 0.8 });
      line(window.__heroLines[0], t, 3.7, Infinity, { dist: 46, dur: 0.9 });
      line(window.__heroLines[1], t, 3.9, Infinity, { dist: 46, dur: 0.9 });
      const nav = document.querySelector('.topnav');
      nav.style.opacity = String(ease.out(ramp(t, 4.2, 5.2)));
    }));
    return 7.0;
  },

  // 6: outro over the Earth, camera pulling away (3.5 s)
  async outro(b) {
    await landingSetup(b);
    await b.eval(`(() => {
      document.querySelector('.hero__copy').style.display = 'none';
      document.querySelector('.topnav').style.display = 'none';
      const { root } = window.__ov;
      const box = document.createElement('div');
      box.className = 'bo-block';
      box.style.cssText = 'left:0;right:0;top:250px;text-align:center;display:flex;flex-direction:column;align-items:center;';
      box.innerHTML = '<div class="headline headline--big" style="font-size:96px;line-height:1.0"><span class="bo-line">Astronaut, are you</span><span class="bo-line bo-second">mission-ready?</span></div>'
        + '<div class="bo-line" style="margin-top:56px"><span class="bo-wordmark"><img src="/static/img/favicon.svg" alt="">AstroVital</span></div>'
        + '<div class="bo-line bo-mono" style="margin-top:22px">Runs on one computer · offline-first · prototype, not a medical device</div>';
      root.append(box);
      window.__lines = [...box.querySelectorAll('.bo-line')];
      return true; })()`);
    await b.eval(frameFn((t) => {
      const { line, ease, ramp } = window.__ov;
      window.__astroHero.setProgress(0.04 + 0.3 * ease.inOut(ramp(t, 0, 3.5)));
      const [a, c, d, e] = window.__lines;
      line(a, t, 0.1, Infinity, { dist: 40 });
      line(c, t, 0.3, Infinity, { dist: 40 });
      line(d, t, 0.85, Infinity, { dist: 20 });
      line(e, t, 1.05, Infinity, { dist: 14 });
    }));
    return 3.5;
  },

  // 3: Today (4.5 s)
  async today(b) {
    await login(b, 'AST-1001');
    await b.goto(`${BASE}/dashboard?q=high`, 1500);
    await b.waitFor('document.querySelector("[data-twin]")?.dataset.twin === "3d"');
    await wait(4000);
    await b.eval(OVERLAY);
    await b.eval(`(() => {
      document.querySelector('[data-system-pill="mind"]').click();
      window.__scores = [...document.querySelectorAll('.score')].map((card) => {
        const num = card.querySelector('[data-score-number]');
        const meter = card.querySelector('[data-score-meter]');
        return { num, meter, value: Number(num.textContent) || 0, width: meter.style.width || getComputedStyle(meter).width };
      });
      for (const s of window.__scores) { s.meter.style.transition = 'none'; s.pct = parseFloat(s.meter.style.width) || (parseFloat(getComputedStyle(s.meter).width) / s.meter.parentElement.clientWidth * 100); }
      const { root } = window.__ov;
      root.insertAdjacentHTML('beforeend', '<div class="bo-scrim" style="left:0;right:auto;width:1360px;height:440px;background:linear-gradient(to top, rgba(0,0,0,.97) 0%, rgba(0,0,0,.93) 55%, rgba(0,0,0,0) 100%);-webkit-mask-image:linear-gradient(to right, #000 66%, transparent 100%)"></div>');
      const cap = document.createElement('div');
      cap.className = 'bo-block headline';
      cap.style.cssText = 'left:120px;bottom:96px;font-size:88px;line-height:1.0;';
      cap.innerHTML = '<span class="bo-line">Three quick checks.</span><span class="bo-line bo-second">A few minutes a day.</span>';
      root.append(cap);
      window.__cap = [...cap.children];
      window.__scrim = root.querySelector('.bo-scrim');
      return true; })()`);
    await b.eval(frameFn((t) => {
      const { line, ease, ramp, camera, ripple, rect } = window.__ov;
      const k = ease.sine(ramp(t, 0, 4.5));
      const s = 1.13 - 0.05 * k;
      camera(s, 975, 385 + 20 * k, 960, 430);
      window.__scores.forEach((sc, i) => {
        const p = ease.outExpo(ramp(t, 0.15 + i * 0.12, 1.25 + i * 0.12));
        sc.num.textContent = String(Math.round(sc.value * p));
        sc.meter.style.width = `${sc.pct * p}%`;
      });
      window.__scrim.style.opacity = String(ease.out(ramp(t, 0.6, 1.3)));
      line(window.__cap[0], t, 0.9, Infinity, { dist: 36 });
      line(window.__cap[1], t, 1.1, Infinity, { dist: 36 });
      const pill = document.querySelector('[data-system-pill="heart"]');
      const r = rect(pill);
      ripple(r.x, r.y, t, 2.6);
      if (t >= 2.6 && !window.__tapped) { window.__tapped = true; pill.click(); }
    }));
    return 4.5;
  },

  // 4: Dr. NOVA (6.0 s)
  async doctor(b) {
    await login(b, 'AST-1001');
    await b.goto(`${BASE}/doctor`, 2500);
    await b.eval(OVERLAY);
    await b.eval(`(() => {
      const list = document.querySelector('[data-messages]');
      const greet = 'Hi Falcon. I\\u2019ve looked at your latest numbers. Ask me anything about how you\\u2019re doing, or tap the microphone and talk.';
      list.innerHTML = '';
      const g = document.createElement('li'); g.className = 'msg msg--assistant'; g.textContent = greet; list.append(g);
      window.__q = 'Why is my heart rate up today?';
      window.__a = 'It\\u2019s 104 this morning, up from your usual 72. Drink some water now, and let\\u2019s check again at 2 pm.';
      window.__input = document.querySelector('#ask-input');
      window.__user = document.createElement('li'); window.__user.className = 'msg msg--user'; window.__user.textContent = window.__q;
      window.__bot = document.createElement('li'); window.__bot.className = 'msg msg--assistant';
      window.__words = window.__a.split(' ');
      document.querySelector('[data-voice-note]').style.visibility = 'hidden';
      return true; })()`);
    await b.eval(frameFn((t) => {
      const { ease, ramp, camera, ripple, rect } = window.__ov;
      const list = document.querySelector('[data-messages]');
      // Start on the composer, glide up to the conversation once the question is sent.
      const pan = ease.inOut(ramp(t, 1.5, 2.6));
      const s = 1.42 + 0.06 * ease.sine(ramp(t, 0, 6.5));
      camera(s, 998, 770 - 420 * pan, 960, 540);
      const q = window.__q;
      const typed = Math.round(q.length * ramp(t, 0.25, 1.35));
      window.__input.value = t < 1.55 ? q.slice(0, typed) : '';
      const send = document.querySelector('.composer__send');
      const r = rect(send);
      ripple(r.x, r.y, t, 1.55);
      const orb = document.querySelector('[data-orb]');
      const label = document.querySelector('[data-state-label]');
      const bars = document.querySelector('[data-bars]');
      if (t >= 1.55 && !window.__user.isConnected) list.append(window.__user);
      const u = ease.outExpo(ramp(t, 1.55, 2.1));
      window.__user.style.opacity = String(u);
      window.__user.style.transform = `translateY(${(1 - u) * 18}px)`;
      let state = 'idle'; let word = 'Ready';
      if (t >= 1.6 && t < 2.35) { state = 'thinking'; word = 'Thinking'; }
      if (t >= 2.35 && t < 6.0) { state = 'speaking'; word = 'Speaking'; }
      orb.dataset.state = state; label.textContent = word; bars.classList.toggle('is-on', state === 'speaking');
      if (t >= 2.35 && !window.__bot.isConnected) list.append(window.__bot);
      const n = Math.ceil(window.__words.length * ramp(t, 2.35, 3.0));
      if (window.__bot.isConnected) {
        window.__bot.innerHTML = window.__words.map((w, i) => `<span style="opacity:${i < n ? 1 : 0}">${w}</span>`).join(' ');
      }
    }));
    return 6.5;
  },

  // 5: Mission Control (3.0 s)
  async mc(b) {
    await login(b, 'FS-9001');
    await b.goto(`${BASE}/mission-control`, 2500);
    await b.eval(OVERLAY);
    await b.eval(`(() => {
      const t = document.querySelector('.page-title');
      t.innerHTML = '<span class="bo-line">Mission Control.</span><span class="bo-line headline__second">The whole crew at a glance.</span>';
      window.__title = [...t.children];
      window.__cards = [...document.querySelectorAll('.crew')];
      window.__note = document.querySelector('.mc__note');
      return true; })()`);
    await b.eval(frameFn((t) => {
      const { line, ease, ramp, camera } = window.__ov;
      const s = 1.5 + 0.06 * ease.sine(ramp(t, 0, 3));
      camera(s, 625, 250, 960, 540);
      line(window.__title[0], t, 0.0, Infinity, { dist: 30, dur: 0.6 });
      line(window.__title[1], t, 0.15, Infinity, { dist: 30, dur: 0.6 });
      line(window.__note, t, 0.4, Infinity, { dist: 12, blur: 4 });
      window.__cards.forEach((c, i) => line(c, t, 0.5 + i * 0.16, Infinity, { dist: 44, dur: 0.8, blur: 6 }));
    }));
    return 3.0;
  },
};

const order = only.length ? only : Object.keys(SCENES);
for (const name of order) {
  const b = await launch({ userDir: `${process.cwd()}/chrome`, port: 9333 });
  try {
    const seconds = await SCENES[name](b);
    const frames = Math.round(seconds * FPS);
    console.log(`${name}: ${frames} frames`);
    if (process.env.PROBE) { await b.eval('window.__vt.freeze(), true'); console.log(await b.eval(process.env.PROBE)); continue; }
    if (stills) {
      // Sample a handful of times through the scene, stepping the clock in between.
      await b.eval('window.__vt.freeze(), true');
      const picks = [0.3, 0.5, 0.75, 0.9].map((p) => Math.floor(frames * p));
      picks.unshift(8);
      let f = 0;
      for (const target of picks) {
        for (; f < target; f++) {
          await b.eval(`(async () => { window.__frame?.(${f / FPS}); window.__vt.step(${1000 / FPS}); window.__syncAnims?.(); return true; })()`);
        }
        await b.eval(`(async () => { window.__frame?.(${f / FPS}); window.__vt.step(${1000 / FPS}); return true; })()`);
        await b.shot(`${process.env.STILLS || "stills"}/${name}_${String(target).padStart(3, '0')}.jpg`);
      }
    } else {
      await b.record(`frames/${name}`, { frames, fps: FPS });
    }
  } finally {
    await b.close();
    await wait(800);
  }
}

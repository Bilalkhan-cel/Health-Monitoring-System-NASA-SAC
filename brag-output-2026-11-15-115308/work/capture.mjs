// All-modules reel: each scene lifts real components out of the running app onto a designed stage.
// Usage: node capture.mjs [scene ...] [--stills]
import { readFileSync, mkdirSync } from 'node:fs';
import { launch } from './cdp.mjs';

const BASE = process.env.BASE || 'http://127.0.0.1:5001';
const FPS = 30;
const KIT = readFileSync(new URL('./overlay.js', import.meta.url), 'utf8') + '\n'
  + readFileSync(new URL('./stage.js', import.meta.url), 'utf8');
const args = process.argv.slice(2);
const stills = args.includes('--stills');
const only = args.filter((a) => !a.startsWith('--'));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const frameFn = (fn) => `window.__frame = ${fn.toString()}; true`;

async function login(b, id) {
  await b.send('Network.enable');
  await b.send('Network.clearBrowserCookies');
  await b.goto(`${BASE}/login`, 600);
  await b.eval(`(() => { const i = document.querySelector('input[name=astro_id]'); i.value = '${id}'; i.form.submit(); return true; })()`);
  await wait(2500);
}

async function page(b, path, { as = 'AST-1001', settle = 3000 } = {}) {
  if (as) await login(b, as);
  await b.goto(`${BASE}${path}`, settle);
  await b.eval(KIT);
}

async function landing(b) {
  await b.goto(`${BASE}/?q=high`, 500);
  await b.waitFor('document.documentElement.dataset.sceneReady === "1" && !!window.__astroHero');
  await wait(2500);
  await b.eval(`(() => {
    const s = document.createElement('style');
    s.textContent = '.hero{min-height:100vh!important} .hero__copy,.hero__caption,.topnav{display:none!important} body{overflow:hidden}';
    document.head.append(s);
    window.ScrollTrigger?.getAll().forEach((x) => x.kill());
    window.gsap?.globalTimeline.getChildren().forEach((c) => { c.progress(1); c.kill(); });
    window.scrollTo(0, 0);
    window.dispatchEvent(new Event('resize'));
    return true; })()`);
  await b.eval(KIT);
  await wait(600);
}

const SCENES = {
  // 1–2: hook + reveal over the live Earth (5.5 s)
  async open(b) {
    await landing(b);
    await b.eval(`(() => {
      const { root } = window.__ov;
      const hook = document.createElement('div');
      hook.className = 'bo-block headline headline--hero';
      hook.style.cssText = 'left:0;right:0;top:330px;text-align:center;font-size:124px;line-height:1.0';
      hook.innerHTML = '<span class="bo-line">Earth is</span><span class="bo-line bo-second">22 minutes away.</span>';
      root.append(hook);
      const rev = document.createElement('div');
      rev.className = 'bo-block';
      rev.style.cssText = 'left:0;right:0;top:330px;display:flex;flex-direction:column;align-items:center;gap:30px;text-align:center';
      rev.innerHTML = '<div class="bo-line" style="display:flex;align-items:center;gap:30px;font-size:132px;font-weight:600;letter-spacing:-.05em;line-height:1"><img src="/static/img/favicon.svg" style="width:128px;height:128px" alt="">AstroVital</div>'
        + '<div class="bo-line tag" style="font-size:24px;padding:12px 24px;gap:12px"><span class="tag__dot"></span>Crew health system for long missions</div>';
      root.append(rev);
      const dim = document.createElement('div');
      dim.style.cssText = 'position:absolute;inset:0;background:#000;opacity:0';
      root.prepend(dim);
      window.__o = { hook: [...hook.children], rev: [...rev.children], dim };
      // The module rail, on a transparent stage over the Earth.
      const st = window.__st.build({ text: false, index: -1 });
      st.style.background = 'transparent';
      st.querySelector('.st-glow').remove();
      st.querySelector('.st-grain').remove();
      window.__railItems = window.__st.parts.rail.items;
      return true; })()`);
    await b.eval(frameFn((t) => {
      const { line, ease, ramp } = window.__ov;
      window.__astroHero.setProgress(0.3 * (1 - ease.inOut(ramp(t, 0, 5.0))));
      const { hook, rev, dim } = window.__o;
      line(hook[0], t, 0.15, 2.75, { dist: 44 });
      line(hook[1], t, 0.35, 2.8, { dist: 44 });
      line(rev[0], t, 3.05, 5.22, { dist: 50, dur: 0.8, outDur: 0.28 });
      line(rev[1], t, 3.3, 5.22, { dist: 20, dur: 0.7, outDur: 0.28 });
      dim.style.opacity = String(0.35 * ease.out(ramp(t, 2.9, 3.4)) + 0.65 * ease.in(ramp(t, 5.0, 5.5)));
      window.__railItems.forEach((it, i) => line(it, t, 3.75 + i * 0.07, Infinity, { dist: 18, dur: 0.5, blur: 6 }));
      window.__st.railAt(0, -1);
    }));
    return 5.5;
  },

  // 3: Heart check + live wearable (2.5 s)
  async heart(b) {
    await page(b, '/cardio');
    await b.eval(`(async () => {
      const S = window.__st;
      S.build({ index: 0, kicker: 'Heart', title: ['Heart check.', 'Seven quiet minutes.'],
        cap: 'Live from the ESP32 wearable<br>MAX30102 pulse + oxygen · DS18B20 temperature', glow: '#FF4D6D' });
      const live = document.querySelector('[data-step="live"]');
      const box = document.createElement('div');
      box.style.cssText = 'display:grid;gap:18px';
      const head = live.querySelector('.live__head');
      head.querySelector('[data-time-left]').textContent = '0:58 left';
      box.append(S.adopt(head));
      const bpm = live.querySelector('.bpm');
      bpm.querySelector('[data-bpm]').textContent = '104';
      box.append(S.adopt(bpm));
      const verdict = live.querySelector('[data-bpm-verdict]');
      verdict.innerHTML = '<span class="verdict is-watch" style="font-size:18px">A bit high · your usual is 76</span>';
      box.append(S.adopt(verdict));
      const wave = live.querySelector('.wave');
      wave.style.height = '200px';
      box.append(S.adopt(wave));
      S.card(null, { width: 760 }).append(box);
      const rows = document.querySelector('.overview__latest');
      [...rows.children].forEach((li) => { const l = li.querySelector('.row__label').textContent.trim();
        if (!['Oxygen', 'Temperature', 'Blood pressure'].includes(l)) li.remove(); });
      S.second(rows, { right: -20, bottom: -40, width: 400 });
      const { createHeartbeat } = await import('/static/js/app/ecg_synth.js');
      const hb = createHeartbeat(wave.querySelector('canvas'), { color: '#FF4D6D' });
      hb.setBpm?.(104);
      await new Promise((r) => setTimeout(r, 4000));
      window.__heart = bpm.querySelector('[data-heart]');
      window.__heart.classList.remove('is-beating');
      window.__bpmNum = bpm.querySelector('[data-bpm]');
      return true; })()`);
    await b.eval(frameFn((t) => {
      window.__st.tick(t, 2.5);
      window.__st.railAt(t, 0);
      const beat = (t * 104 / 60) % 1;
      const s = 1 + 0.16 * Math.exp(-beat * 9);
      window.__heart.style.transform = `scale(${s.toFixed(3)})`;
      window.__bpmNum.textContent = String([104, 105, 104, 103, 104][Math.floor(t * 104 / 60) % 5]);
    }));
    return 2.5;
  },

  // 4: Bones & muscle — camera stage with the app's skeleton style (2.5 s)
  async bones(b) {
    await page(b, '/musculoskeletal');
    await b.eval(`(() => {
      const S = window.__st;
      S.build({ index: 1, kicker: 'Bones & muscle', title: ['Bones & muscle.', 'Load them every day.'],
        cap: 'Camera rep counting and form cues<br>MediaPipe on this computer · video never stored', glow: '#2EE59D' });
      const cam = document.querySelector('.camera');
      cam.style.width = '860px';
      cam.querySelector('video').remove();
      cam.querySelector('[data-set-title]').textContent = 'Squats';
      cam.querySelector('[data-fps]').textContent = '30 fps';
      cam.querySelector('[data-confidence-label]').textContent = 'Pose found';
      cam.querySelector('[data-confidence]').style.width = '92%';
      S.card(cam, { cls: '', width: 860 });
      S.parts.card.style.borderRadius = '32px';
      S.parts.card.style.boxShadow = '0 40px 120px rgba(0,0,0,.7), 0 0 90px -30px #2EE59D';
      const hud = document.querySelector('.hud');
      hud.querySelector('[data-form]').textContent = 'Good';
      hud.querySelector('[data-tempo]').textContent = '2 s down · 1 s up';
      S.second(hud, { right: -30, bottom: -70, width: 380 });
      window.__cv = cam.querySelector('[data-overlay]');
      window.__cv.width = 1280; window.__cv.height = 720;
      window.__reps = cam.querySelector('[data-reps]');
      window.__cue = cam.querySelector('[data-cue]');
      window.__flash = cam.querySelector('[data-flash]');
      window.__timer = hud.querySelector('[data-timer]');
      return true; })()`);
    await b.eval(frameFn((t) => {
      window.__st.tick(t, 2.5);
      window.__st.railAt(t, 1);
      // Synthetic squat (front view), drawn exactly like exercise.js drawSkeleton.
      const P = 1.0; // one rep per two beats
      const ph = ((t + 0.25) % P) / P;
      const d = (1 - Math.cos(ph * Math.PI * 2)) / 2; // 0 standing -> 1 bottom
      const cx = 0.5; const drop = 0.16 * d;
      const sh = 0.3 + drop; const hip = 0.55 + drop; const knee = 0.72 + drop * 0.35; const ank = 0.9;
      const armUp = d; // arms reach forward as he goes down
      const kp = {
        0: [cx, sh - 0.11, 1],
        5: [cx - 0.075, sh, 1], 6: [cx + 0.075, sh, 1],
        7: [cx - 0.1 + 0.03 * armUp, sh + 0.12 - 0.1 * armUp, 1], 8: [cx + 0.1 - 0.03 * armUp, sh + 0.12 - 0.1 * armUp, 1],
        9: [cx - 0.09 + 0.06 * armUp, sh + 0.23 - 0.22 * armUp, 1], 10: [cx + 0.09 - 0.06 * armUp, sh + 0.23 - 0.22 * armUp, 1],
        11: [cx - 0.05, hip, 1], 12: [cx + 0.05, hip, 1],
        13: [cx - 0.07 - 0.05 * d, knee, 1], 14: [cx + 0.07 + 0.05 * d, knee, 1],
        15: [cx - 0.08, ank, 1], 16: [cx + 0.08, ank, 1],
      };
      const edges = [[5, 6], [5, 7], [7, 9], [6, 8], [8, 10], [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16]];
      const cv = window.__cv; const ctx = cv.getContext('2d');
      ctx.clearRect(0, 0, cv.width, cv.height);
      ctx.strokeStyle = 'rgba(255,255,255,.06)'; ctx.lineWidth = 2; ctx.shadowBlur = 0;
      ctx.beginPath(); ctx.moveTo(0, 0.91 * 720); ctx.lineTo(1280, 0.91 * 720); ctx.stroke();
      const x = (p) => p[0] * cv.width; const y = (p) => p[1] * cv.height;
      ctx.lineWidth = Math.max(3, cv.width / 220) * 1.3;
      ctx.strokeStyle = 'rgba(46,229,157,0.9)'; ctx.shadowColor = 'rgba(46,229,157,0.8)'; ctx.shadowBlur = 12;
      for (const [a, c] of edges) { ctx.beginPath(); ctx.moveTo(x(kp[a]), y(kp[a])); ctx.lineTo(x(kp[c]), y(kp[c])); ctx.stroke(); }
      ctx.beginPath(); ctx.arc(x(kp[0]), y(kp[0]), 30, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x(kp[0]), y(kp[0]) + 30); ctx.lineTo(cv.width * cx, y(kp[5])); ctx.stroke();
      ctx.fillStyle = '#F2F4F7';
      for (const [k, p] of Object.entries(kp)) { if (k === '0') continue; ctx.beginPath(); ctx.arc(x(p), y(p), Math.max(4, cv.width / 160) * 1.2, 0, Math.PI * 2); ctx.fill(); }
      const reps = 11 + Math.floor((t + 0.25) / P);
      window.__reps.textContent = String(reps);
      const since = ((t + 0.25) % P);
      window.__flash.style.opacity = String(Math.max(0, 1 - since / 0.4) * (t > 0.3 ? 1 : 0));
      window.__cue.textContent = t < 1.25 ? 'Go a little deeper.' : 'Good depth. Keep going.';
      window.__timer.textContent = `0:${String(34 + Math.floor(t)).padStart(2, '0')}`;
    }));
    return 2.5;
  },

  // 5: Mind — the listening stage (2.5 s)
  async mind(b) {
    await page(b, '/mental');
    await b.eval(`(() => {
      const S = window.__st;
      S.build({ index: 2, kicker: 'Mind', title: ['How are you,', 'really?'],
        cap: 'A short voice check-in · local Whisper<br>sentiment + emotion · it never diagnoses', glow: '#9C8CFF' });
      const listen = document.querySelector('[data-step="recording"]');
      const prompts = JSON.parse(document.querySelector('[data-prompts]')?.dataset.prompts || '[]');
      listen.querySelector('[data-prompt]').textContent = prompts[0] || '';
      listen.querySelector('[data-prompt-count]').textContent = 'Question 1 of ' + (prompts.length || 1);
      listen.querySelectorAll('.listen__actions, .listen__hint, [data-done-hint], .listen__foot').forEach((n) => n.remove());
      listen.style.cssText = 'display:grid;justify-items:center;text-align:center;gap:14px';
      S.card(listen, { width: 720, pad: '30px 40px 34px' });
      const ul = document.querySelector('.card ul') ;
      const facts = [...document.querySelectorAll('li')].filter((li) => /analysed on this computer|Audio is deleted/.test(li.textContent));
      const box = document.createElement('div');
      box.innerHTML = '<h3 class="card__title" style="margin-bottom:10px">What happens to what you say</h3>';
      const list = document.createElement('ul'); list.style.cssText = 'margin:0;padding-left:1.1rem;display:grid;gap:6px;color:var(--text-2);font-size:16px';
      facts.forEach((li) => list.append(li));
      box.append(list);
      S.second(box, { right: -40, bottom: -60, width: 420 });
      window.__cv = listen.querySelector('canvas[data-wave]');
      window.__cv.width = 840; window.__cv.height = 840;
      window.__timer = listen.querySelector('[data-timer]');
      window.__level = listen.querySelector('[data-level]');
      return true; })()`);
    await b.eval(frameFn((t) => {
      window.__st.tick(t, 2.5);
      window.__st.railAt(t, 2);
      const cv = window.__cv; const ctx = cv.getContext('2d');
      ctx.clearRect(0, 0, cv.width, cv.height);
      // Speech-like envelope on the 8th-note grid.
      const syll = (t * 4) % 1;
      const env = 0.35 + 0.65 * Math.max(0, Math.sin(Math.PI * syll)) * (0.6 + 0.4 * Math.sin(t * 3.1));
      const cx = 420; const cy = 420; const R = 300;
      for (let ring = 0; ring < 3; ring += 1) {
        ctx.beginPath();
        for (let i = 0; i <= 240; i += 1) {
          const a = (i / 240) * Math.PI * 2;
          const n = Math.sin(a * 6 + t * 5 + ring) * 0.5 + Math.sin(a * 11 - t * 7) * 0.3 + Math.sin(a * 3 + t * 2) * 0.2;
          const r = R + ring * 14 + n * 26 * env * (1 - ring * 0.25);
          const px = cx + Math.cos(a) * r; const py = cy + Math.sin(a) * r;
          if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
        }
        ctx.strokeStyle = ring === 0 ? 'rgba(156,140,255,.95)' : `rgba(124,243,255,${0.35 - ring * 0.1})`;
        ctx.lineWidth = ring === 0 ? 4 : 2;
        ctx.shadowColor = 'rgba(156,140,255,.7)'; ctx.shadowBlur = ring === 0 ? 18 : 0;
        ctx.stroke();
      }
      window.__timer.textContent = `0:${String(41 + Math.floor(t)).padStart(2, '0')}`;
      window.__level.style.width = `${Math.round(20 + 70 * env)}%`;
    }));
    return 2.5;
  },

  // 6: Body twin — the 3D hologram (2.5 s)
  async twin(b) {
    await landing(b);
    await b.eval(`(() => {
      const S = window.__st;
      S.build({ index: 3, kicker: 'Body twin', title: ['Tap your body.', 'See how it\\u2019s doing.'],
        cap: 'A 3D hologram that glows by status<br>heart · mind · bones and muscle', glow: '#7CF3FF' });
      const twin = document.querySelector('[data-demo-twin]');
      twin.style.cssText = 'position:relative;width:760px;height:700px';
      S.card(twin, { cls: '', width: 760 });
      const pills = document.querySelector('.twin-showcase .system-pills');
      const cardEl = document.querySelector('[data-demo-card]');
      const box = document.createElement('div');
      box.style.cssText = 'display:grid;gap:14px';
      box.append(S.adopt(pills));
      cardEl.style.margin = '0';
      box.append(S.adopt(cardEl));
      S.second(box, { cls: '', right: -50, bottom: -30, width: 430 });
      document.querySelector('[data-demo-pill="bones"]').click();
      window.__pill = document.querySelector('[data-demo-pill="heart"]');
      window.dispatchEvent(new Event('resize'));
      return true; })()`);
    await wait(1200);
    await b.eval(frameFn((t) => {
      window.__st.tick(t, 2.5, { tilt: 0 });
      window.__st.railAt(t, 3);
      const r = window.__ov.rect(window.__pill);
      window.__ov.ripple(r.x, r.y, t, 1.0);
      if (t >= 1.0 && !window.__tapped) { window.__tapped = true; window.__pill.click(); }
    }));
    return 2.5;
  },

  // 7: Dr. NOVA (4.0 s)
  async nova(b) {
    await page(b, '/doctor');
    await b.eval(`(() => {
      const S = window.__st;
      S.build({ index: 4, kicker: 'Dr. NOVA', title: ['A doctor who knows you.', 'Just ask.'],
        cap: 'Text or voice · powered by OpenHome<br>answers from your own numbers', glow: '#3B9EFF' });
      S.root.querySelector('.st-title').style.fontSize = '64px';
      const convo = document.querySelector('.convo');
      const list = convo.querySelector('[data-messages]');
      list.innerHTML = '';
      const g = document.createElement('li'); g.className = 'msg msg--assistant';
      g.textContent = 'Hi Falcon. I\\u2019ve looked at your latest numbers. Ask me anything.'; list.append(g);
      convo.querySelectorAll('.suggestions, [data-voice-note], .convo__tools').forEach((n) => n.remove());
      convo.style.cssText = 'display:flex;flex-direction:column;gap:22px;height:auto';
      list.style.cssText = 'min-height:300px;display:flex;flex-direction:column;gap:18px;justify-content:flex-start;overflow:visible;flex:none';
      S.card(convo, { width: 820, pad: '30px 36px' });
      const sees = document.querySelector('.sees');
      sees.querySelector('.sees__foot')?.remove();
      [...sees.querySelectorAll('.row')].slice(3).forEach((r) => r.remove());
      S.second(sees, { cls: '', right: -60, top: -40, width: 340 });
      window.__q = 'Why is my heart rate up today?';
      window.__a = 'It\\u2019s 104 this morning, up from your usual 72. Drink some water now, and let\\u2019s check again at 2 pm.';
      window.__input = convo.querySelector('#ask-input');
      window.__user = document.createElement('li'); window.__user.className = 'msg msg--user'; window.__user.textContent = window.__q;
      window.__bot = document.createElement('li'); window.__bot.className = 'msg msg--assistant';
      window.__words = window.__a.split(' ');
      window.__list = list;
      return true; })()`);
    await b.eval(frameFn((t) => {
      window.__st.tick(t, 4.0, { secIn: 1.9 });
      window.__st.railAt(t, 4);
      const { ease, ramp, ripple, rect } = window.__ov;
      const q = window.__q;
      window.__input.value = t < 1.3 ? q.slice(0, Math.round(q.length * ramp(t, 0.35, 1.15))) : '';
      const r = rect(document.querySelector('.composer__send'));
      ripple(r.x, r.y, t, 1.3);
      if (t >= 1.3 && !window.__user.isConnected) window.__list.append(window.__user);
      const u = ease.outExpo(ramp(t, 1.3, 1.8));
      window.__user.style.opacity = String(u);
      window.__user.style.transform = `translateY(${(1 - u) * 18}px)`;
      let state = 'idle'; let word = 'Ready';
      if (t >= 1.35 && t < 1.75) { state = 'thinking'; word = 'Thinking'; }
      if (t >= 1.75) { state = 'speaking'; word = 'Speaking'; }
      document.querySelector('[data-orb]').dataset.state = state;
      document.querySelector('[data-state-label]').textContent = word;
      document.querySelector('[data-bars]').classList.toggle('is-on', state === 'speaking');
      if (t >= 1.75 && !window.__bot.isConnected) window.__list.append(window.__bot);
      const n = Math.ceil(window.__words.length * ramp(t, 1.75, 2.15));
      if (window.__bot.isConnected) window.__bot.innerHTML = window.__words.map((w, i) => `<span style="opacity:${i < n ? 1 : 0}">${w}</span>`).join(' ');
    }));
    return 4.0;
  },

  // 8: History — heat map, trend, Downlink Report (2.5 s)
  async history(b) {
    await page(b, '/history', { settle: 4500 });
    await b.eval(`(() => {
      const S = window.__st;
      S.build({ index: 5, kicker: 'History', title: ['Your history.', 'Every check, every day.'],
        cap: 'Heat map · trends · CSV<br>a one-page Downlink Report for the ground', glow: '#3B9EFF' });
      const heat = document.querySelector('.heat');
      const heatCard = heat.closest('.card') || heat;
      heatCard.style.cssText = 'margin:0';
      const c = S.card(heatCard, { cls: '', width: 600 });
      c.style.placeSelf = 'start start';
      c.style.marginTop = '110px';
      c.style.zoom = '1.3';
      const trend = document.querySelector('.trend-card') || document.querySelector('[class*="trend-card"]')?.closest('.card');
      trend.style.margin = '0';
      S.second(trend, { cls: '', right: -60, bottom: -60, width: 640 });
      const exp = document.querySelector('.exports');
      exp.style.margin = '0';
      S.second(exp, { cls: '', right: -40, top: -40, width: 600 });
      window.__cells = [...heat.querySelectorAll('.heat__day')];
      window.__pdf = [...exp.querySelectorAll('a,button')].find((n) => /Downlink/.test(n.textContent));
      return true; })()`);
    await b.eval(frameFn((t) => {
      window.__st.tick(t, 2.5, { tilt: -5, secIn: 0.45 });
      window.__st.railAt(t, 5);
      const { ease, ramp, ripple, rect } = window.__ov;
      const cells = window.__cells;
      cells.forEach((c, i) => {
        const p = ease.outExpo(ramp(t, 0.2 + i * 0.022, 0.5 + i * 0.022));
        c.style.opacity = String(p);
        c.style.transform = `scale(${0.4 + 0.6 * p})`;
      });
      if (window.__pdf) { const r = rect(window.__pdf); ripple(r.x, r.y, t, 1.6); }
    }));
    return 2.5;
  },

  // 9: Alerts (2.5 s)
  async alerts(b) {
    await page(b, '/notifications');
    await b.eval(`(() => {
      const S = window.__st;
      S.build({ index: 6, kicker: 'Alerts', title: ['Get help now.', 'Even 14 minutes from Earth.'],
        cap: 'Cautious rules escalate to the crew<br>medical officer, then the flight surgeon', glow: '#FF4D6D', dot: '#FF4D6D' });
      const bar = document.querySelector('[data-alertbar]');
      bar.hidden = false;
      bar.querySelector('[data-alertbar-text]').textContent = 'Blood pressure 186/118: get help now. Please tell your crew medical officer now and follow the onboard medical protocol. Messages to Earth take 14 min.';
      bar.style.cssText = 'margin:0;border-radius:24px';
      S.card(bar, { cls: '', width: 860 });
      const list = document.querySelector('.notes-list');
      if (list) {
        [...list.children].slice(3).forEach((n) => n.remove());
        list.style.margin = '0';
        S.second(list, { cls: '', left: 30, top: 470, width: 800 });
      }
      window.__bar = bar;
      return true; })()`);
    await b.eval(frameFn((t) => {
      window.__st.tick(t, 2.5, { tilt: -4, secIn: 0.4 });
      window.__st.railAt(t, 6);
      const pulse = 0.5 + 0.5 * Math.cos(t * Math.PI * 2 * 2); // on the beat
      window.__bar.style.boxShadow = `0 0 ${40 + 50 * pulse}px rgba(255,77,109,${0.25 + 0.3 * pulse}), 0 40px 120px rgba(0,0,0,.7)`;
    }));
    return 2.5;
  },

  // 10: Mission Control (2.5 s)
  async mc(b) {
    await page(b, '/mission-control', { as: 'FS-9001' });
    await b.eval(`(() => {
      const S = window.__st;
      S.build({ index: 7, kicker: 'Mission Control', title: ['Mission Control.', 'The whole crew at a glance.'],
        cap: 'For the flight surgeon: status colours only<br>no transcripts · every view audited', glow: '#FFC53D' });
      const cards = [...document.querySelectorAll('.crew')];
      const slot = S.root.querySelector('.st-slot');
      const [a, bb, cc] = cards;
      [bb, cc].forEach((c, i) => {
        c.style.margin = '0';
        c.style.background = '#0B0D12';
        const w = S.second(c, { cls: '', left: i ? 430 : -30, top: i ? 440 : 20, width: 360 });
        w.style.zoom = '1.15';
        w.style.filter = 'brightness(.75)';
      });
      a.style.margin = '0';
      a.style.background = '#0B0D12';
      const main = S.card(a, { cls: '', width: 380 });
      main.style.zoom = '1.45';
      main.style.zIndex = '2';
      return true; })()`);
    await b.eval(frameFn((t) => {
      window.__st.tick(t, 2.5, { secIn: 0.3 });
      window.__st.railAt(t, 7);
    }));
    return 2.5;
  },

  // 11: outro over the Earth (3.5 s)
  async outro(b) {
    await landing(b);
    await b.eval(`(() => {
      const { root } = window.__ov;
      const box = document.createElement('div');
      box.className = 'bo-block';
      box.style.cssText = 'left:0;right:0;top:250px;text-align:center;display:flex;flex-direction:column;align-items:center;';
      box.innerHTML = '<div class="headline headline--big" style="font-size:100px;line-height:1.0"><span class="bo-line">Astronaut, are you</span><span class="bo-line bo-second">mission-ready?</span></div>'
        + '<div class="bo-line" style="margin-top:56px"><span class="bo-wordmark"><img src="/static/img/favicon.svg" alt="">AstroVital</span></div>'
        + '<div class="bo-line bo-mono" style="margin-top:22px">Runs on one computer · offline-first · prototype, not a medical device</div>';
      root.append(box);
      const black = document.createElement('div');
      black.style.cssText = 'position:absolute;inset:0;background:#000';
      root.prepend(black);
      window.__lines = [...box.querySelectorAll('.bo-line')];
      window.__black = black;
      const st = window.__st.build({ text: false, index: 7 });
      st.style.background = 'transparent'; st.style.zIndex = '2147483001';
      st.querySelector('.st-glow').remove(); st.querySelector('.st-grain').remove();
      return true; })()`);
    await b.eval(frameFn((t) => {
      const { line, ease, ramp } = window.__ov;
      window.__astroHero.setProgress(0.04 + 0.28 * ease.inOut(ramp(t, 0, 3.5)));
      window.__black.style.opacity = String(1 - ease.out(ramp(t, 0.1, 0.9)));
      window.__st.railAt(1, 7, { show: 1 - ease.in(ramp(t, 0.0, 0.4)) });
      const [a, c, d, e] = window.__lines;
      line(a, t, 0.3, Infinity, { dist: 40 });
      line(c, t, 0.5, Infinity, { dist: 40 });
      line(d, t, 1.0, Infinity, { dist: 20 });
      line(e, t, 1.2, Infinity, { dist: 14 });
    }));
    return 3.5;
  },
};

const order = only.length ? only : Object.keys(SCENES);
for (const name of order) {
  const b = await launch({ userDir: `${process.cwd()}/chrome`, port: 9333 });
  try {
    const seconds = await SCENES[name](b);
    const frames = Math.round(seconds * FPS);
    console.log(`${name}: ${frames} frames`);
    if (stills) {
      const dir = process.env.STILLS || 'stills';
      mkdirSync(dir, { recursive: true });
      await b.eval('window.__vt.freeze(), true');
      const picks = [Math.round(frames * 0.12), Math.round(frames * 0.5), Math.round(frames * 0.8), frames - 4];
      let f = 0;
      for (const target of picks) {
        for (; f <= target; f++) {
          await b.eval(`(async () => { window.__frame?.(${f / FPS}); window.__vt.step(${1000 / FPS}); window.__syncAnims?.(); return true; })()`);
        }
        await b.shot(`${dir}/${name}_${String(target).padStart(3, '0')}.jpg`);
      }
    } else {
      await b.record(`frames/${name}`, { frames, fps: FPS });
    }
  } catch (e) {
    console.log(`${name} FAILED: ${e.message}`);
  } finally {
    await b.close();
    await wait(800);
  }
}

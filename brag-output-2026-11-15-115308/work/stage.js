// Module stage: lifts real components out of the running page onto a designed scene.
// Needs overlay.js (window.__ov) first. Everything is driven by __st.tick(t).
(() => {
  if (window.__st) return;
  const { ramp, ease, clamp } = window.__ov;
  const MODULES = ['Heart', 'Bones & muscle', 'Mind', 'Body twin', 'Dr. NOVA', 'History', 'Alerts', 'Mission Control'];
  const css = document.createElement('style');
  css.textContent = `
    #st { position: fixed; inset: 0; z-index: 9000; background: #000; overflow: hidden; color: var(--text);
      font-family: var(--font-sans); }
    #st .st-glow { position: absolute; width: 1500px; height: 1500px; left: 600px; top: -260px; border-radius: 50%;
      background: radial-gradient(circle, var(--st-glow) 0%, transparent 62%); opacity: .2; filter: blur(30px); }
    #st .st-grain { position: absolute; inset: 0; background:
      radial-gradient(1px 1px at 12% 18%, rgba(255,255,255,.35), transparent),
      radial-gradient(1px 1px at 72% 12%, rgba(255,255,255,.25), transparent),
      radial-gradient(1px 1px at 38% 78%, rgba(255,255,255,.2), transparent),
      radial-gradient(1px 1px at 88% 64%, rgba(255,255,255,.3), transparent),
      radial-gradient(1px 1px at 22% 58%, rgba(255,255,255,.18), transparent),
      radial-gradient(1px 1px at 58% 38%, rgba(255,255,255,.22), transparent); }
    #st .st-text { position: absolute; left: 130px; top: 0; bottom: 0; width: 800px; display: flex;
      flex-direction: column; justify-content: center; gap: 28px; padding-bottom: 90px; }
    #st .st-kicker { font-family: var(--font-mono); font-size: 20px; letter-spacing: .14em; text-transform: uppercase;
      color: var(--text-2); display: flex; align-items: center; gap: 14px; }
    #st .st-kicker i { width: 10px; height: 10px; border-radius: 50%; background: var(--st-dot); box-shadow: 0 0 14px var(--st-dot); }
    #st .st-title { font-size: 76px; line-height: 1.0; font-weight: 500; letter-spacing: -.045em; }
    #st .st-title .bo-second { color: var(--text-3); }
    #st .st-cap { font-family: var(--font-mono); font-size: 19px; line-height: 1.6; color: var(--text-2); max-width: 600px; }
    #st .st-slot { position: absolute; left: 960px; right: 90px; top: 90px; bottom: 170px; perspective: 1700px;
      display: grid; place-items: center; }
    #st .st-card { position: relative; transform-style: preserve-3d; will-change: transform, opacity, filter; }
    #st .st-card.card { box-shadow: 0 40px 120px rgba(0,0,0,.7), 0 0 0 1px rgba(255,255,255,.06), 0 0 90px -30px var(--st-glow); background: #07090D; }
    #st .st-second { position: absolute; will-change: transform, opacity, filter; }
    #st .st-second.card { box-shadow: 0 30px 90px rgba(0,0,0,.8), 0 0 0 1px rgba(255,255,255,.08); background: #0A0C11; }
    #st .st-rail { position: absolute; left: 0; right: 0; bottom: 64px; display: flex; justify-content: center; }
    #st .st-rail ol { position: relative; display: flex; gap: 6px; margin: 0; padding: 6px; list-style: none;
      border: 1px solid var(--line); border-radius: 999px; background: rgba(255,255,255,.025); }
    #st .st-rail li { position: relative; z-index: 1; padding: 10px 20px; font-size: 17px; font-weight: 500; color: var(--text-3);
      white-space: nowrap; letter-spacing: -.01em; }
    #st .st-rail li.on { color: var(--primary-fg); }
    #st .st-rail .hl { position: absolute; z-index: 0; top: 6px; bottom: 6px; border-radius: 999px; background: var(--primary-bg); }
    #st .wrap-contents { display: contents; }
  `;
  document.head.append(css);

  let st = null;
  const parts = { lines: [], kicker: null, cap: null, card: null, seconds: [], rail: null };

  // Keep the selectors that depended on ancestors working, without their layout.
  function adopt(el) {
    const chain = [];
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      if (p.className && typeof p.className === 'string') chain.unshift(p.className);
    }
    let outer = null;
    let inner = null;
    for (const cls of chain) {
      const d = document.createElement('div');
      d.className = `${cls} wrap-contents`;
      d.removeAttribute('hidden');
      if (inner) inner.append(d); else outer = d;
      inner = d;
    }
    el.hidden = false;
    el.removeAttribute('hidden');
    if (inner) { inner.append(el); return outer; }
    return el;
  }

  function build({ index = -1, kicker, title, cap, glow = '#7CF3FF', dot, rail = true, text = true } = {}) {
    st = document.createElement('div');
    st.id = 'st';
    st.style.setProperty('--st-glow', glow);
    st.style.setProperty('--st-dot', dot || glow);
    st.innerHTML = '<div class="st-glow"></div><div class="st-grain"></div><div class="st-slot"></div>';
    document.body.append(st);
    if (text) {
      const tx = document.createElement('div');
      tx.className = 'st-text';
      tx.innerHTML = `<div class="st-kicker bo-line"><i></i>${index >= 0 ? `${String(index + 1).padStart(2, '0')} / 08 · ` : ''}${kicker}</div>`
        + `<div class="st-title"><span class="bo-line">${title[0]}</span><span class="bo-line bo-second">${title[1]}</span></div>`
        + (cap ? `<div class="st-cap bo-line">${cap}</div>` : '');
      st.append(tx);
      parts.kicker = tx.querySelector('.st-kicker');
      parts.lines = [...tx.querySelectorAll('.st-title .bo-line')];
      parts.cap = tx.querySelector('.st-cap');
    }
    if (rail) {
      const r = document.createElement('div');
      r.className = 'st-rail';
      r.innerHTML = `<ol><span class="hl"></span>${MODULES.map((m) => `<li>${m}</li>`).join('')}</ol>`;
      st.append(r);
      parts.rail = { root: r, items: [...r.querySelectorAll('li')], hl: r.querySelector('.hl'), index };
    }
    return st;
  }

  function card(el, { cls = 'card', width, height, pad = '32px 36px' } = {}) {
    const c = document.createElement('div');
    c.className = `st-card ${cls}`;
    if (width) c.style.width = `${width}px`;
    if (height) c.style.height = `${height}px`;
    if (cls.includes('card')) c.style.padding = pad;
    if (el) c.append(adopt(el));
    st.querySelector('.st-slot').append(c);
    parts.card = c;
    return c;
  }

  function second(el, { cls = 'card', left, top, right, bottom, width, pad = '22px 26px' } = {}) {
    const c = document.createElement('div');
    c.className = `st-second ${cls}`;
    Object.assign(c.style, {
      left: left != null ? `${left}px` : '', top: top != null ? `${top}px` : '',
      right: right != null ? `${right}px` : '', bottom: bottom != null ? `${bottom}px` : '',
      width: width ? `${width}px` : '', padding: cls.includes('card') ? pad : '',
    });
    if (el) c.append(adopt(el));
    st.querySelector('.st-slot').append(c);
    parts.seconds.push(c);
    return c;
  }

  function railAt(t, index, { prev = index - 1, show = 1 } = {}) {
    const r = parts.rail;
    if (!r) return;
    const box = r.root.querySelector('ol').getBoundingClientRect();
    const place = (i) => {
      if (i < 0) return { x: r.items[0].offsetLeft, w: 0 };
      const it = r.items[i];
      return { x: it.offsetLeft, w: it.offsetWidth };
    };
    const a = place(prev);
    const b = place(index);
    const p = ease.outExpo(ramp(t, 0.0, 0.45));
    const x = a.x + (b.x - a.x) * p;
    const w = a.w + (b.w - a.w) * p;
    r.hl.style.left = `${x}px`;
    r.hl.style.width = `${w}px`;
    r.hl.style.opacity = index < 0 ? '0' : '1';
    r.items.forEach((it, i) => it.classList.toggle('on', i === index && p > 0.5));
    r.root.style.opacity = String(show);
    return box;
  }

  // Standard choreography: text in, card tilts in, seconds follow, all out at the end.
  function tick(t, dur, { cardIn = 0.12, secIn = 0.32, exit = 0.26, tilt = -7 } = {}) {
    const out = ease.in(ramp(t, dur - exit, dur));
    const L = window.__ov.line;
    if (parts.kicker) L(parts.kicker, t, 0.0, dur - exit, { dist: 14, dur: 0.5, blur: 4, outDur: exit });
    parts.lines.forEach((n, i) => L(n, t, 0.06 + i * 0.1, dur - exit, { dist: 44, dur: 0.6, outDur: exit }));
    if (parts.cap) L(parts.cap, t, 0.3, dur - exit, { dist: 14, dur: 0.6, blur: 4, outDur: exit });
    const drift = ease.sine(ramp(t, 0, dur));
    if (parts.card) {
      const a = ease.outExpo(ramp(t, cardIn, cardIn + 0.75));
      const c = parts.card;
      c.style.opacity = String(clamp(a * 1.6) * (1 - out));
      c.style.transform = `translateX(${(1 - a) * 160 - out * 60}px) translateY(${(1 - a) * 20 - drift * 8}px) `
        + `rotateY(${tilt + (1 - a) * -26 + drift * 2.5}deg) rotateX(${2 - drift}deg) scale(${0.94 + 0.06 * a})`;
      const f = (1 - a) * 12 + out * 10;
      c.style.filter = f > 0.05 ? `blur(${f.toFixed(2)}px)` : 'none';
    }
    parts.seconds.forEach((c, i) => {
      const at = secIn + i * 0.12;
      const a = ease.outExpo(ramp(t, at, at + 0.7));
      c.style.opacity = String(clamp(a * 1.6) * (1 - out));
      c.style.transform = `translateY(${(1 - a) * 70 - drift * 18 - out * 30}px) translateX(${-out * 40}px) scale(${0.96 + 0.04 * a})`;
      const f = (1 - a) * 10 + out * 10;
      c.style.filter = f > 0.05 ? `blur(${f.toFixed(2)}px)` : 'none';
    });
    st.querySelector('.st-glow').style.opacity = String(0.2 * ease.out(ramp(t, 0, 0.6)) * (1 - out * 0.6));
  }

  window.__st = { MODULES, build, card, second, adopt, railAt, tick, parts, get root() { return st; } };
})();

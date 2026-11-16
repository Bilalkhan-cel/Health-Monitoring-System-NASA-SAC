// Injected into every captured page: easing helpers, a camera transform on <body>, an overlay layer
// outside <body> for captions and touch ripples. Everything is a function of scene time t.
(() => {
  if (window.__ov) return;
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ramp = (t, a, b) => clamp((t - a) / (b - a));
  const ease = {
    out: (x) => 1 - (1 - x) ** 3,
    outExpo: (x) => (x >= 1 ? 1 : 1 - 2 ** (-10 * x)),
    inOut: (x) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2),
    in: (x) => x * x * x,
    sine: (x) => -(Math.cos(Math.PI * x) - 1) / 2,
  };
  const style = document.createElement('style');
  style.textContent = `
    #bo { position: fixed; inset: 0; z-index: 2147483000; pointer-events: none; font-family: var(--font-sans); color: var(--text); }
    #bo .bo-block { position: absolute; }
    .skip-link { display: none !important; }
    .bo-line { display: block; will-change: transform, opacity, filter; }
    #bo .bo-second { color: var(--text-3); }
    #bo .bo-scrim { position: absolute; left: 0; right: 0; bottom: 0; height: 52%;
      background: linear-gradient(to top, rgba(0,0,0,.94) 0%, rgba(0,0,0,.82) 38%, rgba(0,0,0,0) 100%); }
    #bo .bo-ripple { position: absolute; width: 0; height: 0; }
    #bo .bo-ripple i { position: absolute; left: 0; top: 0; border-radius: 50%; transform: translate(-50%, -50%); }
    #bo .bo-ripple .ring { border: 2px solid rgba(242,244,247,.9); }
    #bo .bo-ripple .dotc { background: rgba(242,244,247,.35); }
    #bo .bo-mono { font-family: var(--font-mono); font-size: 18px; letter-spacing: .02em; color: var(--text-2); }
    #bo .bo-wordmark { display: inline-flex; align-items: center; gap: 18px; font-weight: 600; font-size: 44px; letter-spacing: -.03em; }
    #bo .bo-wordmark img { width: 54px; height: 54px; }
  `;
  document.head.append(style);
  const root = document.createElement('div');
  root.id = 'bo';
  document.documentElement.append(root);

  // A text line that rises in through a soft blur, then lifts out.
  function line(node, t, inAt, outAt = Infinity, { dist = 34, dur = 0.7, blur = 10, outDur = 0.35 } = {}) {
    const a = ease.outExpo(ramp(t, inAt, inAt + dur));
    const b = Number.isFinite(outAt) ? ease.in(ramp(t, outAt, outAt + outDur)) : 0;
    node.style.opacity = String(clamp(a * 1.4) * (1 - b));
    node.style.transform = `translateY(${(1 - a) * dist - b * dist * 0.8}px)`;
    const f = (1 - a) * blur + b * blur;
    node.style.filter = f > 0.05 ? `blur(${f.toFixed(2)}px)` : 'none';
  }

  function ripple(x, y, t, at) {
    let el = root.querySelector(`[data-at="${at}"]`);
    if (!el) {
      el = document.createElement('div');
      el.className = 'bo-ripple';
      el.dataset.at = at;
      el.innerHTML = '<i class="dotc"></i><i class="ring"></i>';
      root.append(el);
    }
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    const p = ramp(t, at - 0.12, at + 0.5);
    const press = ramp(t, at - 0.12, at) * (1 - ramp(t, at + 0.05, at + 0.3));
    const [dot, ring] = el.children;
    const r = 26 + ease.out(ramp(t, at, at + 0.5)) * 54;
    ring.style.width = ring.style.height = `${r * 2}px`;
    ring.style.opacity = String(t < at ? 0 : 1 - ease.out(ramp(t, at, at + 0.5)));
    const d = 30 * (0.6 + 0.4 * press);
    dot.style.width = dot.style.height = `${d * 2}px`;
    dot.style.opacity = String(p > 0 && p < 1 ? Math.min(1, press * 1.5 + (1 - ramp(t, at + 0.1, at + 0.45)) * 0.6) : 0);
  }

  // Camera: scale around a page point, landing it at a screen point.
  function camera(scale, px, py, sx = 960, sy = 540) {
    const b = document.body;
    b.style.transformOrigin = '0 0';
    b.style.transform = `translate(${sx - px * scale}px, ${sy - py * scale}px) scale(${scale})`;
  }

  function rect(selector) {
    const el = typeof selector === 'string' ? document.querySelector(selector) : selector;
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, l: r.left, t: r.top };
  }

  window.__ov = { root, clamp, ramp, ease, line, ripple, camera, rect };
})();

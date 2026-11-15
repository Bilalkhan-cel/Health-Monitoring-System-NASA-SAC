// Quality tiers for the 3D scenes (Section 6.1): high, med, low.
// Picked from ?q=, device pixel ratio, CPU cores and (for the hero) a 1-second FPS probe.

const TIERS = {
  high: { name: 'high', dprCap: 2, textures: '4k', clouds: true, bodyDpr: 1.75 },
  med: { name: 'med', dprCap: 1.5, textures: '2k', clouds: true, bodyDpr: 1.5 },
  low: { name: 'low', dprCap: 1, textures: '2k', clouds: false, bodyDpr: 1 },
};

export function webglAvailable() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'));
  } catch {
    return false;
  }
}

export function reducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
    || document.documentElement.classList.contains('reduce-motion');
}

export function initialTier() {
  const forced = new URLSearchParams(window.location.search).get('q');
  if (forced && TIERS[forced]) return TIERS[forced];
  const cores = navigator.hardwareConcurrency || 4;
  const dpr = window.devicePixelRatio || 1;
  if (cores <= 2) return TIERS.low;
  if (cores >= 8 && dpr <= 2) return TIERS.high;
  return TIERS.med;
}

export function forcedTier() {
  const forced = new URLSearchParams(window.location.search).get('q');
  return forced && TIERS[forced] ? TIERS[forced] : null;
}

// Measure frames for ~1 s while the scene renders, then step down if it is slow.
export function probeFps(durationMs = 1000) {
  return new Promise((resolve) => {
    let frames = 0;
    const start = performance.now();
    const tick = (now) => {
      frames += 1;
      if (now - start < durationMs) requestAnimationFrame(tick);
      else resolve((frames * 1000) / (now - start));
    };
    requestAnimationFrame(tick);
  });
}

export function tierAfterProbe(current, fps) {
  if (fps < 32) return TIERS.low;
  if (fps < 50 && current.name === 'high') return TIERS.med;
  return current;
}

export { TIERS };

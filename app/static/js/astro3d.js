// 3D scenes shared by the landing page, login and Today (Section 9.5):
//   mountTwin(container, opts)  digital twin (3D hologram, 2D SVG fallback)
//   mountHero(canvas, opts)     Earth + NASA ISS (landing and login)
// Both pause when the tab is hidden and cap the pixel ratio by quality tier.

import { mountTwin2D } from './3d/twin2d.js';
import { initialTier, reducedMotion, webglAvailable } from './3d/quality.js';

const STATIC = document.querySelector('meta[name="static-root"]')?.content || '/static/';

export async function mountTwin(container, options = {}) {
  // Instant first paint with the 2D body, then upgrade to WebGL when it is ready.
  const flat = mountTwin2D(container, options);
  if (!webglAvailable() || options.force2d) return flat;
  const proxy = { ...flat };
  const pending = { status: null, selected: null, bpm: null };
  proxy.select = (id) => { pending.selected = id; flat.select(id); };
  proxy.setStatus = (systems) => { pending.status = systems; flat.setStatus(systems); };
  proxy.setHeartRate = (bpm) => { pending.bpm = bpm; };
  try {
    const { mountBody } = await import('./3d/twin.js');
    const host = document.createElement('div');
    host.className = 'twin__webgl';
    container.append(host);
    const tier = initialTier();
    const body = await mountBody(host, {
      ...options,
      modelUrl: `${STATIC}models/astronaut.glb`,
      reducedMotion: reducedMotion(),
      dprCap: tier.bodyDpr,
    });
    flat.destroy();
    container.dataset.twin = '3d';
    if (pending.status) body.setStatus(pending.status);
    if (pending.selected) body.select(pending.selected);
    if (pending.bpm) body.setHeartRate(pending.bpm);
    Object.assign(proxy, body);
    return proxy;
  } catch {
    container.querySelector('.twin__webgl')?.remove();
    container.dataset.twin = '2d';
    return flat;
  }
}

export async function mountHero(canvas, options = {}) {
  if (!webglAvailable() || reducedMotion()) return null;
  const { mountEarthScene } = await import('./3d/earth.js');
  return mountEarthScene(canvas, { ...options, staticRoot: STATIC });
}

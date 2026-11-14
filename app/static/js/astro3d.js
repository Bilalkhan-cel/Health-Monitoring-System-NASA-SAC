// 3D scenes: mountTwin (digital twin) and mountHero (Earth + ISS). Phase 1 ships the
// 2D twin only; the WebGL versions replace these exports in later phases.

import { mountTwin2D } from './3d/twin2d.js';

export async function mountTwin(container, options = {}) {
  return mountTwin2D(container, options);
}

export async function mountHero() {
  return null;
}

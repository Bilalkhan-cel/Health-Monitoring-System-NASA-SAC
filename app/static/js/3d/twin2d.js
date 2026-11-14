// 2D digital twin: an SVG hologram body with the same three hotspots as the 3D twin.
// Used when WebGL is unavailable and as the instant first paint before the 3D model loads.

import { svg } from '../app/dom.js';

const SPOTS = {
  mind: { x: 120, y: 46, tagX: 160, tagY: 30, label: 'Mind' },
  heart: { x: 130, y: 122, tagX: 168, tagY: 108, label: 'Heart' },
  bones: { x: 104, y: 312, tagX: 14, tagY: 300, label: 'Bones' },
};

const BODY = [
  'M120 20c13 0 23 11 23 26s-10 28-23 28-23-12-23-28 10-26 23-26z',
  'M110 74h20v14h-20z',
  'M84 92c12-6 24-8 36-8s24 2 36 8l12 10c4 34 0 70-14 104H86C72 172 68 136 72 102z',
  'M72 102c-12 28-16 64-16 102 0 18 3 34 7 48h10c-1-20 1-44 7-66 5-20 8-46 6-74z',
  'M168 102c12 28 16 64 16 102 0 18-3 34-7 48h-10c1-20-1-44-7-66-5-20-8-46-6-74z',
  'M86 206h68l-6 40-12 170h-14l-2-150-2 150H104l-12-170z',
];
const DETAIL = [
  'M120 90v116', 'M96 120c16 8 32 8 48 0', 'M94 140c17 8 35 8 52 0', 'M96 160c16 7 32 7 48 0',
  'M106 330h12', 'M122 330h12', 'M120 206v60',
];

export function mountTwin2D(container, { onSelect } = {}) {
  const root = svg('svg', { class: 'twin2d', viewBox: '0 0 240 440', role: 'group',
    'aria-label': 'Body map. Choose a glowing point to see that system.' });
  const glow = svg('g', {});
  for (const d of BODY) glow.append(svg('path', { d, class: 'body-shape' }));
  for (const d of DETAIL) glow.append(svg('path', { d, class: 'body-line' }));
  root.append(glow);

  const nodes = {};
  for (const [id, spot] of Object.entries(SPOTS)) {
    const group = svg('g', { class: 'hotspot', tabindex: '0', role: 'button', 'data-system': id });
    group.append(svg('circle', { class: 'halo', cx: spot.x, cy: spot.y, r: 18 }));
    group.append(svg('circle', { class: 'ring', cx: spot.x, cy: spot.y, r: 11 }));
    group.append(svg('circle', { cx: spot.x, cy: spot.y, r: 22, fill: 'transparent' }));
    const tag = svg('g', { class: 'tag' });
    tag.append(svg('rect', { x: spot.tagX, y: spot.tagY, width: 66, height: 22, rx: 6 }));
    const text = svg('text', { x: spot.tagX + 9, y: spot.tagY + 15 });
    text.textContent = spot.label;
    tag.append(text);
    group.append(tag);
    const choose = () => onSelect?.(id);
    group.addEventListener('click', choose);
    group.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        choose();
      }
    });
    root.append(group);
    nodes[id] = { group, text, spot };
  }
  container.replaceChildren(root);

  return {
    kind: '2d',
    hint: 'Tap a glowing point',
    select(id) {
      for (const [key, node] of Object.entries(nodes)) {
        node.group.classList.toggle('is-selected', key === id);
        node.group.setAttribute('aria-pressed', String(key === id));
      }
    },
    setStatus(systems) {
      for (const [key, node] of Object.entries(nodes)) {
        const info = systems[key] || {};
        node.group.setAttribute('class', `hotspot${info.key ? ` is-${info.key}` : ''}`
          + (node.group.classList.contains('is-selected') ? ' is-selected' : ''));
        node.text.textContent = `${node.spot.label}${info.score != null ? `  ${info.score}` : ''}`;
        node.group.setAttribute('aria-label', `${info.title || node.spot.label}: ${info.word || 'no recent readings'}`);
      }
    },
    setHeartRate() {},
    destroy() { root.remove(); },
  };
}

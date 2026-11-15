// Tiny DOM helpers shared by every page script.

const SVG_NS = 'http://www.w3.org/2000/svg';

export function spriteUrl() {
  return document.querySelector('[data-sprite]')?.dataset.sprite ?? '/static/vendor/lucide/sprite.svg';
}

export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'style' && typeof value === 'object') Object.assign(node.style, value);
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    node.setAttribute(key, String(value));
  }
  for (const child of children.flat()) if (child) node.append(child);
  return node;
}

export function icon(name, cls = '') {
  const node = svg('svg', { class: `icon ${cls}`.trim(), 'aria-hidden': 'true', focusable: 'false' });
  node.append(svg('use', { href: `${spriteUrl()}#${name}` }));
  return node;
}

export function clear(node) {
  while (node.firstChild) node.firstChild.remove();
  return node;
}

export function statusPill(status) {
  if (!status) return null;
  return h('span', { class: `status is-${status.key}` }, icon(status.icon), status.verdict || status.label);
}

export function toast(text, ms = 3600) {
  const host = document.querySelector('[data-toasts]');
  if (!host) return;
  const item = h('div', { class: 'toast', role: 'status' }, text);
  host.append(item);
  window.setTimeout(() => item.remove(), ms);
}

export function sparkline(values, statusKey) {
  const width = 96;
  const height = 28;
  const node = svg('svg', { class: `spark${statusKey ? ` is-${statusKey}` : ''}`, viewBox: `0 0 ${width} ${height}`,
    'aria-hidden': 'true' });
  if (!values || values.length < 2) return node;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const points = values.map((v, i) => [
    2 + (i * (width - 6)) / (values.length - 1),
    height - 4 - ((v - lo) / span) * (height - 8),
  ]);
  node.append(svg('polyline', { points: points.map((p) => p.join(',')).join(' '), fill: 'none',
    stroke: 'currentColor', 'stroke-width': '1.5', 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
  const [x, y] = points[points.length - 1];
  node.append(svg('circle', { cx: x, cy: y, r: '2.5' }));
  return node;
}

export const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
  || document.documentElement.classList.contains('reduce-motion');

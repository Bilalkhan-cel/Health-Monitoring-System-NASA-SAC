// Landing page: Earth + ISS hero (scroll dollies the camera), one orchestrated intro, quiet
// reveals, the hologram twin with example data, and tiny live visuals for the three checks.

import { mountHero, mountTwin } from '../astro3d.js';
import { createHeartbeat } from './ecg_synth.js';
import { clear, h, statusPill } from './dom.js';

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const gsap = window.gsap;

const DEMO = {
  heart: { title: 'Heart', status: { key: 'watch', icon: 'triangle-alert', label: 'Needs attention' },
    text: 'Resting heart rate 104. The usual is 72.', todo: 'drink a glass of water now and check again at 2 pm.' },
  mind: { title: 'Mind', status: { key: 'okay', icon: 'circle-dot', label: 'Okay' },
    text: 'Mood 62 after three short nights.', todo: 'dim the lights an hour before bed tonight.' },
  bones: { title: 'Bones & muscle', status: { key: 'good', icon: 'circle-check', label: 'Good' },
    text: 'Exercise load 88: on track this week.', todo: 'keep the daily session going.' },
};

async function hero() {
  const canvas = document.querySelector('[data-hero-canvas]');
  let scene = null;
  try {
    scene = await mountHero(canvas, { variant: 'hero' });
  } catch {
    scene = null;
  }
  const section = document.querySelector('[data-hero]');
  section.classList.toggle('has-webgl', Boolean(scene));
  if (scene) document.querySelector('[data-hero-poster]')?.remove();
  if (!gsap) return;
  if (window.ScrollTrigger) gsap.registerPlugin(window.ScrollTrigger);
  const mm = gsap.matchMedia();
  mm.add('(prefers-reduced-motion: no-preference)', () => {
    const intro = gsap.timeline({ defaults: { ease: 'power3.out' } });
    intro.from('[data-hero-copy] .tag', { y: 16, autoAlpha: 0, duration: 0.7 })
      .from('[data-hero-copy] .headline', { y: 28, autoAlpha: 0, duration: 1.1 }, '-=0.4')
      .from('[data-hero-copy] .lede', { y: 16, autoAlpha: 0, duration: 0.8 }, '-=0.7')
      .from('[data-hero-copy] .hero__actions', { y: 12, autoAlpha: 0, duration: 0.7 }, '-=0.55')
      .from('.topnav', { autoAlpha: 0, duration: 0.8 }, '<');
    // GSAP pauses with requestAnimationFrame in background tabs; never leave the copy hidden.
    const settle = window.setTimeout(() => { if (intro.progress() < 1) intro.progress(1); }, 3000);
    if (scene && window.ScrollTrigger) {
      window.ScrollTrigger.create({ trigger: section, start: 'top top', end: 'bottom top', scrub: true,
        onUpdate: (self) => scene.setProgress(self.progress) });
      gsap.to('[data-hero-copy]', { y: -80, autoAlpha: 0, ease: 'none',
        scrollTrigger: { trigger: section, start: 'top top', end: '60% top', scrub: true } });
    }
    if (window.ScrollTrigger) {
      window.ScrollTrigger.batch('[data-reveal]', {
        start: 'top 85%', once: true,
        onEnter: (items) => gsap.from(items, { y: 24, autoAlpha: 0, duration: 0.9, stagger: 0.12, ease: 'power2.out' }),
      });
    }
    return () => window.clearTimeout(settle);
  });
  window.__astroHero = scene;
}

async function twinShowcase() {
  const host = document.querySelector('[data-demo-twin]');
  const card = document.querySelector('[data-demo-card]');
  let selected = 'heart';
  const render = () => {
    const item = DEMO[selected];
    clear(card).append(
      h('div', { class: 'card__head' }, h('h3', { class: 'card__title' }, item.title), statusPill(item.status)),
      h('p', {}, item.text),
      h('p', { class: 'card__meta' }, h('strong', {}, 'Do this: '), item.todo));
    for (const pill of document.querySelectorAll('[data-demo-pill]')) {
      pill.setAttribute('aria-pressed', String(pill.dataset.demoPill === selected));
    }
    twin?.select(selected);
  };
  const select = (id) => { selected = id; render(); };
  for (const pill of document.querySelectorAll('[data-demo-pill]')) {
    pill.addEventListener('click', () => select(pill.dataset.demoPill));
  }
  let twin = null;
  render();
  twin = await mountTwin(host, { onSelect: select, showTags: true });
  twin.setStatus({ heart: { key: 'watch', score: 79, title: 'Heart', word: 'Needs attention' },
    mind: { key: 'okay', score: 72, title: 'Mind', word: 'Okay' },
    bones: { key: 'good', score: 100, title: 'Bones & muscle', word: 'Good' } });
  twin.setHeartRate(reduced ? null : 72);
  twin.select(selected);
}

function miniVisuals() {
  const canvas = document.querySelector('[data-mini-heart]');
  if (canvas) {
    const wave = createHeartbeat(canvas, { reducedMotion: reduced });
    wave.setBpm(72);
  }
  const reps = document.querySelector('[data-mini-reps]');
  if (reps && !reduced) {
    let count = 14;
    window.setInterval(() => {
      count = count >= 20 ? 14 : count + 1;
      reps.textContent = count;
    }, 1800);
  }
}

if (new URLSearchParams(window.location.search).has('poster')) document.documentElement.classList.add('is-poster');
hero();
twinShowcase();
miniVisuals();

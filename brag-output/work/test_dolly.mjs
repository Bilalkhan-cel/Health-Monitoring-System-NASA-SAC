import { launch } from './cdp.mjs';
const b = await launch({ userDir: process.cwd() + '/chrome' });
await b.goto('http://127.0.0.1:5001/?q=high', 500);
await b.waitFor('document.documentElement.dataset.sceneReady === "1"');
await b.eval(`(() => { const s = document.createElement('style'); s.textContent = '.hero{min-height:100vh!important} .hero__copy,.topnav,.hero__caption{visibility:hidden!important}'; document.head.append(s); window.ScrollTrigger?.getAll().forEach(x=>x.kill()); window.dispatchEvent(new Event('resize')); return true; })()`);
for (const p of [0, 0.15, 0.3, 0.5]) {
  await b.eval(`window.__astroHero.setProgress(${p}), true`);
  await new Promise(r => setTimeout(r, 600));
  await b.shot(`dolly_${p}.jpg`);
}
await b.close();

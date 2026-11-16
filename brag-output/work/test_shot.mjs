import { launch } from './cdp.mjs';
const b = await launch({ userDir: process.cwd() + '/chrome' });
await b.goto('http://127.0.0.1:5001/?q=high', 500);
await b.waitFor('document.documentElement.dataset.sceneReady === "1"');
await new Promise(r => setTimeout(r, 4000));
console.log(await b.eval('JSON.stringify({tier: window.__astroHero?.tier, fps: window.__astroHero?.fps, gl: !!document.querySelector(".has-webgl")})'));
await b.shot('test_landing.jpg');
await b.close();

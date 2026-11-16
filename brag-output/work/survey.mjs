import { launch } from './cdp.mjs';
const B='http://127.0.0.1:5001';
const b = await launch({ userDir: process.cwd() + '/chrome' });
await b.send('Network.enable'); await b.send('Network.clearBrowserCookies');
await b.goto(B + '/login', 600);
await b.eval(`(() => { const i = document.querySelector('input[name=astro_id]'); i.value = 'AST-1001'; i.form.submit(); return true; })()`);
await new Promise(r=>setTimeout(r,2500));
for (const p of ['/cardio','/musculoskeletal','/mental','/history','/notifications','/settings']) {
  await b.goto(B + p, 4000);
  const h = await b.eval('document.documentElement.scrollHeight');
  await b.send('Emulation.setDeviceMetricsOverride', { width: 1920, height: Math.min(h, 3000), deviceScaleFactor: 0.5, mobile: false });
  await new Promise(r=>setTimeout(r,800));
  await b.shot('survey' + p.replace('/','_') + '.jpg');
  await b.send('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
}
await b.close();

import { launch } from './cdp.mjs';
const b = await launch({ userDir: process.cwd() + '/chrome' });
const B = 'http://127.0.0.1:5001';
async function login(id) {
  await b.goto(B + '/login', 800).catch(()=>{});
  await b.eval(`location.pathname`).then(console.log);
  await b.eval(`(() => { const i = document.querySelector('input[name=astro_id]'); i.value = '${id}'; i.form.submit(); return true; })()`);
  await new Promise(r => setTimeout(r, 2500));
}
await login('AST-1001');
for (const p of ['/dashboard', '/doctor', '/cardio', '/history']) {
  await b.goto(B + p + '?q=high', 6000);
  await b.shot('test' + p.replace('/', '_') + '.jpg');
}
await b.send('Network.clearBrowserCookies');
await login('FS-9001');
await b.goto(B + '/mission-control', 3000);
await b.shot('test_mc.jpg');
await b.close();

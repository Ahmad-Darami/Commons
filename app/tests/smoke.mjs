// End-to-end smoke test: builds nothing, serves dist/ with `vite preview`, and drives the Room in headless Chromium.
// Run `npm run build` first. Set CHROME=/path/to/chrome to use a specific browser; screenshots go to tests/out/.
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';

const out = new URL('./out/', import.meta.url).pathname; mkdirSync(out, { recursive: true });
const vite = new URL('../node_modules/vite/bin/vite.js', import.meta.url).pathname;
const server = spawn(process.execPath, [vite, 'preview', '--port', '4319', '--strictPort'], { stdio: 'pipe', cwd: new URL('..', import.meta.url).pathname });
await new Promise((ok, fail) => { server.stdout.on('data', d => String(d).includes('4319') && ok()); setTimeout(() => fail(new Error('preview server did not start')), 20000); });
const fails = [];
const check = (ok, what) => { console.log(`${ok ? '✓' : '✗'} ${what}`); if (!ok) fails.push(what); };
const browser = await chromium.launch({ executablePath: process.env.CHROME, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 760 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto('http://localhost:4319/?debug');
  await page.waitForFunction(() => document.body.innerText.includes('M splats'), null, { timeout: 90000 });
  const st = () => page.evaluate(() => { const s = window.__commons.getState(); return { me: s.me, seats: s.layout.seats.length }; });
  check((await st()).me.seatId === null, 'Room loads with the scan, standing');
  await page.waitForTimeout(1500); await page.screenshot({ path: out + '1-room.png' });

  await page.evaluate(() => window.__commons.getState().setMe({ x: -0.6, z: 1.45, yaw: 0 }));
  await page.keyboard.press('e'); await page.waitForTimeout(300);
  check((await st()).me.seatId === 'seat-1', 'E sits in the nearest seat');
  await page.keyboard.press('l'); await page.waitForTimeout(800);
  check((await st()).me.working === true, 'L opens the Laptop (Desk Mode)');
  await page.screenshot({ path: out + '2-seated-working.png' });
  await page.keyboard.press('e'); await page.waitForTimeout(300);
  const after = await st();
  check(after.me.seatId === null && after.me.working === false, 'E stands up and closes the Laptop');

  await page.getByText('Curate Room').click();
  await page.getByText('＋ Seat').click();
  await page.mouse.click(640, 700); await page.waitForTimeout(300);
  check((await st()).seats === 5, 'Curator places a new seat by clicking the floor');
  await page.screenshot({ path: out + '3-curating.png' });
  check(errors.length === 0, `no page errors${errors.length ? ': ' + errors.join(' | ') : ''}`);
} finally { await browser.close(); server.kill(); }
if (fails.length) { console.error(`${fails.length} check(s) failed`); process.exit(1); }
console.log('all smoke checks passed'); process.exit(0);

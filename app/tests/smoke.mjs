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
// In GitHub Actions, failures become annotations so they're readable without opening the full log.
const annotate = msg => { if (process.env.GITHUB_ACTIONS) console.log(`::error title=Smoke test::${msg.replace(/%/g, '%25').replace(/\r?\n/g, '%0A')}`); };
// Screenshots are for humans; a slow software-GL frame shouldn't fail the run.
const shot = (page, name) => page.screenshot({ path: out + name, timeout: 20000 }).catch(e => console.log(`(screenshot ${name} skipped: ${e.message.split('\n')[0]})`));
// The full Chromium build (not the stripped headless shell), which renders WebGL fast enough under SwiftShader.
const browser = await chromium.launch({ ...(process.env.CHROME ? { executablePath: process.env.CHROME } : { channel: 'chromium' }), args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const errors = [], consoleTail = [];
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 760 } });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { consoleTail.push(`${m.type()}: ${m.text()}`); if (consoleTail.length > 30) consoleTail.shift(); });
  await page.goto('http://localhost:4319/?debug&room=demo-study-room');   // the demo Room has known seats
  await page.waitForFunction(() => document.body.innerText.includes('M splats'), null, { timeout: 90000 });
  const st = () => page.evaluate(() => { const s = window.__commons.getState(); return { me: s.me, seats: s.layout.seats.length }; });
  check((await st()).me.seatId === null, 'Room loads with the scan, standing');
  await page.waitForTimeout(1500); await shot(page, '1-room.png');

  await page.evaluate(() => window.__commons.getState().setMe({ x: -0.6, z: 1.45, yaw: 0 }));
  await page.keyboard.press('e'); await page.waitForTimeout(300);
  check((await st()).me.seatId === 'seat-1', 'E sits in the nearest seat');
  await page.keyboard.press('l'); await page.waitForTimeout(800);
  check((await st()).me.working === true, 'L opens the Laptop (Desk Mode)');
  await shot(page, '2-seated-working.png');
  await page.keyboard.press('e'); await page.waitForTimeout(300);
  const after = await st();
  check(after.me.seatId === null && after.me.working === false, 'E stands up and closes the Laptop');

  await page.getByText('Curate Room').click();
  await page.getByText('＋ Seat').click();
  await page.mouse.click(640, 700); await page.waitForTimeout(300);
  check((await st()).seats === 5, 'Curator places a new seat by clicking the floor');
  await shot(page, '3-curating.png');
  // The real scanned Room opens by default: it loads, you start on its floor, and you can take its seat.
  await page.goto('http://localhost:4319/?debug');
  await page.waitForFunction(() => document.body.innerText.includes('M splats'), null, { timeout: 120000 });
  const real = await page.evaluate(() => { const s = window.__commons.getState(); return { room: s.room.id, seats: s.layout.seats.map(x => x.id), me: s.me }; });
  check(real.room === 'psu-first-scan', 'the real scanned Room opens by default');
  await page.evaluate(() => { const st = window.__commons.getState(), seat = st.layout.seats[0]; st.setMe({ x: seat.x + 0.5, z: seat.z }); });
  await page.keyboard.press('e'); await page.waitForTimeout(300);
  check((await st()).me.seatId === real.seats[0], 'you can sit in the real Room\'s chair');
  await shot(page, '4-real-room.png');
  check(errors.length === 0, `no page errors${errors.length ? ': ' + errors.join(' | ') : ''}`);
} catch (e) {
  fails.push(e.message.split('\n')[0]);
  console.error(e);
} finally { await browser.close(); server.kill(); }
if (fails.length) {
  annotate(`${fails.length} check(s) failed:\n${fails.join('\n')}\n\npage errors: ${errors.join(' | ') || 'none'}\n\nlast console lines:\n${consoleTail.join('\n')}`);
  console.error(`${fails.length} check(s) failed`); process.exit(1);
}
console.log('all smoke checks passed'); process.exit(0);

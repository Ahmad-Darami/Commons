// Usage: node capture.js <outDir> [fps] [comma-separated still times]
// Steps the page's clock frame-by-frame so the WebGL scene renders smoothly regardless of machine speed.
const { chromium } = require(process.env.PW || 'playwright');
const fs = require('fs'), path = require('path');
const [outDir, fpsArg, stillsArg] = process.argv.slice(2);
const FPS = +fpsArg || 30, DURATION = 60;
const stills = stillsArg ? stillsArg.split(',').map(Number) : null;
const root = path.resolve(__dirname, '..');
const vendor = process.env.THREE_DIR; // optional local copy of three@0.128.0 (for offline rendering)

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROME, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required'] });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
  await ctx.route('**/*', r => {
    const u = r.request().url();
    if (u.startsWith('https://commons.test/')) return r.fulfill({ contentType: 'text/html', body: fs.readFileSync(path.join(root, 'prototype', 'index.html')) });
    if (vendor && u.includes('three.min.js')) return r.fulfill({ contentType: 'application/javascript', body: fs.readFileSync(path.join(vendor, 'build/three.min.js')) });
    if (vendor && u.includes('GLTFLoader.js')) return r.fulfill({ contentType: 'application/javascript', body: fs.readFileSync(path.join(vendor, 'examples/js/loaders/GLTFLoader.js')) });
    return vendor ? r.abort() : r.continue();
  });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.error('pageerror:', e.message));
  await page.clock.install({ time: new Date('2026-10-23T19:00:00') });
  await page.addInitScript(() => { let s = 7; Math.random = () => ((s = Math.imul(s ^ (s >>> 15), 0x2c1b3c6d) + 0x9e3779b9 | 0) >>> 0) / 4294967296; });
  await page.goto('https://commons.test/', { waitUntil: 'load' });
  await page.clock.pauseAt(new Date('2026-10-23T19:00:30'));   // freeze time; we advance it frame by frame
  await page.clock.runFor(500);
  await page.addScriptTag({ content: fs.readFileSync(path.join(__dirname, 'director.js'), 'utf8') });
  // render only when we're about to capture a frame (the page's own loop would draw on every 16 ms tick)
  await page.evaluate(() => { const real = renderer.render.bind(renderer); window.__render = () => real(scene, camera); renderer.render = () => {}; renderer.setPixelRatio(+(new URLSearchParams(location.search).get('pr') || 1)); resize(); });

  const total = DURATION * FPS; let elapsed = 0; const t0 = Date.now();
  for (let f = 0; f < total; f++) {
    const t = f / FPS;
    await page.evaluate(t => window.__director(t), t);
    const target = Math.round((f + 1) * 1000 / FPS);
    await page.clock.runFor(target - elapsed); elapsed = target;
    const want = stills ? stills.some(s => Math.abs(s - t) < 0.5 / FPS) : true;
    if (want) await page.evaluate(() => window.__render());
    if (want) await page.screenshot({ path: path.join(outDir, stills ? `still_${t.toFixed(1)}.jpg` : `f${String(f).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 92 });
    if (f % 150 === 0) console.log(`frame ${f}/${total}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  await browser.close();
})();

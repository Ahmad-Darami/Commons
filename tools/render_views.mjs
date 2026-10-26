#!/usr/bin/env node
// Render a Room's Appearance from standard viewpoints inside the room, as one labelled contact sheet,
// so a Room Curator can see what Students will see without opening the app.
//
//   node tools/render_views.mjs <appearance.spz> <layout.json> <out.png> [--size 800x450] [--app-dir DIR] [--dry-run]
//
// Every viewpoint comes from the Layout (bounds, height, seats), so it works for any Room. --dry-run prints the
// viewpoints as JSON without starting a browser. Rendering uses Spark in headless Chromium with software WebGL,
// which is slow: expect roughly 10–90 s per view for about 850 k splats at 800×450, depending on the machine's load.
import { createRequire } from 'node:module';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STANDING = 1.6, SEATED = 1.12;   // eye heights in metres; the same ones the scanning guide asks Scans to cover
const FOV = 70;                          // vertical field of view, matching the app's camera

function parseArgs(argv) {
  const pos = [], opt = { size: '800x450', appDir: null, dryRun: false, frameTimeout: 600 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--size') opt.size = argv[++i];
    else if (a === '--app-dir') opt.appDir = argv[++i];
    else if (a === '--frame-timeout') opt.frameTimeout = Number(argv[++i]);
    else if (a === '--dry-run') opt.dryRun = true;
    else if (a === '-h' || a === '--help') { console.log(readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(1, 9).join('\n').replace(/^\/\/ ?/gm, '')); process.exit(0); }
    else pos.push(a);
  }
  if (pos.length !== 3) { console.error('usage: node tools/render_views.mjs <appearance.spz> <layout.json> <out.png> [--size 800x450] [--app-dir DIR] [--dry-run]'); process.exit(2); }
  const m = /^(\d+)x(\d+)$/.exec(opt.size);
  if (!m) { console.error(`--size must look like 800x450, got ${opt.size}`); process.exit(2); }
  return { spz: pos[0], layoutPath: pos[1], out: pos[2], width: +m[1], height: +m[2], ...opt };
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const r2 = v => Math.round(v * 100) / 100;

/** Standard viewpoints from the Layout. Each is { label, eye: [x,y,z], target: [x,y,z] } in metres, +y up. */
export function viewpoints(layout) {
  const b = layout.bounds, H = layout.height || 2.7;
  const cx = (b.min_x + b.max_x) / 2, cz = (b.min_z + b.max_z) / 2;
  const w = b.max_x - b.min_x, d = b.max_z - b.min_z;
  // Stand a little in from the opposite wall, so the wall we look at fills the frame with its neighbours at the edges.
  const ix = clamp(0.15 * w, 0.25, 0.6), iz = clamp(0.15 * d, 0.25, 0.6);
  // In a low or badly measured room keep the eye below the top of the scan, or the view starts above the Room.
  const stand = Math.min(STANDING, Math.max(0.5, H - 0.15)), sit = Math.min(SEATED, Math.max(0.4, H - 0.3));
  const look = Math.min(1.25, stand - 0.2);   // a slight downward look, like a person scanning a wall
  const views = [
    { label: `Standing ${r2(stand)} m, toward the front wall (−z)`, eye: [cx, stand, b.max_z - iz], target: [cx, look, b.min_z] },
    { label: `Standing ${r2(stand)} m, toward the right wall (+x)`, eye: [b.min_x + ix, stand, cz], target: [b.max_x, look, cz] },
    { label: `Standing ${r2(stand)} m, toward the back wall (+z)`, eye: [cx, stand, b.min_z + iz], target: [cx, look, b.max_z] },
    { label: `Standing ${r2(stand)} m, toward the left wall (−x)`, eye: [b.max_x - ix, stand, cz], target: [b.min_x, look, cz] },
    { label: `Seated ${r2(sit)} m, corner toward the room's centre`, eye: [b.min_x + ix, sit, b.max_z - iz], target: [cx, 0.9 * sit, cz] },
  ];
  const seat = (layout.seats || [])[0];
  if (seat) {
    // forward = (−sin yaw, −cos yaw), the app's convention
    const f = [-Math.sin(seat.facing), -Math.cos(seat.facing)];
    views.push({ label: `Seat "${seat.id}", seated ${r2(sit)} m`, eye: [seat.x, sit, seat.z], target: [seat.x + 2 * f[0], sit - 0.3, seat.z + 2 * f[1]] });
  } else {
    views.push({ label: `Seated ${r2(sit)} m, opposite corner toward the centre`, eye: [b.max_x - ix, sit, b.min_z + iz], target: [cx, 0.9 * sit, cz] });
  }
  return views.map(v => ({ ...v, eye: v.eye.map(r2), target: v.target.map(r2) }));
}

/** Find a folder whose node_modules has playwright, three and Spark: --app-dir, the app next to this script, then the main checkout. */
function resolveModules(appDir) {
  const candidates = appDir ? [appDir] : [path.resolve(HERE, '..', 'app'), '/home/user/commons/app'];
  const tried = [];
  for (const dir of candidates) {
    try {
      const req = createRequire(path.join(path.resolve(dir), 'package.json'));
      const threeRoot = path.resolve(path.dirname(req.resolve('three')), '..');
      const sparkDist = path.dirname(req.resolve('@sparkjsdev/spark'));
      const playwright = req.resolve('playwright');
      const files = { three: path.join(threeRoot, 'build', 'three.module.js'), threeCore: path.join(threeRoot, 'build', 'three.core.js'),
        addons: path.join(threeRoot, 'examples', 'jsm'), spark: path.join(sparkDist, 'spark.module.js') };
      if (Object.values(files).every(existsSync)) return { dir, playwright, ...files, require: req };
      tried.push(`${dir} (missing files)`);
    } catch (e) { tried.push(`${dir} (${e.code || e.message.split('\n')[0]})`); }
  }
  throw new Error(`can't find playwright, three and @sparkjsdev/spark. Tried: ${tried.join('; ')}. Run "npm ci" in app/ or pass --app-dir.`);
}

const ORIGIN = 'https://render.commons.test/';   // never reaches the network: page.route answers everything

const PAGE = (W, H) => `<!doctype html><html><head><meta charset="utf-8">
<script type="importmap">{"imports":{"three":"${ORIGIN}three.module.js","three/addons/":"${ORIGIN}addons/","@sparkjsdev/spark":"${ORIGIN}spark.module.js"}}</script>
</head><body style="margin:0;background:#111">
<script type="module">
import * as THREE from 'three';
import { SparkRenderer, SplatMesh } from '@sparkjsdev/spark';
try {
  // preserveDrawingBuffer so the canvas can be read back after an explicit render, without a second (slow) frame
  const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1); renderer.setSize(${W}, ${H}); document.body.appendChild(renderer.domElement);
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x14161c);
  // Spark 2.4 renders black without its own renderer in the scene. autoUpdate off: we drive each sort ourselves,
  // so a frame is only captured once its splats are sorted for that camera.
  const spark = new SparkRenderer({ renderer, autoUpdate: false });
  scene.add(spark);
  const camera = new THREE.PerspectiveCamera(${FOV}, ${W} / ${H}, 0.05, 200);
  // Files from clean_scan.py are already upright (+y up), so no quaternion flip.
  const mesh = new SplatMesh({ url: '${ORIGIN}room.spz' });
  scene.add(mesh);
  await mesh.initialized;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  window.__render = async (eye, target) => {
    camera.position.set(...eye); camera.lookAt(...target); camera.updateMatrixWorld(true);
    await spark.update({ scene, camera });
    while (spark.sorting || spark.sortDirty || spark.sortTimeoutId !== undefined) await sleep(50);
    renderer.render(scene, camera);
    return renderer.domElement.toDataURL('image/png');
  };
  window.__splats = mesh.packedSplats?.numSplats ?? null;
  window.__ready = true;
} catch (e) { window.__error = String(e && e.stack || e); }
</script></body></html>`;

// The contact sheet is drawn in the page with a 2D canvas, so this script needs no image library of its own.
async function contactSheet(page, frames, { W, H, title, subtitle }) {
  return page.evaluate(async ({ frames, W, H, title, subtitle }) => {
    const cols = frames.length > 4 ? 3 : 2, rows = Math.ceil(frames.length / cols);
    const gap = 12, cap = 42, head = 64;
    const c = document.createElement('canvas');
    c.width = cols * W + (cols + 1) * gap; c.height = head + rows * (H + cap + gap) + gap;
    const g = c.getContext('2d');
    g.fillStyle = '#0d0f14'; g.fillRect(0, 0, c.width, c.height);
    g.fillStyle = '#f0f0f0'; g.font = 'bold 22px sans-serif'; g.fillText(title, gap, 30);
    g.fillStyle = '#a8adb8'; g.font = '15px sans-serif'; g.fillText(subtitle, gap, 52);
    for (let i = 0; i < frames.length; i++) {
      const x = gap + (i % cols) * (W + gap), y = head + Math.floor(i / cols) * (H + cap + gap);
      const img = new Image(); img.src = frames[i].png; await img.decode();
      g.drawImage(img, x, y + cap, W, H);
      g.fillStyle = '#f0f0f0'; g.font = 'bold 15px sans-serif'; g.fillText(`${i + 1}. ${frames[i].label}`, x, y + 16, W);
      g.fillStyle = '#7c8290'; g.font = '12px sans-serif';
      g.fillText(`eye (${frames[i].eye.join(', ')}) looking at (${frames[i].target.join(', ')}) · rendered in ${frames[i].seconds}s`, x, y + 34, W);
    }
    return c.toDataURL('image/png');
  }, { frames, W, H, title, subtitle });
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  const layout = JSON.parse(readFileSync(a.layoutPath, 'utf8'));
  const views = viewpoints(layout);
  if (a.dryRun) { console.log(JSON.stringify(views, null, 2)); return; }
  if (!existsSync(a.spz)) throw new Error(`no such file: ${a.spz}`);
  const mods = resolveModules(a.appDir);
  const { chromium } = mods.require(mods.playwright);
  const t0 = Date.now();
  const log = msg => console.log(`[${((Date.now() - t0) / 1000).toFixed(0).padStart(4)}s] ${msg}`);
  log(`modules from ${mods.dir}; ${views.length} views at ${a.width}×${a.height}`);

  const serve = {
    [ORIGIN]: ['text/html', () => PAGE(a.width, a.height)],
    [`${ORIGIN}three.module.js`]: ['application/javascript', () => readFileSync(mods.three)],
    [`${ORIGIN}three.core.js`]: ['application/javascript', () => readFileSync(mods.threeCore)],   // three.module.js imports it
    [`${ORIGIN}spark.module.js`]: ['application/javascript', () => readFileSync(mods.spark)],
    [`${ORIGIN}room.spz`]: ['application/octet-stream', () => readFileSync(a.spz)],
  };
  // The full Chromium build, not the headless shell: under SwiftShader it is the one that renders WebGL reliably.
  const browser = await chromium.launch({ channel: 'chromium', args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: a.width, height: a.height } });
    page.setDefaultTimeout(a.frameTimeout * 1000);
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.route('**/*', route => {
      const url = route.request().url();
      if (serve[url]) return route.fulfill({ contentType: serve[url][0], body: serve[url][1]() });
      if (url.startsWith(`${ORIGIN}addons/`)) {   // Spark imports three/addons/…
        const file = path.join(mods.addons, decodeURIComponent(url.slice(`${ORIGIN}addons/`.length)));
        if (file.startsWith(mods.addons) && existsSync(file)) return route.fulfill({ contentType: 'application/javascript', body: readFileSync(file) });
      }
      return route.abort();
    });
    await page.goto(ORIGIN);
    await page.waitForFunction(() => window.__ready || window.__error, null, { timeout: 300_000 });
    const err = await page.evaluate(() => window.__error);
    if (err) throw new Error(`page failed to load the splats: ${err}`);
    const splats = await page.evaluate(() => window.__splats);
    log(`loaded ${splats ? splats.toLocaleString('en-US') : '?'} splats`);

    // One page, one camera moved between frames: loading and decoding the splats again per view would double the time.
    const frames = [];
    for (const [i, v] of views.entries()) {
      const s = Date.now();
      const png = await page.evaluate(([eye, target]) => window.__render(eye, target), [v.eye, v.target]);
      frames.push({ ...v, png, seconds: Math.round((Date.now() - s) / 1000) });
      log(`view ${i + 1}/${views.length} done in ${frames.at(-1).seconds}s: ${v.label}`);
    }
    const b = layout.bounds;
    const sheet = await contactSheet(page, frames, {
      W: a.width, H: a.height,
      title: `Scan views: ${path.basename(a.spz)}`,
      subtitle: `Room ${(b.max_x - b.min_x).toFixed(2)} × ${(b.max_z - b.min_z).toFixed(2)} m, ${Number(layout.height).toFixed(2)} m tall · ${splats ? splats.toLocaleString('en-US') + ' splats · ' : ''}`
        + `eye heights ${STANDING} m standing, ${SEATED} m seated · front = −z`,
    });
    mkdirSync(path.dirname(path.resolve(a.out)), { recursive: true });
    writeFileSync(a.out, Buffer.from(sheet.split(',')[1], 'base64'));
    log(`wrote ${a.out}`);
    if (errors.length) console.warn(`page reported ${errors.length} error(s):\n  ${errors.slice(0, 5).join('\n  ')}`);
  } finally { await browser.close(); }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(e => { console.error(e.message || e); process.exit(1); });
}

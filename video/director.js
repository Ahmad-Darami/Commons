// Injected into the prototype page. window.__director(t) poses the scene for time t (seconds).
(() => {
  const realToast = toast;
  toast = () => {};                       // the video shows its own captions
  window.__toast = realToast;

  const css = `
  body.vid #bar, body.vid #prompt, body.vid #toasts .toast:not(.vidtoast){display:none!important}
  body.vid #wbStage{margin-bottom:126px}
  body.vid #viewer{top:96px;left:24px;bottom:auto;width:600px}
  .cap{position:fixed;left:50%;bottom:34px;transform:translateX(-50%);width:min(820px,calc(100vw - 48px));z-index:90;
       padding:18px 26px 20px;border-radius:18px;background:rgba(12,14,19,.84);backdrop-filter:blur(16px);
       border:1px solid rgba(255,255,255,.12);box-shadow:0 20px 50px rgba(0,0,0,.45);opacity:0;pointer-events:none}
  .cap .kick{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#6aa8ff;font-weight:700;margin-bottom:4px}
  .cap .h{font-size:27px;font-weight:720;letter-spacing:-.015em;line-height:1.2;color:#fff}
  .cap .s{font-size:15.5px;color:#b8bfcd;margin-top:6px;line-height:1.45}
  .card{position:fixed;inset:0;z-index:95;display:flex;flex-direction:column;justify-content:center;padding:0 9vw;opacity:0;pointer-events:none;
        background:linear-gradient(100deg,rgba(9,11,16,.92) 0%,rgba(9,11,16,.72) 55%,rgba(9,11,16,.35) 100%)}
  .card .logo{font-size:84px;font-weight:780;letter-spacing:-.035em;color:#fff;line-height:1}
  .card .logo span{color:#6aa8ff}
  .card .tag{font-size:30px;color:#d6dbe6;margin-top:14px;font-weight:500;letter-spacing:-.01em}
  .card .kick{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:#6aa8ff;font-weight:700;margin-bottom:14px}
  .card .big{font-size:52px;font-weight:740;letter-spacing:-.03em;color:#fff;line-height:1.1;max-width:900px}
  .card .sub{font-size:21px;color:#b8bfcd;margin-top:18px;max-width:760px;line-height:1.45}
  .card .chips{display:flex;gap:10px;margin-top:30px;flex-wrap:wrap}
  .card .chips span{padding:9px 16px;border-radius:999px;border:1px solid rgba(106,168,255,.45);background:rgba(106,168,255,.12);color:#dce8ff;font-size:16px;font-weight:600}
  .card .foot{position:absolute;left:9vw;bottom:42px;font-size:14px;color:#8a93a6}
  #scanPill{position:fixed;top:26px;left:50%;transform:translateX(-50%);z-index:90;opacity:0;padding:10px 18px 12px;border-radius:14px;
       background:rgba(12,14,19,.84);border:1px solid rgba(106,168,255,.4);color:#dce8ff;font-size:15px;font-weight:600;min-width:330px}
  #scanPill .bar{height:4px;border-radius:2px;background:rgba(255,255,255,.1);margin-top:8px;overflow:hidden}
  #scanPill .bar i{display:block;height:100%;background:#6aa8ff;width:0}
  #fcur{position:fixed;z-index:9999;width:26px;height:26px;pointer-events:none;opacity:0;filter:drop-shadow(0 2px 3px rgba(0,0,0,.4))}
  .vidtoast{animation:none!important}
  `;
  document.head.insertAdjacentHTML('beforeend', `<style>${css}</style>`);
  document.body.classList.add('vid');
  document.body.insertAdjacentHTML('beforeend', `
    <div class="card" id="cTitle"><div class="logo">Commons<span>.</span></div><div class="tag">The campus, in your browser.</div></div>
    <div class="card" id="cProblem"><div class="kick">The problem</div><div class="big">Online learning has nowhere to be.</div>
      <div class="sub">Video grids and discussion forums don't let you study next to someone, ask a quick question, or think out loud together.</div></div>
    <div class="card" id="cEnd" style="background:radial-gradient(1100px 620px at 18% 42%,#172540,#0a0c11)">
      <div class="logo">Commons<span>.</span></div><div class="tag">Online learning with somewhere to be.</div>
      <div class="chips"><span>Scan any real space</span><span>Join from any browser</span><span>Talk by proximity</span><span>One shared whiteboard</span></div>
      <div class="foot">Working browser prototype</div></div>
    <div id="scanPill"><span id="scanTxt"></span><div class="bar"><i id="scanBar"></i></div></div>
    <div class="cap" id="cap"><div class="kick"></div><div class="h"></div><div class="s"></div></div>
    <svg id="fcur" viewBox="0 0 24 24"><path d="M4 2l15 11-6.5 1.2L16 21l-3 1.3-3.4-6.8L4 19z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>`);

  const CAPS = [
    [11.4, 19,   '01 · Capture', 'Scan a real study space with your phone.', 'LiDAR on iPhone, or a simple video walk-through on any phone, becomes a shared 3D room.'],
    [19.4, 27,   '02 · Join', 'Walk in from any browser. Take a seat.', 'No headset and nothing to install. Sitting down puts you at a table with the people next to you.'],
    [27.4, 35,   '03 · Talk', 'Proximity voice: hear the people near you.', 'Your table becomes your audio bubble. Voices across the room fade out, just like in a real library.'],
    [35.6, 46,   '04 · Collaborate', 'One whiteboard for everything.', 'Notes, links, files and your Claude or ChatGPT chats, pinned where the whole group can see them.'],
    [46.4, 53,   '05 · Share', 'Share your screen, with permission.', 'Classmates ask to view and you approve each one, or you can pin your screen to the board for everyone.'],
  ];
  const ease = x => x < 0 ? 0 : x > 1 ? 1 : x * x * (3 - 2 * x);
  const fade = (t, a, b, fi = .5, fo = .45) => Math.min(ease((t - a) / fi), ease((b - t) / fo));
  const lerp = (a, b, k) => a + (b - a) * k;
  function track(t, keys) {           // keys: [[t, ...values]], smooth interpolation
    if (t <= keys[0][0]) return keys[0].slice(1);
    for (let i = 0; i < keys.length - 1; i++) {
      const [ta, ...va] = keys[i], [tb, ...vb] = keys[i + 1];
      if (t <= tb) { const k = ease((t - ta) / (tb - ta)); return va.map((v, j) => lerp(v, vb[j], k)); }
    }
    return keys[keys.length - 1].slice(1);
  }
  const once = new Set();
  const at = (t, when, key, fn) => { if (t >= when && !once.has(key)) { once.add(key); fn(); } };
  const born = new Map();
  const hud = ['#roomCard', '#side'];
  const SAM = { id: 'u-sam', name: 'Sam', color: '#ffb648', x: -3.75, z: 1.75, yaw: 0, seat: 'A0', speaking: false, sharing: false };

  // clean board for the live additions
  items.delete('seed-ai2'); ['seed-s1', 'seed-s2', 'seed-s3'].forEach(id => strokes.delete(id)); boardDirty = true;
  $('#join').classList.add('hidden');
  hud.forEach(s => $(s).style.opacity = 0);

  // "scan in progress": wireframe ahead of the scan line, the solid room behind it
  let scan = null;
  function setupScan() {
    renderer.localClippingEnabled = true;
    const solid = new THREE.Plane(new THREE.Vector3(-1, 0, 0), -7.5), wire = new THREE.Plane(new THREE.Vector3(1, 0, 0), 7.5);
    const clipped = new Set();
    scene.updateMatrixWorld(true);
    scene.traverse(o => { if ((o.isMesh || o.isSprite) && o !== sweep && o !== hearRing) [].concat(o.material).forEach(m => clipped.add(m)); });
    clipped.forEach(m => { m.clippingPlanes = [solid]; m.needsUpdate = true; });
    const lineMat = new THREE.LineBasicMaterial({ color: 0x8fc2ff, transparent: true, opacity: .8, clippingPlanes: [wire] });
    const wires = new THREE.Group();
    [demoRoom, boardGroup, ...bots.map(b => b.av.group)].forEach(g => g.traverse(o => {
      if (!o.isMesh || o.material.opacity === 0 || (o.material.transparent && o.material.opacity < .05)) return;
      const l = new THREE.LineSegments(new THREE.EdgesGeometry(o.geometry, 25), lineMat); l.matrixAutoUpdate = false; l.matrix.copy(o.matrixWorld); wires.add(l);
    }));
    const grid = new THREE.GridHelper(14, 28, 0x6aa8ff, 0x2f4a75); grid.scale.z = 10 / 14; grid.position.y = 0.01;
    grid.material.clippingPlanes = [wire]; grid.material.transparent = true; grid.material.opacity = .55; wires.add(grid);
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(10.5, 3.6), new THREE.MeshBasicMaterial({ color: 0x8fc2ff, transparent: true, opacity: .22, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }));
    plane.rotation.y = Math.PI / 2; plane.position.y = 1.6; wires.add(plane);
    scene.add(wires);
    scan = { solid, wire, clipped, wires, plane };
  }
  function setScanX(X) { scan.solid.constant = X; scan.wire.constant = -X; scan.plane.position.x = X; }
  function endScan() { scan.clipped.forEach(m => { m.clippingPlanes = null; m.needsUpdate = true; }); scene.remove(scan.wires); renderer.localClippingEnabled = false; scan = null; }

  window.__director = t => {
    // title + problem cards over the slow orbit
    $('#cTitle').style.opacity = fade(t, -1, 5.2, .5, .6);
    $('#cProblem').style.opacity = fade(t, 5.4, 11.2, .6, .6);
    $('#cEnd').style.opacity = ease((t - 53.3) / .9);

    // captions
    const cap = CAPS.find(c => t >= c[0] - .1 && t <= c[1] + .1);
    const el = $('#cap');
    if (cap) {
      if (el.dataset.k !== cap[2]) { el.dataset.k = cap[2]; el.querySelector('.kick').textContent = cap[2]; el.querySelector('.h').textContent = cap[3]; el.querySelector('.s').textContent = cap[4]; }
      el.style.opacity = fade(t, cap[0], cap[1]);
      el.style.transform = `translateX(-50%) translateY(${(1 - ease((t - cap[0]) / .5)) * 14}px)`;
    } else el.style.opacity = 0;

    // join + scan sweep
    at(t, 11, 'join', () => {
      $('#nameIn').value = 'Alex'; join();
      me.x = 0; me.z = 4.35; me.yaw = 0; me.pitch = 0.02;
      for (const b of bots) b.nextTalk = 1e9;
      onState({ ...SAM });
      sweepT = 99; setupScan(); setScanX(-7.5);
    });
    if (scan) setScanX(-7.5 + 15 * ease((t - 11.9) / 6));
    at(t, 18.3, 'endscan', () => endScan());
    const pct = Math.round(100 * Math.max(0, Math.min(1, (t - 11.9) / 6)));
    $('#scanPill').style.opacity = fade(t, 11.6, 18.6, .4, .4);
    $('#scanTxt').textContent = pct < 100 ? `📱 Scanning with iPhone LiDAR · ${pct}%` : '✓ Room ready · 8 seats found';
    $('#scanBar').style.width = pct + '%';
    if (t >= 11) {
      hud.forEach(s => $(s).style.opacity = ease((t - 18.6) / .8));
      if (peers.has('u-sam')) onState({ ...SAM, speaking: SAM.speaking });
    }

    // walk to Table A and sit (seat A3, across from Maya)
    if (t >= 11 && t < 25.2) {
      const [x, z, yaw, pitch] = track(t, [
        [11, 0, 4.35, 0, .02], [18.6, 0, 4.0, -0.12, -.04],
        [21.4, -0.95, 2.2, 0.35, -.08], [23.3, -0.95, -0.8, 0.05, -.08],
        [24.6, -2.25, -0.85, 1.6, -.12], [25.2, -2.25, -0.85, 2.5, -.15]]);
      Object.assign(me, { x, z, yaw, pitch });
    }
    at(t, 25.2, 'sit', () => sit(seatById('A3')));
    if (t >= 25.2 && t < 46) {
      const [yaw, pitch] = track(t, [[25.2, 2.5, -.15], [26.6, Math.PI - 0.44, -.08], [34, Math.PI - 0.3, -.07], [46, Math.PI - 0.55, -.06]]);
      me.yaw = yaw; me.pitch = pitch;
    }

    // proximity conversation
    const maya = bots[0], jordan = bots[1];
    maya.talking = (t > 27.6 && t < 30.6) || (t > 34 && t < 35.4) ? 1 : 0;
    jordan.talking = t > 29 && t < 32.6 ? 1 : 0;
    SAM.speaking = t > 31 && t < 33.8;
    at(t, 28.1, 'c1', () => addChat({ name: 'Maya', color: maya.color, text: 'Anyone want to quiz each other on chapter 8?', g: 1, kind: 'sim' }));
    at(t, 31.4, 'c2', () => addChat({ name: 'Sam', color: SAM.color, text: 'Yes! Give me two minutes to finish this problem set.', g: 1 }));
    at(t, 29.6, 'c3', () => addChat({ name: 'Jordan', color: jordan.color, text: 'Who wants this table for the group project?', g: prox(me, jordan).g, kind: 'sim' }));

    // whiteboard
    at(t, 35.4, 'board', () => { openBoard(); setTool('select'); });
    at(t, 37, 'gpt', () => { addItem({ id: 'v-gpt', type: 'ai', source: 'ChatGPT', by: 'Jordan', x: .71, y: .43, w: .26, h: .5,
      title: 'Why is my Lab 4 loop O(n²)?', text: 'You call list.index() inside the for-loop, which scans the list on every iteration.\n\nFix: build a dict once, and then each lookup is O(1).\n\nTotal goes from O(n²) to O(n).' }); born.set('v-gpt', t); });
    const fcur = $('#fcur');
    if (t >= 38.6 && t < 41.4 && wbOpen) {
      const k = ease((t - 38.8) / 2.0), r = wbBoard.getBoundingClientRect();
      const pt = a => [.68 + Math.cos(a) * .1, .205 + Math.sin(a) * .185];
      const a0 = -2.2, a1 = a0 + Math.PI * 2.1, n = Math.max(1, Math.floor(k * 60));
      const pts = []; for (let i = 0; i <= n; i++) pts.push(pt(a0 + (a1 - a0) * i / 60));
      if (t >= 38.8) { curStroke = { id: 'v-ring', color: '#dc2626', size: 3.4, pts, by: 'Alex' }; redrawInk(); boardDirty = true; }
      const last = pts[pts.length - 1];
      fcur.style.left = (r.left + last[0] * r.width - 3) + 'px'; fcur.style.top = (r.top + last[1] * r.height - 2) + 'px';
      fcur.style.opacity = fade(t, 38.6, 41.4, .2, .3);
    } else fcur.style.opacity = 0;
    at(t, 40.9, 'ringdone', () => { strokes.set('v-ring', curStroke); curStroke = null; redrawInk(); syncItemsDOM(); boardDirty = true; });
    at(t, 41.8, 'note', () => { addItem({ id: 'v-note', type: 'note', laptop: true, by: 'Alex', x: .355, y: .3, w: .22, h: .34,
      text: 'Quiz plan for tonight\n1. Krebs inputs & outputs\n2. ETC ATP yield\n3. Ch. 8 practice Qs' }); born.set('v-note', t); });
    at(t, 43.4, 'img', () => { addItem({ id: 'v-link', type: 'link', by: 'Sam', x: .36, y: .69, w: .22, h: .15, url: 'https://www.khanacademy.org/science/biology/cellular-respiration-and-fermentation', title: 'Khan Academy: Cellular respiration' }); born.set('v-link', t); });
    for (const [id, bt] of born) {
      const e = wbItems.querySelector(`[data-id="${id}"]`); if (!e) continue;
      const k = ease((t - bt) / .35); e.style.transform = `scale(${.85 + .15 * k})`; e.style.opacity = k;
      e.style.boxShadow = t - bt < 1.6 ? `0 0 0 ${3 * (1 - ease((t - bt - .6) / 1))}px rgba(106,168,255,.9), 0 .2em .8em rgba(0,0,0,.18)` : '';
    }

    // screen share
    at(t, 46, 'closeboard', () => closeBoard());
    at(t, 46.7, 'ask', () => { const tt = window.__toast('Asked <b>Jordan</b> to view their screen. Waiting for approval…', [], 1300); tt.classList.add('vidtoast'); });
    at(t, 48.1, 'view', () => { openViewer('bot-jordan', 'Jordan'); fake.t = 13; sysChat('Jordan allowed you to view their screen.'); });
  };
})();

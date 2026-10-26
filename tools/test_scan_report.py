#!/usr/bin/env python3
"""Checks the Scan quality report on synthetic scans. Run: python tools/test_scan_report.py

A complete synthetic room must score "good"; the same room with walls, the ceiling or the top of a wall cut away,
with floor holes, or with ghost smears added must be flagged with the right verdict and advice.
"""
import copy, json, os, shutil, subprocess, sys, tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scan_report as sr   # noqa: E402

failures = []


def check(ok, what):
    print(('✓ ' if ok else '✗ ') + what)
    if not ok: failures.append(what)


def run(*args):
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    if r.returncode: print(r.stdout, r.stderr); raise SystemExit(f'failed: {args}')
    return r.stdout


def subset(g, keep):
    return {k: v[keep] for k, v in g.items()}


def report(g, layout):
    return sr.build_report('variant.ply', 'layout.json', g=g, layout=layout)


with tempfile.TemporaryDirectory() as tmp:
    # The fake room from make_test_scan.py is 6 x 4.5 x 2.8 m with a table and a whiteboard, cleaned the usual way.
    for name, flags in [('complete', ['--clean']), ('holes', ['--clean', '--holes'])]:
        run(os.path.join(HERE, 'make_test_scan.py'), os.path.join(tmp, f'{name}.ply'), *flags)
        run(os.path.join(HERE, 'clean_scan.py'), os.path.join(tmp, f'{name}.ply'), '--out-dir', os.path.join(tmp, name))
    d = os.path.join(tmp, 'complete')
    layout_path = os.path.join(d, 'complete.layout.json'); layout = json.load(open(layout_path))

    # --- the command line, on what the browser loads, with an HTML page that embeds a renders image
    from PIL import Image
    renders = os.path.join(tmp, 'views.png'); Image.new('RGB', (40, 20), (200, 30, 30)).save(renders)
    page = os.path.join(tmp, 'report.html'); js = os.path.join(tmp, 'report.json')
    out = run(os.path.join(HERE, 'scan_report.py'), os.path.join(d, 'complete.spz'), layout_path, '--raw', os.path.join(tmp, 'complete.ply'),
              '--html', page, '--renders', renders, '--json', js)
    check('Verdict: GOOD' in out, 'complete room: verdict is good')
    numbers = json.load(open(js))
    cov = numbers['coverage']
    check(all(cov[k]['real'] >= 0.95 for k in cov), f"complete room: every surface ≥ 95% covered ({ {k: round(v['real'], 2) for k, v in cov.items()} })")
    check(numbers['artifacts']['smears'] == 0 and numbers['artifact_levels']['needles'] == 'ok', 'complete room: no artifacts flagged')
    sc = numbers['scale']
    check(abs(sc['width'] - 6) < 0.2 and abs(sc['depth'] - 4.5) < 0.2 and abs(sc['height'] - 2.8) < 0.15 and sc['ceiling_measured'],
          f"complete room: measures about 6 × 4.5 × 2.8 m with a measured ceiling (got {sc['width']:.2f} × {sc['depth']:.2f} × {sc['height']:.2f})")
    check('Original Scan' in out and numbers['raw']['kept_share'] > 0.99, 'complete room: --raw reports what the cleanup kept')
    # clean_scan.py always records what it synthesized; for a complete room that's zero everywhere
    check('Synthesized (layout.json): floor 0.0 m²' in out and 'ceiling 0.0 m²' in out, 'complete room: reads an all-zero "synthesized" record as nothing filled in')
    bare_layout = os.path.join(d, 'no-synthesized.layout.json')
    json.dump({k: v for k, v in layout.items() if k != 'synthesized'}, open(bare_layout, 'w'))
    out_none = run(os.path.join(HERE, 'scan_report.py'), os.path.join(d, 'complete.spz'), bare_layout)
    check('Synthesized: layout.json records none' in out_none, 'complete room: handles a layout.json without "synthesized"')
    html = open(page, encoding='utf-8').read()
    check(html.count('data:image/png;base64,') == 2 and 'good' in html and '<script' not in html,
          'HTML page is self-contained, with the coverage map and the renders embedded')

    g = sr.load(os.path.join(d, 'complete.clean.ply'))
    b = layout['bounds']; H = layout['height']; p = g['pos']

    # --- ceiling and two walls removed, like the first real Scan
    gone = (p[:, 1] > H - 0.4) | ((p[:, 0] > b['max_x'] - 0.3) & (p[:, 1] > 0.05)) | ((p[:, 2] < b['min_z'] + 0.3) & (p[:, 1] > 0.05))
    r = report(subset(g, ~gone), layout)
    check(r['verdict'] == 'rescan recommended', f"no ceiling, two walls missing: rescan recommended (got {r['verdict']})")
    check(r['coverage']['ceiling']['real'] < 0.05 and r['coverage']['wall_+x']['real'] < 0.1 and r['coverage']['wall_-z']['real'] < 0.1,
          'no ceiling, two walls missing: those surfaces read as nearly 0%')
    check(r['coverage']['wall_-x']['real'] > 0.9 and r['coverage']['wall_+z']['real'] > 0.9, 'no ceiling, two walls missing: the other walls still read as covered')
    adv = ' '.join(r['advice'])
    check('ceiling is 0% covered' in adv and 'step 3' in adv, 'no ceiling: advice says to point the phone up (guide step 3)')
    check('right wall (+x)' in adv and 'front wall (−z)' in adv and 'floor to ceiling' in adv, 'missing walls: advice names them and says to sweep floor to ceiling')
    check(not r['scale']['ceiling_measured'] and any('not a measured ceiling' in m for _, m in r['scale']['flags']),
          "no ceiling: the report says the height isn't measured")

    # --- only the ceiling missing: usable, not a rescan
    r = report(subset(g, ~(p[:, 1] > H - 0.4)), layout)
    check(r['verdict'] == 'usable' and r['levels']['ceiling'] == 'poor', f"only the ceiling missing: usable, ceiling poor (got {r['verdict']})")

    # --- the top of one wall missing: the phone never tilted up
    r = report(subset(g, ~((p[:, 0] < b['min_x'] + 0.3) & (p[:, 1] > 1.2))), layout)
    check(any('above 1.2 m' in t and 'left wall (−x)' in t for t in r['advice']), 'upper half of a wall missing: advice says to tilt the phone up')

    # --- ghost smears floating in the room
    rng = np.random.default_rng(3); n = 800
    smear = {'pos': (rng.uniform([-1.5, 0.8, -1], [1.5, 2.2, 1], (n, 3))).astype(np.float32),
             'scale': np.sort(rng.uniform(0.08, 0.2, (n, 3)), 1).astype(np.float32), 'alpha': np.full(n, 0.9, np.float32),
             'rot': np.tile(np.array([0.1, 0, 0, 0.995], np.float32), (n, 1))}
    smear['scale_xyz'] = smear['scale'].copy()
    r = report({k: np.concatenate([g[k], smear[k]]) for k in g}, layout)
    check(r['artifact_levels']['smears'] == 'severe' and r['verdict'] == 'rescan recommended',
          f"ghost smears: flagged as severe ({r['artifacts']['smears']} smears, {r['artifacts']['smear_vs_floor']:.1f}× the floor area)")
    check(r['coverage']['ceiling']['real'] > 0.95, 'ghost smears: walls and ceiling coverage unaffected')

    # --- floor holes, filled by the cleanup: the fill is recognised and doesn't count as scanned
    hl = json.load(open(os.path.join(tmp, 'holes', 'holes.layout.json')))
    r = sr.build_report('holes.spz', 'holes.layout.json', g=sr.load(os.path.join(tmp, 'holes', 'holes.spz')), layout=hl)
    fl = r['coverage']['floor']
    check(r['synthesized_floor_splats'] > 0 and fl['any'] > 0.97, f"floor holes: the cleanup's fill is recognised ({r['synthesized_floor_splats']:,} splats)")
    check(2.4 < fl['missing_m2'] < 4.0, f"floor holes: about 3.2 m² reported as not scanned (got {fl['missing_m2']:.2f})")
    check(r['verdict'] == 'usable' and any('step 6' in t for t in r['advice']), f"floor holes: usable, with advice to scan where you stood (got {r['verdict']})")

    # --- layout.json["synthesized"], in the shapes the repair workstream might write
    for shape in ({'ceiling': 10.0}, {'ceiling': {'m2': 10.0}}, [{'surface': 'ceiling', 'area_m2': 10.0}]):
        lay = copy.deepcopy(layout); lay['synthesized'] = shape
        c = sr.coverage(sr.surface_grids(g, lay, sr.synthesized_floor_mask(g)), lay)['ceiling']
        check(abs(c['synthesized_m2'] - 10) < 1e-6 and abs(c['real'] - (c['any'] - 10 / c['area_m2'])) < 1e-6,
              f'synthesized {json.dumps(shape)}: read as 10 m² of ceiling and taken off the real share')
    lay = copy.deepcopy(layout); lay['synthesized'] = {'walls': 8.0, 'floor': 0.5}
    rec = sr.synthesized_record(lay); cv = sr.coverage(sr.surface_grids(g, lay), lay)
    check(rec['surfaces'] == {'floor': 0.5} and abs(sum(cv[k]['synthesized_m2'] for k in sr.WALLS) - 8) < 1e-6,
          'synthesized "walls" total: shared out over the four walls')

    # --- render_views.mjs picks its viewpoints from the Layout (no browser needed for --dry-run)
    if shutil.which('node'):
        def views(lay):
            lp = os.path.join(tmp, 'v.json'); json.dump(lay, open(lp, 'w'))
            r = subprocess.run(['node', os.path.join(HERE, 'render_views.mjs'), 'x.spz', lp, 'x.png', '--dry-run'], capture_output=True, text=True)
            if r.returncode: print(r.stderr); return []
            return json.loads(r.stdout)
        v = views(layout)
        inside = all(b['min_x'] <= x['eye'][0] <= b['max_x'] and b['min_z'] <= x['eye'][2] <= b['max_z'] for x in v)
        check(4 <= len(v) <= 6 and inside and {x['eye'][1] for x in v} == {1.6, 1.12}, f'render_views: {len(v)} views, all inside the room at 1.6 m and 1.12 m')
        seated = dict(layout, seats=[{'id': 'seat-a', 'x': 0.5, 'z': 1.0, 'facing': 0.0, 'tableId': None}])
        sv = views(seated)[-1]
        check('seat-a' in sv['label'] and sv['eye'] == [0.5, 1.12, 1.0] and sv['target'][2] < sv['eye'][2],
              "render_views: includes the seat's view, looking along its facing (yaw 0 looks toward −z)")
    else:
        print('· node not found: skipping render_views viewpoint checks')

if failures:
    raise SystemExit(f'{len(failures)} check(s) failed')
print('all scan report checks passed')

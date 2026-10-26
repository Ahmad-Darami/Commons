#!/usr/bin/env python3
"""End-to-end check of the scan pipeline on synthetic scans. Run: python tools/test_clean_scan.py"""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
failures = []


def check(ok, what):
    print(('✓ ' if ok else '✗ ') + what)
    if not ok: failures.append(what)


def run(*args):
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    if r.returncode: print(r.stdout, r.stderr); raise SystemExit(f'failed: {args}')
    return r.stdout


with tempfile.TemporaryDirectory() as tmp:
    fixtures = [('clean', ['--clean']), ('messy', []), ('holes', ['--holes']), ('turned', ['--yaw']),
                ('bare', ['--bare']), ('ghosts', ['--clean', '--ghosts'])]
    for name, flags in fixtures:
        run(os.path.join(HERE, 'make_test_scan.py'), os.path.join(tmp, f'{name}.ply'), *flags)
        out = run(os.path.join(HERE, 'clean_scan.py'), os.path.join(tmp, f'{name}.ply'), '--out-dir', os.path.join(tmp, name))
        kept = re.search(r'Kept ([\d,]+) of ([\d,]+)', out)
        k, n = (int(x.replace(',', '')) for x in kept.groups())
        size = [float(v) for v in re.search(r'Room footprint ([\d.]+) × ([\d.]+) m, ([\d.]+) m tall', out).groups()]
        layout = json.load(open(os.path.join(tmp, name, f'{name}.layout.json')))
        for ext in ('.spz', '.clean.ply', '.preview.png', '.layout.json'):
            check(os.path.exists(os.path.join(tmp, name, name + ext)), f'{name}: writes {ext}')
        # the fake room is 6 x 4.5 x 2.8 m, tilted 6 degrees
        check('tilted 6.0°' in out, f'{name}: finds and corrects the 6° tilt')
        check(abs(size[0] - 6) < 0.2 and abs(size[1] - 4.5) < 0.2 and abs(size[2] - 2.8) < 0.15, f'{name}: room measures about 6 × 4.5 × 2.8 m (got {size})')
        check(layout['walkable']['rows'] and '#' in ''.join(layout['walkable']['rows']), f'{name}: layout has a walkable floor map')
        syn = layout.get('synthesized', {})
        check(set(syn) == {'floor_m2', 'walls_m2', 'ceiling_m2'} and set(syn['walls_m2']) == {'-z', '+x', '+z', '-x'} and 'Synthesized: floor' in out,
              f'{name}: records and prints what was synthesized, wall by wall ({syn})')
        if name != 'bare':   # every other fixture has all 4 walls and the ceiling: repair must add nothing there
            check(sum(syn['walls_m2'].values()) == 0 and syn['ceiling_m2'] == 0, f'{name}: complete walls and ceiling get nothing added ({syn})')
        if name == 'clean':
            check(k == n, f'clean: keeps every real splat ({k} of {n})')
            check('ghosts:' not in out and 'faded' not in out, 'clean: ghost suppression leaves a clean room alone')
        if name == 'messy':
            check(0.8 * n < k < 0.95 * n, f'messy: removes junk but keeps the room ({k} of {n})')
            check('below the floor' in out and 'floaters' in out, 'messy: removes floaters and the below-floor ghost')
        if name == 'turned':
            check('turned 30.0°' in out, f'turned: squares up a room scanned at a 30° angle')
        if name == 'holes':
            m = re.search(r'filled ([\d.]+) m² of missing floor', out)
            check(bool(m) and 2.8 < float(m.group(1)) < 3.8, f'holes: fills about 3.2 m² of floor holes (got {m and m.group(1)})')
            check(abs(syn['floor_m2'] - float(m.group(1))) < 0.01, f'holes: layout records the floor it filled ({syn})')
        if name == 'bare':
            # 35.7 m² of wall and 27 m² of ceiling were left out; corners and the floor's edge really are seen
            w = syn['walls_m2']
            check(31 < sum(w.values()) < 37, f"bare: fills about 35 m² of missing walls (got {w})")
            # missing: all of +z (16.8 m²) and +x (12.6 m²), the top half of -x (6.3 m²); -z was scanned
            check(w['-z'] == 0 and 15 < w['+z'] < 17 and 11 < w['+x'] < 12.7 and 5 < w['-x'] < 6.5, f'bare: fills each wall by what it was missing ({w})')
            check(24 < syn['ceiling_m2'] < 27.5, f"bare: fills about 27 m² of missing ceiling (got {syn['ceiling_m2']})")
            check('+x wall   9' in out and '−z wall    0%' in out and 'rescan if you can' in out, 'bare: the Scan report names the missing walls and spares the scanned one')
            off = run(os.path.join(HERE, 'clean_scan.py'), os.path.join(tmp, 'bare.ply'), '--out-dir', os.path.join(tmp, 'bare-off'), '--no-fill-walls', '--no-fill-ceiling')
            syn_off = json.load(open(os.path.join(tmp, 'bare-off', 'bare.layout.json')))['synthesized']
            check(sum(syn_off['walls_m2'].values()) == 0 and syn_off['ceiling_m2'] == 0 and '+x wall   9' in off, '--no-fill-walls/--no-fill-ceiling: adds nothing but still reports what is missing')
            check(int(re.search(r'([\d,]+) in all', off).group(1).replace(',', '')) == k, 'bare: filling never removes or adds real splats')
        if name == 'ghosts':
            # 300 blobs behind the walls, 60 needles, 100 lone blobs in mid-air (see make_test_scan.py)
            got = {w: int(m.group(1).replace(',', '')) for w in ('needles', 'beyond the walls') for m in [re.search(r'([\d,]+)  ghosts: [a-z ]*' + w, out)] if m}
            check(got.get('needles') == 60 and got.get('beyond the walls') == 300, f'ghosts: removes the 60 needles and 300 blobs behind the walls (got {got})')
            check(k >= n - 460, f'ghosts: keeps every real splat ({k} of {n}, 460 ghosts)')
            sys.path.insert(0, HERE); import clean_scan as cs, numpy as np
            g = cs.load(os.path.join(tmp, name, name + '.clean.ply')); big = np.exp(g['scale']).max(1)
            shm = np.abs(g['sh']).max(1)
            check((big > 0.06).sum() > 20 and shm[big > 0.06].max() < 1e-3, 'ghosts: lone big blobs that stay lose their view-dependent colour')
            check(np.median(shm[big < 0.03]) > 0.02, 'ghosts: real splats keep their view-dependent colour')

# Rotating a splat must rotate its view-dependent colour too, or it shows rainbow shimmer.
sys.path.insert(0, HERE)
import math, numpy as np, clean_scan as cs
rng = np.random.default_rng(5); worst = 0.0
for _ in range(5):
    ax = rng.normal(size=3); ax /= np.linalg.norm(ax); th = rng.uniform(-3, 3)
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]]); R = np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K
    c = rng.normal(size=(15, 3)); d = rng.normal(size=(500, 3)); d /= np.linalg.norm(d, axis=1, keepdims=True)
    worst = max(worst, np.abs(cs.sh_basis(d, 3) @ c - cs.sh_basis(d @ R.T, 3) @ (cs.sh_rotation(R, 3) @ c)).max())
check(worst < 1e-9, f'SH rotation keeps view-dependent colour exact (max error {worst:.1e})')

if failures:
    raise SystemExit(f'{len(failures)} check(s) failed')
print('all scan pipeline checks passed')

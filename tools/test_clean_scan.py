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
    for name, flags in [('clean', ['--clean']), ('messy', []), ('holes', ['--holes'])]:
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
        if name == 'clean':
            check(k == n, f'clean: keeps every real splat ({k} of {n})')
        if name == 'messy':
            check(0.8 * n < k < 0.95 * n, f'messy: removes junk but keeps the room ({k} of {n})')
            check('below the floor' in out and 'floaters' in out, 'messy: removes floaters and the below-floor ghost')
        if name == 'holes':
            m = re.search(r'filled ([\d.]+) m² of missing floor', out)
            check(bool(m) and 2.8 < float(m.group(1)) < 3.8, f'holes: fills about 3.2 m² of floor holes (got {m and m.group(1)})')

if failures:
    raise SystemExit(f'{len(failures)} check(s) failed')
print('all scan pipeline checks passed')

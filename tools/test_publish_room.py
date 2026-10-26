#!/usr/bin/env python3
"""Checks for publish_room.py: seat and Table geometry, then a full publish of a synthetic Scan into a temporary
rooms folder. Run: python tools/test_publish_room.py"""
import json, math, os, shutil, subprocess, sys, tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import publish_room as pr

failures = []


def check(ok, what):
    print(('✓ ' if ok else '✗ ') + what)
    if not ok: failures.append(what)


def near(a, b, tol): return abs(a - b) <= tol


def angle_near(a, b, tol): return abs((a - b + math.pi) % (2 * math.pi) - math.pi) <= tol


# --- Seats face the way the editor's makeSeat() makes them face (app/src/room/geometry.ts) --------------------------
table = {'id': 'table-1', 'x': 0, 'z': 0, 'width': 2.4, 'depth': 1.0, 'height': 0.75, 'rotation': 0}
bounds = {'min_x': -3, 'max_x': 3, 'min_z': -2.25, 'max_z': 2.25}
s = pr.make_seat([table], bounds, 's', -0.6, 0.85)
check(s['tableId'] == 'table-1' and angle_near(s['facing'], 0, 1e-9), 'seat in front of a Table joins it and faces -z, like the demo Room')
s = pr.make_seat([table], bounds, 's', 0.6, -0.85)
check(angle_near(s['facing'], math.pi, 1e-9), 'seat behind a Table faces +z')
s = pr.make_seat([table], bounds, 's', -1.75, 0)
check(angle_near(s['facing'], -math.pi / 2, 1e-9) and near(-math.sin(s['facing']), 1, 1e-9), 'seat at a Table end faces along +x (forward = (-sin, -cos))')
s = pr.make_seat([table], bounds, 's', 2.2, -1.5)
check(s['tableId'] is None and angle_near(s['facing'], math.atan2(2.2, -1.5), 1e-9), 'lone seat beyond 1.2 m faces the room centre')
s = pr.make_seat([], {'min_x': -1.87, 'max_x': 1.87, 'min_z': -1.048, 'max_z': 1.048}, 's', 1.06, 0.78)
check(near(s['facing'], 0.9364, 1e-4), 'matches the facing the editor gave the green chair in psu-first-scan (0.9364)')

# --- Rectangle fitting --------------------------------------------------------------------------------------------
rng = np.random.default_rng(3)


def rect_points(n, t):
    lx, lz = (rng.random(n) - 0.5) * t['width'], (rng.random(n) - 0.5) * t['depth']
    c, s = math.cos(t['rotation']), math.sin(t['rotation'])
    return np.c_[t['x'] + lx * c + lz * s, t['z'] - lx * s + lz * c]


r = pr.fit_rect(rect_points(5000, dict(x=0.4, z=-0.3, width=2.4, depth=1.0, rotation=0)))
check(r['rotation'] == 0 and near(r['width'], 2.4, 0.03) and near(r['depth'], 1.0, 0.03) and near(r['x'], 0.4, 0.02),
      f'axis-aligned Table fits exactly, with rotation 0 (got {r["width"]:.3f} × {r["depth"]:.3f})')
r = pr.fit_rect(rect_points(5000, dict(x=-1, z=1, width=1.2, depth=0.6, rotation=0.5)))
check(near(r['rotation'], 0.5, 0.02) and near(r['width'], 1.2, 0.03) and near(r['depth'], 0.6, 0.03) and near(r['z'], 1, 0.02),
      f'rotated Table: recovers 0.5 rad, 1.2 × 0.6 m (got {r["rotation"]:.3f}, {r["width"]:.2f} × {r["depth"]:.2f})')

# --- Re-publishing keeps what a Room Curator placed, and replaces old suggestions ------------------------------------
base = {'units': 'metres', 'up': '+y', 'floor_y': 0, 'bounds': bounds, 'height': 2.8, 'appearance': 'x.spz', 'tables': [], 'seats': [],
        'boards': [], 'synthesized': {'walls_m2': 3.2}}
previous = {'tables': [dict(table, id='table-1'), dict(table, id='table-2', x=2, suggested=True)],
            'seats': [{'id': 'seat-1', 'x': -0.6, 'z': 0.85, 'facing': 0, 'tableId': 'table-1'},
                      {'id': 'seat-9', 'x': 2, 'z': 1, 'facing': 0, 'tableId': 'table-2'},
                      {'id': 'seat-2', 'x': 2.5, 'z': 1.9, 'facing': 1, 'tableId': None, 'suggested': True}],
            'boards': [{'id': 'board-1', 'x': 0, 'y': 1.5, 'z': -2.2, 'width': 2.4, 'height': 1.2, 'rotation': 0}]}
found = [dict(x=0.01, z=0.0, width=2.38, depth=1.0, height=0.75, rotation=0), dict(x=-2, z=-1.4, width=0.8, depth=0.6, height=0.7, rotation=0)]
lay, info = pr.build_layout(base, found, [(-0.62, 0.86), (0.6, 0.86)], previous)
ids = {t['id']: t for t in lay['tables']}
check(set(ids) == {'table-1', 'table-2'} and not ids['table-1'].get('suggested') and ids['table-2'].get('suggested') and ids['table-2']['x'] == -2,
      "keeps the Curator's Table, drops its old suggestion, and doesn't re-suggest a Table the Curator already has")
check([s['id'] for s in lay['seats']] == ['seat-1', 'seat-9', 'seat-2'] and lay['seats'][2]['suggested'] and lay['seats'][2]['tableId'] == 'table-1',
      'keeps confirmed seats, skips a suggestion on top of one, numbers new suggestions after them')
check(lay['boards'] == previous['boards'] and lay['synthesized'] == {'walls_m2': 3.2} and lay['appearance'] == 'appearance.spz',
      "keeps the Curator's Boards and passes clean_scan.py's unknown keys through")
check(info['relinked'] == ['seat-9'] and lay['seats'][1]['tableId'] == 'table-1' and not pr.validate_layout(lay),
      'a confirmed seat whose suggested Table is gone relinks to the nearest Table, not to a new one reusing the id')

# --- index.json ---------------------------------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    rooms = [{'id': 'psu-first-scan', 'name': 'Penn State · first real scan'}, {'id': 'demo-study-room', 'name': 'Demo'}]
    with open(os.path.join(tmp, 'index.json'), 'w', encoding='utf-8') as fh: json.dump(rooms, fh, indent=2, ensure_ascii=False)
    pr.update_index(tmp, 'new-room', 'New', False)
    pr.update_index(tmp, 'demo-study-room', 'Demo study room', True)
    text = open(os.path.join(tmp, 'index.json'), encoding='utf-8').read()
    got = json.loads(text)
    check([r['id'] for r in got] == ['demo-study-room', 'psu-first-scan', 'new-room'] and got[0]['name'] == 'Demo study room',
          'index.json: appends new Rooms, renames in place, --default moves a Room first, never drops one')
    check('Penn State · first real scan' in text and text.endswith('\n') and '\n  {\n    "id"' in text, 'index.json: UTF-8 (not \\u escapes), 2-space indent')

# --- QA tools are optional ------------------------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    for f in ('a.spz', 'layout.json', 'a.clean.ply', 'a.preview.png'): open(os.path.join(tmp, f), 'w').close()
    files = [os.path.join(tmp, f) for f in ('a.spz', 'layout.json', 'a.clean.ply', 'a.preview.png')]
    real_here = pr.HERE
    pr.HERE = os.path.join(tmp, 'no-tools'); os.makedirs(pr.HERE)
    made = pr.run_qa(os.path.join(tmp, 'qa1'), *files)
    check(made == [os.path.join(tmp, 'qa1', 'preview.png')], 'QA: skips render_views.mjs and scan_report.py gracefully when they are missing')
    pr.HERE = os.path.join(tmp, 'tools'); os.makedirs(pr.HERE)
    with open(os.path.join(pr.HERE, 'render_views.mjs'), 'w') as fh:
        fh.write("import fs from 'fs'; const [spz, layout, png] = process.argv.slice(2); fs.writeFileSync(png, 'png'); "
                 "fs.writeFileSync(png + '.args', JSON.stringify([spz, layout]));\n")
    with open(os.path.join(pr.HERE, 'scan_report.py'), 'w') as fh:
        fh.write("import json, sys\na = sys.argv[1:]\nopen(a[a.index('--html') + 1], 'w').write('<html>')\n"
                 "open(a[a.index('--html') + 1] + '.args', 'w').write(json.dumps(a))\n")
    qa = os.path.join(tmp, 'qa2'); made = pr.run_qa(qa, *files)
    pr.HERE = real_here
    if shutil.which('node'):
        rargs = json.load(open(os.path.join(qa, 'views.png.args'))) if os.path.exists(os.path.join(qa, 'views.png.args')) else None
        check(rargs == files[:2] and os.path.join(qa, 'views.png') in made, 'QA: runs node render_views.mjs <spz> <layout.json> <out.png>')
    sargs = json.load(open(os.path.join(qa, 'report.html.args'))) if os.path.exists(os.path.join(qa, 'report.html.args')) else None
    want = [files[2], files[1], '--html', os.path.join(qa, 'report.html')] + (['--renders', os.path.join(qa, 'views.png')] if shutil.which('node') else [])
    check(sargs == want and os.path.join(qa, 'report.html') in made, 'QA: runs scan_report.py <clean.ply> <layout.json> --html <report> --renders <png>')


# --- End to end on the synthetic demo Scan, with chairs and a bookcase added ----------------------------------------
def add_furniture(src, dst):
    """Add chairs, a rotated Table, a small side table and a bookcase to a make_test_scan.py room.

    They're built in the room's true frame, then tilted and shifted exactly as make_test_scan.py tilts and shifts its
    room, so clean_scan.py has to level them along with everything else.
    """
    import spz
    g = np.random.default_rng(7); parts = []

    def surf(n, f, color):
        p = f(n) + g.normal(0, 0.008, (n, 3)); parts.append((p, np.tile(color, (n, 1)) + g.normal(0, 0.03, (n, 3))))

    def top(cx, cz, w, d, y, rot=0.0):   # a flat rectangle, rotated like a Table in geometry.ts
        def f(n):
            lx, lz = (g.random(n) - 0.5) * w, (g.random(n) - 0.5) * d; c, s = math.cos(rot), math.sin(rot)
            return np.c_[cx + lx * c + lz * s, np.full(n, y), cz - lx * s + lz * c]
        return f

    def legs(cx, cz, w, d, y):
        for sx in (-1, 1):
            for sz in (-1, 1):
                surf(150, lambda n, sx=sx, sz=sz: np.c_[np.full(n, cx + sx * (w / 2 - 0.03)), g.random(n) * y, np.full(n, cz + sz * (d / 2 - 0.03))], [0.3, 0.3, 0.3])

    def chair(cx, cz, back):   # back: unit (bx, bz) from the seat centre toward its backrest
        surf(1800, top(cx, cz, 0.42, 0.42, 0.45), [0.35, 0.6, 0.3]); legs(cx, cz, 0.42, 0.42, 0.45)
        bx, bz = back
        surf(1600, lambda n: np.c_[cx + bx * 0.21 + bz * (g.random(n) - 0.5) * 0.42, 0.47 + g.random(n) * 0.43,
                                   cz + bz * 0.21 + bx * (g.random(n) - 0.5) * 0.42], [0.35, 0.6, 0.3])

    chair(0.6, 0.95, (0, 1))          # in front of the demo Table: should face it, along -z
    chair(-1.75, 0.0, (-1, 0))        # at its west end: should face +x
    chair(2.2, -1.5, (1, 0))          # alone, > 1.2 m from any Table: should face the room centre
    surf(6000, top(-2.0, -1.45, 1.0, 0.6, 0.72, math.radians(30)), [0.5, 0.4, 0.3])   # a small Table turned 30°
    surf(900, top(2.3, 1.0, 0.3, 0.3, 0.72), [0.5, 0.4, 0.3]); legs(2.3, 1.0, 0.3, 0.3, 0.72)   # too small to be a Table
    for y in (0.05, 0.47, 0.90):     # bookcase: its middle shelf is at seat height but closed in from above
        surf(2400, top(-2.78, 1.0, 0.35, 0.8, y), [0.6, 0.45, 0.3])
    for z in (0.6, 1.4):
        surf(1500, lambda n, z=z: np.c_[-2.95 + g.random(n) * 0.35, g.random(n) * 0.9, np.full(n, z)], [0.6, 0.45, 0.3])
    surf(2000, lambda n: np.c_[np.full(n, -2.95), g.random(n) * 0.9, 0.6 + g.random(n) * 0.8], [0.6, 0.45, 0.3])

    pos = np.concatenate([p for p, _ in parts]); col = np.concatenate([c for _, c in parts]); n = len(pos)
    th = math.radians(6); R = np.array([[1, 0, 0], [0, math.cos(th), -math.sin(th)], [0, math.sin(th), math.cos(th)]])
    pos = pos @ R.T + [1.3, 0.9, -2.0]                                      # make_test_scan.py's tilt and shift
    o = spz.UnpackOptions(); o.to_coord = spz.CoordinateSystem.RUB
    c = spz.load_splat_from_ply(src, o); m = c.num_points
    cat = lambda old, new: np.concatenate([np.asarray(old, np.float32).reshape(m, -1), np.asarray(new, np.float32).reshape(n, -1)]).ravel()
    c.positions = cat(c.positions, pos)
    c.scales = cat(c.scales, np.log(np.full((n, 3), 0.012) * g.uniform(0.6, 1.6, (n, 1))))
    c.rotations = cat(c.rotations, np.tile([math.sin(th / 2), 0, 0, math.cos(th / 2)], (n, 1)))
    c.alphas = cat(c.alphas, np.full(n, 2.5)); c.colors = cat(c.colors, (col - 0.5) / 0.282095)
    c.sh = cat(c.sh, g.normal(0, 0.05, (n, 9)))
    po = spz.PackOptions(); po.from_coord = spz.CoordinateSystem.RUB
    spz.save_splat_to_ply(c, po, dst)


def publish(*args):
    r = subprocess.run([sys.executable, os.path.join(HERE, 'publish_room.py'), *args], capture_output=True, text=True)
    if r.returncode: print(r.stdout, r.stderr); raise SystemExit(f'publish_room.py failed: {args}')
    return r.stdout


with tempfile.TemporaryDirectory() as tmp:
    raw = os.path.join(tmp, 'demo.ply'); scan = os.path.join(tmp, 'demo_chairs.ply')
    subprocess.run([sys.executable, os.path.join(HERE, 'make_test_scan.py'), raw, '--holes'], check=True, capture_output=True)
    add_furniture(raw, scan)
    rooms = os.path.join(tmp, 'rooms'); os.makedirs(os.path.join(rooms, 'other-room'))
    open(os.path.join(rooms, 'other-room', 'layout.json'), 'w').write('{}')
    existing = [{'id': 'psu-first-scan', 'name': 'Penn State · first real scan'}, {'id': 'other-room', 'name': 'Other'}]
    with open(os.path.join(rooms, 'index.json'), 'w', encoding='utf-8') as fh: json.dump(existing, fh, indent=2, ensure_ascii=False)

    out = publish(scan, 'test-room', 'Test room', '--rooms-dir', rooms, '--no-qa', '--clean-args', '--no-sh --max-splats 0')
    folder = os.path.join(rooms, 'test-room')
    check(sorted(os.listdir(folder)) == ['appearance.spz', 'layout.json'], 'writes exactly appearance.spz and layout.json into the Room folder')
    with open(os.path.join(folder, 'layout.json'), encoding='utf-8') as fh: lay = json.load(fh)
    errs = pr.validate_layout(lay)
    check(not errs and lay['appearance'] == 'appearance.spz' and lay.get('note') and lay['walkable']['rows'], f'layout.json is a valid Layout with appearance and note {errs}')
    check('SH degree 0' in out, '--clean-args reach clean_scan.py (--no-sh)')
    b = lay['bounds']
    check(near(b['max_x'] - b['min_x'], 6, 0.2) and near(b['max_z'] - b['min_z'], 4.5, 0.2), 'Room measures about 6 × 4.5 m')

    tables = lay['tables']
    demo = [t for t in tables if near(t['x'], 0, 0.1) and near(t['z'], 0, 0.1)]
    check(len(demo) == 1 and near(demo[0]['width'], 2.4, 0.08) and near(demo[0]['depth'], 1.0, 0.08) and near(demo[0]['height'], 0.75, 0.03)
          and demo[0]['rotation'] == 0 and demo[0].get('suggested') is True,
          f'finds the demo Table: 2.4 × 1.0 m, top at 0.75 m, at the origin, suggested (got {demo})')
    turned = [t for t in tables if near(t['x'], -2.0, 0.12) and near(t['z'], -1.45, 0.12)]
    check(len(turned) == 1 and angle_near(4 * turned[0]['rotation'], 4 * math.radians(30), 4 * math.radians(3))
          and sorted([round(turned[0]['width'], 1), round(turned[0]['depth'], 1)]) == [0.6, 1.0], f'finds the Table turned 30° (got {turned})')
    check(len(tables) == 2, f'skips the 0.3 × 0.3 m side table and the bookcase (found {len(tables)} Tables)')

    seats = lay['seats']
    def seat_at(x, z): return [s for s in seats if near(s['x'], x, 0.1) and near(s['z'], z, 0.1)]
    a, w, lone = seat_at(0.6, 0.95), seat_at(-1.75, 0), seat_at(2.2, -1.5)
    check(len(a) == 1 and a[0]['tableId'] == demo[0]['id'] and angle_near(a[0]['facing'], 0, 0.05) and a[0].get('suggested') is True,
          f'chair in front of the Table: a suggested seat that joins it and faces it (got {a})')
    check(len(w) == 1 and w[0]['tableId'] == demo[0]['id'] and angle_near(w[0]['facing'], -math.pi / 2, 0.05), f'chair at the Table end faces it (got {w})')
    cx, cz = (b['min_x'] + b['max_x']) / 2, (b['min_z'] + b['max_z']) / 2
    check(len(lone) == 1 and lone[0]['tableId'] is None and angle_near(lone[0]['facing'], pr.yaw_toward(lone[0]['x'], lone[0]['z'], cx, cz), 1e-3),
          f'lone chair faces the room centre and joins no Table (got {lone})')
    check(len(seats) == 3, f"no seat on the bookcase shelf (found {len(seats)} seats)")

    with open(os.path.join(rooms, 'index.json'), encoding='utf-8') as fh: idx = json.load(fh)
    check(idx == existing + [{'id': 'test-room', 'name': 'Test room'}], 'index.json gains the Room and keeps the existing ones')
    check(os.path.exists(os.path.join(rooms, 'other-room', 'layout.json')), 'leaves other Room folders alone')

    first = open(os.path.join(folder, 'layout.json'), 'rb').read(); spz1 = open(os.path.join(folder, 'appearance.spz'), 'rb').read()
    publish(scan, 'test-room', 'Test room', '--rooms-dir', rooms, '--no-qa', '--clean-args', '--no-sh --max-splats 0', '--default')
    with open(os.path.join(rooms, 'index.json'), encoding='utf-8') as fh: idx = json.load(fh)
    check(open(os.path.join(folder, 'layout.json'), 'rb').read() == first and open(os.path.join(folder, 'appearance.spz'), 'rb').read() == spz1,
          're-publishing the same Scan under the same id gives identical files')
    check([r['id'] for r in idx] == ['test-room', 'psu-first-scan', 'other-room'], 'no duplicate index entry; --default lists the Room first')

if failures:
    raise SystemExit(f'{len(failures)} check(s) failed')
print('all publish_room checks passed')

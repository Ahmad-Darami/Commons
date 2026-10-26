#!/usr/bin/env python3
"""Publish a phone Scan as a Room, in one command.

    python tools/publish_room.py <scan.ply|.spz> <room-id> "<Room name>"
        [--rooms-dir app/public/rooms] [--clean-args "--no-sh --max-splats 800000"]
        [--no-qa] [--qa-dir DIR] [--work-dir DIR] [--fresh] [--default]

What it does:
  1. runs tools/clean_scan.py on the Scan (into a temporary folder, or --work-dir), passing --clean-args through
  2. suggests Tables (flat surfaces 0.65-0.80 m up) and seats (chair seats 0.40-0.55 m up) from the cleaned splats,
     marked "suggested": true for the Room Curator to confirm
  3. writes <rooms-dir>/<room-id>/{appearance.spz, layout.json} and adds or updates the Room in index.json
  4. runs the QA tools (render_views.mjs, scan_report.py) if they sit next to this script
  5. prints a summary and the Curator's next steps

Re-publishing an existing Room keeps what a Room Curator already placed there (Boards, and Tables and seats without
"suggested": true) and replaces only the old suggestions. --fresh discards everything and starts over.
Needs: numpy, pillow and Niantic's spz bindings, like clean_scan.py.
"""
import argparse, glob, json, math, os, re, shlex, shutil, subprocess, sys, tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# Detection constants, in metres. The bands come from the scan-pipeline workstream brief.
CELL = 0.05                  # top-down grid; fine enough for a 0.4 m chair seat to cover ~64 cells
YBIN = 0.02                  # height histogram bin
SLAB = 3                     # bins per slab: a flat surface's splats sit within ~±3 cm of its height
CONTRAST_OFF = 0.12          # compare a slab with the slabs this far above and below it
CONTRAST = 2.5               # a flat surface is this much denser than the space on at least one side of it
TABLE_BAND = (0.65, 0.80)
SEAT_BAND = (0.40, 0.55)
MIN_TABLE = 0.38             # "about 0.4 x 0.4 m": smaller flat tops are shelves, stools or clutter
SEAT_SIZE = (0.25, 0.90)     # a single chair seat's sides
BENCH_MAX = 3.0              # longer seat-height surfaces are probably not seating at all
BENCH_SPACING = 0.6          # one seat per this much bench
SEAT_JOIN = 1.2              # a seat joins a Table within this distance (matches makeSeat() in geometry.ts)


def log(msg=''): print(msg, flush=True)


def count(n, word): return f'{n} {word}{"s" * (n != 1)}'


# ---------------------------------------------------------------------------------------------------------------------
# Seat geometry: a line-for-line port of app/src/room/geometry.ts, so suggested seats face exactly as the editor's would.

def yaw_toward(x, z, tx, tz):
    """Yaw that looks from (x, z) toward (tx, tz); forward = (-sin yaw, -cos yaw)."""
    return math.atan2(-(tx - x), -(tz - z))


def to_table_local(t, x, z):
    c, s = math.cos(t['rotation']), math.sin(t['rotation']); dx, dz = x - t['x'], z - t['z']
    return dx * c - dz * s, dx * s + dz * c


def from_table_local(t, lx, lz):
    c, s = math.cos(t['rotation']), math.sin(t['rotation'])
    return t['x'] + lx * c + lz * s, t['z'] - lx * s + lz * c


def distance_to_table(t, x, z):
    lx, lz = to_table_local(t, x, z)
    return math.hypot(max(abs(lx) - t['width'] / 2, 0), max(abs(lz) - t['depth'] / 2, 0))


def closest_point_on_table(t, x, z):
    lx, lz = to_table_local(t, x, z)
    return from_table_local(t, max(-t['width'] / 2, min(t['width'] / 2, lx)), max(-t['depth'] / 2, min(t['depth'] / 2, lz)))


def inside_table(t, x, z, pad=0.0):
    lx, lz = to_table_local(t, x, z)
    return abs(lx) <= t['width'] / 2 + pad and abs(lz) <= t['depth'] / 2 + pad


def nearest_table(tables, x, z, max_dist):
    best, bd = None, max_dist
    for t in tables:
        d = distance_to_table(t, x, z)
        if d <= bd: bd, best = d, t
    return best


def make_seat(tables, bounds, seat_id, x, z):
    """A seat at (x, z): it joins the nearest Table within reach and faces it, otherwise it faces the room's centre."""
    t = nearest_table(tables, x, z, SEAT_JOIN)
    if t:
        px, pz = closest_point_on_table(t, x, z)
        return {'id': seat_id, 'x': x, 'z': z, 'facing': yaw_toward(x, z, px, pz), 'tableId': t['id']}
    cx, cz = (bounds['min_x'] + bounds['max_x']) / 2, (bounds['min_z'] + bounds['max_z']) / 2
    return {'id': seat_id, 'x': x, 'z': z, 'facing': yaw_toward(x, z, cx, cz), 'tableId': None}


# ---------------------------------------------------------------------------------------------------------------------
# Furniture detection

def load_points(path):
    """Splat centres (RUB = three.js axes, as clean_scan.py writes them), keeping only crisp, clearly visible splats.

    Big soft splats (walls, ceilings) and faint fuzz smear surfaces vertically and would blur the height peaks.
    """
    import spz
    opts = spz.UnpackOptions(); opts.to_coord = spz.CoordinateSystem.RUB
    cloud = spz.load_splat_from_ply(path, opts) if path.lower().endswith('.ply') else spz.load_spz(path, opts)
    n = cloud.num_points
    pos = np.asarray(cloud.positions, np.float32).reshape(n, 3)
    opacity = 1 / (1 + np.exp(-np.asarray(cloud.alphas, np.float32).reshape(n)))
    size = np.exp(np.asarray(cloud.scales, np.float32).reshape(n, 3)).max(1)
    ok = np.isfinite(pos).all(1) & (opacity >= 0.2) & (size <= 0.1)
    return pos[ok], n


class Grid:
    """A top-down grid of height histograms: counts[z cell, x cell, height bin]."""

    def __init__(self, pos, bounds, y_top=1.5, margin=0.3):
        self.x0, self.z0 = bounds['min_x'] - margin, bounds['min_z'] - margin
        self.W = int(math.ceil((bounds['max_x'] + margin - self.x0) / CELL))
        self.H = int(math.ceil((bounds['max_z'] + margin - self.z0) / CELL))
        self.NY = int(math.ceil(y_top / YBIN))
        ix, iz, iy = self.cell_of(pos)
        ok = (ix >= 0) & (ix < self.W) & (iz >= 0) & (iz < self.H) & (pos[:, 1] >= 0) & (iy < self.NY)
        flat = (iz[ok] * self.W + ix[ok]) * self.NY + iy[ok]
        self.counts = np.bincount(flat, minlength=self.H * self.W * self.NY).reshape(self.H, self.W, self.NY).astype(np.int32)
        # Scan density varies a lot between phones and apps, so judge "dense" against this Scan's own floor,
        # which every Scan covers well and which is flat like a table top.
        fl = ok & (np.abs(pos[:, 1]) < SLAB * YBIN / 2)
        fc = np.bincount(iz[fl] * self.W + ix[fl], minlength=self.H * self.W)
        self.floor_ref = float(np.median(fc[fc > 0])) if (fc > 0).any() else 10.0
        self.min_count = max(4.0, 0.25 * self.floor_ref)
        c = np.concatenate([np.zeros((self.H, self.W, 1), np.int32), np.cumsum(self.counts, 2, dtype=np.int32)], 2)
        self.cum = c                                        # cum[..., k] = splats below bin k

    def cell_of(self, pos):
        return (np.floor((pos[:, 0] - self.x0) / CELL).astype(np.int64), np.floor((pos[:, 2] - self.z0) / CELL).astype(np.int64),
                np.floor(pos[:, 1] / YBIN).astype(np.int64))

    def between(self, y0, y1):
        """Splats per cell with y0 <= y < y1 (to the nearest bin)."""
        k0, k1 = (int(np.clip(round(v / YBIN), 0, self.NY)) for v in (y0, y1))
        return self.cum[..., k1] - self.cum[..., k0]

    def centre(self, iz, ix):
        return self.x0 + (ix + 0.5) * CELL, self.z0 + (iz + 0.5) * CELL


def surface_heights(grid, band):
    """Per cell, the height of a flat surface within band (NaN where there is none).

    A flat surface piles splats into a thin slab that is much denser than the space just above or below it.
    Requiring that on only one side lets a Table carry books and laptops, and a chair have legs; a wall, which is
    equally dense at every height, never passes.
    """
    off = int(round(CONTRAST_OFF / YBIN)); half = SLAB // 2
    ks = [k for k in range(grid.NY) if band[0] <= (k + 0.5) * YBIN <= band[1] and k - off - half >= 0 and k + off + half + 1 <= grid.NY]
    slab = lambda k: grid.cum[..., k + half + 1] - grid.cum[..., k - half]
    best = np.zeros((grid.H, grid.W)); h = np.full((grid.H, grid.W), np.nan)
    for k in ks:
        s = slab(k)
        ok = (s >= grid.min_count) & (s >= CONTRAST * np.minimum(slab(k - off), slab(k + off))) & (s > best)
        best[ok] = s[ok]; h[ok] = (k + 0.5) * YBIN
    return h


def _shift(a, dy, dx, fill):
    """b[i, j] = a[i + dy, j + dx], or fill off the edge."""
    b = np.full_like(a, fill); H, W = a.shape
    b[max(0, -dy):H - max(0, dy), max(0, -dx):W - max(0, dx)] = a[max(0, dy):H - max(0, -dy), max(0, dx):W - max(0, -dx)]
    return b


def label_surfaces(h, tol=0.04):
    """Connected patches of surface cells (8-neighbours), joined only where neighbouring heights agree.

    The height check keeps a chair seat from merging with the Table edge it is pushed against.
    """
    H, W = h.shape; on = ~np.isnan(h); big = H * W
    lab = np.where(on, np.arange(H * W).reshape(H, W), big)
    links = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                hs = _shift(h, dy, dx, np.nan)
                links.append((dy, dx, on & ~np.isnan(hs) & (np.abs(h - np.nan_to_num(hs)) <= tol)))
    while True:   # min-label propagation with pointer jumping, as clean_scan.components() does in 3D
        new = lab.copy()
        for dy, dx, link in links:
            new = np.where(link, np.minimum(new, _shift(lab, dy, dx, big)), new)
        flat = np.append(new.ravel(), big)
        new = np.where(on, flat[new], big)
        if np.array_equal(new, lab): break
        lab = new
    return np.where(on, lab, -1)


def fit_rect(xz, snap=0.03, q=1.0):
    """Smallest rotated rectangle around a flat patch's splats: (x, z, width, depth, rotation), in the Table frame of
    geometry.ts (width along local x; local x = (cos r, -sin r) in world x, z).

    Extents use the q and 100-q percentiles, so a stray splat can't stretch a Table, scaled back up assuming splats
    spread evenly over the surface. clean_scan.py squares the room up, so an axis-aligned fit within snap (3%) of the
    best area wins: Curators then get tidy zero rotations instead of 0.4-degree noise.
    """
    xz = np.asarray(xz, np.float64)
    if len(xz) > 20000: xz = xz[np.random.default_rng(0).choice(len(xz), 20000, replace=False)]
    m = xz.mean(0); d = xz - m

    def extents(deg):
        r = math.radians(deg); c, s = math.cos(r), math.sin(r)
        lx = d[:, 0] * c - d[:, 1] * s; lz = d[:, 0] * s + d[:, 1] * c
        lo = np.percentile(np.c_[lx, lz], q, 0); hi = np.percentile(np.c_[lx, lz], 100 - q, 0)
        return lo, hi, float(np.prod(hi - lo))

    coarse = np.arange(-45, 45, 1.0)
    deg = float(coarse[int(np.argmin([extents(a)[2] for a in coarse]))])
    fine = np.arange(deg - 1, deg + 1.001, 0.1)
    deg = float(fine[int(np.argmin([extents(a)[2] for a in fine]))])
    deg = (deg + 45) % 90 - 45
    if extents(0)[2] <= (1 + snap) * extents(deg)[2]: deg = 0.0
    lo, hi, _ = extents(deg)
    size = (hi - lo) / (1 - 2 * q / 100)
    mx, mz = (lo + hi) / 2; r = math.radians(deg); c, s = math.cos(r), math.sin(r)
    return {'x': m[0] + mx * c + mz * s, 'z': m[1] - mx * s + mz * c, 'width': float(size[0]), 'depth': float(size[1]), 'rotation': r}


def patches(grid, pos, band, min_cells):
    """Flat patches in a height band: per patch, its cells, its own splats and its surface height."""
    h = surface_heights(grid, band); lab = label_surfaces(h)
    near = pos[(pos[:, 1] >= band[0] - 0.05) & (pos[:, 1] <= band[1] + 0.05)]
    ix, iz, _ = grid.cell_of(near)
    inb = (ix >= 0) & (ix < grid.W) & (iz >= 0) & (iz < grid.H); near, ix, iz = near[inb], ix[inb], iz[inb]
    pl = lab[iz, ix]; hc = h[iz, ix]
    on = (pl >= 0) & (np.abs(near[:, 1] - np.nan_to_num(hc)) <= 0.04)
    out = []
    ids, sizes = np.unique(lab[lab >= 0], return_counts=True)
    for i, n in zip(ids, sizes):
        if n < min_cells: continue
        mine = on & (pl == i)
        if mine.sum() < 20: continue
        cz, cx = np.nonzero(lab == i)
        out.append({'cells': (cz, cx), 'pts': near[mine], 'height': float(np.median(near[mine, 1]))})
    return out


def _rect_corners(r, pad=0.0):
    t = dict(r, width=r['width'] + 2 * pad, depth=r['depth'] + 2 * pad)
    return [from_table_local(t, sx * t['width'] / 2, sz * t['depth'] / 2) for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def rects_touch(a, b, pad=0.1):
    """Separating-axis test for two rotated rectangles, each grown by pad."""
    ca, cb = _rect_corners(a, pad), _rect_corners(b, pad)
    for r in (a, b):
        for ax in ((math.cos(r['rotation']), -math.sin(r['rotation'])), (math.sin(r['rotation']), math.cos(r['rotation']))):
            pa = [x * ax[0] + z * ax[1] for x, z in ca]; pb = [x * ax[0] + z * ax[1] for x, z in cb]
            if max(pa) < min(pb) or max(pb) < min(pa): return False
    return True


def detect_tables(grid, pos):
    found = [dict(fit_rect(p['pts'][:, [0, 2]]), height=p['height'], pts=p['pts'], ncells=len(p['cells'][0]))
             for p in patches(grid, pos, TABLE_BAND, min_cells=int(0.1 / CELL ** 2))]
    # A laptop or a pile of books hides part of a table top and can split it in two: rejoin touching patches at one height.
    merged = True
    while merged:
        merged = False
        for i in range(len(found)):
            for j in range(i + 1, len(found)):
                a, b = found[i], found[j]
                if abs(a['height'] - b['height']) <= 0.04 and rects_touch(a, b):
                    pts = np.concatenate([a['pts'], b['pts']])
                    found[i] = dict(fit_rect(pts[:, [0, 2]]), height=float(np.median(pts[:, 1])), pts=pts, ncells=a['ncells'] + b['ncells'])
                    del found[j]; merged = True; break
            if merged: break
    tables = []
    for t in found:
        fill = t['ncells'] * CELL ** 2 / max(t['width'] * t['depth'], 1e-6)
        # A sparse or L-shaped patch is clutter that happens to be at table height, not a table top.
        if min(t['width'], t['depth']) >= MIN_TABLE and max(t['width'], t['depth']) <= 6.0 and fill >= 0.4:
            tables.append({k: t[k] for k in ('x', 'z', 'width', 'depth', 'height', 'rotation')})
    return tables


def detect_seat_spots(grid, pos, tables):
    """Centres of chair seats (and evenly spaced spots along benches)."""
    spots = []
    for p in patches(grid, pos, SEAT_BAND, min_cells=int(0.04 / CELL ** 2)):
        r = fit_rect(p['pts'][:, [0, 2]]); short, long = sorted((r['width'], r['depth']))
        if short < SEAT_SIZE[0] or short > SEAT_SIZE[1] or long > BENCH_MAX: continue
        # A seat has open space above it (only a backrest along one edge). A shelf inside a bookcase or a cabinet
        # doesn't: the next shelf or the top covers it. A Table top above a tucked-in chair doesn't count.
        cz, cx = p['cells']; x, z = grid.centre(cz, cx)
        above = grid.between(p['height'] + 0.12, p['height'] + 0.45)[cz, cx] >= grid.min_count
        under_table = np.array([any(inside_table(t, xi, zi, 0.05) for t in tables) for xi, zi in zip(x, z)], bool)
        if (above & ~under_table).mean() > 0.5: continue
        if any(inside_table(t, r['x'], r['z']) for t in tables): continue      # a shelf under a Table, or a chair tucked fully under
        n = 1 if long <= SEAT_SIZE[1] else max(2, int(round(long / BENCH_SPACING)))
        along_x = r['width'] >= r['depth']
        for i in range(n):
            o = (i - (n - 1) / 2) * long / n
            spots.append(from_table_local(r, o, 0) if along_x else from_table_local(r, 0, o))
    return spots


def suggest_furniture(points, bounds):
    """Suggested Tables and seat positions, in cleaned (Layout) coordinates."""
    grid = Grid(points, bounds)
    tables = detect_tables(grid, points)
    return tables, detect_seat_spots(grid, points, tables), grid


# ---------------------------------------------------------------------------------------------------------------------
# Layout and Room folder

def validate_layout(l):
    """Fail loudly before writing anything if the Layout doesn't follow app/src/room/types.ts."""
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    errs = []
    for k, ok in (('units', isinstance(l.get('units'), str)), ('up', isinstance(l.get('up'), str)), ('floor_y', num(l.get('floor_y'))),
                  ('height', num(l.get('height'))), ('appearance', isinstance(l.get('appearance'), str))):
        if not ok: errs.append(f'{k} missing or wrong type')
    b = l.get('bounds')
    if not (isinstance(b, dict) and all(num(b.get(k)) for k in ('min_x', 'max_x', 'min_z', 'max_z'))): errs.append('bounds missing or incomplete')
    for key, fields in (('tables', ('x', 'z', 'width', 'depth', 'height', 'rotation')), ('seats', ('x', 'z', 'facing')),
                        ('boards', ('x', 'y', 'z', 'width', 'height', 'rotation'))):
        items = l.get(key)
        if not isinstance(items, list): errs.append(f'{key} is not a list'); continue
        ids = [i.get('id') for i in items]
        if len(set(ids)) != len(ids) or not all(isinstance(i, str) for i in ids): errs.append(f'{key}: ids missing or repeated')
        for it in items:
            if not all(num(it.get(f)) for f in fields): errs.append(f'{key}: {it.get("id")} lacks one of {fields}')
    table_ids = {t.get('id') for t in l.get('tables', [])}
    for s in l.get('seats', []):
        if s.get('tableId') is not None and s.get('tableId') not in table_ids: errs.append(f'seat {s.get("id")} points at missing table {s.get("tableId")}')
    return errs


def next_id(prefix, used):
    i = 1
    while f'{prefix}-{i}' in used: i += 1
    used.add(f'{prefix}-{i}'); return f'{prefix}-{i}'


def build_layout(base, tables, spots, previous=None):
    """The Room's layout.json: the cleanup's starter Layout, plus suggestions, plus anything a Curator already placed.

    Keys this tool doesn't know (e.g. records of synthesized surfaces from clean_scan.py) pass through untouched.
    """
    layout = dict(base)
    layout['appearance'] = 'appearance.spz'
    kept_tables = [t for t in (previous or {}).get('tables', []) if not t.get('suggested')]
    kept_seats = [dict(s) for s in (previous or {}).get('seats', []) if not s.get('suggested')]
    boards = list((previous or {}).get('boards', []))
    t_used = {t['id'] for t in kept_tables}; s_used = {s['id'] for s in kept_seats}
    # Seats the Curator confirmed at a Table that was only ever a suggestion lose it now; find them before new
    # suggestions reuse that Table's id for something else.
    orphans = [s for s in kept_seats if s.get('tableId') is not None and s['tableId'] not in t_used]
    # Number suggestions in reading order (back to front, left to right) so re-runs give the same ids.
    new_tables = []
    for t in sorted(tables, key=lambda t: (round(t['z'], 1), t['x'])):
        if any(rects_touch(t, k, 0.0) for k in kept_tables): continue          # the Curator already has this one
        new_tables.append({'id': next_id('table', t_used), 'x': round(t['x'], 3), 'z': round(t['z'], 3), 'width': round(t['width'], 3),
                           'depth': round(t['depth'], 3), 'height': round(t['height'], 3), 'rotation': round(t['rotation'], 4), 'suggested': True})
    all_tables = kept_tables + new_tables
    relinked = []
    for s in orphans:
        t = nearest_table(all_tables, s['x'], s['z'], SEAT_JOIN)
        s['tableId'] = t['id'] if t else None; relinked.append(s['id'])
    new_seats = []
    for x, z in sorted(spots, key=lambda p: (round(p[1], 1), p[0])):
        if any(math.hypot(s['x'] - x, s['z'] - z) < 0.45 for s in kept_seats): continue
        s = make_seat(all_tables, layout['bounds'], next_id('seat', s_used), round(x, 3), round(z, 3))
        s['facing'] = round(s['facing'], 4); s['suggested'] = True; new_seats.append(s)
    layout['tables'] = all_tables; layout['seats'] = kept_seats + new_seats; layout['boards'] = boards
    return layout, {'kept_tables': len(kept_tables), 'kept_seats': len(kept_seats), 'kept_boards': len(boards), 'relinked': relinked,
                    'tables': new_tables, 'seats': new_seats}


def write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False); fh.write('\n')
    os.replace(tmp, path)       # never leave a half-written file the app would choke on


def update_index(rooms_dir, room_id, name, make_default):
    """Add or rename this Room in index.json, keeping every other Room and their order."""
    path = os.path.join(rooms_dir, 'index.json'); rooms = []
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh: rooms = json.load(fh)
        if not isinstance(rooms, list): sys.exit(f'{path} is not a list of Rooms; fix it by hand before publishing.')
    entry = next((r for r in rooms if isinstance(r, dict) and r.get('id') == room_id), None)
    if entry is None:
        entry = {'id': room_id, 'name': name}; rooms.append(entry)
    else:
        entry['name'] = name
    if make_default:
        rooms.remove(entry); rooms.insert(0, entry)
    write_json(path, rooms)
    return rooms


# ---------------------------------------------------------------------------------------------------------------------
# Steps

def run_cleanup(scan, work, clean_args):
    """Run clean_scan.py as a separate process (it changes independently of this tool) and find what it wrote."""
    cmd = [sys.executable, os.path.join(HERE, 'clean_scan.py'), scan, *clean_args, '--out-dir', work]
    log(f'Cleaning the Scan: {" ".join(shlex.quote(c) for c in cmd[1:])}')
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = []
    for line in proc.stdout:
        lines.append(line); print('  │ ' + line.rstrip(), flush=True)
    if proc.wait():
        sys.exit(f'clean_scan.py failed (exit {proc.returncode}); nothing was published.')
    base = os.path.splitext(os.path.basename(scan))[0]

    def find(suffix, required=True):
        exact = os.path.join(work, base + suffix)
        if os.path.exists(exact): return exact
        hits = sorted(glob.glob(os.path.join(work, '*' + suffix)))
        if suffix == '.spz': hits = [h for h in hits if not h.endswith('.clean.spz')]
        if hits: return hits[0]
        if required: sys.exit(f'clean_scan.py finished but wrote no *{suffix} in {work}; nothing was published.')
        return None

    out = ''.join(lines)
    return {'spz': find('.spz'), 'layout': find('.layout.json'), 'ply': find('.clean.ply', False), 'preview': find('.preview.png', False),
            'kept': re.search(r'Kept ([\d,]+) of ([\d,]+)', out), 'stdout': out}


def run_qa(qa_dir, appearance, layout_path, clean_ply, preview):
    """Render views and a Scan quality report with the QA tools, when they are installed next to this script."""
    os.makedirs(qa_dir, exist_ok=True); made = []
    if preview:
        shutil.copy(preview, os.path.join(qa_dir, 'preview.png')); made.append(os.path.join(qa_dir, 'preview.png'))
    render, report = os.path.join(HERE, 'render_views.mjs'), os.path.join(HERE, 'scan_report.py')
    png = os.path.join(qa_dir, 'views.png'); html = os.path.join(qa_dir, 'report.html')

    def attempt(what, cmd, out):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except (OSError, subprocess.TimeoutExpired) as e:
            log(f'  ! {what} did not run: {e}'); return False
        if r.returncode or not os.path.exists(out):
            tail = (r.stdout + r.stderr).strip().splitlines()[-5:]
            log(f'  ! {what} failed (exit {r.returncode}); the Room is published anyway.' + ''.join(f'\n    {t}' for t in tail)); return False
        made.append(out); return True

    rendered = False
    if os.path.exists(render):
        if shutil.which('node'): rendered = attempt('render_views.mjs', ['node', render, appearance, layout_path, png], png)
        else: log('  ! render_views.mjs needs node, which is not on PATH; skipped.')
    else:
        log('  - render_views.mjs not found next to this script; skipped the rendered views.')
    if os.path.exists(report):
        if clean_ply:
            cmd = [sys.executable, report, clean_ply, layout_path, '--html', html] + (['--renders', png] if rendered else [])
            attempt('scan_report.py', cmd, html)
        else: log('  ! no *.clean.ply from the cleanup, so scan_report.py was skipped.')
    else:
        log('  - scan_report.py not found next to this script; skipped the Scan quality report.')
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('scan', help='raw Scan from Scaniverse or Polycam (.ply or .spz)')
    ap.add_argument('room_id', help='folder and URL name, e.g. pattee-3 (lowercase letters, digits and dashes)')
    ap.add_argument('name', help='the Room name Students see, e.g. "Pattee Library · Room 3"')
    ap.add_argument('--rooms-dir', default=os.path.join(HERE, '..', 'app', 'public', 'rooms'))
    ap.add_argument('--clean-args', default='', help='extra flags passed straight to clean_scan.py, e.g. "--no-sh --max-splats 800000"')
    ap.add_argument('--no-qa', action='store_true', help="don't run the QA tools")
    ap.add_argument('--qa-dir', default=None, help='where QA outputs go (default: <temp>/commons-qa/<room-id>)')
    ap.add_argument('--work-dir', default=None, help='keep the cleanup outputs (*.clean.ply master copy, preview) here instead of a temporary folder')
    ap.add_argument('--fresh', action='store_true', help='discard what a Room Curator already placed in this Room (Boards, confirmed Tables and seats)')
    ap.add_argument('--default', action='store_true', help='list this Room first in index.json, so the app opens it by default')
    a = ap.parse_args(argv)

    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', a.room_id): sys.exit(f'Room id "{a.room_id}" must be lowercase letters, digits and dashes (it becomes a URL).')
    if not a.name.strip(): sys.exit('The Room name is empty.')
    if not os.path.isfile(a.scan): sys.exit(f'No Scan at {a.scan}')
    clean_args = shlex.split(a.clean_args)
    if any(c == '--out-dir' or c.startswith('--out-dir=') for c in clean_args): sys.exit('--clean-args must not set --out-dir; use --work-dir.')
    rooms_dir = os.path.abspath(a.rooms_dir); room_dir = os.path.join(rooms_dir, a.room_id)
    if not os.path.isdir(rooms_dir): sys.exit(f'No rooms folder at {rooms_dir} (use --rooms-dir).')

    tmp = None
    if a.work_dir: work = os.path.abspath(a.work_dir); os.makedirs(work, exist_ok=True)
    else: tmp = tempfile.TemporaryDirectory(prefix='publish-room-'); work = tmp.name
    try:
        out = run_cleanup(os.path.abspath(a.scan), work, clean_args)
        with open(out['layout'], encoding='utf-8') as fh: base = json.load(fh)
        bounds = base.get('bounds') or {}
        if not all(isinstance(bounds.get(k), (int, float)) for k in ('min_x', 'max_x', 'min_z', 'max_z')):
            sys.exit(f'{out["layout"]} has no usable bounds; nothing was published.')
        base.setdefault('units', 'metres'); base.setdefault('up', '+y'); base.setdefault('floor_y', 0)
        for k in ('tables', 'seats', 'boards'): base.setdefault(k, [])

        log('\nSuggesting furniture …')
        points, n_all = load_points(out['ply'] or out['spz'])
        tables, spots, grid = suggest_furniture(points, bounds)
        base.setdefault('splats', n_all)

        previous = None
        prev_path = os.path.join(room_dir, 'layout.json')
        if os.path.exists(prev_path) and not a.fresh:
            try:
                with open(prev_path, encoding='utf-8') as fh: previous = json.load(fh)
            except (OSError, json.JSONDecodeError) as e:
                sys.exit(f'Could not read the existing {prev_path} ({e}). Fix it, or pass --fresh to replace it.')
        layout, info = build_layout(base, tables, spots, previous)
        n_t, n_s = len(info['tables']), len(info['seats'])
        layout['note'] = (f'Published with tools/publish_room.py from the Scan {os.path.basename(a.scan)}. '
                          f'{count(n_t, "Table")} and {count(n_s, "seat")} marked "suggested" were found automatically; '
                          'a Room Curator confirms them and places the Boards in the editor (?curate).')
        errs = validate_layout(layout)
        if errs: sys.exit('The Layout would be invalid, so nothing was published:\n  ' + '\n  '.join(errs))

        os.makedirs(room_dir, exist_ok=True)
        app_path = os.path.join(room_dir, 'appearance.spz')
        shutil.copyfile(out['spz'], app_path + '.tmp'); os.replace(app_path + '.tmp', app_path)
        write_json(prev_path, layout)
        rooms = update_index(rooms_dir, a.room_id, a.name.strip(), a.default)

        qa_made = []
        if not a.no_qa:
            log('\nQA …')
            qa_dir = os.path.abspath(a.qa_dir or os.path.join(tempfile.gettempdir(), 'commons-qa', a.room_id))
            qa_made = run_qa(qa_dir, app_path, prev_path, out['ply'], out['preview'])
    finally:
        if tmp: tmp.cleanup()

    # Summary
    b = layout['bounds']; mb = os.path.getsize(app_path) / 1e6
    pos = 'first' if rooms[0]['id'] == a.room_id else f'#{[r.get("id") for r in rooms].index(a.room_id) + 1}'
    log(f'\nPublished Room "{a.name.strip()}" ({a.room_id}) → {room_dir}')
    log(f'  Room size   {b["max_x"] - b["min_x"]:.2f} × {b["max_z"] - b["min_z"]:.2f} m, {layout["height"]:.2f} m tall   ← check against the real room')
    log(f'  Appearance  {layout.get("splats", 0):,} splats, {mb:.1f} MB')
    log(f'  Suggested   {count(n_t, "Table")}, {count(n_s, "seat")}')
    for t in info['tables']:
        log(f'    {t["id"]:<9} x {t["x"]:+.2f}  z {t["z"]:+.2f}  {t["width"]:.2f} × {t["depth"]:.2f} m, top {t["height"]:.2f} m, turned {math.degrees(t["rotation"]):.0f}°')
    for s in info['seats']:
        log(f'    {s["id"]:<9} x {s["x"]:+.2f}  z {s["z"]:+.2f}  facing {math.degrees(s["facing"]):.0f}° ' + (f'toward {s["tableId"]}' if s['tableId'] else "toward the room's centre"))
    if info['kept_tables'] or info['kept_seats'] or info['kept_boards']:
        log(f'  Kept        {count(info["kept_tables"], "Table")}, {count(info["kept_seats"], "seat")} and {count(info["kept_boards"], "Board")} the Curator already placed. '
            'Check they still line up: a different cleanup can shift the Room slightly. (--fresh discards them.)')
    if info['relinked']: log(f'  Relinked    seats {", ".join(info["relinked"])} to the nearest Table, because theirs is gone')
    log(f'  index.json  {len(rooms)} Rooms, this one {pos}')
    if qa_made: log('  QA          ' + '\n              '.join(qa_made))
    log('\nNext steps for the Room Curator:')
    log(f'  1. cd app && npm run dev, then open http://localhost:5173/?curate&room={a.room_id}')
    log('  2. Confirm or delete each suggested Table and seat, and add any the Scan missed')
    log("  3. Place a Board over each real whiteboard or chalkboard (or one on a wall you choose, if there's none)")
    rel = os.path.relpath(prev_path)
    log(f'  4. Download layout.json and save it over {prev_path if rel.startswith("..") else rel}')


if __name__ == '__main__':
    main()

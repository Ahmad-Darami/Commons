#!/usr/bin/env python3
"""Clean a splat Scan (Scaniverse / Polycam .ply or .spz) so it can become a Room's Appearance.

What it does, in order:
  1. drops near-invisible and oversized splats
  2. removes floaters (fuzz that isn't attached to the room)
  3. finds the floor, levels it to y = 0 (+y up), and centres the room
  4. deletes the mirror-image "ghost room" that shiny floors create below the floor
  5. crops stray splats outside the room, optionally caps the splat count
  6. writes  <name>.clean.ply   (master copy, for editing in SuperSplat)
             <name>.spz         (what the browser loads, via Spark)
             <name>.preview.png (top + front views, to check the result)
             <name>.layout.json (starter Layout: floor, room bounds, empty seats/tables/boards)

Usage:  python clean_scan.py scan.ply [--max-splats 1500000] [--no-sh] [--out-dir out/]
Needs:  numpy, pillow, and Niantic's spz bindings (pip install git+https://github.com/nianticlabs/spz)
"""
import argparse, json, math, os, sys, time

import numpy as np
import spz
from PIL import Image, ImageDraw

RUB = spz.CoordinateSystem.RUB   # three.js convention: +x right, +y up, +z back


def log(msg): print(msg, flush=True)


def load(path):
    opts = spz.UnpackOptions(); opts.to_coord = RUB
    cloud = spz.load_splat_from_ply(path, opts) if path.lower().endswith('.ply') else spz.load_spz(path, opts)
    n = cloud.num_points
    return {
        'pos': np.asarray(cloud.positions, np.float32).reshape(n, 3),
        'scale': np.asarray(cloud.scales, np.float32).reshape(n, 3),
        'rot': np.asarray(cloud.rotations, np.float32).reshape(n, 4),     # x, y, z, w
        'alpha': np.asarray(cloud.alphas, np.float32).reshape(n),
        'color': np.asarray(cloud.colors, np.float32).reshape(n, 3),     # SH DC terms
        'sh': np.asarray(cloud.sh, np.float32).reshape(n, -1) if cloud.sh_degree > 0 else np.zeros((n, 0), np.float32),
        'sh_degree': cloud.sh_degree, 'antialiased': cloud.antialiased,
    }


def keep(g, mask, why, stats):
    stats.append((why, int((~mask).sum())))
    for k in ('pos', 'scale', 'rot', 'alpha', 'color', 'sh'):
        g[k] = g[k][mask]


def to_cloud(g):
    c = spz.GaussianCloud()
    c.sh_degree = g['sh_degree']; c.antialiased = g['antialiased']
    c.positions = g['pos'].ravel(); c.scales = g['scale'].ravel(); c.rotations = g['rot'].ravel()
    c.alphas = g['alpha'].ravel(); c.colors = g['color'].ravel()
    if g['sh_degree'] > 0: c.sh = g['sh'].ravel()
    return c


def sigmoid(x): return 1 / (1 + np.exp(-x))


def components(pos, voxel, min_frac):
    """Keep splats in connected clumps of occupied voxels holding >= min_frac of all splats."""
    k = np.floor((pos - pos.min(0)) / voxel).astype(np.int64)
    dims = k.max(0) + 3; k += 1
    code = (k[:, 0] * dims[1] + k[:, 1]) * dims[2] + k[:, 2]
    vox, inv, counts = np.unique(code, return_inverse=True, return_counts=True)
    label = np.arange(len(vox))
    offs = [((dx * dims[1]) + dy) * dims[2] + dz for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1) if dx or dy or dz]
    nbrs = []
    for o in offs:
        j = np.searchsorted(vox, vox + o); j[j >= len(vox)] = 0
        hit = vox[j] == vox + o
        nbrs.append((np.nonzero(hit)[0], j[hit]))
    for _ in range(1000):   # min-label propagation with pointer jumping
        old = label.copy()
        for a, b in nbrs: np.minimum.at(label, a, label[b])
        label = label[label]
        if np.array_equal(old, label): break
    size = np.bincount(label, weights=counts, minlength=len(vox))
    return size[label][inv] >= min_frac * len(pos)


def dense_enough(pos, voxel, rel):
    """Drop lonely splats: those whose 3x3x3 voxel neighbourhood is far emptier than a typical surface."""
    k = np.floor((pos - pos.min(0)) / voxel).astype(np.int64)
    dims = k.max(0) + 3; k += 1
    code = (k[:, 0] * dims[1] + k[:, 1]) * dims[2] + k[:, 2]
    vox, inv, counts = np.unique(code, return_inverse=True, return_counts=True)
    hood = np.zeros(len(vox))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                o = ((dx * dims[1]) + dy) * dims[2] + dz
                j = np.searchsorted(vox, vox + o); j[j >= len(vox)] = 0
                hood += np.where(vox[j] == vox + o, counts[j], 0)
    per_splat = hood[inv]
    return per_splat >= max(3, rel * np.median(per_splat))


def find_floor(pos, rng, tol):
    """RANSAC for a roughly horizontal plane with (almost) everything above it."""
    P = pos[rng.choice(len(pos), size=min(len(pos), 150_000), replace=False)]
    best = None
    for _ in range(1500):
        a, b, c = P[rng.choice(len(P), 3, replace=False)]
        n = np.cross(b - a, c - a); ln = np.linalg.norm(n)
        if ln < 1e-9: continue
        n /= ln
        if n[1] < 0: n = -n
        if n[1] < math.cos(math.radians(30)): continue   # scans from ARKit are close to gravity-aligned
        d = -n @ a; dist = P @ n + d
        below = np.mean(dist < -tol * 3)
        if below > 0.15: continue                          # shiny floors mirror a little of the room below
        score = np.sum(np.abs(dist) < tol)
        if best is None or score > best[0]: best = (score, n, d)
    if best is None: return None
    _, n, d = best
    for _ in range(3):   # refine with a least-squares fit to the inliers
        inl = P[np.abs(P @ n + d) < tol]
        c = inl.mean(0); _, _, vt = np.linalg.svd(inl - c, full_matrices=False)
        n = vt[2] if vt[2][1] > 0 else -vt[2]; d = -n @ c
    return n, d, inl


def quat_mul(q, r):   # Hamilton product, xyzw, q applied after r
    x1, y1, z1, w1 = q; x2, y2, z2, w2 = r.T
    return np.stack([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
                     w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2], 1)


def rotate(g, axis, th, keep_sh, why):
    """Rotate every splat by th radians about a unit axis through the origin."""
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    R = np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K
    q = np.array([*(np.asarray(axis) * math.sin(th / 2)), math.cos(th / 2)])
    g['pos'] = (g['pos'] @ R.T).astype(np.float32)
    g['rot'] = quat_mul(q, g['rot'].astype(np.float64)).astype(np.float32)
    if abs(math.degrees(th)) > 2 and g['sh_degree'] > 0 and not keep_sh:
        # higher-order SH would need rotating too; dropping them keeps colours right (and tames glare)
        g['sh_degree'] = 0; g['sh'] = g['sh'][:, :0]
        log(f'  {why}, so view-dependent shine (SH) was dropped')


def level(g, n, keep_sh):
    """Rotate so the floor normal n becomes +y. Returns the rotation angle in degrees."""
    up = np.array([0, 1, 0.]); axis = np.cross(n, up); s = np.linalg.norm(axis); c = n @ up
    if s < 1e-9: return 0.0
    th = math.atan2(s, c)
    rotate(g, axis / s, th, keep_sh, f'levelled by {math.degrees(th):.1f}°')
    return math.degrees(th)


def square_up(g, tol, keep_sh):
    """Turn the room about +y so its walls run along x and z.

    Walls and furniture edges seen from above are straight lines. At the right angle, projecting the splats
    between knee and head height onto the x and z axes piles them into sharp peaks, so pick the angle that
    maximises how peaked those projections are (sum of squared histogram counts).
    """
    p = g['pos']; band = (p[:, 1] > 0.3) & (p[:, 1] < 2.2)
    pts = (p[band] if band.sum() > 5000 else p[np.abs(p[:, 1]) < tol])[:, [0, 2]].astype(np.float64)
    if len(pts) > 300_000: pts = pts[np.random.default_rng(2).choice(len(pts), 300_000, replace=False)]
    lo, hi = np.percentile(pts, 0.5, 0), np.percentile(pts, 99.5, 0)
    pts = pts[((pts >= lo) & (pts <= hi)).all(1)]
    r = np.hypot(*(hi - lo)) / 2 + 0.1; bins = np.linspace(-r, r, int(2 * r / 0.04))
    c0 = pts.mean(0); pts = pts - c0

    def peakedness(deg):
        t = math.radians(deg); c, s = math.cos(t), math.sin(t)
        hu, _ = np.histogram(pts[:, 0] * c - pts[:, 1] * s, bins); hv, _ = np.histogram(pts[:, 0] * s + pts[:, 1] * c, bins)
        return float((hu.astype(np.float64) ** 2).sum() + (hv.astype(np.float64) ** 2).sum())

    coarse = np.arange(-45, 45, 1.0)
    best = coarse[int(np.argmax([peakedness(d) for d in coarse]))]
    fine = np.arange(best - 1.5, best + 1.5, 0.05)
    best = float(fine[int(np.argmax([peakedness(d) for d in fine]))])
    best = (best + 45) % 90 - 45                       # a room is the same turned by 90°
    if abs(best) < 0.5: return 0.0
    # a positive turn about +y maps (x, z) to (x cos + z sin, -x sin + z cos); the search used the opposite sense
    rotate(g, np.array([0, 1, 0.]), -math.radians(best), keep_sh, f'turned {abs(best):.1f}° to square the room up')
    return best


def _shift_or(m, r):   # binary dilation by a (2r+1) square, without scipy
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def _shift_and(m, r):  # binary erosion by a (2r+1) square
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out &= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


FILL_PER = 6   # small overlapping discs per filled cell, like the fine splats of a real floor


def floor_grid(g, cell, tol):
    """Which cells of the floor did the Scan actually cover, and with what colour?"""
    p = g['pos']; on = np.abs(p[:, 1]) < tol
    fl, rgb = p[on], np.clip(0.5 + 0.282095 * g['color'][on], 0, 1)
    w = sigmoid(g['alpha'][on])                            # weight by opacity: faint fuzz barely shows, so it shouldn't set the colour
    lo = np.percentile(fl[:, [0, 2]], 0.5, axis=0) - 2 * cell; hi = np.percentile(fl[:, [0, 2]], 99.5, axis=0) + 2 * cell
    shape = (int(np.ceil((hi[1] - lo[1]) / cell)) + 1, int(np.ceil((hi[0] - lo[0]) / cell)) + 1)
    ix = ((fl[:, 0] - lo[0]) / cell).astype(int).clip(0, shape[1] - 1); iz = ((fl[:, 2] - lo[1]) / cell).astype(int).clip(0, shape[0] - 1)
    count = np.zeros(shape); wsum = np.zeros(shape); col = np.zeros(shape + (3,))
    np.add.at(count, (iz, ix), 1); np.add.at(wsum, (iz, ix), w); np.add.at(col, (iz, ix), rgb * w[:, None])
    covered = count >= max(1, 0.15 * np.median(count[count > 0]))
    col[covered] /= np.maximum(wsum[covered], 1e-6)[:, None]
    # Per-cell lists of the real, clearly visible floor splats, so filling can copy individual splat colours.
    vis = w >= 0.3; cid = (iz * shape[1] + ix)[vis]; order = np.argsort(cid, kind='stable')
    starts = np.searchsorted(cid[order], np.arange(shape[0] * shape[1])); counts = np.bincount(cid, minlength=shape[0] * shape[1])
    sampler = (rgb[vis][order], starts, counts)
    return lo, covered, col, sampler


def fill_floor(g, cell, close_m, tol, rng):
    """Synthesise flat floor splats wherever the floor should be but the Scan has a hole."""
    lo, covered, col, (srgb, sstart, scount) = floor_grid(g, cell, tol)
    r = max(1, int(round(close_m / cell)))
    pad = r + 2; cov = np.pad(covered, pad)
    closed = _shift_and(_shift_or(cov, r), r)              # seals gaps up to ~close_m wide, e.g. under a table
    outside = np.zeros_like(closed); outside[0, :] = outside[-1, :] = outside[:, 0] = outside[:, -1] = True
    outside &= ~closed
    while True:                                            # flood-fill from the border: what's left is inside the room
        grown = _shift_or(outside, 1) & ~closed
        if (grown == outside).all(): break
        outside = grown
    footprint = (~outside)[pad:-pad, pad:-pad]
    # Most rooms are rectangles: if the scanned floor fills most of its bounding rectangle, the whole rectangle is floor.
    # That also catches corners the phone never reached, which touch the edge and so can't be told apart from outside.
    iz, ix = np.nonzero(covered)
    rz0, rz1 = np.percentile(iz, [0.5, 99.5]).astype(int); rx0, rx1 = np.percentile(ix, [0.5, 99.5]).astype(int)
    rect = np.zeros_like(covered); rect[rz0:rz1 + 1, rx0:rx1 + 1] = True
    if (covered & rect).sum() >= 0.7 * rect.sum(): footprint |= rect
    holes = footprint & ~covered
    holes &= _shift_or(_shift_and(holes, 1), 1)            # ignore specks narrower than ~3 cells: that's sampling noise, not a hole
    if not holes.any(): return 0, footprint, lo
    # colour each hole by harmonic interpolation from the surrounding real floor
    c = col.copy(); c[~covered] = col[covered].mean(0)
    for _ in range(400):
        avg = (np.roll(c, 1, 0) + np.roll(c, -1, 0) + np.roll(c, 1, 1) + np.roll(c, -1, 1)) / 4
        c = np.where(holes[..., None], avg, c)
    iz, ix = np.nonzero(holes)
    per = FILL_PER
    n = len(iz) * per
    x = lo[0] + (np.repeat(ix, per) + rng.random(n)) * cell; z = lo[1] + (np.repeat(iz, per) + rng.random(n)) * cell
    # Borrow texture: give each new splat the colour of a real floor cell nearby, so a speckled carpet stays speckled.
    # The smooth interpolated colour is only the fallback where no real floor is within reach.
    rgb = np.repeat(c[iz, ix], per, 0)
    cz, cx = np.repeat(iz, per), np.repeat(ix, per); todo = np.ones(n, bool)
    for radius in (8, 16, 32):                             # in cells: ~0.3, 0.6, 1.3 m with the default 4 cm cell
        for _ in range(6):
            if not todo.any(): break
            k = np.nonzero(todo)[0]
            sz = np.clip(cz[k] + rng.integers(-radius, radius + 1, len(k)), 0, covered.shape[0] - 1)
            sx = np.clip(cx[k] + rng.integers(-radius, radius + 1, len(k)), 0, covered.shape[1] - 1)
            ok = covered[sz, sx]
            cells = sz * covered.shape[1] + sx
            ok &= scount[cells] > 0
            pick = sstart[cells[ok]] + (rng.random(ok.sum()) * scount[cells[ok]]).astype(int)
            rgb[k[ok]] = srgb[pick]; todo[k[ok]] = False
    rgb = np.clip(rgb + rng.normal(0, 0.01, (n, 3)), 0, 1)
    new = {
        'pos': np.c_[x, np.zeros(n), z].astype(np.float32),
        'scale': np.log(np.c_[np.full(n, cell * 0.35), np.full(n, 0.002), np.full(n, cell * 0.35)]).astype(np.float32),
        'rot': np.tile(np.array([0, 0, 0, 1], np.float32), (n, 1)),
        'alpha': np.full(n, 1.5, np.float32),                  # sigmoid(1.5) ≈ 0.82: slightly see-through, like real scanned floor
        'color': ((rgb - 0.5) / 0.282095).astype(np.float32),
        'sh': np.zeros((n, g['sh'].shape[1]), np.float32),
    }
    for k in new: g[k] = np.concatenate([g[k], new[k]])
    return int(holes.sum()), footprint, lo


def walkable_rows(footprint, lo, cell, step):
    """Downsample the floor footprint into rows of '#' (floor) and '.' (not floor) for the app's walkable area."""
    k = max(1, int(round(step / cell)))
    H, W = footprint.shape[0] // k, footprint.shape[1] // k
    f = footprint[:H * k, :W * k].reshape(H, k, W, k).mean((1, 3)) > 0.5
    return {'cell': round(cell * k, 3), 'origin': [round(float(lo[0]), 3), round(float(lo[1]), 3)], 'rows': [''.join('#' if v else '.' for v in row) for row in f]}


def preview(g, path, bounds, height):
    rgb = np.clip(0.5 + 0.282095 * g['color'], 0, 1); a = sigmoid(g['alpha'])
    W = 900; pad = 30
    views = [('Top view (x right, z down)', 0, 2), ('Front view (x right, y up)', 0, 1)]
    tiles = []
    for title, ia, ib in views:
        pa, pb = g['pos'][:, ia], g['pos'][:, ib]
        lo_a, hi_a = np.percentile(pa, [0.2, 99.8]); lo_b, hi_b = np.percentile(pb, [0.2, 99.8])
        sc = (W - 2 * pad) / max(hi_a - lo_a, 1e-3); H = int((hi_b - lo_b) * sc) + 2 * pad + 30
        H = min(max(H, 200), 900)
        x = ((pa - lo_a) * sc + pad).astype(int); y = ((pb - lo_b) * sc + pad + 30).astype(int)
        if ib == 1: y = H - 1 - ((pb - lo_b) * sc + pad).astype(int)
        ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
        acc = np.zeros((H, W, 3)); wsum = np.zeros((H, W))
        np.add.at(acc, (y[ok], x[ok]), rgb[ok] * a[ok, None]); np.add.at(wsum, (y[ok], x[ok]), a[ok])
        img = np.where(wsum[..., None] > 0, acc / np.maximum(wsum, 1e-6)[..., None], 0.08)
        im = Image.fromarray((img * 255).astype(np.uint8)); d = ImageDraw.Draw(im)
        d.text((pad, 8), title, fill=(230, 230, 230))
        if ib == 1:
            fy = H - 1 - int((0 - lo_b) * sc + pad); d.line([(0, fy), (W, fy)], fill=(80, 220, 120)); d.text((W - 90, fy - 14), 'floor y=0', fill=(80, 220, 120))
        tiles.append(im)
    out = Image.new('RGB', (W, sum(t.height for t in tiles) + 40), (20, 22, 28)); yy = 0
    for t in tiles: out.paste(t, (0, yy)); yy += t.height
    ImageDraw.Draw(out).text((pad, yy + 12), f"{len(g['pos']):,} splats · room {bounds[1]-bounds[0]:.2f} x {bounds[3]-bounds[2]:.2f} m, {height:.2f} m tall", fill=(230, 230, 230))
    out.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('scan'); ap.add_argument('--out-dir', default=None)
    ap.add_argument('--max-splats', type=int, default=1_500_000, help='cap the splat count (keeps the most visible); 0 = no cap')
    ap.add_argument('--min-opacity', type=float, default=0.03)
    ap.add_argument('--max-size', type=float, default=0.75, help='drop splats bigger than this (metres)')
    ap.add_argument('--floor-tol', type=float, default=0.03, help='floor plane thickness (metres)')
    ap.add_argument('--no-sh', action='store_true', help='drop view-dependent shine: ~4x smaller and less whiteboard glare')
    ap.add_argument('--keep-sh', action='store_true', help='keep SH even if levelling rotated the scan')
    ap.add_argument('--no-square', action='store_true', help="don't turn the room so its walls run along x and z")
    ap.add_argument('--no-fill-floor', action='store_true', help="don't synthesise floor where the Scan has holes")
    ap.add_argument('--fill-cell', type=float, default=0.04, help='floor-filling grid size (metres)')
    ap.add_argument('--fill-close', type=float, default=0.3, help='seal floor gaps up to this wide at the room edges (metres)')
    ap.add_argument('--spz-version', type=int, default=3, choices=(2, 3, 4), help='3 = widest viewer support; 4 = newest, slightly smaller')
    a = ap.parse_args()

    t0 = time.time(); rng = np.random.default_rng(1)
    base = os.path.splitext(os.path.basename(a.scan))[0]
    out = a.out_dir or os.path.dirname(os.path.abspath(a.scan)); os.makedirs(out, exist_ok=True)
    log(f'Loading {a.scan} …'); g = load(a.scan); n0 = len(g['pos'])
    log(f'  {n0:,} splats, SH degree {g["sh_degree"]}')
    stats = []

    keep(g, np.isfinite(g['pos']).all(1) & np.isfinite(g['scale']).all(1), 'invalid numbers', stats)
    keep(g, sigmoid(g['alpha']) >= a.min_opacity, 'nearly invisible', stats)
    keep(g, np.exp(g['scale']).max(1) <= a.max_size, f'larger than {a.max_size} m', stats)
    log('Removing floaters …')
    keep(g, components(g['pos'], 0.15, 0.01), 'floaters (detached clumps)', stats)
    keep(g, dense_enough(g['pos'], 0.06, 0.03), 'floaters (lonely splats near surfaces)', stats)

    log('Finding the floor …')
    f = find_floor(g['pos'], rng, a.floor_tol)
    if f is None: sys.exit('Could not find a floor. Is this a room scan? (A scan of a single object has no floor.)')
    n, d, _ = f
    tilt = level(g, n, a.keep_sh)
    _, _, inl = find_floor(g['pos'], rng, a.floor_tol)
    floor_y = float(np.median(inl[:, 1])); g['pos'][:, 1] -= floor_y
    log(f'  floor found; scan was tilted {tilt:.1f}°, now level at y = 0')
    keep(g, g['pos'][:, 1] >= -0.08, 'below the floor (shiny-floor reflections)', stats)
    if not a.no_square:
        turn = square_up(g, a.floor_tol, a.keep_sh)
        if turn: log(f'  room squared up: turned {abs(turn):.1f}° so its walls run along x and z')

    p = g['pos']; lo = np.percentile(p, 0.3, axis=0) - 0.25; hi = np.percentile(p, 99.7, axis=0) + 0.25
    keep(g, (p[:, 0] >= lo[0]) & (p[:, 0] <= hi[0]) & (p[:, 2] >= lo[2]) & (p[:, 2] <= hi[2]) & (p[:, 1] <= hi[1]), 'outside the room', stats)
    if a.no_sh and g['sh_degree'] > 0: g['sh_degree'] = 0; g['sh'] = g['sh'][:, :0]
    if a.max_splats and len(g['pos']) > a.max_splats:
        imp = sigmoid(g['alpha']) * np.exp(g['scale'].sum(1))
        keep(g, imp >= np.partition(imp, -a.max_splats)[-a.max_splats], f'over the {a.max_splats:,} cap (least visible)', stats)

    fl = g['pos'][np.abs(g['pos'][:, 1]) < a.floor_tol]
    bx = np.percentile(fl[:, 0], [1, 99]); bz = np.percentile(fl[:, 2], [1, 99])
    cx, cz = bx.mean(), bz.mean(); g['pos'][:, 0] -= cx; g['pos'][:, 2] -= cz
    bounds = [float(bx[0] - cx), float(bx[1] - cx), float(bz[0] - cz), float(bz[1] - cz)]
    height = float(np.percentile(g['pos'][:, 1], 99.5))

    filled = 0
    if not a.no_fill_floor:
        log('Filling holes in the floor …')
        filled, footprint, flo = fill_floor(g, a.fill_cell, a.fill_close, a.floor_tol, rng)
        log(f'  filled {filled * a.fill_cell ** 2:.2f} m² of missing floor' if filled else '  no holes found')
    else:
        flo, footprint = floor_grid(g, a.fill_cell, a.floor_tol)[:2]

    cloud = to_cloud(g)
    ply = os.path.join(out, base + '.clean.ply'); spzf = os.path.join(out, base + '.spz')
    po = spz.PackOptions(); po.from_coord = RUB; spz.save_splat_to_ply(cloud, po, ply)
    po = spz.PackOptions(); po.from_coord = RUB; po.version = a.spz_version; spz.save_spz(cloud, po, spzf)
    preview(g, os.path.join(out, base + '.preview.png'), bounds, height)
    layout = {
        'units': 'metres', 'up': '+y', 'floor_y': 0,
        'bounds': dict(zip(['min_x', 'max_x', 'min_z', 'max_z'], [round(v, 3) for v in bounds])), 'height': round(height, 3),
        'appearance': os.path.basename(spzf), 'splats': len(g['pos']),
        'walkable': walkable_rows(footprint, flo, a.fill_cell, 0.1),
        'tables': [], 'seats': [], 'boards': [],
        'note': 'Starter Layout from clean_scan.py. A Room Curator still places tables, seats and Boards.',
    }
    with open(os.path.join(out, base + '.layout.json'), 'w') as fh: json.dump(layout, fh, indent=2)

    log('\nRemoved:')
    for why, k in stats:
        if k: log(f'  {k:>10,}  {why}')
    if filled: log(f'Added {filled * FILL_PER:,} floor splats to fill {filled * a.fill_cell ** 2:.2f} m² of holes')
    log(f'\nKept {len(g["pos"]):,} of {n0:,} splats ({100 * len(g["pos"]) / n0:.0f}%), SH degree {g["sh_degree"]}')
    log(f'Room footprint {bounds[1]-bounds[0]:.2f} × {bounds[3]-bounds[2]:.2f} m, {height:.2f} m tall  ← sanity-check against the real room')
    src_mb = os.path.getsize(a.scan) / 1e6
    log(f'Files: {os.path.basename(ply)} {os.path.getsize(ply)/1e6:.1f} MB · {os.path.basename(spzf)} {os.path.getsize(spzf)/1e6:.1f} MB (from {src_mb:.1f} MB) · preview + layout in {out}')
    log(f'Done in {time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()

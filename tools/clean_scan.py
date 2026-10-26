#!/usr/bin/env python3
"""Clean a splat Scan (Scaniverse / Polycam .ply or .spz) so it can become a Room's Appearance.

What it does, in order:
  1. drops near-invisible and oversized splats
  2. removes floaters (fuzz that isn't attached to the room)
  3. finds the floor, levels it to y = 0 (+y up), and centres the room
  4. deletes the mirror-image "ghost room" that shiny floors create below the floor
  5. crops stray splats outside the room, optionally caps the splat count
  6. suppresses ghosts: needles, blobs behind the walls, outsized smears; fades lone splats' view-dependent colour
  7. repairs what the Scan missed (ADR-0003): holes in the floor, missing walls and ceiling, and reports it
  8. writes  <name>.clean.ply   (master copy, for editing in SuperSplat)
             <name>.spz         (what the browser loads, via Spark)
             <name>.preview.png (top + front views, to check the result)
             <name>.layout.json (starter Layout: floor, room bounds, empty seats/tables/boards)

Usage:  python clean_scan.py scan.ply [--max-splats 1500000] [--sh-degree 1] [--no-fill-walls] [--out-dir out/]
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


def neighbourhood_counts(pos, voxel):
    """How many splats share each splat's 3x3x3 voxel neighbourhood: a cheap measure of how well-seen that spot is."""
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
    return hood[inv]


def dense_enough(pos, voxel, rel):
    """Drop lonely splats: those whose 3x3x3 voxel neighbourhood is far emptier than a typical surface."""
    per_splat = neighbourhood_counts(pos, voxel)
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


# The standard 3D Gaussian Splatting real spherical-harmonic basis (degrees 1 to 3), as renderers evaluate it.
_C1 = 0.4886025119029199
_C2 = [1.0925484305920792, -1.0925484305920792, 0.31539156525252005, -1.0925484305920792, 0.5462742152960396]
_C3 = [-0.5900435899266435, 2.890611442640554, -0.4570457994644658, 0.3731763325901154, -0.4570457994644658, 1.445305721320277, -0.5900435899266435]


def sh_basis(d, degree):
    """SH basis functions (excluding the constant term) at unit directions d (N x 3), in coefficient order."""
    x, y, z = d[:, 0], d[:, 1], d[:, 2]; xx, yy, zz = x * x, y * y, z * z
    cols = [-_C1 * y, _C1 * z, -_C1 * x]
    if degree >= 2:
        cols += [_C2[0] * x * y, _C2[1] * y * z, _C2[2] * (2 * zz - xx - yy), _C2[3] * x * z, _C2[4] * (xx - yy)]
    if degree >= 3:
        cols += [_C3[0] * y * (3 * xx - yy), _C3[1] * x * y * z, _C3[2] * y * (4 * zz - xx - yy), _C3[3] * z * (2 * zz - 3 * xx - 3 * yy),
                 _C3[4] * x * (4 * zz - xx - yy), _C3[5] * z * (xx - yy), _C3[6] * x * (xx - 3 * yy)]
    return np.stack(cols, 1)


def sh_rotation(R, degree):
    """Matrix M so that rotating a splat by R maps its SH coefficients c to M @ c (per colour channel).

    The rotated splat must look, from direction R d, the way the original looked from d. Each SH band is closed
    under rotation, so M is found exactly by least squares over many sample directions.
    """
    d = np.random.default_rng(0).normal(size=(400, 3)); d /= np.linalg.norm(d, axis=1, keepdims=True)
    B, B_rot = sh_basis(d, degree), sh_basis(d @ R, degree)   # d @ R evaluates at R^T d
    M = np.linalg.lstsq(B, B_rot, rcond=None)[0]       # B M = B_rot, so B (M c) reproduces the old colours
    M[np.abs(M) < 1e-9] = 0
    return M


def rotate(g, axis, th, keep_sh, why):
    """Rotate every splat by th radians about a unit axis through the origin."""
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    R = np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K
    q = np.array([*(np.asarray(axis) * math.sin(th / 2)), math.cos(th / 2)])
    g['pos'] = (g['pos'] @ R.T).astype(np.float32)
    g['rot'] = quat_mul(q, g['rot'].astype(np.float64)).astype(np.float32)
    if g['sh_degree'] > 0:
        # view-dependent colour (SH) turns with the splat; unrotated it shows as rainbow shimmer
        deg = min(g['sh_degree'], 3); K = (deg + 1) ** 2 - 1
        sh = g['sh'].reshape(len(g['sh']), -1, 3)[:, :K].astype(np.float64)
        g['sh'] = np.einsum('jk,nkc->njc', sh_rotation(R, deg), sh).reshape(len(sh), -1).astype(np.float32)
        g['sh_degree'] = deg


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


def quat_to_mat(q):   # xyzw unit quaternions -> rotation matrices (n x 3 x 3)
    x, y, z, w = q.T
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


def axis_sigmas(g):
    """Each splat's spread (1 sigma, metres) along world x, y and z: how much of a wall or ceiling it covers."""
    q = g['rot'].astype(np.float64); q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    return np.sqrt(np.einsum('nij,nj->ni', quat_to_mat(q) ** 2, np.exp(2 * g['scale'].astype(np.float64))))


def room_box(g, tol, height):
    """Where the walls and ceiling of a squared-up Room are, judged only from what was scanned.

    Each wall starts where the floor stops (floor splats run right up to the skirting), and moves out to the wall's
    own vertical splats where the Scan saw them. It never moves inward, which would cut real floor off.
    The ceiling is the higher of `height` and the top of the scanned walls: with the ceiling missing, a
    top-of-room percentile lands somewhere on the walls, and a ceiling there would slice through them.
    """
    p = g['pos']; fl = p[np.abs(p[:, 1]) < tol]
    up = p[(p[:, 1] > 0.2) & (p[:, 1] < 2.2)]
    box = {}
    for i, ax in ((0, 'x'), (2, 'z')):
        lo, hi = np.percentile(fl[:, i], [0.3, 99.7])
        for side, edge, q, pick in (('min', lo, 10, min), ('max', hi, 90, max)):
            band = up[np.abs(up[:, i] - edge) < 0.15, i]
            box[f'{side}_{ax}'] = float(pick(edge, np.percentile(band, q)) if len(band) > 50 else edge)
    near = p[(p[:, 1] > 0.2) & ((np.abs(p[:, 0] - box['min_x']) < 0.15) | (np.abs(p[:, 0] - box['max_x']) < 0.15) |
                                (np.abs(p[:, 2] - box['min_z']) < 0.15) | (np.abs(p[:, 2] - box['max_z']) < 0.15))]
    wall_top = float(np.percentile(near[:, 1], 99.5)) if len(near) > 100 else 0.0
    box['ceiling_y'] = max(height, wall_top)
    return box


def room_surfaces(box):
    """The 4 walls and the ceiling as planes: (name, normal axis, plane coordinate, which way is into the room,
    (u axis, from, to), (v axis, from, to)) where u and v span the surface."""
    x0, x1, z0, z1, y1 = box['min_x'], box['max_x'], box['min_z'], box['max_z'], box['ceiling_y']
    return [('−x wall', 0, x0, 1, (2, z0, z1), (1, 0.0, y1)), ('+x wall', 0, x1, -1, (2, z0, z1), (1, 0.0, y1)),
            ('−z wall', 2, z0, 1, (0, x0, x1), (1, 0.0, y1)), ('+z wall', 2, z1, -1, (0, x0, x1), (1, 0.0, y1)),
            ('ceiling', 1, y1, -1, (0, x0, x1), (2, z0, z1))]


def _cdf(x):   # standard normal CDF via Abramowitz & Stegun 7.1.26 (error < 2e-7), since numpy has no erf
    z = np.abs(x) / math.sqrt(2); t = 1 / (1 + 0.3275911 * z)
    erf = 1 - t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429)))) * np.exp(-z * z)
    return 0.5 * (1 + np.sign(x) * erf)


WALL_CELL = 0.08    # coverage grid on walls and ceiling (metres); coarser than the floor's, since walls are mostly plain
WALL_PER = 8        # discs per filled cell ...
WALL_SIGMA = 0.3    # ... each this wide (1 sigma, as a fraction of the cell), so neighbours overlap like real splats
WALL_DEPTH = 0.3    # anything this close in front of a wall hides it (shelves, the Board's whiteboard, radiators)
WALL_BEHIND = 0.1   # real wall splats scatter a little behind the plane, and doors sit in recesses
COVERED = 1.0       # opacity a cell needs to count as seen (sum of alpha x footprint over the cell's area)
WALL_DONOR_Y = 1.3  # walls lend colours only above this height (metres): desks, tables and most shelves are lower


def surface_coverage(g, sig, surf, cell):
    """How much of each cell of a wall or ceiling the Scan covered, plus who could lend it colours.

    Coverage is what a viewer sees: each splat adds alpha x its Gaussian footprint, spread over the cells it
    overlaps (exactly, via the normal CDF), so a few big soft splats count as much as many fine ones.
    """
    _, n_ax, w, s, (iu, u0, u1), (iv, v0, v1) = surf
    p = g['pos']; d = s * (p[:, n_ax] - w)                 # distance from the plane, into the room
    near = (d > -WALL_BEHIND) & (d < WALL_DEPTH) & (p[:, iu] > u0 - 0.5) & (p[:, iu] < u1 + 0.5) & (p[:, iv] > v0 - 0.5) & (p[:, iv] < v1 + 0.5)
    near &= sig.max(1) <= WALL_DEPTH                       # a blob deeper than the slab is a smear, not evidence of this surface
    nu, nv = max(1, int(math.ceil((u1 - u0) / cell - 1e-6))), max(1, int(math.ceil((v1 - v0) / cell - 1e-6)))
    pu, pv = (p[near, iu] - u0) / cell, (p[near, iv] - v0) / cell
    su, sv = np.maximum(sig[near, iu] / cell, 1e-3), np.maximum(sig[near, iv] / cell, 1e-3)
    mass = sigmoid(g['alpha'][near]) * 2 * math.pi * su * sv    # alpha x footprint, in cells
    cu, cv = np.floor(pu).astype(int), np.floor(pv).astype(int)
    D = np.zeros(nv * nu)
    for du in range(-3, 4):                                # big splats spread over up to 3 cells each way; the tail is negligible
        fu = _cdf((cu + du + 1 - pu) / su) - _cdf((cu + du - pu) / su)
        for dv in range(-3, 4):
            m = mass * fu * (_cdf((cv + dv + 1 - pv) / sv) - _cdf((cv + dv - pv) / sv))
            jj, ii = cu + du, cv + dv; ok = (jj >= 0) & (jj < nu) & (ii >= 0) & (ii < nv) & (m > 1e-7)
            D += np.bincount(ii[ok] * nu + jj[ok], weights=m[ok], minlength=nv * nu)
    # colour donors: clearly visible splats on the surface itself, not furniture standing in front of it
    on = near & (np.abs(d) < WALL_BEHIND) & (sigmoid(g['alpha']) >= 0.3)
    # On walls, only above furniture height: below it, what touches a wall is mostly desks, shelves and the floor's
    # edge, whose colour isn't the wall's. A wall seen only down there borrows from the other walls instead.
    if n_ax != 1: on &= p[:, 1] > WALL_DONOR_Y
    ju = ((p[on, iu] - u0) / cell).astype(int); iv_ = ((p[on, iv] - v0) / cell).astype(int)
    ok = (ju >= 0) & (ju < nu) & (iv_ >= 0) & (iv_ < nv)
    rgb = np.clip(0.5 + 0.282095 * g['color'][on][ok], 0, 1); cid = iv_[ok] * nu + ju[ok]; order = np.argsort(cid, kind='stable')
    starts = np.searchsorted(cid[order], np.arange(nv * nu)); counts = np.bincount(cid, minlength=nv * nu)
    return D.reshape(nv, nu), (rgb[order], starts, counts.reshape(nv, nu))


def fill_surface(g, surf, holes, donors, fallback, cell, rng):
    """Synthesise flat splats on a wall or ceiling where it has holes, coloured like the real surface nearby.

    The floor fill copies single splats, which suits carpet. Copied that way onto walls, the result looked like
    gravel: every desk, door or shelf touching a wall lends its colour as specks. Walls are mostly plain paint, so
    each hole cell instead takes the median of several nearby seen cells' mean colours (a lone desk is outvoted),
    blended smoothly into the real surface around it; on top of that it keeps half of one nearby real splat's
    deviation from its cell, so the grain of the real surface carries over. Donors come from the same surface, as
    near as possible; a surface the Scan never saw borrows from the nearest real surface (`fallback`).
    """
    _, n_ax, w, _, (iu, u0, u1), (iv, v0, v1) = surf
    srgb, sstart, scount = donors; nv, nu = holes.shape
    ci, cj = np.nonzero(holes); m = len(ci); per = WALL_PER; n = m * per
    if n == 0: return 0
    cnt = scount.ravel(); has = scount > 0
    cid = np.repeat(np.arange(nv * nu), cnt)                    # donors are sorted by cell
    cmean = np.stack([np.bincount(cid, weights=srgb[:, c], minlength=nv * nu) for c in range(3)], 1) / np.maximum(cnt, 1)[:, None]
    K = 8; got = np.full((m, K, 3), np.nan); ng = np.zeros(m, int); first = np.full(m, -1)
    if len(srgb) >= 50:                                        # a handful of donors is noise, not a surface
        for radius in (2, 4, 8, 16, 32, 64):                   # in cells: ~0.16 m up to the whole surface
            for _ in range(8):
                k = np.nonzero(ng < K)[0]
                if not len(k): break
                sv_ = np.clip(ci[k] + rng.integers(-radius, radius + 1, len(k)), 0, nv - 1)
                su_ = np.clip(cj[k] + rng.integers(-radius, radius + 1, len(k)), 0, nu - 1)
                ok = has[sv_, su_]; kk = k[ok]; cells = (sv_ * nu + su_)[ok]
                got[kk, ng[kk]] = cmean[cells]; first[kk] = np.where(first[kk] < 0, cells, first[kk]); ng[kk] += 1
    col = np.zeros((m, 3)); seen = ng > 0
    if seen.any(): col[seen] = np.nanmedian(got[seen], axis=1)
    if (~seen).any():
        if not len(fallback): return 0                         # nothing real to copy from anywhere: leave the hole
        col[~seen] = np.median(fallback[rng.integers(0, len(fallback), (int((~seen).sum()), 16))], axis=1)
    # blend: hole cells relax toward their neighbours, seen cells hold their real colour, unseen-but-covered cells abstain
    C = np.zeros((nv, nu, 3)); C[has] = cmean.reshape(nv, nu, 3)[has]; C[ci, cj] = col
    W = (has | holes).astype(float)
    for _ in range(12):
        P, Q = np.pad(C * W[..., None], ((1, 1), (1, 1), (0, 0))), np.pad(W, 1)
        num = P[:-2, 1:-1] + P[2:, 1:-1] + P[1:-1, :-2] + P[1:-1, 2:]; den = Q[:-2, 1:-1] + Q[2:, 1:-1] + Q[1:-1, :-2] + Q[1:-1, 2:]
        avg = num / np.maximum(den, 1e-9)[..., None]
        C = np.where((holes & (den > 0))[..., None], 0.5 * C + 0.5 * avg, C)
    cv, cu = np.repeat(ci, per), np.repeat(cj, per); fc = np.repeat(first, per)
    rgb = C[cv, cu]
    d = fc >= 0                                                # grain: half of a nearby real splat's deviation from its cell
    pick = sstart.ravel()[fc[d]] + (rng.random(d.sum()) * cnt[fc[d]]).astype(int)
    rgb[d] += 0.5 * (srgb[pick] - cmean[fc[d]])
    rgb = np.clip(rgb + rng.normal(0, 0.01, (n, 3)), 0, 1)
    pos = np.zeros((n, 3)); pos[:, n_ax] = w
    pos[:, iu] = np.clip(u0 + (cu + rng.random(n)) * cell, u0, u1); pos[:, iv] = np.clip(v0 + (cv + rng.random(n)) * cell, v0, v1)
    scale = np.full((n, 3), math.log(WALL_SIGMA * cell)); scale[:, n_ax] = math.log(0.002)
    new = {
        'pos': pos.astype(np.float32), 'scale': scale.astype(np.float32),
        'rot': np.tile(np.array([0, 0, 0, 1], np.float32), (n, 1)),
        'alpha': np.full(n, 1.5, np.float32),              # like the floor fill: slightly see-through, as real scanned walls are
        'color': ((rgb - 0.5) / 0.282095).astype(np.float32),
        'sh': np.zeros((n, g['sh'].shape[1]), np.float32),  # no view-dependent colour: it would be invented
    }
    for k in new: g[k] = np.concatenate([g[k], new[k]])
    return n


def fill_walls_ceiling(g, box, walls, ceiling, rng):
    """Measure coverage on the 4 walls and the ceiling, and fill the holes of the ones asked for.

    Returns per-surface (name, area m², missing m², splats added). Coverage is measured on the real splats only,
    before anything is added, so one surface's fill never counts as another's coverage.
    """
    sig = axis_sigmas(g); cell = WALL_CELL; surfs = room_surfaces(box)
    measured = []
    for surf in surfs:
        D, donors = surface_coverage(g, sig, surf, cell)
        # A thin cell inside a well-seen surface is just sampling noise; a hole is thin together with its neighbours.
        # (capped, so one very dense row, like the floor's edge, can't vouch for the empty cells beside it)
        P = np.pad(np.minimum(D, 2 * COVERED), 1, mode='edge'); hood = sum(P[i:i + D.shape[0], j:j + D.shape[1]] for i in range(3) for j in range(3)) / 9
        holes = (D < COVERED) & (hood < 1.5 * COVERED)
        # the last row and column may stick out past the surface; count only the part that's on it
        (_, _, _, _, (_, u0, u1), (_, v0, v1)) = surf
        fu = np.minimum(1, (u1 - u0) / cell - np.arange(D.shape[1])); fv = np.minimum(1, (v1 - v0) / cell - np.arange(D.shape[0]))
        area = np.outer(fv, fu) * cell * cell
        measured.append((surf, holes, donors, area))
    report = []
    wall_rgb = [m[2][0] for m in measured[:4]]
    for k, (surf, holes, donors, area) in enumerate(measured):
        name = surf[0]; is_wall = k < 4
        if is_wall:   # the nearest real surface to a wall is a wall sharing a corner with it, then the opposite one
            fallback = np.concatenate([wall_rgb[j] for j in range(4) if (j < 2) != (k < 2)])
            if len(fallback) < 50: fallback = np.concatenate([wall_rgb[j] for j in range(4) if j != k])
        else:         # and to the ceiling, the tops of the walls
            y1 = box['ceiling_y']; tops = []
            for (s2, _, (srgb, sstart, scount), _) in measured[:4]:
                rows = np.arange(scount.shape[0]); top = (rows + 1) * cell > y1 - 0.6
                cells = np.nonzero(np.repeat(top[:, None], scount.shape[1], 1).ravel() & (scount.ravel() > 0))[0]
                tops += [srgb[sstart[c]:sstart[c] + scount.ravel()[c]] for c in cells]
            fallback = np.concatenate(tops) if tops else np.concatenate(wall_rgb)
        added = fill_surface(g, surf, holes, donors, fallback, cell, rng) if (walls if is_wall else ceiling) else 0
        report.append((name, float(area.sum()), float(area[holes].sum()), added))
    return report


NEEDLE_ANISO = 8.0     # a needle is this many times longer than it is wide ...
NEEDLE_SIZE = 0.05     # ... and at least this long (1 sigma, metres); real thin things (chair legs, frames) use many small splats
GHOST_SIZE = 0.03      # splats bigger than this (1 sigma) outside the Room's box are ghosts, not wall detail
OUTSIZED_MIN, OUTSIZED_REL = 0.05, 10.0   # inside the Room: at least 5 cm and 10x the Scan's own median splat


def suppress_ghosts(g, box, keep_background, stats):
    """Remove or tame the colourful smears a phone leaves where it barely looked.

    The phone's guesses at surfaces it saw only once or twice are big, lone, often very opaque splats, many of
    them floating behind the walls, whose view-dependent colour (SH) was fitted to a couple of frames and turns
    pastel from anywhere else. Real detail is the opposite: small splats in crowds. So:
      - needles (long, thin and large) go;
      - big or lonely splats beyond the walls or above the ceiling go: they're outside the Room, and the wall
        filling covers where they were;
      - outsized, fairly opaque smears inside the Room go too (>= 5 cm and >= 10x the Scan's median splat);
      - lonely or biggish splats inside the Room stay, but lose their view-dependent colour.
    Returns how many splats had their SH tamed.
    """
    s = np.sort(np.exp(g['scale']), 1); big = s[:, 2]
    bg = (big > 2.0) & keep_background                       # the scanning app's backdrop, if asked to keep it
    keep(g, ~((big / np.maximum(s[:, 1], 1e-6) > NEEDLE_ANISO) & (big > NEEDLE_SIZE)) | bg, 'ghosts: needles', stats)
    p = g['pos']; big = np.exp(g['scale']).max(1); bg = (big > 2.0) & keep_background
    out = np.max([box['min_x'] - p[:, 0], p[:, 0] - box['max_x'], box['min_z'] - p[:, 2], p[:, 2] - box['max_z'], p[:, 1] - box['ceiling_y']], 0)
    hood = neighbourhood_counts(p, 0.1); lonely = hood < 0.02 * np.median(hood)
    keep(g, ~((out > 0.05) & ((big > GHOST_SIZE) | lonely)) | bg, 'ghosts: big or lonely splats beyond the walls', stats)
    # Inside the Room, size relative to the Scan's own typical splat tells smears from soft walls: renders of the first
    # real Scan lost two glowing blobs and nothing else, and the wall filling covers where they were.
    big = np.exp(g['scale']).max(1); bg = (big > 2.0) & keep_background
    outsized = (big >= max(OUTSIZED_MIN, OUTSIZED_REL * np.median(big))) & (sigmoid(g['alpha']) > 0.3)
    keep(g, ~outsized | bg, 'ghosts: outsized smears inside the Room', stats)
    if g['sh_degree'] == 0: return 0
    p = g['pos']; big = np.exp(g['scale']).max(1); hood = neighbourhood_counts(p, 0.1)
    # SH fades out as a splat gets lonelier (under 5% of a typical neighbourhood) or bigger (2 to 5 cm)
    f = np.clip(hood / (0.05 * np.median(hood)), 0, 1) * np.clip((0.05 - big) / 0.03, 0, 1)
    g['sh'] *= f[:, None].astype(np.float32)
    return int((f < 1).sum())


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
    ap.add_argument('--keep-background', action='store_true', help='keep the distant backdrop the scanning app wraps around the scan, instead of a black void')
    ap.add_argument('--no-square', action='store_true', help="don't turn the room so its walls run along x and z")
    ap.add_argument('--no-fill-floor', action='store_true', help="don't synthesise floor where the Scan has holes")
    ap.add_argument('--fill-cell', type=float, default=0.04, help='floor-filling grid size (metres)')
    ap.add_argument('--fill-close', type=float, default=0.3, help='seal floor gaps up to this wide at the room edges (metres)')
    ap.add_argument('--no-fill-walls', action='store_true', help="don't synthesise wall where the Scan missed it")
    ap.add_argument('--no-fill-ceiling', action='store_true', help="don't synthesise ceiling where the Scan missed it")
    ap.add_argument('--keep-ghosts', action='store_true', help="don't remove needles, blobs behind the walls or outsized smears, or fade lone splats' shine")
    # Default 1: renders of the first real Scan looked the same at degree 3 and 1 once ghosts were dealt with, the file is
    # ~25% smaller, and the high bands, fitted to the phone's path, are the first to go wrong where Students look from.
    ap.add_argument('--sh-degree', type=int, default=1, choices=(0, 1, 2, 3), help='keep view-dependent colour up to this degree (default 1; 3 = all a Scan has; 0 = same as --no-sh)')
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
    # Big splats inside the room are real: phones record walls and ceilings as large, soft splats.
    # Only big splats outside the room are junk (the background "sky" scans add around everything).
    size = np.exp(g['scale']).max(1); p = g['pos']
    lo, hi = np.percentile(p, 0.5, axis=0) - 0.3, np.percentile(p, 99.5, axis=0) + 0.3
    inside = ((p >= lo) & (p <= hi)).all(1)
    backdrop = (size > 2.0) & ~inside                       # the distant backdrop scanning apps wrap around a scan
    keep(g, (size <= a.max_size) | inside | (backdrop & a.keep_background), f'larger than {a.max_size} m and outside the room', stats)
    log('Removing floaters …')
    big = np.exp(g['scale']).max(1) > 0.09                  # large splats sit far apart by nature; don't call them lonely
    keep(g, components(g['pos'], 0.15, 0.01) | big, 'floaters (detached clumps)', stats)
    big = np.exp(g['scale']).max(1) > 0.09
    keep(g, dense_enough(g['pos'], 0.06, 0.03) | big, 'floaters (lonely small splats near surfaces)', stats)

    log('Finding the floor …')
    f = find_floor(g['pos'], rng, a.floor_tol)
    if f is None: sys.exit('Could not find a floor. Is this a room scan? (A scan of a single object has no floor.)')
    n, d, _ = f
    tilt = level(g, n, a.keep_sh)
    _, _, inl = find_floor(g['pos'], rng, a.floor_tol)
    floor_y = float(np.median(inl[:, 1])); g['pos'][:, 1] -= floor_y
    log(f'  floor found; scan was tilted {tilt:.1f}°, now level at y = 0')
    keep(g, (g['pos'][:, 1] >= -0.08) | ((np.exp(g['scale']).max(1) > 2.0) & a.keep_background), 'below the floor (shiny-floor reflections)', stats)
    if not a.no_square:
        turn = square_up(g, a.floor_tol, a.keep_sh)
        if turn: log(f'  room squared up: turned {abs(turn):.1f}° so its walls run along x and z')

    p = g['pos']; small = np.exp(g['scale']).max(1) <= 2.0
    lo = np.percentile(p[small], 0.3, axis=0) - 0.25; hi = np.percentile(p[small], 99.7, axis=0) + 0.25
    within = (p[:, 0] >= lo[0]) & (p[:, 0] <= hi[0]) & (p[:, 2] >= lo[2]) & (p[:, 2] <= hi[2]) & (p[:, 1] <= hi[1])
    keep(g, within | (~small & a.keep_background), 'outside the room', stats)
    cap = 0 if a.no_sh else a.sh_degree
    if g['sh_degree'] > cap:
        g['sh'] = g['sh'].reshape(len(g['sh']), -1, 3)[:, :(cap + 1) ** 2 - 1].reshape(len(g['sh']), -1); g['sh_degree'] = cap
    if a.max_splats and len(g['pos']) > a.max_splats:
        imp = sigmoid(g['alpha']) * np.exp(g['scale'].sum(1))
        keep(g, imp >= np.partition(imp, -a.max_splats)[-a.max_splats], f'over the {a.max_splats:,} cap (least visible)', stats)

    fl = g['pos'][np.abs(g['pos'][:, 1]) < a.floor_tol]
    bx = np.percentile(fl[:, 0], [1, 99]); bz = np.percentile(fl[:, 2], [1, 99])
    cx, cz = bx.mean(), bz.mean(); g['pos'][:, 0] -= cx; g['pos'][:, 2] -= cz
    bounds = [float(bx[0] - cx), float(bx[1] - cx), float(bz[0] - cz), float(bz[1] - cz)]
    height = float(np.percentile(g['pos'][:, 1], 99.5))
    box = room_box(g, a.floor_tol, height); height = box['ceiling_y']
    # The box only means something for a roughly rectangular room whose walls reach a plausible height.
    fz, fx = np.percentile(fl[:, 2], [0.5, 99.5]), np.percentile(fl[:, 0], [0.5, 99.5])
    H, _, _ = np.histogram2d(fl[:, 2], fl[:, 0], [np.arange(fz[0], fz[1] + 0.1, 0.1), np.arange(fx[0], fx[1] + 0.1, 0.1)])
    boxy = (H > 0).mean() >= 0.7 and height >= 1.8
    if not boxy: log('  room is not a box, or its walls were barely scanned: not judging walls, ceiling or ghosts behind them')

    tamed = 0
    if not a.keep_ghosts:
        log('Suppressing ghosts …')
        if boxy: tamed = suppress_ghosts(g, box, a.keep_background, stats)
        else:
            s = np.sort(np.exp(g['scale']), 1)
            keep(g, ~((s[:, 2] / np.maximum(s[:, 1], 1e-6) > NEEDLE_ANISO) & (s[:, 2] > NEEDLE_SIZE)), 'ghosts: needles', stats)

    filled = 0
    if not a.no_fill_floor:
        log('Filling holes in the floor …')
        filled, footprint, flo = fill_floor(g, a.fill_cell, a.fill_close, a.floor_tol, rng)
        log(f'  filled {filled * a.fill_cell ** 2:.2f} m² of missing floor' if filled else '  no holes found')
    else:
        flo, footprint = floor_grid(g, a.fill_cell, a.floor_tol)[:2]
    surfaces = []
    if boxy:
        log('Checking walls and ceiling …')
        surfaces = fill_walls_ceiling(g, box, not a.no_fill_walls, not a.no_fill_ceiling, rng)
    # Walls keyed by the side of the room box they're on, so a Curator (or the Scan report) can tell which wall is synthetic.
    filled_m2 = {name: (m if n else 0.0) for name, _, m, n in surfaces}
    synthesized = {'floor_m2': round(filled * a.fill_cell ** 2, 2),
                   'walls_m2': {side: round(filled_m2.get(f'{side.replace("-", "−")} wall', 0.0), 2) for side in ('-z', '+x', '+z', '-x')},
                   'ceiling_m2': round(filled_m2.get('ceiling', 0.0), 2)}
    walls_total = sum(synthesized['walls_m2'].values())

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
        'synthesized': synthesized,   # ADR-0003: how much of the Appearance was filled in rather than scanned
        # The planes the wall and ceiling fill sits on. Synthesized splats are flat discs, 2 mm thick, aligned to these
        # planes (floor fill: to y = 0), with no view-dependent colour, so they can be told apart from real ones.
        'room_box': {k: round(v, 3) for k, v in box.items()} if boxy else None,
        'tables': [], 'seats': [], 'boards': [],
        'note': 'Starter Layout from clean_scan.py. A Room Curator still places tables, seats and Boards.',
    }
    with open(os.path.join(out, base + '.layout.json'), 'w') as fh: json.dump(layout, fh, indent=2)

    log('\nRemoved:')
    for why, k in stats:
        if k: log(f'  {k:>10,}  {why}')
    if tamed: log(f'  {tamed:>10,}  had their view-dependent colour faded (lonely or oversized splats)')
    if filled: log(f'Added {filled * FILL_PER:,} floor splats to fill {filled * a.fill_cell ** 2:.2f} m² of holes')
    for name, _, m, n in surfaces:
        if n: log(f'Added {n:,} {name} splats to fill {m:.2f} m² it was missing')
    log(f"Synthesized: floor {synthesized['floor_m2']:.2f} m², walls {walls_total:.2f} m², ceiling {synthesized['ceiling_m2']:.2f} m²")
    n_real = len(g['pos']) - filled * FILL_PER - sum(n for *_, n in surfaces)
    log(f'\nKept {n_real:,} of {n0:,} splats ({100 * n_real / n0:.0f}%), SH degree {g["sh_degree"]}; {len(g["pos"]):,} in all with the synthesized ones')
    # ADR-0003: say what the Scan missed, so the next one can be better. Repair is no substitute for scanning well.
    log('\nScan report (what the Scan missed):')
    fl_m2 = synthesized['floor_m2'] if not a.no_fill_floor else None
    log(f'  floor    {"not checked" if fl_m2 is None else f"{fl_m2:.2f} m² of holes"}')
    for name, area, m, _ in surfaces:
        log(f'  {name:<8} {100 * m / max(area, 1e-9):3.0f}% missing ({m:.1f} of {area:.1f} m²)')
    advice = [name for name, area, m, _ in surfaces if m > 0.25 * area] + (['floor'] if (fl_m2 or 0) > 1 else [])
    if not boxy: log('  walls and ceiling not checked (not a box-shaped room, or walls barely scanned)')
    log(f'  → rescan if you can: {", ".join(advice)}' if advice else '  → good coverage, no rescan needed')
    log(f'Room footprint {bounds[1]-bounds[0]:.2f} × {bounds[3]-bounds[2]:.2f} m, {height:.2f} m tall  ← sanity-check against the real room')
    src_mb = os.path.getsize(a.scan) / 1e6
    log(f'Files: {os.path.basename(ply)} {os.path.getsize(ply)/1e6:.1f} MB · {os.path.basename(spzf)} {os.path.getsize(spzf)/1e6:.1f} MB (from {src_mb:.1f} MB) · preview + layout in {out}')
    log(f'Done in {time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Scan quality report: tells a Room Curator, in plain language, what a cleaned Scan captured and missed,
whether it measures like a real room, and what to do better on the next Scan.

Usage:  python scan_report.py <cleaned .clean.ply or .spz> <layout.json> [--raw <original scan>]
                              [--html report.html] [--renders views.png] [--json report.json]

It checks, on the Room box from layout.json (squared up, floor at y = 0, walls along x and z):
  coverage   what share of the floor, each of the 4 walls and the ceiling has real splats on it, plus whatever
             layout.json["synthesized"] says the cleanup filled in (ADR-0003)
  scale      the footprint and height, flagged if they're implausible for a room
  artifacts  needle-shaped streaks, huge blobs and translucent fuzz
and ends with a verdict ("good", "usable" or "rescan recommended") and advice tied to docs/scanning-guide.md.
--raw adds what the cleanup removed from the original Scan. --renders embeds a contact sheet from
render_views.mjs in the HTML page.

Needs: numpy, pillow, and Niantic's spz bindings (see README.md).
"""
import argparse, base64, html, io, json, math, os, sys

import numpy as np

CELL = 0.1   # coverage grid size in metres: fine enough to see a missed patch, coarse enough to ignore sampling noise

# Display names follow the app's convention: yaw 0 looks toward −z, so −z is "front" and +x is "right".
SURFACES = [('floor', 'floor'), ('wall_-z', 'front wall (−z)'), ('wall_+x', 'right wall (+x)'),
            ('wall_+z', 'back wall (+z)'), ('wall_-x', 'left wall (−x)'), ('ceiling', 'ceiling')]
NAMES = dict(SURFACES)
WALLS = [k for k, _ in SURFACES if k.startswith('wall')]

# What share of a surface must be covered. Walls and ceilings get more slack than the floor: doors, windows and
# lights are real gaps, and a phone sees the floor far more than anything else.
THRESHOLDS = {'floor': (0.90, 0.70), 'wall': (0.70, 0.35), 'ceiling': (0.60, 0.25)}   # (good, at least usable)

# Artifact definitions, and the share of all splats at which each starts to show (warn) or ruins views (severe).
NEEDLE_LEN, NEEDLE_RATIO = 0.03, 10.0   # longest axis >= 3 cm and >= 10x the middle one: a visible streak
HUGE_LEN = 0.5                          # longest axis (1 sigma) over half a metre: a blurry blob a metre or more across
# Ghost smears: splats far bigger than the Scan's own typical splat, and opaque enough to show. They grow where the phone
# barely looked (ADR-0003) and blur whole views even when there are only a few hundred, so they are judged by the area
# they cover compared with the floor, not by their share of the splat count.
SMEAR_MIN, SMEAR_REL = 0.05, 10.0       # longest axis >= 5 cm and >= 10x the Scan's median longest axis
SMEAR_LIMITS = (0.25, 1.0)              # smeared area as a multiple of the floor area: warn, severe
FUZZ_ALPHA = 0.10                       # opacity under 10%: haze that dims what's behind it but shows nothing itself
ARTIFACT_LIMITS = {'needles': (0.005, 0.03), 'huge': (0.005, 0.03), 'fuzz': (0.05, 0.15), 'below_floor': (0.01, 0.05)}

GUIDE = 'docs/scanning-guide.md'


# ---------------------------------------------------------------- loading

def sigmoid(x): return 1 / (1 + np.exp(-x))


def load(path):
    """Positions, scales in metres (`scale` sorted small to large per splat, `scale_xyz` per axis), opacity and rotation."""
    import spz   # imported here so the pure analysis functions can be tested and reused without the native library
    opts = spz.UnpackOptions(); opts.to_coord = spz.CoordinateSystem.RUB   # three.js convention, as clean_scan.py writes
    cloud = spz.load_splat_from_ply(path, opts) if path.lower().endswith('.ply') else spz.load_spz(path, opts)
    n = cloud.num_points
    xyz = np.exp(np.asarray(cloud.scales, np.float32).reshape(n, 3))
    g = {'pos': np.asarray(cloud.positions, np.float32).reshape(n, 3),
         'scale': np.sort(xyz, 1), 'scale_xyz': xyz,
         'alpha': sigmoid(np.asarray(cloud.alphas, np.float32).reshape(n)),
         'rot': np.asarray(cloud.rotations, np.float32).reshape(n, 4)}
    return finite(g)


def finite(g):
    ok = np.isfinite(g['pos']).all(1) & np.isfinite(g['scale']).all(1) & np.isfinite(g['alpha'])
    return {k: v[ok] for k, v in g.items()}


def smear_mask(g):
    longest = g['scale'][:, 2]
    if not len(longest): return np.zeros(0, bool)
    # Relative to this Scan's own splats: an app that records walls as big soft splats isn't smearing.
    return (longest >= max(SMEAR_MIN, SMEAR_REL * float(np.median(longest)))) & (g['alpha'] >= 0.2)


def footprint_area(g):
    """Opacity-weighted footprint of each splat: an ellipse 2 sigma out along its two largest axes."""
    s = g['scale']; return math.pi * 4 * s[:, 2] * s[:, 1] * g['alpha']


def synthesized_floor_mask(g):
    """Splats that clean_scan.py's floor filling made rather than the phone saw.

    Filled splats are flat, round, axis-aligned discs exactly at y = 0 with a 2 mm thickness. Real splats are never
    all of that at once, so this signature finds them in old and new files alike (their size and opacity changed
    between versions, their shape didn't) without needing the cleanup to have recorded them.
    """
    p, q = g['pos'], g['rot']
    sx, sy, sz = g['scale_xyz'].T
    return ((np.abs(p[:, 1]) < 2e-3) & (np.abs(q[:, 3]) > 0.99999)
            & (np.abs(sy - 0.002) < 0.0004) & (np.abs(sx / np.maximum(sz, 1e-9) - 1) < 0.03) & (sx > 0.005))


# ---------------------------------------------------------------- coverage

def _accumulate(u, v, area, nu, nv, u0, v0, radius):
    """Per-cell splat count and fill (sum of opacity x footprint area / cell area) on a CELL grid.

    A splat bigger than a cell covers its neighbours too, so it is spread over the square of cells it spans:
    otherwise a wall a phone recorded as a few large soft splats would look mostly empty.
    """
    count = np.zeros((nv, nu)); fill = np.zeros((nv, nu))
    iu = np.floor((u - u0) / CELL).astype(np.int64); iv = np.floor((v - v0) / CELL).astype(np.int64)
    k = np.clip(np.round(radius / CELL), 0, 5).astype(np.int64)
    for kk in np.unique(k):
        m = k == kk; n = (2 * kk + 1) ** 2
        for dv in range(-kk, kk + 1):
            for du in range(-kk, kk + 1):
                a, b = iu[m] + du, iv[m] + dv
                ok = (a >= 0) & (a < nu) & (b >= 0) & (b < nv)
                np.add.at(count, (b[ok], a[ok]), 1)
                np.add.at(fill, (b[ok], a[ok]), area[m][ok] / n)
    return count, fill / CELL ** 2


def _covered(count, fill):
    # Covered means the cell visibly shows something: a few splats whose opacity-weighted footprints add up to at
    # least half the cell. Real scans are strongly bimodal here (hundreds of splats or none), so the exact numbers
    # matter little.
    return (count >= 3) & (fill >= 0.5)


def surface_grids(g, layout, synthetic=None, ignore=None):
    """Coverage grid for each plane of the Room box. Returns {key: dict(real, any, counted, shape info)}.

    `synthetic` splats count as "any" but not "real"; `ignore` (ghost smears) counts as neither, since a smear in
    front of a missing wall doesn't show the wall.
    """
    b = layout['bounds']; H = float(layout['height'])
    x0, x1, z0, z1 = b['min_x'], b['max_x'], b['min_z'], b['max_z']
    p, s = g['pos'], g['scale']
    syn = np.zeros(len(p), bool) if synthetic is None else synthetic
    keep = np.ones(len(p), bool) if ignore is None else ~ignore
    # Flat splats lie in their surface, so their two largest axes are what shows; ignoring orientation keeps this
    # cheap and only overstates edge-on splats slightly.
    area = footprint_area(g)
    radius = np.minimum(2 * s[:, 2], 0.5)
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    margin = 0.25   # the strip of each plane nearest a neighbouring plane, where that plane's splats would count too

    def plane(sel, u, v, u0, u1, v0, v1, counted):
        nu, nv = max(1, int(math.ceil((u1 - u0) / CELL))), max(1, int(math.ceil((v1 - v0) / CELL)))
        res = {}
        for name, m in (('any', sel & keep), ('real', sel & keep & ~syn)):
            res[name] = _covered(*_accumulate(u[m], v[m], area[m], nu, nv, u0, v0, radius[m]))
        uc = u0 + (np.arange(nu) + 0.5) * CELL; vc = v0 + (np.arange(nv) + 0.5) * CELL
        res['counted'] = counted(uc[None, :], vc[:, None]) & np.ones((nv, nu), bool)
        res['v_centres'] = vc
        res['extent'] = (u0, u1, v0, v1)
        return res

    out = {}
    out['floor'] = plane(np.abs(y) < 0.05, x, z, x0, x1, z0, z1, lambda u, v: np.ones_like(u * v, bool))
    out['ceiling'] = plane(np.abs(y - H) < 0.3, x, z, x0, x1, z0, z1,
                           lambda u, v: (u > x0 + margin) & (u < x1 - margin) & (v > z0 + margin) & (v < z1 - margin))
    # Walls: the floor bounds are percentiles of the floor, so a real wall stands a little outside them; the slab
    # reaches further out than in. Anything real within it (a wall, or a shelf against it) is what Students see there.
    wall_band = (y > 0.05) & (y < H - 0.15)
    for key, axis, at, sign in (('wall_-x', 0, x0, -1), ('wall_+x', 0, x1, 1), ('wall_-z', 2, z0, -1), ('wall_+z', 2, z1, 1)):
        d = (p[:, axis] - at) * sign            # > 0 is outside the floor bounds
        sel = wall_band & (d > -0.35) & (d < 0.45)
        o = 2 if axis == 0 else 0
        lo, hi = (z0, z1) if axis == 0 else (x0, x1)
        out[key] = plane(sel, p[:, o], y, lo, hi, 0.0, H,
                         lambda u, v, lo=lo, hi=hi: (u > lo + margin) & (u < hi - margin) & (v > 0.1) & (v < H - 0.2))
    return out


def coverage(grids, layout):
    """Shares of each surface covered by real splats, and by anything (real or synthesized)."""
    syn_rec = synthesized_record(layout)
    per_surface = dict(syn_rec['surfaces'])
    if syn_rec['other'].get('walls'):
        # One total for all walls: share it out by how much of each wall looks covered, since a synthesized patch
        # can only be where something now shows.
        shown = {k: float((grids[k]['any'] & grids[k]['counted']).mean()) * _area(grids[k]) for k in WALLS}
        tot = sum(shown.values()) or 1.0
        for k in WALLS: per_surface[k] = per_surface.get(k, 0.0) + syn_rec['other']['walls'] * shown[k] / tot
    res = {}
    for key, gr in grids.items():
        c = gr['counted']; n = max(1, int(c.sum()))
        area = _area(gr)
        real = float((gr['real'] & c).sum()) / n; anything = float((gr['any'] & c).sum()) / n
        recorded = per_surface.get(key, 0.0)
        # A synthesized patch we can't tell apart from real splats (anything but clean_scan's floor fill) would
        # count as real; take what the cleanup says it made off the measured coverage instead.
        if recorded and anything - real < 0.5 * recorded / area:
            real = max(0.0, anything - recorded / area)
        r = {'name': NAMES[key], 'area_m2': area, 'real': real, 'any': anything, 'synthesized_m2': recorded,
             'missing_m2': (1 - max(real, 0)) * area}
        if key.startswith('wall'):   # a phone pointed at furniture catches the bottom of a wall but not the top
            vc = gr['v_centres'][:, None] * np.ones_like(c, float)
            for half, m in (('lower', vc < 1.2), ('upper', vc >= 1.2)):
                k = c & m; res_k = float((gr['real'] & k).sum()) / max(1, int(k.sum()))
                r[half] = res_k
        res[key] = r
    return res


def _area(gr):
    e = gr['extent']; return (e[1] - e[0]) * (e[3] - e[2])


def synthesized_record(layout):
    """Normalise layout.json["synthesized"], which may be missing, {surface: m2}, {surface: {m2: ..}} or a list.

    Another workstream defines this field, so accept the shapes it could reasonably take rather than one exact form.
    """
    raw = layout.get('synthesized')
    out = {'present': raw is not None, 'surfaces': {}, 'other': {}}
    if raw is None: return out
    items = []
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, list):
        for it in raw:
            if isinstance(it, dict):
                items.append((str(it.get('surface') or it.get('name') or it.get('kind') or 'other'), it))

    def m2(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool): return float(v)
        if isinstance(v, dict):
            for k in ('m2', 'area_m2', 'square_metres', 'square_meters', 'area', 'sq_m'):
                if isinstance(v.get(k), (int, float)): return float(v[k])
        return None

    for name, v in items:
        key = _surface_key(name)
        val = m2(v)
        if isinstance(v, dict) and val is None and key == 'walls':   # {"walls": {"-x": 1.2, ...}}
            for sub, sv in v.items():
                k2 = _surface_key('wall ' + sub)
                if k2 in NAMES and m2(sv) is not None: out['surfaces'][k2] = out['surfaces'].get(k2, 0) + m2(sv)
            continue
        if val is None: continue
        if key in NAMES: out['surfaces'][key] = out['surfaces'].get(key, 0) + val
        elif key == 'walls': out['other']['walls'] = out['other'].get('walls', 0) + val
        else: out['other'][name] = out['other'].get(name, 0) + val
    return out


def _surface_key(name):
    n = str(name).lower().replace('−', '-').replace('_', ' ')
    if 'floor' in n: return 'floor'
    if 'ceil' in n: return 'ceiling'
    if 'wall' in n or n.strip() in ('-x', '+x', '-z', '+z', 'left', 'right', 'front', 'back'):
        for tokens, key in ((('-x', 'min x', 'minx', 'left', 'west'), 'wall_-x'), (('+x', 'max x', 'maxx', 'right', 'east'), 'wall_+x'),
                            (('-z', 'min z', 'minz', 'front', 'north'), 'wall_-z'), (('+z', 'max z', 'maxz', 'back', 'south'), 'wall_+z')):
            if any(t in n for t in tokens): return key
        return 'walls'
    return n


# ---------------------------------------------------------------- scale and artifacts

def scale_check(layout, cov):
    b = layout['bounds']; H = float(layout['height'])
    w, d = b['max_x'] - b['min_x'], b['max_z'] - b['min_z']
    short, long_ = min(w, d), max(w, d)
    ceiling_seen = cov['ceiling']['real'] >= THRESHOLDS['ceiling'][1]
    flags = []   # (level, message): level 'bad' means the measurements can't be right, 'warn' means check them

    if short < 1.2 or w * d < 2: flags.append(('bad', f'The footprint ({w:.2f} × {d:.2f} m) is too small for a room. The floor was probably misdetected.'))
    elif short < 2.0 or w * d < 4: flags.append(('warn', f'The footprint ({w:.2f} × {d:.2f} m) is very small for a study room. Check it against the real room.'))
    if long_ > 40: flags.append(('bad', f'The footprint ({w:.2f} × {d:.2f} m) is too big for one room: the Scan probably includes stray splats far away.'))
    elif long_ > 25: flags.append(('warn', f'The footprint is {long_:.1f} m long, which is big for a study room. Check that nothing outside the room was kept.'))
    if long_ / max(short, 1e-3) > 5: flags.append(('warn', f'The room is {long_ / short:.1f} times longer than it is wide, like a corridor. Check that the whole room was scanned.'))
    if ceiling_seen:
        if H < 1.8 or H > 10: flags.append(('bad', f'The ceiling height ({H:.2f} m) is impossible for a room. The floor or ceiling was misdetected.'))
        elif H < 2.2 or H > 6: flags.append(('warn', f'The ceiling height ({H:.2f} m) is unusual. Check it against the real room.'))
    else:
        flags.append(('note', f'The ceiling wasn\'t scanned, so the height ({H:.2f} m) is only the top of what was scanned, not a measured ceiling.'))
        if H < 1.8: flags.append(('warn', f'Nothing was scanned above {H:.2f} m, so the Room has no upper walls or ceiling at all.'))
    return {'width': w, 'depth': d, 'area': w * d, 'height': H, 'ceiling_measured': ceiling_seen, 'flags': flags}


def artifact_counts(g, layout=None):
    s, a, p = g['scale'], g['alpha'], g['pos']
    n = max(1, len(a))
    longest, middle = s[:, 2], s[:, 1]
    res = {'splats': len(a),
           'needles': int(((longest >= NEEDLE_LEN) & (longest >= NEEDLE_RATIO * np.maximum(middle, 1e-7))).sum()),
           'huge': int((longest >= HUGE_LEN).sum()),
           'fuzz': int((a < FUZZ_ALPHA).sum())}
    sm = smear_mask(g)
    res['smears'] = int(sm.sum()); res['smear_m2'] = float(footprint_area(g)[sm].sum())
    if layout is not None:   # only meaningful once the floor is levelled to y = 0
        res['below_floor'] = int((p[:, 1] < -0.05).sum())
        b = layout['bounds']; H = float(layout['height'])
        res['smear_vs_floor'] = res['smear_m2'] / max(1e-6, (b['max_x'] - b['min_x']) * (b['max_z'] - b['min_z']))
        if sm.any():   # where they are, by the nearest surface of the room box, so the advice can say where to look
            q = p[sm]; w = footprint_area(g)[sm]
            dist = np.stack([np.abs(q[:, 1]), np.abs(q[:, 2] - b['min_z']), np.abs(q[:, 0] - b['max_x']),
                             np.abs(q[:, 2] - b['max_z']), np.abs(q[:, 0] - b['min_x']), np.abs(q[:, 1] - H)], 1)
            near = np.bincount(np.argmin(dist, 1), weights=w, minlength=6)
            res['smears_near'] = SURFACES[int(np.argmax(near))][0]
            res['smears_near_share'] = float(near.max() / max(near.sum(), 1e-9))
    res['share'] = {k: res[k] / n for k in ('needles', 'huge', 'fuzz', 'below_floor', 'smears') if k in res}
    return res


def raw_summary(g_raw, g_clean):
    """What the cleanup removed. The raw Scan isn't levelled or squared up, so only shape-free counts compare."""
    r = artifact_counts(g_raw)
    r['backdrop'] = int((g_raw['scale'][:, 2] > 2.0).sum())   # the far-away backdrop scanning apps wrap around a Scan
    r['kept_share'] = len(g_clean['alpha']) / max(1, len(g_raw['alpha']))
    return r


# ---------------------------------------------------------------- verdict

def _level(key, share):
    good, usable = THRESHOLDS['wall' if key.startswith('wall') else key]
    return 'good' if share >= good else 'weak' if share >= usable else 'poor'


def assess(cov, scale, arts):
    """The verdict and the advice for the next Scan, each tied to a step of the scanning guide."""
    advice = []   # (priority, text): lower priority numbers are printed first
    levels = {k: _level(k, cov[k]['real']) for k in cov}

    fl = cov['floor']
    if levels['floor'] != 'good' or fl['missing_m2'] > 1.0:
        advice.append((2, f"{fl['missing_m2']:.1f} m² of the floor ({100 * (1 - fl['real']):.0f}%) wasn't scanned. Look under tables and "
                          f"behind chairs, and at the end step aside and scan the spot where you were standing ({GUIDE}, How to move, step 6)."))
    poor_walls = [k for k in WALLS if levels[k] == 'poor']
    weak_walls = [k for k in WALLS if levels[k] == 'weak']
    if poor_walls:
        names = _join([f"the {NAMES[k]} ({100 * cov[k]['real']:.0f}%)" for k in poor_walls])
        advice.append((1, f"{_cap(names)} {'is' if len(poor_walls) == 1 else 'are'} mostly missing. Sweep every wall from floor to ceiling, "
                          f"and walk the edge of the room first with the phone pointed into the room ({GUIDE}, How to move, steps 1 and 2)."))
    tops = [k for k in WALLS if k not in poor_walls and cov[k].get('lower', 0) >= 0.6 and cov[k].get('upper', 1) < 0.35]
    if tops:
        advice.append((3, f"The lower part of the {_join([NAMES[k] for k in tops])} is there, but above 1.2 m it's mostly missing. "
                          f"Tilt the phone up as you sweep each wall, all the way to the ceiling ({GUIDE}, How to move, step 2)."))
    if weak_walls:
        advice.append((4, f"The {_join([f'{NAMES[k]} ({100 * cov[k]['real']:.0f}%)' for k in weak_walls])} {'has' if len(weak_walls) == 1 else 'have'} gaps. "
                          f"Give {'it' if len(weak_walls) == 1 else 'them'} a slower second pass ({GUIDE}, How to move, steps 2 and 5)."))
    if levels['ceiling'] != 'good':
        advice.append((1 if levels['ceiling'] == 'poor' else 4,
                       f"The ceiling is {100 * cov['ceiling']['real']:.0f}% covered: point the phone up at the ceiling for a full pass ({GUIDE}, How to move, step 3)."))

    sh = arts['share']
    art_lv = {}
    for k, (warn, severe) in ARTIFACT_LIMITS.items():
        if k in sh: art_lv[k] = 'severe' if sh[k] >= severe else 'warn' if sh[k] >= warn else 'ok'
    if 'smear_vs_floor' in arts:
        r = arts['smear_vs_floor']
        art_lv['smears'] = 'severe' if r >= SMEAR_LIMITS[1] else 'warn' if r >= SMEAR_LIMITS[0] else 'ok'
        if art_lv['smears'] != 'ok':
            where = (f", mostly near the {NAMES[arts['smears_near']]}" if arts.get('smears_near_share', 0) >= 0.4 else '')
            advice.append((3 if art_lv['smears'] == 'severe' else 5,
                           f"{arts['smears']:,} smeared ghost splats blur {arts['smear_m2']:.0f} m² ({r:.1f}× the floor area){where}. They grow where the phone "
                           f"only glanced: look at every part of the room from more than one spot, slowly, with a third of each view overlapping "
                           f"the last ({GUIDE}, How to move, steps 2 and 5). Until then, delete them in SuperSplat."))
    if art_lv.get('needles', 'ok') != 'ok' or art_lv.get('fuzz', 'ok') != 'ok':
        advice.append((5, f"There is a lot of streaky or hazy noise ({100 * sh['needles']:.1f}% needle splats, {100 * sh['fuzz']:.1f}% near-invisible fuzz). "
                          f"Move more slowly and keep about a third of each view overlapping the last one ({GUIDE}, How to move, step 5)."))
    if art_lv.get('huge', 'ok') != 'ok':
        advice.append((5, f"{100 * sh['huge']:.1f}% of splats are huge blurry blobs, which usually come from glossy surfaces or changing light. "
                          f"Keep the lights steady and scan whiteboards, windows and screens at an angle ({GUIDE}, Before you start; How to move, step 7)."))
    if art_lv.get('below_floor', 'ok') != 'ok':
        advice.append((6, f"{100 * sh['below_floor']:.1f}% of splats are below the floor, usually the mirror image a shiny floor creates. "
                          f"Re-run the cleanup, and check the floor line in the preview."))
    bad_scale = [m for lv, m in scale['flags'] if lv == 'bad']
    for m in bad_scale: advice.append((0, m))
    advice.append((9, f"Check the room size ({scale['width']:.2f} × {scale['depth']:.2f} m) against the real room ({GUIDE}, After scanning)."))

    upper_missing = sum(levels[k] == 'poor' for k in WALLS + ['ceiling'])
    if bad_scale or levels['floor'] == 'poor' or upper_missing >= 2 or 'severe' in art_lv.values():
        verdict = 'rescan recommended'
    elif any(v != 'good' for v in levels.values()) or 'warn' in art_lv.values() or any(lv == 'warn' for lv, _ in scale['flags']):
        verdict = 'usable'
    else:
        verdict = 'good'
    return {'verdict': verdict, 'levels': levels, 'artifact_levels': art_lv, 'advice': [t for _, t in sorted(advice, key=lambda x: x[0])]}


def _join(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + ' and ' + xs[-1]


def _cap(s): return s[:1].upper() + s[1:]


SUMMARY = {
    'good': 'This Scan captured the room well. It can be published once a Room Curator has placed its Tables, seats and Boards.',
    'usable': 'This Scan can become a Room, but it has gaps Students will notice. Repair can hide some of them; a better Scan is the real fix.',
    'rescan recommended': 'This Scan misses too much of the room to look right. Scan it again if you can, following the advice below.',
}


def build_report(scan_path, layout_path, raw_path=None, g=None, layout=None, g_raw=None):
    layout = layout if layout is not None else json.load(open(layout_path))
    g = g if g is not None else load(scan_path)
    syn = synthesized_floor_mask(g)
    grids = surface_grids(g, layout, syn, smear_mask(g))
    cov = coverage(grids, layout)
    real_only = {k: v[~syn] for k, v in g.items()}
    arts = artifact_counts(real_only, layout)
    scale = scale_check(layout, cov)
    rep = {'scan': os.path.basename(scan_path), 'layout': os.path.basename(layout_path), 'splats': len(g['alpha']),
           'synthesized_floor_splats': int(syn.sum()),
           'coverage': cov, 'synthesized': synthesized_record(layout), 'scale': scale, 'artifacts': arts}
    if raw_path or g_raw is not None:
        rep['raw'] = raw_summary(g_raw if g_raw is not None else load(raw_path), g)
        rep['raw']['file'] = os.path.basename(raw_path) if raw_path else 'raw scan'
    rep.update(assess(cov, scale, arts))
    rep['summary'] = SUMMARY[rep['verdict']]
    rep['_grids'] = grids   # for the coverage map; not part of the JSON output
    return rep


# ---------------------------------------------------------------- output

def _bar(share, width=20):
    full = share * width; n = int(full)
    return '█' * n + ('▌' if full - n >= 0.5 else '') + '·' * (width - n - (1 if full - n >= 0.5 else 0))


MARK = {'good': ' ', 'weak': '!', 'poor': '✗'}


def to_text(rep):
    L = []; cov = rep['coverage']; sc = rep['scale']; a = rep['artifacts']
    L.append(f"Scan quality report: {rep['scan']}  ({rep['splats']:,} splats; Layout {rep['layout']})")
    L.append('')
    L.append(f"Verdict: {rep['verdict'].upper()}")
    L.append(f"  {rep['summary']}")
    L.append('')
    L.append('Coverage: share of each surface of the room box with real splats on it')
    for key, _ in SURFACES:
        c = cov[key]; extra = ''
        if key == 'floor':
            extra = f"  {c['missing_m2']:.1f} m² not scanned"
            if c['any'] > c['real'] + 0.005: extra += f", {(c['any'] - c['real']) * c['area_m2']:.1f} m² of it filled in by the cleanup"
        elif key.startswith('wall'): extra = f"  below 1.2 m {100 * c['lower']:.0f}%, above {100 * c['upper']:.0f}%"
        if c['synthesized_m2']: extra += f"  (+{c['synthesized_m2']:.1f} m² synthesized)"
        L.append(f"  {MARK[rep['levels'][key]]} {c['name']:<16} {100 * c['real']:>4.0f}%  {_bar(c['real'])}{extra}")
    s = rep['synthesized']
    if not s['present']:
        L.append('    Synthesized: layout.json records none' + (f" (but {rep['synthesized_floor_splats']:,} splats look like floor filling, "
                 f"so the floor share above counts only real splats)" if rep['synthesized_floor_splats'] else '') + '.')
    else:
        parts = [f"{NAMES[k]} {v:.1f} m²" for k, v in s['surfaces'].items()] + [f"{k} {v:.1f} m²" for k, v in s['other'].items()]
        L.append('    Synthesized (layout.json): ' + (', '.join(parts) if parts else 'nothing') + '. Shares above count only real splats.')
    L.append('')
    L.append('Scale')
    L.append(f"    Footprint {sc['width']:.2f} × {sc['depth']:.2f} m ({sc['area']:.1f} m²), height {sc['height']:.2f} m"
             + ('' if sc['ceiling_measured'] else ' (not measured)'))
    for lv, m in sc['flags']:
        L.append(f"  {'✗' if lv == 'bad' else '!' if lv == 'warn' else '·'} {m}")
    L.append('')
    L.append('Artifacts (real splats only)')
    desc = {'needles': f'needle-shaped streaks (≥ {100 * NEEDLE_LEN:.0f} cm long, ≥ {NEEDLE_RATIO:.0f}× longer than wide)',
            'huge': f'huge blobs (≥ {HUGE_LEN:.1f} m across one axis)',
            'fuzz': f'translucent fuzz (opacity < {100 * FUZZ_ALPHA:.0f}%)',
            'below_floor': 'below the floor (more than 5 cm under it)',
            'smears': f"ghost smears (outsized opaque splats), blurring {a['smear_m2']:.1f} m²"
                      + (f" = {a['smear_vs_floor']:.1f}× the floor area" if 'smear_vs_floor' in a else '')}
    for k in ('smears', 'needles', 'huge', 'fuzz', 'below_floor'):
        if k not in a: continue
        lv = rep['artifact_levels'].get(k, 'ok')
        L.append(f"  {'✗' if lv == 'severe' else '!' if lv == 'warn' else ' '} {a[k]:>9,}  {100 * a['share'][k]:5.2f}%  {desc[k]}")
    if 'raw' in rep:
        r = rep['raw']
        L.append('')
        L.append(f"Original Scan ({r['file']}): {r['splats']:,} splats; the cleanup kept {100 * r['kept_share']:.0f}%")
        L.append(f"    It had {r['backdrop']:,} distant backdrop splats, {r['huge']:,} huge blobs, {r['smears']:,} ghost smears, "
                 f"{r['needles']:,} needles and {r['fuzz']:,} fuzz splats; the counts above are what's left.")
    L.append('')
    L.append('Advice for the next Scan')
    for i, t in enumerate(rep['advice'], 1):
        L.append(f"  {i}. {t}")
    return '\n'.join(L)


COLORS = {'real': (63, 178, 127), 'syn': (224, 160, 48), 'missing': (150, 40, 52), 'margin_dim': 0.45, 'bg': (24, 26, 32)}


def coverage_map(rep, px=None):
    """The room box unfolded around its floor, seen from above (front wall at the top), as PNG bytes.

    Green is real splats, amber is only synthesized, red is missing. Faded cells are the strips next to a
    neighbouring surface, which the shares don't count.
    """
    from PIL import Image, ImageDraw
    grids = rep['_grids']
    fl = grids['floor']['real']; nz, nx = fl.shape
    wh = grids['wall_-z']['real'].shape[0]   # wall height in cells
    px = px or max(3, min(12, int(560 / (nx + 2 * wh))))

    def tile(key):
        gr = grids[key]
        img = np.zeros(gr['real'].shape + (3,))
        img[:] = COLORS['missing']; img[gr['any']] = COLORS['syn']; img[gr['real']] = COLORS['real']
        img[~gr['counted']] *= COLORS['margin_dim']
        return img

    # Unfold: each wall hinges on its floor edge, so its floor end touches the floor and its top points away.
    t = {k: tile(k) for k in grids}
    front = t['wall_-z'][::-1]                    # rows = height, top of wall at the top; columns = x
    back = t['wall_+z']                           # floor edge at the top
    left = t['wall_-x'].transpose(1, 0, 2)[:, ::-1]   # rows = z, columns = height with the floor edge on the right
    right = t['wall_+x'].transpose(1, 0, 2)        # floor edge on the left
    W = wh + nx + wh + 3 + nx; Hc = wh + nz + wh
    canvas = np.zeros((Hc, W, 3)); canvas[:] = COLORS['bg']
    canvas[0:wh, wh:wh + nx] = front[:, :nx]
    canvas[wh:wh + nz, 0:wh] = left[:nz]
    canvas[wh:wh + nz, wh:wh + nx] = t['floor']
    canvas[wh:wh + nz, wh + nx:wh + nx + wh] = right[:nz]
    canvas[wh + nz:, wh:wh + nx] = back[:, :nx]
    c0 = 2 * wh + nx + 3
    canvas[wh:wh + nz, c0:c0 + nx] = t['ceiling']
    im = Image.fromarray(canvas.astype(np.uint8)).resize((W * px, Hc * px), Image.NEAREST)
    head = 22; out = Image.new('RGB', (im.width, im.height + head + 22), COLORS['bg']); out.paste(im, (0, head))
    d = ImageDraw.Draw(out)
    d.text((wh * px + 2, 4), 'front wall (-z) at the top, the other walls unfolded around the floor', fill=(220, 220, 220))
    d.text((c0 * px + 2, wh * px + head - 14), 'ceiling (seen from above)', fill=(220, 220, 220))
    y = im.height + head + 6; x = 4
    for label, col in (('real splats', COLORS['real']), ('synthesized only', COLORS['syn']), ('missing', COLORS['missing'])):
        d.rectangle([x, y, x + 10, y + 10], fill=col); d.text((x + 14, y - 1), label, fill=(220, 220, 220)); x += 20 + 7 * len(label) + 14
    buf = io.BytesIO(); out.save(buf, 'PNG')
    return buf.getvalue()


def to_html(rep, renders=None):
    esc = html.escape; cov = rep['coverage']
    b64 = lambda data: base64.b64encode(data).decode()
    tone = {'good': 'good', 'usable': 'warn', 'rescan recommended': 'bad'}[rep['verdict']]
    rows = ''.join(
        f"<tr class='{rep['levels'][k]}'><td>{esc(cov[k]['name'])}</td><td class='num'>{100 * cov[k]['real']:.0f}%</td>"
        f"<td><div class='bar'><span style='width:{100 * cov[k]['real']:.0f}%'></span></div></td>"
        f"<td>{'%.1f m² synthesized' % cov[k]['synthesized_m2'] if cov[k]['synthesized_m2'] else ''}"
        f"{'%.1f m² not scanned' % cov[k]['missing_m2'] if k == 'floor' else ''}"
        f"{'below 1.2 m %.0f%%, above %.0f%%' % (100 * cov[k]['lower'], 100 * cov[k]['upper']) if k.startswith('wall') else ''}</td></tr>"
        for k, _ in SURFACES)
    text = esc(to_text(rep))
    advice = ''.join(f'<li>{esc(t)}</li>' for t in rep['advice'])
    renders_html = ''
    if renders:
        renders_html = (f"<h2>Views from inside the Room</h2><img class='renders' alt='Contact sheet of standard views' "
                        f"src='data:image/png;base64,{b64(open(renders, 'rb').read())}'>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scan quality report</title>
<style>
:root {{ --bg:#f7f7f5; --fg:#1d1f24; --muted:#5d6370; --card:#fff; --line:#e2e2de; --good:#1f8a5b; --warn:#b7791f; --bad:#b4323f; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14161c; --fg:#e8e8ea; --muted:#9aa0ab; --card:#1c1f26; --line:#2c303a; --good:#3fb27f; --warn:#e0a030; --bad:#e0606c; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; }}
main {{ max-width:980px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:17px; margin:28px 0 8px; }}
.muted {{ color:var(--muted); }}
.verdict {{ border-left:6px solid var(--{tone}); background:var(--card); padding:12px 16px; margin:16px 0; border-radius:6px; }}
.verdict b {{ color:var(--{tone}); text-transform:uppercase; letter-spacing:.04em; }}
table {{ border-collapse:collapse; width:100%; background:var(--card); border-radius:6px; overflow:hidden; }}
td {{ padding:6px 10px; border-bottom:1px solid var(--line); }} td.num {{ text-align:right; font-variant-numeric:tabular-nums; width:4em; }}
.bar {{ background:var(--line); height:10px; border-radius:5px; min-width:120px; }} .bar span {{ display:block; height:100%; border-radius:5px; background:var(--good); }}
tr.weak .bar span {{ background:var(--warn); }} tr.poor .bar span {{ background:var(--bad); }} tr.poor td:first-child {{ color:var(--bad); font-weight:600; }}
ol li {{ margin:6px 0; }}
img {{ max-width:100%; height:auto; border-radius:6px; }}
pre {{ background:var(--card); padding:12px; border-radius:6px; white-space:pre-wrap; font-size:12.5px; }}
</style></head><body><main>
<h1>Scan quality report</h1>
<div class="muted">{esc(rep['scan'])} · {rep['splats']:,} splats · Layout {esc(rep['layout'])}</div>
<div class="verdict"><b>{esc(rep['verdict'])}</b><br>{esc(rep['summary'])}</div>
<h2>Advice for the next Scan</h2><ol>{advice}</ol>
<h2>Coverage</h2><p class="muted">Share of each surface of the room box with real splats on it. Synthesized surfaces don't count.</p>
<table>{rows}</table>
<h2>Coverage map</h2><img alt="Coverage map: the room box unfolded" src="data:image/png;base64,{b64(coverage_map(rep))}">
{renders_html}
<h2>Full report</h2><pre>{text}</pre>
</main></body></html>"""


def to_json(rep):
    def clean(o):
        if isinstance(o, dict): return {k: clean(v) for k, v in o.items() if not k.startswith('_')}
        if isinstance(o, (list, tuple)): return [clean(v) for v in o]
        if isinstance(o, (np.floating, float)): return round(float(o), 4)
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.bool_): return bool(o)
        return o
    return json.dumps(clean(rep), indent=2, ensure_ascii=False)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('scan', help='the cleaned Scan: <name>.clean.ply or <name>.spz from clean_scan.py')
    ap.add_argument('layout', help='its layout.json')
    ap.add_argument('--raw', help='the original Scan before cleanup, to report what the cleanup removed')
    ap.add_argument('--html', help='also write a self-contained report page here')
    ap.add_argument('--renders', help='a contact sheet from render_views.mjs to embed in the HTML page')
    ap.add_argument('--json', help='also write the numbers as JSON here (for scripts and CI)')
    a = ap.parse_args(argv)
    if a.renders and not os.path.exists(a.renders): sys.exit(f'no such renders image: {a.renders}')
    rep = build_report(a.scan, a.layout, a.raw)
    print(to_text(rep))
    if a.html:
        with open(a.html, 'w', encoding='utf-8') as fh: fh.write(to_html(rep, a.renders))
        print(f'\nWrote {a.html}')
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as fh: fh.write(to_json(rep))
    return rep


if __name__ == '__main__':
    main()

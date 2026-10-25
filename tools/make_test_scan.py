#!/usr/bin/env python3
"""Generates a fake room splat (.ply) with the usual scan problems, to test clean_scan.py."""
import math, sys
import numpy as np, spz

rng = np.random.default_rng(0)
W, D, H = 6.0, 4.5, 2.8
parts = []
def surf(n, f, color, jitter=0.01):
    p = f(n); p += rng.normal(0, jitter, p.shape); parts.append((p, np.tile(color, (n, 1)) + rng.normal(0, .03, (n, 3))))
u = lambda n: rng.random(n)
surf(120000, lambda n: np.c_[u(n) * W - W/2, np.zeros(n), u(n) * D - D/2], [0.55, 0.42, 0.30])          # wood floor
# --bare: a Scan pointed mostly at the floor, like the first real one. No ceiling, the +x and +z walls missing,
# and the -x wall seen only up to 1.4 m: 16.8 + 12.6 + 6.3 = 35.7 m² of wall and 27 m² of ceiling to fill.
BARE = '--bare' in sys.argv
if not BARE: surf(60000, lambda n: np.c_[u(n) * W - W/2, np.full(n, H), u(n) * D - D/2], [0.92, 0.92, 0.9])  # ceiling
for z in (-D/2, D/2):
    if not (BARE and z > 0): surf(50000, lambda n, z=z: np.c_[u(n) * W - W/2, u(n) * H, np.full(n, z)], [0.85, 0.83, 0.78])
for x in (-W/2, W/2):
    if not (BARE and x > 0):
        top = 1.4 if BARE else H
        surf(int(40000 * top / H), lambda n, x=x, top=top: np.c_[np.full(n, x), u(n) * top, u(n) * D - D/2], [0.85, 0.83, 0.78])
surf(20000, lambda n: np.c_[u(n) * 2.4 - 1.2, np.full(n, 0.75), u(n) * 1.0 - 0.5], [0.45, 0.32, 0.22])     # table top
surf(15000, lambda n: np.c_[u(n) * 2.4 - 1.2, 0.9 + u(n) * 1.2, np.full(n, -D/2 + 0.02)], [0.97, 0.97, 0.97])  # whiteboard
pos = np.concatenate([p for p, _ in parts]); col = np.concatenate([c for _, c in parts])
if '--holes' in sys.argv:   # punch the kind of holes a phone scan leaves: under the table, a missed corner, a blob
    x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]; fl = np.abs(y) < 0.06   # all floor splats, jitter included
    hole = fl & (((np.abs(x) < 1.1) & (np.abs(z) < 0.45)) | ((x > 2.3) & (z > 1.6)) | (np.hypot(x + 1.8, z - 1.2) < 0.5))
    pos, col = pos[~hole], col[~hole]
n_room = len(pos)
ghost = pos[rng.choice(n_room, 25000)] * [1, -1, 1]                                    # shiny-floor mirror below
floaters = np.c_[u(4000) * 14 - 7, u(4000) * 6 - 1.5, u(4000) * 12 - 6]                 # stray fuzz, far and near
clump = rng.normal([2.5, 1.6, 4.5], 0.15, (1500, 3))                                    # detached clump outside
CLEAN = '--clean' in sys.argv
if CLEAN: ghost = ghost[:0]; floaters = floaters[:0]; clump = clump[:0]
# --ghosts: the smears a phone leaves where it barely looked (see suppress_ghosts in clean_scan.py):
#   big opaque blobs just behind the walls, long thin needles, and lone big blobs in mid-air, all with strong SH
GHOSTS = '--ghosts' in sys.argv
n_behind, n_needle, n_lone = (300, 60, 100) if GHOSTS else (0, 0, 0)
side = rng.integers(0, 4, n_behind); off = rng.uniform(0.08, 0.22, n_behind)
behind = np.c_[u(n_behind) * W - W/2, 0.3 + u(n_behind) * (H - 0.6), u(n_behind) * D - D/2]
behind[side == 0, 0] = -W/2 - off[side == 0]; behind[side == 1, 0] = W/2 + off[side == 1]
behind[side == 2, 2] = -D/2 - off[side == 2]; behind[side == 3, 2] = D/2 + off[side == 3]
needles = np.c_[u(n_needle) * 4 - 2, 0.5 + u(n_needle) * 1.8, u(n_needle) * 3 - 1.5]
lone = np.c_[u(n_lone) * 4 - 2, 1.4 + u(n_lone) * 1.0, u(n_lone) * 3 - 1.5]
n_ghosts = n_behind + n_needle + n_lone
pos = np.concatenate([pos, ghost, floaters, clump, behind, needles, lone]); n = len(pos)
col = np.concatenate([col, np.full((len(ghost), 3), .4), rng.random((len(floaters) + len(clump), 3)), np.full((n_ghosts, 3), 0.85)])
scale = np.log(np.full((n, 3), 0.012) * rng.uniform(.6, 1.6, (n, 1)))
g0 = n - n_ghosts
scale[g0:g0 + n_behind] = np.log(rng.uniform(0.1, 0.2, (n_behind, 1)))
scale[g0 + n_behind:g0 + n_behind + n_needle] = np.log([0.25, 0.01, 0.01])
scale[g0 + n_behind + n_needle:] = np.log(rng.uniform(0.07, 0.12, (n_lone, 1)))
alpha = np.full(n, 2.5)
if not CLEAN:
    scale[rng.choice(n, 800)] = math.log(1.5)                                           # giant blobs
    alpha[rng.choice(n, 30000)] = -5                                                    # nearly invisible
alpha[n_room:n_room + len(ghost)] = 0.0
alpha[n - n_ghosts:] = 4.0
rot = np.tile([0, 0, 0, 1.0], (n, 1))
# tilt the whole scan by 6 degrees and shift it, like an imperfect capture
th = math.radians(6); R = np.array([[1, 0, 0], [0, math.cos(th), -math.sin(th)], [0, math.sin(th), math.cos(th)]])
pos = pos @ R.T + [1.3, 0.9, -2.0]
rot = np.tile([math.sin(th / 2), 0, 0, math.cos(th / 2)], (n, 1))
if '--yaw' in sys.argv:   # turn the whole room 30 degrees about the vertical, like a scan that started at an angle
    ya = math.radians(30); Ry = np.array([[math.cos(ya), 0, math.sin(ya)], [0, 1, 0], [-math.sin(ya), 0, math.cos(ya)]])
    pos = pos @ Ry.T
    qy = np.array([0, math.sin(ya / 2), 0, math.cos(ya / 2)]); qt = rot[0]
    rot = np.tile([qy[3] * qt[0] + qy[1] * qt[2], qy[1] * qt[3] + qy[3] * qt[1], -qy[1] * qt[0] + qy[3] * qt[2], qy[3] * qt[3] - qy[1] * qt[1]], (n, 1))
c = spz.GaussianCloud(); c.sh_degree = 1
c.positions = pos.astype(np.float32).ravel(); c.scales = scale.astype(np.float32).ravel(); c.rotations = rot.astype(np.float32).ravel()
c.alphas = alpha.astype(np.float32).ravel(); c.colors = ((col - 0.5) / 0.282095).astype(np.float32).ravel()
sh = rng.normal(0, 0.05, (n, 9)); sh[n - n_ghosts:] = rng.normal(0, 0.6, (n_ghosts, 9))   # ghosts' colour swings with the view
c.sh = sh.astype(np.float32).ravel()
o = spz.PackOptions(); o.from_coord = spz.CoordinateSystem.RUB
spz.save_splat_to_ply(c, o, sys.argv[1])
print(f'wrote {sys.argv[1]}: {n:,} splats ({n_room:,} real room, {n_ghosts:,} ghosts)')

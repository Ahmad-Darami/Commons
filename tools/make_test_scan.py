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
surf(60000, lambda n: np.c_[u(n) * W - W/2, np.full(n, H), u(n) * D - D/2], [0.92, 0.92, 0.9])            # ceiling
for z in (-D/2, D/2): surf(50000, lambda n, z=z: np.c_[u(n) * W - W/2, u(n) * H, np.full(n, z)], [0.85, 0.83, 0.78])
for x in (-W/2, W/2): surf(40000, lambda n, x=x: np.c_[np.full(n, x), u(n) * H, u(n) * D - D/2], [0.85, 0.83, 0.78])
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
pos = np.concatenate([pos, ghost, floaters, clump]); n = len(pos)
col = np.concatenate([col, np.full((len(ghost), 3), .4), rng.random((len(floaters) + len(clump), 3))])
scale = np.log(np.full((n, 3), 0.012) * rng.uniform(.6, 1.6, (n, 1)))
alpha = np.full(n, 2.5)
if not CLEAN:
    scale[rng.choice(n, 800)] = math.log(1.5)                                           # giant blobs
    alpha[rng.choice(n, 30000)] = -5                                                    # nearly invisible
alpha[n_room:n_room + len(ghost)] = 0.0
rot = np.tile([0, 0, 0, 1.0], (n, 1))
# tilt the whole scan by 6 degrees and shift it, like an imperfect capture
th = math.radians(6); R = np.array([[1, 0, 0], [0, math.cos(th), -math.sin(th)], [0, math.sin(th), math.cos(th)]])
pos = pos @ R.T + [1.3, 0.9, -2.0]
rot = np.tile([math.sin(th / 2), 0, 0, math.cos(th / 2)], (n, 1))
c = spz.GaussianCloud(); c.sh_degree = 1
c.positions = pos.astype(np.float32).ravel(); c.scales = scale.astype(np.float32).ravel(); c.rotations = rot.astype(np.float32).ravel()
c.alphas = alpha.astype(np.float32).ravel(); c.colors = ((col - 0.5) / 0.282095).astype(np.float32).ravel()
c.sh = rng.normal(0, 0.05, (n, 9)).astype(np.float32).ravel()
o = spz.PackOptions(); o.from_coord = spz.CoordinateSystem.RUB
spz.save_splat_to_ply(c, o, sys.argv[1])
print(f'wrote {sys.argv[1]}: {n:,} splats ({n_room:,} real room)')

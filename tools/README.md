# Scan cleanup

`clean_scan.py` turns a raw Scaniverse or Polycam splat (`.ply` or `.spz`) into a Room's Appearance, plus a starter Layout.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install numpy pillow git+https://github.com/nianticlabs/spz     # builds Niantic's official SPZ library
python clean_scan.py my_scan.ply                                    # or my_scan.spz
```

**Floor filling:** every phone scan misses patches of floor, such as under tables, behind chairs and in corners. The tool works out where the floor should be and fills each hole with flat floor splats, colored by blending in the surrounding floor. Turn this off with `--no-fill-floor`, and widen the gaps it seals at the room's edges with `--fill-close 0.5`.

**What it removes:** nearly invisible splats, giant blobs, floating fuzz (both detached clumps and lonely splats near walls), the mirror-image "ghost room" that shiny floors create underneath, and strays outside the room. It also levels the floor to `y = 0`, centers the room, and caps the splat count (default 1.5 M).

**What it writes, next to the input:**

| File | Use |
|---|---|
| `*.clean.ply` | Master copy. Edit this in SuperSplat if anything else needs fixing |
| `*.spz` | What the browser loads (SPZ v3, about 10× smaller) |
| `*.preview.png` | Top and front views. Check that it looks like the room and the floor line sits at the floor |
| `*.layout.json` | Starter Layout: floor, room bounds and height. A Room Curator still adds tables, seats and Boards |

**Useful flags:**
- `--no-sh` drops view-dependent shine. Files get about 4× smaller and whiteboard glare goes away.
- `--max-splats 800000` for weaker laptops.
- `--spz-version 4` writes the newest, slightly smaller format.

**Check the printed room size against the real room.** If it's off by more than about 10%, the floor was misdetected. Increase `--floor-tol`, or fix the floor in SuperSplat.

## Loading it in the app (Spark 2.4)
- Spark needs **three.js 0.180 or newer**, and an explicit `SparkRenderer` added to the scene. Without it the frame renders black.
- Files from this tool are already upright (+y up, three.js convention). **Don't** apply the `quaternion.set(1, 0, 0, 0)` flip that Spark's own examples use.

```js
import { SparkRenderer, SplatMesh } from '@sparkjsdev/spark';
scene.add(new SparkRenderer({ renderer }));
const room = new SplatMesh({ url: '/rooms/pattee-3/pattee-3.spz' });
scene.add(room); await room.initialized;
```

`make_test_scan.py` generates a fake messy room for testing. `--clean` makes one with no defects, and `--holes` punches holes in the floor. `python test_clean_scan.py` runs the whole pipeline on all three and checks the results. CI runs it on every PR.

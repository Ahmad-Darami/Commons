# Scan cleanup

`clean_scan.py` turns a raw Scaniverse or Polycam splat (`.ply` or `.spz`) into a Room's Appearance, plus a starter Layout.

```bash
python3 -m venv .venv && . .venv/bin/activate
CMAKE_ARGS="-DCMAKE_DISABLE_FIND_PACKAGE_zstd=ON" \
  pip install numpy pillow git+https://github.com/nianticlabs/spz   # builds Niantic's official SPZ library
python clean_scan.py my_scan.ply                                    # or my_scan.spz
```

**Squaring up:** phone scans start wherever you happened to point the phone, so the room is usually turned at some angle. The tool turns it about the vertical so its walls run along x and z, which the app relies on (for example to place a Board on a wall). It finds the angle where walls and furniture edges, seen from above, line up most sharply. Turn this off with `--no-square`.

**Floor filling:** every phone scan misses patches of floor, such as under tables, behind chairs and in corners. The tool works out where the floor should be and fills each hole with small floor splats that copy the colors of real floor splats nearby, so a speckled carpet stays speckled. That includes the spot where you stood while scanning, which a phone never captures. Turn this off with `--no-fill-floor`, and widen the gaps it seals at the room's edges with `--fill-close 0.5`.

**If the spz install fails on Linux** with `relocation ... libzstd.a`: that's Ubuntu's static zstd library. The `CMAKE_ARGS` line above makes the build use its own copy.

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

## Publishing a Scan as a Room

`publish_room.py` does the whole job in one command: cleanup, suggested furniture, the Room folder and `index.json`.

    python tools/publish_room.py my_scan.spz pattee-3 "Pattee Library · Room 3" --default

- Runs `clean_scan.py`; pass its flags with `--clean-args "--no-sh --max-splats 800000"`.
- Suggests **Tables** (flat surfaces 0.65–0.80 m up, at least 0.4 × 0.4 m) and **seats** (chair seats 0.40–0.55 m up). A seat joins a Table within 1.2 m and faces it; otherwise it faces the room's center. Both are marked `"suggested": true` until a Room Curator confirms them.
- Writes `app/public/rooms/<room-id>/{appearance.spz, layout.json}` and adds or renames the Room in `index.json` (`--default` lists it first). It never touches other Rooms.
- Re-publishing keeps what a Curator already placed (Boards, and confirmed Tables and seats) and replaces only old suggestions. `--fresh` starts over.
- Runs `render_views.mjs` and `scan_report.py` when they're installed, into `--qa-dir`. `--no-qa` skips them, and `--work-dir` keeps the `*.clean.ply` master copy and the preview.

Then open `http://localhost:5173/?curate&room=<room-id>` to confirm the suggestions and place the Boards. `python tools/test_publish_room.py` checks it on a synthetic Scan.

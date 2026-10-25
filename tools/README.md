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

**Wall and ceiling filling (ADR-0003):** phone scans usually miss most of the walls and the whole ceiling, and the Room then floats in black. The tool works out the room's box (each wall where the floor stops, moved out to the wall's own splats where it was scanned; the ceiling at the top of the scanned walls), measures how much of each wall and the ceiling the Scan actually covers on an 8 cm grid, and fills only the holes. The fill copies colours from the real surface nearby, using the median of several nearby patches so a desk or door against a wall doesn't speckle it. A surface the Scan never saw borrows from the nearest real one: other walls, or the tops of the walls for the ceiling. Real splats are never moved. Every synthesized splat is a flat disc, 2 mm thick, lying on its surface's plane, with no view-dependent colour. Turn this off with `--no-fill-walls` and `--no-fill-ceiling`. Rooms that aren't box-shaped (floor covering under 70% of its bounding rectangle) are left alone.

**Ghost suppression:** where the phone barely looked it leaves big, lone, often opaque splats whose view-dependent colour turns into pastel streaks from new viewpoints. The tool removes needles (σ ≥ 5 cm and 8× longer than wide), big or lonely splats behind the walls or above the ceiling, and outsized smears inside the Room (σ ≥ 5 cm and ≥ 10× the Scan's median splat). It also fades the view-dependent colour of splats that are lonely or bigger than 2 cm. By default it keeps SH up to degree 1 (`--sh-degree`, 0 to 3), which looks the same in renders and gives a ~25% smaller file. `--keep-ghosts` turns all of this off.

**What it reports:** a *Scan report* lists how much of each wall, the ceiling and the floor the Scan missed, and which to rescan. `layout.json` records what was synthesized, as `"synthesized": {"floor_m2": …, "walls_m2": {"-z": …, "+x": …, "+z": …, "-x": …}, "ceiling_m2": …}`, with walls keyed by their side of `"room_box"` (the wall and ceiling planes), so a Room Curator can see how much of a Room is real.

**What it removes:** nearly invisible splats, giant blobs, floating fuzz (both detached clumps and lonely splats near walls), the mirror-image "ghost room" that shiny floors create underneath, and strays outside the room. It also levels the floor to `y = 0`, centers the room, and caps the splat count (default 1.5 M).

**What it writes, next to the input:**

| File | Use |
|---|---|
| `*.clean.ply` | Master copy. Edit this in SuperSplat if anything else needs fixing |
| `*.spz` | What the browser loads (SPZ v3, about 10× smaller) |
| `*.preview.png` | Top and front views. Check that it looks like the room and the floor line sits at the floor |
| `*.layout.json` | Starter Layout: floor, room bounds and height. A Room Curator still adds tables, seats and Boards |

**Useful flags:**
- `--no-sh` (same as `--sh-degree 0`) drops view-dependent shine. Files get smaller and whiteboard glare goes away. `--sh-degree 3` keeps all the shine a Scan has.
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

`make_test_scan.py` generates a fake messy room for testing. `--clean` makes one with no defects, `--holes` punches holes in the floor, `--yaw` turns it 30°, `--bare` leaves out the ceiling and most of three walls, and `--ghosts` adds blobs behind the walls, needles and lone mid-air blobs. `python test_clean_scan.py` runs the whole pipeline on each and checks the results, including that a complete room gets nothing synthesized. CI runs it on every PR.

## Publishing a Scan as a Room

`publish_room.py` does the whole job in one command: cleanup, suggested furniture, the Room folder and `index.json`.

    python tools/publish_room.py my_scan.spz pattee-3 "Pattee Library · Room 3" --default

- Runs `clean_scan.py`; pass its flags with `--clean-args "--no-sh --max-splats 800000"`.
- Suggests **Tables** (flat surfaces 0.65–0.80 m up, at least 0.4 × 0.4 m) and **seats** (chair seats 0.40–0.55 m up). A seat joins a Table within 1.2 m and faces it; otherwise it faces the room's center. Both are marked `"suggested": true` until a Room Curator confirms them.
- Writes `app/public/rooms/<room-id>/{appearance.spz, layout.json}` and adds or renames the Room in `index.json` (`--default` lists it first). It never touches other Rooms.
- Re-publishing keeps what a Curator already placed (Boards, and confirmed Tables and seats) and replaces only old suggestions. `--fresh` starts over.
- Runs `render_views.mjs` and `scan_report.py` when they're installed, into `--qa-dir`. `--no-qa` skips them, and `--work-dir` keeps the `*.clean.ply` master copy and the preview.

Then open `http://localhost:5173/?curate&room=<room-id>` to confirm the suggestions and place the Boards. `python tools/test_publish_room.py` checks it on a synthetic Scan.

## Checking a Scan

`scan_report.py` writes a **Scan quality report** for a Room Curator. It covers:
- how much of the floor, each wall and the ceiling has real splats (what the cleanup filled in doesn't count)
- whether the room's size is plausible
- how many ghost smears, needle streaks, huge blobs and fuzz splats remain
- a verdict of **good**, **usable** or **rescan recommended**, with advice that points to the steps of `docs/scanning-guide.md`

    python scan_report.py out/my_scan.clean.ply out/my_scan.layout.json --raw my_scan.spz --html out/report.html --renders out/views.png

`--html` writes one self-contained page with a coverage map (the room box unfolded around its floor: green real, amber synthesized, red missing). `--json` writes the numbers for scripts.

`render_views.mjs` renders six standard views from inside the Room as one labeled contact sheet: standing at 1.6 m toward each wall, seated at 1.12 m toward the center, and a seat's view, all derived from `layout.json`. It uses Spark in headless Chromium and takes its modules from `app/node_modules` (run `npm ci` in `app/` first, or pass `--app-dir`). Software rendering takes about 10–90 s per view.

    node render_views.mjs out/my_scan.spz out/my_scan.layout.json out/views.png [--size 800x450]

`python test_scan_report.py` checks the report on synthetic scans: a complete room, one with the ceiling and walls cut away, floor holes and ghost smears.

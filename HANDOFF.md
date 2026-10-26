# Handoff: continuing Commons locally

_Last updated: 2026-10-26, after the whole scan pipeline (#18–#22) was merged into `main`. If this file and GitHub disagree, GitHub is the truth._

Start with `CLAUDE.md` (rules for anyone, human or agent, working here), `CONTEXT.md` (the glossary) and `docs/adr/`. This file covers only **where things stand right now** and how to pick them up.

## 1. Get set up on your computer
```bash
git clone https://github.com/Ahmad-Darami/Commons commons && cd commons
git fetch origin                      # fetches every branch below

# The app (Node 22)
cd app && npm ci && npm run dev       # http://localhost:5173  (?curate = Room Curator editor, ?room=<id>, ?debug)

# The scan tools (Python 3.12)
cd .. && python3 -m venv .venv && . .venv/bin/activate
CMAKE_ARGS="-DCMAKE_DISABLE_FIND_PACKAGE_zstd=ON" pip install numpy pillow git+https://github.com/nianticlabs/spz
python tools/test_clean_scan.py       # should end "all scan pipeline checks passed"
```
The live preview is at **https://ahmad-darami.github.io/Commons/**. It redeploys on every merge to `main`.

## 2. Pull requests
None are open. The scan pipeline (#18, #19, #20, #22) and this handoff (#21) are all merged into `main`, and the live preview shows the repaired first Room. Start new work from `main`.

## 3. Where the scan pipeline stands
The whole pipeline is built and in the PRs above. One command takes a raw phone Scan to a published, checked Room in about 1–2 minutes:
```bash
python tools/publish_room.py <scan.spz> <room-id> "<Room name>" --default --work-dir scans/<room-id>
```
It runs the cleanup and repair (walls, ceiling, floor, ghosts), suggests Tables and seats, writes the Room folder, and renders six preview views plus a quality report (`report.html`) into a QA folder. `scans/` is git-ignored; keep raw scans out of git.

**Next for the scan pipeline:**
- **Rescan** the room following `docs/scanning-guide.md`, and publish it with the command above. The first Scan's report says "rescan recommended": walls 7–54% covered, ceiling 0%.
- **Filled walls don't match each other in color, and look grainy up close.** With a better Scan there's less to fill. Ideas if it still shows:
  - estimate one paint color per room from whatever wall is seen
  - smoother discs for walls
- **L-shaped rooms** are skipped by wall filling, which assumes a box.
- **One Scan or several?** A Room comes from one Scan today (ADR-0001), and `publish_room.py` takes one file. Several Scans of the same room *could* be stitched together: the pipeline already levels and squares up each one, so lining them up is mostly a slide across the floor and a quarter-turn. It would need:
  - a `tools/merge_scans.py` that aligns the Scans, removes the doubled overlap and matches their color
  - a new ADR superseding ADR-0001

  Not decided. Try one complete Scan with the scanning guide first. Stitching makes sense for a top-up Scan of walls and ceiling, or for the bigger classroom later.
- **The Curator editor** should show `"suggested": true` Tables and seats, and drop the flag when one is confirmed (workstream curator, #8).

## 4. Decisions waiting on you (GitHub issues)
- **#1 Backend** for Study Groups and Invite Links. Recommended: Cloudflare Workers + Durable Objects.
- **#2 How Live Windows run.** Recommended: a shared server browser opening public share links, with opt-in live control.
- **#3 Whiteboard engine.** Recommended: tldraw for the pilot, with a licence before any commercial launch.
- **#4 Desk Mode seated-only?** Try both with the switch in the prototype's **?** sheet.
- **#5 / #6:** rescan with `docs/scanning-guide.md`, and pick the first real room.

## 5. Workstreams not started yet
Briefs are in `docs/workstreams/`, and each has a GitHub issue (#7–#14) and a tracking issue (#15).
- **Can start now:** curator (#8), desk-mode (#9), board-pages (#10, against the in-memory stub).
- **Can start against a local `livekit-server --dev`:** presence (#12), voice (#13).
- **Blocked on decisions:** study-groups (#11, needs #1), live-windows (#14, needs #2).

To hand a workstream to an agent locally: *"Read CLAUDE.md, CONTEXT.md and docs/workstreams/<name>.md, then work issue #N on a `ws/<name>-<topic>` branch and open a PR."*

## 6. Things that bit us (so they don't bite you)
- **Spark (the splat renderer):**
  - It needs `scene.add(new SparkRenderer({ renderer }))`, or the scene renders black. It also needs three.js 0.180 or newer.
  - Scans from `clean_scan.py` are already upright: **don't** apply the `quaternion.set(1, 0, 0, 0)` flip from Spark's examples.
- **The spz library on Linux:** the `CMAKE_ARGS` above are needed, or linking fails on Ubuntu's static libzstd.
- **Rendering in headless Chromium:** use Playwright's full Chromium (`channel: 'chromium'`), not the headless shell, which is too slow for screenshots with software rendering.
- **Scans from Scaniverse:**
  - **The backdrop:** about 1% of splats are 7.4 m blobs 130–200 m away, a backdrop the app adds.
  - **Soft splats:** walls often come through as large soft splats, so never filter by absolute size alone.
  - **Turned rooms:** rooms come in at an arbitrary angle; `clean_scan.py` squares them up.
- **View-dependent color (SH)** must be rotated along with the splats (`sh_rotation()` in `clean_scan.py`), or it shows as rainbow shimmer.
- **GitHub from the cloud session:** GraphQL and the Pages-settings API were blocked, so use `gh api` REST calls.

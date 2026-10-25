# Handoff: continuing Commons locally

_Last updated: 2026-10-25, during the cloud session. If this file and GitHub disagree, GitHub is the truth._

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

## 2. Open pull requests: merge in this order
They're **stacked**: each is built on the one before.

| PR | Branch | What |
|---|---|---|
| [#18](https://github.com/Ahmad-Darami/Commons/pull/18) | `ws/scan-pipeline-sh-and-walls` → `main` | Correct rotation of view-dependent color; filters that keep walls; `--keep-background`; ADR-0003; `docs/scanning-guide.md` |
| [#19](https://github.com/Ahmad-Darami/Commons/pull/19) | `ws/scan-pipeline-publish` → #18 | `tools/publish_room.py`: Scan → Room in one command, with suggested Tables and seats. Adds optional `suggested` to the Layout types |
| [#20](https://github.com/Ahmad-Darami/Commons/pull/20) | `ws/scan-pipeline-report` → #19 | `tools/scan_report.py` (quality report and verdict) and `tools/render_views.mjs` (six preview renders) |

After merging #18, GitHub retargets #19 to `main` (and likewise #20 after #19), if you delete each merged branch. Otherwise edit the base branch by hand.

## 3. Work that was still in progress
- **Scan repair** (branch `ws/scan-pipeline-repair`): automatic filling of missing **walls and ceiling**, removal of **ghost smears** (outsized opaque splats; the first Scan has 521 of them blurring about 38 m²), and recording what was synthesized in `layout.json["synthesized"]`. A subagent was working on it in the cloud.
  - If the branch exists on GitHub, it's either finished or a `WIP:` checkpoint. Check its last commit.
  - **If it doesn't exist, the work was lost.** Redo it from `docs/adr/0003-repair-what-a-scan-misses.md` and the findings in #20's description. Its tasks:
    1. Coverage grid on each wall plane and the ceiling.
    2. Synthesize splats only where there's no coverage, copying colors from real splats on the same surface. Copy how `fill_floor()` does it.
    3. Drop splats that are both ≥ 5 cm and ≥ 10× the Scan's median splat size.
    4. Write `"synthesized": {"floor_m2", "walls_m2": {"-z","+x","+z","-x"}, "ceiling_m2"}`.
    5. Add synthetic test fixtures without walls and ceiling.
- **The live Room `psu-first-scan`** still uses the older cleanup. Once the repair lands, re-publish it:
  ```bash
  python tools/publish_room.py <your .spz> psu-first-scan "Penn State · first real scan" --default --work-dir scans/psu
  python tools/scan_report.py scans/psu/*.clean.ply scans/psu/*.layout.json --html scans/psu/report.html
  ```
  (`scans/` is git-ignored. Keep raw scans out of git.)

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

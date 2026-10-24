# Working on Commons

Commons is scanned replicas of real Penn State rooms where World Campus Study Groups meet from the browser. Several agents work on it in parallel, so follow these rules.

## Before you change anything
1. **Read `CONTEXT.md`.** It's the glossary. Use its terms exactly, in code, comments, UI text and PRs: Room, Scan, Layout, Appearance, Board, Page, Table, Study Group, Study Session, Room Instance, Invite Link, Desk Mode, Laptop, Live Window, Room Curator. Don't invent synonyms. Its "_Avoid_" lists are binding.
2. **Read the ADRs in `docs/adr/`** that touch your area. Don't contradict one silently. If you need to, write a new ADR that supersedes it, and say so in your PR.
3. **Find your workstream brief in `docs/workstreams/`.** It says which files you own, which shared contracts you consume, and what "done" means.

## Ownership
- Stay inside the directories your workstream owns.
- The **shared contracts** belong to nobody: `app/src/contracts.ts`, `app/src/services.ts`, `app/src/store.ts` and `app/src/room/types.ts`. Change them only additively (new optional fields, new methods with stub implementations). Flag every change under a **"Contract change"** heading in your PR description. Anything breaking needs the owner's (the user's) sign-off first.
- A workstream plugs in by replacing its stub in `app/src/services.ts`, not by editing other workstreams' code.

## Decisions you must not make alone
Anything listed under "Open decisions" in your brief, or under "Flagged ambiguities" in `CONTEXT.md`. Write up the options and your recommendation (as a draft ADR or in the PR), then stop and ask.

## Conventions
- Units are **metres**. **+y is up** (three.js convention). Yaw 0 looks toward −z; forward = (−sin yaw, −cos yaw).
- Splat files come out of `tools/clean_scan.py` already upright. Spark needs a `SparkRenderer` in the scene, and **no** `quaternion.set(1, 0, 0, 0)` flip.
- TypeScript strict, no `any`. Pure logic goes in plain `.ts` files with a `*.test.ts` next to it. Keep React components thin.
- Comment the *why*, not the *what*.

## Commands
```bash
cd app && npm ci
npm run dev            # http://localhost:5173  (add ?curate to open the Room Curator editor, ?debug to expose state)
npx tsc -b && npm test # type-check + unit tests
npm run build && npm run smoke   # end-to-end check in headless Chromium
python tools/test_clean_scan.py  # scan pipeline check (needs numpy, pillow, spz; see tools/README.md)
```

## Git
- Work on a branch named `ws/<workstream>-<short-topic>`, and open a PR into `main`. Don't push to `main` directly.
- CI must be green: type-check, unit tests, build, smoke and the scan-pipeline test.
- Keep PRs small enough to review in one sitting. Link the GitHub issue you're closing.

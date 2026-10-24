# Commons app

React + Vite + TypeScript, with three.js via React Three Fiber, and Spark for the scanned Appearance.

```bash
npm ci
npm run dev          # http://localhost:5173
```

- `?curate` opens the Room Curator editor: place Tables, seats and Boards, then download `layout.json` into `public/rooms/<room-id>/`.
- `?room=<room-id>` picks a Room from `public/rooms/index.json`. `?invite=<token>` opens a Study Group's Invite Link (stubbed for now).
- `?debug` exposes the app state as `window.__commons` (used by the smoke test).

**Controls:** drag to look · WASD to walk (Shift to go faster) · **E** sit or stand · **L** open or close your Laptop (Desk Mode) · click a seat ring to sit.

## Layout of the code
| Path | What |
|---|---|
| `src/contracts.ts` | The seams between workstreams (presence, voice, Pages, Study Groups). Shared; change only additively |
| `src/services.ts` | Where real implementations replace the stubs |
| `src/store.ts` | App state (zustand). Shared |
| `src/room/` | Room loading, Layout types, geometry rules (walkable floor, Tables, seats, Boards), 3D objects |
| `src/people/` | The local Student's controls and actions, and remote Students' avatars |
| `src/curator/` | The Room Curator editor |
| `src/ui/` | HUD |
| `tests/smoke.mjs` | End-to-end check in headless Chromium (`npm run build && npm run smoke`) |

The demo Room in `public/rooms/demo-study-room/` is a **synthetic** scan (`tools/make_test_scan.py --holes`, cleaned by `tools/clean_scan.py`). Replace it with real Scans.

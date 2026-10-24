# Workstreams

The work is split so that several agents can build at once without stepping on each other. Each workstream owns some directories, implements one seam from `app/src/contracts.ts`, and plugs in through `app/src/services.ts`, where a stub keeps the app working until it lands.

| Brief | Owns | Implements | Depends on |
|---|---|---|---|
| [scan-pipeline](scan-pipeline.md) | `tools/`, `app/public/rooms/` | the Room folder format | none |
| [study-groups](study-groups.md) | `server/`, `app/src/join/` | `StudyGroupService` | open decision: backend |
| [presence](presence.md) | `app/src/net/`, `app/src/people/RemoteStudents.tsx` | `PresenceService` | study-groups (a stub works until then) |
| [voice](voice.md) | `app/src/voice/` | `VoiceService` | presence (for positions) |
| [board-pages](board-pages.md) | `app/src/board/` | `PageService` | study-groups (for persistence) |
| [live-windows](live-windows.md) | `app/src/board/live-window/` | — | open decision: how it runs |
| [desk-mode](desk-mode.md) | `app/src/desk/` | — | none |
| [curator](curator.md) | `app/src/curator/` | — | none |

## What can start today
**scan-pipeline**, **desk-mode**, **curator** and **board-pages** (against the in-memory stub) can all start immediately. **presence** and **voice** can start against a local dev server. **study-groups** and **live-windows** start with a decision the user has to make: write up the options and ask.

## Changing a contract
`app/src/contracts.ts`, `app/src/services.ts`, `app/src/store.ts` and `app/src/room/types.ts` are shared:
- Additive changes are fine: new optional fields, or new methods with a stub. List them under "Contract change" in the PR.
- Renaming or removing anything needs the user's sign-off first, because other workstreams are coding against it.

## Definition of done (every workstream)
- Uses `CONTEXT.md` terms. A new term gets proposed to the user before it's used.
- Unit tests for pure logic, and the smoke test still passes. Extend `app/tests/smoke.mjs` if your feature is user-visible.
- No new console errors. Works in Chrome and Edge; check Safari if the feature uses the browser APIs involved.

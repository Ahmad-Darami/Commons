# Commons

Faithful, scanned replicas of real Penn State rooms where World Campus students study together from anywhere. You join from the browser, sit at a table with your Study Group, talk, and share a Board.

## What's here

| Path | What it is |
|---|---|
| [`HANDOFF.md`](HANDOFF.md) | Where things stand right now, and how to continue locally |
| [`CONTEXT.md`](CONTEXT.md) | The glossary: Room, Scan, Layout, Appearance, Board, Page, Study Group, Desk Mode and the rest. **Read this first.** |
| [`docs/adr/`](docs/adr) | Architecture decisions and why they were made |
| [`app/`](app) | The real app: React, Vite, TypeScript, three.js and Spark (work in progress) |
| [`tools/`](tools) | `clean_scan.py` turns a phone splat scan (`.ply` / `.spz`) into a Room's Appearance and a starter Layout |
| [`prototype/`](prototype) | The single-file pitch prototype, plus its Wallpaper Engine desk-display package |
| [`video/`](video) | The 60-second walkthrough video and the scripts that render it |

## Turning a phone scan into a Room

1. Scan the room in Scaniverse (splat mode) on an iPhone Pro, and export `.ply` or `.spz`.
2. Run `python tools/clean_scan.py my_scan.ply`. It removes fuzz and ghost reflections, levels the floor, fills holes in the floor, and writes a `.spz`, a preview image and a starter `layout.json`.
3. Put both files under `app/public/rooms/<room-id>/`. Open the app's Curator editor to place tables, seats and Boards, then save the Layout.

See [`tools/README.md`](tools/README.md) for the details.

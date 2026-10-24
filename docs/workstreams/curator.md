# Workstream: Room Curator editor

**Goal:** a Room Curator turns a freshly scanned Room into a usable one in about 15 minutes, by placing Tables, seats and Boards over the real furniture and whiteboards.

**Terms:** Room Curator, Layout, Table, Board, Publish.
**Owns:** `app/src/curator/`.

## Start here
`?curate` opens the editor. It already places Tables, seats (which join and face the nearest Table) and Boards (on the wall you click). It edits by number, deletes, keeps drafts in the browser, and downloads `layout.json`.

## Tasks
- [ ] Drag to move, and a rotate handle, for Tables and seats, instead of only typing numbers.
- [ ] **"Add seats around this Table"**: a quick action that places seats evenly along the Table's long sides, facing it.
- [ ] Undo and redo.
- [ ] A top-down view toggle, so placing over the real furniture is easier.
- [ ] Show the scan's suggested tables from the scan-pipeline workstream, and accept or reject each one.
- [ ] **Publish** in development: a Vite dev-server endpoint that writes `layout.json` straight into the Room folder (dev only; production publishing comes with the backend).

## Done when
Starting from the synthetic demo Room with no tables, a new Curator recreates the Table, its 4 seats and the Board in under 5 minutes without reading code, and the result saves to the Room folder.

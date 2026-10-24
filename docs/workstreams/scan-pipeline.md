# Workstream: scan pipeline

**Goal:** a Room Curator turns a phone Scan into a published Room folder with one command, and the Room looks and measures like the real space (ADR-0001).

**Terms:** Scan, Layout, Appearance, Room, Room Curator, Publish.
**Owns:** `tools/`, `app/public/rooms/`.
**Contract:** the Room folder format, `app/public/rooms/<room-id>/{layout.json, appearance.spz}` plus an entry in `app/public/rooms/index.json`. `layout.json` follows `app/src/room/types.ts`. Additive changes only.

## Start here
- `tools/clean_scan.py` already does: fuzz and ghost removal, floor levelling, cropping, floor-hole filling, the walkable map, and SPZ output. It's tested only on synthetic scans from `tools/make_test_scan.py`.
- `tools/README.md` has the setup.

## Tasks
- [ ] Run it on the **first real Scaniverse scan** from the user. Check the coordinate system, the scale and the floor detection, and fix what breaks. Commit the result as a real Room (keep the synthetic demo Room too).
- [ ] `tools/publish_room.py <scan> <room-id> "<Room name>"`: runs the cleanup, writes the Room folder, and adds or updates `index.json`.
- [ ] `tools/test_clean_scan.py` in CI (it already exists; keep it green, and add a case for every bug a real scan uncovers).
- [ ] Optional hole filling for **walls and ceiling**, the same way the floor is filled, behind a flag.
- [ ] **Suggested tables:** find horizontal clusters of splats 0.65–0.8 m above the floor and write them into `layout.json` as *suggested* tables for the Curator to confirm. Never as final.
- [ ] Splat budget for bigger Rooms: measure frame rate on integrated graphics at 1 M, 2 M and 3 M splats, and document the recommended `--max-splats`.

## Done when
A real Scan becomes a Room that loads in the app upright, at true size, with no visible holes in the floor. A Curator can then place its Tables, seats and Boards.

## Open decisions (ask the user)
- Whether walls and ceiling should be filled by default, since synthesized surfaces bend "accurately replicates."

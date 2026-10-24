# Workstream: Desk Mode

**Goal:** a seated Student opens their Laptop and works in their own apps, while a small always-on-top **pop-out** keeps their Table in view, with who's talking and a mic button. The group sees the Laptop open.

**Terms:** Desk Mode, Room View, Laptop, Table.
**Owns:** `app/src/desk/` (new).

## Rules from the glossary
- The Laptop is only a signal. Open means the Student is working in Desk Mode; it's never an editor.
- *Provisional:* Desk Mode only while seated. Opening it while standing sits the Student at the nearest free seat, and standing up ends it. The prototype has an on/off switch for this; keep that switch until the user decides.
- The pop-out is the primary Room View. The wallpaper is an optional extra.

## Start here
- In the new app, `me.working` already opens and closes the Laptop (`L` key, `toggleLaptop()` in `app/src/people/actions.ts`).
- The prototype (`prototype/index.html`, "desk view") already does this with Document Picture-in-Picture, with a fallback to video picture-in-picture. **Port it**, don't reinvent it: the pop-out's own animation loop keeps the Room rendering while the main tab is hidden.

## Tasks
- [ ] Opening the Laptop opens the pop-out, and closing either one closes both.
- [ ] The pop-out shows the Table view, nearby Students with speaking indicators (from presence and voice), and mute.
- [ ] The video picture-in-picture fallback for Safari and Firefox.
- [ ] Later: the wallpaper Room View (the package in `prototype/wallpaper/`), pointed at the real app with a read-only session.

## Done when
In Chrome, a seated Student presses L, switches to Word, and still sees the Table and who's talking in the pop-out. The other Students see their Laptop open.

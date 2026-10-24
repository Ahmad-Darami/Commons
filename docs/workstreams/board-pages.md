# Workstream: Board & Pages

**Goal:** each Board in a Room shows one of the Study Group's Pages. The group can create as many Pages as it wants and switch between them, and the Pages are waiting when the group comes back next week.

**Terms:** Board, Page, Study Group, Study Session.
**Owns:** `app/src/board/` (new). The Board's 3D surface in `app/src/room/RoomObjects.tsx` (`Board`) may be moved into `app/src/board/`.
**Implements:** `PageService`. Swap it in for the `memoryPages` stub in `app/src/services.ts`.

## Rules from the glossary
- A Board sits over a real writing surface at true size (placed by the Curator). Students never move or resize Boards.
- Pages belong to the **Study Group**, not the Room. Another group in the same Room sees only its own Pages.
- Any Student in the Study Session can create a Page or switch which Page a Board shows, and everyone sees the switch.

## Tasks
- [ ] Clicking a Board opens a full-screen editor for the Page it's showing. Recommended: **tldraw**, with its sync for live multi-user editing. Mind its licence; see the open decision below.
- [ ] A Page switcher: list, create, rename, and pick which Page a Board shows.
- [ ] The 3D Board shows a live image of its Page (refresh about every 2 seconds while someone is editing).
- [ ] Persistence keyed by Study Group (needs the study-groups backend; develop against the in-memory stub).
- [ ] Content types on a Page: drawing, sticky notes, images and files, links. Live Windows are a separate workstream that plugs in as a shape.

## Done when
Two Students edit the same Page live. One switches the Board to another Page and both see it. Both leave, rejoin a day later, and the Pages are still there.

## Open decisions (ask the user)
- tldraw's licence: free with a "made with tldraw" mark, but a commercial product needs a paid licence. The alternatives are Excalidraw (MIT) or a custom canvas.

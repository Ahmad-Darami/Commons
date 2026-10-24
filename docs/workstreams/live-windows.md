# Workstream: Live Windows

**Goal:** a Live Window is a live web page on a Page, such as a Claude or ChatGPT chat or any website, which **everyone in the Study Session can see and scroll**. When nobody has it open, it shows a **preview** of the page.

**Terms:** Live Window, Page, Board, Study Session.
**Owns:** `app/src/board/live-window/` (new), plus a server-side component if the decision below requires one.

## The decision to make first (ask the user)
"Everyone can scroll" rules out the prototype's approach, where a Student streams their own browser tab. Chrome's Captured Surface Control only forwards the streamer's own scrolling, not a viewer's. The options:
1. **A shared browser running on a server**, one per Live Window (for example Hyperbeam, or the open-source Neko). Everyone sees and controls the same page. Costs: running browsers on a server, and someone has to sign in to Claude or ChatGPT *inside* that shared browser, which other people could then see. Viewer input could be limited to scrolling, so others can't type into your chat.
2. **Public share links in a shared browser:** open a chat's public share link (claude.ai or chatgpt.com share URLs) in the server browser. Nobody's login is involved, everyone can scroll, but it's read-only.
3. **A tab stream from one Student** (the prototype's way): free and private, but only that Student can scroll.

Recommendation to bring to the user: **(2) by default, (1) when a Student chooses to drive a live session.** Write it up as a proposal ADR, then wait for the decision.

## Tasks (after the decision)
- [ ] A Live Window shape on a Page (it plugs into the board-pages workstream's editor).
- [ ] The preview: the latest frame saved with the Page, so it's visible when the window isn't live and on the 3D Board.
- [ ] Who may control it, and how a viewer asks for control.
- [ ] A privacy note in the UI whenever a signed-in session is visible to the group.

## Done when
A Student adds a Claude chat as a Live Window. Two others scroll it on their own machines. After everyone leaves, the Page still shows its preview.

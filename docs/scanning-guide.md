# Scanning a room for Commons

What the first real Scan taught us, as a checklist for the next one. The cleanup tool can repair some gaps (ADR-0003), but a good Scan always looks better than a repaired one.

## Before you start
- Use an **iPhone Pro** and **Scaniverse**, in splat mode.
- **Clear the room of people.** Leave the furniture where Students would use it.
- **Lights on and steady.** Turn off the lights directly in front of glossy whiteboards, and close the blinds on windows that face them.
- **Erase the whiteboards.**

## How to move (about 10 to 20 minutes for a small room)
1. **Walk the edge first**, phone pointed into the room. Then walk through the middle.
2. **Sweep every wall from floor to ceiling.** The first Scan pointed mostly at the floor and furniture, so the walls and ceiling were missing and the Room floated in darkness.
3. **Point up at the ceiling** for a full pass. It's easy to forget and very visible when missing.
4. **Look at tables and chairs from two heights**: standing (1.6 m) and sitting (1.1 m). Students see the room from both.
5. **Move slowly**, and keep about a third of each view overlapping the last one.
6. **Step aside at the end and scan where you were standing.** The spot under your feet is always a hole otherwise.
7. Scan glossy surfaces (whiteboards, windows, screens) **at an angle**, never straight on.

## After scanning
- Export **SPZ** (smaller) or **PLY**, and send it, or run `python tools/clean_scan.py <file>`.
- Read the tool's report. If it says walls, ceiling or more than about 1 m² of floor are missing, rescan those parts if you can.
- Check the printed room size against the real room.

# Repair what a Scan misses, and mark what was synthesized

The first real Scan (Oct 2026) captured the floor and furniture well but missed most of the walls and all of the ceiling. It also had floor holes where the scanner stood and under furniture, colorful "ghost" smears where the phone barely looked, and a distant backdrop of huge splats that the scanning app adds 130 to 200 m away. Shown as-is, the Room floats in darkness and looks bad, even though it measures right (ADR-0001).

The owner decided that the pipeline should **fill in what a Scan misses** rather than only remove junk: holes in the floor, missing walls and ceiling, and the void beyond the Room. It does so automatically, so a Room Curator doesn't patch scans by hand. This bends "the Appearance is recognizable" toward "the Appearance is complete." That's acceptable as long as:

- Synthesized surfaces copy colors and texture from real, nearby parts of the same Scan, and are never invented.
- Everything synthesized is recorded in `layout.json` (which surfaces, and how many square meters), so a Curator can see how much of a Room is real.
- Filling never moves or reshapes anything real. The Layout's measurements still come only from what was scanned.
- The tool reports what a Scan missed, so the next Scan can be better. Repair isn't a substitute for scanning well.

## Consequences
- `tools/clean_scan.py` grows repair steps, each with a switch to turn it off, and a test on a synthetic Scan that lacks the thing being repaired.
- A Scan quality report runs with every cleanup, telling the Curator what was missed and whether to rescan.

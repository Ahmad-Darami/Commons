# One iPhone Pro Scan produces both the Layout and the Appearance of a Room

Penn State is buying faithful replicas of its own spaces. Every Room must be recognizable to someone who has been there, *and* dimensionally correct, so that seats, tables and the whiteboard wall sit where they really are. No single capture method gives both. LiDAR room capture (Apple RoomPlan) measures accurately and identifies furniture, but looks like a floor plan. Photoreal capture (a Gaussian splat built from video) looks like the room, but carries no structure. So one walk-through on an iPhone Pro records LiDAR and video together. Commons runs on the measured Layout, and Students see the photoreal Appearance, aligned on top of it.

## Consequences

- Scanning needs an iPhone Pro, because only Pro models have LiDAR, and a native iOS capture app, because browsers can't access LiDAR. Joining a Room stays browser-only.
- Every Scan needs an alignment step, and a check that the Appearance lines up with the Layout.
- We rejected scanning twice (one LiDAR pass, one video pass), because aligning two separate walk-throughs is harder and makes scanning slower.
- **Interim stand-in:** until the native capture app exists, Scans come from an off-the-shelf scanning app (Scaniverse or Polycam) that exports a true-to-scale splat. `tools/clean_scan.py` levels it and derives a starter Layout, and a Room Curator places tables, seats and Boards by hand. The decision above still stands.

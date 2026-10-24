# Workstream: multiplayer presence

**Goal:** everyone in a Study Session sees everyone else in the Room Instance, live: where they stand, which seat they're in, whether their Laptop is open, and whether they're talking.

**Terms:** Study Session, Room Instance, Table, Laptop, Desk Mode.
**Owns:** `app/src/net/` (new), and the look of `app/src/people/RemoteStudents.tsx`.
**Implements:** `PresenceService`. Swap it in for the `soloPresence` stub in `app/src/services.ts`.

## How it plugs in (already wired)
- `app/src/SessionBridge.tsx` calls `presence.join(session)`, then `publish(me)` 10 times a second, and feeds `onChange(others)` into the store.
- `app/src/people/actions.ts` turns `others` into taken seats, so nobody can sit in an occupied chair.
- `RemoteStudents.tsx` already draws a placeholder avatar per Student.

## Tasks
- [ ] Recommended transport: **LiveKit data messages** in a LiveKit room named after the Study Group, so voice and presence share one connection. Use a local `livekit-server --dev` for development.
- [ ] Interpolate remote movement smoothly, and drop a Student who has been silent for about 5 seconds.
- [ ] **Seat races:** two Students click the same free seat at once, and exactly one gets it. Write down the rule (for example, lowest join time wins) and test it.
- [ ] Better avatars, with name tags. Keep them cheap to render.
- [ ] Extend the smoke test with two browser pages in one Room Instance.

## Done when
Two machines in the same Room Instance see each other walk, sit, and open their Laptops within about 200 ms. A seat taken by one is unavailable to the other.

## Open decisions (ask the user)
- Avatar style: abstract (like the prototype) vs something more personal.

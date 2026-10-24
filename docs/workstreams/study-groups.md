# Workstream: Study Groups & Invite Links

**Goal:** a Student creates a Study Group for a Room and shares its Invite Link. Whoever opens the link joins that group's Study Session, in a private Room Instance (ADR-0002).

**Terms:** Study Group, Study Session, Invite Link, Room Instance, Room.
**Owns:** `server/` (new), `app/src/join/` (new).
**Implements:** `StudyGroupService` in `app/src/contracts.ts`. Swap it in for the `demoGroups` stub in `app/src/services.ts`.

## Rules from the glossary (MVP)
- The Invite Link **is** the membership. No accounts: the Student types a display name.
- Any member present can **reset** the Invite Link, and the old link stops working immediately.
- **At most 5 Students** in one Study Session at once. A 6th sees "This Study Group is full right now."
- A Study Group has a usual Room. Two groups in the same Room never see each other.

## Tasks
- [ ] **Decide the backend first (open decision below).** Write a short proposal ADR and get the user's choice.
- [ ] Server: create a group (name, Room), resolve an Invite Link token, reset a token, and enforce the 5-person cap (with presence).
- [ ] The server also mints **voice and presence access tokens** for a Study Session, if the chosen voice service needs them (see the voice and presence briefs).
- [ ] App: a join screen that asks for a display name (remembered per browser), then opens the Room. Add a "Create a Study Group" flow and a "Copy / reset Invite Link" control.
- [ ] Deploy target and environment variables documented in `server/README.md`. Never commit secrets.

## Done when
Two browsers on different machines open the same Invite Link and land in the same Room Instance. A third link to another Study Group in the same Room lands in a different Instance. Resetting the link locks out the old one.

## Open decisions (ask the user)
- **Backend:** Supabase (database, edge functions, realtime) vs Cloudflare Workers (+ Durable Objects) vs something else. It has to sit alongside LiveKit (voice) and the Board's sync. The recommendation should minimize the number of services.

# Workstream: voice

**Goal:** real voice between the Students in a Study Session. Everyone at the same Table hears each other clearly. Others fade with distance, like a real study room.

**Terms:** Table, Study Session, Room Instance, Desk Mode.
**Owns:** `app/src/voice/` (new).
**Implements:** `VoiceService`. Swap it in for the `silentVoice` stub in `app/src/services.ts`.

## How it plugs in (already wired)
`SessionBridge` calls `voice.start(session)` after presence joins, and calls `voice.update(me, others)` every frame.

## Rules
- Same Table (both seated at seats with the same `tableId`): full volume.
- Otherwise: linear-ish falloff to silence at about 6 m, with left/right panning by direction.
- Desk Mode doesn't change audio. A Student in Desk Mode is still heard and can still hear (CONTEXT.md).
- The prototype's rule lives in `prototype/index.html` (`prox()`).

## Tasks
- [ ] LiveKit audio tracks in the same room as presence. Tokens come from the study-groups server; use dev tokens locally.
- [ ] Per-person gain via Web Audio, from `update()`. Put this logic in a pure `gain.ts` with unit tests.
- [ ] Mute button and speaking detection (`isSpeaking()`), shown on avatars and in the people list.
- [ ] Echo cancellation and noise suppression on; test with two laptops in the same physical room.

## Done when
Two machines at the same Table talk clearly. When one walks to the far wall, the voice fades and pans. Muting works, and the speaking ring lights up.

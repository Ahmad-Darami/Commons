// The one place real implementations get plugged in. Until a workstream lands, a stub keeps the app working solo.
import type { PageService, PageSummary, PresenceService, StudyGroupService, VoiceService } from './contracts';

/** Stub: alone in the Room. */
const soloPresence: PresenceService = {
  async join() {},
  leave() {},
  publish() {},
  onChange() { return () => {}; },
};

/** Stub: no audio. */
const silentVoice: VoiceService = {
  async start() {},
  stop() {},
  setMuted() {},
  update() {},
  isSpeaking: () => false,
};

/** Stub: Pages kept in memory for this tab only. */
const memoryPages: PageService = (() => {
  const pages = new Map<string, PageSummary[]>();
  return {
    async list(g) { return pages.get(g) ?? []; },
    async create(g, name) { const p = { id: `page-${Math.random().toString(36).slice(2, 8)}`, name }; pages.set(g, [...(pages.get(g) ?? []), p]); return p; },
    onShowing() { return () => {}; },
    show() {},
  };
})();

/** Stub: every Invite Link opens the demo Study Group in the first Room. */
const demoGroups: StudyGroupService = {
  async resolveInvite() { return { studyGroupId: 'demo-group', roomId: '', groupName: 'Demo Study Group' }; },
  async createGroup() { return { inviteToken: 'demo' }; },
  async resetInvite() { return { inviteToken: 'demo' }; },
};

export const services = {
  presence: soloPresence,
  voice: silentVoice,
  pages: memoryPages,
  groups: demoGroups,
};

// The seams between workstreams. Each workstream replaces one stub in services.ts with a real implementation,
// without changing these interfaces unilaterally (see docs/workstreams/README.md: "Changing a contract").
// Terms follow CONTEXT.md.
import type { Me } from './store';

/** Which Study Session this browser is in: opened from a Study Group's Invite Link. */
export interface SessionInfo {
  studyGroupId: string;
  roomId: string;
  displayName: string;
}

/** Another Student in the same Room Instance. */
export interface RemoteStudent {
  id: string;
  name: string;
  color: string;
  x: number; z: number; yaw: number;
  seatId: string | null;
  /** Laptop open = in Desk Mode. */
  working: boolean;
  speaking: boolean;
}

/** Workstream: Multiplayer presence. Who else is in this Study Session, and where. */
export interface PresenceService {
  join(session: SessionInfo): Promise<void>;
  leave(): void;
  /** Called about 10 times a second with the local Student's state. */
  publish(me: Me): void;
  /** Subscribe to the other Students in the Room Instance. Returns an unsubscribe function. */
  onChange(cb: (others: RemoteStudent[]) => void): () => void;
}

/** Workstream: Voice. Real audio, with Table bubbles and distance falloff (CONTEXT.md: Table). */
export interface VoiceService {
  start(session: SessionInfo): Promise<void>;
  stop(): void;
  setMuted(muted: boolean): void;
  /** Called every frame so volumes can follow who's at your Table and how far away others are. */
  update(me: Me, others: RemoteStudent[]): void;
  /** Whether the local Student is currently talking (drives the speaking indicator). */
  isSpeaking(): boolean;
}

/** A Page a Study Group owns (CONTEXT.md: Page). */
export interface PageSummary {
  id: string;
  name: string;
  /** An image of the Page, for drawing it on the Board in 3D. */
  previewUrl?: string;
}

/** Workstream: Board & Pages. Pages belong to the Study Group and persist between Study Sessions. */
export interface PageService {
  list(studyGroupId: string): Promise<PageSummary[]>;
  create(studyGroupId: string, name: string): Promise<PageSummary>;
  /** Which Page each Board is showing right now, keyed by Board id. Shared by everyone in the Study Session. */
  onShowing(cb: (showing: Record<string, string>) => void): () => void;
  show(boardId: string, pageId: string): void;
}

/** Workstream: Study Groups & Invite Links. */
export interface StudyGroupService {
  /** Resolve an Invite Link token into the session to join, or throw if the link was reset. */
  resolveInvite(token: string): Promise<{ studyGroupId: string; roomId: string; groupName: string }>;
  createGroup(name: string, roomId: string): Promise<{ inviteToken: string }>;
  resetInvite(studyGroupId: string): Promise<{ inviteToken: string }>;
}

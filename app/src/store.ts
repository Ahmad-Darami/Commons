import { create } from 'zustand';
import type { RemoteStudent, SessionInfo } from './contracts';
import type { Layout, RoomEntry } from './room/types';

export type CuratorTool = 'select' | 'table' | 'seat' | 'board' | 'delete';
export type Selection = { kind: 'table' | 'seat' | 'board'; id: string } | null;

export interface Me {
  x: number; z: number; yaw: number; pitch: number;
  seatId: string | null;
  /** Laptop open = in Desk Mode (see CONTEXT.md: Laptop). */
  working: boolean;
}

interface State {
  room: RoomEntry | null;
  layout: Layout | null;
  me: Me;
  /** The other Students in this Room Instance, from the presence service. */
  others: RemoteStudent[];
  session: SessionInfo | null;
  curating: boolean;
  tool: CuratorTool;
  selected: Selection;
  dirty: boolean;
  setRoom: (room: RoomEntry, layout: Layout) => void;
  editLayout: (fn: (l: Layout) => void) => void;
  setMe: (patch: Partial<Me>) => void;
  setOthers: (others: RemoteStudent[]) => void;
  setCurating: (on: boolean) => void;
  setTool: (t: CuratorTool) => void;
  select: (s: Selection) => void;
}

export const useApp = create<State>((set, get) => ({
  room: null,
  layout: null,
  me: { x: 0, z: 0, yaw: 0, pitch: -0.05, seatId: null, working: false },
  others: [],
  session: null,
  curating: false,
  tool: 'select',
  selected: null,
  dirty: false,
  setRoom: (room, layout) => set({ room, layout, dirty: false, selected: null }),
  editLayout: fn => {
    const l = get().layout; if (!l) return;
    const next: Layout = structuredClone(l); fn(next);
    set({ layout: next, dirty: true });
    saveDraft(get().room?.id, next);
  },
  setMe: patch => set({ me: { ...get().me, ...patch } }),
  setOthers: others => set({ others }),
  setCurating: on => set({ curating: on, tool: 'select', selected: null }),
  setTool: tool => set({ tool, selected: null }),
  select: selected => set({ selected }),
}));

export const newId = (prefix: string) => `${prefix}-${Math.random().toString(36).slice(2, 8)}`;

// Curator edits survive a reload until they're saved into the room folder.
const draftKey = (roomId: string) => `commons-layout-draft:${roomId}`;
function saveDraft(roomId: string | undefined, l: Layout) {
  if (!roomId) return;
  try { localStorage.setItem(draftKey(roomId), JSON.stringify(l)); } catch { /* private mode etc. */ }
}
export function loadDraft(roomId: string): Layout | null {
  try { const s = localStorage.getItem(draftKey(roomId)); return s ? JSON.parse(s) as Layout : null; } catch { return null; }
}
export function clearDraft(roomId: string) {
  try { localStorage.removeItem(draftKey(roomId)); } catch { /* ignore */ }
}

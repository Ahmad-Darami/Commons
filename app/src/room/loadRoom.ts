import type { Layout, RoomEntry } from './types';

const base = `${import.meta.env.BASE_URL}rooms/`;

export async function listRooms(): Promise<RoomEntry[]> {
  const r = await fetch(`${base}index.json`);
  if (!r.ok) throw new Error(`No rooms list at ${base}index.json`);
  return r.json();
}

export async function loadLayout(roomId: string): Promise<Layout> {
  const r = await fetch(`${base}${roomId}/layout.json`);
  if (!r.ok) throw new Error(`Room "${roomId}" has no layout.json`);
  const l = await r.json() as Layout;
  l.tables ??= []; l.seats ??= []; l.boards ??= [];
  return l;
}

export const appearanceUrl = (roomId: string, layout: Layout) => `${base}${roomId}/${layout.appearance}`;

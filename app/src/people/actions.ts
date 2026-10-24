import { nearestSeat, standUpSpot } from '../room/geometry';
import { useApp } from '../store';

/** Seats other Students are sitting in, kept in sync with the presence service's list of others. */
export const takenSeats = new Set<string>();
useApp.subscribe((s, prev) => {
  if (s.others === prev.others) return;
  takenSeats.clear();
  for (const o of s.others) if (o.seatId) takenSeats.add(o.seatId);
});

export function sitNearest(maxDist = 1.5): boolean {
  const { layout, me, setMe } = useApp.getState();
  if (!layout || me.seatId) return false;
  const s = nearestSeat(layout, me.x, me.z, maxDist, takenSeats);
  if (!s) return false;
  setMe({ seatId: s.id, x: s.x, z: s.z, yaw: s.facing, pitch: -0.22 });
  return true;
}

export function sitAt(seatId: string): boolean {
  const { layout, me, setMe } = useApp.getState();
  const s = layout?.seats.find(x => x.id === seatId);
  if (!s || takenSeats.has(seatId) || Math.hypot(s.x - me.x, s.z - me.z) > 3.5) return false;
  setMe({ seatId: s.id, x: s.x, z: s.z, yaw: s.facing, pitch: -0.22, working: false });
  return true;
}

export function stand() {
  const { layout, me, setMe } = useApp.getState();
  const s = layout?.seats.find(x => x.id === me.seatId);
  if (!layout || !s) return;
  const [x, z] = standUpSpot(layout, s);
  setMe({ seatId: null, working: false, x, z, pitch: -0.05 });
}

/** Opening the Laptop puts a seated Student in Desk Mode; it only means anything while seated. */
export function toggleLaptop() {
  const { me, setMe } = useApp.getState();
  if (!me.seatId) return;
  setMe({ working: !me.working });
}

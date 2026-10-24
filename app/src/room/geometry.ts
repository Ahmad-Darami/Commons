import type { BoardSpot, Bounds, Layout, Seat, Table, Walkable } from './types';

export const PLAYER_RADIUS = 0.22;

/** Yaw that looks from (x, z) toward (tx, tz), matching the camera convention forward = (-sin yaw, -cos yaw). */
export function yawToward(x: number, z: number, tx: number, tz: number): number {
  return Math.atan2(-(tx - x), -(tz - z));
}

/** World point → a Table's local frame (x along its width, z along its depth). */
export function toTableLocal(t: Table, x: number, z: number): [number, number] {
  const c = Math.cos(t.rotation), s = Math.sin(t.rotation), dx = x - t.x, dz = z - t.z;
  return [dx * c - dz * s, dx * s + dz * c];
}

export function fromTableLocal(t: Table, lx: number, lz: number): [number, number] {
  const c = Math.cos(t.rotation), s = Math.sin(t.rotation);
  return [t.x + lx * c + lz * s, t.z - lx * s + lz * c];
}

export function insideTable(t: Table, x: number, z: number, pad = 0): boolean {
  const [lx, lz] = toTableLocal(t, x, z);
  return Math.abs(lx) <= t.width / 2 + pad && Math.abs(lz) <= t.depth / 2 + pad;
}

/** Distance from a point to a Table's edge (0 if the point is over the table). */
export function distanceToTable(t: Table, x: number, z: number): number {
  const [lx, lz] = toTableLocal(t, x, z);
  return Math.hypot(Math.max(Math.abs(lx) - t.width / 2, 0), Math.max(Math.abs(lz) - t.depth / 2, 0));
}

/** The point on a Table's edge closest to (x, z). */
export function closestPointOnTable(t: Table, x: number, z: number): [number, number] {
  const [lx, lz] = toTableLocal(t, x, z);
  return fromTableLocal(t, Math.max(-t.width / 2, Math.min(t.width / 2, lx)), Math.max(-t.depth / 2, Math.min(t.depth / 2, lz)));
}

export function onFloor(w: Walkable | undefined, x: number, z: number): boolean {
  if (!w) return true;
  const row = w.rows[Math.floor((z - w.origin[1]) / w.cell)];
  return !!row && row[Math.floor((x - w.origin[0]) / w.cell)] === '#';
}

function insideBounds(b: Bounds, x: number, z: number, pad: number): boolean {
  return x >= b.min_x + pad && x <= b.max_x - pad && z >= b.min_z + pad && z <= b.max_z - pad;
}

/** Can a standing Student occupy (x, z)? On scanned floor, inside the room, and not inside a Table. */
export function canStand(layout: Layout, x: number, z: number, r = PLAYER_RADIUS): boolean {
  if (!insideBounds(layout.bounds, x, z, r)) return false;
  for (const [dx, dz] of [[0, 0], [r, 0], [-r, 0], [0, r], [0, -r]]) if (!onFloor(layout.walkable, x + dx, z + dz)) return false;
  return !layout.tables.some(t => insideTable(t, x, z, r));
}

/** Move toward (nx, nz), sliding along whatever blocks the way. */
export function slide(layout: Layout, x: number, z: number, nx: number, nz: number): [number, number] {
  if (canStand(layout, nx, nz)) return [nx, nz];
  if (canStand(layout, nx, z)) return [nx, z];
  if (canStand(layout, x, nz)) return [x, nz];
  return [x, z];
}

export function nearestTable(layout: Layout, x: number, z: number, maxDist: number): Table | null {
  let best: Table | null = null, bd = maxDist;
  for (const t of layout.tables) { const d = distanceToTable(t, x, z); if (d <= bd) { bd = d; best = t; } }
  return best;
}

/** A new seat at (x, z): it joins the nearest Table within reach and faces it, otherwise it faces the room's centre. */
export function makeSeat(layout: Layout, id: string, x: number, z: number): Seat {
  const t = nearestTable(layout, x, z, 1.2);
  if (t) { const [px, pz] = closestPointOnTable(t, x, z); return { id, x, z, facing: yawToward(x, z, px, pz), tableId: t.id }; }
  const b = layout.bounds;
  return { id, x, z, facing: yawToward(x, z, (b.min_x + b.max_x) / 2, (b.min_z + b.max_z) / 2), tableId: null };
}

export function nearestSeat(layout: Layout, x: number, z: number, maxDist: number, taken: ReadonlySet<string> = new Set()): Seat | null {
  let best: Seat | null = null, bd = maxDist;
  for (const s of layout.seats) { const d = Math.hypot(s.x - x, s.z - z); if (d <= bd && !taken.has(s.id)) { bd = d; best = s; } }
  return best;
}

/** Where to stand after getting up: a step back from the seat, if that spot is free. */
export function standUpSpot(layout: Layout, s: Seat): [number, number] {
  for (const back of [0.6, 0.45, 0.8, 0.3]) {
    const x = s.x + Math.sin(s.facing) * back, z = s.z + Math.cos(s.facing) * back;
    if (canStand(layout, x, z)) return [x, z];
  }
  return [s.x, s.z];
}

/** A standing spot to start from: the floor cell nearest the room's centre. */
export function spawnPoint(layout: Layout): [number, number] {
  const b = layout.bounds, cx = (b.min_x + b.max_x) / 2, cz = (b.min_z + b.max_z) / 2;
  if (canStand(layout, cx, cz)) return [cx, cz];
  for (let r = 0.2; r < 10; r += 0.2)
    for (let a = 0; a < Math.PI * 2; a += Math.PI / 12) {
      const x = cx + Math.cos(a) * r, z = cz + Math.sin(a) * r;
      if (canStand(layout, x, z)) return [x, z];
    }
  return [cx, cz];
}

/**
 * Place a Board on the room wall that a ray hits (the Layout's bounds stand in for the walls).
 * Returns the Board centre and the yaw its surface faces (into the room), or null if the ray misses.
 */
export function boardOnWall(layout: Layout, origin: [number, number, number], dir: [number, number, number], width: number, height: number, id: string): BoardSpot | null {
  const b = layout.bounds, [ox, oy, oz] = origin, [dx, dy, dz] = dir, inset = 0.01;
  const walls: { t: number; rotation: number; at: (t: number) => [number, number] }[] = [];
  const hit = (plane: number, o: number, d: number) => (Math.abs(d) < 1e-6 ? -1 : (plane - o) / d);
  walls.push({ t: hit(b.min_x, ox, dx), rotation: Math.PI / 2, at: t => [b.min_x + inset, oz + dz * t] });
  walls.push({ t: hit(b.max_x, ox, dx), rotation: -Math.PI / 2, at: t => [b.max_x - inset, oz + dz * t] });
  walls.push({ t: hit(b.min_z, oz, dz), rotation: 0, at: t => [ox + dx * t, b.min_z + inset] });
  walls.push({ t: hit(b.max_z, oz, dz), rotation: Math.PI, at: t => [ox + dx * t, b.max_z - inset] });
  let best: BoardSpot | null = null, bt = Infinity;
  for (const w of walls) {
    if (w.t <= 0 || w.t >= bt) continue;
    const [x, z] = w.at(w.t);
    if (x < b.min_x - 0.02 || x > b.max_x + 0.02 || z < b.min_z - 0.02 || z > b.max_z + 0.02) continue;
    const y = Math.max(height / 2 + 0.5, Math.min(layout.height - height / 2 - 0.1, oy + dy * w.t));
    bt = w.t; best = { id, x, y, z, width, height, rotation: w.rotation };
  }
  return best;
}

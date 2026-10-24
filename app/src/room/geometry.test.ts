import { describe, expect, it } from 'vitest';
import { boardOnWall, canStand, distanceToTable, insideTable, makeSeat, nearestSeat, onFloor, slide, spawnPoint, standUpSpot, yawToward } from './geometry';
import type { Layout, Table } from './types';

const table: Table = { id: 't1', x: 0, z: 0, width: 2, depth: 1, height: 0.75, rotation: 0 };
function room(extra: Partial<Layout> = {}): Layout {
  return {
    units: 'metres', up: '+y', floor_y: 0, height: 2.8, appearance: 'a.spz',
    bounds: { min_x: -3, max_x: 3, min_z: -2, max_z: 2 },
    walkable: { cell: 1, origin: [-3, -2], rows: ['######', '######', '######', '###...'] },
    tables: [table], seats: [], boards: [], ...extra,
  };
}

describe('facing', () => {
  it('yaw 0 looks toward -z, and +pi/2 toward -x', () => {
    expect(yawToward(0, 0, 0, -1)).toBeCloseTo(0);
    expect(yawToward(0, 0, -1, 0)).toBeCloseTo(Math.PI / 2);
  });
});

describe('tables', () => {
  it('handles rotated tables', () => {
    const turned = { ...table, rotation: Math.PI / 2 };   // now 1 wide in x, 2 deep in z
    expect(insideTable(turned, 0, 0.9)).toBe(true);
    expect(insideTable(turned, 0.9, 0)).toBe(false);
    expect(distanceToTable(table, 0, 1.5)).toBeCloseTo(1);
  });
});

describe('walking', () => {
  it('stays on scanned floor, inside the room, and off tables', () => {
    const L = room();
    expect(onFloor(L.walkable, 2.5, 1.5)).toBe(false);   // the '...' corner was never scanned
    expect(canStand(L, -2, -1)).toBe(true);
    expect(canStand(L, 0, 0)).toBe(false);                // on the table
    expect(canStand(L, 2.5, 1.5)).toBe(false);            // off the floor
    expect(canStand(L, -2.95, 0)).toBe(false);            // through the wall
  });
  it('slides along a table instead of stopping dead', () => {
    const [x, z] = slide(room(), -0.5, 0.9, -0.4, 0.7);  // pushing diagonally into the table's long edge
    expect(x).toBeCloseTo(-0.4); expect(z).toBeCloseTo(0.9);
  });
  it('spawns on floor, not on a table', () => {
    const L = room(); const [x, z] = spawnPoint(L);
    expect(canStand(L, x, z)).toBe(true);
  });
});

describe('seats', () => {
  it('a new seat joins the nearest table and faces it', () => {
    const s = makeSeat(room(), 's1', 0.5, 1.0);
    expect(s.tableId).toBe('t1');
    expect(s.facing).toBeCloseTo(0);                       // the table is toward -z, which is yaw 0
  });
  it('a seat far from tables belongs to none', () => {
    expect(makeSeat(room(), 's2', -2.5, -1.8).tableId).toBeNull();
  });
  it('skips taken seats and stands you up behind the chair', () => {
    const L = room(); const a = makeSeat(L, 'a', -0.5, 0.9), b = makeSeat(L, 'b', 0.5, 0.9); L.seats.push(a, b);
    expect(nearestSeat(L, -0.5, 1.2, 1.5, new Set(['a']))?.id).toBe('b');
    const [x, z] = standUpSpot(L, a);
    expect(z).toBeGreaterThan(0.9); expect(canStand(L, x, z)).toBe(true);
  });
});

describe('boards', () => {
  it('lands on the wall the ray hits, facing into the room', () => {
    const b = boardOnWall(room(), [0, 1.6, 0], [0, 0, -1], 1.8, 1.1, 'b1')!;
    expect(b.z).toBeCloseTo(-1.99); expect(b.rotation).toBeCloseTo(0); expect(b.y).toBeCloseTo(1.6);
    const e = boardOnWall(room(), [0, 1.6, 0], [1, 0, 0], 1.8, 1.1, 'b2')!;
    expect(e.x).toBeCloseTo(2.99); expect(e.rotation).toBeCloseTo(-Math.PI / 2);
  });
});

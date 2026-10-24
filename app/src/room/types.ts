// The shape of a Room's Layout file (see CONTEXT.md: Layout, Table, Board).
// tools/clean_scan.py writes the starter version; the Room Curator editor fills in tables, seats and Boards.

export interface Bounds { min_x: number; max_x: number; min_z: number; max_z: number }

/** Floor footprint from the Scan: rows of '#' (floor) and '.' (not floor), starting at origin [x, z]. */
export interface Walkable { cell: number; origin: [number, number]; rows: string[] }

/** A Table, as an axis box on the floor, rotated by `rotation` radians about +y. */
export interface Table { id: string; x: number; z: number; width: number; depth: number; height: number; rotation: number }

/** A seat. `facing` is the yaw a seated Student looks along (forward = (-sin, -cos)). */
export interface Seat { id: string; x: number; z: number; facing: number; tableId: string | null }

/** Where a Board sits: centre, size, and the yaw its writing surface faces. */
export interface BoardSpot { id: string; x: number; y: number; z: number; width: number; height: number; rotation: number }

export interface Layout {
  units: string;
  up: string;
  floor_y: number;
  bounds: Bounds;
  height: number;
  appearance: string;
  splats?: number;
  walkable?: Walkable;
  tables: Table[];
  seats: Seat[];
  boards: BoardSpot[];
  note?: string;
}

export interface RoomEntry { id: string; name: string }

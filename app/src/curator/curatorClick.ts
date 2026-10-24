import * as THREE from 'three';
import { boardOnWall, insideTable, makeSeat } from '../room/geometry';
import { newId, useApp } from '../store';

const floor = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

/** A click in the 3D view while curating: place, select or delete depending on the current tool. */
export function curatorClick(ray: THREE.Ray) {
  const { layout, tool, editLayout, select } = useApp.getState();
  if (!layout) return;
  const hit = ray.intersectPlane(floor, new THREE.Vector3());

  if (tool === 'board') {
    const b = boardOnWall(layout, ray.origin.toArray(), ray.direction.toArray(), 1.8, 1.1, newId('board'));
    if (b) { editLayout(l => { l.boards.push(b); }); select({ kind: 'board', id: b.id }); }
    return;
  }
  if (!hit) return;
  const { x, z } = hit;

  if (tool === 'table') {
    const id = newId('table');
    editLayout(l => { l.tables.push({ id, x, z, width: 1.6, depth: 0.8, height: 0.74, rotation: 0 }); });
    select({ kind: 'table', id });
  } else if (tool === 'seat') {
    const id = newId('seat');
    editLayout(l => { l.seats.push(makeSeat(l, id, x, z)); });
    select({ kind: 'seat', id });
  } else {
    const found = pick(x, z, ray);
    if (tool === 'delete' && found) {
      editLayout(l => {
        if (found.kind === 'table') { l.tables = l.tables.filter(t => t.id !== found.id); l.seats.forEach(s => { if (s.tableId === found.id) s.tableId = null; }); }
        if (found.kind === 'seat') l.seats = l.seats.filter(s => s.id !== found.id);
        if (found.kind === 'board') l.boards = l.boards.filter(b => b.id !== found.id);
      });
      select(null);
    } else select(found);
  }
}

/** What did the click land on? Seats first (small targets), then Boards, then Tables. */
function pick(x: number, z: number, ray: THREE.Ray) {
  const { layout } = useApp.getState(); if (!layout) return null;
  let best: { kind: 'seat' | 'table' | 'board'; id: string } | null = null, bd = 0.35;
  for (const s of layout.seats) { const d = Math.hypot(s.x - x, s.z - z); if (d < bd) { bd = d; best = { kind: 'seat', id: s.id }; } }
  if (best) return best;
  for (const b of layout.boards) {
    const n = new THREE.Vector3(Math.sin(b.rotation), 0, Math.cos(b.rotation));
    const p = ray.intersectPlane(new THREE.Plane().setFromNormalAndCoplanarPoint(n, new THREE.Vector3(b.x, b.y, b.z)), new THREE.Vector3());
    if (!p) continue;
    const right = new THREE.Vector3(Math.cos(b.rotation), 0, -Math.sin(b.rotation));
    const local = p.clone().sub(new THREE.Vector3(b.x, b.y, b.z));
    if (Math.abs(local.dot(right)) <= b.width / 2 && Math.abs(local.y) <= b.height / 2) return { kind: 'board' as const, id: b.id };
  }
  const t = layout.tables.find(t => insideTable(t, x, z, 0.05));
  return t ? { kind: 'table' as const, id: t.id } : null;
}

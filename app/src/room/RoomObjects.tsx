import { useFrame } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useApp } from '../store';
import type { BoardSpot, Layout, Seat, Table } from './types';

const SEATED_EYE = 1.12;
export { SEATED_EYE };

function boardTexture(): THREE.CanvasTexture {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 512;
  const x = c.getContext('2d')!;
  x.fillStyle = '#fbfbf8'; x.fillRect(0, 0, 1024, 512);
  x.strokeStyle = 'rgba(30,60,120,.07)'; x.lineWidth = 2;
  for (let i = 0; i <= 1024; i += 32) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i, 512); x.stroke(); }
  for (let j = 0; j <= 512; j += 32) { x.beginPath(); x.moveTo(0, j); x.lineTo(1024, j); x.stroke(); }
  x.fillStyle = '#94a3b8'; x.font = '600 26px system-ui, sans-serif'; x.fillText('Board', 28, 48);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

/** Each Board covers the real writing surface it was placed over (CONTEXT.md: Board). Pages come in a later workstream. */
function Board({ b, selected }: { b: BoardSpot; selected: boolean }) {
  const tex = useMemo(boardTexture, []);
  return (
    <group position={[b.x, b.y, b.z]} rotation={[0, b.rotation, 0]}>
      <mesh position={[0, 0, -0.012]}>
        <boxGeometry args={[b.width + 0.08, b.height + 0.08, 0.02]} />
        <meshBasicMaterial color={selected ? '#6aa8ff' : '#a7afba'} />
      </mesh>
      <mesh userData={{ boardId: b.id }}>
        <planeGeometry args={[b.width, b.height]} />
        <meshBasicMaterial map={tex} toneMapped={false} />
      </mesh>
    </group>
  );
}

function SeatMarker({ s, mine, show, selected, curating }: { s: Seat; mine: boolean; show: boolean; selected: boolean; curating: boolean }) {
  if (!show && !curating) return null;
  const color = selected ? '#6aa8ff' : mine ? '#4fd18b' : s.tableId ? '#e9ebf1' : '#ffb648';
  return (
    <group position={[s.x, 0.012, s.z]} rotation={[0, s.facing, 0]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} userData={{ seatId: s.id }}>
        <ringGeometry args={[0.17, 0.22, 40]} />
        <meshBasicMaterial color={color} transparent opacity={curating ? 0.9 : 0.55} depthWrite={false} />
      </mesh>
      {curating && (
        <mesh position={[0, 0, -0.3]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.06, 3]} />
          <meshBasicMaterial color={color} />
        </mesh>
      )}
    </group>
  );
}

function TableBox({ t, selected }: { t: Table; selected: boolean }) {
  return (
    <group position={[t.x, t.height / 2, t.z]} rotation={[0, t.rotation, 0]}>
      <mesh userData={{ tableId: t.id }}>
        <boxGeometry args={[t.width, t.height, t.depth]} />
        <meshBasicMaterial color={selected ? '#6aa8ff' : '#ffb648'} transparent opacity={0.18} depthWrite={false} />
      </mesh>
      <lineSegments>
        <edgesGeometry args={[new THREE.BoxGeometry(t.width, t.height, t.depth)]} />
        <lineBasicMaterial color={selected ? '#6aa8ff' : '#ffb648'} />
      </lineSegments>
    </group>
  );
}

function BoundsOutline({ layout }: { layout: Layout }) {
  const b = layout.bounds, w = b.max_x - b.min_x, d = b.max_z - b.min_z;
  const geo = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(w, layout.height, d)), [w, d, layout.height]);
  return (
    <lineSegments geometry={geo} position={[(b.min_x + b.max_x) / 2, layout.height / 2, (b.min_z + b.max_z) / 2]}>
      <lineBasicMaterial color="#6aa8ff" transparent opacity={0.5} />
    </lineSegments>
  );
}

/** The Laptop is only a signal (CONTEXT.md: Laptop): the lid is open while the Student is working in Desk Mode. */
function Laptop({ seat, tableHeight, open }: { seat: Seat; tableHeight: number; open: boolean }) {
  const hinge = useRef<THREE.Group>(null);
  useFrame((_, dt) => { if (hinge.current) hinge.current.rotation.x += ((open ? -0.28 : 1.5) - hinge.current.rotation.x) * Math.min(1, dt * 8); });
  const fx = -Math.sin(seat.facing), fz = -Math.cos(seat.facing);
  return (
    <group position={[seat.x + fx * 0.5, tableHeight + 0.003, seat.z + fz * 0.5]} rotation={[0, seat.facing, 0]}>
      <mesh position={[0, 0.0075, 0]}><boxGeometry args={[0.34, 0.015, 0.24]} /><meshBasicMaterial color="#a3a9b2" /></mesh>
      <group ref={hinge} position={[0, 0.015, -0.12]} rotation={[1.5, 0, 0]}>
        <mesh position={[0, 0.115, 0]}><boxGeometry args={[0.34, 0.23, 0.012]} /><meshBasicMaterial color="#8d939c" /></mesh>
        <mesh position={[0, 0.115, 0.0065]}><planeGeometry args={[0.31, 0.2]} /><meshBasicMaterial color={open ? '#9fc4ff' : '#3a3f47'} /></mesh>
      </group>
    </group>
  );
}

export function RoomObjects() {
  const layout = useApp(s => s.layout)!;
  const me = useApp(s => s.me);
  const curating = useApp(s => s.curating);
  const selected = useApp(s => s.selected);
  const mySeat = layout.seats.find(s => s.id === me.seatId);
  const myTable = mySeat?.tableId ? layout.tables.find(t => t.id === mySeat.tableId) : undefined;
  return (
    <>
      {layout.boards.map(b => <Board key={b.id} b={b} selected={selected?.kind === 'board' && selected.id === b.id} />)}
      {layout.seats.map(s => (
        <SeatMarker key={s.id} s={s} mine={s.id === me.seatId} curating={curating}
          show={!me.seatId && Math.hypot(s.x - me.x, s.z - me.z) < 3.5}
          selected={selected?.kind === 'seat' && selected.id === s.id} />
      ))}
      {curating && layout.tables.map(t => <TableBox key={t.id} t={t} selected={selected?.kind === 'table' && selected.id === t.id} />)}
      {curating && <BoundsOutline layout={layout} />}
      {mySeat && <Laptop seat={mySeat} tableHeight={myTable?.height ?? 0.74} open={me.working} />}
    </>
  );
}

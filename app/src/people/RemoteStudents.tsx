import { useFrame } from '@react-three/fiber';
import { useRef } from 'react';
import * as THREE from 'three';
import type { RemoteStudent } from '../contracts';
import { useApp } from '../store';

/** Placeholder avatars for the other Students. The multiplayer workstream can replace the look; the data comes from presence. */
function Avatar({ s }: { s: RemoteStudent }) {
  const g = useRef<THREE.Group>(null);
  const layout = useApp(st => st.layout)!;
  useFrame((_, dt) => {
    if (!g.current) return;
    const seat = s.seatId ? layout.seats.find(x => x.id === s.seatId) : undefined;
    const tx = seat?.x ?? s.x, tz = seat?.z ?? s.z, k = 1 - Math.exp(-dt * 12);
    g.current.position.x += (tx - g.current.position.x) * k;
    g.current.position.z += (tz - g.current.position.z) * k;
    g.current.position.y += ((seat ? -0.42 : 0) - g.current.position.y) * k;
    g.current.rotation.y = seat?.facing ?? s.yaw;
  });
  return (
    <group ref={g} position={[s.x, 0, s.z]}>
      <mesh position={[0, 0.78, 0]}><cylinderGeometry args={[0.19, 0.24, 0.9, 20]} /><meshBasicMaterial color={s.color} /></mesh>
      <mesh position={[0, 1.4, 0]}><sphereGeometry args={[0.17, 20, 14]} /><meshBasicMaterial color="#f0d2b6" /></mesh>
      <mesh position={[0, 1.42, -0.14]}><boxGeometry args={[0.22, 0.07, 0.06]} /><meshBasicMaterial color="#1e2229" /></mesh>
      {s.speaking && <mesh position={[0, 1.4, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[0.27, 0.018, 8, 40]} /><meshBasicMaterial color="#4fd18b" /></mesh>}
    </group>
  );
}

export function RemoteStudents() {
  const others = useApp(s => s.others);
  return <>{others.map(o => <Avatar key={o.id} s={o} />)}</>;
}

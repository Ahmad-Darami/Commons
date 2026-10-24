import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { curatorClick } from '../curator/curatorClick';
import { slide } from '../room/geometry';
import { SEATED_EYE } from '../room/RoomObjects';
import { useApp } from '../store';
import { sitAt, sitNearest, stand, toggleLaptop } from './actions';

const STANDING_EYE = 1.6;
const isTyping = (el: EventTarget | null) => el instanceof HTMLElement && !!el.closest('input:not([type=checkbox]),textarea,select,[contenteditable="true"]');

/** First-person controls: drag to look, WASD to walk, E to sit or stand, L to open or close the Laptop. */
export function Player() {
  const { camera, gl } = useThree();
  const keys = useRef(new Set<string>());
  const eye = useRef(new THREE.Vector3());

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return;
      const k = e.key.toLowerCase(); keys.current.add(k);
      if (k === 'e') { if (useApp.getState().me.seatId) stand(); else sitNearest(); }
      if (k === 'l') toggleLaptop();
      if (k.startsWith('arrow')) e.preventDefault();
    };
    const up = (e: KeyboardEvent) => keys.current.delete(e.key.toLowerCase());
    const blur = () => keys.current.clear();
    addEventListener('keydown', down); addEventListener('keyup', up); addEventListener('blur', blur);
    return () => { removeEventListener('keydown', down); removeEventListener('keyup', up); removeEventListener('blur', blur); };
  }, []);

  useEffect(() => {
    const el = gl.domElement; let drag: { x: number; y: number; moved: number } | null = null;
    const ray = new THREE.Raycaster();
    const onDown = (e: PointerEvent) => { drag = { x: e.clientX, y: e.clientY, moved: 0 }; el.setPointerCapture(e.pointerId); };
    const onMove = (e: PointerEvent) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY; drag.moved += Math.abs(dx) + Math.abs(dy);
      const { me, setMe } = useApp.getState();
      setMe({ yaw: me.yaw - dx * 0.0045, pitch: Math.max(-1.2, Math.min(1.1, me.pitch - dy * 0.0035)) });
    };
    const onUp = (e: PointerEvent) => {
      if (drag && drag.moved < 6) {
        const r = el.getBoundingClientRect();
        ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
        if (useApp.getState().curating) curatorClick(ray.ray);
        else clickSeat(ray);
      }
      drag = null;
    };
    el.addEventListener('pointerdown', onDown); el.addEventListener('pointermove', onMove); el.addEventListener('pointerup', onUp);
    return () => { el.removeEventListener('pointerdown', onDown); el.removeEventListener('pointermove', onMove); el.removeEventListener('pointerup', onUp); };
  }, [camera, gl]);

  useFrame((_, rawDt) => {
    const dt = Math.min(rawDt, 0.05);
    const { layout, me, setMe } = useApp.getState();
    if (!layout) return;
    if (!me.seatId) {
      const k = keys.current; let f = 0, s = 0;
      if (k.has('w') || k.has('arrowup')) f += 1;
      if (k.has('s') || k.has('arrowdown')) f -= 1;
      if (k.has('d') || k.has('arrowright')) s += 1;
      if (k.has('a') || k.has('arrowleft')) s -= 1;
      if (f || s) {
        const len = Math.hypot(f, s), sp = (k.has('shift') ? 2.8 : 1.6) * dt;
        const fx = -Math.sin(me.yaw), fz = -Math.cos(me.yaw), rx = Math.cos(me.yaw), rz = -Math.sin(me.yaw);
        const [x, z] = slide(layout, me.x, me.z, me.x + (fx * f + rx * s) / len * sp, me.z + (fz * f + rz * s) / len * sp);
        if (x !== me.x || z !== me.z) setMe({ x, z });
      }
    }
    eye.current.set(me.x, me.seatId ? SEATED_EYE : STANDING_EYE, me.z);
    camera.position.lerp(eye.current, 1 - Math.exp(-dt * 10));
    camera.rotation.set(me.pitch, me.yaw, 0, 'YXZ');
  });
  return null;
}

function clickSeat(ray: THREE.Raycaster) {
  const hit = ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3());
  const { layout, me } = useApp.getState();
  if (!hit || !layout || me.seatId) return;
  const s = layout.seats.find(s => Math.hypot(s.x - hit.x, s.z - hit.z) < 0.4);
  if (s) sitAt(s.id);
}

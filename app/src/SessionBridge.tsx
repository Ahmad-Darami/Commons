import { useFrame } from '@react-three/fiber';
import { useEffect } from 'react';
import { services } from './services';
import { useApp } from './store';

/** Connects this tab to its Study Session: joins presence and voice, publishes the local Student, receives the others. */
export function SessionBridge() {
  const session = useApp(s => s.session);
  useEffect(() => {
    if (!session) return;
    const { presence, voice } = services;
    let live = true;
    const off = presence.onChange(others => useApp.getState().setOthers(others));
    presence.join(session).then(async () => { if (live) await voice.start(session); }).catch(e => console.warn('Could not join the Study Session', e));
    const tick = setInterval(() => presence.publish(useApp.getState().me), 100);   // timers keep running in background tabs
    return () => { live = false; clearInterval(tick); off(); voice.stop(); presence.leave(); };
  }, [session]);
  useFrame(() => { const { me, others } = useApp.getState(); services.voice.update(me, others); });
  return null;
}

import { Canvas } from '@react-three/fiber';
import { useCallback, useEffect, useState } from 'react';
import { CuratorPanel } from './curator/CuratorPanel';
import { Player } from './people/Player';
import { RemoteStudents } from './people/RemoteStudents';
import { SessionBridge } from './SessionBridge';
import { services } from './services';
import { Appearance, SparkSetup } from './room/Appearance';
import { spawnPoint } from './room/geometry';
import { appearanceUrl, listRooms, loadLayout } from './room/loadRoom';
import { RoomObjects } from './room/RoomObjects';
import { loadDraft, useApp } from './store';
import { Hud } from './ui/Hud';

function displayName(): string {
  try { return localStorage.getItem('commons-name') || 'Guest'; } catch { return 'Guest'; }
}

export default function App() {
  const room = useApp(s => s.room);
  const layout = useApp(s => s.layout);
  const curating = useApp(s => s.curating);
  const [error, setError] = useState<string | null>(null);
  const [splats, setSplats] = useState<number | null>(null);
  const [usingDraft, setUsingDraft] = useState(false);

  useEffect(() => {
    (async () => {
      const params = new URLSearchParams(location.search);
      const rooms = await listRooms();
      const invite = await services.groups.resolveInvite(params.get('invite') ?? '');   // the Invite Link is the membership
      const wanted = params.get('room') ?? invite.roomId;
      const entry = rooms.find(r => r.id === wanted) ?? rooms[0];
      if (!entry) throw new Error('No Rooms have been published yet.');
      const draft = loadDraft(entry.id);
      const l = draft ?? await loadLayout(entry.id);
      if (draft) l.appearance = (await loadLayout(entry.id)).appearance;   // the scan file always comes from the room folder
      useApp.getState().setRoom(entry, l);
      useApp.setState({ dirty: !!draft });
      setUsingDraft(!!draft);
      const [x, z] = spawnPoint(l);
      useApp.getState().setMe({ x, z });
      useApp.setState({ session: { studyGroupId: invite.studyGroupId, roomId: entry.id, displayName: displayName() } });
      if (params.has('curate')) useApp.getState().setCurating(true);
    })().catch(e => setError(String(e.message ?? e)));
  }, []);

  const onReady = useCallback((n: number) => setSplats(n), []);

  if (error) return <div className="center"><div className="panel"><b>Couldn’t open the Room</b><p className="muted">{error}</p></div></div>;
  if (!room || !layout) return <div className="center muted">Opening the Room…</div>;
  return (
    <>
      <Canvas className="scene" camera={{ fov: 70, near: 0.05, far: 200 }} gl={{ antialias: false }} dpr={[1, 1.5]}>
        <color attach="background" args={['#101216']} />
        <SparkSetup />
        <Appearance url={appearanceUrl(room.id, layout)} onReady={onReady} />
        <RoomObjects />
        <RemoteStudents />
        <Player />
        <SessionBridge />
      </Canvas>
      <Hud splats={splats} />
      {curating && <CuratorPanel />}
      {usingDraft && !curating && <div className="toast panel small">Showing your unsaved Curator edits for this Room.</div>}
    </>
  );
}

import { nearestSeat } from '../room/geometry';
import { useApp } from '../store';
import { sitNearest, stand, takenSeats, toggleLaptop } from '../people/actions';

export function Hud({ splats }: { splats: number | null }) {
  const room = useApp(s => s.room)!;
  const layout = useApp(s => s.layout)!;
  const me = useApp(s => s.me);
  const curating = useApp(s => s.curating);
  const setCurating = useApp(s => s.setCurating);
  const near = !me.seatId && nearestSeat(layout, me.x, me.z, 1.5, takenSeats);
  return (
    <>
      <header className="panel roomcard">
        <div className="title"><span className="dot" />{room.name}</div>
        <div className="muted small">
          {(layout.bounds.max_x - layout.bounds.min_x).toFixed(1)} × {(layout.bounds.max_z - layout.bounds.min_z).toFixed(1)} m ·{' '}
          {layout.seats.length} seats · {splats == null ? 'loading scan…' : `${(splats / 1e6).toFixed(2)} M splats`}
        </div>
        <button className={`btn small ${curating ? 'on' : ''}`} onClick={() => setCurating(!curating)}>{curating ? 'Done curating' : 'Curate Room'}</button>
      </header>
      {!curating && (
        <div className="prompt">
          {me.seatId ? (
            <>
              <span>{me.working ? '💻 Working. Your Laptop is open for your group to see' : 'Seated'}</span>
              <button className="btn small" onClick={toggleLaptop}><b>L</b> {me.working ? 'Close laptop' : 'Open laptop'}</button>
              <button className="btn small" onClick={stand}><b>E</b> Stand</button>
            </>
          ) : near ? (
            <button className="btn small" onClick={() => sitNearest()}><b>E</b> Sit down</button>
          ) : layout.seats.length === 0 ? (
            <span className="muted">This Room has no seats yet. Click <b>Curate Room</b> to add some.</span>
          ) : (
            <span className="muted">Drag to look · WASD to walk · click a seat ring to sit</span>
          )}
        </div>
      )}
    </>
  );
}

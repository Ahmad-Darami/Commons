import { closestPointOnTable, yawToward } from '../room/geometry';
import { clearDraft, useApp, type CuratorTool } from '../store';
import type { Layout } from '../room/types';

const TOOLS: [CuratorTool, string, string][] = [
  ['select', 'Select', 'Click a Table, seat or Board to edit it'],
  ['table', '＋ Table', 'Click the floor where a real table stands'],
  ['seat', '＋ Seat', 'Click the floor where a chair is. It joins and faces the nearest Table'],
  ['board', '＋ Board', 'Look at the real whiteboard and click it'],
  ['delete', 'Delete', 'Click a Table, seat or Board to remove it'],
];
const deg = (r: number) => Math.round((r * 180) / Math.PI);
const rad = (d: number) => (d * Math.PI) / 180;

function download(l: Layout) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(l, null, 2) + '\n'], { type: 'application/json' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: 'layout.json' }); a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Num({ label, value, step, onChange }: { label: string; value: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="num">{label}
      <input type="number" step={step} value={Number(value.toFixed(3))} onChange={e => { const v = parseFloat(e.target.value); if (Number.isFinite(v)) onChange(v); }} />
    </label>
  );
}

function SelectionEditor() {
  const layout = useApp(s => s.layout)!;
  const selected = useApp(s => s.selected);
  const edit = useApp(s => s.editLayout);
  if (!selected) return <p className="muted">Nothing selected.</p>;
  if (selected.kind === 'table') {
    const t = layout.tables.find(t => t.id === selected.id); if (!t) return null;
    const set = (k: 'x' | 'z' | 'width' | 'depth' | 'height' | 'rotation', v: number) => edit(l => { const tt = l.tables.find(x => x.id === t.id)!; tt[k] = v; });
    return (
      <div className="grid">
        <b className="span">Table</b>
        <Num label="x (m)" value={t.x} step={0.05} onChange={v => set('x', v)} /><Num label="z (m)" value={t.z} step={0.05} onChange={v => set('z', v)} />
        <Num label="width" value={t.width} step={0.05} onChange={v => set('width', v)} /><Num label="depth" value={t.depth} step={0.05} onChange={v => set('depth', v)} />
        <Num label="height" value={t.height} step={0.01} onChange={v => set('height', v)} /><Num label="turn (°)" value={deg(t.rotation)} step={5} onChange={v => set('rotation', rad(v))} />
        <span className="span muted">{layout.seats.filter(s => s.tableId === t.id).length} seats at this Table</span>
      </div>
    );
  }
  if (selected.kind === 'seat') {
    const s = layout.seats.find(s => s.id === selected.id); if (!s) return null;
    const faceTable = () => edit(l => {
      const ss = l.seats.find(x => x.id === s.id)!, t = l.tables.find(x => x.id === ss.tableId); if (!t) return;
      const [px, pz] = closestPointOnTable(t, ss.x, ss.z); ss.facing = yawToward(ss.x, ss.z, px, pz);
    });
    return (
      <div className="grid">
        <b className="span">Seat</b>
        <Num label="x (m)" value={s.x} step={0.05} onChange={v => edit(l => { l.seats.find(x => x.id === s.id)!.x = v; })} />
        <Num label="z (m)" value={s.z} step={0.05} onChange={v => edit(l => { l.seats.find(x => x.id === s.id)!.z = v; })} />
        <Num label="facing (°)" value={deg(s.facing)} step={15} onChange={v => edit(l => { l.seats.find(x => x.id === s.id)!.facing = rad(v); })} />
        <label className="num">Table
          <select value={s.tableId ?? ''} onChange={e => edit(l => { l.seats.find(x => x.id === s.id)!.tableId = e.target.value || null; })}>
            <option value="">none</option>
            {layout.tables.map((t, i) => <option key={t.id} value={t.id}>Table {i + 1}</option>)}
          </select>
        </label>
        <button className="btn span" disabled={!s.tableId} onClick={faceTable}>Face its Table</button>
      </div>
    );
  }
  const b = layout.boards.find(b => b.id === selected.id); if (!b) return null;
  const set = (k: 'y' | 'width' | 'height', v: number) => edit(l => { l.boards.find(x => x.id === b.id)![k] = v; });
  return (
    <div className="grid">
      <b className="span">Board</b>
      <Num label="width" value={b.width} step={0.05} onChange={v => set('width', v)} /><Num label="height" value={b.height} step={0.05} onChange={v => set('height', v)} />
      <Num label="centre height" value={b.y} step={0.05} onChange={v => set('y', v)} />
      <span className="span muted">Match the real whiteboard's size: the Board covers it exactly.</span>
    </div>
  );
}

export function CuratorPanel() {
  const layout = useApp(s => s.layout)!;
  const room = useApp(s => s.room)!;
  const tool = useApp(s => s.tool);
  const setTool = useApp(s => s.setTool);
  const dirty = useApp(s => s.dirty);
  const hint = TOOLS.find(t => t[0] === tool)![2];
  return (
    <aside className="panel curator">
      <div className="panel-h">Room Curator · {room.name}</div>
      <div className="tools">
        {TOOLS.map(([id, label]) => <button key={id} className={`btn ${tool === id ? 'on' : ''}`} onClick={() => setTool(id)}>{label}</button>)}
      </div>
      <p className="hint">{hint}</p>
      <SelectionEditor />
      <p className="muted counts">{layout.tables.length} tables · {layout.seats.length} seats · {layout.boards.length} boards</p>
      <div className="row">
        <button className="btn primary" onClick={() => download(layout)}>Download layout.json</button>
        <button className="btn" onClick={() => navigator.clipboard?.writeText(JSON.stringify(layout, null, 2))}>Copy</button>
      </div>
      <p className="muted small">
        Save it as <code>public/rooms/{room.id}/layout.json</code> to Publish it.
        {dirty && <> Unsaved edits are kept in this browser. <button className="link" onClick={() => { clearDraft(room.id); location.reload(); }}>Discard them</button></>}
      </p>
    </aside>
  );
}

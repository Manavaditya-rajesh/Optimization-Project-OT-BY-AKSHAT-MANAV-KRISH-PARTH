import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, post } from '../auth';
import { usePublished } from '../campus';
import { useStore } from '../store';
import TimetablePoster from '../components/TimetablePoster';
import PosterFrame from '../components/PosterFrame';
import { aspects } from '../themes/designs';
import type { Instance, Solution, ViewKind } from '../types';

// ---- API shapes (api/disruptions.py) ----
interface DisruptionItem {
  id: number;
  kind: 'availability' | 'teacher_absent' | 'teacher_leaves' | 'room_closed';
  resource: string;
  source: 'availability' | 'leave' | 'reported';
  description: string;
  broken: number;
  status: 'open' | 'resolved' | 'dismissed';
  createdAt: string;
  createdBy: string;
  resolvedBy: string | null;
  hasResult: boolean;
  resultStale: boolean;
}
interface Slot {
  day: number;
  period: number;
  roomId: string;
  facultyId: string;
}
interface ChangedSession {
  eventId: string;
  code: string;
  groupIds: string[];
  what: ('time' | 'room' | 'teacher')[];
  before: Slot;
  after: Slot;
}
interface Option {
  key: string;
  label: string;
  labels: string[];
  epsilon: number;
  objectives: { f1: number; f2: number; f3: number };
  changes: { total: number; time: number; room: number; teacher: number };
  hypervolume: number;
  levelHypervolume: number;
  frontSize: number;
  solution: Solution;
  changedSessions: ChangedSession[];
}
interface ReoptResult {
  basedOn: string;
  description: string;
  instance: Instance;
  sessions: number;
  brokenSessions: number;
  lowerBound: number;
  provenMinimal: boolean;
  originalObjectives: { f1: number; f2: number; f3: number };
  options: Option[];
  constraintsApplied: string[];
  runtime: number;
}
interface Progress {
  phase?: string;
  level?: number;
  levels?: number;
  epsilon?: number;
  evaluations?: number;
  budget?: number;
  seconds?: number;
}

const SOURCE: Record<DisruptionItem['source'], string> = {
  availability: 'Teacher availability',
  leave: 'Long leave',
  reported: 'Reported by admin',
};
const KINDS = [
  { id: 'teacher_absent', label: 'Teacher unavailable (a weekday or all week)' },
  { id: 'teacher_leaves', label: 'Teacher is leaving' },
  { id: 'room_closed', label: 'Room closed (a weekday or all week)' },
] as const;

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

/** Admin page: disruptions of the published timetable and minimal-change re-optimisation. */
export default function Disruptions() {
  const { pub, reload: reloadPub } = usePublished();
  const [items, setItems] = useState<DisruptionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    api<{ items: DisruptionItem[] }>('/disruptions')
      .then((r) => {
        setItems(r.items);
        window.dispatchEvent(new Event('clockwork:disruptions')); // refresh the sidebar badge
      })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const open = (items ?? []).filter((d) => d.status === 'open');
  const closed = (items ?? []).filter((d) => d.status !== 'open');

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Disruptions</h1>
          <p>
            When a teacher becomes unavailable, leaves, or a room closes, part of the published timetable breaks. Instead of re-optimising from
            scratch, which changes almost every class, the optimiser repairs it with the <b>fewest possible changes</b> and shows what each extra
            change would buy in quality (ε-constraint method). Short leave is handled by cover in the Calendar.
          </p>
        </div>
      </div>
      {error && <div className="error-box">{error}</div>}
      {msg && (
        <div className="card" style={{ marginBottom: 16, background: 'var(--sage-soft)' }}>
          {msg}
        </div>
      )}
      {pub === 'none' && <p className="muted">Publish a timetable first; disruptions are measured against it.</p>}

      <section style={{ marginBottom: 22 }}>
        <h2 style={{ fontSize: 22, marginBottom: 10 }}>Open {open.length ? `(${open.length})` : ''}</h2>
        {items === null && <p className="muted">Loading…</p>}
        {items !== null && !open.length && <p className="muted">No open disruptions. The published timetable is consistent with every saved constraint.</p>}
        <div className="stack" style={{ display: 'grid', gap: 16 }}>
          {open.map((d) => (
            <DisruptionCard
              key={d.id}
              d={d}
              onDone={(m) => {
                setMsg(m);
                load();
                reloadPub();
              }}
              onError={setError}
            />
          ))}
        </div>
      </section>

      {pub && pub !== 'none' && <ReportForm instance={pub.instance} onDone={(m) => (setMsg(m), load())} onError={setError} />}

      {closed.length > 0 && (
        <details className="card" style={{ marginTop: 22 }}>
          <summary>
            <b>History ({closed.length})</b>
          </summary>
          <table className="table" style={{ marginTop: 10 }}>
            <tbody>
              {closed.map((d) => (
                <tr key={d.id}>
                  <td>{d.description}</td>
                  <td>
                    <span className="chip">{d.status}</span>
                  </td>
                  <td className="tiny">{d.resolvedBy}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </>
  );
}

function DisruptionCard({ d, onDone, onError }: { d: DisruptionItem; onDone: (m: string) => void; onError: (m: string) => void }) {
  const [result, setResult] = useState<ReoptResult | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);

  useEffect(() => {
    if (d.hasResult && !d.resultStale)
      api<{ result: ReoptResult | null }>(`/disruptions/${d.id}`)
        .then((r) => setResult(r.result))
        .catch(() => undefined);
  }, [d.id, d.hasResult, d.resultStale]);

  const run = async () => {
    setRunning(true);
    setResult(null);
    try {
      const { jobId } = await post<{ jobId: string }>(`/disruptions/${d.id}/reoptimize`, { seed: 0 });
      for (;;) {
        await new Promise((r) => setTimeout(r, 600));
        const st = await api<{ status: string; progress?: Progress; result?: ReoptResult; error?: string }>(`/disruption-jobs/${jobId}`);
        if (st.progress) setProgress(st.progress);
        if (st.status === 'done' && st.result) {
          setResult(st.result);
          break;
        }
        if (st.status === 'error') throw new Error(st.error ?? 'Re-optimisation failed');
      }
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setRunning(false);
      setProgress(null);
    }
  };

  const dismiss = async () => {
    if (!confirm('Dismiss this disruption without changing the timetable?')) return;
    try {
      await post(`/disruptions/${d.id}/dismiss`);
      onDone('Disruption dismissed; the published timetable is unchanged.');
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const pctDone =
    progress && progress.levels ? Math.round((((progress.level ?? 0) + (progress.evaluations ?? 0) / (progress.budget || 1)) / progress.levels) * 100) : 0;

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div>
          <h3 style={{ fontSize: 17 }}>⚠ {d.description}</h3>
          <div className="row" style={{ gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
            <span className="chip accent">{d.broken} published session{d.broken === 1 ? '' : 's'} affected</span>
            <span className="chip">{SOURCE[d.source]}</span>
            <span className="tiny">
              {new Date(d.createdAt).toLocaleString()} · {d.createdBy}
            </span>
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn accent" onClick={run} disabled={running}>
            {running ? <span className="spinner" /> : '↻'} {result ? 'Re-run' : 'Re-optimise with minimal changes'}
          </button>
          <button className="btn ghost" onClick={dismiss} disabled={running}>
            Dismiss
          </button>
        </div>
      </div>
      {running && (
        <div style={{ marginTop: 12 }}>
          <span className="tiny">
            {progress?.epsilon != null
              ? `Searching with at most ${progress.epsilon} changes (level ${(progress.level ?? 0) + 1} of ${progress.levels}) · ${progress.evaluations}/${progress.budget} evaluations`
              : 'Repairing the published timetable with the fewest changes…'}
          </span>
          <div className="progress">
            <div style={{ width: `${pctDone}%` }} />
          </div>
        </div>
      )}
      {result && <Results d={d} r={result} onDone={onDone} onError={onError} />}
    </div>
  );
}

function TradeoffChart({ r, selected, onPick }: { r: ReoptResult; selected: string; onPick: (k: string) => void }) {
  const W = 320;
  const H = 150;
  const m = { l: 40, r: 10, t: 10, b: 30 };
  const xs = r.options.map((o) => o.changes.total);
  const ys = r.options.map((o) => o.levelHypervolume);
  const x0 = Math.min(...xs, r.lowerBound);
  const x1 = Math.max(...xs, x0 + 1);
  const y0 = Math.min(...ys) * 0.995;
  const y1 = Math.max(...ys) * 1.005;
  const sx = (v: number) => m.l + ((v - x0) / (x1 - x0)) * (W - m.l - m.r);
  const sy = (v: number) => H - m.b - ((v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b);
  const pts = r.options.map((o) => ({ o, x: sx(o.changes.total), y: sy(o.levelHypervolume) })).sort((a, b) => a.x - b.x);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 420 }} role="img" aria-label="Changes against quality">
      <rect x={m.l} y={m.t} width={W - m.l - m.r} height={H - m.t - m.b} fill="#fbf7ef" rx="6" />
      <line x1={sx(r.lowerBound)} x2={sx(r.lowerBound)} y1={m.t} y2={H - m.b} stroke="#c8553d" strokeDasharray="3 3" />
      <text x={sx(r.lowerBound) + 3} y={m.t + 10} fontSize="9" fill="#c8553d">
        minimum
      </text>
      <path d={pts.map((p, i) => `${i ? 'L' : 'M'}${p.x} ${p.y}`).join(' ')} fill="none" stroke="var(--accent)" strokeWidth="2" />
      {pts.map((p) => (
        <circle key={p.o.key} cx={p.x} cy={p.y} r={p.o.key === selected ? 6 : 4} fill={p.o.key === selected ? 'var(--ink)' : 'var(--accent)'} style={{ cursor: 'pointer' }} onClick={() => onPick(p.o.key)}>
          <title>{`${p.o.label}: ${p.o.changes.total} changes, HV ${p.o.levelHypervolume.toFixed(4)}`}</title>
        </circle>
      ))}
      <text x={(m.l + W - m.r) / 2} y={H - 6} fontSize="10" fill="#6b655c" textAnchor="middle">
        changed sessions
      </text>
      <text transform={`translate(11 ${(m.t + H - m.b) / 2}) rotate(-90)`} fontSize="10" fill="#6b655c" textAnchor="middle">
        quality (hypervolume)
      </text>
      <text x={m.l} y={H - m.b + 12} fontSize="9" fill="#a39b8e">
        {x0}
      </text>
      <text x={W - m.r} y={H - m.b + 12} fontSize="9" fill="#a39b8e" textAnchor="end">
        {x1}
      </text>
    </svg>
  );
}

function Results({ d, r, onDone, onError }: { d: DisruptionItem; r: ReoptResult; onDone: (m: string) => void; onError: (m: string) => void }) {
  const theme = useStore((s) => s.theme);
  const [selected, setSelected] = useState(r.options[0].key);
  const [view, setView] = useState<{ kind: ViewKind; entityId: string }>({ kind: 'group', entityId: r.instance.groups[0].id });
  const [active, setActive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const opt = r.options.find((o) => o.key === selected) ?? r.options[0];
  const inst = r.instance;
  const days = inst.grid.days;
  const periods = inst.grid.periods;
  const name = useMemo(() => {
    const m: Record<string, string> = {};
    [...inst.faculty, ...inst.rooms, ...inst.groups].forEach((x) => (m[x.id] = x.name));
    return m;
  }, [inst]);
  const size = aspects.find((a) => a.id === theme.aspect) ?? aspects[0];
  const slot = (s: Slot) => `${days[s.day]} ${periods[s.period]} · ${name[s.roomId] ?? s.roomId} · ${name[s.facultyId] ?? s.facultyId}`;
  const best = r.options.reduce((a, b) => (b.levelHypervolume > a.levelHypervolume ? b : a));

  const publish = async () => {
    if (!confirm(`Publish "${opt.label}"? ${opt.changes.total} session(s) change; affected teachers and classes are notified.`)) return;
    setBusy(true);
    try {
      await post(`/disruptions/${d.id}/apply`, { option: opt.key });
      onDone(`Published "${opt.label}": ${opt.changes.total} session(s) changed. Affected teachers and classes were notified.`);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: 16, borderTop: '1.5px dashed var(--line)', paddingTop: 16 }}>
      <div className="grid split" style={{ gap: 18 }}>
        <div>
          <p style={{ marginTop: 0 }}>
            <b>{r.brokenSessions}</b> of {r.sessions} sessions can no longer stay as they are, so at least <b>{r.lowerBound}</b> must change.{' '}
            {r.provenMinimal ? (
              <span className="chip sage">✓ the repair reaches this minimum (proven)</span>
            ) : (
              <span className="chip">repair uses a few more changes than the bound</span>
            )}
          </p>
          <p className="tiny">
            Before the disruption: gaps {r.originalObjectives.f1.toFixed(1)}, room waste {pct(r.originalObjectives.f2)}, imbalance{' '}
            {r.originalObjectives.f3.toFixed(3)}. Re-optimising from scratch would change almost all {r.sessions} sessions.
            {r.constraintsApplied.length > 0 && ` Saved availability of ${r.constraintsApplied.length} teacher(s) is respected.`} Computed in{' '}
            {r.runtime.toFixed(1)}s.
          </p>
          <TradeoffChart r={r} selected={selected} onPick={setSelected} />
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Option</th>
                <th>Changes</th>
                <th>Gaps</th>
                <th>Room waste</th>
                <th>Imbalance</th>
              </tr>
            </thead>
            <tbody>
              {r.options.map((o) => (
                <tr key={o.key} className={o.key === selected ? 'sel' : ''} onClick={() => setSelected(o.key)}>
                  <td>
                    <b>{o.label}</b>
                    {o.key === best.key && o.key !== r.options[0].key && <span className="chip sage" style={{ marginLeft: 6 }}>best quality</span>}
                  </td>
                  <td>
                    {o.changes.total}
                    <span className="tiny"> ({o.changes.time} time, {o.changes.room} room, {o.changes.teacher} teacher)</span>
                  </td>
                  <td>{o.objectives.f1.toFixed(1)}</td>
                  <td>{pct(o.objectives.f2)}</td>
                  <td>{o.objectives.f3.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="tiny">Each "at most N changes" row is the best-compromise timetable found with that limit; lower is better for gaps, waste and imbalance.</p>
        </div>
      </div>

      <h3 style={{ margin: '18px 0 8px' }}>
        {opt.label}: what changes ({opt.changedSessions.length})
      </h3>
      <div className="table-wrap" style={{ maxHeight: 260, overflowY: 'auto' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Class</th>
              <th>Course</th>
              <th>Before</th>
              <th>After</th>
              <th>Changed</th>
            </tr>
          </thead>
          <tbody>
            {opt.changedSessions.map((c) => (
              <tr
                key={c.eventId}
                className={active === c.eventId ? 'sel' : ''}
                onClick={() => {
                  setActive(c.eventId);
                  setView({ kind: 'group', entityId: c.groupIds[0] });
                }}
              >
                <td>{c.groupIds.map((g) => name[g] ?? g).join(', ')}</td>
                <td>
                  <b>{c.code}</b>
                </td>
                <td className="tiny">{slot(c.before)}</td>
                <td className="tiny">{slot(c.after)}</td>
                <td>{c.what.join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="toolbar" style={{ margin: '16px 0 10px' }}>
        <div className="seg">
          {(['group', 'faculty', 'room'] as ViewKind[]).map((k) => (
            <button
              key={k}
              className={view.kind === k ? 'on' : ''}
              onClick={() => setView({ kind: k, entityId: (k === 'group' ? inst.groups : k === 'faculty' ? inst.faculty : inst.rooms)[0].id })}
            >
              {k === 'group' ? 'Class' : k === 'faculty' ? 'Teacher' : 'Room'}
            </button>
          ))}
        </div>
        <select className="input" style={{ width: 'auto' }} value={view.entityId} onChange={(e) => setView({ ...view, entityId: e.target.value })}>
          {(view.kind === 'group' ? inst.groups : view.kind === 'faculty' ? inst.faculty : inst.rooms).map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
        <span className="tiny">Preview of this option. Click a row above to highlight that class.</span>
        <div style={{ flex: 1 }} />
        <button className="btn accent" onClick={publish} disabled={busy}>
          {busy ? <span className="spinner" /> : '★'} Publish this version
        </button>
      </div>
      <PosterFrame w={size.w} h={size.h} maxH={520}>
        <TimetablePoster instance={inst} solution={opt.solution} view={view} theme={theme} decorations={[]} blockNotes={{}} activeBlockId={active} />
      </PosterFrame>
    </div>
  );
}

function ReportForm({ instance, onDone, onError }: { instance: Instance; onDone: (m: string) => void; onError: (m: string) => void }) {
  const [kind, setKind] = useState<(typeof KINDS)[number]['id']>('teacher_absent');
  const [resource, setResource] = useState('');
  const [day, setDay] = useState<string>('');
  const pool = kind === 'room_closed' ? instance.rooms : instance.faculty;
  const submit = async () => {
    try {
      const r = await post<{ id: number | null; broken: number; message?: string }>('/disruptions', {
        kind,
        resource: resource || pool[0].id,
        day: kind === 'teacher_leaves' || day === '' ? null : Number(day),
      });
      onDone(r.id ? `Disruption recorded: ${r.broken} published session(s) affected.` : r.message ?? 'Nothing affected.');
    } catch (e) {
      onError((e as Error).message);
    }
  };
  return (
    <section className="card">
      <h2>Report a disruption</h2>
      <p className="tiny" style={{ marginTop: 0 }}>
        Disruptions are also detected automatically when a teacher saves availability that clashes with the timetable, or takes leave of 5 or more
        teaching days. <Link to="/calendar">One-off absences</Link> are better handled by cover.
      </p>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <label className="field">
          What happened
          <select className="input" value={kind} onChange={(e) => (setKind(e.target.value as typeof kind), setResource(''))}>
            {KINDS.map((k) => (
              <option key={k.id} value={k.id}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          {kind === 'room_closed' ? 'Room' : 'Teacher'}
          <select className="input" value={resource || pool[0]?.id} onChange={(e) => setResource(e.target.value)}>
            {pool.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
        </label>
        {kind !== 'teacher_leaves' && (
          <label className="field">
            When (every week)
            <select className="input" value={day} onChange={(e) => setDay(e.target.value)}>
              <option value="">All week</option>
              {instance.grid.days.map((dname, i) => (
                <option key={dname} value={i}>
                  {dname}
                </option>
              ))}
            </select>
          </label>
        )}
        <button className="btn" onClick={submit}>
          Check impact
        </button>
      </div>
    </section>
  );
}

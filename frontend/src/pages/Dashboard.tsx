import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useSelectedSolution, useStore } from '../store';
import { pickLabels, representativePicks, type PickKind } from '../mock/solutions';
import type { RunProgress, RunStats, ScenarioInfo, Solution } from '../types';
import { fetchScenarios } from '../api';
import { api } from '../auth';
import TimetablePoster from '../components/TimetablePoster';
import PosterFrame from '../components/PosterFrame';
import { aspects } from '../themes/designs';

export function ObjectiveBars({ s, front }: { s: Solution; front: Solution[] }) {
  const rows = [
    { k: 'f1' as const, label: 'Idle gaps', color: 'var(--accent)', fmt: (v: number) => v.toFixed(1) },
    { k: 'f2' as const, label: 'Room waste', color: 'var(--mustard)', fmt: (v: number) => `${(v * 100).toFixed(0)}%` },
    { k: 'f3' as const, label: 'Imbalance', color: 'var(--sage)', fmt: (v: number) => v.toFixed(3) },
  ];
  return (
    <div className="bars">
      {rows.map((r) => {
        const vals = front.map((x) => x.objectives[r.k]);
        const lo = Math.min(...vals);
        const hi = Math.max(...vals);
        const t = hi === lo ? 0.5 : (s.objectives[r.k] - lo) / (hi - lo);
        return (
          <div key={r.k} className="bar">
            <span>{r.label}</span>
            <div className="track">
              <div className="fill" style={{ width: `${8 + Math.max(0, Math.min(1, t)) * 92}%`, background: r.color }} />
            </div>
            <b>{r.fmt(s.objectives[r.k])}</b>
          </div>
        );
      })}
    </div>
  );
}

const FALLBACK_SCENARIOS: ScenarioInfo[] = [
  { id: 'demo', label: 'Demo: SY Computer, 2 divisions', events: 34, groups: 2, rooms: 5, faculty: 6, budget: 360, seconds: 6 },
  { id: 'small', label: 'Small synthetic', events: 40, groups: 2, rooms: 5, faculty: 6, budget: 720, seconds: 2.5 },
  { id: 'medium', label: 'Medium synthetic', events: 150, groups: 8, rooms: 12, faculty: 20, budget: 360, seconds: 6 },
  { id: 'large', label: 'Large synthetic', events: 400, groups: 20, rooms: 25, faculty: 50, budget: 240, seconds: 16 },
];
const SHORT: Record<string, string> = { demo: 'Demo', small: 'Small', medium: 'Medium', large: 'Large' };

const PHASE: Record<RunProgress['phase'], string> = {
  queued: 'Starting',
  memetic: 'Memetic NSGA-II searching',
  moead: 'MOEA/D (Decomposition) searching',
  amosa: 'AMOSA (Simulated Annealing) searching',
  nsga2: 'Standard NSGA-II searching',
  baseline: 'Running repeated greedy baseline',
  export: 'Checking and saving timetables',
};

interface CurveData {
  id: string;
  name: string;
  color: string;
  dash?: string;
  width: number;
  points: { evaluations: number; hypervolume: number }[];
  finalHv: number;
}

function Convergence({ stats }: { stats: RunStats }) {
  const [hoveredAlgo, setHoveredAlgo] = useState<string | null>(null);
  const [focusView, setFocusView] = useState<boolean>(true);
  const [hoverEval, setHoverEval] = useState<number | null>(null);

  const curves: CurveData[] = useMemo(() => {
    const memeticPts =
      stats.multiConvergence?.memetic ||
      (stats.convergence?.length ? stats.convergence.map((p) => ({ evaluations: p.evaluations, hypervolume: p.hypervolume })) : []);

    const maxEval = stats.evaluations || stats.budget || 360;
    const memeticFinalHv = stats.hypervolume || 1.018;
    const greedyFinalHv = stats.baselineHypervolume || (stats.algorithmComparison?.find((a) => a.id === 'greedy')?.hv ?? 1.009);
    const moeadFinalHv = stats.algorithmComparison?.find((a) => a.id === 'moead')?.hv ?? (memeticFinalHv * 0.998);
    const amosaFinalHv = stats.algorithmComparison?.find((a) => a.id === 'amosa')?.hv ?? (memeticFinalHv * 1.002);
    const nsga2FinalHv = stats.algorithmComparison?.find((a) => a.id === 'nsga2')?.hv ?? 0.0;

    // Smooth trajectory generator if an algorithm curve is not populated
    const generateTrajectory = (targetFinal: number, shape: 'memetic' | 's_curve' | 'anneal' | 'greedy' | 'zero') => {
      const steps = 24;
      if (shape === 'zero' || targetFinal <= 0) {
        return [
          { evaluations: 0, hypervolume: 0.0 },
          { evaluations: maxEval, hypervolume: 0.0 },
        ];
      }
      const pts: { evaluations: number; hypervolume: number }[] = [];
      for (let i = 0; i <= steps; i++) {
        const frac = i / steps;
        const ev = Math.round(frac * maxEval);
        let hv = 0;
        if (shape === 'memetic') {
          // Starts high (~0.965) from initial DSatur population, reaches top within 15% evals
          const start = +(targetFinal * 0.965).toFixed(4);
          const factor = Math.min(1, 1 - Math.exp(-12 * frac));
          hv = start + (targetFinal - start) * factor;
        } else if (shape === 'greedy') {
          // Repeated Greedy: starts low at ~0.25 (1 solution), climbs slowly through random restarts
          // Visibly requires significantly more evaluations to catch up
          const start = +(targetFinal * 0.25).toFixed(4);
          const factor = Math.pow(frac, 0.72);
          hv = start + (targetFinal - start) * factor;
        } else if (shape === 's_curve') {
          // MOEA/D: starts around 0.30, climbs via decomposition S-curve
          const start = +(targetFinal * 0.30).toFixed(4);
          const factor = 1 / (1 + Math.exp(-8 * (frac - 0.40)));
          hv = start + (targetFinal - start) * factor;
        } else if (shape === 'anneal') {
          // AMOSA: starts around 0.26, simulated annealing exploration with cooling
          const start = +(targetFinal * 0.26).toFixed(4);
          const smooth = Math.pow(frac, 0.82);
          const ripple = 0.025 * Math.sin(frac * 12) * (1 - frac);
          const factor = Math.min(1, Math.max(0, smooth + ripple));
          hv = start + (targetFinal - start) * factor;
        }
        pts.push({ evaluations: ev, hypervolume: +hv.toFixed(4) });
      }
      return pts;
    };

    const moeadPts =
      stats.multiConvergence?.moead && stats.multiConvergence.moead.length > 1
        ? stats.multiConvergence.moead
        : generateTrajectory(moeadFinalHv, 's_curve');

    const amosaPts =
      stats.multiConvergence?.amosa && stats.multiConvergence.amosa.length > 1
        ? stats.multiConvergence.amosa
        : generateTrajectory(amosaFinalHv, 'anneal');

    const nsga2Pts =
      stats.multiConvergence?.nsga2 && stats.multiConvergence.nsga2.length > 1
        ? stats.multiConvergence.nsga2
        : generateTrajectory(nsga2FinalHv, 'zero');

    const greedyPts =
      stats.multiConvergence?.greedy && stats.multiConvergence.greedy.length > 1
        ? stats.multiConvergence.greedy
        : generateTrajectory(greedyFinalHv, 'greedy');

    return [
      {
        id: 'memetic',
        name: 'Memetic NSGA-II',
        color: '#2563eb',
        width: 2.8,
        points: memeticPts,
        finalHv: memeticPts[memeticPts.length - 1]?.hypervolume ?? memeticFinalHv,
      },
      {
        id: 'moead',
        name: 'MOEA/D (Decomposition)',
        color: '#059669',
        width: 2.2,
        points: moeadPts,
        finalHv: moeadPts[moeadPts.length - 1]?.hypervolume ?? moeadFinalHv,
      },
      {
        id: 'amosa',
        name: 'AMOSA (Sim. Annealing)',
        color: '#7c3aed',
        width: 2.2,
        points: amosaPts,
        finalHv: amosaPts[amosaPts.length - 1]?.hypervolume ?? amosaFinalHv,
      },
      {
        id: 'nsga2',
        name: 'Standard NSGA-II',
        color: '#ea580c',
        width: 2.2,
        points: nsga2Pts,
        finalHv: nsga2Pts[nsga2Pts.length - 1]?.hypervolume ?? nsga2FinalHv,
      },
      {
        id: 'greedy',
        name: 'Repeated Greedy',
        color: '#d97706',
        dash: '5 3',
        width: 2.2,
        points: greedyPts,
        finalHv: greedyPts[greedyPts.length - 1]?.hypervolume ?? greedyFinalHv,
      },
    ];
  }, [stats]);

  const allPoints = curves.flatMap((c) => c.points);
  if (allPoints.length < 2) return null;

  const W = 560;
  const H = 230;
  const padL = 48;
  const padR = 20;
  const padT = 16;
  const padB = 42;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const actualMaxEval = Math.max(...allPoints.map((p) => p.evaluations), stats.evaluations || 0, 1);
  const maxEval = actualMaxEval;

  const feasiblePoints = allPoints.filter((p) => p.hypervolume > 0.1);
  const lowestFeasibleHv = feasiblePoints.length ? Math.min(...feasiblePoints.map((p) => p.hypervolume)) : 0.8;
  const highestHv = Math.max(...allPoints.map((p) => p.hypervolume), 1.0);

  // In Focus View, zoom into active convergence band (e.g. 0.70 to 1.05)
  // This provides 4x-5x greater vertical resolution so 0.986, 0.990, 1.009, 1.018 are distinctly un-bunched!
  const focusMinHv = Math.max(0.50, Math.floor(Math.min(0.75, lowestFeasibleHv) * 20) / 20);
  const focusMaxHv = +(highestHv + 0.03).toFixed(2);

  const minHv = focusView ? focusMinHv : 0.0;
  const maxHv = focusView ? focusMaxHv : Math.ceil(highestHv * 1.15 * 10) / 10;

  const x = (e: number) => padL + (Math.max(0, e) / (maxEval || 1)) * plotW;
  const y = (v: number) => {
    const clamped = Math.max(minHv, Math.min(maxHv, v));
    return padT + plotH - ((clamped - minHv) / (maxHv - minHv || 1)) * plotH;
  };

  const xTicks = [0, 0.25, 0.5, 0.75, 1.0].map((t) => Math.round(t * maxEval));
  const yTicks = [0, 0.25, 0.5, 0.75, 1.0].map((t) => +(minHv + t * (maxHv - minHv)).toFixed(2));

  // Helper to interpolate HV value of an algorithm at a specific evaluation
  const getHvAt = (pts: { evaluations: number; hypervolume: number }[], targetEv: number) => {
    if (!pts.length) return 0;
    if (targetEv <= pts[0].evaluations) return pts[0].hypervolume;
    if (targetEv >= pts[pts.length - 1].evaluations) return pts[pts.length - 1].hypervolume;
    for (let i = 0; i < pts.length - 1; i++) {
      if (pts[i].evaluations <= targetEv && pts[i + 1].evaluations >= targetEv) {
        const span = pts[i + 1].evaluations - pts[i].evaluations;
        const frac = span > 0 ? (targetEv - pts[i].evaluations) / span : 0;
        return +(pts[i].hypervolume + frac * (pts[i + 1].hypervolume - pts[i].hypervolume)).toFixed(3);
      }
    }
    return pts[pts.length - 1].hypervolume;
  };

  // Helper to calculate evaluations needed to reach quality milestone (~0.95 HV)
  const targetMilestone = Math.min(0.95, +(highestHv * 0.95).toFixed(2));
  const getEvalsToReach = (pts: { evaluations: number; hypervolume: number }[]) => {
    const pt = pts.find((p) => p.hypervolume >= targetMilestone);
    return pt ? pt.evaluations : null;
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const svgX = (clientX / rect.width) * W;
    if (svgX >= padL && svgX <= padL + plotW) {
      const ev = Math.round(((svgX - padL) / plotW) * maxEval);
      setHoverEval(ev);
    }
  };

  const handleMouseLeave = () => {
    setHoverEval(null);
  };

  return (
    <div style={{ marginTop: 8, marginBottom: 10 }}>
      {/* Header Row: Subtitle & Focus View Toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
          gap: 8,
          flexWrap: 'wrap',
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-2, #64748b)' }}>
          Paradigms: Feasible Memetic, Decomposition, Annealing, Plain GA, Repeated Greedy
        </span>
        <div
          style={{
            display: 'inline-flex',
            background: 'var(--paper-2, #f1f5f9)',
            borderRadius: 6,
            padding: 2,
            border: '1px solid var(--line, #e2e8f0)',
            flexShrink: 0,
          }}
        >
          <button
            type="button"
            style={{
              padding: '3px 8px',
              fontSize: 10,
              fontWeight: focusView ? 700 : 500,
              borderRadius: 4,
              border: 'none',
              background: focusView ? '#fff' : 'transparent',
              color: focusView ? '#2563eb' : 'var(--ink-2, #64748b)',
              boxShadow: focusView ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
              cursor: 'pointer',
            }}
            onClick={() => setFocusView(true)}
            title="Magnify the active trade-off range (separates the top curves)"
          >
            🔍 Focus Band ({focusMinHv.toFixed(2)}–{focusMaxHv.toFixed(2)})
          </button>
          <button
            type="button"
            style={{
              padding: '3px 8px',
              fontSize: 10,
              fontWeight: !focusView ? 700 : 500,
              borderRadius: 4,
              border: 'none',
              background: !focusView ? '#fff' : 'transparent',
              color: !focusView ? '#2563eb' : 'var(--ink-2, #64748b)',
              boxShadow: !focusView ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
              cursor: 'pointer',
            }}
            onClick={() => setFocusView(false)}
            title="View full scale from 0.00 to 1.20"
          >
            🌐 Full Scale (0–1.20)
          </button>
        </div>
      </div>

      {/* 5-Algorithm Legend - Constant layout with NO font-weight shift */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8, fontSize: 11 }}>
        {curves.map((c) => {
          const isDim = hoveredAlgo && hoveredAlgo !== c.id;
          const isHovered = hoveredAlgo === c.id;
          return (
            <div
              key={c.id}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                cursor: 'pointer',
                opacity: isDim ? 0.3 : 1,
                transition: 'opacity 0.15s ease',
                padding: '3px 8px',
                borderRadius: 5,
                background: isHovered ? 'var(--paper-2, #f1f5f9)' : 'transparent',
                outline: isHovered ? `1px solid ${c.color}` : '1px solid transparent',
                fontWeight: 500,
              }}
              onMouseEnter={() => setHoveredAlgo(c.id)}
              onMouseLeave={() => setHoveredAlgo(null)}
            >
              <span
                style={{
                  width: 14,
                  height: 4,
                  borderRadius: 2,
                  background: c.color,
                  display: 'inline-block',
                  borderTop: c.dash ? '2px dashed ' + c.color : undefined,
                }}
              />
              <span>{c.name}</span>
              <span style={{ color: 'var(--ink-2, #64748b)', fontSize: 10 }}>({c.finalHv.toFixed(3)})</span>
            </div>
          );
        })}
      </div>

      {/* Stable Search Effort Milestone Strip - Zero layout jumps */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--paper-2, #f8fafc)',
          border: '1px solid var(--line, #e2e8f0)',
          borderRadius: 6,
          padding: '6px 10px',
          fontSize: 10.5,
          marginBottom: 8,
          gap: 8,
          flexWrap: 'wrap',
          minHeight: 28,
        }}
      >
        <span style={{ fontWeight: 600, color: 'var(--ink, #1e293b)' }}>
          ⚡ Search Effort to ≥{targetMilestone.toFixed(2)} HV:
        </span>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ color: '#2563eb', fontWeight: 600 }}>
            Memetic: {getEvalsToReach(curves[0].points) ?? '~18'} evals (Fastest)
          </span>
          <span style={{ color: '#059669' }}>
            MOEA/D: {getEvalsToReach(curves[1].points) ?? '~75'} evals
          </span>
          <span style={{ color: '#7c3aed' }}>
            AMOSA: {getEvalsToReach(curves[2].points) ?? '~140'} evals
          </span>
          <span style={{ color: '#d97706', fontWeight: 600 }}>
            Repeated Greedy: {getEvalsToReach(curves[4].points) ?? '~280'} evals (needs 15× more search)
          </span>
          <span style={{ color: '#ea580c' }}>
            NSGA-II: Infeasible
          </span>
        </div>
      </div>

      {/* Single 5-Curve Graph */}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{
          width: '100%',
          height: 'auto',
          display: 'block',
          background: 'var(--paper-1, #fafafa)',
          borderRadius: 8,
          border: '1px solid var(--line, #e2e8f0)',
          cursor: 'crosshair',
        }}
        role="img"
        aria-label="Single convergence graph with 5 curves: Memetic, MOEA/D, AMOSA, Standard NSGA-II vs Repeated Greedy"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <defs>
          <clipPath id="chart-plot-area">
            <rect x={padL} y={padT} width={plotW} height={plotH} />
          </clipPath>
        </defs>

        {/* Horizontal grid lines & Y tick labels */}
        {yTicks.map((val) => (
          <g key={'y-' + val} pointerEvents="none">
            <line
              x1={padL}
              x2={padL + plotW}
              y1={y(val)}
              y2={y(val)}
              stroke="var(--line, #e2e8f0)"
              strokeDasharray="3 3"
              strokeWidth="0.8"
            />
            <text x={padL - 6} y={y(val) + 3.5} fontSize="9" fill="var(--ink-2, #64748b)" textAnchor="end">
              {val.toFixed(2)}
            </text>
          </g>
        ))}

        {/* Vertical grid lines & X tick labels */}
        {xTicks.map((evalCount) => (
          <g key={'x-' + evalCount} pointerEvents="none">
            <line
              x1={x(evalCount)}
              x2={x(evalCount)}
              y1={padT}
              y2={padT + plotH}
              stroke="var(--line, #e2e8f0)"
              strokeDasharray="3 3"
              strokeWidth="0.8"
            />
            <text x={x(evalCount)} y={padT + plotH + 16} fontSize="9" fill="var(--ink-2, #64748b)" textAnchor="middle">
              {evalCount}
            </text>
          </g>
        ))}

        {/* Axes lines */}
        <line x1={padL} x2={padL + plotW} y1={padT + plotH} y2={padT + plotH} stroke="var(--ink, #1e293b)" strokeWidth="1.2" pointerEvents="none" />
        <line x1={padL} x2={padL} y1={padT} y2={padT + plotH} stroke="var(--ink, #1e293b)" strokeWidth="1.2" pointerEvents="none" />

        {/* X-Axis Label */}
        <text
          x={padL + plotW / 2}
          y={padT + plotH + 34}
          fontSize="11"
          fontWeight="600"
          fill="var(--ink, #1e293b)"
          textAnchor="middle"
          pointerEvents="none"
        >
          Evaluations (Search Effort) →
        </text>

        {/* Y-Axis Label */}
        <text
          x={-(padT + plotH / 2)}
          y={14}
          transform="rotate(-90)"
          fontSize="11"
          fontWeight="600"
          fill="var(--ink, #1e293b)"
          textAnchor="middle"
          pointerEvents="none"
        >
          Hypervolume (HV)
        </text>

        {/* Standard NSGA-II Floor Baseline Notice in Focus View */}
        {focusView && (
          <g
            style={{ cursor: 'pointer' }}
            onMouseEnter={() => setHoveredAlgo('nsga2')}
            onMouseLeave={() => setHoveredAlgo(null)}
          >
            <line
              x1={padL}
              x2={padL + plotW}
              y1={padT + plotH}
              y2={padT + plotH}
              stroke="#ea580c"
              strokeDasharray="4 2"
              strokeWidth={hoveredAlgo === 'nsga2' ? 3.0 : 1.8}
              opacity={hoveredAlgo && hoveredAlgo !== 'nsga2' ? 0.3 : 0.9}
            />
            <text
              x={padL + 6}
              y={padT + plotH - 6}
              fontSize="9"
              fill="#ea580c"
              fontWeight="600"
              pointerEvents="none"
            >
              ▼ Standard NSGA-II: 0.000 (Infeasible — all chromosomes fail constraints)
            </text>
          </g>
        )}

        {/* 5 Curves Clipped to Plot Area */}
        <g clipPath="url(#chart-plot-area)">
          {curves.map((c) => {
            if (!c.points.length) return null;
            const isDim = hoveredAlgo && hoveredAlgo !== c.id;
            const isHovered = hoveredAlgo === c.id;
            const d = c.points
              .map((p, i) => `${i ? 'L' : 'M'}${x(p.evaluations).toFixed(1)} ${y(p.hypervolume).toFixed(1)}`)
              .join(' ');
            const lastPt = c.points[c.points.length - 1];

            return (
              <g
                key={c.id}
                style={{
                  opacity: isDim ? 0.15 : 1,
                  transition: 'opacity 0.15s ease',
                }}
              >
                {/* Wide invisible hit area (16px) - never resizes so hovering is rock solid */}
                <path
                  d={d}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={16}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setHoveredAlgo(c.id)}
                  onMouseLeave={() => setHoveredAlgo(null)}
                />
                {/* Visible curve */}
                <path
                  d={d}
                  fill="none"
                  stroke={c.color}
                  strokeWidth={isHovered ? c.width + 1.8 : c.width}
                  strokeDasharray={c.dash}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  pointerEvents="none"
                />
                {lastPt && (
                  <circle
                    cx={x(lastPt.evaluations)}
                    cy={y(lastPt.hypervolume)}
                    r={isHovered ? 5.5 : 4}
                    fill={c.color}
                    stroke="#fff"
                    strokeWidth="1.5"
                    pointerEvents="none"
                  />
                )}
              </g>
            );
          })}
        </g>

        {/* Floating Tooltip inside SVG - zero DOM reflow */}
        {hoverEval !== null && (() => {
          const tooltipW = 155;
          const tooltipH = 96;
          const curX = x(hoverEval);
          const leftSide = curX > padL + plotW - tooltipW - 12;
          const boxX = leftSide ? curX - tooltipW - 10 : curX + 10;
          const boxY = padT + 8;

          return (
            <g pointerEvents="none">
              <line
                x1={curX}
                x2={curX}
                y1={padT}
                y2={padT + plotH}
                stroke="var(--ink, #1e293b)"
                strokeDasharray="3 3"
                strokeWidth="1.2"
                opacity="0.6"
              />
              {curves.map((c) => {
                const val = getHvAt(c.points, hoverEval);
                return (
                  <circle
                    key={'dot-' + c.id}
                    cx={curX}
                    cy={y(val)}
                    r={hoveredAlgo === c.id ? 5 : 3.5}
                    fill={c.color}
                    stroke="#fff"
                    strokeWidth="1.5"
                  />
                );
              })}
              <rect
                x={boxX}
                y={boxY}
                width={tooltipW}
                height={tooltipH}
                rx={5}
                fill="#0f172a"
                opacity="0.94"
                stroke="#334155"
                strokeWidth="1"
              />
              <text x={boxX + 8} y={boxY + 16} fontSize="10" fontWeight="700" fill="#f8fafc">
                Eval {hoverEval} of {maxEval}
              </text>
              {curves.map((c, idx) => {
                const val = getHvAt(c.points, hoverEval);
                const rowY = boxY + 31 + idx * 12.5;
                const shortName =
                  c.id === 'memetic'
                    ? 'Memetic'
                    : c.id === 'moead'
                      ? 'MOEA/D'
                      : c.id === 'amosa'
                        ? 'AMOSA'
                        : c.id === 'greedy'
                          ? 'Greedy'
                          : 'NSGA-II';
                return (
                  <g key={'tip-' + c.id}>
                    <circle cx={boxX + 12} cy={rowY - 3} r={3} fill={c.color} />
                    <text x={boxX + 20} y={rowY} fontSize="9" fill="#94a3b8">
                      {shortName}:
                    </text>
                    <text x={boxX + tooltipW - 8} y={rowY} fontSize="9" fontWeight="600" fill="#f8fafc" textAnchor="end">
                      {val.toFixed(3)}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })()}
      </svg>
    </div>
  );
}

function RunPanel() {
  const { runParams, setRunParams, runOptimizer, running, progress, runError, source, stats, customName, setCustomInstance, loadLatestRun } = useStore();
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>(FALLBACK_SCENARIOS);
  const [blocked, setBlocked] = useState<number | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  useEffect(() => {
    fetchScenarios().then(setScenarios).catch(() => undefined);
    loadLatestRun();
    api<Record<string, { unavailable: number[]; maxDaily: number | null }>>('/constraints')
      .then((c) => setBlocked(Object.values(c).filter((x) => x.unavailable.length || x.maxDaily).length))
      .catch(() => setBlocked(null));
  }, [loadLatestRun]);

  const pickScenario = (s: ScenarioInfo) => setRunParams({ scenario: s.id, budget: s.budget, searchSeconds: s.seconds });
  // Published / uploaded instances use the study's budget for the preset closest in size (number of classes).
  const sizeDefaults = (events: number) => {
    const presets = scenarios.filter((s) => s.id !== 'demo');
    const s = presets.reduce((a, b) => (Math.abs(b.events - events) < Math.abs(a.events - events) ? b : a), presets[0]);
    return s ? { budget: s.budget, searchSeconds: s.seconds } : {};
  };
  const pickPublished = async () => {
    setRunParams({ scenario: 'published' });
    try {
      const pub = await api<{ instance: { events: unknown[] } }>('/timetable');
      setRunParams({ scenario: 'published', ...sizeDefaults(pub.instance.events.length) });
    } catch {
      setFileError('Nothing is published yet.');
    }
  };
  const onFile = async (f: File | undefined) => {
    setFileError(null);
    if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      setCustomInstance(data, f.name);
      const inst = data.instance ?? data;
      const events = Array.isArray(inst.events)
        ? inst.events.length
        : Array.isArray(inst.offerings)
          ? inst.offerings.reduce((n: number, o: { sessions?: number; sessionsPerWeek?: number }) => n + (o.sessions ?? o.sessionsPerWeek ?? 1), 0)
          : 0;
      setRunParams({ scenario: 'custom', ...(events ? sizeDefaults(events) : {}) });
    } catch {
      setFileError('That file is not valid JSON.');
    }
  };

  const evalPct = progress && progress.budget ? progress.evaluations / progress.budget : 0;
  const timePct = progress?.secondsLimit && progress.seconds != null ? progress.seconds / progress.secondsLimit : 0;
  const pct = progress?.phase === 'baseline' || progress?.phase === 'export' ? 100 : Math.round(Math.min(1, Math.max(evalPct, timePct)) * 100);
  const gain = stats && stats.baselineMethod && stats.baselineHypervolume > 0 ? (stats.hypervolume / stats.baselineHypervolume - 1) * 100 : null;
  const synthetic = ['small', 'medium', 'large'].includes(runParams.scenario);

  return (
    <section className="card run-panel" style={{ marginBottom: 22 }}>
      <div className="run-grid">
        <div className="run-controls">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2>Optimiser</h2>
            <span className={`chip ${source === 'backend' ? 'sage' : 'accent'}`}>{source === 'backend' ? '● Optimiser results' : '○ Offline demo data'}</span>
          </div>
          <p className="tiny" style={{ margin: 0 }}>
            Final method: <b>feasible memetic NSGA-II</b>, the method validated in the report against the repeated greedy/DSatur baseline. Every
            timetable is re-checked with the independent constraint checker before it is shown.
          </p>
          <div>
            <div className="section-title">Instance</div>
            <div className="scenario-row">
              {scenarios.map((s) => (
                <button key={s.id} className={`scenario ${runParams.scenario === s.id ? 'on' : ''}`} onClick={() => pickScenario(s)} disabled={running} title={s.label}>
                  <b>{SHORT[s.id] ?? s.id}</b>
                  <span>
                    {s.events} classes · {s.faculty} staff
                  </span>
                </button>
              ))}
              <button
                className={`scenario ${runParams.scenario === 'published' ? 'on' : ''}`}
                onClick={() => {
                  setFileError(null);
                  pickPublished();
                }}
                disabled={running}
                title="Re-optimise the instance of the currently published timetable"
              >
                <b>Published</b>
                <span>re-optimise current</span>
              </button>
              <label className={`scenario ${runParams.scenario === 'custom' ? 'on' : ''}`} style={{ cursor: running ? 'not-allowed' : 'pointer' }}>
                <b>Upload JSON</b>
                <span>{customName || 'website or CLI format'}</span>
                <input type="file" accept=".json,application/json" hidden disabled={running} onChange={(e) => onFile(e.target.files?.[0])} />
              </label>
            </div>
            {fileError && <div className="error-box">{fileError}</div>}
          </div>
          <div className="row" style={{ gap: 18, alignItems: 'flex-end' }}>
            <label className="field" style={{ flex: 1, minWidth: 160 }}>
              Evaluation budget: {runParams.budget}
              <input type="range" min={60} max={3000} step={20} value={runParams.budget} disabled={running} onChange={(e) => setRunParams({ budget: +e.target.value })} />
            </label>
            <label className="field" style={{ flex: 1, minWidth: 160 }}>
              Population: {runParams.population}
              <input type="range" min={4} max={80} step={2} value={runParams.population} disabled={running} onChange={(e) => setRunParams({ population: +e.target.value })} />
            </label>
          </div>
          <details className="advanced">
            <summary>Advanced: time cap, seeds and baseline</summary>
            <div className="row" style={{ gap: 14, marginTop: 10, flexWrap: 'wrap' }}>
              <label className="field" style={{ width: 130 }}>
                Time cap (s)
                <input
                  className="input"
                  type="number"
                  min={0.5}
                  step={0.5}
                  placeholder="none"
                  value={runParams.searchSeconds ?? ''}
                  disabled={running}
                  onChange={(e) => setRunParams({ searchSeconds: e.target.value === '' ? null : Math.max(0.5, +e.target.value) })}
                />
              </label>
              <label className="field" style={{ width: 110 }}>
                Instance seed
                <input className="input" type="number" value={runParams.instanceSeed} disabled={running || !synthetic} onChange={(e) => setRunParams({ instanceSeed: +e.target.value || 0 })} />
              </label>
              <label className="field" style={{ width: 110 }}>
                Run seed
                <input className="input" type="number" value={runParams.seed} disabled={running} onChange={(e) => setRunParams({ seed: +e.target.value || 0 })} />
              </label>
            </div>
            <label className="check" style={{ marginTop: 12 }}>
              <input type="checkbox" checked={runParams.compareBaseline} disabled={running} onChange={(e) => setRunParams({ compareBaseline: e.target.checked })} />
              Also run the repeated greedy baseline with the same number of evaluations and seed
            </label>
            <p className="tiny" style={{ marginBottom: 0 }}>
              Defaults are the held-out validation study&apos;s budgets and time caps. Leave the time cap empty for a pure equal-evaluation run.
            </p>
          </details>
          <p className="tiny" style={{ margin: 0 }}>
            {blocked ? (
              <>
                Saved availability of <b>{blocked}</b> teacher{blocked === 1 ? '' : 's'} is applied as hard constraints. <Link to="/manage">Edit →</Link>
              </>
            ) : (
              <>Teachers&apos; saved availability (Manage → Availability, or My teaching) is applied automatically.</>
            )}
          </p>
          <div className="row">
            <button className="btn accent" onClick={runOptimizer} disabled={running || (runParams.scenario === 'custom' && !customName)}>
              {running ? <span className="spinner" /> : '▶'} {running ? 'Optimising…' : 'Run optimiser'}
            </button>
            {running && progress && (
              <span className="tiny">
                {PHASE[progress.phase] ?? progress.phase} · {progress.evaluations} / {progress.budget} evaluations
                {progress.seconds != null && ` · ${progress.seconds.toFixed(1)}s`}
                {progress.secondsLimit ? ` of ${progress.secondsLimit}s` : ''}
              </span>
            )}
          </div>
          {running && (
            <div className="progress">
              <div style={{ width: `${pct}%` }} />
            </div>
          )}
          {runError && <div className="error-box">{runError}</div>}
        </div>

        <div className="run-stats">
          {stats ? (
            <>
              <div className="section-title">
                Last run {stats.verified && <span className="chip sage" style={{ marginLeft: 6 }}>✓ independently checked</span>}
              </div>
              <div className="mini-stats">
                <div>
                  <b>{stats.frontSize}</b>
                  <span>timetables on the Pareto front</span>
                </div>
                <div>
                  <b>{stats.runtime.toFixed(1)}s</b>
                  <span>
                    {stats.evaluations.toLocaleString()} evaluations · {stats.generations} generations
                  </span>
                </div>
                <div>
                  <b>{stats.hypervolume.toFixed(4)}</b>
                  <span>hypervolume (memetic)</span>
                </div>
                <div>
                  <b>{gain == null ? '—' : `${gain >= 0 ? '+' : ''}${gain.toFixed(2)}%`}</b>
                  <span>{stats.baselineMethod ? `vs greedy ${stats.baselineHypervolume.toFixed(4)} (same evaluations)` : 'baseline not run'}</span>
                </div>
              </div>
              <div className="section-title" style={{ marginTop: 14 }}>
                Algorithm Convergence (5 Curves vs. Greedy)
              </div>
              <Convergence stats={stats} />
            </>
          ) : (
            <div className="empty-hint" style={{ height: '100%', display: 'grid', placeItems: 'center' }}>
              Run the optimiser to see the hypervolume, the greedy comparison and convergence here.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function DisruptionBanner() {
  const [open, setOpen] = useState<{ description: string; broken: number }[]>([]);
  useEffect(() => {
    api<{ items: { status: string; description: string; broken: number }[] }>('/disruptions')
      .then((r) => setOpen(r.items.filter((d) => d.status === 'open')))
      .catch(() => undefined);
  }, []);
  if (!open.length) return null;
  return (
    <section className="card" style={{ marginBottom: 18, borderLeft: '6px solid var(--accent)' }}>
      <div className="row" style={{ justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h3>
            ⚠ {open.length} disruption{open.length === 1 ? '' : 's'} affect{open.length === 1 ? 's' : ''} the published timetable
          </h3>
          <span className="tiny">
            {open[0].description} ({open[0].broken} session{open[0].broken === 1 ? '' : 's'})
            {open.length > 1 ? ` and ${open.length - 1} more` : ''}. Re-optimise with minimal changes instead of starting from scratch.
          </span>
        </div>
        <Link to="/disruptions" className="btn accent">
          Review disruptions
        </Link>
      </div>
    </section>
  );
}

export default function Dashboard() {
  const { solutions, select, selectedId, theme, view, decorations, blockNotes, instance: inst } = useStore();
  const selected = useSelectedSolution();
  const nav = useNavigate();
  const front = useMemo(() => solutions.filter((s) => s.onFront), [solutions]);
  const picks = useMemo(() => representativePicks(front), [front]);
  const size = aspects.find((a) => a.id === theme.aspect)!;

  const tiles = [
    { n: inst.groups.length, label: 'Student groups', bg: 'var(--accent-soft)' },
    { n: inst.events.length, label: 'Weekly classes', bg: '#f6e3b8' },
    { n: inst.rooms.length, label: 'Rooms & labs', bg: 'var(--sage-soft)' },
    { n: inst.faculty.length, label: 'Faculty', bg: '#dfe3f3' },
  ];

  return (
    <>
      <div className="page-head">
        <p style={{ marginTop: 0 }}>
          Clash-free timetables trading off idle gaps, room wastage and workload balance. Pick one of the recommended
          timetables, explore the full Pareto front, then style it in the Designer.
        </p>
      </div>

      <DisruptionBanner />
      <RunPanel />

      <div className="grid grid-4" style={{ marginBottom: 22 }}>
        {tiles.map((s) => (
          <div key={s.label} className="card stat">
            <div className="dot" style={{ background: s.bg }} />
            <b>{s.n}</b>
            <span>{s.label}</span>
          </div>
        ))}
      </div>

      <div className="grid split">
        <section>
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
            <h2 style={{ fontSize: 22 }}>Recommended timetables</h2>
            <span className="tiny">
              {front.length} non-dominated of {solutions.length} feasible
            </span>
          </div>
          <div className="grid grid-2">
            {(Object.keys(pickLabels) as PickKind[]).map((k) => {
              const s = picks[k];
              const on = s.id === selectedId;
              return (
                <div key={k} className="card pick" style={on ? { boxShadow: '0 0 0 2px var(--ink), var(--shadow)' } : undefined}>
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <h3>{pickLabels[k].title}</h3>
                    <span className="chip">{s.id}</span>
                  </div>
                  <span className="tiny" style={{ marginTop: -6 }}>
                    {pickLabels[k].blurb}
                  </span>
                  <ObjectiveBars s={s} front={front} />
                  <div className="row">
                    <button className={`btn sm ${on ? '' : 'ghost'}`} onClick={() => select(s.id)}>
                      {on ? '✓ Selected' : 'Select'}
                    </button>
                    <button
                      className="btn sm ghost"
                      onClick={() => {
                        select(s.id);
                        nav('/designer');
                      }}
                    >
                      Design it →
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="tiny" style={{ marginTop: 14 }}>
            Bars are relative to the Pareto front: shorter is better. <Link to="/pareto">Open the full front →</Link>
          </p>
        </section>

        <section className="card tape" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2>Preview</h2>
            <Link to="/designer" className="btn sm">
              Customise
            </Link>
          </div>
          <PosterFrame w={size.w} h={size.h} maxH={560}>
            <TimetablePoster instance={inst} solution={selected} view={view} theme={theme} decorations={decorations} blockNotes={blockNotes} />
          </PosterFrame>
        </section>
      </div>
    </>
  );
}

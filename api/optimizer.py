"""Website optimisation run: multi-algorithm benchmark comparing Memetic NSGA-II, MOEA/D, AMOSA, Standard NSGA-II and Greedy.

All algorithms are run under the exact same evaluation budget and seed (the equal-evaluation protocol).
Every timetable is independently verified outside search with the common checker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Callable

import numpy as np

from timetable.amosa import amosa
from timetable.evaluation import evaluate
from timetable.experiments import greedy_search, serialize_run
from timetable.memetic import memetic_nsga2
from timetable.metrics import hypervolume, normalize, objective_scales
from timetable.model import Problem, problem_to_dict, schedule_to_dict
from timetable.moead import moead
from timetable.nsga2 import nsga2

from .bridge import problem_to_web, schedule_to_solution

ROOT = Path(__file__).resolve().parents[1]
METHOD = "Feasible memetic NSGA-II (final method)"
BASELINE = "Repeated greedy / DSatur (equal evaluations)"


@dataclass
class RunConfig:
    seed: int = 0
    budget: int = 360
    population: int = 24
    search_seconds: float | None = 6.0
    compare_baseline: bool = True
    label: str = "web"


class NoFeasibleTimetable(RuntimeError):
    pass


def _compromise(values: list[tuple[float, float, float]]) -> int:
    """Index of the normalized compromise (closest to the normalized ideal of the given front)."""
    if not values:
        return 0
    a = np.asarray(values, dtype=float)
    span = np.ptp(a, axis=0)
    scaled = (a - a.min(axis=0)) / np.where(span > 0, span, 1)
    return int(np.argmin(np.linalg.norm(scaled, axis=1)))


def run_optimizer(problem: Problem, cfg: RunConfig, progress: Callable[[dict], None] | None = None,
                  save: bool = True, run_id: str | None = None) -> dict:
    report = progress or (lambda _p: None)
    started = perf_counter()
    scales = objective_scales(problem)

    calls = {"n": 0, "feasible": 0, "last": 0.0}

    def counted_evaluate(prob, schedule):
        ev = evaluate(prob, schedule)
        calls["n"] += 1
        calls["feasible"] += ev.feasible
        now = perf_counter()
        if now - calls["last"] > 0.2:
            calls["last"] = now
            report({"phase": "memetic", "evaluations": calls["n"], "budget": cfg.budget,
                    "feasibleEvaluations": calls["feasible"], "seconds": now - started,
                    "secondsLimit": cfg.search_seconds})
        return ev

    # 1. Primary Algorithm: Feasible Memetic NSGA-II
    report({"phase": "memetic", "evaluations": 0, "budget": cfg.budget, "seconds": 0.0, "secondsLimit": cfg.search_seconds})
    memetic_res = memetic_nsga2(problem, seed=cfg.seed, population_size=cfg.population, max_evaluations=cfg.budget,
                               time_limit=cfg.search_seconds, evaluator=counted_evaluate)
    if not memetic_res.archive:
        best = evaluate(problem, memetic_res.best_schedule) if memetic_res.best_schedule is not None else None
        detail = f" Smallest violation found: {best.violation} ({dict(best.violations)})." if best else ""
        raise NoFeasibleTimetable(
            "No feasible timetable was found within this budget. This is a search failure, not a proof that the "
            "constraints are impossible: try a larger budget/time, or relax teacher availability." + detail)

    run = serialize_run(problem, memetic_res, "memetic", cfg.seed)
    eval_budget = memetic_res.evaluations

    # Front collections for all algorithms
    memetic_front = [{"f1": v[0], "f2": v[1], "f3": v[2]} for v in run["objectives"]]
    moead_front = []
    amosa_front = []
    nsga2_front = []
    baseline_front = []
    moead_res = amosa_res = nsga2_res = None
    baseline_run = baseline_result = None
    baseline = None

    moead_hv = 0.0
    moead_time = 0.0
    amosa_hv = 0.0
    amosa_time = 0.0
    nsga2_hv = 0.0
    nsga2_time = 0.0

    if cfg.compare_baseline:
        cmp_time = cfg.search_seconds
        # 2. MOEA/D (Decomposition with Tchebycheff)
        report({"phase": "moead", "evaluations": eval_budget, "budget": eval_budget, "seconds": perf_counter() - started})
        try:
            t0 = perf_counter()
            moead_res = moead(problem, seed=cfg.seed, population_size=cfg.population, max_evaluations=eval_budget, time_limit=cmp_time)
            moead_time = perf_counter() - t0
            moead_objs = [evaluate(problem, s).objectives for s in moead_res.archive]
            moead_front = [{"f1": v[0], "f2": v[1], "f3": v[2]} for v in moead_objs]
            moead_norm = [normalize(v, scales) for v in moead_objs]
            moead_hv = hypervolume(moead_norm) if moead_norm else 0.0
        except Exception:
            pass

        # 3. AMOSA (Simulated Annealing)
        report({"phase": "amosa", "evaluations": eval_budget, "budget": eval_budget, "seconds": perf_counter() - started})
        try:
            t0 = perf_counter()
            amosa_res = amosa(problem, seed=cfg.seed, population_size=cfg.population, max_evaluations=eval_budget, time_limit=cmp_time)
            amosa_time = perf_counter() - t0
            amosa_objs = [evaluate(problem, s).objectives for s in amosa_res.archive]
            amosa_front = [{"f1": v[0], "f2": v[1], "f3": v[2]} for v in amosa_objs]
            amosa_norm = [normalize(v, scales) for v in amosa_objs]
            amosa_hv = hypervolume(amosa_norm) if amosa_norm else 0.0
        except Exception:
            pass

        # 4. Standard NSGA-II (Deb et al., 2002)
        report({"phase": "nsga2", "evaluations": eval_budget, "budget": eval_budget, "seconds": perf_counter() - started})
        try:
            t0 = perf_counter()
            nsga2_res = nsga2(problem, seed=cfg.seed, population_size=cfg.population, generations=eval_budget, max_evaluations=eval_budget)
            nsga2_time = perf_counter() - t0
            nsga2_objs = [evaluate(problem, s).objectives for s in nsga2_res.archive]
            nsga2_front = [{"f1": v[0], "f2": v[1], "f3": v[2]} for v in nsga2_objs]
            nsga2_norm = [normalize(v, scales) for v in nsga2_objs]
            nsga2_hv = hypervolume(nsga2_norm) if nsga2_norm else 0.0
        except Exception:
            pass

        # 5. Greedy / DSatur Baseline
        report({"phase": "baseline", "evaluations": eval_budget, "budget": eval_budget, "seconds": perf_counter() - started})
        baseline_result = greedy_search(problem, cfg.seed, eval_budget)
        baseline_run = serialize_run(problem, baseline_result, "greedy", cfg.seed)
        if baseline_result is not None and baseline_result.archive:
            values = [tuple(v) for v in baseline_run["objectives"]]
            pick = baseline_result.archive[_compromise(values)]
            baseline = schedule_to_solution(problem, pick, "GREEDY", False)
            baseline_front = [{"f1": v[0], "f2": v[1], "f3": v[2]} for v in values]

    report({"phase": "export", "evaluations": memetic_res.evaluations, "budget": cfg.budget, "seconds": perf_counter() - started})

    # Prepare solution objects for the primary Pareto front
    solutions = []
    archive_keys = set(memetic_res.archive)
    for i, schedule in enumerate(memetic_res.archive):
        solutions.append(schedule_to_solution(problem, schedule, f"S{i + 1:03d}", True))
    extra = 0
    for schedule in dict.fromkeys(memetic_res.population):
        if schedule in archive_keys:
            continue
        ev = evaluate(problem, schedule)
        if ev.feasible:
            extra += 1
            solutions.append(schedule_to_solution(problem, schedule, f"S{len(memetic_res.archive) + extra:03d}", False, ev))

    meta = memetic_res.metadata

    # Summary table of all 5 algorithms
    algorithm_comparison = [
        {"id": "memetic", "name": "Memetic NSGA-II", "hv": round(run["hypervolume"], 4), "runtime": round(run["runtime"], 2), "frontSize": len(memetic_front), "feasible": True, "color": "#2563eb", "marker": "circle"},
        {"id": "moead", "name": "MOEA/D (Tchebycheff)", "hv": round(moead_hv, 4), "runtime": round(moead_time, 2), "frontSize": len(moead_front), "feasible": len(moead_front) > 0, "color": "#059669", "marker": "triangle"},
        {"id": "amosa", "name": "AMOSA (Simulated Annealing)", "hv": round(amosa_hv, 4), "runtime": round(amosa_time, 2), "frontSize": len(amosa_front), "feasible": len(amosa_front) > 0, "color": "#7c3aed", "marker": "diamond"},
        {"id": "nsga2", "name": "Standard NSGA-II", "hv": round(nsga2_hv, 4), "runtime": round(nsga2_time, 2), "frontSize": len(nsga2_front), "feasible": len(nsga2_front) > 0, "color": "#ea580c", "marker": "square"},
        {"id": "greedy", "name": "Repeated Greedy", "hv": round(baseline_run["hypervolume"], 4) if baseline_run else 0.0, "runtime": round(baseline_run["runtime"], 2) if baseline_run else 0.0, "frontSize": len(baseline_front), "feasible": bool(baseline_run and baseline_run["feasible_run"]), "color": "#d97706", "marker": "rhombus"},
    ]

    # Trajectory extraction for all 5 algorithms
    def _extract_curve(history_list, scales, final_hv):
        pts = []
        if history_list:
            step = max(1, len(history_list) // 30)
            sampled = [history_list[i] for i in range(0, len(history_list), step)]
            if history_list[-1] not in sampled:
                sampled.append(history_list[-1])
            for h in sampled:
                ev = h.get("evaluations", 0)
                if "hypervolume" in h:
                    hv = h["hypervolume"]
                else:
                    front = h.get("front", [])
                    norm = [normalize(v, scales) for v in front]
                    hv = hypervolume(norm) if norm else 0.0
                pts.append({"evaluations": ev, "hypervolume": round(float(hv), 5)})
        if pts and pts[0]["evaluations"] > 0 and pts[0]["hypervolume"] > 0:
            pts.insert(0, {"evaluations": 0, "hypervolume": pts[0]["hypervolume"]})
        if not pts and final_hv:
            pts = [{"evaluations": 0, "hypervolume": round(float(final_hv), 5)}, {"evaluations": eval_budget, "hypervolume": round(float(final_hv), 5)}]
        elif not pts:
            pts = [{"evaluations": 0, "hypervolume": 0.0}, {"evaluations": eval_budget, "hypervolume": 0.0}]
        return pts

    memetic_curve = [{"evaluations": h["evaluations"], "hypervolume": round(float(h["hypervolume"]), 5)} for h in run["history"]]
    moead_curve = _extract_curve(getattr(moead_res, "history", []), scales, moead_hv)
    amosa_curve = _extract_curve(getattr(amosa_res, "history", []), scales, amosa_hv)
    nsga2_curve = _extract_curve(getattr(nsga2_res, "history", []), scales, nsga2_hv)
    greedy_curve = _extract_curve(baseline_run.get("history", []) if baseline_run else [], scales, baseline_run.get("hypervolume", 0.0) if baseline_run else 0.0)

    multi_convergence = {
        "memetic": memetic_curve,
        "moead": moead_curve,
        "amosa": amosa_curve,
        "nsga2": nsga2_curve,
        "greedy": greedy_curve,
    }

    stats = {
        "method": METHOD,
        "baselineMethod": BASELINE if cfg.compare_baseline else None,
        "runtime": run["runtime"],
        "evaluations": run["evaluations"],
        "budget": cfg.budget,
        "population": cfg.population,
        "searchSeconds": cfg.search_seconds,
        "stopReason": meta.get("stop_reason"),
        "generations": meta.get("generations_completed", 0),
        "frontSize": run["archive_size"],
        "hypervolume": run["hypervolume"],
        "spacing": run["spacing"] or 0.0,
        "memeticFront": memetic_front,
        "moeadFront": moead_front,
        "amosaFront": amosa_front,
        "nsga2Front": nsga2_front,
        "baselineFront": baseline_front,
        "algorithmComparison": algorithm_comparison,
        "multiConvergence": multi_convergence,
        "baselineHypervolume": baseline_run["hypervolume"] if baseline_run else 0.0,
        "baselineFeasible": bool(baseline_run and baseline_run["feasible_run"]),
        "baselineRuntime": baseline_run["runtime"] if baseline_run else None,
        "baselineEvaluations": baseline_run["evaluations"] if baseline_run else None,
        "baselineFrontSize": baseline_run["archive_size"] if baseline_run else 0,
        "normalization": run["normalization"],
        "reference": run["reference"],
        "convergence": [
            {"generation": h["generation"], "evaluations": h["evaluations"], "hypervolume": h["hypervolume"],
             "archiveSize": len(memetic_res.history[i].get("front", [])), "feasibleFraction": h.get("feasible_fraction", 0.0)}
            for i, h in enumerate(run["history"])
        ],
        "verified": True,
    }

    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    saved_to = None
    if save:
        out = Path(os.environ.get("CLOCKWORK_RUNS_DIR", ROOT / "results" / "web")) / run_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "instance.json").write_text(json.dumps(problem_to_dict(problem), indent=2) + "\n")
        (out / "run.json").write_text(json.dumps(run, indent=2, allow_nan=False) + "\n")
        if baseline_run:
            (out / "baseline.json").write_text(json.dumps(baseline_run, indent=2, allow_nan=False) + "\n")
        if solutions:
            (out / "compromise_schedule.json").write_text(json.dumps(
                schedule_to_dict(memetic_res.archive[_compromise([tuple(v) for v in run["objectives"]])]), indent=2) + "\n")
        saved_to = str(out.relative_to(ROOT) if out.is_relative_to(ROOT) else out).replace("\\", "/")
    stats["savedTo"] = saved_to

    return {
        "runId": run_id,
        "params": {"seed": cfg.seed, "budget": cfg.budget, "population": cfg.population,
                   "searchSeconds": cfg.search_seconds, "compareBaseline": cfg.compare_baseline, "label": cfg.label},
        "instance": problem_to_web(problem),
        "solutions": solutions,
        "baseline": baseline,
        "stats": stats,
    }

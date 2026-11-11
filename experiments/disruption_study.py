"""Disruption study: minimal-change epsilon-constraint re-optimisation vs repair-only vs re-optimising from scratch.

    python experiments/disruption_study.py                 # full study (~15 min)
    python experiments/disruption_study.py --quick         # one medium instance, one seed

Design (fixed before running):
* Instances: the held-out validation instances data/enhancement_validation/{medium_1010,medium_1020,medium_1030,
  large_1010}.json (never used to design this method).
* Published timetable S0 per instance: the normalized compromise of the final memetic NSGA-II (seed 0; 360
  evaluations for medium, 240 for large, the validation study's budgets, evaluation cap only -> deterministic).
* Disruptions derived deterministically from S0: the busiest teacher is absent on their busiest day; the busiest
  teacher leaves; the most-used classroom closes for the week.
* Methods, solver seeds 0,1,2:
    repair    minimal_repair only (no search)
    epsilon   epsilon_reoptimize: eps = repair changes + {0,2,5,10,20,40}, 120 evaluations per level, population 12
    scratch   memetic_nsga2 on the disrupted problem, population 24, the SAME total number of evaluations the
              epsilon method used (it ignores S0 entirely)
* Hypervolume: the project's a-priori normalisation and reference (1.1,1.1,1.1) on the disrupted problem.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from timetable.disruption import (Disruption, _compromise, apply_disruption, changed_sessions, day_slots,  # noqa: E402
                                  epsilon_reoptimize, minimal_repair)
from timetable.evaluation import evaluate  # noqa: E402
from timetable.memetic import memetic_nsga2  # noqa: E402
from timetable.metrics import hypervolume, normalize, objective_scales  # noqa: E402
from timetable.model import problem_from_dict  # noqa: E402

INSTANCES = ["medium_1010", "medium_1020", "medium_1030", "large_1010"]
S0_BUDGET = {"medium": 360, "large": 240}
SEEDS = [0, 1, 2]
EPS_STEPS = (0, 2, 5, 10, 20, 40)
LEVEL_BUDGET, LEVEL_POP, SCRATCH_POP = 120, 12, 24


def published(problem, size):
    run = memetic_nsga2(problem, seed=0, population_size=24, max_evaluations=S0_BUDGET[size])
    values = [evaluate(problem, s).objectives for s in run.archive]
    return run.archive[_compromise(values)]


def disruptions(problem, s0):
    offering = {o.id: k for k, o in enumerate(problem.offerings)}
    load, daily, rooms = Counter(), Counter(), Counter()
    for i, e in enumerate(problem.events):
        t = s0.teachers[offering[e.offering_id]]
        load[t] += e.duration
        daily[(t, s0.placements[i].start // problem.periods_per_day)] += e.duration
        rooms[s0.placements[i].room] += e.duration
    teacher = min(load, key=lambda t: (-load[t], t))
    day = min((d for (t, d) in daily if t == teacher), key=lambda d: (-daily[(teacher, d)], d))
    kinds = {r.id: r.kind for r in problem.rooms}
    room = min((r for r in rooms if kinds[r] == "classroom"), key=lambda r: (-rooms[r], r))
    return [Disruption("teacher_absent", teacher, day_slots(problem, day)),
            Disruption("teacher_leaves", teacher),
            Disruption("room_closed", room)]


def run_one(problem, s0, disruption, seed):
    pd = apply_disruption(problem, disruption)
    scales = objective_scales(pd)
    t0 = perf_counter()
    rep = minimal_repair(pd, s0, seed=seed)
    eps = sorted({min(len(pd.events), rep.changes + s) for s in EPS_STEPS})
    res = epsilon_reoptimize(pd, s0, disruption, eps, LEVEL_BUDGET, LEVEL_POP, seed, repair=rep, original_problem=problem)
    eps_time = perf_counter() - t0
    used = sum(level.evaluations for level in res.levels)
    scratch = memetic_nsga2(pd, seed=seed, population_size=SCRATCH_POP, max_evaluations=used)
    s_obj = [evaluate(pd, s).objectives for s in scratch.archive]
    s_changes = [changed_sessions(pd, s0, s) for s in scratch.archive]
    s_ci = _compromise(s_obj) if s_obj else None
    rep_obj = evaluate(pd, rep.schedule).objectives
    final = res.levels[-1]
    return {
        "disruption": disruption.kind, "resource": disruption.resource, "seed": seed, "sessions": len(pd.events),
        "original_objectives": list(res.original_objectives),
        "repair": {"broken": len(rep.broken), "changes": rep.changes, "proven_minimal": rep.proven_minimal,
                   "method": rep.method, "runtime": rep.runtime, "objectives": list(rep_obj),
                   "hypervolume": hypervolume([normalize(rep_obj, scales)])},
        "epsilon": {"evaluations": used, "runtime": eps_time, "levels": [
            {"epsilon": lv.epsilon, "offset": lv.epsilon - rep.changes, "feasible": lv.feasible, "front": len(lv.archive),
             "hypervolume": lv.hypervolume, "evaluations": lv.evaluations, "rejected": lv.rejected_by_epsilon,
             "min_changes": min(lv.changes) if lv.changes else None,
             "compromise": {"objectives": list(lv.objectives[lv.compromise_index()]), "changes": lv.changes[lv.compromise_index()]} if lv.feasible else None}
            for lv in res.levels], "tradeoff_points": len(res.tradeoff),
            "final_hypervolume": final.hypervolume, "final_min_changes": min(final.changes) if final.changes else None},
        "scratch": {"evaluations": scratch.evaluations, "runtime": scratch.runtime, "front": len(scratch.archive),
                    "hypervolume": hypervolume([normalize(v, scales) for v in s_obj]) if s_obj else 0.0,
                    "min_changes": min(s_changes) if s_changes else None,
                    "compromise": {"objectives": list(s_obj[s_ci]), "changes": s_changes[s_ci]} if s_ci is not None else None},
    }


def summarize(records):
    by_kind = defaultdict(list)
    for r in records:
        by_kind[r["disruption"]].append(r)
    summary = {}
    for kind, rs in by_kind.items():
        offsets = sorted({lv["offset"] for r in rs for lv in r["epsilon"]["levels"]})
        per_offset = {}
        for off in offsets:
            hv = [lv["hypervolume"] for r in rs for lv in r["epsilon"]["levels"] if lv["offset"] == off]
            rel = [lv["hypervolume"] / r["scratch"]["hypervolume"] for r in rs for lv in r["epsilon"]["levels"]
                   if lv["offset"] == off and r["scratch"]["hypervolume"] > 0]
            per_offset[off] = {"runs": len(hv), "mean_hv": mean(hv), "mean_hv_vs_scratch": mean(rel) if rel else None}
        summary[kind] = {
            "runs": len(rs),
            "mean_sessions": mean(r["sessions"] for r in rs),
            "mean_broken": mean(r["repair"]["broken"] for r in rs),
            "repair_mean_changes": mean(r["repair"]["changes"] for r in rs),
            "repair_proven_minimal": sum(r["repair"]["proven_minimal"] for r in rs),
            "repair_mean_hv": mean(r["repair"]["hypervolume"] for r in rs),
            "epsilon_levels": per_offset,
            "scratch_mean_hv": mean(r["scratch"]["hypervolume"] for r in rs),
            "scratch_mean_min_changes": mean(r["scratch"]["min_changes"] for r in rs),
            "scratch_mean_compromise_changes": mean(r["scratch"]["compromise"]["changes"] for r in rs),
            "epsilon_final_beats_scratch_hv": sum(r["epsilon"]["final_hypervolume"] >= r["scratch"]["hypervolume"] for r in rs),
            "mean_evaluations": mean(r["epsilon"]["evaluations"] for r in rs),
            "epsilon_mean_runtime": mean(r["epsilon"]["runtime"] for r in rs),
            "scratch_mean_runtime": mean(r["scratch"]["runtime"] for r in rs),
        }
    return summary


def write_markdown(summary, records, path):
    kinds = {"teacher_absent": "Teacher absent for a day", "teacher_leaves": "Teacher leaves",
             "room_closed": "Classroom closed all week"}
    lines = ["# Disruption study: minimal-change re-optimisation", "",
             f"{len(records)} runs: held-out instances {', '.join(INSTANCES)}; 3 disruptions each; solver seeds {SEEDS}.",
             "Hypervolume uses the project's a-priori normalisation, reference (1.1, 1.1, 1.1), on the disrupted problem.",
             "*Changes* = sessions whose time, room or teacher differs from the published timetable S0. *Broken* = sessions",
             "of S0 that the disruption makes infeasible; it is a lower bound on the changes of any feasible timetable.", "",
             "## Repair vs re-optimising from scratch", "",
             "| Disruption | Sessions | Broken (lower bound) | Repair changes | Repair proven minimal | Scratch: fewest changes on its front | Scratch: compromise changes |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for k, s in summary.items():
        lines.append(f"| {kinds[k]} | {s['mean_sessions']:.0f} | {s['mean_broken']:.1f} | {s['repair_mean_changes']:.1f} | "
                     f"{s['repair_proven_minimal']}/{s['runs']} | {s['scratch_mean_min_changes']:.1f} | {s['scratch_mean_compromise_changes']:.1f} |")
    lines += ["", "## Stability / quality trade-off (epsilon-constraint)", "",
              "Mean hypervolume at each change limit (eps = repair changes + offset), and relative to re-optimising from scratch",
              "with the same total evaluations (which ignores S0 and changes most sessions).", ""]
    for k, s in summary.items():
        lines += [f"**{kinds[k]}** (repair HV {s['repair_mean_hv']:.4f}; scratch HV {s['scratch_mean_hv']:.4f} with "
                  f"{s['scratch_mean_compromise_changes']:.0f} changed sessions at its compromise)", "",
                  "| eps offset | mean HV | HV / scratch HV |", "|---:|---:|---:|"]
        for off, v in s["epsilon_levels"].items():
            lines.append(f"| +{off} | {v['mean_hv']:.4f} | {v['mean_hv_vs_scratch']:.1%} |" if v["mean_hv_vs_scratch"] is not None
                         else f"| +{off} | {v['mean_hv']:.4f} | — |")
        lines += ["", f"Final eps level reaches at least the scratch hypervolume in {s['epsilon_final_beats_scratch_hv']}/{s['runs']} runs; "
                  f"mean {s['mean_evaluations']:.0f} evaluations; runtime {s['epsilon_mean_runtime']:.1f}s (epsilon, incl. repair) "
                  f"vs {s['scratch_mean_runtime']:.1f}s (scratch).", ""]
    lines += ["Single-study, synthetic held-out instances; hypervolumes are comparable only within the same disrupted problem.",
              "The broken-session lower bound certifies minimality of the repair only where the two numbers are equal."]
    path.write_text("\n".join(lines) + "\n")


def plot(records, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    kinds = ["teacher_absent", "teacher_leaves", "room_closed"]
    titles = {"teacher_absent": "Teacher absent for a day", "teacher_leaves": "Teacher leaves", "room_closed": "Classroom closed"}
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=False)
    for ax, kind in zip(axes, kinds):
        rs = [r for r in records if r["disruption"] == kind]
        for r in rs:
            base = r["scratch"]["hypervolume"] or 1
            xs = [lv["epsilon"] / r["sessions"] * 100 for lv in r["epsilon"]["levels"] if lv["feasible"]]
            ys = [lv["hypervolume"] / base * 100 for lv in r["epsilon"]["levels"] if lv["feasible"]]
            ax.plot(xs, ys, color="#15836c", alpha=0.35, marker="o", markersize=3)
            ax.scatter([r["scratch"]["compromise"]["changes"] / r["sessions"] * 100], [100], color="#7c6a52", marker="s", s=18, alpha=0.6)
        ax.axhline(100, color="#7c6a52", linestyle="--", linewidth=1)
        ax.set_title(titles[kind])
        ax.set_xlabel("change limit eps (% of sessions)")
        ax.set_xlim(left=0)
    axes[0].set_ylabel("hypervolume (% of re-optimising from scratch)")
    axes[0].plot([], [], color="#15836c", marker="o", label="epsilon-constraint (one line per run)")
    axes[0].scatter([], [], color="#7c6a52", marker="s", label="from scratch: changes at its compromise")
    axes[0].legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="one medium instance and one seed (smoke run)")
    ap.add_argument("--output", default=str(ROOT / "results" / "disruption"))
    ap.add_argument("--figures", default=str(ROOT / "figures" / "disruption"))
    args = ap.parse_args()
    instances, seeds = (INSTANCES[:1], SEEDS[:1]) if args.quick else (INSTANCES, SEEDS)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    records = []
    for name in instances:
        problem = problem_from_dict(json.loads((ROOT / "data" / "enhancement_validation" / f"{name}.json").read_text()))
        s0 = published(problem, name.split("_")[0])
        for disruption in disruptions(problem, s0):
            for seed in seeds:
                r = run_one(problem, s0, disruption, seed)
                r["instance"] = name
                records.append(r)
                fin = r["epsilon"]["levels"][-1]
                print(f"{name} {disruption.kind:15s} {disruption.resource:4s} seed {seed}: broken {r['repair']['broken']:3d} "
                      f"repair {r['repair']['changes']:3d} | eps HV {r['epsilon']['levels'][0]['hypervolume']:.4f} -> {fin['hypervolume']:.4f} "
                      f"| scratch HV {r['scratch']['hypervolume']:.4f}, min changes {r['scratch']['min_changes']}", flush=True)
    summary = summarize(records)
    (out / "runs.json").write_text(json.dumps(records, indent=1) + "\n")
    with (out / "runs.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["instance", "disruption", "resource", "seed", "sessions", "broken", "repair_changes", "repair_proven_minimal",
                    "repair_hv", "eps_first_hv", "eps_final_hv", "eps_final_min_changes", "eps_evaluations",
                    "scratch_hv", "scratch_min_changes", "scratch_compromise_changes", "eps_runtime", "scratch_runtime"])
        for r in records:
            lv = r["epsilon"]["levels"]
            w.writerow([r["instance"], r["disruption"], r["resource"], r["seed"], r["sessions"], r["repair"]["broken"],
                        r["repair"]["changes"], r["repair"]["proven_minimal"], f"{r['repair']['hypervolume']:.6f}",
                        f"{lv[0]['hypervolume']:.6f}", f"{lv[-1]['hypervolume']:.6f}", r["epsilon"]["final_min_changes"],
                        r["epsilon"]["evaluations"], f"{r['scratch']['hypervolume']:.6f}", r["scratch"]["min_changes"],
                        r["scratch"]["compromise"]["changes"], f"{r['epsilon']['runtime']:.2f}", f"{r['scratch']['runtime']:.2f}"])
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "manifest.json").write_text(json.dumps({
        "instances": instances, "seeds": seeds, "eps_steps": EPS_STEPS, "level_budget": LEVEL_BUDGET,
        "level_population": LEVEL_POP, "scratch_population": SCRATCH_POP, "s0_budget": S0_BUDGET,
        "python": sys.version.split()[0], "platform": platform.platform(), "runtime_seconds": perf_counter() - started}, indent=2) + "\n")
    write_markdown(summary, records, out / "summary.md")
    plot(records, Path(args.figures) / "tradeoff.png")
    print(f"\n{len(records)} runs in {perf_counter() - started:.0f}s -> {out}")


if __name__ == "__main__":
    main()

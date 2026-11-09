"""Exact arithmetic cleanup of saved schedule archives; never reruns a search.

Dominance uses (weighted gaps, room wastage, relative-load variance). Comparing
nonnegative variance is equivalent to comparing SD. Canonical floats are used
only for display and the existing hypervolume/spacing indicators.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from fractions import Fraction
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from statistics import mean
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from timetable.evaluation import evaluate
from timetable.metrics import hypervolume, normalize, objective_scales, spacing
from timetable.model import problem_from_dict, schedule_from_dict


def exact_key(problem, schedule):
    """Exact rational objective ordering for a fully validated schedule."""
    result = evaluate(problem, schedule)
    if not result.feasible:
        raise ValueError("Exact-front input contains an infeasible schedule")
    metrics = result.metrics
    gaps = Fraction(2 * metrics["student_gaps"] + metrics["faculty_gaps"], 2)
    rooms = {room.id: room.capacity for room in problem.rooms}
    demand = sum(event.duration for event in problem.events)
    waste = sum((event.duration * Fraction(rooms[p.room] - event.size, rooms[p.room])
                 for event, p in zip(problem.events, schedule.placements)), Fraction())
    waste = waste / demand if demand else Fraction()
    relative = [Fraction(metrics["faculty_loads"][person.id], person.max_weekly)
                for person in problem.faculty]
    average = sum(relative, Fraction()) / len(relative) if relative else Fraction()
    variance = (sum((value * value for value in relative), Fraction()) / len(relative)
                - average * average) if relative else Fraction()
    return gaps, waste, variance


def exact_dominates(a, b):
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def front_indices(keys):
    """Stable incremental non-dominated set, retaining the first exact duplicate."""
    front = []
    for index, candidate in enumerate(keys):
        if any(keys[old] == candidate or exact_dominates(keys[old], candidate) for old in front):
            continue
        front = [old for old in front if not exact_dominates(candidate, keys[old])]
        front.append(index)
    return sorted(front)


def coordinates(key):
    return [float(key[0]), float(key[1]), sqrt(float(key[2]))]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def clean_run(problem, run, path=None, include_schedules=False):
    encoded = run["archive"]
    schedules = [schedule_from_dict(value) for value in encoded]
    keys = [exact_key(problem, schedule) for schedule in schedules]
    raw = [list(evaluate(problem, schedule).objectives) for schedule in schedules]
    expected_objectives = raw
    if run.get("objective_representation") == "canonical_exact_v1":
        expected_objectives = [coordinates(key) for key in keys]
        if run.get("exact_keys") != [[str(v) for v in key] for key in keys]:
            raise ValueError("Canonical exact keys disagree with the supplied schedules")
    if "objectives" in run and expected_objectives != run["objectives"]:
        raise ValueError("Stored raw objectives disagree with the frozen evaluator")
    scales = list(objective_scales(problem))
    if "normalization" in run and list(run["normalization"]) != scales:
        raise ValueError("Stored normalization disagrees with the problem's fixed scales")
    reference = list(run.get("reference", [1.1, 1.1, 1.1]))
    raw_hv = hypervolume([normalize(v, scales) for v in raw], reference)
    if "hypervolume" in run and abs(raw_hv - run["hypervolume"]) > 1e-12:
        raise ValueError("Stored raw hypervolume disagrees with its archive")
    survivors = front_indices(keys)
    dominated = [i for i, value in enumerate(keys)
                 if any(exact_dominates(other, value) for other in keys)]
    duplicates = [i for i in range(len(keys)) if i not in survivors and i not in dominated]
    vectors = [coordinates(keys[i]) for i in survivors]
    canonical = [normalize(v, scales) for v in vectors]
    saved_hv = run.get("hypervolume", raw_hv)
    result = {
        "run": str(path) if path is not None else None,
        "run_sha256": sha256(path.read_bytes()).hexdigest() if path is not None else None,
        "instance_id": run.get("instance_id", problem.name),
        "size": run.get("size", "unspecified"), "method": run.get("method", "unspecified"),
        "protocol": run.get("protocol", "evaluations"), "solver_seed": run.get("solver_seed", run.get("seed")),
        "raw_archive_count": len(keys), "exact_front_count": len(survivors),
        "exact_dominated_indices": dominated, "exact_duplicate_indices": duplicates,
        "survivor_indices": survivors,
        "canonical_survivor_objectives": vectors,
        "exact_survivor_f1_f2_variance": [[str(v) for v in keys[i]] for i in survivors],
        "normalization": scales, "reference": reference,
        "raw_hypervolume_saved": saved_hv, "corrected_hypervolume": hypervolume(canonical, reference),
        "hypervolume_delta": hypervolume(canonical, reference) - saved_hv,
        "corrected_spacing": spacing(canonical),
        "scope": "Exact non-dominance among supplied saved schedule alternatives; no global optimality claim.",
    }
    if include_schedules:
        result.update({"archive": [encoded[i] for i in survivors], "objectives": vectors,
                       "exact_keys": result["exact_survivor_f1_f2_variance"],
                       "objective_representation": "canonical_exact_v1"})
    return result


def process_study(study, root=ROOT, output=None, plot=False):
    folder = root / "results" / study
    output = output or root / "results/exact_fronts" / study
    if output.resolve() == folder.resolve() or folder.resolve() in output.resolve().parents:
        raise ValueError("Exact-front output must be separate from the raw study directory")
    problems = {p.stem: problem_from_dict(json.loads(p.read_text()))
                for p in (root / "data" / study).glob("*.json")}
    rows = []
    for path in sorted((folder / "runs").glob("*.json")):
        run = json.loads(path.read_text())
        row = clean_run(problems[run["instance_id"]], run, path)
        row["run"] = str(path.relative_to(root))
        write_json(output / "runs" / path.name, row)
        rows.append(row)
    if not rows:
        raise ValueError(f"No saved runs found for study {study!r}")
    groups = defaultdict(list)
    for row in rows:
        groups[row["size"], row["protocol"], row["method"]].append(row)
    aggregates = []
    for (size, protocol, method), selected in sorted(groups.items()):
        aggregates.append({"size": size, "protocol": protocol, "method": method,
                           "runs": len(selected),
                           "raw_mean_hypervolume": mean(r["raw_hypervolume_saved"] for r in selected),
                           "corrected_mean_hypervolume": mean(r["corrected_hypervolume"] for r in selected),
                           "raw_mean_archive_count": mean(r["raw_archive_count"] for r in selected),
                           "exact_mean_archive_count": mean(r["exact_front_count"] for r in selected)})
    gains = []
    for size, protocol in sorted({(r["size"], r["protocol"]) for r in rows}):
        lookup = {r["method"]: r for r in aggregates if (r["size"], r["protocol"]) == (size, protocol)}
        method = "memetic" if "memetic" in lookup else "enhanced"
        if "greedy" in lookup and method in lookup:
            baseline, new = lookup["greedy"], lookup[method]
            denominator = baseline["corrected_mean_hypervolume"]
            gains.append({"size": size, "protocol": protocol, "method": method,
                          "corrected_relative_hv_change_percent":
                          100 * (new["corrected_mean_hypervolume"] / denominator - 1) if denominator else None})
    summary = {
        "runs": len(rows), "raw_archived_schedules": sum(r["raw_archive_count"] for r in rows),
        "exact_front_survivors": sum(r["exact_front_count"] for r in rows),
        "exact_dominated_points": sum(len(r["exact_dominated_indices"]) for r in rows),
        "exact_duplicate_points": sum(len(r["exact_duplicate_indices"]) for r in rows),
        "affected_runs": sum(bool(r["exact_dominated_indices"] or r["exact_duplicate_indices"]) for r in rows),
        "max_absolute_hypervolume_change": max(abs(r["hypervolume_delta"]) for r in rows),
    }
    payload = {"study": study, "summary": summary, "aggregate_normalized_means": aggregates,
               "relative_hv_gains": gains,
               "scope": "Postprocessing only: raw schedules, source, search histories and timings unchanged.",
               "runs": [{"input": r["run"], "sha256": r["run_sha256"],
                         "exact_record": "runs/" + Path(r["run"]).name} for r in rows]}
    write_json(output / "summary.json", payload)
    lines = [f"# Exact arithmetic fronts: {study}", "", payload["scope"], "",
             "Exact non-dominance is among saved schedule alternatives, not all possible timetables.", "",
             f"{summary['runs']} runs; {summary['raw_archived_schedules']} raw feasible archive records; "
             f"{summary['exact_dominated_points']} dominated records removed; "
             f"{summary['exact_front_survivors']} canonical records retained.", "",
             f"Maximum absolute per-run HV change: {summary['max_absolute_hypervolume_change']:.17g}.", "",
             "| Size | Protocol | Method | Runs | Raw mean HV | Canonical mean HV | Mean canonical archive size |",
             "|---|---|---|---:|---:|---:|---:|"]
    for row in aggregates:
        lines.append(f"| {row['size']} | {row['protocol']} | {row['method']} | {row['runs']} | "
                     f"{row['raw_mean_hypervolume']:.8f} | {row['corrected_mean_hypervolume']:.8f} | "
                     f"{row['exact_mean_archive_count']:.2f} |")
    (output / "summary.md").write_text("\n".join(lines) + "\n")
    if plot:
        from timetable.visualization import COLORS, plot_fronts
        COLORS.update({"original_enhanced": "#6486af", "memetic": "#15836c", "ablation_local": "#9b6bb0"})
        for instance, protocol in sorted({(r["instance_id"], r["protocol"]) for r in rows}):
            records = []
            for method in sorted({r["method"] for r in rows}):
                keys = [tuple(Fraction(v) for v in key) for row in rows
                        if (row["instance_id"], row["protocol"], row["method"]) == (instance, protocol, method)
                        for key in row["exact_survivor_f1_f2_variance"]]
                records.extend({"method": method, "objectives": coordinates(keys[i])} for i in front_indices(keys))
            plot_fronts(records, root / "figures/exact_fronts" / study / f"{instance}_{protocol}.png",
                        f"{instance}: exact non-dominance of saved alternatives ({protocol})")
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--study")
    mode.add_argument("--run", type=Path)
    parser.add_argument("--instance", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plot", action="store_true", help="Plot exact per-method fronts for fixed study instances")
    args = parser.parse_args(argv)
    if args.study:
        result = process_study(args.study, output=args.output, plot=args.plot)
        print(json.dumps(result["summary"], indent=2))
    else:
        if args.instance is None:
            parser.error("--instance is required with --run")
        problem = problem_from_dict(json.loads(args.instance.read_text()))
        result = clean_run(problem, json.loads(args.run.read_text()), args.run, include_schedules=True)
        result["instance_sha256"] = sha256(args.instance.read_bytes()).hexdigest()
        output = args.output or args.run.parent / "exact_front.json"
        if output.resolve() in {args.run.resolve(), args.instance.resolve()}:
            raise ValueError("Exact-front output cannot overwrite an input file")
        write_json(output, result)
        print(f"Retained {result['exact_front_count']} of {result['raw_archive_count']} feasible alternatives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read saved archives; audit exact Pareto dominance without rerunning a search.

No measured source, data, run or result file is changed. All three objective
orders can be checked exactly: gaps are half-integers, room waste is rational,
and comparing squared workload SD is equivalent to comparing SD. Exact
relative-load variance supports unequal faculty allowances as well.

Usage (from the project root):
    python results/final_audit/independent_precision_audit.py \
      --output work/final-audit/exact_front_audit.json

This audits non-dominance among the candidates in each SAVED archive. It does
not claim a new timed experiment or globally Pareto-optimal timetables.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from statistics import mean
import sys


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(DEFAULT_ROOT / "src"))
from timetable.metrics import hypervolume, normalize
from timetable.model import problem_from_dict


AXES = ("f1_gaps", "f2_room_waste", "f3_workload_sd")


def exact_objectives(problem, encoded):
    """Return (f1,f2,variance), all exact Fraction objects from schedule data."""
    teacher_by_offering = dict(zip((o.id for o in problem.offerings), encoded["teachers"]))
    capacities = {room.id: room.capacity for room in problem.rooms}
    group_busy, faculty_busy = defaultdict(set), defaultdict(set)
    room_terms = []
    demand = 0
    for event, placement in zip(problem.events, encoded["placements"]):
        assert placement is not None
        day, period = divmod(placement["start"], problem.periods_per_day)
        for p in range(period, period + event.duration):
            for group in event.groups:
                group_busy[group, day].add(p)
            faculty_busy[teacher_by_offering[event.offering_id], day].add(p)
        capacity = capacities[placement["room"]]
        room_terms.append(event.duration * Fraction(capacity - event.size, capacity))
        demand += event.duration
    lunch = set(problem.lunch_periods)

    def gaps(occupancy):
        return sum(sum(p not in busy and p not in lunch
                       for p in range(min(busy), max(busy) + 1))
                   for busy in occupancy.values() if busy)

    f1 = Fraction(2 * gaps(group_busy) + gaps(faculty_busy), 2)
    f2 = sum(room_terms, Fraction()) / demand if demand else Fraction()
    loads = dict.fromkeys((faculty.id for faculty in problem.faculty), 0)
    for offering, teacher in zip(problem.offerings, encoded["teachers"]):
        loads[teacher] += offering.sessions * offering.duration
    relative = [Fraction(loads[f.id], f.max_weekly) for f in problem.faculty]
    average = sum(relative, Fraction()) / len(relative) if relative else Fraction()
    variance = sum(((r - average) ** 2 for r in relative), Fraction()) / len(relative) if relative else Fraction()
    return f1, f2, variance


def exact_dominates(a, b):
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def coordinates(key):
    return float(key[0]), float(key[1]), sqrt(float(key[2]))


def mean_vectors(vectors):
    return [mean(v[j] for v in vectors) for j in range(3)] if vectors else None


def audit_study(root, study):
    folder = root / "results" / study
    problems = {p.stem: problem_from_dict(json.loads(p.read_text()))
                for p in (root / "data" / study).glob("*.json")}
    rows, representations, tie_reversals = [], defaultdict(set), Counter()
    for path in sorted((folder / "runs").glob("*.json")):
        run_bytes = path.read_bytes()
        run = json.loads(run_bytes)
        problem = problems[run["instance_id"]]
        keys = [exact_objectives(problem, schedule) for schedule in run["archive"]]
        raw = run["objectives"]
        assert len(keys) == len(raw)
        for key, vector in zip(keys, raw):
            assert float(key[0]) == vector[0], (path, "exact gap disagreement")
            for j in (1, 2):
                representations[run["instance_id"], j, key[j]].add(vector[j])
        dominated, duplicate, survivors, dominance_pairs = [], [], [], []
        seen = set()
        for i, b in enumerate(keys):
            dominators = [j for j, a in enumerate(keys) if i != j and exact_dominates(a, b)]
            if dominators:
                dominated.append(i)
                for j in dominators:
                    reversed_axes = [AXES[axis] for axis in range(3)
                                     if keys[j][axis] == b[axis] and raw[j][axis] > raw[i][axis]]
                    for axis in reversed_axes:
                        tie_reversals[axis] += 1
                    dominance_pairs.append({
                        "dominator_index": j, "dominated_index": i,
                        "reversed_equal_axes": reversed_axes,
                        "dominator_raw": raw[j], "dominated_raw": raw[i],
                        "dominator_exact_f1_f2_variance": [str(x) for x in keys[j]],
                        "dominated_exact_f1_f2_variance": [str(x) for x in b],
                    })
            elif b in seen:
                duplicate.append(i)
            else:
                survivors.append(i)
                seen.add(b)
        canonical = [coordinates(keys[i]) for i in survivors]
        normalization = run["normalization"]
        raw_normalized = [normalize(v, normalization) for v in raw]
        corrected_normalized = [normalize(v, normalization) for v in canonical]
        raw_recomputed = hypervolume(raw_normalized)
        assert abs(raw_recomputed - run["hypervolume"]) < 1e-12
        corrected_hv = hypervolume(corrected_normalized)
        rows.append({
            "run": str(path.relative_to(root)), "run_sha256": sha256(run_bytes).hexdigest(),
            "instance_id": run["instance_id"], "size": run["size"],
            "protocol": run.get("protocol", "evaluations"), "method": run["method"],
            "solver_seed": run["solver_seed"],
            "raw_archive_count": len(raw), "exact_front_count": len(survivors),
            "exact_dominated_indices": dominated, "exact_duplicate_indices": duplicate,
            "survivor_indices": survivors, "dominance_pairs": dominance_pairs,
            "normalization": normalization, "reference": run["reference"],
            "raw_hypervolume_saved": run["hypervolume"],
            "raw_hypervolume_recomputed": raw_recomputed,
            "corrected_hypervolume": corrected_hv,
            "hypervolume_delta": corrected_hv - run["hypervolume"],
            "canonical_survivor_objectives": canonical,
            "exact_survivor_f1_f2_variance": [[str(v) for v in keys[i]] for i in survivors],
            "raw_mean_front_normalized_objectives": mean_vectors(raw_normalized),
            "corrected_mean_front_normalized_objectives": mean_vectors(corrected_normalized),
            "raw_best_normalized_objectives": [min(v[j] for v in raw_normalized) for j in range(3)] if raw else None,
            "corrected_best_normalized_objectives": [min(v[j] for v in corrected_normalized) for j in range(3)] if canonical else None,
        })
    varying = [{"instance_id": identity, "axis": AXES[axis],
                "exact_value": str(value), "raw_float_values": sorted(floats)}
               for (identity, axis, value), floats in representations.items() if len(floats) > 1]
    aggregates = []
    for size, protocol, method in sorted({(r["size"], r["protocol"], r["method"]) for r in rows}):
        selected = [r for r in rows if (r["size"], r["protocol"], r["method"]) == (size, protocol, method)]
        raw_means = [r["raw_mean_front_normalized_objectives"] for r in selected
                     if r["raw_mean_front_normalized_objectives"] is not None]
        corrected_means = [r["corrected_mean_front_normalized_objectives"] for r in selected
                           if r["corrected_mean_front_normalized_objectives"] is not None]
        aggregates.append({
            "size": size, "protocol": protocol, "method": method, "runs": len(selected),
            "raw_mean_hypervolume": mean(r["raw_hypervolume_saved"] for r in selected),
            "corrected_mean_hypervolume": mean(r["corrected_hypervolume"] for r in selected),
            "raw_mean_archive_count": mean(r["raw_archive_count"] for r in selected),
            "exact_mean_archive_count": mean(r["exact_front_count"] for r in selected),
            "raw_mean_of_run_front_normalized_objectives_conditional": mean_vectors(raw_means),
            "corrected_mean_of_run_front_normalized_objectives_conditional": mean_vectors(corrected_means),
        })
    gains = []
    for size, protocol in sorted({(r["size"], r["protocol"]) for r in rows}):
        baseline = [a for a in aggregates if a["size"] == size and a["protocol"] == protocol and a["method"] == "greedy"]
        compared = [a for a in aggregates if a["size"] == size and a["protocol"] == protocol
                    and a["method"] == ("memetic" if study == "enhancement_validation" else "enhanced")]
        if baseline and compared:
            g, m = baseline[0], compared[0]
            gains.append({
                "size": size, "protocol": protocol,
                "method": m["method"], "baseline": "greedy",
                "raw_relative_hv_change_percent": 100 * (m["raw_mean_hypervolume"] / g["raw_mean_hypervolume"] - 1),
                "corrected_relative_hv_change_percent": 100 * (m["corrected_mean_hypervolume"] / g["corrected_mean_hypervolume"] - 1),
            })
    return {
        "study": study,
        "summary": {
            "runs": len(rows), "raw_archived_schedules": sum(r["raw_archive_count"] for r in rows),
            "exact_front_survivors": sum(r["exact_front_count"] for r in rows),
            "exact_dominated_points": sum(len(r["exact_dominated_indices"]) for r in rows),
            "exact_duplicate_points": sum(len(r["exact_duplicate_indices"]) for r in rows),
            "affected_runs": sum(bool(r["exact_dominated_indices"] or r["exact_duplicate_indices"]) for r in rows),
            "max_absolute_hypervolume_change": max(abs(r["hypervolume_delta"]) for r in rows),
            "equal_exact_objectives_with_multiple_float_representations": dict(Counter(r["axis"] for r in varying)),
            "dominance_pairs_with_reversed_equal_axis": dict(tie_reversals),
        },
        "aggregate_normalized_means": aggregates,
        "relative_hv_gains": gains,
        "equal_exact_objectives_with_multiple_float_representations": varying,
        "runs": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--studies", nargs="+", default=["benchmark", "enhancement_validation"])
    parser.add_argument("--output", type=Path, default=DEFAULT_ROOT / "work/final-audit/exact_front_audit.json")
    args = parser.parse_args()
    root = args.root.resolve()
    audited = [audit_study(root, study) for study in args.studies]
    payload = {
        "scope": "Exact rational non-dominance audit among existing saved archive candidates; no new search or timing measurement.",
        "objective_key": ["exact student gaps + half faculty gaps", "exact duration-weighted rational room wastage", "exact rational relative-load variance; monotone equivalent to SD"],
        "float_hv_policy": "First prune using exact keys; then convert fractions once to float, sqrt variance once, and apply unchanged fixed normalization/reference.",
        "integrity_policy": "Measured source, instance data, run archives and measurements are not modified; run-file SHA-256 hashes identify audited input bytes.",
        "studies": audited,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    for study in audited:
        print(study["study"], json.dumps(study["summary"], sort_keys=True))
    print(args.output)


if __name__ == "__main__":
    main()

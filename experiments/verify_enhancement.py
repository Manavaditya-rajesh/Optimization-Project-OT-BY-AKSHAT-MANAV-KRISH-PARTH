"""Independently recheck frozen follow-up runs, archives, and cutoff evidence."""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from timetable.evaluation import evaluate
from timetable.metrics import dominates, hypervolume, normalize, objective_scales
from timetable.model import problem_from_dict, schedule_from_dict, schedule_to_dict


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="enhancement_validation")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = root / "results" / args.study
    manifest = json.loads((folder / "manifest.json").read_text())
    config = manifest["config"]
    assert digest(config) == manifest["config_sha256"]
    expected_identities = set()
    for scenario in config["scenarios"]:
        for instance_seed in scenario.get("instance_seeds", config["instance_seeds"]):
            for solver_seed in scenario.get("solver_seeds", config["solver_seeds"]):
                for method in config["methods"]:
                    for protocol in config["protocols"]:
                        expected_identities.add((scenario["size"],instance_seed,solver_seed,method,protocol))
    actual_identities = set()
    initialization_prefixes = {}
    for name, sha in manifest["source_files"].items():
        assert hashlib.sha256((folder / "source_snapshot" / name).read_bytes()).hexdigest() == sha
        assert hashlib.sha256((root / "src/timetable" / name).read_bytes()).hexdigest() == sha
    problems = {}
    for path in sorted((root / "data" / args.study).glob("*.json")):
        problem = problem_from_dict(json.loads(path.read_text()))
        certificate = schedule_from_dict(json.loads((path.parent / "certificates" / path.name).read_text()))
        assert evaluate(problem, certificate).feasible, path
        problems[path.stem] = problem
    completed = archived = late = failures = 0
    workload_bounds = {}
    for identity,problem in problems.items():
        allowances={teacher.max_weekly for teacher in problem.faculty}
        if len(allowances) != 1 or not problem.faculty:
            continue
        h=next(iter(allowances))
        m=len(problem.faculty)
        total=sum(event.duration for event in problem.events)
        low,remainder=divmod(total,m)
        squares=(m-remainder)*low*low+remainder*(low+1)**2
        variance=Fraction(squares,m*h*h)-Fraction(total,m*h)**2
        workload_bounds[identity]={"total_teaching_periods":total,"faculty_count":m,
                                   "common_allowance":h,"integer_sum_squares_lower_bound":squares,
                                   "relative_load_variance_lower_bound_exact":str(variance),
                                   "best_observed_integer_sum_squares":None,
                                   "attaining_certificates":[],
                                   "scope":"Workload objective only; ignores offering indivisibility, eligibility and time constraints. Bound nonattainment does not prove nonoptimality."}
    for path in sorted((folder / "runs").glob("*.json")):
        run = json.loads(path.read_text())
        problem = problems[run["instance_id"]]
        identity=(run["size"],run["instance_seed"],run["solver_seed"],run["method"],run["protocol"])
        assert identity not in actual_identities and identity in expected_identities
        actual_identities.add(identity)
        scenario=next(s for s in config["scenarios"] if s["size"]==run["size"] and run["instance_seed"] in s.get("instance_seeds",config["instance_seeds"]))
        assert run["population_size"] == scenario.get("population_size",config["population_size"])
        assert run["normalization"] == list(objective_scales(problem))
        assert run["reference"] == [1.1,1.1,1.1]
        if run["protocol"] == "wall_time":
            assert run["wall_time_limit"] == scenario["wall_time_seconds"]
            assert run["evaluation_cap"] == config["evaluation_ceiling"]
        else:
            assert run["evaluation_cap"] == run["paired_evaluation_budget"] == scenario["budget"]
        assert run["instance_sha256"] == digest(json.loads((root / "data" / args.study / (run["instance_id"] + ".json")).read_text()))
        history = run["history"]
        if run["method"] in {"greedy","memetic","ablation_local"}:
            key=(run["instance_id"],run["solver_seed"],run["protocol"])
            initialization_prefixes.setdefault(key,{})[run["method"]]=[
                h["schedule_sha256"] for h in history[:run["population_size"]]]
        assert len(history) == run["evaluations"] <= run["evaluation_cap"]
        assert [h["evaluations"] for h in history] == list(range(1, len(history)+1))
        assert all(a["elapsed_seconds"] <= b["elapsed_seconds"] for a,b in zip(history, history[1:]))
        assert dict(Counter(h["schedule_sha256"] for h in history)) == run["genotype_evaluation_counts"]
        discovered = []
        available_hashes = set()
        last_vectors = ()
        prefix_hv = 0.0
        for h in history:
            assert h["candidate_feasible"] == (h["candidate_violation"] == 0)
            if h["completed_after_deadline"]:
                assert run["wall_time_limit"] is not None and h["elapsed_seconds"] > run["wall_time_limit"]
                late += 1
                assert abs(h["hypervolume"]-prefix_hv) < 1e-12
                continue
            assert h["elapsed_seconds"] <= run["quality_cutoff_seconds"] + 1e-9
            if h["candidate_feasible"]:
                available_hashes.add(h["schedule_sha256"])
                v = tuple(h["candidate_objectives"])
                if not any(old == v or dominates(old, v) for old in discovered):
                    discovered = [old for old in discovered if not dominates(v, old)] + [v]
            current_vectors=tuple(discovered)
            if current_vectors != last_vectors:
                prefix_hv=hypervolume([normalize(v,objective_scales(problem)) for v in discovered])
                last_vectors=current_vectors
            assert abs(h["hypervolume"]-prefix_hv) < 1e-12, (path,"Incorrect prefix hypervolume")
        vectors = []
        for index,encoded in enumerate(run["archive"]):
            schedule = schedule_from_dict(encoded)
            result = evaluate(problem, schedule)
            assert result.feasible, (path, result.violations)
            assert digest(schedule_to_dict(schedule)) in available_hashes
            vectors.append(result.objectives)
            bound=workload_bounds.get(run["instance_id"])
            if bound is not None:
                loads=result.metrics["faculty_loads"].values()
                assert sum(loads)==bound["total_teaching_periods"]
                squares=sum(load*load for load in loads)
                assert squares >= bound["integer_sum_squares_lower_bound"]
                best=bound["best_observed_integer_sum_squares"]
                bound["best_observed_integer_sum_squares"]=squares if best is None else min(best,squares)
                if squares==bound["integer_sum_squares_lower_bound"]:
                    bound["attaining_certificates"].append({"run":str(path.relative_to(root)),"archive_index":index,
                                                          "method":run["method"],"protocol":run["protocol"],
                                                          "sorted_faculty_loads":sorted(loads)})
            archived += 1
        assert vectors == [tuple(v) for v in run["objectives"]]
        assert len(set(vectors)) == len(vectors)
        assert run["archive_size"] == len(vectors) and run["feasible_run"] == bool(vectors)
        assert set(vectors) == set(discovered), (path, "Cutoff front does not match on-time discoveries")
        assert not any(dominates(a,b) for a in vectors for b in vectors)
        assert abs(hypervolume([normalize(v, objective_scales(problem)) for v in vectors])-run["hypervolume"]) < 1e-12
        assert all(a["hypervolume"] <= b["hypervolume"] + 1e-12 for a,b in zip(history, history[1:]))
        if run["protocol"] == "evaluations":
            assert run["evaluations"] == run["paired_evaluation_budget"]
        failures += not run["feasible_run"]
        completed += 1
    expected = sum(len(s.get("instance_seeds", config["instance_seeds"])) *
                   len(s.get("solver_seeds", config["solver_seeds"])) * len(config["methods"]) * len(config["protocols"])
                   for s in config["scenarios"])
    assert completed == expected, (completed, expected)
    assert actual_identities == expected_identities
    initialization_groups=0
    for key,methods in initialization_prefixes.items():
        if {"greedy","memetic","ablation_local"}.issubset(methods):
            # The same constructor/RNG prefix is supplied by all three policies.
            shortest=min(len(v) for v in methods.values())
            assert methods["greedy"][:shortest] == methods["memetic"][:shortest] == methods["ablation_local"][:shortest], key
            initialization_groups += 1
    result = {"status": "PASS", "study": args.study, "runs": completed, "expected_runs": expected,
              "certificates": len(problems), "archived_feasible_schedules": archived,
              "excluded_late_evaluations": late, "empty_archives": failures,
              "source_snapshot_matches_current": True, "all_cutoff_fronts_reconstructed": True,
              "common_initialization_groups_checked":initialization_groups,
              "workload_integer_relaxation":workload_bounds}
    (folder / "verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

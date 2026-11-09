"""Paired enhancement comparisons with independently observed search evidence.

The original greedy construction and enhanced NSGA-II are left unchanged.
Their evaluator is observed in a serial adapter, while the new memetic method
accepts the same observer explicitly.  Every complete evaluation is charged,
including initialization and duplicates.  Direct resource/delta checks consume
wall time but are not relabeled as complete evaluations.

Wall-clock limits are checked at evaluator boundaries: an atomic construction
or evaluation can overrun.  Candidates whose full evaluation finishes after the
deadline are excluded from quality indicators, and overshoot is reported.  No
background thread is allowed to continue optimizing after a run is reported.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import platform
from statistics import mean, stdev
import sys
import threading
from time import perf_counter

from .evaluation import evaluate
from .greedy import _domains as construction_domains
from .metrics import (
    coverage, dominates, hypervolume, normalize, objective_scales,
    paired_comparison, spacing,
)
from .model import (
    problem_to_dict, schedule_from_dict, schedule_to_dict, validate_problem,
)


METHODS = ("greedy", "original_enhanced", "memetic", "ablation_local")
PROTOCOLS = ("evaluations", "wall_time")
_RUN_LOCK = threading.Lock()


class SearchStopped(Exception):
    """Private adapter control flow; completed evidence remains in the observer."""


def _digest(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


class _Observer:
    """One charged evaluator shared by all compared search policies."""

    def __init__(self, problem, cap: int, time_limit: float | None, clock=None):
        self.problem = problem
        self.cap = cap
        self.time_limit = time_limit
        self.clock = clock or perf_counter
        self.started = self.clock()
        self.evaluation_fn = evaluate
        self.calls = 0
        self.feasible_calls = 0
        self.on_time_feasible = 0
        self.late_calls = 0
        self.minimum_violation = None
        self.best = None
        self.archive = []
        self.history = []
        self.hashes = Counter()
        self.feasible_hashes = set()
        self.feasible_vectors = set()
        self.first_feasible = None
        self.reason = None

    def elapsed(self) -> float:
        return self.clock() - self.started

    def __call__(self, problem, schedule):
        if problem is not self.problem and problem != self.problem:
            raise ValueError("An observed evaluator cannot mix timetable instances")
        if self.calls >= self.cap:
            self.reason = "evaluation_cap"
            raise SearchStopped
        if self.time_limit is not None and self.elapsed() >= self.time_limit:
            self.reason = "wall_time"
            raise SearchStopped
        assessment = self.evaluation_fn(problem, schedule)
        completed_at = self.elapsed()
        self.calls += 1
        key = _digest(schedule_to_dict(schedule))
        self.hashes[key] += 1
        self.feasible_calls += int(assessment.feasible)
        late = self.time_limit is not None and completed_at > self.time_limit
        if late:
            self.late_calls += 1
        else:
            if self.minimum_violation is None or assessment.violation < self.minimum_violation:
                self.minimum_violation = assessment.violation
                self.best = (schedule, assessment)
            if assessment.feasible:
                self.on_time_feasible += 1
                self.feasible_hashes.add(key)
                self.feasible_vectors.add(assessment.objectives)
                if self.first_feasible is None:
                    self.first_feasible = completed_at
                if not any(
                    old.objectives == assessment.objectives
                    or dominates(old.objectives, assessment.objectives)
                    for _, old in self.archive
                ):
                    self.archive = [
                        (candidate, old) for candidate, old in self.archive
                        if not dominates(assessment.objectives, old.objectives)
                    ]
                    self.archive.append((schedule, assessment))
        self.history.append({
            "generation": self.calls - 1,
            "evaluations": self.calls,
            "elapsed_seconds": completed_at,
            "schedule_sha256": key,
            "candidate_feasible": assessment.feasible,
            "candidate_violation": assessment.violation,
            "candidate_objectives": list(assessment.objectives),
            "completed_after_deadline": late,
            "evaluated_feasible_fraction": self.feasible_calls / self.calls,
            "min_violation": self.minimum_violation,
            "front": [list(old.objectives) for _, old in self.archive],
        })
        if late:
            # The completed call is counted, but its quality is not credited.
            self.reason = "wall_time"
            raise SearchStopped
        return assessment


@contextmanager
def _observed_legacy(module, observer):
    original = module.evaluate
    module.evaluate = observer
    try:
        yield
    finally:
        module.evaluate = original


def run_comparison_method(
    problem,
    method: str,
    seed: int = 0,
    budget: int = 240,
    population_size: int = 24,
    time_limit: float | None = None,
    evaluation_ceiling: int = 100_000,
) -> dict:
    """Run one policy under a full-evaluation cap or a wall-time allocation.

    ``time_limit=None`` selects the evaluation protocol and uses ``budget``.
    Otherwise ``evaluation_ceiling`` is only a safety cap, not the paired budget.
    Module imports, shared input validation, and resetting the construction LRU
    are preflight work. Algorithm preprocessing, seeding, direct resource checks,
    objective evaluations, observer archives, and survival are timed.

    The original algorithm's search decisions are untouched. The serial legacy
    adapter temporarily replaces its module-local evaluator and restores it even
    on interruption. This API serializes in-process invocations for that reason.
    """
    if method not in METHODS:
        raise ValueError(f"Unknown comparison method {method!r}")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if type(population_size) is not int or population_size < 2:
        raise ValueError("population_size must be an integer >= 2")
    if type(budget) is not int or budget < 1:
        raise ValueError("budget must be a positive integer")
    if type(evaluation_ceiling) is not int or evaluation_ceiling < population_size:
        raise ValueError("evaluation_ceiling must allow the initial population")
    if time_limit is not None and (not math.isfinite(time_limit) or time_limit <= 0):
        raise ValueError("time_limit must be finite and positive")
    cap = budget if time_limit is None else evaluation_ceiling
    if method != "greedy" and cap < population_size:
        raise ValueError("The full-evaluation cap must allow initialization")
    validate_problem(problem)
    protocol = "evaluations" if time_limit is None else "wall_time"
    legacy = (
        importlib.import_module("timetable.experiments") if method == "greedy" else
        importlib.import_module("timetable.nsga2") if method == "original_enhanced" else None
    )
    modern = importlib.import_module("timetable.memetic") if method in {"memetic", "ablation_local"} else None
    if modern is not None:
        importlib.import_module("timetable.faculty_search")
    with _RUN_LOCK:
        # Prevent the later method in a pair from inheriting a free cached
        # preprocessing stage from the first method. Construction logic is intact.
        construction_domains.cache_clear()
        observer = _Observer(problem, cap, time_limit)
        result = None
        progress = {}
        interrupted = False
        try:
            if method == "greedy":
                with _observed_legacy(legacy, observer):
                    # Keep native archive/history bookkeeping as well as the
                    # original construction/RNG stream in the timing protocol.
                    result = legacy.greedy_search(problem, seed=seed, budget=cap)
            elif method == "original_enhanced":
                with _observed_legacy(legacy, observer):
                    result = legacy.nsga2(
                        problem, seed=seed, population_size=population_size,
                        generations=cap, max_evaluations=cap, enhanced=True,
                        repair=True, local_search=True,
                    )
            else:
                result = modern.memetic_nsga2(
                    problem, seed=seed, population_size=population_size,
                    max_evaluations=cap, time_limit=time_limit,
                    selection="nsga2" if method == "memetic" else "scalar_local",
                    evaluator=observer, progress=progress,
                )
        except SearchStopped:
            interrupted = True
        runtime = observer.elapsed()
        if result is not None and result.evaluations != observer.calls:
            raise RuntimeError("Algorithm and independent observer evaluation counts disagree")
        if observer.reason is None:
            observer.reason = (
                "evaluation_cap" if observer.calls >= cap else
                "wall_time" if time_limit is not None and runtime >= time_limit else
                "algorithm_returned"
            )

    # Indicators and independent verification are postprocessing and do not
    # feed back into search or consume its allocated time/evaluation budget.
    ordered = sorted(observer.archive, key=lambda item: item[1].objectives)
    schedules = [candidate for candidate, _ in ordered]
    assessments = [evaluate(problem, candidate) for candidate in schedules]
    if any(not outcome.feasible for outcome in assessments):
        raise AssertionError("Independent comparison archive contains an invalid timetable")
    objectives = [outcome.objectives for outcome in assessments]
    scales = objective_scales(problem)
    history = []
    history_volumes = {}
    for row in observer.history:
        row = dict(row)
        vector_key = tuple(tuple(vector) for vector in row.pop("front"))
        if vector_key not in history_volumes:
            history_volumes[vector_key] = hypervolume([normalize(vector, scales) for vector in vector_key])
        row["hypervolume"] = history_volumes[vector_key]
        history.append(row)
    normalized = [normalize(vector, scales) for vector in objectives]
    metadata = dict(result.metadata) if result is not None else dict(progress)
    native_metadata = dict(metadata)
    metadata.update({
        "comparison_method": method,
        "native_search_metadata": native_metadata,
        "postprocessing_distinct_history_fronts": len(history_volumes),
        "evaluation_adapter_interrupted": interrupted,
        "termination": observer.reason,
        "full_evaluator_calls": observer.calls,
        "evaluated_feasible": observer.feasible_calls,
        "on_time_feasible_evaluations": observer.on_time_feasible,
        "late_completed_evaluations": observer.late_calls,
        "minimum_violation": observer.minimum_violation,
        "unique_genotypes_evaluated": len(observer.hashes),
        "duplicate_evaluations": observer.calls - len(observer.hashes),
        "unique_feasible_genotypes_by_cutoff": len(observer.feasible_hashes),
        "unique_feasible_objective_vectors_by_cutoff": len(observer.feasible_vectors),
        "initialization_and_partial_resource_checks_timed": True,
        "partial_resource_checks_counted_as_full_evaluations": False,
        "construction_cache_reset_before_each_run": True,
        "archive_policy": "all feasible candidates fully evaluated by quality cutoff; one representative per objective vector",
        "ablation_scope": (
            "fixed-scalar local trajectories replace NSGA-II tournament/rank/crowding/survival; same initialization and proposal family"
            if method == "ablation_local" else None
        ),
    })
    return {
        "method": method, "solver_seed": seed, "protocol": protocol,
        "population_size": population_size, "evaluations": observer.calls,
        "evaluation_cap": cap, "paired_evaluation_budget": budget if time_limit is None else None,
        "wall_time_limit": time_limit, "runtime": runtime,
        "quality_cutoff_seconds": runtime if time_limit is None else time_limit,
        "wall_time_overshoot_seconds": max(0.0, runtime - time_limit) if time_limit is not None else 0.0,
        "time_to_first_feasible_seconds": observer.first_feasible,
        "feasible_run": bool(schedules), "archive_size": len(schedules),
        "objectives": objectives,
        "archive": [schedule_to_dict(candidate) for candidate in schedules],
        "normalization": scales, "reference": [1.1, 1.1, 1.1],
        "hypervolume": hypervolume(normalized), "spacing": spacing(normalized),
        "feasible_evaluation_fraction": observer.feasible_calls / observer.calls if observer.calls else 0.0,
        "on_time_feasible_evaluation_fraction": observer.on_time_feasible / observer.calls if observer.calls else 0.0,
        "minimum_violation": observer.minimum_violation,
        "duplicate_evaluation_fraction": (observer.calls - len(observer.hashes)) / observer.calls if observer.calls else 0.0,
        "genotype_evaluation_counts": dict(sorted(observer.hashes.items())),
        "history": history, "metadata": metadata,
        "best_candidate_diagnostic": asdict(observer.best[1]) if observer.best is not None else None,
    }


def _configuration(config) -> None:
    name = config.get("name")
    if not isinstance(name, str) or not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
        raise ValueError("Comparison name must use letters, digits, underscore or hyphen")
    methods = config.get("methods", list(METHODS))
    protocols = config.get("protocols", list(PROTOCOLS))
    if not methods or len(set(methods)) != len(methods) or any(m not in METHODS for m in methods):
        raise ValueError("Unknown, empty or repeated comparison methods")
    if not protocols or len(set(protocols)) != len(protocols) or any(p not in PROTOCOLS for p in protocols):
        raise ValueError("Unknown, empty or repeated comparison protocols")
    seen = set()
    if not config.get("scenarios"):
        raise ValueError("At least one comparison scenario is required")
    for scenario in config["scenarios"]:
        if scenario.get("size") not in {"small", "medium", "large"}:
            raise ValueError("Unknown comparison size")
        instance_seeds = scenario.get("instance_seeds", config.get("instance_seeds", []))
        solver_seeds = scenario.get("solver_seeds", config.get("solver_seeds", []))
        for seeds in (instance_seeds, solver_seeds):
            if not seeds or len(set(seeds)) != len(seeds) or any(type(seed) is not int for seed in seeds):
                raise ValueError("Seeds must be nonempty, unique integer lists")
        population = scenario.get("population_size", config.get("population_size", 24))
        budget = scenario.get("budget")
        if type(population) is not int or population < 2 or type(budget) is not int or budget < 1:
            raise ValueError("Positive integer budget and population >=2 required")
        if "evaluations" in protocols and any(m != "greedy" for m in methods) and budget < population:
            raise ValueError("Evaluation budget must allow initialization")
        seconds = scenario.get("wall_time_seconds")
        if "wall_time" in protocols and (not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0):
            raise ValueError("Wall-time scenarios require positive finite wall_time_seconds")
        if scenario.get("generator"):
            raise ValueError("Enhancement comparisons preserve the original generator presets; use a separate sensitivity study for generator changes")
        for instance_seed in instance_seeds:
            key = (scenario["size"], instance_seed)
            if key in seen:
                raise ValueError("Repeated size/instance seed would overwrite comparison records")
            seen.add(key)


def _source_manifest() -> dict:
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(Path(__file__).parent.glob("*.py"))}
    versions = {}
    for package in ("numpy", "matplotlib", "ortools"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return {"source_sha256": _digest(files), "source_files": files,
            "python": sys.version, "platform": platform.platform(), "versions": versions}


def _validate_cached(problem, payload, expected) -> None:
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("Cached comparison identity or allocation mismatch")
    if not 0 <= payload["evaluations"] <= payload["evaluation_cap"]:
        raise ValueError("Cached comparison exceeds its evaluation cap")
    schedules = [schedule_from_dict(data) for data in payload["archive"]]
    outcomes = [evaluate(problem, candidate) for candidate in schedules]
    vectors = [list(outcome.objectives) for outcome in outcomes]
    if any(not outcome.feasible for outcome in outcomes) or vectors != payload["objectives"]:
        raise ValueError("Cached comparison archive failed independent validation")
    hv = hypervolume([normalize(vector, objective_scales(problem)) for vector in vectors])
    if hv != payload["hypervolume"] or len(schedules) != payload["archive_size"] or bool(schedules) != payload["feasible_run"]:
        raise ValueError("Cached comparison indicators disagree with its archive")
    if sum(payload["genotype_evaluation_counts"].values()) != payload["evaluations"]:
        raise ValueError("Cached comparison genotype counts disagree with its evaluation count")


def run_comparison(config_path: str | Path, root: str | Path = ".", resume: bool = False) -> Path:
    """Run a saved development/held-out study, sequentially and checkpointed."""
    config = json.loads(Path(config_path).read_text())
    _configuration(config)
    root = Path(root)
    directory = root / "results" / config["name"]
    identity = {"config_sha256": _digest(config), **_source_manifest()}
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        original = json.loads(manifest_path.read_text())
        if any(original.get(key) != value for key, value in identity.items()):
            raise ValueError("Comparison config/source/runtime changed; choose a new study name")
        if not resume:
            raise ValueError("Comparison already exists; use --resume or another name")
    else:
        manifest = {
            **identity, "config": config,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "data": "unchanged original synthetic generator presets; separate feasibility certificates never supplied to search",
            "evaluation_protocol": "same full evaluator cap; all initialization/duplicates/rejected local candidates charged",
            "wall_time_protocol": "same wall allocation; boundary stop; late completed evaluations excluded from quality; overshoot reported",
            "timing": "sequential cold construction-cache runs; algorithm initialization/partial checks timed; imports/input validation/serialization/independent verification/plots excluded",
        }
        _json(manifest_path, manifest)
        source_snapshot = directory / "source_snapshot"
        source_snapshot.mkdir(parents=True, exist_ok=True)
        for source in Path(__file__).parent.glob("*.py"):
            (source_snapshot / source.name).write_bytes(source.read_bytes())
    methods = list(config.get("methods", METHODS))
    protocols = list(config.get("protocols", PROTOCOLS))
    for scenario in config["scenarios"]:
        size = scenario["size"]
        budget = scenario["budget"]
        population = scenario.get("population_size", config.get("population_size", 24))
        for instance_seed in scenario.get("instance_seeds", config.get("instance_seeds", [])):
            problem, certificate = importlib.import_module("timetable.generation").generate_instance(size, instance_seed)
            instance_id = f"{size}_{instance_seed}"
            problem_data = problem_to_dict(problem)
            instance_hash = _digest(problem_data)
            _json(root / "data" / config["name"] / f"{instance_id}.json", problem_data)
            _json(root / "data" / config["name"] / "certificates" / f"{instance_id}.json", schedule_to_dict(certificate))
            for solver_seed in scenario.get("solver_seeds", config.get("solver_seeds", [])):
                offset = solver_seed % len(methods)
                ordered_methods = methods[offset:] + methods[:offset]
                ordered_protocols = protocols if solver_seed % 2 == 0 else list(reversed(protocols))
                for protocol in ordered_protocols:
                    for method in ordered_methods:
                        allocation = scenario.get("wall_time_seconds") if protocol == "wall_time" else None
                        cap = config.get("evaluation_ceiling", 100_000) if allocation is not None else budget
                        expected = {"instance_id": instance_id, "instance_seed": instance_seed, "size": size,
                                    "instance_sha256": instance_hash, "method": method,
                                    "solver_seed": solver_seed, "protocol": protocol,
                                    "population_size": population, "evaluation_cap": cap,
                                    "wall_time_limit": allocation}
                        path = directory / "runs" / f"{instance_id}_{protocol}_{method}_{solver_seed}.json"
                        if resume and path.exists():
                            _validate_cached(problem, json.loads(path.read_text()), expected)
                            continue
                        print(f"{config['name']}: {instance_id} {protocol} {method} seed={solver_seed}", flush=True)
                        payload = run_comparison_method(
                            problem, method, solver_seed, budget, population,
                            allocation, config.get("evaluation_ceiling", 100_000),
                        )
                        payload.update(expected)
                        payload["phase"] = config.get("phase", "unspecified")
                        _json(path, payload)
                        print(f"  HV={payload['hypervolume']:.8f} feasible={payload['feasible_run']} "
                              f"evals={payload['evaluations']} elapsed={payload['runtime']:.3f}s "
                              f"overshoot={payload['wall_time_overshoot_seconds']:.3f}s", flush=True)
    final_source = _source_manifest()
    if final_source != {key: identity[key] for key in final_source}:
        raise ValueError("Source/runtime changed during comparison; results must not be combined as one frozen study")
    analyze_comparison(directory)
    return directory


def _first_quality_time(run, target: float | None) -> float | None:
    if target is None or target <= 0:
        return None
    return next((row["elapsed_seconds"] for row in run["history"]
                 if not row["completed_after_deadline"] and row["hypervolume"] >= target - 1e-12), None)


def _direct_pair_summary(pairs, reference_method: str) -> dict:
    """Paired comparison for predeclared non-greedy causal/reference questions."""
    identities = sorted(set(run["instance_id"] for run, _ in pairs))
    forward = [coverage(run["objectives"], reference["objectives"]) for run, reference in pairs]
    reverse = [coverage(reference["objectives"], run["objectives"]) for run, reference in pairs]
    forward_defined = [value for value in forward if value is not None]
    reverse_defined = [value for value in reverse if value is not None]
    return {
        "method": "memetic", "reference_method": reference_method,
        "paired_run_descriptive": paired_comparison(
            [run["hypervolume"] for run, _ in pairs], [reference["hypervolume"] for _, reference in pairs]),
        "instance_mean_sign_test": paired_comparison(
            [mean(run["hypervolume"] for run, _ in pairs if run["instance_id"] == identity) for identity in identities],
            [mean(reference["hypervolume"] for _, reference in pairs if reference["instance_id"] == identity) for identity in identities]),
        "instance_mean_differences": _instance_differences(pairs),
        "coverage_method_over_reference_mean": mean(forward_defined) if forward_defined else None,
        "coverage_method_over_reference_defined_pairs": len(forward_defined),
        "coverage_reference_over_method_mean": mean(reverse_defined) if reverse_defined else None,
        "coverage_reference_over_method_defined_pairs": len(reverse_defined),
        "interpretation": (
            "Compares the NSGA-II tournament/rank/crowding/survival policy bundle against fixed-scalar local trajectories with the same initialization/proposal family; it does not isolate one selection component."
            if reference_method == "ablation_local" else
            "Compares the replacement feasible memetic method against the unchanged original enhanced NSGA-II."
        ),
        "inference_note": "Instance means are the independent comparison units; run-level results are descriptive, few instances have low power, and no multiplicity correction is applied.",
    }


def _instance_differences(pairs) -> list[dict]:
    result = []
    for identity in sorted(set(run["instance_id"] for run, _ in pairs)):
        selected = [(run, reference) for run, reference in pairs if run["instance_id"] == identity]
        first = mean(run["hypervolume"] for run, _ in selected)
        second = mean(reference["hypervolume"] for _, reference in selected)
        result.append({"instance_id": identity, "paired_solver_seeds": len(selected),
                       "method_mean_hypervolume": first, "reference_mean_hypervolume": second,
                       "difference": first - second})
    return result


def analyze_comparison(directory: str | Path) -> dict:
    """Summarize paired evidence without requiring an enhancement win."""
    directory = Path(directory)
    runs = [json.loads(path.read_text()) for path in sorted((directory / "runs").glob("*.json"))]
    if not runs:
        raise ValueError("No completed comparison runs")
    fields = ["instance_id", "size", "instance_seed", "solver_seed", "protocol", "method",
              "population_size", "evaluation_cap", "wall_time_limit", "evaluations", "runtime",
              "wall_time_overshoot_seconds", "feasible_run", "archive_size", "hypervolume",
              "spacing", "time_to_first_feasible_seconds", "feasible_evaluation_fraction",
              "on_time_feasible_evaluation_fraction", "duplicate_evaluation_fraction", "minimum_violation"]
    with (directory / "runs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: run.get(field) for field in fields} for run in runs)
    summary = []
    comparisons = {}
    quality_times = []
    groups = sorted(set((run["size"], run["protocol"]) for run in runs))
    lines = ["# Enhancement comparison: measured synthetic results", "",
             "Original datasets, objectives, constraints and greedy heuristic are unchanged. "
             "Evaluation caps and wall-time allocations are separate protocols. "
             "Boundary overshoot is reported; late evaluations receive no quality credit. "
             "Observed archives do not certify global Pareto optimality.", "",
             "| Size | Protocol | Method | Runs | Feasible | HV mean ± SD | Runtime mean (s) | Evaluations mean | Duplicate fraction |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for size, protocol in groups:
        selected = [run for run in runs if run["size"] == size and run["protocol"] == protocol]
        baselines = {(run["instance_id"], run["solver_seed"]): run for run in selected if run["method"] == "greedy"}
        for method in sorted(set(run["method"] for run in selected)):
            values = [run for run in selected if run["method"] == method]
            record = {"size": size, "protocol": protocol, "method": method, "runs": len(values),
                      "feasible_runs": sum(run["feasible_run"] for run in values)}
            for metric in ("hypervolume", "runtime", "evaluations", "archive_size", "duplicate_evaluation_fraction",
                           "feasible_evaluation_fraction", "wall_time_overshoot_seconds"):
                sample = [run[metric] for run in values]
                record[metric + "_mean"] = mean(sample)
                record[metric + "_sd"] = stdev(sample) if len(sample) > 1 else 0.0
            vectors = [vector for run in values for vector in run["objectives"]]
            record["best_objectives"] = [min(vector[j] for vector in vectors) for j in range(3)] if vectors else None
            feasible_values = [run for run in values if run["objectives"]]
            record["mean_run_best_objectives_conditional"] = [
                mean(min(vector[j] for vector in run["objectives"]) for run in feasible_values)
                for j in range(3)
            ] if feasible_values else None
            record["mean_front_objectives_per_run_conditional"] = [
                mean(mean(vector[j] for vector in run["objectives"]) for run in feasible_values)
                for j in range(3)
            ] if feasible_values else None
            first_times = [run["time_to_first_feasible_seconds"] for run in values if run["time_to_first_feasible_seconds"] is not None]
            record["time_to_first_feasible_mean_conditional"] = mean(first_times) if first_times else None
            record["time_to_first_feasible_observations"] = len(first_times)
            summary.append(record)
            lines.append(f"| {size} | {protocol} | {method} | {len(values)} | {record['feasible_runs']} | "
                         f"{record['hypervolume_mean']:.8f} ± {record['hypervolume_sd']:.8f} | "
                         f"{record['runtime_mean']:.3f} | {record['evaluations_mean']:.1f} | "
                         f"{record['duplicate_evaluation_fraction_mean']:.1%} |")
            if method == "greedy":
                continue
            pairs = [(run, baselines[run["instance_id"], run["solver_seed"]]) for run in values
                     if (run["instance_id"], run["solver_seed"]) in baselines]
            if not pairs:
                continue
            instance_ids = sorted(set(run["instance_id"] for run, _ in pairs))
            cover_forward = [coverage(run["objectives"], baseline["objectives"]) for run, baseline in pairs]
            cover_reverse = [coverage(baseline["objectives"], run["objectives"]) for run, baseline in pairs]
            observed_forward = [value for value in cover_forward if value is not None]
            observed_reverse = [value for value in cover_reverse if value is not None]
            comparisons[f"{size}/{protocol}/{method}_vs_greedy"] = {
                "paired_run_descriptive": paired_comparison(
                    [run["hypervolume"] for run, _ in pairs], [baseline["hypervolume"] for _, baseline in pairs]),
                "instance_mean_sign_test": paired_comparison(
                    [mean(run["hypervolume"] for run, _ in pairs if run["instance_id"] == identity) for identity in instance_ids],
                    [mean(base["hypervolume"] for _, base in pairs if base["instance_id"] == identity) for identity in instance_ids]),
                "instance_mean_differences": _instance_differences(pairs),
                "coverage_method_over_greedy_mean": mean(observed_forward) if observed_forward else None,
                "coverage_method_over_greedy_defined_pairs": len(observed_forward),
                "coverage_greedy_over_method_mean": mean(observed_reverse) if observed_reverse else None,
                "coverage_greedy_over_method_defined_pairs": len(observed_reverse),
                "inference_note": "Solver seeds within an instance are clustered; independent-instance mean tests have low power with few instances. No multiplicity-adjusted superiority claim is implied.",
            }
            for run, baseline in pairs:
                quality_times.append({
                    "instance_id": run["instance_id"], "size": size, "protocol": protocol,
                    "solver_seed": run["solver_seed"], "method": method,
                    "paired_greedy_final_hypervolume": baseline["hypervolume"],
                    "method_time_to_target_seconds": _first_quality_time(run, baseline["hypervolume"]),
                    "greedy_time_to_target_seconds": _first_quality_time(baseline, baseline["hypervolume"]),
                    "target_scope": "retrospective paired greedy endpoint, not a predeclared independent quality target; null means not reached or target undefined",
                })
        memetic_runs = [run for run in selected if run["method"] == "memetic"]
        for reference_method in ("ablation_local", "original_enhanced"):
            references = {(run["instance_id"], run["solver_seed"]): run for run in selected
                          if run["method"] == reference_method}
            direct_pairs = [(run, references[run["instance_id"], run["solver_seed"]]) for run in memetic_runs
                            if (run["instance_id"], run["solver_seed"]) in references]
            if direct_pairs:
                comparisons[f"{size}/{protocol}/memetic_vs_{reference_method}"] = _direct_pair_summary(direct_pairs, reference_method)
    result = {"summary": summary, "comparisons": comparisons, "paired_endpoint_quality_times": quality_times}
    _json(directory / "summary.json", result)
    (directory / "summary.md").write_text("\n".join(lines) + "\n")
    return result

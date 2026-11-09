"""Seed-controlled experiments, checkpointed raw schedules, and honest summaries."""
from __future__ import annotations

import csv
from dataclasses import asdict
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import random
from statistics import mean, stdev
import sys
from time import perf_counter

import numpy as np

from .evaluation import evaluate
from .export import export_schedule
from .generation import generate_instance
from .greedy import construct
from .metrics import (hypervolume, nondominated_indices, normalize, objective_scales,
                      paired_comparison, spacing, coverage)
from .model import problem_to_dict, problem_from_dict, schedule_to_dict, schedule_from_dict
from .nsga2 import SearchResult, nsga2
from .visualization import plot_comparison, plot_convergence, plot_fronts, plot_grid

METHODS = ("greedy", "nsga2", "seeded", "enhanced")


def _json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic checkpoint: interrupted experiment files are never mistaken for complete runs.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def greedy_search(problem, seed: int, budget: int) -> SearchResult:
    """Strong baseline: repeated independent DSatur constructions + Pareto archive.

    One construction is deterministic, subsequent constructions are randomized.
    Exactly one full evaluator call per attempt; failed attempts count too.
    """
    if budget < 1:
        raise ValueError("budget must be positive")
    rng = random.Random(seed)
    started = perf_counter()
    archive = []
    values = []
    history = []
    feasible_count = 0
    min_violation = None
    best = None
    for i in range(budget):
        candidate = construct(problem, rng, randomized=i > 0)
        ev = evaluate(problem, candidate)
        if min_violation is None or ev.violation < min_violation:
            min_violation, best = ev.violation, candidate
        if ev.feasible:
            feasible_count += 1
            all_values = values + [ev.objectives]
            keep = nondominated_indices(all_values)
            archive = [(archive + [candidate])[j] for j in keep]
            values = [all_values[j] for j in keep]
        history.append({"generation": i, "evaluations": i + 1, "front": [list(v) for v in values],
                        "feasible_fraction": float(ev.feasible),
                        "evaluated_feasible_fraction": feasible_count / (i + 1), "min_violation": min_violation})
    return SearchResult(archive, history, budget, perf_counter() - started,
                        {"evaluated_feasible": feasible_count, "minimum_violation": min_violation,
                         "algorithm": "random_restart_dsatur", "budget": budget},
                        archive[0] if archive else best, [])


def run_method(problem, method: str, seed: int, budget: int, population_size: int = 24) -> SearchResult:
    if method == "greedy":
        return greedy_search(problem, seed, budget)
    if method not in METHODS:
        raise ValueError(f"Unknown method {method}")
    return nsga2(problem, seed=seed, population_size=population_size,
                 generations=budget, max_evaluations=budget,
                 enhanced=method != "nsga2", repair=method == "enhanced",
                 local_search=method == "enhanced")


def serialize_run(problem, result: SearchResult, method: str, seed: int) -> dict:
    scales = objective_scales(problem)
    objectives = [evaluate(problem, schedule).objectives for schedule in result.archive]
    for schedule in result.archive:
        if not evaluate(problem, schedule).feasible:
            raise AssertionError("Algorithm returned an invalid archive timetable")
    normalized = [normalize(v, scales) for v in objectives]
    history = []
    for row in result.history:
        row = dict(row)
        row["hypervolume"] = hypervolume([normalize(v, scales) for v in row.pop("front", [])])
        history.append(row)
    diagnostic = evaluate(problem, result.best_schedule) if result.best_schedule is not None else None
    return {"method": method, "solver_seed": seed,
            "evaluations": result.evaluations, "runtime": result.runtime,
            "normalization": scales, "reference": [1.1, 1.1, 1.1],
            "hypervolume": hypervolume(normalized), "spacing": spacing(normalized),
            "archive_size": len(objectives), "objectives": objectives,
            "archive": [schedule_to_dict(s) for s in result.archive],
            "history": history, "metadata": result.metadata,
            "best_candidate_diagnostic": asdict(diagnostic) if diagnostic else None,
            "feasible_run": bool(objectives),
            "feasible_evaluation_fraction": result.metadata.get("evaluated_feasible", 0) / result.evaluations if result.evaluations else 0.0,
            "minimum_violation": result.metadata.get("minimum_violation", 0)}


def run_suite(config_path: str | Path, root: str | Path = ".", resume: bool = False) -> Path:
    root = Path(root)
    config = json.loads(Path(config_path).read_text())
    study = config["name"]
    if not study or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in study):
        raise ValueError("Study name must contain only letters, digits, underscore and hyphen")
    methods_config = config.get("methods", METHODS)
    if not methods_config or len(set(methods_config)) != len(methods_config) or any(m not in METHODS for m in methods_config):
        raise ValueError("Methods must be a nonempty unique selection of greedy, nsga2, seeded, enhanced")
    seen_instances = set()
    for scenario in config["scenarios"]:
        seeds = scenario.get("instance_seeds", config.get("instance_seeds", [10]))
        solver_seeds = scenario.get("solver_seeds", config.get("solver_seeds", [0, 1, 2]))
        if not seeds or not solver_seeds or len(set(solver_seeds)) != len(solver_seeds):
            raise ValueError("Each scenario needs nonempty unique instance/solver seeds")
        if any(type(s) is not int for s in list(seeds) + list(solver_seeds)):
            raise ValueError("Seeds must be integers")
        for seed in seeds:
            key = (scenario["size"], seed)
            if key in seen_instances:
                raise ValueError("Repeated size/instance_seed would overwrite a run; use a separate study name for each scenario")
            seen_instances.add(key)
    result_dir = root / "results" / study
    result_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    source_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(Path(__file__).parent.glob("*.py"))}
    source_fingerprint = hashlib.sha256(json.dumps(source_files, sort_keys=True).encode()).hexdigest()
    manifest_path = result_dir / "manifest.json"
    old = None
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        if old["config_sha256"] != fingerprint:
            raise ValueError("Study exists with a different config; choose another study name")
        if old.get("source_sha256") != source_fingerprint:
            raise ValueError("Study exists with different source code; choose another study name to keep comparisons reproducible")
        if not resume:
            raise ValueError("Study already exists; use --resume or a different name")
    versions = {}
    for name in ("numpy", "matplotlib", "ortools", "pytest"):
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    manifest = {"config": config, "config_sha256": fingerprint,
                          "source_sha256": source_fingerprint, "source_files": source_files,
                          "python": sys.version, "platform": platform.platform(), "versions": versions,
                          "cpu_count": os.cpu_count(),
                          "data_source": "synthetic planted-feasible; no real institutional data",
                          "runtime_protocol": "sequential methods; wall time includes construction/repair; excludes serialization/plotting",
                          "budget_protocol": "equal full evaluator cap within scenario; constructive resource checks timed but not counted"}
    if old is not None:
        if old["versions"] != versions or old["python"] != sys.version or old["platform"] != platform.platform():
            raise ValueError("Resume requires the recorded Python/dependencies/platform; use a new study name for another environment")
    else:
        _json(manifest_path, manifest)
    for scenario in config["scenarios"]:
        size = scenario["size"]
        budget = scenario["budget"]
        population = scenario.get("population_size", config.get("population_size", 24))
        for instance_seed in scenario.get("instance_seeds", config.get("instance_seeds", [10])):
            problem, witness = generate_instance(size, instance_seed, scenario.get("generator"))
            instance_id = f"{size}_{instance_seed}"
            data = problem_to_dict(problem)
            instance_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            _json(root / "data" / study / f"{instance_id}.json", data)
            _json(root / "data" / study / "certificates" / f"{instance_id}.json", schedule_to_dict(witness))
            for seed in scenario.get("solver_seeds", config.get("solver_seeds", [0, 1, 2])):
                # Rotate execution order deterministically to reduce systematic timing order bias.
                methods = list(config.get("methods", METHODS))
                offset = seed % len(methods)
                methods = methods[offset:] + methods[:offset]
                for method in methods:
                    path = result_dir / "runs" / f"{instance_id}_{method}_{seed}.json"
                    if resume and path.exists():
                        cached = json.loads(path.read_text())
                        expected = {"instance_id": instance_id, "instance_seed": instance_seed, "solver_seed": seed,
                                    "size": size, "method": method, "budget": budget, "population_size": population,
                                    "instance_sha256": instance_hash}
                        if any(cached.get(k) != v for k, v in expected.items()) or cached.get("evaluations") != budget:
                            raise ValueError(f"Cached run identity/budget mismatch: {path}")
                        archived = [schedule_from_dict(s) for s in cached["archive"]]
                        outcomes = [evaluate(problem, s) for s in archived]
                        if any(not ev.feasible for ev in outcomes) or [list(ev.objectives) for ev in outcomes] != cached["objectives"]:
                            raise ValueError(f"Cached archive failed independent validation: {path}")
                        continue
                    print(f"{study}: {instance_id} {method} seed={seed} budget={budget}", flush=True)
                    result = run_method(problem, method, seed, budget, population)
                    payload = serialize_run(problem, result, method, seed)
                    payload.update({"instance_id": instance_id, "instance_seed": instance_seed,
                                    "size": size, "budget": budget, "population_size": population,
                                    "instance_sha256": instance_hash})
                    _json(path, payload)
                    print(f"  feasible={payload['feasible_run']} HV={payload['hypervolume']:.6f} "
                          f"front={payload['archive_size']} runtime={payload['runtime']:.2f}s", flush=True)
    analyze_suite(result_dir, root / "figures" / study)
    return result_dir


def analyze_suite(result_dir: str | Path, figure_dir: str | Path | None = None) -> dict:
    result_dir = Path(result_dir)
    figure_dir = Path(figure_dir) if figure_dir else result_dir.parent.parent / "figures" / result_dir.name
    figure_dir.mkdir(parents=True, exist_ok=True)
    runs = [json.loads(p.read_text()) for p in sorted((result_dir / "runs").glob("*.json"))]
    if not runs:
        raise ValueError("No completed runs found")
    fields = ["instance_id", "size", "instance_seed", "solver_seed", "method", "budget", "evaluations", "runtime",
              "feasible_run", "feasible_evaluation_fraction", "minimum_violation", "archive_size", "hypervolume", "spacing"]
    with (result_dir / "runs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: run[key] for key in fields} for run in runs)
    summary = []
    markdown = ["# Measured synthetic benchmark results", "",
                "Each cell summarizes independent solver seeds and planted-feasible instance seeds. "
                "Objective minima may belong to different schedules. Empty archives have HV=0. "
                "Observed fronts are not certificates of global Pareto optimality.", "",
                "| Size | Method | Runs | Feasible runs | Mean HV ± SD | Mean runtime (s) | Mean front size | Feasible evaluations |",
                "|---|---|---:|---:|---:|---:|---:|---:|"]
    comparisons = {}
    for size in dict.fromkeys(run["size"] for run in runs):
        selected = [r for r in runs if r["size"] == size]
        for method in sorted(set(r["method"] for r in selected)):
            method_runs = [r for r in selected if r["method"] == method]
            record = {"size": size, "method": method, "runs": len(method_runs),
                      "feasible_runs": sum(r["feasible_run"] for r in method_runs)}
            for metric in ["hypervolume", "runtime", "archive_size", "feasible_evaluation_fraction"]:
                values = [r[metric] for r in method_runs]
                record[metric + "_mean"] = mean(values)
                record[metric + "_sd"] = stdev(values) if len(values) > 1 else 0
            points = [v for r in method_runs for v in r["objectives"]]
            record["best_objectives"] = [min(v[j] for v in points) for j in range(3)] if points else None
            feasible_runs = [r for r in method_runs if r["objectives"]]
            record["mean_run_best_objectives"] = [mean(min(v[j] for v in r["objectives"]) for r in feasible_runs)
                                                    for j in range(3)] if feasible_runs else None
            record["mean_front_objectives_per_run"] = [mean(mean(v[j] for v in r["objectives"]) for r in feasible_runs)
                                                       for j in range(3)] if feasible_runs else None
            summary.append(record)
            markdown.append(f"| {size} | {method} | {len(method_runs)} | {record['feasible_runs']} | "
                            f"{record['hypervolume_mean']:.6f} ± {record['hypervolume_sd']:.6f} | "
                            f"{record['runtime_mean']:.3f} | {record['archive_size_mean']:.2f} | "
                            f"{record['feasible_evaluation_fraction_mean']:.1%} |")
        plot_convergence(selected, figure_dir / f"{size}_convergence.png", selected[0]["budget"])
        plot_comparison(selected, figure_dir / f"{size}_comparison.png")
        points = [{"method": r["method"], "objectives": v} for r in selected for v in r["objectives"]]
        plot_fronts(points, figure_dir / f"{size}_pareto.png", f"{size.title()} synthetic instances: per-run non-dominated archives")
        baseline = {(r["instance_id"], r["solver_seed"]): r for r in selected if r["method"] == "greedy"}
        for method in sorted(set(r["method"] for r in selected) - {"greedy"}):
            pairs = [(r, baseline[(r["instance_id"], r["solver_seed"])]) for r in selected
                     if r["method"] == method and (r["instance_id"], r["solver_seed"]) in baseline]
            if pairs:
                descriptive = paired_comparison([a["hypervolume"] for a, b in pairs], [b["hypervolume"] for a, b in pairs])
                ids = sorted(set(a["instance_id"] for a, b in pairs))
                instance_means = paired_comparison(
                    [mean(a["hypervolume"] for a, b in pairs if a["instance_id"] == i) for i in ids],
                    [mean(b["hypervolume"] for a, b in pairs if b["instance_id"] == i) for i in ids])
                comparisons[f"{size}/{method}_vs_greedy"] = {
                    "paired_run_descriptive": descriptive, "instance_mean_sign_test": instance_means,
                    "note": "Runs within an instance are clustered; use instance means for inference. Few instances => low power.",
                    "coverage_method_over_greedy_mean": mean(coverage(a["objectives"], b["objectives"]) or 0 for a, b in pairs),
                    "coverage_greedy_over_method_mean": mean(coverage(b["objectives"], a["objectives"]) or 0 for a, b in pairs)}
    tradeoffs = {}
    for instance_id in sorted(set(r["instance_id"] for r in runs)):
        pooled = [v for r in runs if r["instance_id"] == instance_id for v in r["objectives"]]
        front = [pooled[i] for i in nondominated_indices(pooled)]
        counts = {}
        for a, b in [(0, 1), (0, 2), (1, 2)]:
            counts[f"f{a+1}_vs_f{b+1}"] = sum((p[a]-q[a]) * (p[b]-q[b]) < -1e-14
                                                 for i, p in enumerate(front) for q in front[i+1:])
        tradeoffs[instance_id] = {"pooled_nondominated_vectors": len(front), "opposing_pair_counts": counts,
                                  "objective_ranges": [[min(v[j] for v in front), max(v[j] for v in front)]
                                                       for j in range(3)] if front else None,
                                  "scope": "empirical pooled archives on this instance; no global optimality claim"}
    _json(result_dir / "summary.json", {"summary": summary, "comparisons": comparisons, "tradeoffs": tradeoffs})
    (result_dir / "summary.md").write_text("\n".join(markdown) + "\n")
    return {"summary": summary, "comparisons": comparisons}


def export_representatives(problem, schedules, output: Path, figure_dir: Path) -> None:
    if not schedules:
        return
    values = [evaluate(problem, s).objectives for s in schedules]
    keep = nondominated_indices(values)
    schedules = [schedules[i] for i in keep]
    values = [values[i] for i in keep]
    selections = {label: min(range(len(values)), key=lambda i: values[i][j])
                  for j, label in enumerate(["fewest_gaps", "best_room_fit", "balanced_workload"])}
    # This is an explicitly defined compromise, not an asserted geometrical knee.
    array = np.asarray(values)
    spans = np.ptp(array, axis=0)
    scaled = (array - array.min(axis=0)) / np.where(spans > 0, spans, 1)
    selections["normalized_compromise"] = int(np.argmin(np.linalg.norm(scaled, axis=1)))
    index = {}
    for label, i in selections.items():
        export_schedule(problem, schedules[i], output / label, label)
        plot_grid(problem, schedules[i], "group", problem.groups[0].id, figure_dir / f"{label}.png")
        index[label] = {"archive_index": i, "objectives": values[i]}
    _json(output / "representatives.json", index)

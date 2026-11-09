"""Small CLI: data generation, search, independent validation and experiments."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .evaluation import evaluate
from .generation import generate_instance
from .model import problem_from_dict, problem_to_dict, schedule_from_dict, schedule_to_dict


def _read(path):
    return json.loads(Path(path).read_text())


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Multi-objective college timetable optimization")
    sub = p.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="Generate a synthetic instance and optional separate feasibility certificate")
    gen.add_argument("--size", choices=["small", "medium", "large"], default="small")
    gen.add_argument("--seed", type=int, default=0)
    gen.add_argument("--config", help="JSON generator parameter overrides")
    gen.add_argument("--output", default="data/demo.json")
    gen.add_argument("--certificate", help="Optional separate certificate file; never used by solve")
    solve = sub.add_parser("solve", help="Optimize and export feasible non-dominated timetables")
    solve.add_argument("instance")
    solve.add_argument("--method", choices=["greedy", "nsga2", "seeded", "enhanced", "memetic", "cpsat"], default="enhanced")
    solve.add_argument("--seed", type=int, default=0)
    solve.add_argument("--budget", type=int, default=480)
    solve.add_argument("--population", type=int, default=24)
    solve.add_argument("--output", default="results/demo")
    solve.add_argument("--figures", default="figures/demo")
    solve.add_argument("--objective", choices=["feasibility", "gaps", "room"], default="gaps", help="CP-SAT objective only")
    solve.add_argument("--time-limit", type=float, default=15.0, help="CP-SAT solver time limit, excluding model build")
    solve.add_argument("--search-seconds", type=float, help="Optional total search deadline for the memetic method")
    val = sub.add_parser("evaluate", aliases=["validate"], help="Independently check a schedule (nonzero exit if infeasible)")
    val.add_argument("instance")
    val.add_argument("schedule")
    exp = sub.add_parser("experiment", help="Run/resume a saved paired benchmark configuration")
    exp.add_argument("--config", default="experiments/benchmark.json")
    exp.add_argument("--resume", action="store_true")
    compare = sub.add_parser("compare", help="Compare the new search with unchanged baselines under evaluation/time budgets")
    compare.add_argument("--config", default="experiments/enhancement_validation.json")
    compare.add_argument("--resume", action="store_true")
    plot = sub.add_parser("plot", help="Regenerate summary tables and figures from saved raw runs")
    plot.add_argument("--results", default="results/benchmark")
    plot.add_argument("--figures")
    micro = sub.add_parser("prove-tradeoffs", help="Exhaust tiny synthetic instances to certify genuine global Pareto fronts")
    micro.add_argument("--output", default="results/exact_micro")
    micro.add_argument("--figures", default="figures/exact_micro")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "generate":
            problem, certificate = generate_instance(args.size, args.seed, _read(args.config) if args.config else None)
            _write(args.output, problem_to_dict(problem))
            if args.certificate:
                _write(args.certificate, schedule_to_dict(certificate))
            print(f"Generated {len(problem.events)} synthetic events: {args.output}")
            return 0
        if args.command in {"evaluate", "validate"}:
            problem = problem_from_dict(_read(args.instance))
            data = _read(args.schedule)
            schedule = schedule_from_dict(data.get("schedule", data))
            result = evaluate(problem, schedule)
            print(json.dumps(asdict(result) | {"feasible": result.feasible}, indent=2, allow_nan=False))
            return 0 if result.feasible else 2
        if args.command == "experiment":
            from .experiments import run_suite
            print(run_suite(args.config, resume=args.resume))
            return 0
        if args.command == "compare":
            from .comparison import run_comparison
            print(run_comparison(args.config, resume=args.resume))
            return 0
        if args.command == "plot":
            from .experiments import analyze_suite
            result = analyze_suite(args.results, args.figures)
            print(json.dumps(result["summary"], indent=2))
            return 0
        if args.command == "prove-tradeoffs":
            from .exact import enumerate_pareto
            from .examples import conflict_instance
            from .experiments import export_representatives
            from .visualization import plot_fronts
            for case in ("room", "workload"):
                problem = conflict_instance(case)
                result = enumerate_pareto(problem)
                out = Path(args.output) / case
                _write(out / "instance.json", problem_to_dict(problem))
                _write(out / "exact_front.json", {"status": result.status, "evaluated": result.evaluated,
                                                 "feasible_candidates": result.feasible_candidates,
                                                 "runtime": result.runtime, "objectives": result.objectives,
                                                 "archive": [schedule_to_dict(s) for s in result.archive]})
                export_representatives(problem, result.archive, out / "timetables", Path(args.figures) / case)
                plot_fronts([{"method": "exhaustive", "objectives": v} for v in result.objectives],
                            Path(args.figures) / f"{case}_exact_front.png", f"Certified complete tiny {case} Pareto front", certified=True)
                print(f"{case}: {result.status}; {result.evaluated} genotypes; {result.objectives}")
            return 0
        if args.command == "solve":
            from .experiments import export_representatives, run_method, serialize_run
            from .visualization import plot_fronts
            problem = problem_from_dict(_read(args.instance))
            out, figures = Path(args.output), Path(args.figures)
            if args.method == "cpsat":
                from .exact import cp_sat
                from .export import export_schedule
                result = cp_sat(problem, objective=args.objective, time_limit=args.time_limit, seed=args.seed)
                payload = asdict(result)
                if result.schedule is not None:
                    payload["schedule"] = schedule_to_dict(result.schedule)
                    payload["evaluation"] = asdict(evaluate(problem, result.schedule))
                    export_schedule(problem, result.schedule, out / "timetable", f"CP-SAT {result.status}: {args.objective}")
                _write(out / "exact.json", payload)
                print(json.dumps({key: value for key, value in payload.items() if key not in {"schedule", "metadata"}}, indent=2))
                return 0 if result.schedule is not None else 2
            if args.method == "memetic":
                from .memetic import memetic_nsga2
                result = memetic_nsga2(problem, seed=args.seed, population_size=args.population,
                                       max_evaluations=args.budget, time_limit=args.search_seconds)
            else:
                result = run_method(problem, args.method, args.seed, args.budget, args.population)
            payload = serialize_run(problem, result, args.method, args.seed)
            _write(out / "run.json", payload)
            _write(out / "instance.json", problem_to_dict(problem))
            export_representatives(problem, result.archive, out / "timetables", figures)
            plot_fronts([{"method": args.method, "objectives": v} for v in payload["objectives"]], figures / "pareto.png")
            print(json.dumps({key: payload[key] for key in ["method", "evaluations", "runtime", "archive_size", "hypervolume", "minimum_violation"]}, indent=2))
            if not result.archive:
                print("No feasible timetable found. This is a search failure, not an infeasibility proof.")
            return 0 if result.archive else 2
    except (ValueError, KeyError, TypeError, OSError, ImportError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 1

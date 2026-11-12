"""Small CLI: data generation, search, independent validation, MCDM and experiments."""
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
    solve.add_argument("--method", choices=["greedy", "nsga2", "seeded", "enhanced", "memetic", "moead", "amosa", "cpsat", "cpsat-eps"], default="enhanced")
    solve.add_argument("--seed", type=int, default=0)
    solve.add_argument("--budget", type=int, default=480)
    solve.add_argument("--population", type=int, default=24)
    solve.add_argument("--output", default="results/demo")
    solve.add_argument("--figures", default="figures/demo")
    solve.add_argument("--objective", choices=["feasibility", "gaps", "room"], default="gaps", help="CP-SAT objective only")
    solve.add_argument("--time-limit", type=float, default=15.0, help="CP-SAT solver time limit, excluding model build")
    solve.add_argument("--search-seconds", type=float, help="Optional total search deadline for the memetic/moead/amosa method")
    solve.add_argument("--scalarization", choices=["tchebycheff", "augmented_tchebycheff", "weighted_sum"], default="tchebycheff", help="MOEA/D scalarization function")
    solve.add_argument("--neighborhood", type=int, default=6, help="MOEA/D subproblem neighborhood size")
    solve.add_argument("--eps-steps", type=int, default=5, help="Number of epsilon grid points for CP-SAT epsilon-constraint")

    val = sub.add_parser("evaluate", aliases=["validate"], help="Independently check a schedule (nonzero exit if infeasible)")
    val.add_argument("instance")
    val.add_argument("schedule")

    mcdm = sub.add_parser("mcdm", help="Run TOPSIS Multi-Criteria Decision-Making analysis on a Pareto front")
    mcdm.add_argument("instance")
    mcdm.add_argument("run", help="Path to run.json containing Pareto archive")
    mcdm.add_argument("--profile", choices=["balanced", "student_first", "admin_room_fit", "faculty_fairness"], default="balanced")

    exp = sub.add_parser("experiment", help="Run/resume a saved paired benchmark configuration")
    exp.add_argument("--config", default="experiments/benchmark.json")
    exp.add_argument("--resume", action="store_true")

    compare = sub.add_parser("compare", help="Compare the new search with unchanged baselines under evaluation/time budgets")
    compare.add_argument("--config", default="experiments/enhancement_validation.json")
    compare.add_argument("--resume", action="store_true")

    plot = sub.add_parser("plot", help="Regenerate summary tables and figures from saved raw runs")
    plot.add_argument("--results", default="results/benchmark")
    plot.add_argument("--figures")
    reopt = sub.add_parser("reoptimize", help="Minimal-change re-optimisation of a timetable after a disruption (epsilon-constraint)")
    reopt.add_argument("instance")
    reopt.add_argument("schedule", help="the published timetable S0 (schedule JSON, e.g. a representative's schedule.json)")
    reopt.add_argument("--disruption", required=True,
                       help="teacher_absent:F03:day=1 | teacher_absent:F03:slots=8,9 | teacher_leaves:F03 | room_closed:R02[:day=0]")
    reopt.add_argument("--epsilons", help="comma-separated change limits; default: repair changes + 0,2,5,10,20,40")
    reopt.add_argument("--budget", type=int, default=120, help="full evaluations per epsilon level")
    reopt.add_argument("--population", type=int, default=12)
    reopt.add_argument("--seed", type=int, default=0)
    reopt.add_argument("--output", default="results/reoptimize")
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

        if args.command == "mcdm":
            from .mcdm import analyze_stakeholder_profiles, topsis
            data = _read(args.run)
            objectives = [tuple(v) for v in data.get("objectives", [])]
            if not objectives:
                print("Error: No objectives found in run file.", file=sys.stderr)
                return 1
            analysis = analyze_stakeholder_profiles(objectives)
            print(f"--- TOPSIS Decision Analysis ({args.profile.upper()} profile) ---")
            profile_data = analysis[args.profile]
            print(f"Stakeholder Weights: {profile_data['weights']}")
            print(f"Top Recommended Solution Index: #{profile_data['top_choice_index']}")
            print(f"Top Solution Objectives: {profile_data['top_choice_objectives']} (Score: {profile_data['top_choice_score']})")
            print("\nFull Rankings across alternatives:")
            for item in profile_data["all_rankings"]:
                print(f"  Rank {item['rank']}: Sol #{item['index']} | Score: {item['score']} | Obj: {item['objectives']}")
            return 0

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
        if args.command == "reoptimize":
            from .disruption import apply_disruption, epsilon_reoptimize, parse_disruption, reoptimization_to_dict
            problem = problem_from_dict(_read(args.instance))
            data = _read(args.schedule)
            original = schedule_from_dict(data.get("schedule", data))
            if not evaluate(problem, original).feasible:
                raise ValueError("the given timetable is not feasible for the given instance")
            disruption = parse_disruption(problem, args.disruption)
            disrupted = apply_disruption(problem, disruption)
            epsilons = [int(x) for x in args.epsilons.split(",")] if args.epsilons else None
            result = epsilon_reoptimize(disrupted, original, disruption, epsilons, args.budget, args.population,
                                        args.seed, original_problem=problem)
            out = Path(args.output)
            payload = reoptimization_to_dict(disrupted, original, result)
            _write(out / "reoptimization.json", payload)
            _write(out / "disrupted_instance.json", problem_to_dict(disrupted))
            _write(out / "repaired_schedule.json", schedule_to_dict(result.repair.schedule))
            for level in result.levels:
                if level.feasible:
                    _write(out / f"eps_{level.epsilon}" / "schedule.json", schedule_to_dict(level.archive[level.compromise_index()]))
            print(json.dumps({"disruption": payload["disruption"], "repair": payload["repair"],
                              "levels": [{k: lv[k] for k in ("epsilon", "front_size", "hypervolume", "compromise")} for lv in payload["levels"]]},
                             indent=2))
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

            if args.method == "cpsat-eps":
                from .exact import epsilon_constraint_cp_sat
                eps_res = epsilon_constraint_cp_sat(
                    problem,
                    primary_objective="gaps",
                    epsilon_objective="room",
                    steps=args.eps_steps,
                    time_limit_per_step=args.time_limit,
                    seed=args.seed,
                )
                payload = {
                    "method": "cpsat_epsilon_constraint",
                    "runtime": eps_res.runtime,
                    "evaluated_steps": eps_res.evaluated_steps,
                    "optimal_steps": eps_res.optimal_steps,
                    "feasible_steps": eps_res.feasible_steps,
                    "archive_size": len(eps_res.objectives),
                    "objectives": eps_res.objectives,
                    "epsilons": eps_res.epsilons,
                    "metadata": eps_res.metadata,
                }
                _write(out / "exact_pareto.json", payload)
                export_representatives(problem, eps_res.archive, out / "timetables", figures)
                plot_fronts([{"method": "cpsat_eps", "objectives": v} for v in eps_res.objectives], figures / "exact_pareto.png", "Exact Pareto Front via Epsilon-Constraint CP-SAT", certified=True)
                print(json.dumps({key: payload[key] for key in ["method", "runtime", "archive_size", "objectives"]}, indent=2))
                return 0 if eps_res.archive else 2

            if args.method == "memetic":
                from .memetic import memetic_nsga2
                result = memetic_nsga2(problem, seed=args.seed, population_size=args.population,
                                       max_evaluations=args.budget, time_limit=args.search_seconds)
            elif args.method == "moead":
                from .moead import moead
                result = moead(problem, seed=args.seed, population_size=args.population,
                               max_evaluations=args.budget, time_limit=args.search_seconds,
                               neighborhood_size=args.neighborhood, scalarization=args.scalarization)
            elif args.method == "amosa":
                from .amosa import amosa
                result = amosa(problem, seed=args.seed, population_size=args.population,
                               max_evaluations=args.budget, time_limit=args.search_seconds)
            else:
                result = run_method(problem, args.method, args.seed, args.budget, args.population)

            payload = serialize_run(problem, result, args.method, args.seed)
            # Add TOPSIS analysis to payload
            if payload["objectives"]:
                from .mcdm import analyze_stakeholder_profiles
                payload["topsis"] = analyze_stakeholder_profiles([tuple(v) for v in payload["objectives"]])

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

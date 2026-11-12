"""Paired experimental comparison between all multi-objective algorithms.

Compares:
1. Greedy / DSatur repeated construction baseline
2. Standard NSGA-II (Deb et al., 2002)
3. Feasible-domain Memetic NSGA-II
4. MOEA/D (Decomposition with Tchebycheff scalarization)
5. AMOSA (Archived Multi-Objective Simulated Annealing)

Evaluates all algorithms on the same problem instance, under identical evaluation
budgets, and computes Hypervolume, Spacing, Runtime, and TOPSIS rankings.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter
import sys

from timetable.evaluation import evaluate
from timetable.experiments import greedy_search, serialize_run
from timetable.generation import generate_instance
from timetable.mcdm import analyze_stakeholder_profiles, topsis
from timetable.memetic import memetic_nsga2
from timetable.moead import moead
from timetable.amosa import amosa
from timetable.nsga2 import nsga2
from timetable.metrics import hypervolume, normalize, objective_scales, spacing
from timetable.model import problem_from_dict, problem_to_dict


def run_benchmark(
    problem,
    seed: int = 0,
    budget: int = 240,
    population_size: int = 24,
) -> dict:
    scales = objective_scales(problem)
    results = {}

    print(f"Running benchmark on instance ({len(problem.events)} events, {len(problem.groups)} groups, {len(problem.faculty)} faculty)...")
    print(f"Protocol: Budget = {budget} full evaluations, Seed = {seed}, Pop = {population_size}\n")

    # 1. Greedy baseline
    print("--> 1/5: Running Greedy (DSatur baseline)...", end="", flush=True)
    t0 = perf_counter()
    res_greedy = greedy_search(problem, seed=seed, budget=budget)
    t_greedy = perf_counter() - t0
    results["Greedy"] = (res_greedy, t_greedy)
    print(f" Done ({t_greedy:.2f}s)")

    # 2. Standard NSGA-II
    print("--> 2/5: Running Standard NSGA-II...", end="", flush=True)
    t0 = perf_counter()
    res_nsga2 = nsga2(problem, seed=seed, population_size=population_size, generations=budget, max_evaluations=budget)
    t_nsga2 = perf_counter() - t0
    results["Standard NSGA-II"] = (res_nsga2, t_nsga2)
    print(f" Done ({t_nsga2:.2f}s)")

    # 3. Memetic NSGA-II
    print("--> 3/5: Running Memetic NSGA-II...", end="", flush=True)
    t0 = perf_counter()
    res_memetic = memetic_nsga2(problem, seed=seed, population_size=population_size, max_evaluations=budget)
    t_memetic = perf_counter() - t0
    results["Memetic NSGA-II"] = (res_memetic, t_memetic)
    print(f" Done ({t_memetic:.2f}s)")

    # 4. MOEA/D (Tchebycheff)
    print("--> 4/5: Running MOEA/D (Tchebycheff)...", end="", flush=True)
    t0 = perf_counter()
    res_moead = moead(problem, seed=seed, population_size=population_size, max_evaluations=budget, scalarization="tchebycheff")
    t_moead = perf_counter() - t0
    results["MOEA/D (Tchebycheff)"] = (res_moead, t_moead)
    print(f" Done ({t_moead:.2f}s)")

    # 5. AMOSA (Simulated Annealing)
    print("--> 5/5: Running AMOSA (Simulated Annealing)...", end="", flush=True)
    t0 = perf_counter()
    res_amosa = amosa(problem, seed=seed, population_size=population_size, max_evaluations=budget)
    t_amosa = perf_counter() - t0
    results["AMOSA"] = (res_amosa, t_amosa)
    print(f" Done ({t_amosa:.2f}s)\n")

    summary_table = []
    for name, (res, runtime) in results.items():
        objectives = [evaluate(problem, s).objectives for s in res.archive]
        normalized = [normalize(v, scales) for v in objectives]
        hv = hypervolume(normalized) if normalized else 0.0
        sp = spacing(normalized) if len(normalized) >= 2 else 0.0
        
        # Run TOPSIS
        topsis_res = topsis(objectives) if objectives else []
        top_score = topsis_res[0].score if topsis_res else 0.0
        top_obj = topsis_res[0].objectives if topsis_res else None

        summary_table.append({
            "Method": name,
            "Evaluations": res.evaluations,
            "Feasible": len(objectives) > 0,
            "Archive Size": len(objectives),
            "Hypervolume (HV)": round(hv, 6),
            "Spacing (Spread)": round(sp, 4) if sp else "-",
            "Runtime (s)": round(runtime, 2),
            "TOPSIS Compromise Obj": [round(x, 4) for x in top_obj] if top_obj else "-",
        })

    return summary_table


def main():
    parser = argparse.ArgumentParser(description="Multi-Algorithm Comparison Benchmark")
    parser.add_argument("--instance", default="data/demo.json", help="Path to problem JSON")
    parser.add_argument("--budget", type=int, default=240, help="Full evaluation budget")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed")
    parser.add_argument("--population", type=int, default=24, help="Population size")
    args = parser.parse_args()

    inst_path = Path(args.instance)
    if not inst_path.exists():
        print(f"Generating instance at {inst_path}...")
        problem, _ = generate_instance("small", seed=42)
        inst_path.parent.mkdir(parents=True, exist_ok=True)
        inst_path.write_text(json.dumps(problem_to_dict(problem), indent=2))
    else:
        problem = problem_from_dict(json.loads(inst_path.read_text()))

    table = run_benchmark(problem, seed=args.seed, budget=args.budget, population_size=args.population)

    # Print markdown table
    print("=" * 80)
    print("MULTI-OBJECTIVE OPTIMIZATION ALGORITHMIC BENCHMARK")
    print("=" * 80)
    header = f"{'Method':<25} | {'Feasible':<8} | {'Archive':<7} | {'Hypervolume':<12} | {'Runtime (s)':<11} | {'Compromise (Gaps, Room, SD)'}"
    print(header)
    print("-" * len(header))
    for row in table:
        comp_str = str(row['TOPSIS Compromise Obj'])
        print(f"{row['Method']:<25} | {str(row['Feasible']):<8} | {row['Archive Size']:<7} | {row['Hypervolume (HV)']:<12} | {row['Runtime (s)']:<11} | {comp_str}")
    print("=" * 80)


if __name__ == "__main__":
    main()

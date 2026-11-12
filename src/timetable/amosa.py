"""Archived Multi-Objective Simulated Annealing (AMOSA).

A trajectory-based metaheuristic for multi-objective optimization that uses a
cooling schedule and energy differences based on Pareto dominance.

Key Optimization Techniques (OT) Concepts:
------------------------------------------
1. Simulated Annealing for Multi-Objective Problems:
   In classical single-objective SA, worse solutions are accepted with probability
   P = exp(-Delta f / T). In multi-objective spaces, "worse" is defined through
   Pareto dominance. AMOSA defines energy differences based on the amount of
   dominance between the current solution, the proposed candidate, and the archive.

2. Archive-Guided Search:
   Maintains an external archive of non-dominated solutions discovered during the
   walk. When a candidate and the current solution are mutually non-dominating,
   the candidate is checked against the archive, directing search towards
   under-explored and promising Pareto regions.

3. Escaping Local Optima:
   High temperatures allow wide exploratory jumps across disjoint feasible
   regions; low temperatures focus the search on fine local refinement.
"""
from __future__ import annotations

import math
from math import isfinite
import random
from time import perf_counter
from typing import Callable, Sequence

from .evaluation import Evaluation, evaluate
from .feasible import FeasibleNeighborhood
from .greedy import construct
from .metrics import constraint_dominates, dominates, objective_scales
from .model import Problem, Schedule, validate_problem
from .nsga2 import Individual, SearchResult


def dominance_distance(
    a_objs: Sequence[float],
    b_objs: Sequence[float],
    scales: Sequence[float],
) -> float:
    """Normalized dominance distance measure between two objective vectors.
    
    Returns the average normalized shortfall across objectives where b is worse than a.
    """
    diffs = [max(0.0, (b - a) / s) for a, b, s in zip(a_objs, b_objs, scales)]
    return sum(diffs) / len(diffs)


def amosa(
    problem: Problem,
    seed: int = 0,
    population_size: int = 24,  # Kept for interface parity; used for initial archive seeding
    max_evaluations: int = 480,
    time_limit: float | None = None,
    t_max: float = 1.0,
    t_min: float = 0.001,
    alpha: float = 0.95,
    use_faculty_search: bool = True,
    evaluator: Callable[[Problem, Schedule], Evaluation] | None = None,
    faculty_every: int = 6,
    faculty_nodes: int = 12000,
    progress: dict | None = None,
) -> SearchResult:
    """Archived Multi-Objective Simulated Annealing.
    
    Parameters:
        problem: Target timetable problem instance.
        seed: Random seed.
        population_size: Number of initial exploratory seeds.
        max_evaluations: Full candidate evaluation budget.
        time_limit: Optional wall-clock second limit.
        t_max: Initial annealing temperature.
        t_min: Final cooling temperature.
        alpha: Geometric cooling parameter.
        use_faculty_search: Whether to periodically apply bounded faculty reassignment.
        evaluator: Counted objective evaluator.
    """
    validate_problem(problem)
    if type(max_evaluations) is not int or max_evaluations < 1:
        raise ValueError("max_evaluations must be a positive integer")
    if time_limit is not None and (not isfinite(time_limit) or time_limit <= 0):
        raise ValueError("time_limit must be finite and positive")
    if t_max <= t_min or t_min <= 0:
        raise ValueError("Temperatures must satisfy t_max > t_min > 0")

    evaluator = evaluate if evaluator is None else evaluator
    rng = random.Random(seed)
    started = perf_counter()
    deadline = started + time_limit if time_limit is not None else float("inf")
    neighborhood = FeasibleNeighborhood(problem)
    scales = objective_scales(problem)

    archive: list[Individual] = []
    history = []
    calls = feasible_calls = late_calls = initial_attempts = 0
    proposals = noops = restarts = faculty_calls = faculty_search_nodes = faculty_changes = 0
    accepted_moves = uphill_accepted = 0
    neighborhood_calls = final_noops = 0
    minimum_violation: int | None = None
    best: Individual | None = None
    seen: set[Schedule] = set()

    current_temp = t_max

    def remaining() -> bool:
        return calls < max_evaluations and perf_counter() < deadline

    def diagnostics() -> dict:
        return {
            "algorithm": "amosa",
            "temperature": current_temp,
            "archive_size": len(archive),
            "accepted_moves": accepted_moves,
            "uphill_accepted": uphill_accepted,
            "variation_proposals": proposals,
            "faculty_search_calls": faculty_calls,
            "faculty_search_nodes": faculty_search_nodes,
            "faculty_changes": faculty_changes,
        }

    def counted(schedule: Schedule) -> Individual | None:
        nonlocal calls, feasible_calls, late_calls, minimum_violation, best
        if not remaining():
            return None
        ev = evaluator(problem, schedule)
        calls += 1
        candidate = Individual(schedule, ev)
        if perf_counter() > deadline:
            late_calls += 1
            return None
        seen.add(schedule)
        minimum_violation = ev.violation if minimum_violation is None else min(minimum_violation, ev.violation)
        if best is None or constraint_dominates(ev.objectives, best.evaluation.objectives, ev.violation, best.evaluation.violation):
            best = candidate
        if ev.feasible:
            feasible_calls += 1
            if not any(old.evaluation.objectives == ev.objectives or dominates(old.evaluation.objectives, ev.objectives)
                       for old in archive):
                archive[:] = [old for old in archive if not dominates(ev.objectives, old.evaluation.objectives)]
                archive.append(candidate)
        if progress is not None:
            progress.update(diagnostics())
        return candidate

    # 1. Initialize feasible starting point and seed archive
    current: Individual | None = None
    init_target = min(population_size, max(2, max_evaluations // 10))
    while len(archive) < init_target and remaining() and initial_attempts < 4 * init_target:
        schedule = construct(problem, rng, randomized=initial_attempts > 0)
        initial_attempts += 1
        cand = counted(schedule)
        if cand is not None and cand.evaluation.feasible:
            if current is None:
                current = cand

    if current is None and archive:
        current = archive[0]
    elif current is not None and not current.evaluation.feasible:
        current = archive[0] if archive else None

    history.append({
        "generation": 0,
        "evaluations": calls,
        "elapsed": perf_counter() - started,
        "temperature": current_temp,
        "feasible_fraction": 1.0 if archive else 0.0,
        "evaluated_feasible_fraction": feasible_calls / calls if calls else 0.0,
        "min_violation": minimum_violation,
        "front": [list(x.evaluation.objectives) for x in archive],
    })

    # 2. Main AMOSA Annealing Loop
    step = 0
    last_archive_size = len(archive)
    while remaining() and current is not None and current.evaluation.feasible:
        step += 1
        # Adaptive temperature decay: maintains exploratory probability, then anneals
        frac = min(1.0, calls / max_evaluations)
        current_temp = max(t_min, t_max * ((t_min / t_max) ** (frac ** 1.25)))

        # Periodic restart from archive point to explore diverse Pareto regions
        if proposals % 25 == 0 and archive:
            current = rng.choice(archive)

        proposals += 1
        # Trigger faculty integer search periodically or whenever workload variance is elevated
        if use_faculty_search and (proposals % faculty_every == 0 or (current.evaluation.objectives[2] > 0.04 and proposals % 7 == 0)):
            from .faculty_search import faculty_reassign
            fac_diag = {}
            child_schedule = faculty_reassign(
                problem, current.schedule, rng, max_offerings=8,
                max_nodes=faculty_nodes, diagnostics=fac_diag
            )
            faculty_calls += 1
            faculty_search_nodes += fac_diag.get("nodes", 0)
            faculty_changes += child_schedule != current.schedule
        elif proposals % 41 == 0:
            child_schedule = construct(problem, rng, randomized=True)
            restarts += 1
        else:
            child_schedule = neighborhood.propose(current.schedule, rng)
            neighborhood_calls += 1

        if child_schedule == current.schedule:
            noops += 1
            child_schedule = neighborhood.propose(current.schedule, rng)
            neighborhood_calls += 1
        final_noops += child_schedule == current.schedule

        child = counted(child_schedule)
        if child is None:
            break

        # Acceptance logic
        if child.evaluation.feasible:
            curr_objs = current.evaluation.objectives
            child_objs = child.evaluation.objectives

            # Case A: child dominates current
            if dominates(child_objs, curr_objs):
                current = child
                accepted_moves += 1
            # Case B: current dominates child (uphill move)
            elif dominates(curr_objs, child_objs):
                delta = dominance_distance(curr_objs, child_objs, scales)
                prob = math.exp(-max(1e-6, delta) / max(1e-6, current_temp))
                if rng.random() < prob:
                    current = child
                    accepted_moves += 1
                    uphill_accepted += 1
            # Case C: current and child are mutually non-dominating
            else:
                # Check against archive
                dominating_arch = [a for a in archive if dominates(a.evaluation.objectives, child_objs)]
                if dominating_arch:
                    avg_delta = sum(dominance_distance(a.evaluation.objectives, child_objs, scales)
                                    for a in dominating_arch) / len(dominating_arch)
                    prob = math.exp(-max(1e-6, avg_delta) / max(1e-6, current_temp))
                    if rng.random() < prob:
                        current = child
                        accepted_moves += 1
                        uphill_accepted += 1
                else:
                    # Child is non-dominated by archive or dominates some points
                    current = child
                    accepted_moves += 1

        if step % 8 == 0 or len(archive) > last_archive_size:
            last_archive_size = len(archive)
            history.append({
                "generation": step,
                "evaluations": calls,
                "elapsed": perf_counter() - started,
                "temperature": current_temp,
                "feasible_fraction": 1.0,
                "evaluated_feasible_fraction": feasible_calls / calls if calls else 0.0,
                "min_violation": minimum_violation,
                "front": [list(x.evaluation.objectives) for x in archive],
            })

    metadata = diagnostics()
    metadata.update({
        "evaluated_feasible": feasible_calls,
        "minimum_violation": minimum_violation if minimum_violation is not None else 0,
        "calls": calls,
        "budget": max_evaluations,
    })
    best_sched = archive[0].schedule if archive else (best.schedule if best else None)
    return SearchResult(
        archive=[x.schedule for x in archive],
        history=history,
        evaluations=calls,
        runtime=perf_counter() - started,
        metadata=metadata,
        best_schedule=best_sched,
        population=[x.schedule for x in archive[:population_size]],
    )

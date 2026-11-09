"""Feasible-domain memetic NSGA-II with a matched scalar-local-search ablation.

The original NSGA-II comparator stays unchanged. This variant uses genuinely
rank/crowding-selected parents and elitist parent/offspring survival, but replaces
destructive independent gene crossover with feasibility-preserving mutation and
bounded offering-level faculty intensification. Mutation-only variation is an
explicit design choice; no crossover benefit is claimed.

Every completed candidate goes through the common counted evaluator. Partial
checks and integer load search are timed and separately recorded; equal numbers
of full evaluations are not asserted to mean equal computation.
"""
from __future__ import annotations

from math import isfinite
import random
from time import perf_counter
from typing import Callable

from .evaluation import Evaluation, evaluate
from .feasible import FeasibleNeighborhood
from .greedy import construct
from .metrics import constraint_dominates, dominates, objective_scales
from .model import Problem, Schedule, validate_problem
from .nsga2 import Individual, SearchResult, environmental_selection, rank_and_crowding


def memetic_nsga2(
    problem: Problem,
    seed: int = 0,
    population_size: int = 24,
    max_evaluations: int = 480,
    time_limit: float | None = None,
    selection: str = "nsga2",
    use_faculty_search: bool = True,
    evaluator: Callable[[Problem, Schedule], Evaluation] | None = None,
    faculty_every: int = 6,
    faculty_nodes: int = 12000,
    progress: dict | None = None,
) -> SearchResult:
    """Search without using any planted schedule or changing an objective.

    ``selection='scalar_local'`` removes the NSGA-II selection/survival bundle:
    equally initialized trajectories accept improvements in fixed, independently
    sampled positive scalar directions. Both variants archive all evaluated
    feasible proposals, including proposals rejected by population acceptance.

    Resource limits are checked between bounded operations. A last operation can
    overrun a wall deadline; late completed evaluations are charged but excluded
    from the reported in-time archive. Comparison observers can additionally
    interrupt at evaluation boundaries, retaining their own complete history.
    """
    validate_problem(problem)
    if type(population_size) is not int or population_size < 2:
        raise ValueError("population_size must be an integer >=2")
    if type(max_evaluations) is not int or max_evaluations < 1:
        raise ValueError("max_evaluations must be a positive integer")
    if time_limit is not None and (not isfinite(time_limit) or time_limit <= 0):
        raise ValueError("time_limit must be finite and positive")
    if selection not in {"nsga2", "scalar_local"}:
        raise ValueError("selection must be nsga2 or scalar_local")
    if type(faculty_every) is not int or faculty_every < 1 or type(faculty_nodes) is not int or faculty_nodes < 1:
        raise ValueError("Faculty-search intervals and node limits must be positive integers")
    evaluator = evaluate if evaluator is None else evaluator
    rng = random.Random(seed)
    started = perf_counter()
    deadline = started + time_limit if time_limit is not None else float("inf")
    neighborhood = FeasibleNeighborhood(problem)
    archive: list[Individual] = []
    population: list[Individual] = []
    history = []
    calls = feasible_calls = late_calls = initial_attempts = 0
    proposals = noops = restarts = faculty_calls = faculty_search_nodes = faculty_changes = 0
    offspring_feasible = offspring_evaluated = 0
    accepted_local = 0
    neighborhood_calls = final_noops = 0
    minimum_violation: int | None = None
    best: Individual | None = None
    seen: set[Schedule] = set()
    unique_feasible: set[Schedule] = set()

    def remaining() -> bool:
        return calls < max_evaluations and perf_counter() < deadline

    def diagnostics() -> dict:
        return {"algorithm": "feasible_memetic_nsga2" if selection == "nsga2" else "feasible_scalar_local_search",
                "selection": selection, "use_faculty_search": use_faculty_search,
                "faculty_every": faculty_every, "faculty_nodes": faculty_nodes,
                "initial_attempts": initial_attempts, "initial_feasible_population": min(len(population), population_size),
                "variation_proposals": proposals, "no_op_first_attempts": noops,
                "final_noop_proposals": final_noops, "neighborhood_calls": neighborhood_calls,
                "restarts": restarts, "offspring_evaluated": offspring_evaluated,
                "offspring_feasible": offspring_feasible, "faculty_search_calls": faculty_calls,
                "faculty_search_nodes": faculty_search_nodes, "faculty_changes": faculty_changes,
                "scalar_local_accepts": accepted_local,
                "crossover": "disabled; feasibility-preserving mutation only"}

    def counted(schedule: Schedule) -> Individual | None:
        nonlocal calls, feasible_calls, late_calls, minimum_violation, best
        try:
            if not remaining():
                return None
            ev = evaluator(problem, schedule)
        finally:
            # A serial experiment observer may terminate at this boundary. Its
            # partial record still retains all completed bounded-search effort.
            if progress is not None:
                progress.update(diagnostics())
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
            unique_feasible.add(schedule)
            if not any(old.evaluation.objectives == ev.objectives or dominates(old.evaluation.objectives, ev.objectives)
                       for old in archive):
                archive[:] = [old for old in archive if not dominates(ev.objectives, old.evaluation.objectives)]
                archive.append(candidate)
        return candidate

    def record(generation: int) -> None:
        history.append({"generation": generation, "evaluations": calls, "elapsed": perf_counter()-started,
                        "feasible_fraction": sum(x.evaluation.feasible for x in population) / len(population) if population else 0,
                        "evaluated_feasible_fraction": feasible_calls / calls if calls else 0,
                        "min_violation": minimum_violation,
                        "front": [list(x.evaluation.objectives) for x in archive]})

    # Identical seeded constructors/RNG prefix to the multi-start greedy
    # comparator, with every successful and failed initial attempt charged.
    while len(population) < population_size and remaining() and initial_attempts < 4*population_size:
        schedule = construct(problem, rng, randomized=initial_attempts > 0)
        initial_attempts += 1
        candidate = counted(schedule)
        if candidate is not None and candidate.evaluation.feasible:
            population.append(candidate)
    record(0)
    scales = objective_scales(problem)
    # Draw directions after construction so both selection policies receive
    # exactly the same initial schedules for a given problem/seed.
    directions = [tuple(rng.expovariate(1.0) for _ in range(3)) for _ in population]
    generation = 0
    while len(population) >= 2 and remaining():
        generation += 1
        ranks, distances = rank_and_crowding(population) if selection == "nsga2" else ({}, {})
        children: list[Individual] = []
        for _ in range(len(population)):
            if not remaining():
                break
            if selection == "nsga2":
                a, b = rng.randrange(len(population)), rng.randrange(len(population))
                key_a, key_b = (ranks[a], -distances[a]), (ranks[b], -distances[b])
                parent_index = a if key_a < key_b or (key_a == key_b and rng.random() < .5) else b
            else:
                parent_index = rng.randrange(len(population))
            parent = population[parent_index]
            proposals += 1
            if use_faculty_search and proposals % faculty_every == 0:
                from .faculty_search import faculty_reassign
                faculty_diagnostics = {}
                schedule = faculty_reassign(problem, parent.schedule, rng, max_offerings=8,
                                            max_nodes=faculty_nodes, diagnostics=faculty_diagnostics)
                faculty_calls += 1
                faculty_search_nodes += faculty_diagnostics.get("nodes", 0)
                faculty_changes += schedule != parent.schedule
            elif proposals % 31 == 0:
                schedule = construct(problem, rng, randomized=True)
                restarts += 1
            else:
                schedule = neighborhood.propose(parent.schedule, rng)
                neighborhood_calls += 1
            if schedule == parent.schedule:
                noops += 1
                # Try another bounded neighborhood before charging a no-op.
                # If both attempts fail, retaining the evaluated duplicate is
                # honest and prevents an infinite free-evaluation search loop.
                schedule = neighborhood.propose(parent.schedule, rng)
                neighborhood_calls += 1
            final_noops += schedule == parent.schedule
            child = counted(schedule)
            if child is None:
                break
            offspring_evaluated += 1
            offspring_feasible += child.evaluation.feasible
            if selection == "nsga2":
                children.append(child)
            elif child.evaluation.feasible:
                direction = directions[parent_index]
                def scalar(x):
                    return sum(w*f/s for w,f,s in zip(direction, x.evaluation.objectives, scales))
                if scalar(child) < scalar(parent):
                    population[parent_index] = child
                    accepted_local += 1
        if selection == "nsga2":
            population = environmental_selection(population+children, len(population), rng)
        record(generation)
    record(generation) if history[-1]["evaluations"] != calls else None
    ordered = sorted(archive, key=lambda x: x.evaluation.objectives)
    elapsed = perf_counter()-started
    return SearchResult(
        [x.schedule for x in ordered], history, calls, elapsed,
        {**diagnostics(),
         "seed": seed, "population_size": population_size, "selection": selection,
         "budget": max_evaluations, "time_limit": time_limit,
         "initial_attempts": initial_attempts, "seeded_candidates": len(directions),
         "generations_completed": generation, "evaluated_feasible": feasible_calls,
         "minimum_violation": minimum_violation, "unique_evaluated_schedules": len(seen),
         "unique_feasible_schedules": len(unique_feasible), "late_evaluations": late_calls,
         "variation_proposals": proposals, "no_op_first_attempts": noops,
         "restarts": restarts, "offspring_evaluated": offspring_evaluated,
         "offspring_feasible": offspring_feasible,
         "faculty_search_calls": faculty_calls, "faculty_search_nodes": faculty_search_nodes,
         "faculty_changes": faculty_changes, "scalar_local_accepts": accepted_local,
         "crossover": "disabled; feasibility-preserving mutation only",
         "stop_reason": "evaluation_cap" if calls >= max_evaluations else
                        "wall_time" if perf_counter() >= deadline else "initialization_failure",
         "wall_time_overrun": max(0.0, elapsed-time_limit) if time_limit is not None else 0.0,
         "construction_checks_counted_as_objective_evaluations": False},
        ordered[0].schedule if ordered else best.schedule if best else None,
        [x.schedule for x in population],
    )

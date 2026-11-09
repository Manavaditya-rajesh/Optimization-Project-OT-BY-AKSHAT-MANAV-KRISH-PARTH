"""Transparent constrained NSGA-II with optional domain enhancements.

The plain algorithm uses independent domain-valid random chromosomes, whole-
offering crossover, categorical mutation, Deb's constraint-domination rule,
binary tournaments, crowding distance and elitist parent/offspring selection.
The enhanced algorithm additionally seeds from randomized greedy constructions,
repairs infeasible offspring, and uses a short feasible local search. No planted
feasibility witness is accepted or consulted by this module.

Evaluation budgets count *every* full call to the shared objective/constraint
calculator, including initialization, failed repairs and local-search proposals.
Constructive resource checks are not objective evaluations; their runtime is
included. Consequently equal evaluation budgets are not equal wall-clock costs.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from .evaluation import Evaluation, evaluate
from .model import Placement, Problem, Schedule, compatible_rooms, valid_starts, validate_problem
from .hybrid import HybridOperators


@dataclass
class Individual:
    schedule: Schedule
    evaluation: Evaluation


@dataclass
class SearchResult:
    archive: list[Schedule]
    history: list[dict[str, Any]]
    evaluations: int
    runtime: float
    metadata: dict[str, Any] = field(default_factory=dict)
    best_schedule: Schedule | None = None
    population: list[Schedule] = field(default_factory=list)


def objective_dominates(a: Sequence[float], b: Sequence[float]) -> bool:
    """Strict Pareto dominance for minimization; equal vectors do not dominate."""
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def constrained_dominates(a: Evaluation, b: Evaluation) -> bool:
    """Deb rule: feasible first; among infeasible candidates use violation only."""
    if a.violation != b.violation and (a.violation or b.violation):
        return a.violation < b.violation
    return a.violation == 0 and objective_dominates(a.objectives, b.objectives)


def non_dominated_sort(evaluations: Sequence[Evaluation]) -> list[list[int]]:
    """Fast non-dominated sorting, O(M N^2), with constrained dominance."""
    successors: list[list[int]] = [[] for _ in evaluations]
    predecessors = [0] * len(evaluations)
    for i in range(len(evaluations)):
        for j in range(i + 1, len(evaluations)):
            if constrained_dominates(evaluations[i], evaluations[j]):
                successors[i].append(j)
                predecessors[j] += 1
            elif constrained_dominates(evaluations[j], evaluations[i]):
                successors[j].append(i)
                predecessors[i] += 1
    current = [i for i, count in enumerate(predecessors) if count == 0]
    fronts: list[list[int]] = []
    while current:
        fronts.append(current)
        following: list[int] = []
        for i in current:
            for j in successors[i]:
                predecessors[j] -= 1
                if predecessors[j] == 0:
                    following.append(j)
        current = following
    return fronts


def crowding_distance(evaluations: Sequence[Evaluation], front: Sequence[int]) -> dict[int, float]:
    """Normalized objective-wise crowding; constant objectives add no distance.

    Equal objective vectors receive no artificial boundary advantage on a
    constant axis. Ties on nonconstant axes are stable and deterministic.
    """
    distances = {i: 0.0 for i in front}
    if len(front) <= 2:
        return {i: math.inf for i in front}
    for objective in range(3):
        ordered = sorted(front, key=lambda i: evaluations[i].objectives[objective])
        low = evaluations[ordered[0]].objectives[objective]
        high = evaluations[ordered[-1]].objectives[objective]
        if high == low:
            continue
        distances[ordered[0]] = distances[ordered[-1]] = math.inf
        for position in range(1, len(ordered) - 1):
            before = evaluations[ordered[position - 1]].objectives[objective]
            after = evaluations[ordered[position + 1]].objectives[objective]
            distances[ordered[position]] += (after - before) / (high - low)
    return distances


def rank_and_crowding(population: Sequence[Individual]) -> tuple[dict[int, int], dict[int, float]]:
    evaluations = [individual.evaluation for individual in population]
    rank: dict[int, int] = {}
    crowd: dict[int, float] = {}
    for level, front in enumerate(non_dominated_sort(evaluations)):
        rank.update((i, level) for i in front)
        crowd.update(crowding_distance(evaluations, front))
    return rank, crowd


def environmental_selection(population: Sequence[Individual], size: int, rng: random.Random) -> list[Individual]:
    evaluations = [individual.evaluation for individual in population]
    selected: list[Individual] = []
    for front in non_dominated_sort(evaluations):
        if len(selected) + len(front) <= size:
            selected.extend(population[i] for i in front)
        else:
            distances = crowding_distance(evaluations, front)
            # Shuffle equal-distance candidates to avoid persistent index bias.
            ordered = list(front)
            rng.shuffle(ordered)
            ordered.sort(key=lambda i: distances[i], reverse=True)
            selected.extend(population[i] for i in ordered[:size - len(selected)])
            break
    return selected


class _BudgetExhausted(Exception):
    pass


class _Evaluator:
    def __init__(self, problem: Problem, budget: int):
        self.problem = problem
        self.budget = budget
        self.calls = 0
        self.feasible_calls = 0
        self.archive: list[Individual] = []
        self.best: Individual | None = None

    @property
    def remaining(self) -> int:
        return self.budget - self.calls

    def __call__(self, schedule: Schedule) -> Individual:
        if self.calls >= self.budget:
            raise _BudgetExhausted
        individual = Individual(schedule, evaluate(self.problem, schedule))
        self.calls += 1
        ev = individual.evaluation
        if self.best is None or constrained_dominates(ev, self.best.evaluation):
            self.best = individual
        if ev.feasible:
            self.feasible_calls += 1
            if not any(
                old.evaluation.objectives == ev.objectives
                or objective_dominates(old.evaluation.objectives, ev.objectives)
                for old in self.archive
            ):
                self.archive = [old for old in self.archive if not objective_dominates(ev.objectives, old.evaluation.objectives)]
                self.archive.append(individual)
        return individual


class _Domains:
    def __init__(self, problem: Problem):
        self.problem = problem
        self.starts = [valid_starts(problem, event) for event in problem.events]
        self.rooms = [compatible_rooms(problem, event) for event in problem.events]
        offering_index = {offering.id: i for i, offering in enumerate(problem.offerings)}
        self.event_offerings = [offering_index[event.offering_id] for event in problem.events]
        self.offering_events: list[list[int]] = [[] for _ in problem.offerings]
        for event_index, offering in enumerate(self.event_offerings):
            self.offering_events[offering].append(event_index)

    def random_schedule(self, rng: random.Random) -> Schedule:
        placements = tuple(
            Placement(rng.choice(starts), rng.choice(rooms)) if starts and rooms else None
            for starts, rooms in zip(self.starts, self.rooms)
        )
        teachers = tuple(rng.choice(offering.eligible_faculty) if offering.eligible_faculty else "" for offering in self.problem.offerings)
        return Schedule(placements, teachers)

    def crossover(self, a: Schedule, b: Schedule, rng: random.Random) -> Schedule:
        choices = [rng.random() < 0.5 for _ in self.problem.offerings]
        teachers = tuple((a.teachers if choice else b.teachers)[i] for i, choice in enumerate(choices))
        placements = tuple((a.placements if choices[self.event_offerings[i]] else b.placements)[i] for i in range(len(self.problem.events)))
        return Schedule(placements, teachers)

    def mutate(self, schedule: Schedule, rng: random.Random) -> Schedule:
        placements = list(schedule.placements)
        teachers = list(schedule.teachers)
        if not placements:
            return schedule
        # Expected O(1) event edits rather than destroying an entire timetable.
        for _ in range(1 + int(rng.random() < 0.2)):
            kind = rng.randrange(4)
            i = rng.randrange(len(placements))
            place = placements[i]
            if kind == 0 and self.starts[i] and self.rooms[i]:
                placements[i] = Placement(rng.choice(self.starts[i]), place.room if place else rng.choice(self.rooms[i]))
            elif kind == 1 and self.rooms[i] and place:
                placements[i] = Placement(place.start, rng.choice(self.rooms[i]))
            elif kind == 2 and len(placements) > 1:
                j = rng.randrange(len(placements))
                other = placements[j]
                if place and other and other.start in self.starts[i] and place.start in self.starts[j]:
                    placements[i] = Placement(other.start, place.room)
                    placements[j] = Placement(place.start, other.room)
            else:
                k = self.event_offerings[i]
                eligible = self.problem.offerings[k].eligible_faculty
                if eligible:
                    teachers[k] = rng.choice(eligible)
        return Schedule(tuple(placements), tuple(teachers))



def nsga2(
    problem: Problem,
    seed: int = 0,
    population_size: int = 40,
    generations: int = 40,
    enhanced: bool = False,
    max_evaluations: int | None = None,
    seed_fraction: float = 0.5,
    intelligent_initialization: bool | None = None,
    repair: bool | None = None,
    local_search: bool | None = None,
    local_steps: int = 2,
    crossover_probability: float = 0.9,
) -> SearchResult:
    """Run plain or enhanced NSGA-II, returning only feasible archive solutions.

    ``enhanced`` selects all additions; individual switches support ablations.
    ``seed_fraction=0`` disables constructive initialization even when enhanced.
    A supplied budget is a hard cap, never exceeded, and must allow initialization.
    No infeasible candidate is exposed as a valid member of ``archive``.
    """
    validate_problem(problem)
    if population_size < 2 or generations < 0:
        raise ValueError("population_size must be >=2 and generations >=0")
    if not 0 <= seed_fraction <= 1 or not 0 <= crossover_probability <= 1 or local_steps < 0:
        raise ValueError("invalid seeding/crossover fraction or local_steps")
    do_repair = enhanced if repair is None else repair
    do_local = enhanced if local_search is None else local_search
    # Default plain is genuinely independent random initialization. The explicit
    # switch allows seeding-only or repair-only ablations without hidden coupling.
    do_seed = enhanced if intelligent_initialization is None else intelligent_initialization
    budget = max_evaluations if max_evaluations is not None else population_size * (generations + 1)
    if budget < population_size:
        raise ValueError("max_evaluations must be >= population_size")
    rng = random.Random(seed)
    started = time.perf_counter()
    counter = _Evaluator(problem, budget)
    domains = _Domains(problem)
    hybrid = HybridOperators(problem) if do_repair or do_local else None
    population: list[Individual] = []
    seeded = round(population_size * seed_fraction) if do_seed else 0
    repairs = 0
    local_proposals = 0
    local_accepts = 0
    construct = None
    if seeded or do_repair:
        from .greedy import construct
    for i in range(population_size):
        if i < seeded:
            assert construct is not None
            candidate = construct(problem, rng, randomized=True)
        else:
            candidate = domains.random_schedule(rng)
        population.append(counter(candidate))

    history: list[dict[str, Any]] = []

    def record(generation: int) -> None:
        history.append({
            "generation": generation,
            "evaluations": counter.calls,
            "feasible_fraction": sum(ind.evaluation.feasible for ind in population) / len(population),
            "evaluated_feasible_fraction": counter.feasible_calls / counter.calls,
            "min_violation": min(ind.evaluation.violation for ind in population),
            "front": [list(ind.evaluation.objectives) for ind in counter.archive],
        })

    record(0)
    for generation in range(1, generations + 1):
        if not counter.remaining:
            break
        ranks, distances = rank_and_crowding(population)

        def tournament() -> Schedule:
            a, b = rng.randrange(len(population)), rng.randrange(len(population))
            key_a, key_b = (ranks[a], -distances[a]), (ranks[b], -distances[b])
            winner = a if key_a < key_b or (key_a == key_b and rng.random() < 0.5) else b
            return population[winner].schedule

        offspring: list[Individual] = []
        for _ in range(population_size):
            if not counter.remaining:
                break
            first = tournament()
            child = domains.crossover(first, tournament(), rng) if rng.random() < crossover_probability else first
            child = domains.mutate(child, rng)
            individual = counter(child)
            if do_repair and not individual.evaluation.feasible and counter.remaining:
                assert hybrid is not None
                individual = hybrid.repair(individual, counter, rng)
                repairs += 1
            if do_local and individual.evaluation.feasible:
                assert hybrid is not None
                individual, proposals, accepts = hybrid.local_search(
                    individual, counter, rng, local_steps, lambda: bool(counter.remaining),
                )
                local_proposals += proposals
                local_accepts += accepts
            offspring.append(individual)
        population = environmental_selection(population + offspring, population_size, rng)
        record(generation)
    archive = sorted(counter.archive, key=lambda ind: ind.evaluation.objectives)
    return SearchResult(
        archive=[ind.schedule for ind in archive],
        history=history,
        evaluations=counter.calls,
        runtime=time.perf_counter() - started,
        metadata={
            "algorithm": "enhanced_nsga2" if enhanced else "nsga2",
            "seed": seed, "population_size": population_size,
            "generations_requested": generations, "generations_completed": len(history) - 1,
            "budget": budget, "seeded_candidates": seeded,
            "intelligent_initialization": do_seed,
            "repair_enabled": do_repair, "repairs": repairs,
            "local_search_enabled": do_local, "local_steps": local_steps,
            "local_proposals": local_proposals, "local_accepts": local_accepts,
            "evaluated_feasible": counter.feasible_calls,
            "minimum_violation": min(ind.evaluation.violation for ind in population),
            "construction_checks_counted_as_objective_evaluations": False,
        },
        best_schedule=archive[0].schedule if archive else (counter.best.schedule if counter.best else None),
        population=[ind.schedule for ind in population],
    )

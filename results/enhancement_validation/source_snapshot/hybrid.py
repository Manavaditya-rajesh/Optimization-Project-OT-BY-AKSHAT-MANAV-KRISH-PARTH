"""Domain enhancements kept separate from the standard NSGA-II machinery.

Construction repair preserves preferred genes when feasible. Local search uses
compaction, fitting-room, single-faculty and whole-offering teacher-exchange
neighborhoods. Every proposal evaluated here goes through the caller's counted
shared evaluator. No hidden certificate or separate objective calculation is
used to accept an infeasible schedule.
"""
from __future__ import annotations

import math
import random
from typing import Callable, Protocol, TypeVar

from .evaluation import Evaluation
from .metrics import constraint_dominates, objective_scales
from .model import Placement, Problem, Schedule, compatible_rooms, valid_starts


class EvaluatedCandidate(Protocol):
    schedule: Schedule
    evaluation: Evaluation


Candidate = TypeVar("Candidate", bound=EvaluatedCandidate)


class HybridOperators:
    """Precomputed domains and bounded, evaluation-budget-aware enhancements."""

    def __init__(self, problem: Problem):
        self.problem = problem
        self.starts = [valid_starts(problem, event) for event in problem.events]
        self.rooms = [compatible_rooms(problem, event) for event in problem.events]
        offering_index = {offering.id: i for i, offering in enumerate(problem.offerings)}
        self.event_offerings = [offering_index[event.offering_id] for event in problem.events]
        self.room_map = {room.id: room for room in problem.rooms}
        self.faculty_map = {faculty.id: faculty for faculty in problem.faculty}
        self.scale = objective_scales(problem)

    def repair(
        self, individual: Candidate, evaluate_candidate: Callable[[Schedule], Candidate],
        rng: random.Random,
    ) -> Candidate:
        """Reconstruct with inheritance preferences, then apply the Deb rule.

        ``construct`` performs direct resource checks while rebuilding complete
        offerings. The result is independently checked here through the counted
        evaluator; a failed repair remains explicitly infeasible. Equal positive
        violations are broken randomly rather than by a penalty-weight objective.
        """
        from .greedy import construct
        schedule = construct(self.problem, rng, preferred=individual.schedule, randomized=True)
        repaired = evaluate_candidate(schedule)
        a, b = repaired.evaluation, individual.evaluation
        if constraint_dominates(a.objectives, b.objectives, a.violation, b.violation) or (
            a.violation == b.violation and rng.random() < 0.5
        ):
            return repaired
        return individual

    def local_proposal(self, schedule: Schedule, rng: random.Random, mode: int) -> Schedule:
        """Propose one of four neighborhoods, with a shared final feasibility check.

        Mode 3 swaps faculty genes of two whole offerings if both cross-
        qualifications hold. It can improve balance when moving one offering
        alone would overshoot the desirable workload or violate a weekly limit.
        """
        problem = self.problem
        if not problem.events:
            return schedule
        placements = list(schedule.placements)
        teachers = list(schedule.teachers)
        i = rng.randrange(len(placements))
        place = placements[i]
        if place is None:
            return schedule
        event = problem.events[i]
        mode %= 4
        if mode == 0:
            neighbors = [j for j, other in enumerate(problem.events)
                         if j != i and set(event.groups).intersection(other.groups)
                         and placements[j] is not None]
            if neighbors:
                j = rng.choice(neighbors)
                neighbor = placements[j]
                assert neighbor is not None
                proposed = (neighbor.start + problem.events[j].duration if rng.random() < 0.5
                            else neighbor.start - event.duration)
                if proposed in self.starts[i]:
                    placements[i] = Placement(proposed, place.room)
        elif mode == 1:
            alternatives = sorted(self.rooms[i], key=lambda room: (self.room_map[room].capacity, room))
            if alternatives:
                room = alternatives[min(len(alternatives) - 1, int(rng.random() < 0.15))]
                placements[i] = Placement(place.start, room)
        else:
            k = self.event_offerings[i]
            offering = problem.offerings[k]
            loads = {faculty.id: 0 for faculty in problem.faculty}
            for offering_index, other in enumerate(problem.offerings):
                teacher = teachers[offering_index]
                if teacher in loads:
                    loads[teacher] += other.duration * other.sessions
            if mode == 2:
                old = teachers[k]
                if old in loads:
                    loads[old] -= offering.duration * offering.sessions
                eligible = list(offering.eligible_faculty)
                rng.shuffle(eligible)
                eligible.sort(key=lambda faculty: (loads[faculty] + offering.duration * offering.sessions)
                              / self.faculty_map[faculty].max_weekly)
                if eligible:
                    teachers[k] = eligible[0]
            else:
                # Compare the exact normalized-load SD of cross-qualified swaps.
                # This score only chooses a proposal. Full objective acceptance
                # below also considers gaps and enforces every hard constraint.
                first_teacher = teachers[k]
                first_hours = offering.duration * offering.sessions
                alternatives: list[tuple[float, int]] = []
                for other_index, other in enumerate(problem.offerings):
                    second_teacher = teachers[other_index]
                    if other_index == k or first_teacher == second_teacher:
                        continue
                    if second_teacher not in offering.eligible_faculty or first_teacher not in other.eligible_faculty:
                        continue
                    second_hours = other.duration * other.sessions
                    next_first = loads[first_teacher] - first_hours + second_hours
                    next_second = loads[second_teacher] - second_hours + first_hours
                    if (next_first > self.faculty_map[first_teacher].max_weekly
                            or next_second > self.faculty_map[second_teacher].max_weekly):
                        continue
                    ratios = [(next_first if faculty.id == first_teacher else
                               next_second if faculty.id == second_teacher else loads[faculty.id]) / faculty.max_weekly
                              for faculty in problem.faculty]
                    average = sum(ratios) / len(ratios) if ratios else 0.0
                    sd = math.sqrt(sum((ratio - average) ** 2 for ratio in ratios) / len(ratios)) if ratios else 0.0
                    alternatives.append((sd, other_index))
                if alternatives:
                    rng.shuffle(alternatives)
                    alternatives.sort(key=lambda item: item[0])
                    other_index = alternatives[0][1]
                    teachers[k], teachers[other_index] = teachers[other_index], teachers[k]
        return Schedule(tuple(placements), tuple(teachers))

    def local_search(
        self, individual: Candidate, evaluate_candidate: Callable[[Schedule], Candidate],
        rng: random.Random, steps: int, remaining: Callable[[], bool],
    ) -> tuple[Candidate, int, int]:
        """Accept feasible improvements in a random positive scalar direction.

        This does not replace Pareto survival: each child has fresh directions,
        and every feasible proposal enters the external non-dominated archive
        through ``evaluate_candidate``, including locally rejected alternatives.
        """
        weights = [rng.expovariate(1.0) for _ in range(3)]

        def scalar(ev: Evaluation) -> float:
            return sum(weight * value / scale for weight, value, scale
                       in zip(weights, ev.objectives, self.scale))

        proposals = accepted = 0
        for step in range(steps):
            if not remaining():
                break
            proposed = self.local_proposal(individual.schedule, rng, step + rng.randrange(4))
            if proposed == individual.schedule:
                continue
            neighbor = evaluate_candidate(proposed)
            proposals += 1
            if neighbor.evaluation.feasible and scalar(neighbor.evaluation) < scalar(individual.evaluation):
                individual = neighbor
                accepted += 1
        return individual, proposals, accepted

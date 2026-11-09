"""Optional CP-SAT reference with exact feasibility and single-objective models.

CP-SAT proves a *single-objective* optimum only when its status is OPTIMAL.
These runs do not certify the complete three-objective Pareto front.  In
particular, normalized workload standard deviation is deliberately not replaced
by a surrogate and then described as an exact objective.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from math import isfinite, lcm
from itertools import product
from time import perf_counter
from typing import Any

from .model import (
    Placement,
    Problem,
    Schedule,
    compatible_rooms,
    valid_starts,
    validate_problem,
)


@dataclass
class ExactResult:
    schedule: Schedule | None
    status: str
    objective_value: float | None
    best_bound: float | None
    runtime: float
    objective: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def proven_optimal(self) -> bool:
        """Whether CP-SAT completed an optimality proof for the chosen objective."""
        return self.status == "OPTIMAL"


@dataclass
class EnumerationResult:
    """A complete, globally non-dominated front for a deliberately tiny model."""

    archive: list[Schedule]
    objectives: list[tuple[float, float, float]]
    evaluated: int
    feasible_candidates: int
    runtime: float
    status: str = "COMPLETE"


def enumerate_pareto(problem: Problem, max_combinations: int = 100_000) -> EnumerationResult:
    """Exhaust all structurally valid genotypes and certify a tiny Pareto front.

    This reference needs no solver dependency.  Room fit, availability and
    block geometry are filtered without excluding any feasible assignment;
    every remaining complete genotype is independently evaluated.  One
    representative is retained per objective vector.  An a priori combination
    bound prevents accidentally starting an institute-scale exhaustive run.
    Exceeding the bound raises ValueError and does not produce a partial front
    that could be mistaken for an exact result.
    """
    from .evaluation import evaluate

    validate_problem(problem)
    if type(max_combinations) is not int or max_combinations <= 0:
        raise ValueError("max_combinations must be a positive integer")
    started = perf_counter()
    faculty = {f.id: f for f in problem.faculty}
    rooms = {r.id: r for r in problem.rooms}
    offering_index = {o.id: i for i, o in enumerate(problem.offerings)}
    teacher_choices = 1
    for offering in problem.offerings:
        teacher_choices *= len(offering.eligible_faculty)
        if teacher_choices > max_combinations:
            raise ValueError("Teacher assignment space exceeds max_combinations")

    domains = {}
    for event in problem.events:
        offering = problem.offerings[offering_index[event.offering_id]]
        for teacher_id in offering.eligible_faculty:
            domains[event.id, teacher_id] = tuple(
                Placement(start, room_id)
                for start in valid_starts(problem, event)
                for room_id in compatible_rooms(problem, event)
                if not any(
                    slot in rooms[room_id].unavailable
                    or slot in faculty[teacher_id].unavailable
                    for slot in range(start, start + event.duration)
                )
            )
    # Count once before evaluating; teacher products are safely bounded above.
    combinations = 0
    for selected_teachers in product(*(o.eligible_faculty for o in problem.offerings)):
        count = 1
        for event in problem.events:
            teacher_id = selected_teachers[offering_index[event.offering_id]]
            count *= len(domains[event.id, teacher_id])
        combinations += count
        if combinations > max_combinations:
            raise ValueError("Scheduling space exceeds max_combinations")

    archive = []
    objective_vectors = []
    evaluated = feasible = 0

    def dominates(first, second):
        return all(a <= b for a, b in zip(first, second)) and any(
            a < b for a, b in zip(first, second)
        )

    for selected_teachers in product(*(o.eligible_faculty for o in problem.offerings)):
        event_domains = [
            domains[e.id, selected_teachers[offering_index[e.offering_id]]]
            for e in problem.events
        ]
        for selected_placements in product(*event_domains):
            schedule = Schedule(tuple(selected_placements), tuple(selected_teachers))
            assessment = evaluate(problem, schedule)
            evaluated += 1
            if not assessment.feasible:
                continue
            feasible += 1
            vector = assessment.objectives
            if vector in objective_vectors or any(
                dominates(other, vector) for other in objective_vectors
            ):
                continue
            kept = [
                i for i, other in enumerate(objective_vectors)
                if not dominates(vector, other)
            ]
            archive = [archive[i] for i in kept] + [schedule]
            objective_vectors = [objective_vectors[i] for i in kept] + [vector]
    ordered = sorted(zip(objective_vectors, archive), key=lambda item: item[0])
    return EnumerationResult(
        archive=[schedule for _, schedule in ordered],
        objectives=[vector for vector, _ in ordered],
        evaluated=evaluated,
        feasible_candidates=feasible,
        runtime=perf_counter() - started,
    )


def cp_sat(
    problem: Problem,
    objective: str = "feasibility",
    time_limit: float = 10.0,
    seed: int = 0,
) -> ExactResult:
    """Solve a small instance without consulting its generation witness.

    ``objective`` is ``feasibility``, ``gaps`` or ``room``.  The gaps objective
    uses the project's fixed faculty weight 0.5 and excludes lunch.  The room
    objective uses exact integer coefficients obtained from the least common
    multiple of room capacities, rather than rounded decimal penalties.

    One Boolean alternative jointly fixes an event's start, room and teacher;
    offering-level teacher variables enforce teaching consistency.  Resource
    constraints cover every period of multi-period sessions.

    OR-Tools is optional and imported only when this function is called.  A
    missing installation raises an actionable ImportError.  UNKNOWN means no
    solution or infeasibility proof was found before the limit; INFEASIBLE is
    reserved for a solver proof.  Single-thread search and a fixed seed improve
    reproducibility; wall-clock limits can still affect timed-out runs.
    """
    if objective not in {"feasibility", "gaps", "room"}:
        raise ValueError("objective must be 'feasibility', 'gaps' or 'room'")
    if not isfinite(time_limit) or time_limit <= 0:
        raise ValueError("time_limit must be a finite positive number")
    if not isinstance(seed, int) or not 0 <= seed <= 2**31 - 1:
        raise ValueError("seed must be an integer in [0, 2**31 - 1]")
    try:
        from ortools.sat.python import cp_model
        import ortools
    except ImportError as exc:
        raise ImportError(
            "The CP-SAT reference requires OR-Tools. Install with "
            "`pip install -e '.[exact]'`."
        ) from exc

    validate_problem(problem)
    started = perf_counter()
    model = cp_model.CpModel()
    events = problem.events
    faculty = {f.id: f for f in problem.faculty}
    rooms = {r.id: r for r in problem.rooms}
    offering_index = {o.id: i for i, o in enumerate(problem.offerings)}
    offerings = {o.id: o for o in problem.offerings}
    width = problem.periods_per_day

    teachers = {}
    for offering in problem.offerings:
        for teacher in offering.eligible_faculty:
            teachers[offering.id, teacher] = model.NewBoolVar(
                f"teacher_{offering.id}_{teacher}"
            )
        model.AddExactlyOne(
            teachers[offering.id, f] for f in offering.eligible_faculty
        )

    room_occupancy: dict[tuple[str, int], list] = defaultdict(list)
    faculty_occupancy: dict[tuple[str, int], list] = defaultdict(list)
    group_occupancy: dict[tuple[str, int], list] = defaultdict(list)
    faculty_weekly: dict[str, list] = defaultdict(list)
    faculty_daily: dict[tuple[str, int], list] = defaultdict(list)
    offering_days: dict[tuple[str, int], list] = defaultdict(list)
    choices: list[list[tuple[Any, int, str, str]]] = []
    room_terms = []
    room_coefficient_sum = 0
    total_duration = sum(e.duration for e in events)
    capacity_lcm = lcm(*(r.capacity for r in problem.rooms))
    room_scale = capacity_lcm * max(total_duration, 1)
    # CP-SAT sums use signed int64.  Refuse an unsafe scale rather than round an
    # objective silently; this can happen with unusually many coprime capacities.
    if objective == "room" and room_scale > 2**60:
        raise ValueError(
            "Room capacities produce an unsafe exact integer scale; "
            "use fewer distinct capacities for this small-instance reference."
        )

    for event in events:
        offering = offerings[event.offering_id]
        options = []
        event_teacher: dict[str, list] = defaultdict(list)
        for start in valid_starts(problem, event):
            block = tuple(range(start, start + event.duration))
            day = start // width
            for room_id in compatible_rooms(problem, event):
                room = rooms[room_id]
                if any(t in room.unavailable for t in block):
                    continue
                for teacher_id in offering.eligible_faculty:
                    teacher = faculty[teacher_id]
                    if any(t in teacher.unavailable for t in block):
                        continue
                    variable = model.NewBoolVar(
                        f"x_{event.id}_{start}_{room_id}_{teacher_id}"
                    )
                    options.append((variable, start, room_id, teacher_id))
                    event_teacher[teacher_id].append(variable)
                    faculty_weekly[teacher_id].append(event.duration * variable)
                    faculty_daily[teacher_id, day].append(event.duration * variable)
                    if offering.distinct_days:
                        offering_days[offering.id, day].append(variable)
                    for slot in block:
                        room_occupancy[room_id, slot].append(variable)
                        faculty_occupancy[teacher_id, slot].append(variable)
                        for group in event.groups:
                            group_occupancy[group, slot].append(variable)
                    if objective == "room":
                        coefficient = (
                            event.duration
                            * (room.capacity - event.size)
                            * (capacity_lcm // room.capacity)
                        )
                        room_coefficient_sum += coefficient
                        if room_coefficient_sum > 2**60:
                            raise ValueError(
                                "Room objective coefficients exceed the safe "
                                "exact integer range for this reference."
                            )
                        room_terms.append(coefficient * variable)
        choices.append(options)
        model.AddExactlyOne(x[0] for x in options)
        for teacher_id in offering.eligible_faculty:
            model.Add(
                sum(event_teacher[teacher_id])
                == teachers[offering.id, teacher_id]
            )

    for occupancy in (room_occupancy, faculty_occupancy, group_occupancy):
        for variables in occupancy.values():
            if len(variables) > 1:
                model.AddAtMostOne(variables)
    for teacher in problem.faculty:
        model.Add(sum(faculty_weekly[teacher.id]) <= teacher.max_weekly)
        for day in range(len(problem.days)):
            model.Add(
                sum(faculty_daily[teacher.id, day]) <= teacher.max_daily
            )
    for variables in offering_days.values():
        model.Add(sum(variables) <= 1)

    objective_scale = 1
    if objective == "room":
        objective_scale = room_scale
        model.Minimize(sum(room_terms))
    elif objective == "gaps":
        objective_scale = 2
        terms = []
        teachable_periods = [
            p for p in range(width) if p not in problem.lunch_periods
        ]
        for resources, occupancy, weight, label in (
            (problem.groups, group_occupancy, 2, "group"),
            (problem.faculty, faculty_occupancy, 1, "faculty"),
        ):
            for resource in resources:
                for day in range(len(problem.days)):
                    busy = []
                    for period in teachable_periods:
                        slot = day * width + period
                        indicator = model.NewBoolVar(
                            f"busy_{label}_{resource.id}_{slot}"
                        )
                        model.Add(indicator == sum(occupancy[resource.id, slot]))
                        busy.append(indicator)
                    # A teaching-period gap exists exactly when this period is
                    # free and there is teaching on both sides in the same day.
                    for index in range(1, len(busy) - 1):
                        prefix = model.NewBoolVar(
                            f"before_{label}_{resource.id}_{day}_{index}"
                        )
                        suffix = model.NewBoolVar(
                            f"after_{label}_{resource.id}_{day}_{index}"
                        )
                        model.AddMaxEquality(prefix, busy[:index])
                        model.AddMaxEquality(suffix, busy[index + 1 :])
                        gap = model.NewBoolVar(
                            f"gap_{label}_{resource.id}_{day}_{index}"
                        )
                        model.Add(gap <= prefix)
                        model.Add(gap <= suffix)
                        model.Add(gap <= 1 - busy[index])
                        model.Add(gap >= prefix + suffix - busy[index] - 1)
                        terms.append(weight * gap)
        model.Minimize(sum(terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = seed
    status_code = solver.Solve(model)
    status = solver.StatusName(status_code)
    metadata = {
        "ortools_version": ortools.__version__,
        "option_variables": sum(len(options) for options in choices),
        "branches": solver.NumBranches(),
        "conflicts": solver.NumConflicts(),
        "solver_wall_time": solver.WallTime(),
        "time_limit": time_limit,
        "seed": seed,
        "workers": 1,
        "objective_scale": objective_scale,
    }
    if status_code == cp_model.MODEL_INVALID:
        metadata["validation_error"] = model.Validate()
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ExactResult(
            None, status, None, None, perf_counter() - started, objective, metadata
        )

    placements = []
    assigned_teachers = [""] * len(problem.offerings)
    for event, options in zip(events, choices):
        selected = next(option for option in options if solver.Value(option[0]))
        _, start, room_id, teacher_id = selected
        placements.append(Placement(start, room_id))
        assigned_teachers[offering_index[event.offering_id]] = teacher_id
    schedule = Schedule(tuple(placements), tuple(assigned_teachers))
    # Re-evaluation is an independent guard against extraction/model mistakes.
    from .evaluation import evaluate

    assessment = evaluate(problem, schedule)
    if not assessment.feasible:
        raise RuntimeError(
            f"CP-SAT extracted an invalid schedule: {assessment.violations}"
        )
    value = solver.ObjectiveValue() / objective_scale
    bound = solver.BestObjectiveBound() / objective_scale
    if objective != "feasibility":
        expected = assessment.objectives[0 if objective == "gaps" else 1]
        if abs(value - expected) > 1e-8:
            raise RuntimeError("CP-SAT objective and independent evaluation disagree")
    return ExactResult(
        schedule, status, value, bound, perf_counter() - started, objective, metadata
    )

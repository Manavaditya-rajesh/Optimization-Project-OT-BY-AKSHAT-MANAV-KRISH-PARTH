"""Independent hard-constraint checker and three minimization objectives.

Violation is an integer diagnostic, never an objective in a reported Pareto
front. Feasible candidates always outrank infeasible ones during search.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import fsum, isfinite, sqrt
from typing import Any

from .model import Placement, Problem, Schedule


@dataclass(frozen=True)
class Evaluation:
    objectives: tuple[float, float, float]
    violation: int
    violations: dict[str, int]
    metrics: dict[str, Any]

    @property
    def feasible(self) -> bool:
        return self.violation == 0


def _daily_gaps(
    occupancy: dict[tuple[str, int], set[int]], problem: Problem
) -> tuple[int, int, int]:
    """Return gaps, longest idle stretch, and teaching runs exceeding 3 periods."""
    total = longest = consecutive_excess = 0
    lunch = set(problem.lunch_periods)
    for (_, _day), busy in occupancy.items():
        if not busy:
            continue
        first, last = min(busy), max(busy)
        run = idle = 0
        for period in range(first, last + 1):
            if period in lunch:
                run = 0
                continue
            if period in busy:
                run += 1
                idle = 0
                consecutive_excess += int(run > 3)
            else:
                total += 1
                idle += 1
                longest = max(longest, idle)
                run = 0
    return total, longest, consecutive_excess


def evaluate(problem: Problem, schedule: Schedule, faculty_gap_weight: float = 0.5) -> Evaluation:
    """Evaluate a candidate and check every hard constraint independently.

    Every event and offering is represented by its index in the model's stable
    order. Invalid/missing entries are explicitly infeasible. Per-offering
    teacher genes enforce same-teacher consistency by construction. Faculty
    weekly loads count *required* periods, including unscheduled events, so
    deleting a placement cannot reduce the workload objective.

    V sums missing/extra genes, invalid assignment/domain entries, excess
    resource-slot occupancies, blocked resource-periods, excess same-day
    sessions, and daily/weekly overload periods. Its component scales differ;
    V is an infeasibility search ranking, not a measure of practical quality.
    """
    if not isfinite(faculty_gap_weight) or faculty_gap_weight < 0:
        raise ValueError("faculty_gap_weight must be finite and nonnegative")
    events = problem.events
    offerings = {offering.id: offering for offering in problem.offerings}
    rooms = {room.id: room for room in problem.rooms}
    faculty = {person.id: person for person in problem.faculty}
    room_blocked = {room.id: set(room.unavailable) for room in problem.rooms}
    faculty_blocked = {person.id: set(person.unavailable) for person in problem.faculty}
    violations: Counter[str] = Counter()
    if len(schedule.placements) != len(events):
        violations["placement_count"] += abs(len(schedule.placements) - len(events))
    if len(schedule.teachers) != len(problem.offerings):
        violations["teacher_count"] += abs(len(schedule.teachers) - len(problem.offerings))
    teachers: dict[str, str | None] = {}
    loads: dict[str, int] = {person.id: 0 for person in problem.faculty}
    for index, offering in enumerate(problem.offerings):
        teacher = schedule.teachers[index] if index < len(schedule.teachers) else None
        if not isinstance(teacher, str) or teacher not in offering.eligible_faculty or teacher not in faculty:
            violations["invalid_teacher"] += 1
            teachers[offering.id] = None
        else:
            teachers[offering.id] = teacher
            loads[teacher] += offering.sessions * offering.duration
    for person in problem.faculty:
        violations["weekly_overload"] += max(0, loads[person.id] - person.max_weekly)

    room_occupancy: Counter[tuple[str, int]] = Counter()
    faculty_occupancy: Counter[tuple[str, int]] = Counter()
    group_occupancy: Counter[tuple[str, int]] = Counter()
    faculty_daily_load: Counter[tuple[str, int]] = Counter()
    offering_days: Counter[tuple[str, int]] = Counter()
    group_busy: dict[tuple[str, int], set[int]] = defaultdict(set)
    faculty_busy: dict[tuple[str, int], set[int]] = defaultdict(set)
    # Stable summation matters for Pareto equality: permutations of identical
    # room-fit or relative-load multisets must not create artificial trade-offs.
    weighted_room_terms: list[float] = []
    demand_periods = sum(event.duration for event in events)
    lunch = set(problem.lunch_periods)

    for index, event in enumerate(events):
        placement = schedule.placements[index] if index < len(schedule.placements) else None
        if placement is None:
            violations["missing_event"] += 1
            weighted_room_terms.append(float(event.duration))
            continue
        if not isinstance(placement, Placement):
            violations["invalid_placement"] += 1
            weighted_room_terms.append(float(event.duration))
            continue
        room = rooms.get(placement.room) if isinstance(placement.room, str) else None
        if room is None:
            violations["invalid_room"] += 1
            weighted_room_terms.append(float(event.duration))
        else:
            if room.capacity < event.size:
                violations["room_capacity"] += 1
            if room.kind != event.room_kind:
                violations["room_type"] += 1
            # Clipping keeps diagnostics defined for invalid capacity placements.
            weighted_room_terms.append(event.duration * max(0.0, (room.capacity - event.size) / room.capacity))
        start = placement.start
        if type(start) is not int or not 0 <= start < problem.total_periods:
            violations["invalid_start"] += 1
            continue
        day, period = divmod(start, problem.periods_per_day)
        end = period + event.duration
        if end > problem.periods_per_day:
            violations["day_boundary"] += 1
        blocked_lunch = sum(p in lunch for p in range(period, min(end, problem.periods_per_day)))
        violations["lunch"] += blocked_lunch
        offering = offerings[event.offering_id]
        if offering.distinct_days:
            offering_days[(offering.id, day)] += 1
        teacher = teachers[event.offering_id]
        # Count only in-day periods for malformed cross-day blocks. The explicit
        # boundary violation prevents such candidates from being feasible.
        for p in range(period, min(end, problem.periods_per_day)):
            slot = day * problem.periods_per_day + p
            if room is not None:
                room_occupancy[(room.id, slot)] += 1
                violations["room_unavailable"] += int(slot in room_blocked[room.id])
            for group in event.groups:
                group_occupancy[(group, slot)] += 1
                if p not in lunch:
                    group_busy[(group, day)].add(p)
            if teacher is not None:
                faculty_occupancy[(teacher, slot)] += 1
                faculty_daily_load[(teacher, day)] += 1
                violations["faculty_unavailable"] += int(slot in faculty_blocked[teacher])
                if p not in lunch:
                    faculty_busy[(teacher, day)].add(p)
    for name, occupancy in (
        ("room_clash", room_occupancy),
        ("faculty_clash", faculty_occupancy),
        ("student_clash", group_occupancy),
        ("same_day_sessions", offering_days),
    ):
        violations[name] += sum(max(0, count - 1) for count in occupancy.values())
    violations["daily_overload"] += sum(
        max(0, load - faculty[teacher].max_daily)
        for (teacher, _day), load in faculty_daily_load.items()
    )

    student_gaps, student_longest, student_excess = _daily_gaps(group_busy, problem)
    faculty_gaps, faculty_longest, faculty_excess = _daily_gaps(faculty_busy, problem)
    relative_loads = [loads[person.id] / person.max_weekly for person in problem.faculty]
    mean_load = fsum(relative_loads) / len(relative_loads) if relative_loads else 0.0
    imbalance = sqrt(fsum((load - mean_load) ** 2 for load in relative_loads) / len(relative_loads)) if relative_loads else 0.0
    room_waste = fsum(weighted_room_terms) / demand_periods if demand_periods else 0.0
    objectives = (
        float(student_gaps + faculty_gap_weight * faculty_gaps),
        float(room_waste),
        float(imbalance),
    )
    violations = Counter({name: count for name, count in violations.items() if count})
    return Evaluation(
        objectives, sum(violations.values()), dict(sorted(violations.items())),
        {
            "student_gaps": student_gaps,
            "faculty_gaps": faculty_gaps,
            "average_student_gap_per_day": student_gaps / (len(problem.groups) * len(problem.days)) if problem.groups else 0.0,
            "longest_idle_stretch": max(student_longest, faculty_longest),
            "room_utilization": 1.0 - room_waste,
            "faculty_loads": loads,
            "faculty_relative_loads": dict(zip((person.id for person in problem.faculty), relative_loads)),
            "max_faculty_daily_load": max(faculty_daily_load.values(), default=0),
            "consecutive_periods_over_three": student_excess + faculty_excess,
            "required_teaching_periods": demand_periods,
        },
    )

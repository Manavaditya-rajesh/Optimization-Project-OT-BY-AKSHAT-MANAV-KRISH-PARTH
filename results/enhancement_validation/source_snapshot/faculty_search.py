"""Bounded exact faculty reassignment within a fixed-time neighborhood.

This operator assumes a feasible incoming schedule. It holds every room and
event time fixed and jointly changes whole-offering faculty genes. Resource
checks cover the complete occupied block of every session. It never calls the
full objective evaluator: its output must pass through the caller's counted
independent evaluator before entering an archive.

For equal weekly limits H, total contact hours and the mean relative workload
are fixed. Thus minimizing integer ``sum(load_f ** 2)`` is exactly equivalent to
minimizing the project's relative-load standard deviation. Unequal H is an
explicit safe no-op, rather than silently optimizing a surrogate. Faculty gaps
can worsen; the caller's Pareto selection must assess that genuine trade-off.

Search is capped by deterministic branch nodes, not elapsed time. Internal
constraint checks, integer workload scores and lower bounds cost computation;
diagnostics expose these counts and elapsed time for fair runtime comparisons.
"""

from __future__ import annotations

import random
from time import perf_counter
from typing import Any

from .model import Placement, Problem, Schedule


def faculty_reassign(
    problem: Problem,
    schedule: Schedule,
    rng: random.Random,
    max_offerings: int = 8,
    max_nodes: int = 12_000,
    diagnostics: dict[str, Any] | None = None,
) -> Schedule:
    """Return a feasible batch reassignment with a strictly better workload SD.

    A no-op is returned if no strict improvement is found, the incoming faculty
    assignment is invalid, or weekly maxima differ. The incoming placement
    feasibility is a precondition: unchanged room/student/time constraints are
    independently checked by the caller. A completed search proves optimality
    only within the selected offering neighborhood, never for the timetable.
    """
    if type(max_offerings) is not int or max_offerings < 1:
        raise ValueError("max_offerings must be a positive integer")
    if type(max_nodes) is not int or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")
    started = perf_counter()
    stats: dict[str, Any] = {
        "operator": "fixed_time_faculty_branch_and_bound",
        "nodes": 0,
        "assignment_checks": 0,
        "complete_assignments": 0,
        "lower_bound_checks": 0,
        "selected_offerings": [],
        "max_nodes": max_nodes,
        "full_evaluations": 0,
        "optimal_within_selected": False,
        "improved": False,
        "initial_sum_squares": None,
        "best_sum_squares": None,
    }

    def finish(candidate: Schedule, status: str) -> Schedule:
        stats["status"] = status
        stats["runtime"] = perf_counter() - started
        if diagnostics is not None:
            diagnostics.update(stats)
        return candidate

    offerings = problem.offerings
    faculty = problem.faculty
    if not offerings or not faculty:
        return finish(schedule, "empty")
    if len({person.max_weekly for person in faculty}) != 1:
        return finish(schedule, "unequal_weekly_limits")
    if len(schedule.placements) != len(problem.events) or len(schedule.teachers) != len(offerings):
        return finish(schedule, "invalid_incoming_assignment")
    faculty_index = {person.id: i for i, person in enumerate(faculty)}
    offering_index = {offering.id: i for i, offering in enumerate(offerings)}
    n_faculty, n_days = len(faculty), len(problem.days)
    teacher_indices: list[int] = []
    for k, offering in enumerate(offerings):
        teacher = schedule.teachers[k]
        if not isinstance(teacher, str) or teacher not in faculty_index or teacher not in offering.eligible_faculty:
            return finish(schedule, "invalid_incoming_assignment")
        teacher_indices.append(faculty_index[teacher])
    masks = [0] * len(offerings)
    day_hours = [[0] * n_days for _ in offerings]
    hours = [offering.sessions * offering.duration for offering in offerings]
    lunch = set(problem.lunch_periods)
    for event, placement in zip(problem.events, schedule.placements):
        if not isinstance(placement, Placement) or type(placement.start) is not int:
            return finish(schedule, "invalid_incoming_assignment")
        if not 0 <= placement.start < problem.total_periods:
            return finish(schedule, "invalid_incoming_assignment")
        day, period = divmod(placement.start, problem.periods_per_day)
        if period + event.duration > problem.periods_per_day or any(
            p in lunch for p in range(period, period + event.duration)
        ):
            return finish(schedule, "invalid_incoming_assignment")
        k = offering_index[event.offering_id]
        block = ((1 << event.duration) - 1) << placement.start
        if masks[k] & block:
            return finish(schedule, "invalid_incoming_assignment")
        masks[k] |= block
        day_hours[k][day] += event.duration
    unavailable = [sum(1 << slot for slot in person.unavailable) for person in faculty]
    original_loads = [0] * n_faculty
    original_busy = [0] * n_faculty
    original_daily = [[0] * n_days for _ in faculty]
    for k, teacher in enumerate(teacher_indices):
        if masks[k] & (original_busy[teacher] | unavailable[teacher]):
            return finish(schedule, "invalid_incoming_assignment")
        original_busy[teacher] |= masks[k]
        original_loads[teacher] += hours[k]
        for day, contact in enumerate(day_hours[k]):
            original_daily[teacher][day] += contact
    if any(
        original_loads[f] > person.max_weekly
        or any(load > person.max_daily for load in original_daily[f])
        for f, person in enumerate(faculty)
    ):
        return finish(schedule, "invalid_incoming_assignment")
    initial_cost = sum(load * load for load in original_loads)
    stats["initial_sum_squares"] = initial_cost
    stats["best_sum_squares"] = initial_cost
    total_hours = sum(original_loads)
    quotient, remainder = divmod(total_hours, n_faculty)
    global_relaxation = remainder * (quotient + 1) ** 2 + (n_faculty - remainder) * quotient**2
    if initial_cost == global_relaxation:
        return finish(schedule, "already_integer_balanced")

    eligible = [tuple(faculty_index[f] for f in offering.eligible_faculty) for offering in offerings]
    count = min(max_offerings, len(offerings))
    if count == len(offerings):
        selected = list(range(len(offerings)))
    else:
        # Start from an offering of a relatively overloaded faculty member.
        # Diversify within the difficult candidates instead of always selecting
        # the same globally heaviest teacher on every invocation.
        movable = [k for k in range(len(offerings)) if len(eligible[k]) > 1]
        if not movable:
            return finish(schedule, "no_eligible_alternative")
        rng.shuffle(movable)
        movable.sort(key=lambda k: (original_loads[teacher_indices[k]], hours[k]), reverse=True)
        seed = rng.choice(movable[:max(1, min(len(movable), count))])
        selected = [seed]
        selected_set = {seed}
        # Pull in offerings currently blocking an eligible destination. This
        # permits chains and unequal-size swaps that single-teacher edits miss.
        while len(selected) < count:
            related = []
            for k in movable:
                if k in selected_set:
                    continue
                teacher = teacher_indices[k]
                collision_links = sum(
                    teacher in eligible[other] and bool(masks[k] & masks[other])
                    for other in selected
                )
                qualification_links = sum(teacher in eligible[other] for other in selected)
                reverse_links = sum(teacher_indices[other] in eligible[k] for other in selected)
                related.append((collision_links, qualification_links + reverse_links,
                                original_loads[teacher], rng.random(), k))
            if not related:
                break
            k = max(related)[-1]
            selected.append(k)
            selected_set.add(k)
    selected_set = set(selected)
    base_loads = [0] * n_faculty
    base_busy = [0] * n_faculty
    base_daily = [[0] * n_days for _ in faculty]
    for k, teacher in enumerate(teacher_indices):
        if k not in selected_set:
            base_loads[teacher] += hours[k]
            base_busy[teacher] |= masks[k]
            for day, contact in enumerate(day_hours[k]):
                base_daily[teacher][day] += contact
    domains: dict[int, tuple[int, ...]] = {}
    for k in selected:
        domains[k] = tuple(
            f for f in eligible[k]
            if not masks[k] & (base_busy[f] | unavailable[f])
            and base_loads[f] + hours[k] <= faculty[f].max_weekly
            and all(base_daily[f][d] + contact <= faculty[f].max_daily
                    for d, contact in enumerate(day_hours[k]))
        )
    # Every original selected assignment remains available because the incoming
    # schedule was faculty-feasible. Small domains and long offerings go first.
    selected.sort(key=lambda k: (len(domains[k]), -hours[k], k))
    stats["selected_offerings"] = [offerings[k].id for k in selected]
    tie_breaks = {(k, f): rng.random() for k in selected for f in domains[k]}
    loads = base_loads[:]
    busy = base_busy[:]
    daily = [row[:] for row in base_daily]
    assignment = teacher_indices[:]
    best_assignment = teacher_indices[:]
    best_cost = initial_cost
    stopped = False

    def search(depth: int, cost: int) -> None:
        nonlocal best_cost, best_assignment, stopped
        if stats["nodes"] >= max_nodes:
            stopped = True
            return
        stats["nodes"] += 1
        if depth == len(selected):
            stats["complete_assignments"] += 1
            if cost < best_cost:
                best_cost = cost
                best_assignment = assignment[:]
            return
        # Sum independent optimistic marginal convex costs. Competition for a
        # teacher can only increase these marginals, so this is a valid bound.
        stats["lower_bound_checks"] += 1
        lower = cost
        for k in selected[depth:]:
            if not domains[k]:
                return
            demand = hours[k]
            lower += min(2 * loads[f] * demand + demand * demand for f in domains[k])
        if lower >= best_cost:
            return
        k = selected[depth]
        demand = hours[k]
        candidates = sorted(domains[k], key=lambda f: (2 * loads[f] * demand + demand * demand,
                                                       tie_breaks[k, f]))
        for f in candidates:
            if stopped:
                return
            stats["assignment_checks"] += 1
            if masks[k] & busy[f] or loads[f] + demand > faculty[f].max_weekly:
                continue
            if any(daily[f][d] + contact > faculty[f].max_daily
                   for d, contact in enumerate(day_hours[k])):
                continue
            delta = 2 * loads[f] * demand + demand * demand
            previous_busy = busy[f]
            busy[f] |= masks[k]
            loads[f] += demand
            for day, contact in enumerate(day_hours[k]):
                daily[f][day] += contact
            assignment[k] = f
            search(depth + 1, cost + delta)
            for day, contact in enumerate(day_hours[k]):
                daily[f][day] -= contact
            loads[f] -= demand
            busy[f] = previous_busy
            if best_cost == global_relaxation:
                return

    search(0, sum(load * load for load in loads))
    stats["best_sum_squares"] = best_cost
    stats["optimal_within_selected"] = not stopped or best_cost == global_relaxation
    stats["improved"] = best_cost < initial_cost
    if best_cost >= initial_cost:
        return finish(schedule, "node_limit" if stopped else "no_improvement")
    proposal = Schedule(schedule.placements, tuple(faculty[f].id for f in best_assignment))
    return finish(proposal, "node_limit_improved" if stopped else "improved")

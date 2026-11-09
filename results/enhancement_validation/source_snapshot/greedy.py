"""Dynamic saturation/degree construction with offering-consistent teachers.

This is a domain heuristic inspired by DSatur, not a claim that timetabling is
ordinary vertex colouring.  Whole offerings are assigned atomically: a teacher
is selected together with every weekly session, with weekly capacity reserved
for the complete offering.  Long blocks, scarcity, saturation and conflict
degree determine the next offering.  Restricted candidate lists diversify
restarts while preferring compact days, fitting rooms and balanced loads.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import random

from .evaluation import evaluate
from .model import Placement, Problem, Schedule, compatible_rooms, valid_starts, validate_problem


class SchedulingFailure(RuntimeError):
    """The heuristic failed; this is not a proof that the instance is infeasible."""


@dataclass
class _Domains:
    indices: list[tuple[int, ...]]
    starts: list[tuple[tuple[int, int, int], ...]]
    rooms: list[tuple[str, ...]]
    faculty: dict
    room_catalogue: dict
    unavailable_faculty: dict[str, int]
    unavailable_rooms: dict[str, int]
    degree: list[int]
    teaching_by_day: tuple[int, ...]


def _bits(slots) -> int:
    return sum(1 << slot for slot in slots)


@lru_cache(maxsize=16)
def _domains(problem: Problem) -> _Domains:
    events = problem.events
    indices = [tuple(i for i, e in enumerate(events) if e.offering_id == o.id)
               for o in problem.offerings]
    starts = []
    rooms = []
    room_catalogue = {r.id: r for r in problem.rooms}
    for event_indices in indices:
        event = events[event_indices[0]]
        starts.append(tuple((s, ((1 << event.duration) - 1) << s,
                             s // problem.periods_per_day)
                            for s in valid_starts(problem, event)))
        rooms.append(tuple(sorted(compatible_rooms(problem, event),
                                  key=lambda r: (room_catalogue[r].capacity, r))))
    groups = [set(o.groups) for o in problem.offerings]
    # Shared eligible faculty are potential resource competition, whereas a
    # shared cohort is a mandatory conflict; both inform heuristic difficulty.
    eligible = [set(o.eligible_faculty) for o in problem.offerings]
    degree = [sum(i != j and (bool(groups[i] & groups[j]) or bool(eligible[i] & eligible[j]))
                  for j in range(len(groups))) for i in range(len(groups))]
    return _Domains(
        indices, starts, rooms, {f.id: f for f in problem.faculty}, room_catalogue,
        {f.id: _bits(f.unavailable) for f in problem.faculty},
        {r.id: _bits(r.unavailable) for r in problem.rooms}, degree,
        tuple(_bits(d * problem.periods_per_day + p
                    for p in range(problem.periods_per_day)
                    if p not in problem.lunch_periods) for d in range(len(problem.days))),
    )


def construct(problem: Problem, rng: random.Random, preferred: Schedule | None = None,
              randomized: bool = True) -> Schedule:
    """Construct/repair without invoking the full objective evaluator.

    Invalid original placements are discarded by direct resource checks.  A
    preferred chromosome biases retention, but no hidden feasibility witness is
    read.  Failure is represented by ``None`` placements and can be measured by
    the common evaluator.  This helper performs no evaluation-budget calls.
    """
    domain = _domains(problem)
    offerings = problem.offerings
    placements: list[Placement | None] = [None] * len(problem.events)
    teachers = [o.eligible_faculty[0] if o.eligible_faculty else "" for o in offerings]
    group_busy = {g.id: 0 for g in problem.groups}
    faculty_busy = {f.id: 0 for f in problem.faculty}
    room_busy = {r.id: 0 for r in problem.rooms}
    faculty_load = {f.id: 0 for f in problem.faculty}
    daily_load = {f.id: [0] * len(problem.days) for f in problem.faculty}
    pending = set(range(len(offerings)))
    ties = {k: rng.random() if randomized else -k for k in pending}
    gap_weight = rng.uniform(0.8, 1.2) if randomized else 1.0
    room_weight = rng.uniform(0.3, 1.2) if randomized else 0.6
    balance_weight = rng.uniform(1.0, 4.0) if randomized else 2.0

    @lru_cache(maxsize=12000)
    def gaps(mask: int) -> int:
        total = 0
        for teaching in domain.teaching_by_day:
            busy = mask & teaching
            if busy:
                first = (busy & -busy).bit_length() - 1
                last = busy.bit_length() - 1
                span = ((1 << (last - first + 1)) - 1) << first
                total += (span & teaching).bit_count() - busy.bit_count()
        return total

    def priority(k: int):
        offering = offerings[k]
        occupied = 0
        for group in offering.groups:
            occupied |= group_busy[group]
        saturation = sum(bool(mask & occupied) for _, mask, _ in domain.starts[k])
        scarcity = len(domain.starts[k]) * max(1, len(domain.rooms[k])) * max(1, len(offering.eligible_faculty))
        return (offering.duration > 1, saturation, -scarcity,
                domain.degree[k], offering.sessions, ties[k])

    while pending:
        k = max(pending, key=priority)
        pending.remove(k)
        offering = offerings[k]
        event_indices = domain.indices[k]
        contact = offering.sessions * offering.duration
        group_mask = 0
        for group in offering.groups:
            group_mask |= group_busy[group]
        candidate_plans = []
        faculty_candidates = list(offering.eligible_faculty)
        if randomized:
            rng.shuffle(faculty_candidates)
        for faculty_id in faculty_candidates:
            faculty = domain.faculty[faculty_id]
            if faculty_load[faculty_id] + contact > faculty.max_weekly:
                continue
            local_mask = 0
            local_rooms: dict[str, int] = {}
            local_daily = [0] * len(problem.days)
            used_days: set[int] = set()
            plan = []
            plan_cost = 0.0
            for event_index in event_indices:
                candidates = []
                old = preferred.placements[event_index] if preferred and event_index < len(preferred.placements) else None
                for start, mask, day in domain.starts[k]:
                    if (offering.distinct_days and day in used_days) or (mask & (group_mask | local_mask)):
                        continue
                    if mask & (faculty_busy[faculty_id] | local_mask | domain.unavailable_faculty[faculty_id]):
                        continue
                    if daily_load[faculty_id][day] + local_daily[day] + offering.duration > faculty.max_daily:
                        continue
                    gap_delta = sum(gaps(group_busy[g] | local_mask | mask) - gaps(group_busy[g] | local_mask)
                                    for g in offering.groups)
                    gap_delta += 0.5 * (gaps(faculty_busy[faculty_id] | local_mask | mask) -
                                        gaps(faculty_busy[faculty_id] | local_mask))
                    for room_id in domain.rooms[k]:
                        if mask & (room_busy[room_id] | local_rooms.get(room_id, 0) | domain.unavailable_rooms[room_id]):
                            continue
                        room = domain.room_catalogue[room_id]
                        waste = offering.duration * (1.0 - problem.events[event_index].size / room.capacity)
                        keep = 0.0 if old and old.start == start and old.room == room_id else (5.0 if old else 0.0)
                        jitter = rng.random() * 0.08 if randomized else 0.0
                        cost = gap_weight * gap_delta + room_weight * waste + keep + jitter + start * 0.0001
                        candidates.append((cost, start, room_id, mask, day))
                if not candidates:
                    break
                candidates.sort()
                if randomized:
                    # Restricted candidate list: only near-ties are randomized.
                    shortlist = [c for c in candidates[:4] if c[0] <= candidates[0][0] + 0.13]
                    chosen = rng.choice(shortlist)
                else:
                    chosen = candidates[0]
                cost, start, room_id, mask, day = chosen
                plan.append((event_index, Placement(start, room_id), mask, day))
                plan_cost += cost
                local_mask |= mask
                local_rooms[room_id] = local_rooms.get(room_id, 0) | mask
                local_daily[day] += offering.duration
                used_days.add(day)
            if len(plan) == len(event_indices):
                future_ratio = (faculty_load[faculty_id] + contact) / faculty.max_weekly
                plan_cost += balance_weight * future_ratio
                if preferred and k < len(preferred.teachers) and preferred.teachers[k] != faculty_id:
                    plan_cost += 3.0
                candidate_plans.append((plan_cost, faculty_id, plan, local_mask, local_rooms, local_daily))
        if not candidate_plans:
            continue
        candidate_plans.sort(key=lambda candidate: candidate[0])
        if randomized:
            shortlist = [p for p in candidate_plans[:3] if p[0] <= candidate_plans[0][0] + 0.15]
            chosen_plan = rng.choice(shortlist)
        else:
            chosen_plan = candidate_plans[0]
        _, faculty_id, plan, local_mask, local_rooms, local_daily = chosen_plan
        teachers[k] = faculty_id
        faculty_busy[faculty_id] |= local_mask
        faculty_load[faculty_id] += contact
        for day, hours in enumerate(local_daily):
            daily_load[faculty_id][day] += hours
        for group in offering.groups:
            group_busy[group] |= local_mask
        for room_id, mask in local_rooms.items():
            room_busy[room_id] |= mask
        for event_index, placement, _, _ in plan:
            placements[event_index] = placement
    return Schedule(tuple(placements), tuple(teachers))


def greedy(problem: Problem, seed: int = 0, restarts: int = 8) -> Schedule:
    """Return the best feasible restart under an explicitly documented score.

    The first restart uses deterministic candidate selection.  Later restarts
    use seeded restricted candidate lists.  A scalar compromise is appropriate
    for this baseline; NSGA-II separately retains Pareto alternatives.
    """
    validate_problem(problem)
    if restarts < 1:
        raise ValueError("restarts must be at least one")
    rng = random.Random(seed)
    best = None
    best_score = float("inf")
    for restart in range(restarts):
        candidate = construct(problem, rng, randomized=restart > 0)
        outcome = evaluate(problem, candidate)
        if outcome.feasible:
            gap, waste, imbalance = outcome.objectives
            score = gap / max(1, len(problem.groups) * len(problem.days)) + waste + imbalance
            if score < best_score:
                best, best_score = candidate, score
    if best is None:
        raise SchedulingFailure(f"No feasible timetable found in {restarts} constructive restarts; infeasibility is not proven")
    return best

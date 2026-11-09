"""Bounded, feasibility-preserving timetable neighborhoods.

Unlike whole-offering crossover, these operators begin with a complete feasible
schedule and check every changed resource block before inserting it. Teacher
moves remove and jointly reinsert all sessions of an offering; reciprocal
teacher exchanges can reinsert two offerings. Failure returns the original
schedule, never a partial timetable. No planted certificate or full objective
calculator is imported: callers independently evaluate and count each returned
candidate. Internal bitmask resource checks and incremental gap/load scores are
part of proposal construction and must be included in runtime comparisons.
"""
from __future__ import annotations

from functools import lru_cache
import math
import random
from typing import Iterable

from .model import Placement, Problem, Schedule, compatible_rooms, valid_starts, validate_problem


class _State:
    """Mutable occupancy for one bounded move; bitmasks include the full week."""

    def __init__(self, neighborhood: "FeasibleNeighborhood", schedule: Schedule):
        self.n = neighborhood
        self.placements = list(schedule.placements)
        self.teachers = list(schedule.teachers)
        self.room = {key: 0 for key in neighborhood.rooms}
        self.faculty = {key: 0 for key in neighborhood.faculty}
        self.group = {group.id: 0 for group in neighborhood.problem.groups}
        self.load = {key: 0 for key in neighborhood.faculty}
        self.daily = {key: [0] * len(neighborhood.problem.days) for key in neighborhood.faculty}
        self.days = [[0] * len(neighborhood.problem.days) for _ in neighborhood.problem.offerings]
        self.masks = [0] * len(neighborhood.events)

    def copy(self) -> "_State":
        other = object.__new__(_State)
        other.n = self.n
        other.placements, other.teachers = list(self.placements), list(self.teachers)
        other.room, other.faculty, other.group = dict(self.room), dict(self.faculty), dict(self.group)
        other.load = dict(self.load)
        other.daily = {teacher: list(values) for teacher, values in self.daily.items()}
        other.days = [list(values) for values in self.days]
        other.masks = list(self.masks)
        return other

    def can_place(self, index: int, start: int, room: str) -> bool:
        n = self.n
        if type(start) is not int or not isinstance(room, str) or start not in n.start_sets[index] or room not in n.room_sets[index]:
            return False
        event = n.events[index]
        k = n.event_offering[index]
        teacher = self.teachers[k]
        if teacher not in n.faculty or teacher not in n.problem.offerings[k].eligible_faculty:
            return False
        day = start // n.problem.periods_per_day
        if n.problem.offerings[k].distinct_days and self.days[k][day]:
            return False
        mask = n.mask(index, start)
        if mask & (self.room[room] | n.room_blocked[room] | self.faculty[teacher] | n.faculty_blocked[teacher]):
            return False
        if any(mask & self.group[group] for group in event.groups):
            return False
        faculty = n.faculty[teacher]
        return (self.load[teacher] + event.duration <= faculty.max_weekly
                and self.daily[teacher][day] + event.duration <= faculty.max_daily)

    def add(self, index: int, placement: Placement) -> bool:
        if not self.can_place(index, placement.start, placement.room):
            return False
        event = self.n.events[index]
        k = self.n.event_offering[index]
        teacher = self.teachers[k]
        day = placement.start // self.n.problem.periods_per_day
        mask = self.n.mask(index, placement.start)
        self.placements[index], self.masks[index] = placement, mask
        self.room[placement.room] |= mask
        self.faculty[teacher] |= mask
        for group in event.groups:
            self.group[group] |= mask
        self.load[teacher] += event.duration
        self.daily[teacher][day] += event.duration
        self.days[k][day] += 1
        return True

    def remove(self, index: int) -> None:
        placement = self.placements[index]
        assert placement is not None
        mask = self.masks[index]
        event = self.n.events[index]
        k = self.n.event_offering[index]
        teacher = self.teachers[k]
        day = placement.start // self.n.problem.periods_per_day
        self.room[placement.room] &= ~mask
        self.faculty[teacher] &= ~mask
        for group in event.groups:
            self.group[group] &= ~mask
        self.load[teacher] -= event.duration
        self.daily[teacher][day] -= event.duration
        self.days[k][day] -= 1
        self.placements[index], self.masks[index] = None, 0

    def schedule(self) -> Schedule:
        assert all(placement is not None for placement in self.placements)
        return Schedule(tuple(self.placements), tuple(self.teachers))


class FeasibleNeighborhood:
    """Generate complete feasible candidates with bounded direct resource checks.

    ``propose(schedule, rng, mode=None)`` accepts a *feasible* schedule. Malformed
    or infeasible input raises ``ValueError`` using direct checks, without
    calling the full evaluator. Modes are ``relocate``/0, ``room``/1,
    ``swap``/2, ``teacher``/3 and ``exchange``/4; ``None`` samples a mode.
    Internal ranking is heuristic; Pareto survival remains the caller's job.
    """

    MODES = ("relocate", "room", "swap", "teacher", "exchange")

    def __init__(self, problem: Problem, *, candidate_events: int = 5,
                 teacher_targets: int = 8, max_nodes: int = 120):
        validate_problem(problem)
        if any(type(value) is not int or value <= 0 for value in (candidate_events, teacher_targets, max_nodes)):
            raise ValueError("candidate_events, teacher_targets and max_nodes must be positive integers")
        self.problem = problem
        self.events = problem.events
        self.rooms = {room.id: room for room in problem.rooms}
        self.faculty = {faculty.id: faculty for faculty in problem.faculty}
        self.starts = [valid_starts(problem, event) for event in self.events]
        self.start_sets = [set(starts) for starts in self.starts]
        self.compatible = [tuple(sorted(compatible_rooms(problem, event),
                                      key=lambda room: (self.rooms[room].capacity, room))) for event in self.events]
        self.room_sets = [set(rooms) for rooms in self.compatible]
        self.room_blocked = {room.id: sum(1 << slot for slot in room.unavailable) for room in problem.rooms}
        self.faculty_blocked = {faculty.id: sum(1 << slot for slot in faculty.unavailable) for faculty in problem.faculty}
        offering_index = {offering.id: i for i, offering in enumerate(problem.offerings)}
        self.event_offering = [offering_index[event.offering_id] for event in self.events]
        self.offering_events: list[list[int]] = [[] for _ in problem.offerings]
        for i, k in enumerate(self.event_offering):
            self.offering_events[k].append(i)
        self.contacts = [offering.sessions * offering.duration for offering in problem.offerings]
        self.teaching_days = tuple(sum(1 << (day * problem.periods_per_day + period)
                                      for period in range(problem.periods_per_day) if period not in problem.lunch_periods)
                                   for day in range(len(problem.days)))
        self.candidate_events = candidate_events
        self.teacher_targets = teacher_targets
        self.max_nodes = max_nodes
        self.last_diagnostics: dict = {}

    def mask(self, index: int, start: int) -> int:
        return ((1 << self.events[index].duration) - 1) << start

    @lru_cache(maxsize=24000)
    def gaps(self, mask: int) -> int:
        """Exact occupied-span gaps, excluding lunch and empty days."""
        total = 0
        for teaching in self.teaching_days:
            busy = mask & teaching
            if busy:
                first = (busy & -busy).bit_length() - 1
                last = busy.bit_length() - 1
                span = ((1 << (last - first + 1)) - 1) << first
                total += (span & teaching).bit_count() - busy.bit_count()
        return total

    def _state(self, schedule: Schedule) -> _State:
        if len(schedule.placements) != len(self.events) or len(schedule.teachers) != len(self.problem.offerings):
            raise ValueError("FeasibleNeighborhood requires a complete feasible schedule")
        state = _State(self, schedule)
        for k, offering in enumerate(self.problem.offerings):
            teacher = schedule.teachers[k]
            if not isinstance(teacher, str) or teacher not in self.faculty or teacher not in offering.eligible_faculty:
                raise ValueError("FeasibleNeighborhood requires valid offering teachers")
        for index, placement in enumerate(schedule.placements):
            if not isinstance(placement, Placement) or not state.add(index, placement):
                raise ValueError("FeasibleNeighborhood requires a feasible schedule")
        return state

    def _focus(self, state: _State, rng: random.Random, limit: int | None = None) -> list[int]:
        """Biased sampling towards gap-bearing resources and poorly fitting rooms."""
        priorities = []
        for i, event in enumerate(self.events):
            place = state.placements[i]
            assert place is not None
            teacher = state.teachers[self.event_offering[i]]
            score = sum(self.gaps(state.group[group]) for group in event.groups)
            score += 0.5 * self.gaps(state.faculty[teacher])
            score += 1 - event.size / self.rooms[place.room].capacity
            priorities.append((score + rng.random(), i))
        priorities.sort(reverse=True)
        return [i for _, i in priorities[:limit or self.candidate_events]]

    def _placement_candidates(self, state: _State, index: int, rng: random.Random,
                              *, preferred: Placement | None = None,
                              room_weight: float = 1.0, gap_weight: float = 1.0,
                              limit: int | None = None) -> list[tuple[float, Placement]]:
        event = self.events[index]
        teacher = state.teachers[self.event_offering[index]]
        before_groups = sum(self.gaps(state.group[group]) for group in event.groups)
        before_faculty = self.gaps(state.faculty[teacher])
        choices = []
        for start in self.starts[index]:
            mask = self.mask(index, start)
            # Room-independent checks avoid scanning rooms at occupied times.
            if mask & (state.faculty[teacher] | self.faculty_blocked[teacher]):
                continue
            if any(mask & state.group[group] for group in event.groups):
                continue
            gap_delta = sum(self.gaps(state.group[group] | mask) for group in event.groups) - before_groups
            gap_delta += 0.5 * (self.gaps(state.faculty[teacher] | mask) - before_faculty)
            for room in self.compatible[index]:
                if state.can_place(index, start, room):
                    waste = event.duration * (1 - event.size / self.rooms[room].capacity)
                    # Near-equal candidates are randomized reproducibly; retaining
                    # an original placement is a tie preference, not a constraint.
                    keep = -1e-5 if preferred == Placement(start, room) else 0
                    score = gap_weight * gap_delta + room_weight * waste + keep + rng.random() * 1e-7
                    choices.append((score, Placement(start, room)))
        choices.sort(key=lambda item: item[0])
        return choices if limit is None else choices[:limit]

    def _relocate(self, state: _State, rng: random.Random) -> Schedule:
        best: tuple[float, Schedule] | None = None
        gap_weight, room_weight = rng.uniform(0.8, 1.2), rng.uniform(0.25, 1.5)
        for index in self._focus(state, rng):
            old = state.placements[index]
            assert old is not None
            candidate = state.copy()
            candidate.remove(index)
            choices = self._placement_candidates(candidate, index, rng, preferred=old,
                                                  room_weight=room_weight, gap_weight=gap_weight)
            old_score = next((score for score, place in choices if place == old), math.inf)
            for score, place in choices:
                if place == old:
                    continue
                delta = score - old_score
                if best is None or delta < best[0]:
                    moved = candidate.copy()
                    assert moved.add(index, place)
                    best = (delta, moved.schedule())
                break
        return best[1] if best is not None else state.schedule()

    def _room(self, state: _State, rng: random.Random) -> Schedule:
        candidates = list(range(len(self.events)))
        rng.shuffle(candidates)
        candidates.sort(key=lambda i: (1 - self.events[i].size / self.rooms[state.placements[i].room].capacity), reverse=True)
        for index in candidates:
            old = state.placements[index]
            assert old is not None
            candidate = state.copy()
            candidate.remove(index)
            for room in self.compatible[index]:
                if self.rooms[room].capacity >= self.rooms[old.room].capacity:
                    break
                place = Placement(old.start, room)
                if candidate.add(index, place):
                    return candidate.schedule()
        return state.schedule()

    def _gap_total(self, state: _State) -> float:
        return sum(self.gaps(mask) for mask in state.group.values()) + 0.5 * sum(self.gaps(mask) for mask in state.faculty.values())

    def _swap(self, state: _State, rng: random.Random) -> Schedule:
        focus = self._focus(state, rng)
        partners = list(range(len(self.events)))
        rng.shuffle(partners)
        best: tuple[float, Schedule] | None = None
        for first in focus:
            old_first = state.placements[first]
            assert old_first is not None
            # Prioritize cohorts/faculty sharing the affected timetable, then
            # a bounded random suffix for exchanges across independent groups.
            candidates = sorted(partners, key=lambda j: not bool(set(self.events[first].groups) & set(self.events[j].groups)))[:24]
            for second in candidates:
                old_second = state.placements[second]
                assert old_second is not None
                if first == second or old_first.start == old_second.start:
                    continue
                trial = state.copy()
                trial.remove(first)
                trial.remove(second)
                # Each event retains its room; unequal lengths are safe because
                # both complete blocks pass normal insertion checks.
                if not trial.add(first, Placement(old_second.start, old_first.room)):
                    continue
                if not trial.add(second, Placement(old_first.start, old_second.room)):
                    continue
                score = self._gap_total(trial)
                if best is None or score < best[0]:
                    best = (score, trial.schedule())
        return best[1] if best is not None else state.schedule()

    def _load_score(self, loads: dict[str, int]) -> float:
        ratios = [loads[faculty.id] / faculty.max_weekly for faculty in self.problem.faculty]
        average = sum(ratios) / len(ratios) if ratios else 0.0
        return sum((ratio - average) ** 2 for ratio in ratios) / len(ratios) if ratios else 0.0

    def _reinsert(self, state: _State, indices: Iterable[int], original: Schedule,
                  rng: random.Random) -> _State | None:
        """Bounded backtracking over complete blocks, with dynamic scarcity."""
        pending = list(indices)
        nodes = 0
        room_weight = rng.uniform(0.25, 1.5)

        def visit(remaining: list[int]) -> _State | None:
            nonlocal nodes
            if not remaining:
                return state
            if nodes >= self.max_nodes:
                return None
            options = []
            for index in remaining:
                choices = self._placement_candidates(state, index, rng,
                                                      preferred=original.placements[index],
                                                      room_weight=room_weight, limit=5)
                if not choices:
                    return None
                options.append((len(choices), index, choices))
            _, index, choices = min(options, key=lambda item: (item[0], -self.events[item[1]].duration, item[1]))
            following = [other for other in remaining if other != index]
            for _, place in choices:
                nodes += 1
                if state.add(index, place):
                    result = visit(following)
                    if result is not None:
                        return result
                    state.remove(index)
                if nodes >= self.max_nodes:
                    break
            return None

        return visit(pending)

    def _teacher(self, state: _State, rng: random.Random) -> Schedule:
        targets = []
        for k, offering in enumerate(self.problem.offerings):
            old_teacher = state.teachers[k]
            contact = self.contacts[k]
            for teacher in offering.eligible_faculty:
                if teacher == old_teacher or state.load[teacher] + contact > self.faculty[teacher].max_weekly:
                    continue
                loads = dict(state.load)
                loads[old_teacher] -= contact
                loads[teacher] += contact
                targets.append((self._load_score(loads), rng.random(), k, teacher))
        targets.sort()
        original = state.schedule()
        for _, _, k, teacher in targets[:self.teacher_targets]:
            trial = state.copy()
            indices = self.offering_events[k]
            for index in indices:
                trial.remove(index)
            trial.teachers[k] = teacher
            candidate = self._reinsert(trial, indices, original, rng)
            if candidate is not None:
                return candidate.schedule()
        return original

    def _exchange(self, state: _State, rng: random.Random) -> Schedule:
        targets = []
        offerings = self.problem.offerings
        for first, a in enumerate(offerings):
            ta = state.teachers[first]
            for second in range(first + 1, len(offerings)):
                tb = state.teachers[second]
                if ta == tb or tb not in a.eligible_faculty or ta not in offerings[second].eligible_faculty:
                    continue
                loads = dict(state.load)
                loads[ta] += self.contacts[second] - self.contacts[first]
                loads[tb] += self.contacts[first] - self.contacts[second]
                if loads[ta] > self.faculty[ta].max_weekly or loads[tb] > self.faculty[tb].max_weekly:
                    continue
                targets.append((self._load_score(loads), rng.random(), first, second))
        targets.sort()
        original = state.schedule()
        for _, _, first, second in targets[:self.teacher_targets]:
            trial = state.copy()
            indices = self.offering_events[first] + self.offering_events[second]
            for index in indices:
                trial.remove(index)
            trial.teachers[first], trial.teachers[second] = trial.teachers[second], trial.teachers[first]
            candidate = self._reinsert(trial, indices, original, rng)
            if candidate is not None:
                return candidate.schedule()
        return original

    def propose(self, schedule: Schedule, rng: random.Random, mode: str | int | None = None) -> Schedule:
        """Return a complete feasible neighbor, or the unchanged feasible input."""
        if mode is None:
            mode = rng.randrange(len(self.MODES))
        if type(mode) is int and 0 <= mode < len(self.MODES):
            mode = self.MODES[mode]
        if mode not in self.MODES:
            raise ValueError(f"Unknown feasible-neighborhood mode {mode!r}; choose {self.MODES}")
        state = self._state(schedule)
        if not self.events:
            return schedule
        operator = {"relocate": self._relocate, "room": self._room, "swap": self._swap,
                    "teacher": self._teacher, "exchange": self._exchange}[mode]
        candidate = operator(state, rng)
        self.last_diagnostics = {"mode": mode, "changed": candidate != schedule,
                                 "full_objective_evaluations": 0, "max_backtrack_nodes": self.max_nodes}
        return candidate

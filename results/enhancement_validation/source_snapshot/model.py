"""Typed, JSON-serializable problem and schedule representation.

All student groups are atomic, disjoint cohorts. An event can involve several
groups, in which case every group is occupied and their sizes are summed.
Time is a zero-based flattened index ``day * periods_per_day + period``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import cached_property
from typing import Any


@dataclass(frozen=True)
class Group:
    id: str
    size: int


@dataclass(frozen=True)
class Room:
    id: str
    capacity: int
    kind: str
    unavailable: tuple[int, ...] = ()


@dataclass(frozen=True)
class Faculty:
    id: str
    max_weekly: int
    max_daily: int
    unavailable: tuple[int, ...] = ()


@dataclass(frozen=True)
class Offering:
    id: str
    groups: tuple[str, ...]
    eligible_faculty: tuple[str, ...]
    sessions: int
    duration: int
    room_kind: str
    distinct_days: bool = True


@dataclass(frozen=True)
class Event:
    id: str
    offering_id: str
    groups: tuple[str, ...]
    duration: int
    room_kind: str
    size: int


@dataclass(frozen=True)
class Problem:
    name: str
    days: tuple[str, ...]
    periods_per_day: int
    lunch_periods: tuple[int, ...]
    groups: tuple[Group, ...]
    rooms: tuple[Room, ...]
    faculty: tuple[Faculty, ...]
    offerings: tuple[Offering, ...]
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    @cached_property
    def events(self) -> tuple[Event, ...]:
        sizes = {group.id: group.size for group in self.groups}
        return tuple(
            Event(
                f"{offering.id}:{session + 1}", offering.id,
                offering.groups, offering.duration, offering.room_kind,
                sum(sizes[group] for group in offering.groups),
            )
            for offering in self.offerings
            for session in range(offering.sessions)
        )

    @property
    def total_periods(self) -> int:
        """Number of grid cells, including lunch, used as the time-index bound."""
        return len(self.days) * self.periods_per_day

    @property
    def teaching_periods(self) -> tuple[int, ...]:
        return tuple(
            time for time in range(self.total_periods)
            if time % self.periods_per_day not in self.lunch_periods
        )


@dataclass(frozen=True)
class Placement:
    start: int
    room: str


@dataclass(frozen=True)
class Schedule:
    placements: tuple[Placement | None, ...]
    teachers: tuple[str, ...]


def valid_starts(problem: Problem, event: Event) -> tuple[int, ...]:
    """Starts respecting day boundaries and lunch; resources checked separately."""
    return tuple(
        day * problem.periods_per_day + period
        for day in range(len(problem.days))
        for period in range(problem.periods_per_day - event.duration + 1)
        if all(
            occupied not in problem.lunch_periods
            for occupied in range(period, period + event.duration)
        )
    )


def compatible_rooms(problem: Problem, event: Event) -> tuple[str, ...]:
    """Capacity and exact kind match; availability depends on the placement."""
    return tuple(
        room.id for room in problem.rooms
        if room.kind == event.room_kind and room.capacity >= event.size
    )


def validate_problem(problem: Problem) -> None:
    """Reject malformed data, while permitting well-formed infeasible instances.

    Empty domains and impossible demand are scheduling infeasibility, not schema
    failures. IDs/references, dimensions, and numeric ranges are schema failures.
    """
    def positive(value: Any, label: str) -> None:
        if type(value) is not int or value <= 0:
            raise ValueError(f"{label} must be a positive integer")

    positive(problem.periods_per_day, "periods_per_day")
    if not problem.days or any(not isinstance(day, str) or not day for day in problem.days) or len(set(problem.days)) != len(problem.days):
        raise ValueError("days must contain unique nonempty string labels")
    for collection, label in (
        (problem.groups, "group"), (problem.rooms, "room"),
        (problem.faculty, "faculty"), (problem.offerings, "offering"),
    ):
        ids = [entity.id for entity in collection]
        if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"{label} IDs must be nonempty and unique")
    if len(set(problem.lunch_periods)) != len(problem.lunch_periods) or any(
        type(p) is not int or not 0 <= p < problem.periods_per_day
        for p in problem.lunch_periods
    ):
        raise ValueError("lunch_periods must be unique within-day indices")
    for group in problem.groups:
        positive(group.size, "group size")
    for resource in (*problem.rooms, *problem.faculty):
        if len(set(resource.unavailable)) != len(resource.unavailable) or any(
            type(t) is not int or not 0 <= t < problem.total_periods
            for t in resource.unavailable
        ):
            raise ValueError(f"invalid unavailable indices for {resource.id}")
    for room in problem.rooms:
        positive(room.capacity, "room capacity")
        if not isinstance(room.kind, str) or not room.kind:
            raise ValueError("room kind cannot be empty")
    for faculty in problem.faculty:
        positive(faculty.max_weekly, "faculty weekly limit")
        positive(faculty.max_daily, "faculty daily limit")
    group_ids = {group.id for group in problem.groups}
    faculty_ids = {faculty.id for faculty in problem.faculty}
    for offering in problem.offerings:
        positive(offering.sessions, "offering sessions")
        positive(offering.duration, "offering duration")
        if not offering.groups or len(set(offering.groups)) != len(offering.groups):
            raise ValueError("offering groups must be nonempty and unique")
        if not set(offering.groups) <= group_ids:
            raise ValueError(f"unknown group in {offering.id}")
        if len(set(offering.eligible_faculty)) != len(offering.eligible_faculty):
            raise ValueError("eligible_faculty must be unique")
        if not set(offering.eligible_faculty) <= faculty_ids:
            raise ValueError(f"unknown eligible faculty in {offering.id}")
        if not isinstance(offering.room_kind, str) or not offering.room_kind or type(offering.distinct_days) is not bool:
            raise ValueError("invalid room_kind or distinct_days")


def problem_to_dict(problem: Problem) -> dict[str, Any]:
    return {"schema_version": 1, **asdict(problem)}


def problem_from_dict(data: dict[str, Any]) -> Problem:
    data = dict(data)
    version = data.pop("schema_version", 1)
    if version != 1:
        raise ValueError(f"unsupported problem schema version {version}")
    data["days"] = tuple(data["days"])
    data["lunch_periods"] = tuple(data["lunch_periods"])
    data["groups"] = tuple(Group(**group) for group in data["groups"])
    data["rooms"] = tuple(Room(**{**room, "unavailable": tuple(room.get("unavailable", ()))}) for room in data["rooms"])
    data["faculty"] = tuple(Faculty(**{**faculty, "unavailable": tuple(faculty.get("unavailable", ()))}) for faculty in data["faculty"])
    data["offerings"] = tuple(Offering(**{
        **offering,
        "groups": tuple(offering["groups"]),
        "eligible_faculty": tuple(offering["eligible_faculty"]),
    }) for offering in data["offerings"])
    problem = Problem(**data)
    validate_problem(problem)
    return problem


def schedule_to_dict(schedule: Schedule) -> dict[str, Any]:
    return {"schema_version": 1, **asdict(schedule)}


def schedule_from_dict(data: dict[str, Any]) -> Schedule:
    """Read even malformed candidates; evaluator decides their feasibility."""
    version = data.get("schema_version", 1)
    if version != 1:
        raise ValueError(f"unsupported schedule schema version {version}")
    return Schedule(
        tuple(Placement(**placement) if placement is not None else None for placement in data["placements"]),
        tuple(data["teachers"]),
    )

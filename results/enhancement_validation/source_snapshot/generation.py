"""Deterministic, planted-feasible engineering-college instance generation.

The construction certificate is returned separately and never hidden in the
instance metadata. Optimizers must not use it. Availability is sampled only
after constructing the certificate, from slots unused by that resource.
"""

from __future__ import annotations

from dataclasses import replace
import math
import random
from typing import Any

from .model import Faculty, Group, Offering, Placement, Problem, Room, Schedule, validate_problem


PRESETS: dict[str, dict[str, int]] = {
    "small": {"groups": 2, "rooms": 5, "faculty": 6, "target_events": 40},
    "medium": {"groups": 8, "rooms": 12, "faculty": 20, "target_events": 150},
    "large": {"groups": 20, "rooms": 25, "faculty": 50, "target_events": 400},
}

_DEFAULTS: dict[str, Any] = {
    "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "periods_per_day": 8,
    "lunch_periods": [4],
    "theory_offerings_per_group": 6,
    "lab_offerings_per_group": 2,
    "lab_duration": 2,
    "max_weekly": 20,
    "max_daily": 6,
    "unavailability_rate": 0.08,
    "eligible_per_offering": 4,
    "construction_attempts": 40,
}


def _settings(size: str, config: dict[str, Any] | None) -> dict[str, Any]:
    if size not in PRESETS:
        raise ValueError(f"Unknown size {size!r}; choose from {tuple(PRESETS)}")
    given = dict(config or {})
    allowed = set(_DEFAULTS) | set(PRESETS[size]) | {"theory_sessions"}
    unknown = set(given) - allowed
    if unknown:
        raise ValueError(f"Unknown generator parameters: {sorted(unknown)}")
    cfg = {**_DEFAULTS, **PRESETS[size], **given}
    if "groups" in given and "target_events" not in given:
        cfg["target_events"] = cfg["groups"] * (
            cfg["theory_offerings_per_group"] * given.get("theory_sessions", 3)
            + cfg["lab_offerings_per_group"]
        )
    if "theory_sessions" in given:
        if "target_events" in given:
            raise ValueError("Choose theory_sessions or target_events, not both")
        cfg["target_events"] = cfg["groups"] * (
            cfg["theory_offerings_per_group"] * given["theory_sessions"]
            + cfg["lab_offerings_per_group"]
        )
    positive = (
        "groups", "rooms", "faculty", "target_events", "periods_per_day",
        "theory_offerings_per_group", "lab_duration", "max_weekly",
        "max_daily", "eligible_per_offering", "construction_attempts",
    )
    for key in positive:
        if isinstance(cfg[key], bool) or not isinstance(cfg[key], int) or cfg[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    labs = cfg["lab_offerings_per_group"]
    if isinstance(labs, bool) or not isinstance(labs, int) or labs < 0:
        raise ValueError("lab_offerings_per_group must be a nonnegative integer")
    if not isinstance(cfg["days"], (list, tuple)) or not cfg["days"]:
        raise ValueError("days must be a nonempty sequence of unique day names")
    if len(set(cfg["days"])) != len(cfg["days"]):
        raise ValueError("days must be unique")
    if not isinstance(cfg["lunch_periods"], (list, tuple)) or any(
        isinstance(p, bool) or not isinstance(p, int) or not 0 <= p < cfg["periods_per_day"]
        for p in cfg["lunch_periods"]
    ):
        raise ValueError("lunch_periods must contain valid zero-based period indices")
    if len(set(cfg["lunch_periods"])) != len(cfg["lunch_periods"]):
        raise ValueError("lunch_periods must be unique")
    rate = cfg["unavailability_rate"]
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 <= rate < 1:
        raise ValueError("unavailability_rate must be in [0, 1)")
    if labs and cfg["rooms"] < 2:
        raise ValueError("At least two rooms are needed when classrooms and labs are required")
    cfg["days"] = list(cfg["days"])
    cfg["lunch_periods"] = sorted(cfg["lunch_periods"])
    return cfg


def generate_instance(
    size: str = "small", seed: int = 0, config: dict[str, Any] | None = None,
) -> tuple[Problem, Schedule]:
    """Return a synthetic instance and an independently checkable certificate.

    Parameters override the selected preset. ``target_events`` distributes
    theory sessions as evenly as possible across groups and offerings; every
    theory offering has at least one session and no more than one per day.
    ``theory_sessions`` instead fixes the sessions per theory offering. Groups
    are disjoint full cohorts; laboratory events use the entire cohort. Room
    kinds are exact: classrooms cannot substitute for laboratories.

    This is a planted-feasible distribution, not an unbiased sample of all
    timetabling instances. A bounded constructive restart can fail for severe
    custom settings; failure does not prove those settings infeasible.
    """
    cfg = _settings(size, config)
    rng = random.Random(seed)
    n_groups, n_rooms, n_faculty = (cfg[k] for k in ("groups", "rooms", "faculty"))
    periods = cfg["periods_per_day"]
    n_days = len(cfg["days"])
    lunch = set(cfg["lunch_periods"])
    available_slots = tuple(
        d * periods + p for d in range(n_days) for p in range(periods) if p not in lunch
    )
    theory_count = cfg["theory_offerings_per_group"]
    lab_count = cfg["lab_offerings_per_group"]
    minimum_events = n_groups * (theory_count + lab_count)
    maximum_events = n_groups * (theory_count * n_days + lab_count)
    if not minimum_events <= cfg["target_events"] <= maximum_events:
        raise ValueError(
            f"target_events must be in [{minimum_events}, {maximum_events}] for these offerings/days"
        )
    groups = tuple(Group(f"G{i+1:02d}", (24, 36, 48, 54)[i % 4]) for i in range(n_groups))
    class_count = n_rooms if lab_count == 0 else min(n_rooms - 1, max(1, math.ceil(n_rooms * 0.64)))
    rooms = tuple(
        Room(
            f"R{i+1:02d}",
            (30, 45, 60, 90)[i % 4] if i < class_count else (30, 45, 60, 90)[(i - class_count) % 4],
            "classroom" if i < class_count else "lab",
        ) for i in range(n_rooms)
    )
    # Ensure each kind has a room that can seat the largest generated cohort.
    largest = max(g.size for g in groups)
    for kind in ("classroom", "lab"):
        indices = [i for i, r in enumerate(rooms) if r.kind == kind]
        if indices and max(rooms[i].capacity for i in indices) < largest:
            i = indices[-1]
            rooms = rooms[:i] + (replace(rooms[i], capacity=60 if largest <= 60 else 90),) + rooms[i+1:]
    faculty = tuple(Faculty(f"F{i+1:02d}", cfg["max_weekly"], cfg["max_daily"]) for i in range(n_faculty))
    offerings: list[Offering] = []
    base, remainder = divmod(cfg["target_events"], n_groups)
    for gi, group in enumerate(groups):
        group_events = base + (gi < remainder)
        theory_events = group_events - lab_count
        session_base, session_extra = divmod(theory_events, theory_count)
        for si in range(theory_count):
            offerings.append(Offering(
                f"{group.id}-T{si+1}", (group.id,), tuple(f.id for f in faculty),
                session_base + (si < session_extra), 1, "classroom", True,
            ))
        for si in range(lab_count):
            offerings.append(Offering(
                f"{group.id}-L{si+1}", (group.id,), tuple(f.id for f in faculty),
                1, cfg["lab_duration"], "lab", False,
            ))
    total_contact = sum(k.sessions * k.duration for k in offerings)
    if total_contact > sum(f.max_weekly for f in faculty):
        raise ValueError("Aggregate weekly teaching capacity is smaller than required contact periods")
    for g in groups:
        required = sum(k.sessions * k.duration for k in offerings if g.id in k.groups)
        if required > len(available_slots):
            raise ValueError(f"Group {g.id} requires {required} periods but only {len(available_slots)} exist")
    starts_by_length = {
        length: tuple(
            d * periods + p
            for d in range(n_days)
            for p in range(periods - length + 1)
            if all(q not in lunch for q in range(p, p + length))
        ) for length in {k.duration for k in offerings}
    }
    if any(not starts for starts in starts_by_length.values()):
        raise ValueError("A requested event duration cannot fit between lunch/day boundaries")
    group_size = {g.id: g.size for g in groups}
    room_options = {
        k.id: [r.id for r in rooms if r.kind == k.room_kind and r.capacity >= group_size[k.groups[0]]]
        for k in offerings
    }
    if any(not rs for rs in room_options.values()):
        raise ValueError("No suitable room exists for a generated offering")

    certificate: dict[str, list[Placement]] | None = None
    chosen_teacher: dict[str, str] = {}
    for _ in range(cfg["construction_attempts"]):
        room_busy = {r.id: set() for r in rooms}
        group_busy = {g.id: set() for g in groups}
        faculty_busy = {f.id: set() for f in faculty}
        faculty_load = {f.id: 0 for f in faculty}
        daily_load = {f.id: [0] * n_days for f in faculty}
        placed: dict[str, list[Placement]] = {}
        teachers: dict[str, str] = {}
        # Labs must reserve contiguous blocks before the grid becomes fragmented.
        order = list(offerings)
        rng.shuffle(order)
        order.sort(key=lambda k: (-k.duration, -group_size[k.groups[0]], -k.sessions))
        success = True
        for k in order:
            candidates = list(faculty)
            rng.shuffle(candidates)
            candidates.sort(key=lambda f: faculty_load[f.id] + rng.random() * 2)
            local: list[Placement] | None = None
            teacher_id: str | None = None
            for f in candidates:
                if faculty_load[f.id] + k.sessions * k.duration > f.max_weekly:
                    continue
                proposal: list[Placement] = []
                used_days: set[int] = set()
                for _session in range(k.sessions):
                    options: list[tuple[int, str]] = []
                    for start in starts_by_length[k.duration]:
                        day = start // periods
                        if k.distinct_days and day in used_days:
                            continue
                        own_daily = sum(k.duration for p in proposal if p.start // periods == day)
                        if daily_load[f.id][day] + own_daily + k.duration > f.max_daily:
                            continue
                        occupied = set(range(start, start + k.duration))
                        if occupied & faculty_busy[f.id]:
                            continue
                        if any(occupied & group_busy[g] for g in k.groups):
                            continue
                        # Non-distinct-day offerings may still not overlap themselves.
                        if any(occupied & set(range(p.start, p.start + k.duration)) for p in proposal):
                            continue
                        for room_id in room_options[k.id]:
                            if not occupied & room_busy[room_id]:
                                options.append((start, room_id))
                    if not options:
                        break
                    start, room_id = rng.choice(options)
                    proposal.append(Placement(start, room_id))
                    used_days.add(start // periods)
                if len(proposal) == k.sessions:
                    local, teacher_id = proposal, f.id
                    break
            if local is None or teacher_id is None:
                success = False
                break
            placed[k.id] = local
            teachers[k.id] = teacher_id
            faculty_load[teacher_id] += k.sessions * k.duration
            for p in local:
                occupied = set(range(p.start, p.start + k.duration))
                room_busy[p.room].update(occupied)
                faculty_busy[teacher_id].update(occupied)
                daily_load[teacher_id][p.start // periods] += k.duration
                for group_id in k.groups:
                    group_busy[group_id].update(occupied)
        if success:
            certificate, chosen_teacher = placed, teachers
            break
    if certificate is None:
        raise ValueError(
            "Bounded planted-witness construction failed; this is not a proof of infeasibility. "
            "Increase rooms/faculty/limits, reduce sessions, or change the seed."
        )

    # Qualification sets contain genuine alternatives; retain the certificate's
    # teacher and ensure no listed faculty is structurally irrelevant to balance.
    eligible: dict[str, set[str]] = {}
    for k in offerings:
        others = [f.id for f in faculty if f.id != chosen_teacher[k.id]]
        count = min(len(others), cfg["eligible_per_offering"] - 1)
        eligible[k.id] = {chosen_teacher[k.id], *rng.sample(others, count)}
    represented = set().union(*eligible.values())
    for f in faculty:
        if f.id not in represented:
            k = rng.choice(offerings)
            eligible[k.id].add(f.id)
    offerings = [replace(k, eligible_faculty=tuple(sorted(eligible[k.id]))) for k in offerings]

    def blocked(occupied: set[int]) -> tuple[int, ...]:
        return tuple(s for s in available_slots if s not in occupied and rng.random() < cfg["unavailability_rate"])

    rooms = tuple(replace(r, unavailable=blocked(room_busy[r.id])) for r in rooms)
    faculty = tuple(replace(f, unavailable=blocked(faculty_busy[f.id])) for f in faculty)
    problem = Problem(
        name=f"synthetic-{size}-{seed}", days=tuple(cfg["days"]), periods_per_day=periods,
        lunch_periods=tuple(cfg["lunch_periods"]), groups=groups, rooms=rooms,
        faculty=faculty, offerings=tuple(offerings),
        metadata={
            "synthetic": True, "generator_version": 1, "seed": seed,
            "preset": size, "config": cfg,
            "sampling": "planted feasible; availability sampled from resource-free certificate slots",
            "group_assumption": "disjoint cohorts; full-cohort labs; no split-batch inference",
        },
    )
    validate_problem(problem)
    placements = tuple(p for k in offerings for p in certificate[k.id])
    schedule = Schedule(placements, tuple(chosen_teacher[k.id] for k in offerings))
    # Defensive independent validation is intentionally kept in the generator.
    from .evaluation import evaluate

    evaluation = evaluate(problem, schedule)
    if not evaluation.feasible:
        raise RuntimeError(f"Internal planted-certificate validation failed: {evaluation.violations}")
    return problem, schedule

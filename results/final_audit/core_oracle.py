#!/usr/bin/env python3
"""Read-only independent core audit; does not modify project source or results.

Run from the repository root:
  PYTHONPATH=src python results/final_audit/core_oracle.py \
    > work/core_oracle_results.json

The feasibility/objective oracle below does not call project helpers or reuse
project constraint checks. Project evaluate is compared against that oracle.
"""
from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from itertools import product
from math import fsum, sqrt
from pathlib import Path
import json
import platform
import random
import subprocess
import sys

from timetable.evaluation import evaluate
from timetable.faculty_search import faculty_reassign
from timetable.feasible import FeasibleNeighborhood
from timetable.generation import generate_instance
from timetable.greedy import greedy
from timetable.model import Faculty, Group, Offering, Placement, Problem, Room, Schedule, compatible_rooms, valid_starts

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATHS = ["src/timetable/model.py", "src/timetable/generation.py", "src/timetable/evaluation.py",
                "src/timetable/feasible.py", "src/timetable/faculty_search.py"]


def source_fingerprints():
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_PATHS}


def oracle(problem, schedule):
    """Independent resource-set feasibility and occupied-span objective oracle."""
    offerings = {offering.id: (index, offering) for index, offering in enumerate(problem.offerings)}
    rooms = {room.id: room for room in problem.rooms}
    faculty = {person.id: person for person in problem.faculty}
    if len(schedule.placements) != len(problem.events) or len(schedule.teachers) != len(problem.offerings):
        return False, None
    occupied = defaultdict(set)
    teaching = defaultdict(set)
    load = defaultdict(int)
    daily = defaultdict(int)
    offering_days = defaultdict(list)
    waste = []
    for index, offering in enumerate(problem.offerings):
        teacher = schedule.teachers[index]
        if teacher not in offering.eligible_faculty or teacher not in faculty:
            return False, None
        load[teacher] += offering.sessions * offering.duration
    if any(load[person.id] > person.max_weekly for person in problem.faculty):
        return False, None
    for event, placement in zip(problem.events, schedule.placements):
        if placement is None or type(placement.start) is not int or placement.room not in rooms:
            return False, None
        start = placement.start
        day, period = divmod(start, problem.periods_per_day)
        room = rooms[placement.room]
        index, offering = offerings[event.offering_id]
        teacher = faculty[schedule.teachers[index]]
        if start < 0 or start >= problem.total_periods or period + event.duration > problem.periods_per_day:
            return False, None
        periods = range(period, period + event.duration)
        if (any(value in problem.lunch_periods for value in periods)
                or room.capacity < event.size or room.kind != event.room_kind):
            return False, None
        slots = set(range(start, start + event.duration))
        if slots & set(room.unavailable) or slots & set(teacher.unavailable):
            return False, None
        resources = [("r", room.id), ("f", teacher.id)] + [("g", group) for group in event.groups]
        for resource in resources:
            if slots & occupied[resource]:
                return False, None
            occupied[resource] |= slots
        for resource in [("f", teacher.id)] + [("g", group) for group in event.groups]:
            teaching[resource, day].update(periods)
        daily[teacher.id, day] += event.duration
        offering_days[offering.id].append(day)
        waste.append(event.duration * (room.capacity - event.size) / room.capacity)
    if any(hours > faculty[teacher].max_daily for (teacher, _day), hours in daily.items()):
        return False, None
    for offering in problem.offerings:
        if offering.distinct_days and len(set(offering_days[offering.id])) < len(offering_days[offering.id]):
            return False, None
    gap = 0.0
    for ((kind, _resource), _day), periods in teaching.items():
        gap += (1.0 if kind == "g" else 0.5) * sum(
            period not in periods and period not in problem.lunch_periods
            for period in range(min(periods), max(periods) + 1)
        )
    ratios = [load[person.id] / person.max_weekly for person in problem.faculty]
    mean = fsum(ratios) / len(ratios) if ratios else 0.0
    return True, (
        gap,
        fsum(waste) / sum(event.duration for event in problem.events) if problem.events else 0.0,
        sqrt(fsum((ratio - mean) ** 2 for ratio in ratios) / len(ratios)) if ratios else 0.0,
    )


def audit_evaluator():
    problem = Problem(
        "independent-audit", ("M", "T"), 5, (2,),
        (Group("a", 10), Group("b", 15)),
        (Room("c", 30, "classroom", (5,)), Room("l", 30, "lab", (8,)), Room("h", 60, "classroom")),
        (Faculty("x", 5, 3, (6,)), Faculty("y", 4, 2, (1,))),
        (Offering("theory", ("a",), ("x", "y"), 2, 1, "classroom", True),
         Offering("shared", ("a", "b"), ("x", "y"), 1, 1, "classroom"),
         Offering("lab", ("b",), ("x", "y"), 1, 2, "lab", False)),
    )
    counts = {"random_seed": 93454, "random_candidates": 0, "random_feasible": 0,
              "domain_candidates": 0, "domain_feasible": 0,
              "feasibility_mismatches": 0, "objective_mismatches": 0}

    def check(schedule, category):
        valid, objectives = oracle(problem, schedule)
        actual = evaluate(problem, schedule)
        counts[f"{category}_candidates"] += 1
        assert actual.feasible == valid, (schedule, actual, valid)
        if valid:
            counts[f"{category}_feasible"] += 1
            assert actual.objectives == objectives, (actual.objectives, objectives)

    rng = random.Random(counts["random_seed"])
    starts = [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    for _ in range(8000):
        schedule = Schedule(
            tuple(Placement(rng.choice(starts), rng.choice(problem.rooms).id) for _event in problem.events),
            tuple(rng.choice(offering.eligible_faculty) for offering in problem.offerings),
        )
        check(schedule, "random")
    # Exhaust the product of individually valid time/capacity/type domains.
    # Resource availability, clashes, workloads and day rules remain to check.
    for teachers in product(*(offering.eligible_faculty for offering in problem.offerings)):
        for starts in product(*(valid_starts(problem, event) for event in problem.events)):
            for room_ids in product(*(compatible_rooms(problem, event) for event in problem.events)):
                schedule = Schedule(tuple(Placement(start, room) for start, room in zip(starts, room_ids)), teachers)
                check(schedule, "domain")
    counts["total_candidates"] = counts["random_candidates"] + counts["domain_candidates"]
    counts["total_feasible_objective_checks"] = counts["random_feasible"] + counts["domain_feasible"]
    assert counts["total_candidates"] == 139072
    assert counts["total_feasible_objective_checks"] == 5068
    return counts


def audit_faculty_search():
    records = []
    config = {"groups": 2, "rooms": 4, "faculty": 3,
              "theory_offerings_per_group": 2, "lab_offerings_per_group": 1,
              "theory_sessions": 2, "max_weekly": 10, "max_daily": 5}
    for seed in (9311, 9312, 9313):
        problem, _unused_certificate = generate_instance("small", seed, config)
        schedule = greedy(problem, seed, 2)
        optimum, worst = float("inf"), -1.0
        worst_schedule = None
        enumerated = feasible = 0
        for teachers in product(*(offering.eligible_faculty for offering in problem.offerings)):
            candidate = replace(schedule, teachers=teachers)
            assessment = evaluate(problem, candidate)
            enumerated += 1
            if assessment.feasible:
                feasible += 1
                optimum = min(optimum, assessment.objectives[2])
                if assessment.objectives[2] > worst:
                    worst, worst_schedule = assessment.objectives[2], candidate
        assert worst_schedule is not None and worst > optimum
        diagnostics = {}
        result = faculty_reassign(problem, worst_schedule, random.Random(seed),
                                  max_offerings=100, max_nodes=100000, diagnostics=diagnostics)
        assessment = evaluate(problem, result)
        assert assessment.feasible and assessment.objectives[2] == optimum
        assert diagnostics["nodes"] > 0 and diagnostics["optimal_within_selected"]
        records.append({"seed": seed, "enumerated_assignments": enumerated,
                        "feasible_assignments": feasible, "initial_sd": worst,
                        "exhaustive_min_sd": optimum, "returned_sd": assessment.objectives[2],
                        "branch_nodes": diagnostics["nodes"],
                        "complete_assignments": diagnostics["complete_assignments"],
                        "optimal_within_selected": diagnostics["optimal_within_selected"]})
    return records


def audit_multiple_lunch():
    records = []
    for seed in (9321, 9322):
        problem, _unused_certificate = generate_instance("small", seed, {"periods_per_day": 9, "lunch_periods": [3, 6]})
        schedule = greedy(problem, seed, 2)
        neighborhood = FeasibleNeighborhood(problem)
        rng = random.Random(seed)
        changed = 0
        for trial in range(100):
            candidate = neighborhood.propose(schedule, rng, trial % 5)
            assert oracle(problem, candidate)[0] and evaluate(problem, candidate).feasible
            changed += candidate != schedule
            schedule = candidate
        records.append({"seed": seed, "periods_per_day": 9, "lunch_periods": [3, 6],
                        "proposals_checked": 100, "changed_proposals": changed, "invalid_proposals": 0})
    return records


def main():
    fingerprints = source_fingerprints()
    output = {"audit": "independent read-only core oracle", "python": sys.version,
              "platform": platform.platform(),
              "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "source_sha256": fingerprints,
              "evaluator_oracle": audit_evaluator(), "faculty_exhaustive": audit_faculty_search(),
              "multiple_lunch": audit_multiple_lunch()}
    assert fingerprints == source_fingerprints(), "Core source changed during audit"
    output["source_unchanged_during_run"] = True
    output["passed"] = True
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

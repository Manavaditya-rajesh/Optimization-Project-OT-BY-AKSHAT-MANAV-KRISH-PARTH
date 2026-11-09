"""Independent verification of bounded fixed-time batch faculty reassignment."""

from dataclasses import replace
from itertools import product
import random

import pytest

from timetable.evaluation import evaluate
from timetable.faculty_search import faculty_reassign
from timetable.generation import generate_instance
from timetable.greedy import greedy
from timetable.model import Faculty, Group, Offering, Placement, Problem, Room, Schedule


def blocked_exchange_problem():
    problem = Problem(
        "blocked-exchange", ("Monday", "Tuesday"), 4, (),
        (Group("G1", 20), Group("G2", 20)),
        (Room("R1", 30, "lab"), Room("R2", 30, "lab")),
        (Faculty("F1", 6, 4), Faculty("F2", 6, 4)),
        (
            Offering("A", ("G1",), ("F1", "F2"), 2, 2, "lab"),
            Offering("B", ("G1",), ("F1",), 1, 2, "lab"),
            Offering("C", ("G2",), ("F1", "F2"), 1, 2, "lab"),
        ),
    )
    schedule = Schedule(
        (Placement(0, "R1"), Placement(4, "R1"), Placement(2, "R1"), Placement(0, "R2")),
        ("F1", "F1", "F2"),
    )
    return problem, schedule


def test_joint_exchange_escapes_a_single_gene_feasibility_trap():
    problem, schedule = blocked_exchange_problem()
    original = evaluate(problem, schedule)
    assert original.feasible
    assert original.objectives[2] == pytest.approx(1 / 3)
    for k, offering in enumerate(problem.offerings):
        for teacher in offering.eligible_faculty:
            if teacher == schedule.teachers[k]:
                continue
            teachers = list(schedule.teachers)
            teachers[k] = teacher
            assert not evaluate(problem, replace(schedule, teachers=tuple(teachers))).feasible
    diagnostics = {}
    proposed = faculty_reassign(problem, schedule, random.Random(9000), diagnostics=diagnostics)
    improved = evaluate(problem, proposed)
    assert improved.feasible
    assert proposed.placements == schedule.placements
    assert proposed.teachers == ("F2", "F1", "F1")
    assert improved.objectives[0:2] == original.objectives[0:2]
    assert improved.objectives[2] == 0
    assert diagnostics["improved"]
    assert diagnostics["optimal_within_selected"]
    assert diagnostics["full_evaluations"] == 0


def test_completed_neighborhood_search_matches_exhaustive_teacher_enumeration():
    problem, schedule = blocked_exchange_problem()
    exhaustive = []
    for teachers in product(*(k.eligible_faculty for k in problem.offerings)):
        candidate = replace(schedule, teachers=tuple(teachers))
        assessment = evaluate(problem, candidate)
        if assessment.feasible:
            exhaustive.append(assessment.objectives[2])
    result = faculty_reassign(problem, schedule, random.Random(9001))
    assert evaluate(problem, result).objectives[2] == min(exhaustive)


@pytest.mark.parametrize("size", ["small", "medium", "large"])
@pytest.mark.parametrize("seed", [9000, 9001, 9002])
def test_batch_reassignment_preserves_all_constraints_and_rooms_times(size, seed):
    problem, _unused_certificate = generate_instance(size, seed)
    initial = greedy(problem, seed=seed, restarts=1)
    before = evaluate(problem, initial)
    diagnostics = {}
    candidate = faculty_reassign(problem, initial, random.Random(seed), diagnostics=diagnostics)
    assessment = evaluate(problem, candidate)
    assert assessment.feasible, assessment.violations
    assert candidate.placements == initial.placements
    assert assessment.objectives[1] == before.objectives[1]
    assert assessment.objectives[2] <= before.objectives[2]
    assert diagnostics["nodes"] <= diagnostics["max_nodes"]
    assert diagnostics["full_evaluations"] == 0


def test_deterministic_node_budget_and_rng_reproduce_assignment_and_search_counts():
    problem, _ = generate_instance("medium", 9010)
    initial = greedy(problem, seed=9010, restarts=1)
    first_meta, second_meta = {}, {}
    first = faculty_reassign(problem, initial, random.Random(9010), max_nodes=7, diagnostics=first_meta)
    second = faculty_reassign(problem, initial, random.Random(9010), max_nodes=7, diagnostics=second_meta)
    assert first == second
    assert first_meta["nodes"] <= 7
    assert {k: v for k, v in first_meta.items() if k != "runtime"} == {
        k: v for k, v in second_meta.items() if k != "runtime"
    }
    assert evaluate(problem, first).feasible


def test_unequal_weekly_limits_and_malformed_input_are_explicit_safe_noops():
    problem, schedule = blocked_exchange_problem()
    unequal = replace(problem, faculty=(problem.faculty[0], replace(problem.faculty[1], max_weekly=7)))
    diagnostics = {}
    assert faculty_reassign(unequal, schedule, random.Random(9000), diagnostics=diagnostics) == schedule
    assert diagnostics["status"] == "unequal_weekly_limits"
    partial = replace(schedule, placements=(None, *schedule.placements[1:]))
    diagnostics = {}
    assert faculty_reassign(problem, partial, random.Random(9000), diagnostics=diagnostics) == partial
    assert diagnostics["status"] == "invalid_incoming_assignment"


def test_faculty_availability_and_daily_limits_can_prevent_exchange():
    problem, schedule = blocked_exchange_problem()
    # F2 cannot cover the second session of A, even though its first session fits.
    blocked = replace(problem, faculty=(problem.faculty[0], replace(problem.faculty[1], unavailable=(4,))))
    assert evaluate(blocked, schedule).feasible
    assert faculty_reassign(blocked, schedule, random.Random(9000)) == schedule
    # An otherwise balancing exchange would give F2 four hours on Monday,
    # exceeding its two-hour daily maximum while the incoming assignment fits.
    limited = replace(problem,
        offerings=(replace(problem.offerings[0], distinct_days=False), *problem.offerings[1:]),
        faculty=(problem.faculty[0], replace(problem.faculty[1], max_daily=2)),
    )
    clustered = replace(schedule, placements=(Placement(0, "R1"), Placement(2, "R1"),
                                               Placement(4, "R1"), Placement(0, "R2")))
    assert evaluate(limited, clustered).feasible
    assert faculty_reassign(limited, clustered, random.Random(9000)) == clustered
    invalid = replace(problem, faculty=(problem.faculty[0], replace(problem.faculty[1], max_daily=1)))
    diagnostics = {}
    assert faculty_reassign(invalid, schedule, random.Random(9000), diagnostics=diagnostics) == schedule
    assert diagnostics["status"] == "invalid_incoming_assignment"


@pytest.mark.parametrize("kwargs", [{"max_offerings": 0}, {"max_nodes": 0}, {"max_nodes": True}])
def test_invalid_bounds_rejected(kwargs):
    problem, schedule = blocked_exchange_problem()
    with pytest.raises(ValueError, match="positive integer"):
        faculty_reassign(problem, schedule, random.Random(9000), **kwargs)

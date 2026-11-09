"""Feasible variation is verified by the independent full constraint checker.

Randomized development cases use seeds >= 9000.  Targeted fixtures exercise
changes that require more than merely retaining an already feasible parent.
"""

import random

import pytest

from timetable import evaluation
from timetable.evaluation import evaluate
from timetable.feasible import FeasibleNeighborhood
from timetable.generation import generate_instance
from timetable.greedy import greedy
from timetable.model import Faculty, Group, Offering, Placement, Problem, Room, Schedule


MODES = ("relocate", "room", "swap", "teacher", "exchange")


@pytest.mark.parametrize("size", ("small", "medium", "large"))
@pytest.mark.parametrize("seed", (9001, 9002))
def test_repeated_variation_preserves_every_hard_constraint(size, seed):
    problem, _unused_certificate = generate_instance(size, seed)
    current = greedy(problem, seed=seed, restarts=2)
    assert evaluate(problem, current).feasible
    neighborhood = FeasibleNeighborhood(problem)
    rng = random.Random(seed)
    for _ in range(3):
        for mode in (*MODES, None):
            original = (current.placements, current.teachers)
            proposed = neighborhood.propose(current, rng, mode=mode)
            outcome = evaluate(problem, proposed)
            assert outcome.feasible, (mode, outcome.violations)
            assert len(proposed.placements) == len(problem.events)
            assert len(proposed.teachers) == len(problem.offerings)
            assert (current.placements, current.teachers) == original
            current = proposed


def test_seed_reproducibility_and_integer_modes():
    problem, _unused_certificate = generate_instance("small", 9011)
    initial = greedy(problem, seed=9012, restarts=1)
    neighborhood = FeasibleNeighborhood(problem)
    for index, name in enumerate(MODES):
        named = neighborhood.propose(initial, random.Random(9013), mode=name)
        numbered = neighborhood.propose(initial, random.Random(9013), mode=index)
        assert named == numbered
    first, second = initial, initial
    first_rng, second_rng = random.Random(9014), random.Random(9014)
    for _ in range(20):
        first = neighborhood.propose(first, first_rng)
        second = neighborhood.propose(second, second_rng)
        assert first == second


def test_relocation_can_remove_a_real_idle_gap():
    problem = Problem(
        "gap", ("Monday",), 6, (3,),
        (Group("g", 20),), (Room("r", 30, "classroom"),),
        (Faculty("f", 5, 5),),
        (Offering("a", ("g",), ("f",), 1, 1, "classroom"),
         Offering("b", ("g",), ("f",), 1, 1, "classroom")),
    )
    initial = Schedule((Placement(0, "r"), Placement(2, "r")), ("f", "f"))
    before = evaluate(problem, initial)
    assert before.feasible and before.objectives[0] > 0
    neighborhood = FeasibleNeighborhood(problem)
    proposals = [neighborhood.propose(initial, random.Random(seed), "relocate")
                 for seed in range(9020, 9036)]
    outcomes = [evaluate(problem, candidate) for candidate in proposals]
    assert all(outcome.feasible for outcome in outcomes)
    assert any(outcome.objectives[0] < before.objectives[0] for outcome in outcomes)


def test_room_selection_respects_capacity_kind_and_resource_availability():
    problem = Problem(
        "rooms", ("Monday",), 4, (2,), (Group("g", 20),),
        (Room("undersized", 10, "classroom"), Room("wrong-kind", 20, "lab"),
         Room("blocked", 20, "classroom", (0,)), Room("fit", 25, "classroom"),
         Room("large", 100, "classroom")),
        (Faculty("f", 3, 3),),
        (Offering("k", ("g",), ("f",), 1, 1, "classroom"),),
    )
    initial = Schedule((Placement(0, "large"),), ("f",))
    assert evaluate(problem, initial).feasible
    neighborhood = FeasibleNeighborhood(problem)
    proposals = [neighborhood.propose(initial, random.Random(seed), "room")
                 for seed in range(9040, 9056)]
    for proposal in proposals:
        assert evaluate(problem, proposal).feasible
        assert proposal.placements[0].start == 0
        assert proposal.placements[0].room in {"large", "fit"}
    assert any(proposal.placements[0].room == "fit" for proposal in proposals)


def test_teacher_change_reinserts_all_weekly_sessions_when_availability_changes():
    problem = Problem(
        "teacher-reinsertion", ("Monday", "Tuesday"), 4, (2,),
        (Group("g", 20),), (Room("r", 30, "classroom"),),
        (Faculty("f1", 4, 2), Faculty("f2", 4, 2, (0, 4))),
        (Offering("flexible", ("g",), ("f1", "f2"), 2, 1, "classroom"),
         Offering("fixed-teacher", ("g",), ("f1",), 1, 1, "classroom")),
    )
    initial = Schedule((Placement(0, "r"), Placement(4, "r"), Placement(1, "r")), ("f1", "f1"))
    before = evaluate(problem, initial)
    assert before.feasible
    neighborhood = FeasibleNeighborhood(problem)
    proposals = [neighborhood.propose(initial, random.Random(seed), "teacher")
                 for seed in range(9060, 9092)]
    for proposal in proposals:
        assert evaluate(problem, proposal).feasible
        assert proposal.teachers[1] == "f1"
    changed = [proposal for proposal in proposals if proposal.teachers[0] == "f2"]
    assert changed, "The neighborhood must reach a qualified teacher with different availability"
    for proposal in changed:
        assert proposal.placements[0].start != 0
        assert proposal.placements[1].start != 4
        assert evaluate(problem, proposal).objectives[2] < before.objectives[2]


def test_teacher_exchange_can_balance_unequal_offerings_with_reinsertion():
    problem = Problem(
        "teacher-exchange", ("Monday", "Tuesday", "Wednesday"), 4, (2,),
        (Group("g1", 20), Group("g2", 20), Group("g3", 20)),
        (Room("r1", 30, "classroom"), Room("r2", 30, "classroom")),
        (Faculty("f1", 4, 2), Faculty("f2", 4, 2, (4, 8))),
        (Offering("large", ("g1",), ("f1", "f2"), 3, 1, "classroom"),
         Offering("small", ("g2",), ("f1", "f2"), 1, 1, "classroom"),
         Offering("fixed", ("g3",), ("f1",), 1, 1, "classroom")),
    )
    initial = Schedule((Placement(0, "r1"), Placement(4, "r1"), Placement(8, "r1"),
                        Placement(0, "r2"), Placement(1, "r1")), ("f1", "f2", "f1"))
    before = evaluate(problem, initial)
    assert before.feasible
    neighborhood = FeasibleNeighborhood(problem)
    proposals = [neighborhood.propose(initial, random.Random(seed), "exchange")
                 for seed in range(9100, 9132)]
    assert all(evaluate(problem, proposal).feasible for proposal in proposals)
    exchanged = [proposal for proposal in proposals if proposal.teachers == ("f2", "f1", "f1")]
    assert exchanged
    assert all(evaluate(problem, proposal).objectives[2] < before.objectives[2] for proposal in exchanged)
    assert all(proposal.placements[1].start != 4 and proposal.placements[2].start != 8
               for proposal in exchanged)


def test_lab_swap_cannot_cross_lunch_or_change_room_kind():
    problem = Problem(
        "lab-lunch", ("Monday",), 6, (3,), (Group("g", 20),),
        (Room("lab", 20, "lab"), Room("class", 20, "classroom")),
        (Faculty("f", 4, 4),),
        (Offering("lab", ("g",), ("f",), 1, 2, "lab", False),
         Offering("lecture", ("g",), ("f",), 1, 1, "classroom")),
    )
    initial = Schedule((Placement(4, "lab"), Placement(2, "class")), ("f", "f"))
    assert evaluate(problem, initial).feasible
    neighborhood = FeasibleNeighborhood(problem)
    for seed in range(9140, 9156):
        proposal = neighborhood.propose(initial, random.Random(seed), "swap")
        assert evaluate(problem, proposal).feasible
        # The only changed start-swap puts the lab at 2, across lunch at 3.
        assert proposal == initial


def test_weekly_limit_prevents_splitting_one_offering_between_teachers():
    problem = Problem(
        "indivisible", ("Monday", "Tuesday"), 3, (), (Group("g", 10),),
        (Room("r", 20, "classroom"),),
        (Faculty("f1", 2, 1), Faculty("f2", 1, 1)),
        (Offering("k", ("g",), ("f1", "f2"), 2, 1, "classroom"),),
    )
    initial = Schedule((Placement(0, "r"), Placement(3, "r")), ("f1",))
    neighborhood = FeasibleNeighborhood(problem)
    for seed in range(9160, 9176):
        proposal = neighborhood.propose(initial, random.Random(seed), "teacher")
        assert evaluate(problem, proposal).feasible
        assert proposal.teachers == ("f1",)


def test_daily_limit_blocks_reassigning_an_indivisible_lab_block():
    problem = Problem(
        "daily-limit", ("Monday", "Tuesday"), 4, (2,), (Group("g", 10),),
        (Room("lab", 20, "lab"),),
        (Faculty("f1", 2, 2), Faculty("f2", 4, 1)),
        (Offering("k", ("g",), ("f1", "f2"), 1, 2, "lab", False),),
    )
    initial = Schedule((Placement(0, "lab"),), ("f1",))
    assert evaluate(problem, initial).feasible
    neighborhood = FeasibleNeighborhood(problem)
    for seed in range(9176, 9180):
        proposal = neighborhood.propose(initial, random.Random(seed), "teacher")
        assert evaluate(problem, proposal).feasible
        assert proposal.teachers == ("f1",)


def test_shared_event_occupies_every_group_and_sums_capacity():
    problem = Problem(
        "shared-groups", ("Monday", "Tuesday"), 6, (3,),
        (Group("g1", 10), Group("g2", 15)),
        (Room("small", 15, "classroom"), Room("large", 30, "classroom"),
         Room("lab", 30, "lab")),
        (Faculty("f1", 6, 4, (4,)), Faculty("f2", 6, 4, (10,))),
        (Offering("shared", ("g1", "g2"), ("f1", "f2"), 2, 1, "classroom"),
         Offering("g1-lab", ("g1",), ("f1",), 1, 2, "lab", False),
         Offering("g2-lecture", ("g2",), ("f2",), 1, 1, "classroom")),
    )
    current = Schedule((Placement(0, "large"), Placement(6, "large"),
                        Placement(1, "lab"), Placement(4, "small")), ("f1", "f1", "f2"))
    assert evaluate(problem, current).feasible
    neighborhood = FeasibleNeighborhood(problem)
    rng = random.Random(9199)
    for _ in range(4):
        for mode in MODES:
            current = neighborhood.propose(current, rng, mode)
            assert evaluate(problem, current).feasible
            assert current.placements[0].room == current.placements[1].room == "large"
            assert current.placements[0].start // 6 != current.placements[1].start // 6


def test_no_full_evaluator_calls_inside_neighborhood(monkeypatch):
    # Both the evaluator's module symbol and any directly imported symbol in
    # feasible.py are patched; the test retains an independent check reference.
    import timetable.feasible as feasible_module

    problem, _unused_certificate = generate_instance("small", 9180)
    current = greedy(problem, seed=9181, restarts=1)
    independent_check = evaluate

    def forbidden_evaluation(*_args, **_kwargs):
        raise AssertionError("Feasible variation must use direct resource checks, not hidden objective evaluations")

    monkeypatch.setattr(evaluation, "evaluate", forbidden_evaluation)
    monkeypatch.setattr(feasible_module, "evaluate", forbidden_evaluation, raising=False)
    neighborhood = FeasibleNeighborhood(problem)
    for index, mode in enumerate(MODES):
        current = neighborhood.propose(current, random.Random(9182 + index), mode)
        assert independent_check(problem, current).feasible


def test_empty_schedule_and_invalid_input_contract():
    empty = Problem("empty", ("Monday",), 2, (), (), (), (), ())
    schedule = Schedule((), ())
    neighborhood = FeasibleNeighborhood(empty)
    assert neighborhood.propose(schedule, random.Random(9190)) == schedule
    with pytest.raises(ValueError):
        neighborhood.propose(schedule, random.Random(9190), "unknown")
    problem, _unused_certificate = generate_instance("small", 9191)
    initial = greedy(problem, seed=9192, restarts=1)
    neighborhood = FeasibleNeighborhood(problem)
    with pytest.raises(ValueError):
        neighborhood.propose(Schedule(initial.placements[:-1], initial.teachers), random.Random(9193))
    with pytest.raises(ValueError):
        neighborhood.propose(Schedule(initial.placements, ("not-qualified",) + initial.teachers[1:]), random.Random(9194))

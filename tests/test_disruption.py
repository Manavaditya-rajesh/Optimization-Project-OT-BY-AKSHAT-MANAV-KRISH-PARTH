"""Disruption re-optimisation: disrupted models, stability measure, minimal repair, epsilon-constraint search."""
from collections import Counter
from functools import lru_cache

import pytest

from timetable.disruption import (Disruption, apply_disruption, broken_sessions, change_breakdown, changed_sessions,
                                  day_slots, default_epsilons, epsilon_reoptimize, minimal_repair, parse_disruption,
                                  restore_move)
from timetable.evaluation import evaluate
from timetable.feasible import FeasibleNeighborhood
from timetable.generation import generate_instance
from timetable.greedy import greedy
from timetable.metrics import dominates


@lru_cache(maxsize=None)
def base():
    problem, _ = generate_instance("small", 7)
    return problem, greedy(problem)


def busiest_teacher(problem, schedule):
    load = Counter()
    for event in problem.events:
        k = [o.id for o in problem.offerings].index(event.offering_id)
        load[schedule.teachers[k]] += event.duration
    return load.most_common(1)[0][0]


def teacher_days(problem, schedule, teacher):
    days = Counter()
    for i, event in enumerate(problem.events):
        k = [o.id for o in problem.offerings].index(event.offering_id)
        if schedule.teachers[k] == teacher:
            days[schedule.placements[i].start // problem.periods_per_day] += 1
    return days


def test_apply_disruption_kinds():
    P, S0 = base()
    t = busiest_teacher(P, S0)
    absent = apply_disruption(P, Disruption("teacher_absent", t, day_slots(P, 0)))
    assert set(day_slots(P, 0)) <= set(next(f for f in absent.faculty if f.id == t).unavailable)
    gone = apply_disruption(P, Disruption("teacher_leaves", t))
    assert t not in {f.id for f in gone.faculty} and all(t not in o.eligible_faculty for o in gone.offerings)
    closed = apply_disruption(P, Disruption("room_closed", S0.placements[0].room))
    assert len(next(r for r in closed.rooms if r.id == S0.placements[0].room).unavailable) == len(P.teaching_periods)
    assert [o.id for o in gone.offerings] == [o.id for o in P.offerings]  # schedules stay comparable
    with pytest.raises(ValueError):
        apply_disruption(P, Disruption("teacher_absent", "nobody"))
    with pytest.raises(ValueError):
        apply_disruption(P, Disruption("meteor", t))


def test_parse_disruption():
    P, _ = base()
    d = parse_disruption(P, "teacher_absent:F01:day=2")
    assert d.slots == day_slots(P, 2) and d.kind == "teacher_absent"
    assert parse_disruption(P, "room_closed:R01").slots == ()
    assert parse_disruption(P, "teacher_absent:F01:slots=3,1").slots == (1, 3)
    with pytest.raises(ValueError):
        parse_disruption(P, "flood:R01")


def test_change_measure():
    P, S0 = base()
    assert changed_sessions(P, S0, S0) == 0
    moved = S0.placements[0]
    other_room = next(r.id for r in P.rooms if r.id != moved.room)
    from timetable.model import Placement, Schedule
    S1 = Schedule((Placement(moved.start, other_room),) + S0.placements[1:], S0.teachers)
    assert change_breakdown(P, S0, S1) == {"total": 1, "time": 0, "room": 1, "teacher": 0}
    k = 0
    new_teacher = next(f for f in P.offerings[k].eligible_faculty if f != S0.teachers[k])
    S2 = Schedule(S0.placements, (new_teacher,) + S0.teachers[1:])
    assert changed_sessions(P, S0, S2) == P.offerings[k].sessions  # a teacher change moves every session of it


@pytest.mark.parametrize("kind", ["teacher_absent", "teacher_leaves", "room_closed"])
def test_minimal_repair_is_feasible_and_bounded(kind):
    P, S0 = base()
    t = busiest_teacher(P, S0)
    if kind == "teacher_absent":
        day = teacher_days(P, S0, t).most_common(1)[0][0]
        d = Disruption(kind, t, day_slots(P, day))
    elif kind == "teacher_leaves":
        d = Disruption(kind, t)
    else:
        d = Disruption(kind, Counter(p.room for p in S0.placements).most_common(1)[0][0])
    Pd = apply_disruption(P, d)
    assert not evaluate(Pd, S0).feasible  # the disruption really breaks S0
    rep = minimal_repair(Pd, S0, seed=0)
    assert rep.schedule is not None and evaluate(Pd, rep.schedule).feasible
    assert rep.broken == broken_sessions(Pd, S0) and rep.broken
    assert rep.changes >= rep.lower_bound  # the lower bound is valid
    # sessions that were not broken and not part of a ripple keep their placement
    assert changed_sessions(Pd, S0, rep.schedule) == rep.changes


def test_undisrupted_repair_is_identity():
    P, S0 = base()
    rep = minimal_repair(P, S0)
    assert rep.schedule == S0 and rep.changes == 0 and rep.proven_minimal


def test_restore_move_reduces_changes():
    P, S0 = base()
    nb = FeasibleNeighborhood(P)
    import random
    rng = random.Random(3)
    S = S0
    for _ in range(6):
        S = nb.propose(S, rng)
    before = changed_sessions(P, S0, S)
    if before == 0:
        pytest.skip("neighbourhood moves happened to cancel out")
    after = changed_sessions(P, S0, restore_move(nb, S, S0, random.Random(0), tries=50))
    assert after < before


@pytest.fixture(scope="module")
def reopt():
    P, S0 = base()
    t = busiest_teacher(P, S0)
    d = Disruption("teacher_leaves", t)
    Pd = apply_disruption(P, d)
    return P, Pd, S0, epsilon_reoptimize(Pd, S0, d, budget=40, population=6, seed=1, original_problem=P)


def test_epsilon_constraint_is_respected(reopt):
    P, Pd, S0, res = reopt
    for level in res.levels:
        assert all(changed_sessions(Pd, S0, s) <= level.epsilon for s in level.archive)
        assert all(evaluate(Pd, s).feasible for s in level.archive)
        assert level.changes == [changed_sessions(Pd, S0, s) for s in level.archive]
        assert level.evaluations <= 40


def test_warm_start_gives_monotone_hypervolume(reopt):
    _, _, _, res = reopt
    hv = [level.hypervolume for level in res.levels if level.feasible]
    assert all(b >= a - 1e-12 for a, b in zip(hv, hv[1:]))
    # every point of a smaller-eps front is weakly dominated by the next level's front
    for a, b in zip(res.levels, res.levels[1:]):
        for v in a.objectives:
            assert any(w == v or dominates(w, v) for w in b.objectives)


def test_tradeoff_is_nondominated_and_starts_at_repair(reopt):
    _, _, _, res = reopt
    pts = [(p["changes"], *p["objectives"]) for p in res.tradeoff]
    assert pts and not any(dominates(a, b) for a in pts for b in pts)
    assert min(p[0] for p in pts) == res.repair.changes
    assert res.original_objectives is not None


def test_default_epsilons():
    assert default_epsilons(4, 100) == [4, 6, 9, 14, 24, 44]
    assert default_epsilons(95, 100) == [95, 97, 100]


def test_reoptimize_is_deterministic():
    P, S0 = base()
    d = Disruption("teacher_leaves", busiest_teacher(P, S0))
    Pd = apply_disruption(P, d)
    a = epsilon_reoptimize(Pd, S0, d, epsilons=[0, 50], budget=15, population=4, seed=5)
    b = epsilon_reoptimize(Pd, S0, d, epsilons=[0, 50], budget=15, population=4, seed=5)
    assert [lv.objectives for lv in a.levels] == [lv.objectives for lv in b.levels]
    assert not a.levels[0].feasible or a.repair.changes == 0  # eps=0 is infeasible after a real disruption

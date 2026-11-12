"""Tests for newly implemented optimization techniques: MOEA/D, AMOSA, TOPSIS MCDM, and Epsilon-Constraint CP-SAT."""
from __future__ import annotations

import pytest

from timetable.amosa import amosa
from timetable.evaluation import evaluate
from timetable.examples import conflict_instance
from timetable.exact import cp_sat, epsilon_constraint_cp_sat
from timetable.generation import generate_instance
from timetable.mcdm import analyze_stakeholder_profiles, topsis
from timetable.moead import generate_simplex_weights, moead


def test_weight_generation():
    weights = generate_simplex_weights(12, dim=3, seed=0)
    assert len(weights) == 12
    for w in weights:
        assert len(w) == 3
        assert pytest.approx(sum(w), rel=1e-4) == 1.0
        assert all(coord > 0 for coord in w)


def test_moead_runs_and_evaluates():
    problem, _ = generate_instance("small", 9002)
    calls = []

    def observer(p, s):
        calls.append(s)
        return evaluate(p, s)

    result = moead(problem, seed=9002, population_size=6, max_evaluations=36, evaluator=observer)
    assert result.evaluations == len(calls) == 36
    assert result.metadata["evaluated_feasible"] == 36
    assert len(result.archive) >= 1
    assert all(evaluate(problem, s).feasible for s in result.archive)


def test_amosa_runs_and_evaluates():
    problem, _ = generate_instance("small", 9002)
    calls = []

    def observer(p, s):
        calls.append(s)
        return evaluate(p, s)

    result = amosa(problem, seed=9002, population_size=6, max_evaluations=36, evaluator=observer)
    assert result.evaluations == len(calls) == 36
    assert len(result.archive) >= 1
    assert all(evaluate(problem, s).feasible for s in result.archive)


def test_topsis_mcdm_ranking():
    # 2 extreme alternatives:
    # Sol 0: Perfect gaps (0.0), poor room fit (1.0), equal workload (0.1)
    # Sol 1: Poor gaps (10.0), near-perfect room fit (0.01), equal workload (0.1)
    candidates = [
        (0.0, 1.0, 0.1),
        (10.0, 0.01, 0.1),
    ]
    # Under student-first profile (80% gaps), Sol 0 must be top
    student_ranking = topsis(candidates, weights=(0.8, 0.1, 0.1))
    assert student_ranking[0].solution_index == 0

    # Under admin room-fit profile (80% room), Sol 1 must be top
    room_ranking = topsis(candidates, weights=(0.1, 0.8, 0.1))
    assert room_ranking[0].solution_index == 1

    # Analysis across stakeholder profiles
    analysis = analyze_stakeholder_profiles(candidates)
    assert "balanced" in analysis
    assert "student_first" in analysis
    assert "admin_room_fit" in analysis
    assert "faculty_fairness" in analysis


def test_epsilon_constraint_cp_sat_micro():
    problem = conflict_instance("room")
    res = epsilon_constraint_cp_sat(problem, time_limit_per_step=3.0, steps=3)
    assert res.evaluated_steps == 3
    assert len(res.archive) >= 1
    assert all(evaluate(problem, s).feasible for s in res.archive)

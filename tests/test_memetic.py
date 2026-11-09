"""The new search preserves the original model and charges every full check."""
from dataclasses import replace

import pytest

from timetable.evaluation import evaluate
from timetable.experiments import greedy_search
from timetable.generation import generate_instance
from timetable.memetic import memetic_nsga2
from timetable.metrics import dominates


@pytest.mark.parametrize("size", ["small", "medium", "large"])
def test_feasible_search_all_sizes_and_accounting(size):
    problem, _ = generate_instance(size, 9003)
    calls = []
    def observer(problem, schedule):
        calls.append(schedule)
        return evaluate(problem, schedule)
    result = memetic_nsga2(problem, seed=9003, population_size=6, max_evaluations=48, evaluator=observer)
    assert result.evaluations == len(calls) == 48
    assert result.metadata["evaluated_feasible"] == 48
    assert result.metadata["offspring_feasible"] == result.metadata["offspring_evaluated"]
    assert all(evaluate(problem, schedule).feasible for schedule in calls)
    vals = [evaluate(problem, schedule).objectives for schedule in result.archive]
    assert vals
    assert len(vals) == len(set(vals))
    assert not any(dominates(a,b) for a in vals for b in vals)
    assert result.metadata["faculty_search_calls"] > 0
    assert result.history[-1]["evaluations"] == 48


def test_reproducibility_and_shared_initialization():
    problem, _ = generate_instance("small", 9002)
    kwargs = dict(seed=9002, population_size=8, max_evaluations=8)
    standard = memetic_nsga2(problem, **kwargs)
    local = memetic_nsga2(problem, selection="scalar_local", **kwargs)
    baseline = greedy_search(problem, 9002, 8)
    assert standard.archive == local.archive
    assert set(standard.archive) == set(baseline.archive)
    assert standard.population == local.population
    a = memetic_nsga2(problem, seed=9002, population_size=8, max_evaluations=80)
    b = memetic_nsga2(problem, seed=9002, population_size=8, max_evaluations=80)
    assert a.archive == b.archive and a.population == b.population
    assert a.metadata == b.metadata


def test_local_ablation_and_optional_faculty_component():
    problem, _ = generate_instance("small", 9004)
    result = memetic_nsga2(problem, seed=9004, population_size=6, max_evaluations=48,
                          selection="scalar_local", use_faculty_search=False)
    assert result.metadata["algorithm"] == "feasible_scalar_local_search"
    assert result.metadata["faculty_search_calls"] == 0
    assert result.evaluations == 48
    assert all(evaluate(problem,schedule).feasible for schedule in result.archive)


def test_empty_time_budget_and_impossible_input_are_not_false_success():
    problem, _ = generate_instance("small", 9005)
    result = memetic_nsga2(problem, time_limit=1e-12, max_evaluations=48)
    assert result.evaluations == 0 and result.archive == []
    assert result.metadata["stop_reason"] == "wall_time"
    impossible = replace(problem, rooms=tuple(replace(room, capacity=1) for room in problem.rooms))
    result = memetic_nsga2(impossible, population_size=4, max_evaluations=20)
    assert result.archive == []
    assert result.metadata["stop_reason"] == "initialization_failure"
    assert result.metadata["minimum_violation"] > 0


def test_diagnostics_retained_when_external_observer_interrupts():
    problem, _ = generate_instance("small", 9006)
    progress = {}
    calls = 0
    class StopObserver(Exception):
        pass
    def observer(problem, schedule):
        nonlocal calls
        calls += 1
        if calls == 20:
            raise StopObserver
        return evaluate(problem, schedule)
    with pytest.raises(StopObserver):
        memetic_nsga2(problem, population_size=4, max_evaluations=48,
                      evaluator=observer, progress=progress)
    assert progress["faculty_search_calls"] > 0
    assert progress["use_faculty_search"] is True
    assert progress["initial_attempts"] == 4
    assert progress["neighborhood_calls"] > 0


@pytest.mark.parametrize("kwargs", [{"population_size":1}, {"max_evaluations":0},
                                    {"selection":"fake"}, {"time_limit":float("nan")},
                                    {"faculty_every":0}, {"faculty_nodes":0}])
def test_invalid_search_configuration(kwargs):
    problem, _ = generate_instance("small",9000)
    with pytest.raises(ValueError):
        memetic_nsga2(problem, **kwargs)

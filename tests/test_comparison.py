"""Fairness/accounting boundaries, using development seeds and analytic cases."""

from collections import Counter
import importlib
import json

import pytest

from timetable import comparison
from timetable.evaluation import evaluate
from timetable.exact import enumerate_pareto
from timetable.examples import conflict_instance
from timetable.experiments import greedy_search
from timetable.generation import generate_instance
from timetable.model import Placement, Schedule, schedule_to_dict


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


def test_observer_charges_duplicates_and_every_full_evaluation():
    problem = conflict_instance("room")
    schedule = enumerate_pareto(problem).archive[0]
    clock = Clock()
    observed = comparison._Observer(problem, cap=2, time_limit=None, clock=clock)
    observed(problem, schedule)
    observed(problem, schedule)
    with pytest.raises(comparison.SearchStopped):
        observed(problem, schedule)
    assert observed.calls == 2
    assert len(observed.hashes) == 1
    assert sum(observed.hashes.values()) == 2
    assert len(observed.archive) == 1
    assert observed.on_time_feasible == observed.feasible_calls == 2


def test_late_dominating_candidate_is_counted_but_cannot_improve_reported_quality():
    problem = conflict_instance("room")
    before = Schedule((Placement(1, "large"), Placement(3, "large")), ("A", "B"))
    better = Schedule((Placement(0, "small"), Placement(1, "large")), ("A", "B"))
    assert evaluate(problem, before).feasible and evaluate(problem, better).feasible
    assert comparison.dominates(evaluate(problem, better).objectives, evaluate(problem, before).objectives)
    clock = Clock()
    observed = comparison._Observer(problem, cap=10, time_limit=1.0, clock=clock)

    def timed_evaluate(problem, schedule):
        clock.value += 0.3 if schedule == before else 0.8
        return evaluate(problem, schedule)

    observed.evaluation_fn = timed_evaluate
    observed(problem, before)
    with pytest.raises(comparison.SearchStopped):
        observed(problem, better)
    assert observed.calls == 2 and observed.late_calls == 1
    assert observed.feasible_calls == 2 and observed.on_time_feasible == 1
    assert observed.archive == [(before, evaluate(problem, before))]
    assert observed.first_feasible == pytest.approx(0.3)
    assert observed.history[-1]["completed_after_deadline"]
    assert observed.history[-1]["elapsed_seconds"] == pytest.approx(1.1)


def test_no_evaluator_call_can_start_at_or_after_deadline():
    problem = conflict_instance("room")
    schedule = enumerate_pareto(problem).archive[0]
    clock = Clock()
    observed = comparison._Observer(problem, 10, 1.0, clock=clock)
    clock.value = 1.0
    with pytest.raises(comparison.SearchStopped):
        observed(problem, schedule)
    assert observed.calls == 0 and observed.archive == []
    assert observed.reason == "wall_time"


def test_repeated_greedy_policy_and_genotypes_are_unchanged(monkeypatch):
    module = importlib.import_module("timetable.experiments")
    problem, _ = generate_instance("small", 9006)
    calls = []
    original = module.construct

    def recorded(*args, **kwargs):
        candidate = original(*args, **kwargs)
        calls.append(candidate)
        return candidate

    monkeypatch.setattr(module, "construct", recorded)
    old = greedy_search(problem, seed=9006, budget=8)
    expected = Counter(comparison._digest(schedule_to_dict(schedule)) for schedule in calls)
    current = comparison.run_comparison_method(problem, "greedy", seed=9006, budget=8, population_size=4)
    assert current["genotype_evaluation_counts"] == dict(expected)
    assert {tuple(vector) for vector in current["objectives"]} == {
        evaluate(problem, schedule).objectives for schedule in old.archive
    }
    assert current["evaluations"] == current["evaluation_cap"] == 8


@pytest.mark.parametrize("method", ["greedy", "original_enhanced", "memetic", "ablation_local"])
def test_compared_algorithms_use_shared_counted_archive_and_fixed_scales(method):
    problem, _ = generate_instance("small", 9007)
    result = comparison.run_comparison_method(problem, method, seed=9007, budget=12, population_size=4)
    assert result["evaluations"] == 12
    assert sum(result["genotype_evaluation_counts"].values()) == 12
    assert result["history"][-1]["evaluations"] == 12
    assert result["history"][-1]["hypervolume"] == pytest.approx(result["hypervolume"])
    times = [row["elapsed_seconds"] for row in result["history"]]
    assert times == sorted(times)
    assert all(0 <= elapsed <= result["runtime"] for elapsed in times)
    assert result["normalization"] == comparison.objective_scales(problem)
    schedules = [comparison.schedule_from_dict(data) for data in result["archive"]]
    assert all(evaluate(problem, schedule).feasible for schedule in schedules)
    assert result["archive_size"] == len(schedules)


def test_interrupted_legacy_adapter_restores_source_evaluator_and_handles_zero_calls():
    module = importlib.import_module("timetable.nsga2")
    original = module.evaluate
    problem, _ = generate_instance("small", 9008)
    result = comparison.run_comparison_method(
        problem, "original_enhanced", seed=9008, budget=8,
        population_size=4, time_limit=1e-12,
    )
    assert module.evaluate is original
    assert result["evaluations"] == 0
    assert result["archive"] == [] and result["hypervolume"] == 0
    assert result["time_to_first_feasible_seconds"] is None
    assert result["wall_time_overshoot_seconds"] >= 0
    assert result["metadata"]["evaluation_adapter_interrupted"]


def _config(tmp_path, **overrides):
    config = {"name": "comparison_test", "phase": "development", "population_size": 4,
              "methods": ["greedy"], "protocols": ["evaluations"],
              "instance_seeds": [9009], "solver_seeds": [0],
              "scenarios": [{"size": "small", "budget": 2}]}
    config.update(overrides)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path


def test_comparison_checkpoint_resume_and_cached_hypervolume_validation(tmp_path, monkeypatch):
    generation = importlib.import_module("timetable.generation")
    problem = conflict_instance("room")
    certificate = enumerate_pareto(problem).archive[0]
    monkeypatch.setattr(generation, "generate_instance", lambda *a: (problem, certificate))
    path = _config(tmp_path)
    directory = comparison.run_comparison(path, root=tmp_path)
    run_path = next((directory / "runs").glob("*.json"))
    original_run = run_path.read_bytes()
    original_manifest = (directory / "manifest.json").read_bytes()
    comparison.run_comparison(path, root=tmp_path, resume=True)
    assert run_path.read_bytes() == original_run
    assert (directory / "manifest.json").read_bytes() == original_manifest
    assert (directory / "source_snapshot" / "comparison.py").exists()
    saved = json.loads(run_path.read_text())
    saved["hypervolume"] += 0.01
    run_path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="indicators"):
        comparison.run_comparison(path, root=tmp_path, resume=True)


@pytest.mark.parametrize("override", [
    {"methods": ["greedy", "greedy"]},
    {"protocols": ["wall_time"], "scenarios": [{"size": "small", "budget": 4}]},
    {"solver_seeds": [0, 0]},
    {"scenarios": [{"size": "small", "budget": 4, "generator": {"unavailability_rate": 0.1}}]},
    {"scenarios": [{"size": "small", "budget": 4}, {"size": "small", "budget": 8}]},
])
def test_bad_or_dataset_changing_comparisons_rejected_before_measurement(tmp_path, override):
    path = _config(tmp_path, **override)
    with pytest.raises(ValueError):
        comparison.run_comparison(path, root=tmp_path)
    assert not (tmp_path / "results").exists()


def test_undefined_empty_target_coverage_preserved_in_analysis(tmp_path):
    problem = conflict_instance("room")
    baseline = comparison.run_comparison_method(problem, "greedy", budget=2, population_size=2)
    baseline.update({"instance_id": "small_9009", "size": "small", "instance_seed": 9009})
    empty = {**baseline, "method": "original_enhanced", "archive": [], "objectives": [],
             "hypervolume": 0.0, "archive_size": 0, "feasible_run": False, "history": [],
             "time_to_first_feasible_seconds": None}
    comparison._json(tmp_path / "runs" / "greedy.json", baseline)
    comparison._json(tmp_path / "runs" / "empty.json", empty)
    result = comparison.analyze_comparison(tmp_path)
    pair = result["comparisons"]["small/evaluations/original_enhanced_vs_greedy"]
    assert pair["coverage_greedy_over_method_mean"] is None
    assert pair["coverage_greedy_over_method_defined_pairs"] == 0
    assert pair["coverage_method_over_greedy_mean"] == 0


def test_direct_population_vs_local_policy_comparison_is_reported(tmp_path):
    problem = conflict_instance("room")
    baseline = comparison.run_comparison_method(problem, "greedy", budget=2, population_size=2)
    baseline.update({"instance_id": "small_9009", "size": "small", "instance_seed": 9009})
    for method in ("greedy", "memetic", "ablation_local", "original_enhanced"):
        comparison._json(tmp_path / "runs" / f"{method}.json", {**baseline, "method": method})
    result = comparison.analyze_comparison(tmp_path)
    for reference in ("ablation_local", "original_enhanced"):
        key = f"small/evaluations/memetic_vs_{reference}"
        assert result["comparisons"][key]["reference_method"] == reference
        assert result["comparisons"][key]["paired_run_descriptive"]["ties"] == 1


def test_timed_memetic_retains_native_progress_when_observer_interrupts():
    # A tiny real wall-time run exercises interruption during initialization,
    # without relying on a specific speed, solution quality, or call count.
    problem, _ = generate_instance("small", 9010)
    result = comparison.run_comparison_method(
        problem, "memetic", seed=9010, budget=24, population_size=4,
        time_limit=0.01,
    )
    assert "algorithm" in result["metadata"]["native_search_metadata"]
    assert "faculty_search_nodes" in result["metadata"]["native_search_metadata"]
    assert result["metadata"]["full_evaluator_calls"] == result["evaluations"]
    assert all(not row["completed_after_deadline"] or row["elapsed_seconds"] > 0.01
               for row in result["history"])
    assert result["wall_time_overshoot_seconds"] >= 0

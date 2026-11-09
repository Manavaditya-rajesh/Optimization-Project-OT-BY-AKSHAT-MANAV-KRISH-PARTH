"""Numerical regression cases for strict reporting fronts, independent of search."""
from fractions import Fraction
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("exact_front_tool", ROOT / "experiments/exact_fronts.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

from timetable.generation import generate_instance
from timetable.model import problem_from_dict, schedule_from_dict, problem_to_dict, schedule_to_dict


def test_saved_equal_variance_false_tradeoff_is_removed():
    problem = problem_from_dict(json.loads((ROOT / "data/enhancement_validation/large_1010.json").read_text()))
    source = json.loads((ROOT / "results/enhancement_validation/runs/large_1010_evaluations_memetic_0.json").read_text())
    a, b = [schedule_from_dict(source["archive"][i]) for i in (8, 9)]
    ka, kb = tool.exact_key(problem, a), tool.exact_key(problem, b)
    assert ka == (Fraction(5), Fraction(2701, 13200), Fraction(83, 10000))
    assert kb == (Fraction(5), Fraction(43, 200), Fraction(83, 10000))
    assert source["objectives"][8][2] > source["objectives"][9][2]
    assert tool.exact_dominates(ka, kb)
    assert tool.front_indices([ka, kb]) == [0]
    subset = {"archive": [source["archive"][8], source["archive"][9]]}
    first = tool.clean_run(problem, subset, include_schedules=True)
    second = tool.clean_run(problem, first, include_schedules=True)
    assert second["archive"] == first["archive"]
    assert second["objectives"] == first["objectives"]
    assert second["exact_keys"] == first["exact_keys"]


def test_no_epsilon_discards_small_real_tradeoffs():
    delta = Fraction(1, 10**40)
    keys = [(Fraction(0), Fraction(1), Fraction(0)),
            (Fraction(0), Fraction(1)-delta, delta)]
    assert tool.front_indices(keys) == [0, 1]
    assert tool.front_indices([keys[0], (Fraction(0), Fraction(1)+delta, Fraction(0))]) == [0]


def test_incremental_front_handles_later_dominators_and_duplicates():
    F = Fraction
    keys = [(F(2), F(2), F(2)), (F(1), F(1), F(1)),
            (F(0), F(3), F(1)), (F(1), F(1), F(1))]
    assert tool.front_indices(keys) == [1, 2]


def test_clean_front_rejects_infeasible_input():
    problem, schedule = generate_instance("small", 2081)
    encoded = json.loads(json.dumps(schedule_to_dict(schedule)))
    encoded["placements"][0] = None
    with pytest.raises(ValueError, match="infeasible"):
        tool.clean_run(problem, {"archive": [encoded]})


def test_empty_front_is_not_fabricated():
    problem, _ = generate_instance("small", 2082)
    result = tool.clean_run(problem, {"archive": []}, include_schedules=True)
    assert result["archive"] == result["objectives"] == result["exact_keys"] == []
    assert result["corrected_hypervolume"] == 0


def test_fresh_run_exports_exact_archive_and_preserves_input_bytes(tmp_path):
    problem, schedule = generate_instance("small", 2083)
    instance, run, output = (tmp_path / name for name in ("instance.json", "run.json", "front.json"))
    instance.write_text(json.dumps(problem_to_dict(problem)))
    run.write_text(json.dumps({"archive": [schedule_to_dict(schedule), schedule_to_dict(schedule)]}))
    before = instance.read_bytes(), run.read_bytes()
    assert tool.main(["--run", str(run), "--instance", str(instance), "--output", str(output)]) == 0
    result = json.loads(output.read_text())
    assert result["survivor_indices"] == [0] and len(result["archive"]) == 1
    assert result["exact_duplicate_indices"] == [1]
    assert before == (instance.read_bytes(), run.read_bytes())
    with pytest.raises(ValueError, match="overwrite"):
        tool.main(["--run", str(run), "--instance", str(instance), "--output", str(run)])
    assert before == (instance.read_bytes(), run.read_bytes())


def test_invalid_stored_normalization_is_rejected():
    problem, schedule = generate_instance("small", 2084)
    with pytest.raises(ValueError, match="normalization"):
        tool.clean_run(problem, {"archive": [schedule_to_dict(schedule)], "normalization": [1, 1, 1]})


def test_unequal_allowances_have_exact_variance_and_sd_ordering():
    from timetable.model import Problem, Group, Room, Faculty, Offering, Placement, Schedule
    problem = Problem("unequal", ("Monday",), 3, (), (Group("G", 10),),
                      (Room("R", 10, "classroom"),),
                      (Faculty("A", 2, 2), Faculty("B", 4, 2)),
                      (Offering("X", ("G",), ("A",), 1, 1, "classroom"),
                       Offering("Y", ("G",), ("B",), 1, 1, "classroom")))
    schedule = Schedule((Placement(0, "R"), Placement(1, "R")), ("A", "B"))
    key = tool.exact_key(problem, schedule)
    assert key == (Fraction(0), Fraction(0), Fraction(1, 64))
    assert tool.coordinates(key) == [0.0, 0.0, 0.125]

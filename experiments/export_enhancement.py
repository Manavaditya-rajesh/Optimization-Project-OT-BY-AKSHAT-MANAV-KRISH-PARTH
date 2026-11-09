"""Export fixed-priority schedules for predeclared first held-out instances."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from timetable.evaluation import evaluate
from timetable.export import export_schedule
from timetable.model import problem_from_dict, schedule_from_dict
from timetable.visualization import plot_grid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="enhancement_validation")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = root / "results" / args.study
    manifest = json.loads((folder / "manifest.json").read_text())
    rows = []
    for scenario in manifest["config"]["scenarios"]:
        size = scenario["size"]
        if size == "small":
            continue
        # Selection is fixed by configuration order, not by observed quality.
        instance_seed = scenario.get("instance_seeds", manifest["config"]["instance_seeds"])[0]
        solver_seed = scenario.get("solver_seeds", manifest["config"]["solver_seeds"])[0]
        instance = f"{size}_{instance_seed}"
        problem = problem_from_dict(json.loads((root / "data" / args.study / (instance + ".json")).read_text()))
        for method in ["greedy", "memetic"]:
            run = json.loads((folder / "runs" / f"{instance}_wall_time_{method}_{solver_seed}.json").read_text())
            for label, key in [("fewest_gaps", lambda v:(v[0],v[1],v[2])),
                               ("balanced_workload", lambda v:(v[2],v[0],v[1]))]:
                if not run["archive"]:
                    continue
                i = min(range(len(run["archive"])), key=lambda i:key(run["objectives"][i]))
                schedule = schedule_from_dict(run["archive"][i])
                ev = evaluate(problem, schedule)
                assert ev.feasible
                export_schedule(problem, schedule, folder / "timetables" / instance / method / label,
                                f"{instance}: {method}, {label}, common wall-time allocation")
                figure = root / "figures" / args.study / "timetables" / f"{instance}_{method}_{label}.png"
                plot_grid(problem, schedule, "group", problem.groups[0].id, figure)
                rows.append({"instance":instance,"method":method,"selection":label,
                             "solver_seed":solver_seed,"protocol":"wall_time","archive_index":i,
                             "objectives":ev.objectives,"metrics":ev.metrics,
                             "selection_rule":"lexicographic f1,f2,f3" if label == "fewest_gaps" else "lexicographic f3,f1,f2"})
    (folder / "representatives.json").write_text(json.dumps(rows,indent=2)+"\n")
    print(f"Exported {len(rows)} feasible representative timetables")


if __name__ == "__main__":
    main()

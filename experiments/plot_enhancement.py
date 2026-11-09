"""Plot measured follow-up quality and exact stepwise elapsed-time prefixes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from timetable.visualization import COLORS, plot_fronts

COLORS.update({"original_enhanced": "#6486af", "memetic": "#15836c", "ablation_local": "#9b6bb0"})
METHODS = ["greedy", "original_enhanced", "memetic", "ablation_local"]
NAMES = ["Greedy", "Original enhanced", "Feasible NSGA-II", "Scalar local"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="enhancement_validation")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = root / "results" / args.study
    figures = root / "figures" / args.study
    figures.mkdir(parents=True, exist_ok=True)
    runs = [json.loads(p.read_text()) for p in sorted((folder / "runs").glob("*.json"))]
    for size in ["small", "medium", "large"]:
        for protocol in ["evaluations", "wall_time"]:
            selected = [r for r in runs if r["size"] == size and r["protocol"] == protocol]
            if not selected:
                continue
            fig, axes = plt.subplots(1,3,figsize=(15,4.5),constrained_layout=True)
            for ax, key, label in zip(axes, ["hypervolume", "runtime", "on_time_feasible_evaluation_fraction"],
                                     ["Hypervolume (fixed normalization)", "Actual search time (seconds)", "On-time feasible evaluation fraction"]):
                values = [[r[key] for r in selected if r["method"] == m] for m in METHODS]
                ax.boxplot(values, tick_labels=NAMES, showmeans=True)
                ax.tick_params(axis="x", rotation=25)
                ax.set_ylabel(label)
                ax.grid(axis="y", alpha=.2)
            fig.suptitle(f"{size.title()}: {protocol} protocol; variability across paired solver runs")
            fig.savefig(figures / f"{size}_{protocol}_comparison.png",dpi=150)
            plt.close(fig)
        selected = [r for r in runs if r["size"] == size and r["protocol"] == "wall_time"]
        if not selected:
            continue
        horizon = selected[0]["wall_time_limit"]
        grid = np.linspace(0,horizon,161)
        fig, axes = plt.subplots(1,2,figsize=(13,4.5),constrained_layout=True)
        for method,name in zip(METHODS,NAMES):
            curves = []
            evals = []
            for run in selected:
                if run["method"] != method:
                    continue
                history = [h for h in run["history"] if not h["completed_after_deadline"]]
                idx = np.searchsorted([h["elapsed_seconds"] for h in history],grid,side="right")-1
                curves.append([0 if i < 0 else history[i]["hypervolume"] for i in idx])
                evals.append([0 if i < 0 else history[i]["evaluations"] for i in idx])
            values = np.array(curves)
            avg,sd = values.mean(axis=0),values.std(axis=0)
            axes[0].step(grid,avg,where="post",label=name,color=COLORS[method])
            axes[0].fill_between(grid,np.maximum(0,avg-sd),avg+sd,step="post",alpha=.1,color=COLORS[method])
            axes[1].step(grid,np.mean(evals,axis=0),where="post",label=name,color=COLORS[method])
        axes[0].set(xlabel="Measured elapsed time (seconds)",ylabel="Archive hypervolume")
        axes[1].set(xlabel="Measured elapsed time (seconds)",ylabel="Completed on-time evaluations")
        for ax in axes:
            ax.grid(alpha=.2)
        axes[0].legend()
        fig.suptitle(f"{size.title()}: sampled stepwise time prefixes, mean ± 1 SD; no interpolation of discoveries")
        fig.savefig(figures / f"{size}_anytime.png",dpi=150)
        plt.close(fig)
    # Each Pareto image uses a single fixed instance, avoiding cross-instance fronts.
    for instance in sorted(set(r["instance_id"] for r in runs)):
        for protocol in ["evaluations", "wall_time"]:
            records = [{"method": r["method"], "objectives": vector} for r in runs
                       if r["instance_id"] == instance and r["protocol"] == protocol for vector in r["objectives"]]
            plot_fronts(records,figures / f"{instance}_{protocol}_pareto.png",
                        f"{instance}, {protocol}: feasible per-run archives on one fixed instance")
    print(f"Generated plots in {figures.relative_to(root)}")


if __name__ == "__main__":
    main()

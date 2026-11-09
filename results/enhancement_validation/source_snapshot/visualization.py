"""Headless, reproducible scientific plots (all values come from saved results)."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .export import resource_grid
from .metrics import nondominated_indices

LABELS = ["Idle gaps (periods; faculty weight 0.5)", "Unused room capacity fraction", "Faculty relative-load SD"]
COLORS = {"greedy": "#7c6a52", "nsga2": "#6486af", "seeded": "#9b6bb0", "enhanced": "#15836c"}


def plot_fronts(records: list[dict], output: str | Path, title: str = "Observed feasible fronts", certified: bool = False) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(14, 10), constrained_layout=True)
    pairs = [(0, 1), (0, 2), (1, 2)]
    methods = sorted(set(row["method"] for row in records))
    for panel, (a, b) in enumerate(pairs, 1):
        ax = fig.add_subplot(2, 2, panel)
        for method in methods:
            pts = [row["objectives"] for row in records if row["method"] == method]
            if pts:
                values = np.array(pts)
                ax.scatter(values[:, a], values[:, b], s=28, alpha=0.65,
                           label=method, color=COLORS.get(method))
        ax.set(xlabel=LABELS[a], ylabel=LABELS[b])
        ax.grid(alpha=0.18)
        if panel == 1:
            ax.legend()
    ax = fig.add_subplot(2, 2, 4, projection="3d")
    for method in methods:
        pts = [row["objectives"] for row in records if row["method"] == method]
        if pts:
            values = np.array(pts)
            ax.scatter(values[:, 0], values[:, 1], values[:, 2], label=method, s=22, color=COLORS.get(method))
    ax.set(xlabel="Idle gaps", ylabel="Unused capacity", zlabel="Load SD")
    subtitle = ("All feasible assignments were exhausted; these tiny fronts are globally certified."
                if certified else "All plotted points are feasible; pooled across runs, not a proven global Pareto front.")
    fig.suptitle(title + "\n" + subtitle)
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_convergence(runs: list[dict], output: str | Path, budget: int) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    xs = np.linspace(0, budget, min(budget + 1, 101))
    for method in sorted(set(run["method"] for run in runs)):
        selected = [run for run in runs if run["method"] == method]
        for metric, ax, ylabel in [("hypervolume", axes[0], "Archive hypervolume (normalized)"),
                                   ("evaluated_feasible_fraction", axes[1], "Cumulative evaluated feasible fraction")]:
            curves = []
            for run in selected:
                history = run["history"]
                evaluations = [row["evaluations"] for row in history]
                values = [row.get(metric, 0.0) for row in history]
                indices = np.searchsorted(evaluations, xs, side="right") - 1
                curves.append(np.array([0 if i < 0 else values[i] for i in indices]))
            curves = np.array(curves)
            avg, sd = curves.mean(axis=0), curves.std(axis=0)
            ax.plot(xs, avg, label=method, color=COLORS.get(method))
            ax.fill_between(xs, np.maximum(0, avg - sd), avg + sd, alpha=0.12, color=COLORS.get(method))
            ax.set(xlabel="Complete schedule evaluations (includes repair/local search)", ylabel=ylabel)
            ax.grid(alpha=0.18)
    axes[0].legend()
    axes[1].set_ylim(-0.02, 1.02)
    fig.suptitle("Mean ± 1 SD across paired runs; stepwise archive progress")
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_comparison(rows: list[dict], output: str | Path) -> None:
    methods = sorted(set(row["method"] for row in rows))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for ax, metric, ylabel in zip(axes, ["hypervolume", "runtime", "feasible_evaluation_fraction"],
                                  ["Hypervolume", "Runtime (seconds)", "Evaluated feasible fraction"]):
        values = [[row[metric] for row in rows if row["method"] == method] for method in methods]
        ax.boxplot(values, tick_labels=methods, showmeans=True)
        ax.tick_params(axis="x", rotation=25)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.18)
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_grid(problem, schedule, resource_kind: str, resource_id: str, output: str | Path) -> None:
    grid = resource_grid(problem, schedule, resource_kind, resource_id)
    fig, ax = plt.subplots(figsize=(16, 5), constrained_layout=True)
    ax.axis("off")
    cells = [[cell or "—" for cell in row] for row in grid]
    table = ax.table(cellText=cells, rowLabels=problem.days,
                     colLabels=[f"Period {p+1}" for p in range(problem.periods_per_day)],
                     cellLoc="center", loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(7)
    table.scale(1, 3.8)
    for (row, col), cell in table.get_celld().items():
        if row == 0 or col == -1:
            cell.set_facecolor("#e1e9ed")
        elif col in problem.lunch_periods:
            cell.set_facecolor("#eeeeee")
        elif cells[row-1][col] != "—":
            cell.set_facecolor("#dcf1e7")
    ax.set_title(f"{problem.name}: {resource_kind} {resource_id}\nPeriods are categorical; lunch is blocked", pad=20)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(fig)

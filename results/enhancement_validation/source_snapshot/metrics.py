"""Transparent Pareto indicators for minimization; no sampled/fabricated fronts.

Hypervolume is exact for three objectives, computed by slicing unions of boxes.
Only feasible objective vectors belong in a reported front.
"""
from __future__ import annotations

from math import comb, isfinite, sqrt
from statistics import mean, median
from typing import Sequence

Vector = Sequence[float]


def dominates(a: Vector, b: Vector) -> bool:
    if len(a) != len(b):
        raise ValueError("Objective dimensions must agree")
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def constraint_dominates(a: Vector, b: Vector, va: float = 0, vb: float = 0) -> bool:
    """Deb's feasibility rule; equal positive violations do not dominate."""
    if va < 0 or vb < 0:
        raise ValueError("Violations must be nonnegative")
    if va == 0 and vb == 0:
        return dominates(a, b)
    return va < vb


def non_dominated_sort(values: Sequence[Vector], violations: Sequence[float] | None = None) -> list[list[int]]:
    if not values:
        return []
    if any(len(v) != len(values[0]) or not all(isfinite(x) for x in v) for v in values):
        raise ValueError("Objectives must be finite and have consistent dimensions")
    violations = [0.0] * len(values) if violations is None else list(violations)
    if len(violations) != len(values) or any(v < 0 or not isfinite(v) for v in violations):
        raise ValueError("One finite nonnegative violation is required per vector")
    dominates_set = [[] for _ in values]
    dominated_count = [0] * len(values)
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            if constraint_dominates(values[i], values[j], violations[i], violations[j]):
                dominates_set[i].append(j)
                dominated_count[j] += 1
            elif constraint_dominates(values[j], values[i], violations[j], violations[i]):
                dominates_set[j].append(i)
                dominated_count[i] += 1
    front = [i for i, count in enumerate(dominated_count) if count == 0]
    fronts = []
    while front:
        fronts.append(front)
        following = []
        for i in front:
            for j in dominates_set[i]:
                dominated_count[j] -= 1
                if dominated_count[j] == 0:
                    following.append(j)
        front = following
    return fronts


def nondominated_indices(values: Sequence[Vector], unique: bool = True) -> list[int]:
    if not values:
        return []
    front = non_dominated_sort(values)[0]
    if not unique:
        return front
    seen = set()
    result = []
    for i in front:
        key = tuple(values[i])
        if key not in seen:
            seen.add(key)
            result.append(i)
    return result


def crowding_distance(values: Sequence[Vector], front: Sequence[int]) -> dict[int, float]:
    distances = dict.fromkeys(front, 0.0)
    if len(front) <= 2:
        return dict.fromkeys(front, float("inf"))
    for objective in range(len(values[0])):
        ordered = sorted(front, key=lambda i: values[i][objective])
        span = values[ordered[-1]][objective] - values[ordered[0]][objective]
        if span == 0:
            continue
        distances[ordered[0]] = distances[ordered[-1]] = float("inf")
        for at in range(1, len(ordered) - 1):
            distances[ordered[at]] += (values[ordered[at + 1]][objective] - values[ordered[at - 1]][objective]) / span
    return distances


def _area_2d(points: Sequence[Vector], reference: Vector) -> float:
    best_y = reference[1]
    area = 0.0
    for x, y in sorted(points):
        if y < best_y:
            area += (reference[0] - x) * (best_y - y)
            best_y = y
    return area


def hypervolume(points: Sequence[Vector], reference: Vector = (1.1, 1.1, 1.1)) -> float:
    """Exact dominated volume in 3D; strict validation avoids silent clipping."""
    if len(reference) != 3 or not all(isfinite(x) for x in reference):
        raise ValueError("A finite three-dimensional reference is required")
    if not points:
        return 0.0
    for p in points:
        if len(p) != 3 or not all(isfinite(x) for x in p):
            raise ValueError("A finite objective triple is required")
        if any(x > r for x, r in zip(p, reference)):
            raise ValueError("Reference must weakly dominate every point")
    front = [points[i] for i in nondominated_indices(points)]
    xs = sorted(set(p[0] for p in front) | {reference[0]})
    volume = 0.0
    for x, next_x in zip(xs, xs[1:]):
        yz = [(p[1], p[2]) for p in front if p[0] <= x]
        volume += (next_x - x) * _area_2d(yz, reference[1:])
    return float(volume)


def objective_scales(problem) -> tuple[float, float, float]:
    """A priori upper bounds for feasible solutions; never fitted to results.

    For each participant/day, a loose gap bound is the teaching-day length.
    Relative loads lie in [0,1], hence population SD <= 0.5 (Popoviciu).
    """
    teach = problem.periods_per_day - len(problem.lunch_periods)
    gap = len(problem.days) * teach * (len(problem.groups) + 0.5 * len(problem.faculty))
    return max(1.0, float(gap)), 1.0, 0.5


def normalize(values: Vector, scales: Vector) -> tuple[float, ...]:
    if len(values) != len(scales) or any(x <= 0 or not isfinite(x) for x in scales):
        raise ValueError("Positive finite scale required for each objective")
    return tuple(x / s for x, s in zip(values, scales))


def spacing(points: Sequence[Vector]) -> float | None:
    """Schott spacing (sample SD of nearest Manhattan distances).

    Undefined for fewer than two unique vectors; small spacing alone is not
    evidence of quality or coverage.
    """
    points = list(dict.fromkeys(tuple(p) for p in points))
    if len(points) < 2:
        return None
    distances = [min(sum(abs(a - b) for a, b in zip(p, q)) for j, q in enumerate(points) if i != j)
                 for i, p in enumerate(points)]
    avg = mean(distances)
    return sqrt(sum((d - avg) ** 2 for d in distances) / (len(distances) - 1))


def coverage(a: Sequence[Vector], b: Sequence[Vector]) -> float | None:
    """Fraction of B weakly dominated by A; asymmetric, including equality."""
    if not b:
        return None
    return sum(any(all(x <= y for x, y in zip(p, q)) for p in a) for q in b) / len(b)


def paired_comparison(a: Sequence[float], b: Sequence[float]) -> dict:
    """Exact two-sided paired sign test, higher is better (e.g. hypervolume).

    Ties are removed for the binomial test and counted as half for superiority.
    No normality/independence-of-runs-within-instance inference is implied.
    """
    if len(a) != len(b) or not a:
        raise ValueError("Equal nonempty paired samples required")
    differences = [x - y for x, y in zip(a, b)]
    wins = sum(d > 1e-12 for d in differences)
    losses = sum(d < -1e-12 for d in differences)
    ties = len(a) - wins - losses
    n = wins + losses
    p = min(1.0, 2 * sum(comb(n, k) for k in range(min(wins, losses) + 1)) / 2**n) if n else 1.0
    return {"pairs": len(a), "wins": wins, "losses": losses, "ties": ties,
            "median_difference": median(differences), "mean_difference": mean(differences),
            "paired_superiority": (wins + 0.5 * ties) / len(a), "sign_test_p_two_sided": p}

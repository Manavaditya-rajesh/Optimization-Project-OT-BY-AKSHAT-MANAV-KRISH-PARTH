"""Multi-Criteria Decision-Making (MCDM) using TOPSIS.

Technique for Order Preference by Similarity to Ideal Solution (TOPSIS).

In multi-objective optimization, metaheuristics discover a front of non-dominated
trade-off solutions. However, a university coordinator or Dean must ultimately
deploy a SINGLE timetable. TOPSIS provides a principled, objective-weighted
decision-making mechanism to select and rank timetables based on stakeholder priorities.

Key Optimization Techniques (OT) Concepts:
------------------------------------------
1. Positive Ideal Solution (PIS, A+) and Negative Ideal Solution (NIS, A-):
   - For minimization objectives (gaps, seat wastage, faculty SD):
     A+_j = min_i { v_ij } (theoretical best across the front)
     A-_j = max_i { v_ij } (worst compromise across the front)

2. Relative Closeness Coefficient (C_i*):
   C_i* = S-_i / (S+_i + S-_i)
   where S+_i is the Euclidean distance to PIS and S-_i is the distance to NIS.
   C_i* in [0, 1]. A higher score indicates the solution is simultaneously close
   to the ideal benchmark and far from the worst alternative.

3. Stakeholder Weight Sensitivity:
   Different campus departments have conflicting interests:
   - Students prioritize minimizing idle teaching gaps.
   - Administration prioritizes room utilization / minimizing seat wastage.
   - Faculty Deans prioritize balanced weekly teaching distribution.
   TOPSIS reveals which timetable best aligns with each stakeholder group.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


STAKEHOLDER_PROFILES: dict[str, tuple[float, float, float]] = {
    "balanced": (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
    "student_first": (0.6, 0.2, 0.2),
    "admin_room_fit": (0.2, 0.6, 0.2),
    "faculty_fairness": (0.2, 0.2, 0.6),
}


@dataclass(frozen=True)
class TopsisRanking:
    rank: int
    solution_index: int
    objectives: tuple[float, float, float]
    score: float
    distance_ideal: float
    distance_nadir: float


def topsis(
    objectives: Sequence[tuple[float, float, float]],
    weights: Sequence[float] = (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
) -> list[TopsisRanking]:
    """Rank Pareto-optimal objective vectors using the TOPSIS method.
    
    All objectives are assumed to be minimized:
    - Obj 0: Internal gaps (student + 0.5 * faculty)
    - Obj 1: Duration-weighted unused room seat fraction
    - Obj 2: Faculty workload standard deviation
    
    Parameters:
        objectives: List of non-dominated 3D objective tuples.
        weights: 3-element weight vector representing stakeholder priorities.
        
    Returns:
        List of TopsisRanking dataclasses sorted from best (rank 1) to worst.
    """
    if not objectives:
        return []
    if len(weights) != 3:
        raise ValueError("weights must be a 3-element sequence for 3 objectives")
    weight_sum = sum(weights)
    if weight_sum <= 0:
        raise ValueError("Sum of weights must be positive")
    w_norm = [w / weight_sum for w in weights]

    m = len(objectives)
    n = 3

    # Step 1: Vector Normalization
    col_norms = []
    for j in range(n):
        sum_sq = sum(objectives[i][j] ** 2 for i in range(m))
        col_norms.append(math.sqrt(sum_sq) if sum_sq > 0 else 1.0)

    # Step 2: Weighted Normalized Decision Matrix
    # V[i][j] = w_norm[j] * (X[i][j] / col_norms[j])
    v = []
    for i in range(m):
        row = [w_norm[j] * (objectives[i][j] / col_norms[j]) for j in range(n)]
        v.append(row)

    # Step 3: Determine Ideal (PIS / A+) and Anti-Ideal (NIS / A-) Solutions
    # Because all objectives are minimized:
    # A+_j = min_i(V[i][j]), A-_j = max_i(V[i][j])
    pis = [min(v[i][j] for i in range(m)) for j in range(n)]
    nis = [max(v[i][j] for i in range(m)) for j in range(n)]

    # Step 4: Calculate Separation Distances S+ and S-
    scores = []
    for i in range(m):
        d_plus = math.sqrt(sum((v[i][j] - pis[j]) ** 2 for j in range(n)))
        d_minus = math.sqrt(sum((v[i][j] - nis[j]) ** 2 for j in range(n)))
        
        # Step 5: Calculate Relative Closeness to Ideal Solution C_i*
        denom = d_plus + d_minus
        closeness = d_minus / denom if denom > 0 else 1.0
        scores.append((i, closeness, d_plus, d_minus, objectives[i]))

    # Step 6: Rank alternatives by closeness in descending order
    scores.sort(key=lambda item: item[1], reverse=True)

    rankings = []
    for rank, (idx, c_score, d_pos, d_neg, objs) in enumerate(scores, start=1):
        rankings.append(TopsisRanking(
            rank=rank,
            solution_index=idx,
            objectives=objs,
            score=round(c_score, 6),
            distance_ideal=round(d_pos, 6),
            distance_nadir=round(d_neg, 6),
        ))
    return rankings


def analyze_stakeholder_profiles(
    objectives: Sequence[tuple[float, float, float]],
) -> dict[str, dict]:
    """Run TOPSIS across standard institutional stakeholder profiles.
    
    Profiles:
    - balanced: Equal emphasis on students, rooms, and faculty.
    - student_first: 60% weight on minimizing student gap hours.
    - admin_room_fit: 60% weight on room seat utilization.
    - faculty_fairness: 60% weight on equitable teaching workload distribution.
    """
    analysis = {}
    for profile_name, weights in STAKEHOLDER_PROFILES.items():
        ranking = topsis(objectives, weights=weights)
        top = ranking[0] if ranking else None
        analysis[profile_name] = {
            "weights": list(weights),
            "top_choice_index": top.solution_index if top else None,
            "top_choice_objectives": list(top.objectives) if top else None,
            "top_choice_score": top.score if top else None,
            "all_rankings": [
                {
                    "rank": r.rank,
                    "index": r.solution_index,
                    "score": r.score,
                    "objectives": list(r.objectives),
                }
                for r in ranking
            ],
        }
    return analysis

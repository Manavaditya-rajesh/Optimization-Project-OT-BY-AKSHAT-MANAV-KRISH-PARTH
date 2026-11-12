# Disruption re-optimisation (minimal-change, ε-constraint)

Code: `src/timetable/disruption.py` · CLI: `python main.py reoptimize` · Tests: `tests/test_disruption.py` ·
Study: `experiments/disruption_study.py` → `results/disruption/`, `figures/disruption/`.

The rest of the project optimises a timetable from scratch. In practice a timetable is published once and then has
to survive disruptions: a teacher is ill for a day, a teacher leaves, a room is closed. Re-running the optimiser
from scratch produces a good timetable that is almost entirely different, which is unusable mid-semester. This
extension asks: **what is the best timetable we can get while changing at most ε sessions of the published one?**

## Formulation

Let `P` be the original problem and `S₀` the published feasible timetable. A disruption `d` gives a new problem
`P' = apply_disruption(P, d)`:

| Disruption | Change to the model |
|---|---|
| `teacher_absent` | the teacher's unavailable set gains the given slots (default: one whole day) |
| `teacher_leaves` | the teacher is removed from the faculty and from every offering's eligible set |
| `room_closed` | the room's unavailable set gains the given slots (default: the whole week) |

All hard constraints and the three objectives `f = (f₁ gaps, f₂ room wastage, f₃ workload SD)` are unchanged.

**Stability** is a fourth objective: the number of changed sessions

  Δ(S, S₀) = |{ sessions e : start(e), room(e) or teacher(offering(e)) differs between S and S₀ }|.

A teacher change counts every session of that offering, because each of them now has a different teacher.

The **ε-constraint problem** for a change limit ε is

  min f(S)  subject to  S feasible for P',  Δ(S, S₀) ≤ ε.

Solving it for ε₁ < ε₂ < … traces the stability/quality trade-off. The union of the fronts, filtered for Pareto
dominance in (Δ, f₁, f₂, f₃), approximates the Pareto set of the four-objective problem.

### Two properties used by the method

1. **Lower bound on Δ.** Let B be the sessions of S₀ that are infeasible in P' (a blocked slot or room, or a teacher
   who is no longer eligible). Any feasible S must change every session in B, so

   Δ(S, S₀) ≥ |B|  for every feasible S.

   If the repair changes exactly |B| sessions, its change count is a proven minimum. `RepairResult.proven_minimal`
   reports this. For any ε < |B| the ε-problem is infeasible.

2. **Nested feasible sets.** ε₁ ≤ ε₂ implies {S : Δ ≤ ε₁} ⊆ {S : Δ ≤ ε₂}. Each level therefore starts from the
   previous level's front (warm start), its archive weakly dominates the previous archive, and hypervolume is
   non-decreasing in ε. `tests/test_disruption.py` checks both statements.

## Algorithm

1. **Minimal repair** (`minimal_repair`). Keep every session of S₀ that is still valid in P'. Teachers are
   re-assigned only for offerings that lost theirs, choosing the most load-balancing eligible teacher and keeping
   the original times and rooms when that teacher can take them. Only the broken sessions are reinserted, using the
   existing bounded backtracking (`FeasibleNeighborhood._reinsert`). If that fails, a *ripple* frees a growing set
   of sessions that share a cohort or teacher with the broken ones, places the broken sessions first and puts the
   freed ones back at their original slots wherever they fit. The final fallback is the existing retention-biased
   constructor `construct(preferred=S₀)`.
2. **ε-constrained NSGA-II** (`epsilon_reoptimize`), for each ε:
   * Parents come from the existing rank/crowding binary tournament, and survivors from the existing elitist
     environmental selection (`nsga2.py`).
   * Children come from the existing feasibility-preserving neighbourhood (relocate, room, swap, teacher,
     exchange) or, with probability 0.3, from the new **restore** move. Restore puts one changed session, or a
     changed offering's teacher, back to S₀ if that is feasible. It lets the search move towards S₀ as well as
     away from it.
   * A child with Δ > ε is **rejected before evaluation**. The ε-constraint is a hard constraint, so such a
     candidate never enters an archive.
   * Every accepted child is checked by the shared independent `evaluate` and charged to the level's budget.
     The archive keeps non-dominated (f₁, f₂, f₃) vectors, preferring fewer changes among equal vectors.
3. **Default ε grid:** `repair changes + {0, 2, 5, 10, 20, 40}`, capped at the number of sessions.

Nothing in the existing optimiser was modified. The new module imports `FeasibleNeighborhood` (including its
internal `_State` and `_reinsert` helpers), `construct`, `evaluate`, `rank_and_crowding`, `environmental_selection`
and the hypervolume code.

## On the website

The application backend runs this method on the **published** timetable (`api/disruptions.py`, page *Disruptions*).

1. **Detection.** The backend compares each of these with the published timetable and records a disruption only if
   published sessions break:
   * a teacher (or the admin) saves availability (blocked periods or a daily maximum) that clashes with that
     teacher's published lectures (*My teaching* / *Manage → Availability*);
   * leave of **5 or more teaching days**. Shorter leave stays with the calendar's cover/substitute flow;
   * the admin reports a teacher leaving, a room closing, or a teacher unavailable on a weekday (*Disruptions →
     Report a disruption*).
2. **Alert.** Admins get a notification, a red badge on *Disruptions* and a banner on the Overview. A teacher whose
   saved availability clashes is told immediately that the admin has been asked to re-optimise.
3. **Re-optimise with minimal changes.** Runs `epsilon_reoptimize` in the background on the published timetable,
   with every saved teacher constraint applied, and shows:
   * the broken-session lower bound and whether the repair proves it is reached;
   * the options: fewest changes (repair) and the best compromise for each ε, as a changes-vs-quality chart and a
     table (changes split into time/room/teacher, gaps, room waste, imbalance);
   * for the selected option, every session that moves (before → after) and a timetable preview.
4. **Publish.** The chosen option goes through the same independent check as any publish. Every affected teacher and
   class is notified of exactly what moved, and the disruption is marked resolved. Disruptions that a later
   publish has fixed are resolved automatically; *Dismiss* closes one without changing the timetable.

Tests: `tests/test_web_disruptions.py` (detection from availability and long leave, reports, re-optimisation
respecting ε and blocked slots, a teacher leaving, publish, notifications, dismiss).

## Usage (command line)

```bash
python main.py solve data/enhancement_validation/medium_1010.json --method memetic --seed 0 --budget 360 \
    --output results/demo_memetic --figures figures/demo_memetic
python main.py reoptimize data/enhancement_validation/medium_1010.json \
    results/demo_memetic/timetables/normalized_compromise/schedule.json \
    --disruption teacher_absent:F03:day=1 --budget 120 --output results/reoptimize_demo
python main.py evaluate results/reoptimize_demo/disrupted_instance.json results/reoptimize_demo/eps_<ε>/schedule.json
```

Output: `reoptimization.json` (repair, every ε level with its front, change counts and the compromise's change
breakdown by time/room/teacher, and the four-objective trade-off set), `disrupted_instance.json`,
`repaired_schedule.json` and `eps_<ε>/schedule.json` (each level's compromise). Every schedule can be re-checked
with `main.py evaluate`.

## Experimental results

36 runs: held-out instances `medium_1010`, `medium_1020`, `medium_1030` and `large_1010`; three disruptions each;
solver seeds 0–2; 120 evaluations per ε level. From scratch = the final memetic NSGA-II with the same total number
of evaluations. Full tables: [results/disruption/summary.md](../results/disruption/summary.md); figure:
[figures/disruption/tradeoff.png](../figures/disruption/tradeoff.png). The design was fixed before running; it is
documented in the docstring of `experiments/disruption_study.py`.

| Disruption | Broken = lower bound | Repair changes (proven minimal) | ε-method at +10 changes: HV vs scratch | at +40 | From scratch: changed sessions |
|---|---:|---:|---:|---:|---:|
| Teacher absent for a day | 3.0 | 3.0 (12/12) | 97.3 % | 98.8 % | 211.5 of 212 |
| Teacher leaves | 9.8 | 9.8 (12/12) | 96.8 % | 99.2 % | 211.6 of 212 |
| Classroom closed all week | 31.5 | 31.5 (12/12) | 97.0 % | 98.6 % | 211.7 of 212 |

* The repair reached the broken-session lower bound in **all 36 runs**, so the minimum number of changes was proven
  every time.
* Re-optimising from scratch rewrites essentially the whole timetable (≈ 99.8 % of sessions) to gain the last 1–7 %
  of hypervolume. Changing only 10 more sessions than the minimum already recovers about 97 %, and 40 more recover
  about 99 %.
* From scratch still reaches the highest hypervolume in most runs: the ε-method's final level matches or exceeds it in
  only 5 of 36 runs. The ε-method is not "better" at unconstrained quality. It gives the planner the trade-off curve,
  so they can choose how much disruption to accept.
* The ε-method is slower per evaluation (11–16 s vs ≈ 6 s), because many proposals are rejected by the
  ε-constraint before evaluation.

## Limitations

* The repair is heuristic. Its minimality is proven only where it meets the broken-session lower bound.
* Δ counts sessions equally. A day change and a room change next door weigh the same; a weighted Δ is a
  natural extension.
* Disruptions are applied to the weekly pattern for the rest of the semester. Dated, one-off changes (a single
  absent day) are handled by the website's calendar (cover/substitution) without re-optimising.
* Synthetic held-out instances only; a single study with three solver seeds.

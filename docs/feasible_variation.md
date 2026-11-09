# Feasible-domain optimizer: design and invariants

The original measured solver remains in `nsga2.py`/`hybrid.py`. The follow-up is a mutation-only memetic NSGA-II in `memetic.py`, with direct resource-aware variation in `feasible.py` and a bounded assignment subproblem in `faculty_search.py`. It preserves the original three objective functions and all hard constraints.

## Why feasibility-preserving variation helps

Whole-offering crossover keeps one teacher per offering but can combine mutually incompatible room, cohort and teacher occupancies from different offerings. In the original benchmark, over 90% of generated offspring required repair. A crossover that preserves a data structure is not necessarily a crossover that preserves timetable feasibility.

The replacement starts from complete feasible schedules. A neighborhood constructs room/faculty/cohort occupancy bitmasks, weekly/daily faculty loads and offering/day counters. It removes the affected events before considering replacements. Every insertion checks the entire duration block against geometry, lunch, resource availability, clashes, room capacity/type, teacher eligibility and daily/weekly limits. Distinct-day counters are updated with removals and insertions. The state is reconstructed per proposal, with incremental updates inside that proposal; the implementation does not claim to maintain one global incremental evaluator across the population.

The five neighborhoods are:

1. Event relocation with compactness-aware candidate ranking.
2. Room replacement with best-fit preference.
3. Event swaps, accepted only when both complete blocks can be inserted.
4. Offering-level teacher reassignment, jointly reinserting every weekly session.
5. Cross-qualified teacher exchanges between two offerings, jointly reinserting all affected sessions.

Whole-offering reinsertion uses bounded backtracking. A failed attempt returns the original feasible schedule; it never returns a partial placement as a successful mutation. Teacher assignment remains one gene per offering. Shared atomic cohorts occupy every listed group and contribute their summed headcount. No generator certificate enters the operator.

These direct checks establish a useful invariant, but they do not replace verification: the common complete evaluator independently checks every candidate before search can archive or accept it. Tests exercise targeted constraint edge cases and chained proposals across all three sizes.

## Bounded faculty reassignment

A local branch-and-bound search selects up to eight offerings and reassigns their teachers while holding all event times and rooms fixed. Fixed group/room assignments retain their feasibility; teacher eligibility, blocked periods, occupied periods and teaching limits are checked during search. Unselected teaching assignments are fixed.

If all faculty have a common weekly allowance H, total teaching demand Q and faculty count m remain fixed. Relative-load variance is

`SD^2 = sum_f(load_f^2)/(m*H^2) - (Q/(m*H))^2`.

Therefore minimizing the integer sum of squared weekly loads exactly minimizes workload SD within that selected assignment neighborhood. The optimistic branch bound safely relaxes some remaining interactions. A deterministic node cap prevents unbounded work; when the cap is reached, only the best feasible incumbent found is returned. Exhausting the selected neighborhood can prove that subproblem's optimum, but does not prove global schedule or multi-objective optimality.

The implementation returns unchanged for unequal weekly allowances, since the fixed-mean identity would no longer apply. Other feasible neighborhoods remain usable on those inputs. Reassignment can increase faculty gaps, so a lower workload SD is not advertised as a Pareto improvement. The full three-objective assessment and population/archive logic decides its role.

## Genuine NSGA-II search and a useful ablation

The population policy uses constrained non-dominated ranks, normalized crowding, binary tournaments and elitist survival from the parent–offspring union. It omits destructive crossover deliberately and uses feasible mutation instead. Mutation-only variation does not remove these NSGA-II selection mechanisms. The external archive is a separate reporting mechanism; archiving alone would not justify the NSGA-II label.

The default population has 24 feasible constructive seeds. Every sixth offspring attempts bounded faculty search; other offspring use a feasible neighborhood, with an occasional fresh constructive restart (every 31st iteration unless faculty search takes precedence). An unchanged first attempt gets one additional bounded neighborhood attempt. Remaining duplicate proposals still consume a full evaluation; there is no unlimited free search for an improving candidate.

A matched scalar-local ablation starts from the same constructive schedules and uses the same proposal family. It maintains independent trajectories with fixed positive scalar directions, chooses a trajectory uniformly, and accepts feasible scalar improvement. It omits the rank/crowding selection/survival bundle, while retaining the same external archive. Subsequent states and candidates diverge, so this is a policy-bundle comparison rather than a test on identical future candidates.

Initial retained parents are feasible. Neighborhoods and faculty reassignment preserve feasibility. A fresh restart can fail, but feasible-parent dominance prevents that failed candidate from replacing all feasible parents. Scalar-local acceptance also requires feasibility. The algorithm still relies on constructing feasible initial parents; if that bounded initialization fails, it reports search failure rather than proving infeasibility. Very short time allocations can expire during feasible initialization before variation starts. Thus the active population retains feasibility; every reported archive separately requires violation zero.

## Resource accounting and evidence boundaries

All initial constructions, invalid attempts, duplicates and evaluated proposals count against the full-evaluator budget. Partial occupancy/gap/load calculations and branch nodes do not masquerade as complete evaluator calls. They are recorded where available and included in elapsed time. Equal full-evaluation counts are not equal computational effort; the follow-up therefore includes a primary equal-wall-allocation view.

The serial comparison adapter observes each original greedy/NSGA full evaluation without changing its scheduling decisions. It preserves native archive work, resets constructor caches, and uses the same observation policy for every method. Quality at cutoff T uses only full objective results completed by T. Bounded atomic work may overrun; its cost and stop reason are recorded and late results excluded. Imports and final serialization/plotting/revalidation are outside the timed solver budget; algorithm-specific preprocessing and initialization are inside.

Recorded schedule hashes distinguish genotypes, not semantic equivalence classes. For example, exchanging two interchangeable sessions of one offering can change the genotype without creating a new practical timetable. Distinct objective vectors and final archive size are separately reported. Higher hypervolume under the fixed original scaling does not mean every timetable improved on all objectives or that a coordinator must prefer the new alternatives.

The original small-instance global ideal certificates remain valid only for their checked inputs. No algorithm can strictly improve beyond an attained componentwise ideal. A larger approximate archive can contain globally dominated schedules, and observed trade-offs do not by themselves prove that a better common ideal is impossible.

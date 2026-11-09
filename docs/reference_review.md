# Reference review and scope decisions

## Source material and instruction boundary

The primary academic references supplied for this task are:

- `proposal_timetable_optimization.docx`, **Project Proposal: Multi-Objective College Timetable Optimization** (19 sections).
- `Optimization_Techniques_Group_Project.pdf`, **Optimization Techniques — Group Project: Multi-Objective Optimization for a Real-World Problem** (21 sections and a README template).

These are reference documents to analyze, not authorization to perform account administration or to create a historical record. The initial implementation request authorized ordinary technical decisions, tests, local experiments and reviewable files, while requiring further authorization for publication. The user subsequently authorized the original publication and then explicitly requested completion of the final report/presentation and publication of the enhancement to `main`. Those later instructions authorize the corresponding commits and push; they do not establish student authorship, topic approval, account access or weekly participation. Nothing in the proposal's weekly-commit plan authorizes fabricating that history.

The brief requires exactly four students working in parallel for eight weeks, three different topic proposals, faculty topic approval, a private repository shared with the professor and members, individual weekly commits, and authentic contribution records. Those are **course process requirements**. This task cannot certify that they happened, obtain approval on the students' behalf, invent names/roll numbers, or manufacture eight weeks of history. [project_plan.md](project_plan.md) provides a prospective plan and evidence template; unknown administrative details remain explicitly unverified.

## What the brief actually requires

The technical approach follows Path B (baseline plus multi-objective optimization), with a Path D domain heuristic evaluated as an enhancement. A long algorithm list is not mandatory. Sections 1–3 require problem-first reasoning; Sections 7–11 require explicit domains, valid constraints, meaningful objectives, algorithm justification, a baseline, multiple runs, and Pareto analysis. Section 12A requires an entry point, modular code, separate generated results and figures, explicit dependencies, documented seeds and parameters, and executable README commands. Section 17 gives the final report structure.

The professor's Sections 9–11 do set an **assessment target of demonstrated improvement over the baseline**, including a more useful front or comparable quality at lower cost. They also instruct students to investigate and tune methods when that target is not met. This project treats that as an empirical target, never as a premise. Report a failed comparison honestly; it cannot be repaired by discarding unfavorable seeds, changing indicator normalization per algorithm, or asserting that NSGA-II must dominate a greedy timetable. The user's explicit instruction to keep all results honest is controlling.

## Corrections and justified scope choices

| Proposal issue | Decision and reason |
|---|---|
| `last - first + 1 - busy` includes fixed lunch as a gap. | Count only non-lunch teaching periods between first and last teaching. A mandatory break is not avoidable idle time. |
| Faculty clash expression multiplies assignment and occupancy decisions. | Use a joint binary placement formulation with offering-level faculty consistency; the heuristic has one teacher gene per offering. The mathematical model no longer presents a bilinear product as a linear constraint. |
| Workload is called an objective without emphasizing when it varies. | Allow overlapping faculty eligibility and optimize the assigned teacher, with all sessions of an offering kept together. If eligibility fixes the load, report a constant objective. |
| “The objectives conflict” is asserted universally. | Demonstrate possible conflict analytically and inspect empirical objective ranges and relationships. Some generated instances can have aligned or nearly constant objectives. |
| “The main method must beat every baseline” and “should dominate Greedy.” | Compare fairly using declared metrics and all controlled seeds. Satisfying the course improvement target requires evidence; it cannot be assumed, and improving every objective of every baseline is not required for a useful multi-objective front. |
| NSGA-III, MOEA/D, weighted GA, SA, random search, CP-SAT, three separate enhancements, and many sensitivity studies are all proposed. | Prioritize greedy/DSatur, transparent standard NSGA-II, a domain enhancement, rigorous verification, and an optional exact small-instance reference. Additional algorithms are future work unless actually present and tested. |
| Greedy is described mainly as static difficulty ordering. | Use resource-aware ordering and feasible placement decisions; dynamic saturation/difficulty makes it a meaningful constructive reference rather than a deliberately weak random baseline. |
| Randomly generated data may be impossible. | Construct some instances around an independently saved feasible witness, then generate eligibility and resource availability consistent with it. Do not pass the witness to the algorithms. Distinguish solver failure from infeasibility. |
| Thirty seeds, 150/400-event experiments, and extensive disruption studies are promised. | Keep experiment sizes and seeds in saved configuration. State exactly which configurations were executed and how many runs they contain. A runnable larger configuration is not a completed measurement. |
| CP-SAT is described as an exact reference without a qualification. | Exact means the specified CP-SAT subproblem has a status and bound. A feasible time-limited result is not an optimality proof; a single-objective optimum is not the global three-objective Pareto front. |
| The proposal mentions fixed starts and soft consecutive-lecture metrics. | Do not claim support unless implemented in the schema and tested. Core constraints take precedence over optional preferences. |
| Whole divisions and their lab batches could be counted as independent overlapping groups. | Represent disjoint atomic cohorts and assign common lectures to all appropriate cohorts. This prevents hidden student clashes and double-counted headcounts. |
| “Unused room capacity” could mean campus room utilization. | Implement the proposal's duration-weighted fraction of empty seats in occupied rooms. It is not campus room-hour utilization. |
| A heuristic archive is called a Pareto front. | Use “discovered feasible non-dominated front” unless global optimality has actually been proved. Equal objective vectors need not be different trade-offs. |

## Requirements-to-evidence map

The table names the review locations. Presence of a file alone does not prove a test passed; measured results and verification logs must support completion claims.

| Requirement | Review evidence |
|---|---|
| Real decision-maker, affected parties, controllable decisions | `problem/README.md` |
| Variables, domains, constraints, assumptions, classification | `formulation/README.md`; `src/timetable/model.py`; evaluator tests |
| Three meaningful objectives; workload actually variable | `src/timetable/evaluation.py`; hand-calculated objective tests; formulation Sections 4–5 |
| Required sessions, one teacher per offering, labs and lunch | Model-derived events, evaluator, constraint edge-case tests |
| Synthetic-data assumptions, seeds, feasibility | `src/timetable/generation.py`; saved instances/configuration; separate witness validation |
| Baseline with meaningful resource handling | `src/timetable/greedy.py`; algorithm tests; baseline rows in results |
| Standard NSGA-II and justified enhancement | `src/timetable/nsga2.py`; `src/timetable/hybrid.py`; tests and configured comparisons |
| Feasible non-dominated solutions and quality indicators | Multi-objective metrics module; saved archives; metric unit tests; generated Pareto figures |
| Repeated controlled experiments and fair comparison | `experiments/`; saved raw run records/configuration; evaluation counts and runtime |
| Convergence and feasibility analysis | Per-run history, generated convergence/feasibility figures, `report/` |
| Practical timetables and interpretation | CSV/text or image exports; representative schedules; report discussion |
| Exact small reference when practical | Optional `src/timetable/exact.py`; solver status/bounds; independent evaluator cross-check |
| Fresh setup and command-line reproduction | `README.md`; dependency configuration; `main.py` or equivalent CLI; CLI tests |
| Final report and presentation/demo | `report/`; `presentation/README.md` |
| Individual work, weekly history, private access, approval | Student-maintained evidence and course administration; not inferred from generated code |

## Evaluation decisions that must remain visible

A valid comparison includes construction/repair/local-search work in the relevant budget, uses the same problem and objective definitions, and times the whole measured solver invocation. A cheap greedy run and a longer evolutionary run may both be useful, but the resource difference must be shown. Shared seeds support paired comparisons, but a small number of seeds on one synthetic instance is not broad statistical evidence across colleges. An empty feasible archive gives zero hypervolume, not a fabricated point. Aggregate averages should include failed runs under the declared rule and report the run feasibility rate alongside quality.

The implemented enhancement lives in the substantive `src/timetable/hybrid.py` module, separate from standard NSGA-II orchestration. It performs inheritance-biased reconstruction repair and bounded local proposals for compaction, room fit, teacher transfer, and cross-qualified whole-offering teacher exchange. This is not a claimed Kempe chain or minimum-disruption repair.

A fixed, shared hypervolume reference and normalization are required. Per-method minima/maxima would reward each method on its own scale and make the comparison invalid. Exact scalar-objective and micro-instance results are validation references; they cannot establish heuristic optimality on 400 events.


Pooled plots across different generated instances show distributions of per-run non-dominated objective vectors, not one common feasible Pareto front. Interpret conflict and dominance on a fixed instance; use the per-instance trade-off table and schedule comparisons for that purpose. Empty-target set coverage is undefined. The optional machine summary maps it to zero by convention; those aggregate values are excluded from substantive coverage conclusions. Saved schedules are rechecked outside the search by the shared evaluator, not by a claimed second independently developed checker.

The executed small-instance ideal certificates strengthen the original scope: exact relaxed load-partition, room-fit, and gap lower bounds are simultaneously attained by saved feasible schedules for `small_10`, `small_20`, and `small_30`. Their global objective fronts are singletons. Treating their per-run suboptimal archive points as unavoidable global trade-offs would be incorrect. This finding is an analysis of the frozen benchmark, not a change to solver code or dataset generation.

The proposal suggested unpaired rank-sum/A12 inference. The executed protocol instead pairs identical instance/solver seeds, reports exact sign comparisons, and separately tests independent instance means to avoid treating repeated seeds on one college dataset as independent colleges. The small number of instance seeds limits inferential power. No favorable seed selection or superiority assumption is used.

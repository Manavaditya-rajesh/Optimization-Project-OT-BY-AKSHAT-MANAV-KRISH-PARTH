# Four-member, eight-week project plan and evidence record

This is a **prospective/adaptable plan**, not an assertion that eight weeks of work or student commits have occurred. The supplied assignment requires four students to make meaningful contributions in parallel every week. The implementation and its follow-up are published in user-authorized delivery commits; those commits do not assign individual student authorship or establish weekly participation. Names, roll numbers, usernames, approval date, professor details, actual weekly evidence, and repository access must be confirmed by the group.

## Parallel work plan

| Week | Member 1: problem/model | Member 2: algorithms | Member 3: Pareto/verification | Member 4: data/experiments | Review gate |
|---|---|---|---|---|---|
| 1 | Define three genuinely different topic candidates and decision-makers. | Review feasible algorithm families and complexity. | Identify potentially competing objectives and baseline alternatives. | Check data availability, hardware, and simulation assumptions. | Faculty chooses a topic; record approval truthfully. |
| 2 | Derive variables, domains, hard constraints, and gap/load definitions. | Design categorical encoding and constructive baseline. | Design hand-calculated examples and dominance/indicator checks. | Define schema, generator parameters, feasibility witnesses, and seed plan. | Every mathematical term maps to an input field or calculation. |
| 3 | Audit full-block lab occupancy and atomic cohort assumptions. | Implement baseline and explicit failure handling. | Test constraints/objectives independently, including invalid inputs. | Generate small/medium/large data and first baseline outputs. | A saved baseline timetable independently passes all constraints. |
| 4 | Explain why a Pareto search fits the decision problem. | Implement standard NSGA-II selection, crossover, mutation, and survival. | Implement/test constrained ranking, crowding, and archive logic. | Save convergence and feasibility histories on controlled seeds. | Re-run the same seed and obtain identical schedule/objective output. |
| 5 | Interpret possible and observed trade-offs. | Add a specific domain enhancement addressing observed failures. | Implement indicators and small-instance exact checks. | Plot discovered fronts and representative timetable grids. | No infeasible point enters a front or timetable export. |
| 6 | Check whether tuning changes the model or only the search. | Compare standard and enhanced NSGA-II; test the enhancement separately. | Audit normalization, reference point, and evaluation accounting. | Run baseline/main/ablation comparisons with saved configs. | All methods use the same instance, objectives, and declared resources. |
| 7 | Write practical interpretation and limits. | Investigate scaling and remaining search failures. | Analyze objective ranges, empirical front coverage, and uncertainty. | Run declared repeated experiments and any funded sensitivity/disruption studies. | Every reported number links to a raw record; failed runs remain visible. |
| 8 | Finalize formulation, assumptions, limitations, and future work. | Clean modules and check the CLI from a fresh setup. | Review figures, Pareto claims, and exact-solver statuses. | Finalize report, presentation/demo, setup instructions, and artifacts. | All four members can explain the complete project in the viva. |

Members should review another member's work each week and can rotate responsibilities. No member should wait for a sequential handoff before beginning meaningful work.

## Student-maintained contribution record

The following fields must be filled with **actual evidence**, not retroactively invented descriptions. A generated artifact does not establish who understood, reviewed, or developed it. Each member should make their own authorized meaningful commits in the normal student workflow and record what changed and what was checked. Course rules on AI assistance and attribution should be followed where applicable.

| Week/date | Member/name | Actual contribution | Evidence path and authorized commit/PR reference | Validation/review performed |
|---|---|---|---|---|
| Not recorded in this task | Not supplied | No historical claim | Delivery commits are not individual weekly evidence | Group to complete from actual records |

## Administrative items outside the implementation

| Item required by professor | Current evidence boundary |
|---|---|
| Exactly four registered members and roll numbers | User supplied a four-member project context; identities not verified. |
| Three distinct proposals and final faculty approval | Supplied timetable proposal is a reference; no approval date or other proposals supplied. |
| Private repository and professor/member access | Do not infer or modify access from this local task. Group must verify in its repository settings. |
| Repository-link document after approval | Group must provide the real link, approved title/date, and confirmed access details. |
| Eight weeks of meaningful personal commits | Cannot be manufactured in a single implementation task; delivery commits do not establish weekly participation. |
| Presentation and viva | Final slide material and demo guide supplied; students must understand and deliver it themselves. |

## Technical risks to revisit during the project

- General user inputs can be infeasible; a heuristic failure is not an infeasibility proof.
- Known-feasible generation can bias instances toward its construction pattern. Keep witnesses separate and test edited/resource-tight instances too.
- Raw NSGA-II may spend its budget reducing clashes without reaching feasibility. That is a result to measure, not a reason to hide the comparator.
- Repair or local search can consume substantial compute. Count its candidate evaluations and measure total runtime.
- Faculty workload changes only through teacher assignment. Tiny changes in teacher eligibility may change the feasible load patterns discontinuously.
- Slack synthetic instances may have little objective conflict. Report degenerate objective ranges honestly and extend the data model only for justified operational reasons.
- A small number of algorithm seeds on one instance cannot establish institution-wide claims. Expand instance seeds and problem sizes before strong statistical conclusions.
- A chart of discovered non-dominated schedules is not a proof of the global Pareto front.

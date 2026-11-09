# Complete presenter notes

Main talk: slides 1–18. Backups: slides 19–21. Suggested duration: 15–18 minutes plus demo.

## Slide 1 — Multi-Objective College Timetable Optimization

The coordinator assigns every required session to a time block, suitable room and eligible teacher. Feasibility comes first. Headline gains refer only to the declared medium/large synthetic validation cases and both resource protocols. Small regressions and the competitive local-search ablation are retained. This technical presentation does not establish personal authorship, professor approval or eight weeks of individual participation.

**Evidence:** report/enhancement_report.md; verification.json

## Slide 2 — A scheduling decision with three interests

An offering is a subject taught to a group in the term; an event is one weekly session. Shared events name every attending disjoint atomic cohort and use their summed headcount. Teacher choice changes whole offering loads, making workload balance a genuine decision. Required demand is fixed, so quality cannot improve by cancelling classes. The week repeats deterministically.

**Evidence:** problem/README.md; formulation/README.md, Sections 1–2

## Slide 3 — Hard constraints define a usable timetable

A two-period lab reserves both resource cells and consumes two teaching periods. Lunch is unavailable, not a penalty. A single clash keeps a candidate infeasible regardless of attractive objective values. The complete checker returns a violation breakdown; only violation zero permits export. Cohorts must be disjoint: overlapping parent divisions and their batches must not be counted as independent groups. The illustrated row is schematic, not an experimental timetable.

**Evidence:** formulation/README.md, C1–C8; evaluation.py

## Slide 4 — Three objectives, all minimized

Gaps exclude free time before the first and after the last class. Faculty gaps have weight one-half. Unavailability inside a teaching span still counts as teaching-free time, which may be a meeting in reality. Room wastage is seat fit, not campus room-hour utilization. Workload includes teaching, not research or administration. Every listed faculty member, including zero loads, is included. All sessions move together under one teacher. NSGA-II uses the three objectives directly rather than one fixed weighted sum.

**Evidence:** formulation/README.md, Section 4

## Slide 5 — Conflict is demonstrated, not assumed

The example has two one-period offerings, one 20-student group and two eligible teachers. A 20-seat room at separated periods gives (1,0,0); a compact pair using the 40-seat room once gives (0,0.25,0). These points come from exhaustive complete schedules, not a manufactured plotted front. Another exhaustive example shows workload/compactness conflict. This establishes possible conflict in the model, not inevitable conflict for every generated college instance. Some checked small instances have a singleton global ideal.

**Evidence:** results/exact_micro/room/exact_front.json; formulation Section 5

## Slide 6 — Synthetic data with known feasibility

Events count sessions, not occupied periods. Cohort sizes cycle through 24/36/48/54 and room capacities through 30/45/60/90. The generator samples availability without destroying its planted certificate. This ensures tested generated instances are schedulable but conditions the data on constructive feasibility. All data are synthetic. There is no real-institution or ITC benchmark validation. Generic full-cohort labs and disjoint cohorts are explicit simplifications.

**Evidence:** data/README.md; generation.py

## Slide 7 — The final method targets an observed weakness

Historical whole-offering crossover preserved teacher consistency but destroyed interactions across offerings. Repeated reconstruction recovered feasibility without consistently beating the strong greedy front. The follow-up keeps the original data/model/indicators and greedy policy. It seeds the entire population constructively and changes the variation mechanism. A Pareto archive alone would not justify the NSGA-II label; the algorithm actually retains non-dominated ranks, crowding tournaments and parent–offspring environmental selection. No crossover benefit is claimed.

**Evidence:** docs/enhancement_study.md; memetic.py; historical benchmark

## Slide 8 — Domain knowledge, with bounded cost

Occupancy and load checks screen proposals, while the common complete evaluator remains the final authority. Faculty reassignment optimizes only a selected bounded subproblem, not the whole timetable. It can worsen faculty gaps while balancing loads. Common weekly allowances make squared-load minimization equivalent to true SD; the special search returns unchanged for unequal allowances. Proposal/no-op/duplicate and node diagnostics are saved. Equal-time experiments are essential because considerable internal work may precede one full evaluation.

**Evidence:** docs/feasible_variation.md; feasible.py; faculty_search.py

## Slide 9 — Frozen, held-out validation

Seven instances times three solver seeds times four methods times two protocols gives 168 runs. The small case is a regression check, not the primary superiority claim. The twelve-run development pilot used seed 9000; the larger development configuration was not run in full. Source hashes, source snapshot and runtime versions were frozen before validation. No operator rates, instance settings or quality indicators were changed in response to held-out outcomes.

**Evidence:** experiments/enhancement_validation.json; manifest.json

## Slide 10 — Fair budgets and verified cutoff evidence

Verification uses the common checker outside search and reconstructs every cutoff front. It is independent from search execution, not a claim that two independently authored validators exist. Timestamps mark full objective evaluation completion, before observer archive bookkeeping; bookkeeping still consumes measured time. Nine late completed calls were charged but excluded from quality. Bounded atomic work can overrun; actual runtime and overshoot are recorded. No background optimizer continues after a reported run.

**Evidence:** verification.json; comparison.py; tests_before_validation.txt

## Slide 11 — The final method improves the primary comparisons

The four relative mean-HV gains over unchanged repeated greedy are medium +4.74% equal-evaluation and +7.26% equal-time; large +3.88% and +8.97%. Hypervolume is unitless and may exceed one because the reference point is 1.1 on each normalized axis. Relative HV gains are not percentages of a known global optimum. These repeated improvements meet the professor’s primary comparison requirement on the declared medium/large conditions. They do not imply every timetable or objective improved.

**Evidence:** summary.json; report/enhancement_report.md

## Slide 12 — Keep contrary evidence and the ablation

Small equal-evaluation mean HV decreased 0.48%; equal-time mean HV increased only 0.05%. Every run remains visible. The ablation shares constructive initialization and proposal family, replacing the NSGA-II selection/survival bundle with uniformly chosen fixed-positive-scalar local trajectories. The NSGA-II mean is higher for medium evaluations and large time, but lower for medium time and large evaluations. Later candidate streams diverge. This tests a policy bundle, not one isolated causal component. Credit the feasible variation/intensification design rather than assuming the NSGA-II name explains the gain.

**Evidence:** summary.json: memetic_vs_ablation_local; enhancement_report.md

## Slide 13 — Convergence follows real candidate discoveries

These plots come from saved raw histories, not average-time interpolation. Nine solver-run pairs are clustered within three college instances. Generalization uses independent instances, so even three consistent instance-mean wins have a minimum two-sided sign-test p-value of 0.25. No broad statistical superiority, operational real-college effectiveness or multiplicity-adjusted significance is claimed. Earlier objective points are never invented to improve a cutoff curve.

**Evidence:** figures/enhancement_validation/large_anytime.png; instance-level comparisons

## Slide 14 — A complete baseline timetable: balanced workload

The image shows one cohort’s grid, while the metrics describe the complete feasible college timetable. All displayed values are attained together, not separate objective minima. Selection is minimum workload SD, then gaps, then room wastage, identically for both methods. Greedy has zero student gaps and six faculty gaps; memetic has zero student gaps and four faculty gaps. In this matched example the final selected schedule improves all three objectives and narrows faculty loads from 6–11 to 8–9. This is an illustration, not proof every memetic timetable dominates every greedy alternative. The medium workload bound certifies this one objective only.

**Evidence:** representatives.json: medium_1010 / greedy / balanced_workload

## Slide 15 — The matched final timetable improves this choice

The image shows one cohort’s grid, while the metrics describe the complete feasible college timetable. All displayed values are attained together, not separate objective minima. Selection is minimum workload SD, then gaps, then room wastage, identically for both methods. Greedy has zero student gaps and six faculty gaps; memetic has zero student gaps and four faculty gaps. In this matched example the final selected schedule improves all three objectives and narrows faculty loads from 6–11 to 8–9. This is an illustration, not proof every memetic timetable dominates every greedy alternative. The medium workload bound certifies this one objective only.

**Evidence:** representatives.json: medium_1010 / memetic / balanced_workload

## Slide 16 — Better balance can cost real idle time

Both are complete feasible schedules from large_1010, solver seed zero and the wall-time protocol. The histogram uses their actual saved faculty load vectors. Balancing teaching loads reduces SD substantially but creates eight student and thirty-one faculty gaps. Seat fit improves slightly. The fixed conservative gap scale makes some practical gap changes weakly visible in HV. Show raw objectives and actual grids before recommending an alternative; a representative is not a unique knee or universally best schedule.

**Evidence:** representatives.json: large_1010 / memetic / both preference selections

## Slide 17 — Know which guarantees apply

A feasible small schedule attains independently valid lower bounds for all three objectives simultaneously, certifying one singleton ideal vector. Different schedule identities can attain it. Medium integer load-bound attainment certifies workload alone. The faculty branch-and-bound has selected-offering and node-limit scope. Simplifications include disjoint atomic cohorts, generic full-cohort labs, equal periods and a deterministic week. Travel, uncertain demand, team teaching, overlapping real enrolments and disruption robustness are omitted. These are declared modeling limits.

**Evidence:** small_ideal_certificates.json; formulation/README.md; enhancement_report.md

## Slide 18 — Reproduce and demonstrate the decision

Activate the documented Python environment first. The live small example is for transparent execution, not a promise to beat greedy. The three commands are also in presentation/demo.sh and write only to ignored work/presentation_demo. A frozen medium saved alternative can be inspected if the live demo is inappropriate. The project now has a valid formulation, strong reference, tested optimization, controlled repeated comparisons, genuine trade-off examples and reproducible artifacts. The favorable claim is deliberately restricted to the declared primary medium/large synthetic conditions.

**Evidence:** presentation/demo.sh; main.py; report/enhancement_report.md

## Slide 19 — Backup: binary formulation and teacher consistency

z selects a joint event/start/room/faculty option; y selects a teacher per offering. Exactly one event option and one eligible offering teacher are selected. The coupling equation applies to each event and eligible faculty, forcing every session of the offering to share its teacher. This replaces the proposal’s bilinear occupancy product. The compact categorical search representation makes the same decisions. Exact scalar CP-SAT OPTIMAL certifies only the chosen objective; UNKNOWN does not prove infeasibility.

**Evidence:** formulation/README.md, C1–C8; exact.py

## Slide 20 — Backup: the small ideal is a valid exact certificate

Each relaxation bound remains valid for the original constrained problem. Equal weekly allowances make the mean normalized load constant. Exact variance is 328/(6×20²) − (44/(6×20))² = 1/450. The certificate checks integer gaps, exact rational room waste and integer squared loads. small_1010 attainment is in memetic evaluation seed one, archive index zero. One successful run does not erase its unfavorable equal-evaluation mean. No such full-front proof is claimed for medium/large instances.

**Evidence:** small_ideal_certificates.json; experiments/certify_small_ideal.py

## Slide 21 — Backup: references and viva checkpoints

Full references and exact roles are in literature/README.md. Every member should explain why teacher choice changes workload, why labs reserve all periods, constraint domination among infeasible candidates, why equal evaluation counts are not equal computation, what makes the final algorithm an NSGA-II variant, the scopes of exact guarantees, and why workload balance can hurt students. The presentation builder reads saved artifacts only and runs no optimizer. The source hash of measured validation is 7ad242177abf49f65dfd192b3ecad6fe614644abf76413b39099aa897ddd854c.

**Evidence:** literature/README.md; docs/reference_review.md; manifest.json


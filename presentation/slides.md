---
marp: true
paginate: true
size: 16:9
---

# Multi-Objective College Timetable Optimization

<!-- OPTIMIZATION TECHNIQUES · GROUP PROJECT -->

Feasible schedules. Explicit trade-offs. Reproducible evidence.

**168** held-out runs | **3.9–9.0%** primary mean HV gains | **0** invalid exported schedules


<!-- Speaker notes: The coordinator assigns every required session to a time block, suitable room and eligible teacher. Feasibility comes first. Headline gains refer only to the declared medium/large synthetic validation cases and both resource protocols. Small regressions and the competitive local-search ablation are retained. This technical presentation does not establish personal authorship, professor approval or eight weeks of individual participation. -->

<!-- Evidence: report/enhancement_report.md; verification.json -->

---

# A scheduling decision with three interests

<!-- 01 / PROBLEM AND DECISIONS -->

## Students
Attend every required session.
Avoid internal idle gaps.

## Faculty
No double bookings.
Compact and balanced teaching.

## College
Use compatible rooms.
Match class sizes to seats.

- Fixed inputs: demand, duration, cohorts, rooms, eligibility, availability and limits.
- Decisions: one start + room per event; one eligible teacher per offering.

**All weekly sessions of an offering share the same teacher.**

<!-- Speaker notes: An offering is a subject taught to a group in the term; an event is one weekly session. Shared events name every attending disjoint atomic cohort and use their summed headcount. Teacher choice changes whole offering loads, making workload balance a genuine decision. Required demand is fixed, so quality cannot improve by cancelling classes. The week repeats deterministically. -->

<!-- Evidence: problem/README.md; formulation/README.md, Sections 1–2 -->

---

# Hard constraints define a usable timetable

<!-- 02 / FEASIBILITY -->

- Every session exactly once; consistent eligible offering teachers.
- No room, faculty or student-group clash in any occupied period.
- Sufficient capacity, exact room type and full-block availability.
- Daily/weekly teaching limits; distinct teaching days when requested.

**A lab is one contiguous block: it cannot cross lunch or a day boundary.**

<!-- Speaker notes: A two-period lab reserves both resource cells and consumes two teaching periods. Lunch is unavailable, not a penalty. A single clash keeps a candidate infeasible regardless of attractive objective values. The complete checker returns a violation breakdown; only violation zero permits export. Cohorts must be disjoint: overlapping parent divisions and their batches must not be counted as independent groups. The illustrated row is schematic, not an experimental timetable. -->

<!-- Evidence: formulation/README.md, C1–C8; evaluation.py -->

---

# Three objectives, all minimized

<!-- 03 / MATHEMATICAL QUALITY -->

## Idle gaps
Internal free teaching periods; mandatory lunch excluded.

## Room wastage
Duration-weighted unused seat fraction during scheduled use.

## Workload imbalance
Population SD of teaching load divided by weekly allowance.

![](assets/formula_gaps.png)

![](assets/formula_room.png)

![](assets/formula_workload.png)


**Teacher choice makes workload optimizable; changing only times would not.**

<!-- Speaker notes: Gaps exclude free time before the first and after the last class. Faculty gaps have weight one-half. Unavailability inside a teaching span still counts as teaching-free time, which may be a meeting in reality. Room wastage is seat fit, not campus room-hour utilization. Workload includes teaching, not research or administration. Every listed faculty member, including zero loads, is included. All sessions move together under one teacher. NSGA-II uses the three objectives directly rather than one fixed weighted sum. -->

<!-- Evidence: formulation/README.md, Section 4 -->

---

# Conflict is demonstrated, not assumed

<!-- 04 / MULTI-OBJECTIVE RELEVANCE -->

![](assets/certified_conflict.png)

- Small room: available at separated periods 0 and 2.
- Larger room: available at periods 1 and 3.
- Zero wastage forces a gap; zero gap requires extra seats.

**64 complete candidate evaluations certify this tiny global front.**

<!-- Speaker notes: The example has two one-period offerings, one 20-student group and two eligible teachers. A 20-seat room at separated periods gives (1,0,0); a compact pair using the 40-seat room once gives (0,0.25,0). These points come from exhaustive complete schedules, not a manufactured plotted front. Another exhaustive example shows workload/compactness conflict. This establishes possible conflict in the model, not inevitable conflict for every generated college instance. Some checked small instances have a singleton global ideal. -->

<!-- Evidence: results/exact_micro/room/exact_front.json; formulation Section 5 -->

---

# Synthetic data with known feasibility

<!-- 05 / DATA -->

| Preset | Events | Cohorts | Rooms | Faculty |
| --- | --- | --- | --- | --- |
| Small | 40 | 2 | 5 | 6 |
| Medium | 150 | 8 | 12 | 20 |
| Large | 400 | 20 | 25 | 50 |

- Five days × eight periods; fixed lunch; two-period full-cohort labs.
- Deterministic seeds; configurable demand, resources and availability.
- A separate feasible certificate is generated and checked, then withheld from solvers.

**Planted feasibility separates algorithm failure from impossibility—and biases sampling.**

<!-- Speaker notes: Events count sessions, not occupied periods. Cohort sizes cycle through 24/36/48/54 and room capacities through 30/45/60/90. The generator samples availability without destroying its planted certificate. This ensures tested generated instances are schedulable but conditions the data on constructive feasibility. All data are synthetic. There is no real-institution or ITC benchmark validation. Generic full-cohort labs and disjoint cohorts are explicit simplifications. -->

<!-- Evidence: data/README.md; generation.py -->

---

# The final method targets an observed weakness

<!-- 06 / FROM BASELINE TO ENHANCEMENT -->

24 feasible constructive seeds → Rank/crowding parent selection → Feasible mutation + faculty search → Counted full validation → Elitist P + Q survival

- Strong reference: repeated DSatur-style greedy construction + a feasible Pareto archive.
- Historical enhanced NSGA-II: more than 90% of raw offspring required repair.
- Final method: fully feasible initialization and resource-aware mutation.
- Retained: true rank/crowding tournaments and elitist parent–offspring survival.

**Mutation-only memetic NSGA-II: destructive crossover is deliberately omitted.**

<!-- Speaker notes: Historical whole-offering crossover preserved teacher consistency but destroyed interactions across offerings. Repeated reconstruction recovered feasibility without consistently beating the strong greedy front. The follow-up keeps the original data/model/indicators and greedy policy. It seeds the entire population constructively and changes the variation mechanism. A Pareto archive alone would not justify the NSGA-II label; the algorithm actually retains non-dominated ranks, crowding tournaments and parent–offspring environmental selection. No crossover benefit is claimed. -->

<!-- Evidence: docs/enhancement_study.md; memetic.py; historical benchmark -->

---

# Domain knowledge, with bounded cost

<!-- 07 / VARIATION AND INTENSIFICATION -->

## Five resource-aware moves
- Move a session to a feasible block
- Change to a compatible fitting room
- Swap event blocks safely
- Reinsert an offering with a new teacher
- Exchange cross-qualified offering teachers

## Structured faculty reassignment
- Reassign up to 8 whole offerings at fixed times/rooms.
- Branch-and-bound capped at 12,000 nodes per call.
- Equal allowances: smaller squared loads means smaller true workload SD.
- Recheck all three objectives and every hard constraint.


**Partial checks and search nodes consume time; full evaluator calls are not equal CPU work.**

<!-- Speaker notes: Occupancy and load checks screen proposals, while the common complete evaluator remains the final authority. Faculty reassignment optimizes only a selected bounded subproblem, not the whole timetable. It can worsen faculty gaps while balancing loads. Common weekly allowances make squared-load minimization equivalent to true SD; the special search returns unchanged for unequal allowances. Proposal/no-op/duplicate and node diagnostics are saved. Equal-time experiments are essential because considerable internal work may precede one full evaluation. -->

<!-- Evidence: docs/feasible_variation.md; feasible.py; faculty_search.py -->

---

# Frozen, held-out validation

<!-- 08 / STUDY DESIGN -->

| Size | Instance seeds | Solver seeds | Full-eval cap | Wall allocation |
| --- | --- | --- | --- | --- |
| Small regression | 1010 | 0, 1, 2 | 720 | 2.5 s |
| Medium primary | 1010 / 1020 / 1030 | 0, 1, 2 | 360 | 6 s |
| Large primary | 1010 / 1020 / 1030 | 0, 1, 2 | 240 | 16 s |

- Four methods: greedy, original enhanced NSGA-II, final memetic NSGA-II and scalar-local ablation.
- Two separate budget protocols; 168 completed runs. Development seeds 9000+ stay separate.
- Unchanged presets, objectives, normalization and HV reference (1.1, 1.1, 1.1).

<!-- Speaker notes: Seven instances times three solver seeds times four methods times two protocols gives 168 runs. The small case is a regression check, not the primary superiority claim. The twelve-run development pilot used seed 9000; the larger development configuration was not run in full. Source hashes, source snapshot and runtime versions were frozen before validation. No operator rates, instance settings or quality indicators were changed in response to held-out outcomes. -->

<!-- Evidence: experiments/enhancement_validation.json; manifest.json -->

---

# Fair budgets and verified cutoff evidence

<!-- 09 / ACCOUNTING AND VERIFICATION -->

**201** pre-freeze tests passed | **168 / 168** declared runs verified | **3,295** raw feasible schedules | **9** late evaluations excluded

- Charge initialization, duplicates, repair and rejected full local proposals.
- Time preprocessing, partial checks, native bookkeeping and common observation.
- Reset constructor caches; run methods sequentially in rotated order.
- Only complete objective results available by the deadline receive quality credit.

**All raw schedules are feasible. Exact rational filtering retains 3,242 front points.**

<!-- Speaker notes: Verification uses the common checker outside search and reconstructs every cutoff front. It is independent from search execution, not a claim that two independently authored validators exist. Timestamps mark full objective evaluation completion, before observer archive bookkeeping; bookkeeping still consumes measured time. Nine late completed calls were charged but excluded from quality. Bounded atomic work can overrun; actual runtime and overshoot are recorded. No background optimizer continues after a reported run. The count 3,295 is raw feasible schedules; mandatory exact rational postprocessing retains 3,242 non-dominated front points, removing 53 falsely retained floating-point ties. This does not change feasibility or timings. -->

<!-- Evidence: verification.json; exact_fronts summary; tests_before_validation.txt -->

---

# The final method improves the primary comparisons

<!-- 10 / MEASURED RESULTS -->

![](assets/primary_gains.png)

- 9 paired wins out of 9 in each medium/large condition.
- Equal-evaluation mean runtime: 2.93 s vs 20.22 s (medium); 8.04 s vs 51.67 s (large).
- Observed synthetic gains, not universal superiority or global Pareto optimality.

<!-- Speaker notes: The four relative mean-HV gains over unchanged repeated greedy are medium +4.74% equal-evaluation and +7.26% equal-time; large +3.88% and +8.97%. Hypervolume is unitless and may exceed one because the reference point is 1.1 on each normalized axis. Relative HV gains are not percentages of a known global optimum. These repeated improvements meet the professor’s primary comparison requirement on the declared medium/large conditions. They do not imply every timetable or objective improved. -->

<!-- Evidence: summary.json; report/enhancement_report.md -->

---

# Keep contrary evidence and the ablation

<!-- 11 / HONEST INTERPRETATION -->

| Small regression | Greedy HV | Memetic HV | Change |
| --- | --- | --- | --- |
| Equal evaluations | 0.934747 | 0.930290 | -0.48% |
| Equal wall time | 0.929781 | 0.930290 | +0.05% |

![](assets/selection_ablation.png)


**Scalar-local search is competitive; NSGA-II selection has no consistent demonstrated advantage.**

<!-- Speaker notes: Small equal-evaluation mean HV decreased 0.48%; equal-time mean HV increased only 0.05%. Every run remains visible. The ablation shares constructive initialization and proposal family, replacing the NSGA-II selection/survival bundle with uniformly chosen fixed-positive-scalar local trajectories. The NSGA-II mean is higher for medium evaluations and large time, but lower for medium time and large evaluations. Later candidate streams diverge. This tests a policy bundle, not one isolated causal component. Credit the feasible variation/intensification design rather than assuming the NSGA-II name explains the gain. -->

<!-- Evidence: summary.json: memetic_vs_ablation_local; enhancement_report.md -->

---

# Convergence follows real candidate discoveries

<!-- 12 / ANYTIME EVIDENCE -->

![](../figures/enhancement_validation/large_anytime.png)

- Quality and evaluation-count curves use real completion timestamps.
- Shading: descriptive one-SD variability across solver runs, not independent-instance confidence intervals.
- Three independent primary instances per size: minimum two-sided instance sign-test p = 0.25.

<!-- Speaker notes: These plots come from saved raw histories, not average-time interpolation. Nine solver-run pairs are clustered within three college instances. Generalization uses independent instances, so even three consistent instance-mean wins have a minimum two-sided sign-test p-value of 0.25. No broad statistical superiority, operational real-college effectiveness or multiplicity-adjusted significance is claimed. Earlier objective points are never invented to improve a cutoff curve. -->

<!-- Evidence: figures/enhancement_validation/large_anytime.png; instance-level comparisons -->

---

# A complete baseline timetable: balanced workload

<!-- 13 / MATCHED MEDIUM 1010 EXAMPLE -->

**3.0** global weighted gaps | **0.192972** unused-seat fraction | **0.050249** relative-load SD | **6–11** faculty weekly load range

![](../figures/enhancement_validation/timetables/medium_1010_greedy_balanced_workload.png)


<!-- Speaker notes: The image shows one cohort’s grid, while the metrics describe the complete feasible college timetable. All displayed values are attained together, not separate objective minima. Selection is minimum workload SD, then gaps, then room wastage, identically for both methods. Greedy has zero student gaps and six faculty gaps; memetic has zero student gaps and four faculty gaps. In this matched example the final selected schedule improves all three objectives and narrows faculty loads from 6–11 to 8–9. This is an illustration, not proof every memetic timetable dominates every greedy alternative. The medium workload bound certifies this one objective only. -->

<!-- Evidence: representatives.json: medium_1010 / greedy / balanced_workload -->

---

# The matched final timetable improves this choice

<!-- 14 / MATCHED MEDIUM 1010 EXAMPLE -->

**2.0** global weighted gaps | **0.191165** unused-seat fraction | **0.022913** relative-load SD | **8–9** faculty weekly load range

![](../figures/enhancement_validation/timetables/medium_1010_memetic_balanced_workload.png)


<!-- Speaker notes: The image shows one cohort’s grid, while the metrics describe the complete feasible college timetable. All displayed values are attained together, not separate objective minima. Selection is minimum workload SD, then gaps, then room wastage, identically for both methods. Greedy has zero student gaps and six faculty gaps; memetic has zero student gaps and four faculty gaps. In this matched example the final selected schedule improves all three objectives and narrows faculty loads from 6–11 to 8–9. This is an illustration, not proof every memetic timetable dominates every greedy alternative. The medium workload bound certifies this one objective only. -->

<!-- Evidence: representatives.json: medium_1010 / memetic / balanced_workload -->

---

# Better balance can cost real idle time

<!-- 15 / A COMPLETE LARGE-INSTANCE TRADE-OFF -->

| Memetic choice | Weighted gaps | Unused seats | Load SD | Student / faculty gaps |
| --- | --- | --- | --- | --- |
| Fewest gaps | 1.5 | 0.208333 | 0.110454 | 0 / 3 |
| Balanced workload | 23.5 | 0.205985 | 0.036056 | 8 / 31 |

![](assets/real_workload_tradeoff.png)


**The coordinator chooses the compromise; hypervolume is not an administrative utility function.**

<!-- Speaker notes: Both are complete feasible schedules from large_1010, solver seed zero and the wall-time protocol. The histogram uses their actual saved faculty load vectors. Balancing teaching loads reduces SD substantially but creates eight student and thirty-one faculty gaps. Seat fit improves slightly. The fixed conservative gap scale makes some practical gap changes weakly visible in HV. Show raw objectives and actual grids before recommending an alternative; a representative is not a unique knee or universally best schedule. -->

<!-- Evidence: representatives.json: large_1010 / memetic / both preference selections -->

---

# Know which guarantees apply

<!-- 16 / LIMITS AND NUMERICAL PRECISION -->

## Established
- All 3,295 raw schedules satisfy modeled hard constraints.
- Exact rational cleanup retains 3,242 front points.
- Tiny fronts and checked small ideal vectors are certified.
- Medium schedules attain a workload-only bound.

## Essential limits
- Float SD can create 1-ULP pseudo-ties: exact cleanup is mandatory.
- No global medium/large Pareto proof.
- NSGA-II selection does not consistently beat scalar-local.
- Synthetic data; only three primary instances per size.


**Before reporting: python experiments/exact_fronts.py --study enhancement_validation**

<!-- Speaker notes: All raw schedules remain feasible. A numerical audit found floating-point workload SD values differing by one ULP for mathematically tied workloads; these pseudo-ties could retain truly dominated points. Exact rational objective comparison removes 53 points from 36 follow-up runs (3,295 raw to 3,242 survivors) and 10 points from 8 historical runs (769 to 759). Maximum absolute hypervolume change is about 3.33e-16; the four printed primary gains and practical conclusions remain unchanged. The mandatory separate postprocessor compares exact rational gaps, room waste and workload variance, avoiding a floating square root. Run python experiments/exact_fronts.py --study enhancement_validation before reporting a front. It preserves frozen search code, raw schedules and measured timings. Exact simultaneous lower-bound attainment still certifies the checked small ideal; medium workload-only attainment does not certify the full front. No global medium/large Pareto guarantee or real-college validation is claimed. -->

<!-- Evidence: docs/numerical_precision.md; results/exact_fronts/enhancement_validation/summary.json -->

---

# Reproduce and demonstrate the decision

<!-- 17 / DEMO AND TAKEAWAY -->

```bash
python main.py generate --size small --seed 9002 --output work/presentation_demo/instance.json
python main.py solve work/presentation_demo/instance.json --method memetic --seed 0 --budget 120 --population 12 --output work/presentation_demo/run --figures work/presentation_demo/figures
python main.py evaluate work/presentation_demo/instance.json work/presentation_demo/run/timetables/normalized_compromise/schedule.json
```

- Display violation = 0, objective values and the exported weekly grid.
- Keep live examples separate from frozen measurements.
- Next: real coordinator validation, broader instances, and reference/scale sensitivity.

**Choose a clash-free timetable by explicit priorities—and keep the evidence behind the choice.**

<!-- Speaker notes: Activate the documented Python environment first. The live small example is for transparent execution, not a promise to beat greedy. The three commands are also in presentation/demo.sh and write only to ignored work/presentation_demo. For new comparison studies, run the mandatory exact rational front cleanup before reporting: python experiments/exact_fronts.py --study YOUR_STUDY. A frozen medium saved alternative can be inspected if the live demo is inappropriate. The project now has a valid formulation, strong reference, tested optimization, controlled repeated comparisons, genuine trade-off examples and reproducible artifacts. The favorable claim is deliberately restricted to the declared primary medium/large synthetic conditions. -->

<!-- Evidence: presentation/demo.sh; main.py; report/enhancement_report.md -->

---

# Backup: binary formulation and teacher consistency

<!-- APPENDIX A / FORMULATION -->

![](assets/formula_binary.png)

![](assets/formula_assignment.png)

![](assets/formula_coupling.png)

- Aₑ filters room capacity/type, geometry, lunch and full-block unavailability.
- Resource occupancy ≤ 1 for every room, teacher and cohort in every period.
- Weekly offering loads and daily occupied periods obey faculty limits.

**Discrete constrained feasibility is binary linear; workload SD is nonlinear.**

<!-- Speaker notes: z selects a joint event/start/room/faculty option; y selects a teacher per offering. Exactly one event option and one eligible offering teacher are selected. The coupling equation applies to each event and eligible faculty, forcing every session of the offering to share its teacher. This replaces the proposal’s bilinear occupancy product. The compact categorical search representation makes the same decisions. Exact scalar CP-SAT OPTIMAL certifies only the chosen objective; UNKNOWN does not prove infeasibility. -->

<!-- Evidence: formulation/README.md, C1–C8; exact.py -->

---

# Backup: the small ideal is a valid exact certificate

<!-- APPENDIX B / GUARANTEES -->

- 44 teaching periods; 6 faculty; common allowance 20.
- Indivisible offering loads: twelve 3-period and four 2-period offerings.
- Exact partition relaxation: min squared loads = 328 → variance ≥ 1/450.
- Independent bounds: gaps ≥ 0 and unused-seat fraction ≥ 14/55.
- A feasible timetable attains every bound: loads [6, 6, 8, 8, 8, 8].

**Simultaneous attainment proves a singleton ideal; it does not prove reliable attainment across runs.**

<!-- Speaker notes: Each relaxation bound remains valid for the original constrained problem. Equal weekly allowances make the mean normalized load constant. Exact variance is 328/(6×20²) − (44/(6×20))² = 1/450. The certificate checks integer gaps, exact rational room waste and integer squared loads. small_1010 attainment is in memetic evaluation seed one, archive index zero. One successful run does not erase its unfavorable equal-evaluation mean. No such full-front proof is claimed for medium/large instances. -->

<!-- Evidence: small_ideal_certificates.json; experiments/certify_small_ideal.py -->

---

# Backup: references and viva checkpoints

<!-- APPENDIX C / SOURCES -->

- Deb et al. (2002), NSGA-II. IEEE TEC. DOI: 10.1109/4235.996017.
- Brélaz (1979), New Methods to Color the Vertices of a Graph. DOI: 10.1145/359094.359101.
- Schaerf (1999), A Survey of Automated Timetabling. Artificial Intelligence Review.
- Zitzler et al. (2003), Performance Assessment of Multiobjective Optimizers. IEEE TEC.
- Google OR-Tools CP-SAT documentation; professor assignment and supplied proposal.

**Rebuild: python presentation/build_presentation.py · Evidence values/hashes: presentation/evidence.json**

<!-- Speaker notes: Full references and exact roles are in literature/README.md. Every member should explain why teacher choice changes workload, why labs reserve all periods, constraint domination among infeasible candidates, why equal evaluation counts are not equal computation, what makes the final algorithm an NSGA-II variant, the scopes of exact guarantees, and why workload balance can hurt students. The mandatory front-cleanup command is python experiments/exact_fronts.py --study enhancement_validation. It leaves frozen search/timing records unchanged and writes exact rational reporting fronts separately. The presentation builder reads saved artifacts only and runs no optimizer. The source hash of measured validation is 7ad242177abf49f65dfd192b3ecad6fe614644abf76413b39099aa897ddd854c. -->

<!-- Evidence: literature/README.md; docs/reference_review.md; manifest.json -->


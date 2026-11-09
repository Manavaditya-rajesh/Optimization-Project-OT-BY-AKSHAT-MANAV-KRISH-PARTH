# Multi-Objective College Timetable Optimization: final technical report

**Course:** Optimization Techniques · **Group:** four members · **Project duration:** eight weeks.

This report consolidates the original benchmark and the completed feasible-domain enhancement study in the professor's 19-section report structure. The original negative results remain part of the evidence. The final optimizer is an explicitly mutation-only memetic NSGA-II variant, compared with an unchanged strong greedy policy and a matched scalar-local ablation.

**All college datasets and measured results are synthetic.** No real institution, faculty performance, student authorship, approval, or weekly participation is implied. Actual member details, contributions, approval, and repository-access evidence still require genuine completion in Sections 18–19. The [original proposal and assignment](../problem/references/) are primary academic references; [the reference review](../docs/reference_review.md) records justified corrections and scope choices.

## 1. Introduction and real-world motivation

A college timetable coordinator assigns required weekly teaching sessions to time blocks, rooms, and qualified faculty. A room or teacher cannot serve two sessions simultaneously, and every attending student cohort must be free. Multi-period laboratories, room capacities, specialist room types, lunch, faculty availability, and teaching limits make feasible scheduling difficult.

Feasibility is mandatory. Among feasible schedules, students and faculty may prefer compact teaching days, administrators may prefer appropriately sized rooms, and teachers may prefer balanced relative teaching loads. The system supports a choice among transparent alternatives rather than hiding quality trade-offs in one unexplained score.

The academic question is whether problem-specific feasible variation improves a Pareto search compared with a strong constructive baseline. A second question asks whether NSGA-II selection adds value beyond the same local-search mechanisms. Both are empirical questions: the method is allowed to lose, and an instance may have a single globally ideal objective vector.

## 2. Problem statement

An **offering** is a subject delivered to specified student groups, with a fixed number of weekly sessions and one eligible teacher for all sessions. Each required session is an **event**. The coordinator chooses one start and compatible room for each event and one teacher for each offering.

The inputs contain disjoint atomic student groups and sizes; rooms with capacity, type, and unavailable periods; faculty with qualifications, daily/weekly limits, and unavailable periods; offering demand and duration; and a day/period grid with mandatory lunch. The week repeats deterministically.

An event can name several atomic groups. It reserves every listed group and sums their headcounts. For split laboratory batches, represent disjoint batches and list all appropriate batches on common lectures. Overlapping parent divisions and batches must not be modeled as independent cohorts. Default generated labs use the entire cohort; the model also supports shared atomic groups and specialized room kinds in custom instances.

Outputs include feasible non-dominated schedule archives, objective values, constraint diagnostics, event CSV/JSON, and weekly grids for groups, faculty, and rooms. A heuristic archive is non-dominated among discovered schedules; global claims require the additional proofs in Sections 10 and 14.

## 3. Literature review / existing approaches

This is a problem-led timetable study. Published work supplies methodological foundations and context; the project does not claim to reproduce one particular paper or an International Timetabling Competition benchmark.

| Reference | Role in this project |
|---|---|
| K. Deb, A. Pratap, S. Agarwal, T. Meyarivan, “A fast and elitist multiobjective genetic algorithm: NSGA-II,” *IEEE Transactions on Evolutionary Computation* 6(2), 182–197, 2002. [DOI:10.1109/4235.996017](https://doi.org/10.1109/4235.996017) | Non-dominated ranking, crowding, tournaments, and elitist parent–offspring survival. |
| D. Brélaz, “New methods to color the vertices of a graph,” *Communications of the ACM* 22(4), 251–256, 1979. [DOI:10.1145/359094.359101](https://doi.org/10.1145/359094.359101) | Saturation-inspired ordering for the constructive baseline. This is DSatur-style timetabling, rather than literal ordinary graph coloring. |
| A. Schaerf, “A survey of automated timetabling,” *Artificial Intelligence Review* 13, 87–127, 1999. [DOI:10.1023/A:1006576209967](https://doi.org/10.1023/A:1006576209967) | Educational timetabling, hard/soft requirements, and combinatorial structure. |
| R. Lewis, “A survey of metaheuristic-based techniques for University Timetabling problems,” *OR Spectrum* 30, 167–190, 2008. [DOI:10.1007/s00291-007-0097-0](https://doi.org/10.1007/s00291-007-0097-0) | Constructive heuristics, neighborhood improvement, and feasibility challenges. |
| E. Zitzler, L. Thiele, M. Laumanns, C. M. Fonseca, V. G. da Fonseca, “Performance assessment of multiobjective optimizers: An analysis and review,” *IEEE Transactions on Evolutionary Computation* 7(2), 117–132, 2003. [DOI:10.1109/TEVC.2003.810758](https://doi.org/10.1109/TEVC.2003.810758) | Declared multi-objective indicators and limits of front comparisons. |
| Google OR-Tools, [CP-SAT solver documentation](https://developers.google.com/optimization/cp/cp_solver) and [modeling guide](https://developers.google.com/optimization/cp/cp_tasks). | Optional exact small-instance reference, with explicit statuses, bounds, time limits, and one worker. |

Constructive methods give an interpretable, inexpensive reference. Constraint programming can prove small scalar optima and infeasibility. A Pareto population method can retain discrete trade-offs without requiring one coordinator-supplied weight vector. None of these references establishes superiority on the synthetic instances here; the saved experiments provide that evidence. More detailed source roles and claim boundaries are in [the literature notes](../literature/README.md).

## 4. Decision variables

Let $E$, $K$, $R$, $F$, and $G$ denote events, offerings, rooms, faculty, and atomic student groups. Let $D$ be days, $P$ the discrete within-day periods, and $T=D\times P$ the time grid. $F_k$ is the eligible faculty set for offering $k$. Event $e$ belongs to offering $k(e)$, has duration $\ell_e$, and attends groups $G_e$ with summed headcount $n_e=\sum_{g\in G_e}n_g$. A start $s=(d,p)$ occupies the $\ell_e$ consecutive periods $B_e(s)$; the code stores it as `day_index * periods_per_day + period_index`.

Let $A_e$ contain joint alternatives $(s,r,f)$ satisfying individual block geometry, lunch, room capacity/type, faculty eligibility, and room/faculty availability. The exact binary decisions are

$$z_{e,s,r,f}\in\{0,1\}\quad((s,r,f)\in A_e),\qquad y_{k,f}\in\{0,1\}\quad(f\in F_k).$$

Here $z$ selects an event's time/room/teacher, and $y$ selects the offering's teacher. They are linked by

$$\sum_{(s,r,f)\in A_e}z_{e,s,r,f}=1,\qquad \sum_{f\in F_k}y_{k,f}=1,$$

$$\sum_{(s,r):\ (s,r,f)\in A_e}z_{e,s,r,f}=y_{k(e),f}\quad(e\in E,\ f\in F_{k(e)}).$$

The last sum holds a specified $f$ fixed. Empty domains are infeasibility, not permission to omit an event. This joint formulation removes the proposal's unlinearized product of faculty assignment and occupancy.

The heuristic uses an equivalent compact categorical encoding: one `(start, room)` gene per event and one faculty-ID gene per offering. Event order is deterministically derived from offering order and session count. The teacher decision is essential: if teachers were fixed, weekly workload imbalance could become constant even though the timetable changes.

## 5. Objective functions

All objectives are minimized. Let $P^*$ be the non-lunch teaching periods, $b_{v,d,p}$ the teaching occupancy of a student group or faculty member, and $p^-_{v,d},p^+_{v,d}$ its first/last occupied periods that day. An empty teaching day has gap zero; otherwise,

$$\operatorname{gap}_{v,d}=\sum_{p\in P^*:\ p^-_{v,d}\le p\le p^+_{v,d}}(1-b_{v,d,p}).$$

The compactness objective is

$$f_1=\sum_{g\in G,d}\operatorname{gap}_{g,d}+0.5\sum_{f\in F,d}\operatorname{gap}_{f,d}.$$

Common mandatory lunch is excluded, and free time before/after teaching is excluded. Faculty-specific unavailability inside a teaching span remains teaching-free internal time; the data cannot infer whether it contains an administrative meeting. The faculty factor 0.5 is an explicit policy choice. Separate student/faculty gaps are also reported.

With room capacity $c_r$ and fixed total contact demand $Q=\sum_e\ell_e$,

$$f_2=\frac1Q\sum_e\ell_e\frac{c_{r(e)}-n_e}{c_{r(e)}}.$$

This is duration-weighted empty-seat fraction **during scheduled use**. It is neither campus room-hour utilization nor a reward for cancelling sessions. Capacity remains a hard constraint.

Faculty $f$ has weekly allowance $H_f$, required teaching load $L_f$, relative load $\rho_f=L_f/H_f$, and mean relative load $\bar\rho=|F|^{-1}\sum_f\rho_f$. Workload imbalance is

$$f_3=\sqrt{\frac1{|F|}\sum_{f\in F}(\rho_f-\bar\rho)^2}.$$

All listed faculty, including zero-load faculty, participate. Overlapping eligibility makes assignments and workload genuinely variable; all sessions move together when an offering changes teacher. This measures relative teaching load, rather than research, administration, or preparation effort. The evaluator defines degenerate empty-demand/empty-faculty diagnostics as zero; a nonempty offering without an eligible teacher is infeasible.

## 6. Constraints and assumptions

Every reported timetable must satisfy all of the following; objective improvements cannot compensate for a violation.

| Code | Hard requirement and implementation meaning |
|---|---|
| C1 | Exactly one complete placement per required event; exactly one eligible, offering-consistent teacher. Missing, extra, malformed, or unknown assignments are infeasible. |
| C2 | At most one event in each room at each occupied period. |
| C3 | At most one event taught by each faculty member at each occupied period. |
| C4 | At most one event attended by each atomic student group at each occupied period. Shared events occupy every listed group. |
| C5 | Room capacity at least summed headcount; exact room-kind match, including lab type. |
| C6 | Every period of the event is available for its room and teacher; the block stays in one day and avoids lunch. A two-period lab consumes and checks both periods. |
| C7 | Faculty weekly and daily loads do not exceed their limits, counted in periods rather than sessions. |
| C8 | At most one session of an offering per day when its `distinct_days` flag is enabled; the generator enables it for repeated theory sessions. |

For a joint alternative $q=(s_q,r_q,f_q)\in A_e$, write $z_{e,q}=z_{e,s_q,r_q,f_q}$. At every time-grid period $t$, room, faculty, and student occupancies respectively satisfy

$$\sum_e\sum_{q\in A_e:\ r_q=r,\ t\in B_e(s_q)}z_{e,q}\le1\quad(r,t),$$

$$\sum_e\sum_{q\in A_e:\ f_q=f,\ t\in B_e(s_q)}z_{e,q}\le1\quad(f,t),$$

$$\sum_{e:\ g\in G_e}\sum_{q\in A_e:\ t\in B_e(s_q)}z_{e,q}\le1\quad(g,t).$$

Let $E_k$ be the required events of offering $k$, and let $h_f$ denote the daily teaching allowance. Weekly and daily limits are

$$\sum_{k:\ f\in F_k}\left(\sum_{e\in E_k}\ell_e\right)y_{k,f}\le H_f\quad(f),$$

$$\sum_e\sum_{q\in A_e:\ f_q=f,\ d(s_q)=d}\ell_e z_{e,q}\le h_f\quad(f,d).$$

For every offering $k$ marked `distinct_days` and each day $d$,

$$\sum_{e\in E_k}\sum_{q\in A_e:\ d(s_q)=d}z_{e,q}\le1.$$

If $U_r,U_f$ denote unavailable periods, then $A_e$ includes only alternatives with $f\in F_{k(e)}$, $c_r\ge n_e$, exact required room type, $B_e(s)\cap U_r=B_e(s)\cap U_f=\varnothing$, and a contiguous block lying in one day and excluding lunch. These restrictions implement C5/C6 for the entire block. The [full formulation](../formulation/README.md) gives additional notation and domain details.

Assumptions are a fixed repeating week, equal-length periods, known demand, fixed session durations, atomic cohorts, and one teacher per offering. The default generator uses generic classrooms/labs and full-cohort labs. The model omits travel, individual elective enrollment, rotating weeks, team teaching, uncertain attendance, minimum faculty loads, fixed event starts, and non-teaching workload.

## 7. Problem classification

The problem is deterministic, finite, discrete, constrained, combinatorial, and multi-objective. Simplified feasibility contains graph coloring. Feasibility and room wastage admit binary linear formulations; gap indicators admit exact logical encodings. Relative-load SD is nonlinear. It would be incorrect to describe the complete three-objective problem as an ordinary linear program.

Gradient methods do not directly represent categorical room/teacher decisions or no-clash logic. Exhaustive schedule enumeration grows rapidly. This motivates a constructive baseline, exact small references, and bounded heuristic search, with no general global-optimality promise.

## 8. Baseline approach

The strong baseline repeatedly constructs schedules using dynamic saturation/scarcity/degree ordering, long-block prioritization, room fit, compactness, and offering-level faculty selection. An offering's sessions are placed together while respecting teacher consistency and reserving its complete weekly load. The first construction is deterministic; subsequent constructions use seeded restricted candidate lists.

Each completed attempt receives one full shared evaluation, including failed constructions. Every feasible non-dominated objective vector discovered by the repeated baseline is retained. This is stronger than comparing with one poor greedy schedule. The same constructive scheduling policy is unchanged in the final follow-up; the comparison adapter adds common observation and stopping, not a weaker heuristic.

The public `greedy()` function returns one scalar-compromise feasible schedule or an explicit `SchedulingFailure`. Experimental repeated greedy returns an archive and is the primary comparison here. A heuristic failure never proves infeasibility.

## 9. Optimization algorithm selection and justification

The development sequence follows the problem structure rather than selecting an algorithm first:

1. Implement the model, feasibility-certified generator, evaluator, and constructive baseline.
2. Compare standard constrained NSGA-II with random categorical initialization, then add seeding, reconstruction repair, and short local search.
3. Retain the original negative quality results. Diagnose infeasible offspring and the cost of repeatedly rebuilding schedules.
4. Develop a feasible-domain mutation-only memetic NSGA-II, freeze it after development, and compare it on new instance seeds under both evaluation and time allocations.
5. Compare its NSGA-II selection/survival bundle with matched scalar-local trajectories so improvements are not automatically credited to population selection.

NSGA-II provides a transparent population comparator for discrete Pareto trade-offs. The final method retains rank/crowding tournaments and elitist survival but intentionally omits crossover because offering-level gene exchanges destroy shared resources. The evidence supports the final feasible-search package on the declared primary instances; it does not establish that NSGA-II selection consistently improves over the strong local-search ablation.

## 10. Multi-objective formulation

Feasible objective vector $u$ dominates $v$ if every $u_i\le v_i$ and at least one inequality is strict. Equal vectors are one trade-off vector, even if several schedules attain them. Search uses Deb-style constraint domination: feasible candidates outrank infeasible candidates; among infeasible candidates smaller positive violation wins; among feasible candidates ordinary Pareto dominance applies.

The integer violation score includes incompleteness, invalid assignments, resource-period excess, blocked periods, same-day excess, and teaching overload. It guides search and has no interpretation as an acceptable quality trade-off. Only violation-zero schedules enter reported fronts, hypervolume, and timetable exports.

Possible conflict is established by exhaustive controlled micro-instances: compactness/room fit has global front `(0,0.25,0)` and `(1,0,0)` after 64 complete candidate evaluations; compactness/workload has `(0,0,0.5)` and `(1,0,0)` after nine. They are tiny mathematical examples, not college-scale measurements.

Conflict is instance-dependent. Exact lower-bound attainment proves a singleton global ideal `(0,14/55,sqrt(1/450))` for the four checked small college instances (seeds 10,20,30,1010). Medium/large heuristic archives show discovered trade-offs without certifying their full global fronts. The meaning and proof scope of these statements are developed in Section 14.

## 11. Algorithm implementation

| Component | Actual implementation and boundary |
|---|---|
| Standard NSGA-II | Independent domain-valid categorical initialization; whole-offering uniform crossover; time/room/swap/teacher mutations; constrained sorting, crowding tournaments, and parent–offspring elitist selection. Domain-valid genes alone do not guarantee resource feasibility. |
| Original enhancement | Half the initial population constructed; inheritance-biased reconstruction repair; sampled compaction, room-fit, teacher-change, and whole-offering teacher-exchange proposals. It is neither a Kempe chain nor minimum-disruption repair. |
| Final feasible initialization | Repeated constructive attempts fill a feasible population, bounded by four times the requested population and the resource limits. Failed attempts are charged. The measured follow-up uses population 24. |
| Final local variation | Five resource-checked neighborhoods: relocation, smaller-room assignment, event swap, joint reinsertion under a different offering teacher, and joint teacher exchange. Complete block checks precede final shared evaluation. Unsuccessful moves return an explicit no-op. |
| Faculty intensification | Every sixth offspring proposal invokes a branch-and-bound reassignment of up to eight offerings at fixed times/rooms, capped at 12,000 branch nodes. With common weekly allowances, exact integer squared-load sum is equivalent to relative-load SD. Unequal allowances produce a safe no-op. |
| Diversification | Periodic randomized reconstruction is attempted every 31st proposal unless the faculty-search branch takes priority. No generator certificate is used. |
| Final NSGA-II selection | Rank/crowding binary tournaments and environmental selection from parent plus offspring populations genuinely affect the search. Mutation-only variation is an explicit variant, not an unimplemented crossover claim. |
| Scalar-local ablation | Identical construction/RNG prefix, then independent fixed positive scalar directions for local trajectories, uniform trajectory choice, and feasible scalar-improving acceptance. It removes the NSGA-II selection/survival bundle. Subsequent RNG use and candidates diverge. |
| Common archive | Every fully evaluated feasible proposal can enter, including proposals rejected by local acceptance; one schedule represents each non-dominated objective vector. |

For common weekly allowance $H$, total teaching demand fixes the mean relative load, so faculty intensification can minimize integer $C=\sum_f L_f^2$ without approximating $f_3$. Assigning offering load $w$ to a teacher currently at load $L$ increases $C$ by $2Lw+w^2$. The branch-and-bound lower bound adds each remaining offering's smallest independent marginal cost to the partial cost; shared-teacher competition can only increase those marginals. Faculty eligibility, full-block clashes/availability, daily limits, and weekly limits are checked on insertion. Exhaustion proves optimality only within the selected fixed-time neighborhood; a node-limited result has no such completion guarantee. The returned candidate is always checked on all three objectives.

All complete evaluator calls during search are charged, including initialization, duplicates, failed repair results, and rejected local candidates. Partial occupancy, gap, and integer-workload calculations are disclosed and timed; they are not mislabeled as complete evaluator calls. Native counters distinguish first/final no-ops, neighborhood calls, faculty nodes, and interrupted progress.

The original version had 136 automated tests passing, including a fresh snapshot installation and CLI check. Before the final held-out freeze, **201 tests passed in 15.54 seconds**, recorded in [the saved test log](../results/enhancement_validation/tests_before_validation.txt). Tests cover hand-calculated objectives, every important hard constraint, shared cohorts, labs/lunch, malformed/infeasible inputs, all preset sizes, seeds/serialization, dominance/crowding, independently cross-checked hypervolume, exact references, feasible operators, integer workload search, evaluator accounting, timing cutoffs, and cache/resume integrity. Historical test counts refer to their measured versions, not fabricated student activity.

## 12. Experimental setup

### Data generation and feasibility

All main data are synthetic and use the unchanged generator presets:

| Preset | Events | Atomic cohorts | Rooms | Faculty | Required contact periods |
|---|---:|---:|---:|---:|---:|
| Small | 40 | 2 | 5 | 6 | 44 |
| Medium | 150 | 8 | 12 | 20 | 166 |
| Large | 400 | 20 | 25 | 50 | 440 |

Defaults use five days, eight grid periods, and lunch at zero-based period 4. Cohort sizes cycle through 24/36/48/54; room capacities through 30/45/60/90. Labs last two periods. Faculty allowances are 20 periods weekly and six daily. Availability is sampled at rate 0.08 from resource periods unused by a separately constructed feasible certificate; eligibility retains that certificate's teacher and adds alternatives.

The certificate is independently checked outside the search, saved separately, and never passed to an optimizer or hidden in its metadata. Thus failure on a generated instance is a search failure. This is a planted-feasible, potentially slack distribution, not an unbiased sample of real colleges. Configurable parameters and JSON fields are documented in [data/README.md](../data/README.md).

### Historical benchmark and development

The original benchmark contains 192 runs, 109,440 complete search evaluations, seven instances, and 769 archived feasible schedules. Small instance seeds are 10/20/30 with ten solver seeds each; medium uses 10/20 with six seeds each; large uses 10/20 with three seeds each. Four methods—greedy, plain NSGA-II, seeding-only, and original enhanced—use population 24 and caps 720/360/240 by size. These records are retained under `results/benchmark/`.

A separate 12-run development pilot used instance/solver seed 9000, all three sizes, four candidate policies, and 240 complete evaluations. The larger supplied 64-run development matrix was not executed in full. Development outcomes were not pooled with held-out validation. No operator rates or generator settings were selected in response to validation results.

### Frozen final validation

The predeclared final matrix is:

| Size | Instance seeds | Solver seeds | Complete-evaluation cap | Separate wall allocation | Runs across four methods and both protocols |
|---|---|---|---:|---:|---:|
| Small regression | 1010 | 0,1,2 | 720 | 2.5 s | 24 |
| Medium primary | 1010,1020,1030 | 0,1,2 | 360 | 6 s | 72 |
| Large primary | 1010,1020,1030 | 0,1,2 | 240 | 16 s | 72 |

All **168 runs** completed, totaling **76,086 complete search evaluations**. Four methods were paired: unchanged greedy, original enhanced NSGA-II, final feasible memetic NSGA-II, and scalar-local search. Every run returned a feasible archive. The [manifest](../results/enhancement_validation/manifest.json) records the exact configuration, versions, per-file hashes, and measured source snapshot.

Frozen final package SHA-256: `7ad242177abf49f65dfd192b3ecad6fe614644abf76413b39099aa897ddd854c`. Python: `3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]`; platform: `Linux-6.18.57-x86_64-with-glibc2.41`. Recorded NumPy/Matplotlib/OR-Tools versions are `{'numpy': '2.3.5', 'matplotlib': '3.10.8', 'ortools': '9.15.6755'}`.

### Resource protocols and indicators

Equal-evaluation runs charge the same complete evaluator cap within a size. Equal-time runs use the same wall allocation, with a 100,000-evaluation safety ceiling. Common imports, input validation, and construction-cache reset are preflight; algorithm preprocessing, initialization, direct checks, scoring, selection, observer work, and archive bookkeeping are timed. Methods run sequentially in rotated order. Hardware/load limit timing generalization.

The common observer timestamps completion of each full objective/constraint calculation. Cutoff quality uses only results completed by the allocation. Bounded atomic operations may overrun; late results are charged and excluded from quality, and overshoot is reported. This is the same allocation with late-result exclusion, rather than strict preemption or identical actual runtime. It does not estimate a time prefix from average time per evaluation. Plots use sampled stepwise prefixes; shading is descriptive one-SD variability across solver runs.

Hypervolume is the exact 3-D union of dominated boxes after fixed a priori scaling by `days * non-lunch periods/day * (groups + 0.5*faculty)`, `1`, and `0.5`, with reference `(1.1,1.1,1.1)`. It is not fitted per method/run. The loose gap bound can underweight compactness. Maximum reference-box volume is 1.331; HV is not a percentage or administrative utility. Cross-size HV is not one common decision problem.

For normalized feasible front $A$ and reference $r$, the indicator is

$$HV(A;r)=\lambda_3\!\left(\bigcup_{v\in A}[v_1,r_1]\times[v_2,r_2]\times[v_3,r_3]\right),$$

where $\lambda_3$ is three-dimensional volume. Empty feasible archives have HV zero and remain in all-run averages.

Other indicators include feasible-run/evaluation rates, constraint components, runtime, archive size, raw objectives, duplicates, and spacing. Spacing is undefined with fewer than two vectors. The historical optional empty-target coverage aggregate uses zero by convention and is excluded from conclusions; final comparisons preserve undefined coverage and record defined-pair counts.

Paired comparisons match instance and solver seed. Run-level wins are descriptive; instance-mean tests avoid treating repeated solver seeds as independent colleges. Only three independent primary instances per size give low statistical power. No multiplicity-adjusted or institutional superiority claim is made.

## 13. Results and Pareto analysis

### Original results retained: why the first enhancement was revised

The original enhanced method found feasible schedules but had lower mean HV than repeated greedy at every size:

| Size | Greedy mean HV | Original enhanced mean HV | Greedy mean seconds | Original enhanced mean seconds |
|---|---:|---:|---:|---:|
| Small | 0.935319 | 0.935173 | 7.918 | 2.432 |
| Medium | 1.017029 | 0.981213 | 18.550 | 6.087 |
| Large | 0.937241 | 0.909322 | 48.520 | 16.236 |

Greedy, seeded, and original enhanced each found feasible schedules in 48/48 runs. Plain NSGA-II found none in 48 runs at these caps; those empty fronts retain HV zero. This is bounded-search failure on known-feasible data, not infeasibility or proof that NSGA-II can never work. Its ending violation ranges were 1–8 small, 75–89 medium, and 310–342 large.

From saved original counters, approximately 91.1%, 94.6%, and 97.2% of raw offspring required repair by size. These percentages describe offspring incidence, not the fraction of total CPU time or evaluations spent repairing. Accepted local proposals were approximately 18.6%, 12.7%, and 8.5%. This diagnosed destructive variation and motivated feasible local refinement. Full original tables, failures, and histories remain in [the historical summary](../results/benchmark/summary.md) and raw records.

### Final held-out comparison with the unchanged greedy policy

| Size | Protocol | Greedy mean HV | Final NSGA-II mean HV | Relative change in mean HV | Paired final wins/ties/losses |
|---|---|---:|---:|---:|---|
| Small | evaluations | 0.934747 | 0.930290 | -0.477% | 1/0/2 |
| Small | wall_time | 0.929781 | 0.930290 | +0.055% | 2/0/1 |
| Medium | evaluations | 1.008330 | 1.056105 | +4.738% | 9/0/0 |
| Medium | wall_time | 0.988710 | 1.060477 | +7.259% | 9/0/0 |
| Large | evaluations | 0.940824 | 0.977304 | +3.878% | 9/0/0 |
| Large | wall_time | 0.930485 | 1.013967 | +8.972% | 9/0/0 |

The final method has higher mean HV on both primary sizes under both resource protocols, with nine paired wins in each of those four conditions. Small results remain mixed. Relative percentages divide the difference between method means by the greedy mean; they do not turn HV into a utility percentage.

At equal complete evaluations, final mean runtime was 2.928 versus 20.215 seconds for medium and 8.041 versus 51.671 seconds for large (final versus greedy), ratios about 6.90× and 6.43× in this environment. Under common wall allocations, final mean evaluator counts were about 948 versus 106 medium and 800 versus 75 large. Partial search costs are included in those wall times.

All four final-study methods returned feasible archives in all their runs: 21/21 instance/solver combinations per protocol, or 42/42 runs per method. Every reported archive has violation zero. All 3,295 final archived schedules and seven separate certificates were rechecked; nine late completed evaluations were excluded. Verification also reconstructed the on-time fronts and checked 42 common-initialization groups. See [the verification record](../results/enhancement_validation/verification.json).

### Raw objective changes

These are means of each run's best feasible value **per objective**, conditional on feasible archives. Different columns may belong to different schedules; they are not simultaneous ideal vectors.

| Size | Protocol | Method | Mean run-best gaps | Mean run-best unused capacity | Mean run-best workload SD |
|---|---|---|---:|---:|---:|
| Small | evaluations | greedy | 0.000 | 0.254545 | 0.047140 |
| Small | evaluations | memetic | 0.000 | 0.259091 | 0.047140 |
| Small | wall_time | greedy | 0.000 | 0.259091 | 0.047140 |
| Small | wall_time | memetic | 0.000 | 0.259091 | 0.047140 |
| Medium | evaluations | greedy | 0.000 | 0.182173 | 0.050272 |
| Medium | evaluations | memetic | 0.056 | 0.184092 | 0.025650 |
| Medium | wall_time | greedy | 0.000 | 0.183333 | 0.059463 |
| Medium | wall_time | memetic | 0.000 | 0.183490 | 0.024008 |
| Large | evaluations | greedy | 1.722 | 0.202138 | 0.073058 |
| Large | evaluations | memetic | 2.444 | 0.203746 | 0.053389 |
| Large | wall_time | greedy | 2.222 | 0.203114 | 0.077700 |
| Large | wall_time | memetic | 1.889 | 0.202980 | 0.035238 |

At equal evaluations, workload balance improves substantially while the mean best room wastage and gaps can worsen. A higher-HV front does not imply that every greedy point is dominated or that every coordinator would prefer every new schedule. The fixed gap scale makes raw timetable interpretation especially important.

### Pareto and convergence visualizations

![Medium fixed-instance discovered archives](../figures/enhancement_validation/medium_1010_wall_time_pareto.png)

![Large fixed-instance discovered archives](../figures/enhancement_validation/large_1010_wall_time_pareto.png)

These plots use one fixed instance each and pool per-run archives. They show feasible discovered vectors, including vectors that another run may dominate; they are not a global Pareto certificate. The original fixed-instance diagnostics also report opposing objective changes on medium/large instances. Observed opposition alone cannot rule out an undiscovered joint ideal.

![Medium sampled anytime prefixes](../figures/enhancement_validation/medium_anytime.png)

![Large sampled anytime prefixes](../figures/enhancement_validation/large_anytime.png)

The anytime plots use actual completion timestamps with sample-and-hold prefixes, rather than interpolating an undiscovered timetable. One-SD bands describe solver-run variability, not independent-instance confidence intervals. The [complete final summary](../results/enhancement_validation/summary.md) retains original enhanced and scalar-local results alongside these primary comparisons.

## 14. Comparison and discussion

### Does NSGA-II selection add value?

| Size | Protocol | Final NSGA-II mean HV | Scalar-local mean HV | NSGA-II paired wins/ties/losses |
|---|---|---:|---:|---|
| Small | evaluations | 0.930290 | 0.930231 | 2/0/1 |
| Small | wall_time | 0.930290 | 0.930236 | 2/0/1 |
| Medium | evaluations | 1.056105 | 1.054147 | 5/0/4 |
| Medium | wall_time | 1.060477 | 1.061314 | 6/0/3 |
| Large | evaluations | 0.977304 | 0.978518 | 4/0/5 |
| Large | wall_time | 1.013967 | 1.011318 | 5/0/4 |

Scalar-local has a slightly higher mean on medium wall-time and large equal-evaluation runs; NSGA-II has the higher mean on medium equal-evaluation and large wall-time runs. There is no consistently positive selection-bundle effect. The evidence supports the new initialization/variation/intensification package while leaving the incremental benefit of NSGA-II selection unresolved. The bundle comparison does not isolate full feasible initialization, an individual neighborhood, or faculty branch-and-bound.

Each primary condition has only three independent instances. Instance-mean sign tests give p=0.25 for final NSGA-II versus greedy even though all nine paired runs favor it. Smaller run-level p-values are descriptive because runs share instances. These results support bounded improvement on the declared synthetic cases; they do not establish broad statistical, institutional, or universal superiority.

### Exact reference results and guarantee boundaries

The optional CP-SAT reference uses OR-Tools 9.15.6755, one worker, seed 0, and a 20-second solver limit excluding model build. On reference small seed 10 it independently proved:

| Scalar objective | Status | Value | Best bound | Total runtime | Independently evaluated full objective vector |
|---|---|---:|---:|---:|---|
| Gaps | OPTIMAL | 0 | 0 | 2.746 s | (0, 0.4121212121, 0.1598610508) |
| Room waste | OPTIMAL | 14/55 | 14/55 | 2.321 s | (14.5, 0.2545454545, 0.2544056254) |

Total runtime includes model construction/extraction. These are scalar optima; unoptimized axes can be poor because tie-breaking is unconstrained. CP-SAT `FEASIBLE` would provide an incumbent without an optimality proof; `UNKNOWN` would not prove infeasibility. No workload surrogate is advertised as the exact three-objective problem. [Exact-model documentation](../docs/exact.md) and saved outputs provide the details.

A stronger, independent lower-bound certificate gives the singleton global ideal for small seeds 10,20,30,1010. Nonnegative gaps give $f_1\ge0$; independent best-fit compatible rooms give exact $f_2\ge14/55$. An exact integer dynamic program allocates twelve indivisible three-period offerings and four two-period offerings to six common-allowance-20 faculty bins, dropping eligibility and temporal interactions. Its minimum squared-load sum is 328, giving

$$f_3^2\ge\frac{328}{6\cdot20^2}-\left(\frac{44}{120}\right)^2=\frac1{450}.$$

Actual feasible schedules attain all three bounds simultaneously, with integer zero gaps, exact rational room fraction 14/55, and loads `[6,6,8,8,8,8]`. Each checked small instance therefore has singleton global objective front `(0,14/55,sqrt(1/450))`, although many schedule identities may attain it. This is a proof about the fixed cases, not every generated seed.

For held-out small_1010, the final memetic equal-evaluation run with solver seed 1 attains the ideal. The other two memetic seeds are worse, so one globally optimal run coexists with an unfavorable small-case mean. Both the success and the reliability limitation are retained. Certificates are in [the original small record](../results/benchmark/small_ideal_certificates.json) and [the final small record](../results/enhancement_validation/small_ideal_certificates.json).

There is also a workload-only global certificate on all three held-out medium cases. Their 166 periods across 20 equal-allowance faculty have integer-load relaxation minimum `14*8² + 6*9² = 1382`, with exact relative-load variance `21/40000`. Feasible memetic/local schedules attain it. This proves the global minimum of $f_3$ alone; it proves neither the other objectives nor the global three-objective front. Large-case bounds were not attained; nonattainment of a relaxed bound does not itself establish nonoptimality.

## 15. Practical interpretation

A coordinator chooses a whole feasible timetable using declared priorities. Exports include fewest gaps, best room fit, balanced workload, and an observed-archive-normalized compromise. The compromise is a specified preference rule rather than a unique mathematical knee; selections can coincide.

The following final examples use the first configured primary instance and solver seed 0 under the common wall allocation. Both methods use the same preference: lexicographic `(gaps, room, SD)` or `(SD, gaps, room)`. All columns in each row belong to the **same complete timetable**.

| Instance | Method | Preference | Gaps | Unused capacity | Workload SD | Student gaps | Faculty gaps | Faculty load range |
|---|---|---|---:|---:|---:|---:|---:|---|
| medium_1010 | greedy | fewest_gaps | 0 | 0.187550 | 0.117367 | 0 | 0 | 5–12 |
| medium_1010 | greedy | balanced_workload | 3 | 0.192972 | 0.050249 | 0 | 6 | 6–11 |
| medium_1010 | memetic | fewest_gaps | 0 | 0.185542 | 0.050249 | 0 | 0 | 6–10 |
| medium_1010 | memetic | balanced_workload | 2 | 0.191165 | 0.022913 | 0 | 4 | 8–9 |
| large_1010 | greedy | fewest_gaps | 3 | 0.208333 | 0.110454 | 1 | 4 | 5–14 |
| large_1010 | greedy | balanced_workload | 9.5 | 0.208333 | 0.078740 | 0 | 19 | 5–11 |
| large_1010 | memetic | fewest_gaps | 1.5 | 0.208333 | 0.110454 | 0 | 3 | 5–14 |
| large_1010 | memetic | balanced_workload | 23.5 | 0.205985 | 0.036056 | 8 | 31 | 8–10 |

For medium_1010, the final gap-priority timetable has zero gaps, better room fit, and lower workload SD than the displayed greedy gap-priority timetable. For large_1010, the workload-priority final timetable greatly improves relative balance but has 23.5 gap units versus greedy's 9.5; that is a concrete administrative trade-off rather than a uniformly better timetable. A coordinator who prioritizes compactness may choose a different point.

![Greedy medium group timetable](../figures/enhancement_validation/timetables/medium_1010_greedy_fewest_gaps.png)

![Final medium group timetable](../figures/enhancement_validation/timetables/medium_1010_memetic_fewest_gaps.png)

The images show one group's weekly grid, rather than the entire faculty allocation. Complete event JSON/CSV and all group/faculty/room CSV grids are in [the final timetable exports](../results/enhancement_validation/timetables/). The [representative index](../results/enhancement_validation/representatives.json) records exact selection and archive references. Human-readable periods start at 1; model slots are zero-based.

## 16. Limitations

- Data are synthetic and planted feasible, with structural and resource-slack bias. No real-college or ITC validation is claimed. Certificates establish feasibility, not representativeness.
- Final primary results use only three independent instances per size and three solver seeds each. The small regression has one instance. Statistical generalization is limited despite consistent primary paired wins.
- The small global ideal makes a broad global trade-off front unnecessary there. Other fronts are discovered non-dominated sets with no global completeness proof.
- Final small equal-evaluation mean quality regresses; scalar-local remains competitive. The evidence does not establish a consistent NSGA-II selection benefit or isolate one enhancement component.
- Equal complete evaluations are not equal compute. Wall allocations permit bounded overshoot with late results excluded. Hardware/load, common instrumentation, and caching policy affect times.
- Hypervolume's conservative fixed gap scale can underweight compactness. No indicator/reference-scale sensitivity study has been completed, and HV is not a coordinator utility.
- Relative teaching load omits research, administration, and preparation effort. Individual unavailability inside a teaching span counts as teaching-free time. Specialized room kinds/shared cohorts are supported in custom data but not generated by default.
- The repeating week omits individual elective enrollment, travel, rotating weeks, fixed starts, team teaching, uncertainty, minimum faculty loads, and disruption stability.
- Structured faculty search supports equal weekly allowances; it safely returns unchanged for unequal allowances. General exact workload optimization and college-scale Pareto enumeration are not implemented.
- The larger five-instance/30-solver-seed study, extensive sensitivity/disruption tests, real-data adapters, NSGA-III/MOEA/D/SA/weighted GA, Excel-specific export, and an interactive frontend are not claimed. These are additional opportunities, not substitutes for authentic contribution evidence.
- Approval, group identities, private access, and eight weeks of individual contribution history cannot be inferred from generated artifacts, local tests, or one publication commit.

## 17. Future work

First validate atomic cohorts, qualification sets, lab equipment, teaching allowances, and preferences with a coordinator using anonymized real data. Expand independent instance diversity and realistic resource pressure before broadening performance claims.

Next run the larger configured study and reference/scale sensitivity; add component-specific ablations, independent initialization/selection/variation RNG streams for variance control, and profiling-driven incremental checks. Study whether strong scalar-local search should be the practical default when population selection adds little.

Then consider unequal-allowance structured assignment, exact epsilon-constraint fronts on tiny cases, standard benchmark import with faithful rule mapping, and genuine minimum-disruption rescheduling. New algorithms should answer observed limitations rather than expand a name list.

## 18. Individual contributions

The professor requires exactly four members, meaningful parallel work every week, at least one meaningful personal commit per member per week, individual contribution records, and understanding of the full project for the viva. Those are authentic process requirements. The implementation and experiments do not create retrospective evidence that they occurred.

| Member | Full name / roll number / username | Verified actual contribution and evidence |
|---|---|---|
| Member 1 | Not supplied | To be completed from genuine work and review records; no authorship assigned here. |
| Member 2 | Not supplied | To be completed from genuine work and review records; no authorship assigned here. |
| Member 3 | Not supplied | To be completed from genuine work and review records; no authorship assigned here. |
| Member 4 | Not supplied | To be completed from genuine work and review records; no authorship assigned here. |

| Academic field | Current evidence boundary |
|---|---|
| Professor / group number | Not supplied. |
| Topic approval / approval date | Not supplied or verified. |
| Three genuinely different proposals submitted | Only the supplied timetable proposal is evidenced in this repository. |
| Actual weekly member participation | Not recorded; fill from actual dates, personal commits, reviews, and work. |

The [prospective four-member/eight-week plan and evidence template](../docs/project_plan.md) supports genuine completion; it is not a historical log. Final presentation/demo material is under [presentation/](../presentation/). All four students must be able to defend the variables, constraints, algorithms, experiments, unfavorable findings, and proof boundaries themselves.

## 19. GitHub/GitLab repository link

Repository: <https://github.com/akshattikaria/Optimization-Project-OT-BY-AKSHAT-MANAV-KRISH-PARTH>.

The professor requires a private repository, access for all four members and the professor, and the repository-link submission document after topic approval. Confirm those facts in the actual account settings and record the submitted revision; a URL or publication commit alone does not establish them. No member identities, access approvals, or eight-week history are invented in this report.

### Reproducing and inspecting the submitted work

The [root README](../README.md) is the installation/CLI entry point. From a fresh checkout in Bash:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install -e . --no-deps
python -m pytest -q
python main.py generate --size small --seed 42 --output data/demo.json --certificate data/certificates/demo.json
python main.py solve data/demo.json --method memetic --seed 0 --budget 240 --population 24 --output results/demo --figures figures/demo
python main.py evaluate data/demo.json results/demo/timetables/normalized_compromise/schedule.json
```

Recheck saved evidence and regenerate final plots/exports without changing solver measurements:

```bash
python experiments/verify_saved_results.py --study benchmark
python experiments/verify_enhancement.py --study enhancement_validation
python experiments/certify_small_ideal.py --study enhancement_validation
python experiments/plot_enhancement.py --study enhancement_validation
python experiments/export_enhancement.py --study enhancement_validation
python experiments/report_enhancement.py --study enhancement_validation
```

For fresh final-study measurements, preserve existing records under a new study name:

```bash
mkdir -p work
python - <<'PYCONFIG'
import json
from pathlib import Path
config = json.loads(Path('experiments/enhancement_validation.json').read_text())
config['name'] = 'enhancement_reproduction'
Path('work/enhancement_reproduction.json').write_text(json.dumps(config, indent=2))
PYCONFIG
python main.py compare --config work/enhancement_reproduction.json
python experiments/verify_enhancement.py --study enhancement_reproduction
```

Resume requires the measured source/configuration/runtime; wall-time trajectories naturally vary between machines. Historical benchmark measurements remain associated with their original version and are never spliced into the final timing comparison.

This consolidated report is the final narrative. The [historical summary](../results/benchmark/summary.md), [final summary](../results/enhancement_validation/summary.md), [frozen study protocol](../docs/enhancement_study.md), and [detailed follow-up report](enhancement_report.md) provide supporting traceable evidence. Administrative approval, access, actual contribution records, and presentation delivery remain genuine submission responsibilities.

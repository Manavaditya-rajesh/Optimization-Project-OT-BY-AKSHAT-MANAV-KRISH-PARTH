# Mathematical formulation

This document specifies the problem solved by the code. The supplied proposal is a starting point; the corrections in [reference_review.md](../docs/reference_review.md) explain where its equations or claims needed refinement. All three objectives are minimized. Only candidates satisfying every hard constraint may be exported as valid timetables.

## 1. Sets, input data, and conventions

| Symbol | Meaning |
|---|---|
| $D$ | Days of a repeating week |
| $P=\{0,\ldots,P_{\max}-1\}$ | Equal-length periods within a day |
| $L\subseteq P$ | Common mandatory lunch periods |
| $T=D\times P$ | Time grid; code stores $(d,p)$ as `d * periods_per_day + p` |
| $G,R,F,K$ | Atomic student groups, rooms, faculty, and course offerings |
| $E_k$, $E=\bigcup_k E_k$ | Required weekly sessions of offering $k$, and all events |
| $k(e)$, $G_e$ | Offering of event $e$ and its attending groups |
| $\ell_e$, $n_e$ | Event duration in periods and headcount $\sum_{g\in G_e}n_g$ |
| $F_k$ | Faculty eligible to teach offering $k$ |
| $c_r$, $q_r$, $q_e$ | Room capacity, room type, and required event room type |
| $U_r,U_f\subseteq T$ | Unavailable periods of room $r$ and faculty member $f$ |
| $H_f$, $h_f$ | Maximum weekly and daily teaching periods for faculty $f$ |
| $a_k\in\{0,1\}$ | Whether sessions of offering $k$ must occur on distinct days |

Groups are **disjoint atomic cohorts**. An event may involve several cohorts; every attending cohort is occupied and its size contributes to headcount. To model a division split into lab batches, represent the batches as atomic groups and list all batches on common lectures. Do not add an overlapping parent group as an independent cohort. The generator is synthetic; this mathematical structure does not claim to reproduce a particular college.

Every event occupies a contiguous block on one day. For start $s=(d,p)$, let $B_e(s)=\{(d,p),\ldots,(d,p+\ell_e-1)\}$. A start is invalid if it crosses a day boundary or any lunch period. Lunch is never a scheduling option. Type matching is exact: a `lab` event needs a `lab` room, and a theory event a `classroom` room. A shared lecture may use a larger compatible room, but a laboratory is not automatically a substitute lecture hall.

Define the static candidate domain

$$
A_e=\{(s,r,f)\in T\times R\times F: B_e(s)\subseteq T\setminus(D\times L),\;B_e(s)\text{ lies in one day},\;c_r\ge n_e,\;q_r=q_e,\;f\in F_{k(e)},\; B_e(s)\cap(U_r\cup U_f)=\varnothing\}.
$$

This domain filters individual placement restrictions. It does not remove interactions with other events. Empty domains are valid evidence of infeasibility, rather than a reason to invent a placement.

## 2. Controllable decisions and domains

Use joint binary placement variables

$$z_{e,s,r,f}\in\{0,1\}\quad((s,r,f)\in A_e),$$

meaning event $e$ starts at $s$, in room $r$, taught by $f$, and offering assignment variables

$$y_{k,f}\in\{0,1\}\quad(f\in F_k).$$

For unambiguous summation, write a candidate as $q=(s_q,r_q,f_q)\in A_e$ and abbreviate $z_{e,q}=z_{e,s_q,r_q,f_q}$. A sum over $q$ includes all joint alternatives satisfying its displayed filters; any separately quantified room $r$ or faculty $f$ is held fixed.

A teacher is selected **per offering**, and all its weekly sessions share that teacher. This makes workload a genuine decision whenever eligibility permits alternatives; changing only event times cannot change total weekly teaching load. The heuristic representation is equivalent: one `(start, room)` placement per event, plus one eligible faculty ID per offering. Event IDs and ordering are derived deterministically from offering session counts; there is no independent mutable list of required events that could omit a lecture silently.

The joint formulation replaces the proposal's bilinear term $y_{k(e),f}\operatorname{occ}_e(t)$. It gives a finite binary feasibility model directly, without treating a product of decisions as a linear expression. The expanded model can be large; the evolutionary solver uses the compact categorical representation.

## 3. Hard constraints

**C1 — Required sessions and one consistent eligible teacher.**

$$\sum_{q\in A_e}z_{e,q}=1\quad(e\in E),\qquad \sum_{f\in F_k}y_{k,f}=1\quad(k\in K).$$

For every $e\in E_k$ and $f\in F_k$,

$$\sum_{q\in A_e:\ f_q=f}z_{e,q}=y_{k,f}.$$

An empty sum is zero. The latter equation couples every event to the same offering-level faculty assignment. Sessions cannot be dropped, duplicated, split across teachers, or assigned to ineligible faculty.

**C2 — Room clashes.** For every room $r$ and period $t$,

$$\sum_e\sum_{q\in A_e:\ r_q=r,\ t\in B_e(s_q)}z_{e,q}\le1.$$

**C3 — Faculty clashes.** For every faculty member $f$ and period $t$,

$$\sum_e\sum_{q\in A_e:\ f_q=f,\ t\in B_e(s_q)}z_{e,q}\le1.$$

**C4 — Student clashes.** For every atomic group $g$ and period $t$,

$$\sum_{e:g\in G_e}\sum_{q\in A_e:\ t\in B_e(s_q)}z_{e,q}\le1.$$

These sums cover **every occupied period**, including the second or later period of a laboratory.

**C5/C6 — Room capacity, room type, availability, lunch, and block integrity.** Variables exist only for candidates in $A_e$; all other placements are fixed to zero. Capacity is a hard lower bound, not a penalty that a favorable objective can compensate. Room and faculty availability apply to the whole block.

**C7 — Weekly and daily faculty teaching limits.** Let $w_k=\sum_{e\in E_k}\ell_e$. Then

$$L_f=\sum_{k:f\in F_k}w_k y_{k,f}\le H_f\quad(f\in F).$$

For each $f,d$,

$$\sum_e\sum_{q\in A_e:\ f_q=f,\ d(s_q)=d}\ell_e z_{e,q}\le h_f.$$

Limits count periods, not sessions: a two-period lab consumes two units of load. There is no requirement to fill every faculty member's allowance.

**C8 — Distinct teaching days when requested.** For every $k$ with $a_k=1$ and every day $d$,

$$\sum_{e\in E_k}\sum_{q\in A_e:\ d(s_q)=d}z_{e,q}\le1.$$

The flag is `Offering.distinct_days`; it is normally enabled for repeated theory sessions. When enabled for a lab or another offering, the same rule applies. This is a configurable hard rule rather than an assumed preference.

## 4. Objective functions

### 4.1 Teaching-free internal gaps

For resource $v\in G\cup F$, day $d$, and period $p$, let $b_{v,d,p}\in\{0,1\}$ indicate teaching occupancy implied by the placement sums above. On a feasible schedule the resource-clash constraints guarantee binary occupancy. If a resource has no teaching that day, its gap is zero. Otherwise, let $p^-_{v,d}$ and $p^+_{v,d}$ be its first and last occupied periods, and define

$$
\operatorname{gap}_{v,d}=\sum_{p\in P\setminus L:\;p^-_{v,d}\le p\le p^+_{v,d}}(1-b_{v,d,p}).
$$

Then

$$f_1=\sum_{g\in G,d\in D}\operatorname{gap}_{g,d}+\tfrac12\sum_{f\in F,d\in D}\operatorname{gap}_{f,d}.$$

This counts internal empty **teaching periods**. It excludes the common mandatory lunch even when classes occur on both sides of lunch; it excludes free time before the first and after the last class. Faculty-specific unavailability inside the teaching span still counts as teaching-free internal time: the dataset cannot infer whether that time contains a meeting. Thus this is a teaching compactness measure, not a direct measurement of wasted working time. The factor $1/2$ is a declared policy choice; student and faculty gap totals are also reported separately.

An exact binary implementation can define `before` as the OR of occupancies up to a period and `after` as the OR from that period onward; a gap indicator is `before AND after AND NOT busy`. OR/AND constraints provide an exact CP-SAT or MILP encoding without a numerical big-$M$ span approximation.

### 4.2 Duration-weighted unused room capacity

With constant total demand $Q=\sum_e\ell_e$,

$$f_2=\frac1Q\sum_e\sum_{q\in A_e}\ell_e\left(\frac{c_{r_q}-n_e}{c_{r_q}}\right)z_{e,q}.$$

On feasible schedules, $0\le f_2<1$. For the degenerate empty-demand test case, the code defines this objective as zero rather than dividing by zero. This measures seat wastage **during scheduled use**, weighted by session duration. It does not measure how many room-hours are unused across the campus, nor total unused seat-hours, and it does not reward cancelling classes. The denominator remains fixed across solutions.

### 4.3 Relative faculty workload imbalance

Let $m=|F|$, $\rho_f=L_f/H_f$, and $\bar\rho=m^{-1}\sum_f\rho_f$. The third objective is the population standard deviation

$$f_3=\sqrt{\frac1m\sum_{f\in F}(\rho_f-\bar\rho)^2}.$$

All listed faculty are included, even if their current load is zero. For the degenerate empty-faculty/empty-demand test case, the code defines imbalance as zero; a nonempty offering with no eligible teacher remains infeasible. Under the hard limits $\rho_f\in[0,1]$, so $f_3\le1/2$. Relative loads recognize unequal teaching allowances; they do not model research, administration, or differences in class preparation effort. Shared eligibility lets an entire offering move between teachers. Individual sessions cannot be reassigned independently to make this metric appear more variable. With fixed teachers or singleton eligibility sets, $f_3$ can become constant; the system should report that degeneracy instead of claiming a three-way trade-off.

NSGA-II ranking and survival compare the three objectives separately. Heuristic weighted scores may guide construction or local proposals without replacing the objective vector used for Pareto selection and reporting. The search output approximates the feasible non-dominated set. Globally Pareto-optimal means non-dominated over **all feasible schedules**. Exact cleanup certifies non-domination only among saved archive alternatives; the legacy timed algorithms use floating-point comparisons and need the numerical qualification in Section 6.1.

## 5. Why a trade-off is possible, and why it must be measured

The proposal's claim that all objectives necessarily conflict on every instance is too strong. Two analytical micro-instances establish that the objectives can conflict without constructing an artificial plotted front:

1. **Compactness versus room fit.** Take one day with periods 0–3, no lunch, one 20-student group, two one-period offerings, and two fully available eligible teachers (weekly limit 2 each). A 20-seat theory room is available only at periods 0 and 2; a 40-seat theory room only at 1 and 3. Assign a different teacher to each offering. Using the small room twice gives $(f_1,f_2,f_3)=(1,0,0)$. Consecutive classes require the large room for one class, giving $(0,1/4,0)$. Zero wastage forces the gap; zero gap forces positive wastage. These two vectors are globally non-dominated for this micro-instance.
2. **Compactness versus workload.** Keep the two offerings and one adequate room, but let faculty A be available only at 0 and 1, and faculty B only at 3. Both teachers are eligible for both offerings and have weekly allowance 2. A compact timetable at 0 and 1 taught entirely by A gives $(0,0,1/2)$. Teaching one event at 1 with A and the other at 3 with B gives $(1,0,0)$. Equal relative loads force the internal student gap; compactness forces A to teach both sessions.

Neither example proves that every random college instance has a large non-dominated front or that an evolutionary algorithm will find it. On a resource-rich instance all objectives may improve together, room wastage may be nearly constant, or one solution may dominate almost everything. Report objective ranges, pairwise relationships, discovered front size, and representative schedules. Never add noise to points, relax hard constraints, or omit a strong baseline to make a Pareto plot look convincing.

### 5.1 Exact ideal-vector certificates for the executed small instances

A heuristic can sometimes find a globally certified vector without enumerating the full schedule space: establish a valid lower bound for every objective, then exhibit one feasible schedule attaining all bounds **simultaneously**. The lower bounds need not preserve the same constraints; each is valid independently. Simultaneous attainment is the essential step.

For the executed 40-event cases `small_10`, `small_20`, and `small_30`, required contact is 44 periods. The workload relaxation drops eligibility, time, and resource interactions but retains indivisible offering loads: twelve offerings of three periods and four of two periods, assigned to six faculty with identical allowance 20. Dynamic programming exhausts the load-count allocations to faculty bins and obtains

$$\min\sum_f L_f^2=328.$$

This is a relaxation, so its minimum is a lower bound for any schedule obeying the original constraints. Equal allowances make the mean normalized load constant, giving

$$f_3^2\ge\frac{328}{6\cdot20^2}-\left(\frac{44}{6\cdot20}\right)^2=\frac1{450}.$$

Nonnegative gaps give $f_1\ge0$. Selecting the best-fitting compatible room separately for each event, while ignoring resource conflicts and availability, gives the exact rational bound $f_2\ge14/55$. Actual feasible archived schedules attain zero student/faculty gaps, exact room wastage $14/55$, and faculty loads $[6,6,8,8,8,8]$, whose squared sum is 328. Therefore their objective vector

$$(0,14/55,\sqrt{1/450})$$

is the **singleton global three-objective Pareto front** for each of those three fixed instances. Different timetable identities may attain it. Any non-ideal vectors in another run's discovered archive are globally dominated by this ideal, even if that run has not discovered it. This is stronger evidence of an easy/sufficiently slack small-instance distribution than a large plotted cloud of schedules would be.

The analysis script `experiments/certify_small_ideal.py` and saved `results/benchmark/small_ideal_certificates.json` record the bounds and attaining schedule references. Exact integer gaps, rational room waste, and integer squared loads establish attainment; approximate equality of plotted floating-point values alone is not the certificate. The proof applies to the explicitly checked cases, not all generated seeds or larger instances. A singleton ideal means there is no unavoidable compromise at the global optimum; objectives can still oppose along suboptimal schedules. The separate exhaustive micro-examples remain valid demonstrations that meaningful conflicts are possible in this model.

## 6. Constraint handling in heuristic search

The evaluator reports a nonnegative integer violation $V$ and a breakdown by constraint. $V=0$ means every hard requirement is satisfied, including completeness and valid IDs; it is not merely a clash count. Overloads are counted in excess periods and clashes over all occupied resource-periods. Malformed, missing, invalid, or ineligible assignments receive positive violation. The exact aggregation is implemented and tested in `src/timetable/evaluation.py`; it is a search ordering, not a calibrated measure of administrative harm.

Constrained dominance follows the standard feasibility rule:

- A feasible candidate dominates every infeasible candidate.
- Between infeasible candidates, the smaller violation wins.
- Between feasible candidates, $u$ dominates $v$ iff $u_i\le v_i$ for all objectives and $u_j<v_j$ for at least one.

Infeasible candidates may be retained internally to help search, but are excluded from timetable exports, feasible fronts, hypervolume, and claims of usable schedules. Objective values attached to infeasible candidates are diagnostics; they do not establish better timetables.

### 6.1 Numerical precision and reporting

The mathematical dominance definition is exact. Legacy timed search archives instead compare floating-point objective values. An exact-rational audit found 10 dominated saved points in the historical archives and 53 in the final validation archives, primarily because equal exact workload variances produced slightly different floating-point SD values. Every affected timetable remains feasible. Raw archive cardinality and strict mathematical front cardinality must therefore be distinguished.

The separate `experiments/exact_fronts.py` postprocessor compares exact gap, room-waste, and workload-variance keys. For $C=\operatorname{lcm}_{r\in R}c_r$, $D_H=\operatorname{lcm}_{f\in F}H_f$, and $z_f=L_f(D_H/H_f)$,

$$f_2=\frac{\sum_e\ell_e(c_{r(e)}-n_e)(C/c_{r(e)})}{C\sum_e\ell_e},\qquad
f_3^2=\frac{|F|\sum_f z_f^2-(\sum_f z_f)^2}{|F|^2D_H^2}.$$

The quantities are rational and comparisons are exact; square root is strictly increasing for nonnegative variance, so ordering $f_3^2$ is equivalent to ordering $f_3$. The fixed faculty-gap weight 0.5 gives an exact half-integer gap key. Canonical numeric SD is generated only after exact comparison for display and indicator calculation.

Cleanup leaves 759 historical and 3,242 final non-dominated saved alternatives, while the original 769/3,295 raw feasible schedule records remain unchanged. The maximum per-run HV difference is approximately 3.33e-16 and all published rounded gains remain unchanged. Postprocessing is outside the recorded optimizer runtime. It certifies a front among the **saved candidates**, not every evaluated candidate or the complete feasible space; it cannot recover discarded schedules. Exact global small-instance certificates are independent proofs and remain valid.

Use `python experiments/exact_fronts.py --study enhancement_validation` or `--study benchmark` for the retained studies. For a new run, use `--run RUN.JSON --instance INSTANCE.JSON --output FRONT.JSON`; the output includes full surviving schedules and original survivor indices. The [final report](../report/report.md) gives complete validation/export commands, and [the numerical-precision notes](../docs/numerical_precision.md) describe the artifact policy.

## 7. Classification, assumptions, and limits

The model is deterministic, finite, discrete, constrained, combinatorial, and multi-objective. Its feasibility and room-wastage components admit a 0–1 linear formulation. Gap indicators admit linear logical encodings. The standard-deviation objective is nonlinear; calling the full three-objective problem an ordinary linear program would be incorrect. Even simplified timetabling contains graph coloring, so exact optimization is not expected to scale uniformly with instance size.

The week repeats, event durations are fixed, all demand is known, and each offering has one teacher. There are no student-level elective decisions, travel times, online classes, uncertain attendance, minimum faculty loads, team teaching, room preferences, rotating weeks, or resilience objective. Optional fixed event starts described in the proposal are not assumed by this formulation unless explicitly added to the input schema. Global lunch is excluded from idle gaps; individual absences are not. Feasibility of general user-provided instances is not guaranteed. Constructive synthetic witnesses establish feasibility only for the corresponding generated instance and are kept separate from optimization inputs.

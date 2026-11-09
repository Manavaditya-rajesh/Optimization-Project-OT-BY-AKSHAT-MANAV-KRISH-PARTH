# Follow-up enhancement study: protocol and evidence boundaries

This document separates the original completed benchmark from an executed follow-up study of timetable quality and computational efficiency. It preserves the declared protocol and records measured outcomes, including unfavorable comparisons and the limits of the evidence. The original `results/benchmark/` records, certificates, configurations, and figures are retained unchanged.

## 1. What the original results establish

The original study compared equal counts of complete schedule evaluations. Repeated greedy was a deliberately strong baseline, and it had higher mean hypervolume than the original enhanced NSGA-II at every tested size. The enhanced method used less wall time, so equal evaluation counts alone do not answer the equal-compute comparison.

The original implementation offers concrete improvement targets:

- Only half of its initial population was constructed; the other half used independent random categorical genes and was usually infeasible.
- Whole-offering crossover preserves the teacher for each offering but does not preserve interactions between different offerings. It can simultaneously create student, faculty, and room clashes.
- Reconstruction repair can discard much of the inherited structure, returning the search toward repeated construction rather than refining feasible schedules.
- Two local proposals per child can be too few, and proposals lacking direct resource checks can be rejected without useful change.
- A front archive is necessary for reporting trade-offs but does not itself establish that NSGA-II selection is helping the search.

From the original immutable run metadata, base offspring evaluation count is `evaluations - population_size - repairs - local_proposals`. The mean fraction of those offspring requiring repair was approximately **91.1% small, 94.6% medium, and 97.2% large**. Accepted local steps divided by evaluated local proposals were approximately **18.6%, 12.7%, and 8.5%**. These are retrospective diagnostics of that implementation, not held-out evidence for a replacement.

The three original 40-event cases also have a certified singleton global ideal vector `(0, 14/55, sqrt(1/450))`. A solver cannot strictly improve hypervolume beyond that ideal on those instances. A meaningful small-case success can be more reliable or faster attainment of the same ideal; it cannot be a manufactured wider front or a promise to beat the optimal greedy objective vector. Any analogous claim on new small instances must be independently certified.

## 2. Candidate improvement and precise algorithm label

The proposed replacement starts from a population of feasible constructive schedules and uses resource-aware local variation. Every changed candidate still passes the shared complete evaluator before it can be treated as feasible. Direct resource checks are proposal screening, not a replacement for final validation. They count toward runtime even when no full evaluator call is needed.

A mutation-only NSGA-II variant is valid when it genuinely uses constrained non-dominated ranks, crowding tournaments, and elitist environmental selection from the parent–offspring union. Its label must state that it uses feasible mutation and omits genetic crossover. Feasible local moves plus a Pareto archive alone would instead be multi-objective local search; those ingredients do not justify calling an algorithm NSGA-II.

The intended new population method reuses the tested rank/crowding and parent–offspring survival machinery from the standard implementation. Its enhancement is targeted at the observed feasibility destruction and reconstruction cost. It does not receive a generator certificate or an exact optimal timetable. Structured faculty reassignment, if enabled, must be described as a distinct component with its own limits and cost; it must not silently supply uncharged complete candidate evaluations.

The exact enabled moves, initialization count, step policy, restart policy, optional structured faculty search, and stopping parameters must be saved with every new run. Do not retrospectively rename the best-performing method as the originally preselected algorithm.

## 3. Development, freeze, and held-out validation

The old benchmark and explicitly declared development cases may be used for profiling, debugging, and choosing a bounded number of implementation variants. Previously inspected seeds are development data. The new instance seeds **1010, 1020, and 1030 are reserved for validation** and must not be used to choose operator rates, population size, objective scales, or a favorable stopping cap.

Before any validation run:

1. Save a machine-readable study matrix listing sizes, instance seeds, solver seeds, generator settings, methods, complete-evaluation caps, time budgets, and any ablations.
2. Freeze the implementation and save its source hashes, configuration fingerprint, dependency versions, Python/platform details, and exact objective/indicator definitions.
3. Record the development decisions and which candidate variants were rejected. Code fixes after validation begins require a new version and new validation disclosure; they are not an opportunity to retain only favorable runs.
4. Run every declared method/instance/seed combination. Preserve failed runs, no-feasible archives, exceptions, and time overruns under a declared reporting rule.

Default synthetic instances remain the primary comparison. Additional resource-tight or availability-stressed scenarios, if practical, must be predeclared and reported as separate scenarios; do not change the distribution solely because the default results are unfavorable. Instance seed and solver seed are different experimental factors. More solver seeds on one instance do not create more independent college datasets.

The saved matrices are `experiments/enhancement_development.json` and `experiments/enhancement_validation.json`. The validation configuration declares the following **planned** matrix:

| Size | Held-out instance seeds | Solver seeds | Complete-evaluation cap | Wall-time allowance | Planned runs across 4 methods and 2 protocols |
|---|---|---|---:|---:|---:|
| Small regression | 1010 | 0, 1, 2 | 720 | 2.5 s | 24 |
| Medium primary | 1010, 1020, 1030 | 0, 1, 2 | 360 | 6 s | 72 |
| Large primary | 1010, 1020, 1030 | 0, 1, 2 | 240 | 16 s | 72 |

The four methods are `greedy`, `original_enhanced`, `memetic`, and `ablation_local`; all use population parameter 24 where applicable. Equal-time runs have a safety ceiling of 100,000 full evaluations. This matrix declared **168 validation runs** before execution; all 168 are now complete and verified, as detailed in Section 8. The larger development matrix uses instance/solver seeds 9000/9001, medium/large sizes, the same four methods and both resource protocols, for 64 planned development runs; it was **not executed in full**. Actual development consisted of a **12-run pilot**, one instance and solver seed 9000 at each of the three sizes, four methods, and 240 complete evaluations per run. Those exploratory records are in `results/enhancement_validation/development_pilot.json`; they are not held-out evidence and are not pooled with validation.

Before validation, the combined automated suite passed **201 tests**. The candidate implementation, settings, and validation matrix were then frozen in `results/enhancement_validation/freeze_evidence.json`; the validation manifest and `source_snapshot/` preserve the measured source independently of that scratch record. No source changes, tuning, or concurrent tests are permitted during the timing study. Saved run files and the eventual verification record establish actual completion.

## 4. Comparison methods and causal ablations

The minimum useful comparison includes the **unchanged repeated-greedy policy**, the original enhanced NSGA-II where practical, the new feasible population method, and a strong local-search ablation.

The proposed ablation uses the same feasible initialization and move distribution as the new population method, but maintains independent local trajectories with fixed positive random scalar directions. It selects a trajectory uniformly and accepts feasible scalar improvements. Every evaluated feasible proposal still enters the common reporting archive, including locally rejected alternatives. This removes the rank/crowding selection and survival **bundle** while retaining local improvement and diverse preferences.

This comparison can test whether the NSGA-II population selection bundle adds value beyond well-designed multi-start local search. It cannot isolate tournament selection from environmental survival, or attribute any difference to one neighborhood. Parent states and later candidates will diverge; “same moves” means the same proposal policy, not an identical candidate stream. The implementation pairs initialization through an identical seeded construction/RNG prefix, which the tests verify. It then continues with one RNG per run; the two selection policies consume that stream differently, so later proposal streams are not paired or identical. Separating initialization, selection, and variation RNG streams is a future variance-control improvement, not an implemented guarantee.

Optional component ablations should answer an observed development question, rather than expand the algorithm catalog. Examples include disabling structured faculty reassignment while retaining feasible moves, or disabling only the new selection bundle. Use the same declared budgets and initialization accounting. If local search outperforms the population method, report that result and recommend the stronger method; preserving the NSGA-II name is not the project objective.

## 5. Evaluation accounting and equal-runtime comparison

Two resource views are required because a constructive attempt and a locally edited candidate have very different internal costs.

**Equal complete evaluations.** Charge every full call to the common evaluator made during search, including initialization, infeasible attempts, rejected proposals, repaired results, and local or structured-search candidates. Any internal partial occupancy/load/delta calculation must be disclosed and included in wall time. A generated candidate that is screened before full evaluation is not a charged complete evaluation, but its screening cost and count remain visible. Report full evaluations, proposal attempts, no-op returns, duplicate schedules, and feasible evaluation fractions separately. The frozen implementation distinguishes first-attempt no-ops from final no-ops after fallback, counts actual neighborhood calls, records the full search policy, and preserves native progress counters when the timing observer interrupts a run.

**Equal runtime.** Use a common wall-clock allowance within each paired instance. Common imports, shared input-schema validation, and cold-cache reset are preflight work for every method. Start timing before algorithm-specific preprocessing and initialization; include candidate screening, construction, local search, population ranking/survival, and archive bookkeeping. Exclude input generation, reading already saved data, final revalidation, serialization, plotting, and post-study analysis uniformly. Document cache treatment and use a sequential, rotated method order or another fixed order-control rule. New greedy measurements must be collected alongside the new algorithms; comparing new timings against historical benchmark timings would confound environment and machine load.

A valid time-prefix trace records actual elapsed wall time and complete evaluation count for each finished full candidate evaluation. The new common observer timestamps immediately after the full objective/constraint calculation and before its archive bookkeeping. Thus cutoff quality means information from complete evaluations available by the cutoff, not a guarantee that the fully packaged archive was published before it. Observer and algorithm bookkeeping still consume the measured wall time, and this timestamp policy is common to all methods. At a cutoff `T`, quality uses only candidate results available no later than `T`; it must not include the first candidate completed after `T`, a repaired schedule discovered after `T`, or the final archive of a run that continued past `T`. Interpolation between archive discoveries cannot create a schedule earlier than it was evaluated. If an indivisible construction overruns the stop time, log its end time and overrun, exclude its late result from the cutoff front, and report the prefix convention explicitly.

A safe implementation can retain an event trace of feasible objective discoveries and actual completion times, then reconstruct the non-dominated archive at each common cutoff. The timestamp policy must be identical across methods. A trace that records only a final runtime or one timestamp per generation cannot resolve candidate-level quality at an earlier cutoff. Do not estimate equal-time quality by multiplying evaluation count by average time per evaluation.

A common evaluation safety cap may bound an equal-time run, but report when that cap is reached before the time allowance; otherwise the experiment is silently evaluation-limited. If a solver stops early by its own policy, its last available archive can be carried forward with that early-stop reason stated. No method receives free initialization or an incumbent created outside its measured budget.

## 6. Indicators, uncertainty, and acceptable conclusions

Reuse the original objective definitions, fixed a priori normalization, and hypervolume reference `(1.1,1.1,1.1)` so the follow-up changes the optimizer rather than the meaning of quality. Report raw gaps, room wastage, workload SD, feasible-run rate, feasible evaluation fraction, runtime, and front-vector counts alongside hypervolume. The conservative gap scale can make small gap changes weakly visible in HV; do not call two schedules practically equal solely because their HV values are close. Distinguish per-run discovered fronts from pooled plots across different instances.

Primary comparisons must be paired by instance and solver seed. Show per-instance mean differences and all-run distributions rather than only an overall winning mean. Descriptive paired wins/ties/losses and effect magnitudes are useful. With only three independent validation instances for each primary medium/large size, even an exact two-sided sign test with all three wins has minimum p-value 0.25. The small regression has only one independent instance and is not a basis for general superiority claims. Repeated solver seeds cannot remove that limitation. Avoid claims of broad statistical superiority from clustered runs or from a selected favorable metric.

Feasibility is mandatory. An empty feasible archive receives HV zero and remains in all-run quality averages. Undefined spacing or empty-target coverage remains undefined or is explicitly excluded from conclusions; do not use the original optional zero-coverage convention to assert dominance. Comparing equal objective vectors does not create additional trade-offs.

A defensible positive conclusion is specific: for example, higher measured HV at the same evaluation cap or wall-time allowance on the declared held-out synthetic instances, with raw objective changes and feasibility disclosed. It does not imply global optimality, real-college effectiveness, or dominance over every baseline. A mixed or negative result is also a complete experimental result and should guide the next development decision.

## 7. Evidence checklist and current status

The following artifacts are required before marking the follow-up study complete:

- Saved development and frozen validation configurations, source fingerprints, and recorded solver parameters.
- Tests for feasible variation, full-block occupancy, teacher consistency, budget charging, no-op/duplicate handling, deterministic evaluation-limited runs, and time-prefix exclusion of late results.
- Raw paired run records containing all objective vectors, saved feasible schedules, complete-evaluation counts, elapsed discovery traces, feasibility diagnostics, and method-specific counters.
- Independent-from-search revalidation of every reported schedule; no claim of a second independently written checker unless one exists.
- Equal-evaluation and equal-time tables and plots, with all declared failures retained and no results copied from the old timing study.
- A direct population-method versus local-search ablation, interpreted as a bundle comparison.
- An outcome section identifying what improved, what did not, and which claims remain unsupported.

**Status:** 201 tests passed before the source freeze; the 12-run development pilot is complete; the 64-run larger development configuration remains unexecuted. All 168 held-out runs completed under the frozen package and declared matrix. Post-search verification reports PASS for every saved archive and cutoff front. Verification, sampled-prefix plotting, fixed-instance timetable export, and report generation use separate postprocessing files outside the measured package. Section 8 records the actual outcomes and their limits.

## 8. Measured held-out findings

The frozen validation study contains 168 runs on seven synthetic instances. All four methods returned a feasible archive in every run. The new mutation-only memetic NSGA-II had higher mean hypervolume than repeated greedy on both primary sizes under both resource protocols, winning all nine paired solver runs in each of those four conditions. These are observations on the declared test set; the one small regression case gave mixed outcomes.

| Size | Resource protocol | Greedy mean HV | New NSGA-II mean HV | Relative change in mean HV | Paired NSGA-II wins / ties / losses |
|---|---|---:|---:|---:|---|
| Small | Complete evaluations | 0.934747 | 0.930290 | -0.477% | 1 / 0 / 2 |
| Small | Wall-time allocation | 0.929781 | 0.930290 | +0.055% | 2 / 0 / 1 |
| Medium | Complete evaluations | 1.008330 | 1.056105 | +4.738% | 9 / 0 / 0 |
| Medium | Wall-time allocation | 0.988710 | 1.060477 | +7.259% | 9 / 0 / 0 |
| Large | Complete evaluations | 0.940824 | 0.977304 | +3.878% | 9 / 0 / 0 |
| Large | Wall-time allocation | 0.930485 | 1.013967 | +8.972% | 9 / 0 / 0 |

Relative changes divide the difference between method means by the greedy mean; HV itself is an indicator volume rather than a percentage or an administrative utility. At equal complete evaluations, mean search time was approximately 2.928 versus 20.215 seconds for medium and 8.041 versus 51.671 seconds for large (new NSGA-II versus greedy). These are about 6.90× and 6.43× runtime ratios in this measured environment. The separate wall-time protocol includes only results completed within the common 6-second and 16-second allocations; boundary overshoot receives no quality credit.

The new method also evaluates many more candidates within those allocations: mean counts were about 948 versus 106 for medium, and 800 versus 75 for large. Direct screening, partial workload search, initialization, and selection are included in measured time. The evaluation and time views therefore support complementary conclusions; candidate counts are not interchangeable with compute.

### 8.1 Objective-level trade-offs

Higher HV does not mean every timetable or objective improved. At equal evaluation caps, the mean of each run's best workload SD improved from approximately 0.05027 to 0.02565 for medium, and from 0.07306 to 0.05339 for large. At the same time, the mean best room-wastage fraction rose from 0.18217 to 0.18409 for medium and from 0.20214 to 0.20375 for large; mean best gaps rose from 0 to 0.056 and from 1.722 to 2.444 respectively. The archives contain alternatives favoring different priorities.

These objective-wise extrema can belong to different schedules. They are not a jointly attained ideal vector or a proof that the full greedy archive is dominated. The conservative fixed normalization can make gap changes weakly visible in HV, so timetable grids, raw faculty loads, and the coordinator's preferences remain necessary for a practical choice. A separate exact integer/rational certificate now establishes the same singleton global ideal `(0, 14/55, sqrt(1/450))` for the held-out `small_1010` instance. The memetic equal-evaluation run with solver seed 1 attains it; the other two memetic seeds have worse final HV. One globally optimal run therefore coexists with a lower small-case mean than greedy. This certificate was checked for seed 1010 itself rather than inferred from the historical certificates or a plotted front; it is saved in `results/enhancement_validation/small_ideal_certificates.json`.

### 8.2 Does NSGA-II selection explain the gain?

| Primary condition | New NSGA-II mean HV | Scalar-local mean HV | NSGA-II paired wins / ties / losses |
|---|---:|---:|---|
| Medium, complete evaluations | 1.056105 | 1.054147 | 5 / 0 / 4 |
| Medium, wall-time allocation | 1.060477 | 1.061314 | 6 / 0 / 3 |
| Large, complete evaluations | 0.977304 | 0.978518 | 4 / 0 / 5 |
| Large, wall-time allocation | 1.013967 | 1.011318 | 5 / 0 / 4 |

The matched scalar-local method is highly competitive: it has slightly higher mean HV on medium wall-time runs and large equal-evaluation runs. NSGA-II has the higher mean on medium equal-evaluation and large wall-time runs. There is no consistently positive selection-bundle effect across these conditions. The comparison supports the effectiveness of the new initialization/variation/intensification package while leaving the incremental value of NSGA-II selection unresolved. It does not isolate full feasible initialization, any one neighborhood, or faculty branch-and-bound as the sole cause.

### 8.3 Verification and inference limits

The 168-run study performed **76,086 complete search evaluations**. `results/enhancement_validation/verification.json` reports PASS for **168 runs**, **7 separate feasibility certificates**, and **3295 archived feasible schedules**. It reconstructs the cutoff fronts, checks fixed allocations and discovery prefixes, confirms source-snapshot identity, and excludes **9 late completed evaluations**. All 42 paired initialization groups checked agree. There are no empty feasible archives. This reuses the shared checker outside search and does not claim a second independently written constraint checker.

Each primary condition has only three independent synthetic instances. Their instance-mean sign tests give p=0.25 for new NSGA-II versus greedy, even though all nine paired solver runs favor the new method. The smaller run-level p-values are descriptive because solver seeds are clustered within instances. There is no basis here for a broad statistical or institutional superiority claim, and no multiplicity-adjusted claim is made. The small regression uses one instance and three solver seeds.

### 8.4 Additional workload-only lower-bound check

For each held-out medium instance, total teaching demand is 166 periods across 20 faculty with common weekly allowance 20. Relaxing offering indivisibility, eligibility, and timing gives the integer-load bound `sum(load²) >= 14*8² + 6*9² = 1382`, hence relative-load variance at least `21/40000`. Saved feasible schedules attain that bound on all three medium instances. They therefore certify the global minimum of the **workload objective alone** on those fixed cases. They do not certify gap or room optimality, nor the global three-objective front.

The corresponding large-case integer bound was not attained in the saved archives. Nonattainment of a relaxation bound does not establish that the observed workloads are nonoptimal, because the relaxation ignores several hard constraints. The simple small-case integer-load relaxation gives 324, while the stronger offering-partition proof gives 328 because offerings are indivisible. A feasible `small_1010` schedule attains 328 together with the exact gap/room lower bounds, yielding the separate global ideal-vector certificate described above.

### 8.5 Evidence artifacts and remaining work

- Frozen configuration and source identity: `experiments/enhancement_validation.json`, validation `manifest.json`, and `source_snapshot/`.
- Raw outcomes and direct paired comparisons: `results/enhancement_validation/runs/`, `summary.json`, and `summary.md`.
- Constraint, prefix, and workload lower-bound evidence: `results/enhancement_validation/verification.json`; the small global ideal proof is in `small_ideal_certificates.json`.
- Postprocessing entry points: `experiments/verify_enhancement.py`, `plot_enhancement.py`, `export_enhancement.py`, and `report_enhancement.py`.

The delivered follow-up is a successful bounded synthetic comparison against the unchanged greedy policy, with mixed small-case and selection-ablation findings retained. Remaining work includes more independent institutions or realistic datasets, broader instance seeds, tighter-resource scenarios, indicator-scale sensitivity, component-specific ablations, and separate RNG streams for variance control. Equal-time results remain sensitive to hardware/load. Global Pareto certification is limited to the explicitly proved small instances; the medium/large archives have no global front certificate. Real-college validation and universal optimizer superiority are not claimed. The [follow-up report](../report/enhancement_report.md) includes complete schedule examples and generated figures; the [saved summary](../results/enhancement_validation/summary.md) retains every method and condition.

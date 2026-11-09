# Final technical audit

The audit started from published revision `3ca05148d1245e08575d9e2b7499e0d825d802af`.
It covers installation, code, mathematical constraints, experimental evidence,
public commands, reproducibility and submission artifacts. The 19 package
source files used in the timed enhancement study are preserved unchanged.

## Checks completed

| Check | Observed result |
|---|---|
| Fresh GitHub checkout and isolated Python 3.12 environment | Pinned dependencies and editable project install succeeded; system site packages disabled; `pip check` passed; installed `timetable` command works. |
| Existing automated suite in that clean environment | 201 tests passed in 15.81 seconds. After adding eight precision regressions, the complete suite passed **209 tests in 16.47 seconds** in the isolated environment. |
| Independent small-instance feasibility/objective oracle | 139,072 candidates checked: 8,000 random/malformed and 131,072 domain-valid combinations. No feasibility mismatches; 5,068 feasible cases matched independently calculated ordinary floating-point objectives. |
| Faculty intensification | Three nontrivial cases each compared with all 729 teacher assignments; returned best values matched exhaustive enumeration. |
| Multi-period/lunch moves | 200 further proposals with two lunch breaks remained feasible. |
| Historical saved study | All 192 runs, 769 feasible archived schedules and seven certificates rechecked; 48 plain NSGA-II failures remain visible. |
| Enhancement saved study | All 168 runs, 3,295 feasible archived schedules and seven certificates rechecked; all cutoff histories reconstructed; nine late evaluations excluded. |
| CLI | 38 end-to-end checks passed, including all three sizes, five search methods, certificate checking, exports, invalid inputs, exact micro examples and CP-SAT. Plain NSGA-II may correctly return search-failure code 2. |
| Experiment orchestration | Twelve separate smoke runs completed; original and follow-up experiment commands both resumed without changing saved raw-run hashes. These are smoke checks, not additional performance evidence. |
| Replotting | Both historical and enhancement plotting commands succeeded in the fresh checkout. |

The independent oracle uses different resource-set logic from the solver/checker.
Its ordinary floating-point objective comparisons do not establish exact rational
Pareto dominance. The separate precision audit below addresses that distinction.

## Findings corrected

**Formulation indices.** Some original displayed sums reused a room or faculty
index as both a summed and fixed index. `formulation/README.md` now introduces
explicit candidate coordinates and fixed-resource filters for teacher coupling,
room/faculty clashes and daily limits. The code and consolidated report already
used the intended constraints.

**Bounded-search claims.** The implementation summary now states that faculty
branch-and-bound certifies a selected-neighborhood optimum only when it finishes
or attains a valid bound. A 12,000-node cap alone supplies no such guarantee.

**Plotting dependency floor.** Flexible dependency declarations now require
Matplotlib 3.9 or newer: the plotting code uses `boxplot(tick_labels=...)`, which
was introduced in 3.9. The pinned, tested version remains 3.10.8. This corrects an
overly permissive lower bound without changing the measured environment.

**Numerical Pareto ties.** Exact arithmetic found mathematically dominated points
retained by the frozen floating-point archive comparator. The separate
`experiments/exact_fronts.py` tool now produces canonical fronts among saved
schedule alternatives, with exact rational keys and traceable survivor indices.

| Study | Raw feasible archive records | Dominated records removed | Canonical front records |
|---|---:|---:|---:|
| Historical | 769 | 10 | 759 |
| Enhancement | 3,295 | 53 | 3,242 |

The production postprocessor and independent rational audit agree on survivor
indices, exact objective keys and input-run hashes for **all 360 runs**. Fresh-run
and repeated canonical cleanup commands also pass without altering their inputs.
The largest absolute per-run HV change is `3.3306690738754696e-16`.
The four printed primary gains remain **4.74%, 7.26%, 3.88% and 8.97%**.
All eight published whole-timetable examples survive cleanup. Raw records,
timings, source snapshots, failures and cutoff rules are retained. This correction
is postprocessing, not a newly timed optimization experiment. See
[the precise finding and workflow](numerical_precision.md).

## Remaining low-priority hardening items

These edge cases are disclosed rather than silently changing the frozen search
source used to obtain the benchmark measurements:

1. Optional generator `theory_sessions` accepts Boolean `true` as one session.
   Supply a positive JSON integer. Default presets and saved experiments do not
   use this invalid input.
2. Generated metadata for a `theory_sessions` override also records derived
   `target_events`; replaying both as input overrides is rejected. Remove the
   derived field when replaying, and preserve the original input configuration.
3. The fast comparison resume validator does not check every invariant of a
   manually altered checkpoint. The full saved-results verifier checks additional
   front/history properties. Run full verification and exact-front postprocessing
   before trusting edited or externally supplied records. Published records pass.
4. The original repair helper can randomize an equal-violation tie even at zero
   violation if directly called with an already-feasible parent. Published NSGA-II
   invokes it only for infeasible candidates, so this does not affect its searches.

Future changes inside the evaluator, generator or repair/search policy should
receive a new source fingerprint and separately reported experimental results.
The exact-front postprocessor is deliberately outside the frozen timed package.

## Evidence and reproduction

Logs, source fingerprints, the independent oracle and the independent numerical
audit are under [results/final_audit/](../results/final_audit/).
Canonical front summaries are saved separately for
[the historical study](../results/exact_fronts/benchmark/summary.md) and
[the enhancement study](../results/exact_fronts/enhancement_validation/summary.md).

```bash
python -m pytest -q
python experiments/verify_saved_results.py --study benchmark
python experiments/verify_enhancement.py --study enhancement_validation
python experiments/exact_fronts.py --study benchmark
python experiments/exact_fronts.py --study enhancement_validation
PYTHONPATH=src python results/final_audit/core_oracle.py
python results/final_audit/independent_precision_audit.py --output work/precision_audit.json
```

## Final artifacts

The regenerated final report has 21 pages and all 19 required sections. The
presentation has 21 slides, 21 nonempty embedded note sets and 21 PDF pages.
All 106 scientific/timetable/presentation PNGs decoded successfully, all local
Markdown links resolved, and both PDFs passed text-boundary checks. Presentation
evidence hashes match their inputs. See `results/final_audit/artifacts.json`.

## Limits of the conclusion

No modeled hard-constraint failure or invalid exported benchmark timetable was
found. This audit does not establish global medium/large Pareto optimality,
real-college effectiveness, consistent superiority over scalar-local search or
broad statistical significance. Data are planted-feasible and synthetic, and
only three independent instances per primary size were tested. Small-instance
regressions and globally singleton ideal fronts remain part of the findings.
Course approval, membership, access and authentic weekly participation remain
group-managed matters, as agreed; they are not certified by these technical checks.

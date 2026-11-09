# Exact arithmetic for reported fronts

The final audit found a floating-point tie issue in the frozen search evaluator.
All saved schedules remain feasible. The issue concerns whether every retained
objective vector is mathematically non-dominated.

## Finding and measured effect

Different faculty load multisets can have the same exact relative-load
variance. The evaluator's floating-point calculation can give their standard
deviations values one unit in the last place apart. An apparent tiny workload
advantage can then keep a timetable whose other objectives are worse.

For example, archive entries 8 and 9 in
`results/enhancement_validation/runs/large_1010_evaluations_memetic_0.json`
both have gap score 5, total teaching load 440, 50 faculty, weekly allowance
20 and squared-load sum 4038. Both therefore have exact relative-load variance
`83/10000`. Their room wastages are `2701/13200` and `43/200`, so entry 8
mathematically dominates entry 9. The stored workload SD values are respectively
`0.091104335791443` and `0.09110433579144299`; the frozen floating-point
comparator treats these as a trade-off.

| Study | Raw feasible archive records | Mathematically dominated records removed | Exact-front records retained |
|---|---:|---:|---:|
| Historical benchmark | 769 | 10, across 8 runs | 759 |
| Enhancement validation | 3,295 | 53, across 36 runs | 3,242 |

There were no exact duplicate full objective vectors in those archives. All
eight timetable representatives used by the report and presentation survive
the cleanup. The largest absolute change in any run's normalized hypervolume
is `3.3306690738754696e-16`. The printed tables, four primary improvement
percentages, small regression and competitive ablation findings remain unchanged.

## Correction and guarantee

`experiments/exact_fronts.py` validates each schedule and compares the key

`(exact weighted gaps, exact duration-weighted room wastage, exact relative-load variance)`.

The first two coordinates are rational; the third is calculated from exact
fractions of integer faculty loads and allowances. Comparing nonnegative
variance is equivalent to comparing SD. This avoids taking square roots during
dominance checks, uses no numerical tolerance and preserves genuinely small
objective differences. SD is computed only for display and the existing
floating-point hypervolume indicator.

The resulting set is exactly non-dominated **among the saved schedule
alternatives supplied to the tool**. It is not a global Pareto certificate,
and the tool cannot recover schedules absent from the supplied archive. The
hypervolume implementation remains a deterministic 3-D slicing algorithm
using floating-point displayed coordinates; exact dominance does not turn its
irrational SD coordinates into arbitrary-precision volumes.

This is postprocessing, not a new optimization experiment. Original source
snapshots, raw objective values, candidate histories, runtimes, stopping
budgets, failures and measurements are preserved. Cleaned artifacts record
the source run and original archive indices so that every retained timetable
is traceable. No corrected value is substituted silently into a timed run.

## Reproduce

From the installed project root:

```bash
python experiments/exact_fronts.py --study benchmark
python experiments/exact_fronts.py --study enhancement_validation
```

Separate canonical results are written under
`results/exact_fronts/STUDY/`, including summaries and per-run survivor
references. For a newly generated timetable archive:

```bash
python experiments/exact_fronts.py --instance data/demo.json --run results/demo_memetic/run.json --output results/demo_memetic/exact_front.json
```

Use the resulting exact-front JSON as the final objective-front artifact.
Existing raw solver exports remain available for diagnosis. The original
timed study can be reproduced at its recorded revision; a future change to
canonical arithmetic inside search would require a new source fingerprint
and newly reported experiment results.

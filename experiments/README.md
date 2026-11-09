# Reproducible experiments

Run commands from the repository root after installing the project. Historical `benchmark` measurements belong to source commit `9947d9d`; the follow-up changes the package fingerprint. Verify/replot historical records or use a newly named configuration for fresh runs, rather than resuming old measurements under changed source. The
experiment runner uses saved JSON configurations, deterministic instance and
solver seeds, complete-schedule evaluation caps, raw schedule archives, and
independent validation. A configuration defines a study; it is not evidence that
all of its runs have been completed. Inspect the saved run files and summaries
to determine actual completion.

```bash
python main.py experiment --config experiments/smoke.json
python experiments/verify_saved_results.py --study benchmark
python main.py plot --results results/benchmark --figures figures/benchmark
```

The configurations have these intended scopes:

| Configuration | Instances and solver seeds | Evaluation cap per run | Intended use |
|---|---|---|---|
| `smoke.json` | One instance of each size, two solver seeds | 96 | End-to-end sanity check; 24 runs across four methods |
| `benchmark.json` | Small: 3 instances × 10 seeds; medium: 2 × 6; large: 2 × 3 | Small 720; medium 360; large 240 | Bounded comparison; 192 runs across four methods |
| `full_study.json` | Five instances of each size × 30 solver seeds | 4000 | Larger optional study; 1800 runs across four methods |

Budgets differ between sizes to bound computational cost. Method comparisons
are made **within a size**, with identical instance/solver seed pairings and
the same evaluation cap. Cross-size hypervolumes are not treated as a common
performance ranking.

## Methods and fairness

- `greedy`: a strong baseline consisting of repeated dynamic DSatur/MRV
  constructions and a feasible non-dominated archive. The first construction
  uses deterministic choices and subsequent attempts are randomized.
- `nsga2`: standard constrained NSGA-II with domain-valid random chromosomes,
  whole-offering crossover, mutation, rank/crowding tournaments, and elitist
  environmental selection.
- `seeded`: NSGA-II with constructive initialization; repair and local search
  are disabled. This is an ablation of the full enhancement.
- `enhanced`: constructive initialization plus feasibility repair and short
  feasible local search.

Every full call to the shared evaluator during search is charged, including
initialization, rejected repair proposals, and local-search proposals. Greedy
construction uses resource checks internally, with one full evaluation per
completed attempt. Equal evaluation budgets are therefore not equal CPU work.
Wall-clock runtime is reported alongside quality and includes constructive
checks, repair, and local search. It excludes postprocessing, archive
revalidation, JSON serialization, and plotting. Methods run sequentially, with
a deterministic rotation of method order across solver seeds. Timings still
depend on machine load and hardware.

Certificates are stored separately and never used to initialize any method.
Failure to find a feasible timetable on a planted instance is a solver failure.
For arbitrary input, heuristic failure does not establish infeasibility.
CP-SAT is a separate small-instance reference rather than a method included in
these evaluation-capped stochastic comparisons.

## Configuration API

```json
{
  "name": "my_study",
  "population_size": 24,
  "instance_seeds": [10, 20],
  "solver_seeds": [0, 1, 2],
  "methods": ["greedy", "nsga2", "seeded", "enhanced"],
  "scenarios": [
    {"size": "small", "budget": 480},
    {"size": "medium", "budget": 240, "population_size": 12,
     "generator": {"unavailability_rate": 0.12}}
  ]
}
```

Scenario values override top-level `instance_seeds`, `solver_seeds`, and
`population_size`. `size` selects `small`, `medium`, or `large`. `generator` is
an optional dictionary of the dataset overrides documented in `data/README.md`.
NSGA-II budgets must be at least the population size, which must be at least 2.
Methods and seeds must be unique. A study cannot repeat the same
`(size, instance_seed)` pair across scenarios because those pairs identify saved
instances and runs. Use a different study name when varying generator settings,
budgets, or operator configurations for the same seed.

## Saved evidence and resumption

Each study creates:

- `results/STUDY/manifest.json`: exact configuration and SHA-256 fingerprint,
  source hashes, Python/platform/library versions, and budget/timing protocols;
- `data/STUDY/`: generated problem JSON and separate certificates;
- `results/STUDY/runs/`: one atomic JSON checkpoint per instance/method/seed,
  including objective vectors, complete schedule archives, feasibility
  diagnostics, convergence history, runtime, and instance hash;
- `results/STUDY/runs.csv`, `summary.json`, and `summary.md`: comparison tables,
  paired statistics, and empirical trade-off diagnostics;
- `figures/STUDY/`: Pareto projections/3D views, convergence curves, and method
  comparisons generated from the saved raw results.

`--resume` preserves completed run records and the original manifest. It rejects
changed configuration, source, Python, tracked library versions, or platform.
Cached run identity, budget, and instance hash are checked, and cached archives
are independently evaluated against the regenerated instance and their saved
objective vectors. Incomplete `.tmp` checkpoints are not counted as finished
runs. If code or configuration changes, select a new study name; do not splice
measurements from different implementations into one study.

## Indicators and interpretation

Only feasible objective vectors enter archives and indicators. Empty archives
have hypervolume zero and are retained in all-run comparisons. Objective bounds
are fixed from the problem before search: a conservative participant/day gap
bound, room waste bound 1, and relative-workload standard deviation bound 0.5.
Hypervolume is an exact three-dimensional union of boxes in normalized
minimization space with fixed reference `(1.1, 1.1, 1.1)`. It is not a sampled
estimate or a manufactured front.

The summary reports feasible-run count, feasible-evaluation fraction,
hypervolume, runtime, archive size, and objective summaries. Objective-wise
minima can belong to different schedules. Spacing is undefined for fewer than
two distinct vectors and is not evidence of front coverage by itself. Reported
quality fronts are empirical non-dominated archives; global Pareto optimality is
claimed for the exhaustive tiny examples and the independently certified ideal vectors of the three checked small college instances. Generate the tiny examples with:

```bash
python main.py prove-tradeoffs --output results/exact_micro --figures figures/exact_micro
```

Paired comparisons match the same instance and solver seed. Run-level
superiority/sign counts are descriptive; independent-instance mean comparisons
are supplied separately because solver runs within one instance are clustered.
Few independent instances give low statistical power. Coverage is asymmetric. The optional aggregate coverage fields currently use zero for undefined empty-target cases; direct `metrics.coverage` returns `None`. Do not interpret those aggregate zero values as evidence of dominance, and exclude them from substantive conclusions when a target archive is empty.
Pooled objective ranges and opposing-pair counts describe observed trade-offs
within each instance, not universal conflict or globally optimal alternatives.
Neither the protocol nor the documentation assumes NSGA-II must beat the
baseline; feasibility failures and baseline wins are valid findings.

For fresh historical-method measurements, copy `benchmark.json`, change its `name`, and run `python main.py experiment --config YOUR_CONFIG.json`; the root README includes exact commands. Resume only a newly named study with matching source/runtime.

For the bounded benchmark, run `python experiments/certify_small_ideal.py` to verify the exact small-instance ideal certificates; the complete integer/rational proof is in formulation Section5.1. `python experiments/write_report.py` generates `report/historical_benchmark_report.md` after `verification.json` records PASS. It does not overwrite the consolidated final report. Build the final printable report with `python report/build_report.py` (optional Pandoc/XeLaTeX dependencies).

## Feasible-domain follow-up

`enhancement_validation.json` declares the held-out comparison of unchanged multi-start greedy, original enhanced NSGA-II, feasible memetic NSGA-II, and a matched scalar-local ablation. It uses separate evaluation and wall-allocation protocols, source snapshots and per-evaluation completion timestamps. All late results are excluded from cutoff quality and bounded overruns are recorded. The development configuration is separate; its existence does not mean every planned development run was executed.

```bash
python main.py compare --config experiments/enhancement_validation.json --resume
python experiments/verify_enhancement.py --study enhancement_validation
python experiments/plot_enhancement.py --study enhancement_validation
python experiments/export_enhancement.py --study enhancement_validation
python experiments/report_enhancement.py --study enhancement_validation
```

For fresh measurements, copy the configuration and change `name` before running `compare`. The common observer retains genotype hashes, feasible-evaluation counts, raw objectives, duplicates and actual elapsed prefixes; it includes native search bookkeeping and initialization in runtime. The comparison clears constructor caches and rotates method order. The scalar-local comparator shares the initial construction prefix but later random streams/states diverge. It removes the NSGA-II selection/survival bundle, not one isolated component.

Full methodology is in `docs/enhancement_study.md`; operator invariants and workload mathematics are in `docs/feasible_variation.md`. The measured follow-up report is generated only after complete-run verification. Original datasets, benchmarks and the original model/indicator/algorithm implementation files are preserved.

# Final implementation and release summary

The project provides a working optimization system, checked synthetic datasets, reproducible measurements, timetable exports and academic documentation. The recommended method for the evaluated medium/large cases is **feasible-domain memetic NSGA-II (`memetic`)**. Repeated greedy remains a strong baseline and a sensible choice for the small cases. All college data are synthetic; larger heuristic archives are discovered non-dominated sets, not certified global Pareto fronts.

The attached references are retained under `problem/references/`. [Reference review](reference_review.md) documents corrections to the proposal and the professor's requirements. Publication to the main branch is authorized; no student identities, approval, contribution history or eight-week development record are invented.

## Implemented system

The repository contains **19 Python package modules and 16 test modules**. The implementation includes:

- A typed, versioned problem/schedule schema and configurable generators for exactly 40, 150 and 400 events. Separate feasible certificates establish that the generated instances can be scheduled; certificates are excluded from optimizer inputs.
- Whole-offering faculty assignments and an independent-from-search checker for required sessions, qualifications, room/faculty/student clashes, capacity/type, full-block availability, lunch/day boundaries, daily/weekly limits and distinct-day rules. Multi-period laboratories occupy every required period.
- Three minimization objectives: student gaps plus half the faculty gaps, duration-weighted unused seat fraction, and population SD of relative faculty teaching loads. Eligible faculty choices make workload balance a genuine decision.
- A DSatur-style constructor, strong repeated-greedy baseline, standard constrained NSGA-II, initialization-only ablation and the original repair/local-search enhancement.
- The recommended feasible-domain method: feasible initialization, resource-checked mutation, bounded batch faculty reassignment, rank/crowding tournaments and elitist NSGA-II survival. It deliberately omits crossover. A matched scalar-local ablation tests the selection/survival bundle.
- Exact CP-SAT scalar references, exhaustive micro-instance Pareto fronts, and integer/rational small-instance ideal certificates. Batch faculty search minimizes squared loads within a selected fixed-time neighborhood when weekly limits match, subject to a branch-node cap. It certifies the neighborhood optimum only if the search completes or attains a valid lower bound; a node-limited incumbent has no optimality guarantee. Unequal weekly limits produce an explicit no-op.
- Fixed-scale exact 3-D hypervolume, convergence and feasibility traces, paired comparisons, CSV/JSON event tables, Markdown grids, per-group/faculty/room CSV grids, representative timetables and generated scientific figures.

All full search evaluations are charged. Partial resource checks and branch-and-bound scores are disclosed and timed. Equal-time comparisons use actual completed-candidate timestamps and exclude late results from cutoff quality.

## Verified evidence

**201 automated tests passed in the release check**; the log is `results/release_verification/pytest.txt`. Tests cover hand-calculated objectives, hard constraints and edge cases, all instance sizes, assignment consistency, genuine workload variation, deterministic seeds, serialization, Pareto sorting/crowding, independent hypervolume checks, exact references, evaluator charging, feasible operators, bounded faculty search, cutoff timing and resumption integrity.

| Study | Completed runs | Charged search evaluations | Revalidated archived timetables |
|---|---:|---:|---:|
| Historical benchmark | 192 | 109,440 | 769 |
| Held-out enhancement validation | 168 | 76,086 | 3,295 |

The release verification rechecked both studies and their separate instance certificates. Historical datasets, measurements and figures remain unchanged. The **19 current source files match the enhancement study's frozen snapshot**. Manifests preserve configuration, source hashes, dependency versions and timing conventions. These checks use the shared constraint checker outside search; they are not described as a second independently written checker. Hand-derived cases and CP-SAT provide additional checks.

## Measured conclusions

The original enhancement was faster than repeated greedy but had lower mean hypervolume. The follow-up addresses feasibility destruction using a separate, frozen validation study rather than replacing those unfavorable records.

| Held-out condition | Greedy mean HV | Memetic mean HV | Relative improvement |
|---|---:|---:|---:|
| Medium, equal evaluations | 1.008330 | 1.056105 | +4.74% |
| Medium, equal wall time | 0.988710 | 1.060477 | +7.26% |
| Large, equal evaluations | 0.940824 | 0.977304 | +3.88% |
| Large, equal wall time | 0.930485 | 1.013967 | +8.97% |

The new method won all nine paired runs in each of these four conditions. This supports higher measured HV on the declared held-out synthetic medium/large instances. It does not establish global optimality, improvement of every objective, or effectiveness on real college data. Only three independent instances per primary size limit generalization.

Small-case results are mixed: mean HV changed by **−0.48% at equal evaluations** and **+0.05% at equal wall time**. The scalar-local ablation is competitive, so no consistent isolated advantage of NSGA-II selection is established. Faculty reassignment can improve workload balance while worsening gaps; all feasible proposals are assessed through the common archive.

The three original small instances have certified singleton ideal vectors `(0, 14/55, sqrt(1/450))`; an additional certificate covers held-out small_1010. An algorithm cannot improve beyond an attained ideal vector. Exhaustive micro-instances separately demonstrate genuine objective conflicts. Other medium/large fronts remain empirical.

## Reproduce

Run from the repository root after installing the pinned dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install -e . --no-deps
python -m pytest -q
python main.py generate --size small --seed 42 --output data/demo.json
python main.py solve data/demo.json --method memetic --seed 0 --budget 240 --population 24 --search-seconds 6 --output results/memetic_demo --figures figures/memetic_demo
python main.py evaluate data/demo.json results/memetic_demo/timetables/normalized_compromise/schedule.json
python experiments/verify_saved_results.py --study benchmark
python experiments/verify_enhancement.py --study enhancement_validation
```

To collect **fresh measurements** without altering the supplied studies, create a newly named configuration:

```bash
mkdir -p work
python - <<'PY'
import json
from pathlib import Path
config = json.loads(Path('experiments/enhancement_validation.json').read_text())
config['name'] = 'enhancement_reproduction'
Path('work/enhancement_reproduction.json').write_text(json.dumps(config, indent=2))
PY
python main.py compare --config work/enhancement_reproduction.json
python experiments/verify_enhancement.py --study enhancement_reproduction
```

Use `--resume` only for matching source/configuration/runtime records. Wall-time trajectories depend on hardware and load. See [experiment instructions](../experiments/README.md), [frozen study protocol](enhancement_study.md) and [operator invariants](feasible_variation.md).

## Deliverables and remaining limits

Source and tests are under `src/timetable/` and `tests/`; configurations and analysis scripts are under `experiments/`. Data/certificates, measured results and plots are under `data/`, `results/` and `figures/`. [File inventory](file_inventory.txt) lists the release files. The academic package includes the [final report source](../report/report.md), [measured enhancement report](../report/enhancement_report.md), report PDF and presentation deck. The [presentation guide](../presentation/README.md) identifies the slides, demo and viva material. PDF rebuilding uses `python report/build_report.py` with optional Pandoc/XeLaTeX documentation tools.

The model assumes a repeating week, equal periods, fixed demand, disjoint atomic cohorts, one teacher per offering and exact room-kind matching. Default laboratories use whole cohorts. Individual enrollment overlaps, travel, alternating weeks, fixed starts, team teaching, uncertainty and non-teaching workloads are omitted. Planted feasibility conditions the synthetic distribution and can favor constructive scheduling.

The larger 30-seed study is configured but unexecuted. Real-data/ITC validation, systematic disruption/sensitivity studies, separate ablation of every operator, general exact workload optimization, extra metaheuristics and a complex frontend are not claimed. Recommended next work is broader independent-instance and real-data validation, sensitivity to objective scaling/resource pressure, and minimum-disruption rescheduling. Confirmed member/course details, professor approval and authentic participation records remain the group's responsibility.

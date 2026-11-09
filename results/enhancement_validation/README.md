# Completed enhancement validation

This is a separate, frozen held-out follow-up; historical `results/benchmark/` remains unchanged.

- **168 completed runs**, **76,086 search evaluator calls**: four methods, two resource protocols, seven instance seeds across three sizes.
- **3295 archived feasible timetables** and **seven certificates** rechecked. Every saved time prefix was reconstructed. Nine late completed evaluations were excluded; atomic runtime overruns are reported.
- **201 tests passed before source freeze** (`tests_before_validation.txt`). The CLI memetic solve/evaluate flow was also exercised separately as a smoke check.
- `manifest.json`, `freeze_evidence.json`, and `source_snapshot/` identify the exact code/configuration/runtime used. Source still matches the frozen snapshot.
- `runs/` contains full schedule archives, objective vectors, hashes, raw candidate diagnostics and measured completion times. `runs.csv`, `summary.json`, `summary.md` contain aggregate and paired results.
- `verification.json` contains independent archive/prefix checks and integer workload-bound certificates. Attaining workload bounds proves only that objective, not a global joint front.
- `small_ideal_certificates.json` certifies the full ideal vector on new small_1010, attained in one memetic run. The method's small-case mean still trails greedy at equal evaluations; one optimum does not imply reliable attainment.
- `representatives.json` and `timetables/` export fixed-priority whole schedules for first configured medium/large instance and solver seed, under the common wall allocation.
- `development_pilot.json` stores the actual exploratory twelve-run pilot. The separate larger 64-run development configuration was not executed in full; pilot results are not pooled into validation.
- `execution.log` records actual run completion; `reproduction_environment.json` records CPU/platform context. Timings are application-serial and hardware/load dependent.
- `final_check.json` is the prepublication checkpoint: its `new_commit_or_push: false` records that stage, rather than the repository's later publication status. Release checks are recorded separately under `results/release_verification/`.

The new variant wins all 36 paired primary medium/large comparisons against greedy in fixed HV, but does not improve every objective on every timetable. The scalar-local ablation is highly competitive, with no consistent isolated benefit established for NSGA-II selection. Only three independent instances per primary size limit inference.

See `report/enhancement_report.md` and `docs/enhancement_study.md` from the project root. Reproduce with `python main.py compare --config experiments/enhancement_validation.json --resume` only under matching source/runtime; use a newly named config for fresh measurements.

# Exact arithmetic fronts: enhancement_validation

Postprocessing only: raw schedules, source, search histories and timings unchanged.

Exact non-dominance is among saved schedule alternatives, not all possible timetables.

168 runs; 3295 raw feasible archive records; 53 dominated records removed; 3242 canonical records retained.

Maximum absolute per-run HV change: 3.3306690738754696e-16.

| Size | Protocol | Method | Runs | Raw mean HV | Canonical mean HV | Mean canonical archive size |
|---|---|---|---:|---:|---:|---:|
| large | evaluations | ablation_local | 9 | 0.97851752 | 0.97851752 | 26.56 |
| large | evaluations | greedy | 9 | 0.94082358 | 0.94082358 | 24.44 |
| large | evaluations | memetic | 9 | 0.97730424 | 0.97730424 | 33.78 |
| large | evaluations | original_enhanced | 9 | 0.91701410 | 0.91701410 | 5.67 |
| large | wall_time | ablation_local | 9 | 1.01131791 | 1.01131791 | 48.78 |
| large | wall_time | greedy | 9 | 0.93048496 | 0.93048496 | 16.11 |
| large | wall_time | memetic | 9 | 1.01396716 | 1.01396716 | 62.33 |
| large | wall_time | original_enhanced | 9 | 0.91701410 | 0.91701410 | 5.67 |
| medium | evaluations | ablation_local | 9 | 1.05414662 | 1.05414662 | 21.33 |
| medium | evaluations | greedy | 9 | 1.00833048 | 1.00833048 | 14.67 |
| medium | evaluations | memetic | 9 | 1.05610482 | 1.05610482 | 25.33 |
| medium | evaluations | original_enhanced | 9 | 0.97671885 | 0.97671885 | 6.33 |
| medium | wall_time | ablation_local | 9 | 1.06131369 | 1.06131369 | 21.89 |
| medium | wall_time | greedy | 9 | 0.98870983 | 0.98870983 | 8.44 |
| medium | wall_time | memetic | 9 | 1.06047667 | 1.06047667 | 21.00 |
| medium | wall_time | original_enhanced | 9 | 0.97669964 | 0.97669964 | 6.22 |
| small | evaluations | ablation_local | 3 | 0.93023122 | 0.93023122 | 3.00 |
| small | evaluations | greedy | 3 | 0.93474736 | 0.93474736 | 2.67 |
| small | evaluations | memetic | 3 | 0.93029016 | 0.93029016 | 1.00 |
| small | evaluations | original_enhanced | 3 | 0.93424223 | 0.93424223 | 11.33 |
| small | wall_time | ablation_local | 3 | 0.93023557 | 0.93023557 | 2.67 |
| small | wall_time | greedy | 3 | 0.92978088 | 0.92978088 | 3.67 |
| small | wall_time | memetic | 3 | 0.93029016 | 0.93029016 | 1.00 |
| small | wall_time | original_enhanced | 3 | 0.93147114 | 0.93147114 | 9.67 |

# Enhancement comparison: measured synthetic results

Original datasets, objectives, constraints and greedy heuristic are unchanged. Evaluation caps and wall-time allocations are separate protocols. Boundary overshoot is reported; late evaluations receive no quality credit. Observed archives do not certify global Pareto optimality.

| Size | Protocol | Method | Runs | Feasible | HV mean ± SD | Runtime mean (s) | Evaluations mean | Duplicate fraction |
|---|---|---|---:|---:|---:|---:|---:|---:|
| large | evaluations | ablation_local | 9 | 9 | 0.97851752 ± 0.01398441 | 7.961 | 240.0 | 4.0% |
| large | evaluations | greedy | 9 | 9 | 0.94082358 ± 0.00921675 | 51.671 | 240.0 | 0.0% |
| large | evaluations | memetic | 9 | 9 | 0.97730424 ± 0.01298749 | 8.041 | 240.0 | 6.8% |
| large | evaluations | original_enhanced | 9 | 9 | 0.91701410 ± 0.01525706 | 17.030 | 240.0 | 0.8% |
| large | wall_time | ablation_local | 9 | 9 | 1.01131791 ± 0.00528595 | 16.012 | 819.1 | 5.8% |
| large | wall_time | greedy | 9 | 9 | 0.93048496 ± 0.00925737 | 16.099 | 74.8 | 0.0% |
| large | wall_time | memetic | 9 | 9 | 1.01396716 ± 0.00310313 | 16.045 | 800.3 | 9.8% |
| large | wall_time | original_enhanced | 9 | 9 | 0.91701410 ± 0.01525706 | 16.135 | 226.9 | 0.7% |
| medium | evaluations | ablation_local | 9 | 9 | 1.05414662 ± 0.00472294 | 2.970 | 360.0 | 5.0% |
| medium | evaluations | greedy | 9 | 9 | 1.00833048 ± 0.01209177 | 20.215 | 360.0 | 0.0% |
| medium | evaluations | memetic | 9 | 9 | 1.05610482 ± 0.00744808 | 2.928 | 360.0 | 9.4% |
| medium | evaluations | original_enhanced | 9 | 9 | 0.97671885 ± 0.00974009 | 6.490 | 360.0 | 1.1% |
| medium | wall_time | ablation_local | 9 | 9 | 1.06131369 ± 0.00286719 | 6.019 | 974.2 | 9.6% |
| medium | wall_time | greedy | 9 | 9 | 0.98870983 ± 0.01428120 | 6.025 | 106.2 | 0.0% |
| medium | wall_time | memetic | 9 | 9 | 1.06047667 ± 0.00716019 | 6.008 | 948.1 | 12.6% |
| medium | wall_time | original_enhanced | 9 | 9 | 0.97669964 ± 0.00974761 | 6.029 | 328.0 | 1.1% |
| small | evaluations | ablation_local | 3 | 3 | 0.93023122 ± 0.00494575 | 2.034 | 720.0 | 15.4% |
| small | evaluations | greedy | 3 | 3 | 0.93474736 ± 0.00012078 | 8.912 | 720.0 | 0.0% |
| small | evaluations | memetic | 3 | 3 | 0.93029016 ± 0.00502860 | 2.118 | 720.0 | 12.4% |
| small | evaluations | original_enhanced | 3 | 3 | 0.93424223 ± 0.00081212 | 2.738 | 720.0 | 1.4% |
| small | wall_time | ablation_local | 3 | 3 | 0.93023557 ± 0.00495225 | 2.503 | 846.0 | 16.9% |
| small | wall_time | greedy | 3 | 3 | 0.92978088 ± 0.00488955 | 2.508 | 189.0 | 0.0% |
| small | wall_time | memetic | 3 | 3 | 0.93029016 ± 0.00502860 | 2.505 | 805.7 | 12.3% |
| small | wall_time | original_enhanced | 3 | 3 | 0.93147114 ± 0.00551753 | 2.507 | 608.3 | 1.1% |

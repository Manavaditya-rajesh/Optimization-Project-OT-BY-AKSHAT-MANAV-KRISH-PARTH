# Disruption study: minimal-change re-optimisation

36 runs: held-out instances medium_1010, medium_1020, medium_1030, large_1010; 3 disruptions each; solver seeds [0, 1, 2].
Hypervolume uses the project's a-priori normalisation, reference (1.1, 1.1, 1.1), on the disrupted problem.
*Changes* = sessions whose time, room or teacher differs from the published timetable S0. *Broken* = sessions
of S0 that the disruption makes infeasible; it is a lower bound on the changes of any feasible timetable.

## Repair vs re-optimising from scratch

| Disruption | Sessions | Broken (lower bound) | Repair changes | Repair proven minimal | Scratch: fewest changes on its front | Scratch: compromise changes |
|---|---:|---:|---:|---:|---:|---:|
| Teacher absent for a day | 212 | 3.0 | 3.0 | 12/12 | 209.8 | 211.5 |
| Teacher leaves | 212 | 9.8 | 9.8 | 12/12 | 209.8 | 211.6 |
| Classroom closed all week | 212 | 31.5 | 31.5 | 12/12 | 210.2 | 211.7 |

## Stability / quality trade-off (epsilon-constraint)

Mean hypervolume at each change limit (eps = repair changes + offset), and relative to re-optimising from scratch
with the same total evaluations (which ignores S0 and changes most sessions).

**Teacher absent for a day** (repair HV 0.9812; scratch HV 1.0439 with 212 changed sessions at its compromise)

| eps offset | mean HV | HV / scratch HV |
|---:|---:|---:|
| +0 | 0.9883 | 94.7% |
| +2 | 1.0029 | 96.1% |
| +5 | 1.0094 | 96.7% |
| +10 | 1.0152 | 97.3% |
| +20 | 1.0236 | 98.1% |
| +40 | 1.0313 | 98.8% |

Final eps level reaches at least the scratch hypervolume in 2/12 runs; mean 539 evaluations; runtime 16.0s (epsilon, incl. repair) vs 5.8s (scratch).

**Teacher leaves** (repair HV 0.9554; scratch HV 1.0349 with 212 changed sessions at its compromise)

| eps offset | mean HV | HV / scratch HV |
|---:|---:|---:|
| +0 | 0.9572 | 92.5% |
| +2 | 0.9704 | 93.8% |
| +5 | 0.9862 | 95.3% |
| +10 | 1.0013 | 96.8% |
| +20 | 1.0192 | 98.5% |
| +40 | 1.0263 | 99.2% |

Final eps level reaches at least the scratch hypervolume in 1/12 runs; mean 620 evaluations; runtime 11.2s (epsilon, incl. repair) vs 6.3s (scratch).

**Classroom closed all week** (repair HV 0.9397; scratch HV 1.0026 with 212 changed sessions at its compromise)

| eps offset | mean HV | HV / scratch HV |
|---:|---:|---:|
| +0 | 0.9475 | 94.5% |
| +2 | 0.9571 | 95.5% |
| +5 | 0.9646 | 96.2% |
| +10 | 0.9720 | 97.0% |
| +20 | 0.9820 | 98.0% |
| +40 | 0.9882 | 98.6% |

Final eps level reaches at least the scratch hypervolume in 2/12 runs; mean 639 evaluations; runtime 11.2s (epsilon, incl. repair) vs 6.5s (scratch).

Single-study, synthetic held-out instances; hypervolumes are comparable only within the same disrupted problem.
The broken-session lower bound certifies minimality of the repair only where the two numbers are equal.

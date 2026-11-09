# Final audit evidence

This folder records checks of published revision `3ca0514` and the subsequent
reporting corrections. It contains no replacement timed benchmark measurements.

- `clean_pytest.txt`: 201 existing tests passed in a fresh checkout and isolated
  Python environment installed from the pinned requirements.
- `final_pytest.txt`: the complete suite including eight new precision
  regressions passed: 209 tests.
- `dependency_check.txt`: `pip check` found no broken dependencies.
- `cli_summary.json`: arguments and observed exit codes for 38 CLI checks,
  including all sizes/methods, validation, error paths and exact references.
- `saved_results_check.json`: official rechecks of 192 historical and 168
  follow-up runs, archives, certificates and cutoff histories.
- `core_oracle.py` and `core_oracle_results.json`: independently coded
  feasibility/objective checks on 139,072 candidates, exhaustive faculty tests
  and additional two-lunch neighborhood checks. Results include source hashes
  and the audit script hash. Objectives here use ordinary floating-point
  arithmetic; exact rational archive dominance is a separate check.
- `independent_precision_audit.py` and its JSON report: exact arithmetic audit
  of all saved archive candidates, with original run hashes, survivor indices,
  rational objective keys and hypervolume impacts. This was the implementation
  used to discover the precision issue.
- `exact_tool_crosscheck.txt`: production `experiments/exact_fronts.py` agrees
  with the independent audit for all 360 runs; fresh-run/repeated cleanup passed.
- `representative_precision_check.json`: all eight published timetable examples
  remain members of their exact cleaned fronts.

Canonical results are in `results/exact_fronts/benchmark/` and
`results/exact_fronts/enhancement_validation/`. They are separate from raw
search/timing archives. See [the audit report](../../docs/final_audit.md) and
[precision correction](../../docs/numerical_precision.md) for interpretation,
scope and remaining low-priority limitations.

To rerun the independent checks from an installed project root:

```bash
PYTHONPATH=src python results/final_audit/core_oracle.py
python results/final_audit/independent_precision_audit.py --output work/precision_audit.json
```

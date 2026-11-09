# Release verification

These checks verify the delivered project after finalizing the follow-up.
They do not rerun or replace the original timed benchmark measurements.

- `pytest.txt`: all 201 automated tests pass.
- `historical_verification.txt`: 192 historical runs, 769 archived feasible
  schedules and seven separate feasibility certificates rechecked.
- `enhancement_verification.txt`: 168 follow-up runs, 3,295 archived schedules,
  seven certificates, every cutoff front and 42 common initialization groups
  rechecked. Nine late completed evaluations correctly receive no quality credit.
  All 19 package source files still match the measured snapshot.
- `cli.txt`: a separate seed-42 synthetic instance is generated, optimized using
  `--method memetic` at 240 full evaluations, exported and independently checked
  as feasible. Outputs go to ignored `work/`, keeping this smoke test separate
  from benchmark records.
- `historical_report_build.txt`: the original report generator succeeds and
  writes a separate historical report, preserving the reviewed final report.
- `report_build.txt`: the consolidated report PDF builds successfully. The
  19-page PDF was inspected after enabling table and command wrapping; no
  extracted words extend beyond the page safety margin.
- `presentation_demo.txt`: the presentation demo actually generated, solved and
  validated a feasible schedule at 120 full evaluations.
- `presentation.txt`: the finished 21-slide PowerPoint/PDF, embedded notes,
  evidence text and rendered slide boundaries were checked. The presentation
  builder reads saved evidence and runs no optimizers.

Commands run from the project root with the project's existing test environment:

```bash
python -m pytest -q
python experiments/verify_saved_results.py --study benchmark
python experiments/verify_enhancement.py --study enhancement_validation
python main.py generate --size small --seed 42 --output work/release_demo.json --certificate work/release_demo_certificate.json
python main.py solve work/release_demo.json --method memetic --seed 0 --budget 240 --population 24 --output work/release_demo_result --figures work/release_demo_figures
python main.py evaluate work/release_demo.json work/release_demo_result/timetables/normalized_compromise/schedule.json
python experiments/write_report.py
```

The pre-freeze test record and prepublication checkpoint remain unchanged in
`results/enhancement_validation/`; a checkpoint's historical no-push field is
not a statement about subsequent repository publication.

# Final presentation

The finished technical presentation has **21 slides: 18 main slides and 3 backups**.
Suggested duration: 15–18 minutes plus the optional short live demonstration.
It presents the final **mutation-only feasible memetic NSGA-II**, the completed
168-run held-out comparison, all four medium/large gains, unfavorable small
results, the competitive scalar-local ablation, mathematical guarantees, and
complete timetable trade-offs.

- [Editable PowerPoint](college_timetable_optimization.pptx) — includes speaker notes on every slide.
- [Portable PDF slides](college_timetable_optimization.pdf).
- [Complete Markdown slide source](slides.md) — slide separators and speaker comments.
- [Presenter notes](presenter_notes.md) — evidence references and speaking guidance.
- [Rendered contact sheet](preview.png).
- [Build checks](build_checks.json) and [exact evidence values/hashes](evidence.json).

The deck omits unverified personal identities, approval and participation history.
Add authentic cover details only when the group supplies them; no scientific
content or figure needs to be filled in.

## Rebuilding

Opening the supplied PPTX/PDF requires no Python dependencies. To rebuild from
the repository root, use an environment with these optional presentation libraries:

```bash
python -m pip install -r presentation/requirements.txt
python experiments/exact_fronts.py --study enhancement_validation
python presentation/build_presentation.py
```

The build uses python-pptx, Matplotlib and Pillow. PDF conversion requires
LibreOffice (`soffice`) on PATH; previews and checks also require Poppler tools
(`pdfinfo`, `pdftotext`, `pdftoppm`). These were already installed in the cloud
environment. Their use is separate from the core optimizer requirements.
Exact rational front cleanup is mandatory before reporting: floating workload SD
pseudo-ties caused 53 dominated follow-up points to be retained in the raw
archives. The exact reporting fronts retain 3,242 points from 3,295 feasible raw
schedules; raw schedules, frozen code and measured timings remain unchanged.
See [numerical precision](../docs/numerical_precision.md).

The builder reads saved measurements and creates presentation artifacts only;
it never runs an optimizer or changes experimental records.

The shared slide specification is in `build_presentation.py`. It produces the
editable PPTX, matching LibreOffice PDF, complete Markdown and presenter notes.
New presentation charts are derived from saved objective/count/load values;
existing anytime and timetable images are reused with source references.

## Live demonstration

Activate the project's installed Python environment, then run:

```bash
bash presentation/demo.sh
```

This generates small synthetic seed 9002, solves it with the final method using
seed 0, population 12 and 120 full evaluations, and rechecks a representative.
It writes only to ignored `work/presentation_demo/`. The demo illustrates
execution and validation; it is not a fresh benchmark or a promised small-case
win over greedy. Open `work/presentation_demo/run/timetables/normalized_compromise/grids.md`
and `work/presentation_demo/figures/normalized_compromise.png` afterward.

A saved matched example is available without running optimization:

```bash
python main.py evaluate data/enhancement_validation/medium_1010.json results/enhancement_validation/timetables/medium_1010/memetic/balanced_workload/schedule.json
```

## Viva preparation

Every member should explain offering-level teacher consistency, full-block lab
occupancy, hard constraints versus objectives, genuine workload variability,
constraint domination, NSGA-II rank/crowding/survival, fair evaluation/time
accounting, the local-search ablation, empirical versus global Pareto guarantees,
and why improved workload balance may create student/faculty gaps.

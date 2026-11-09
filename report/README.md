# Final report and supporting studies

- [Final report source](report.md) and [printable PDF](final_report.pdf): the
  consolidated submission, in the professor's 19-section order. It presents
  the final memetic method, both studies, mathematical guarantees, observed
  trade-offs and limitations.
- [Enhancement study](enhancement_report.md): detailed results of the completed
  168-run follow-up, including the full comparison and ablation tables.
- [Historical benchmark report](historical_benchmark_report.md): the original
  192-run study. Its unfavorable hypervolume result is retained as evidence
  motivating the enhancement.

Fill actual registered member/course details and authentic contribution records
after the group meeting. The report does not claim approval or weekly history.

To rebuild the PDF from reviewed Markdown:

```bash
python report/build_report.py
```

This optional documentation build requires Pandoc 3.x, XeLaTeX, DejaVu fonts,
and the TeX packages `fvextra` and `xurl`. These are separate from the Python
optimizer dependencies; the ready-built PDF needs none of them. `layout.lua`
sets wrapping table widths and `layout.tex` wraps long commands. The generated
report was checked for page-edge clipping.

`python experiments/write_report.py` regenerates only the historical report.
`python experiments/report_enhancement.py --study enhancement_validation`
regenerates only the detailed follow-up report and its marked README result
block. Neither command overwrites the reviewed consolidated final report.

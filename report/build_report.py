"""Build the final report PDF from its reviewed Markdown source.

Requires Pandoc and XeLaTeX on PATH. These tools are optional documentation
dependencies; the timetable optimizer does not require a TeX installation.
Run from any directory: python report/build_report.py
"""
from pathlib import Path
import shutil
import subprocess


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for command in ("pandoc", "xelatex"):
        if shutil.which(command) is None:
            raise SystemExit(f"Install optional documentation tool: {command}")
    subprocess.run(
        [
            "pandoc", "report/report.md", "--from=gfm+tex_math_dollars",
            "--standalone", "--toc", "--pdf-engine=xelatex",
            "--lua-filter=report/layout.lua",
            "--include-in-header=report/layout.tex",
            "--resource-path=.:report", "--highlight-style=tango",
            "-V", "geometry:margin=20mm", "-V", "fontsize=10pt",
            "-V", "mainfont=DejaVu Serif", "-V", "sansfont=DejaVu Sans",
            "-V", "monofont=DejaVu Sans Mono",
            "-V", "colorlinks=true", "-V", "urlcolor=blue",
            "-V", "linestretch=1.05", "-o", "report/final_report.pdf",
        ],
        cwd=root,
        check=True,
    )
    print(root / "report/final_report.pdf")


if __name__ == "__main__":
    main()

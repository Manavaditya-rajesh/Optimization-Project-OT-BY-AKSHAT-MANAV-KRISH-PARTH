#!/usr/bin/env bash
set -euo pipefail
task_repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$task_repo_dir"
python main.py generate --size small --seed 9002 --output work/presentation_demo/instance.json
python main.py solve work/presentation_demo/instance.json --method memetic --seed 0 --budget 120 --population 12 --output work/presentation_demo/run --figures work/presentation_demo/figures
python main.py evaluate work/presentation_demo/instance.json work/presentation_demo/run/timetables/normalized_compromise/schedule.json

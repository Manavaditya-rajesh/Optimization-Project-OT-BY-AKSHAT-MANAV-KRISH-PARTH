"""Auditable event tables and weekly grids for every resource."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .evaluation import evaluate
from .model import schedule_to_dict


def schedule_rows(problem, schedule) -> list[dict]:
    teachers = {o.id: schedule.teachers[i] for i, o in enumerate(problem.offerings)}
    rows = []
    for event, placement in zip(problem.events, schedule.placements):
        if placement is None:
            continue
        day, period = divmod(placement.start, problem.periods_per_day)
        rows.append({"event": event.id, "offering": event.offering_id,
                     "groups": ";".join(event.groups), "students": event.size,
                     "day": problem.days[day], "start_period": period + 1,
                     "duration": event.duration, "room": placement.room,
                     "faculty": teachers[event.offering_id]})
    return rows


def resource_grid(problem, schedule, resource_kind: str, resource_id: str) -> list[list[str]]:
    if resource_kind not in {"group", "faculty", "room"}:
        raise ValueError("resource_kind must be group, faculty or room")
    grid = [["LUNCH" if p in problem.lunch_periods else "" for p in range(problem.periods_per_day)]
            for _ in problem.days]
    teachers = {o.id: schedule.teachers[i] for i, o in enumerate(problem.offerings)}
    for e, placement in zip(problem.events, schedule.placements):
        if placement is None:
            continue
        teacher = teachers[e.offering_id]
        include = (resource_id in e.groups if resource_kind == "group" else
                   teacher == resource_id if resource_kind == "faculty" else placement.room == resource_id)
        if include:
            day, period = divmod(placement.start, problem.periods_per_day)
            for offset in range(e.duration):
                value = f"{e.offering_id}\n{placement.room} / {teacher}"
                if offset:
                    value = f"{e.offering_id} (cont.)\n{placement.room} / {teacher}"
                grid[day][period + offset] = value
    return grid


def export_schedule(problem, schedule, output: str | Path, label: str = "schedule") -> dict:
    evaluation = evaluate(problem, schedule)
    if not evaluation.feasible:
        raise ValueError(f"Refusing to export an invalid timetable: {evaluation.violations}")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    payload = {"label": label, "objectives": evaluation.objectives,
               "violation": evaluation.violation, "metrics": evaluation.metrics,
               "schedule": schedule_to_dict(schedule)}
    (output / "schedule.json").write_text(json.dumps(payload, indent=2) + "\n")
    rows = schedule_rows(problem, schedule)
    with (output / "events.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["event", "offering", "groups", "students", "day",
                                                   "start_period", "duration", "room", "faculty"])
        writer.writeheader()
        writer.writerows(rows)
    markdown = [f"# {label}", "", f"Objectives (gaps, unused capacity, workload SD): {evaluation.objectives}", ""]
    for kind, entities in [("group", problem.groups), ("faculty", problem.faculty), ("room", problem.rooms)]:
        folder = output / kind
        folder.mkdir(exist_ok=True)
        for entity in entities:
            grid = resource_grid(problem, schedule, kind, entity.id)
            # Resource IDs are data, so filenames are ordinal rather than unsanitized IDs.
            index = list(entities).index(entity)
            with (folder / f"{index:03d}.csv").open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow([f"{kind}: {entity.id}"] + [f"P{p+1}" for p in range(problem.periods_per_day)])
                for day, cells in zip(problem.days, grid):
                    writer.writerow([day] + [cell.replace("\n", " | ") for cell in cells])
            markdown += [f"## {kind.title()} {entity.id}", "",
                         "| Day | " + " | ".join(f"P{p+1}" for p in range(problem.periods_per_day)) + " |",
                         "| " + " | ".join(["---"] * (problem.periods_per_day + 1)) + " |"]
            markdown += ["| " + " | ".join([day] + [c.replace("\n", "<br>") or "—" for c in cells]) + " |"
                         for day, cells in zip(problem.days, grid)]
            markdown.append("")
    (output / "grids.md").write_text("\n".join(markdown) + "\n")
    return payload

"""Disruptions of the published timetable: detection, admin alerts, minimal-change re-optimisation, publishing.

How a disruption is detected (each check compares against the PUBLISHED weekly timetable):
  * availability  a teacher (or the admin) saves blocked periods / a daily maximum that some of the teacher's
                  published lectures violate                                         (hook in PUT /constraints)
  * long leave    leave of at least LONG_LEAVE_DAYS teaching days; shorter leave is handled by the calendar's
                  cover/substitute flow                                              (hook in POST /leaves)
  * reported      the admin reports a teacher leaving, a room closing, or a teacher absent on a weekday
                                                                                     (POST /api/disruptions)
A disruption is recorded only if it actually breaks published sessions; admins are notified with a link to the
Disruptions page.

Re-optimisation runs timetable.disruption (minimal repair + epsilon-constraint NSGA-II) on the published
timetable, with every saved teacher constraint applied. The admin compares options (fewest changes ... better
quality), sees exactly which sessions move, and publishes one; publishing reuses the normal independent check.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from timetable.disruption import (Disruption, apply_disruption, broken_sessions, change_breakdown,
                                  day_slots, epsilon_reoptimize)
from timetable.evaluation import evaluate
from timetable.metrics import hypervolume, normalize, objective_scales

from .bridge import apply_constraints, problem_to_web, schedule_to_solution, solution_to_schedule, web_to_problem
from .campus.db import admin_ids, connect, get_setting, load_published, notify, now, users_for_faculty

router = APIRouter(prefix="/api")
LONG_LEAVE_DAYS = 5
REPORTABLE = ("teacher_absent", "teacher_leaves", "room_closed")

_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _admin():
    from .campus.routes import ADMIN  # late import: routes imports this module's hooks
    return ADMIN


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _published_model(pub: dict):
    problem = web_to_problem(pub["instance"])
    return problem, solution_to_schedule(problem, pub["solution"])


def _name(pub: dict, kind: str, rid: str) -> str:
    inst = pub["instance"]
    pool = inst["rooms"] if kind == "room_closed" else inst["faculty"]
    return next((x.get("name", rid) for x in pool if x["id"] == rid), rid)


def describe(pub: dict, kind: str, rid: str, slots: list[int], note: str = "") -> str:
    who = _name(pub, kind, rid)
    days = pub["instance"]["grid"]["days"]
    P = len(pub["instance"]["grid"]["periods"])
    on_days = sorted({s // P for s in slots})
    when = (" on " + ", ".join(days[d] for d in on_days)) if slots and len(on_days) < len(days) else ""
    text = {"availability": f"{who}'s saved availability conflicts with the published timetable",
            "teacher_absent": f"{who} is unavailable{when or ' all week'}",
            "teacher_leaves": f"{who} is leaving",
            "room_closed": f"{who} is closed{when or ' all week'}"}[kind]
    return text + (f" ({note})" if note else "")


def _disrupted(pub: dict, kind: str, rid: str, slots: list[int], overrides: dict | None):
    """(P, S0, P') for a disruption; ``overrides`` are saved teacher constraints applied on top."""
    problem, s0 = _published_model(pub)
    disrupted = problem if kind == "availability" else apply_disruption(problem, Disruption(kind, rid, tuple(slots)))
    if overrides:
        disrupted, _ = apply_constraints(disrupted, overrides)
    return problem, s0, disrupted


def _broken(pub: dict, kind: str, rid: str, slots: list[int], overrides: dict | None) -> list[int]:
    _, s0, disrupted = _disrupted(pub, kind, rid, slots, overrides)
    return broken_sessions(disrupted, s0)


def _record(con, pub: dict, kind: str, rid: str, slots: list[int], source: str, note: str, by: str, broken: int) -> int:
    """Insert or refresh an open disruption and alert the admins."""
    row = con.execute("SELECT id FROM disruptions WHERE status = 'open' AND kind = ? AND resource = ? AND source = ?",
                      (kind, rid, source)).fetchone()
    if row:
        con.execute("UPDATE disruptions SET slots = ?, note = ?, broken = ?, published_at = ?, result_json = NULL, created_at = ? WHERE id = ?",
                    (json.dumps(slots), note, broken, pub["publishedAt"], now(), row["id"]))
        did = row["id"]
    else:
        cur = con.execute("INSERT INTO disruptions (kind, resource, slots, source, note, broken, status, published_at, created_by, created_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)",
                          (kind, rid, json.dumps(slots), source, note, broken, pub["publishedAt"], by, now()))
        did = cur.lastrowid
    notify(con, admin_ids(con), f"Disruption: {describe(pub, kind, rid, slots, note)}. {broken} published session(s) are affected. "
                                "Review it and re-optimise with minimal changes.", "disruption", "/disruptions")
    return did


def _resolve_open(con, kind: str, rid: str, source: str, reason: str) -> None:
    con.execute("UPDATE disruptions SET status = 'resolved', resolved_at = ?, resolved_by = ? WHERE status = 'open' AND kind = ? AND resource = ? AND source = ?",
                (now(), reason, kind, rid, source))


# ---------------------------------------------------------------------------
# detection hooks (called by api/campus/routes.py; never raise into the original action)
# ---------------------------------------------------------------------------
def on_constraints_saved(faculty_id: str, unavailable: list[int], max_daily: int | None, by: str) -> int:
    """Return how many published sessions the teacher's new availability breaks (0 if none / nothing published)."""
    try:
        with connect() as con:
            pub = load_published(con)
            if not pub or faculty_id not in {f["id"] for f in pub["instance"]["faculty"]}:
                return 0
            override = {faculty_id: {"unavailable": unavailable, "max_daily": max_daily}}
            broken = _broken(pub, "availability", faculty_id, [], override)
            if not broken:
                _resolve_open(con, "availability", faculty_id, "availability", "availability no longer conflicts")
                return 0
            note = f"max {max_daily} per day" if max_daily else ""
            _record(con, pub, "availability", faculty_id, sorted(set(unavailable)), "availability", note, by, len(broken))
            return len(broken)
    except Exception:  # detection must never block saving availability
        traceback.print_exc()
        return 0


def on_leave_added(faculty_id: str, start: date, end: date, by: str) -> dict | None:
    """Long leave (>= LONG_LEAVE_DAYS teaching days) is a disruption of the weekly timetable."""
    try:
        with connect() as con:
            pub = load_published(con)
            if not pub or faculty_id not in {f["id"] for f in pub["instance"]["faculty"]}:
                return None
            sem_start, sem_end = date.fromisoformat(get_setting(con, "semester_start")), date.fromisoformat(get_setting(con, "semester_end"))
            n_days = len(pub["instance"]["grid"]["days"])
            d, teaching = max(start, sem_start), 0
            while d <= min(end, sem_end):
                teaching += d.weekday() < n_days
                d += timedelta(days=1)
            if teaching < LONG_LEAVE_DAYS:
                return None
            broken = _broken(pub, "teacher_absent", faculty_id, [], None)
            if not broken:
                return None
            note = f"leave {start} to {end}, {teaching} teaching days"
            did = _record(con, pub, "teacher_absent", faculty_id, [], "leave", note, by, len(broken))
            return {"id": did, "broken": len(broken)}
    except Exception:
        traceback.print_exc()
        return None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class ReportBody(BaseModel):
    kind: str
    resource: str
    day: int | None = Field(None, ge=0, le=6, description="weekday index; omit for the whole week")
    note: str = ""


class ReoptBody(BaseModel):
    seed: int = 0
    budget: int | None = Field(None, ge=10, le=2000, description="full evaluations per epsilon level")


class ApplyBody(BaseModel):
    option: str


def _row(con, r, pub) -> dict:
    slots = json.loads(r["slots"])
    result = json.loads(r["result_json"]) if r["result_json"] else None
    return {"id": r["id"], "kind": r["kind"], "resource": r["resource"], "slots": slots, "source": r["source"],
            "note": r["note"], "broken": r["broken"], "status": r["status"], "createdAt": r["created_at"],
            "createdBy": r["created_by"], "resolvedAt": r["resolved_at"], "resolvedBy": r["resolved_by"],
            "description": describe(pub, r["kind"], r["resource"], slots, r["note"]) if pub else r["kind"],
            "stale": bool(pub) and r["published_at"] != pub["publishedAt"],
            "hasResult": result is not None,
            "resultStale": bool(result and pub and result.get("basedOn") != pub["publishedAt"])}


@router.get("/disruptions")
def list_disruptions(user=Depends(_admin())):
    with connect() as con:
        pub = load_published(con)
        # An open disruption recorded against an older published timetable is re-assessed against the current one.
        for r in con.execute("SELECT * FROM disruptions WHERE status = 'open'").fetchall():
            if pub and r["published_at"] != pub["publishedAt"]:
                try:
                    overrides = None
                    if r["kind"] == "availability":
                        from .campus.routes import constraint_overrides
                        overrides = {r["resource"]: constraint_overrides().get(r["resource"], {})}
                    n = len(_broken(pub, r["kind"], r["resource"], json.loads(r["slots"]), overrides))
                except ValueError:
                    n = 0
                if n == 0:
                    con.execute("UPDATE disruptions SET status = 'resolved', resolved_at = ?, resolved_by = ? WHERE id = ?",
                                (now(), "no longer affects the published timetable", r["id"]))
                else:
                    con.execute("UPDATE disruptions SET broken = ?, published_at = ?, result_json = NULL WHERE id = ?",
                                (n, pub["publishedAt"], r["id"]))
        rows = con.execute("SELECT * FROM disruptions ORDER BY status = 'open' DESC, id DESC LIMIT 50").fetchall()
        return {"published": bool(pub), "items": [_row(con, r, pub) for r in rows]}


@router.get("/disruptions/{did}")
def get_disruption(did: int, user=Depends(_admin())):
    with connect() as con:
        r = con.execute("SELECT * FROM disruptions WHERE id = ?", (did,)).fetchone()
        if not r:
            raise HTTPException(404, "No such disruption.")
        pub = load_published(con)
        out = _row(con, r, pub)
        out["result"] = json.loads(r["result_json"]) if r["result_json"] else None
        return out


@router.post("/disruptions")
def report_disruption(b: ReportBody, user=Depends(_admin())):
    if b.kind not in REPORTABLE:
        raise HTTPException(400, f"kind must be one of {REPORTABLE}")
    with connect() as con:
        pub = load_published(con)
        if not pub:
            raise HTTPException(409, "Publish a timetable first.")
        P = len(pub["instance"]["grid"]["periods"])
        lunch = pub["instance"]["grid"].get("lunchPeriods") or [pub["instance"]["grid"]["lunchPeriod"]]
        slots = [] if b.day is None else [b.day * P + p for p in range(P) if p not in lunch]
        if b.kind == "teacher_absent" and b.day is not None and b.day >= len(pub["instance"]["grid"]["days"]):
            raise HTTPException(400, "That day is not in the timetable.")
        try:
            broken = _broken(pub, b.kind, b.resource, slots, None)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not broken:
            return {"id": None, "broken": 0, "message": "This does not affect any published session; nothing to re-optimise."}
        did = _record(con, pub, b.kind, b.resource, slots, "reported", b.note, user["username"], len(broken))
        return {"id": did, "broken": len(broken)}


@router.post("/disruptions/{did}/dismiss")
def dismiss(did: int, user=Depends(_admin())):
    with connect() as con:
        n = con.execute("UPDATE disruptions SET status = 'dismissed', resolved_at = ?, resolved_by = ? WHERE id = ? AND status = 'open'",
                        (now(), user["username"], did)).rowcount
    if not n:
        raise HTTPException(404, "No open disruption with that id.")
    return {"ok": True}


def _session_diff(problem, original, candidate, web_instance) -> list[dict]:
    ids = [e["id"] for e in web_instance["events"]]
    offering = {o["id"]: o for o in web_instance["offerings"]}
    k_of = {o.id: k for k, o in enumerate(problem.offerings)}
    P = problem.periods_per_day
    out = []
    for i, event in enumerate(problem.events):
        k = k_of[event.offering_id]
        a, b = original.placements[i], candidate.placements[i]
        ta, tb = original.teachers[k], candidate.teachers[k]
        what = [w for w, changed in (("time", a.start != b.start), ("room", a.room != b.room), ("teacher", ta != tb)) if changed]
        if what:
            o = offering[event.offering_id]
            out.append({"eventId": ids[i], "offeringId": event.offering_id, "code": o.get("code", event.offering_id),
                        "groupIds": o["groupIds"], "what": what,
                        "before": {"day": a.start // P, "period": a.start % P, "roomId": a.room, "facultyId": ta},
                        "after": {"day": b.start // P, "period": b.start % P, "roomId": b.room, "facultyId": tb}})
    return out


def _budget_for(n_events: int) -> int:
    return 120 if n_events <= 200 else 80


def _work(job_id: str, did: int, seed: int, budget: int | None, overrides: dict):
    job = _jobs[job_id]
    try:
        with connect() as con:
            r = con.execute("SELECT * FROM disruptions WHERE id = ?", (did,)).fetchone()
            pub = load_published(con)
        kind, rid, slots = r["kind"], r["resource"], json.loads(r["slots"])
        problem, s0, disrupted = _disrupted(pub, kind, rid, slots, overrides)
        if not evaluate(problem, s0).feasible:
            raise RuntimeError("The published timetable is not feasible for its own instance; re-publish it first.")
        d = Disruption("teacher_absent" if kind == "availability" else kind, rid, tuple(slots))
        budget = budget or _budget_for(len(problem.events))
        started = time.time()

        def progress(info):
            job["progress"] = {**info, "seconds": time.time() - started}

        job["progress"] = {"level": 0, "levels": 1, "evaluations": 0, "budget": budget, "phase": "repair"}
        res = epsilon_reoptimize(disrupted, s0, d, budget=budget, population=12, seed=seed,
                                 original_problem=problem, progress=progress)
        web = problem_to_web(disrupted)
        scales = objective_scales(disrupted)
        options, seen = [], {}
        rep = res.repair

        def add(key, label, schedule, eps, level_hv, front):
            if schedule in seen:
                seen[schedule]["labels"].append(label)
                return
            sol = schedule_to_solution(disrupted, schedule, key.upper(), True)
            opt = {"key": key, "label": label, "labels": [label], "epsilon": eps, "levelHypervolume": level_hv, "frontSize": front,
                   "objectives": sol["objectives"], "changes": change_breakdown(disrupted, s0, schedule),
                   "hypervolume": hypervolume([normalize(evaluate(disrupted, schedule).objectives, scales)]),
                   "solution": sol, "changedSessions": _session_diff(disrupted, s0, schedule, web)}
            seen[schedule] = opt
            options.append(opt)

        add("repair", "Fewest changes (minimal repair)", rep.schedule, rep.changes,
            hypervolume([normalize(evaluate(disrupted, rep.schedule).objectives, scales)]), 1)
        for level in res.levels:
            if level.feasible:
                ci = level.compromise_index()
                add(f"eps-{level.epsilon}", f"At most {level.epsilon} changes", level.archive[ci], level.epsilon,
                    level.hypervolume, len(level.archive))
        result = {
            "basedOn": pub["publishedAt"], "disruptionId": did, "instance": web,
            "description": describe(pub, kind, rid, slots, r["note"]),
            "sessions": len(problem.events), "brokenSessions": len(rep.broken), "lowerBound": rep.lower_bound,
            "provenMinimal": rep.proven_minimal, "repairMethod": rep.method,
            "originalObjectives": dict(zip(("f1", "f2", "f3"), res.original_objectives)),
            "options": options,
            "tradeoff": res.tradeoff,
            "levels": [{"epsilon": lv.epsilon, "feasible": lv.feasible, "hypervolume": lv.hypervolume, "front": len(lv.archive),
                        "evaluations": lv.evaluations} for lv in res.levels],
            "constraintsApplied": sorted(overrides),
            "runtime": time.time() - started, "seed": seed, "budgetPerLevel": budget,
        }
        with connect() as con:
            con.execute("UPDATE disruptions SET result_json = ? WHERE id = ?", (json.dumps(result), did))
        job.update(status="done", result=result)
    except Exception as e:  # report to the client instead of failing silently
        traceback.print_exc()
        job.update(status="error", error=f"{type(e).__name__}: {e}" if not isinstance(e, RuntimeError) else str(e))


@router.post("/disruptions/{did}/reoptimize")
def reoptimize(did: int, b: ReoptBody, user=Depends(_admin())):
    from .campus.routes import constraint_overrides
    with connect() as con:
        r = con.execute("SELECT * FROM disruptions WHERE id = ?", (did,)).fetchone()
        if not r or r["status"] != "open":
            raise HTTPException(404, "No open disruption with that id.")
        if not load_published(con):
            raise HTTPException(409, "Nothing is published.")
    job_id = uuid.uuid4().hex[:10]
    with _lock:
        for k in [k for k, j in _jobs.items() if j["status"] != "running"][:-10]:
            del _jobs[k]
        _jobs[job_id] = {"status": "running", "progress": {"phase": "queued"}, "disruptionId": did}
    _executor.submit(_work, job_id, did, b.seed, b.budget, constraint_overrides())
    return {"jobId": job_id}


@router.get("/disruption-jobs/{job_id}")
def job_status(job_id: str, user=Depends(_admin())):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "No such job.")
    out = {"status": job["status"], "progress": job.get("progress")}
    if job["status"] == "done":
        out["result"] = job["result"]
    if job["status"] == "error":
        out["error"] = job["error"]
    return out


@router.post("/disruptions/{did}/apply")
def apply_option(did: int, b: ApplyBody, user=Depends(_admin())):
    from .campus.routes import publish_timetable, students_of
    with connect() as con:
        r = con.execute("SELECT * FROM disruptions WHERE id = ?", (did,)).fetchone()
        pub = load_published(con)
    if not r or r["status"] != "open" or not r["result_json"]:
        raise HTTPException(404, "Re-optimise this disruption first.")
    result = json.loads(r["result_json"])
    if not pub or result["basedOn"] != pub["publishedAt"]:
        raise HTTPException(409, "The published timetable changed since this was computed. Re-optimise again.")
    option = next((o for o in result["options"] if o["key"] == b.option), None)
    if option is None:
        raise HTTPException(400, "Unknown option.")
    n = option["changes"]["total"]
    publish_timetable(result["instance"], option["solution"], pub.get("design"), user,
                      message=f"The timetable was updated after a disruption ({result['description']}): {n} session(s) changed.")
    with connect() as con:
        con.execute("UPDATE disruptions SET status = 'resolved', resolved_at = ?, resolved_by = ? WHERE id = ?",
                    (now(), f"{user['username']} published '{option['label']}' ({n} changes)", did))
        # Tell each affected teacher and class exactly what moved.
        inst = result["instance"]
        days, periods = inst["grid"]["days"], inst["grid"]["periods"]
        rooms = {x["id"]: x.get("name", x["id"]) for x in inst["rooms"]}
        fac = {x["id"]: x.get("name", x["id"]) for x in pub["instance"]["faculty"]}

        def slot(s):
            return f"{days[s['day']]} {periods[s['period']]}, {rooms.get(s['roomId'], s['roomId'])}, {fac.get(s['facultyId'], s['facultyId'])}"
        per_teacher, per_group = {}, {}
        for c in option["changedSessions"]:
            line = f"{c['code']}: {slot(c['before'])} -> {slot(c['after'])}"
            for t in {c["before"]["facultyId"], c["after"]["facultyId"]}:
                per_teacher.setdefault(t, []).append(line)
            for g in c["groupIds"]:
                per_group.setdefault(g, []).append(line)
        for t, lines in per_teacher.items():
            more = f" (+{len(lines) - 3} more)" if len(lines) > 3 else ""
            notify(con, users_for_faculty(con, t), "Your timetable changed: " + "; ".join(lines[:3]) + more, "change", "/timetable")
        for g, lines in per_group.items():
            more = f" (+{len(lines) - 3} more)" if len(lines) > 3 else ""
            notify(con, students_of(con, [g]), "Your class timetable changed: " + "; ".join(lines[:3]) + more, "change", "/timetable")
    return {"ok": True, "changes": n}

"""Website disruption flow: detect -> alert admin -> minimal-change re-optimisation -> publish -> notify."""
import os
import tempfile
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.bridge import check_web_timetable, demo_problem, problem_to_web, schedule_to_solution
from timetable.greedy import greedy

MONDAY = date(2026, 11, 2)


@pytest.fixture(scope="module")
def env():
    """Own database (other web tests use theirs); restored afterwards."""
    old_db, old_runs = os.environ.get("CLOCKWORK_DB"), os.environ.get("CLOCKWORK_RUNS_DIR")
    tmp = tempfile.mkdtemp()
    os.environ["CLOCKWORK_DB"] = os.path.join(tmp, "disruptions.db")
    os.environ["CLOCKWORK_RUNS_DIR"] = os.path.join(tmp, "runs")
    from api.campus.db import init_db
    from api.server import app
    init_db()
    client = TestClient(app)

    def login(u, p):
        r = client.post("/api/auth/login", json={"username": u, "password": p})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}

    admin = login("admin", "admin")
    prob = demo_problem()
    instance = problem_to_web(prob)
    solution = schedule_to_solution(prob, greedy(prob), "S001", True)
    assert client.post("/api/timetable/publish", json={"instance": instance, "solution": solution}, headers=admin).status_code == 200
    client.put("/api/semester", json={"start": MONDAY.isoformat(), "end": (MONDAY + timedelta(weeks=10)).isoformat()}, headers=admin)
    pw = {u["username"]: u["password"] for u in client.post("/api/users/bulk", headers=admin).json()["created"]}
    yield {"client": client, "admin": admin, "login": login, "pw": pw, "instance": instance, "solution": solution}
    for key, value in (("CLOCKWORK_DB", old_db), ("CLOCKWORK_RUNS_DIR", old_runs)):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def teacher_slots(pub, fid):
    P = len(pub["instance"]["grid"]["periods"])
    ev = {e["id"]: e for e in pub["instance"]["events"]}
    out = set()
    for a in pub["solution"]["assignments"]:
        e = ev[a["eventId"]]
        if pub["solution"]["facultyOf"][e["offeringId"]] == fid:
            out |= {a["day"] * P + a["period"] + k for k in range(e["length"])}
    return out


def run_job(env, did, budget=25):
    c, admin = env["client"], env["admin"]
    r = c.post(f"/api/disruptions/{did}/reoptimize", json={"seed": 0, "budget": budget}, headers=admin)
    assert r.status_code == 200, r.text
    job = r.json()["jobId"]
    for _ in range(600):
        st = c.get(f"/api/disruption-jobs/{job}", headers=admin).json()
        if st["status"] != "running":
            break
        time.sleep(0.05)
    assert st["status"] == "done", st.get("error")
    return st["result"]


def test_availability_conflict_is_detected_and_cleared(env):
    c, admin = env["client"], env["admin"]
    f1 = env["login"]("f1", env["pw"]["f1"])
    pub = c.get("/api/timetable", headers=admin).json()
    used = sorted(teacher_slots(pub, "f1"))[:2]
    r = c.put("/api/constraints/f1", json={"unavailable": used}, headers=f1)
    assert r.status_code == 200 and r.json()["conflicts"] > 0
    items = c.get("/api/disruptions", headers=admin).json()["items"]
    d = next(x for x in items if x["kind"] == "availability" and x["resource"] == "f1" and x["status"] == "open")
    assert d["broken"] == r.json()["conflicts"]
    notes = c.get("/api/notifications", headers=admin).json()["items"]
    assert any(n["message"].startswith("Disruption:") and n["link"] == "/disruptions" for n in notes)
    # a non-conflicting availability resolves it
    free = sorted(set(range(40)) - teacher_slots(pub, "f1") - {4, 12, 20, 28, 36})[:1]
    assert c.put("/api/constraints/f1", json={"unavailable": free}, headers=f1).json()["conflicts"] == 0
    assert c.get(f"/api/disruptions/{d['id']}", headers=admin).json()["status"] == "resolved"
    # only admins see / act on disruptions
    assert c.get("/api/disruptions", headers=f1).status_code == 403


def test_reoptimise_and_publish(env):
    c, admin = env["client"], env["admin"]
    f1 = env["login"]("f1", env["pw"]["f1"])
    pub = c.get("/api/timetable", headers=admin).json()
    blocked = sorted(teacher_slots(pub, "f1"))[:3]
    conflicts = c.put("/api/constraints/f1", json={"unavailable": blocked}, headers=f1).json()["conflicts"]
    d = next(x for x in c.get("/api/disruptions", headers=admin).json()["items"] if x["kind"] == "availability" and x["status"] == "open")
    res = run_job(env, d["id"])
    assert res["brokenSessions"] == conflicts == res["lowerBound"]
    opts = res["options"]
    assert opts[0]["key"] == "repair" and opts[0]["changes"]["total"] >= res["lowerBound"]
    for o in opts:
        ev = check_web_timetable(res["instance"], o["solution"])
        assert ev.feasible
        assert o["changes"]["total"] == len(o["changedSessions"])
        if o["key"] != "repair":
            assert o["changes"]["total"] <= o["epsilon"]
        assert not set(blocked) & {s for s in teacher_slots({"instance": res["instance"], "solution": o["solution"]}, "f1")}
    assert c.get(f"/api/disruptions/{d['id']}", headers=admin).json()["hasResult"]
    # publish the option with the best hypervolume
    best = max(opts, key=lambda o: o["hypervolume"])
    r = c.post(f"/api/disruptions/{d['id']}/apply", json={"option": best["key"]}, headers=admin)
    assert r.status_code == 200, r.text
    new = c.get("/api/timetable", headers=admin).json()
    assert new["solution"]["verified"] and not set(blocked) & teacher_slots(new, "f1")
    assert c.get(f"/api/disruptions/{d['id']}", headers=admin).json()["status"] == "resolved"
    # affected people are told what moved; publishing twice is refused
    if best["changedSessions"]:
        teachers = {s["before"]["facultyId"] for s in best["changedSessions"]} | {s["after"]["facultyId"] for s in best["changedSessions"]}
        t = sorted(teachers)[0]
        th = env["login"](t, env["pw"][t])
        assert any(n["message"].startswith("Your timetable changed") for n in c.get("/api/notifications", headers=th).json()["items"])
        g = best["changedSessions"][0]["groupIds"][0]
        st = env["login"](f"{g.lower()}-student", env["pw"][f"{g.lower()}-student"])
        assert any(n["message"].startswith("Your class timetable changed") for n in c.get("/api/notifications", headers=st).json()["items"])
    assert c.post(f"/api/disruptions/{d['id']}/apply", json={"option": best["key"]}, headers=admin).status_code == 404
    c.put("/api/constraints/f1", json={"unavailable": []}, headers=f1)


def test_long_leave_is_a_disruption_short_leave_is_not(env):
    c = env["client"]
    f2 = env["login"]("f2", env["pw"]["f2"])
    short = c.post("/api/leaves", json={"start": (MONDAY + timedelta(days=14)).isoformat(),
                                        "end": (MONDAY + timedelta(days=15)).isoformat()}, headers=f2).json()
    assert short["disruption"] is None
    long_ = c.post("/api/leaves", json={"start": (MONDAY + timedelta(days=21)).isoformat(),
                                        "end": (MONDAY + timedelta(days=27)).isoformat()}, headers=f2).json()
    assert long_["disruption"] and long_["disruption"]["broken"] > 0
    item = c.get(f"/api/disruptions/{long_['disruption']['id']}", headers=env["admin"]).json()
    assert item["source"] == "leave" and item["kind"] == "teacher_absent"


def test_reported_disruptions_and_dismiss(env):
    c, admin = env["client"], env["admin"]
    pub = c.get("/api/timetable", headers=admin).json()
    busy_room = pub["solution"]["assignments"][0]["roomId"]
    r = c.post("/api/disruptions", json={"kind": "room_closed", "resource": busy_room}, headers=admin).json()
    assert r["id"] and r["broken"] > 0
    assert c.post(f"/api/disruptions/{r['id']}/dismiss", headers=admin).status_code == 200
    assert c.get(f"/api/disruptions/{r['id']}", headers=admin).json()["status"] == "dismissed"
    # teacher leaving: re-optimisation reassigns every course of that teacher
    r = c.post("/api/disruptions", json={"kind": "teacher_leaves", "resource": "f3"}, headers=admin).json()
    res = run_job(env, r["id"])
    for o in res["options"]:
        assert "f3" not in o["solution"]["facultyOf"].values()
        assert "f3" not in {f["id"] for f in res["instance"]["faculty"]}
    # unknown kind / nothing affected
    assert c.post("/api/disruptions", json={"kind": "flood", "resource": "r1"}, headers=admin).status_code == 400
    unused = next(rm["id"] for rm in pub["instance"]["rooms"] if rm["id"] not in {a["roomId"] for a in pub["solution"]["assignments"]}) \
        if any(rm["id"] not in {a["roomId"] for a in pub["solution"]["assignments"]} for rm in pub["instance"]["rooms"]) else None
    if unused:
        assert c.post("/api/disruptions", json={"kind": "room_closed", "resource": unused}, headers=admin).json()["id"] is None

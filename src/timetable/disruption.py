"""Minimal-perturbation re-optimisation after a disruption (epsilon-constraint method).

A timetable ``S0`` has been published. Then a resource fails: a teacher is absent for some periods, a teacher
leaves, or a room closes. The disrupted problem ``P'`` (``apply_disruption``) makes part of ``S0`` infeasible.
We want a feasible timetable for ``P'`` that is good on the project's three objectives *and* changes as little
as possible, because students and staff have already planned around ``S0``.

Stability is measured by the number of changed sessions

    delta(S, S0) = #{ sessions e : start, room or (offering) teacher of e differs between S and S0 },

and the trade-off is solved with the epsilon-constraint method: for an increasing sequence eps_1 < eps_2 < ...

    minimise (f1, f2, f3)(S)   subject to   S feasible for P'   and   delta(S, S0) <= eps.

Every eps gives a Pareto front; together they trace the stability/quality trade-off, i.e. the Pareto set of the
four-objective problem (delta, f1, f2, f3).

Algorithm (this module only *reuses* the existing operators and selection; none of them is modified):

1. ``minimal_repair``: keep every session of S0 that is still valid in P', remove only the broken ones and
   reinsert them with the neighbourhood's bounded backtracking, which prefers original placements. If that
   fails, a "ripple" frees a few sessions of the affected cohorts/teachers, reinserts the broken sessions
   first and then puts the freed sessions back at their original slots where possible. A last fallback is the
   retention-biased constructor ``greedy.construct(preferred=S0)``. The repair gives the smallest eps searched.
2. ``epsilon_reoptimize``: for each eps, an epsilon-constrained NSGA-II. Parents are chosen by the existing
   rank/crowding tournament and survivors by the existing elitist environmental selection. Children come from the
   existing feasibility-preserving neighbourhood plus a new *restore* move that puts changed sessions (or a
   changed offering teacher) back to S0. A child with delta > eps is rejected BEFORE evaluation: the
   epsilon-constraint is a hard constraint and such candidates never enter an archive.
3. Warm start: each level starts from the previous level's archive. Anything feasible for eps_i is feasible for
   eps_{i+1} (the feasible sets are nested), so each level's archive weakly dominates the previous one and its
   hypervolume cannot decrease.

Every complete candidate is checked with the shared independent ``evaluate`` and counted against the per-level
budget. Constraint pre-checks (delta, resource masks) are not full evaluations, exactly as in the memetic method.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
import random
from time import perf_counter
from typing import Sequence

from .evaluation import Evaluation, evaluate
from .feasible import FeasibleNeighborhood, _State
from .greedy import construct
from .metrics import dominates, hypervolume, normalize, objective_scales
from .model import Placement, Problem, Schedule, validate_problem
from .nsga2 import Individual, environmental_selection, rank_and_crowding

KINDS = ("teacher_absent", "teacher_leaves", "room_closed")


# ---------------------------------------------------------------------------
# disruptions
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Disruption:
    """``kind`` is one of KINDS. ``slots`` are flat time indices (day * periods_per_day + period); an empty
    tuple means the whole week for ``teacher_absent`` / ``room_closed``. ``teacher_leaves`` ignores slots."""

    kind: str
    resource: str
    slots: tuple[int, ...] = ()

    def describe(self, problem: Problem | None = None) -> str:
        what = {"teacher_absent": "teacher {r} unavailable", "teacher_leaves": "teacher {r} leaves",
                "room_closed": "room {r} closed"}[self.kind].format(r=self.resource)
        if self.kind == "teacher_leaves" or not self.slots:
            return what + ("" if self.kind == "teacher_leaves" else " all week")
        if problem is not None:
            days = sorted({s // problem.periods_per_day for s in self.slots})
            return f"{what} on {', '.join(problem.days[d] for d in days)} ({len(self.slots)} periods)"
        return f"{what} for {len(self.slots)} periods"


def day_slots(problem: Problem, day: int) -> tuple[int, ...]:
    """Every teaching period (lunch excluded) of one day."""
    if not 0 <= day < len(problem.days):
        raise ValueError(f"day must be in 0..{len(problem.days) - 1}")
    P = problem.periods_per_day
    return tuple(day * P + p for p in range(P) if p not in problem.lunch_periods)


def parse_disruption(problem: Problem, spec: str) -> Disruption:
    """CLI syntax: ``teacher_absent:F03:day=1``, ``teacher_absent:F03:slots=8,9``, ``teacher_leaves:F03``,
    ``room_closed:R02`` (whole week) or ``room_closed:R02:day=0``."""
    parts = spec.split(":")
    if len(parts) < 2 or parts[0] not in KINDS:
        raise ValueError(f"disruption must look like KIND:RESOURCE[:day=D|slots=a,b]; KIND in {KINDS}")
    kind, resource = parts[0], parts[1]
    slots: tuple[int, ...] = ()
    for extra in parts[2:]:
        key, _, value = extra.partition("=")
        if key == "day":
            slots += day_slots(problem, int(value))
        elif key == "slots":
            slots += tuple(int(x) for x in value.split(",") if x)
        else:
            raise ValueError(f"unknown disruption option {extra!r}")
    return Disruption(kind, resource, tuple(sorted(set(slots))))


def apply_disruption(problem: Problem, disruption: Disruption) -> Problem:
    """Return the disrupted problem P'. Offerings keep their order and ids, so schedules stay comparable."""
    kind, rid = disruption.kind, disruption.resource
    if kind not in KINDS:
        raise ValueError(f"unknown disruption kind {kind!r}")
    teaching = tuple(t for t in range(problem.total_periods) if t % problem.periods_per_day not in problem.lunch_periods)
    slots = disruption.slots or teaching
    if any(not 0 <= s < problem.total_periods for s in slots):
        raise ValueError("disruption slots out of range")
    if kind in ("teacher_absent", "teacher_leaves") and rid not in {f.id for f in problem.faculty}:
        raise ValueError(f"unknown teacher {rid!r}")
    if kind == "room_closed" and rid not in {r.id for r in problem.rooms}:
        raise ValueError(f"unknown room {rid!r}")
    if kind == "teacher_absent":
        faculty = tuple(replace(f, unavailable=tuple(sorted(set(f.unavailable) | set(slots)))) if f.id == rid else f
                        for f in problem.faculty)
        new = replace(problem, faculty=faculty)
    elif kind == "room_closed":
        rooms = tuple(replace(r, unavailable=tuple(sorted(set(r.unavailable) | set(slots)))) if r.id == rid else r
                      for r in problem.rooms)
        new = replace(problem, rooms=rooms)
    else:
        offerings = []
        for o in problem.offerings:
            eligible = tuple(f for f in o.eligible_faculty if f != rid)
            if not eligible:
                raise ValueError(f"no eligible teacher would remain for {o.id}")
            offerings.append(replace(o, eligible_faculty=eligible))
        new = replace(problem, faculty=tuple(f for f in problem.faculty if f.id != rid), offerings=tuple(offerings))
    new = replace(new, name=f"{problem.name} | {disruption.describe(problem)}",
                  metadata={**problem.metadata, "disruption": {"kind": kind, "resource": rid, "slots": list(disruption.slots)}})
    validate_problem(new)
    return new


# ---------------------------------------------------------------------------
# stability measure
# ---------------------------------------------------------------------------
def change_breakdown(problem: Problem, original: Schedule, candidate: Schedule) -> dict[str, int]:
    """Changed sessions (``total``) and why: different time, different room, different offering teacher.
    A session can change for several reasons but counts once in ``total``."""
    offering_of = {o.id: k for k, o in enumerate(problem.offerings)}
    out = {"total": 0, "time": 0, "room": 0, "teacher": 0}
    for i, event in enumerate(problem.events):
        k = offering_of[event.offering_id]
        a, b = original.placements[i], candidate.placements[i]
        time = a is None or b is None or a.start != b.start
        room = a is None or b is None or a.room != b.room
        teacher = original.teachers[k] != candidate.teachers[k]
        out["time"] += time
        out["room"] += room
        out["teacher"] += teacher
        out["total"] += time or room or teacher
    return out


def changed_sessions(problem: Problem, original: Schedule, candidate: Schedule) -> int:
    return change_breakdown(problem, original, candidate)["total"]


# ---------------------------------------------------------------------------
# minimal repair
# ---------------------------------------------------------------------------
@dataclass
class RepairResult:
    schedule: Schedule | None
    broken: list[int]
    changes: int | None
    method: str
    runtime: float

    @property
    def lower_bound(self) -> int:
        """Every broken session must change (its time, room or teacher is no longer allowed), so
        delta(S, S0) >= len(broken) for every feasible S. Equality certifies a minimum-change repair."""
        return len(self.broken)

    @property
    def proven_minimal(self) -> bool:
        return self.changes is not None and self.changes == self.lower_bound


def broken_sessions(problem: Problem, original: Schedule) -> list[int]:
    """Indices of sessions of S0 that cannot stay as they are in P' (invalid teacher or blocked resources)."""
    nb = FeasibleNeighborhood(problem)
    state, broken, _ = _keep_valid(nb, problem, original)
    return broken


def _keep_valid(nb: FeasibleNeighborhood, problem: Problem, original: Schedule):
    needs_teacher = {k for k, o in enumerate(problem.offerings)
                     if original.teachers[k] not in nb.faculty or original.teachers[k] not in o.eligible_faculty}
    state = _State(nb, Schedule((None,) * len(problem.events), tuple(original.teachers)))
    broken = []
    for i, placement in enumerate(original.placements):
        if nb.event_offering[i] in needs_teacher or placement is None or not state.add(i, placement):
            broken.append(i)
    return state, broken, needs_teacher


def _teacher_order(nb: FeasibleNeighborhood, state: _State, k: int, rng: random.Random) -> list[str]:
    """Eligible replacement teachers that fit the weekly limit, most balancing first."""
    contact = nb.contacts[k]
    options = []
    for t in nb.problem.offerings[k].eligible_faculty:
        if t in nb.faculty and state.load[t] + contact <= nb.faculty[t].max_weekly:
            loads = dict(state.load)
            loads[t] += contact
            options.append((nb._load_score(loads), rng.random(), t))
    return [t for _, _, t in sorted(options)]


def _place(nb: FeasibleNeighborhood, state: _State, pending: list[int], needs_teacher: set[int],
           original: Schedule, rng: random.Random) -> _State | None:
    """Assign teachers to offerings that lost theirs, then reinsert every pending session."""
    work = state.copy()
    for k in sorted(needs_teacher, key=lambda k: -nb.contacts[k]):
        indices = [i for i in nb.offering_events[k] if work.placements[i] is None]
        for teacher in _teacher_order(nb, work, k, rng):
            trial = work.copy()
            trial.teachers[k] = teacher
            # Keep the original times/rooms if the new teacher can take them; otherwise backtrack.
            kept = [i for i in indices if original.placements[i] is not None and trial.add(i, original.placements[i])]
            rest = [i for i in indices if i not in kept]
            done = nb._reinsert(trial, rest, original, rng) if rest else trial
            if done is not None:
                work = done
                break
        else:
            return None
    remaining = [i for i in pending if work.placements[i] is None]
    if not remaining:
        return work
    return nb._reinsert(work.copy(), remaining, original, rng)


def minimal_repair(problem: Problem, original: Schedule, seed: int = 0, ripple_rounds: int = 6,
                   construct_attempts: int = 12) -> RepairResult:
    """Feasible timetable for P' that keeps as much of S0 as the heuristic can (not a proven minimum)."""
    validate_problem(problem)
    started = perf_counter()
    rng = random.Random(seed)
    nb = FeasibleNeighborhood(problem, max_nodes=600)
    state, broken, needs_teacher = _keep_valid(nb, problem, original)
    if not broken:
        return RepairResult(original, [], 0, "unchanged", perf_counter() - started)

    done = _place(nb, state, broken, needs_teacher, original, rng)
    method = "reinsert"
    if done is None:
        # Ripple: free sessions sharing a cohort or teacher with the broken ones, place the broken sessions
        # first, then put the freed ones back at their original slots wherever they still fit.
        method = "ripple"
        touched_groups = {g for i in broken for g in problem.events[i].groups}
        touched_teachers = {original.teachers[nb.event_offering[i]] for i in broken}
        neighbours = [i for i, p in enumerate(state.placements) if p is not None and
                      (set(problem.events[i].groups) & touched_groups or state.teachers[nb.event_offering[i]] in touched_teachers)]
        for round_ in range(1, ripple_rounds + 1):
            rng.shuffle(neighbours)
            freed = neighbours[: min(len(neighbours), 2 * round_ * len(broken))]
            trial = state.copy()
            for i in freed:
                trial.remove(i)
            placed = _place(nb, trial, broken, needs_teacher, original, rng)
            if placed is None:
                continue
            back = [i for i in freed if not placed.add(i, original.placements[i])]
            done = nb._reinsert(placed, back, original, rng) if back else placed
            if done is not None:
                break
    best = done.schedule() if done is not None else None
    if best is None:
        method = "construct"
        for _ in range(construct_attempts):
            candidate = construct(problem, rng, preferred=original, randomized=True)
            if evaluate(problem, candidate).feasible:
                if best is None or changed_sessions(problem, original, candidate) < changed_sessions(problem, original, best):
                    best = candidate
    if best is not None and not evaluate(problem, best).feasible:  # defensive: the operators only build feasible blocks
        raise AssertionError("repair produced an infeasible timetable")
    changes = changed_sessions(problem, original, best) if best is not None else None
    return RepairResult(best, broken, changes, method if best is not None else "failed", perf_counter() - started)


# ---------------------------------------------------------------------------
# restore move (new operator)
# ---------------------------------------------------------------------------
def restore_move(nb: FeasibleNeighborhood, schedule: Schedule, original: Schedule, rng: random.Random,
                 tries: int = 6) -> Schedule:
    """Move one changed session (or a changed offering's teacher) back to S0, if that is feasible in P'.
    Returns the unchanged schedule when no restoration fits."""
    state = nb._state(schedule)
    changed = [i for i in range(len(nb.events)) if schedule.placements[i] != original.placements[i]
               or schedule.teachers[nb.event_offering[i]] != original.teachers[nb.event_offering[i]]]
    rng.shuffle(changed)
    for i in changed[:tries]:
        k = nb.event_offering[i]
        trial = state.copy()
        if trial.teachers[k] != original.teachers[k]:
            teacher = original.teachers[k]
            if teacher not in nb.faculty or teacher not in nb.problem.offerings[k].eligible_faculty:
                continue
            indices = nb.offering_events[k]
            for j in indices:
                trial.remove(j)
            trial.teachers[k] = teacher
            if all(original.placements[j] is not None and trial.add(j, original.placements[j]) for j in indices):
                return trial.schedule()
            continue
        trial.remove(i)
        if original.placements[i] is not None and trial.add(i, original.placements[i]):
            return trial.schedule()
    return schedule


# ---------------------------------------------------------------------------
# epsilon-constraint search
# ---------------------------------------------------------------------------
@dataclass
class EpsilonLevel:
    epsilon: int
    archive: list[Schedule]
    objectives: list[tuple[float, float, float]]
    changes: list[int]
    evaluations: int
    proposals: int
    rejected_by_epsilon: int
    hypervolume: float
    runtime: float
    feasible: bool

    def compromise_index(self) -> int | None:
        return _compromise(self.objectives) if self.objectives else None


@dataclass
class ReoptimizationResult:
    disruption: Disruption
    repair: RepairResult
    levels: list[EpsilonLevel]
    original_objectives: tuple[float, float, float] | None
    tradeoff: list[dict] = field(default_factory=list)  # non-dominated (delta, f1, f2, f3) over all levels
    metadata: dict = field(default_factory=dict)


def _compromise(values: Sequence[Sequence[float]]) -> int:
    lo = [min(v[j] for v in values) for j in range(3)]
    hi = [max(v[j] for v in values) for j in range(3)]
    def dist(v):
        return math.sqrt(sum(((v[j] - lo[j]) / ((hi[j] - lo[j]) or 1)) ** 2 for j in range(3)))
    return min(range(len(values)), key=lambda i: dist(values[i]))


def default_epsilons(minimum: int, total_sessions: int) -> list[int]:
    """eps grid relative to the repaired timetable's change count, capped at the number of sessions."""
    steps = (0, 2, 5, 10, 20, 40)
    return sorted({min(total_sessions, minimum + s) for s in steps})


def epsilon_reoptimize(problem: Problem, original: Schedule, disruption: Disruption | None = None,
                       epsilons: Sequence[int] | None = None, budget: int = 120, population: int = 12,
                       seed: int = 0, restore_rate: float = 0.3, repair: RepairResult | None = None,
                       original_problem: Problem | None = None, progress=None) -> ReoptimizationResult:
    """Epsilon-constrained NSGA-II on the disrupted problem ``problem`` (P').

    ``budget`` full evaluations per epsilon level; ``population`` individuals per level. ``epsilons`` default to
    ``default_epsilons`` around the repair's change count. ``original_problem`` (P) is only used to report S0's
    objectives before the disruption. ``progress`` (optional) is called with a dict after each generation; it
    only observes and never changes the search.
    """
    validate_problem(problem)
    if budget < 1 or population < 2:
        raise ValueError("budget must be >=1 and population >=2")
    if not 0 <= restore_rate <= 1:
        raise ValueError("restore_rate must be in [0, 1]")
    rng = random.Random(seed)
    repair = repair or minimal_repair(problem, original, seed=seed)
    if repair.schedule is None:
        raise RuntimeError("No feasible repaired timetable was found; the disruption may make the problem "
                           "infeasible (this is not a proof).")
    n_sessions = len(problem.events)
    eps_list = sorted(set(int(e) for e in (epsilons if epsilons is not None else default_epsilons(repair.changes, n_sessions))))
    if any(e < 0 for e in eps_list):
        raise ValueError("epsilons must be non-negative")
    nb = FeasibleNeighborhood(problem)
    scales = objective_scales(problem)

    def delta(s: Schedule) -> int:
        return changed_sessions(problem, original, s)

    levels: list[EpsilonLevel] = []
    carried: list[Schedule] = [repair.schedule]
    report = progress or (lambda _info: None)
    for level_index, eps in enumerate(eps_list):
        started = perf_counter()
        calls = proposals = rejected = 0
        archive: dict[Schedule, tuple[tuple[float, float, float], int]] = {}

        def counted(s: Schedule) -> Individual:
            nonlocal calls
            calls += 1
            ev: Evaluation = evaluate(problem, s)
            if not ev.feasible:  # cannot happen with these operators; kept as an explicit guard
                raise AssertionError("an operator produced an infeasible timetable")
            d = delta(s)
            if not any(old == ev.objectives and dd <= d or dominates(old, ev.objectives) for old, dd in archive.values()):
                for other in [o for o, (obj, dd) in archive.items()
                              if dominates(ev.objectives, obj) or (obj == ev.objectives and d < dd)]:
                    del archive[other]
                archive[s] = (ev.objectives, d)
            return Individual(s, ev)

        seeds = [s for s in dict.fromkeys(carried) if delta(s) <= eps]
        pop: list[Individual] = []
        seen: set[Schedule] = set()
        for s in seeds:
            if calls >= budget or len(pop) >= population:
                break
            pop.append(counted(s))
            seen.add(s)
        # Fill the population with eps-feasible neighbours of the seeds.
        attempts = 0
        while pop and len(pop) < population and calls < budget and attempts < 20 * population:
            attempts += 1
            parent = rng.choice(pop).schedule
            child = restore_move(nb, parent, original, rng) if rng.random() < restore_rate else nb.propose(parent, rng)
            proposals += 1
            if child in seen:
                continue
            if delta(child) > eps:
                rejected += 1
                continue
            seen.add(child)
            pop.append(counted(child))
        stall = 0
        while len(pop) >= 2 and calls < budget and stall < 20 * budget:
            ranks, crowd = rank_and_crowding(pop)
            children: list[Individual] = []
            for _ in range(len(pop)):
                if calls >= budget:
                    break
                a, b = rng.randrange(len(pop)), rng.randrange(len(pop))
                ka, kb = (ranks[a], -crowd[a]), (ranks[b], -crowd[b])
                parent = pop[a if ka < kb or (ka == kb and rng.random() < 0.5) else b].schedule
                child = restore_move(nb, parent, original, rng) if rng.random() < restore_rate else nb.propose(parent, rng)
                proposals += 1
                if child == parent or child in seen:
                    stall += 1
                    continue
                if delta(child) > eps:  # epsilon-constraint: rejected before any evaluation
                    rejected += 1
                    stall += 1
                    continue
                seen.add(child)
                children.append(counted(child))
            if children:
                pop = environmental_selection(pop + children, len(pop), rng)
            report({"level": level_index, "levels": len(eps_list), "epsilon": eps, "evaluations": calls,
                    "budget": budget, "front": len(archive)})
        ordered = sorted(archive.items(), key=lambda item: item[1][0])
        objectives = [v[0] for _, v in ordered]
        levels.append(EpsilonLevel(
            epsilon=eps, archive=[s for s, _ in ordered], objectives=objectives, changes=[v[1] for _, v in ordered],
            evaluations=calls, proposals=proposals, rejected_by_epsilon=rejected,
            hypervolume=hypervolume([normalize(v, scales) for v in objectives]) if objectives else 0.0,
            runtime=perf_counter() - started, feasible=bool(objectives)))
        carried = [s for s, _ in ordered] + carried  # warm start: nested feasible sets

    tradeoff = _tradeoff(levels)
    original_objectives = evaluate(original_problem, original).objectives if original_problem is not None else None
    return ReoptimizationResult(disruption, repair, levels, original_objectives, tradeoff,
                                {"budget_per_level": budget, "population": population, "seed": seed,
                                 "restore_rate": restore_rate, "epsilons": eps_list, "sessions": n_sessions,
                                 "normalization": list(scales), "reference": [1.1, 1.1, 1.1]})


def _tradeoff(levels: list[EpsilonLevel]) -> list[dict]:
    """Non-dominated points of (delta, f1, f2, f3) over every level: the stability/quality Pareto set found."""
    points = {}
    for level in levels:
        for s, obj, d in zip(level.archive, level.objectives, level.changes):
            points[s] = (d, *obj)
    keys = list(points)
    keep = [s for s in keys if not any(dominates(points[o], points[s]) for o in keys if o is not s)]
    unique = {points[s]: s for s in keep}
    return [{"changes": v[0], "objectives": list(v[1:])} for v in sorted(unique)]


def reoptimization_to_dict(problem: Problem, original: Schedule, result: ReoptimizationResult) -> dict:
    """JSON-ready summary (schedules of each level's archive included in the optimizer's own format)."""
    from .model import schedule_to_dict
    rep = result.repair
    levels = []
    for level in result.levels:
        ci = level.compromise_index()
        levels.append({
            "epsilon": level.epsilon, "feasible": level.feasible, "front_size": len(level.archive),
            "hypervolume": level.hypervolume, "evaluations": level.evaluations, "proposals": level.proposals,
            "rejected_by_epsilon": level.rejected_by_epsilon, "runtime": level.runtime,
            "objectives": [list(v) for v in level.objectives], "changes": level.changes,
            "compromise": None if ci is None else {"objectives": list(level.objectives[ci]), "changes": level.changes[ci],
                                                   "breakdown": change_breakdown(problem, original, level.archive[ci])},
            "archive": [schedule_to_dict(s) for s in level.archive],
        })
    return {
        "disruption": {"kind": result.disruption.kind if result.disruption else None,
                       "resource": result.disruption.resource if result.disruption else None,
                       "slots": list(result.disruption.slots) if result.disruption else [],
                       "description": problem.name},
        "original_objectives": list(result.original_objectives) if result.original_objectives else None,
        "repair": {"broken_sessions": len(rep.broken), "changes": rep.changes, "lower_bound": rep.lower_bound,
                   "proven_minimal": rep.proven_minimal, "method": rep.method, "runtime": rep.runtime,
                   "objectives": list(evaluate(problem, rep.schedule).objectives) if rep.schedule else None},
        "levels": levels, "tradeoff": result.tradeoff, "metadata": result.metadata,
    }

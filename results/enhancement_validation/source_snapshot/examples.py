"""Deliberately tiny, exhaustible conflict demonstrations; separate from benchmarks."""
from .model import Faculty, Group, Offering, Problem, Room


def conflict_instance(case: str) -> Problem:
    if case not in {"room", "workload"}:
        raise ValueError("case must be room or workload")
    rooms = ((Room("small", 20, "classroom", (1, 3)), Room("large", 40, "classroom", (0, 2)))
             if case == "room" else (Room("classroom", 20, "classroom"),))
    faculty = ((Faculty("A", 2, 2), Faculty("B", 2, 2)) if case == "room" else
               (Faculty("A", 2, 2, (2, 3)), Faculty("B", 2, 2, (0, 1, 2))))
    return Problem(f"exact_{case}_conflict", ("Monday",), 4, (), (Group("G", 20),), rooms, faculty,
                   tuple(Offering(k, ("G",), ("A", "B"), 1, 1, "classroom") for k in ("S1", "S2")),
                   {"source": "synthetic analytical conflict example; exhaustive proof possible"})

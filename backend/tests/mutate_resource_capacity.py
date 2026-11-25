"""Mutations against ADM-SCH-06's capacity and containment rules. ADR-0018.

**The schema half is `tests/sql/sweep_resource_capacity.py`; this is the behaviour.** What
these prove is that the three numbers stay three -- a space's capacity, how many of a thing
there are, and how many places a class offers -- that an anonymous space requirement is
bounded by the *smallest* candidate rather than the largest, that equipment is counted inside
the space rather than across the club, and that the room which binds is named in the refusal.

**One of them is the slice's own hardest decision.** An anonymous requirement means the
generator may pick any room of that kind, so the ceiling has to be the smallest -- taking the
largest would let a class of fifty be assigned a studio holding twenty, which is the failure
the whole slice exists to prevent. The mutation that swaps `min` for `max` is the one to read.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_resource_capacity
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
CAP = "app/scheduling/capacity.py"
RES = "app/scheduling/resources.py"
SVC = "app/scheduling/service.py"
TESTS = [
    "tests.test_scheduling_domain.CeilingTests",
    "tests.test_scheduling_domain.ResourceFactTests",
    "tests.test_scheduling_api.ResourceCapacityTests",
]

#: **Four of these are proven at the domain layer and could not be proven above it**, which is
#: this build's "the case exists and the layer is wrong" reading of an uncaught mutation.
#: `check_resource`'s three new rules and `check_requirement`'s one each sit behind an
#: equivalent CHECK -- `sch_resources_capacity_is_a_space`, `capacity_sane`,
#: `parent_is_equipment`, `per_attendee_is_anonymous` -- so with the Python guard removed the
#: schema answers and the route still returns 422. No HTTP case can distinguish them, and the
#: schema's own evidence is CHECK 90b. `ResourceFactTests` is where the decision layer is
#: asserted, so that is where these four bite.

MUTATIONS = [
    # ---- the three numbers stay three -------------------------------------------------
    ("a capacity may be stated for anything, so a coach holds ten people",
     RES,
     '        if resource.kind not in SPACE_KINDS:\n'
     '            raise ScheduleError(\n'
     '                f"a capacity is how many people a place holds, and a {resource.kind} is '
     'not "\n'
     '                f"a place")',
     "        if False:\n"
     '            raise ScheduleError("unreachable")'),
    ("a space may hold nobody, which reads as unstated",
     RES,
     '        if resource.capacity < 1:\n'
     '            raise ScheduleError("a space holds at least one person")',
     "        if False:\n"
     '            raise ScheduleError("a space holds at least one person")'),
    ("anything goes inside a space, so a room sits in a room",
     RES,
     '    if resource.parent_resource_id is not None and resource.kind != "equipment":',
     "    if False:"),
    ("a named resource may also be required per attendee",
     RES,
     "    if requirement.per_attendee and requirement.resource_id is not None:",
     "    if False:"),
    # ---- the ceiling -----------------------------------------------------------------
    ("a space stating no capacity binds the class at nothing",
     CAP,
     "        if space.capacity is None:\n            continue",
     "        if False:\n            continue"),
    ("the largest room wins, so a class may exceed the one it is assigned",
     CAP,
     "        if best.places is None or space.capacity < best.places:",
     "        if best.places is None or space.capacity > best.places:"),
    ("a tie names the equipment rather than the room",
     CAP,
     "        if best.places is None or serves < best.places:",
     "        if best.places is None or serves <= best.places:"),
    ("two of a thing each no longer halves the room",
     CAP,
     "        return self.available // self.per_person",
     "        return self.available"),
    ("the ceiling counts overbooking, so the two settings fight",
     CAP,
     "    if limit.places is not None and policy.capacity > limit.places:",
     "    if limit.places is not None and places(policy) > limit.places:"),
    ("the refusal states no figure and no room",
     CAP,
     '        raise ScheduleError(\n'
     '            f"a capacity of {policy.capacity} exceeds {limit.bound_by}, which allows "\n'
     '            f"{limit.places}")',
     '        raise ScheduleError("capacity too high")'),
    # ---- the read the ceiling is built from -------------------------------------------
    ("an anonymous requirement takes the largest candidate",
     SVC,
     "            smallest = min(stated, key=lambda r: int(r[2]))",
     "            smallest = max(stated, key=lambda r: int(r[2]))"),
    ("equipment is counted across the club rather than inside the space",
     SVC,
     "        fewest = min(int(r[1]) for r in counts)",
     "        fewest = sum(int(r[1]) for r in counts)"),
    ("a retired room still bounds a class",
     SVC,
     "            \" WHERE resource_kind = %s AND status = 'active'\"",
     '            " WHERE resource_kind = %s"'),
    ("retired equipment still counts toward the ceiling",
     SVC,
     '"   ON e.parent_resource_id = p.resource_id AND e.resource_kind = %s"\n'
     '            "      AND e.status = \'active\'"',
     '"   ON e.parent_resource_id = p.resource_id AND e.resource_kind = %s"'),
    ("the template write does not consult the ceiling at all",
     SVC,
     "            capacity.check_against_ceiling(parsed_policy, limit)",
     "            pass"),
    # **The second caller, which is what makes the shared function worth having.** ADM-SCH-03
    # types the number and this read is what tells it the ceiling; a figure computed its own
    # way here would be a screen clearing a capacity the write then refuses.
    ("the live check reports no ceiling, so the screen cannot say what the room allows",
     SVC,
     "        limit_places = _ceiling_for(conn, needs, location_id=location_id)",
     "        limit_places = capacity.Ceiling(\n"
     "            places=None, bound_by=None, bound_kind=None)"),
    ("the live check does not say the capacity is over it",
     SVC,
     "            limit_places.places is not None and wanted.capacity > limit_places.places)",
     "            False)"),
]


def digest(path: pathlib.Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    caught: list[str] = []
    uncaught: list[str] = []
    notrun: list[str] = []
    for name, rel, old, new in MUTATIONS:
        path = BACKEND / rel
        original = path.read_text()
        before = digest(path)

        def restore(
            *_: object, path: pathlib.Path = path, original: str = original,
        ) -> None:
            path.write_text(original)
            sys.exit(130)

        handlers = {
            sig: signal.signal(sig, restore)
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        }
        try:
            if original.count(old) != 1:
                notrun.append(f"{name}: anchor appears {original.count(old)} times")
                continue
            path.write_text(original.replace(old, new))
            if digest(path) == before:
                notrun.append(f"{name}: the file did not change")
                continue
            run = subprocess.run(
                [str(BACKEND.parent / ".venv/bin/python3"), "-B", "-m", "unittest", *TESTS],
                cwd=BACKEND, capture_output=True, text=True,
                env={**os.environ, "VEYRO_SCRYPT_COST_LOG2": "10",
                     "VEYRO_ENV": "local", "VEYRO_RELEASE": "dev"},
            )
            if run.returncode == 0:
                uncaught.append(name)
                print(f"UNCAUGHT  {name}")
            else:
                caught.append(name)
                print(f"CAUGHT    {name}")
        finally:
            path.write_text(original)
            for sig, prior in handlers.items():
                signal.signal(sig, prior)

    print(f"\n{len(caught)}/{len(MUTATIONS)} caught, {len(notrun)} not run")
    for line in notrun:
        print(f"NOT RUN   {line}")
    for line in uncaught:
        print(f"UNCAUGHT  {line}")
    return 0 if len(caught) == len(MUTATIONS) and not notrun else 1


if __name__ == "__main__":
    raise SystemExit(main())

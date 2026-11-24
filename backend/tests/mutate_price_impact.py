"""Mutations against ADM-MSH-09's blast radius, one protection at a time.

What these prove is that the two halves add up to the total, that a rolling member is not lost
between them, that the count follows the supersession chain rather than the immutable root,
that a membership which has ended is not reached, and that the earliest-move date is about the
members who actually move.

**The canvas's own note is the requirement**: "the affected count is computed before the change
is saved, not reported after. A price rise is the most consequential action in Admin and the
only one where the blast radius is stated in members rather than currency."

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_price_impact
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MEM = "app/commercial/service.py"
TESTS = ["tests.test_commercial_api.PriceImpactTests"]

MUTATIONS = [
    # **`minimum_term_ends_on` is nullable and `NULL > date` is NULL.** Without the explicit
    # null test a rolling member falls out of the committed count *and* out of the moving one,
    # so the two halves stop adding up -- which is the one property a reader checks.
    ("a rolling member is counted as committed",
     MEM,
     '            "        count(*) FILTER ("\n'
     '            "          WHERE a.minimum_term_ends_on IS NOT NULL"\n'
     '            "            AND a.minimum_term_ends_on > %s),"',
     '            "        count(*) FILTER ("\n'
     '            "          WHERE a.minimum_term_ends_on IS NULL"\n'
     '            "            OR a.minimum_term_ends_on > %s),"'),
    # A member whose term has run out moves at renewal like any other.
    ("a served term still counts as a commitment",
     MEM,
     '            "            AND a.minimum_term_ends_on > %s),"\n'
     '            "        min(m.current_period_end) FILTER ("',
     '            "            AND a.minimum_term_ends_on IS NOT NULL),"\n'
     '            "        min(m.current_period_end) FILTER ("'),
    # **The date is about the members who move.** A commitment running to next March is not
    # when somebody starts paying more, and a `min` over everybody reports it as though it were.
    ("the earliest move is taken over everybody, committed or not",
     MEM,
     '            "        min(m.current_period_end) FILTER ("\n'
     '            "          WHERE a.minimum_term_ends_on IS NULL"\n'
     '            "             OR a.minimum_term_ends_on <= %s),"',
     '            "        min(m.current_period_end) FILTER ("\n'
     '            "          WHERE %s IS NOT NULL),"'),
    # **The root is immutable by grant**, so after an upgrade it names the plan the member
    # moved off -- and a count joined to it attributes them to the plan they left while the
    # one they are on reads zero.
    ("the count joins the root agreement rather than the chain's live end",
     MEM,
     '            "   JOIN plt01.mem_agreements a ON a.agreement_id = l.agreement_id"\n'
     '            "  WHERE a.variant_id = %s",',
     '            "   JOIN plt01.mem_agreements a ON a.agreement_id = m.agreement_id"\n'
     '            "  WHERE a.variant_id = %s",'),
    # Live by the dates rather than the cached status, which is MOD-022's rule for a door: a
    # membership that has run out is not somebody a price rise reaches.
    # **Well-formed, which the first version was not.** It named `_ANY_MEMBERSHIP`, which does
    # not exist -- so the suite failed with a `NameError` and the mutation was "caught" for a
    # reason that had nothing to do with the count. This repository records three distinct
    # forms of that trap; this is a fourth. The replacement keeps both placeholders and admits
    # every membership, which is the thing the live predicate is there to stop.
    ("a membership that has ended is counted",
     MEM,
     '            f"WITH RECURSIVE {_walk_from(_LIVE_MEMBERSHIP)}"\n'
     '            " SELECT count(*),"',
     '            f"WITH RECURSIVE {_walk_from("\n'
     '                             "m.starts_on <= %s AND %s IS NOT NULL")}"\n'
     '            " SELECT count(*),"'),
    # The two halves are derived from one query, so a surface cannot be handed a pair that
    # does not add up.
    ("the moving half is counted separately rather than derived",
     MEM,
     '        "move_at_renewal": on_this_plan - committed,',
     '        "move_at_renewal": on_this_plan,'),
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
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        try:
            if original.count(old) != 1:
                notrun.append(f"{name}: anchor appears {original.count(old)} times")
                continue
            path.write_text(original.replace(old, new, 1))
            if digest(path) == before:
                notrun.append(f"{name}: file unchanged")
                continue
            run = subprocess.run(
                ["../.venv/bin/python3", "-B", "-m", "unittest", *TESTS],
                cwd=BACKEND, capture_output=True, text=True, env=os.environ.copy())
            (caught if run.returncode != 0 else uncaught).append(name)
        finally:
            path.write_text(original)
            assert digest(path) == before, f"{rel} not restored"
            for sig, previous in handlers.items():
                signal.signal(sig, previous)

    for name in caught:
        print(f"CAUGHT    {name}")
    for name in uncaught:
        print(f"UNCAUGHT  {name}")
    for name in notrun:
        print(f"NOT RUN   {name}")
    print(f"\n{len(caught)}/{len(MUTATIONS)} caught, {len(notrun)} not run")
    return 0 if not uncaught and not notrun else 1


if __name__ == "__main__":
    sys.exit(main())

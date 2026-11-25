"""Mutations against ADM-SCH-07's decisions, one protection at a time. ADR-0016.

**The schema half is `tests/sql/sweep_cancellation_remedy.py`; this is the behaviour.** What
these prove is that the allocation is in booking order, that a member already on the
replacement class is reported rather than refusing the whole cancellation, that the destination
is asked about the *member* rather than about its own fullness, that the waitlist is settled
before the places go back, and that a retry answers from what was recorded.

**One of them reproduces a real defect.** `_candidates_on` read the eligibility verdict's
`eligible` key, which folds in the room being full and the booking window being shut -- so
every member of a full destination came back `ineligible` and `free_places` was decoration.
`check_eligibility_on` carries `ineligible` as its own key for exactly that reason, and its
comment says so.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_cancellation_remedy
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
DEC = "app/booking/cancellation.py"
SVC = "app/booking/service.py"
TESTS = [
    "tests.test_booking_api.CancellationRemedyApiTests",
    "tests.test_booking_domain.CancellationRemedyTests",
]

MUTATIONS = [
    # ---- the allocation -------------------------------------------------------------
    # **The canvas's own arithmetic.** With the counter never decremented, a class with six
    # places takes all eighteen -- and MOD-019's hold is what would then refuse, in the middle
    # of a transaction that has already cancelled the class.
    ("the free places never run out",
     DEC,
     "        left -= 1\n        placements.append(Placement(",
     "        placements.append(Placement("),
    ("a full class still takes everybody",
     DEC,
     "        if left <= 0:\n",
     "        if False:\n"),
    # **D4's order.** Reversed, the last member to book takes the place the first was owed,
    # which is the waitlist's position rule inverted.
    ("the latest bookings take the places",
     DEC,
     "    for candidate in candidates:\n        if candidate.already_there:",
     "    for candidate in reversed(candidates):\n        if candidate.already_there:"),
    # **D5.** A member who booked both classes is the ordinary case: counted against the free
    # places they shorten the list for everybody behind them on the strength of a place
    # nobody took, and moved they are refused by `bkg_bookings_one_live_per_person` -- which
    # would fail the whole cancellation.
    ("a member already on the replacement class is moved again",
     DEC,
     "        if candidate.already_there:\n",
     "        if False:\n"),
    ("a member the replacement class refuses is moved anyway",
     DEC,
     "        if not candidate.eligible:\n",
     "        if False:\n"),
    # ---- the credit ------------------------------------------------------------------
    ("a credit lasts twice as long as the canvas says",
     DEC,
     "CREDIT_DAYS = 30",
     "CREDIT_DAYS = 60"),
    # ---- the remedy itself -----------------------------------------------------------
    ("a move need not name a class",
     DEC,
     '        if self.kind == "move" and not self.to_session_id:\n'
     '            raise CancellationError("a move names the class they are moved to")',
     '        if False:\n'
     '            raise CancellationError("a move names the class they are moved to")'),
    ("a credit may name a class as well",
     DEC,
     '        if self.kind == "credit" and self.to_session_id:\n'
     '            raise CancellationError("a credit is not a move to another class")',
     '        if False:\n'
     '            raise CancellationError("a credit is not a move to another class")'),
    # ---- the destination -------------------------------------------------------------
    # **The real defect, reproduced.** `eligible` folds in the room being full, so every
    # member of a full destination reads as ineligible and the shortfall is reported as a
    # refusal of each member rather than of the class.
    ("the destination is asked whether it is full rather than about the member",
     SVC,
     "        refused = verdict.get(\"ineligible\")\n"
     "        out.append(cancellation.Candidate(\n"
     "            str(row[0]), person_id, eligible=refused is None,\n"
     "            ineligible_because=refused))",
     "        out.append(cancellation.Candidate(\n"
     "            str(row[0]), person_id, eligible=bool(verdict[\"eligible\"]),\n"
     "            ineligible_because=verdict.get(\"ineligible\")))"),
    ("nobody is read as already being on the replacement class",
     SVC,
     '    there = {\n        str(r[0]) for r in conn.execute(\n'
     '            "SELECT person_id FROM plt01.bkg_bookings"\n'
     '            " WHERE session_id = %s AND state IN (\'booked\', \'attended\')",\n'
     '            (to_session_id,),\n        ).fetchall()}',
     '    there: set[str] = set()'),
    ("the candidates come back in whatever order the planner chooses",
     SVC,
     '        " WHERE session_id = %s AND state = \'booked\' ORDER BY booked_at",\n'
     '        (session_id,),\n    ).fetchall()\n    if to_session_id is None:',
     '        " WHERE session_id = %s AND state = \'booked\' ORDER BY booked_at DESC",\n'
     '        (session_id,),\n    ).fetchall()\n    if to_session_id is None:'),
    ("a cancelled class may be the replacement",
     SVC,
     '    if there["status"] != "scheduled":\n'
     '        raise Conflict(f"the_replacement_class_is_{there[\'status\']}")',
     '    if False:\n'
     '        raise Conflict(f"the_replacement_class_is_{there[\'status\']}")'),
    ("a class may be moved to itself",
     SVC,
     '    if to_session_id == session_id:\n'
     '        raise InvalidRequest("a_class_cannot_be_moved_to_itself")',
     '    if False:\n'
     '        raise InvalidRequest("a_class_cannot_be_moved_to_itself")'),
    # ---- the credit policy -----------------------------------------------------------
    ("a tenant with no class credit is credited anyway",
     SVC,
     '    if not rows:\n'
     '        raise Conflict("this_tenant_has_declared_no_class_credit_entitlement")',
     '    if False:\n'
     '        raise Conflict("this_tenant_has_declared_no_class_credit_entitlement")'),
    ("one of two class credits is chosen by whichever sorted first",
     SVC,
     "    if len(rows) > 1:\n",
     "    if False:\n"),
    # ---- the waitlist ----------------------------------------------------------------
    # **D9.** An offered entry holds a place and the cancellation releases it, so settling the
    # queue afterwards is refused by the trigger on the one entry that has a seat.
    ("the queue is settled after the places have gone back",
     SVC,
     "        lapsed = _lapse_waitlist_on(\n"
     "            conn, session_id, at=moment, actor_id=actor_id,\n"
     "            correlation_id=correlation_id,\n"
     '            reason=f"the class was cancelled: {cancellation_reason}")\n'
     "        cancelled = scheduling.cancel_session_on(",
     "        cancelled = scheduling.cancel_session_on("),
    # The anchor carries the line above it, because `preview_session_cancellation` counts the
    # queue with the same predicate -- "the anchor appears 2 times", which the harness reports
    # as NOT RUN rather than counting.
    ("an offered place is left reading as an offer",
     SVC,
     '        " settle_correlation_id = %s"\n'
     '        " WHERE session_id = %s AND state IN (\'waiting\', \'offered\', \'expired\')",',
     '        " settle_correlation_id = %s"\n'
     '        " WHERE session_id = %s AND state IN (\'waiting\', \'expired\')",'),
    # ---- the move's own writes -------------------------------------------------------
    # **D3.** The member paid once: a second draw would charge them for the gym's change of
    # plan, and the policy is the agreement they booked under.
    ("the moved booking draws a second entitlement",
     SVC,
     "             placement.booking_id, grant_id, actor_id, key, correlation_id),",
     "             placement.booking_id, None, actor_id, key, correlation_id),"),
    ("the moved booking does not say what it replaced",
     SVC,
     "             placement.booking_id, grant_id, actor_id, key, correlation_id),",
     "             None, grant_id, actor_id, key, correlation_id),"),
    # ---- the retry -------------------------------------------------------------------
    # **MOD-017's finding.** Without the comparison, anybody's cancellation request on an
    # already-cancelled class is answered as though it had carried it out.
    ("any request on a cancelled class is answered as its own repeat",
     SVC,
     '    if row is None or str(row[0]) != correlation_id:\n'
     '        raise Conflict("this_session_is_cancelled")',
     '    if row is None:\n'
     '        raise Conflict("this_session_is_cancelled")'),
    ("a repeated request cancels the class a second time",
     SVC,
     '        if session["status"] == "cancelled":\n'
     "            return _cancellation_report(",
     '        if False:\n'
     "            return _cancellation_report("),
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

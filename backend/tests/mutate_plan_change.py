"""Twelve mutations against COM-01-R04's upgrade and downgrade.

**Two declared change kinds with no writer** is what this closes, and the protections are
mostly about not letting a caller choose which of the two acts it is: ADM-MSH-05 is effective
immediately and charges the difference, ADM-MSH-06 lands at the next renewal and charges
nothing, so a caller able to name the direction would take the rest of the period on the
dearer plan for free.

**Three of these are against the supersession walk**, which this slice had to tighten: "not
void" is not "in force", and the first version let a *draft* successor -- one route call,
nobody's signature -- become the agreement every disclosed figure answered from.

Each mutation removes one protection and nothing else; the harness compares the file's bytes
before and after, so a mutation that did not apply is reported NOT RUN rather than counted as
a gap. It restores on a signal as well as in `finally`, because a `finally` does not run when
the process is killed and this repository has twice found a leftover mutation afterwards.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_plan_change
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SERVICE = "app/commercial/service.py"
LIFECYCLE = "app/commercial/lifecycle.py"

MUTATIONS = [
    # ---- the direction, which is the whole shape of the command -------------------------
    ("every plan change is an upgrade, whatever the price says",
     LIFECYCLE,
     '    kind = "upgrade" if to_amount_minor > from_amount_minor else "downgrade"',
     '    kind = "upgrade"'),
    ("every plan change is a downgrade, so a dearer plan is free until the renewal",
     LIFECYCLE,
     '    kind = "upgrade" if to_amount_minor > from_amount_minor else "downgrade"',
     '    kind = "downgrade"'),
    ("a move at the same price is guessed at instead of refused",
     LIFECYCLE,
     '''    if to_amount_minor == from_amount_minor:
        raise LifecycleError(
            "a_plan_change_at_the_same_price_is_a_transfer_which_has_no_writer")''',
     '''    if False:
        raise LifecycleError(
            "a_plan_change_at_the_same_price_is_a_transfer_which_has_no_writer")'''),
    ("a downgrade is prorated mid-period instead of landing at the renewal",
     LIFECYCLE,
     '    if kind == "downgrade":', '    if False:'),
    ("an upgrade prorates a period today does not fall in",
     LIFECYCLE,
     '    if not (period_start <= decided_on <= period_end):',
     '    if False:'),
    # ---- the walk, which decides which agreement governs -------------------------------
    ("a draft successor governs the member",
     SERVICE,
     '    "  AND a.signed_at IS NOT NULL AND a.starts_on <= %s"',
     '    "  AND a.starts_on <= %s"'),
    ("a future-dated successor governs before its date arrives",
     SERVICE,
     '    "  AND a.signed_at IS NOT NULL AND a.starts_on <= %s"',
     '    "  AND a.signed_at IS NOT NULL AND (%s IS NOT NULL)"'),
    # ---- the command's own guards ------------------------------------------------------
    ("an agreement that supersedes something else moves this membership",
     SERVICE,
     '''    if row[6] is None or str(row[6]) != from_agreement_id:
        raise Conflict("this_agreement_does_not_supersede_the_live_one")''',
     '''    if False:
        raise Conflict("this_agreement_does_not_supersede_the_live_one")'''),
    ("a credit in one currency is set against a charge in another",
     SERVICE,
     '''    if str(row[2]).upper() != str(from_row[1]).upper():
        raise Conflict("a_plan_change_does_not_cross_currencies")''',
     '''    if False:
        raise Conflict("a_plan_change_does_not_cross_currencies")'''),
    ("the new agreement may start on a different day from the change",
     SERVICE,
     '    if row[3] != change.effective_on:', '    if False:'),
    ("the acknowledged figure is echoed instead of compared",
     SERVICE,
     '''        if (acknowledged_due_minor is not None
                and acknowledged_due_minor != change.due_minor):''',
     '''        if False and (acknowledged_due_minor is not None
                and acknowledged_due_minor != change.due_minor):'''),
    ("a retried key is accepted against a different target plan",
     SERVICE,
     '''            if prior["to_agreement_id"] != to_agreement_id:
                raise Conflict("this_idempotency_key_moved_this_membership_to_another_plan")''',
     '''            if False:
                raise Conflict("this_idempotency_key_moved_this_membership_to_another_plan")'''),
]

TESTS = [
    "tests.test_commercial_api.PlanChangeTests",
    "tests.test_commercial_domain.PlanChangeTests",
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

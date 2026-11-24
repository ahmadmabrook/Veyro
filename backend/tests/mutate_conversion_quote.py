"""Mutations against ADM-CRM-06's conversion quote, one protection at a time.

**Every figure on that card is produced by one line here**, and the two refusals beside them
are the difference between a quote and a number printed next to a button nobody may press.

**The permission mutation is the one worth the sweep.** Five modules' facts reach this card, so
dropping any one `permit` call turns a sales permission into a read of MOD-016's resolution,
MOD-017's row, MOD-020's bookings or MOD-022's events -- MOD-010's `events.event.read` finding,
which this build has shipped once already in the sibling trial route.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_conversion_quote
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MAIN = "app/main.py"
CRM = "app/crm/service.py"
COMM = "app/commercial/service.py"
TESTS = [
    "tests.test_commercial_api.ConversionQuoteTests",
    "tests.test_commercial_api.SellablePlanTests",
]

MUTATIONS = [
    # ---- the two refusals ------------------------------------------------------------
    ("a trial may be converted into another trial",
     CRM,
     '        if plan[4] is not None:\n'
     '            raise Conflict("a_trial_product_is_not_a_conversion_target")',
     '        if False:\n'
     '            raise Conflict("a_trial_product_is_not_a_conversion_target")'),
    ("an unpublished plan is quoted rather than refused",
     CRM,
     '        if str(plan[5]) != "published" or str(plan[6]) != "active" \\\n'
     '                or str(plan[7]) != "active":\n'
     '            raise Conflict("this_plan_is_not_sellable")',
     '        if False:\n'
     '            raise Conflict("this_plan_is_not_sellable")'),
    # ---- the figures -----------------------------------------------------------------
    # **The anchor.** Ignoring the contract's own anchor charges the whole period from today
    # and quotes no proration, which is the figure ADM-CRM-06 exists to disclose.
    ("the contract's anchor is ignored and every plan bills from today",
     CRM,
     "        billing_period=str(plan[2]), anchor=str(plan[3]))",
     '        billing_period=str(plan[2]), anchor="agreement_start")'),
    # **The disclosure.** `prorated` is what a screen branches on, so a constant makes an
    # agreement-start contract print a pro-rata line equal to its own recurring amount.
    ("the quote always claims it prorated",
     CRM,
     '        "prorated": first_minor != recurring,',
     '        "prorated": True,'),
    # **The subject.** Dropping it loses the segment, which is derived from the person's own
    # MOD-014 tags -- so a corporate or staff member would be quoted the public price.
    ("the quote forgets whose price it is",
     CRM,
     '        subject_id=person_id, channel=channel, actor_id=actor_id,',
     '        subject_id=None, channel=channel, actor_id=actor_id,'),
    # ---- the gate --------------------------------------------------------------------
    ("the card no longer charges the price read",
     MAIN,
     '        permit(session, "catalog.price.read")\n'
     '        permit(session, "membership.record.read")\n'
     '        permit(session, "booking.booking.read")\n'
     '        permit(session, "access.decision.read")\n'
     '        return crm.read_conversion_quote(',
     '        permit(session, "membership.record.read")\n'
     '        permit(session, "booking.booking.read")\n'
     '        permit(session, "access.decision.read")\n'
     '        return crm.read_conversion_quote('),
    # ---- the picker ------------------------------------------------------------------
    # **The trial filter itself, and the first version of this mutation did not touch it.**
    # It appended `AND true` to the status clauses, which changes nothing -- the harness
    # manufacturing the gap it then reports, which is this build's recorded "a mutation that
    # changes nothing is not evidence" trap. The filter is the WHERE's own first line, and the
    # parameter has to stay or the statement no longer matches its tuple.
    ("the picker offers trial products as conversion targets",
     COMM,
     "            WHERE (NOT %s OR t.trial_days IS NULL)",
     "            WHERE (NOT %s OR true)"),
    ("the picker's bound is removed",
     COMM,
     '    if limit < 1 or limit > SELLABLE_PLANS:\n'
     '        raise InvalidRequest("a_plan_listing_is_bounded")',
     '    if False:\n'
     '        raise InvalidRequest("a_plan_listing_is_bounded")'),
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

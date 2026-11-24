"""Mutations against ADR-0011's billing anchor, one protection at a time.

**The schema half is `tests/sql/sweep_billing_anchor.py`; this is the arithmetic.** Every
figure ADM-CRM-06 discloses comes out of three functions -- which calendar unit contains the
start, where the first period ends, and what the part-period costs -- and each is an
off-by-one or a wrong denominator away from charging the wrong amount. 21.29 is 55.00 x 12/31,
so a denominator of twelve gives 55.00 and reads as a contract that does not prorate, which is
the figure a member would dispute.

**The default anchor has its own mutation**, because ADR-0011 D1 rests on it: if adding the
column changed what an existing membership is billed, every renewal date in the product would
have moved for people who have been told a date. The case that sees it is the regression
asserting `agreement_start` is what this build already did.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    python3 -m tests.mutate_billing_anchor
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
LIFE = "app/commercial/lifecycle.py"
TESTS = ["tests.test_commercial_domain"]

MUTATIONS = [
    # ---- the calendar unit, which is the denominator ---------------------------------
    ("the month starts on the day the member joined, not the first",
     LIFE,
     '        start = day.replace(day=1)',
     '        start = day'),
    ("a quarter is taken from the month rather than from the quarter",
     LIFE,
     '        start = date(day.year, ((day.month - 1) // 3) * 3 + 1, 1)',
     '        start = date(day.year, day.month, 1)'),
    ("a year is taken from the month rather than from January",
     LIFE,
     '        start = date(day.year, 1, 1)',
     '        start = date(day.year, day.month, 1)'),
    # **The unit is inclusive of both ends.** Without the day taken off, August runs to the
    # first of September and the member is billed for a day in two periods.
    ("the calendar unit overlaps the next one by a day",
     LIFE,
     '    return start, _add_months(start, months) - timedelta(days=1)',
     '    return start, _add_months(start, months)'),
    # ---- the first period -----------------------------------------------------------
    ("a calendar first period runs a whole unit instead of to the boundary",
     LIFE,
     '    _, unit_end = calendar_unit(day=starts_on, billing_period=billing_period)\n'
     '    return starts_on, unit_end',
     '    unit_start, unit_end = calendar_unit(\n'
     '        day=starts_on, billing_period=billing_period)\n'
     '    return unit_start, unit_end'),
    # **The off-by-one this function was written to hold.** `renewal_period` returns the period
    # *after* the date it is given, so passing the start rather than the day before it makes
    # the first period one day longer than every later one and the drift compounds for life.
    ("the first period is one day longer than every later one",
     LIFE,
     '        return renewal_period(\n'
     '            current_end=starts_on - timedelta(days=1), billing_period=billing_period)',
     '        return renewal_period(\n'
     '            current_end=starts_on, billing_period=billing_period)'),
    ("a week becomes a calendar period after all",
     LIFE,
     'CALENDAR_PERIODS: tuple[str, ...] = ("monthly", "quarterly", "annual")',
     'CALENDAR_PERIODS: tuple[str, ...] = (\n'
     '    "weekly", "monthly", "quarterly", "annual")'),
    ("an anchor nobody declared is accepted",
     LIFE,
     '    if anchor not in ANCHORS:\n'
     '        raise LifecycleError(f"{anchor!r} is not a billing anchor")',
     '    if False:\n'
     '        raise LifecycleError(f"{anchor!r} is not a billing anchor")'),
    # ---- the first charge -----------------------------------------------------------
    # **The denominator.** Prorating over the short period instead of the full unit is twelve
    # over twelve: the full price, disclosed as a pro-rata figure.
    ("the part-period is prorated over itself rather than over the full unit",
     LIFE,
     '    unit_start, unit_end = calendar_unit(day=starts_on, billing_period=billing_period)\n'
     '    amount, steps = prorated_amount(\n'
     '        full_amount_minor=full_amount_minor, period_start=unit_start,\n'
     '        period_end=unit_end, effective_on=starts_on)',
     '    unit_start, unit_end = period_start, period_end\n'
     '    amount, steps = prorated_amount(\n'
     '        full_amount_minor=full_amount_minor, period_start=unit_start,\n'
     '        period_end=unit_end, effective_on=starts_on)'),
    # **The recurring date.** A boundary and the day after it are two facts, and a screen that
    # printed the boundary as the start of the next charge would be a day out.
    ("the recurring amount starts on the boundary rather than the day after",
     LIFE,
     '    next_start = period_end + timedelta(days=1)',
     '    next_start = period_end'),
    # **ADR-0011 D1.** Default the anchor to `calendar` and every membership already sold is
    # re-dated; the regression test is the only thing that says so.
    ("the default anchor becomes calendar, re-dating every membership already sold",
     LIFE,
     '    *, starts_on: date, billing_period: str, anchor: str = "agreement_start",\n'
     ') -> tuple[date, date]:',
     '    *, starts_on: date, billing_period: str, anchor: str = "calendar",\n'
     ') -> tuple[date, date]:'),
    # **The stated case.** A full first period returns the full amount and says it did not
    # prorate; routing it through the proration arrives at the same figure, so only the
    # sentence tells a reader "this contract does not prorate" from "they joined on the first".
    ("a full first period stops saying that nothing was prorated",
     LIFE,
     '            "anchored on the membership\'s own start, so nothing is prorated",',
     '            "",'),
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

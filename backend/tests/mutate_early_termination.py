"""Break the buy-out on purpose and watch the suite fail.

**A constraint nobody has broken is a constraint nobody has tested**, and this repository's
own standard applies to a pure function as much as to a CHECK: the arithmetic that decides
what a member is charged for leaving a commitment early is worth seven mutations.

Each mutation is checked for having *applied* -- the file's bytes have to change -- because a
harness that reports a never-applied mutation as UNCAUGHT manufactures the gap it then
reports. That cost a round on `design:coverage`'s own sweep an hour before this was written.

    python3 -m tests.mutate_early_termination
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

TARGET = pathlib.Path(__file__).resolve().parent.parent / "app" / "commercial" / "lifecycle.py"

#: (name, what it breaks, from, to)
MUTATIONS: list[tuple[str, str, str]] = [
    (
        "the term wins even where the contract sells a buy-out",
        "        if terms.early_termination_months is None:",
        "        if True:",
    ),
    (
        "a contract with no buy-out is read as a free early exit",
        "    if months is None:\n"
        "        steps.append(\"early_termination_minor: 0 (this contract has no buy-out)\")",
        "    if False:\n"
        "        steps.append(\"early_termination_minor: 0 (this contract has no buy-out)\")",
    ),
    (
        "the boundary charges a member who served the whole term",
        "    elif minimum_term_ends_on is None or effective_on >= minimum_term_ends_on:",
        "    elif minimum_term_ends_on is None or effective_on > minimum_term_ends_on:",
    ),
    (
        "the buy-out is one month however many the contract says",
        "        parts[\"early_termination_minor\"] = months * amount_minor",
        "        parts[\"early_termination_minor\"] = amount_minor",
    ),
    (
        "a negative buy-out is admitted",
        "    if months is not None and months < 0:\n"
        "        raise LifecycleError(\"a_buy_out_is_not_negative\")",
        "    if False:\n"
        "        raise LifecycleError(\"a_buy_out_is_not_negative\")",
    ),
    (
        "a negative agreement amount is admitted",
        "    if amount_minor < 0:\n"
        "        raise LifecycleError(\"an_agreement_amount_is_not_negative\")",
        "    if False:\n"
        "        raise LifecycleError(\"an_agreement_amount_is_not_negative\")",
    ),
    (
        "the period part is the remainder rather than the part used",
        "        parts[\"period_minor\"] = amount_minor - remaining",
        "        parts[\"period_minor\"] = remaining",
    ),
    (
        "the total drops the buy-out",
        "    total = parts[\"period_minor\"] + parts[\"early_termination_minor\"]",
        "    total = parts[\"period_minor\"]",
    ),
]


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    caught = 0
    not_run = 0
    for name, old, new in MUTATIONS:
        if old not in original:
            print(f"NOT RUN   {name}  (anchor absent)")
            not_run += 1
            continue
        mutated = original.replace(old, new, 1)
        if mutated == original:
            print(f"NOT RUN   {name}  (replacement changed nothing)")
            not_run += 1
            continue
        TARGET.write_text(mutated, encoding="utf-8")
        try:
            run = subprocess.run(
                [sys.executable, "-m", "unittest",
                 "tests.test_commercial_domain.EarlyTerminationTests"],
                capture_output=True, text=True, cwd=TARGET.parent.parent.parent)
        finally:
            TARGET.write_text(original, encoding="utf-8")
        if run.returncode == 0:
            print(f"UNCAUGHT  {name}")
        else:
            first = next(
                (line for line in run.stderr.splitlines() if line.startswith("FAIL:")),
                "(failed)")
            caught += 1
            print(f"caught    {name}\n            -> {first}")
    print(f"\n{caught}/{len(MUTATIONS) - not_run} caught, {not_run} not run")
    return 0 if not_run == 0 and caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

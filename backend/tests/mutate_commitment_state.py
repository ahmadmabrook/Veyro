"""Break `term_is_running` on purpose and watch the suite fail.

**This field exists because a surface read the wrong one, so the evidence has to be that the
wrong one no longer passes.** `leaving_early` is "access ends before the term does"; where a
contract forbids an early exit the lifecycle pushes the effective date *to* the term end, so
it goes false exactly when the member is most firmly held. ADM-MSH-07 was keyed on it and
told such a member their commitment "has been served" nine months early.

Both directions, because a field asserted true twice is a field proved once: one mutation
restores the defect and one makes the term always running, which is what a `served` case
catches.

Each mutation is checked for having *applied* -- the file's bytes have to change -- because a
harness reporting a never-applied mutation as UNCAUGHT manufactures the gap it then reports.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_commitment_state
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "app" / "commercial" / "service.py"

LIVE = '''            "term_is_running": (
                minimum_term_ends_on is not None and today < minimum_term_ends_on),'''

#: (name, from, to, the test that must notice)
MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "the commitment state reads the date access ends rather than today",
        LIVE,
        '''            "term_is_running": (
                minimum_term_ends_on is not None
                and effective_on < minimum_term_ends_on),''',
        "tests.test_commercial_api.LifecycleTests"
        ".test_a_running_commitment_says_so_even_where_access_does_not_end_early",
    ),
    (
        "every commitment reads as still running, so a served term never says so",
        LIVE,
        '''            "term_is_running": (
                minimum_term_ends_on is not None and True),''',
        "tests.test_commercial_api.LifecycleTests"
        ".test_a_term_that_is_not_running_says_so_whether_served_or_absent",
    ),
    (
        "a contract with no term reads as a running commitment",
        LIVE,
        '''            "term_is_running": (
                minimum_term_ends_on is None or today < minimum_term_ends_on),''',
        "tests.test_commercial_api.LifecycleTests"
        ".test_a_term_that_is_not_running_says_so_whether_served_or_absent",
    ),
]


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    caught = 0
    not_run = 0
    for name, old, new, selector in MUTATIONS:
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
                [sys.executable, "-m", "unittest", selector],
                capture_output=True, text=True, cwd=ROOT)
        finally:
            TARGET.write_text(original, encoding="utf-8")
        if run.returncode == 0:
            print(f"UNCAUGHT  {name}\n            -> {selector} still passes")
        else:
            first = next(
                (line for line in run.stderr.splitlines()
                 if line.startswith(("FAIL:", "ERROR:"))),
                "(failed)")
            caught += 1
            print(f"caught    {name}\n            -> {first}")
    print(f"\n{caught}/{len(MUTATIONS) - not_run} caught, {not_run} not run")
    return 0 if not_run == 0 and caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

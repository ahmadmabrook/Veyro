#!/usr/bin/env python3
"""Replace the generated case blocks in `isolation.sql` with a fresh run of the generator.

**This exists because a splice by eye deleted nineteen hand-written cases.** Re-generating is
routine -- a schema change means new cases -- and the generated output has to land between the
hand-written cases above it and the hand-written cases below it. The first version of this step
was a one-off script that chose its end line by reading the file, and it chose the line below
the hand-written section. The markers the generator now prints are the fix, and this script is
the only thing that should move them.

    python3 backend/tests/sql/splice_access_cases.py

It refuses rather than guessing if either marker pair is missing, and it rewrites check 110's
own case-count assertion from what is actually in the block afterwards.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
TARGET = ROOT / "backend/tests/sql/isolation.sql"
GENERATOR = ROOT / "backend/tests/sql/generate_access_cases.py"

PAIRS = [
    ("    -- >>> GENERATED CHECK CASES BEGIN", "    -- <<< GENERATED CHECK CASES END"),
    ("    -- >>> GENERATED UNIQUE CASES BEGIN", "    -- <<< GENERATED UNIQUE CASES END"),
]


def section(text: str, begin: str, end: str) -> tuple[int, int]:
    if text.count(begin) != 1 or text.count(end) != 1:
        raise SystemExit(f"expected exactly one {begin!r} and one {end!r}")
    a = text.index(begin)
    b = text.index(end, a) + len(end)
    return a, b


def main() -> int:
    produced = subprocess.run([sys.executable, str(GENERATOR)],
                              capture_output=True, text=True, check=True)
    sys.stderr.write(produced.stderr)
    fresh = produced.stdout
    target = TARGET.read_text()

    # Highest offset first, so replacing one block does not move the other.
    for begin, end in reversed(PAIRS):
        new_a, new_b = section(fresh, begin, end)
        old_a, old_b = section(target, begin, end)
        target = target[:old_a] + fresh[new_a:new_b] + target[old_b:]

    start = target.index("------------- 110.")
    stop = target.index("------------- 111.")
    count = target[start:stop].count("probe := probe + 1")
    target = re.sub(r"IF probe <> \d+ THEN\n        RAISE EXCEPTION 'CHECK 110 FAILED: ran %"
                    r" of \d+ MOD-022 rule cases', probe;",
                    f"IF probe <> {count} THEN\n        RAISE EXCEPTION 'CHECK 110 FAILED:"
                    f" ran % of {count} MOD-022 rule cases', probe;",
                    target, count=1)
    TARGET.write_text(target)
    print(f"spliced; check 110 now asserts {count} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

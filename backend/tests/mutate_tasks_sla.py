"""Break the SLA arithmetic on purpose and watch the suite fail.

INV-AUT-02's "time-zone and business-calendar aware" is one module, and the ways it goes
wrong are quiet: an hour counted twice, a clock change ignored, a pause subtracted from the
wrong total. None of those raises; each returns a plausible number. So the arithmetic earns
thirteen mutations, each one a defect this repository has shipped somewhere else.

Each mutation is checked for having *applied* -- the file's bytes have to change -- because a
harness reporting a never-applied mutation as UNCAUGHT manufactures the gap it then reports.

    python3 -m tests.mutate_tasks_sla
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "app" / "tasks" / "sla.py"
SUITE = "tests.test_tasks_sla"

#: (name, from, to)
MUTATIONS: list[tuple[str, str, str]] = [
    (
        "overlapping windows are counted twice instead of merged",
        "    out: list[tuple[time, time]] = []\n"
        "    for start, end in sorted(spans):\n"
        "        if out and start <= out[-1][1]:",
        "    out: list[tuple[time, time]] = []\n"
        "    for start, end in sorted(spans):\n"
        "        if False:",
    ),
    (
        "a dated row adds to the weekly pattern instead of replacing it",
        "    dated = [w for w in windows if w.on_date == day]\n    if dated:",
        "    dated = [w for w in windows if w.on_date == day]\n    if False:",
    ),
    (
        "a closed window may carry hours, so a shut day counts as open",
        '        if self.kind == "closed" and (self.opens_at is not None\n'
        '                                      or self.closes_at is not None):',
        '        if False and (self.opens_at is not None\n'
        '                                      or self.closes_at is not None):',
    ),
    (
        "a weekly window binds every day rather than its own weekday",
        "        if w.weekday == day.weekday() and w.kind == \"open\"",
        "        if w.kind == \"open\"",
    ),
    (
        "an empty calendar answers zero instead of saying it has none",
        "    return any(w.kind == \"open\" for w in windows)",
        "    return True",
    ),
    (
        "the local window is measured in local hours rather than real elapsed time",
        "        start = datetime.combine(day, opens, tzinfo=zone).astimezone(UTC)\n"
        "        end = datetime.combine(day, closes, tzinfo=zone).astimezone(UTC)",
        "        start = datetime.combine(day, opens, tzinfo=UTC)\n"
        "        end = datetime.combine(day, closes, tzinfo=UTC)",
    ),
    (
        "a pause is subtracted whole rather than where it overlaps open time",
        "                    total -= _overlap(span, (max(pause[0], frm), "
        "min(pause[1], to)))",
        "                    total -= pause[1] - pause[0]",
    ),
    (
        "a span that ends before it starts is admitted",
        "    if to < frm:\n"
        "        raise SlaError(\"an SLA span ends after it starts\")",
        "    if False:\n"
        "        raise SlaError(\"an SLA span ends after it starts\")",
    ),
    (
        "the due walk starts from the window rather than from the start instant",
        "            start = max(span[0], started_at)",
        "            start = span[0]",
    ),
    (
        "the due walk has no ceiling",
        "    for _ in range(MAX_DAYS):",
        "    for _ in range(10_000_000):",
    ),
    (
        "a breach is called one second late, so a target met exactly reads as missed",
        "    if consumed_seconds >= target_seconds:",
        "    if consumed_seconds > target_seconds:",
    ),
    (
        "the warning threshold is measured against the consumed time instead of the target",
        "    return \"warning\" if consumed_seconds / target_seconds >= warn_at_fraction "
        "else \"running\"",
        "    return \"warning\" if 1.0 >= warn_at_fraction else \"running\"",
    ),
    (
        "a pause is ignored once the clock is judged on what it spent",
        "                for pause in paused:\n"
        "                    total -= _overlap(span, (max(pause[0], frm), "
        "min(pause[1], to)))",
        "                for pause in paused:\n                    pass",
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
                [sys.executable, "-B", "-m", "unittest", SUITE],
                capture_output=True, text=True, cwd=ROOT, timeout=300)
        except subprocess.TimeoutExpired:
            # A mutation that makes the walk unbounded hangs rather than failing, which is
            # itself the catch: the ceiling exists so a request thread keeps answering.
            TARGET.write_text(original, encoding="utf-8")
            caught += 1
            print(f"caught    {name}\n            -> it hung, which is what the ceiling is for")
            continue
        finally:
            TARGET.write_text(original, encoding="utf-8")
        if run.returncode == 0:
            print(f"UNCAUGHT  {name}")
        else:
            first = next(
                (line for line in run.stderr.splitlines()
                 if line.startswith(("FAIL:", "ERROR:"))),
                "(failed at import)")
            caught += 1
            print(f"caught    {name}\n            -> {first}")
    print(f"\n{caught}/{len(MUTATIONS) - not_run} caught, {not_run} not run")
    return 0 if not_run == 0 and caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

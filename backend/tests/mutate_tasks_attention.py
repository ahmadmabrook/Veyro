"""Break the attention-item decisions on purpose and watch the suite fail.

Each of these returns a plausible value when it is wrong -- a state, a duration, a median --
so none of them raises and none would be noticed by a screen that renders whatever it is
given. That is the argument for a sweep rather than a careful read.

Each mutation is checked for having *applied* -- the file's bytes have to change -- because a
harness reporting a never-applied mutation manufactures the gap it then reports. There is no
name filter here, deliberately: the runner runs the whole module, so there is no pattern that
can go stale against a renamed test, which is the other half of that trap.

    python3 -m tests.mutate_tasks_attention
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "app" / "tasks" / "attention.py"
SUITE = "tests.test_tasks_attention"

#: (name, from, to)
MUTATIONS: list[tuple[str, str, str]] = [
    (
        "assignment is read before lifecycle, so a snoozed item offers a Release button",
        '    if status != "open":\n        return "resolved"\n'
        '    if snoozed_until is not None and snoozed_until > now:\n'
        '        return "snoozed"\n',
        '    if assignee_person_id is not None and assignee_person_id == viewer_person_id:\n'
        '        return "mine"\n'
        '    if status != "open":\n        return "resolved"\n'
        '    if snoozed_until is not None and snoozed_until > now:\n'
        '        return "snoozed"\n',
    ),
    (
        "a deferral that has elapsed still reads as snoozed, so nobody sees it again",
        "    if snoozed_until is not None and snoozed_until > now:",
        "    if snoozed_until is not None:",
    ),
    (
        "the deferral boundary is inclusive, so an item returns a second late",
        "    if snoozed_until is not None and snoozed_until > now:",
        "    if snoozed_until is not None and snoozed_until >= now:",
    ),
    (
        "a reader with no person record owns every assigned item",
        '    return "mine" if assignee_person_id == viewer_person_id else "someone_else"',
        '    return "mine" if assignee_person_id != viewer_person_id else "someone_else"',
    ),
    (
        "somebody else's item has live actions",
        '    return state in ("unassigned", "mine")',
        '    return state in ("unassigned", "mine", "someone_else")',
    ),
    (
        "an unknown state reads as no rather than being refused",
        "    if state not in STATES:\n        raise AttentionError",
        "    if False:\n        raise AttentionError",
    ),
    (
        "an unresolved case reads as having taken no time at all",
        "    if resolved_at is None:\n        return None",
        "    if resolved_at is None:\n        return 0",
    ),
    (
        "a resolution before the opening is admitted and comes back negative",
        "    if resolved_at < opened_at:",
        "    if False:",
    ),
    (
        "the median takes the lower middle on an even count",
        "    return (ordered[middle - 1] + ordered[middle]) // 2",
        "    return ordered[middle - 1]",
    ),
    (
        "an empty window reports a median of zero",
        "    if not values:\n        return None",
        "    if not values:\n        return 0",
    ),
    (
        "the median is taken over the input order rather than the sorted values",
        "    ordered = sorted(values)",
        "    ordered = list(values)",
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
            done = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", SUITE],
                capture_output=True, text=True, cwd=ROOT)
        finally:
            TARGET.write_text(original, encoding="utf-8")
        if done.returncode == 0:
            print(f"UNCAUGHT  {name}")
        else:
            first = next((ln for ln in done.stderr.splitlines()
                          if ln.startswith(("FAIL:", "ERROR:"))), "")
            caught += 1
            print(f"caught    {name}\n            -> {first[:120]}")
    print(f"\n{caught}/{len(MUTATIONS)} caught, {not_run} not run")
    return 0 if caught == len(MUTATIONS) and not not_run else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

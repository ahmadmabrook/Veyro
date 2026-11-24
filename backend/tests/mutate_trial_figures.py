"""Nine mutations against ADM-CRM-05's trial arithmetic.

**Every figure on that card is an off-by-one away from being wrong**, and the canvas's own
three date numbers only agree under the inclusive reading -- `DAY 6 OF 7` beside `2 DAYS LEFT`
beside "her trial ends tomorrow". So each bound, each clamp and each band threshold is removed
on its own and the case that names it has to fail.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    python3 -m tests.mutate_trial_figures
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
TRIAL = "app/crm/trial.py"

MUTATIONS = [
    # ---- the inclusive counts, which is what makes the canvas's figures agree ----------
    ("the trial is a day shorter than it was sold as",
     TRIAL,
     "        return (self.ends_on - self.starts_on).days + 1",
     "        return (self.ends_on - self.starts_on).days"),
    ("the first day of a trial is day zero",
     TRIAL,
     "    return (today - window.starts_on).days + 1",
     "    return (today - window.starts_on).days"),
    ("today does not count as a day left",
     TRIAL,
     "    return (window.ends_on - today).days + 1",
     "    return (window.ends_on - today).days"),
    # ---- the clamps, which the lapsed state needs -------------------------------------
    ("a lapsed trial still has a day left",
     TRIAL,
     "    if today > window.ends_on:\n        return 0",
     "    if False:\n        return 0"),
    ("the last day of a trial reads as lapsed",
     TRIAL,
     "    return today > window.ends_on",
     "    return today >= window.ends_on"),
    ("a trial ending today is reported as ending tomorrow",
     TRIAL,
     "    return window.ends_on == today + timedelta(days=1)",
     "    return window.ends_on <= today + timedelta(days=1)"),
    # ---- the bands --------------------------------------------------------------------
    ("nobody having been in reads as the bottom of a scale rather than its own band",
     TRIAL,
     '    if visits == 0:\n        return "none"',
     '    if False:\n        return "none"'),
    ("the band is measured against the whole trial rather than the days elapsed",
     TRIAL,
     "    elapsed = day_of(window, today)",
     "    elapsed = window.days"),
    ("a negative visit count is banded rather than refused",
     TRIAL,
     '    if visits < 0:\n        raise TrialError("a visit count cannot be negative")',
     '    if False:\n        raise TrialError("a visit count cannot be negative")'),
]


TESTS = ["tests.test_crm_trial_domain"]


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

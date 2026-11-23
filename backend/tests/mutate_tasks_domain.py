"""Break MOD-026's decisions on purpose and watch the suite fail.

**A guard nobody has broken is a guard nobody has tested**, and that applies to a pure
function as much as to a CHECK. Nine mutations, chosen so each one is a defect this
repository has actually shipped somewhere else:

  * the two cross-encoding assertions, because a Python table that silently drifts from the
    schema's CHECK is MOD-020's waitlist edge;
  * the cancelled-dependency rule, because treating called-off work as blocking is MOD-016's
    permanently-unsatisfiable obligation;
  * the cycle walk, because a cycle leaves every task in it blocked with no exit;
  * and the settled-state exits, because a settled task that reopens makes the one-way
    trigger and this table disagree.

Each mutation is checked for having *applied* -- the file's bytes have to change -- because a
harness reporting a never-applied mutation as UNCAUGHT manufactures the gap it then reports.
This session paid for that twice in one afternoon: once on `design:coverage`'s sweep and once
on a constraint name guessed wrong in CHECK 112's sweep.

    python3 -m tests.mutate_tasks_domain
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SUBJECTS = ROOT / "app" / "tasks" / "subjects.py"
WORKFLOW = ROOT / "app" / "tasks" / "workflow.py"

SUITE = "tests.test_tasks_domain"

#: (name, file, from, to)
MUTATIONS: list[tuple[str, pathlib.Path, str, str]] = [
    (
        "a subject kind the schema does not admit is accepted",
        SUBJECTS,
        '    "member", "lead", "tenant", "invoice", "incident", "device", "booking", "asset",\n'
        '    "workflow",\n',
        '    "member", "lead", "tenant", "invoice", "incident", "device", "booking", "asset",\n'
        '    "workflow", "campaign",\n',
    ),
    (
        "a kind the schema admits goes missing from the vocabulary",
        SUBJECTS,
        '    "member", "lead", "tenant", "invoice", "incident", "device", "booking", "asset",\n'
        '    "workflow",\n',
        '    "member", "lead", "tenant", "invoice", "incident", "device", "booking",\n'
        '    "workflow",\n',
    ),
    (
        "a tenant subject is allowed to carry an id as well",
        SUBJECTS,
        '    if kind == "tenant" and subject_id is not None:',
        '    if False and subject_id is not None:',
    ),
    (
        "a subject with no id at all is accepted",
        SUBJECTS,
        '    if kind != "tenant" and subject_id is None:',
        '    if False and subject_id is None:',
    ),
    (
        "a claim kind answers with a table instead of refusing",
        SUBJECTS,
        "    if kind in UNRESOLVABLE:\n"
        "        raise SubjectError(",
        "    if False:\n"
        "        raise SubjectError(",
    ),
    (
        "a settled task is given an exit, so the table and the trigger disagree",
        WORKFLOW,
        '    "done": (),\n    "cancelled": (),',
        '    "done": ("open",),\n    "cancelled": (),',
    ),
    (
        "a case is allowed to move backwards",
        WORKFLOW,
        '    "resolved": ("closed",),\n    "closed": (),',
        '    "resolved": ("closed", "open"),\n    "closed": (),',
    ),
    (
        "a cancelled dependency keeps blocking for ever",
        WORKFLOW,
        "        if status not in SETTLED:\n            out.append(task_id)",
        '        if status != "done":\n            out.append(task_id)',
    ),
    (
        "the cycle walk only notices a self-reference",
        WORKFLOW,
        "        if here == task_id:\n"
        "            raise WorkflowError(",
        "        if False:\n"
        "            raise WorkflowError(",
    ),
]


def main() -> int:
    originals = {p: p.read_text(encoding="utf-8") for p in (SUBJECTS, WORKFLOW)}
    caught = 0
    not_run = 0
    for name, target, old, new in MUTATIONS:
        original = originals[target]
        if old not in original:
            print(f"NOT RUN   {name}  (anchor absent from {target.name})")
            not_run += 1
            continue
        mutated = original.replace(old, new, 1)
        if mutated == original:
            print(f"NOT RUN   {name}  (replacement changed nothing)")
            not_run += 1
            continue
        target.write_text(mutated, encoding="utf-8")
        try:
            run = subprocess.run(
                [sys.executable, "-m", "unittest", SUITE],
                capture_output=True, text=True, cwd=ROOT)
        finally:
            target.write_text(original, encoding="utf-8")
        if run.returncode == 0:
            print(f"UNCAUGHT  {name}")
        else:
            # An import-time `AssertionError` is a catch too: several of these trip the
            # partition and edge guards before any test body runs, which is the point of
            # checking a catalogue where it is declared.
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

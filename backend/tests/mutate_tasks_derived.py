"""Five mutations against the two derived-viewer route additions.

Each removes one protection and nothing else; the harness compares the file's bytes before
and after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap
-- the trap this repository has paid for in three separate sweeps.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent

MUTATIONS = [
    ("an unlinked identity's `mine` falls through to everybody's work",
     "app/main.py",
     '''        own = actor_person_id(tenant_id, session) if mine else None
        if mine and own is None:''',
     '''        own = actor_person_id(tenant_id, session) if mine else None
        if False and mine and own is None:'''),
    ("`mine` is accepted from the query string instead of derived",
     "app/main.py",
     '''            assignee_person_id=own or optional_uuid(
                assignee_person_id, "assignee_person_id"),''',
     '''            assignee_person_id=optional_uuid(
                assignee_person_id, "assignee_person_id"),'''),
    ("the overdue filter counts work that was finished late",
     "app/tasks/service.py",
     "             overdue, at, list(IN_HAND), limit),",
     "             overdue, at, list(workflow.TASK_STATUSES), limit),"),
    ("`to_self` with no person record writes a release",
     "app/main.py",
     "                _require_person(actor_person_id(tenant_id, session))",
     "                actor_person_id(tenant_id, session)"),
    ("`to_self` and a named person together is accepted",
     "app/main.py",
     '        if self.to_self and self.assignee_person_id is not None:',
     '        if False and self.to_self and self.assignee_person_id is not None:'),
]

TESTS = ["tests.test_tasks_api.DerivedViewerTests"]


def digest(path: pathlib.Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    caught, uncaught, notrun = [], [], []
    for name, rel, old, new in MUTATIONS:
        path = BACKEND / rel
        original = path.read_text()
        before = digest(path)
        if original.count(old) != 1:
            notrun.append(f"{name}: anchor appears {original.count(old)} times")
            continue
        path.write_text(original.replace(old, new, 1))
        try:
            if digest(path) == before:
                notrun.append(f"{name}: file unchanged")
                continue
            run = subprocess.run(
                ["../.venv/bin/python3", "-B", "-m", "unittest", *TESTS],
                cwd=BACKEND, capture_output=True, text=True,
                env=os.environ.copy())
            (caught if run.returncode != 0 else uncaught).append(name)
        finally:
            path.write_text(original)
            assert digest(path) == before, f"{rel} not restored"
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

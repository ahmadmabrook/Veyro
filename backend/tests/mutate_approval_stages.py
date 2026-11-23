"""Five mutations against the stage decisions, which no schema sweep can reach.

`tests/sql/sweep_approval_stages.py` breaks the migration's constraints and trigger branches;
these break the pure functions the service decides with. Each removes one protection and
nothing else, and the harness compares the file's bytes before and after -- so a mutation that
did not apply is reported NOT RUN rather than counted as a gap, which is the trap this
repository has paid for in three separate sweeps.

**A sixth was removed rather than left uncaught**, which is this harness earning its place:
`order_conflict` looked for a pair ordered both ways before looking for a cycle, and the
mutation said the first check was redundant -- a pair ordered both ways *is* a two-cycle. The
code is one check shorter for it.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent

MUTATIONS = [
    ("the combined order is a per-key maximum again (a cycle resolves silently)",
     "app/authorization/approval.py",
     "    ordered = _topological(list(policies), counts)",
     "    ordered = sorted(counts)"),
    ("a cycle in the stage order is accepted",
     "app/authorization/approval.py",
     "    nodes = {node for edge in edges for node in edge}",
     "    return None\n    nodes = {node for edge in edges for node in edge}"),
    ("a sequential stage is open before its predecessor",
     "app/authorization/approval.py",
     "    if not sequential:\n        return",
     "    if True:\n        return"),
    ("the decider need not hold the stage's own permission",
     "app/authorization/approval.py",
     "    if here.required_permission not in decider_permissions:",
     "    if False:"),
    ("a staged request resolves on the total rather than per stage",
     "app/authorization/approval.py",
     "    if stages:\n        if all(stage_approvals(decisions, stage.ordinal)"
     " >= stage.required_approvals\n               for stage in stages):\n"
     "            return APPROVED\n        return PENDING",
     "    if False:\n        return PENDING"),
]

TESTS = ["tests.test_authorization_domain.ApprovalStageTests", "tests.test_approval_stages"]


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
                cwd=BACKEND, capture_output=True, text=True, env=os.environ.copy())
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

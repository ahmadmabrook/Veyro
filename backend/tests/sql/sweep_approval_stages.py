"""Break each of `0006`'s trigger branches and constraints, and watch CHECK 113 fail.

**A plpgsql branch is invisible to every structural sweep in this suite** -- a generated
`ALTER TABLE` touches nothing in `pg_proc`, and a definition pin over `md5(prosrc)` says a
body changed without saying whether it still bites. MOD-018 paid for that when a reviewer
deleted the balance trigger's mixed-currency branch and the suite reported 84/84.

**Each function mutation keeps the `RAISE` and makes its whole condition unreachable**
(`IF false THEN`), rather than deleting the statement: CHECK 113 compares the module's total
refusal count against the catalogue, so a deletion would be caught by that assertion rather
than by the probe it is aimed at -- "caught by a sibling", in the evidence itself. The anchor
is the whole condition up to and including its `THEN`, because `IF false AND a OR b` is
`(false AND a) OR b` and a prefix mutation on a disjunction leaves the branch firing.

**One of the four function mutations is a permission rather than a refusal**: removing the
parallel early return makes every request behave as a sequential one, so stage 2 is shut on an
approval whose whole point is that it is not. No `RAISE`-counting assertion can see a guard
that refuses too much, and no refusal probe can either.

**And one mutation was removed rather than left uncaught**, which is the sweep earning its
place twice over: the trigger's `FOR UPDATE` on the request row turned out to be redundant in
both directions, so the lock is gone and the reasoning is in `0006`'s own comment.

This is the `product/` sibling of `sweep_tasks_triggers.py`: same discipline, the `iam`
schema, and CHECK 113 rather than 114.

    PSQL="docker exec -i veyro-pg-mut psql -U postgres" python3 -m tests.sql.sweep_approval_stages
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((ROOT / "migrations" / "product").glob("*.sql"))
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

#: (function, what the mutation removes, the condition, how it is made unreachable)
MUTATIONS: list[tuple[str, str, str, str]] = [
    ("approval_decision_names_a_real_stage",
     "a single-stage request accepts a decision on a stage it has not got",
     "        IF NEW.stage_ordinal <> 1 THEN", "        IF false THEN"),
    ("approval_decision_names_a_real_stage",
     "a staged request accepts a decision on a stage nobody declared",
     "    IF NOT EXISTS (\n"
     "        SELECT 1 FROM iam.approval_request_stages\n"
     "         WHERE tenant_id = NEW.tenant_id AND request_id = NEW.request_id\n"
     "           AND ordinal = NEW.stage_ordinal\n"
     "    ) THEN",
     "    IF false THEN"),
    ("approval_stage_is_open",
     "a sequential second stage may be decided before the first",
     "    IF unmet > 0 THEN", "    IF false THEN"),
    # **A permission, which no `RAISE`-counting assertion can see.** Removing the early return
    # makes every parallel request behave as a sequential one, so stage 2 is shut until stage 1
    # is approved on an approval whose whole point is that it is not -- a guard that refuses
    # too much, which only a probe for the allowed case catches.
    ("approval_stage_is_open",
     "every request behaves as sequential (the parallel early return goes)",
     "    IF in_order IS NULL OR NOT in_order OR NEW.stage_ordinal = 1 THEN",
     "    IF false THEN"),
]

#: (name, the SQL that breaks it). A drop or a weakening, applied by `verify_db.sh` after the
#: build and before the suite.
SQL_MUTATIONS: list[tuple[str, str]] = [
    ("a policy stage may sit outside the declared range",
     "ALTER TABLE iam.approval_policy_stages"
     " DROP CONSTRAINT approval_policy_stages_ordinal"),
    ("a policy stage may ask for no approvers at all",
     "ALTER TABLE iam.approval_policy_stages"
     " DROP CONSTRAINT approval_policy_stages_count"),
    ("a policy stage may name a wildcard instead of a permission",
     "ALTER TABLE iam.approval_policy_stages"
     " DROP CONSTRAINT approval_policy_stages_permission_shape"),
    ("a request stage may sit outside the declared range",
     "ALTER TABLE iam.approval_request_stages"
     " DROP CONSTRAINT approval_request_stages_ordinal"),
    ("a request stage may ask for no approvers at all",
     "ALTER TABLE iam.approval_request_stages"
     " DROP CONSTRAINT approval_request_stages_count"),
    ("a request stage may name a wildcard instead of a permission",
     "ALTER TABLE iam.approval_request_stages"
     " DROP CONSTRAINT approval_request_stages_permission_shape"),
    # **A weakening, not a drop.** Dropping the key is caught by CHECK 28's prefix-free `iam`
    # sweep, which answers first -- so the mutation would prove the sibling and say nothing
    # about the shape. What that sweep cannot see is a key with the right prefix and an extra
    # column: the permission in it admits two stages at one ordinal, which is two steps
    # claiming the same position and makes "earlier" ambiguous for `sequential`.
    ("two stages may share one ordinal (the permission joins the key)",
     "ALTER TABLE iam.approval_request_stages"
     " DROP CONSTRAINT approval_request_stages_pkey CASCADE;"
     " ALTER TABLE iam.approval_request_stages ADD PRIMARY KEY"
     " (tenant_id, request_id, ordinal, required_permission)"),
    # **PostgreSQL truncates a generated constraint name at 63 characters**, so the name is
    # taken from the catalogue rather than composed -- a mutation naming a constraint that does
    # not exist errors and is recorded as not-run, which is the harness manufacturing the gap
    # it then reports. The rules file records that trap for MOD-009's sweep.
    ("one authority may be two stages of one request",
     "ALTER TABLE iam.approval_request_stages DROP CONSTRAINT"
     " approval_request_stages_tenant_id_request_id_required_permi_key"),
]


def definitions() -> dict[str, str]:
    """The *last* definition of each approval trigger function across the migrations."""
    found: dict[str, str] = {}
    pattern = re.compile(
        r"CREATE OR REPLACE FUNCTION iam\.(approval_\w+)\(\) RETURNS trigger.*?\n\$\$;",
        re.DOTALL)
    for path in MIGRATIONS:
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            found[match.group(1)] = match.group(0)
    return found


def main() -> int:
    bodies = definitions()
    caught = 0
    not_run = 0
    for function, what, before, after in MUTATIONS:
        source = bodies.get(function)
        if source is None:
            print(f"NOT RUN   {function}: {what}  (no definition found)")
            not_run += 1
            continue
        if before not in source:
            print(f"NOT RUN   {function}: {what}  (anchor absent)")
            not_run += 1
            continue
        mutated = source.replace(before, after, 1)
        if mutated == source:
            print(f"NOT RUN   {function}: {what}  (replacement changed nothing)")
            not_run += 1
            continue
        done = subprocess.run(
            [str(VERIFY)], capture_output=True, text=True,
            env={**_env(), "MUTATE": mutated, "PSQL": PSQL})
        if done.returncode == 0:
            print(f"UNCAUGHT  {function}: {what}")
        else:
            line = next((ln for ln in done.stdout.splitlines() + done.stderr.splitlines()
                         if "CHECK 113" in ln), "")
            if "CHECK 113" not in line:
                print(f"MUTERR    {function}: {what}  (a check other than 113 answered)")
                not_run += 1
                continue
            caught += 1
            print(f"caught    {function}: {what}\n            -> {line.strip()[:140]}")
    for what, statement in SQL_MUTATIONS:
        done = subprocess.run(
            [str(VERIFY)], capture_output=True, text=True,
            env={**_env(), "MUTATE": statement, "PSQL": PSQL})
        if done.returncode == 0:
            print(f"UNCAUGHT  schema: {what}")
        else:
            line = next((ln for ln in done.stdout.splitlines() + done.stderr.splitlines()
                         if "CHECK 113" in ln), "")
            if "CHECK 113" not in line:
                print(f"MUTERR    schema: {what}  (a check other than 113 answered)")
                not_run += 1
                continue
            caught += 1
            print(f"caught    schema: {what}\n            -> {line.strip()[:140]}")

    total = len(MUTATIONS) + len(SQL_MUTATIONS)
    # **Leave the database as the migrations describe it.** Every other mutation harness in
    # this repository restores a *file*; this one mutates the database, and `verify_db.sh`
    # applies `MUTATE` after the build with nothing putting it back -- so the last run's
    # mutation survives the sweep and sits in the development database afterwards. That cost
    # a whole backend suite run: 2,648 tests reported OK against a trigger branch the sweep
    # had disabled, which is this repository's "a stale artefact read as current" arriving
    # through its own evidence tooling. Restoring is one more rebuild and it is not optional.
    print("\nrestoring the database to the migrations ...", flush=True)
    clean = {k: v for k, v in _env().items() if k not in ("MUTATE", "TAMPER")}
    restored = subprocess.run([str(VERIFY)], capture_output=True, text=True,
                              env={**clean, "PSQL": PSQL})
    if restored.returncode != 0:
        print("COULD NOT RESTORE -- the database still carries the last mutation; run "
              f"`PSQL=\"{PSQL}\" backend/scripts/verify_db.sh` before trusting any suite")
        not_run += 1
    else:
        print("restored")
    print(f"\n{caught}/{total} caught, {not_run} not run")
    return 0 if caught == total and not not_run else 1


def _env() -> dict[str, str]:
    return dict(os.environ)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

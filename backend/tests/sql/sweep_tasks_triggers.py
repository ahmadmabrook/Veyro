"""Break each MOD-026 trigger branch on purpose and watch CHECK 114 fail.

A plpgsql branch is invisible to every structural sweep in this suite: a generated
`ALTER TABLE` mutation touches nothing in `pg_proc`, and a definition pin over `md5(prosrc)`
says a body changed without saying whether it still bites. MOD-018 paid for that when a
reviewer deleted the balance trigger's mixed-currency branch and the suite reported 84/84.

**Each mutation keeps the `RAISE` and makes its whole condition unreachable** (`IF false
THEN`), rather than deleting the statement. Deleting it changes the refusal count, which CHECK 114
compares against the catalogue -- so the mutation would be caught by that assertion rather
than by the probe it is aimed at, which is "caught by a sibling" in the evidence itself. This
repository already paid for the other half of that: two earlier mutations kept a dummy
`RAISE` and fired it unconditionally, so the seed died and the sweep reported MUTERR for
mutations it had never really run. And a third form of the same trap cost four mutations
here: `IF false AND a OR b` is `(false AND a) OR b`, because `AND` binds tighter, so a
prefix mutation on a multi-line disjunction disables one term and leaves the branch firing.
The anchor is the whole condition, up to and including its `THEN`.

The twelfth mutation is not a refusal at all. It restores the pre-`0022` escalation trigger,
which re-judged the route on every write and so froze every clock pointing at a queue that
was later retired -- a permission, which no `RAISE`-counting assertion can see.

    python3 -m tests.sql.sweep_tasks_triggers
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((ROOT / "migrations" / "tenant").glob("*.sql"))
VERIFY = ROOT / "scripts" / "verify_db.sh"
#: Taken from the environment with `verify_db.sh`'s own default, because this script drops
#: and rebuilds the database on every mutation -- which destroys whatever fixture another
#: session in this checkout is holding. Point it at a container of your own:
#:
#:     PSQL="docker exec -i veyro-pg-mut psql -U postgres" python3 -m tests.sql.sweep_tasks_triggers
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

#: (function, what the mutation removes, the condition, how it is made unreachable)
MUTATIONS: list[tuple[str, str, str, str]] = [
    ("tsk_task_matches_its_case", "one piece of work may sit in two backlogs",
     "IF case_queue <> NEW.queue_id THEN", "IF false THEN"),
    ("tsk_task_matches_its_case", "a task may be added to a closed case",
     "IF case_status = 'closed' AND (TG_OP = 'INSERT'",
     "IF false AND (TG_OP = 'INSERT'"),
    ("tsk_settlement_is_final", "a settled task's attribution may be rewritten",
     "        IF NEW.settled_at IS DISTINCT FROM OLD.settled_at\n"
     "           OR NEW.settled_by IS DISTINCT FROM OLD.settled_by\n"
     "           OR NEW.settle_reason IS DISTINCT FROM OLD.settle_reason THEN",
     "        IF false THEN"),
    ("tsk_case_resolution_is_final", "a case may move backwards",
     "IF rank < was THEN", "IF false THEN"),
    ("tsk_case_resolution_is_final", "a resolved case's attribution may be rewritten",
     "        IF NEW.resolved_at IS DISTINCT FROM OLD.resolved_at\n"
     "           OR NEW.resolved_by IS DISTINCT FROM OLD.resolved_by\n"
     "           OR NEW.resolution_reason IS DISTINCT FROM OLD.resolution_reason THEN",
     "        IF false THEN"),
    ("tsk_sla_escalation_is_live", "a clock may escalate to a retired queue",
     "IF queue_status <> 'active' THEN", "IF false AND queue_status <> 'active' THEN"),
    ("tsk_sla_escalation_is_live",
     "the pre-0022 freeze: a retired route blocks every later write to the clock",
     "    IF TG_OP = 'UPDATE'\n"
     "       AND NEW.escalate_to_queue_id IS NOT DISTINCT FROM OLD.escalate_to_queue_id THEN",
     "    IF false\n"
     "       AND NEW.escalate_to_queue_id IS NOT DISTINCT FROM OLD.escalate_to_queue_id THEN"),
    ("tsk_sla_settlement_is_final", "a target may be judged twice",
     "IF NEW.status <> OLD.status THEN", "IF false THEN"),
    ("tsk_sla_settlement_is_final", "a settled clock's attribution may be rewritten",
     "        IF NEW.settled_at IS DISTINCT FROM OLD.settled_at\n"
     "           OR NEW.settled_by IS DISTINCT FROM OLD.settled_by\n"
     "           OR NEW.settle_reason IS DISTINCT FROM OLD.settle_reason THEN",
     "        IF false THEN"),
    ("tsk_sla_settlement_is_final", "a promise may be re-measured after the fact",
     "    IF NEW.started_at IS DISTINCT FROM OLD.started_at\n"
     "       OR NEW.target_seconds IS DISTINCT FROM OLD.target_seconds THEN",
     "    IF false THEN"),
]


def definitions() -> dict[str, str]:
    """The *last* definition of each trigger function across the migrations, in order.

    Last, because `0022` replaces one of `0021`'s: mutating the superseded text would produce
    a statement that is valid, applies, and restores a body the database had already moved
    past -- a mutation testing something nobody ships.
    """
    found: dict[str, str] = {}
    pattern = re.compile(
        r"CREATE OR REPLACE FUNCTION plt01\.(tsk_\w+)\(\) RETURNS trigger.*?\n\$\$;",
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
                         if "CHECK 114" in ln), "")
            if "CHECK 114" not in line:
                print(f"MUTERR    {function}: {what}  (a check other than 114 answered)")
                not_run += 1
                continue
            caught += 1
            print(f"caught    {function}: {what}\n            -> {line.strip()[:140]}")
    total = len(MUTATIONS)
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

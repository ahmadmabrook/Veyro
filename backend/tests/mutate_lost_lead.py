"""Mutations against ADR-0010 D8 to D11's decisions, one protection at a time.

**The schema half is `tests/sql/sweep_lost_lead.py`; this is the behaviour.** What these prove
is that the stage does not move, that a lost lead leaves the pipeline, that the loss reaches
the timeline, that reopening is not gated, and that a withdrawn interest can be asked for
again -- the last of which was a real defect until the test for it existed.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_lost_lead
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
PIPE = "app/crm/pipeline.py"
SVC = "app/crm/service.py"
TESTS = ["tests.test_crm_api.LostLeadTests"]

MUTATIONS = [
    # ---- the decisions --------------------------------------------------------------
    # **A lost lead is not going cold.** Nobody has failed to ring them: they said no, and the
    # reason is on the record. Counting them puts every refusal into the one chip that exists
    # to surface a lead somebody has forgotten.
    ("a lost lead counts as going cold",
     PIPE,
     "    if lost_at is not None:\n        return False\n    since = last_touch_at",
     "    since = last_touch_at"),
    # Ninety days is the figure the canvas states. Shortening it makes a refusal from last
    # month read as worth another try, which is a list a manager works through.
    ("the re-contact window shrinks to a month",
     PIPE,
     "RECONTACT_AFTER = timedelta(days=90)",
     "RECONTACT_AFTER = timedelta(days=30)"),
    # The service's own vocabulary check, behind the route's `Literal`. Only the service test
    # sees it, which is why that test exists.
    ("the service stops checking the reason it was given",
     PIPE,
     '    if reason not in LOST_REASONS:\n'
     '        raise PipelineError(f"{reason!r} is not one of the four reasons '
     'ADM-CRM-07 offers")',
     '    if False:\n'
     '        raise PipelineError(f"{reason!r} is not one of the four reasons '
     'ADM-CRM-07 offers")'),
    # ---- the guards ------------------------------------------------------------------
    ("a lead may be lost twice, re-dating when they said no",
     SVC,
     '        if lead[1] is not None:\n            raise Conflict("this_lead_is_already_lost")',
     '        if False:\n            raise Conflict("this_lead_is_already_lost")'),
    ("a live lead may be reopened",
     SVC,
     '        if lead[1] is None:\n            raise Conflict("this_lead_is_not_lost")',
     '        if False:\n            raise Conflict("this_lead_is_not_lost")'),
    # ---- the history -----------------------------------------------------------------
    # **ADR-0010 D4**: the history is the timeline, so a loss with nothing in it is a refusal
    # nobody can account for -- and the row keeps only the latest reason.
    ("the loss stops reaching the timeline",
     SVC,
     '             f"Marked lost: {reason}" + (f" -- {said}" if said else ""),',
     '             "Marked lost",'),
    # ---- the reads -------------------------------------------------------------------
    ("a lost lead stays on the board",
     SVC,
     '    where.append("l.lost_at IS NULL")\n    with tenant_scope(pool, tenant_id) as conn:\n'
     '        rows = conn.execute(\n'
     '            "SELECT l.lead_id, l.person_id, l.stage, l.created_at,"',
     '    with tenant_scope(pool, tenant_id) as conn:\n'
     '        rows = conn.execute(\n'
     '            "SELECT l.lead_id, l.person_id, l.stage, l.created_at,"'),
    ("a lost lead stays in the default listing",
     SVC,
     '    if lost is not None:\n'
     '        where.append("l.lost_at IS NOT NULL" if lost else "l.lost_at IS NULL")\n'
     '    else:\n'
     '        where.append("l.lost_at IS NULL")',
     '    if lost:\n        where.append("l.lost_at IS NOT NULL")'),
    # ---- the withdrawal --------------------------------------------------------------
    # The profile would list an interest somebody took back, which is the record and the state
    # saying different things -- the reason the withdrawal is a column rather than a delete,
    # undone by the read.
    # The anchor carries the line after it, because `read_lead`'s query and
    # `record_interests`' `held` read are the same two lines otherwise -- "the anchor appears
    # 2 times", which the harness reports as NOT RUN rather than counting.
    ("a withdrawn interest still shows on the profile",
     SVC,
     '            "SELECT interest FROM plt01.crm_lead_interests"\n'
     '            " WHERE lead_id = %s AND withdrawn_at IS NULL",\n'
     '            (lead_id,)).fetchall()]',
     '            "SELECT interest FROM plt01.crm_lead_interests"\n'
     '            " WHERE lead_id = %s",\n'
     '            (lead_id,)).fetchall()]'),
    # **The defect this slice shipped and its own test found.** With every row counted as
    # held, a withdrawn interest blocks its own return: the lead is told "already recorded"
    # and the profile keeps showing one interest.
    ("a withdrawn interest blocks its own return",
     SVC,
     '        held = {str(r[0]) for r in conn.execute(\n'
     '            "SELECT interest FROM plt01.crm_lead_interests"\n'
     '            " WHERE lead_id = %s AND withdrawn_at IS NULL",\n'
     '            (lead_id,)).fetchall()}',
     '        held = {str(r[0]) for r in conn.execute(\n'
     '            "SELECT interest FROM plt01.crm_lead_interests WHERE lead_id = %s",\n'
     '            (lead_id,)).fetchall()}'),
    ("an interest nobody holds may be withdrawn",
     SVC,
     '        if found is None:\n'
     '            raise NotFound("this_lead_does_not_hold_that_interest")',
     '        if False:\n'
     '            raise NotFound("this_lead_does_not_hold_that_interest")'),
]


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

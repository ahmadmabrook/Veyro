"""Mutations against FD-05's walk-in command, one protection at a time. ADR-0010 D12.

What these prove is that the plan is derived rather than guessed at, that a number somebody
already holds is refused rather than reused, that both refusals happen before anything is
written, that the figure is the plan's own, that the press resumes rather than repeating, and
that the touchpoint moves the stage.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_walk_in_trial
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SVC = "app/crm/service.py"
MEM = "app/commercial/service.py"
PPL = "app/people/service.py"
# **Three suites, because one protection lives outside this command.** `holders_of`'s
# merged-away filter is invisible through the walk-in -- its only use of the answer is
# `if holders`, so counting the loser refuses too -- and the case that sees it is the one on
# the function itself, in MOD-014's own merge fixture.
TESTS = ["tests.test_crm_api.WalkInTrialTests",
         "tests.test_commercial_api.SellablePlanTests",
         "tests.test_people_api.ErasureAfterMergeTests"]

MUTATIONS = [
    # ---- the duplicate, which is MOD-014's decision and not this command's -----------
    # `AUTO_MERGE_THRESHOLD` is `None` because two siblings at one address with one family
    # line is the ordinary case, so reusing whoever holds the number would be making the merge
    # decision paragraph 10200 reserves for a person.
    ("a number somebody already holds is reused rather than refused",
     SVC,
     '        if holders and not different_person:',
     '        if False:'),
    # The escape is what makes the refusal usable at a desk: without it a family line locks
    # out every sibling for ever.
    ("the escape stops working, so a sibling can never be recorded",
     SVC,
     '        if holders and not different_person:',
     '        if holders:'),
    # **`merge_status = 'active'` is the survivor.** A merge leaves the losing record's contact
    # points where they are, so without it one number sits on two rows and a desk is refused
    # on behalf of a record whose own readers are told to follow a pointer.
    ("the duplicate check counts merged-away records",
     PPL,
     '            " WHERE c.kind = %s AND c.value_normalized = %s"\n'
     '            "   AND p.merge_status = \'active\'"\n'
     '            " ORDER BY p.person_id LIMIT %s",',
     '            " WHERE c.kind = %s AND c.value_normalized = %s"\n'
     '            " ORDER BY p.person_id LIMIT %s",'),
    # ---- refuse before writing, which is this build's oldest rule --------------------
    # The first version resolved the plan after creating the person, so a refused press left a
    # person, a lead and a touchpoint -- and the next press was refused for the duplicate
    # rather than for the plan.
    ("the plan is resolved after the person is created",
     SVC,
     '    plan = _trial_plan(pool, tenant_id, variant_id=variant_id)\n'
     '    if person_id is None:\n'
     '        assert legal_name is not None and phone is not None\n'
     '        created = people.create_person(',
     '    if person_id is None:\n'
     '        assert legal_name is not None and phone is not None\n'
     '        created = people.create_person('),
    # ---- the plan, derived where there is one and named where there is not -----------
    ("two trial plans are chosen between rather than named",
     SVC,
     '    elif len(offered) > 1:\n        raise InvalidRequest("name_the_trial_plan")',
     '    elif False:\n        raise InvalidRequest("name_the_trial_plan")'),
    ("a tenant with no trial plan gets a 500 instead of the reason",
     SVC,
     '    if not offered:\n'
     '        raise InvalidRequest("this_tenant_publishes_no_trial_plan")',
     '    if False:\n'
     '        raise InvalidRequest("this_tenant_publishes_no_trial_plan")'),
    ("a named variant that is not a trial plan is accepted",
     SVC,
     '        if not chosen:\n            raise NotFound("trial_plan_not_found")',
     '        if False:\n            chosen = offered'),
    # **`only` is the inverse of the default, not a third list.** With the clause gone the
    # walk-in resolves whatever plan sorts first, which is a membership rather than a trial --
    # MOD-018's unordered lookup deciding what somebody was sold.
    ("the trials-only filter stops filtering",
     MEM,
     '              AND (NOT %s OR t.trial_days IS NOT NULL)\n',
     ''),
    ("an unknown trials filter behaves like the default",
     MEM,
     '    if trials not in PLAN_TRIAL_FILTERS:\n'
     '        raise InvalidRequest("a_trial_filter_is_exclude_include_or_only")',
     '    if False:\n'
     '        raise InvalidRequest("a_trial_filter_is_exclude_include_or_only")'),
    # ---- the figure, quoted and never supplied ---------------------------------------
    ("the agreement is written at a figure nobody quoted",
     SVC,
     '        amount_minor = int(quoted["final_amount_minor"])',
     '        amount_minor = 0'),
    ("the currency is guessed rather than read off the live price",
     SVC,
     "    plan[\"currency\"] = offered_in[0]",
     '    plan["currency"] = "USD"'),
    # ---- the resume, which is what four transactions buy instead of one --------------
    # Without it a press between the signature and the activation draws up a second contract
    # on the same terms for the same person on the same day.
    ("an interrupted attempt draws up a second contract",
     SVC,
     '    resumed = commercial.resumable_agreement(\n'
     '        pool, tenant_id, person_id=person_id,\n'
     '        membership_terms_id=plan["membership_terms_id"], starts_on=today)',
     '    resumed = None'),
    # **One mutation was deleted rather than tested harder.** It removed
    # `AND m.membership_id IS NULL` from `resumable_agreement`, came back uncaught, and was
    # right to: `activate_membership` sets the agreement to `active`, so the status filter
    # already excludes every activated agreement and the extra clause -- with the `LEFT JOIN`
    # it needed -- proved nothing. Deleted in the query, which is the judgement this repository
    # records for a constraint subsumed by a sibling.
    ("a second press starts a second trial",
     SVC,
     '    if already is not None:\n        steps["trial"] = "existing"',
     '    if False:\n        steps["trial"] = "existing"'),
    # ---- the record -------------------------------------------------------------------
    # The board counts what the timeline says, so a trial started with an empty timeline is a
    # lead nobody can account for -- and a `tour` would claim a guided viewing happened.
    # **The stage cannot see this and the kind can.** `stage_from_touchpoint` returns
    # `contacted` for everything that is not a `tour`, so swapping `visit` for `note` moves the
    # lead exactly as far -- the first version of this mutation asserted the stage and came back
    # uncaught for that reason. What changes is the fact a report groups by: `note` says nobody
    # came in.
    ("the walk-in records something other than a visit",
     SVC,
     'WALK_IN_KIND = "visit"',
     'WALK_IN_KIND = "note"'),
    # Derived from the agreement so a resumed press produces the same handle; a random one
    # would be refused by the uniqueness index on the retry that resumes.
    ("the membership handle stops being derived from the agreement",
     SVC,
     '    return "TRIAL-" + agreement_id.replace("-", "")[:12].upper()',
     '    return "TRIAL-" + "".join("0123456789ABCDEF"[0] for _ in range(12))'),
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

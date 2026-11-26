"""Mutations against ADM-SCH-05's personal-training session. ADR-0019.

**The schema half is `tests/sql/sweep_personal_session.py`; this is the behaviour.** What
these prove is the half the schema cannot: that the five inner joins which would have hidden a
PT session are LEFT joins, that the grant is derived from the member rather than accepted, that
the soonest-expiring credit is the one spent, that the retry is answered before anything is
written, that the coach's clash refuses rather than warning, and that MOD-020's booking path
turns a personal session away by name.

**The join mutation is the one to read.** `JOIN plt01.sch_templates t ON t.template_id =
s.template_id` silently drops a row whose `template_id` is null, so a PT booking would vanish
from the calendar, from the coach's week and -- worst -- from `_held_over`, the reader every
conflict decision is made from. Each of the three is mutated separately, because a test of one
proves nothing about the others.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_personal_session
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SCH = "app/scheduling/service.py"
BKG = "app/booking/service.py"
COM = "app/commercial/service.py"

TESTS = ["tests.test_scheduling_api.PersonalSessionTests"]

MUTATIONS = [
    # ---- the five LEFT joins, one at a time --------------------------------------------
    # **The conflict reader is the dangerous one**, because an inner join there makes a PT
    # booking invisible to the class generator: the coach is double-bookable with nothing
    # objecting, which is the harm ADR-0019 D2 exists to prevent.
    ("the conflict reader loses a personal session, so the coach is double-bookable",
     SCH,
     '        " FROM plt01.sch_session_resources r"\n'
     '        " JOIN plt01.sch_sessions s ON s.session_id = r.session_id"\n'
     '        " LEFT JOIN plt01.sch_templates t ON t.template_id = s.template_id"',
     '        " FROM plt01.sch_session_resources r"\n'
     '        " JOIN plt01.sch_sessions s ON s.session_id = r.session_id"\n'
     '        " JOIN plt01.sch_templates t ON t.template_id = s.template_id"'),
    ("the calendar drops a personal session",
     SCH,
     '            " FROM plt01.sch_sessions s"\n'
     '            " LEFT JOIN plt01.sch_templates t ON t.template_id = s.template_id"\n'
     '            " WHERE s.location_id = %s AND s.local_date >= %s AND s.local_date <= %s"',
     '            " FROM plt01.sch_sessions s"\n'
     '            " JOIN plt01.sch_templates t ON t.template_id = s.template_id"\n'
     '            " WHERE s.location_id = %s AND s.local_date >= %s AND s.local_date <= %s"'),
    ("the coach's week drops their own personal training",
     SCH,
     '            " JOIN plt01.sch_sessions s ON s.session_id = a.session_id"\n'
     '            " LEFT JOIN plt01.sch_templates t ON t.template_id = s.template_id"',
     '            " JOIN plt01.sch_sessions s ON s.session_id = a.session_id"\n'
     '            " JOIN plt01.sch_templates t ON t.template_id = s.template_id"'),
    ("the session read drops a personal session",
     SCH,
     '            " FROM plt01.sch_sessions s"\n'
     '            " LEFT JOIN plt01.sch_templates t ON t.template_id = s.template_id"\n'
     '            " WHERE s.session_id = %s",',
     '            " FROM plt01.sch_sessions s"\n'
     '            " JOIN plt01.sch_templates t ON t.template_id = s.template_id"\n'
     '            " WHERE s.session_id = %s",'),
    # ---- the nulls the reads carry ----------------------------------------------------
    ("the session read renders the word None where a class would have a name",
     SCH,
     '        "template_id": None if row[0] is None else str(row[0]),',
     '        "template_id": str(row[0]),'),
    ("the calendar renders the word None",
     SCH,
     '             "display_name": None if r[2] is None else str(r[2]),',
     '             "display_name": str(r[2]),'),
    # ---- the grant is derived, not accepted -------------------------------------------
    ("the standing credit is spent before the one about to expire",
     COM,
     '        " ORDER BY g.valid_to NULLS LAST, g.grant_id",',
     '        " ORDER BY g.valid_to DESC NULLS FIRST, g.grant_id",'),
    ("a grant that is not usable now is offered anyway",
     COM,
     "        if not verdict.ok:\n            continue",
     "        if False:\n            continue"),
    ("a grant belonging to anybody is drawable",
     COM,
     '        " WHERE g.person_id = %s AND p.entitlement_type = %s AND g.status = \'active\'"',
     '        " WHERE (g.person_id = %s OR true) AND p.entitlement_type = %s'
     ' AND g.status = \'active\'"'),
    # ---- the command's own refusals ---------------------------------------------------
    ("a member with no credit is booked for nothing",
     SCH,
     '        if not credits:\n'
     '            raise Conflict("this_member_has_no_personal_training_credit")',
     "        if False:\n"
     '            raise Conflict("this_member_has_no_personal_training_credit")'),
    ("the coach's clash is reported rather than refused",
     SCH,
     "        if clashes:\n"
     "            # **Refused, where ADM-SCH-03's class check only warns.**",
     "        if False:\n"
     "            # **Refused, where ADM-SCH-03's class check only warns.**"),
    ("a retry is compared on the member and not on the coach or the hour",
     SCH,
     '            if (str(prior[2]) != person_id or str(prior[3]) != coach_resource_id\n'
     '                    or prior[4] != window.starts_at or prior[5] != window.ends_at):',
     "            if str(prior[2]) != person_id and False:"),
    ("a personal session may be with a room",
     SCH,
     '    if str(row[1]) != "staff":\n'
     '        raise InvalidRequest("a_personal_session_is_with_a_staff_resource")',
     "    if False:\n"
     '        raise InvalidRequest("a_personal_session_is_with_a_staff_resource")'),
    ("a personal session may be five minutes or three days",
     SCH,
     "    if minutes < low or minutes > high:\n"
     '        raise InvalidRequest("a_personal_session_is_15_to_240_minutes")',
     "    if False:\n"
     '        raise InvalidRequest("a_personal_session_is_15_to_240_minutes")'),
    # **No mutation for the two key prefixes, and the sweep is what settled it.** The
    # mutation that collapsed them came back uncaught and was right to: the hold's key and the
    # reservation's live in two tables under two unique indexes, and this command is the only
    # writer of both -- so a collision in one cannot make the other read as repeated, and no
    # case can tell one key from two. The prefixes are legibility (a row in either table says
    # what made it) rather than the namespace control MOD-018's finding is about, and the
    # comment where they are derived says so rather than claiming more.
    # ---- MOD-020's refusal ------------------------------------------------------------
    # **In `_evaluate`, which all three callers reach.** A guard in the command alone is "a
    # control consulted on one path and not its sibling", and the *read* is the one that
    # matters: a surface asking whether a member may book gets the reason rather than a
    # Conflict it has to parse.
    ("MOD-020 books a second member onto a personal session",
     BKG,
     '    if session["session_kind"] != "class":\n'
     "        return Denial(\n"
     '            reason="session_not_bookable",\n'
     '            detail="a personal session holds its member when it is scheduled")',
     "    if False:\n"
     "        return Denial(\n"
     '            reason="session_not_bookable",\n'
     '            detail="a personal session holds its member when it is scheduled")'),

    # ---- the credit is judged at the hour it buys ---------------------------------------
    # **Found by a time-of-day flake rather than by this sweep**, which is the honest order:
    # the quote derived the club's local minute from `now`, so an off-peak package read as
    # usable whenever the request happened to be made inside its window. One of these was
    # written before the defect and could not see it, because `drawable_credits_on` took the
    # moment from its caller and both callers passed the same wrong one.
    ("the quote judges the credit at the moment of asking rather than at the session",
     SCH,
     '            entitlement_type=PERSONAL_ENTITLEMENT, at=window.starts_at,\n'
     '            location_id=location_id)\n'
     '    chosen = credits[0] if credits else None',
     '            entitlement_type=PERSONAL_ENTITLEMENT, at=_now(),\n'
     '            location_id=location_id)\n'
     '    chosen = credits[0] if credits else None'),
    # **And there is deliberately no mutation for the draw's own `usable_at`.** It was
    # written, ran, and came back UNCAUGHT -- correctly: `drawable_credits_on` refuses first
    # on every path a route can take, so the list has already excluded the grant by the time
    # the draw's check would speak, and removing the argument changes no answer through the
    # command. The argument stays, because the draw is the check taken *under the grant's own
    # lock* and the two have to ask the same question or the module has two definitions of
    # when a credit may be spent. A permanently-uncaught entry is noise on every run, so what
    # is asserted instead is the premise the redundancy rests on:
    # `test_the_draw_itself_judges_the_credit_at_the_session_not_at_the_hold` calls
    # `reserve_entitlement_on` directly with a grant the list would never have offered, and
    # the off-peak test above asserts that the quote and the command refuse together.
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
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        }
        try:
            if original.count(old) != 1:
                notrun.append(f"{name}: anchor appears {original.count(old)} times")
                continue
            path.write_text(original.replace(old, new))
            if digest(path) == before:
                notrun.append(f"{name}: the file did not change")
                continue
            run = subprocess.run(
                [str(BACKEND.parent / ".venv/bin/python3"), "-B", "-m", "unittest", *TESTS],
                cwd=BACKEND, capture_output=True, text=True,
                env={**os.environ, "VEYRO_SCRYPT_COST_LOG2": "10",
                     "VEYRO_ENV": "local", "VEYRO_RELEASE": "dev"},
            )
            if run.returncode == 0:
                uncaught.append(name)
                print(f"UNCAUGHT  {name}")
            else:
                caught.append(name)
                print(f"CAUGHT    {name}")
        finally:
            path.write_text(original)
            for sig, prior in handlers.items():
                signal.signal(sig, prior)

    print(f"\n{len(caught)}/{len(MUTATIONS)} caught, {len(notrun)} not run")
    for line in notrun:
        print(f"NOT RUN   {line}")
    for line in uncaught:
        print(f"UNCAUGHT  {line}")
    return 0 if len(caught) == len(MUTATIONS) and not notrun else 1


if __name__ == "__main__":
    raise SystemExit(main())

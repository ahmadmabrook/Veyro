"""Mutations against ADM-SCH-03's live conflict check, one protection at a time.

What these prove is that the walk is bounded, that an impossible rule is refused rather than
reported clear, that the margins are part of the window, that a suggestion is a coach who is
actually free *here*, and that the spare quantity bounding the capacity field counts what is
held.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_conflict_check
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SVC = "app/scheduling/service.py"
TESTS = ["tests.test_scheduling_api.ConflictCheckTests"]

MUTATIONS = [
    # ---- the walk ---------------------------------------------------------------------
    # Asked per keystroke and each occurrence costs a `_held_over` query, so an unbounded walk
    # is a field that feels broken rather than informed -- a daily rule over its 400-day
    # horizon is four hundred queries a keystroke.
    ("the preview walk stops being bounded",
     SVC,
     "        upcoming = [o for o in occurrences if o.local_date >= today][:limit]",
     "        upcoming = [o for o in occurrences if o.local_date >= today]"),
    # **This came back uncaught because the ceiling had two definitions.** The request body
    # carried `le=CONFLICT_PREVIEW` as well, so Pydantic refused `limit: 99` at the boundary
    # and the service's own guard never ran -- a guard the sweep could not reach through any
    # route. The `le` is gone, which is `sellable_plans`' own shape, so the service is the one
    # ceiling and this mutation is decisive.
    ("the bound is not refused above its ceiling",
     SVC,
     '    if limit < 1 or limit > CONFLICT_PREVIEW:\n'
     '        raise InvalidRequest("a_conflict_preview_is_bounded")',
     '    if False:\n'
     '        raise InvalidRequest("a_conflict_preview_is_bounded")'),
    # A rule whose occurrences are all in the past says nothing about a class somebody is
    # about to create, and examining them spends the bound on dates nobody asked about.
    ("the walk examines occurrences that have already passed",
     SVC,
     "        upcoming = [o for o in occurrences if o.local_date >= today][:limit]",
     "        upcoming = list(occurrences)[:limit]"),
    # ---- the refusals -----------------------------------------------------------------
    # **One mutation was deleted rather than tested harder.** It removed
    # `recurrence.check_rule(proposed)` from the dry run, came back uncaught, and was right
    # to: `_parse_rule` calls it and raises `InvalidRequest` itself, as `_parse_policy` and
    # `_parse_requirements` do for their own, so all three explicit checks were controls that
    # could not fail. Deleted in the service, which is the judgement this repository records
    # for a constraint subsumed by a sibling. The refusal is still asserted -- by the test
    # that sends a weekly rule with no weekdays.
    # ---- the window -------------------------------------------------------------------
    # A coach is held for the setup and cleanup margins too, so checking the bare session lets
    # a clash in the margin pass -- `conflicts.detect` was already using the wider window in
    # the generation, so the two questions would be asked about different spans.
    ("the margins stop being part of the window the check asks about",
     SVC,
     "            window = capacity.resource_window(place, wanted)\n"
     "            held = _held_over(\n"
     "                conn, holds_from=window.starts_at, holds_until=window.ends_at)\n"
     "            clashes = list(conflicts.detect(window, needs, chart, held))",
     "            window = place\n"
     "            held = _held_over(\n"
     "                conn, holds_from=window.starts_at, holds_until=window.ends_at)\n"
     "            clashes = list(conflicts.detect(window, needs, chart, held))"),
    # "The rota says no" and "the room is busy" have different remedies, so availability is
    # asked separately and reported as its own kind -- the generation's own split.
    ("a coach whose rota refuses the hour is no longer a conflict",
     SVC,
     '                        clashes.append(conflicts.Conflict(\n'
     '                            kind="unavailable", resource_id=resource_id,'
     ' detail=reason))',
     '                        pass'),
    # ---- the suggestion ---------------------------------------------------------------
    ("a coach at another site is suggested",
     SVC,
     "        if resource.location_id is not None and resource.location_id != location_id:\n"
     "            continue\n"
     "        if availability.unavailable_reason(",
     "        if False:\n"
     "            continue\n"
     "        if availability.unavailable_reason("),
    ("a coach whose rota refuses the hour is suggested",
     SVC,
     "        if availability.unavailable_reason(\n"
     "                window, _windows(conn, resource.resource_id), timezone=timezone)"
     " is not None:\n"
     "            continue",
     "        if False:\n"
     "            continue"),
    # **A third mutation was deleted rather than tested harder.** It removed the `besides`
    # guard -- the conflicting resource ids skipped in `_free_staff` -- and came back uncaught
    # because every route to a staff conflict already excludes that coach: held over the
    # window is the `busy` set, a rota that refuses the hour is `unavailable_reason`, and a
    # coach at another site is the location filter. No case could be written because there is
    # none, so the guard is gone and its reasoning is in the function's docstring.
    ("a coach already holding the hour is suggested",
     SVC,
     '        if resource.kind != "staff" or resource.resource_id in busy:',
     '        if resource.kind != "staff":'),
    ("the suggestion list stops being bounded",
     SVC,
     "        if len(out) == FREE_STAFF_SUGGESTIONS:\n            break",
     "        if False:\n            break"),
    # ---- the capacity ceiling ---------------------------------------------------------
    # A named requirement's ceiling is the thing itself, so counting it would put a spare
    # figure under a field the reader cannot change.
    ("a named requirement contributes a spare count",
     SVC,
     "        if requirement.resource_id is not None:\n            continue\n        total = 0",
     "        if False:\n            continue\n        total = 0"),
    ("the spare count ignores what is already held over the window",
     SVC,
     "            taken = sum(h.quantity for h in held\n"
     "                        if h.resource_id == resource.resource_id\n"
     "                        and conflicts.overlaps(h.placement, window))\n"
     "            total += max(0, resource.quantity - taken)",
     "            total += resource.quantity"),
    ("the spare count includes equipment at another site",
     SVC,
     "            if resource.location_id is not None and resource.location_id"
     " != location_id:\n                continue\n            taken = sum(",
     "            if False:\n                continue\n            taken = sum("),
    # ---- the figure the button states -------------------------------------------------
    # "Create · 2 classes a week" is a weekly figure, and a monthly or one-off rule has no such
    # answer -- one computed from a span would be a number nobody wrote.
    ("a non-weekly rule is given a weekly figure",
     SVC,
     '    weekly = (len(proposed.weekdays) if proposed.frequency == "weekly" else None)',
     "    weekly = len(proposed.weekdays)"),
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

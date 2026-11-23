"""Fourteen mutations against MOD-027 slice 1's decisions and its request path.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap -- the
trap this repository has paid for in four separate sweeps. It restores on a signal as well as
in `finally`, because a `finally` does not run when the process is killed and a leftover
mutation has twice been found sitting in a source file afterwards.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_crm
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
PIPELINE = "app/crm/pipeline.py"
SERVICE = "app/crm/service.py"
MAIN = "app/main.py"

MUTATIONS = [
    # ---- the stage machine -------------------------------------------------------------
    ("a lead may be moved back down the pipeline",
     PIPELINE,
     '''EDGES: dict[str, tuple[str, ...]] = {
    "new": ("contacted",),
    "contacted": ("toured",),
    "toured": (),
}''',
     '''EDGES: dict[str, tuple[str, ...]] = {
    "new": ("contacted", "toured"),
    "contacted": ("toured", "new"),
    "toured": ("contacted", "new"),
}'''),
    ("a touchpoint moves a toured lead back to contacted",
     PIPELINE,
     '    return reached if STAGES.index(reached) > STAGES.index(stage) else stage',
     '    return reached'),
    # ---- the board column --------------------------------------------------------------
    ("a membership no longer outranks the sales stage",
     PIPELINE,
     '    if membership is not None and membership.active:',
     '    if False:'),
    ("a lapsed membership still holds a lead in a derived column",
     PIPELINE,
     '    if membership is not None and membership.active:',
     '    if membership is not None:'),
    # ---- the cold rule -----------------------------------------------------------------
    ("an untouched lead is treated as warm for ever",
     PIPELINE,
     '''    since = last_touch_at if last_touch_at is not None else created_at
    return now - since >= GOING_COLD_AFTER''',
     '''    if last_touch_at is None:
        return False
    return now - last_touch_at >= GOING_COLD_AFTER'''),
    ("the threshold is a week instead of the canvas's forty-eight hours",
     PIPELINE,
     "GOING_COLD_AFTER = timedelta(hours=48)",
     "GOING_COLD_AFTER = timedelta(days=7)"),
    # ---- the interests -----------------------------------------------------------------
    ("gym_only is combined with another interest",
     PIPELINE,
     '''    if "gym_only" in chosen and len(chosen) > 1:
        raise PipelineError("gym_only_is_not_combined_with_another_interest")''',
     '''    if False:
        raise PipelineError("gym_only_is_not_combined_with_another_interest")'''),
    ("the pair is built one request at a time",
     SERVICE,
     "        _interests(tuple(held | set(chosen)))",
     "        pass"),
    # ---- the duplicate the design is structured against --------------------------------
    ("a second lead is created for a person who already has one",
     SERVICE,
     '''        if seen is not None:
            return {"lead_id": str(seen[0]), "person_id": person_id,
                    "stage": str(seen[1]), "created_at": seen[2].isoformat(),
                    "existing": True,''',
     '''        if False:
            return {"lead_id": str(seen[0]), "person_id": person_id,
                    "stage": str(seen[1]), "created_at": seen[2].isoformat(),
                    "existing": True,'''),
    # ---- the stage move and the timeline, in one transaction ---------------------------
    ("a touchpoint leaves the stage where it was",
     SERVICE,
     "        if reached != str(lead[0]):",
     "        if False:"),
    # ---- the mask ----------------------------------------------------------------------
    ("a summary is returned to a reader who cannot write one",
     MAIN,
     '            may_read_summaries=("crm.touchpoint.write" in held_permissions(session)),',
     '            may_read_summaries=True,'),
    ("the mask keys on the cheapest permission in the module, which masks nothing",
     MAIN,
     '            may_read_summaries=("crm.touchpoint.write" in held_permissions(session)),',
     '            may_read_summaries=("crm.lead.read" in held_permissions(session)),'),
    # ---- ownership ---------------------------------------------------------------------
    ("assigning the owner a lead already has is accepted",
     SERVICE,
     '''        if was == owner_person_id:
            raise Conflict("this_lead_already_has_that_owner")''',
     '''        if False:
            raise Conflict("this_lead_already_has_that_owner")'''),
    ("claiming a lead with no person record writes a release instead",
     MAIN,
     '''        owner = (_require_person(actor_person_id(tenant_id, session)) if body.to_self
                 else None if body.release
                 else optional_uuid(body.owner_person_id, "owner_person_id"))''',
     '''        owner = (actor_person_id(tenant_id, session) if body.to_self
                 else None if body.release
                 else optional_uuid(body.owner_person_id, "owner_person_id"))'''),
    # ---- the order the board's own note calls load-bearing -----------------------------
    ("the list is ordered by when a lead was created rather than last contacted",
     SERVICE,
     '''            " ORDER BY coalesce("
            "   (SELECT max(t.occurred_at) FROM plt01.crm_touchpoints t"
            "     WHERE t.lead_id = l.lead_id), l.created_at), l.lead_id"''',
     '''            " ORDER BY l.created_at, l.lead_id"'''),
]

TESTS = ["tests.test_crm_api", "tests.test_crm_domain"]


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

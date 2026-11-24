"""Six mutations against ADR-0010 D7's trial derivation.

**`membership_standing` is the one definition of where somebody stands**, and the board draws
two columns from it -- so each mutation removes one clause and the case that names it has to
fail. Two of them are the window's two sides, which a one-sided case cannot tell apart; one is
the supersession chain, which is the whole reason this read walks it; and one is the
precedence, which only a person holding both a trial and a membership can see.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap. It
restores on a signal as well as in `finally`, because a `finally` does not run when the process
is killed.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_trial_standing
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SERVICE = "app/commercial/service.py"
CRM = "app/crm/service.py"

MUTATIONS = [
    # ---- the window, one side at a time ------------------------------------------------
    ("a trial that has run out is still on the board",
     SERVICE,
     '            " AND m.starts_on <= %s AND (m.ends_on IS NULL OR m.ends_on >= %s)")',
     '            " AND m.starts_on <= %s AND (%s IS NOT NULL)")'),
    ("a trial that has not started yet is already on the board",
     SERVICE,
     '            "m.person_id = ANY(%s) AND m.status = \'active\'"\n'
     '            " AND m.starts_on <= %s AND (m.ends_on IS NULL OR m.ends_on >= %s)")',
     '            "m.person_id = ANY(%s) AND m.status = \'active\'"\n'
     '            " AND (%s IS NOT NULL) AND (m.ends_on IS NULL OR m.ends_on >= %s)")'),
    # ---- the status, which the dates cannot answer -------------------------------------
    ("a cancelled membership still counts",
     SERVICE,
     '            "m.person_id = ANY(%s) AND m.status = \'active\'"',
     '            "m.person_id = ANY(%s) AND m.status IS NOT NULL"'),
    # ---- the chain, which is why this read walks at all --------------------------------
    ("the standing is read from the chain's root rather than its live end",
     SERVICE,
     '          " JOIN plt01.mem_agreements a ON a.agreement_id = live.agreement_id"',
     '          " JOIN plt01.mem_agreements a ON a.agreement_id = m.agreement_id"'),
    # ---- the precedence ----------------------------------------------------------------
    ("a trial outranks a membership where somebody has both",
     SERVICE,
     '        if bool(row[1]) and standing.get(person) != "member":\n'
     '            standing[person] = "trial"\n'
     '        elif not bool(row[1]):\n'
     '            standing[person] = "member"',
     '        if bool(row[1]):\n'
     '            standing[person] = "trial"\n'
     '        elif standing.get(person) != "trial":\n'
     '            standing[person] = "member"'),
    # ---- the board asks at all ---------------------------------------------------------
    ("the board stops asking where anybody stands",
     CRM,
     """        standing = commercial.membership_standing(
            conn, [str(r[1]) for r in rows], at=now.date())""",
     """        standing = {}"""),
    # ---- the end date, which a trial made load-bearing --------------------------------
    ("a conversion leaves the membership ending at the trial",
     SERVICE,
     '        ends_on = _trial_end(conn, to_agreement_id, change.effective_on)\n'
     '        if change.effective_on <= today:',
     '        ends_on = _trial_end(conn, to_agreement_id, change.effective_on)\n'
     '        if False:'),
    ("a trial runs a day longer than it was sold as",
     SERVICE,
     '    return None if trial_days is None else starts_on + _days(trial_days - 1)',
     '    return None if trial_days is None else starts_on + _days(trial_days)'),
]


TESTS = ["tests.test_crm_api", "tests.test_commercial_api"]


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

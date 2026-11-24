"""Mutations against FD-07's handover, one protection at a time.

What these prove is that the float is posted only when it is actually drawn, that which case a
drawer is in is derived from its own balance rather than taken from a caller, that a short
handover refuses without a reason and without somewhere to post the difference, that the
discrepancy is attributed to the shift it belongs to, that a retry answers from what was
recorded, and that what a bag leaves behind is accounted for rather than tolerated.

**The one that matters is the first.** Measured before any of this was written: a 50.00 float
left overnight made the drawer account read 100.00 with 50.00 in notes, so the next close
posted a 50.00 shortfall to suspense against the name of whoever found it, the safe went 50.00
short with nothing having left it, and it compounded every shift.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_handover
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
LED = "app/ledger/service.py"
SET = "app/ledger/settlement.py"
PPL = "app/people/service.py"
# **Three suites.** The handover's own HTTP tests, the domain tests that pin the two decision
# functions with no database, and MOD-014's batch resolver, whose merged-away walk is invisible
# through the ledger.
TESTS = ["tests.test_ledger_api.HandoverTests",
         "tests.test_ledger_api.IdentityLinkTests",
         "tests.test_ledger_domain.HandoverTests",
         "tests.test_ledger_domain.RetainedDepositTests"]

MUTATIONS = [
    # ---- the money, which is what this slice is about -------------------------------
    # **The measured defect.** The float is drawn from the safe only where the drawer holds
    # nothing; posting it on a handover doubles money that is already there.
    ("the float is posted on a handover as well",
     LED,
     '        if not handover and opening_float_minor:',
     '        if opening_float_minor:'),
    # Derived, never accepted: a caller able to say which case this is could choose whether
    # their own count is checked at all.
    ("every drawer is treated as empty, so nothing is ever a handover",
     LED,
     '        handover = held != 0',
     '        handover = False'),
    ("every drawer is treated as a handover, so a first float is never funded",
     LED,
     '        handover = held != 0',
     '        handover = True'),
    # ---- the controls on a short handover -------------------------------------------
    ("a short handover need not state why",
     LED,
     '                settlement.check_handover(count, reason=handover_reason)',
     '                settlement.check_handover(count, reason="anything")'),
    ("a short handover need not name an entity or a suspense account",
     LED,
     '            if gap and not (legal_entity_id and suspense_account_id):',
     '            if False:'),
    # The close's own finding, on the same routine AAL-1 permission: unchecked, this posts an
    # arbitrary amount between the drawer and whatever the caller named.
    ("the account the difference goes to is not checked for being suspense",
     LED,
     '                _account_of_kind(conn, suspense_account_id, ("suspense",),\n'
     '                                 currency=currency.upper(), role="counterpart")',
     '                pass'),
    ("the difference is recorded on the row and never posted",
     LED,
     '        if handover and gap:\n'
     '            assert legal_entity_id is not None and suspense_account_id is not None',
     '        if False:\n'
     '            assert legal_entity_id is not None and suspense_account_id is not None'),
    # ---- the field that would be validated and thrown away --------------------------
    ("a handover accepts an account to draw from and ignores it",
     LED,
     '            if float_source_account_id is not None:',
     '            if False:'),
    # ---- the attribution ------------------------------------------------------------
    # A morning discrepancy recorded as an evening one is attributed to whoever found it.
    ("a handover variance is recorded as an ordinary till variance",
     LED,
     '                case_kind="handover_variance", subject_kind="cash_session",\n'
     '                subject_ref=session_id, expected_minor=held,',
     '                case_kind="cash_variance", subject_kind="cash_session",\n'
     '                subject_ref=session_id, expected_minor=held,'),
    ("the case does not say which shift the difference belongs to",
     LED,
     '                    f"{(handover_reason or \'\').strip()} [handed over from {whose}; "\n'
     '                    f"the difference belongs to that shift]"),',
     '                    f"{(handover_reason or \'\').strip()}"),'),
    # ---- the figures the ledger keeps -----------------------------------------------
    # Stored rather than recomputed, because a posting can be back-dated: the claim is "she
    # counted 50.00 and the ledger said 50.00".
    ("the opening balance is not recorded against the count",
     LED,
     '             held, (handover_reason or "").strip() or None),',
     '             None, (handover_reason or "").strip() or None),'),
    # ---- the retry ------------------------------------------------------------------
    ("a retry reports nothing about the handover it performed",
     LED,
     '                    "handover_variance_minor": (\n'
     '                        int(prior[4]) - was_expected\n'
     '                        if was_expected is not None else None),',
     '                    "handover_variance_minor": None,'),
    # ---- the deposit ----------------------------------------------------------------
    ("what a bag leaves behind is not counted towards the sessions it banks",
     SET,
     '    if declared_minor + retained_minor == sessions_minor:',
     '    if declared_minor == sessions_minor:'),
    # **The control the retained figure must not remove.** Banking less than the till held and
    # pocketing the difference is what this comparison is for.
    ("a bag smaller than the till held is tolerated",
     SET,
     '    if declared_minor + retained_minor == sessions_minor:',
     '    if declared_minor + retained_minor <= sessions_minor:'),
    ("the retained figure is dropped on the way to the row",
     LED,
     '                 currency.upper(), declared_minor, retained_minor, deposited_on,',
     '                 currency.upper(), declared_minor, 0, deposited_on,'),
    # ---- one rule, two sentences ----------------------------------------------------
    ("the handover and the close stop reading one rule",
     SET,
     '    if not count_is_explained(count, reason=reason):\n'
     '        raise LedgerError(\n'
     '            f"the drawer is out by {variance(count)} against what the last shift left "',
     '    if False:\n'
     '        raise LedgerError(\n'
     '            f"the drawer is out by {variance(count)} against what the last shift left "'),
    # ---- the name on a handover -----------------------------------------------------
    # An identity with no person is the ordinary staff case, so a surface has to be able to
    # tell it from a name it could not read.
    ("an unlinked identity comes back present with a null person",
     PPL,
     '        rows = conn.execute(\n'
     '            "SELECT identity_id, person_id FROM plt01.ppl_identity_links"\n'
     '            " WHERE identity_id = ANY(%s)",\n'
     '            (list(identity_ids),),\n'
     '        ).fetchall()',
     '        rows = conn.execute(\n'
     '            "SELECT identity_id, person_id FROM plt01.ppl_identity_links"\n'
     '            " WHERE identity_id = ANY(%s) OR true",\n'
     '            (list(identity_ids),),\n'
     '        ).fetchall()'),
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

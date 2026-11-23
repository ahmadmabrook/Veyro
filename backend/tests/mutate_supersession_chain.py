"""Nine mutations against the readers that follow `supersedes_agreement_id`.

**The defect this sweep is the evidence for had no adversary**: the write path took
`supersedes_agreement_id` and every reader of a membership's terms joined on
`mem_memberships.agreement_id`, which is the chain's *root*. So one route call left the freeze
allowance, the cancellation fee, the notice period, the buy-out, the listing's amount, the
billing tab's whole agreement block and the expiring-value total all answering from the
agreement the member had left.

Each mutation puts one reader back on the root -- or breaks one clause of the walk -- and
nothing else. The harness compares the file's bytes before and after, so a mutation that did
not apply is reported NOT RUN rather than counted as a gap: the trap this repository has paid
for in four separate sweeps.

**It restores on a signal as well as in `finally`.** A `finally` does not run when the process
is killed, and this repository has twice found a leftover mutation sitting in a source file
after an interrupted sweep -- once in a file the session had legitimately edited, where the
file's presence in `git status` was expected and the hunk was never read.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_supersession_chain
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

#: (what the mutation removes, file, anchor, replacement)
MUTATIONS = [
    # ---- the four single-membership readers, each put back on the root ----------------
    ("the cancellation preview prices the agreement the member left",
     SERVICE,
     '        agreement_id = current_agreement(conn, {"agreement_id": membership[0]})',
     '        agreement_id = str(membership[0])'),
    ("the cancel command charges against the agreement the member left",
     SERVICE,
     "        agreement_id = current_agreement(conn, membership)\n"
     "        agreement = conn.execute(",
     '        agreement_id = str(membership["agreement_id"])\n'
     "        agreement = conn.execute("),
    ("the freeze allowance is counted against the superseded contract",
     SERVICE,
     "        terms = _terms_of(conn, current_agreement(conn, membership))\n"
     '        year_start, year_end = _contract_year(membership["starts_on"], today)',
     '        terms = _terms_of(conn, str(membership["agreement_id"]))\n'
     '        year_start, year_end = _contract_year(membership["starts_on"], today)'),
    # ---- the three listing joins, each put back on the root ---------------------------
    ("the membership listing joins the agreement on the chain's root",
     SERVICE,
     '            " JOIN live l ON l.membership_id = m.membership_id"\n'
     '            " JOIN plt01.mem_agreements a ON a.agreement_id = l.agreement_id"\n'
     '            " JOIN plt01.mem_membership_terms t"\n'
     '            "   ON t.membership_terms_id = a.membership_terms_id"\n'
     "            f\" WHERE {' AND '.join(where)}\"\n"
     '            " ORDER BY m.created_at DESC, m.membership_id DESC LIMIT %s",',
     '            " JOIN live l ON l.membership_id = m.membership_id"\n'
     '            " JOIN plt01.mem_agreements a ON a.agreement_id = m.agreement_id"\n'
     '            " JOIN plt01.mem_membership_terms t"\n'
     '            "   ON t.membership_terms_id = a.membership_terms_id"\n'
     "            f\" WHERE {' AND '.join(where)}\"\n"
     '            " ORDER BY m.created_at DESC, m.membership_id DESC LIMIT %s",'),
    ("the billing tab's agreement block is the chain's root",
     SERVICE,
     '            " JOIN plt01.mem_agreements a ON a.agreement_id = l.agreement_id"\n'
     '            " JOIN plt01.mem_membership_terms t"\n'
     '            "   ON t.membership_terms_id = a.membership_terms_id"\n'
     '            " WHERE m.membership_id = %s",',
     '            " JOIN plt01.mem_agreements a ON a.agreement_id = m.agreement_id"\n'
     '            " JOIN plt01.mem_membership_terms t"\n'
     '            "   ON t.membership_terms_id = a.membership_terms_id"\n'
     '            " WHERE m.membership_id = %s",'),
    ("the expiring-value total sums the superseded amount",
     SERVICE,
     '            " JOIN plt01.mem_agreements a ON a.agreement_id = l.agreement_id"\n'
     '            " JOIN plt01.mem_membership_terms t"\n'
     '            "   ON t.membership_terms_id = a.membership_terms_id"\n'
     '            " WHERE m.status IN (\'active\', \'grace\')"',
     '            " JOIN plt01.mem_agreements a ON a.agreement_id = m.agreement_id"\n'
     '            " JOIN plt01.mem_membership_terms t"\n'
     '            "   ON t.membership_terms_id = a.membership_terms_id"\n'
     '            " WHERE m.status IN (\'active\', \'grace\')"'),
    # ---- the walk itself --------------------------------------------------------------
    ("a voided successor governs the membership",
     SERVICE,
     '    "   ON a.supersedes_agreement_id = w.agreement_id AND a.status <> \'void\'"',
     '    "   ON a.supersedes_agreement_id = w.agreement_id"'),
    ("the listing walk takes the shallowest link, which is the root",
     SERVICE,
     ' FROM walk ORDER BY membership_id, depth DESC)")',
     ' FROM walk ORDER BY membership_id, depth)")'),
    ("the single-membership walk takes the shallowest link, which is the root",
     SERVICE,
     '        f"WITH RECURSIVE {_WALK_FROM_ONE} SELECT agreement_id, depth FROM walk"\n'
     '        " ORDER BY depth DESC LIMIT 1",',
     '        f"WITH RECURSIVE {_WALK_FROM_ONE} SELECT agreement_id, depth FROM walk"\n'
     '        " ORDER BY depth LIMIT 1",'),
]

TESTS = ["tests.test_commercial_api.SupersessionChainTests"]


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

        # The loop variables are bound as defaults rather than captured: a handler that read
        # them late would restore the *next* mutation's file, which is the leftover-mutation
        # hazard this harness exists to avoid arriving through the handler written for it.
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

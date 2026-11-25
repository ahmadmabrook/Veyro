"""Mutations against ADM-STF-03's decisions, one protection at a time. ADR-0017.

**The schema half is `tests/sql/sweep_invitations.py`; this is the behaviour.** What these
prove is that the window's band bites, that the state is derived in the order a settled outcome
outranks the clock, that an inviter cannot hand out a role they do not hold, that a resend kills
the link it replaces -- and, the one that matters most, that **nothing is written before the
last check**.

**One of them reproduces the defect this slice shipped.** The first version of `accept_invitation`
created the identity and *then* asked whether the inviter could still grant the role, returning
the refusal so the audit denial would survive the commit -- which committed the identity with
it: a refused invitation left the invitee a working login with no role at all, permanently,
since the address is taken by then. "A control that commits anything before it refuses is not a
control", and the remedy for "the denial must survive" is never "commit everything else too".
Its own test found it.

**Another reproduces the two-clock window.** `expires_at` computed from this process's clock and
bounded in SQL against a `created_at` the database generates is two clocks deciding one fact,
and at exactly thirty days they disagreed.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_invitation
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
DEC = "app/authorization/invitation.py"
SVC = "app/authorization/service.py"
TESTS = [
    "tests.test_authorization_api.InvitationApiTests",
    "tests.test_authorization_domain.InvitationTests",
]

MUTATIONS = [
    # ---- the clubs -------------------------------------------------------------------
    ("an invitation may name no club at all",
     DEC,
     '    if not scopes:\n'
     '        raise InvitationError("an invitation names at least one club or the whole tenant")',
     '    if False:\n'
     '        raise InvitationError("an invitation names at least one club or the whole tenant")'),
    ("one club may be named twice",
     DEC,
     "        if scope.key in seen:\n"
     '            raise InvitationError("a club is named twice on one invitation")',
     "        if False:\n"
     '            raise InvitationError("a club is named twice on one invitation")'),
    ("a tenant-wide invitation may also name a club",
     DEC,
     '    if any(scope.scope_type == "tenant" for scope in scopes) and len(scopes) > 1:',
     "    if False:"),
    ("the club list is unbounded",
     DEC,
     "    if len(scopes) > MAX_SCOPES:",
     "    if False:"),
    # ---- the scope shape -------------------------------------------------------------
    # The shape `role_assignments_scope_shape` admits, because these rows become those rows:
    # a scope this module took and that constraint refused would be an invitation nobody
    # could accept.
    ("a location-scoped invitation need not name its club",
     DEC,
     '        if self.scope_type == "location" and not self.location_id:\n'
     '            raise InvitationError("a location-scoped invitation names its club")',
     "        if False:\n"
     '            raise InvitationError("a location-scoped invitation names its club")'),
    # ---- the window ------------------------------------------------------------------
    ("an invitation may last a year",
     DEC,
     "MAX_EXPIRY_DAYS = 30",
     "MAX_EXPIRY_DAYS = 365"),
    ("an invitation may expire the same minute",
     DEC,
     "MIN_EXPIRY_DAYS = 1",
     "MIN_EXPIRY_DAYS = 0"),
    # **The two-clock window, reproduced.** The expiry computed here and bounded in SQL
    # against a database-generated `created_at` refuses exactly the ceiling the band admits.
    ("the expiry is computed from this process's clock",
     SVC,
     "            VALUES (%s, %s, %s, %s,\n"
     "                    now() + make_interval(days => %s), %s, %s, %s)",
     "            VALUES (%s, %s, %s, %s,\n"
     "                    %s::timestamptz, %s, %s, %s)"),
    # ---- the state -------------------------------------------------------------------
    # A settled outcome outranks the clock: an invitation accepted on Monday is accepted for
    # ever, and reporting it expired a week later would make the pending list disagree with
    # the identity that exists.
    ("the clock outranks a settled outcome",
     DEC,
     "    if accepted_at is not None:\n"
     '        return "accepted"\n'
     "    if revoked_at is not None:\n"
     '        return "revoked"\n'
     '    return "expired" if expires_at <= at else "pending"',
     '    if expires_at <= at:\n        return "expired"\n'
     "    if accepted_at is not None:\n"
     '        return "accepted"\n'
     "    if revoked_at is not None:\n"
     '        return "revoked"\n'
     '    return "pending"'),
    ("the days left are rounded down",
     DEC,
     "    return int(-(-seconds // 86_400))",
     "    return int(seconds // 86_400)"),
    # ---- who may invite --------------------------------------------------------------
    ("an inviter may hand out a role they do not hold",
     SVC,
     "        refusal = _invitation_escalation(\n"
     "            conn, tenant_id, role_id=str(role[0]), role_key=role_key, scopes=scopes,\n"
     "            granted_by=actor_id, correlation_id=correlation_id)",
     "        refusal = None"),
    ("an address that already has an identity may be invited",
     SVC,
     "        if taken is not None:",
     "        if False:"),
    # ---- the accept ------------------------------------------------------------------
    # **The defect this slice shipped.** Checking after the identity exists leaves a working
    # login behind on a refusal, because the refusal is returned rather than raised.
    # **The defect this slice shipped, and the one the assertion it forced then found.**
    # Raising the refusal inside the block rolls the denial back with the identity -- so an
    # attempted escalation at accept time leaves no record at all, which is MOD-008's own rule
    # ("return the error and raise it outside") broken in the most literal way. The mutation
    # that catches it is the one that puts the raise back inside.
    ("the accept raises its refusal inside the transaction, losing the denial",
     SVC,
     "        if refusal is not None:\n"
     "            # **Set and fall out of the block",
     "        if refusal is not None:\n"
     "            raise refusal\n"
     "            # **Set and fall out of the block"),
    ("a settled invitation may be accepted again",
     SVC,
     '        if state != "pending":\n'
     '            raise Conflict(f"this_invitation_is_{state}")',
     "        if False:\n"
     '            raise Conflict(f"this_invitation_is_{state}")'),
    # ---- the resend ------------------------------------------------------------------
    # The old link has to die, or a resend doubles the ways in rather than replacing one.
    ("a resend leaves the old link alive",
     SVC,
     '            if current["revoked_at"] is None:\n'
     '                conn.execute(\n'
     '                    "UPDATE iam.invitations SET revoked_at = %s, revoked_by = %s,"',
     '            if False:\n'
     '                conn.execute(\n'
     '                    "UPDATE iam.invitations SET revoked_at = %s, revoked_by = %s,"'),
    ("an accepted invitation may be resent",
     SVC,
     '        current = _invitation_row(conn, invitation_id)\n'
     '        if current["accepted_at"] is not None:\n'
     '            raise Conflict("this_invitation_has_been_accepted")\n'
     '        scopes = _invitation_scopes(conn, invitation_id)',
     '        current = _invitation_row(conn, invitation_id)\n'
     '        scopes = _invitation_scopes(conn, invitation_id)'),
    # ---- the withdrawal --------------------------------------------------------------
    ("an accepted invitation may be withdrawn",
     SVC,
     '        current = _invitation_row(conn, invitation_id)\n'
     '        if current["accepted_at"] is not None:\n'
     '            raise Conflict("this_invitation_has_been_accepted")\n'
     '        if current["revoked_at"] is not None:',
     '        current = _invitation_row(conn, invitation_id)\n'
     '        if False:'),
    ("a withdrawal need not state why",
     SVC,
     '    if not reason.strip():\n'
     '        raise InvalidRequest("a_withdrawal_states_why")',
     "    if False:\n"
     '        raise InvalidRequest("a_withdrawal_states_why")'),
    # ---- the name the invitee gives ---------------------------------------------------
    # **There is no mutation here, and that is the finding.** The invitation carries no name
    # (D11), so the accept is the only place one comes from -- and a blank-name guard in
    # `accept_invitation` came back UNCAUGHT: `register_identity_on` refuses a
    # whitespace-only display name, the accept is one transaction, so nothing a guard here
    # could add changes the answer or what was written. It was deleted rather than tested
    # harder, which is this build's judgement for a constraint subsumed by a sibling. The
    # property still has a case -- `test_an_invitee_says_what_they_are_called_and_a_blank
    # _leaves_no_login` asserts the refusal *and* that the link still works.
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

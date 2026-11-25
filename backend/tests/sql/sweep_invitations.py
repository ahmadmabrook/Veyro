"""Break 0007's rules on purpose, and watch CHECK 116 fail.

**A constraint nobody has broken on purpose is a constraint nobody has tested.** `iam` is the
one plane in this build whose module checks pin policies and privileges and no constraint set,
which `CLAUDE.md` records as a gap -- so CHECK 116's cases are the invitation's only behavioural
evidence and this is what proves they reach their own rules.

**A weakening is caught only if the weakened rule admits the row**, so the window gets a
mutation per direction and the one-live index gets one for its partial clause. The two
permission cases -- the canvas's own invitation and the accept that settles it -- are what no
refusal can see: a rule tightened until an ordinary invitation is unwritable leaves every
refusal above passing.

**The trigger's branches go one at a time.** `IF false AND ...` keeps the `RAISE` count, which
the probe count in 116b reads; and its probes run as the table owner, because four of the five
columns it freezes carry no UPDATE grant at all and the privilege layer would answer first.

**It restores the database when it finishes.** `verify_db.sh` applies `MUTATE` after the build
with nothing putting it back, so the last mutation survives the sweep -- which cost a whole
backend suite once.

    PSQL="docker exec -i veyro-pg psql -U postgres" python3 -m tests.sql.sweep_invitations
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

_INV = "iam.invitations"
_SCOPES = "iam.invitation_scopes"
_WINDOW = "invitations_window"
_REVOKED = "invitations_revocation_attributed"
_OUTCOME = "invitations_one_outcome"
_LIVE = "iam.invitations_one_live_per_email"
_PER_SCOPE = "iam.invitation_scopes_one_per_scope"

_FN_HEAD = (
    "CREATE OR REPLACE FUNCTION iam.invitation_is_settled_once()"
    " RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $f$ BEGIN")
_FN_TAIL = " RETURN NEW; END; $f$"

_ACCEPTED = (
    " IF %s OLD.accepted_at IS NOT NULL AND ("
    " NEW.accepted_at IS DISTINCT FROM OLD.accepted_at"
    " OR NEW.accepted_identity_id IS DISTINCT FROM OLD.accepted_identity_id) THEN"
    " RAISE EXCEPTION 'accepted once'; END IF;")
_REVOKED_BRANCH = (
    " IF %s OLD.revoked_at IS NOT NULL AND ("
    " NEW.revoked_at IS DISTINCT FROM OLD.revoked_at"
    " OR NEW.revoked_by IS DISTINCT FROM OLD.revoked_by"
    " OR NEW.revoke_reason IS DISTINCT FROM OLD.revoke_reason) THEN"
    " RAISE EXCEPTION 'withdrawn once'; END IF;")
_FROZEN = (
    " IF %s (NEW.token_hash <> OLD.token_hash OR NEW.role_id <> OLD.role_id"
    " OR NEW.expires_at <> OLD.expires_at) THEN"
    " RAISE EXCEPTION 'an invitation keeps its link'; END IF;")
#: The address branch, in three forms. **The tightening is the interesting one**: "the address
#: never moves" reads stricter and is what the first draft of this trigger said, and under it
#: every refusal probe still passes while MOD-009's erasure cannot clear the copy of a staff
#: member's email this row holds. Only a *permission* case sees that, which is 116b's sixth.
_ADDRESS = (
    " IF %s NEW.email_normalized <> OLD.email_normalized"
    " AND OLD.accepted_at IS NULL AND OLD.revoked_at IS NULL THEN"
    " RAISE EXCEPTION 'this invitation is still live'; END IF;")
_ADDRESS_ALWAYS = (
    " IF NEW.email_normalized <> OLD.email_normalized THEN"
    " RAISE EXCEPTION 'this invitation is still live'; END IF;")


def _fn(skip: str) -> str:
    """The trigger body with exactly one branch disabled and its `RAISE` still counted."""
    return (_FN_HEAD
            + _ACCEPTED % ("false AND" if skip == "accepted" else "")
            + _REVOKED_BRANCH % ("false AND" if skip == "revoked" else "")
            + _FROZEN % ("false AND" if skip == "frozen" else "")
            + (_ADDRESS_ALWAYS if skip == "address_always"
               else _ADDRESS % ("false AND" if skip == "address" else ""))
            + _FN_TAIL)


MUTATIONS = [
    # ------------------------------------------------------------- the outcomes
    ("an invitation may be accepted and withdrawn at once",
     f"ALTER TABLE {_INV} DROP CONSTRAINT {_OUTCOME}", "CHECK 116"),
    # ---------------------------------------------------- one live per address
    ("two live invitations to one address",
     f"DROP INDEX {_LIVE}", "CHECK 116"),
    # **The partial clause removed**, which only the resend case sees: a withdrawn invitation
    # would hold the slot for ever, so the remedy D4 provides is defeated by the index that
    # exists to stop two live links.
    ("a withdrawn invitation keeps the address for ever",
     f"DROP INDEX {_LIVE};"
     " CREATE UNIQUE INDEX invitations_one_live_per_email ON"
     f" {_INV} (tenant_id, email_normalized)", "CHECK 116"),
    # ------------------------------------------------- the withdrawal's reason
    ("a withdrawal need not state why",
     f"ALTER TABLE {_INV} DROP CONSTRAINT {_REVOKED}", "CHECK 116"),
    # **The `coalesce` removed**, which only the NULL case sees: `x ~ ...` is NULL and a CHECK
    # passes on NULL, so every blank-reason case in this build passed with it gone until
    # MOD-014's sweep found that.
    ("a withdrawal may state no reason at all",
     f"ALTER TABLE {_INV} DROP CONSTRAINT {_REVOKED};"
     f" ALTER TABLE {_INV} ADD CONSTRAINT {_REVOKED} CHECK ("
     " (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL)"
     " OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL"
     "     AND revoke_reason ~ '[^[:space:]]'))", "CHECK 116"),
    # **The whitespace form restored**, which only the tab case sees: PostgreSQL's one-argument
    # `btrim` strips spaces and nothing else.
    ("a withdrawal reason of one tab becomes a reason",
     f"ALTER TABLE {_INV} DROP CONSTRAINT {_REVOKED};"
     f" ALTER TABLE {_INV} ADD CONSTRAINT {_REVOKED} CHECK ("
     " (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL)"
     " OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL"
     "     AND length(btrim(coalesce(revoke_reason, ''))) > 0))", "CHECK 116"),
    # -------------------------------------------------------------- the window
    ("an invitation may last as long as it likes",
     f"ALTER TABLE {_INV} DROP CONSTRAINT {_WINDOW}", "CHECK 116"),
    # **The ceiling raised**, seen only by the month-and-a-day case: a year-long invitation is
    # a permanent back door with a friendly name.
    ("an invitation may last a year",
     f"ALTER TABLE {_INV} DROP CONSTRAINT {_WINDOW};"
     f" ALTER TABLE {_INV} ADD CONSTRAINT {_WINDOW} CHECK ("
     " expires_at > created_at AND expires_at <= created_at + interval '365 days')",
     "CHECK 116"),
    # **The floor removed**, seen only by the already-closed case: an invitation that expired
    # before it existed is a link nobody can use and a row that reads as one they can.
    ("an invitation may expire before it is written",
     f"ALTER TABLE {_INV} DROP CONSTRAINT {_WINDOW};"
     f" ALTER TABLE {_INV} ADD CONSTRAINT {_WINDOW} CHECK ("
     " expires_at <= created_at + interval '30 days')", "CHECK 116"),
    # **Tightened until the canvas's own seven days is unwritable**, which only the permission
    # case sees: every refusal above still passes while nobody can be invited at all.
    ("the window is tightened until no invitation is storable",
     f"ALTER TABLE {_INV} DROP CONSTRAINT {_WINDOW};"
     f" ALTER TABLE {_INV} ADD CONSTRAINT {_WINDOW} CHECK ("
     " expires_at > created_at AND expires_at <= created_at + interval '1 hour')",
     "CHECK 116"),
    # ------------------------------------------------ the link and the address
    ("the token may be anything",
     f"ALTER TABLE {_INV} DROP CONSTRAINT invitations_token_hash_length", "CHECK 116"),
    ("an invitation may name something that is not an address",
     f"ALTER TABLE {_INV} DROP CONSTRAINT invitations_email_shape", "CHECK 116"),
    # ---------------------------------------------------------------- the clubs
    ("a club shape the assignment would refuse is storable here",
     f"ALTER TABLE {_SCOPES} DROP CONSTRAINT invitation_scopes_shape", "CHECK 116"),
    ("one club may be named twice on one invitation",
     f"DROP INDEX {_PER_SCOPE}", "CHECK 116"),
    # **The `coalesce` in the index removed**, which only the repeated-club case sees: NULLs
    # are distinct in a plain unique index, so two tenant-wide rows -- which is what "the
    # whole tenant" looks like -- would not collide at all.
    ("two tenant-wide clubs stop colliding because NULLs are distinct",
     f"DROP INDEX {_PER_SCOPE};"
     " CREATE UNIQUE INDEX invitation_scopes_one_per_scope ON"
     f" {_SCOPES} (tenant_id, invitation_id, scope_type, brand_id, location_id)",
     "CHECK 116"),
    # ------------------------------------------------------------- the trigger
    ("an acceptance may be re-dated and re-attributed", _fn("accepted"), "CHECK 116"),
    ("a withdrawal's reason may be rewritten", _fn("revoked"), "CHECK 116"),
    ("a live invitation's address may be re-pointed at somebody else",
     _fn("address"), "CHECK 116"),
    ("the address never moves, so an erasure cannot clear it",
     _fn("address_always"), "CHECK 116"),
    ("the address loses its grant, so an erasure cannot reach it",
     f"REVOKE UPDATE (email_normalized) ON {_INV} FROM veyro_iam_app", "CHECK 116"),
    ("the link, the role or the window joins the grant the address is in",
     f"GRANT UPDATE (expires_at) ON {_INV} TO veyro_iam_app", "CHECK 116"),
    ("a name comes back, holding a copy of somebody's name in iam",
     f"ALTER TABLE {_INV} ADD COLUMN display_name text", "CHECK 116"),
    ("a column a token could live in comes back",
     f"ALTER TABLE {_INV} ADD COLUMN invite_url text", "CHECK 116"),
    ("an invitation's clubs become editable",
     f"GRANT UPDATE (scope_type) ON {_SCOPES} TO veyro_iam_app", "CHECK 116"),
    ("an invitation's link, role and window may be rewritten", _fn("frozen"),
     "CHECK 116"),
    # **Answered by 116b's `tgenabled` read, not by a probe**: nothing in this suite read it
    # until MOD-020's review disabled a trigger with every check passing.
    ("the settled-once trigger is disabled outright",
     f"ALTER TABLE {_INV} DISABLE TRIGGER invitations_settled_once", "CHECK 116"),
    ("the trigger function loses its pinned search_path",
     "ALTER FUNCTION iam.invitation_is_settled_once() RESET search_path", "CHECK 116"),
    # --------------------------------------------------------------- the grants
    # A granted column nothing writes is an unattributed edit path, and these two are the
    # link itself and the window it is valid for.
    ("the token may be replaced by this service",
     f"GRANT UPDATE (token_hash) ON {_INV} TO veyro_iam_app", "CHECK 116"),
    ("the window may be moved by this service",
     f"GRANT UPDATE (expires_at) ON {_INV} TO veyro_iam_app", "CHECK 116"),
    # **Answered by CHECK 28, the prefix-free `iam` sweep**, and saying which is the point: a
    # table nobody added to a module's own list is caught by the schema rather than by whoever
    # remembers to extend it.
    ("the invitation loses its forced RLS",
     f"ALTER TABLE {_INV} NO FORCE ROW LEVEL SECURITY", "CHECK 28"),
    ("the clubs lose their forced RLS",
     f"ALTER TABLE {_SCOPES} NO FORCE ROW LEVEL SECURITY", "CHECK 28"),
    ("this service may delete an invitation",
     f"GRANT DELETE ON {_INV} TO veyro_iam_app", "CHECK 28"),
]


def main() -> int:
    caught: list[str] = []
    uncaught: list[str] = []
    notrun: list[str] = []
    for what, statement, wanted in MUTATIONS:
        done = subprocess.run(
            [str(VERIFY)], capture_output=True, text=True,
            env={**os.environ, "MUTATE": statement, "PSQL": PSQL})
        if done.returncode == 0:
            uncaught.append(what)
            continue
        lines = done.stdout.splitlines() + done.stderr.splitlines()
        line = next((ln for ln in lines if wanted in ln), "")
        if not line:
            answered = next(
                (ln for ln in lines if "FAILED" in ln or "ERROR" in ln),
                "nothing named a check")
            notrun.append(f"{what}: wanted {wanted}, got {answered.strip()[:110]}")
            continue
        caught.append(f"{what}\n            -> {line.strip()[:150]}")

    for name in caught:
        print(f"caught    {name}")
    for name in uncaught:
        print(f"UNCAUGHT  {name}")
    for name in notrun:
        print(f"MUTERR    {name}")
    print("\nrestoring the database to the migrations ...", flush=True)
    clean = {k: v for k, v in os.environ.items() if k not in ("MUTATE", "TAMPER")}
    restored = subprocess.run([str(VERIFY)], capture_output=True, text=True,
                              env={**clean, "PSQL": PSQL})
    if restored.returncode != 0:
        print("COULD NOT RESTORE -- run verify_db.sh before trusting any suite")
        notrun.append("the restore failed")
    else:
        print("restored")
    print(f"\n{len(caught)}/{len(MUTATIONS)} caught, {len(notrun)} not run")
    return 0 if len(caught) == len(MUTATIONS) and not notrun else 1


if __name__ == "__main__":
    sys.exit(main())

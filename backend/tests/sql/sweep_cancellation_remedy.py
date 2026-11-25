"""Break 0034's rules on purpose, and watch CHECK 97 and CHECK 78b fail.

**A constraint nobody has broken on purpose is a constraint nobody has tested.** 0034 adds the
two facts ADM-SCH-07 needs -- a booking that replaces one the gym cancelled, and one goodwill
credit per cancelled class -- and every case for them names the constraint or the sentence that
refused it, so a sibling answering fails on a clean database rather than at the next sweep.

**A weakening is caught only if the weakened rule admits the row**, so the biconditional gets a
mutation per side: relaxed to "moved implies a predecessor" only the unmoved-booking case sees
it, and relaxed the other way only the moved-from-nothing case does.

**The permission mutations are what no refusal can see.** The rule tightened until no move is
storable, and `moved` taken out of the source-kind domain, both leave every refusal passing
while the feature is unreachable -- the canvas's own row is the only thing that notices.

**The trigger's branches go one at a time**, because a probe for one is answered by another
when all three are present: a `NOT EXISTS` lookup satisfies the two comparisons below it with
NULLs. `IF false AND ...` keeps the `RAISE` count, which `md5(prosrc)` and the branch count
both read.

**The index needs `DROP INDEX`.** Both new unique rules are partial, which a constraint cannot
be, so the generated `DROP CONSTRAINT` form this repository uses elsewhere would error at
mutation time and be recorded as a false catch.

**It restores the database when it finishes.** `verify_db.sh` applies `MUTATE` after the build
with nothing putting it back, so the last mutation survives the sweep -- which cost a whole
backend suite once.

    PSQL="docker exec -i veyro-pg psql -U postgres" python3 -m tests.sql.sweep_cancellation_remedy
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

_BK = "plt01.bkg_bookings"
_GRANTS = "plt01.mem_entitlement_grants"
_PAIR = "bkg_bookings_moved_names_its_predecessor"
_KIND = "bkg_bookings_source_kind"
_GOODWILL = "plt01.mem_entitlement_grants_one_goodwill_per_source"

_FN_HEAD = (
    "CREATE OR REPLACE FUNCTION plt01.bkg_booking_predecessor_matches()"
    " RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $f$"
    " DECLARE was_person uuid; was_session uuid; BEGIN"
    " IF NEW.moved_from_booking_id IS NULL THEN RETURN NEW; END IF;"
    " SELECT person_id, session_id INTO was_person, was_session FROM plt01.bkg_bookings"
    "  WHERE tenant_id = NEW.tenant_id AND booking_id = NEW.moved_from_booking_id;")
_FN_TAIL = " RETURN NEW; END; $f$"

_EXISTS = (" IF %s was_person IS NULL THEN"
           " RAISE EXCEPTION 'a moved booking cites a booking that does not exist';"
           " END IF;")
_PERSON = (" IF %s was_person <> NEW.person_id THEN RAISE EXCEPTION"
           " 'that booking is another member''''s; a move replaces the member''''s own place';"
           " END IF;")
_SESSION = (" IF %s was_session = NEW.session_id THEN RAISE EXCEPTION"
            " 'that booking is on this same session; a move goes to another one';"
            " END IF;")


def _fn(skip: str) -> str:
    """The trigger body with exactly one branch disabled and its RAISE still counted."""
    return (_FN_HEAD
            + _EXISTS % ("false AND" if skip == "exists" else "")
            + _PERSON % ("false AND" if skip == "person" else "")
            + _SESSION % ("false AND" if skip == "session" else "")
            + _FN_TAIL)


MUTATIONS = [
    # ---------------------------------------------------- the pointer and its source kind
    ("the moved pairing is dropped",
     f"ALTER TABLE {_BK} DROP CONSTRAINT {_PAIR}", "CHECK 97"),
    # **Relaxed to an implication**, seen only by the unmoved-booking case: a `member` booking
    # could then name what it replaced, which is a pointer no reader of `source_kind` consults.
    ("a booking nobody moved may name what it replaced",
     f"ALTER TABLE {_BK} DROP CONSTRAINT {_PAIR};"
     f" ALTER TABLE {_BK} ADD CONSTRAINT {_PAIR}"
     " CHECK (source_kind <> 'moved' OR moved_from_booking_id IS NOT NULL)", "CHECK 97"),
    # **Relaxed the other way**, seen only by the moved-from-nothing case: the product would
    # say a member was moved and have nothing to say where from.
    ("a moved booking may have moved from nothing",
     f"ALTER TABLE {_BK} DROP CONSTRAINT {_PAIR};"
     f" ALTER TABLE {_BK} ADD CONSTRAINT {_PAIR}"
     " CHECK (moved_from_booking_id IS NULL OR source_kind = 'moved')", "CHECK 97"),
    # **Tightened until no move is storable**, which only the permission case sees: every
    # refusal above still passes while ADM-SCH-07's whole remedy is unwritable.
    ("the pairing is tightened until no move is storable",
     f"ALTER TABLE {_BK} DROP CONSTRAINT {_PAIR};"
     f" ALTER TABLE {_BK} ADD CONSTRAINT {_PAIR}"
     " CHECK (moved_from_booking_id IS NULL AND source_kind <> 'moved')", "CHECK 97"),
    # **`moved` taken back out of the vocabulary**, the same shape one column over: the
    # pointer survives and nothing may be written against it.
    ("`moved` is not a source a booking may have",
     f"ALTER TABLE {_BK} DROP CONSTRAINT {_KIND};"
     f" ALTER TABLE {_BK} ADD CONSTRAINT {_KIND} CHECK (source_kind IN"
     " ('member', 'waitlist', 'front_desk', 'migration'))", "CHECK 97"),
    # ------------------------------------------------------- the correspondence trigger
    ("a moved booking may cite a predecessor that does not exist",
     _fn("exists"), "CHECK 97"),
    ("a moved booking may cite another member's place",
     _fn("person"), "CHECK 97"),
    ("a moved booking may cite a place on its own session",
     _fn("session"), "CHECK 97"),
    # **Answered by CHECK 96, not 97**, and saying which is the point: nothing in this
    # suite read `tgenabled` until MOD-020's review disabled a trigger with every check
    # passing, so the catalogue sweep sees a disabled trigger before any probe reaches
    # it. A sweep demanding its own check would report a gap the schema does not have.
    ("the predecessor trigger is disabled outright",
     f"ALTER TABLE {_BK} DISABLE TRIGGER bkg_bookings_predecessor_matches", "CHECK 96"),
    # ------------------------------------------------------ one goodwill credit per source
    ("a member may be credited twice for one cancelled class",
     f"DROP INDEX {_GOODWILL}", "CHECK 78b"),
    # **The revoked clause removed**, which only the replacement case sees: a credit revoked
    # by mistake would hold its slot for ever and the remedy the status exists to provide is
    # defeated by the index that exists to stop a retry.
    ("a revoked credit keeps its slot for ever",
     f"DROP INDEX {_GOODWILL};"
     " CREATE UNIQUE INDEX mem_entitlement_grants_one_goodwill_per_source ON"
     f" {_GRANTS} (tenant_id, person_id, policy_id, source_id)"
     " WHERE source_kind = 'goodwill' AND source_id IS NOT NULL", "CHECK 78b"),
    # **The source clause removed**, seen only by the sourceless pair: two unrelated gestures
    # to one person would collide, so the index would be a rule about generosity.
    ("two unrelated goodwill gestures stop being allowed",
     f"DROP INDEX {_GOODWILL};"
     " CREATE UNIQUE INDEX mem_entitlement_grants_one_goodwill_per_source ON"
     f" {_GRANTS} (tenant_id, person_id, policy_id,"
     " coalesce(source_id, '00000000-0000-0000-0000-000000000000'))"
     " WHERE source_kind = 'goodwill' AND status <> 'revoked'", "CHECK 78b"),
    # **Broadened past goodwill**, seen only by the two-scoped-membership-grants case: one
    # plan legitimately produces two grants of one policy from one source, which is ADR-0013's
    # "two rows each naming one location".
    ("the rule is broadened to every kind of grant",
     f"DROP INDEX {_GOODWILL};"
     " CREATE UNIQUE INDEX mem_entitlement_grants_one_goodwill_per_source ON"
     f" {_GRANTS} (tenant_id, person_id, policy_id, source_id)"
     " WHERE source_id IS NOT NULL AND status <> 'revoked'", "CHECK 78b"),
    # ---------------------------------------------------------------------------- the pins
    ("the predecessor index is dropped",
     "DROP INDEX plt01.bkg_bookings_by_predecessor", "CHECK 98"),
    ("a second predecessor column arrives undeclared",
     f"ALTER TABLE {_BK} ADD COLUMN moved_to_booking_id uuid", "CHECK 95"),
    # A granted column nothing writes is an unattributed edit path: re-pointing a move would
    # rewrite which cancelled class a member was moved off, after the fact.
    ("the predecessor may be re-pointed on a live booking",
     f"GRANT UPDATE (moved_from_booking_id) ON {_BK} TO veyro_cp_app", "CHECK 96"),
    ("the predecessor trigger loses its pinned search_path",
     "ALTER FUNCTION plt01.bkg_booking_predecessor_matches() RESET search_path",
     "CHECK 96"),
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

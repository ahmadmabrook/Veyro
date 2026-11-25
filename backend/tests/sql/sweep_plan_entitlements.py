"""Break ADR-0013's plan-to-entitlement edge on purpose, and watch CHECK 78b fail.

**A constraint nobody has broken on purpose is a constraint nobody has tested.**
`mem_plan_entitlements` is the one edge between a plan and the rights it sells, and
`from_variant_id` is what lets a downgrade know which rights the plan being left gave. Every
case in CHECK 78b names the constraint that refused it, so a sibling answering fails on a clean
database -- and these mutations are what prove the cases reach their own rules at all.

**A weakening is caught only if the weakened rule admits the row**, so each bound gets a
mutation per direction: a quantity rule relaxed downwards is seen only by the zero case and
upwards only by the ten-thousand-and-one case.

**And the permission mutations are what no refusal can see.** The band rule tightened until no
plan may declare an off-peak window, and the quantity rule tightened until no counted right is
storable, both leave every refusal case passing while the column is decoration -- the ordinary
"2 monthly PT sessions" row is the only thing that notices.

**The unique index needs `DROP INDEX`, not `DROP CONSTRAINT`.** It is partial on the
withdrawal, which a constraint cannot be, so the generated form this repository uses elsewhere
would error at mutation time and be recorded as a false catch.

**Four mutations are answered by a different check and saying which is the point.** The column
lists and the nullability are CHECK 76's pins and the UPDATE grant is CHECK 77's, so a sweep
demanding its own check would report gaps the schema does not have -- which costs the same
trust as missing one.

**It restores the database when it finishes.** `verify_db.sh` applies `MUTATE` after the build
with nothing putting it back, so the last mutation survives the sweep -- which cost a whole
backend suite once.

    PSQL="docker exec -i veyro-pg psql -U postgres" python3 -m tests.sql.sweep_plan_entitlements
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

_PLAN = "plt01.mem_plan_entitlements"
_GRANTS = "plt01.mem_entitlement_grants"
_QTY = "mem_plan_entitlements_quantity_positive"
_PAIRED = "mem_plan_entitlements_band_paired"
_BOUNDED = "mem_plan_entitlements_band_bounded"
_ATTRIB = "mem_plan_entitlements_withdrawal_attributed"
_PROV = "mem_entitlement_grants_variant_is_a_membership"

MUTATIONS = [
    ("the quantity bound is dropped",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_QTY}"),
    # **Relaxed downwards**, which only the zero case sees: a plan granting zero reads as
    # including PT and refuses it, because `entitlements.usable` has nothing to draw.
    ("a plan may grant zero of a counted right",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_QTY};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_QTY}"
     " CHECK (quantity IS NULL OR (quantity >= 0 AND quantity <= 10000))"),
    # **Relaxed upwards**, which only the ten-thousand-and-one case sees. A typo at the plan
    # is a typo in every future member's grant.
    ("a plan may grant an unbounded quantity",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_QTY};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_QTY}"
     " CHECK (quantity IS NULL OR quantity > 0)"),
    # **Tightened until no counted right is storable**, which no refusal case can see: the
    # table would hold only uncounted access rights and "2 monthly PT sessions" would be
    # unexpressible, with every refusal above still passing.
    ("the quantity rule is tightened until no counted right is storable",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_QTY};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_QTY} CHECK (quantity IS NULL)"),
    ("the band pairing is dropped",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_PAIRED}"),
    # Weakened to an implication: a start with no end still passes, which is the half the
    # pairing exists for.
    ("a band may state its start and not its end",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_PAIRED};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_PAIRED}"
     " CHECK (usable_to_minute IS NULL OR usable_from_minute IS NOT NULL)"),
    ("the band bound is dropped",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_BOUNDED}"),
    # **The ordering half**, seen only by the reversed-band case: the range still holds.
    ("a band may end before it starts",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_BOUNDED};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_BOUNDED}"
     " CHECK (usable_from_minute IS NULL"
     " OR (usable_from_minute >= 0 AND usable_from_minute < 1440"
     "     AND usable_to_minute > 0 AND usable_to_minute <= 1440))"),
    # **The end-of-day half**, seen only by the 1441 case: the ordering still holds.
    ("a band may end after midnight",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_BOUNDED};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_BOUNDED}"
     " CHECK (usable_from_minute IS NULL"
     " OR (usable_from_minute >= 0 AND usable_from_minute < 1440"
     "     AND usable_to_minute > usable_from_minute))"),
    # **Tightened until no band is storable**, which only the permission case sees.
    ("the band rule is tightened until no off-peak plan is storable",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_BOUNDED};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_BOUNDED}"
     " CHECK (usable_from_minute IS NULL)"),
    ("the withdrawal attribution is dropped",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_ATTRIB}"),
    # **The `coalesce` removed**, which only the NULL-reason case sees:
    # `length(btrim(NULL)) > 0` is NULL and a CHECK passes on NULL, so every blank-reason case
    # in this build passed with it gone until MOD-014's sweep found it.
    ("a withdrawal may state no reason at all",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_ATTRIB};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_ATTRIB}"
     " CHECK ((withdrawn_at IS NULL AND withdrawn_by IS NULL AND withdraw_reason IS NULL)"
     "        OR (withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL"
     "            AND withdraw_reason ~ '[^[:space:]]'))"),
    # **The whitespace form restored**, which only the tab case sees: PostgreSQL's one-argument
    # `btrim` strips spaces and nothing else, so 122 constraints in this build were once
    # satisfied by a single tab.
    ("a withdrawal reason of one tab becomes a reason",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_ATTRIB};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_ATTRIB}"
     " CHECK ((withdrawn_at IS NULL AND withdrawn_by IS NULL AND withdraw_reason IS NULL)"
     "        OR (withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL"
     "            AND length(btrim(coalesce(withdraw_reason, ''))) > 0))"),
    # **The actor half alone**, seen only by the no-actor case: a withdrawal with a reason and
    # nobody's name on it is MOD-009's rule, and the row is kept to answer who stopped it.
    ("a withdrawal may name a reason and no actor",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT {_ATTRIB};"
     f" ALTER TABLE {_PLAN} ADD CONSTRAINT {_ATTRIB}"
     " CHECK (withdrawn_at IS NULL"
     "        OR coalesce(withdraw_reason, '') ~ '[^[:space:]]')"),
    # **The index, which needs `DROP INDEX`.** It is partial on the withdrawal, so a
    # `DROP CONSTRAINT` would error at mutation time and read as a false catch.
    ("one plan may grant one right twice at one scope",
     "DROP INDEX plt01.mem_plan_entitlements_one_live"),
    # **The partial clause removed**, which only the corrected-row case sees: a withdrawn row
    # would hold its slot for ever, so the remedy the withdrawal exists to provide is defeated
    # by the index that exists to stop a duplicate.
    ("a withdrawn row keeps its slot for ever",
     "DROP INDEX plt01.mem_plan_entitlements_one_live;"
     " CREATE UNIQUE INDEX mem_plan_entitlements_one_live ON"
     " plt01.mem_plan_entitlements (tenant_id, variant_id, policy_id,"
     " coalesce(brand_id, '00000000-0000-0000-0000-000000000000'),"
     " coalesce(location_id, '00000000-0000-0000-0000-000000000000'))"),
    # **The `coalesce` in the index removed**, which only the duplicate case sees: NULLs are
    # distinct in a plain unique index, so two unscoped rows -- which is what "all clubs"
    # looks like -- would not collide at all.
    ("two unscoped rows stop colliding because NULLs are distinct",
     "DROP INDEX plt01.mem_plan_entitlements_one_live;"
     " CREATE UNIQUE INDEX mem_plan_entitlements_one_live ON"
     " plt01.mem_plan_entitlements (tenant_id, variant_id, policy_id, brand_id, location_id)"
     " WHERE withdrawn_at IS NULL"),
    # **The trigger's two branches**, each on its own, because a probe for one is answered by
    # the other when both are present. `IF false AND ...` keeps the `RAISE` count.
    ("a withdrawal may be re-dated",
     "CREATE OR REPLACE FUNCTION plt01.mem_plan_entitlements_withdrawal_is_final()"
     " RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $f$"
     " BEGIN IF false AND OLD.withdrawn_at IS NOT NULL"
     "   AND (NEW.withdrawn_at IS DISTINCT FROM OLD.withdrawn_at"
     "        OR NEW.withdrawn_by IS DISTINCT FROM OLD.withdrawn_by) THEN"
     "   RAISE EXCEPTION 'unreachable'; END IF; RETURN NEW; END; $f$"),
    ("the trigger is disabled outright",
     f"ALTER TABLE {_PLAN} DISABLE TRIGGER"
     " mem_plan_entitlements_withdrawal_is_final"),
    # **The provenance rule.** A goodwill grant naming a plan would make a provenance up, and
    # the downgrade reads `from_variant_id` to decide what to withdraw.
    ("a grant of any source may name a plan",
     f"ALTER TABLE {_GRANTS} DROP CONSTRAINT {_PROV}"),
    # The pins.
    ("the quantity becomes NOT NULL, so an uncounted right is unexpressible",
     f"ALTER TABLE {_PLAN} ALTER COLUMN quantity SET NOT NULL", "CHECK 76"),
    ("the variant reference becomes nullable",
     f"ALTER TABLE {_PLAN} ALTER COLUMN variant_id DROP NOT NULL", "CHECK 76"),
    ("a second quantity column arrives undeclared",
     f"ALTER TABLE {_PLAN} ADD COLUMN quantity_per_week integer", "CHECK 76"),
    # A granted column nothing writes is an unattributed edit path, and this one would change
    # what every future member of the plan gets with no record of the change.
    ("the quantity may be re-typed on a live plan",
     f"GRANT UPDATE (quantity) ON {_PLAN} TO veyro_cp_app", "CHECK 77"),
    # **Answered by CHECK 61, not 75.** The prefix-free `plt01` sweep requires every table to
    # carry a tenant-registry reference and runs first, which is the sweep working at its
    # widest: a table nobody prefixed is caught by the schema rather than by whoever remembers
    # to extend a module's own list.
    ("the plan entitlement loses its tenant reference",
     f"ALTER TABLE {_PLAN} DROP CONSTRAINT mem_plan_entitlements_tenant_id_fkey",
     "CHECK 61"),
]


def main() -> int:
    caught: list[str] = []
    uncaught: list[str] = []
    notrun: list[str] = []
    for entry in MUTATIONS:
        what, statement = entry[0], entry[1]
        wanted = entry[2] if len(entry) > 2 else "CHECK 78b"
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
                (ln for ln in lines if "FAILED" in ln), "nothing named a check")
            notrun.append(f"{what}: wanted {wanted}, got {answered.strip()[:90]}")
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

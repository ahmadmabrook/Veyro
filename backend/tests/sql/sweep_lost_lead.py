"""Break ADR-0010 D8 to D11's rules on purpose, and watch CHECK 115 fail.

**A constraint nobody has broken on purpose is a constraint nobody has tested.** What this
schema has to hold is that a loss carries a reason and a name, that the reason is one of the
four ADM-RPT-03 groups by, that a detail is about a loss that happened, and that an interest
taken back stays taken back -- and each of CHECK 115's new cases names the constraint that
refused it, so a sibling answering fails on a clean database.

**Weakenings as well as drops**, because a case catches a weakening only if the weakened rule
*admits* the row. The attribution constraint is two conjuncts over three columns, so there is a
mutation per conjunct; the detail rule is a conjunction of a regex and a bound, so there is one
per side.

**Two of these are permissions**, which no refusal case can see: a constraint set tightened
until an ordinary loss is unrecordable, and a unique rule that stops being partial so an
interest asked for again is refused for ever.

**It restores the database when it finishes.** `verify_db.sh` applies `MUTATE` after the build
with nothing putting it back, so the last mutation survives the sweep -- which cost a whole
backend suite once.

    PSQL="docker exec -i veyro-pg psql -U postgres" python3 -m tests.sql.sweep_lost_lead
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

_L = "plt01.crm_leads"
_I = "plt01.crm_lead_interests"
_ATTR = "crm_leads_lost_is_reasoned_and_attributed"
_DETAIL = "crm_leads_lost_detail_said_something"

MUTATIONS = [
    ("the loss attribution is dropped",
     f"ALTER TABLE {_L} DROP CONSTRAINT {_ATTR}"),
    # One conjunct at a time. With the reason half gone a lead can be lost for nothing while
    # the actor half still refuses a loss nobody recorded -- which the drop cannot tell apart.
    ("a lead may be lost for no reason",
     f"ALTER TABLE {_L} DROP CONSTRAINT {_ATTR};"
     f" ALTER TABLE {_L} ADD CONSTRAINT {_ATTR}"
     " CHECK ((lost_at IS NULL) = (lost_by IS NULL))"),
    ("a loss may have nobody's name on it",
     f"ALTER TABLE {_L} DROP CONSTRAINT {_ATTR};"
     f" ALTER TABLE {_L} ADD CONSTRAINT {_ATTR}"
     " CHECK ((lost_at IS NULL) = (lost_reason IS NULL))"),
    # **The permission.** Tightened until no loss is recordable, every refusal case above still
    # passes and the feature is unusable.
    ("the attribution is tightened until no lead can be lost",
     f"ALTER TABLE {_L} DROP CONSTRAINT {_ATTR};"
     f" ALTER TABLE {_L} ADD CONSTRAINT {_ATTR} CHECK (lost_at IS NULL)"),
    ("the reason vocabulary is dropped",
     f"ALTER TABLE {_L} DROP CONSTRAINT crm_leads_lost_reason"),
    # Widened by one value, which only the out-of-vocabulary case sends.
    ("a fifth reason nobody declared becomes storable",
     f"ALTER TABLE {_L} DROP CONSTRAINT crm_leads_lost_reason;"
     f" ALTER TABLE {_L} ADD CONSTRAINT crm_leads_lost_reason"
     " CHECK (lost_reason IS NULL OR lost_reason IN ('too_expensive', 'joined_elsewhere',"
     " 'location_or_hours', 'no_longer_responding', 'changed_their_mind'))"),
    ("a detail may describe a loss that did not happen",
     f"ALTER TABLE {_L} DROP CONSTRAINT crm_leads_lost_detail_needs_a_loss"),
    ("the detail rule is dropped",
     f"ALTER TABLE {_L} DROP CONSTRAINT {_DETAIL}"),
    # The blank half, on its own: the bound still refuses 501 characters.
    ("a detail of whitespace becomes storable",
     f"ALTER TABLE {_L} DROP CONSTRAINT {_DETAIL};"
     f" ALTER TABLE {_L} ADD CONSTRAINT {_DETAIL}"
     " CHECK (lost_detail IS NULL OR length(lost_detail) <= 500)"),
    # And the bound half: the regex still refuses a tab.
    ("the detail bound is removed",
     f"ALTER TABLE {_L} DROP CONSTRAINT {_DETAIL};"
     f" ALTER TABLE {_L} ADD CONSTRAINT {_DETAIL}"
     " CHECK (lost_detail IS NULL OR lost_detail ~ '[^[:space:]]')"),
    # **`btrim` strips spaces and nothing else**, which is the form this repository banned
    # across 118 constraints -- and only a case that sends a tab can tell the two apart.
    ("the detail rule reverts to btrim",
     f"ALTER TABLE {_L} DROP CONSTRAINT {_DETAIL};"
     f" ALTER TABLE {_L} ADD CONSTRAINT {_DETAIL}"
     " CHECK (lost_detail IS NULL OR (length(btrim(lost_detail)) > 0"
     " AND length(lost_detail) <= 500))"),
    ("the withdrawal attribution is dropped",
     f"ALTER TABLE {_I} DROP CONSTRAINT crm_lead_interests_withdrawal_is_attributed"),
    # The one-way trigger, which no generated constraint sweep can reach: a plpgsql branch is
    # invisible to `pg_constraint`.
    ("a withdrawal may be cleared or re-dated",
     "DROP TRIGGER crm_interest_withdrawal_is_final ON " + _I),
    # Half of it: the branch still refuses a clear and admits a re-date, which only the
    # re-dating case sees.
    ("a withdrawal may be re-dated but not cleared",
     "CREATE OR REPLACE FUNCTION plt01.crm_interest_withdrawal_is_final()"
     " RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER"
     " SET search_path = pg_catalog, pg_temp AS $f$ BEGIN"
     " IF OLD.withdrawn_at IS NOT NULL AND NEW.withdrawn_at IS NULL THEN"
     " RAISE EXCEPTION 'a withdrawn interest stays withdrawn'; END IF;"
     " RETURN NEW; END; $f$"),
    # **The permission, from the index side.** Back to a total unique rule and an interest
    # asked for again after a withdrawal is refused for ever -- which every refusal case above
    # still passes.
    ("the live-interest rule stops being partial",
     f"DROP INDEX plt01.crm_lead_interests_one_live;"
     " CREATE UNIQUE INDEX crm_lead_interests_one_live"
     f" ON {_I} (tenant_id, lead_id, interest)"),
    # The pins. A column added and not declared is a column no sweep in this file can see.
    ("a second loss column arrives undeclared",
     f"ALTER TABLE {_L} ADD COLUMN lost_note text", "CHECK 115"),
    ("the loss columns become editable by nobody's decision",
     f"REVOKE UPDATE (lost_reason) ON {_L} FROM veyro_cp_app, veyro_cp_worker", "CHECK 115"),
]


def main() -> int:
    caught: list[str] = []
    uncaught: list[str] = []
    notrun: list[str] = []
    for entry in MUTATIONS:
        what, statement = entry[0], entry[1]
        # **"CHECK 115", not "CHECK 78".** This harness was copied from MOD-017's sweep and
        # kept its default, so twelve mutations this module's own check caught were reported
        # MUTERR -- the harness manufacturing the gaps it then reports, which is the trap this
        # repository records for a generated mutation that changes nothing.
        wanted = entry[2] if len(entry) > 2 else "CHECK 115"
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
    return 0 if not uncaught and not notrun else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

"""Break each of MOD-027 slice 1's rules on purpose, and watch CHECK 115 fail.

**A constraint nobody has broken on purpose is a constraint nobody has tested**, and this
repository has found the shape six times by sweeping afterwards each time: a case answered by a
*sibling* proves nothing about the rule it names. CHECK 115's cases carry
`GET STACKED DIAGNOSTICS offender = CONSTRAINT_NAME`, so a sibling answering fails on a clean
database -- and these mutations are what prove the cases reach their own rules at all.

**Weakenings as well as drops**, because a case catches a weakening only if the weakened rule
*admits* the row: the one-sided bound on `occurred_at` is the shape, and the case that bites is
a touchpoint in the future rather than one in the past.

**It restores the database when it finishes.** `verify_db.sh` applies `MUTATE` after the build
with nothing putting it back, so the last mutation survives the sweep -- which cost a whole
backend suite once: 2,648 tests reported OK against a trigger branch a sweep had disabled.

    PSQL="docker exec -i veyro-pg-mut psql -U postgres" python3 -m tests.sql.sweep_crm
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

_CHECKS = (
    "crm_lead_sources_key_shape", "crm_lead_sources_name_stated",
    "crm_lead_sources_retired_is_retired", "crm_lead_sources_retirement_attributed",
    "crm_lead_sources_status", "crm_leads_next_action_bounded",
    "crm_leads_next_action_paired", "crm_leads_next_action_stated", "crm_leads_stage",
    "crm_leads_version_positive", "crm_touchpoints_kind",
    "crm_touchpoints_not_in_the_future", "crm_touchpoints_summary_bounded",
    "crm_touchpoints_summary_stated", "crm_lead_interests_vocabulary",
)

def _table(constraint: str) -> str:
    for table in ("crm_lead_interests", "crm_lead_sources", "crm_touchpoints", "crm_leads"):
        if constraint.startswith(table + "_"):
            return table
    raise AssertionError(constraint)


MUTATIONS = [
    *((f"{name} is dropped", f"ALTER TABLE plt01.{_table(name)} DROP CONSTRAINT {name}")
      for name in _CHECKS),
    # **A weakening, not a drop.** The bound is one-sided, so the case that catches its
    # removal is the touchpoint in the *future*; widening it to a day admits exactly the row
    # that case sends while still refusing nothing anybody writes.
    ("the forward-only bound on a touchpoint is widened to a day",
     "ALTER TABLE plt01.crm_touchpoints"
     " DROP CONSTRAINT crm_touchpoints_not_in_the_future;"
     " ALTER TABLE plt01.crm_touchpoints ADD CONSTRAINT"
     " crm_touchpoints_not_in_the_future"
     " CHECK (occurred_at <= recorded_at + interval '2 days')"),
    # **The other side of a biconditional**, which a one-way implication admits: with this
    # form a lead can carry a next action and no date, which is the first of the two cases.
    ("the next-action pairing becomes a one-way implication",
     "ALTER TABLE plt01.crm_leads DROP CONSTRAINT crm_leads_next_action_paired;"
     " ALTER TABLE plt01.crm_leads ADD CONSTRAINT crm_leads_next_action_paired"
     " CHECK (next_action_on IS NULL OR next_action IS NOT NULL)"),
    # The `coalesce`, which is what makes the retirement attribution bite on a NULL reason --
    # a CHECK passes on NULL, and every case in this build that sent a blank string instead
    # proved only the regex.
    ("the coalesce goes from the retirement attribution",
     "ALTER TABLE plt01.crm_lead_sources"
     " DROP CONSTRAINT crm_lead_sources_retirement_attributed;"
     " ALTER TABLE plt01.crm_lead_sources ADD CONSTRAINT"
     " crm_lead_sources_retirement_attributed CHECK ("
     " (retired_at IS NULL AND retired_by IS NULL AND retire_reason IS NULL"
     "  AND retire_correlation_id IS NULL)"
     " OR (retired_at IS NOT NULL AND retired_by IS NOT NULL"
     "     AND retire_reason ~ '[^[:space:]]'"
     "     AND retire_correlation_id IS NOT NULL))"),
    # The two unique rules. An index is not a constraint, so the mutation is `DROP INDEX`.
    ("two leads may be opened for one person",
     "DROP INDEX plt01.crm_leads_one_per_person"),
    ("two sources may share one key",
     "DROP INDEX plt01.crm_lead_sources_one_key"),
    # The pins. A NOT NULL is what makes a sibling CHECK bite and, under MATCH SIMPLE, a NULL
    # in a composite key skips the whole reference.
    ("a lead may name no person",
     "ALTER TABLE plt01.crm_leads ALTER COLUMN person_id DROP NOT NULL"),
    ("a touchpoint may have no recorded time",
     "ALTER TABLE plt01.crm_touchpoints ALTER COLUMN occurred_at DROP NOT NULL"),
    # A granted column nothing writes is an unattributed edit path -- MOD-016's
    # `cat_prices.effective_to` and MOD-019's three rota columns.
    ("a lead's person may be re-pointed by an UPDATE",
     "GRANT UPDATE (person_id) ON plt01.crm_leads TO veyro_cp_app"),
    ("a lead's age may be reset",
     "GRANT UPDATE (created_at) ON plt01.crm_leads TO veyro_cp_app"),
    ("a source may be re-keyed, which merges two histories",
     "GRANT UPDATE (source_key) ON plt01.crm_lead_sources TO veyro_cp_app"),
    # A sweep of one *kind* of reference is not a sweep: `owner_person_id` beside `person_id`
    # is exactly the shape that gets sampled.
    ("the owner reference leaves the tenant",
     "ALTER TABLE plt01.crm_leads DROP CONSTRAINT crm_leads_tenant_id_owner_person_id_fkey"),
    ("a touchpoint may cite a lead in another tenant",
     "ALTER TABLE plt01.crm_touchpoints"
     " DROP CONSTRAINT crm_touchpoints_tenant_id_lead_id_fkey"),
]


def main() -> int:
    caught: list[str] = []
    uncaught: list[str] = []
    notrun: list[str] = []
    for what, statement in MUTATIONS:
        done = subprocess.run(
            [str(VERIFY)], capture_output=True, text=True,
            env={**os.environ, "MUTATE": statement, "PSQL": PSQL})
        if done.returncode == 0:
            uncaught.append(what)
            continue
        lines = done.stdout.splitlines() + done.stderr.splitlines()
        line = next((ln for ln in lines if "CHECK 115" in ln), "")
        if not line:
            notrun.append(f"{what}: a check other than 115 answered")
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

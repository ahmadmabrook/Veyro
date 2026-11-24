"""Break ADR-0011's billing anchor on purpose, and watch its cases fail.

**A constraint nobody has broken on purpose is a constraint nobody has tested.**
`billing_anchor` decides which boundary a billing period falls on, so what the schema has to
hold is that the value is one of the two this build defines and that `calendar` is only ever
paired with a period that *has* a calendar boundary. Each of CHECK 78's three new cases names
the constraint that refused it, so a sibling answering fails on a clean database -- and these
mutations are what prove the cases reach their own rules at all.

**A weakening is caught only if the weakened rule admits the row**, so the boundary rule gets
a mutation per direction: admitting `weekly` is seen only by the weekly case, and refusing
`monthly` only by the permission case.

**And the permission case is what no refusal can see.** A boundary rule that refused every
period would make `calendar` unusable while every refusal case still passed; the mutation that
tightens it to "no calendar anchor at all" is caught by the ordinary monthly contract, which
is what ADM-CRM-06 sells.

**Two mutations are answered by a different check, and saying which is the point.** The column
list and the nullability are both CHECK 76's pins and the UPDATE grant is CHECK 77's, so a
sweep that demanded its own check would report a gap the schema does not have -- which costs
the same trust as missing one.

**It restores the database when it finishes.** `verify_db.sh` applies `MUTATE` after the build
with nothing putting it back, so the last mutation survives the sweep -- which cost a whole
backend suite once.

    PSQL="docker exec -i veyro-pg psql -U postgres" python3 -m tests.sql.sweep_billing_anchor
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

_TERMS = "plt01.mem_membership_terms"
_DOMAIN = "mem_membership_terms_billing_anchor"
_BOUNDARY = "mem_membership_terms_calendar_anchor_has_a_boundary"

MUTATIONS = [
    ("the anchor domain is dropped",
     f"ALTER TABLE {_TERMS} DROP CONSTRAINT {_DOMAIN}"),
    # Widened to admit a third value: only the domain case sends one, so this is its own
    # mutation rather than a restatement of the drop.
    ("a third anchor nobody implemented becomes storable",
     f"ALTER TABLE {_TERMS} DROP CONSTRAINT {_DOMAIN};"
     f" ALTER TABLE {_TERMS} ADD CONSTRAINT {_DOMAIN}"
     " CHECK (billing_anchor IN ('agreement_start', 'calendar', 'quarterly'))"),
    ("the calendar-boundary rule is dropped",
     f"ALTER TABLE {_TERMS} DROP CONSTRAINT {_BOUNDARY}"),
    # **The weekly direction.** A week has no calendar boundary this build may name, and only
    # the weekly case sees this -- the rule still refuses `one_off`.
    ("a weekly contract may be anchored on a calendar boundary",
     f"ALTER TABLE {_TERMS} DROP CONSTRAINT {_BOUNDARY};"
     f" ALTER TABLE {_TERMS} ADD CONSTRAINT {_BOUNDARY}"
     " CHECK (billing_anchor = 'agreement_start'"
     " OR billing_period IN ('weekly', 'monthly', 'quarterly', 'annual'))"),
    # **The permission direction.** Tightened until no contract may use a calendar anchor, the
    # column is decoration and every refusal case above still passes.
    ("the boundary rule is tightened until no calendar anchor is storable",
     f"ALTER TABLE {_TERMS} DROP CONSTRAINT {_BOUNDARY};"
     f" ALTER TABLE {_TERMS} ADD CONSTRAINT {_BOUNDARY}"
     " CHECK (billing_anchor = 'agreement_start')"),
    # The pins. A nullable anchor is the one this build has a rule for: nothing in 11,000 lines
    # of isolation suite had ever read `attnotnull` until MOD-016's sweep, and a NULL here
    # makes `first_period` answer about an anchor nobody declared.
    ("the anchor becomes nullable",
     f"ALTER TABLE {_TERMS} ALTER COLUMN billing_anchor DROP NOT NULL", "CHECK 76"),
    ("a second anchor column arrives undeclared",
     f"ALTER TABLE {_TERMS} ADD COLUMN billing_anchor_day integer", "CHECK 76"),
    # A granted column nothing writes is an unattributed edit path, and this one would re-date
    # every future renewal for every member on the contract.
    ("the anchor may be re-typed on live terms",
     f"GRANT UPDATE (billing_anchor) ON {_TERMS} TO veyro_cp_app", "CHECK 77"),
]


def main() -> int:
    caught: list[str] = []
    uncaught: list[str] = []
    notrun: list[str] = []
    for entry in MUTATIONS:
        what, statement = entry[0], entry[1]
        wanted = entry[2] if len(entry) > 2 else "CHECK 78"
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

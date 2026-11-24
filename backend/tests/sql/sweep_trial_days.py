"""Break ADR-0010 D7's trial rules on purpose, and watch CHECK 78 fail.

**A constraint nobody has broken on purpose is a constraint nobody has tested.** `trial_days`
is the one column that says a product is sold as a trial, so what the schema has to hold is
that the value is a short clock somebody meant and that it does not contradict the shape the
product is sold on -- and every case in CHECK 78 names the constraint that refused it, so a
sibling answering fails on a clean database. These mutations are what prove the cases reach
their own rules at all.

**Weakenings as well as drops**, because a case catches a weakening only if the weakened rule
*admits* the row. The bound has two sides and the shape rule names two kinds, so there is a
mutation per side and per conjunct: widening the floor to 0 is caught only by the zero case,
and dropping one kind from the shape rule is caught only by that kind's case.

**And the permission case is what no refusal can see.** The shape rule admits eight of
COM-01-R01's ten kinds, and a constraint that refused all ten would make the column unusable;
the mutation that tightens it to "no trial on any kind" is caught by the ordinary seven-day
trial.

**It restores the database when it finishes.** `verify_db.sh` applies `MUTATE` after the build
with nothing putting it back, so the last mutation survives the sweep -- which cost a whole
backend suite once.

    PSQL="docker exec -i veyro-pg psql -U postgres" python3 -m tests.sql.sweep_trial_days
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

MUTATIONS = [
    ("the trial-length bound is dropped",
     f"ALTER TABLE {_TERMS} DROP CONSTRAINT mem_membership_terms_trial_days_sane"),
    # **The floor, on its own.** A zero-day trial is the declared value nothing can mean, and
    # only the zero case sees this: widening the floor still refuses 91.
    ("a trial of no days becomes admissible",
     f"ALTER TABLE {_TERMS} DROP CONSTRAINT mem_membership_terms_trial_days_sane;"
     f" ALTER TABLE {_TERMS} ADD CONSTRAINT mem_membership_terms_trial_days_sane"
     " CHECK (trial_days IS NULL OR (trial_days >= 0 AND trial_days <= 90))"),
    # The ceiling, likewise: raising it admits exactly the row the 91 case sends.
    ("the ceiling is raised past a quarter",
     f"ALTER TABLE {_TERMS} DROP CONSTRAINT mem_membership_terms_trial_days_sane;"
     f" ALTER TABLE {_TERMS} ADD CONSTRAINT mem_membership_terms_trial_days_sane"
     " CHECK (trial_days IS NULL OR (trial_days >= 1 AND trial_days <= 3650))"),
    ("the shape rule is dropped",
     f"ALTER TABLE {_TERMS}"
     " DROP CONSTRAINT mem_membership_terms_trial_is_not_a_payment_plan"),
    # One conjunct at a time. With `installment` out, a trial paid in twelve instalments is
    # storable and `prepaid_days` still refuses -- which is the half a drop-only case cannot
    # tell apart.
    ("a trial may be sold as an instalment plan",
     f"ALTER TABLE {_TERMS}"
     " DROP CONSTRAINT mem_membership_terms_trial_is_not_a_payment_plan;"
     f" ALTER TABLE {_TERMS} ADD CONSTRAINT"
     " mem_membership_terms_trial_is_not_a_payment_plan"
     " CHECK (trial_days IS NULL OR membership_kind <> 'prepaid')"),
    ("a trial may be sold as a prepayment",
     f"ALTER TABLE {_TERMS}"
     " DROP CONSTRAINT mem_membership_terms_trial_is_not_a_payment_plan;"
     f" ALTER TABLE {_TERMS} ADD CONSTRAINT"
     " mem_membership_terms_trial_is_not_a_payment_plan"
     " CHECK (trial_days IS NULL OR membership_kind <> 'installment')"),
    # **The permission, which no refusal probe can see.** Tightened to refuse every shape, the
    # column is unusable and the ordinary seven-day trial is the only case that notices.
    ("the shape rule is tightened until no trial is storable",
     f"ALTER TABLE {_TERMS}"
     " DROP CONSTRAINT mem_membership_terms_trial_is_not_a_payment_plan;"
     f" ALTER TABLE {_TERMS} ADD CONSTRAINT"
     " mem_membership_terms_trial_is_not_a_payment_plan"
     " CHECK (trial_days IS NULL)"),
    # The pin. A column added to the table and not to CHECK 78's list is a column no sweep in
    # this file can see -- which is the hole the prefix-free sweeps were written for.
    # **These last two are answered by a different check, and saying which is the point.**
    # The column list is CHECK 76's pin and the UPDATE grant is CHECK 77's, so a sweep that
    # demanded its own check would report a gap the schema does not have -- which costs the
    # same trust as missing one. A mutation names the control that must answer it.
    ("a second trial column arrives undeclared",
     f"ALTER TABLE {_TERMS} ADD COLUMN trial_extended_days integer", "CHECK 76"),
    # A granted column nothing writes is an unattributed edit path, and this one would change
    # what a trial means for a live product while members are on one.
    ("the offered trial length may be re-typed on live terms",
     f"GRANT UPDATE (trial_days) ON {_TERMS} TO veyro_cp_app", "CHECK 77"),
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

"""Break `0031`'s rules on purpose, and watch CHECK 84 fail.

**A constraint nobody has broken on purpose is a constraint nobody has tested.** What this
schema has to hold is that a handover that does not balance states why, that the two opening
figures stay inside the bounds every money column here has, that a note is passed on by a shift
that has ended and is not blank, and that a bag's retained figure is a real amount.

**Weakenings as well as drops**, because a case catches a weakening only if the weakened rule
*admits* the row. Each bound has a mutation per side; the explained rule is a disjunction, so
there is one per clause -- including the `coalesce`, which only a NULL case can see and which
every "not blank" case in this repository missed until MOD-014 paid for it.

**Three of these are permissions**, which no refusal case can see: the explained rule tightened
until funding an empty drawer is refused (which is what the first draft of this migration
actually did, and what nine existing cases caught within the minute), the case-kind domain
narrowed back so a morning discrepancy cannot be recorded at all, and the insert-only opening
columns given an UPDATE grant so a handover can be restated after the fact.

**It restores the database when it finishes.** `verify_db.sh` applies `MUTATE` after the build
with nothing putting it back, so the last mutation survives the sweep -- which cost a whole
backend suite once.

    PSQL="docker exec -i veyro-pg psql -U postgres" python3 -m tests.sql.sweep_handover
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

_S = "plt01.led_cash_sessions"
_D = "plt01.led_deposits"
_C = "plt01.led_reconciliation_cases"
_EXPLAINED = "led_cash_sessions_opening_variance_explained"
_BOUNDED = "led_cash_sessions_opening_expected_bounded"
_REASON = "led_cash_sessions_opening_reason_not_blank"
_NOTE = "led_cash_sessions_handover_note_not_blank"
_NOTE_CLOSE = "led_cash_sessions_handover_note_needs_a_close"
_RETAINED = "led_deposits_retained_bounded"
_KIND = "led_reconciliation_cases_kind"

MUTATIONS = [
    # ---------------------------------------------------------------- the explained rule
    ("a handover need not state why it does not balance",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_EXPLAINED}"),
    # **The `coalesce` removed.** `length(btrim(NULL)) > 0` is NULL and a CHECK passes on NULL,
    # so without it the rule admits the exact row it exists to refuse -- and only the NULL case
    # sees it, which is why the blank case uses a tab and the unexplained case sends NULL.
    ("the coalesce is removed, so a NULL reason satisfies the rule",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_EXPLAINED};"
     f" ALTER TABLE {_S} ADD CONSTRAINT {_EXPLAINED}"
     " CHECK (opening_expected_minor IS NULL"
     "        OR opening_expected_minor = 0"
     "        OR opening_float_minor = opening_expected_minor"
     "        OR opening_variance_reason ~ '[^[:space:]]')"),
    # **The permission.** Tightened by taking the zero clause out, which is what the first
    # draft of this migration did: an empty drawer stores a zero expected figure against the
    # float it is being funded with, so every ordinary first open is refused while every
    # refusal case above still passes.
    ("the zero clause goes, so funding an empty drawer is refused",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_EXPLAINED};"
     f" ALTER TABLE {_S} ADD CONSTRAINT {_EXPLAINED}"
     " CHECK (opening_expected_minor IS NULL"
     "        OR opening_float_minor = opening_expected_minor"
     "        OR coalesce(opening_variance_reason, '') ~ '[^[:space:]]')"),
    # ---------------------------------------------------------------- the opening bound
    ("the opening balance is unbounded",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_BOUNDED}"),
    ("the opening balance has no ceiling",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_BOUNDED};"
     f" ALTER TABLE {_S} ADD CONSTRAINT {_BOUNDED}"
     " CHECK (opening_expected_minor IS NULL"
     "        OR opening_expected_minor >= -1000000000000)"),
    ("the opening balance has no floor",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_BOUNDED};"
     f" ALTER TABLE {_S} ADD CONSTRAINT {_BOUNDED}"
     " CHECK (opening_expected_minor IS NULL"
     "        OR opening_expected_minor <= 1000000000000)"),
    # ---------------------------------------------------------------- the two prose columns
    ("a handover reason may be whitespace",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_REASON}"),
    # **The banned form.** PostgreSQL's one-argument `btrim` strips spaces and nothing else, so
    # a single tab satisfies it -- which is why the case sends a tab rather than spaces.
    ("the handover reason falls back to the btrim form",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_REASON};"
     f" ALTER TABLE {_S} ADD CONSTRAINT {_REASON}"
     " CHECK (opening_variance_reason IS NULL"
     "        OR length(btrim(opening_variance_reason)) > 0)"),
    ("a handover note may be whitespace",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_NOTE}"),
    ("the handover note falls back to the btrim form",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_NOTE};"
     f" ALTER TABLE {_S} ADD CONSTRAINT {_NOTE}"
     " CHECK (handover_note IS NULL OR length(btrim(handover_note)) > 0)"),
    ("a shift that has not ended may hand over a note",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_NOTE_CLOSE}"),
    # ---------------------------------------------------------------- the retained figure
    ("a deposit's retained figure is unbounded",
     f"ALTER TABLE {_D} DROP CONSTRAINT {_RETAINED}"),
    ("the retained figure has no ceiling",
     f"ALTER TABLE {_D} DROP CONSTRAINT {_RETAINED};"
     f" ALTER TABLE {_D} ADD CONSTRAINT {_RETAINED} CHECK (retained_minor >= 0)"),
    ("the retained figure has no floor",
     f"ALTER TABLE {_D} DROP CONSTRAINT {_RETAINED};"
     f" ALTER TABLE {_D} ADD CONSTRAINT {_RETAINED}"
     " CHECK (retained_minor <= 1000000000000)"),
    # ---------------------------------------------------------------- the case kind
    ("the case-kind domain is dropped",
     f"ALTER TABLE {_C} DROP CONSTRAINT {_KIND}"),
    # **The second permission.** Narrowed back to what `0012` admitted, so a morning
    # discrepancy cannot be recorded at all while every refusal case still passes.
    ("handover_variance is taken back out of the domain",
     f"ALTER TABLE {_C} DROP CONSTRAINT {_KIND};"
     f" ALTER TABLE {_C} ADD CONSTRAINT {_KIND} CHECK (case_kind IN ("
     " 'settlement_line', 'settlement_total', 'cash_variance', 'deposit_variance',"
     " 'control_total'))"),
    # ---------------------------------------------------------------- the grants and the pins
    # **The third permission, read the other way.** The three opening columns are written by
    # the INSERT alone, so a handover cannot be restated once it is recorded -- an absence,
    # which is exactly what a later migration adds back.
    ("the opening figures are given an update grant",
     f"GRANT UPDATE (opening_expected_minor, opening_variance_reason) ON {_S}"
     " TO veyro_cp_app", "CHECK 83"),
    ("a column is added to the sessions table",
     f"ALTER TABLE {_S} ADD COLUMN handover_mood text", "CHECK 82"),
    ("a column is added to the deposits table",
     f"ALTER TABLE {_D} ADD COLUMN retained_mood text", "CHECK 82"),
    ("the retained figure stops being mandatory",
     f"ALTER TABLE {_D} ALTER COLUMN retained_minor DROP NOT NULL", "CHECK 82"),
]


def main() -> int:
    caught: list[str] = []
    uncaught: list[str] = []
    notrun: list[str] = []
    for entry in MUTATIONS:
        what, statement = entry[0], entry[1]
        # "CHECK 84", because MOD-018's cases live there. A harness copied from another
        # module's sweep and left with its default reports every catch as MUTERR, which is the
        # harness manufacturing the gaps it then reports -- MOD-027 paid for that once.
        # **Four of these name CHECK 82 or 83 rather than 84**, and that is the answer
        # being honest rather than the harness being lenient: a pin notices a column, a
        # nullability or a grant that moved, and a *case* notices a rule that stopped biting.
        # Reporting the pin's catch as a gap would be the harness manufacturing one.
        wanted = entry[2] if len(entry) > 2 else "CHECK 84"
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

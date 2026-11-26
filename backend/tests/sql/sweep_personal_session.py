"""Schema mutations against ADM-SCH-05's personal-training session. ADR-0019.

**The behaviour half is `tests/mutate_personal_session.py`; this is the schema.** Every rule
`0036` adds is broken on purpose and watched to fail -- the kind domain, both halves of the
biconditional against it, both conjuncts of the one-place rule, the nullability of the three
columns a class cites, the partial index, and the column pin.

**Six of these are weakenings rather than drops**, because a case catches a weakening only if
the weakened rule admits the row. Two matter most: tightening the biconditional back to "every
session names a template" leaves every refusal probe in CHECK 90d passing while ADM-SCH-05 can
book nobody, and putting NOT NULL back on `template_id` does the same thing from the other
side -- only the *permission* case sees either.

**And restoring the NOT NULLs is the mutation that proves the nullability is load-bearing.**
Dropping a NOT NULL is the usual direction and is caught by CHECK 88's set comparison; adding
one back is caught by the same comparison, and it is the one a reader would not think to try,
because it reads as making the schema stricter rather than as breaking a feature.

The harness restores the database at the end, because `verify_db.sh` applies `MUTATE` after
the build with nothing putting it back: the last mutation would otherwise survive the sweep,
which cost a whole backend suite once.

    PSQL="docker exec -i veyro-pg psql -U postgres" python3 -m tests.sql.sweep_personal_session
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

_S = "plt01.sch_sessions"
_CAME = "sch_sessions_class_came_from_a_template"
_ONE = "sch_sessions_personal_holds_one"

MUTATIONS = [
    # ---- the kind -------------------------------------------------------------------
    ("a session kind may be any word, so a third one nothing reads appears",
     f"ALTER TABLE {_S} DROP CONSTRAINT sch_sessions_kind", "CHECK 90"),
    ("the kind domain is tightened until a personal session cannot exist",
     f"ALTER TABLE {_S} DROP CONSTRAINT sch_sessions_kind,"
     f" ADD CONSTRAINT sch_sessions_kind CHECK (session_kind = 'class')",
     "CHECK 90"),
    ("the kind becomes nullable, so a session says neither",
     f"ALTER TABLE {_S} ALTER COLUMN session_kind DROP NOT NULL", "CHECK 88"),
    ("the kind is granted an UPDATE, so a class becomes a personal session",
     f"GRANT UPDATE (session_kind) ON {_S} TO veyro_cp_app", "CHECK 89"),
    # ---- what each kind cites -------------------------------------------------------
    ("a class need not say which rule version it came from",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_CAME}", "CHECK 90"),
    # **The weakening that only the permission case sees.** An implication rather than a
    # biconditional: a class still needs its three, and a personal session may now claim them
    # -- which puts it on `(rule_id, starts_at)`, so two coaches' PT at one instant collide.
    ("the biconditional becomes an implication, so a personal session may claim a rule",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_CAME},"
     f" ADD CONSTRAINT {_CAME}"
     f" CHECK (session_kind <> 'class'"
     f"        OR (template_id IS NOT NULL AND rule_id IS NOT NULL"
     f"            AND policy_id IS NOT NULL))",
     "CHECK 90"),
    ("the biconditional is tightened until every session names a template",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_CAME},"
     f" ADD CONSTRAINT {_CAME}"
     f" CHECK (template_id IS NOT NULL AND rule_id IS NOT NULL"
     f"        AND policy_id IS NOT NULL)",
     "CHECK 90"),
    # ---- the nullability, in the direction nobody tries -----------------------------
    ("the template is required again, so no personal session may be written",
     f"ALTER TABLE {_S} ALTER COLUMN template_id SET NOT NULL", "CHECK 88"),
    ("the rule is required again", f"ALTER TABLE {_S} ALTER COLUMN rule_id SET NOT NULL",
     "CHECK 88"),
    ("the policy is required again", f"ALTER TABLE {_S} ALTER COLUMN policy_id SET NOT NULL",
     "CHECK 88"),
    # ---- one place ------------------------------------------------------------------
    ("a personal session may hold a class's worth of people",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_ONE}", "CHECK 90"),
    # One conjunct at a time: a drop of the overbooking half is invisible to the capacity case.
    ("only the capacity half of the one-place rule survives",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_ONE},"
     f" ADD CONSTRAINT {_ONE}"
     f" CHECK (session_kind <> 'personal' OR capacity = 1)",
     "CHECK 90"),
    ("only the overbooking half survives",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_ONE},"
     f" ADD CONSTRAINT {_ONE}"
     f" CHECK (session_kind <> 'personal' OR overbook_places = 0)",
     "CHECK 90"),
    # **Tightened to two rather than onto every session**, because the latter is refused by
    # the committed seed -- which carries a class of ten thousand places -- so the mutation
    # never applies and the sweep reports MUTERR for a rule it did not test. Two places is a
    # rule the seed admits (it holds no personal session) and that CHECK 90d's *permission*
    # case is the only thing which sees: the canvas's one-coach-one-member hour stops being
    # writable while every refusal probe passes.
    ("the one-place rule is tightened to two, so the canvas's own booking is refused",
     f"ALTER TABLE {_S} DROP CONSTRAINT {_ONE},"
     f" ADD CONSTRAINT {_ONE}"
     f" CHECK (session_kind <> 'personal' OR (capacity = 2 AND overbook_places = 0))",
     "CHECK 90"),
    # ---- the index and the columns --------------------------------------------------
    ("a coach's personal sessions cannot be found over a window in one query",
     "DROP INDEX plt01.sch_sessions_personal_by_start", "CHECK 91"),
    ("the partial index becomes a whole one, so every class is in it too",
     "DROP INDEX plt01.sch_sessions_personal_by_start;"
     " CREATE INDEX sch_sessions_personal_by_start ON plt01.sch_sessions"
     " (tenant_id, starts_at)",
     "CHECK 91"),
    ("a second kind column appears beside the first",
     f"ALTER TABLE {_S} ADD COLUMN is_personal boolean", "CHECK 88"),
    ("this service may delete a session",
     f"GRANT DELETE ON {_S} TO veyro_cp_app", "CHECK 61"),
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

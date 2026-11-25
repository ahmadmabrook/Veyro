"""Schema mutations against ADM-SCH-06's capacity and containment rules. ADR-0018.

**The behaviour half is `tests/mutate_resource_capacity.py`; this is the schema.** Every rule
`0035` adds is broken on purpose and watched to fail -- the two capacity CHECKs, the kind rule
on containment, the per-attendee rule on a requirement, the three branches of the containment
trigger, the self-reference foreign key, the index, and each of the five pins check 91 carries.

**Three of these are weakenings rather than drops**, because a case catches a weakening only if
the weakened rule admits the row: tightening "a capacity is for a place" to "no resource carries
a capacity" leaves every refusal probe passing while the ordinary room ADM-SCH-06 draws becomes
unwritable, and only CHECK 90b's two *permission* cases see it.

**And the trigger's branches are mutated by replacing the function with one branch disabled**,
with its `RAISE` kept so the branch count still balances -- a dummy `RAISE` on the straight
path kills the seed and the sweep then reports MUTERR for a mutation it never ran.

The harness restores the database at the end, because `verify_db.sh` applies `MUTATE` after the
build with nothing putting it back: the last mutation would otherwise survive the sweep, which
cost a whole backend suite once.

    PSQL="docker exec -i veyro-pg psql -U postgres" python3 -m tests.sql.sweep_resource_capacity
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts" / "verify_db.sh"
PSQL = os.environ.get("PSQL", "docker exec -i veyro-pg psql -U postgres")

_RES = "plt01.sch_resources"
_REQ = "plt01.sch_template_requirements"

_FN_HEAD = (
    "CREATE OR REPLACE FUNCTION plt01.sch_resource_parent_is_a_space()"
    " RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $f$"
    " DECLARE parent_kind text; parent_location uuid; BEGIN"
    " IF NEW.parent_resource_id IS NULL THEN RETURN NEW; END IF;"
    " SELECT resource_kind, location_id INTO parent_kind, parent_location"
    " FROM plt01.sch_resources"
    " WHERE tenant_id = NEW.tenant_id AND resource_id = NEW.parent_resource_id;")
_FN_TAIL = " RETURN NEW; END; $f$"
_MISSING = (" IF %s parent_kind IS NULL THEN"
            " RAISE EXCEPTION 'that space does not exist'; END IF;")
_KIND = (" IF %s parent_kind NOT IN ('room', 'zone', 'court') THEN"
         " RAISE EXCEPTION 'equipment goes in a room, a zone or a court, and %% is a %%',"
         " NEW.parent_resource_id, parent_kind; END IF;")
_WHERE = (" IF %s parent_location IS DISTINCT FROM NEW.location_id THEN"
          " RAISE EXCEPTION 'this equipment and the space it is in are at different"
          " locations'; END IF;")


def _fn(skip: str) -> str:
    """The trigger body with exactly one branch disabled and its `RAISE` still counted."""
    return (_FN_HEAD
            + _MISSING % ("false AND" if skip == "missing" else "")
            + _KIND % ("false AND" if skip == "kind" else "")
            + _WHERE % ("false AND" if skip == "where" else "")
            + _FN_TAIL)


MUTATIONS = [
    # ---- the capacity ---------------------------------------------------------------
    ("a capacity may be stated for anything, so a coach holds ten people",
     f"ALTER TABLE {_RES} DROP CONSTRAINT sch_resources_capacity_is_a_space", "CHECK 90"),
    ("the capacity rule is tightened until no room may state one",
     f"ALTER TABLE {_RES} DROP CONSTRAINT sch_resources_capacity_is_a_space,"
     f" ADD CONSTRAINT sch_resources_capacity_is_a_space CHECK (capacity IS NULL)",
     "CHECK 90"),
    ("a space may hold nobody, or a city",
     f"ALTER TABLE {_RES} DROP CONSTRAINT sch_resources_capacity_sane", "CHECK 90"),
    ("the capacity band is tightened until the canvas's thirty is unwritable",
     f"ALTER TABLE {_RES} DROP CONSTRAINT sch_resources_capacity_sane,"
     f" ADD CONSTRAINT sch_resources_capacity_sane"
     f" CHECK (capacity IS NULL OR (capacity >= 1 AND capacity <= 10))",
     "CHECK 90"),
    # ---- the containment ------------------------------------------------------------
    ("anything goes inside a space, so a room sits in a room",
     f"ALTER TABLE {_RES} DROP CONSTRAINT sch_resources_parent_is_equipment", "CHECK 90"),
    ("the containment rule is tightened until no equipment may be placed",
     f"ALTER TABLE {_RES} DROP CONSTRAINT sch_resources_parent_is_equipment,"
     f" ADD CONSTRAINT sch_resources_parent_is_equipment"
     f" CHECK (parent_resource_id IS NULL)",
     "CHECK 90"),
    ("a space in another tenant may hold this one's equipment",
     f"ALTER TABLE {_RES} DROP CONSTRAINT sch_resources_parent_in_tenant", "CHECK 87"),
    ("the equipment of a room cannot be found in one query",
     "DROP INDEX plt01.sch_resources_by_parent", "CHECK 91"),
    # ---- the trigger, one branch at a time ------------------------------------------
    ("a space that does not exist is named by the foreign key rather than the trigger",
     _fn("missing"), "CHECK 90"),
    ("equipment may be placed inside a coach", _fn("kind"), "CHECK 90"),
    ("equipment may be placed in another club's space", _fn("where"), "CHECK 90"),
    # **Both of these are caught by a sweep this module did not have.** MOD-020's CHECK 96,
    # MOD-021's and MOD-022's each read `proconfig`, `prosecdef` and `tgenabled` over their own
    # prefix and `sch_%` was never added -- so ten trigger functions' pinned search path and
    # closing REVOKE were verified by nothing, which this mutation coming back uncaught is
    # what found. Adding the sweep then found `0017`'s own missing REVOKE.
    ("the containment trigger is disabled outright",
     f"ALTER TABLE {_RES} DISABLE TRIGGER sch_resources_parent_is_a_space", "CHECK 89"),
    ("the trigger function loses its pinned search_path",
     "ALTER FUNCTION plt01.sch_resource_parent_is_a_space() RESET search_path", "CHECK 89"),
    ("the trigger function becomes PUBLIC-executable",
     "GRANT EXECUTE ON FUNCTION plt01.sch_resource_parent_is_a_space() TO PUBLIC",
     "CHECK 89"),
    # ---- the requirement ------------------------------------------------------------
    ("a named resource may also be required per attendee",
     f"ALTER TABLE {_REQ}"
     f" DROP CONSTRAINT sch_template_requirements_per_attendee_is_anonymous", "CHECK 90"),
    ("the per-attendee rule is tightened until no requirement may be one each",
     f"ALTER TABLE {_REQ}"
     f" DROP CONSTRAINT sch_template_requirements_per_attendee_is_anonymous,"
     f" ADD CONSTRAINT sch_template_requirements_per_attendee_is_anonymous"
     f" CHECK (NOT per_attendee)",
     "CHECK 90"),
    ("per-attendee becomes nullable, so a requirement says neither",
     f"ALTER TABLE {_REQ} ALTER COLUMN per_attendee DROP NOT NULL", "CHECK 88"),
    # ---- the columns themselves -----------------------------------------------------
    ("a second capacity column appears beside the first",
     f"ALTER TABLE {_RES} ADD COLUMN floor_capacity integer", "CHECK 88"),
    ("the capacity is granted an UPDATE nothing writes",
     f"GRANT UPDATE (capacity) ON {_RES} TO veyro_cp_app", "CHECK 89"),
    ("the containment is granted an UPDATE nothing writes",
     f"GRANT UPDATE (parent_resource_id) ON {_RES} TO veyro_cp_app", "CHECK 89"),
    ("this service may delete a resource",
     f"GRANT DELETE ON {_RES} TO veyro_cp_app", "CHECK 61"),
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

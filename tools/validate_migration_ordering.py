#!/usr/bin/env python3
"""
Database-migration expand/contract ordering + record-completeness
validator (MOD-001, GOV-01-R06 — "Database-change policy/tooling").

Per `REQUIREMENTS.md` GOV-01-R06 and TSD §24.2 (verbatim): "Expand ->
migrate/backfill -> switch reads/writes -> contract. Destructive contract
happens only after all deployed versions stop using old shape... Every
migration records owner, expected lock/write impact, rollback/forward-fix
strategy and data validation query."

This tool is deliberately NOT wired to Alembic or any specific DB
migration framework: no actual product schema exists yet (R06's own
"OUT of scope" line), and CAPABILITIES.md's precedent for GOV-01-R01
explicitly defers concrete-tool selection to real implementation rather
than inventing a stack this planning turn didn't mandate. What TSD §24.2
actually requires right now — ordering discipline and a fixed record
schema — is fully checkable as a static lint over plain migration-record
files, with zero new dependencies (stdlib only), matching
`validate_baseline_binding.py`/`validate_capability_manifest.py`/
`validate_repo_skeleton.py`'s existing self-contained convention. A real
Alembic (or other) migration tool can be introduced later, at the point a
real schema exists, without needing to change this lint's contract.

## Record format

Each migration record is a `.yaml`-front-matter file (parsed with a
minimal `key: value` line scanner, not a YAML library — no new
dependency for 6 flat scalar fields):

    ---
    change_id: add_user_email_index
    phase: expand
    owner: jane@example.com
    lock_impact: CREATE INDEX CONCURRENTLY, no write lock
    rollback_strategy: DROP INDEX CONCURRENTLY IF EXISTS ix_users_email
    validation_query: SELECT count(*) FROM users WHERE email IS NULL
    ---

    Free-text description below the closing `---` is ignored by this tool.

`phase` must be one of `expand`, `migrate`, `switch`, `contract` (TSD
§24.2's own 4 stages — `migrate` covers "migrate/backfill"). The other 5
fields (`change_id` plus TSD's 4 named record fields: `owner`,
`lock_impact`, `rollback_strategy`, `validation_query`) are all required
and must be non-empty.

## Ordering rule

Per `change_id`, phases must appear across files (in filename-sorted
order, so callers use a numeric prefix like `0001_...`) in the sequence
expand -> migrate -> switch -> contract. A phase may repeat (multiple
expand files for one change are fine) but may not skip ahead or regress:
`contract` for a `change_id` that never saw a prior `switch` (or `switch`
before `migrate`, etc.) fails closed as `OUT_OF_ORDER_PHASE`, naming the
change_id, the phase found, and the phase it needed to see first — never
a silent partial pass.

This tool never writes to the checked tree — read-only, always.
"""
import argparse
import sys
from pathlib import Path

PHASE_ORDER = ["expand", "migrate", "switch", "contract"]
REQUIRED_FIELDS = ["change_id", "phase", "owner", "lock_impact", "rollback_strategy", "validation_query"]

DEFAULT_RECORDS_DIR = Path(__file__).resolve().parent.parent / "backend" / "migrations" / "records"


class RecordError(Exception):
    """A single migration record fails a structural or field check."""


def parse_front_matter(path: Path) -> dict[str, str]:
    """Parses the `---`-delimited front matter at the top of `path` into a
    flat dict of the 6 scalar fields this tool understands. Raises
    `RecordError` (never returns a partial dict) if the file has no
    front-matter block at all, so a malformed record is never silently
    treated as an empty-but-valid one."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise RecordError(f"{path.name}: MISSING_FRONT_MATTER — no opening '---' on line 1")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    raise RecordError(f"{path.name}: MISSING_FRONT_MATTER — no closing '---' found")


def validate_fields(name: str, fields: dict[str, str]) -> list[str]:
    """Returns every TSD §24.2 field missing or empty in `fields`, plus an
    invalid `phase` value — empty list means the record's fields are
    structurally complete (ordering is checked separately)."""
    problems = []
    for field in REQUIRED_FIELDS:
        if not fields.get(field, "").strip():
            problems.append(f"{name}: MISSING_REQUIRED_FIELD — '{field}' absent or empty")
    phase = fields.get("phase", "").strip()
    if phase and phase not in PHASE_ORDER:
        problems.append(
            f"{name}: INVALID_PHASE — '{phase}' is not one of {PHASE_ORDER}"
        )
    return problems


def check_ordering(records: list[tuple[str, dict[str, str]]]) -> list[str]:
    """`records` is a filename-sorted list of (name, fields) tuples for
    records that already passed `validate_fields`. Returns every
    out-of-order phase transition found, walking each change_id's own
    phase history independently so unrelated changes never interfere with
    each other's ordering."""
    problems = []
    highest_index: dict[str, int] = {}
    for name, fields in records:
        change_id = fields["change_id"]
        phase = fields["phase"]
        phase_index = PHASE_ORDER.index(phase)
        if change_id not in highest_index:
            if phase_index != 0:
                needed = PHASE_ORDER[0]
                problems.append(
                    f"{name}: OUT_OF_ORDER_PHASE — change_id '{change_id}' starts at "
                    f"'{phase}' but must start with '{needed}'"
                )
                continue
            highest_index[change_id] = 0
            continue
        last = highest_index[change_id]
        if phase_index == last:
            continue  # repeat of the current phase (e.g. a second expand file) — fine
        if phase_index == last + 1:
            highest_index[change_id] = phase_index
            continue
        needed = PHASE_ORDER[last + 1] if phase_index > last else PHASE_ORDER[last]
        problems.append(
            f"{name}: OUT_OF_ORDER_PHASE — change_id '{change_id}' jumps to '{phase}' "
            f"without a preceding '{needed}'"
        )
    return problems


def validate_directory(records_dir: Path) -> list[str]:
    """Runs the full check (field completeness, then ordering) over every
    `*.yaml` file directly inside `records_dir`, filename-sorted. Returns
    every problem found across all records; an empty list is PASS. An
    empty or absent directory is also PASS — no product schema exists
    yet, per this requirement's own explicitly-stated OUT-of-scope line."""
    if not records_dir.exists():
        return []
    problems: list[str] = []
    valid_records: list[tuple[str, dict[str, str]]] = []
    for path in sorted(records_dir.glob("*.yaml")):
        try:
            fields = parse_front_matter(path)
        except RecordError as exc:
            problems.append(str(exc))
            continue
        field_problems = validate_fields(path.name, fields)
        if field_problems:
            problems.extend(field_problems)
            continue
        valid_records.append((path.name, fields))
    problems.extend(check_ordering(valid_records))
    return problems


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Database-migration expand/contract ordering + record-completeness "
                     "validator (MOD-001, GOV-01-R06). Fails closed, naming every problem "
                     "record, if any migration record is incomplete or out of TSD "
                     "§24.2 phase order."
    )
    p.add_argument(
        "--records-dir", type=Path, default=DEFAULT_RECORDS_DIR,
        help=f"Directory of migration-record .yaml files to validate "
             f"(default: {DEFAULT_RECORDS_DIR}). Point this at a throwaway fixture "
             "directory for negative testing without touching the real tree.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    problems = validate_directory(args.records_dir)

    print("=" * 70)
    print("MOD-001 DATABASE-MIGRATION ORDERING + RECORD VALIDATOR")
    print("=" * 70)
    print(f"\nRecords dir checked: {args.records_dir}")

    if problems:
        print(f"\nBLOCKED: {len(problems)} problem(s) found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nPASS — every migration record is complete and phase-ordered correctly "
          "(or no records exist yet).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

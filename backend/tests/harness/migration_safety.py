"""Migration-safety harness — GOV-01-R02's testable 4-phase contract, proving
TSD §24.2 (verbatim):

    "Expand -> migrate/backfill -> switch reads/writes -> contract.
     Destructive contract happens only after all deployed versions stop
     using old shape. Large backfills are online/resumable jobs with
     progress and throttling; never a single deployment transaction.
     Every migration records owner, expected lock/write impact,
     rollback/forward-fix strategy and data validation query."

This module is deliberately independent of `tenant_isolation`/`authn` — no
RLS, no tenant context, no shared fixtures or roles. It exercises a single
synthetic table (`WIDGET`, schema `migration_harness`) through the classic
"retype a column safely" expand/contract pattern: a legacy integer
`status_code` evolving to a text `status`.

  expand   -> ALTER TABLE ... ADD COLUMN status text            (additive)
  migrate  -> batched, resumable backfill of status from status_code
  switch   -> ALTER COLUMN status SET NOT NULL, only once backfill is
              confirmed complete — the point reads/writes move to the new
              shape
  contract -> ALTER TABLE ... DROP COLUMN status_code            (destructive)

GOV-01-R02's own acceptance criterion is "the migration-safety harness runs
a synthetic expand/contract migration and detects a deliberately broken
rollback." The companion static ordering lint
(`tools/validate_migration_ordering.py`, GOV-01-R06, SCN-MOD001-070) already
proves the out-of-order-phase half; this module proves the other half:
`run_full_sequence` + `validate_post_contract` is the positive proof
(SCN-MOD001-022), and `rollback_contract_broken` + `verify_rollback` is the
negative one. `verify_rollback` never silently "passes" a broken rollback —
see its own docstring for the full, current list of what it compares
(column existence/set, `id`/`status_code`/`status` schema shape, the
table's constraint set, the live row count/duplicate-id check, and the
full row data). This was tightened twice following two independent
reviews — the original P1-1
(`knowledge/03-Modules/MOD-001/evidence/security/
GOV01-R02-MIGRATION-SAFETY-HARNESS-INDEPENDENT-REVIEW-2026-10-03.md`),
which proved, by direct execution, that an earlier version compared only
`status_code`'s *values*; and the 2026-10-03 re-review's NF-1/NF-3
(`knowledge/03-Modules/MOD-001/evidence/security/
GOV01-R02-MIGRATION-SAFETY-HARNESS-SECURITY-REREVIEW-2026-10-03.md`),
which proved, by direct execution, that the P1-1 fix still collapsed
duplicate rows through an id-keyed dict and never compared table
constraints, defaults, or the full column set.

The disposable integration suite now proves interrupted-batch progress,
resume, and invocation of the configured throttle hook, plus TSD §24.2 ¶2's
rolling-deploy (N-1) compatibility in the bounded form the "rolling-deploy
(N-1) compatibility" section below defines: an N-1 reader/writer that knows
only `status_code` and an N reader/writer that knows only `status`, both
exercised against one live schema across expand, backfill and switch with no
write lost or read stale from either side, plus a gated contract that is
refused while the N-1 version is still deployed. It does not prove
*concurrent* writers — the two versions' statements are interleaved
deterministically on one connection, never racing — and it does not run a
genuine previously-released application artifact; see that section's own
boundary note for exactly what remains unproven.

All data is synthetic (integer ids, synthetic status labels) — no real
member data, per this project's owner-reserved restriction.

**Non-disposable-database warning (C4, surfaced here per the 2026-10-03
security re-review round 2's NR2-10 — previously this notice lived only in
a bug-tracker file and a test-file comment, not here):** every function in
this module accepts any `psycopg` connection and performs destructive DDL
(`DROP COLUMN`, `ALTER TABLE`, etc.) against whatever table it is pointed
at. There is no technical safeguard in this module itself against being
run against a real, non-disposable database — safety today is entirely a
matter of caller discipline, i.e. always obtaining the connection through
`tests.harness.postgres.disposable_postgres()` (loopback-only, a
random per-run superuser password, force-removed on exit). Any future
importer of these functions must preserve that discipline itself.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

Conn = psycopg.Connection[TupleRow]


def one_row(cur: psycopg.Cursor[TupleRow]) -> TupleRow:
    row = cur.fetchone()
    if row is None:
        raise AssertionError("expected exactly one row, got none")
    return row


# --- named, stable, machine-checkable failures -------------------------------


class MigrationPhaseError(Exception):
    """Base for this harness's named migration-safety failures — never a bare
    assertion failure or generic exception, so callers can branch on `.code`."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class RollbackVerificationError(MigrationPhaseError):
    """Raised by `verify_rollback` when the post-rollback state disagrees with
    the pre-contract snapshot in any of the ways it now checks: the
    just-restored legacy column's data, either surviving column's schema
    shape (type, nullability, default) including `id`'s own shape, the
    table's own constraint set (primary key, unique, check), or a changed
    live row count/duplicate id — the GOV-01-R02 acceptance criterion's
    'detects a deliberately broken rollback', as a stable code string
    (`ROLLBACK_VERIFICATION_FAILED`), not a bare `AssertionError`. (Widened
    per the 2026-10-03 security re-review's NF-1 finding — see
    `verify_rollback`'s own docstring for exactly what is and is not
    compared.)"""

    def __init__(self, detail: str) -> None:
        super().__init__("ROLLBACK_VERIFICATION_FAILED", detail)


# --- the synthetic expand/contract fixture table ------------------------------


@dataclass(frozen=True)
class WidgetTable:
    schema: str = "migration_harness"
    name: str = "widget"

    @property
    def ident(self) -> sql.Identifier:
        return sql.Identifier(self.schema, self.name)

    def __str__(self) -> str:
        return f"{self.schema}.{self.name}"


WIDGET = WidgetTable()

# Legacy status_code -> new status text. Deliberately small and synthetic.
STATUS_BY_CODE: dict[int, str] = {0: "inactive", 1: "active", 2: "pending"}


def status_for_code(code: int) -> str:
    """Pure: the forward mapping the `migrate` phase and the post-contract
    validation query both rely on."""
    try:
        return STATUS_BY_CODE[code]
    except KeyError:
        raise ValueError(f"no status mapping for status_code={code}") from None


def code_for_status(status: str) -> int:
    """Pure: the reverse mapping a *correct* rollback must reproduce."""
    for code, name in STATUS_BY_CODE.items():
        if name == status:
            return code
    raise ValueError(f"no status_code mapping for status={status!r}")


def diff_int_maps(expected: dict[int, int], actual: dict[int, int]) -> dict[int, tuple[int, int | None]]:
    """Pure: every key in `expected` whose `actual` value differs or is
    missing, mapped to `(expected, actual_or_none)`. NOT currently called by
    `verify_rollback` or `validate_post_contract` (that mismatch detection
    builds its own two/three-column dict inline, since a single int map
    isn't the shape either function actually needs) — kept only because
    `unit/test_migration_safety_harness.py` exercises it as a pure, standalone
    comparison utility. Corrected 2026-10-03 (security re-review NF-4): this
    docstring previously overclaimed that `verify_rollback` shared this
    logic, which was already false before this session even started."""
    return {k: (v, actual.get(k)) for k, v in expected.items() if actual.get(k) != v}


def row_count_or_duplicate_violations(ids: list[int], expected_count: int) -> list[str]:
    """Pure: shared by `verify_rollback` and `validate_post_contract`. Detects
    a changed live row count and/or a duplicate id directly from the raw id
    list, rather than ever building an id-keyed dict first — that collapsing
    step is exactly what let a rollback which drops the primary key and
    duplicates rows (or a post-contract state with the same shape) report
    clean with a wrong `rows_checked`/row count (security re-review, NF-1/
    NF-3, probes N7-N9/V1)."""
    violations: list[str] = []
    live_count = len(ids)
    if live_count != expected_count:
        violations.append(f"row count changed: expected {expected_count}, found {live_count}")
    duplicate_ids = sorted(i for i, n in Counter(ids).items() if n > 1)
    if duplicate_ids:
        violations.append(f"duplicate id(s) found: {duplicate_ids}")
    return violations


# --- fixture setup (run as whatever connection the caller provides — this
# harness has no opinion on migration-role vs runtime-role separation; that is
# `.claude/rules/backend/database.md`'s concern for real product migrations) --


def create_schema_and_table(conn: Conn, table: WidgetTable = WIDGET) -> None:
    conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(table.schema)))
    conn.execute(
        sql.SQL("CREATE TABLE {} (id integer PRIMARY KEY, status_code integer NOT NULL)").format(
            table.ident
        )
    )


def seed_widgets(conn: Conn, count: int, table: WidgetTable = WIDGET) -> None:
    """Synthetic rows only — tens, not thousands, per this harness's scope."""
    codes = list(STATUS_BY_CODE)
    for widget_id in range(count):
        conn.execute(
            sql.SQL("INSERT INTO {} (id, status_code) VALUES (%s, %s)").format(table.ident),
            (widget_id, codes[widget_id % len(codes)]),
        )


# --- phase 1: expand -----------------------------------------------------------


def expand(conn: Conn, table: WidgetTable = WIDGET) -> None:
    """TSD §24.2 expand phase: additive only. The new column is nullable, so
    any reader/writer still using the old shape is unaffected."""
    conn.execute(sql.SQL("ALTER TABLE {} ADD COLUMN status text").format(table.ident))


# --- phase 2: migrate / backfill -----------------------------------------------


def migrate_backfill(
    conn: Conn, table: WidgetTable = WIDGET, batch_size: int = 4, throttle_s: float = 0.0
) -> int:
    """TSD §24.2 migrate/backfill phase: an online, resumable, throttled loop
    of small bounded batches — never one single deployment transaction. Each
    batch commits as its own transaction (real progress, not an all-or-nothing
    write), and an optional `throttle_s` pause between batches stands in for
    real rate limiting. Returns the total row count backfilled.

    The disposable integration suite interrupts after one committed batch,
    observes progress, then resumes without repeating rows and verifies that
    the configured throttle hook is invoked. It does not prove real elapsed
    rate limiting or concurrent writers. Rolling-deploy (N-1) compatibility
    *across* this phase is proven separately, by running this same loop over a
    table two app-shape versions are both writing to — see the rolling-deploy
    section below — not by this function's own interruption/resume test."""
    total = 0
    while True:
        with conn.transaction():
            rows = conn.execute(
                sql.SQL(
                    "SELECT id, status_code FROM {} WHERE status IS NULL ORDER BY id LIMIT %s"
                ).format(table.ident),
                (batch_size,),
            ).fetchall()
            if not rows:
                break
            for widget_id, status_code in rows:
                conn.execute(
                    sql.SQL("UPDATE {} SET status = %s WHERE id = %s").format(table.ident),
                    (status_for_code(status_code), widget_id),
                )
            total += len(rows)
        if throttle_s:
            time.sleep(throttle_s)
    return total


# --- phase 3: switch ------------------------------------------------------------


def switch(conn: Conn, table: WidgetTable = WIDGET) -> None:
    """TSD §24.2 switch phase: flips reads/writes to the new shape, once
    backfill is confirmed complete. Fails closed (`SWITCH_BEFORE_BACKFILL_
    COMPLETE`) if any row still lacks `status` — catching that here, rather
    than letting the `SET NOT NULL` below do it, gives a specific,
    named failure instead of a generic constraint-violation error."""
    remaining = one_row(
        conn.execute(sql.SQL("SELECT count(*) FROM {} WHERE status IS NULL").format(table.ident))
    )[0]
    if remaining:
        raise MigrationPhaseError(
            "SWITCH_BEFORE_BACKFILL_COMPLETE", f"{remaining} row(s) still have NULL status"
        )
    conn.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN status SET NOT NULL").format(table.ident))


# --- phase 4: contract (the one destructive phase) -----------------------------


def contract(conn: Conn, table: WidgetTable = WIDGET) -> None:
    """TSD §24.2 contract phase: destructive. Drops the legacy column. The
    static ordering lint (`tools/validate_migration_ordering.py`, GOV-01-R06)
    is what proves this never runs before its expand/migrate/switch
    predecessors in a real change's record sequence — not re-implemented
    here."""
    conn.execute(sql.SQL("ALTER TABLE {} DROP COLUMN status_code").format(table.ident))


# --- rolling-deploy (N-1) compatibility ----------------------------------------
#
# TSD §24.2 ¶2, verbatim: "Destructive contract happens only after all deployed
# versions stop using old shape." `.claude/rules/backend/database.md` control 9
# states the testable half: "Schema and application deployment ordering is
# verified compatible with at least the immediately prior deployed version, so
# a rolling deploy never runs new application code against an unmigrated schema
# or vice versa."
#
# Modeled here as the narrowest thing that can actually be falsified on the
# disposable database: two *shape-scoped* reader/writer pairs over the same
# synthetic WIDGET table. The N-1 pair's SQL names only `id`/`status_code`; the
# N pair's names only `id`/`status`. Neither can see the other's column at all,
# so "the old version still works" is a property of the live schema rather than
# of a flag the test sets, and a premature `contract` breaks the N-1 pair for
# the same reason it would break a real previous release — its statements no
# longer parse.
#
# `install_old_shape_compatibility_trigger` is what makes the expand window
# genuinely two-way: without it, an N-1 insert leaves `status` NULL (a stale
# read for the N version, and after `switch` a hard constraint failure), and an
# N insert leaves `status_code` NULL (a lost write from the N-1 version's
# view). It is additive, so it belongs to the expand phase, and it is dropped
# as part of old-shape retirement, immediately before the destructive contract.
#
# BOUNDARY — what this does NOT prove, and the one mandatory gap that cannot be
# closed inside this harness:
#   * Not concurrent. The two versions' statements are interleaved
#     deterministically on a single connection. No racing transactions, no lock
#     contention, no isolation-level or lost-update window is exercised here.
#   * Not a real artifact. The "N-1 version" is these functions, authored in
#     the same commit as the N ones — not the previously-released application
#     build. A product-grade N-1 proof needs the prior release's actual
#     artifact and a release/version registry identifying which version is
#     "previous supported", which is GOV-01-R05 release-evidence territory and
#     does not exist in this repository yet. That remains a mandatory blocker
#     for GOV-01-R06 certification; nothing below should be read as closing it.
#   * Not a migration engine. There is no real product schema, no Alembic
#     revision, and no deployment orchestration here — only this one synthetic
#     table.

APP_N_MINUS_1 = "N-1"  # the previous supported version: knows only `status_code`
APP_N = "N"  # the version being rolled out: knows only `status`

# The versions whose SQL still names the legacy column. Contract must wait for
# every one of these to be out of `deployed_versions`.
OLD_SHAPE_VERSIONS = frozenset({APP_N_MINUS_1})

COMPATIBILITY_TRIGGER = "widget_shape_sync"


def _status_from_code_case() -> sql.Composed:
    """`CASE NEW.status_code WHEN <code> THEN <status> ... END`, generated from
    `STATUS_BY_CODE` so the compatibility trigger cannot drift away from
    `status_for_code`. An unmapped code yields NULL, which `switch`'s
    `NOT NULL` then rejects — never a silently wrong status."""
    return sql.SQL("CASE NEW.status_code {} END").format(
        sql.SQL(" ").join(
            sql.SQL("WHEN {} THEN {}").format(sql.Literal(code), sql.Literal(status))
            for code, status in STATUS_BY_CODE.items()
        )
    )


def _code_from_status_case() -> sql.Composed:
    """The reverse of `_status_from_code_case`, generated from the same dict —
    the SQL counterpart of `code_for_status`."""
    return sql.SQL("CASE NEW.status {} END").format(
        sql.SQL(" ").join(
            sql.SQL("WHEN {} THEN {}").format(sql.Literal(status), sql.Literal(code))
            for code, status in STATUS_BY_CODE.items()
        )
    )


def install_old_shape_compatibility_trigger(conn: Conn, table: WidgetTable = WIDGET) -> None:
    """Additive (expand-phase) two-way shape sync, so an N-1 and an N
    reader/writer can both write the same row during the rolling-deploy
    window: a write that supplies only one shape's column has the other
    derived from it before the row lands. A write supplying both is left
    untouched, so the forward `migrate_backfill` and the fixture seed are
    unaffected. `BEFORE` + `NEW` assignment only — no recursive statement, and
    no `UPDATE OF <column>` list, so it never becomes a drop-blocking
    dependency on either column."""
    function = sql.Identifier(table.schema, COMPATIBILITY_TRIGGER)
    conn.execute(
        sql.SQL(
            "CREATE FUNCTION {fn}() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN "
            "  IF TG_OP = 'INSERT' THEN "
            "    IF NEW.status IS NULL AND NEW.status_code IS NOT NULL THEN "
            "      NEW.status := {to_status}; "
            "    ELSIF NEW.status_code IS NULL AND NEW.status IS NOT NULL THEN "
            "      NEW.status_code := {to_code}; "
            "    END IF; "
            "  ELSIF NEW.status_code IS DISTINCT FROM OLD.status_code THEN "
            "    NEW.status := {to_status}; "
            "  ELSIF NEW.status IS DISTINCT FROM OLD.status THEN "
            "    NEW.status_code := {to_code}; "
            "  END IF; "
            "  RETURN NEW; "
            "END $$"
        ).format(
            fn=function,
            to_status=_status_from_code_case(),
            to_code=_code_from_status_case(),
        )
    )
    conn.execute(
        sql.SQL(
            "CREATE TRIGGER {trg} BEFORE INSERT OR UPDATE ON {table}"
            " FOR EACH ROW EXECUTE FUNCTION {fn}()"
        ).format(trg=sql.Identifier(COMPATIBILITY_TRIGGER), table=table.ident, fn=function)
    )


def drop_old_shape_compatibility_trigger(conn: Conn, table: WidgetTable = WIDGET) -> None:
    """Retires the expand-window shape sync. Must happen before `contract`:
    the trigger body still names `NEW.status_code`, so leaving it installed
    across the drop would break every subsequent write to the table."""
    conn.execute(
        sql.SQL("DROP TRIGGER IF EXISTS {} ON {}").format(
            sql.Identifier(COMPATIBILITY_TRIGGER), table.ident
        )
    )
    conn.execute(
        sql.SQL("DROP FUNCTION IF EXISTS {}()").format(
            sql.Identifier(table.schema, COMPATIBILITY_TRIGGER)
        )
    )


def old_app_read(conn: Conn, table: WidgetTable = WIDGET) -> dict[int, int]:
    """The N-1 version's entire view of the table: `id -> status_code`. Names
    no new-shape column, so it fails the way a real previous release would the
    moment `contract` drops the legacy column."""
    rows = conn.execute(
        sql.SQL("SELECT id, status_code FROM {} ORDER BY id").format(table.ident)
    ).fetchall()
    return {int(i): int(c) for i, c in rows}


def old_app_write(
    conn: Conn, widget_id: int, status_code: int, table: WidgetTable = WIDGET
) -> None:
    """An N-1 insert: supplies only the legacy column, exactly as the previous
    release's own INSERT would."""
    conn.execute(
        sql.SQL("INSERT INTO {} (id, status_code) VALUES (%s, %s)").format(table.ident),
        (widget_id, status_code),
    )


def old_app_update(
    conn: Conn, widget_id: int, status_code: int, table: WidgetTable = WIDGET
) -> None:
    """An N-1 in-place update: touches only the legacy column."""
    conn.execute(
        sql.SQL("UPDATE {} SET status_code = %s WHERE id = %s").format(table.ident),
        (status_code, widget_id),
    )


def new_app_read(conn: Conn, table: WidgetTable = WIDGET) -> dict[int, str]:
    """The N version's entire view of the table: `id -> status`. Names no
    legacy column, so it keeps working across `contract` unchanged."""
    rows = conn.execute(
        sql.SQL("SELECT id, status FROM {} ORDER BY id").format(table.ident)
    ).fetchall()
    return {int(i): str(s) for i, s in rows}


def new_app_write(conn: Conn, widget_id: int, status: str, table: WidgetTable = WIDGET) -> None:
    """An N insert: supplies only the new column. Before `contract` this only
    satisfies `status_code NOT NULL` because the compatibility trigger derives
    it — which is precisely the expand-window property being proven."""
    conn.execute(
        sql.SQL("INSERT INTO {} (id, status) VALUES (%s, %s)").format(table.ident),
        (widget_id, status),
    )


def new_app_update(conn: Conn, widget_id: int, status: str, table: WidgetTable = WIDGET) -> None:
    """An N in-place update: touches only the new column."""
    conn.execute(
        sql.SQL("UPDATE {} SET status = %s WHERE id = %s").format(table.ident),
        (status, widget_id),
    )


def rolling_deploy_divergences(old_view: dict[int, int], new_view: dict[int, str]) -> list[str]:
    """Pure: every way the N-1 view and the N view of the same table disagree —
    a row one version can see and the other cannot (a lost write, in whichever
    direction), or a row whose `status` does not mean what its `status_code`
    means (a stale read). An empty list is the "no lost/stale writes"
    property; it is never vacuous, because a caller comparing two empty views
    would also have nothing to assert about row counts."""
    violations: list[str] = []
    only_old = sorted(set(old_view) - set(new_view))
    only_new = sorted(set(new_view) - set(old_view))
    if only_old or only_new:
        violations.append(f"id sets differ: only_N-1={only_old} only_N={only_new}")
    for widget_id in sorted(set(old_view) & set(new_view)):
        code = old_view[widget_id]
        expected = STATUS_BY_CODE.get(code)
        if new_view[widget_id] != expected:
            violations.append(
                f"id={widget_id}: N-1 sees status_code={code} (meaning {expected!r}),"
                f" N sees status={new_view[widget_id]!r}"
            )
    return violations


def contract_after_old_shape_retirement(
    conn: Conn, table: WidgetTable = WIDGET, *, deployed_versions: frozenset[str]
) -> None:
    """TSD §24.2 ¶2's ordering gate, fail-closed: refuses the destructive
    contract (`CONTRACT_BEFORE_OLD_SHAPE_RETIRED`) while any still-deployed
    version in `OLD_SHAPE_VERSIONS` reads or writes the legacy column, and
    performs no DDL at all in that case — the refusal must never leave a
    half-retired schema behind. Once the old shape is retired, it drops the
    expand-window compatibility trigger and then contracts, in that order, in
    one transaction so a failed contract restores the trigger.

    `deployed_versions` is supplied by the caller. This harness has no
    deployment registry and does not attempt to discover the real set — that
    is the GOV-01-R05/release-evidence gap recorded in this section's boundary
    note, and the reason this gate is a bounded proof of the *ordering rule*
    rather than of a real rolling deploy."""
    still_deployed = sorted(OLD_SHAPE_VERSIONS & deployed_versions)
    if still_deployed:
        raise MigrationPhaseError(
            "CONTRACT_BEFORE_OLD_SHAPE_RETIRED",
            f"version(s) {still_deployed} still use the legacy status_code column",
        )
    # One transaction: if `contract` fails (e.g. a dependent view, SQLSTATE
    # 2BP01), the trigger drop rolls back too, so N writes keep working.
    with conn.transaction():
        drop_old_shape_compatibility_trigger(conn, table)
        contract(conn, table)


# --- pre-contract ground truth, and the full positive sequence ----------------


@dataclass(frozen=True)
class ColumnShape:
    """A column's type/nullability/default shape — the schema-level ground
    truth `verify_rollback` and `validate_post_contract` check `id`,
    `status_code` and `status` against. Added per the independent review's
    P1-1 finding: a pure value/data comparison alone cannot catch a column
    restored with the wrong type (e.g. `text` instead of `integer`) or
    restored without its original `NOT NULL` constraint, since the *values*
    can still look correct in both cases. `default` was added per the
    2026-10-03 re-review's NF-1 finding (probe N10: a `DEFAULT 0` silently
    added to a restored column was not compared)."""

    data_type: str
    not_null: bool
    default: str | None


def _column_exists(conn: Conn, table: WidgetTable, column: str) -> bool:
    return bool(
        one_row(
            conn.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns"
                " WHERE table_schema = %s AND table_name = %s AND column_name = %s)",
                (table.schema, table.name, column),
            )
        )[0]
    )


def _column_shape(conn: Conn, table: WidgetTable, column: str) -> ColumnShape:
    """Caller must already know `column` exists — use `_column_exists` first,
    so a missing column is always reported as its own named failure rather
    than this function's `AssertionError` (no matching `pg_attribute` row)."""
    row = one_row(
        conn.execute(
            "SELECT a.atttypid::regtype::text, a.attnotnull,"
            " pg_get_expr(ad.adbin, ad.adrelid) FROM pg_attribute a"
            " LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum"
            " WHERE a.attrelid = %s::regclass AND a.attname = %s AND NOT a.attisdropped",
            (str(table), column),
        )
    )
    return ColumnShape(data_type=str(row[0]), not_null=bool(row[1]), default=row[2])


def _column_names(conn: Conn, table: WidgetTable) -> frozenset[str]:
    """The full set of live, non-dropped column names — lets `verify_rollback`
    and `validate_post_contract` catch an extra column a broken rollback
    introduced (security re-review, NF-1 probe N12), not just a regression on
    the two columns this harness otherwise names explicitly."""
    rows = conn.execute(
        "SELECT a.attname FROM pg_attribute a"
        " WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped",
        (str(table),),
    ).fetchall()
    return frozenset(str(r[0]) for r in rows)


def _table_constraints(conn: Conn, table: WidgetTable) -> frozenset[str]:
    """The table's own constraint set (primary key, unique, check), as the
    text Postgres itself renders for each one. A plain equality of this set
    against the pre-contract snapshot catches a dropped primary key (NF-1
    probe N7), an added `CHECK` (probe N11), and would equally catch an
    added `UNIQUE` constraint, without this harness needing to special-case
    `contype` values it never otherwise exercises. Corrected 2026-10-03
    (security re-review round 2, NR2-6): this query has no `contype`
    filter, so a foreign-key constraint is NOT excluded by it and would be
    detected the same way — this fixture table simply has none defined, so
    there is nothing to currently test that against. A constraint *rename*
    alone, with its definition unchanged, is not detected (names are never
    compared, only `pg_get_constraintdef` text)."""
    rows = conn.execute(
        "SELECT pg_get_constraintdef(oid, true) FROM pg_constraint WHERE conrelid = %s::regclass",
        (str(table),),
    ).fetchall()
    return frozenset(str(r[0]) for r in rows)


@dataclass(frozen=True)
class DataIntegritySnapshot:
    """Ground truth captured before the destructive contract phase runs, so
    both the post-sequence validation query and the rollback-verification
    step have something to check against without needing to resurrect the
    (by then dropped) legacy column. Carries both surviving columns' full
    row data (`status_code` is dropped by `contract` and must be restored
    by rollback; `status` must survive `contract` untouched), `id`'s and
    both columns' schema shape, the full live column-name set, and the
    table's own constraint set — so `verify_rollback`/`validate_post_contract`
    can detect a schema or constraint regression (or an extra column) as
    well as a data regression (independent review, P1-1; widened 2026-10-03
    per the security re-review's NF-1/NF-3 findings to also cover `id`'s own
    shape, defaults, constraints, and the full column set)."""

    rows: tuple[tuple[int, int, str], ...]  # (id, status_code, status)
    id_shape: ColumnShape
    status_code_shape: ColumnShape
    status_shape: ColumnShape
    column_names: frozenset[str]
    table_constraints: frozenset[str]


def capture_snapshot(conn: Conn, table: WidgetTable = WIDGET) -> DataIntegritySnapshot:
    rows = conn.execute(
        sql.SQL("SELECT id, status_code, status FROM {} ORDER BY id").format(table.ident)
    ).fetchall()
    return DataIntegritySnapshot(
        rows=tuple((int(i), int(c), str(s)) for i, c, s in rows),
        id_shape=_column_shape(conn, table, "id"),
        status_code_shape=_column_shape(conn, table, "status_code"),
        status_shape=_column_shape(conn, table, "status"),
        column_names=_column_names(conn, table),
        table_constraints=_table_constraints(conn, table),
    )


def _require_nonempty_snapshot(snapshot: DataIntegritySnapshot) -> None:
    """Independent review P2-1: an empty (zero-row) snapshot makes both
    `verify_rollback` and `validate_post_contract` vacuously "pass" no
    matter what the rollback/contract actually did (probe J). Refuse it
    with a named error instead of silently treating it as ground truth."""
    if not snapshot.rows:
        raise MigrationPhaseError(
            "EMPTY_SNAPSHOT",
            "pre-contract snapshot has zero rows; refusing to verify against degenerate ground truth",
        )


def run_full_sequence(
    conn: Conn, table: WidgetTable = WIDGET, batch_size: int = 4
) -> DataIntegritySnapshot:
    """Runs expand -> migrate/backfill -> switch, in that order, and returns
    the pre-contract snapshot. Deliberately stops short of `contract` — that
    is the one destructive phase TSD §24.2 gates separately, so callers run
    it as their own explicit, distinct step."""
    expand(conn, table)
    migrate_backfill(conn, table, batch_size)
    switch(conn, table)
    return capture_snapshot(conn, table)


@dataclass(frozen=True)
class ValidationResult:
    violations: list[str]


def validate_post_contract(
    conn: Conn, snapshot: DataIntegritySnapshot, table: WidgetTable = WIDGET
) -> ValidationResult:
    """SCN-MOD001-022's own post-migration validation query: confirms every
    row's `status` still matches what its (now-dropped) `status_code` meant
    per the captured pre-contract snapshot, that no row was gained, lost, or
    duplicated (a direct row-count/duplicate-id check, not an id-keyed dict
    that would silently collapse duplicates), that `id`'s and `status`'s own
    schema shape and the table's constraint set are unregressed, and that
    the legacy column is really gone. Widened 2026-10-03 (security re-review
    NF-3) — this previously had the same multiplicity-blind, shape-blind gap
    `verify_rollback` had (NF-1); probes V1/V2 showed it reporting a clean
    `violations == []` for a primary-key drop plus a duplicate row, and for
    a dropped `NOT NULL` on the surviving `status` column. Corrected
    2026-10-03 (security re-review round 2, NR2-3): a dropped or renamed
    `status` column previously leaked a bare `AssertionError` instead of
    reporting the named `COLUMN_SET_CHANGED` violation that already covers
    that case. That round's own fix and this docstring's prior wording both
    overclaimed `id` as fixed the same way — a dropped or renamed `id`
    still leaked a bare `UndefinedColumn`, because both row-query branches
    below selected `id` unconditionally regardless of whether it still
    existed. Corrected 2026-10-03 (security re-review round 3, NR3-1/
    NR3-2): the `id` path is fixed this round — when `id` is missing, the
    row-level checks are skipped entirely and whatever violation already
    fired above (`COLUMN_SET_CHANGED` naming `id`, when the legacy column
    is already gone, or `LEGACY_COLUMN_STILL_PRESENT`, when it is not) is
    returned instead, rather than running the row queries at all.
    Corrected 2026-10-03 (security re-review round 4, NR4-5a): the
    previous wording here named only `COLUMN_SET_CHANGED` as the reason
    the early return below fails closed — that is not the violation that
    fires when `status_code` is still present; the fail-closed property
    holds either way because *some* named violation fires in both
    branches, never specifically because of `COLUMN_SET_CHANGED`. Also
    fixed this round (NR4-1): a present-but-NULL-or-non-integer `id` value
    (e.g. its `NOT NULL` dropped and one row set to NULL, or `id` retyped
    to a type holding non-numeric content) previously leaked a bare
    `TypeError`/`ValueError` from the row-level `int()` conversions below
    instead of reporting a named `ID_VALUE_INVALID` violation — the same
    named-failure defect class as NR2-3/NR3-1, now guarded the same way
    `verify_rollback` already guards this exact shape."""
    _require_nonempty_snapshot(snapshot)
    violations: list[str] = []
    legacy_present = one_row(
        conn.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns"
            " WHERE table_schema = %s AND table_name = %s AND column_name = 'status_code')",
            (table.schema, table.name),
        )
    )[0]
    if legacy_present:
        violations.append("LEGACY_COLUMN_STILL_PRESENT")
    else:
        expected_columns = snapshot.column_names - {"status_code"}
        live_columns = _column_names(conn, table)
        if live_columns != expected_columns:
            violations.append(
                f"COLUMN_SET_CHANGED:expected={sorted(expected_columns)} got={sorted(live_columns)}"
            )
        for column, expected_shape in (("id", snapshot.id_shape), ("status", snapshot.status_shape)):
            if not _column_exists(conn, table, column):
                # COLUMN_SET_CHANGED already fired above for a missing/
                # renamed column; calling _column_shape unconditionally here
                # would hit its own `one_row` and raise a bare
                # AssertionError instead of a named violation (2026-10-03
                # security re-review round 2, NR2-3).
                continue
            shape = _column_shape(conn, table, column)
            if shape != expected_shape:
                violations.append(
                    f"{column.upper()}_SHAPE_REGRESSED:expected={expected_shape} got={shape}"
                )
        live_constraints = _table_constraints(conn, table)
        if live_constraints != snapshot.table_constraints:
            violations.append(
                "TABLE_CONSTRAINTS_CHANGED:"
                f"expected={sorted(snapshot.table_constraints)} got={sorted(live_constraints)}"
            )

    # A missing/renamed `id` already produced a named violation above:
    # `COLUMN_SET_CHANGED` (naming the missing column directly, e.g.
    # "expected=['id', 'status'] got=['status']") when the legacy column
    # is already gone, or `LEGACY_COLUMN_STILL_PRESENT` when it is not —
    # in which case the branch above never even inspects `id`'s presence.
    # Corrected 2026-10-03 (security re-review round 4, NR4-5a): this
    # comment previously named only `COLUMN_SET_CHANGED`, overstating
    # which violation is guaranteed here. Every row-level query below
    # selects `id` unconditionally, so continuing would leak a bare
    # `UndefinedColumn` instead of relying on one of those already-
    # collected violations — the same NR2-3 class one level up (2026-10-03
    # security re-review round 3, NR3-1). Skip the row-level checks
    # entirely rather than add a second, redundant violation tag.
    if not _column_exists(conn, table, "id"):
        if not violations:
            # NR4-4 (2026-10-03 security re-review round 4): defensive
            # only — not reachable through `capture_snapshot`'s real API
            # (which would itself fail first on a missing `id` via
            # `_column_shape`'s own `one_row`), but this closes the latent
            # fail-open path a hand-built `DataIntegritySnapshot` could
            # otherwise hit: this function must never return a clean `[]`
            # while `id` is actually missing, regardless of how that state
            # was reached.
            violations.append("ID_MISSING")
        return ValidationResult(violations)

    # A missing/renamed `status` already produced COLUMN_SET_CHANGED above;
    # selecting it unconditionally here would leak a bare `UndefinedColumn`
    # instead of a named violation — the same NR2-3 class one level down.
    # The id-only row-count/duplicate check still runs regardless, since it
    # needs no `status` value at all.
    status_column_exists = _column_exists(conn, table, "status")
    if status_column_exists:
        current_rows = conn.execute(
            sql.SQL("SELECT id, status FROM {} ORDER BY id").format(table.ident)
        ).fetchall()
    else:
        current_rows = [
            (r[0], None)
            for r in conn.execute(sql.SQL("SELECT id FROM {} ORDER BY id").format(table.ident)).fetchall()
        ]

    # NR4-1 (2026-10-03 security re-review round 4): `id` can exist but
    # hold a NULL or non-integer-content value (its `NOT NULL` dropped and
    # one row set to NULL; or `id` retyped to a type holding non-numeric
    # content) — a bare `int()` here would leak a `TypeError`/`ValueError`
    # instead of a named violation, the same NR2-3/NR3-1 defect class.
    # Mirrors `verify_rollback`'s own NULL-id check and int-conversion
    # `try` for this exact shape. A row whose `id` fails this check is
    # excluded from `ids`/`current` below rather than crashing the whole
    # validation — the row-count/duplicate check and `ROW_SET_CHANGED`
    # will independently flag the resulting shortfall.
    ids: list[int] = []
    current: dict[int, str] = {}
    for raw_id, status in current_rows:
        if raw_id is None:
            violations.append("ID_VALUE_INVALID:NULL id found")
            continue
        try:
            widget_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            violations.append(f"ID_VALUE_INVALID:non-integer id {raw_id!r}: {exc}")
            continue
        ids.append(widget_id)
        if status_column_exists:
            # A NULL `status` here becomes the literal string "None", but
            # that can never equal a real mapped status ("inactive"/
            # "active"/"pending" — see `STATUS_BY_CODE`), so it always
            # surfaces as a genuine `STATUS_MISMATCH` below rather than
            # ever being silently treated as a valid/matching value.
            # Confirmed as part of NR4-1 rather than added as a redundant
            # check: this path was already fail-closed.
            current[widget_id] = str(status)

    violations.extend(row_count_or_duplicate_violations(ids, len(snapshot.rows)))

    if status_column_exists:
        expected = {widget_id: status_for_code(code) for widget_id, code, _ in snapshot.rows}
        if set(current) != set(expected):
            violations.append("ROW_SET_CHANGED")
        mismatched = {
            wid: (exp, current.get(wid)) for wid, exp in expected.items() if current.get(wid) != exp
        }
        if mismatched:
            violations.append(f"STATUS_MISMATCH:{mismatched}")
    return ValidationResult(violations)


# --- rollback for the contract phase, and its deliberately-broken twin --------


def _backfill_status_code(conn: Conn, table: WidgetTable, batch_size: int, *, corrupt: bool) -> None:
    while True:
        with conn.transaction():
            rows = conn.execute(
                sql.SQL(
                    "SELECT id, status FROM {} WHERE status_code IS NULL ORDER BY id LIMIT %s"
                ).format(table.ident),
                (batch_size,),
            ).fetchall()
            if not rows:
                break
            for widget_id, status in rows:
                # Broken variant: every row gets the same wrong constant
                # instead of the real reverse mapping — never the correct
                # value, so a genuinely-restored column can never match it.
                value = 0 if corrupt else code_for_status(status)
                conn.execute(
                    sql.SQL("UPDATE {} SET status_code = %s WHERE id = %s").format(table.ident),
                    (value, widget_id),
                )


def rollback_contract(conn: Conn, table: WidgetTable = WIDGET, batch_size: int = 4) -> None:
    """Real rollback for the (only destructive) contract phase: re-adds the
    dropped column and correctly backfills it back from `status`, batched the
    same way the forward `migrate` phase is. This harness has no rollback for
    `switch` or `expand` — both are additive/non-destructive, so TSD §24.2's
    rollback concern does not apply to them the way it does to `contract`;
    building one for those phases is out of scope here (security re-review,
    NF-6)."""
    conn.execute(sql.SQL("ALTER TABLE {} ADD COLUMN status_code integer").format(table.ident))
    _backfill_status_code(conn, table, batch_size, corrupt=False)
    conn.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN status_code SET NOT NULL").format(table.ident))


def rollback_contract_broken(conn: Conn, table: WidgetTable = WIDGET, batch_size: int = 4) -> None:
    """Deliberately-broken rollback for the negative proof (GOV-01-R02's own
    acceptance criterion): re-adds the column but backfills every row with
    the same wrong constant instead of correctly reversing the forward
    mapping. `verify_rollback` must never report this as having passed."""
    conn.execute(sql.SQL("ALTER TABLE {} ADD COLUMN status_code integer").format(table.ident))
    _backfill_status_code(conn, table, batch_size, corrupt=True)
    conn.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN status_code SET NOT NULL").format(table.ident))


@dataclass(frozen=True)
class RollbackVerificationResult:
    rows_checked: int


def verify_rollback(
    conn: Conn, snapshot: DataIntegritySnapshot, table: WidgetTable = WIDGET
) -> RollbackVerificationResult:
    """Compares the just-restored `status_code` column, the surviving
    `status` column, `id` itself, the table's own constraint set, and the
    live row count/id set, against the pre-contract snapshot captured before
    the destructive phase ran. Raises `RollbackVerificationError` (code
    `ROLLBACK_VERIFICATION_FAILED`) the moment any of the following disagree
    with the snapshot: `status_code` or `status` is missing; the live
    column set gained or lost a column; any of `id`/`status_code`/`status`'s
    type, nullability or default has regressed; the table's primary
    key/unique/check constraint set changed; the live row count changed or
    any `id` is duplicated; or any surviving row's `status_code` or `status`
    value disagrees. This is GOV-01-R02's 'detects a deliberately broken
    rollback' acceptance criterion, made a named, stable, machine-checkable
    failure rather than a bare assertion or a leaked database-driver
    exception. Returns a result (never silently "passes") only when every
    check above agrees with the snapshot, and `rows_checked` is always the
    live row count actually compared — never the snapshot's own row count,
    which could disagree with it precisely in the cases this function must
    catch.

    Tightened twice. Per the original independent review's P1-1 finding: an
    earlier version only selected and compared `status_code`'s values, so it
    reported a clean result for a `status_code` restored with the wrong type
    or without `NOT NULL`, and for a rollback that clobbered or dropped the
    surviving `status` column entirely. Per the 2026-10-03 security
    re-review's NF-1 finding: the fix above still built an id-keyed dict
    before comparing, so a rollback that dropped the primary key and then
    duplicated rows (12 -> 13 or 12 -> 24) silently collapsed back down to
    the expected id set and reported clean with a wrong `rows_checked`;
    neither table-level constraints, column defaults, the full column set,
    nor `id`'s own shape were compared at all. Deliberately out of scope
    even now: any schema object beyond this one table (e.g. indexes,
    triggers) — not claimed as covered by this docstring or the checks
    above. Corrected 2026-10-03 (security re-review round 2, NR2-6): this
    docstring previously called foreign keys "deliberately out of scope",
    which overstated the exclusion — `_table_constraints`' query has no
    `contype` filter, so an added FK constraint *is* detected the same way
    a CHECK/UNIQUE one is; this fixture table simply has none to compare
    against. Disclosed residuals that still report clean (NR2-5, same
    re-review round): an identity-column attribute (`attidentity`), a
    collation change (`attcollation`), a constraint *rename* alone with its
    definition unchanged (names are never compared, only definition text),
    and an identical-definition duplicate constraint added under a new name
    (the `frozenset` collapses it, so the duplicate is invisible). One more,
    disclosed 2026-10-03 (security re-review round 3, NR3-6): `_column_shape`'s
    `atttypid::regtype::text` cast drops the type's typmod, so a `varchar(n)`
    length change (e.g. `varchar(50)` widened to `varchar(100)`) would go
    undetected — both render identically as `character varying`. No column
    in this fixture currently has a typmod, so this is a latent gap, not a
    live one."""
    _require_nonempty_snapshot(snapshot)

    for column in ("status_code", "status"):
        if not _column_exists(conn, table, column):
            raise RollbackVerificationError(f"column {column!r} is missing after rollback")

    live_columns = _column_names(conn, table)
    if live_columns != snapshot.column_names:
        raise RollbackVerificationError(
            f"column set changed after rollback: expected {sorted(snapshot.column_names)}, "
            f"got {sorted(live_columns)}"
        )

    for column, expected_shape in (
        ("id", snapshot.id_shape),
        ("status_code", snapshot.status_code_shape),
        ("status", snapshot.status_shape),
    ):
        shape = _column_shape(conn, table, column)
        if shape != expected_shape:
            raise RollbackVerificationError(
                f"{column} column shape regressed: expected {expected_shape}, got {shape}"
            )

    live_constraints = _table_constraints(conn, table)
    if live_constraints != snapshot.table_constraints:
        raise RollbackVerificationError(
            "table constraints changed after rollback: "
            f"expected {sorted(snapshot.table_constraints)}, got {sorted(live_constraints)}"
        )

    raw_rows = conn.execute(
        sql.SQL("SELECT id, status_code, status FROM {} ORDER BY id").format(table.ident)
    ).fetchall()

    rows: list[tuple[int, int, str]] = []
    for widget_id, status_code, status in raw_rows:
        if widget_id is None:
            raise RollbackVerificationError("row with NULL id found after rollback")
        if status_code is None or status is None:
            raise RollbackVerificationError(
                f"row id={widget_id} has NULL status_code or status after rollback"
            )
        try:
            rows.append((int(widget_id), int(status_code), str(status)))
        except (TypeError, ValueError) as exc:
            raise RollbackVerificationError(
                f"row id={widget_id} has a non-integer status_code after rollback: {exc}"
            ) from None

    # Detected directly from the raw id list, before any id-keyed dict is
    # built — that collapsing step is exactly what let a PK-dropped,
    # row-duplicated rollback report clean (security re-review, NF-1).
    count_or_dup_violations = row_count_or_duplicate_violations([r[0] for r in rows], len(snapshot.rows))
    if count_or_dup_violations:
        raise RollbackVerificationError("; ".join(count_or_dup_violations))

    current = {wid: (code, status) for wid, code, status in rows}
    expected = {widget_id: (code, status) for widget_id, code, status in snapshot.rows}
    row_set_changed = set(current) != set(expected)
    mismatches = {wid: (exp, current.get(wid)) for wid, exp in expected.items() if current.get(wid) != exp}
    if mismatches or row_set_changed:
        raise RollbackVerificationError(
            f"{len(mismatches)} row(s) mismatched after rollback "
            f"(row_set_changed={row_set_changed}); sample={dict(list(mismatches.items())[:5])}"
        )
    return RollbackVerificationResult(rows_checked=len(rows))

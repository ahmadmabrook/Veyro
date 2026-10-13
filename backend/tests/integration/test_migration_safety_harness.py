"""GOV-01-R02 migration-safety harness against a real, disposable Postgres.

SCN-MOD001-022  a synthetic 4-phase migration (expand -> migrate/backfill ->
                switch -> contract) run against a disposable schema; each
                phase completes in order and a post-migration validation
                query confirms data integrity.
GOV-01-R02      acceptance criterion: "the migration-safety harness runs a
                synthetic expand/contract migration and detects a
                deliberately broken rollback" — proven here as the negative
                companion to SCN-MOD001-022, distinct from the static
                out-of-order-phase lint (`tools/validate_migration_ordering.py`,
                GOV-01-R06, SCN-MOD001-070), which is not reimplemented here.
GOV-01-R06      TSD §24.2 ¶2 ("destructive contract happens only after all
                deployed versions stop using old shape") and
                `.claude/rules/backend/database.md` control 9 ("rolling-deploy
                compatibility is tested against the previous supported
                version") — the N-1/N coexistence section at the end of this
                file. Bounded: deterministic interleaving of two shape-scoped
                reader/writer pairs, not concurrent writers and not a real
                previously-released artifact (see
                `migration_safety.py`'s rolling-deploy boundary note).

Self-contained: this file defines its own fixtures directly from
`tests.harness.postgres.disposable_postgres()` and does not import or depend
on `tests/integration/conftest.py` (that conftest wires the tenant-isolation/
authn critical-slice harnesses specifically) — zero coupling to that shared
state, per this task's own scope boundary. Every test gets its own disposable
schema inside one shared disposable Postgres container for the module.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from tests.harness import migration_safety
from tests.harness.migration_safety import (
    APP_N,
    APP_N_MINUS_1,
    COMPATIBILITY_TRIGGER,
    WIDGET,
    Conn,
    MigrationPhaseError,
    RollbackVerificationError,
    WidgetTable,
    capture_snapshot,
    contract,
    contract_after_old_shape_retirement,
    create_schema_and_table,
    expand,
    install_old_shape_compatibility_trigger,
    migrate_backfill,
    new_app_read,
    new_app_update,
    new_app_write,
    old_app_read,
    old_app_update,
    old_app_write,
    rollback_contract,
    rollback_contract_broken,
    rolling_deploy_divergences,
    run_full_sequence,
    seed_widgets,
    status_for_code,
    switch,
    validate_post_contract,
    verify_rollback,
)
from tests.harness.postgres import DisposablePostgres, disposable_postgres

ROW_COUNT = 12  # tens, not thousands — CI-smoke-load budget, per this task's scope
BATCH_SIZE = 4

# Disclosure (independent review, P2-5): `migration_safety.py`'s own functions
# accept any `psycopg` connection and this file's `table` fixture runs
# `DROP SCHEMA ... CASCADE` against it. The harness itself has no technical
# safeguard against being pointed at a non-disposable database — safety here
# comes entirely from `pg`/`admin` below always going through
# `disposable_postgres()` (loopback-only, random per-run superuser password,
# force-removed on exit). Any future caller of these harness functions must
# preserve that discipline itself; this was deliberately not re-engineered
# into the harness in this bounded fix, per the review's own scope.


@pytest.fixture(scope="module")
def pg() -> Iterator[DisposablePostgres]:
    with disposable_postgres() as instance:
        yield instance


@pytest.fixture(scope="module")
def admin(pg: DisposablePostgres) -> Iterator[Conn]:
    with psycopg.connect(pg.superuser_dsn, autocommit=True) as conn:
        yield conn


@pytest.fixture
def table(admin: Conn) -> Iterator[WidgetTable]:
    """Fresh `migration_harness.widget` schema per test, seeded with
    `ROW_COUNT` synthetic rows — isolated so one test's phase progression
    never leaks into another's."""
    admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(WIDGET.schema)))
    create_schema_and_table(admin, WIDGET)
    seed_widgets(admin, ROW_COUNT, WIDGET)
    yield WIDGET
    admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(WIDGET.schema)))


def _column_exists(admin: Conn, table: WidgetTable, column: str) -> bool:
    row = admin.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns"
        " WHERE table_schema = %s AND table_name = %s AND column_name = %s)",
        (table.schema, table.name, column),
    ).fetchone()
    assert row is not None
    return bool(row[0])


_COLUMN_SET_CHANGED_RE = re.compile(r"^COLUMN_SET_CHANGED:expected=(\[.*?\]) got=(\[.*?\])$")


def _parse_column_set_changed(violation: str) -> tuple[list[str], list[str]]:
    """NR4-2 (2026-10-03 security re-review round 4): parses the exact
    `expected=[...]`/`got=[...]` column lists out of a `COLUMN_SET_CHANGED`
    violation string, so callers can assert the precise set difference
    (which column is genuinely absent/present) instead of a substring
    check — `"id" in violation`/`"status" in violation` are vacuous, since
    both substrings appear in the literal word "expected" and in a renamed
    column's own new name (`id2`, `status2`)."""
    match = _COLUMN_SET_CHANGED_RE.match(violation)
    assert match is not None, violation
    expected = ast.literal_eval(match.group(1))
    got = ast.literal_eval(match.group(2))
    assert isinstance(expected, list) and isinstance(got, list), violation
    return expected, got


def _is_not_null(admin: Conn, table: WidgetTable, column: str) -> bool:
    row = admin.execute(
        "SELECT a.attnotnull FROM pg_attribute a"
        " WHERE a.attrelid = %s::regclass AND a.attname = %s AND NOT a.attisdropped",
        (str(table), column),
    ).fetchone()
    assert row is not None
    return bool(row[0])


# --- SCN-MOD001-022 positive: full sequence + validation query ----------------


def test_scn022_each_phase_completes_in_order(admin: Conn, table: WidgetTable) -> None:
    """Each of the 4 phases, observed individually in order: expand adds a
    nullable column, migrate backfills it, switch enforces NOT NULL, contract
    drops the legacy column — exactly TSD §24.2's sequence."""
    expand(admin, table)
    assert _column_exists(admin, table, "status")
    assert not _is_not_null(admin, table, "status")

    # switch before backfill must fail closed — proves the ordering is real,
    # not just a documentation convention this harness happens to follow.
    with pytest.raises(MigrationPhaseError) as exc_info:
        switch(admin, table)
    assert exc_info.value.code == "SWITCH_BEFORE_BACKFILL_COMPLETE"

    backfilled = migrate_backfill(admin, table, batch_size=BATCH_SIZE)
    assert backfilled == ROW_COUNT
    remaining_null = admin.execute(
        sql.SQL("SELECT count(*) FROM {} WHERE status IS NULL").format(table.ident)
    ).fetchone()
    assert remaining_null == (0,)

    switch(admin, table)
    assert _is_not_null(admin, table, "status")

    contract(admin, table)
    assert not _column_exists(admin, table, "status_code")


class _BackfillInterrupted(Exception):
    pass


def test_migrate_backfill_resumes_after_interruption_and_reaches_throttle_hook(
    admin: Conn, table: WidgetTable, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TSD §24.2 ¶3 (online/resumable/progress/throttling), bounded: the
    throttle hook runs only after a batch's own transaction commits, so
    interrupting from inside it simulates a crash between batches. Proves the
    first batch's progress is durable, the throttle hook is genuinely reached
    with the configured value, and a re-run resumes without re-doing or
    losing work. Does not cover concurrent writers or N-1 rolling deploys."""
    expand(admin, table)
    throttle_calls: list[float] = []

    def interrupting_sleep(seconds: float) -> None:
        throttle_calls.append(seconds)
        raise _BackfillInterrupted

    monkeypatch.setattr(migration_safety, "time", SimpleNamespace(sleep=interrupting_sleep))
    with pytest.raises(_BackfillInterrupted):
        migrate_backfill(admin, table, batch_size=BATCH_SIZE, throttle_s=0.25)
    assert throttle_calls == [0.25]

    # Exactly one bounded batch committed before the interruption.
    done_ids = [
        r[0]
        for r in admin.execute(
            sql.SQL("SELECT id FROM {} WHERE status IS NOT NULL ORDER BY id").format(table.ident)
        ).fetchall()
    ]
    assert done_ids == list(range(BATCH_SIZE))

    monkeypatch.undo()
    resumed = migrate_backfill(admin, table, batch_size=BATCH_SIZE)
    assert resumed == ROW_COUNT - BATCH_SIZE  # only the remaining rows: no duplicate work

    rows = admin.execute(
        sql.SQL("SELECT id, status_code, status FROM {} ORDER BY id").format(table.ident)
    ).fetchall()
    assert [r[0] for r in rows] == list(range(ROW_COUNT))  # no loss, no duplicates
    assert all(status == status_for_code(code) for _, code, status in rows)


def test_scn022_full_sequence_passes_post_migration_validation(
    admin: Conn, table: WidgetTable
) -> None:
    """The positive proof: run the whole sequence through the harness's own
    helpers, then confirm the post-contract validation query finds zero
    integrity violations."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    assert len(snapshot.rows) == ROW_COUNT

    contract(admin, table)

    result = validate_post_contract(admin, snapshot, table)
    assert result.violations == []


# --- GOV-01-R02 negative: deliberately-broken rollback is detected ------------


def test_rollback_verification_detects_a_deliberately_broken_rollback(
    admin: Conn, table: WidgetTable
) -> None:
    """GOV-01-R02's own acceptance criterion: a rollback that re-adds the
    dropped column but backfills it with a wrong, constant mapping must be
    caught — never reported as a clean rollback."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    rollback_contract_broken(admin, table, batch_size=BATCH_SIZE)

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "mismatched" in exc_info.value.detail


def test_rollback_verification_passes_a_genuinely_correct_rollback(
    admin: Conn, table: WidgetTable
) -> None:
    """Boundary case proving the detector is real, not a check that always
    fails: a correctly-implemented rollback (re-add + correct reverse
    backfill) must verify clean."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    result = verify_rollback(admin, snapshot, table)
    assert result.rows_checked == ROW_COUNT
    assert _column_exists(admin, table, "status_code")


# --- P1-1 (independent review): schema regressions and data loss that a
# pure value diff on `status_code` alone previously reported as clean -------


def test_rollback_verification_detects_status_code_restored_with_wrong_type(
    admin: Conn, table: WidgetTable
) -> None:
    """Shape A: `status_code` is restored as `text` instead of `integer`,
    with values that look correct once cast — a value-only comparison
    cannot see this; the schema-shape check must."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} ADD COLUMN status_code text").format(table.ident))
    for widget_id, code, _ in snapshot.rows:
        admin.execute(
            sql.SQL("UPDATE {} SET status_code = %s WHERE id = %s").format(table.ident),
            (str(code), widget_id),
        )
    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN status_code SET NOT NULL").format(table.ident))

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "shape regressed" in exc_info.value.detail


def test_rollback_verification_detects_data_loss_on_the_surviving_status_column(
    admin: Conn, table: WidgetTable
) -> None:
    """Shape C: `status_code` is restored correctly, but the rollback
    clobbers the surviving `status` column's data — a check scoped to
    `status_code` alone cannot see this data loss; the full-row comparison
    across both surviving columns must."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    rollback_contract(admin, table, batch_size=BATCH_SIZE)  # status_code restored correctly
    admin.execute(sql.SQL("UPDATE {} SET status = 'clobbered'").format(table.ident))

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"


# --- P2-1 (independent review): an empty snapshot must not vacuously pass --


def test_verify_rollback_refuses_an_empty_snapshot(admin: Conn, table: WidgetTable) -> None:
    admin.execute(sql.SQL("DELETE FROM {}").format(table.ident))
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    assert snapshot.rows == ()
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    with pytest.raises(MigrationPhaseError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "EMPTY_SNAPSHOT"


def test_validate_post_contract_refuses_an_empty_snapshot(admin: Conn, table: WidgetTable) -> None:
    admin.execute(sql.SQL("DELETE FROM {}").format(table.ident))
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    with pytest.raises(MigrationPhaseError) as exc_info:
        validate_post_contract(admin, snapshot, table)
    assert exc_info.value.code == "EMPTY_SNAPSHOT"


# --- P2-2 (independent review): every rollback-verification failure path is
# a named `RollbackVerificationError`, never a bare driver exception --------


def test_rollback_verification_names_a_missing_status_code_column(
    admin: Conn, table: WidgetTable
) -> None:
    """Shape H: a rollback that does nothing at all (`status_code` never
    re-added) must raise the named error, never a bare `UndefinedColumn`."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "status_code" in exc_info.value.detail


def test_rollback_verification_names_an_all_null_status_code_column(
    admin: Conn, table: WidgetTable
) -> None:
    """Shape I: `status_code` is re-added but left all-NULL (no backfill, no
    `NOT NULL`) — must raise the named error, never a bare `TypeError`."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    admin.execute(sql.SQL("ALTER TABLE {} ADD COLUMN status_code integer").format(table.ident))

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"


# --- P2-3 (independent review): upgrade -> rollback -> upgrade again -------


def test_contract_can_run_again_after_a_genuinely_correct_rollback(
    admin: Conn, table: WidgetTable
) -> None:
    """Proves the harness supports re-running the destructive `contract`
    phase after a genuinely correct rollback, not just the single downgrade
    the other tests exercise."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)
    result = verify_rollback(admin, snapshot, table)
    assert result.rows_checked == ROW_COUNT

    contract(admin, table)
    assert not _column_exists(admin, table, "status_code")
    result2 = validate_post_contract(admin, snapshot, table)
    assert result2.violations == []


def test_cycle_detects_a_broken_second_rollback(admin: Conn, table: WidgetTable) -> None:
    """NF-6 (2026-10-03 security re-review): upgrade -> correct rollback ->
    upgrade again -> a second, deliberately broken rollback must also be
    caught. The re-review's own probe (P23e) already showed this works;
    this pins it in the suite rather than leaving it proven only by a
    probe that was deleted afterward."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)
    assert verify_rollback(admin, snapshot, table).rows_checked == ROW_COUNT

    contract(admin, table)
    assert validate_post_contract(admin, snapshot, table).violations == []

    rollback_contract_broken(admin, table, batch_size=BATCH_SIZE)
    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"


# --- NF-1 (2026-10-03 security re-review): row-count/duplicate-id false
# cleans that an id-keyed dict silently collapsed -----------------------------


def _drop_primary_key(admin: Conn, table: WidgetTable) -> None:
    row = admin.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'p'",
        (str(table),),
    ).fetchone()
    assert row is not None
    admin.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(table.ident, sql.Identifier(row[0])))


def test_rollback_verification_detects_pk_dropped_plus_one_duplicate_row(
    admin: Conn, table: WidgetTable
) -> None:
    """Probe N8: a rollback that drops the primary key and then inserts one
    exact duplicate row (12 -> 13 live rows) must be caught. An id-keyed
    dict silently collapses the duplicate back down to 12 and reports a
    clean `rows_checked=12` — exactly the false clean this fix closes."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    _drop_primary_key(admin, table)
    admin.execute(
        sql.SQL(
            "INSERT INTO {} (id, status_code, status) SELECT id, status_code, status FROM {} WHERE id = 0"
        ).format(table.ident, table.ident)
    )

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"


def test_rollback_verification_detects_pk_dropped_plus_every_row_duplicated(
    admin: Conn, table: WidgetTable
) -> None:
    """Probe N9: a rollback that drops the primary key and then duplicates
    every row (12 -> 24 live rows) must be caught the same way."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    _drop_primary_key(admin, table)
    admin.execute(
        sql.SQL("INSERT INTO {} (id, status_code, status) SELECT id, status_code, status FROM {}").format(
            table.ident, table.ident
        )
    )

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"


# --- C2 (2026-10-03 security re-review): detector branches that already
# work today but had no dedicated test killing a mutant that removes them ---


def test_rollback_verification_detects_status_code_missing_not_null(
    admin: Conn, table: WidgetTable
) -> None:
    """Shape B (one of BUG-049's own 4 named shapes; mutant M6): `status_code`
    is restored with the correct type and correct values, but without its
    original `NOT NULL` — a nullability-only regression, distinct from
    shape A's wrong-*type* test above, which this repo's suite never
    separately pinned."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN status_code DROP NOT NULL").format(table.ident))

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "shape regressed" in exc_info.value.detail


def test_rollback_verification_detects_an_extra_row_with_a_new_id(
    admin: Conn, table: WidgetTable
) -> None:
    """Shape G (mutant M4): a rollback that leaves an extra row with a
    brand-new id — row-set *growth*, not the shrinkage/duplication the
    other negative tests exercise — must be caught."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    admin.execute(
        sql.SQL("INSERT INTO {} (id, status_code, status) VALUES (%s, %s, %s)").format(table.ident),
        (ROW_COUNT, 0, "inactive"),
    )

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"


def test_rollback_verification_detects_status_column_shape_regression(
    admin: Conn, table: WidgetTable
) -> None:
    """N2/N3-style (mutant M1): the surviving `status` column's own shape
    regresses (its `NOT NULL` dropped) — a schema-shape regression on the
    *surviving* column, not the restored `status_code` column the shape-A
    test above already covers."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN status DROP NOT NULL").format(table.ident))

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "shape regressed" in exc_info.value.detail


# --- NR2-1 (2026-10-03 security re-review round 2): each NF-1 comparison
# pinned in ISOLATION — no row duplication alongside a constraint change, so
# the constraint/default/column-set/id-shape checks are each the only thing
# that can catch the probe, never shadowed by the row-count/duplicate check
# the way the two combined PK-drop-plus-duplicate tests above are. ----------


def test_rollback_verification_detects_pk_only_drop(admin: Conn, table: WidgetTable) -> None:
    """Probe R01, isolated: the primary key is dropped and nothing else
    changes — no duplicate row inserted. Must be caught by the constraint
    comparison specifically (mutant N2); the row-count/duplicate check
    cannot see this, since the live row count and id set are unchanged."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    _drop_primary_key(admin, table)

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "table constraints changed" in exc_info.value.detail


def test_rollback_verification_detects_a_check_constraint_added(admin: Conn, table: WidgetTable) -> None:
    """Probe R23, isolated: a CHECK constraint added after a correct
    rollback — the constraint set changed, nothing else. Must be caught by
    the constraint comparison specifically (mutant N2)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    admin.execute(
        sql.SQL("ALTER TABLE {} ADD CONSTRAINT ck_status_code_nonneg CHECK (status_code >= 0)").format(
            table.ident
        )
    )

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "table constraints changed" in exc_info.value.detail


def test_rollback_verification_detects_a_default_added_on_status_code(
    admin: Conn, table: WidgetTable
) -> None:
    """Probe R04, isolated: a DEFAULT added to the restored `status_code`
    column after a correct rollback — type and nullability unchanged, only
    the default. Must be caught by the default comparison inside the
    `status_code` shape check specifically (mutant N3), not the
    `NOT NULL`-only test above."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN status_code SET DEFAULT 0").format(table.ident))

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "status_code column shape regressed" in exc_info.value.detail


def test_rollback_verification_detects_an_extra_column(admin: Conn, table: WidgetTable) -> None:
    """Probe R09, isolated: an extra column added after a correct
    rollback — row data and constraints unchanged. Must be caught by the
    full column-set comparison specifically (mutant N4)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    admin.execute(sql.SQL("ALTER TABLE {} ADD COLUMN extra_note text").format(table.ident))

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "column set changed" in exc_info.value.detail


def test_rollback_verification_detects_id_retyped_to_bigint(admin: Conn, table: WidgetTable) -> None:
    """Probe R13, isolated: `id` retyped to `bigint` after a correct
    rollback — nothing else changes. Must be caught by the `id` shape
    comparison specifically (mutant N6), not the `status_code`/`status`
    shape checks the other shape tests exercise."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)
    rollback_contract(admin, table, batch_size=BATCH_SIZE)

    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN id TYPE bigint").format(table.ident))

    with pytest.raises(RollbackVerificationError) as exc_info:
        verify_rollback(admin, snapshot, table)
    assert exc_info.value.code == "ROLLBACK_VERIFICATION_FAILED"
    assert "id column shape regressed" in exc_info.value.detail


# --- NR2-2 (2026-10-03 security re-review round 2): `validate_post_contract`
# had zero negative tests — every check in it could be deleted while the
# suite stayed green. Mirrors the review's own V01/V04/V06/V07/V08/V09/V13/
# V14 probes, asserting the specific named violation string each one must
# produce, not merely `!= []`. ------------------------------------------------


def test_validate_post_contract_detects_pk_dropped_plus_duplicate_row(
    admin: Conn, table: WidgetTable
) -> None:
    """Probe V01: constraint comparison (mutants P2/P10)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    _drop_primary_key(admin, table)
    admin.execute(
        sql.SQL("INSERT INTO {} (id, status) SELECT id, status FROM {} WHERE id = 0").format(
            table.ident, table.ident
        )
    )

    result = validate_post_contract(admin, snapshot, table)
    assert any(v.startswith("TABLE_CONSTRAINTS_CHANGED") for v in result.violations)


def test_validate_post_contract_detects_status_not_null_dropped(admin: Conn, table: WidgetTable) -> None:
    """Probe V04: `status` shape comparison (mutant P5)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN status DROP NOT NULL").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    assert any(v.startswith("STATUS_SHAPE_REGRESSED") for v in result.violations)


def test_validate_post_contract_detects_id_retyped_to_bigint(admin: Conn, table: WidgetTable) -> None:
    """Probe V06: `id` shape comparison (mutant P6)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN id TYPE bigint").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    assert any(v.startswith("ID_SHAPE_REGRESSED") for v in result.violations)


def test_validate_post_contract_detects_a_check_constraint_added(admin: Conn, table: WidgetTable) -> None:
    """Probe V07: constraint comparison (mutant P2)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(
        sql.SQL("ALTER TABLE {} ADD CONSTRAINT ck_status_nonempty CHECK (status <> '')").format(table.ident)
    )

    result = validate_post_contract(admin, snapshot, table)
    assert any(v.startswith("TABLE_CONSTRAINTS_CHANGED") for v in result.violations)


def test_validate_post_contract_detects_a_default_added_on_status(admin: Conn, table: WidgetTable) -> None:
    """Probe V08: `status` shape comparison, default specifically (mutant P5)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN status SET DEFAULT 'inactive'").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    assert any(v.startswith("STATUS_SHAPE_REGRESSED") for v in result.violations)


def test_validate_post_contract_detects_an_extra_column(admin: Conn, table: WidgetTable) -> None:
    """Probe V09: full column-set comparison (mutant P4)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} ADD COLUMN extra_note text").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    assert any(v.startswith("COLUMN_SET_CHANGED") for v in result.violations)


def test_validate_post_contract_detects_a_changed_status_value(admin: Conn, table: WidgetTable) -> None:
    """Probe V13: `STATUS_MISMATCH` (mutant P8). Widget id 0 always maps to
    status_code 0 -> 'inactive' (see `STATUS_BY_CODE`/`seed_widgets`), so
    overwriting it with a different value is a genuine mismatch regardless
    of `ROW_COUNT`."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("UPDATE {} SET status = 'pending' WHERE id = 0").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    assert any(v.startswith("STATUS_MISMATCH") for v in result.violations)


def test_validate_post_contract_detects_legacy_column_still_present(
    admin: Conn, table: WidgetTable
) -> None:
    """Probe V14: the legacy `status_code` column still present after a
    no-op re-contract (mutant P9) — `contract()` is deliberately never
    called here, so `status_code` survives and nothing else about the
    sequence's end state is wrong."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)

    result = validate_post_contract(admin, snapshot, table)
    assert result.violations == ["LEGACY_COLUMN_STILL_PRESENT"]


# --- NR2-3 (2026-10-03 security re-review round 2): `validate_post_contract`
# must never leak a bare `AssertionError` when a surviving column is dropped
# or renamed after contract — it must report a named violation instead. ----


def test_validate_post_contract_names_a_dropped_surviving_column_instead_of_raising(
    admin: Conn, table: WidgetTable
) -> None:
    """Dropping the surviving `status` column after contract previously hit
    `_column_shape`'s unconditional `pg_attribute` lookup and raised a bare
    `AssertionError` (`one_row`); it must instead report a named violation
    (`COLUMN_SET_CHANGED`, which already fires for a missing column).
    Tightened 2026-10-03 (NR4-2): asserts the exact `got` column set
    (`status` genuinely absent, nothing else changed), not just that the
    substring `"status"` appears somewhere in the violation text."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} DROP COLUMN status").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    violation = next(v for v in result.violations if v.startswith("COLUMN_SET_CHANGED"))
    expected, got = _parse_column_set_changed(violation)
    assert expected == ["id", "status"]
    assert got == ["id"]


# --- NR3-1 (2026-10-03 security re-review round 3): the `id` case of the
# same leak, plus `status` renamed (the missing-case the round-2 tests above
# never covered — they only drop `status`, never rename it). Both row-query
# branches in `validate_post_contract` selected `id` unconditionally, so a
# missing/renamed `id` still leaked a bare `UndefinedColumn` after round 2's
# fix covered `status` only. ------------------------------------------------


def test_validate_post_contract_names_a_renamed_status_column_instead_of_raising(
    admin: Conn, table: WidgetTable
) -> None:
    """Renaming (not dropping) the surviving `status` column after contract
    must also report a named violation, not raise — the missing case
    alongside the drop test above. Tightened 2026-10-03 (NR4-2): asserts
    the exact `got` set — the original name genuinely absent and the new
    name genuinely present — not just that the substring `"status"`
    appears (which it would even for `status2`, or for a mutant reporting
    no change at all)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} RENAME COLUMN status TO status2").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    violation = next(v for v in result.violations if v.startswith("COLUMN_SET_CHANGED"))
    expected, got = _parse_column_set_changed(violation)
    assert expected == ["id", "status"]
    assert got == ["id", "status2"]


def test_validate_post_contract_names_a_renamed_id_column_instead_of_raising(
    admin: Conn, table: WidgetTable
) -> None:
    """NR3-1: renaming `id` after contract previously hit the unconditional
    `SELECT id` row-query and leaked a bare `UndefinedColumn`; it must
    instead report the named `COLUMN_SET_CHANGED` violation that already
    fires for a missing/renamed column, with no exception raised.
    Tightened 2026-10-03 (NR4-2): asserts the exact `got` set — `id`
    genuinely absent, `id2` genuinely present — not just that the
    substring `"id"` appears (which it would even for `id2`, the word
    "expected" in the violation's own prefix, or a mutant reporting no
    change at all)."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} RENAME COLUMN id TO id2").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    violation = next(v for v in result.violations if v.startswith("COLUMN_SET_CHANGED"))
    expected, got = _parse_column_set_changed(violation)
    assert expected == ["id", "status"]
    assert got == ["id2", "status"]


def test_validate_post_contract_names_a_dropped_id_column_instead_of_raising(
    admin: Conn, table: WidgetTable
) -> None:
    """NR3-1: dropping `id` after contract previously leaked a bare
    `UndefinedColumn` the same way; it must instead report the named
    violation, with no exception raised. Tightened 2026-10-03 (NR4-2):
    asserts the exact `got` column set (`id` genuinely absent, nothing
    else changed), not just a substring match."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} DROP COLUMN id").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    violation = next(v for v in result.violations if v.startswith("COLUMN_SET_CHANGED"))
    expected, got = _parse_column_set_changed(violation)
    assert expected == ["id", "status"]
    assert got == ["status"]


# --- NR4-1 (2026-10-03 security re-review round 4): `id` can exist but hold
# a NULL or non-integer value after `contract` — `validate_post_contract`
# previously ran `int(r[0])` unguarded on such values and leaked a bare
# `TypeError`/`ValueError` instead of a named violation. ---------------------


def test_validate_post_contract_names_an_invalid_id_instead_of_raising_on_null(
    admin: Conn, table: WidgetTable
) -> None:
    """Probe V18: the primary key is dropped, `id`'s own `NOT NULL` is
    dropped, and one row's `id` is set to NULL. Must report the named
    `ID_VALUE_INVALID` violation, never a bare `TypeError`."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    _drop_primary_key(admin, table)
    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN id DROP NOT NULL").format(table.ident))
    admin.execute(sql.SQL("UPDATE {} SET id = NULL WHERE id = 0").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    violation = next(v for v in result.violations if v.startswith("ID_VALUE_INVALID"))
    assert "NULL id found" in violation


def test_validate_post_contract_names_an_invalid_id_instead_of_raising_on_non_numeric(
    admin: Conn, table: WidgetTable
) -> None:
    """Probe V19: `id` is retyped to `text` and one row's `id` is set to a
    non-numeric string (`'x'`) — the `int()`-conversion failure branch,
    distinct from V18's NULL-id branch above. Must report the named
    `ID_VALUE_INVALID` violation, never a bare `ValueError`."""
    snapshot = run_full_sequence(admin, table, batch_size=BATCH_SIZE)
    contract(admin, table)

    admin.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN id TYPE text USING id::text").format(table.ident))
    admin.execute(sql.SQL("UPDATE {} SET id = 'x' WHERE id = '0'").format(table.ident))

    result = validate_post_contract(admin, snapshot, table)
    violation = next(v for v in result.violations if v.startswith("ID_VALUE_INVALID"))
    assert "non-integer id" in violation


# --- GOV-01-R06 / TSD §24.2 ¶2: rolling-deploy (N-1) compatibility ----------
#
# The N-1 version's SQL names only `id`/`status_code`; the N version's names
# only `id`/`status` (`old_app_*` / `new_app_*` in the harness). Neither can
# see the other's column, so these tests cannot accidentally prove
# compatibility through a shared code path.
#
# Scope, restated here because it bounds every assertion below: the two
# versions' statements are interleaved deterministically on the one `admin`
# connection — this is not a concurrency test — and the "N-1 version" is
# harness code, not the previously-released application artifact. The real
# previous-artifact proof needs a release/version registry that does not exist
# in this repository yet (GOV-01-R05); see the harness's own boundary note.

OLD_WRITER_ID = 100  # written by N-1 during the expand window
NEW_WRITER_ID = 101  # written by N during the same window
POST_SWITCH_OLD_ID = 102  # written by N-1 after `switch` enforced NOT NULL
POST_SWITCH_NEW_ID = 103
STALE_WRITER_ID = 200  # written by N-1 with no compatibility trigger installed


def _trigger_exists(admin: Conn, table: WidgetTable, name: str) -> bool:
    row = admin.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = %s::regclass"
        " AND tgname = %s AND NOT tgisinternal)",
        (str(table), name),
    ).fetchone()
    assert row is not None
    return bool(row[0])


def _reach_switch_with_both_versions_live(admin: Conn, table: WidgetTable) -> None:
    """Shared arrangement for the contract-ordering tests below: expand with
    the compatibility trigger installed, one write from each version, the
    backfill, then switch. `test_n_minus_1_and_n_coexist_...` asserts its way
    through this same progression step by step instead of calling this."""
    expand(admin, table)
    install_old_shape_compatibility_trigger(admin, table)
    old_app_write(admin, OLD_WRITER_ID, 2, table)
    new_app_write(admin, NEW_WRITER_ID, "active", table)
    migrate_backfill(admin, table, batch_size=BATCH_SIZE)
    switch(admin, table)


def test_n_minus_1_and_n_coexist_across_expand_backfill_and_switch(
    admin: Conn, table: WidgetTable
) -> None:
    """The positive proof: across expand, backfill and switch, every write by
    either version is visible and correctly meaningful to the other — no lost
    write (a row one version cannot see) and no stale read (a `status` that
    disagrees with its `status_code`)."""
    expand(admin, table)
    install_old_shape_compatibility_trigger(admin, table)

    # Expand window, before any backfill: the previous release keeps writing
    # its own shape, and the new version must not read it as NULL/stale.
    old_app_write(admin, OLD_WRITER_ID, 2, table)
    assert new_app_read(admin, table)[OLD_WRITER_ID] == "pending"

    # ...and the new version's writes must not be lost to the previous one,
    # which can only ever see `status_code`.
    new_app_write(admin, NEW_WRITER_ID, "active", table)
    assert old_app_read(admin, table)[NEW_WRITER_ID] == 1

    # Both versions' in-place updates, each touching only its own column.
    old_app_update(admin, 0, 1, table)  # seeded id 0 was status_code 0
    assert new_app_read(admin, table)[0] == "active"
    new_app_update(admin, 1, "inactive", table)  # seeded id 1 was status_code 1
    assert old_app_read(admin, table)[1] == 0

    # The backfill only ever had untouched seeded rows left to do: every row
    # either version wrote or updated above already landed in *both* shapes, so
    # there was never a window in which a live-written row sat NULL waiting for
    # the backfill to reach it. Here that is the 12 seeded rows minus ids 0 and
    # 1 (synced by the two updates above); the two rows ids 100/101 inserted
    # during the window were never in the queue at all.
    assert migrate_backfill(admin, table, batch_size=BATCH_SIZE) == ROW_COUNT - 2
    assert admin.execute(
        sql.SQL("SELECT count(*) FROM {} WHERE status IS NULL").format(table.ident)
    ).fetchone() == (0,)
    assert rolling_deploy_divergences(old_app_read(admin, table), new_app_read(admin, table)) == []

    # `switch` enforces `status NOT NULL`. The N-1 writer, which cannot supply
    # `status` at all, must still work — this is the step a rolling deploy
    # breaks on if the expand phase was incomplete.
    switch(admin, table)
    old_app_write(admin, POST_SWITCH_OLD_ID, 0, table)
    assert new_app_read(admin, table)[POST_SWITCH_OLD_ID] == "inactive"
    new_app_write(admin, POST_SWITCH_NEW_ID, "pending", table)
    assert old_app_read(admin, table)[POST_SWITCH_NEW_ID] == 2

    old_view = old_app_read(admin, table)
    new_view = new_app_read(admin, table)
    assert rolling_deploy_divergences(old_view, new_view) == []
    # Not a vacuous empty-view comparison: every seeded row plus all four
    # rolling-deploy writes are present in both versions' views.
    assert len(old_view) == ROW_COUNT + 4
    assert set(old_view) == set(range(ROW_COUNT)) | {
        OLD_WRITER_ID,
        NEW_WRITER_ID,
        POST_SWITCH_OLD_ID,
        POST_SWITCH_NEW_ID,
    }


def test_an_n_minus_1_write_is_stale_to_n_without_the_compatibility_trigger(
    admin: Conn, table: WidgetTable
) -> None:
    """The negative half of the expand-window proof, and the one that makes
    `rolling_deploy_divergences` falsifiable: with `expand` alone and no
    compatibility trigger, an N-1 write leaves `status` NULL, so the N version
    reads a row the previous release considers `pending` as having no status at
    all. The detector must report clean before that write and name exactly
    that row after it — so neither an always-clean nor an always-dirty
    detector could pass this."""
    expand(admin, table)  # deliberately WITHOUT install_old_shape_compatibility_trigger
    migrate_backfill(admin, table, batch_size=BATCH_SIZE)
    assert rolling_deploy_divergences(old_app_read(admin, table), new_app_read(admin, table)) == []

    old_app_write(admin, STALE_WRITER_ID, 2, table)

    divergences = rolling_deploy_divergences(old_app_read(admin, table), new_app_read(admin, table))
    assert len(divergences) == 1
    assert divergences[0].startswith(f"id={STALE_WRITER_ID}:")
    assert "'pending'" in divergences[0]  # what N-1 means by status_code=2


def test_contract_is_refused_while_the_n_minus_1_version_is_still_deployed(
    admin: Conn, table: WidgetTable
) -> None:
    """TSD §24.2 ¶2's gate, fail-closed: with N-1 still deployed the gated
    contract raises the named error and performs no DDL — the legacy column,
    the compatibility trigger, and the N-1 version's own writes all survive."""
    _reach_switch_with_both_versions_live(admin, table)

    with pytest.raises(MigrationPhaseError) as exc_info:
        contract_after_old_shape_retirement(
            admin, table, deployed_versions=frozenset({APP_N_MINUS_1, APP_N})
        )
    assert exc_info.value.code == "CONTRACT_BEFORE_OLD_SHAPE_RETIRED"
    assert APP_N_MINUS_1 in exc_info.value.detail

    assert _column_exists(admin, table, "status_code")
    assert _trigger_exists(admin, table, COMPATIBILITY_TRIGGER)
    old_app_write(admin, POST_SWITCH_OLD_ID, 0, table)
    assert new_app_read(admin, table)[POST_SWITCH_OLD_ID] == "inactive"
    assert rolling_deploy_divergences(old_app_read(admin, table), new_app_read(admin, table)) == []


def test_premature_contract_breaks_the_still_deployed_n_minus_1_version(
    admin: Conn, table: WidgetTable
) -> None:
    """The negative the gate above exists for: contracting while N-1 is still
    deployed — here by calling `contract` directly, bypassing the gate — makes
    both the previous version's reads and its writes fail outright. The N
    version's existing rows remain readable; this test does not prove N writes
    survive the invalid contract. This is what proves the ordering requirement is
    real rather than a convention the harness merely documents."""
    _reach_switch_with_both_versions_live(admin, table)

    contract(admin, table)

    with pytest.raises(psycopg.errors.UndefinedColumn):
        old_app_read(admin, table)
    with pytest.raises(psycopg.errors.UndefinedColumn):
        old_app_write(admin, POST_SWITCH_OLD_ID, 0, table)

    # The N version still reads every row written during the expand window.
    new_view = new_app_read(admin, table)
    assert new_view[OLD_WRITER_ID] == "pending"
    assert new_view[NEW_WRITER_ID] == "active"


def test_contract_proceeds_once_the_old_shape_is_retired(
    admin: Conn, table: WidgetTable
) -> None:
    """The permitted ordering: once N-1 is out of `deployed_versions`, the
    gated contract drops the compatibility trigger and the legacy column, the
    post-contract validation query is clean, and the rows both versions wrote
    during the rolling-deploy window survive for the N version."""
    _reach_switch_with_both_versions_live(admin, table)
    snapshot = capture_snapshot(admin, table)
    assert len(snapshot.rows) == ROW_COUNT + 2

    contract_after_old_shape_retirement(admin, table, deployed_versions=frozenset({APP_N}))

    assert not _column_exists(admin, table, "status_code")
    assert not _trigger_exists(admin, table, COMPATIBILITY_TRIGGER)
    assert validate_post_contract(admin, snapshot, table).violations == []

    new_view = new_app_read(admin, table)
    assert new_view[OLD_WRITER_ID] == "pending"
    assert new_view[NEW_WRITER_ID] == "active"
    # The N version's own writes keep working after the old shape is gone.
    new_app_write(admin, POST_SWITCH_NEW_ID, "inactive", table)
    assert new_app_read(admin, table)[POST_SWITCH_NEW_ID] == "inactive"


def test_failed_contract_restores_the_compatibility_trigger_so_n_writes_survive(
    admin: Conn, table: WidgetTable
) -> None:
    """A dependent view on `status_code` makes the gated contract's DROP COLUMN
    fail (SQLSTATE 2BP01). The trigger drop and the contract share one
    transaction, so the failure restores the trigger and the N version's
    `status`-only writes still succeed (without it they would fail 23502).
    Once the view is removed, the same guarded contract succeeds."""
    _reach_switch_with_both_versions_live(admin, table)
    view = sql.Identifier(table.schema, "widget_status_code_view")
    admin.execute(
        sql.SQL("CREATE VIEW {} AS SELECT id, status_code FROM {}").format(view, table.ident)
    )

    with pytest.raises(psycopg.errors.DependentObjectsStillExist):
        contract_after_old_shape_retirement(admin, table, deployed_versions=frozenset({APP_N}))

    assert _column_exists(admin, table, "status_code")
    assert _trigger_exists(admin, table, COMPATIBILITY_TRIGGER)
    new_app_write(admin, POST_SWITCH_NEW_ID, "pending", table)
    assert new_app_read(admin, table)[POST_SWITCH_NEW_ID] == "pending"

    admin.execute(sql.SQL("DROP VIEW {}").format(view))
    contract_after_old_shape_retirement(admin, table, deployed_versions=frozenset({APP_N}))
    assert not _column_exists(admin, table, "status_code")
    assert not _trigger_exists(admin, table, COMPATIBILITY_TRIGGER)

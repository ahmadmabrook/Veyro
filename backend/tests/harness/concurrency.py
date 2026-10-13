"""Optimistic-concurrency/versioning harness — GOV-01-R02, CONC category,
proving `.claude/rules/backend/concurrency.md` (`DOM-002`:
"Each mutable aggregate uses optimistic concurrency/versioning. Lost-update
behavior must be explicit") against a synthetic mutable aggregate.

Guarantees this harness proves on that aggregate:

* A correct version-checked mutation reads, checks, and increments the
  version in one atomic `UPDATE ... WHERE id = %s AND version = %s`
  statement (rule control 2).
* A version mismatch (another writer moved the version first) affects zero
  rows and is surfaced as a typed, distinguishable `VersionConflict` — never
  silently retried or overwritten (rule control 3). A missing row is a
  *different* typed error, `RowNotFound` — never conflated with a version
  conflict (round-1 code-review P2-1 fix: a bare zero-rowcount check cannot
  tell the two apart). The existence check and the version-checked update
  are folded into **one** `WITH` statement (round-4 code-review R4-4 fix —
  see `update_versioned`'s own docstring): running them as two separate
  statements let a concurrent insert land in the gap between them and
  produce a 409-shaped `VersionConflict` for a row that did not exist when
  the mutation actually ran.
* A deliberately-broken comparison fixture (`update_unversioned_blind`, no
  version predicate at all) is included so the pattern can be shown to tell
  correct from broken: run the identical two-writer shape against it and
  the lost update actually happens, proving the proof method is sensitive to
  the defect rather than passing vacuously (fail-closed rule: "a
  deliberately-broken version-check fixture must be shown to fail closed,
  not silently pass").

Lost-update resolution for this fixture aggregate (rule control 4, an
explicit documented decision, not an accident of whichever write lands
last): **reject-and-retry**. `update_versioned` raises `VersionConflict`
rather than merging or silently last-writer-wins; the caller decides whether
and how to re-read and retry. A later domain module adopting this pattern
for its own real aggregate may choose a different documented resolution
(explicit merge, acknowledged last-writer-wins) — this harness's choice
binds only its own synthetic `versioned_widget` fixture. This decision is
also recorded durably and non-chronologically in
`knowledge/03-Modules/MOD-001/REQUIREMENTS.md`'s own `DOM-002` traceability
row (round-1 code-review P3-5: a chronological front-matter `updated:` line
alone is fragile, since later rounds demote it to history).

Schema-ownership contract (round-1 code-review P1-1 fix): this harness owns
the `concurrency_harness` schema **exclusively** — no other harness module
creates, grants on, or reassigns ownership of it. `create_versioned_table`
always runs `CREATE SCHEMA IF NOT EXISTS concurrency_harness AUTHORIZATION
<superuser>` (the same superuser role `admin` always connects as, per
`tests/harness/postgres.py`'s `SUPERUSER`), so ownership is deterministic
regardless of which test module runs first. This harness deliberately does
**not** touch `tenant_isolation.py`'s `"harness"` schema or its `OWNER_ROLE`
— the original defect was sharing that schema name without that module's
own `AUTHORIZATION`/`SET ROLE` ownership contract, which silently handed
schema ownership to whichever harness ran `CREATE SCHEMA IF NOT EXISTS`
first (a no-op on an already-existing schema, so it never reassigns
ownership) and broke the tenant-isolation harness's own
`GRANT USAGE ON SCHEMA harness` under a different collection order.

Teardown contract (round-1 code-review P1-2 fix): the `versioned_widget`
table is created and dropped around every individual test (see
`drop_versioned_table` and `tests/integration/test_concurrency_harness.py`'s
`widget` fixture) — it never persists across tests. The ADR-010 RLS
architecture gate (`tools/validate_architecture_gates.py`) scans *every*
non-system schema by default and flags any relation with no `tenant_id` and
no manifest platform-table entry as `RLS_TABLE_UNCLASSIFIED`; a persistent,
unclassified synthetic table could make that Blocker-tier gate FAIL whenever
a gate invocation ran later in the same test session. Per-test teardown
means no gate invocation, in any order, can ever observe this table.

Plug-in point for later modules (MOD-002, MOD-019, MOD-020, MOD-034,
MOD-037 — `DOM-002`'s co-owners per `EIP_MIRROR.md` lines 20899-20906):
give your own mutable-aggregate table a `version integer NOT NULL DEFAULT 1`
column, mirror `update_versioned`'s `WHERE id = %s AND version = %s` +
`SET version = version + 1` shape for your own mutations, and reuse
`VersionConflict`/`RowNotFound` (or your own typed equivalents) as the API
boundary errors `.claude/rules/backend/api.md`'s typed-errors control
requires. Your own real aggregate presumably lives in a schema your own
module owns and has its own `tenant_id`, so the P1-2 teardown concern this
harness has (an unclassified synthetic relation) will not apply to you the
same way — but a real aggregate table still needs the RLS lint's own
`tenant_id`/policy controls (`.claude/rules/backend/database.md`), which are
orthogonal to and not satisfied by this concurrency pattern. One more thing
to know before reusing these two types: `VersionConflict` and `RowNotFound`
deliberately share no common base class (both are direct `Exception`
subclasses) — this is a recorded, upheld deferral (round-2 review R2-4),
not an oversight; round-3 review R3-5 flagged that this fact needed to be
discoverable from the code itself, not only from the round-2/round-3
reports, which is why it is stated here. If your own domain's API boundary
wants one broad `except` for "any optimistic-concurrency failure on this
aggregate" as well as the narrow 409-vs-404 distinction, that is a decision
for you to make for your own real aggregate — this harness's synthetic
fixture has no caller today that needs it, so it was not invented in
advance of a real one to validate the shape against.

Known ceiling: this harness simulates concurrency (two sequential,
deterministic "writers" racing on the same previously-read version, over
the same connection — not two genuinely separate sessions), not real
parallel load or a real database serialization-failure/deadlock path —
`SCN-MOD001-009` itself says "simulated, not real load." It does not attempt
to prove behavior under genuine concurrent transactions, connection-pool
exhaustion, or `SERIALIZABLE` isolation-level conflicts; a later module
adding real load needs its own test for that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from tests.harness.postgres import SUPERUSER

# `one_row`/`Conn` deliberately re-declared rather than imported from
# `tests/harness/tenant_isolation.py` (round-1 code-review P3-4): this
# harness has zero dependency on the tenant-isolation harness — not its
# fixtures, not its schema, not its ownership model — by design, so a future
# change to that module's internals cannot silently affect this one.
Conn = psycopg.Connection[TupleRow]

SCHEMA = "concurrency_harness"


@dataclass(frozen=True)
class VersionedTable:
    schema: str
    name: str

    @property
    def ident(self) -> sql.Identifier:
        return sql.Identifier(self.schema, self.name)

    def __str__(self) -> str:
        return f"{self.schema}.{self.name}"


class VersionConflict(Exception):
    """Typed, distinguishable conflict error (rule control 3) — raised when a
    version-checked update affects zero rows because another writer already
    moved the version on a row that does exist. Never swallowed, never
    retried automatically here. Never raised for a missing row — see
    `RowNotFound`."""

    def __init__(self, table: VersionedTable, row_id: UUID, expected_version: int) -> None:
        self.table = table
        self.row_id = row_id
        self.expected_version = expected_version
        super().__init__(
            f"version conflict on {table}: id={row_id} expected_version={expected_version}"
        )


class RowNotFound(Exception):
    """Typed, distinguishable missing-row error — raised when a
    version-checked update affects zero rows because `row_id` does not exist
    at all, never conflated with `VersionConflict` (round-1 code-review
    P2-1: a bare zero-rowcount check cannot otherwise tell the two apart)."""

    def __init__(self, table: VersionedTable, row_id: UUID) -> None:
        self.table = table
        self.row_id = row_id
        super().__init__(f"no row at {table}: id={row_id}")


def one_row(cur: psycopg.Cursor[TupleRow]) -> TupleRow:
    row = cur.fetchone()
    if row is None:
        raise AssertionError("expected exactly one row, got none")
    return row


def create_versioned_table(admin: Conn, table: VersionedTable, columns: sql.Composable) -> None:
    """Fixture mutable-aggregate table exactly as `DOM-002` requires: an
    explicit `version integer NOT NULL DEFAULT 1` column (rule control 1),
    plus whatever caller-supplied columns the aggregate needs. Explicit
    `AUTHORIZATION` (module docstring's schema-ownership contract, P1-1 fix)
    makes ownership deterministic regardless of call order; `IF NOT EXISTS`
    is safe here only because `drop_versioned_table` always removes the
    table at the end of the test that created it (P1-2 fix) — the table
    never outlives a single test, so there is no earlier-session leftover
    for `IF NOT EXISTS` to silently paper over."""
    schema, t = sql.Identifier(table.schema), table.ident
    admin.execute(
        sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(
            schema, sql.Identifier(SUPERUSER)
        )
    )
    admin.execute(
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {} ("
            "id uuid PRIMARY KEY, version integer NOT NULL DEFAULT 1, {})"
        ).format(t, columns)
    )


def drop_versioned_table(admin: Conn, table: VersionedTable) -> None:
    """Teardown counterpart to `create_versioned_table` (P1-2 fix): removes
    the table so no later architecture-gate invocation in the same test
    session can ever see it. Does not drop the schema — `SCHEMA` is reused
    across tests *within* a session and owns nothing else worth tearing
    down. (Round-2 review R2-3: this previously also said "across
    sessions", which is false — `conftest.py`'s `pg` fixture is
    session-scoped over `disposable_postgres()`, which gives every pytest
    session a fresh container and therefore a fresh, empty database; no
    schema survives a session boundary regardless of what this function
    does.)"""
    admin.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(table.ident))


def insert(conn: Conn, table: VersionedTable, row_id: UUID, fields: dict[str, Any]) -> None:
    cols = [sql.Identifier("id"), *(sql.Identifier(c) for c in fields)]
    conn.execute(
        sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            table.ident,
            sql.SQL(", ").join(cols),
            sql.SQL(", ").join([sql.Placeholder()] * len(cols)),
        ),
        [row_id, *fields.values()],
    )


def read_version(conn: Conn, table: VersionedTable, row_id: UUID) -> int:
    row = one_row(
        conn.execute(
            sql.SQL("SELECT version FROM {} WHERE id = %s").format(table.ident), (row_id,)
        )
    )
    return int(row[0])


def update_versioned(
    conn: Conn,
    table: VersionedTable,
    row_id: UUID,
    expected_version: int,
    assignments: sql.Composable,
    params: list[Any],
) -> int:
    """The correct mutation (rule control 2): read-checked, atomic. Raises
    `VersionConflict` (rule control 3) when the row exists but its version
    moved, or `RowNotFound` when the row does not exist at all (P2-1 fix) —
    never a silent zero rowcount a caller could accidentally ignore, and
    never one error type standing in for both conditions.

    Round-4 code-review R4-4 fix: the existence check and the version-
    checked update are now **one statement**, not two. The prior shape ran
    the `UPDATE` and a separate `SELECT EXISTS` as two independent
    statements on an autocommit connection — each took its own snapshot, so
    a writer that inserted `row_id` in the gap between them made the
    `UPDATE` (which ran first, saw no row) and the existence check (which
    ran second, now saw one) disagree, raising `VersionConflict` for a row
    that did not exist when the mutation actually ran — a 409 where 404 was
    the truthful answer, demonstrated live before this fix. Folding both
    into one `WITH` query makes this impossible by construction, not just
    unlikely: every part of a single statement that does not pass data to
    another part via `RETURNING` reads the *same* snapshot, taken once at
    that statement's start (PostgreSQL's own CTE semantics) — so there is
    no gap for a concurrent commit to land in between "did the row exist"
    and "did the update match" anymore; both questions are answered from
    the one snapshot this one statement took. This is also still exactly
    one round trip, so control 2's "one atomic statement" is strengthened,
    not weakened."""
    stmt = sql.SQL(
        "WITH existing AS (SELECT 1 FROM {t} WHERE id = %s), "
        "attempt AS (UPDATE {t} SET version = version + 1, {assignments} "
        "WHERE id = %s AND version = %s RETURNING 1) "
        "SELECT (SELECT count(*) FROM existing)::int, (SELECT count(*) FROM attempt)::int"
    ).format(t=table.ident, assignments=assignments)
    existing_count, updated_count = one_row(
        conn.execute(stmt, [row_id, *params, row_id, expected_version])
    )
    if updated_count:
        return int(updated_count)
    if not existing_count:
        raise RowNotFound(table, row_id)
    raise VersionConflict(table, row_id, expected_version)


def update_unversioned_blind(
    conn: Conn, table: VersionedTable, row_id: UUID, assignments: sql.Composable, params: list[Any]
) -> int:
    """Deliberately-broken comparison fixture: no version predicate at all.
    Exists only so this harness's own fail-closed test can show the pattern
    detects the lost-update bug this rule exists to prevent — never a
    template for real mutation code."""
    stmt = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(table.ident, assignments)
    return conn.execute(stmt, [*params, row_id]).rowcount


# --- MOD-001's canonical fixture aggregate -----------------------------------

VERSIONED_WIDGET = VersionedTable(SCHEMA, "versioned_widget")
VERSIONED_WIDGET_COLUMNS = sql.SQL("value text NOT NULL")

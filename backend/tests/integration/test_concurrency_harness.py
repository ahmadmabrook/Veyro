"""Concurrency/versioning test pattern — GOV-01-R02, CONC category.

Proves `.claude/rules/backend/concurrency.md` against the synthetic
`concurrency_harness.versioned_widget` aggregate (`tests/harness/
concurrency.py`): positive single-writer evidence, lost-update negative
evidence (exactly one of two simulated, sequential writers succeeds, the
other gets a typed `VersionConflict`), a missing-row negative evidence
(`RowNotFound`, never conflated with a version conflict), and a
fail-closed differential proof that the deliberately-broken unversioned
comparison fixture actually loses an update when run through the identical
two-writer shape — i.e. the pattern is shown to distinguish correct from
broken, not pass either vacuously.

Round-1 code review (`knowledge/03-Modules/MOD-001/evidence/code-review/
DOM002-CONCURRENCY-PATTERN-CODE-REVIEW-ROUND1-2026-10-04.md`) found this
file's `_widget_table` fixture was session-scoped/autouse with no teardown,
which (combined with the harness sharing the tenant-isolation harness's
`"harness"` schema) made this suite's "199/199 passing" claim contingent on
pytest's default alphabetical collection order and could make the ADR-010
RLS architecture gate FAIL under a different order (P1-1/P1-2). Fixed here:
`widget` now creates and drops the table around every individual test (see
`tests/harness/concurrency.py`'s teardown contract), and the aggregate lives
in its own exclusively-owned `concurrency_harness` schema. See
`test_concurrency_harness_order_independence.py` for the permanent,
automated regression coverage pinning the review's own §4.4/§4.5 drills.

Scope note: this proves the test *pattern* works on a synthetic aggregate.
It does not by itself promote or claim PASS on `SCN-MOD001-009`. That
scenario's former GOV-01-R04/TSD §24.1 "gate 2" label was confirmed a
catalog error and corrected to GOV-01-R02/CONC on 2026-10-04 (gate 2 is the
module dependency/SQL lint, per `IMPLEMENTATION.md` §4) — see
`knowledge/00-System/DOM002-CONVERGENCE-ASSESSMENT-2026-10-04.md` and the
`SCENARIOS.md` entry. What remained unsatisfied after that correction was
the scenario's own *evidence* clause, which asks for more than a pass/fail
signal: "both write attempts' outcomes logged; exactly one succeeds, one
gets a version-conflict error." Assertions alone prove that to whoever reads
the source; they leave no durable artifact an auditor can read the two
outcomes *off*. `_evidence` below closes that gap, using the same
`{TAG}-EVIDENCE <json>` stdout convention this suite's sibling harnesses
already use (`test_authn_harness.py`, `test_architecture_gate_rls.py`) —
no new mechanism invented for this one scenario. Promotion itself still
needs an independent review of this instrumentation (DC-06: no
self-approval), which this file cannot grant itself.

Only reuses the generic `pg`/`admin` fixtures from `conftest.py`; does not
touch the tenant-isolation-specific `runtime`/`tenants`/`elevated_login`
fixtures, which this pattern has no dependency on.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from psycopg import sql

from tests.harness.concurrency import (
    VERSIONED_WIDGET,
    VERSIONED_WIDGET_COLUMNS,
    Conn,
    RowNotFound,
    VersionConflict,
    create_versioned_table,
    drop_versioned_table,
    insert,
    read_version,
    update_unversioned_blind,
    update_versioned,
)


def _evidence(tag: str, payload: Any) -> None:
    """Durable, machine-readable outcome record on stdout — identical
    convention to `test_authn_harness.py` and `test_architecture_gate_rls.py`
    (deliberately reused rather than reinvented). `pytest -s` (or `-rA` with
    captured output shown on the report) puts the line in the run log that
    gets quoted into `knowledge/03-Modules/MOD-001/evidence/`, which is what
    `SCN-MOD001-009`'s "both write attempts' outcomes logged" clause asks
    for: a record an auditor reads the outcomes off, not an assertion they
    must trust the source of."""
    print(f"{tag}-EVIDENCE {json.dumps(payload, sort_keys=True, default=str)}")


def _attempt(writer: str, expected_version: int, mutate: Callable[[], int]) -> dict[str, Any]:
    """Runs one synthetic writer's attempt and reduces it to a serializable
    outcome record, so "exactly one succeeds, one gets a version-conflict
    error" becomes a *counted* property of two uniformly-recorded attempts
    rather than a shape the reader has to infer from which call sites happen
    to be wrapped in `pytest.raises`. Both writers go through this same
    helper, so neither is privileged by its call shape.

    Catches only the two typed errors this harness defines — any other
    exception propagates and fails the test, exactly as before. The typed
    error's own attributes are copied into the record (not just its
    message), so the assertions below can still check them and the logged
    evidence carries them too."""
    try:
        return {
            "writer": writer,
            "expected_version": expected_version,
            "outcome": "committed",
            "rowcount": mutate(),
            "error": None,
        }
    except VersionConflict as exc:
        error: dict[str, Any] = {
            "type": "VersionConflict",
            "message": str(exc),
            "conflict_expected_version": exc.expected_version,
        }
    except RowNotFound as exc:
        error = {"type": "RowNotFound", "message": str(exc), "row_id": str(exc.row_id)}
    return {
        "writer": writer,
        "expected_version": expected_version,
        "outcome": "rejected",
        "rowcount": 0,
        "error": error,
    }


@pytest.fixture
def widget(admin: Conn) -> Iterator[UUID]:
    """Creates the table, inserts one fresh row, yields its id, then drops
    the table — scoped to a single test (round-1 review P1-2 fix) so no
    architecture-gate invocation running later in the same session can ever
    see this synthetic relation. The drop is wrapped in `try`/`finally`
    around everything after the create (round-2 review R2-2 fix): a plain
    post-`yield` statement only runs if `yield` is actually reached, so a
    failure in `insert` between the create and the `yield` — reproduced live
    by round 2's own §4.11 drill — would otherwise leak the table for the
    rest of the session, the exact P1-2 condition this fixture exists to
    prevent. The sibling test below already used this `try`/`finally` idiom
    for its own inline create/drop; this fixture now matches it."""
    create_versioned_table(admin, VERSIONED_WIDGET, VERSIONED_WIDGET_COLUMNS)
    try:
        row_id = uuid4()
        insert(admin, VERSIONED_WIDGET, row_id, {"value": "initial"})
        yield row_id
    finally:
        drop_versioned_table(admin, VERSIONED_WIDGET)


def test_single_writer_succeeds_and_increments_version(admin: Conn, widget: UUID) -> None:
    """Positive control: a correctly-versioned mutation applies and the
    version column advances exactly once."""
    row_id = widget
    before = read_version(admin, VERSIONED_WIDGET, row_id)
    rowcount = update_versioned(
        admin, VERSIONED_WIDGET, row_id, before,
        sql.SQL("value = %s"), ["updated-once"],
    )
    assert rowcount == 1
    assert read_version(admin, VERSIONED_WIDGET, row_id) == before + 1


def test_concurrent_writers_lost_update_detected(admin: Conn, widget: UUID) -> None:
    """Two simulated, sequential (not real-parallel — see the harness
    module's own "Known ceiling" note) 'requests' both read version N. The
    first commits and advances to N+1; the second, still holding stale N,
    must be rejected with a `VersionConflict` rather than silently
    overwriting the first writer's change (DOM-002 lost-update
    requirement).

    This is `SCN-MOD001-009`'s own scenario body, and its evidence clause
    asks for both attempts' outcomes to be *logged*, not merely asserted.
    Both attempts therefore run through the same `_attempt` recorder and the
    pair is emitted via `_evidence`; the "exactly one / exactly one" property
    is asserted as a count over those two records, which also rules out the
    two failure modes a `pytest.raises`-only shape cannot see at all: two
    successes (the lost update), and a rejection that is the *wrong* typed
    error (`RowNotFound` standing in for a version conflict — round-1 review
    P2-1's defect class)."""
    row_id = widget
    writer_a_version = read_version(admin, VERSIONED_WIDGET, row_id)
    writer_b_version = read_version(admin, VERSIONED_WIDGET, row_id)
    assert writer_a_version == writer_b_version  # both read the same starting version

    attempts = [
        _attempt("writer-a", writer_a_version, lambda: update_versioned(
            admin, VERSIONED_WIDGET, row_id, writer_a_version,
            sql.SQL("value = %s"), ["writer-a"],
        )),
        _attempt("writer-b", writer_b_version, lambda: update_versioned(
            admin, VERSIONED_WIDGET, row_id, writer_b_version,
            sql.SQL("value = %s"), ["writer-b"],
        )),
    ]

    committed = [a for a in attempts if a["outcome"] == "committed"]
    rejected = [a for a in attempts if a["outcome"] == "rejected"]
    assert len(attempts) == 2, "scenario requires exactly two recorded writer attempts"
    assert len(committed) == 1, f"expected exactly one committed write, got {committed}"
    assert len(rejected) == 1, f"expected exactly one rejected write, got {rejected}"
    assert committed[0]["writer"] == "writer-a"
    assert committed[0]["rowcount"] == 1
    assert rejected[0]["writer"] == "writer-b"
    # Must be the version-conflict error specifically, never `RowNotFound`.
    assert rejected[0]["error"]["type"] == "VersionConflict"
    assert rejected[0]["error"]["conflict_expected_version"] == writer_b_version

    final = admin.execute(
        sql.SQL("SELECT value, version FROM {} WHERE id = %s").format(VERSIONED_WIDGET.ident),
        (row_id,),
    ).fetchone()
    assert final is not None
    value, version = final
    assert value == "writer-a"  # writer-a's write is the one that survived
    assert version == writer_a_version + 1

    _evidence("SCN-MOD001-009", {
        "aggregate": str(VERSIONED_WIDGET),
        "row_id": str(row_id),
        "concurrency_shape": "two simulated sequential writers on one connection "
                             "(see tests/harness/concurrency.py 'Known ceiling')",
        "starting_version": writer_a_version,
        "attempts": attempts,
        "committed_count": len(committed),
        "rejected_count": len(rejected),
        "final_row": {"value": value, "version": version},
        "lost_update_resolution": "reject-and-retry (REQUIREMENTS.md DOM-002 row)",
    })


def test_update_versioned_distinguishes_missing_row_from_version_conflict(admin: Conn) -> None:
    """P2-1 fix: a zero rowcount has two distinct causes — a stale version
    and a row that was never there. `update_versioned` must raise
    `RowNotFound`, never a `VersionConflict` with a fabricated expected
    version, for a row that was never inserted. Deliberately does not use
    the `widget` fixture, since the point is to probe an id that never
    existed."""
    create_versioned_table(admin, VERSIONED_WIDGET, VERSIONED_WIDGET_COLUMNS)
    try:
        never_inserted = uuid4()
        with pytest.raises(RowNotFound) as exc_info:
            update_versioned(
                admin, VERSIONED_WIDGET, never_inserted, 1, sql.SQL("value = %s"), ["x"]
            )
        assert exc_info.value.row_id == never_inserted
    finally:
        drop_versioned_table(admin, VERSIONED_WIDGET)


def test_update_versioned_executes_exactly_one_statement(admin: Conn, widget: UUID) -> None:
    """Round-4 code-review R4-4 regression lock, structural rather than
    timing-based. `update_versioned` previously ran its version-checked
    `UPDATE` and its existence-disambiguation check as **two** separate
    statements on an autocommit connection — each took its own snapshot, so
    a genuinely concurrent writer that inserted the probed row in the gap
    between those two statements made the already-returned "zero rows
    updated" and the now-true "row exists" disagree: `update_versioned`
    raised `VersionConflict` (409-shaped) for a row that did not exist when
    its own `UPDATE` ran, when `RowNotFound` (404-shaped) was the truthful
    answer (reproduced live before this fix, with a real second connection
    inserting the row between the two statements of a hand-run equivalent).

    Fixed by folding the existence check and the update into **one** `WITH`
    statement (see `update_versioned`'s own docstring): PostgreSQL gives
    every part of a single statement that isn't chained via `RETURNING` the
    same snapshot, taken once at that statement's start — so there is no
    longer a gap between "did it exist" and "did it update" for a
    concurrent commit to land in. A timing-based test that merely tries to
    race an insert against `update_versioned` cannot reliably reopen that
    gap now that it is closed by construction (that is the point of the
    fix), so this test instead locks the structural property that makes it
    closed: counts real `execute` calls on the connection, which must be
    exactly one. A regression back to two statements would make this count
    2 and fail here, deterministically, with no dependence on scheduling.

    Must exercise the zero-rowcount (disambiguation) path specifically —
    the success path (`rowcount == 1`) was always a single statement in
    both the broken and fixed shapes, so it proves nothing about this
    defect. Uses a never-inserted row id (the `RowNotFound` path), not the
    `widget` fixture's existing row."""
    del widget  # not used: this test needs a row that was never inserted
    never_inserted = uuid4()

    executions: list[Any] = []
    real_execute = admin.execute

    def counting_execute(*args: Any, **kwargs: Any) -> Any:
        executions.append(args)
        return real_execute(*args, **kwargs)

    admin.execute = counting_execute  # type: ignore[method-assign]
    try:
        with pytest.raises(RowNotFound):
            update_versioned(
                admin, VERSIONED_WIDGET, never_inserted, 1, sql.SQL("value = %s"), ["x"]
            )
    finally:
        admin.execute = real_execute  # type: ignore[method-assign]

    assert len(executions) == 1, (
        f"update_versioned made {len(executions)} round trip(s) to the "
        f"database, expected exactly 1 — more than one reopens the TOCTOU "
        f"gap between the update and the existence check that R4-4 closed"
    )


def test_naive_unversioned_update_loses_the_update(admin: Conn, widget: UUID) -> None:
    """Fail-closed differential proof, using the identical two-writer shape
    `test_concurrent_writers_lost_update_detected` uses — both writers read
    the same starting version N (round-1 code-review P2-2 fix: the prior
    version of this test used two blind writes with no version read at all,
    which was a *weaker* shape than claimed in this docstring). Writer A
    commits through the real, correct `update_versioned`; writer B, still
    holding its stale read of N, goes through the deliberately-broken
    `update_unversioned_blind` instead of being rejected. Both writes report
    success and writer B silently overwrites writer A's committed change —
    the exact lost-update bug DOM-002 exists to prevent. The final version
    column (`writer_a_version + 1`, i.e. unchanged since writer A's commit)
    falsely implies nothing happened since writer A, while the value is
    actually writer B's — demonstrating the version column itself becomes a
    false positive once an unversioned write slips through (P3-1 strengthened
    assertion: the original test only checked the overwritten value, not
    this version/value mismatch). This test demonstrates the pattern
    distinguishes correct (`update_versioned`) from broken
    (`update_unversioned_blind`); it is not a template for real mutation
    code."""
    row_id = widget
    writer_a_version = read_version(admin, VERSIONED_WIDGET, row_id)
    writer_b_version = read_version(admin, VERSIONED_WIDGET, row_id)
    assert writer_a_version == writer_b_version  # identical precondition to the negative test above

    attempts = [
        _attempt("writer-a", writer_a_version, lambda: update_versioned(
            admin, VERSIONED_WIDGET, row_id, writer_a_version,
            sql.SQL("value = %s"), ["writer-a"],
        )),
        _attempt("writer-b", writer_b_version, lambda: update_unversioned_blind(
            admin, VERSIONED_WIDGET, row_id, sql.SQL("value = %s"), ["writer-b"],
        )),
    ]

    # Same recorder, same record shape as the correct path above — which is
    # what makes the logged evidence non-vacuous: on the broken fixture the
    # record reads two `committed` attempts and zero rejections, so a
    # `SCN-MOD001-009` evidence line showing 1/1 could not have been produced
    # by an implementation missing its version predicate.
    assert [a["outcome"] for a in attempts] == ["committed", "committed"]
    assert attempts[1]["rowcount"] == 1  # the broken path never rejects writer-b's stale read

    final = admin.execute(
        sql.SQL("SELECT value, version FROM {} WHERE id = %s").format(VERSIONED_WIDGET.ident),
        (row_id,),
    ).fetchone()
    assert final is not None
    value, version = final
    # Writer-a's committed update is silently lost — this is the defect, not the proof's failure.
    assert value == "writer-b"
    # The version column never moved past writer-a's commit: a later reader
    # trusting "version == writer_a_version + 1 means writer-a's write stands"
    # would be wrong, because writer-b's unversioned write landed underneath it.
    assert version == writer_a_version + 1

    _evidence("SCN-MOD001-009-DIFFERENTIAL[unversioned-control]", {
        "aggregate": str(VERSIONED_WIDGET),
        "row_id": str(row_id),
        "starting_version": writer_a_version,
        "attempts": attempts,
        "committed_count": 2,
        "rejected_count": 0,
        "final_row": {"value": value, "version": version},
        "note": "deliberately-broken comparison fixture; lost update is the expected outcome",
    })

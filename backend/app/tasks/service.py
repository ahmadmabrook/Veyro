"""MOD-026 slice 1b: the I/O, and the four things about it that are load-bearing.

**A subject is resolved inside the transaction that writes the row, for the five kinds that
have a table.** `subjects.RESOLVABLE` is that map. A task naming an invoice nobody issued is
work about nothing, and this build has the finding already: MOD-009's erasure "recorded
`done / 0` for each target and completed" because `subject_id` carried no foreign key and
nothing resolved it. The three kinds whose modules do not exist are recorded as claims and
every read says which it was -- presenting an unresolved id as a verified reference is
MOD-012's `validated` shape.

**Two prose columns are masked and the read takes the permission as a required argument.**
`settle_reason` and `resolution_reason` are where a health fact goes in practice: MOD-019
masks a session change's reason for exactly that, after a reviewer read a diagnosis out of
one. MOD-014's rule is why it is an argument rather than a default -- "a read path that could
be called without it is a read path somebody calls without it", which is how `Decision.mask`
went unapplied for five modules.

**Every create is idempotent to the caller and answers from the row it already wrote.** Not
409: a caller told "conflict" cannot tell a duplicate request from a real collision, which is
MOD-017's finding in three commands at once.

**A status change that changes nothing is refused**, because it would write an attribution for
a decision nobody made -- the "evidence with nobody's name on it" rule from the other side.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from psycopg import Connection
from psycopg import Error as PsycopgError

from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound, ServiceError
from app.tasks import sla, subjects, workflow

#: Every listing read is bounded and ordered. Unbounded is a bulk export and a denial of
#: service at once; unordered makes the planner the author, which is MOD-018's `chart_for`
#: finding. The ceiling is refused above rather than silently clamped, because a caller that
#: asked for 500 and got 100 does not know it is looking at a page.
PAGE = 100

#: The value a masked reason is replaced with. A marker rather than an omission: an absent key
#: and a withheld one are different facts, and MOD-014's rule is that a redacted record still
#: exists -- telling a coach there is no reason when there are three is the worse answer.
WITHHELD = "__withheld__"


def _now() -> datetime:
    """UTC, always. A fixture taking its own clock from the local one disagrees with this for
    as long as the two dates differ, which this repository has paid for twice."""
    return datetime.now(UTC)


def _resolve_subject(conn: Connection, kind: str, subject_id: str | None) -> bool:
    """Check the subject exists where it can be checked. Returns whether it is a claim.

    **Refuses rather than recording an unresolvable id for the five kinds that have a table.**
    The table name comes from `subjects.RESOLVABLE` and never from the caller, so there is no
    path from request input to a table name.
    """
    subjects.check_subject(kind, subject_id)
    if kind == "tenant":
        return False
    if subjects.is_a_claim(kind):
        return True
    table = subjects.table_for(kind)
    column = {
        "plt01.ppl_persons": "person_id",
        "plt01.fin_invoices": "invoice_id",
        "plt01.sec_incidents": "incident_id",
        "plt01.dev_devices": "device_id",
        "plt01.bkg_bookings": "booking_id",
    }[table]
    found = conn.execute(
        f"SELECT 1 FROM {table} WHERE {column} = %s",  # noqa: S608 - both are literals above
        (subject_id,),
    ).fetchone()
    if found is None:
        raise NotFound(f"no {kind} with that id in this tenant")
    return False


# ----------------------------------------------------------------------- queues


def create_queue(
    pool: Pool, tenant_id: str, *, queue_key: str, display_name: str,
    location_id: str | None, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Open a work queue. Idempotent on `queue_key`, which is the queue's identity."""
    with tenant_scope(pool, tenant_id) as conn:
        existing = conn.execute(
            "SELECT queue_id, display_name, status FROM plt01.tsk_queues WHERE queue_key = %s",
            (queue_key,),
        ).fetchone()
        if existing is not None:
            return {"queue_id": str(existing[0]), "queue_key": queue_key,
                    "display_name": str(existing[1]), "status": str(existing[2]),
                    "repeated": True}
        row = conn.execute(
            "INSERT INTO plt01.tsk_queues"
            " (tenant_id, queue_key, display_name, location_id, created_by,"
            "  create_correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING queue_id",
            (tenant_id, queue_key, display_name, location_id, actor_id, correlation_id),
        ).fetchone()
        assert row is not None
        return {"queue_id": str(row[0]), "queue_key": queue_key,
                "display_name": display_name, "status": "active", "repeated": False}


def retire_queue(
    pool: Pool, tenant_id: str, queue_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Stop a queue taking work. Reversible, which is why the permission is routine.

    **The open work is counted and returned rather than refused.** A queue with tasks in it is
    the ordinary case for a retirement -- a team is merged into another -- and refusing would
    make somebody settle twenty tasks before they could close a queue they no longer use. What
    would be wrong is doing it silently, so the count is in the answer.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status FROM plt01.tsk_queues WHERE queue_id = %s FOR UPDATE",
            (queue_id,),
        ).fetchone()
        if row is None:
            raise NotFound("queue_not_found")
        if str(row[0]) == "retired":
            return {"queue_id": queue_id, "status": "retired", "repeated": True,
                    "open_tasks": 0}
        open_tasks = conn.execute(
            "SELECT count(*) FROM plt01.tsk_tasks"
            " WHERE queue_id = %s AND status IN ('open', 'in_progress', 'blocked')",
            (queue_id,),
        ).fetchone()
        conn.execute(
            "UPDATE plt01.tsk_queues SET status = 'retired', retired_at = %s,"
            " retired_by = %s, retire_reason = %s, retire_correlation_id = %s"
            " WHERE queue_id = %s",
            (_now(), actor_id, reason, correlation_id, queue_id),
        )
        return {"queue_id": queue_id, "status": "retired", "repeated": False,
                "open_tasks": int(open_tasks[0]) if open_tasks else 0}


def list_queues(
    pool: Pool, tenant_id: str, *, include_retired: bool = False, limit: int = PAGE,
) -> dict[str, Any]:
    """The tenant's queues. **`include_retired` is a parameter because a retired queue is a
    state a surface has to be able to show**; MOD-009's board shipped a `Released` branch
    nothing could reach because its client never passed the equivalent flag."""
    if not 1 <= limit <= PAGE:
        raise InvalidRequest(f"limit is between 1 and {PAGE}")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT queue_id, queue_key, display_name, location_id, status, retired_at,"
            "       retire_reason"
            " FROM plt01.tsk_queues"
            " WHERE (%s OR status = 'active')"
            " ORDER BY status, queue_key LIMIT %s",
            (include_retired, limit),
        ).fetchall()
    return {"queues": [
        {"queue_id": str(r[0]), "queue_key": str(r[1]), "display_name": str(r[2]),
         "location_id": str(r[3]) if r[3] else None, "status": str(r[4]),
         "retired_at": r[5].isoformat() if r[5] else None,
         "retire_reason": str(r[6]) if r[6] else None}
        for r in rows],
        # **A queue's location is a scope and not a boundary**, said on the read rather than
        # implied by a column that looks like it restricts something: `permit` resolves
        # tenant-wide, so a club manager sees every queue. MOD-014's standing scope gap.
        "location_is_a_label_not_a_boundary": (
            "a queue's location says which club it belongs to; this read is not scoped by it, "
            "because authorization in this build resolves tenant-wide"),
    }


# ------------------------------------------------------------- business hours


def set_business_hours(
    pool: Pool, tenant_id: str, *, location_id: str, kind: str, weekday: int | None,
    on_date: date | None, opens_at: time | None, closes_at: time | None, note: str | None,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Add one window to a location's calendar.

    **Adding, never editing.** A window is withdrawn and a corrected one added, which is the
    same edit with a history -- MOD-019's `0017` decision, taken because an unattributed
    retime of the values the table exists to state is what the grant otherwise permits.
    """
    with tenant_scope(pool, tenant_id) as conn:
        known = conn.execute(
            "SELECT 1 FROM plt01.locations WHERE location_id = %s", (location_id,),
        ).fetchone()
        if known is None:
            raise NotFound("location_not_found")
        row = conn.execute(
            "INSERT INTO plt01.tsk_business_hours"
            " (tenant_id, location_id, kind, weekday, on_date, opens_at, closes_at, note,"
            "  created_by, create_correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING window_id",
            (tenant_id, location_id, kind, weekday, on_date, opens_at, closes_at, note,
             actor_id, correlation_id),
        ).fetchone()
        assert row is not None
        return {"window_id": str(row[0]), "location_id": location_id, "kind": kind}


def withdraw_business_hours(
    pool: Pool, tenant_id: str, window_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Take a window back. **A withdrawal, not a delete**: "was this club marked closed on the
    fourteenth, and who said so" is asked precisely when an SLA was missed."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT withdrawn_at FROM plt01.tsk_business_hours WHERE window_id = %s"
            " FOR UPDATE",
            (window_id,),
        ).fetchone()
        if row is None:
            raise NotFound("window_not_found")
        if row[0] is not None:
            return {"window_id": window_id, "repeated": True}
        conn.execute(
            "UPDATE plt01.tsk_business_hours SET withdrawn_at = %s, withdrawn_by = %s,"
            " withdraw_reason = %s, withdraw_correlation_id = %s WHERE window_id = %s",
            (_now(), actor_id, reason, correlation_id, window_id),
        )
        return {"window_id": window_id, "repeated": False}


def read_business_hours(
    pool: Pool, tenant_id: str, *, location_id: str, include_withdrawn: bool = False,
) -> dict[str, Any]:
    """A location's calendar.

    **A location with no windows has no business hours, which is not "closed all week".**
    MOD-019's first version read an empty rota as "never available" and nothing could be
    scheduled in a tenant at all, so the distinction is returned rather than left to a reader:
    `has_a_calendar` is false, and slice 3's SLA runs on wall-clock time and says so.
    """
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT window_id, kind, weekday, on_date, opens_at, closes_at, note,"
            "       withdrawn_at, withdraw_reason"
            " FROM plt01.tsk_business_hours"
            " WHERE location_id = %s AND (%s OR withdrawn_at IS NULL)"
            " ORDER BY on_date NULLS FIRST, weekday, opens_at",
            (location_id, include_withdrawn),
        ).fetchall()
        zone = conn.execute(
            "SELECT timezone FROM plt01.locations WHERE location_id = %s", (location_id,),
        ).fetchone()
    if zone is None:
        raise NotFound("location_not_found")
    live = [r for r in rows if r[7] is None]
    return {
        "location_id": location_id,
        # The zone every window is read in, named on the response because an instant without
        # one is the schedule board's own hard-won lesson.
        "timezone": str(zone[0]),
        "windows": [
            {"window_id": str(r[0]), "kind": str(r[1]),
             "weekday": int(r[2]) if r[2] is not None else None,
             "on_date": r[3].isoformat() if r[3] else None,
             "opens_at": r[4].isoformat() if r[4] else None,
             "closes_at": r[5].isoformat() if r[5] else None,
             "note": str(r[6]) if r[6] else None,
             "withdrawn_at": r[7].isoformat() if r[7] else None,
             "withdraw_reason": str(r[8]) if r[8] else None}
            for r in rows],
        "has_a_calendar": bool(live),
        "no_calendar_is_not_closed": (
            "a location with no windows has no stated business hours, which is not the same "
            "as being closed: an SLA against it runs on elapsed wall-clock time"),
    }


# ------------------------------------------------------------------- cases


def open_case(
    pool: Pool, tenant_id: str, *, case_number: str, title: str, queue_id: str,
    subject_kind: str, subject_id: str | None, priority: str, recurs_from_case_id: str | None,
    idempotency_key: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Open a case. Idempotent on the key, answered from the row already written."""
    with tenant_scope(pool, tenant_id) as conn:
        seen = conn.execute(
            "SELECT case_id, case_number, status FROM plt01.tsk_cases"
            " WHERE idempotency_key = %s",
            (idempotency_key,),
        ).fetchone()
        if seen is not None:
            return {"case_id": str(seen[0]), "case_number": str(seen[1]),
                    "status": str(seen[2]), "repeated": True}
        queue = conn.execute(
            "SELECT status FROM plt01.tsk_queues WHERE queue_id = %s", (queue_id,),
        ).fetchone()
        if queue is None:
            raise NotFound("queue_not_found")
        if str(queue[0]) != "active":
            raise Conflict("this queue is retired, so it takes no new work")
        is_claim = _resolve_subject(conn, subject_kind, subject_id)
        row = conn.execute(
            "INSERT INTO plt01.tsk_cases"
            " (tenant_id, case_number, title, queue_id, subject_kind, subject_id, priority,"
            "  recurs_from_case_id, idempotency_key, opened_by, open_correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING case_id",
            (tenant_id, case_number, title, queue_id, subject_kind, subject_id, priority,
             recurs_from_case_id, idempotency_key, actor_id, correlation_id),
        ).fetchone()
        assert row is not None
        return {"case_id": str(row[0]), "case_number": case_number, "status": "open",
                "subject_is_a_recorded_claim": is_claim, "repeated": False}


def add_case_entry(
    pool: Pool, tenant_id: str, case_id: str, *, entry_kind: str, summary: str,
    document_ref: str | None, occurred_at: datetime | None, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Write a line on a case's timeline. Insert-only: a correction is another entry."""
    with tenant_scope(pool, tenant_id) as conn:
        case = conn.execute(
            "SELECT status FROM plt01.tsk_cases WHERE case_id = %s", (case_id,),
        ).fetchone()
        if case is None:
            raise NotFound("case_not_found")
        if str(case[0]) == "closed":
            raise Conflict("this case is closed; open a new one and cite this one")
        row = conn.execute(
            "INSERT INTO plt01.tsk_case_entries"
            " (tenant_id, case_id, entry_kind, summary, document_ref, occurred_at,"
            "  recorded_by, correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, coalesce(%s, now()), %s, %s) RETURNING entry_id",
            (tenant_id, case_id, entry_kind, summary, document_ref, occurred_at, actor_id,
             correlation_id),
        ).fetchone()
        assert row is not None
        return {"entry_id": str(row[0]), "case_id": case_id}


def settle_case(
    pool: Pool, tenant_id: str, case_id: str, *, target: str, resolution_reason: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Resolve or close a case. **Forward only, and the first resolution's attribution stays.**

    A problem that returns is a new case citing this one through `recurs_from_case_id`, which
    is this build's answer everywhere else -- and here it is the only answer that can be true,
    because the attribution CHECK requires an open case to carry no resolution, so a reopen
    would erase what it is meant to preserve.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status, resolved_at, resolved_by, resolution_reason"
            " FROM plt01.tsk_cases WHERE case_id = %s FOR UPDATE",
            (case_id,),
        ).fetchone()
        if row is None:
            raise NotFound("case_not_found")
        current = str(row[0])
        if current == target:
            return {"case_id": case_id, "status": current, "repeated": True}
        workflow.check_case_transition(current, target)
        if row[1] is None:
            conn.execute(
                "UPDATE plt01.tsk_cases SET status = %s, resolved_at = %s, resolved_by = %s,"
                " resolution_reason = %s, resolve_correlation_id = %s WHERE case_id = %s",
                (target, _now(), actor_id, resolution_reason, correlation_id, case_id),
            )
        else:
            # Already resolved and now closing: the status moves and the attribution does not.
            conn.execute(
                "UPDATE plt01.tsk_cases SET status = %s WHERE case_id = %s",
                (target, case_id),
            )
        return {"case_id": case_id, "status": target, "repeated": False}


def _case_row(r: Any, may_read_reasons: bool) -> dict[str, Any]:
    return {
        "case_id": str(r[0]), "case_number": str(r[1]), "title": str(r[2]),
        "queue_id": str(r[3]), "subject_kind": str(r[4]),
        "subject_id": str(r[5]) if r[5] else None,
        "subject_is_a_recorded_claim": subjects.is_a_claim(str(r[4])),
        "priority": str(r[6]), "status": str(r[7]),
        "opened_at": r[8].isoformat(),
        "resolved_at": r[9].isoformat() if r[9] else None,
        # **Masked unless the caller may settle a case.** `resolution_reason` is prose, and
        # MOD-019 learned that a reason column is where a health fact goes in practice.
        "resolution_reason": (
            (str(r[10]) if r[10] else None) if may_read_reasons
            else (WITHHELD if r[10] else None)),
        "reason_masked": not may_read_reasons,
        "recurs_from_case_id": str(r[11]) if r[11] else None,
    }


_CASE_COLUMNS = (
    "case_id, case_number, title, queue_id, subject_kind, subject_id, priority, status,"
    " opened_at, resolved_at, resolution_reason, recurs_from_case_id"
)


def list_cases(
    pool: Pool, tenant_id: str, *, may_read_reasons: bool, queue_id: str | None = None,
    status: str | None = None, limit: int = PAGE,
) -> dict[str, Any]:
    """The tenant's cases, newest first. `may_read_reasons` is required, not defaulted."""
    if not 1 <= limit <= PAGE:
        raise InvalidRequest(f"limit is between 1 and {PAGE}")
    if status is not None and status not in workflow.CASE_STATUSES:
        # A filter value outside its domain refuses rather than returning nothing: "no cases"
        # and "that is not a status" are different answers and a list that renders both as an
        # empty table is a surface nobody can trust.
        raise InvalidRequest(f"{status!r} is not a case status")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            f"SELECT {_CASE_COLUMNS} FROM plt01.tsk_cases"
            " WHERE (%s::uuid IS NULL OR queue_id = %s)"
            "   AND (%s::text IS NULL OR status = %s)"
            " ORDER BY opened_at DESC, case_id DESC LIMIT %s",
            (queue_id, queue_id, status, status, limit),
        ).fetchall()
    return {"cases": [_case_row(r, may_read_reasons) for r in rows]}


def read_case(
    pool: Pool, tenant_id: str, case_id: str, *, may_read_reasons: bool,
) -> dict[str, Any]:
    """One case with its timeline and the tasks filed under it."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            f"SELECT {_CASE_COLUMNS} FROM plt01.tsk_cases WHERE case_id = %s", (case_id,),
        ).fetchone()
        if row is None:
            raise NotFound("case_not_found")
        entries = conn.execute(
            "SELECT entry_id, entry_kind, summary, document_ref, occurred_at, recorded_by"
            " FROM plt01.tsk_case_entries WHERE case_id = %s"
            " ORDER BY occurred_at DESC, entry_id DESC LIMIT %s",
            (case_id, PAGE),
        ).fetchall()
        tasks = conn.execute(
            "SELECT task_id, title, status, due_at FROM plt01.tsk_tasks"
            " WHERE case_id = %s ORDER BY created_at LIMIT %s",
            (case_id, PAGE),
        ).fetchall()
    out = _case_row(row, may_read_reasons)
    out["timeline"] = [
        {"entry_id": str(e[0]), "entry_kind": str(e[1]), "summary": str(e[2]),
         "document_ref": str(e[3]) if e[3] else None, "occurred_at": e[4].isoformat(),
         "recorded_by": str(e[5])}
        for e in entries]
    out["tasks"] = [
        {"task_id": str(t[0]), "title": str(t[1]), "status": str(t[2]),
         "due_at": t[3].isoformat() if t[3] else None}
        for t in tasks]
    # A document is a locator for a file this build does not hold. Said on the read rather
    # than left for a surface to discover it cannot fetch one.
    out["documents_are_references"] = (
        "a document entry carries a locator; there is no object store in this build, so "
        "nothing here serves the file it points at")
    return out


# ------------------------------------------------------------------- tasks


def create_task(
    pool: Pool, tenant_id: str, *, queue_id: str, case_id: str | None, title: str,
    subject_kind: str, subject_id: str | None, assignee_person_id: str | None,
    priority: str, due_at: datetime | None, evidence_ref: str | None,
    idempotency_key: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Raise a task. Idempotent on the key, answered from the row already written."""
    with tenant_scope(pool, tenant_id) as conn:
        seen = conn.execute(
            "SELECT task_id, title, status FROM plt01.tsk_tasks WHERE idempotency_key = %s",
            (idempotency_key,),
        ).fetchone()
        if seen is not None:
            return {"task_id": str(seen[0]), "title": str(seen[1]), "status": str(seen[2]),
                    "repeated": True}
        queue = conn.execute(
            "SELECT status FROM plt01.tsk_queues WHERE queue_id = %s", (queue_id,),
        ).fetchone()
        if queue is None:
            raise NotFound("queue_not_found")
        if str(queue[0]) != "active":
            raise Conflict("this queue is retired, so it takes no new work")
        # **Resolved here, because nothing in this application handles a psycopg error.**
        # There is no handler for `ForeignKeyViolation` or `RaiseException`, so an unknown
        # `case_id` answered 500 whether the composite key or the trigger spoke -- an id
        # shape-checked and never resolved, which is MOD-009's finding and the reason the
        # queue and the assignee two lines either side of this are looked up. The *other*
        # two refusals stay with the trigger, which is the half that holds for a writer this
        # service is not: a task may not be filed under a different queue from its case, and
        # a closed case takes no new work.
        if case_id is not None:
            holds = conn.execute(
                "SELECT 1 FROM plt01.tsk_cases WHERE case_id = %s", (case_id,),
            ).fetchone()
            if holds is None:
                raise NotFound("case_not_found")
        is_claim = _resolve_subject(conn, subject_kind, subject_id)
        if assignee_person_id is not None:
            known = conn.execute(
                "SELECT 1 FROM plt01.ppl_persons WHERE person_id = %s",
                (assignee_person_id,),
            ).fetchone()
            if known is None:
                raise NotFound("assignee_not_found")
        row = conn.execute(
            "INSERT INTO plt01.tsk_tasks"
            " (tenant_id, queue_id, case_id, title, subject_kind, subject_id,"
            "  assignee_person_id, priority, due_at, evidence_ref, idempotency_key,"
            "  created_by, create_correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " RETURNING task_id",
            (tenant_id, queue_id, case_id, title, subject_kind, subject_id,
             assignee_person_id, priority, due_at, evidence_ref, idempotency_key, actor_id,
             correlation_id),
        ).fetchone()
        assert row is not None
        return {"task_id": str(row[0]), "title": title, "status": "open",
                "subject_is_a_recorded_claim": is_claim, "repeated": False}


def change_task_status(
    pool: Pool, tenant_id: str, task_id: str, *, target: str, reason: str | None,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Move a task. A settlement carries a reason; an ordinary move does not.

    **A blocked task is unblocked before it is finished**, which `workflow` refuses and this
    repeats only by calling it: finishing one leaves a dependency that was never satisfied or
    removed, so R07 cannot say whether the blocker mattered.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status FROM plt01.tsk_tasks WHERE task_id = %s FOR UPDATE", (task_id,),
        ).fetchone()
        if row is None:
            raise NotFound("task_not_found")
        current = str(row[0])
        if current == target:
            return {"task_id": task_id, "status": current, "repeated": True}
        workflow.check_task_transition(current, target)
        needs_reason = workflow.settlement_needs_a_reason(target)
        if needs_reason and not (reason or "").strip():
            raise InvalidRequest(
                "a task is settled with a stated reason: 'why was this not done' is the "
                "question the outcome reporting exists to answer")
        if target == "in_progress":
            blockers = _blockers(conn, task_id)
            if blockers:
                raise Conflict(
                    "this task waits on " + ", ".join(blockers)
                    + "; unblock or remove the dependency first")
        if needs_reason:
            conn.execute(
                "UPDATE plt01.tsk_tasks SET status = %s, settled_at = %s, settled_by = %s,"
                " settle_reason = %s, settle_correlation_id = %s WHERE task_id = %s",
                (target, _now(), actor_id, reason, correlation_id, task_id),
            )
        else:
            conn.execute(
                "UPDATE plt01.tsk_tasks SET status = %s WHERE task_id = %s",
                (target, task_id),
            )
        return {"task_id": task_id, "status": target, "repeated": False}


def assign_task(
    pool: Pool, tenant_id: str, task_id: str, *, assignee_person_id: str | None,
) -> dict[str, Any]:
    """Point a task at somebody, or at nobody.

    **`None` is a real argument**: unassigning returns work to the queue, which is a state
    R07 has to be able to count rather than an incomplete row.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status FROM plt01.tsk_tasks WHERE task_id = %s FOR UPDATE", (task_id,),
        ).fetchone()
        if row is None:
            raise NotFound("task_not_found")
        if str(row[0]) in workflow.SETTLED:
            raise Conflict("a settled task is not reassigned")
        if assignee_person_id is not None:
            known = conn.execute(
                "SELECT 1 FROM plt01.ppl_persons WHERE person_id = %s",
                (assignee_person_id,),
            ).fetchone()
            if known is None:
                raise NotFound("assignee_not_found")
        conn.execute(
            "UPDATE plt01.tsk_tasks SET assignee_person_id = %s WHERE task_id = %s",
            (assignee_person_id, task_id),
        )
        return {"task_id": task_id, "assignee_person_id": assignee_person_id}


def _blockers(conn: Connection, task_id: str) -> tuple[str, ...]:
    """The dependencies still in the way, named rather than counted."""
    rows = conn.execute(
        "SELECT d.depends_on_task_id, t.status FROM plt01.tsk_dependencies d"
        " JOIN plt01.tsk_tasks t ON t.task_id = d.depends_on_task_id"
        " WHERE d.task_id = %s ORDER BY d.created_at",
        (task_id,),
    ).fetchall()
    return workflow.blocking(tuple((str(r[0]), str(r[1])) for r in rows))


def add_dependency(
    pool: Pool, tenant_id: str, task_id: str, *, depends_on_task_id: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Say this task waits on that one.

    **The cycle check is the service's half and the schema cannot do it.** A self-reference is
    a CHECK; a longer loop spans rows, and every task in one is `blocked` with nothing able to
    unblock any of them -- a declared state the product cannot leave.
    """
    with tenant_scope(pool, tenant_id) as conn:
        for tid in (task_id, depends_on_task_id):
            if conn.execute(
                "SELECT 1 FROM plt01.tsk_tasks WHERE task_id = %s", (tid,),
            ).fetchone() is None:
                raise NotFound("task_not_found")
        # **An advisory lock, because `SELECT ... FOR UPDATE` needs the UPDATE privilege**
        # and this table is insert-only -- it has no UPDATE grant at all, so locking the rows
        # that way fails with `permission denied` at runtime, on whichever path happens to
        # need it. MOD-009 hit the same wall and took the same way out. The lock is wanted:
        # two concurrent inserts can each be acyclic on their own and form a loop together,
        # and every task in a cycle is blocked with nothing able to unblock it.
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('tsk_dependencies:' || %s, 0))",
            (tenant_id,),
        )
        edges = conn.execute(
            "SELECT task_id, depends_on_task_id FROM plt01.tsk_dependencies",
        ).fetchall()
        workflow.check_no_cycle(
            task_id, depends_on_task_id, tuple((str(a), str(b)) for a, b in edges))
        existing = conn.execute(
            "SELECT dependency_id FROM plt01.tsk_dependencies"
            " WHERE task_id = %s AND depends_on_task_id = %s",
            (task_id, depends_on_task_id),
        ).fetchone()
        if existing is not None:
            return {"dependency_id": str(existing[0]), "repeated": True}
        row = conn.execute(
            "INSERT INTO plt01.tsk_dependencies"
            " (tenant_id, task_id, depends_on_task_id, created_by, create_correlation_id)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING dependency_id",
            (tenant_id, task_id, depends_on_task_id, actor_id, correlation_id),
        ).fetchone()
        assert row is not None
        return {"dependency_id": str(row[0]), "repeated": False}


_TASK_COLUMNS = (
    "task_id, queue_id, case_id, title, subject_kind, subject_id, assignee_person_id,"
    " priority, status, due_at, evidence_ref, created_at, settled_at, settle_reason"
)


def _task_row(r: Any, may_read_reasons: bool) -> dict[str, Any]:
    return {
        "task_id": str(r[0]), "queue_id": str(r[1]),
        "case_id": str(r[2]) if r[2] else None, "title": str(r[3]),
        "subject_kind": str(r[4]), "subject_id": str(r[5]) if r[5] else None,
        "subject_is_a_recorded_claim": subjects.is_a_claim(str(r[4])),
        "assignee_person_id": str(r[6]) if r[6] else None,
        "priority": str(r[7]), "status": str(r[8]),
        "due_at": r[9].isoformat() if r[9] else None,
        "evidence_ref": str(r[10]) if r[10] else None,
        "created_at": r[11].isoformat(),
        "settled_at": r[12].isoformat() if r[12] else None,
        "settle_reason": (
            (str(r[13]) if r[13] else None) if may_read_reasons
            else (WITHHELD if r[13] else None)),
        "reason_masked": not may_read_reasons,
    }


def list_tasks(
    pool: Pool, tenant_id: str, *, may_read_reasons: bool, queue_id: str | None = None,
    assignee_person_id: str | None = None, status: str | None = None, limit: int = PAGE,
) -> dict[str, Any]:
    """The tenant's tasks. **No name, no address and no birth date**, because
    `tasks.task.read` is routine: a listing carrying the assignee's legal name would be a
    lateral read path around `people.person.read`, which is MOD-010's `events.event.read`
    finding. A surface composes the names through MOD-014's own gate."""
    if not 1 <= limit <= PAGE:
        raise InvalidRequest(f"limit is between 1 and {PAGE}")
    if status is not None and status not in workflow.TASK_STATUSES:
        raise InvalidRequest(f"{status!r} is not a task status")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            f"SELECT {_TASK_COLUMNS} FROM plt01.tsk_tasks"
            " WHERE (%s::uuid IS NULL OR queue_id = %s)"
            "   AND (%s::uuid IS NULL OR assignee_person_id = %s)"
            "   AND (%s::text IS NULL OR status = %s)"
            " ORDER BY due_at NULLS LAST, created_at DESC, task_id DESC LIMIT %s",
            (queue_id, queue_id, assignee_person_id, assignee_person_id, status, status,
             limit),
        ).fetchall()
    return {"tasks": [_task_row(r, may_read_reasons) for r in rows]}


def read_task(
    pool: Pool, tenant_id: str, task_id: str, *, may_read_reasons: bool,
) -> dict[str, Any]:
    """One task with its checklist and what is in its way."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            f"SELECT {_TASK_COLUMNS} FROM plt01.tsk_tasks WHERE task_id = %s", (task_id,),
        ).fetchone()
        if row is None:
            raise NotFound("task_not_found")
        items = conn.execute(
            "SELECT item_id, ordinal, label, completed_at, completed_by"
            " FROM plt01.tsk_checklist_items WHERE task_id = %s ORDER BY ordinal",
            (task_id,),
        ).fetchall()
        blockers = _blockers(conn, task_id)
    out = _task_row(row, may_read_reasons)
    out["checklist"] = [
        {"item_id": str(i[0]), "ordinal": int(i[1]), "label": str(i[2]),
         "completed_at": i[3].isoformat() if i[3] else None,
         "completed_by": str(i[4]) if i[4] else None}
        for i in items]
    out["blocked_by"] = list(blockers)
    return out


def add_checklist_item(
    pool: Pool, tenant_id: str, task_id: str, *, ordinal: int, label: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """One step on a task's checklist."""
    with tenant_scope(pool, tenant_id) as conn:
        if conn.execute(
            "SELECT 1 FROM plt01.tsk_tasks WHERE task_id = %s", (task_id,),
        ).fetchone() is None:
            raise NotFound("task_not_found")
        row = conn.execute(
            "INSERT INTO plt01.tsk_checklist_items"
            " (tenant_id, task_id, ordinal, label, created_by, create_correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING item_id",
            (tenant_id, task_id, ordinal, label, actor_id, correlation_id),
        ).fetchone()
        assert row is not None
        return {"item_id": str(row[0]), "task_id": task_id, "ordinal": ordinal}


def complete_checklist_item(
    pool: Pool, tenant_id: str, item_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Tick a step. **Once, with a name on it**: a checklist whose ticks nobody owns is a
    checklist nobody can be asked about."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT completed_at FROM plt01.tsk_checklist_items WHERE item_id = %s"
            " FOR UPDATE",
            (item_id,),
        ).fetchone()
        if row is None:
            raise NotFound("checklist_item_not_found")
        if row[0] is not None:
            return {"item_id": item_id, "repeated": True}
        conn.execute(
            "UPDATE plt01.tsk_checklist_items SET completed_at = %s, completed_by = %s,"
            " complete_correlation_id = %s WHERE item_id = %s",
            (_now(), actor_id, correlation_id, item_id),
        )
        return {"item_id": item_id, "repeated": False}


# -------------------------------------------------------------- the SLA clocks


def _calendar(conn: Connection, location_id: str) -> tuple[tuple[sla.Window, ...], str]:
    """A location's live calendar and its timezone, read together.

    **The zone is the location's and never the caller's** -- MOD-019's finding, where a rota
    read in the session's zone made a London coach available at six in the morning.
    """
    zone = conn.execute(
        "SELECT timezone FROM plt01.locations WHERE location_id = %s", (location_id,),
    ).fetchone()
    if zone is None:
        raise NotFound("location_not_found")
    rows = conn.execute(
        "SELECT kind, weekday, on_date, opens_at, closes_at"
        " FROM plt01.tsk_business_hours"
        " WHERE location_id = %s AND withdrawn_at IS NULL",
        (location_id,),
    ).fetchall()
    return tuple(sla.Window(str(r[0]), r[1], r[2], r[3], r[4]) for r in rows), str(zone[0])


def start_clock(
    pool: Pool, tenant_id: str, *, task_id: str | None, case_id: str | None,
    target_seconds: int, escalate_to_queue_id: str | None, warn_at_basis_points: int,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Put a target on a task or a case. AUT-02-R06.

    **The location is derived from the subject's queue, not accepted.** A caller able to name
    one could measure a promise against a calendar the work is not done in -- which is
    MOD-017's `brand_id` finding, where an off-peak grant was drawn on at seven in the
    evening because the caller sent the minute.
    """
    if (task_id is None) == (case_id is None):
        raise InvalidRequest("a clock is about one task or one case, and about exactly one")
    with tenant_scope(pool, tenant_id) as conn:
        if task_id is not None:
            row = conn.execute(
                "SELECT q.location_id, t.status FROM plt01.tsk_tasks t"
                " JOIN plt01.tsk_queues q ON q.queue_id = t.queue_id"
                " WHERE t.task_id = %s",
                (task_id,),
            ).fetchone()
            if row is None:
                raise NotFound("task_not_found")
            if str(row[1]) in workflow.SETTLED:
                raise Conflict("a settled task takes no new target")
        else:
            row = conn.execute(
                "SELECT q.location_id, c.status FROM plt01.tsk_cases c"
                " JOIN plt01.tsk_queues q ON q.queue_id = c.queue_id"
                " WHERE c.case_id = %s",
                (case_id,),
            ).fetchone()
            if row is None:
                raise NotFound("case_not_found")
            if str(row[1]) == "closed":
                raise Conflict("a closed case takes no new target")
        if row[0] is None:
            raise InvalidRequest(
                "this queue belongs to no club, so there is no calendar to measure a target "
                "against; give the queue a location first")
        location_id = str(row[0])
        made = conn.execute(
            "INSERT INTO plt01.tsk_sla_clocks"
            " (tenant_id, task_id, case_id, location_id, target_seconds,"
            "  warn_at_basis_points, started_at, escalate_to_queue_id, created_by,"
            "  create_correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, now(), %s, %s, %s) RETURNING clock_id",
            (tenant_id, task_id, case_id, location_id, target_seconds,
             warn_at_basis_points, escalate_to_queue_id, actor_id, correlation_id),
        ).fetchone()
        assert made is not None
        return {"clock_id": str(made[0]), "location_id": location_id,
                "target_seconds": target_seconds}


def pause_clock(
    pool: Pool, tenant_id: str, clock_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Stop a clock, with a stated reason.

    R06's "pause reasons", and the reason is mandatory because **"why did this clock stop" is
    asked precisely when a target was missed** -- the "evidence with nobody's name on it" rule
    in the one place a missed promise gets explained.
    """
    with tenant_scope(pool, tenant_id) as conn:
        clock = conn.execute(
            "SELECT status FROM plt01.tsk_sla_clocks WHERE clock_id = %s FOR UPDATE",
            (clock_id,),
        ).fetchone()
        if clock is None:
            raise NotFound("clock_not_found")
        if str(clock[0]) != "running":
            raise Conflict(f"this clock is already {clock[0]}")
        open_pause = conn.execute(
            "SELECT pause_id FROM plt01.tsk_sla_pauses"
            " WHERE clock_id = %s AND resumed_at IS NULL",
            (clock_id,),
        ).fetchone()
        if open_pause is not None:
            return {"pause_id": str(open_pause[0]), "repeated": True}
        row = conn.execute(
            "INSERT INTO plt01.tsk_sla_pauses"
            " (tenant_id, clock_id, paused_at, reason, paused_by, pause_correlation_id)"
            " VALUES (%s, %s, now(), %s, %s, %s) RETURNING pause_id",
            (tenant_id, clock_id, reason, actor_id, correlation_id),
        ).fetchone()
        assert row is not None
        return {"pause_id": str(row[0]), "repeated": False}


def resume_clock(
    pool: Pool, tenant_id: str, clock_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Start it again. The pause row keeps when it stopped and why."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT pause_id FROM plt01.tsk_sla_pauses"
            " WHERE clock_id = %s AND resumed_at IS NULL FOR UPDATE",
            (clock_id,),
        ).fetchone()
        if row is None:
            raise Conflict("this clock is not paused")
        conn.execute(
            "UPDATE plt01.tsk_sla_pauses SET resumed_at = now(), resumed_by = %s,"
            " resume_correlation_id = %s WHERE pause_id = %s",
            (actor_id, correlation_id, row[0]),
        )
        return {"pause_id": str(row[0]), "resumed": True}


def settle_clock(
    pool: Pool, tenant_id: str, clock_id: str, *, status: str, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Judge a target once. `met`, `breached` or `cancelled`.

    **A target is judged once and the judgement does not move**, which the trigger enforces:
    re-measuring a promise after the fact is how a missed one becomes a met one.
    """
    if status not in ("met", "breached", "cancelled"):
        raise InvalidRequest("a clock settles as met, breached or cancelled")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status FROM plt01.tsk_sla_clocks WHERE clock_id = %s FOR UPDATE",
            (clock_id,),
        ).fetchone()
        if row is None:
            raise NotFound("clock_not_found")
        if str(row[0]) != "running":
            return {"clock_id": clock_id, "status": str(row[0]), "repeated": True}
        conn.execute(
            "UPDATE plt01.tsk_sla_clocks SET status = %s, settled_at = now(),"
            " settled_by = %s, settle_reason = %s, settle_correlation_id = %s"
            " WHERE clock_id = %s",
            (status, actor_id, reason, correlation_id, clock_id),
        )
        return {"clock_id": clock_id, "status": status, "repeated": False}


def _consumed(
    windows: tuple[sla.Window, ...], zone: str, *, started_at: datetime, now: datetime,
    paused: tuple[tuple[datetime, datetime], ...],
) -> tuple[int, str]:
    """How much of a target has been spent, and in which frame it was measured.

    One definition, because the read and the sweep both need it. MOD-018 shipped two
    expressions for one till balance -- one bounded by a date and one not -- and a journal
    dated next year made the drawer balance; the shape here is the same, and worse, because
    the figure a screen shows and the figure a job settles a missed promise on have to be
    the same figure or the screen is wrong about what is about to happen.

    A location with no stated business hours falls back to elapsed wall-clock time and says
    which it did. MOD-019 read an empty rota as "never available" and nothing could be
    scheduled in a tenant at all; the same silence here is a clock that never advances,
    which is a breach that never fires.
    """
    if not sla.has_hours(windows):
        return int((now - started_at).total_seconds()), "elapsed_time"
    return (sla.open_seconds(windows, zone, frm=started_at, to=now, paused=paused),
            "business_hours")


def read_clock(pool: Pool, tenant_id: str, clock_id: str) -> dict[str, Any]:
    """What this target is, and where it stands. **Computed, never stored.**

    **A location with no calendar falls back to elapsed wall-clock time and the answer says
    so**, rather than reporting zero elapsed. MOD-019 read an empty rota as "never available"
    and nothing could be scheduled in a tenant at all; here the same silence would be a clock
    that never advances, which is a breach that never fires.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT task_id, case_id, location_id, target_seconds, warn_at_basis_points,"
            "       started_at, escalate_to_queue_id, status, settled_at, settle_reason"
            " FROM plt01.tsk_sla_clocks WHERE clock_id = %s",
            (clock_id,),
        ).fetchone()
        if row is None:
            raise NotFound("clock_not_found")
        pauses = conn.execute(
            "SELECT paused_at, resumed_at, reason FROM plt01.tsk_sla_pauses"
            " WHERE clock_id = %s ORDER BY paused_at",
            (clock_id,),
        ).fetchall()
        windows, zone = _calendar(conn, str(row[2]))

    now = _now()
    spans = tuple((p[0], p[1] or now) for p in pauses)
    out: dict[str, Any] = {
        "clock_id": clock_id,
        "task_id": str(row[0]) if row[0] else None,
        "case_id": str(row[1]) if row[1] else None,
        "location_id": str(row[2]), "timezone": zone,
        "target_seconds": int(row[3]), "started_at": row[5].isoformat(),
        "escalate_to_queue_id": str(row[6]) if row[6] else None,
        "status": str(row[7]),
        "settled_at": row[8].isoformat() if row[8] else None,
        "settle_reason": str(row[9]) if row[9] else None,
        "paused": [
            {"paused_at": p[0].isoformat(),
             "resumed_at": p[1].isoformat() if p[1] else None,
             "reason": str(p[2])}
            for p in pauses],
        "is_paused": any(p[1] is None for p in pauses),
    }
    consumed, measured_in = _consumed(
        windows, zone, started_at=row[5], now=now, paused=spans)
    out["measured_in"] = measured_in
    out["consumed_seconds"] = consumed
    # **Returned rather than left to a reader**, because remaining time is the number a
    # surface renders and computing it from two instants is where a second definition
    # starts -- and it is the number `state` is derived from, so the two cannot disagree.
    out["remaining_seconds"] = max(0, int(row[3]) - consumed)
    out["state"] = sla.state(
        consumed_seconds=consumed, target_seconds=int(row[3]),
        warn_at_fraction=int(row[4]) / 10_000)
    if measured_in == "elapsed_time":
        out["no_calendar"] = (
            "this club states no business hours, so the target is measured against elapsed "
            "wall-clock time; a business-hours clock against an empty calendar would never "
            "advance, which is a breach that never fires")
        return out

    # **The due instant is projected from now on what is left, so a pause moves it.**
    # Walking forward from the start answers "when would this have been due had it never
    # stopped", which is not a question anybody asks of a clock that has stopped. A clock
    # that is paused right now has no due instant at all -- it depends on when somebody
    # resumes it -- so the field is absent rather than guessed, and `remaining_seconds` is
    # the honest answer in that case.
    out["due_at"] = None if out["is_paused"] or not out["remaining_seconds"] else \
        sla.due_at(windows, zone, started_at=now,
                   target_seconds=out["remaining_seconds"]).isoformat()
    return out


def sweep_breaches(
    pool: Pool, tenant_id: str, *, actor_id: str, correlation_id: str, limit: int = 200,
) -> dict[str, Any]:
    """Judge every running target whose time has gone, and escalate where a route says to.

    AUT-02-R06's "breach warning and escalation routes", and the half a read cannot do. The
    arithmetic says in as many words that a breach is *computed*, so until something looked,
    a missed promise stayed `running` for ever and `escalate_to_queue_id` was a column
    implying a control nobody implemented -- this build's own most-repeated finding, in the
    module whose subject is work nobody is doing.

    **Idempotent, which is what makes the schedule disposable.** `tsk_sla_settlement_is_final`
    admits one judgement per clock, and the escalation task carries a key derived from the
    clock, so a second pass over the same row settles nothing and raises nothing. That is the
    worker runtime's standing rule -- a second pass is free by construction, so there is no
    table recording what has run.

    **An escalation raises a task rather than claiming anybody was told.** MOD-013 authors a
    message and no provider collects it, so a job recording "notified" would be the
    fabricated-evidence shape this codebase has been bitten by six times. A task in the
    escalation queue is a thing somebody actually opens.

    **Each clock is judged inside its own savepoint.** MOD-010 shipped a relay whose failure
    handler raised, so one poison row aborted every healthy delivery behind it -- permanently,
    since it sorted first. The unit of failure here is one clock, and a clock whose
    escalation could not be written is left `running` rather than settled with nobody told,
    so the next pass tries again.
    """
    judged: list[str] = []
    escalated: list[str] = []
    skipped: list[dict[str, str]] = []
    considered = 0
    with tenant_scope(pool, tenant_id) as conn:
        running = conn.execute(
            "SELECT clock_id, task_id, case_id, location_id, target_seconds, started_at,"
            "       escalate_to_queue_id"
            " FROM plt01.tsk_sla_clocks WHERE status = 'running'"
            " ORDER BY started_at LIMIT %s",
            (limit,),
        ).fetchall()
        considered = len(running)
        now = _now()
        for row in running:
            clock_id = str(row[0])
            try:
                with conn.transaction():
                    outcome = _judge(
                        conn, row, now=now, tenant_id=tenant_id, actor_id=actor_id,
                        correlation_id=correlation_id)
            except (ServiceError, PsycopgError) as exc:
                # Recorded and left running. A breach settled with nobody told would be a
                # missed promise that reads as handled.
                skipped.append({"clock_id": clock_id, "why": str(exc)})
                continue
            if outcome is None:
                continue
            judged.append(clock_id)
            if outcome.get("escalated"):
                escalated.append(clock_id)
            elif outcome.get("why"):
                skipped.append({"clock_id": clock_id, "why": str(outcome["why"])})
    return {"considered": considered, "breached": len(judged),
            "escalated": len(escalated), "skipped": skipped}


def _judge(
    conn: Connection[Any], row: Any, *, now: datetime, tenant_id: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any] | None:
    """Settle one clock if its target has gone, and raise its escalation. None if not due."""
    clock_id, task_id, case_id, location_id, target, started_at, queue_id = row
    windows, zone = _calendar(conn, str(location_id))
    pauses = conn.execute(
        "SELECT paused_at, resumed_at FROM plt01.tsk_sla_pauses WHERE clock_id = %s",
        (clock_id,),
    ).fetchall()
    # **A currently-open pause is counted to now and the clock is judged anyway**, which
    # took a second look to get right. The first version returned early for any open pause,
    # reasoning that a stopped clock is not spending its target -- true, and already handled
    # by `_consumed`, which subtracts the pause. What the early return added was an escape:
    # a clock whose target had *already* gone could be kept out of the sweep for ever by
    # pausing it afterwards, and pausing a clock does not un-break a promise that is already
    # broken. The arithmetic is the whole rule; a guard beside it was a second one that
    # disagreed.
    spans = tuple((p[0], p[1] or now) for p in pauses)
    consumed, _frame = _consumed(
        windows, zone, started_at=started_at, now=now, paused=spans)
    if sla.state(consumed_seconds=consumed, target_seconds=int(target)) != "breached":
        return None
    conn.execute(
        "UPDATE plt01.tsk_sla_clocks SET status = 'breached', settled_at = %s,"
        " settled_by = %s, settle_reason = %s, settle_correlation_id = %s"
        " WHERE clock_id = %s AND status = 'running'",
        (now, actor_id,
         f"a target of {int(target)} seconds was judged against {consumed} seconds of "
         f"{_frame.replace('_', ' ')} and had gone",
         correlation_id, clock_id),
    )
    if queue_id is None:
        return {"escalated": False}
    queue = conn.execute(
        "SELECT status FROM plt01.tsk_queues WHERE queue_id = %s", (queue_id,),
    ).fetchone()
    if queue is None or str(queue[0]) != "active":
        # **A route checked once is a route with a window.** The write-time trigger refuses
        # an escalation to a retired queue; nothing stops the queue being retired
        # afterwards, and an alarm wired to a bell nobody answers is worse than none. The
        # breach stands -- it is true whatever the route says -- and the skip is reported.
        return {"escalated": False,
                "why": "the escalation queue is retired, so nothing was raised"}
    subject_kind, subject_id, title = _subject_of(conn, task_id, case_id)
    conn.execute(
        "INSERT INTO plt01.tsk_tasks"
        " (tenant_id, queue_id, title, subject_kind, subject_id, priority,"
        "  evidence_ref, idempotency_key, created_by, create_correlation_id)"
        " VALUES (%s, %s, %s, %s, %s, 'high', %s, %s, %s, %s)"
        " ON CONFLICT (tenant_id, idempotency_key) DO NOTHING",
        (tenant_id, queue_id, f"Escalated: {title}", subject_kind, subject_id,
         f"veyro://sla-clocks/{clock_id}", f"sla-breach-{clock_id}", actor_id,
         correlation_id),
    )
    return {"escalated": True}


def _subject_of(
    conn: Connection[Any], task_id: Any, case_id: Any,
) -> tuple[str, Any, str]:
    """What the escalated work is about, derived from the work rather than invented.

    **The escalation task does not cite the case**, and the schema is what decided that:
    `tsk_task_matches_its_case` refuses a task filed under a different queue from its case,
    "so the same work would not be counted in two backlogs" -- and an escalation is by
    definition filed somewhere else. So the link is the clock, through `evidence_ref`, and
    what travels is the subject: whoever the missed promise was to is who the escalation is
    about, which is what makes it answerable without opening three screens.
    """
    if task_id is not None:
        found = conn.execute(
            "SELECT subject_kind, subject_id, title FROM plt01.tsk_tasks WHERE task_id = %s",
            (task_id,),
        ).fetchone()
    else:
        found = conn.execute(
            "SELECT subject_kind, subject_id, title FROM plt01.tsk_cases WHERE case_id = %s",
            (case_id,),
        ).fetchone()
    if found is None:  # pragma: no cover - the clock carries a foreign key to both
        raise NotFound("clock_subject_not_found")
    return str(found[0]), found[1], str(found[2])

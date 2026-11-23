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

from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.tasks import subjects, workflow

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

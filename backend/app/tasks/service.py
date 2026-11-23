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

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final

from psycopg import Connection
from psycopg import Error as PsycopgError

from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound, ServiceError
from app.tasks import attention, sla, subjects, workflow

#: Every listing read is bounded and ordered. Unbounded is a bulk export and a denial of
#: service at once; unordered makes the planner the author, which is MOD-018's `chart_for`
#: finding. The ceiling is refused above rather than silently clamped, because a caller that
#: asked for 500 and got 100 does not know it is looking at a page.
PAGE = 100

#: The value a masked reason is replaced with. A marker rather than an omission: an absent key
#: and a withheld one are different facts, and MOD-014's rule is that a redacted record still
#: exists -- telling a coach there is no reason when there are three is the worse answer.
WITHHELD = "__withheld__"

#: The statuses ADM-TSK-01's three chips and `workload` both count as work in hand.
#:
#: Stated once, because the list route and the workload read answer the same question about
#: the same rows -- a chip saying 11 over a table of 14 is two definitions of "open", which is
#: MOD-018's one-module-two-definitions finding in the smallest possible space.
IN_HAND: Final[tuple[str, ...]] = ("open", "in_progress", "blocked")


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
            " WHERE queue_id = %s AND status = ANY(%s)",
            (queue_id, list(IN_HAND)),
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


#: The three ADM-TSK-01 names, closed for `subject_kind`'s reason: free text makes "how much
#: of this queue is automation" a group-by over typos, and it is the first thing a manager
#: filters on. `ai` is the canvas's "suggested by Veyro" -- nothing in this build suggests
#: anything yet, and the value exists because the vocabulary is the design's rather than this
#: module's. Checked here as well as by the CHECK, so a typo is a 422 rather than a 500: this
#: application has no handler for a psycopg error.
SOURCES: tuple[str, ...] = ("manual", "automation", "ai")


def check_source(source: str) -> None:
    if source not in SOURCES:
        raise InvalidRequest(f"a source is one of {', '.join(SOURCES)}")


def open_case(
    pool: Pool, tenant_id: str, *, case_number: str, title: str, queue_id: str,
    subject_kind: str, subject_id: str | None, priority: str, recurs_from_case_id: str | None,
    idempotency_key: str, source: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Open a case. Idempotent on the key, answered from the row already written."""
    check_source(source)
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
            "  recurs_from_case_id, idempotency_key, source, opened_by,"
            "  open_correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING case_id",
            (tenant_id, case_number, title, queue_id, subject_kind, subject_id, priority,
             recurs_from_case_id, idempotency_key, source, actor_id, correlation_id),
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
        # ADM-CC-06's header field and ADM-TSK-01's column. Named on every row, because
        # "a task nobody can account for gets ignored".
        "source": str(r[12]),
        "assignee_person_id": str(r[13]) if r[13] else None,
        "snoozed_until": r[14].isoformat() if r[14] else None,
        # The deferral's account of itself, masked like every other reason column here: it is
        # prose, and MOD-019 learned that a reason column is where a health fact goes in
        # practice -- "waiting on the member's consultant" is how one gets written.
        "snooze_reason": (
            (str(r[15]) if r[15] else None) if may_read_reasons
            else (WITHHELD if r[15] else None)),
    }


_CASE_COLUMNS = (
    "case_id, case_number, title, queue_id, subject_kind, subject_id, priority, status,"
    " opened_at, resolved_at, resolution_reason, recurs_from_case_id, source,"
    " assignee_person_id, snoozed_until, snooze_reason"
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
    idempotency_key: str, source: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Raise a task. Idempotent on the key, answered from the row already written."""
    check_source(source)
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
            "  assignee_person_id, priority, due_at, evidence_ref, idempotency_key, source,"
            "  created_by, create_correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " RETURNING task_id",
            (tenant_id, queue_id, case_id, title, subject_kind, subject_id,
             assignee_person_id, priority, due_at, evidence_ref, idempotency_key, source,
             actor_id, correlation_id),
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
    " priority, status, due_at, evidence_ref, created_at, settled_at, settle_reason, source"
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
        "source": str(r[14]),
    }


def list_tasks(
    pool: Pool, tenant_id: str, *, may_read_reasons: bool, queue_id: str | None = None,
    assignee_person_id: str | None = None, status: str | None = None,
    in_hand: bool = False, overdue: bool = False, limit: int = PAGE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The tenant's tasks. **No name, no address and no birth date**, because
    `tasks.task.read` is routine: a listing carrying the assignee's legal name would be a
    lateral read path around `people.person.read`, which is MOD-010's `events.event.read`
    finding. A surface composes the names through MOD-014's own gate.

    **`overdue` is a filter here rather than in the client, and it has to be.** ADM-TSK-01's
    third chip counts work past its due date; a client filtering the page it was given would
    report "Overdue · 2" over whichever two happened to be in the first fifty rows, which is
    the members list's own finding -- summing the page was honest and still the wrong number
    in the place a manager reads the business. It restricts to the statuses still in hand for
    the same reason the chip does: a task that was finished late is not overdue work.

    **`in_hand` is the same restriction for the unfiltered view, and it exists because the
    screen was wrong without it.** ADM-TSK-01's three chips all count work in hand, and the
    unfiltered list showed every status -- so the board read "Team · 5" over a table of six
    rows, one of them already done. That is MOD-018's one-module-two-definitions finding on a
    single screen, and it was found by rendering the page and reading it rather than by any
    assertion. A settled task is still reachable by `status`, which is what that filter is for.

    **The caller does not supply the instant.** `now` exists for the suite, which has to be
    able to say when now is; no route passes it. A caller-chosen "now" on this filter would
    decide which tasks are reported late, which is MOD-020's settlement rule one screen over.
    """
    if not 1 <= limit <= PAGE:
        raise InvalidRequest(f"limit is between 1 and {PAGE}")
    if status is not None and status not in workflow.TASK_STATUSES:
        raise InvalidRequest(f"{status!r} is not a task status")
    at = now or _now()
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            f"SELECT {_TASK_COLUMNS} FROM plt01.tsk_tasks"
            " WHERE (%s::uuid IS NULL OR queue_id = %s)"
            "   AND (%s::uuid IS NULL OR assignee_person_id = %s)"
            "   AND (%s::text IS NULL OR status = %s)"
            "   AND (NOT %s OR status = ANY(%s))"
            "   AND (NOT %s OR (due_at IS NOT NULL AND due_at < %s"
            "                   AND status = ANY(%s)))"
            " ORDER BY due_at NULLS LAST, created_at DESC, task_id DESC LIMIT %s",
            (queue_id, queue_id, assignee_person_id, assignee_person_id, status, status,
             in_hand, list(IN_HAND), overdue, at, list(IN_HAND), limit),
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
        "  evidence_ref, idempotency_key, source, created_by, create_correlation_id)"
        " VALUES (%s, %s, %s, %s, %s, 'high', %s, %s, 'automation', %s, %s)"
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


# --------------------------------------------------------------- the attention item
#
# ADM-CC-06 is a case read the way the Command Center reads it, and ADM-CC-07 is the record
# of what was resolved. `app/tasks/attention.py` holds the decisions; what is here is the
# I/O and the writes the sheet's four actions make.


def _entry(
    conn: Connection, tenant_id: str, case_id: str, *, kind: str, summary: str,
    actor_id: str, correlation_id: str,
) -> None:
    """One timeline row. The history of an act, where the column is only its current state.

    ADM-CC-06 draws "WHAT VEYRO HAS ALREADY DONE" as a timeline and the owner as a field, so
    the two are kept apart the way this module already keeps a settlement's attribution apart
    from its status: `assignee_person_id` answers "who has it", and an entry answers "who
    handed it over, to whom and when". One column cannot do both, and MOD-021's supersession
    pointers are what it costs to try.
    """
    conn.execute(
        "INSERT INTO plt01.tsk_case_entries"
        " (tenant_id, case_id, entry_kind, summary, recorded_by, correlation_id)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (tenant_id, case_id, kind, summary, actor_id, correlation_id),
    )


def assign_case(
    pool: Pool, tenant_id: str, case_id: str, *, assignee_person_id: str | None,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Assign, take over or release. ADM-CC-06's three assignment actions, one write.

    **One function, because they are one fact changing.** The canvas labels them differently
    -- "Assign to…" on an unassigned item, "Release" on your own, "Take over that records the
    handover" on somebody else's -- and all three set `assignee_person_id`. Which it was is
    derived from what the column held, so a caller cannot declare a release and perform a
    handover, and the entry says which happened.

    **The entry names both person ids rather than two names.** A name would be a copy of
    MOD-014's data in an insert-only column no erasure reaches; an id discloses nothing a
    reader of this case cannot already see on the row, and a surface resolves it through
    MOD-014's own gate.

    A resolved case may still be re-assigned: ADM-CC-06 offers Reopen, and somebody has to
    own the follow-up. A *closed* one may not, which is the same line the task trigger draws.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status, assignee_person_id FROM plt01.tsk_cases WHERE case_id = %s"
            " FOR UPDATE",
            (case_id,),
        ).fetchone()
        if row is None:
            raise NotFound("case_not_found")
        if str(row[0]) == "closed":
            raise Conflict("this case is closed, so its ownership does not move")
        before = str(row[1]) if row[1] else None
        if assignee_person_id is not None:
            known = conn.execute(
                "SELECT 1 FROM plt01.ppl_persons WHERE person_id = %s",
                (assignee_person_id,),
            ).fetchone()
            if known is None:
                raise NotFound("assignee_not_found")
        if before == assignee_person_id:
            # Idempotent to the caller rather than a second entry saying nothing happened.
            return {"case_id": case_id, "assignee_person_id": before, "act": "unchanged",
                    "repeated": True}
        # **Snake case, like every other value on this wire.** `handed over` carried a space
        # and nothing else in this build does: a client branching on it has to quote a string
        # with a space in it, and the timeline summary below reads the value too.
        act = ("released" if assignee_person_id is None
               else "assigned" if before is None else "handed_over")
        conn.execute(
            "UPDATE plt01.tsk_cases SET assignee_person_id = %s WHERE case_id = %s",
            (assignee_person_id, case_id),
        )
        _entry(conn, tenant_id, case_id, kind="assignment",
               summary=f"{act}: {before or 'nobody'} -> {assignee_person_id or 'nobody'}",
               actor_id=actor_id, correlation_id=correlation_id)
    return {"case_id": case_id, "assignee_person_id": assignee_person_id, "act": act,
            "repeated": False}


def snooze_case(
    pool: Pool, tenant_id: str, case_id: str, *, until: datetime, reason: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Defer an exception with an account of why. ADM-CC-06.

    "Snoozing requires a reason and a return date -- an exception cannot be dismissed, only
    deferred with an account of why." Both are required arguments here and the schema refuses
    one without the other, so the two layers agree rather than one trusting the other.

    **A past return date is refused with a reason rather than accepted and ignored.** The
    CHECK bounds the far end at a year from the deferral and this bounds the near one,
    because `snoozed_until <= now()` is a deferral that is over before it starts:
    `item_state` would read it as `open` and the caller would be told it worked.
    """
    now = _now()
    if not reason.strip():
        raise InvalidRequest("a deferral states why")
    if until <= now:
        raise InvalidRequest("a return date is in the future")
    if until > now + timedelta(days=365):
        raise InvalidRequest(
            "a deferral longer than a year is a dismissal, and an exception cannot be "
            "dismissed")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status FROM plt01.tsk_cases WHERE case_id = %s FOR UPDATE", (case_id,),
        ).fetchone()
        if row is None:
            raise NotFound("case_not_found")
        if str(row[0]) != "open":
            raise Conflict("this case is settled, so there is nothing to defer")
        conn.execute(
            "UPDATE plt01.tsk_cases SET snoozed_at = %s, snoozed_until = %s,"
            " snooze_reason = %s, snoozed_by = %s, snooze_correlation_id = %s"
            " WHERE case_id = %s",
            (now, until, reason, actor_id, correlation_id, case_id),
        )
        _entry(conn, tenant_id, case_id, kind="deferral",
               summary=f"deferred to {until.isoformat()}: {reason}",
               actor_id=actor_id, correlation_id=correlation_id)
    return {"case_id": case_id, "snoozed_until": until.isoformat(), "state": "snoozed"}


def return_case_to_queue(
    pool: Pool, tenant_id: str, case_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Bring a deferred case back before its return date.

    **The remedy a routine act needs.** Deferring is `tasks.case.write`, which a front desk
    holds, and a return date typed as next year rather than next week would hide an exception
    for eleven months with nothing in the product able to bring it back -- MOD-013's "an
    irreversible act must not be declarable on a routine permission" from the other side, and
    the shape that made ADM-SCH-04's rota form unbuildable until `0017` added a withdrawal.

    The columns are cleared and **the account of why survives on the timeline**, which is why
    every deferral writes an entry: the canvas's "an exception cannot be dismissed, only
    deferred with an account of why" would be defeated by a clear that took the account with
    it.
    """
    if not reason.strip():
        raise InvalidRequest("bringing a case back states why")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT snoozed_until FROM plt01.tsk_cases WHERE case_id = %s FOR UPDATE",
            (case_id,),
        ).fetchone()
        if row is None:
            raise NotFound("case_not_found")
        if row[0] is None:
            raise Conflict("this case is not deferred")
        conn.execute(
            "UPDATE plt01.tsk_cases SET snoozed_at = NULL, snoozed_until = NULL,"
            " snooze_reason = NULL, snoozed_by = NULL, snooze_correlation_id = NULL"
            " WHERE case_id = %s",
            (case_id,),
        )
        _entry(conn, tenant_id, case_id, kind="deferral",
               summary=f"returned to the queue early, from {row[0].isoformat()}: {reason}",
               actor_id=actor_id, correlation_id=correlation_id)
    return {"case_id": case_id, "snoozed_until": None, "state": "open"}


def add_affected(
    pool: Pool, tenant_id: str, case_id: str, *, affected_kind: str, affected_id: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """One of the records an exception is about. ADM-CC-06's "THE SIX RECORDS".

    **Resolved, not merely recorded, where the kind has a table** -- `_resolve_subject` is
    the same function the case's own subject goes through, so an exception cannot be about an
    invoice nobody issued. `tenant` is not in the vocabulary: an affected record is a
    specific thing, and a case about the tenant is about the row's own `tenant_id`, which RLS
    already bounds.

    Idempotent by the key rather than by a caller-supplied one, because the key *is* the
    fact: this member is on this exception, once. That is what makes "6 affected" a count a
    batch action can be sized by.
    """
    if affected_kind == "tenant":
        raise InvalidRequest(
            "an affected record names a specific thing; a case about the tenant is the "
            "case's own subject")
    with tenant_scope(pool, tenant_id) as conn:
        case = conn.execute(
            "SELECT status FROM plt01.tsk_cases WHERE case_id = %s", (case_id,),
        ).fetchone()
        if case is None:
            raise NotFound("case_not_found")
        is_claim = _resolve_subject(conn, affected_kind, affected_id)
        written = conn.execute(
            "INSERT INTO plt01.tsk_case_affected"
            " (tenant_id, case_id, affected_kind, affected_id, added_by, correlation_id)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (tenant_id, case_id, affected_kind, affected_id) DO NOTHING"
            " RETURNING added_at",
            (tenant_id, case_id, affected_kind, affected_id, actor_id, correlation_id),
        ).fetchone()
    return {"case_id": case_id, "affected_kind": affected_kind,
            "affected_id": affected_id, "subject_is_a_recorded_claim": is_claim,
            "repeated": written is None}


def withdraw_affected(
    pool: Pool, tenant_id: str, case_id: str, *, affected_kind: str, affected_id: str,
    reason: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Take a record off an exception. A withdrawal, not a delete.

    "Was this member ever on this exception, and who said so" is asked precisely when
    somebody was contacted by mistake, so the row recedes rather than disappearing -- the
    same shape as MOD-019's rota withdrawal and MOD-007's revoked passkey.
    """
    if not reason.strip():
        raise InvalidRequest("a withdrawal states why")
    with tenant_scope(pool, tenant_id) as conn:
        moved = conn.execute(
            "UPDATE plt01.tsk_case_affected SET withdrawn_at = %s, withdrawn_by = %s,"
            " withdraw_reason = %s, withdraw_correlation_id = %s"
            " WHERE case_id = %s AND affected_kind = %s AND affected_id = %s"
            "   AND withdrawn_at IS NULL",
            (_now(), actor_id, reason, correlation_id, case_id, affected_kind, affected_id),
        )
        if moved.rowcount == 0:
            raise NotFound("affected_record_not_found")
    return {"case_id": case_id, "affected_kind": affected_kind,
            "affected_id": affected_id, "withdrawn": True}


def read_attention_item(
    pool: Pool, tenant_id: str, case_id: str, *, viewer_person_id: str | None,
    may_read_reasons: bool,
) -> dict[str, Any]:
    """ADM-CC-06's sheet: one case, its state for this reader, its records and its history.

    **The state is for this reader**, which is why `viewer_person_id` is a required argument
    rather than something the function looks up: resolving it is MOD-014's job through
    `ppl_identity_links`, and a read that did it itself would be a second resolution of the
    same fact. The route derives it and passes it, the way `may_read_reasons` arrives.

    **The affected records keep their withdrawals**, separately counted. A list that dropped
    them would make "this member was taken off by mistake" unanswerable, and one that mixed
    them in would inflate the figure the sheet's header states and a batch action is sized
    by -- so `affected` is live and `withdrawn` is its own list.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            f"SELECT {_CASE_COLUMNS}, opened_by, resolved_by, snoozed_at"
            " FROM plt01.tsk_cases WHERE case_id = %s",
            (case_id,),
        ).fetchone()
        if row is None:
            raise NotFound("case_not_found")
        entries = conn.execute(
            "SELECT entry_kind, summary, occurred_at, recorded_by, document_ref"
            " FROM plt01.tsk_case_entries WHERE case_id = %s"
            " ORDER BY occurred_at, recorded_at LIMIT %s",
            (case_id, PAGE),
        ).fetchall()
        affected = conn.execute(
            "SELECT affected_kind, affected_id, added_at, added_by, withdrawn_at,"
            "       withdrawn_by, withdraw_reason"
            " FROM plt01.tsk_case_affected WHERE case_id = %s"
            " ORDER BY added_at, affected_kind, affected_id LIMIT %s",
            (case_id, PAGE),
        ).fetchall()
        clock = conn.execute(
            "SELECT clock_id FROM plt01.tsk_sla_clocks"
            " WHERE case_id = %s AND status = 'running'",
            (case_id,),
        ).fetchone()

    now = _now()
    out = _case_row(row, may_read_reasons)
    out["opened_by"] = str(row[16])
    out["resolved_by"] = str(row[17]) if row[17] else None
    out["snoozed_at"] = row[18].isoformat() if row[18] else None
    out["state"] = attention.item_state(
        status=str(row[7]), snoozed_until=row[14], now=now,
        assignee_person_id=str(row[13]) if row[13] else None,
        viewer_person_id=viewer_person_id)
    # **Rendered either way, live only for some.** ADM-CC-06: assigned to somebody else
    # "keeps every action visible but read-only" -- hiding the actions would make the sheet
    # look like a different screen depending on who opened it.
    out["actions_are_live"] = attention.may_act(out["state"])
    out["took_seconds"] = attention.took_seconds(
        opened_at=row[8], resolved_at=row[9])
    # The clock is the age ADM-CC-06's header states; its arithmetic is `read_clock`'s and
    # this says only whether there is one, so a surface asks the one route that can answer.
    out["running_sla_clock_id"] = str(clock[0]) if clock else None
    out["entries"] = [
        {"entry_kind": str(e[0]), "summary": str(e[1]), "occurred_at": e[2].isoformat(),
         "recorded_by": str(e[3]), "document_ref": str(e[4]) if e[4] else None}
        for e in entries]
    out["affected"] = [
        {"affected_kind": str(a[0]), "affected_id": str(a[1]),
         "added_at": a[2].isoformat(), "added_by": str(a[3]),
         "subject_is_a_recorded_claim": subjects.is_a_claim(str(a[0]))}
        for a in affected if a[4] is None]
    out["withdrawn"] = [
        {"affected_kind": str(a[0]), "affected_id": str(a[1]),
         "withdrawn_at": a[4].isoformat(), "withdrawn_by": str(a[5]),
         "withdraw_reason": (str(a[6]) if may_read_reasons else WITHHELD)}
        for a in affected if a[4] is not None]
    out["affected_count"] = len(out["affected"])
    return out


#: ADM-CC-07 is "scoped to resolutions in the last 24h". A default rather than a constant in
#: the client, because the window decides what the median is a median *of* -- and a figure a
#: manager quotes should not change because two surfaces picked different defaults.
RESOLVED_WINDOW_HOURS = 24


def list_resolved(
    pool: Pool, tenant_id: str, *, may_read_reasons: bool,
    window_hours: int = RESOLVED_WINDOW_HOURS, limit: int = PAGE,
) -> dict[str, Any]:
    """ADM-CC-07: what was resolved in the window, and the median time it took.

    "Read-only for every role, including Owner. There is no un-resolve -- reopening happens
    on the item itself and appears here as a new row, so this list is a record rather than a
    state." Nothing here writes, and the recurrence a reopen creates is its own case, so it
    arrives as its own row the way the canvas says.

    **The median is computed here**, because a median in a client is a second definition of a
    figure a manager quotes -- MOD-018's "one module, two definitions of the same balance",
    and the reason `remaining_seconds` is returned rather than derived from two instants.
    """
    if not 1 <= window_hours <= 24 * 90:
        raise InvalidRequest("a resolution window is between an hour and ninety days")
    if not 1 <= limit <= PAGE:
        raise InvalidRequest(f"limit is between 1 and {PAGE}")
    since = _now() - timedelta(hours=window_hours)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT case_id, case_number, title, queue_id, resolved_by, opened_at,"
            "       resolved_at, resolution_reason, status, source"
            " FROM plt01.tsk_cases WHERE resolved_at >= %s"
            " ORDER BY resolved_at DESC LIMIT %s",
            (since, limit),
        ).fetchall()
    took = tuple(
        attention.took_seconds(opened_at=r[5], resolved_at=r[6]) or 0 for r in rows)
    return {
        "window_hours": window_hours, "since": since.isoformat(),
        "resolved": len(rows),
        # None rather than zero for an empty window -- MOD-011's rule, and a dashboard
        # reporting a median of zero would read as a team resolving everything instantly.
        "median_seconds": attention.median_seconds(took),
        "cases": [
            {"case_id": str(r[0]), "case_number": str(r[1]), "title": str(r[2]),
             "queue_id": str(r[3]), "resolved_by": str(r[4]) if r[4] else None,
             "resolved_at": r[6].isoformat(), "took_seconds": t, "status": str(r[8]),
             "source": str(r[9]),
             # The outcome is the resolution's own prose, masked like every other reason
             # column here: MOD-019 learned that a reason column is where a health fact goes
             # in practice, and a resolution is written about a person.
             "outcome": ((str(r[7]) if r[7] else None) if may_read_reasons
                         else (WITHHELD if r[7] else None)),
             "reason_masked": not may_read_reasons}
            for r, t in zip(rows, took, strict=True)],
        # Said rather than implied: this read is a record of resolutions and carries no
        # un-resolve, so a surface offering one would be offering something that does not
        # exist. A reopen is a recurrence on the item, and arrives here as its own row.
        "no_un_resolve": (
            "a resolution is not reversed here; reopening happens on the case and appears "
            "in this list as a new row"),
    }


#: The aging buckets R07 reports open work in, as upper bounds in days. Stated here rather
#: than chosen per caller, because two surfaces bucketing differently would make "how much is
#: over a week old" two numbers -- and the point of the figure is that it is comparable.
AGING_DAYS: tuple[int, ...] = (1, 7, 30)


def workload(
    pool: Pool, tenant_id: str, *, viewer_person_id: str | None,
    window_hours: int = 24 * 7, queue_id: str | None = None,
) -> dict[str, Any]:
    """AUT-02-R07, and ADM-TSK-01's three chips. Five questions over one tenant's work.

    **Counts and ids, never names.** `tasks.task.read` is routine, so a workload read
    carrying an assignee's legal name would be a lateral read path around
    `people.person.read` -- MOD-010's `events.event.read` finding, which MOD-017's listing
    reads already answer for by name-checking the absence in a test. A surface composes the
    names through MOD-014's own gate.

    **"Mine" needs a person and answers zero without one.** Staff hold permissions and do not
    have to be anybody in particular, so an unlinked identity is not an error here -- but it
    is also not everybody's work, which is what a fallback to the team count would have made
    it.
    """
    if not 1 <= window_hours <= 24 * 90:
        raise InvalidRequest("an outcome window is between an hour and ninety days")
    now = _now()
    since = now - timedelta(hours=window_hours)
    with tenant_scope(pool, tenant_id) as conn:
        chips = conn.execute(
            "SELECT count(*) FILTER (WHERE status = ANY(%s)"
            "                          AND %s::uuid IS NOT NULL"
            "                          AND assignee_person_id = %s),"
            "       count(*) FILTER (WHERE status = ANY(%s)),"
            "       count(*) FILTER (WHERE status = ANY(%s)"
            "                          AND due_at IS NOT NULL AND due_at < %s)"
            " FROM plt01.tsk_tasks"
            " WHERE (%s::uuid IS NULL OR queue_id = %s)",
            (list(IN_HAND), viewer_person_id, viewer_person_id, list(IN_HAND),
             list(IN_HAND), now, queue_id, queue_id),
        ).fetchall()[0]
        per_queue = conn.execute(
            "SELECT queue_id, status, count(*) FROM plt01.tsk_tasks"
            " WHERE status = ANY(%s)"
            "   AND (%s::uuid IS NULL OR queue_id = %s)"
            " GROUP BY queue_id, status ORDER BY queue_id, status",
            (list(IN_HAND), queue_id, queue_id),
        ).fetchall()
        aging = conn.execute(
            "SELECT count(*) FILTER (WHERE created_at >= %s),"
            "       count(*) FILTER (WHERE created_at < %s AND created_at >= %s),"
            "       count(*) FILTER (WHERE created_at < %s AND created_at >= %s),"
            "       count(*) FILTER (WHERE created_at < %s)"
            " FROM plt01.tsk_tasks"
            " WHERE status = ANY(%s)"
            "   AND (%s::uuid IS NULL OR queue_id = %s)",
            # Positional, and the status placeholder is the seventh in the statement rather
            # than the first in this tuple -- psycopg binds by order of appearance in the SQL.
            (now - timedelta(days=AGING_DAYS[0]),
             now - timedelta(days=AGING_DAYS[0]), now - timedelta(days=AGING_DAYS[1]),
             now - timedelta(days=AGING_DAYS[1]), now - timedelta(days=AGING_DAYS[2]),
             now - timedelta(days=AGING_DAYS[2]),
             list(IN_HAND), queue_id, queue_id),
        ).fetchall()[0]
        # **The bottleneck is the blocker, not the count of blocked work.** "`blocking` names
        # the blockers rather than counting them, because a count is what a reader cannot act
        # on" -- MOD-005's "a rule id is not a reason", and the same answer one level up: the
        # tasks that block the most other work, which is where somebody should look.
        blockers = conn.execute(
            "SELECT d.depends_on_task_id, count(*) AS blocking"
            " FROM plt01.tsk_dependencies d"
            " JOIN plt01.tsk_tasks b ON b.task_id = d.depends_on_task_id"
            " JOIN plt01.tsk_tasks t ON t.task_id = d.task_id"
            " WHERE b.status NOT IN ('done', 'cancelled')"
            "   AND t.status = ANY(%s)"
            " GROUP BY d.depends_on_task_id ORDER BY blocking DESC, 1 LIMIT 10",
            (list(IN_HAND),),
        ).fetchall()
        outcome = conn.execute(
            "SELECT status, source, count(*) FROM plt01.tsk_tasks"
            " WHERE settled_at >= %s AND (%s::uuid IS NULL OR queue_id = %s)"
            " GROUP BY status, source ORDER BY status, source",
            (since, queue_id, queue_id),
        ).fetchall()
        compliance = conn.execute(
            "SELECT count(*) FILTER (WHERE status = 'met'),"
            "       count(*) FILTER (WHERE status = 'breached'),"
            "       count(*) FILTER (WHERE status = 'running'),"
            "       count(*) FILTER (WHERE status = 'cancelled')"
            " FROM plt01.tsk_sla_clocks WHERE started_at >= %s",
            (since,),
        ).fetchall()[0]

    judged = int(compliance[0]) + int(compliance[1])
    return {
        "as_of": now.isoformat(), "window_hours": window_hours,
        "queue_id": queue_id,
        # ADM-TSK-01's chips, in its own order.
        "mine": int(chips[0]), "team": int(chips[1]), "overdue": int(chips[2]),
        "mine_is_zero_without_a_person_record": viewer_person_id is None,
        "per_queue": [
            {"queue_id": str(r[0]), "status": str(r[1]), "open": int(r[2])}
            for r in per_queue],
        "aging": {
            "bucket_days": list(AGING_DAYS),
            "under_a_day": int(aging[0]), "under_a_week": int(aging[1]),
            "under_a_month": int(aging[2]), "older": int(aging[3])},
        "bottleneck": [
            {"task_id": str(r[0]), "blocking": int(r[1])} for r in blockers],
        "outcome": [
            {"status": str(r[0]), "source": str(r[1]), "settled": int(r[2])}
            for r in outcome],
        "compliance": {
            "met": int(compliance[0]), "breached": int(compliance[1]),
            "running": int(compliance[2]), "cancelled": int(compliance[3]),
            # None rather than zero, and for MOD-011's reason: a window in which nothing was
            # judged is a window with no measurement, not a window in which nothing was kept.
            "met_basis_points": (
                None if judged == 0 else int(compliance[0]) * 10_000 // judged)},
    }

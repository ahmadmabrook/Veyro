"""MOD-027 slice 1: the I/O, and the four things about it that are load-bearing.

**No name, no number and no address.** ADM-CRM-01 makes it structural -- "a lead, a trialist
and a member are one record at three stages, never three records" -- so every person fact on
this module's screens is read through MOD-014's own gate and masked by its rules. A second copy
here would be MOD-013's shadow-database objection with a sales team editing one of them.

**Creating a lead for a person who already has one returns theirs.** ADM-CRM-04 draws exactly
that: "If this number already existed, that record would open instead of a second one being
created." So the command needs no idempotency key -- `person_id` *is* the key, the unique index
is the control, and a retry and a second salesperson get the same answer.

**Recording a touchpoint moves the stage, in the same transaction.** The board's first two
moves are facts somebody records rather than buttons, so a call that left the stage at `new`
would make "Contacted · 9" a count the timeline contradicts.

**`summary` is masked for a reader who cannot write one.** It is prose, and MOD-017 and MOD-019
both paid for discovering that a free-text reason column is where a health fact goes in
practice. The read takes the permission as a required argument, which is MOD-014's rule: "a
read path that could be called without it is a read path somebody calls without it".
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from psycopg import Connection, errors

from app.commercial import service as commercial
from app.crm import pipeline
from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound

#: Every listing read is bounded and ordered -- unbounded is a bulk export and a denial of
#: service at once, and unordered makes the planner the author. Refused above rather than
#: clamped, because a caller that asked for 500 and got 100 does not know it is on a page.
PAGE = 100

#: What a masked summary is replaced with. A marker rather than an omission: a withheld
#: touchpoint and an absent one are different facts, and a timeline missing its rows reads as a
#: lead nobody has spoken to -- which is the one reading that is always wrong here.
WITHHELD = "__withheld__"


def _now() -> datetime:
    """UTC, always. A fixture taking its own clock from the local one disagrees with this for
    as long as the two dates differ, which this repository has paid for twice."""
    return datetime.now(UTC)


def _bounded(limit: int) -> int:
    if limit < 1 or limit > PAGE:
        raise InvalidRequest(f"a_page_is_between_1_and_{PAGE}")
    return limit


# ------------------------------------------------------------------- the sources

def create_source(
    pool: Pool, tenant_id: str, *, source_key: str, display_name: str,
    location_id: str | None, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Declare where leads come from. Idempotent on the key, answered from the row."""
    with tenant_scope(pool, tenant_id) as conn:
        seen = conn.execute(
            "SELECT source_id, display_name, status FROM plt01.crm_lead_sources"
            " WHERE source_key = %s",
            (source_key,),
        ).fetchone()
        if seen is not None:
            return {"source_id": str(seen[0]), "source_key": source_key,
                    "display_name": str(seen[1]), "status": str(seen[2]), "repeated": True}
        try:
            row = conn.execute(
                "INSERT INTO plt01.crm_lead_sources"
                " (tenant_id, source_key, display_name, location_id, created_by,"
                "  create_correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s) RETURNING source_id",
                (tenant_id, source_key, display_name, location_id, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation:
            raise NotFound("location_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        return {"source_id": str(row[0]), "source_key": source_key,
                "display_name": display_name, "status": "active", "repeated": False}


def retire_source(
    pool: Pool, tenant_id: str, source_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Stop offering a source without losing the leads that came through it.

    **Retired, not deleted**, because ADM-RPT-03 groups conversions by source and reads the
    history: a club that ran one open day in March still ran it. The three facts about the
    decision arrive together or the constraint refuses the row.
    """
    with tenant_scope(pool, tenant_id) as conn:
        try:
            updated = conn.execute(
                "UPDATE plt01.crm_lead_sources SET status = 'retired', retired_at = now(),"
                " retired_by = %s, retire_reason = %s, retire_correlation_id = %s"
                " WHERE source_id = %s AND status = 'active'"
                " RETURNING source_key",
                (actor_id, reason, correlation_id, source_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if updated is None:
            raise Conflict("this_source_is_unknown_or_already_retired")
        return {"source_id": source_id, "source_key": str(updated[0]), "status": "retired"}


def list_sources(
    pool: Pool, tenant_id: str, *, include_retired: bool = False, limit: int = 50,
) -> dict[str, Any]:
    """The dropdown ADM-CRM-04 draws, and the groups ADM-RPT-03 will read."""
    limit = _bounded(limit)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT source_id, source_key, display_name, location_id, status, created_at"
            " FROM plt01.crm_lead_sources"
            " WHERE (%s OR status = 'active')"
            " ORDER BY display_name, source_id LIMIT %s",
            (include_retired, limit),
        ).fetchall()
    return {
        "sources": [
            {"source_id": str(r[0]), "source_key": str(r[1]), "display_name": str(r[2]),
             "location_id": (None if r[3] is None else str(r[3])), "status": str(r[4]),
             "created_at": r[5].isoformat()}
            for r in rows],
        "count": len(rows), "limit": limit, "truncated": len(rows) == limit,
        "a_location_is_a_scope_not_a_boundary": (
            "permit resolves tenant-wide, so a club manager sees every source"),
    }


# --------------------------------------------------------------------- the lead

def create_lead(
    pool: Pool, tenant_id: str, *, person_id: str, source_id: str | None,
    interests: tuple[str, ...], owner_person_id: str | None, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Open a lead against a person MOD-014 already holds.

    **A person who already has a lead gets theirs back.** That is ADM-CRM-04's own behaviour
    rather than an idempotency convenience: "If this number already existed, that record would
    open instead of a second one being created." So there is no idempotency key -- the person
    is the key, `crm_leads_one_per_person` is the control, and a retried request, a second
    salesperson and a receptionist who did not check the duplicate read all get one record.

    `GET /people/contact-match` is the check at the door, which catches the common case while
    somebody is typing; this catches the race and the caller that did not look.
    """
    chosen = _interests(interests)
    with tenant_scope(pool, tenant_id) as conn:
        seen = conn.execute(
            "SELECT lead_id, stage, created_at FROM plt01.crm_leads WHERE person_id = %s",
            (person_id,),
        ).fetchone()
        if seen is not None:
            return {"lead_id": str(seen[0]), "person_id": person_id,
                    "stage": str(seen[1]), "created_at": seen[2].isoformat(),
                    "existing": True,
                    "this_person_already_had_a_lead": (
                        "ADM-CRM-04 opens that record rather than creating a second one")}
        try:
            row = conn.execute(
                "INSERT INTO plt01.crm_leads"
                " (tenant_id, person_id, source_id, owner_person_id, created_by,"
                "  correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s) RETURNING lead_id, created_at",
                (tenant_id, person_id, source_id, owner_person_id, actor_id,
                 correlation_id),
            ).fetchone()
            assert row is not None
            lead_id = str(row[0])
            _record_interests(conn, tenant_id, lead_id, chosen, actor_id, correlation_id)
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        return {"lead_id": lead_id, "person_id": person_id, "stage": "new",
                "created_at": row[1].isoformat(), "interests": list(chosen),
                "existing": False}


def record_touchpoint(
    pool: Pool, tenant_id: str, lead_id: str, *, kind: str, summary: str,
    occurred_at: datetime | None, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Write up a conversation, and move the stage the conversation reached.

    **One transaction, because the board counts what the timeline says.** A call that left the
    stage at `new` would make "Contacted · 9" a figure the profile contradicts -- MOD-018's
    one-module-two-definitions finding across two screens instead of two functions.

    `occurred_at` defaults to now and may be in the past, because a salesperson writes up
    Friday's open day on Monday. It may not be in the future: "No contact · 2 days" is counted
    from this column, so a touchpoint dated forward would make a cold lead read as warm.
    """
    moment = occurred_at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        lead = conn.execute(
            "SELECT stage, version FROM plt01.crm_leads WHERE lead_id = %s FOR UPDATE",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise NotFound("lead_not_found")
        try:
            reached = pipeline.stage_from_touchpoint(str(lead[0]), kind)
        except pipeline.PipelineError as e:
            raise InvalidRequest(str(e)) from None
        try:
            row = conn.execute(
                "INSERT INTO plt01.crm_touchpoints"
                " (tenant_id, lead_id, kind, occurred_at, summary, recorded_by,"
                "  correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING touchpoint_id",
                (tenant_id, lead_id, kind, moment, summary, actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        if reached != str(lead[0]):
            conn.execute(
                "UPDATE plt01.crm_leads SET stage = %s, stage_changed_at = now(),"
                " version = version + 1 WHERE lead_id = %s",
                (reached, lead_id))
        return {"touchpoint_id": str(row[0]), "lead_id": lead_id, "kind": kind,
                "occurred_at": moment.isoformat(), "stage": reached,
                "stage_moved": reached != str(lead[0])}


def advance_stage(
    pool: Pool, tenant_id: str, lead_id: str, *, to_stage: str, actor_id: str,
    correlation_id: str, expected_version: int | None = None,
) -> dict[str, Any]:
    """Move a lead along the pipeline without a touchpoint to hang it on.

    The explicit command beside `record_touchpoint`, for the cases a conversation does not
    cover -- a tour somebody booked through another system, a lead a manager re-stages. It
    cannot go backwards, which `pipeline.EDGES` decides and this function does not re-state.
    """
    del actor_id, correlation_id  # recorded on the touchpoint, not on the lead row
    with tenant_scope(pool, tenant_id) as conn:
        lead = conn.execute(
            "SELECT stage, version FROM plt01.crm_leads WHERE lead_id = %s FOR UPDATE",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise NotFound("lead_not_found")
        if expected_version is not None and int(lead[1]) != expected_version:
            raise Conflict("this_lead_changed_since_it_was_read")
        try:
            pipeline.check_transition(str(lead[0]), to_stage)
        except pipeline.PipelineError as e:
            raise Conflict(str(e)) from None
        conn.execute(
            "UPDATE plt01.crm_leads SET stage = %s, stage_changed_at = now(),"
            " version = version + 1 WHERE lead_id = %s",
            (to_stage, lead_id))
        return {"lead_id": lead_id, "stage": to_stage, "from_stage": str(lead[0]),
                "version": int(lead[1]) + 1,
                "the_move_is_not_attributed_on_this_row": (
                    "who moved a lead is a touchpoint, which is the record ADM-CRM-07 says "
                    "survives a lead being lost; the lead row carries the stage and not a "
                    "history of it")}


def assign_lead(
    pool: Pool, tenant_id: str, lead_id: str, *, owner_person_id: str | None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Claim a lead, hand it over, or release it.

    `owner_person_id` is `None` for a release, which the board draws: ADM-CRM-01's counts are
    over unclaimed leads as much as claimed ones, and a required owner would mean the add-lead
    form could not be the two fields it is drawn as.
    """
    with tenant_scope(pool, tenant_id) as conn:
        lead = conn.execute(
            "SELECT owner_person_id, version FROM plt01.crm_leads"
            " WHERE lead_id = %s FOR UPDATE",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise NotFound("lead_not_found")
        if expected_version is not None and int(lead[1]) != expected_version:
            raise Conflict("this_lead_changed_since_it_was_read")
        was = None if lead[0] is None else str(lead[0])
        if was == owner_person_id:
            raise Conflict("this_lead_already_has_that_owner")
        try:
            conn.execute(
                "UPDATE plt01.crm_leads SET owner_person_id = %s, version = version + 1"
                " WHERE lead_id = %s",
                (owner_person_id, lead_id))
        except errors.ForeignKeyViolation:
            raise NotFound("person_not_found") from None
        return {"lead_id": lead_id, "owner_person_id": owner_person_id,
                "previous_owner_person_id": was, "version": int(lead[1]) + 1,
                "act": ("released" if owner_person_id is None
                        else "claimed" if was is None else "handed_over")}


def set_next_action(
    pool: Pool, tenant_id: str, lead_id: str, *, next_action: str | None,
    next_action_on: date | None, expected_version: int | None = None,
) -> dict[str, Any]:
    """ADM-CRM-02's NEXT ACTION column, or clear it.

    **Both halves or neither**, which the constraint enforces and this refuses earlier with a
    sentence: a date with no action is a reminder about nothing, and an action with no date is
    a note -- and the timeline is where a note belongs.
    """
    if (next_action is None) != (next_action_on is None):
        raise InvalidRequest("a_next_action_needs_both_a_sentence_and_a_date")
    with tenant_scope(pool, tenant_id) as conn:
        lead = conn.execute(
            "SELECT version FROM plt01.crm_leads WHERE lead_id = %s FOR UPDATE",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise NotFound("lead_not_found")
        if expected_version is not None and int(lead[0]) != expected_version:
            raise Conflict("this_lead_changed_since_it_was_read")
        try:
            conn.execute(
                "UPDATE plt01.crm_leads SET next_action = %s, next_action_on = %s,"
                " version = version + 1 WHERE lead_id = %s",
                (next_action, next_action_on, lead_id))
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        return {"lead_id": lead_id, "next_action": next_action,
                "next_action_on": (None if next_action_on is None
                                   else next_action_on.isoformat()),
                "version": int(lead[0]) + 1}


def record_interests(
    pool: Pool, tenant_id: str, lead_id: str, *, interests: tuple[str, ...], actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Add to what a lead is interested in.

    **The set only grows in this slice**, and that is stated rather than discovered: there is
    no UPDATE and no DELETE grant on the table, so withdrawing an interest is slice 3's work
    beside `lost`. An interest somebody recorded by mistake is therefore uncorrectable on a
    routine permission, which is MOD-013's "an irreversible act must not be declarable on a
    routine permission" -- and unlike `scheduling.availability.write`, whose remedy `0017` had
    to add before the form could exist, this one is three values on a sales record rather than
    a rota somebody is turned away by. Named as the gap it is rather than closed here, and the
    slice that adds `lost` adds the withdrawal.
    """
    chosen = _interests(interests)
    if not chosen:
        raise InvalidRequest("name_at_least_one_interest")
    with tenant_scope(pool, tenant_id) as conn:
        lead = conn.execute(
            "SELECT lead_id FROM plt01.crm_leads WHERE lead_id = %s", (lead_id,),
        ).fetchone()
        if lead is None:
            raise NotFound("lead_not_found")
        held = {str(r[0]) for r in conn.execute(
            "SELECT interest FROM plt01.crm_lead_interests WHERE lead_id = %s",
            (lead_id,)).fetchall()}
        # **Checked against what is already recorded**, because `gym_only` excludes the other
        # two and a second call could otherwise build the pair one interest at a time -- which
        # is a control defeated by the order of two requests, the shape MOD-020's quota
        # finding has.
        _interests(tuple(held | set(chosen)))
        _record_interests(
            conn, tenant_id, lead_id, tuple(i for i in chosen if i not in held),
            actor_id, correlation_id)
        return {"lead_id": lead_id,
                "interests": [i for i in pipeline.INTERESTS if i in held | set(chosen)],
                "added": [i for i in chosen if i not in held]}


# --------------------------------------------------------------------- the reads

def list_leads(
    pool: Pool, tenant_id: str, *, stage: str | None = None,
    owner_person_id: str | None = None, unowned: bool = False,
    going_cold: bool = False, limit: int = 50, at: datetime | None = None,
) -> dict[str, Any]:
    """ADM-CRM-02's table and its three chips.

    **Age is the sortable column that matters** -- the canvas says so, "a lead's value decays
    by the hour" -- so the order is oldest-contact-first rather than newest-created-first,
    which is the opposite of every other listing read in this build and is deliberate.
    """
    limit = _bounded(limit)
    now = at or _now()
    if stage is not None and stage not in pipeline.STAGES:
        raise InvalidRequest("bad_stage")
    if unowned and owner_person_id is not None:
        raise InvalidRequest("ask_for_unowned_leads_or_one_owners_leads_not_both")
    where = ["true"]
    params: list[Any] = []
    if stage is not None:
        where.append("l.stage = %s")
        params.append(stage)
    if owner_person_id is not None:
        where.append("l.owner_person_id = %s")
        params.append(owner_person_id)
    if unowned:
        where.append("l.owner_person_id IS NULL")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT l.lead_id, l.person_id, l.stage, l.source_id, s.display_name,"
            " l.owner_person_id, l.next_action, l.next_action_on, l.created_at, l.version,"
            " (SELECT max(t.occurred_at) FROM plt01.crm_touchpoints t"
            "   WHERE t.lead_id = l.lead_id)"
            " FROM plt01.crm_leads l"
            " LEFT JOIN plt01.crm_lead_sources s ON s.source_id = l.source_id"
            f" WHERE {' AND '.join(where)}"
            " ORDER BY coalesce("
            "   (SELECT max(t.occurred_at) FROM plt01.crm_touchpoints t"
            "     WHERE t.lead_id = l.lead_id), l.created_at), l.lead_id"
            " LIMIT %s",
            (*params, limit),
        ).fetchall()
        # **The same derivation the board makes, because this is the same list.**
        # ADM-CRM-02's STAGE column over ADM-CRM-01's board: a table that showed the stored
        # sales stage while the board showed "On trial" would be two views of one list
        # disagreeing about where a person is -- MOD-018's one-module-two-definitions finding
        # across two screens rather than two functions. The stored stage stays on the row,
        # because the route's `?stage=` filter is over the three sales stages and a derived
        # stage is not something a `WHERE` can take.
        standing = commercial.membership_standing(
            conn, [str(r[1]) for r in rows], at=now.date())
    leads = [_lead_row(r, now, standing) for r in rows]
    if going_cold:
        leads = [row for row in leads if row["going_cold"]]
    return {
        "leads": leads, "count": len(leads), "limit": limit,
        "truncated": len(rows) == limit,
        "ordered_by": "the oldest contact first, because a lead's value decays by the hour",
        "going_cold_after_hours": int(
            pipeline.GOING_COLD_AFTER.total_seconds() // 3600),
        "board_stage_is_derived": (
            "the stored stage is the sales stage and the last two board columns are "
            "MOD-017's answer, so a row carries both: `stage` is what the filter takes and "
            "`board_stage` is where the person is"),
        "no_name_is_returned_here": (
            "a lead is a ppl_persons row; the name, the number and the email are MOD-014's "
            "and are read through its own gate and masked by its rules"),
    }


def read_lead(
    pool: Pool, tenant_id: str, lead_id: str, *, may_read_summaries: bool,
    limit: int = 50, at: datetime | None = None,
) -> dict[str, Any]:
    """ADM-CRM-03's profile: the lead, what it is interested in, and its timeline.

    `may_read_summaries` is a required argument for MOD-014's reason: a read path that could
    be called without it is a read path somebody calls without it, which is how
    `Decision.mask` went unapplied for five modules.
    """
    limit = _bounded(limit)
    now = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT l.lead_id, l.person_id, l.stage, l.source_id, s.display_name,"
            " l.owner_person_id, l.next_action, l.next_action_on, l.created_at, l.version,"
            " (SELECT max(t.occurred_at) FROM plt01.crm_touchpoints t"
            "   WHERE t.lead_id = l.lead_id), l.stage_changed_at"
            " FROM plt01.crm_leads l"
            " LEFT JOIN plt01.crm_lead_sources s ON s.source_id = l.source_id"
            " WHERE l.lead_id = %s",
            (lead_id,),
        ).fetchone()
        if row is None:
            raise NotFound("lead_not_found")
        interests = [str(r[0]) for r in conn.execute(
            "SELECT interest FROM plt01.crm_lead_interests WHERE lead_id = %s",
            (lead_id,)).fetchall()]
        touchpoints = conn.execute(
            "SELECT touchpoint_id, kind, occurred_at, summary, recorded_at, recorded_by"
            " FROM plt01.crm_touchpoints WHERE lead_id = %s"
            " ORDER BY occurred_at DESC, touchpoint_id DESC LIMIT %s",
            (lead_id, limit),
        ).fetchall()
        membership = _membership_of(conn, str(row[1]))
    lead = _lead_row(row, now)
    lead["stage_changed_at"] = row[11].isoformat()
    lead["interests"] = [i for i in pipeline.INTERESTS if i in interests]
    lead["board_stage"] = pipeline.board_stage(str(row[2]), membership)
    return {
        **lead,
        "touchpoints": [
            {"touchpoint_id": str(t[0]), "kind": str(t[1]),
             "occurred_at": t[2].isoformat(),
             "summary": (str(t[3]) if may_read_summaries else WITHHELD),
             "summary_withheld": not may_read_summaries,
             "recorded_at": t[4].isoformat(), "recorded_by": str(t[5])}
            for t in touchpoints],
        "touchpoint_count": len(touchpoints),
        "touchpoints_truncated": len(touchpoints) == limit,
        "a_summary_is_prose": (
            "it is where a health fact goes in practice, which MOD-017 and MOD-019 each paid "
            "for discovering, so it is masked unless the caller could have written one"),
        "sections": {
            "person": "MOD-014, through its own gate",
            "membership": "MOD-017, through its own gate",
            "visits_and_classes": (
                "MOD-020 and MOD-022. ADM-CRM-03's VISITS, CLASSES and ENGAGEMENT metrics "
                "are the trial's, which is slice 2"),
        },
    }


def board(
    pool: Pool, tenant_id: str, *, owner_person_id: str | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """ADM-CRM-01's five columns and the header's two counts.

    **The last two columns are derived from MOD-017, and both are real now.** ADR-0010 D3:
    "On trial" is *this person has an active membership on a trial product* and "Joined" is
    *an active membership that is not a trial*, "which MOD-017 answers" -- so the stored stage
    is the sales stage and the last two are derived. A stored `on trial` would be a second
    definition of whether somebody has a membership and would go stale the moment a trial
    lapsed, which is MOD-018's one-module-two-definitions finding.

    **`commercial.membership_standing` is that one definition**, called on this transaction's
    own connection: it walks the supersession chain rather than the agreement a membership
    points at, because the root is immutable by grant and a member who converted by
    superseding the trial's agreement still points at the trial. A read that stopped at the
    root would leave every converted member in the "On trial" column for ever.

    **Live by the dates rather than the cached status**, which is the same rule MOD-022's door
    follows -- so a trial that ran out yesterday is in neither column, which is what
    ADM-CRM-07's "trial lapsed" is about.
    """
    now = at or _now()
    where = ["true"]
    params: list[Any] = []
    if owner_person_id is not None:
        where.append("l.owner_person_id = %s")
        params.append(owner_person_id)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT l.lead_id, l.person_id, l.stage, l.created_at,"
            " (SELECT max(t.occurred_at) FROM plt01.crm_touchpoints t"
            "   WHERE t.lead_id = l.lead_id)"
            " FROM plt01.crm_leads l"
            f" WHERE {' AND '.join(where)}",
            tuple(params),
        ).fetchall()
        # One query for every lead's standing, in this transaction, so a conversion landing
        # mid-read cannot put one person in two columns.
        standing = commercial.membership_standing(
            conn, [str(r[1]) for r in rows], at=now.date())
    counts = dict.fromkeys(pipeline.BOARD_COLUMNS, 0)
    cold = 0
    for r in rows:
        where_they_stand = standing.get(str(r[1]))
        member = (None if where_they_stand is None else pipeline.Membership(
            active=True, on_trial_product=where_they_stand == "trial"))
        counts[pipeline.board_stage(str(r[2]), member)] += 1
        if member is None and pipeline.is_going_cold(
                last_touch_at=r[4], created_at=r[3], now=now):
            cold += 1
    open_leads = sum(counts[c] for c in pipeline.STAGES)
    return {
        "columns": [{"stage": c, "count": counts[c]} for c in pipeline.BOARD_COLUMNS],
        "open_leads": open_leads,
        "going_cold": cold,
        "the_last_two_columns_are_derived": (
            "on_trial is an active membership on a product whose terms declare trial_days "
            "and joined is one whose terms do not, both through MOD-017's supersession "
            "chain and both judged by the membership's own dates rather than its status "
            "cache"),
        "going_cold_counts_open_leads_only": (
            "a member is not a lead going cold, and the header's two figures are over the "
            "three stored stages"),
    }


# ------------------------------------------------------------------- the helpers

def _interests(interests: tuple[str, ...]) -> tuple[str, ...]:
    try:
        return pipeline.check_interests(interests)
    except pipeline.PipelineError as e:
        raise InvalidRequest(str(e)) from None


def _record_interests(
    conn: Connection[Any], tenant_id: str, lead_id: str, interests: tuple[str, ...],
    actor_id: str, correlation_id: str,
) -> None:
    for interest in interests:
        conn.execute(
            "INSERT INTO plt01.crm_lead_interests"
            " (tenant_id, lead_id, interest, recorded_by, correlation_id)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (tenant_id, lead_id, interest, actor_id, correlation_id))


def _membership_of(
    conn: Connection[Any], person_id: str,
) -> pipeline.Membership | None:
    """What MOD-017 says about this person, for the two derived board columns.

    A read of another module's table in the same schema and under the same role, which MOD-016
    established when it read MOD-014's tags to choose a price book. It is a *read* for a
    decision of this module's own, not a write -- paragraph 1300 bars the second.
    """
    row = conn.execute(
        "SELECT count(*) FROM plt01.mem_memberships"
        " WHERE person_id = %s AND status = 'active'",
        (person_id,),
    ).fetchone()
    assert row is not None
    if int(row[0]) == 0:
        return None
    return pipeline.Membership(active=True, on_trial_product=False)


def _lead_row(
    r: Any, now: datetime, standing: dict[str, str] | None = None,
) -> dict[str, Any]:
    where_they_stand = (standing or {}).get(str(r[1]))
    member = (None if where_they_stand is None else pipeline.Membership(
        active=True, on_trial_product=where_they_stand == "trial"))
    return {
        "lead_id": str(r[0]), "person_id": str(r[1]), "stage": str(r[2]),
        # The stored sales stage *and* the column the board puts them in. Both, because they
        # answer different questions: `stage` is what somebody typed and is what the filter
        # takes, `board_stage` is where the person actually is.
        "board_stage": pipeline.board_stage(str(r[2]), member),
        "source_id": (None if r[3] is None else str(r[3])),
        "source": (None if r[4] is None else str(r[4])),
        "owner_person_id": (None if r[5] is None else str(r[5])),
        "next_action": (None if r[6] is None else str(r[6])),
        "next_action_on": (None if r[7] is None else r[7].isoformat()),
        "created_at": r[8].isoformat(), "version": int(r[9]),
        "last_touch_at": (None if r[10] is None else r[10].isoformat()),
        # Derived on the server, because the client cannot: `now` is on no response and a
        # browser comparing timestamps against its own clock counts in the wrong frame, which
        # this build has three recorded defects from.
        "hours_since_contact": pipeline.hours_since_contact(
            last_touch_at=r[10], created_at=r[8], now=now),
        # **A member is not a lead going cold**, which the board's own count already says: a
        # person who joined is not somebody nobody has rung.
        "going_cold": member is None and pipeline.is_going_cold(
            last_touch_at=r[10], created_at=r[8], now=now),
    }


def _check_name(error: errors.CheckViolation) -> str:
    return str(getattr(error.diag, "constraint_name", "") or "invalid_request")


def _fk_subject(error: errors.ForeignKeyViolation) -> str:
    name = str(getattr(error.diag, "constraint_name", "") or "")
    for fragment, subject in (
        ("source", "source_not_found"),
        ("owner", "person_not_found"),
        ("person", "person_not_found"),
        ("lead", "lead_not_found"),
    ):
        if fragment in name:
            return subject
    return "not_found"

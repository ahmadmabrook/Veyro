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

from app.access import service as access
from app.booking import service as booking
from app.catalog import service as catalog
from app.commercial import lifecycle
from app.commercial import service as commercial
from app.crm import pipeline, trial
from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.people import service as people

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

    **The set can shrink now**, which this docstring used to say it could not: `withdraw_
    interest` is the remedy ADR-0010 D11 owed, so an interest recorded by mistake is no longer
    permanent on a routine permission -- MOD-013's rule, and the gap this paragraph named.

    **Checked against the *live* set.** A withdrawn interest does not block its own return,
    which is the whole point of the partial uniqueness; what it does block is a second live
    row for the same interest.
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
        # **Live rows only, which the withdrawal made necessary.** This read was every row,
        # which was right while the set only grew -- and the moment one can be taken back it
        # means a withdrawn interest blocks its own return: a lead who wanted PT, changed
        # their mind and changed it back was answered "already recorded" and the profile kept
        # showing one interest. Found by the test written for the withdrawal.
        held = {str(r[0]) for r in conn.execute(
            "SELECT interest FROM plt01.crm_lead_interests"
            " WHERE lead_id = %s AND withdrawn_at IS NULL",
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

def mark_lead_lost(
    pool: Pool, tenant_id: str, lead_id: str, *, reason: str, detail: str | None,
    actor_id: str, correlation_id: str, expected_version: int | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """ADM-CRM-07: why did this person not join?

    **A fact beside the stage, not a sixth value in it** -- ADR-0010 D8. The stage the lead
    reached is untouched, so a reopening resumes it exactly and `Toured · 6` stays
    reconstructible; the pipeline still runs forward only and `EDGES` is unchanged.

    **The loss writes a touchpoint as well**, because D4 says the history is the timeline:
    "the same person is re-contacted, and a new record would defeat D1 ... the history is the
    touchpoint timeline rather than a chain of records". The row carries the *current* state
    and the timeline carries that it happened, which is what makes a lead lost twice for two
    reasons answerable at all -- the row keeps only the latest.

    **In one transaction**, so a lead cannot be lost with nothing in the timeline saying so.
    That is MOD-010's `append_event` argument applied to a sales record: a loss with no
    history is a refusal nobody can account for.

    **Marking a lead lost twice is refused**, rather than quietly re-dating it: the second
    call would move when they said no, and the first reason would disappear from the row with
    nothing to say it had been there. Reopen first.
    """
    now = at or _now()
    reason = _lost_reason(reason)
    said = None if detail is None or not detail.strip() else detail.strip()
    with tenant_scope(pool, tenant_id) as conn:
        lead = conn.execute(
            "SELECT version, lost_at, stage FROM plt01.crm_leads"
            " WHERE lead_id = %s FOR UPDATE",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise NotFound("lead_not_found")
        if expected_version is not None and int(lead[0]) != expected_version:
            raise Conflict("this_lead_changed_since_it_was_read")
        if lead[1] is not None:
            raise Conflict("this_lead_is_already_lost")
        try:
            conn.execute(
                "UPDATE plt01.crm_leads SET lost_at = %s, lost_reason = %s,"
                " lost_detail = %s, lost_by = %s, version = version + 1"
                " WHERE lead_id = %s",
                (now, reason, said, actor_id, lead_id))
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        conn.execute(
            "INSERT INTO plt01.crm_touchpoints"
            " (tenant_id, lead_id, kind, occurred_at, summary, recorded_by, correlation_id)"
            " VALUES (%s, %s, 'note', %s, %s, %s, %s)",
            (tenant_id, lead_id, now,
             f"Marked lost: {reason}" + (f" -- {said}" if said else ""),
             actor_id, correlation_id))
    return {"lead_id": lead_id, "lost": True, "lost_reason": reason,
            "lost_detail": said, "lost_at": now.isoformat(),
            # The stage is answered because it did not move, which is the whole decision: a
            # reader who expected a sixth stage would otherwise assume it had.
            "stage": str(lead[2]), "stage_did_not_move": True,
            "version": int(lead[0]) + 1}


def reopen_lead(
    pool: Pool, tenant_id: str, lead_id: str, *, actor_id: str, correlation_id: str,
    expected_version: int | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """Put a lost lead back in the pipeline, at the stage it was already at.

    **Always permitted, which is ADR-0010 D10.** The canvas says re-contact after ninety days
    is a supported flow, and the emphasis is on "rather than a fresh record" -- the point is
    that re-contact does not duplicate the person. Locking this for ninety days would make a
    lead marked lost by mistake uncorrectable for a quarter on a routine permission, which is
    MOD-013's rule; `pipeline.is_recontactable` answers the read instead and gates nothing.

    **The stage is not touched here either.** It never moved, so there is nothing to restore
    -- and the next touchpoint advances it, because `record_touchpoint` already does. A stage
    value for `lost` would have had to choose where a reopened lead lands, and any choice is a
    number nobody can reconstruct.
    """
    now = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        lead = conn.execute(
            "SELECT version, lost_at, lost_reason, stage FROM plt01.crm_leads"
            " WHERE lead_id = %s FOR UPDATE",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise NotFound("lead_not_found")
        if expected_version is not None and int(lead[0]) != expected_version:
            raise Conflict("this_lead_changed_since_it_was_read")
        if lead[1] is None:
            raise Conflict("this_lead_is_not_lost")
        conn.execute(
            "UPDATE plt01.crm_leads SET lost_at = NULL, lost_reason = NULL,"
            " lost_detail = NULL, lost_by = NULL, version = version + 1"
            " WHERE lead_id = %s",
            (lead_id,))
        conn.execute(
            "INSERT INTO plt01.crm_touchpoints"
            " (tenant_id, lead_id, kind, occurred_at, summary, recorded_by, correlation_id)"
            " VALUES (%s, %s, 'note', %s, %s, %s, %s)",
            (tenant_id, lead_id, now,
             f"Reopened after being lost: {lead[2]}", actor_id, correlation_id))
    return {"lead_id": lead_id, "lost": False, "stage": str(lead[3]),
            "was_lost_for": str(lead[2]), "version": int(lead[0]) + 1}


def withdraw_interest(
    pool: Pool, tenant_id: str, lead_id: str, *, interest: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Take back an interest recorded by mistake. ADR-0010 D11, which `0027` said slice 3 owed.

    **A withdrawal rather than a delete.** "Was this lead ever interested in PT" is asked
    precisely when somebody has changed their mind, so the row stays and recedes -- MOD-019's
    rota withdrawal, and the reason `crm_lead_interests` holds DELETE for nobody.

    **It is the remedy a routine permission needs.** `crm.lead.write` is routine and AAL 1, and
    until now an interest recorded by mistake had no correction anywhere in the product: a
    routine permission whose every act is uncorrectable is MOD-013's "an irreversible act must
    not be declarable on a routine permission", which MOD-019 paid for with a rota somebody is
    turned away by.

    **And it is what lets the interest be recorded again.** The uniqueness is partial on live
    rows, so a lead who wanted PT, changed their mind and changed it back is a new row rather
    than a 409 -- which the total key `0027` wrote would have refused for ever.
    """
    now = at or _now()
    if interest not in pipeline.INTERESTS:
        raise InvalidRequest("that_is_not_an_interest_this_build_records")
    with tenant_scope(pool, tenant_id) as conn:
        found = conn.execute(
            "SELECT interest_id FROM plt01.crm_lead_interests"
            " WHERE lead_id = %s AND interest = %s AND withdrawn_at IS NULL"
            " FOR UPDATE",
            (lead_id, interest),
        ).fetchone()
        if found is None:
            raise NotFound("this_lead_does_not_hold_that_interest")
        conn.execute(
            "UPDATE plt01.crm_lead_interests SET withdrawn_at = %s, withdrawn_by = %s"
            " WHERE interest_id = %s",
            (now, actor_id, str(found[0])))
    return {"lead_id": lead_id, "interest": interest, "withdrawn": True,
            "withdrawn_at": now.isoformat(),
            "it_can_be_recorded_again": (
                "the uniqueness is partial on live rows, so asking for this again is a new "
                "row rather than a refusal")}


def _lost_reason(reason: str) -> str:
    try:
        return pipeline.check_lost_reason(reason)
    except pipeline.PipelineError as e:
        raise InvalidRequest(str(e)) from None


def list_leads(
    pool: Pool, tenant_id: str, *, stage: str | None = None,
    owner_person_id: str | None = None, unowned: bool = False,
    going_cold: bool = False, limit: int = 50, at: datetime | None = None,
    lost: bool | None = None,
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
    # **Lost leads are out unless asked for, and that is the filter ADM-CRM-07 needs.** A lead
    # who said no is not part of the pipeline ADM-CRM-01 draws -- the canvas has five columns
    # and no sixth -- so the default list is the live one. `lost=true` is the other list, which
    # is what a salesperson reviewing refusals and ADM-RPT-03's source effectiveness both want,
    # and the two are a filter rather than two routes because they are one list of one thing.
    if lost is not None:
        where.append("l.lost_at IS NOT NULL" if lost else "l.lost_at IS NULL")
    else:
        where.append("l.lost_at IS NULL")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT l.lead_id, l.person_id, l.stage, l.source_id, s.display_name,"
            " l.owner_person_id, l.next_action, l.next_action_on, l.created_at, l.version,"
            " (SELECT max(t.occurred_at) FROM plt01.crm_touchpoints t"
            "   WHERE t.lead_id = l.lead_id),"
            # Appended, because every index below is positional and mypy cannot see one move.
            " l.lost_at, l.lost_reason, l.lost_detail"
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
        leads = [_lead_row(r, now, standing, lost=(r[11], r[12], r[13]))
                 for r in rows]
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
            "   WHERE t.lead_id = l.lead_id), l.stage_changed_at,"
            # Appended, because `stage_changed_at` already sits at 11 in this query and at
            # nothing in the listing's -- which is why `_lead_row` takes the loss as an
            # argument rather than reading an index.
            " l.lost_at, l.lost_reason, l.lost_detail"
            " FROM plt01.crm_leads l"
            " LEFT JOIN plt01.crm_lead_sources s ON s.source_id = l.source_id"
            " WHERE l.lead_id = %s",
            (lead_id,),
        ).fetchone()
        if row is None:
            raise NotFound("lead_not_found")
        # **Live interests only.** A withdrawn one stays in the table so that "was this lead
        # ever interested in PT" is answerable, and a profile listing it as current would be
        # the record and the state saying different things -- which is the reason the
        # withdrawal is a column rather than a delete, undone by the read.
        interests = [str(r[0]) for r in conn.execute(
            "SELECT interest FROM plt01.crm_lead_interests"
            " WHERE lead_id = %s AND withdrawn_at IS NULL",
            (lead_id,)).fetchall()]
        touchpoints = conn.execute(
            "SELECT touchpoint_id, kind, occurred_at, summary, recorded_at, recorded_by"
            " FROM plt01.crm_touchpoints WHERE lead_id = %s"
            " ORDER BY occurred_at DESC, touchpoint_id DESC LIMIT %s",
            (lead_id, limit),
        ).fetchall()
        membership = _membership_of(conn, str(row[1]))
    lead = _lead_row(row, now, lost=(row[12], row[13], row[14]))
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
    # **A lost lead is off the board.** ADM-CRM-01 draws five columns and no sixth, and
    # ADM-CRM-07 is a side sheet -- so a person who said no is not in the pipeline this read
    # counts. Their refusal is on their own record and in ADM-RPT-03; leaving them in a column
    # would make every chip a count of work nobody is doing.
    where.append("l.lost_at IS NULL")
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


def read_trial(
    pool: Pool, tenant_id: str, lead_id: str, *, at: datetime | None = None,
) -> dict[str, Any]:
    """ADM-CRM-05: the trial card on a lead's profile, or why there is not one.

    **A state of ADM-CRM-03 rather than a screen of its own**, which the canvas says by
    labelling one card with both ids. So this is the four figures and the one sentence that
    appear on the lead profile while the person is on a trial.

    **Three modules, one transaction, and the figures derived here.** The window is MOD-017's,
    the visits are MOD-022's entry events and the classes are MOD-020's settled bookings --
    all three in `plt01` under this role, so they are read on one connection rather than
    composed by a surface. That is the opposite of the Member 360's judgement and the reason
    is the card: every figure on it is an arithmetic over `today`, and a browser comparing
    dates against its own clock counts in the wrong frame -- which this build has three
    recorded defects from. A surface given four counts and asked to work out "day 6 of 7"
    would be the fourth.
    """
    now = at or _now()
    today = now.date()
    with tenant_scope(pool, tenant_id) as conn:
        lead = conn.execute(
            "SELECT person_id, stage FROM plt01.crm_leads WHERE lead_id = %s",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise NotFound("lead_not_found")
        person_id = str(lead[0])
        window = commercial.live_trial(conn, person_id, at=today)
        if window is None:
            # **Not an error and not an empty card.** A lead with no trial is the ordinary
            # case -- three of the five board columns -- so the read says so and the profile
            # draws its own state rather than four zeros, which is MOD-014's "a confident
            # wrong answer where a missing one would have been honest".
            return {
                "lead_id": lead_id, "person_id": person_id, "on_trial": False,
                "stage": str(lead[1]),
                "not_on_a_trial": (
                    "this person has no live membership on a product whose terms declare "
                    "trial_days, so there is no window to count anything in"),
            }
        span = trial.Window(starts_on=window["starts_on"], ends_on=window["ends_on"])
        visits = access.visits_between(conn, person_id, span.starts_on, span.ends_on)
        classes = booking.attended_between(conn, person_id, span.starts_on, span.ends_on)
    return {
        "lead_id": lead_id, "person_id": person_id, "on_trial": True,
        "stage": str(lead[1]),
        "membership_id": window["membership_id"],
        "starts_on": span.starts_on.isoformat(), "ends_on": span.ends_on.isoformat(),
        "trial_days": window["trial_days"],
        # The canvas's four cells and its one sentence, in its own order.
        "visits": visits,
        "classes": classes,
        "day_of": trial.day_of(span, today),
        "of_days": span.days,
        "days_left": trial.days_left(span, today),
        "ends_tomorrow": trial.ends_tomorrow(span, today),
        "engagement": trial.engagement(visits=visits, window=span, today=today),
        "engagement_is_use_not_a_prediction": (
            "the drawn canvas's cell is ENGAGEMENT and this is how much of the trial has "
            "been used; the prototype calls it conversion likelihood, which is a prediction "
            "about a person and is what MOD-020 refuses for the no-show score"),
        "a_visit_and_a_class_are_different_facts": (
            "a visit is an entry event and a class is a booking settled attended, so a "
            "member who trains in the gym four times has four visits and no classes"),
    }


def read_conversion_quote(
    pool: Pool, tenant_id: str, lead_id: str, *, variant_id: str, currency: str,
    actor_id: str, correlation_id: str, channel: str = "crm",
    at: datetime | None = None,
) -> dict[str, Any]:
    """ADM-CRM-06: what it costs this person to become a member on this plan, today.

    The canvas is four lines -- "Club · monthly · JOD 55.00 / Pro-rata to 31 Aug · JOD 21.29 /
    Then 55.00 from 1 Sep / Her four class attendances, her credential and Yasmin's notes all
    carry over. Nothing is re-entered." -- and every figure in them is produced here rather
    than in a browser.

    **The recurring figure is a quote and not a sale.** `catalog.quote_price` runs the whole
    resolution -- the derived segment, the book choice, the automatic promotions -- and writes
    nothing, which is what `catalog.price.read` is described as granting. Calling
    `resolve_price` to put a number on a screen would store a receipt and redeem a coupon for
    somebody who has not agreed to anything, and `list_prices` is explicit that a row in its
    own window is not the resolved price.

    **The part-period figure is `lifecycle.first_charge`**, so the boundary is the one the
    contract declares (ADR-0011). A plan on a `calendar` anchor converting mid-month charges
    to the month end and the full amount from the first; one on `agreement_start` charges the
    whole period from today and the read says `prorated: false` rather than quoting a
    proration that is not one. The canvas's 21.29 is the first of those, and a client deriving
    it would be counting days in its own frame -- which this build has three recorded defects
    from.

    **The quote runs outside the read's transaction, deliberately.** `quote_price` takes a
    pool and opens its own scope, so the trial and the price are two snapshots; for a
    read-only quote that is harmless, and the alternative is threading a connection through
    MOD-016's resolver, which would be a change to the sale's own path for the benefit of a
    screen. What must be atomic is a write, and this writes nothing.

    **A trial product is refused as a target.** `trial_days` is what marks one (ADR-0010 D7),
    so converting a trial onto another trial is not a sale -- and the refusal is here as well
    as in `sellable_plans`' filter, because a caller can name a variant the picker did not
    offer.

    **The carry-over is structural and is stated as such.** "The lead ID becomes the member ID"
    is ADM-CRM-01's own requirement, enforced by there being one `ppl_persons` row: the
    conversion writes a superseding agreement and touches neither the credential, nor the
    attendance, nor the touchpoints. So the counts here are evidence of what already exists
    rather than a promise about a migration, and the credential is named without a number
    because that count is MOD-022's own read with its own permission.
    """
    now = at or _now()
    today = now.date()
    with tenant_scope(pool, tenant_id) as conn:
        lead = conn.execute(
            "SELECT person_id, stage FROM plt01.crm_leads WHERE lead_id = %s",
            (lead_id,),
        ).fetchone()
        if lead is None:
            raise NotFound("lead_not_found")
        person_id = str(lead[0])
        plan = conn.execute(
            """
            SELECT v.display_name, p.product_key, t.billing_period, t.billing_anchor,
                   t.trial_days, p.status, v.status, t.status
            FROM plt01.cat_variants v
            JOIN plt01.cat_products p
                ON p.tenant_id = v.tenant_id AND p.product_id = v.product_id
            JOIN plt01.mem_membership_terms t
                ON t.tenant_id = p.tenant_id AND t.product_id = p.product_id
            WHERE v.variant_id = %s
            """,
            (variant_id,),
        ).fetchone()
        if plan is None:
            raise NotFound("plan_not_found")
        if plan[4] is not None:
            raise Conflict("a_trial_product_is_not_a_conversion_target")
        if str(plan[5]) != "published" or str(plan[6]) != "active" \
                or str(plan[7]) != "active":
            raise Conflict("this_plan_is_not_sellable")
        window = commercial.live_trial(conn, person_id, at=today)
        touchpoints = conn.execute(
            "SELECT count(*) FROM plt01.crm_touchpoints WHERE lead_id = %s",
            (lead_id,),
        ).fetchone()
        classes = 0
        visits = 0
        if window is not None:
            classes = booking.attended_between(
                conn, person_id, window["starts_on"], window["ends_on"])
            visits = access.visits_between(
                conn, person_id, window["starts_on"], window["ends_on"])

    quoted = catalog.quote_price(
        pool, tenant_id, variant_id=variant_id, currency=currency,
        subject_id=person_id, channel=channel, actor_id=actor_id,
        correlation_id=correlation_id, at=now)
    recurring = int(quoted["final_amount_minor"])
    first_minor, ends_on, recurring_from, steps = lifecycle.first_charge(
        full_amount_minor=recurring, starts_on=today,
        billing_period=str(plan[2]), anchor=str(plan[3]))
    return {
        "lead_id": lead_id, "person_id": person_id, "stage": str(lead[1]),
        "today": today.isoformat(),
        "plan": {
            "variant_id": variant_id, "display_name": str(plan[0]),
            "product_key": str(plan[1]), "billing_period": str(plan[2]),
            "billing_anchor": str(plan[3]),
        },
        # The canvas's three money lines, in its own order. `recurring_minor` is what the sale
        # would charge for a whole period and `first_charge_minor` is what is due today; the
        # design's note on the sale sheet says confusing the two is "the most common
        # membership-sale complaint in the industry", which is why both are here and neither
        # is derivable from the other.
        "currency": str(quoted["currency"]),
        # Which book and which row produced the figure. MOD-016's own resolution returns both
        # and a reader asking "why is this 30.00" has nowhere else to look -- the receipt that
        # would normally answer it is the thing a quote deliberately does not write.
        "price_book_id": quoted["price_book_id"],
        "price_id": quoted["price_id"],
        "recurring_minor": recurring,
        "list_amount_minor": int(quoted["list_amount_minor"]),
        "discount_minor": int(quoted["discount_minor"]),
        "first_charge_minor": first_minor,
        "first_period_ends_on": ends_on.isoformat(),
        "recurring_starts_on": recurring_from.isoformat(),
        "prorated": first_minor != recurring,
        "explanation": list(steps) + list(quoted["explanation"]),
        "converting_from_a_trial": window is not None,
        "trial": None if window is None else {
            "membership_id": window["membership_id"],
            "starts_on": window["starts_on"].isoformat(),
            "ends_on": window["ends_on"].isoformat(),
            "trial_days": window["trial_days"],
        },
        "carries_over": {
            "classes": classes,
            "visits": visits,
            "touchpoints": 0 if touchpoints is None else int(touchpoints[0]),
            "the_record_does_not_change": (
                "a lead, a trialist and a member are one ppl_persons row at three stages, so "
                "the credential, the attendance and the notes are untouched by a conversion -- "
                "nothing is re-entered because nothing moves"),
            "no_credential_count_here": (
                "what this person can present at a door is MOD-022's own read and has its own "
                "permission, so it is composed by a surface rather than returned from a CRM "
                "route"),
        },
        "nothing_is_charged_here": (
            "this is the arithmetic and the disclosure; taking the money needs the payment "
            "provider, which is owner-reserved, and no invoice is issued by a conversion"),
    }


# ------------------------------------------------------------------- the helpers


#: FD-05's touchpoint kind. A walk-in *visited*, which is the fact, and `stage_from_touchpoint`
#: moves a `new` lead to `contacted` on it -- D12's reason for recording one at all: the board
#: counts what the timeline says, so a trial started with an empty timeline is a lead nobody
#: can account for. Not a `tour`: a tour is a guided viewing somebody arranged.
WALK_IN_KIND = "visit"

#: How a walk-in's acceptance is recorded. A signature is recorded rather than performed
#: everywhere in MOD-017 -- nothing in this build captures one -- and `click_through` is the
#: kind that names what actually happened: a named actor pressed a button at a desk with the
#: member standing there.
WALK_IN_SIGNATURE = "click_through"


def _walk_in_evidence(correlation_id: str) -> str:
    """The locator that goes on a walk-in's signature.

    `mem_agreements_evidence_is_a_locator` requires a URI, which is MOD-017's answer to a
    column that would otherwise accept a card number -- and there is no captured artefact
    here, so the honest locator points at the only evidence there is: the request in which a
    named actor recorded that the member accepted at the desk. The alternative is a plausible
    `s3://` path to a file nobody wrote, which is the fabricated-evidence shape this build has
    been bitten by six times.
    """
    return f"veyro+desk://walk-in-trial/{correlation_id}"


def _walk_in_number(agreement_id: str) -> str:
    """The membership handle a walk-in trial gets, derived rather than typed.

    **It is a handle, not a number the gym chose, and the response says so.**
    `mem_memberships.membership_number` is unique per tenant under
    `^[A-Z0-9][A-Z0-9-]{2,31}$` and every other caller supplies one; FD-05 draws two fields
    and a button, so there is nobody to ask -- and a receptionist inventing one is how a
    tenant ends up with three numbering schemes. Minting one here would be inventing the
    scheme, which this build refuses for MOD-026's case number for the same reason: MOD-017
    and MOD-014 already carry two human-facing numbers with nothing relating them.

    Derived from the agreement so a resumed attempt produces the same handle, which is what
    keeps the uniqueness index from refusing a retry.
    """
    return "TRIAL-" + agreement_id.replace("-", "")[:12].upper()


def start_walk_in_trial(
    pool: Pool, tenant_id: str, *, summary: str, actor_id: str, correlation_id: str,
    person_id: str | None = None, legal_name: str | None = None, phone: str | None = None,
    different_person: bool = False, variant_id: str | None = None,
    source_id: str | None = None, owner_person_id: str | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """FD-05: two fields and a start. ADR-0010 D12 is the record.

    "Creates a lead already in trial state with the clock running. Everything else is captured
    later by the sales team -- a person standing at a desk will not complete a form." So one
    press produces four facts across four modules: a person, a lead, a signed agreement on a
    trial product, and the activation that sets `ends_on`.

    **Four transactions, resumable rather than atomic**, which D12 argues at length. None of
    the four is a control over another's state, every partial outcome is a *less complete*
    record that already has a screen, and three of the four key on the person -- the contact
    match resolves them, `crm_leads_one_per_person` hands back the lead, `live_trial` hands
    back the trial. The fourth is `resumable_agreement`, which exists because
    `create_agreement` has no idempotency key and a second press between the signature and
    the activation would otherwise draw up a second contract. Every step says `created` or
    `existing`, so the caller is told what this press did rather than being left to assume.

    **A phone that already has a record is refused, not reused.** MOD-014's
    `AUTO_MERGE_THRESHOLD` is `None` because two siblings at one address with one family line
    is the ordinary case, so reusing whoever holds the number would be making the merge
    decision paragraph 10200 reserves for a person. The screen shows ADM-MEM-10's own two
    escapes -- start the trial on that record, or say it is somebody else -- and that refusal
    is also what makes a retry converge, because the second attempt finds the person the first
    one created.

    **The figure is quoted, never supplied.** `catalog.quote_price` is the read that may name
    a price and records nothing, so the agreement's amount is the trial plan's own live price
    rather than a number a till sent. It cites no resolution because a quote stores none, and
    the response says that rather than leaving a null id to read as a write that failed.

    **The plan is derived where there is one and named where there is not.** Two fields is the
    canvas, so this resolves the tenant's published trial plan itself; two of them is a case
    the canvas does not draw and is refused with both named rather than chosen between --
    MOD-018's unordered-lookup finding applied to which product somebody is sold.
    """
    moment = at or _now()
    today = moment.date()
    if not summary.strip():
        raise InvalidRequest("a_touchpoint_says_what_happened")
    if person_id is None and not (legal_name and phone):
        raise InvalidRequest("a_walk_in_is_a_person_or_a_name_and_a_number")
    if person_id is not None and (legal_name or phone):
        raise InvalidRequest("a_walk_in_is_a_person_or_a_name_and_a_number")

    # **Both refusals happen before anything is written**, which is this build's oldest rule:
    # a control that commits anything before it refuses is not a control. The first version
    # resolved the plan *after* creating the person, so a tenant publishing two trial plans
    # got a person, a lead and a touchpoint written on every refused press -- and the second
    # press was then refused for the *duplicate* rather than the plan, which is the wrong
    # answer to the wrong question. Found by a test that pressed the button twice.
    steps: dict[str, str] = {}
    if person_id is None:
        assert legal_name is not None and phone is not None
        holders = people.holders_of(pool, tenant_id, kind="phone", value=phone)
        if holders and not different_person:
            # Refused rather than reused, and the screen already holds the match from its own
            # `GET /people/contact-match` -- a `ServiceError` carries a code and no payload, so
            # naming the person is the surface's half of this.
            raise Conflict("this_number_already_has_a_record")
    plan = _trial_plan(pool, tenant_id, variant_id=variant_id)
    if person_id is None:
        assert legal_name is not None and phone is not None
        created = people.create_person(
            pool, tenant_id, legal_name=legal_name, actor_id=actor_id,
            correlation_id=correlation_id,
            contacts=[{"kind": "phone", "value": phone, "is_primary": "1"}], at=moment)
        person_id = str(created["person_id"])
        steps["person"] = "created"
    else:
        steps["person"] = "named"

    lead = create_lead(
        pool, tenant_id, person_id=person_id, source_id=source_id, interests=(),
        owner_person_id=owner_person_id, actor_id=actor_id, correlation_id=correlation_id)
    steps["lead"] = "existing" if lead.get("existing") else "created"
    touch = record_touchpoint(
        pool, tenant_id, str(lead["lead_id"]), kind=WALK_IN_KIND, summary=summary,
        occurred_at=moment, actor_id=actor_id, correlation_id=correlation_id)

    with tenant_scope(pool, tenant_id) as conn:
        already = commercial.live_trial(conn, person_id, at=today)
    if already is not None:
        steps["trial"] = "existing"
        return {
            "person_id": person_id, "lead_id": str(lead["lead_id"]),
            "stage": str(touch["stage"]), "steps": steps,
            "membership_id": already["membership_id"],
            "starts_on": already["starts_on"].isoformat(),
            "ends_on": already["ends_on"].isoformat(),
            "trial_days": already["trial_days"],
            "this_person_was_already_on_a_trial": (
                "the window is the one they are on; FD-05 does not start a second"),
            **_WALK_IN_GAPS,
        }

    resumed = commercial.resumable_agreement(
        pool, tenant_id, person_id=person_id,
        membership_terms_id=plan["membership_terms_id"], starts_on=today)
    if resumed is not None:
        agreement_id, status = resumed["agreement_id"], resumed["status"]
        amount_minor, currency = resumed["amount_minor"], resumed["currency"]
        steps["agreement"] = "existing"
    else:
        quoted = catalog.quote_price(
            pool, tenant_id, variant_id=plan["variant_id"], currency=plan["currency"],
            actor_id=actor_id, correlation_id=correlation_id, subject_id=person_id, at=moment)
        amount_minor = int(quoted["final_amount_minor"])
        currency = str(quoted["currency"])
        drawn = commercial.create_agreement(
            pool, tenant_id, person_id=person_id,
            membership_terms_id=plan["membership_terms_id"], variant_id=plan["variant_id"],
            amount_minor=amount_minor, currency=currency, starts_on=today,
            actor_id=actor_id, correlation_id=correlation_id)
        agreement_id, status = str(drawn["agreement_id"]), "draft"
        steps["agreement"] = "created"

    if status == "draft":
        commercial.sign_agreement(
            pool, tenant_id, agreement_id, signature_kind=WALK_IN_SIGNATURE,
            signature_evidence_ref=_walk_in_evidence(correlation_id),
            signed_by_person_id=person_id, actor_id=actor_id,
            correlation_id=correlation_id, at=moment)
        steps["signature"] = "recorded"
    else:
        steps["signature"] = "existing"

    live = commercial.activate_membership(
        pool, tenant_id, agreement_id=agreement_id,
        membership_number=_walk_in_number(agreement_id),
        idempotency_key=f"walk-in-trial:{agreement_id}", actor_id=actor_id,
        correlation_id=correlation_id, at=today)
    steps["trial"] = "existing" if live.get("repeated") else "created"
    return {
        "person_id": person_id, "lead_id": str(lead["lead_id"]),
        "stage": str(touch["stage"]), "steps": steps,
        "agreement_id": agreement_id,
        "membership_id": str(live["membership_id"]),
        "membership_number": str(live["membership_number"]),
        "membership_number_is_a_handle": (
            "derived from the agreement because FD-05 has nobody to ask for one, and this "
            "build has no tenant numbering scheme -- MOD-017 and MOD-014 already carry two "
            "human-facing numbers with nothing relating them"),
        "amount_minor": amount_minor, "currency": currency,
        "cites_no_price_resolution_because": (
            "a quote records none: the figure is the trial plan's own live price rather than "
            "one the caller sent"),
        "plan": {"variant_id": plan["variant_id"], "display_name": plan["display_name"],
                 "trial_days": plan["trial_days"]},
        "starts_on": today.isoformat(),
        "ends_on": live.get("ends_on"),
        "trial_days": live.get("trial_days"),
        **_WALK_IN_GAPS,
    }


#: The two of FD-05's three promises this build does not keep, named on every answer rather
#: than left for a screen to discover. "Creates a lead already in trial with the clock running,
#: a credential, and an app invitation by text" -- the first is the whole of what is ours.
_WALK_IN_GAPS = {
    "no_credential_because": (
        "a credential needs somewhere for the member to show it: there is no mobile client in "
        "this build and nothing that could text one"),
    "no_invitation_because": (
        "an app invitation by text needs the messaging provider, which is external blocker 2 "
        "-- MOD-013 authors a message and sends nothing"),
}


def _trial_plan(
    pool: Pool, tenant_id: str, *, variant_id: str | None,
) -> dict[str, Any]:
    """Which trial a walk-in is started on, and the currency its price is quoted in.

    Derived where a tenant publishes one trial, which is the canvas's two-field screen; named
    where it publishes several, because choosing for them would be MOD-018's unordered lookup
    deciding what somebody is sold. A tenant that publishes none cannot use FD-05 at all and
    the refusal says so, rather than a button that 422s on the contract behind it.
    """
    offered = commercial.sellable_plans(pool, tenant_id, trials="only")["plans"]
    if not offered:
        raise InvalidRequest("this_tenant_publishes_no_trial_plan")
    if variant_id is not None:
        chosen = [p for p in offered if p["variant_id"] == variant_id]
        if not chosen:
            raise NotFound("trial_plan_not_found")
    elif len(offered) > 1:
        raise InvalidRequest("name_the_trial_plan")
    else:
        chosen = offered
    plan = dict(chosen[0])
    # **The currency comes from the plan's own live price, through MOD-016's own read.**
    # `quote_price` takes a currency and FD-05 has no field for one, and a currency the caller
    # chose would let a JOD trial be quoted in dollars -- the one comparison MOD-015's money
    # discipline forbids. `list_prices` is the read that answers which rows were written
    # against a variant; writing the predicate here instead would be a second definition of
    # which price is live, and the first version of this function did exactly that and named a
    # column that does not exist. Rows in two currencies are refused rather than ordered
    # between, for `_trial_plan`'s own reason one level down.
    live = catalog.list_prices(pool, tenant_id, variant_id=plan["variant_id"])["prices"]
    offered_in = sorted({str(r["currency"]) for r in live if r["in_window"]})
    if not offered_in:
        raise InvalidRequest("the_trial_plan_has_no_live_price")
    if len(offered_in) > 1:
        raise InvalidRequest("the_trial_plan_is_priced_in_more_than_one_currency")
    plan["currency"] = offered_in[0]
    return plan

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
            # **The target is named**, because `ON CONFLICT DO NOTHING` with no target stays
            # valid SQL when the rule it relies on changes and silently stops doing anything
            # -- MOD-010's deduplication finding. The conflict that matters is the partial
            # one: a second *live* row for the same interest.
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (tenant_id, lead_id, interest) WHERE withdrawn_at IS NULL"
            " DO NOTHING",
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
    *, lost: tuple[datetime | None, str | None, str | None] = (None, None, None),
) -> dict[str, Any]:
    """One lead, as every read of one returns it.

    **The loss is an argument rather than an index, because three callers pass rows of three
    shapes.** The first version read `r[11]` for `lost_at` -- which is the listing's own
    column and is `stage_changed_at` in `read_lead`'s query, so a single read would have
    reported the day the stage moved as the day the lead said no. Two timestamps, no crash,
    and a wrong figure on the one screen that explains a refusal. That is MOD-018's
    positional-read hazard, and the fix is not to guess.
    """
    where_they_stand = (standing or {}).get(str(r[1]))
    lost_at, lost_reason, lost_detail = lost
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
        # **A member is not a lead going cold and neither is a lost one.** A person who
        # joined is not somebody nobody has rung, and a person who said no is not either --
        # the reason is on the record. Counting a refusal here would put every one of them
        # into the chip that exists to surface a lead somebody has forgotten.
        "going_cold": member is None and pipeline.is_going_cold(
            last_touch_at=r[10], created_at=r[8], now=now, lost_at=lost_at),
        "lost": lost_at is not None,
        "lost_at": (None if lost_at is None else lost_at.isoformat()),
        "lost_reason": lost_reason,
        "lost_detail": lost_detail,
        # Advisory, never a lock -- ADR-0010 D10. Reopening is always permitted; this says
        # which lost leads are worth another try.
        "recontactable": pipeline.is_recontactable(lost_at=lost_at, now=now),
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

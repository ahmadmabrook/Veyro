"""MOD-020 OPS-02: the I/O. The decisions are in the modules beside this one.

**The one thing here that is load-bearing: a booking and its place commit together.**
Paragraph 4142 requires the reservation to be atomic against the scheduled instance, and the
only way to mean it is to take MOD-019's hold on *this* transaction's connection --
`scheduling.take_hold_on`, not `take_hold`. A booking written in one transaction with its place
taken in another is a member holding a confirmed booking and no seat, or a seat nobody holds,
and no reconciliation afterwards can tell which happened. Everything else in this module is
bookkeeping around that.

**And this module counts no capacity.** Every "is there room" question is answered by MOD-019
refusing the hold -- under a row lock on the session, with a trigger behind it -- so paragraph
4697's "booking capacity never falls below zero" is kept there and not restated here. A count
in this module would be MOD-018's cached balance applied to seats.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import Connection, errors

from app.authorization.service import Forbidden
from app.booking import appeals, attendance, consequence, policy, waitlist
from app.booking.denial import Denial
from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events
from app.scheduling import service as scheduling


def _now() -> datetime:
    return datetime.now(UTC)


def _check_name(error: errors.CheckViolation) -> str:
    detail = str(getattr(error, "diag", None) and error.diag.constraint_name or "")
    return detail or "invalid_request"


def _fk_subject(error: errors.ForeignKeyViolation) -> str:
    name = str(getattr(error, "diag", None) and error.diag.constraint_name or "")
    for fragment, subject in (
        ("session", "scheduling_session_not_found"),
        ("person", "person_not_found"),
        ("hold", "capacity_hold_not_found"),
        ("policy", "booking_policy_not_found"),
        ("grant", "entitlement_grant_not_found"),
        ("booking", "booking_not_found"),
        ("no_show", "no_show_record_not_found"),
        ("cancellation", "cancellation_not_found"),
    ):
        if fragment in name:
            return subject
    return "referenced_row_not_found"


def _append(
    conn: Connection[Any], tenant_id: str, event_type: str, aggregate_type: str,
    aggregate_id: str, payload: dict[str, Any], *, correlation_id: str, actor_id: str,
) -> None:
    """One event, in the transaction that caused it. MOD-010's rule, not restated."""
    events.append_event(
        conn, tenant_id, event_type=event_type, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, payload=payload, correlation_id=correlation_id,
        actor_id=actor_id)


# ------------------------------------------------------------------ the policy

def set_policy(
    pool: Pool, tenant_id: str, *, policy_key: str, display_name: str,
    rules: dict[str, Any], actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """A new version of a booking policy. OPS-02-R02.

    **A version, never an edit.** A booking snapshots the policy by reference, and the
    consequence of cancelling it late is decided months afterwards -- so changing the window in
    place would change the terms of every booking already made under it. That is MOD-012's
    install snapshot and MOD-017's agreement, and it is why the rule columns carry no UPDATE
    grant.
    """
    parsed = _parse_policy(rules)
    if not display_name.strip():
        raise InvalidRequest("a_booking_policy_has_a_name")
    with tenant_scope(pool, tenant_id) as conn:
        current = conn.execute(
            "SELECT coalesce(max(version), 0) FROM plt01.bkg_policies"
            " WHERE policy_key = %s",
            (policy_key.upper(),),
        ).fetchone()
        version = int(current[0]) + 1 if current else 1
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.bkg_policies
                    (tenant_id, policy_key, version, display_name, cancellation_hours,
                     max_concurrent, quota, quota_period, checkin_grace_minutes,
                     warn_after_no_shows, strike_after_no_shows, priority_rule,
                     offer_minutes, forfeits_entitlement, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING policy_id
                """,
                (tenant_id, policy_key.upper(), version, display_name.strip(),
                 parsed.cancellation_hours, parsed.max_concurrent, parsed.quota,
                 parsed.quota_period, parsed.checkin_grace_minutes,
                 parsed.warn_after_no_shows, parsed.strike_after_no_shows,
                 parsed.priority_rule, parsed.offer_minutes,
                 bool(rules.get("forfeits_entitlement", True)), actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_policy_version_already_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"policy_id": str(row[0]), "policy_key": policy_key.upper(),
            "version": version, "status": "active"}


def retire_policy(
    pool: Pool, tenant_id: str, policy_key: str, *, reason: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Withdraw a booking policy version, so nothing new is sold on it.

    **The writer the grant was waiting for.** `status`, `retired_at`, `retired_by` and
    `retire_reason` carried an UPDATE grant and two `write_once` privacy declarations, and
    nothing in the build retired a policy -- so `create_booking`'s own
    `this_booking_policy_is_retired` refusal was unreachable, because `_live_policy` already
    filters on `status = 'active'` and nothing could ever leave that state. MOD-012's "a
    column implying a control nobody implemented is worse than no column", found by review.

    **Bookings already made keep their snapshot**, which is the whole of the versioning: a
    booking cites `policy_id`, and what a member owes for cancelling late is decided months
    later on the terms they agreed to. Retiring one stops the next sale and changes nothing
    about the last.
    """
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("retiring_a_policy_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT policy_id, version FROM plt01.bkg_policies"
            " WHERE policy_key = %s AND status = 'active'"
            " ORDER BY version DESC LIMIT 1",
            (policy_key,),
        ).fetchone()
        if row is None:
            raise NotFound("booking_policy_not_found")
        try:
            moved = conn.execute(
                "UPDATE plt01.bkg_policies SET status = 'retired', retired_at = %s,"
                " retired_by = %s, retire_reason = %s, retire_correlation_id = %s"
                " WHERE policy_id = %s AND status = 'active'",
                (moment, actor_id, reason.strip(), correlation_id, str(row[0])),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if moved == 0:
            raise Conflict("this_policy_was_retired_by_somebody_else")
    return {"policy_key": policy_key, "policy_id": str(row[0]),
            "version": int(row[1]), "status": "retired",
            "detail": ("bookings already made keep the terms they were made under; this "
                       "stops the next one being made on them")}


def _parse_policy(rules: dict[str, Any]) -> policy.Policy:
    """A request's policy as the decision functions take it."""
    try:
        parsed = policy.Policy(
            cancellation_hours=int(rules.get("cancellation_hours", 12)),
            max_concurrent=int(rules.get("max_concurrent", 10)),
            quota=None if rules.get("quota") is None else int(rules["quota"]),
            quota_period=str(rules.get("quota_period", "rolling_7_days")),
            checkin_grace_minutes=int(rules.get("checkin_grace_minutes", 15)),
            warn_after_no_shows=int(rules.get("warn_after_no_shows", 2)),
            strike_after_no_shows=int(rules.get("strike_after_no_shows", 3)),
            priority_rule=str(rules.get("priority_rule", "first_come")),
            offer_minutes=int(rules.get("offer_minutes", 60)),
        )
    except (TypeError, ValueError) as e:
        raise InvalidRequest(str(e)) from None
    try:
        policy.check_policy(parsed)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    return parsed


def _policy_row(conn: Connection[Any], policy_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT cancellation_hours, max_concurrent, quota, quota_period,"
        " checkin_grace_minutes, warn_after_no_shows, strike_after_no_shows,"
        " priority_rule, offer_minutes, forfeits_entitlement, status, policy_key, version"
        " FROM plt01.bkg_policies WHERE policy_id = %s",
        (policy_id,),
    ).fetchone()
    if row is None:
        raise NotFound("booking_policy_not_found")
    return {
        "policy": policy.Policy(
            cancellation_hours=int(row[0]), max_concurrent=int(row[1]),
            quota=None if row[2] is None else int(row[2]), quota_period=str(row[3]),
            checkin_grace_minutes=int(row[4]), warn_after_no_shows=int(row[5]),
            strike_after_no_shows=int(row[6]), priority_rule=str(row[7]),
            offer_minutes=int(row[8])),
        "forfeits_entitlement": bool(row[9]), "status": str(row[10]),
        "policy_key": str(row[11]), "version": int(row[12]), "policy_id": policy_id,
    }


def _live_policy(conn: Connection[Any], policy_key: str) -> dict[str, Any]:
    """The newest active version of a policy, by key."""
    row = conn.execute(
        "SELECT policy_id FROM plt01.bkg_policies"
        " WHERE policy_key = %s AND status = 'active'"
        " ORDER BY version DESC LIMIT 1",
        (policy_key.upper(),),
    ).fetchone()
    if row is None:
        raise NotFound("booking_policy_not_found")
    return _policy_row(conn, str(row[0]))


# ------------------------------------------------------------------ the booking

def _short(value: str) -> str:
    """A caller's key, folded to a fixed-width digest for use inside a derived key.

    **Truncation is what this replaces.** The hold key was `f"bkg-{key}"[:200]` against a body
    field bounded at 200, so two keys differing only in their last four characters produced one
    hold key: a reviewer booked member A with a 200-character counter and watched member B's
    booking refused as a duplicate request in a class with nine free places. A digest is the
    same length whatever goes in, and `sha256` here is a collision-free label rather than a
    security claim -- nothing authenticates on it.
    """
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()[:32]


def _session(
    conn: Connection[Any], session_id: str, *, for_update: bool = False,
) -> dict[str, Any]:
    """The MOD-019 session a booking is for.

    A read by default. The lock that matters is MOD-019's own, taken inside `take_hold_on`
    against the row it counts against -- taking a second one here would be a different lock
    ordering on the same row and a deadlock waiting to happen.
    """
    row = conn.execute(
        "SELECT status, starts_at, ends_at, capacity, overbook_places, local_date,"
        " timezone, template_id, location_id, cancelled_at, cancellation_reason"
        " FROM plt01.sch_sessions WHERE session_id = %s"
        + (" FOR UPDATE" if for_update else ""),
        (session_id,),
    ).fetchone()
    if row is None:
        raise NotFound("scheduling_session_not_found")
    return {"status": str(row[0]), "starts_at": row[1], "ends_at": row[2],
            "capacity": int(row[3]), "overbook_places": int(row[4]),
            "local_date": row[5], "timezone": str(row[6]),
            "template_id": str(row[7]), "location_id": str(row[8]),
            "cancelled_at": row[9], "cancellation_reason": row[10]}


def _live_bookings(conn: Connection[Any], person_id: str, *, at: datetime) -> int:
    """How many live bookings this member holds on sessions that have not happened.

    Counted from the rows, not stored: a column would be MOD-018's cached balance applied to a
    limit, and here the disagreement decides whether somebody may book.
    """
    row = conn.execute(
        "SELECT count(*) FROM plt01.bkg_bookings b"
        " JOIN plt01.sch_sessions s ON s.session_id = b.session_id"
        " WHERE b.person_id = %s AND b.state = 'booked' AND s.ends_at > %s",
        (person_id, at),
    ).fetchone()
    return int(row[0]) if row else 0


def _quota_others(
    conn: Connection[Any], person_id: str, *, span: tuple[datetime, datetime],
    exclude_session_id: str,
) -> list[datetime]:
    """When this member's other sessions in the span start.

    **Instants, not a count.** A rolling quota is a statement about every window containing
    the session being booked, so the decision needs the times rather than a total -- a count
    inside a backwards-only window let a member book the last class of the week first and take
    seven under a quota of three. `policy.quota_allows` is what reads these.

    **Counted on when the session is, not on when they booked.** A quota is about how much
    somebody uses the gym; counting the booking's own timestamp would let a member book ten
    classes for next month today and nothing for the rest of the window.

    The session being booked is excluded, because `quota_allows` adds the candidate itself --
    and a member who already holds a booking on it is refused earlier, by the one-live index.
    """
    rows = conn.execute(
        "SELECT s.starts_at FROM plt01.bkg_bookings b"
        " JOIN plt01.sch_sessions s ON s.session_id = b.session_id"
        " WHERE b.person_id = %s AND b.state IN ('booked', 'attended', 'no_show')"
        "   AND b.session_id <> %s"
        "   AND s.starts_at >= %s AND s.starts_at < %s",
        (person_id, exclude_session_id, span[0], span[1]),
    ).fetchall()
    return [row[0] for row in rows]


def _entitlement_grant(
    conn: Connection[Any], person_id: str, *, session: dict[str, Any],
    entitlement_key: str | None,
) -> str | None:
    """The MOD-017 grant this booking draws on, or None when there is none to draw on.

    **Derived, never accepted.** A caller naming a grant id would be naming somebody else's
    entitlement, which MOD-016's review found in a coupon and MOD-019's in an age. What the
    caller may say is *which kind* of entitlement to spend; which grant that is, and whether
    the member holds a live one over this session, is read here.

    **It returns rather than raises**, so `_evaluate` can turn the absence into the declared
    `no_entitlement` denial and the eligibility read can say so before the member taps. The
    raising version was reached only by the command, which is how the read came to answer
    `may_book: true` for a member with no pass.
    """
    if entitlement_key is None:
        return None
    row = conn.execute(
        "SELECT g.grant_id FROM plt01.mem_entitlement_grants g"
        " JOIN plt01.mem_entitlement_policies p ON p.policy_id = g.policy_id"
        " WHERE g.person_id = %s AND p.policy_key = %s AND g.status = 'active'"
        "   AND g.valid_from <= %s AND (g.valid_to IS NULL OR g.valid_to >= %s)"
        " ORDER BY g.valid_to NULLS LAST LIMIT 1",
        (person_id, entitlement_key, session["local_date"], session["local_date"]),
    ).fetchone()
    return None if row is None else str(row[0])


def _evaluate(
    conn: Connection[Any], *, session: dict[str, Any], session_id: str, person_id: str,
    rules: dict[str, Any], at: datetime, entitlement_key: str | None = None,
    skills: list[str] | None = None,
) -> Denial | None:
    """Whether this member may book this session, and why not. OPS-02's first Critical Control.

    **Evaluated in a fixed order, which is what makes the denial stable.** Paragraph 5032 asks
    for a stable denial and paragraph 1888 for an understandable one; a member who taps *book*
    twice on a full class must be told "full" both times rather than "full" and then "you are
    not eligible". So the order here is: is the session bookable at all, is the window open, is
    the member already on it, may they hold another, are they inside their quota -- and
    capacity *last*, because it is the one that offers the waitlist and the one most likely to
    change between two taps.

    Capacity itself is not counted here: `take_hold_on` refuses under MOD-019's lock. What this
    does is read the count to decide whether to *offer the waitlist*, which is a different
    question and may be stale without harm -- the hold is what settles it.

    **Every refusal the command can give is given here, which it was not.** The first version
    left the session's own restrictions to `take_hold_on` and the entitlement to
    `_entitlement_grant`, both of which ran *after* this -- so the eligibility read answered
    `may_book: true` for a fourteen-year-old on an 18+ class and for a member with no pass,
    and the command then refused with free prose outside `DENIAL_REASONS`. Those were the two
    refusals that matter most, on the surface that exists to explain them: a minor's parent
    and a member without a pass were told to tap *book*. Found by review, and it is why
    `ineligible` and `no_entitlement` were declared and never produced.
    """
    live = rules["policy"]
    if session["status"] != "scheduled":
        return Denial(
            reason="session_not_bookable",
            detail=f"this session is {session['status']}")
    opens = session["starts_at"] - timedelta(hours=_opens_hours(conn, session_id))
    closes = session["starts_at"] - timedelta(minutes=_closes_minutes(conn, session_id))
    if at < opens:
        return Denial(reason="window_not_open",
                      detail=f"booking opens at {opens.isoformat()}",
                      retry_at=opens.isoformat())
    if at > closes:
        return Denial(reason="window_closed",
                      detail=f"booking closed at {closes.isoformat()}")
    already = conn.execute(
        "SELECT booking_id FROM plt01.bkg_bookings"
        " WHERE session_id = %s AND person_id = %s AND state IN ('booked', 'attended')",
        (session_id, person_id),
    ).fetchone()
    if already is not None:
        return Denial(reason="already_booked",
                      detail="this member already holds a place on this session")
    held = _live_bookings(conn, person_id, at=at)
    if not policy.within_concurrent_limit(held, policy=live):
        return Denial(
            reason="quota_reached",
            detail=(f"this member holds {held} bookings and the policy allows "
                    f"{live.max_concurrent}"))
    # **Anchored on the session, in the session's own zone, and looking both ways.** A window
    # ending at the moment of booking contains only sessions that have already happened, so
    # the quota never saw a booking for tomorrow; one ending *at the session* is defeated by
    # booking the last class of the week first. A bucket computed on the UTC day is the wrong
    # day for every tenant an hour out. All three were review findings.
    if live.quota is not None:
        span = policy.quota_span(
            live.quota_period, at=session["starts_at"], timezone=session["timezone"])
        others = _quota_others(
            conn, person_id, span=span, exclude_session_id=session_id)
        if not policy.quota_allows(
                session["starts_at"], others,
                policy=live, timezone=session["timezone"]):
            return Denial(
                reason="quota_reached",
                detail=(f"this member's {live.quota} per {live.quota_period} is already "
                        f"committed around this session"),
                retry_at=span[1].isoformat())
    # MOD-019's own read, on this connection, so the two cannot diverge.
    eligible = scheduling.check_eligibility_on(
        conn, session_id, person_id=person_id, skills=skills, at=at)
    if eligible["ineligible"] is not None:
        return Denial(reason="ineligible", detail=str(eligible["ineligible"]))
    # **A suspended membership does not book.** `suspended` was a declared denial reason with
    # no producer -- the shape this module shipped four times -- and it is the one of them
    # that is a product hole rather than an unbuilt feature: MOD-017 suspends a membership for
    # non-payment, `mem_memberships` is on this plane under this role, and nothing stopped the
    # member carrying on booking classes. A member with *no* membership at all is not refused
    # here: a pay-as-you-go booking is ordinary, and the entitlement check above is what asks
    # whether they hold what the session needs.
    suspended = conn.execute(
        "SELECT 1 FROM plt01.mem_memberships"
        " WHERE person_id = %s AND status = 'suspended' LIMIT 1",
        (person_id,),
    ).fetchone()
    if suspended is not None:
        return Denial(
            reason="suspended",
            detail="this membership is suspended; booking resumes when it does")
    if entitlement_key is not None:
        grant = _entitlement_grant(
            conn, person_id, session=session, entitlement_key=entitlement_key)
        if grant is None:
            return Denial(
                reason="no_entitlement",
                detail=(f"this member holds no live {entitlement_key} entitlement over "
                        f"this session"))
    taken = conn.execute(
        "SELECT coalesce(sum(places), 0) FROM plt01.sch_capacity_holds"
        " WHERE session_id = %s AND status IN ('held', 'attended')",
        (session_id,),
    ).fetchone()
    room = session["capacity"] + session["overbook_places"]
    if int(taken[0] if taken else 0) >= room:
        # **Full offers the waitlist, and a full waitlist does not.** The two are different
        # offers and a surface switching on the reason needs to tell them apart.
        return Denial(
            reason="full", detail=f"this session has {room} places and all are held",
            offer_waitlist=True)
    return None


def _opens_hours(conn: Connection[Any], session_id: str) -> int:
    row = conn.execute(
        "SELECT p.opens_hours_before FROM plt01.sch_sessions s"
        " JOIN plt01.sch_capacity_policies p ON p.policy_id = s.policy_id"
        " WHERE s.session_id = %s",
        (session_id,),
    ).fetchone()
    return int(row[0]) if row else 168


def _closes_minutes(conn: Connection[Any], session_id: str) -> int:
    row = conn.execute(
        "SELECT p.closes_minutes_before FROM plt01.sch_sessions s"
        " JOIN plt01.sch_capacity_policies p ON p.policy_id = s.policy_id"
        " WHERE s.session_id = %s",
        (session_id,),
    ).fetchone()
    return int(row[0]) if row else 0


def create_booking(
    pool: Pool, tenant_id: str, session_id: str, *, person_id: str, policy_key: str,
    source_kind: str, idempotency_key: str, actor_id: str, correlation_id: str,
    entitlement_key: str | None = None, skills: list[str] | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """CreateBooking. OPS-02-R01, and the command the whole module is arranged around.

    **The place and the booking commit together.** `scheduling.take_hold_on` runs on this
    connection, inside this transaction, under MOD-019's `FOR UPDATE` count and its fit
    trigger. That is paragraph 4142's atomic reservation, and the pool-taking `take_hold` would
    be the bug: a booking row with a place taken in a separate transaction can fail either way
    round, leaving a member confirmed with no seat or a seat nobody holds.

    **Eligibility is MOD-019's and is not re-decided here.** `take_hold_on` evaluates the
    session's own age, skill and entitlement restrictions against facts it derives from the
    member's record -- which is where that belongs, because the session declares them. What
    this adds is the *member's* side: their concurrent limit, their quota, whether they are
    already on it, and whether the booking window is open.
    """
    moment = at or _now()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    if source_kind not in ("member", "waitlist", "front_desk", "migration"):
        raise InvalidRequest("unknown_booking_source")
    with tenant_scope(pool, tenant_id) as conn:
        prior = conn.execute(
            "SELECT booking_id, session_id, person_id, state, hold_id"
            " FROM plt01.bkg_bookings WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if prior is not None:
            # **Every field of the request is compared.** MOD-019 shipped a key checked on one
            # field and handed one member another's hold, with 201 and the previous caller's
            # id; the realistic input is a client reusing a per-shift counter across members.
            if str(prior[1]) != session_id or str(prior[2]) != person_id:
                raise Conflict("this_idempotency_key_was_used_for_a_different_request")
            return {"booking_id": str(prior[0]), "session_id": session_id,
                    "person_id": person_id, "state": str(prior[3]),
                    "hold_id": str(prior[4]), "repeated": True}
        rules = _live_policy(conn, policy_key)
        if rules["status"] != "active":
            raise Conflict("this_booking_policy_is_retired")
        session = _session(conn, session_id)
        denial = _evaluate(
            conn, session=session, session_id=session_id, person_id=person_id,
            rules=rules, at=moment, entitlement_key=entitlement_key, skills=skills)
        if denial is not None:
            # **Refused before anything is written**, so a denial leaves no row -- and the
            # reason is structured, because a surface decides what to offer from it.
            raise Conflict(denial.reason)
        # `_evaluate` has already refused a member with no live grant, so this resolves the
        # one it found rather than deciding again.
        grant_id = _entitlement_grant(
            conn, person_id, session=session, entitlement_key=entitlement_key)
        # The place. On this connection, which is the whole point.
        hold = scheduling.take_hold_on(
            conn, tenant_id, session_id, person_id=person_id, source_kind="booking",
            source_ref=f"booking:{_short(idempotency_key)}",
            idempotency_key=f"bkg-{_short(idempotency_key)}", actor_id=actor_id,
            correlation_id=correlation_id, places=1, at=moment, skills=skills)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.bkg_bookings
                    (tenant_id, session_id, person_id, hold_id, policy_id, source_kind,
                     entitlement_grant_id, booked_by, idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING booking_id
                """,
                (tenant_id, session_id, person_id, hold["hold_id"], rules["policy_id"],
                 source_kind, grant_id, actor_id, idempotency_key.strip(),
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_member_already_holds_a_place_on_this_session") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        assert row is not None
        booking_id = str(row[0])
        _append(conn, tenant_id, "booking.created", "booking", booking_id,
                {"booking_id": booking_id, "session_id": session_id,
                 "person_id": person_id, "source_kind": source_kind,
                 "starts_at": session["starts_at"].isoformat()},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"booking_id": booking_id, "session_id": session_id, "person_id": person_id,
            "hold_id": str(hold["hold_id"]), "state": "booked",
            "policy_id": rules["policy_id"], "entitlement_grant_id": grant_id,
            "repeated": False}


def may_book(
    pool: Pool, tenant_id: str, session_id: str, *, person_id: str, policy_key: str,
    entitlement_key: str | None = None, skills: list[str] | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Whether this member could book, and why not. A read, for OPS-02's Critical Control.

    **Separate from `create_booking` because a denial has to be explainable before it is
    met.** Paragraph 1888: a surface that can only find out by trying gives a member a refusal
    with no reason attached -- and one that computes its own guess from a different rule set is
    MOD-019's eligibility read disagreeing with its own write path. So this calls the same
    `_evaluate` the command does, and the only difference is that it returns the denial rather
    than raising it.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        rules = _live_policy(conn, policy_key)
        session = _session(conn, session_id)
        denial = _evaluate(
            conn, session=session, session_id=session_id, person_id=person_id,
            rules=rules, at=moment, entitlement_key=entitlement_key, skills=skills)
    if denial is None:
        return {"may_book": True, "session_id": session_id, "person_id": person_id}
    return {"may_book": False, "session_id": session_id, "person_id": person_id,
            "reason": denial.reason, "detail": denial.detail,
            "offer_waitlist": denial.offer_waitlist, "retry_at": denial.retry_at}


# ------------------------------------------------------------------ cancelling

def cancel_booking(
    pool: Pool, tenant_id: str, booking_id: str, *, reason: str, actor_id: str,
    acting_person_id: str | None, may_act_for_another: bool, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """CancelBooking, with the consequence the policy declares. OPS-02-R04.

    **The place comes back in the same transaction, and the consequence is recorded with it.**
    A cancellation that released the hold separately could release the seat and fail to record
    the fee -- a member no longer booked and owing nothing -- or record the fee and keep the
    seat, which is a place nobody can book and somebody charged for it.

    **The consequence is decided against the policy the booking snapshotted**, not the live
    one. A tenant that shortened its window last week cannot change what somebody owes for a
    class they booked under the old one -- which is what the policy reference is for.

    **It decides; it does not charge.** `fee_due` and `credit_forfeit` are a decision for
    MOD-017 to act on, because a fee is an invoice and a forfeit credit is an entitlement
    debit, and real financial expenditure is owner-reserved. A row here saying "charged" with
    nothing having charged anything is the shape this codebase has been bitten by five times.
    """
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("cancelling_a_booking_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        booking = _booking(conn, booking_id, for_update=True)
        _require_own(booking["person_id"], acting_person_id=acting_person_id,
                     may_act_for_another=may_act_for_another, act="cancelling")
        if booking["state"] != "booked":
            raise Conflict(f"this_booking_is_{booking['state']}")
        rules = _policy_row(conn, booking["policy_id"])
        session = _session(conn, booking["session_id"])
        late = policy.cancellation_is_late(
            session["starts_at"], at=moment, policy=rules["policy"])
        occasion = "cancelled_late" if late else "cancelled_in_time"
        outcome = consequence.decide(
            occasion, no_show_count=_no_show_count(conn, booking["person_id"]),
            policy=rules["policy"],
            entitlement_cited=(booking["entitlement_grant_id"] is not None
                               and rules["forfeits_entitlement"]))
        hours_given = int(
            (session["starts_at"] - moment).total_seconds() // 3600)
        try:
            conn.execute(
                "UPDATE plt01.bkg_bookings SET state = 'cancelled', cancelled_at = %s,"
                " cancelled_by = %s, cancellation_reason = %s,"
                " cancel_correlation_id = %s"
                " WHERE booking_id = %s AND state = 'booked'",
                (moment, actor_id, reason.strip(), correlation_id, booking_id))
            conn.execute(
                """
                INSERT INTO plt01.bkg_cancellations
                    (tenant_id, booking_id, person_id, occasion, policy_hours,
                     hours_given, fee_due, credit_forfeit, reason, cancelled_at,
                     cancelled_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, booking_id, booking["person_id"], occasion,
                 rules["policy"].cancellation_hours,
                 max(-8760, min(8760, hours_given)), outcome.fee_due,
                 outcome.credit_forfeit, reason.strip(), moment, actor_id,
                 correlation_id))
        except errors.UniqueViolation:
            raise Conflict("this_booking_was_already_cancelled") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        # The place, back on the same connection.
        scheduling.release_hold_on(
            conn, tenant_id, booking["hold_id"],
            reason=f"booking cancelled: {reason.strip()}"[:500], actor_id=actor_id,
            correlation_id=correlation_id)
        _append(conn, tenant_id, "booking.cancelled", "booking", booking_id,
                {"booking_id": booking_id, "session_id": booking["session_id"],
                 "person_id": booking["person_id"], "occasion": occasion,
                 "fee_due": outcome.fee_due, "credit_forfeit": outcome.credit_forfeit},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"booking_id": booking_id, "state": "cancelled", "occasion": occasion,
            "fee_due": outcome.fee_due, "credit_forfeit": outcome.credit_forfeit,
            "hours_given": hours_given, "detail": outcome.detail,
            # **What this does not do**, said in the response rather than left to be
            # discovered: the fee and the credit are decisions MOD-017 acts on.
            "charged": False,
            "note": ("the fee and the entitlement are decided here and acted on by the "
                     "module that owns them; nothing has been charged")}


def _require_own(
    record_person_id: str, *, acting_person_id: str | None, may_act_for_another: bool,
    act: str,
) -> None:
    """Refuse a member doing something to another member's booking.

    **Both arguments are required, which is the point.** MOD-014's review showed that a check
    taking an optional list is a check somebody calls without it, so every command that acts on
    a record somebody else owns takes who the caller is *and* whether they may act for another
    -- and mypy is what makes the next caller supply them.

    `acting_person_id` is None for an identity with no `ppl_identity_links` row, which cannot
    be anybody's own record: that falls to the permission, which is the fail-closed direction.
    """
    if may_act_for_another:
        return
    if acting_person_id is not None and acting_person_id == record_person_id:
        return
    raise Forbidden(
        f"this booking belongs to another member; {act} on their behalf needs "
        f"booking.booking.act_for_another")


def _booking(
    conn: Connection[Any], booking_id: str, *, for_update: bool = False,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT session_id, person_id, hold_id, policy_id, state, entitlement_grant_id,"
        " checked_in_at"
        " FROM plt01.bkg_bookings WHERE booking_id = %s"
        + (" FOR UPDATE" if for_update else ""),
        (booking_id,),
    ).fetchone()
    if row is None:
        raise NotFound("booking_not_found")
    return {"session_id": str(row[0]), "person_id": str(row[1]),
            "hold_id": str(row[2]), "policy_id": str(row[3]), "state": str(row[4]),
            "entitlement_grant_id": None if row[5] is None else str(row[5]),
            "checked_in_at": row[6]}


def _no_show_count(conn: Connection[Any], person_id: str) -> int:
    """How many no-shows this member has that have not been overturned.

    **A sum over the rows, not a column on the member.** MOD-018's argument: a cached count is
    a second authority that can disagree with the records it came from, and here it decides
    whether somebody is struck. An upheld appeal sets `overturned_at`, which takes the record
    out of the count without unsaying that they missed the class.
    """
    row = conn.execute(
        "SELECT count(*) FROM plt01.bkg_no_shows"
        " WHERE person_id = %s AND overturned_at IS NULL",
        (person_id,),
    ).fetchone()
    return int(row[0]) if row else 0


# ------------------------------------------------------------------ the waitlist

#: How a tenant marks a member's waitlist tier: a MOD-014 tag named `waitlist-tier:<n>`,
#: lowest first. **A tag rather than a request field**, which is the whole of this: `tier` was
#: on `JoinWaitlistBody`, bounded `0..1000` and compared with nothing, so a basic member sent a
#: zero and took the place a premium member had paid priority for -- `position_of` put the
#: premium member second behind somebody who typed a number. Found by review, and it is the
#: shape `CLAUDE.md` names at the end: shape-checked, never checked for correspondence. MOD-016
#: reads the same table for the customer segment that chooses a price book.
TIER_TAG_PREFIX = "waitlist-tier:"


def _tier_for(conn: Connection[Any], person_id: str) -> int:
    """The member's waitlist tier, derived from their own record.

    Zero when they carry no tier tag, which is both the default and the best tier -- so a
    tenant that marks nobody has a pure first-come queue, and `priority_rule` is what decides
    whether the tag is consulted at all. An unparseable tag is ignored rather than raising: a
    typo in a tag name must not stop a member joining a waitlist.
    """
    rows = conn.execute(
        "SELECT t.tag_key FROM plt01.ppl_person_tags pt"
        " JOIN plt01.ppl_tags t ON t.tag_id = pt.tag_id"
        " WHERE pt.person_id = %s AND pt.removed_at IS NULL AND t.retired_at IS NULL"
        "   AND t.tag_key LIKE %s",
        (person_id, TIER_TAG_PREFIX + "%"),
    ).fetchall()
    tiers = [
        int(suffix) for suffix in (str(r[0])[len(TIER_TAG_PREFIX):] for r in rows)
        if suffix.isdecimal() and len(suffix) <= 4 and int(suffix) <= 1000]
    return min(tiers) if tiers else 0


def join_waitlist(
    pool: Pool, tenant_id: str, session_id: str, *, person_id: str, policy_key: str,
    idempotency_key: str, actor_id: str, correlation_id: str,
    entitlement_key: str | None = None, skills: list[str] | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """JoinWaitlist. OPS-02-R03.

    **Only a full session has a waitlist.** Joining one that has room is a member who could
    have booked and did not, and the queue would then promote them into a place they could
    have taken directly -- which reads to everybody else as somebody jumping it.
    """
    moment = at or _now()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        prior = conn.execute(
            "SELECT entry_id, session_id, person_id, state FROM plt01.bkg_waitlist_entries"
            " WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if prior is not None:
            if str(prior[1]) != session_id or str(prior[2]) != person_id:
                raise Conflict("this_idempotency_key_was_used_for_a_different_request")
            return {"entry_id": str(prior[0]), "state": str(prior[3]), "repeated": True}
        rules = _live_policy(conn, policy_key)
        session = _session(conn, session_id)
        if session["status"] != "scheduled":
            raise Conflict(f"this_session_is_{session['status']}")
        denial = _evaluate(
            conn, session=session, session_id=session_id, person_id=person_id,
            rules=rules, at=moment, entitlement_key=entitlement_key, skills=skills)
        if denial is None:
            raise Conflict(
                "this session has room; book it rather than joining the waitlist")
        if not denial.offer_waitlist:
            raise Conflict(denial.reason)
        # **The declared cap, which nothing read.** MOD-019 writes `waitlist_capacity` on the
        # session's capacity policy and `denial.py` makes `full` against `waitlist_full` a
        # design point -- "the first is an invitation to wait, the second is the end of the
        # conversation" -- for an outcome nothing could produce: a capacity-one policy with a
        # waitlist of one took five joins. Zero means no cap, which is the default and is why
        # the comparison is guarded. Found by review.
        cap = conn.execute(
            "SELECT p.waitlist_capacity FROM plt01.sch_capacity_policies p"
            " JOIN plt01.sch_sessions s ON s.policy_id = p.policy_id"
            " WHERE s.session_id = %s",
            (session_id,),
        ).fetchone()
        limit = int(cap[0]) if cap else 0
        if limit > 0:
            waiting = len([
                e for e in _entries(conn, session_id)
                if e.state in waitlist.LIVE_STATES])
            if waiting >= limit:
                raise Conflict("waitlist_full")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.bkg_waitlist_entries
                    (tenant_id, session_id, person_id, policy_id, tier, joined_at,
                     joined_by, idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING entry_id
                """,
                (tenant_id, session_id, person_id, rules["policy_id"],
                 _tier_for(conn, person_id), moment,
                 actor_id, idempotency_key.strip(), correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_member_is_already_on_this_waitlist") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        entry_id = str(row[0])
        _append(conn, tenant_id, "waitlist.joined", "waitlist_entry", entry_id,
                {"entry_id": entry_id, "session_id": session_id,
                 "person_id": person_id, "position": _position(conn, session_id,
                                                               entry_id, rules)},
                correlation_id=correlation_id, actor_id=actor_id)
        position = _position(conn, session_id, entry_id, rules)
    return {"entry_id": entry_id, "session_id": session_id, "person_id": person_id,
            "state": "waiting", "position": position, "repeated": False}


def _entries(conn: Connection[Any], session_id: str) -> list[waitlist.Entry]:
    rows = conn.execute(
        "SELECT entry_id, person_id, joined_at, state, tier, offered_at,"
        " offer_expires_at"
        " FROM plt01.bkg_waitlist_entries WHERE session_id = %s"
        " ORDER BY tier, joined_at, entry_id",
        (session_id,),
    ).fetchall()
    return [waitlist.Entry(
        entry_id=str(r[0]), person_id=str(r[1]), joined_at=r[2], state=str(r[3]),
        tier=int(r[4]), offered_at=r[5], offer_expires_at=r[6]) for r in rows]


def _queue_policy(conn: Connection[Any], session_id: str) -> dict[str, Any]:
    """The policy that orders this queue: the one in force when the queue opened.

    **The order is a property of the queue, so it has to come from one policy.** Entries can
    cite different versions -- a tenant publishing a new one mid-queue is ordinary -- and the
    priority rule is the one field that cannot differ per member: a queue half ordered by
    arrival and half by tier has no order at all.

    **The earliest entry's**, stated rather than incidental, which is the snapshot discipline
    this build uses everywhere else: the rule in force when the queue opened governs it, like
    the terms on an agreement. The first version read "some entry's policy" with an
    `ORDER BY joined_at LIMIT 1` and no comment, which is MOD-010's finding -- a decision made
    once per job and applied per item, where which item you get is the planner's choice.

    The *offer window* is a different question and is read per member, from the policy that
    member joined under: how long somebody has to answer is about them.
    """
    row = conn.execute(
        "SELECT policy_id FROM plt01.bkg_waitlist_entries WHERE session_id = %s"
        " ORDER BY joined_at, entry_id LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        raise NotFound("waitlist_entry_not_found")
    return _policy_row(conn, str(row[0]))


def _entry_row(conn: Connection[Any], entry_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT session_id, person_id, policy_id, state, hold_id, offered_at,"
        " offer_expires_at, tier, joined_at"
        " FROM plt01.bkg_waitlist_entries WHERE entry_id = %s FOR UPDATE",
        (entry_id,),
    ).fetchone()
    if row is None:
        raise NotFound("waitlist_entry_not_found")
    return {"session_id": str(row[0]), "person_id": str(row[1]),
            "policy_id": str(row[2]), "state": str(row[3]),
            "hold_id": None if row[4] is None else str(row[4]),
            "offered_at": row[5], "offer_expires_at": row[6], "tier": int(row[7]),
            "joined_at": row[8]}


def _position(
    conn: Connection[Any], session_id: str, entry_id: str, rules: dict[str, Any],
) -> int | None:
    return waitlist.position_of(
        _entries(conn, session_id), entry_id, policy=rules["policy"])


def promote_waitlist(
    pool: Pool, tenant_id: str, session_id: str, *, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """PromoteWaitlist: offer the next free place to the next member. OPS-02-R03.

    **Reserve, then notify.** Paragraph 5031, and the order is the whole design: a promotion
    that notified first would tell a member they have a place and then race somebody else for
    it, and the loser would have been told they had won. So the MOD-019 hold is taken here, on
    this connection, inside the transaction that records the offer -- and MOD-013's message
    goes out afterwards, reading the row. "Notification failure does not lose the booking
    state" (paragraph 5032) follows: the place is already held, so a message that never arrives
    is a member who has to be told again.

    **Idempotent, and by the database rather than by a flag.** Paragraph 4144. Calling this
    twice cannot promote two members into one seat: MOD-019's
    `sch_capacity_holds_one_live_per_person` refuses a second hold for the same member, and
    `next_to_offer` counts the offers already outstanding against the free places -- so the
    second call finds nothing free and does nothing.

    **One member per call, and the call says how many more it could serve.** The free count
    and the queue are both returned, so a caller promoting into five free places calls this
    five times and can see that it should. A loop here would hold MOD-019's lock across five
    holds in one transaction, which is the lock ordering `take_hold_on` is written to avoid.

    **It takes no lock of its own on the session**, deliberately: `take_hold_on` takes
    MOD-019's, and a second lock here in a different order is a deadlock between promoting and
    booking.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        session = _session(conn, session_id)
        if session["status"] != "scheduled":
            raise Conflict(f"this_session_is_{session['status']}")
        entries = _entries(conn, session_id)
        if not entries:
            return {"session_id": session_id, "promoted": None,
                    "detail": "nobody is waiting"}
        queue_rules = _queue_policy(conn, session_id)
        # **As many as there are free places.** Counted here rather than assumed to be one:
        # five cancellations two hours before a class used to fill two seats, because the
        # promotion refused to look past a single outstanding offer.
        taken = conn.execute(
            "SELECT coalesce(sum(places), 0) FROM plt01.sch_capacity_holds"
            " WHERE session_id = %s AND status IN ('held', 'attended')",
            (session_id,),
        ).fetchone()
        free = max(0, session["capacity"] + session["overbook_places"]
                   - int(taken[0] if taken else 0))
        candidates = waitlist.next_to_offer(
            entries, policy=queue_rules["policy"], at=moment, places=free)
        if not candidates:
            return {"session_id": session_id, "promoted": None, "offered": [],
                    "free": free,
                    "detail": ("no place is free beyond the offers already outstanding, "
                               "or nobody is waiting; the queue advances when an offer "
                               "resolves")}
        candidate = candidates[0]
        # **This member's own policy decides how long they have.** The queue's order is one
        # rule for everybody; the offer window is about the person answering it.
        own = _policy_row(conn, _entry_row(conn, candidate.entry_id)["policy_id"])
        expires = waitlist.offer_expiry(at=moment, policy=own["policy"])
        # The place first. If this refuses -- the session filled from somewhere else between
        # the read and now -- nothing is offered and nothing is written.
        try:
            hold = scheduling.take_hold_on(
                conn, tenant_id, session_id, person_id=candidate.person_id,
                source_kind="booking",
                source_ref=f"waitlist:{candidate.entry_id}",
                idempotency_key=f"wl-{candidate.entry_id}-{int(moment.timestamp())}",
                actor_id=actor_id, correlation_id=correlation_id, places=1, at=moment)
        except Conflict as e:
            return {"session_id": session_id, "promoted": None,
                    "detail": f"no place came free: {e}"}
        try:
            moved = conn.execute(
                "UPDATE plt01.bkg_waitlist_entries"
                "   SET state = 'offered', hold_id = %s, offered_at = %s,"
                "       offer_expires_at = %s, offer_correlation_id = %s,"
                "       offers_made = offers_made + 1"
                " WHERE entry_id = %s AND state IN ('waiting', 'expired')",
                (hold["hold_id"], moment, expires, correlation_id,
                 candidate.entry_id),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if moved == 0:
            # Somebody else promoted this entry between the read and the write. The hold we
            # just took is theirs, not a leak: it is the same entry and the same person.
            raise Conflict("this_entry_was_offered_by_somebody_else")
        _append(conn, tenant_id, "waitlist.promoted", "waitlist_entry",
                candidate.entry_id,
                {"entry_id": candidate.entry_id, "session_id": session_id,
                 "person_id": candidate.person_id,
                 "offer_expires_at": expires.isoformat()},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"session_id": session_id,
            "promoted": {"entry_id": candidate.entry_id,
                         "person_id": candidate.person_id,
                         "hold_id": str(hold["hold_id"]),
                         "offer_expires_at": expires.isoformat()},
            # **How many more this session could still promote**, so a caller with five
            # cancellations knows to call again rather than assuming one went out.
            "more_to_offer": max(0, len(candidates) - 1),
            # **The place is reserved and the member has not been told.** MOD-013 sends the
            # message from this row; saying so here is what stops a caller assuming it went.
            "notified": False,
            "detail": ("the place is held for this member until the offer expires; "
                       "notifying them is MOD-013's and has not happened")}





def confirm_offer(
    pool: Pool, tenant_id: str, entry_id: str, *, idempotency_key: str, actor_id: str,
    acting_person_id: str | None, may_act_for_another: bool, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """A member takes the place they were offered: the offer becomes a booking.

    **The place is already theirs**, taken when the offer was made -- so this writes a booking
    against the hold that exists rather than taking a new one. Taking another would be a second
    seat for one member, which MOD-019's one-live-hold index would refuse and which would make
    a confirmation fail for a member who was correctly promoted.

    **The expiry is re-read here**, under a lock on the entry: `may_confirm` answers a surface
    asking whether to show the button, and an offer window is an hour long -- "a control
    consulted once is a control with a window" is MOD-009's finding and this is a window by
    construction.
    """
    moment = at or _now()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        entry = _entry_row(conn, entry_id)
        _require_own(entry["person_id"], acting_person_id=acting_person_id,
                     may_act_for_another=may_act_for_another,
                     act="confirming an offer")
        # **A namespace of its own.** The booking this writes shares
        # `bkg_bookings.idempotency_key` with `create_booking`, so a till reusing one counter
        # across both had its confirmation refused by the unique index -- mapped to
        # "this_offer_was_already_confirmed", which was the opposite of what was true: the
        # offer was never confirmed, the member could not confirm it, and the seat stayed held
        # until an expiry nothing drives. MOD-018's rule: an idempotency namespace a caller
        # can write into is not a namespace.
        key = f"wl-confirm:{entry_id}:{_short(idempotency_key)}"
        # **And idempotent to the caller**, which it was not at all: a client whose request
        # timed out after the commit was told 409 for work that had succeeded. MOD-017's rule.
        prior = conn.execute(
            "SELECT booking_id, person_id, session_id FROM plt01.bkg_bookings"
            " WHERE idempotency_key = %s",
            (key,),
        ).fetchone()
        if prior is not None:
            if (str(prior[1]) != entry["person_id"]
                    or str(prior[2]) != entry["session_id"]):
                raise Conflict("this_idempotency_key_was_used_for_a_different_request")
            return {"entry_id": entry_id, "booking_id": str(prior[0]),
                    "state": "confirmed", "session_id": entry["session_id"],
                    "person_id": entry["person_id"], "repeated": True}
        live = waitlist.Entry(
            entry_id=entry_id, person_id=entry["person_id"],
            joined_at=entry["joined_at"], state=entry["state"], tier=entry["tier"],
            offered_at=entry["offered_at"],
            offer_expires_at=entry["offer_expires_at"])
        try:
            waitlist.may_confirm(live, at=moment)
        except ValueError as e:
            raise Conflict(str(e)) from None
        assert entry["hold_id"] is not None
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.bkg_bookings
                    (tenant_id, session_id, person_id, hold_id, policy_id, source_kind,
                     booked_by, idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, 'waitlist', %s, %s, %s)
                RETURNING booking_id
                """,
                (tenant_id, entry["session_id"], entry["person_id"], entry["hold_id"],
                 entry["policy_id"], actor_id, key, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_offer_was_already_confirmed") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        assert row is not None
        booking_id = str(row[0])
        moved = conn.execute(
            "UPDATE plt01.bkg_waitlist_entries SET state = 'confirmed',"
            " booking_id = %s, settled_at = %s, settled_by = %s,"
            " settle_reason = 'the member took the place', settle_correlation_id = %s"
            " WHERE entry_id = %s AND state = 'offered'",
            (booking_id, moment, actor_id, correlation_id, entry_id),
        ).rowcount
        if moved == 0:
            raise Conflict("this_offer_was_settled_by_somebody_else")
        _append(conn, tenant_id, "booking.created", "booking", booking_id,
                {"booking_id": booking_id, "session_id": entry["session_id"],
                 "person_id": entry["person_id"], "source_kind": "waitlist",
                 "starts_at": _session(conn, entry["session_id"])[
                     "starts_at"].isoformat()},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"entry_id": entry_id, "booking_id": booking_id, "state": "confirmed",
            "session_id": entry["session_id"], "person_id": entry["person_id"],
            "repeated": False}


def leave_waitlist(
    pool: Pool, tenant_id: str, entry_id: str, *, reason: str, actor_id: str,
    acting_person_id: str | None, may_act_for_another: bool, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """A member takes themselves off a waitlist, whether or not they hold an offer.

    **Two of seven states were unreachable, and this is the act that reaches them.**
    `withdrawn` and `lapsed` were declared in `ENTRY_STATES` and in `EDGES` and nothing in
    the build wrote either, so a member could not leave a queue at all: a reviewer tried
    `settle_offer` on a waiting entry, was refused, and watched the member auto-promoted into
    a seat they no longer wanted while somebody who did want it was told the class was full.

    **One act, because that is how a member thinks of it.** From `waiting` it is a withdrawal;
    from `offered` it is a decline, which also releases the place -- and declining is the
    member's own choice, so it belongs on a member-facing route rather than on the operational
    `settle_offer`, which is the sweep that releases an offer the *clock* ran out on.
    """
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("leaving_a_waitlist_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        entry = _entry_row(conn, entry_id)
        _require_own(entry["person_id"], acting_person_id=acting_person_id,
                     may_act_for_another=may_act_for_another,
                     act="leaving a waitlist")
        if entry["state"] not in ("waiting", "offered", "expired"):
            raise Conflict(f"this_entry_is_{entry['state']}")
        target = "declined" if entry["state"] == "offered" else "withdrawn"
        if entry["hold_id"] is not None:
            # A declined offer that kept its hold is a seat nobody can book, held for a
            # member who said no.
            scheduling.release_hold_on(
                conn, tenant_id, entry["hold_id"],
                reason=f"the member left the waitlist: {reason.strip()}"[:500],
                actor_id=actor_id, correlation_id=correlation_id)
        moved = conn.execute(
            "UPDATE plt01.bkg_waitlist_entries SET state = %s, hold_id = NULL,"
            " settled_at = %s, settled_by = %s, settle_reason = %s,"
            " settle_correlation_id = %s"
            " WHERE entry_id = %s AND state = %s",
            (target, moment, actor_id, reason.strip(), correlation_id, entry_id,
             entry["state"]),
        ).rowcount
        if moved == 0:
            raise Conflict("this_entry_was_settled_by_somebody_else")
    return {"entry_id": entry_id, "state": target,
            "session_id": entry["session_id"],
            "place_released": entry["hold_id"] is not None}


def settle_offer(
    pool: Pool, tenant_id: str, entry_id: str, *, declined: bool, reason: str,
    actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """An offer the member turned down, or one the clock ran out on.

    **Declining ends the entry; expiring returns it to the queue.** A member asleep at six in
    the morning did not decline, and sending them to the back would make the waitlist a lottery
    about who is awake -- so an expiry goes back to `waiting` and keeps its place. A decline is
    a choice and is final.

    **The place goes back either way**, on this connection: paragraph 5032's "expired promotion
    releases capacity", and a declined offer that kept its hold would be a seat nobody can book
    held for a member who said no.
    """
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("settling_an_offer_states_why")
    target = "declined" if declined else "expired"
    with tenant_scope(pool, tenant_id) as conn:
        entry = _entry_row(conn, entry_id)
        if entry["state"] != "offered":
            raise Conflict(f"this_entry_is_{entry['state']}")
        if not declined and not waitlist.offer_has_expired(
                waitlist.Entry(
                    entry_id=entry_id, person_id=entry["person_id"],
                    joined_at=entry["joined_at"], state="offered",
                    tier=entry["tier"], offered_at=entry["offered_at"],
                    offer_expires_at=entry["offer_expires_at"]), at=moment):
            raise Conflict("this_offer_has_not_expired_yet")
        assert entry["hold_id"] is not None
        scheduling.release_hold_on(
            conn, tenant_id, entry["hold_id"],
            reason=f"waitlist offer {target}: {reason.strip()}"[:500],
            actor_id=actor_id, correlation_id=correlation_id)
        if declined:
            moved = conn.execute(
                "UPDATE plt01.bkg_waitlist_entries SET state = 'declined',"
                " hold_id = NULL, settled_at = %s, settled_by = %s,"
                " settle_reason = %s, settle_correlation_id = %s"
                " WHERE entry_id = %s AND state = 'offered'",
                (moment, actor_id, reason.strip(), correlation_id, entry_id),
            ).rowcount
        else:
            # **Back to waiting, keeping `joined_at`.** The grant on that column does not
            # exist and the trigger refuses a change to it, so the place in the queue is not
            # something this path could lose even by mistake.
            moved = conn.execute(
                "UPDATE plt01.bkg_waitlist_entries SET state = 'expired',"
                " hold_id = NULL, offered_at = NULL, offer_expires_at = NULL,"
                " offer_correlation_id = NULL"
                " WHERE entry_id = %s AND state = 'offered'",
                (entry_id,),
            ).rowcount
        if moved == 0:
            raise Conflict("this_offer_was_settled_by_somebody_else")
    return {"entry_id": entry_id, "state": target,
            "session_id": entry["session_id"], "place_released": True,
            "detail": ("this entry keeps its place in the queue" if not declined
                       else "this entry is closed")}


def expire_offers(
    pool: Pool, tenant_id: str, *, actor_id: str, correlation_id: str, limit: int = 200,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Release the places held by offers whose window has closed. ReleaseCapacity.

    **Nothing drives this.** It is the sweep paragraph 5032 implies -- "expired promotion
    releases capacity" -- and no worker loops on it in this build, which is the twelfth module
    to want one. Until there is one, an expired offer holds its place until somebody calls
    this or the member answers.
    """
    moment = at or _now()
    released: list[dict[str, Any]] = []
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT entry_id FROM plt01.bkg_waitlist_entries"
            " WHERE state = 'offered' AND offer_expires_at <= %s"
            " ORDER BY offer_expires_at LIMIT %s",
            (moment, max(1, min(limit, 1000))),
        ).fetchall()
        for row in rows:
            entry_id = str(row[0])
            entry = _entry_row(conn, entry_id)
            if entry["state"] != "offered" or entry["hold_id"] is None:
                continue
            scheduling.release_hold_on(
                conn, tenant_id, entry["hold_id"],
                reason="the waitlist offer expired unanswered", actor_id=actor_id,
                correlation_id=correlation_id)
            conn.execute(
                "UPDATE plt01.bkg_waitlist_entries SET state = 'expired',"
                " hold_id = NULL, offered_at = NULL, offer_expires_at = NULL,"
                " offer_correlation_id = NULL"
                " WHERE entry_id = %s AND state = 'offered'",
                (entry_id,))
            released.append({"entry_id": entry_id,
                             "session_id": entry["session_id"],
                             "person_id": entry["person_id"]})
    return {"released": len(released), "entries": released,
            "as_of": moment.isoformat()}


# ------------------------------------------------------------------ attendance

def check_in_booking(
    pool: Pool, tenant_id: str, booking_id: str, *, source: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """CheckInBooking. OPS-02's attendance linkage.

    **Recorded, not performed.** Nothing in this build reads a turnstile -- MOD-021 is the
    hardware bridge and MOD-022 is access, neither of which exists -- so this records that a
    named actor marked a member present at a time, through a declared channel. The same shape
    as MOD-012's `validated` install and MOD-014's contact verification, and said here for the
    same reason: a row that read as a verified arrival with nothing having verified anything is
    the fabricated-evidence shape this codebase has been bitten by repeatedly.

    **The place is marked attended, not released.** MOD-019 distinguishes the two, and a place
    released at check-in would read as free for the hour the member is in the room.
    """
    moment = at or _now()
    try:
        attendance.check_source(source)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        booking = _booking(conn, booking_id, for_update=True)
        if booking["checked_in_at"] is not None:
            return {"booking_id": booking_id, "state": booking["state"],
                    "checked_in_at": booking["checked_in_at"].isoformat(),
                    "repeated": True}
        rules = _policy_row(conn, booking["policy_id"])
        session = _session(conn, booking["session_id"])
        try:
            attendance.may_check_in(
                attendance.Attendance(
                    booking_state=booking["state"],
                    session_starts_at=session["starts_at"],
                    session_ends_at=session["ends_at"]),
                at=moment, policy=rules["policy"])
        except ValueError as e:
            raise Conflict(str(e)) from None
        try:
            marked = conn.execute(
                "UPDATE plt01.bkg_bookings SET checked_in_at = %s, checked_in_by = %s,"
                " checkin_source = %s, checkin_correlation_id = %s"
                " WHERE booking_id = %s AND state = 'booked'"
                "   AND checked_in_at IS NULL",
                (moment, actor_id, source, correlation_id, booking_id),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if marked == 0:
            raise Conflict("this_booking_was_checked_in_by_somebody_else")
        _append(conn, tenant_id, "booking.checked_in", "booking", booking_id,
                {"booking_id": booking_id, "session_id": booking["session_id"],
                 "person_id": booking["person_id"], "source": source},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"booking_id": booking_id, "state": "booked",
            "checked_in_at": moment.isoformat(), "source": source, "repeated": False}


def declare_intent(
    pool: Pool, tenant_id: str, booking_id: str, *, intent: str, source: str,
    idempotency_key: str, actor_id: str, acting_person_id: str | None,
    may_act_for_another: bool, correlation_id: str,
) -> dict[str, Any]:
    """The AttendanceIntent entity: a member says whether they are coming.

    **Insert-only, so a change of mind is a new row.** "I am coming" at nine and "I cannot make
    it" at five are both true of their day, and overwriting the first would lose the fact that
    the gym was told twice -- which is what distinguishes a member who always answers from one
    who never does.

    This is the observable signal `consequence.py` says is enough without a predictive score: a
    member who declared they are not coming is not a risk, they are a place that can be offered.
    """
    if intent not in ("attending", "not_attending", "unsure"):
        raise InvalidRequest("unknown_attendance_intent")
    if source not in ("app", "reminder_reply", "front_desk", "migration"):
        raise InvalidRequest("unknown_intent_source")
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        booking = _booking(conn, booking_id)
        _require_own(booking["person_id"], acting_person_id=acting_person_id,
                     may_act_for_another=may_act_for_another,
                     act="declaring attendance")
        prior = conn.execute(
            "SELECT intent_id, intent, booking_id, source"
            " FROM plt01.bkg_attendance_intents WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if prior is not None:
            # **Compared on every field**, which it did not do either: two members' bookings
            # under one key returned 201 for a write that never happened, against the wrong
            # booking and reporting the wrong intent. `consequence.py` calls this the
            # observable signal that makes the absence of a predicted score affordable, and a
            # channel that records nothing while saying it did is worse than none.
            if (str(prior[2]) != booking_id or str(prior[1]) != intent
                    or str(prior[3]) != source):
                raise Conflict("this_idempotency_key_was_used_for_a_different_request")
            return {"intent_id": str(prior[0]), "intent": str(prior[1]),
                    "booking_id": booking_id, "source": source, "repeated": True}
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.bkg_attendance_intents
                    (tenant_id, booking_id, person_id, intent, source, declared_by,
                     idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING intent_id
                """,
                (tenant_id, booking_id, booking["person_id"], intent, source, actor_id,
                 idempotency_key.strip(), correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        assert row is not None
    return {"intent_id": str(row[0]), "booking_id": booking_id, "intent": intent,
            "source": source, "repeated": False}


def _release_booking(
    conn: Connection[Any], tenant_id: str, booking_id: str, *, person_id: str,
    session_id: str, session: dict[str, Any], rules: dict[str, Any], at: datetime,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Where a booking goes when the *session* was cancelled, rather than the member.

    **The defect this closes is the worst one available to this module.** `released` and
    `consequence.OCCASIONS`'s `session_cancelled` were both declared, both documented as
    existing so that "somebody does not get a strike for a class the gym called off", and
    nothing in the build wrote either -- so settling a cancelled session ran the ordinary
    no-show path and recorded every member of it as absent, with a fee, a forfeited credit and
    a warning or a strike. `bkg_bookings.state` is one-way by trigger and `bkg_no_shows` has
    no DELETE grant, so it was permanent, and the only remedy was an appeal per member by
    hand. Found by review, on a tenant doing nothing but cancelling a class.

    **A cancellation row rather than silence**, because the member has to be able to see why
    their booking ended. `bkg_cancellations_gym_cancellation_is_free` is the constraint that
    makes the figures on it unarguable -- it refuses a `session_cancelled` row carrying a fee
    at all, so the schema would have caught a service that got this half right.

    **The holds are MOD-019's to release and it already has.** `cancel_session` releases every
    hold on the session in the transaction that cancels it, so touching them here would be a
    second release of a settled hold -- refused, correctly, and it would abort the sweep.
    """
    reason = (session["cancellation_reason"]
              or "the session was cancelled")
    conn.execute(
        "UPDATE plt01.bkg_bookings SET state = 'released', cancelled_at = %s,"
        " cancelled_by = %s, cancellation_reason = %s, cancel_correlation_id = %s"
        " WHERE booking_id = %s AND state = 'booked'",
        (at, actor_id, reason, correlation_id, booking_id))
    outcome = consequence.decide(
        "session_cancelled", no_show_count=0, policy=rules["policy"],
        entitlement_cited=rules["forfeits_entitlement"])
    given = int((session["starts_at"]
                 - (session["cancelled_at"] or at)).total_seconds() // 3600)
    try:
        conn.execute(
            """
            INSERT INTO plt01.bkg_cancellations
                (tenant_id, booking_id, person_id, occasion, policy_hours, hours_given,
                 fee_due, credit_forfeit, reason, cancelled_at, cancelled_by,
                 correlation_id)
            VALUES (%s, %s, %s, 'session_cancelled', %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (tenant_id, booking_id, person_id, rules["policy"].cancellation_hours,
             given, outcome.fee_due, outcome.credit_forfeit, reason, at, actor_id,
             correlation_id))
    except errors.UniqueViolation:
        raise Conflict("this_booking_already_has_a_cancellation_record") from None
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    _append(conn, tenant_id, "booking.cancelled", "booking", booking_id,
            {"booking_id": booking_id, "session_id": session_id,
             "person_id": person_id, "occasion": "session_cancelled",
             "fee_due": outcome.fee_due, "credit_forfeit": outcome.credit_forfeit},
            actor_id=actor_id, correlation_id=correlation_id)
    return {"booking_id": booking_id, "person_id": person_id, "state": "released",
            "occasion": "session_cancelled", "fee_due": outcome.fee_due,
            "credit_forfeit": outcome.credit_forfeit, "sanction": outcome.sanction}


def settle_session_bookings(
    pool: Pool, tenant_id: str, session_id: str, *, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """RecordNoShow, for every booking on a finished session. OPS-02-R04.

    **Derived from three facts, not set by anybody**: the booking is still open, nobody checked
    in, and the check-in window has closed. Two tenants cannot disagree about what a no-show is,
    and nobody can mark one by hand -- which matters because it carries a sanction.

    **The count is read per member inside the loop**, so a member with two no-shows on one day
    gets a warning for the first and a strike for the second where the policy says so. Reading
    it once outside would be MOD-010's finding: a decision made once per job and applied per
    item.

    **Nothing drives this either.** The thirteenth place in this build that wants the worker
    runtime, and the one where the absence is most visible: a session nobody settles leaves
    every member's place reading as held for ever.
    """
    moment = at or _now()
    settled: list[dict[str, Any]] = []
    with tenant_scope(pool, tenant_id) as conn:
        session = _session(conn, session_id)
        rows = conn.execute(
            "SELECT booking_id, person_id, hold_id, policy_id, checked_in_at"
            " FROM plt01.bkg_bookings WHERE session_id = %s AND state = 'booked'"
            " ORDER BY booked_at",
            (session_id,),
        ).fetchall()
        for row in rows:
            booking_id = str(row[0])
            person_id = str(row[1])
            rules = _policy_row(conn, str(row[3]))
            if session["status"] == "cancelled":
                settled.append(_release_booking(
                    conn, tenant_id, booking_id, person_id=person_id,
                    session_id=session_id, session=session, rules=rules, at=moment,
                    actor_id=actor_id,
                    correlation_id=correlation_id))
                continue
            facts = attendance.Attendance(
                booking_state="booked", session_starts_at=session["starts_at"],
                session_ends_at=session["ends_at"], checked_in_at=row[4])
            try:
                target = attendance.settle(facts, at=moment, policy=rules["policy"])
            except ValueError as e:
                raise Conflict(str(e)) from None
            conn.execute(
                "UPDATE plt01.bkg_bookings SET state = %s, settled_at = %s"
                " WHERE booking_id = %s AND state = 'booked'",
                (target, moment, booking_id))
            scheduling.release_hold_on(
                conn, tenant_id, str(row[2]),
                reason=f"the session is over and this place was {target}",
                actor_id=actor_id, correlation_id=correlation_id,
                attended=(target == "attended"))
            if target == "no_show":
                # **Counted after this one is recorded**, including it: the sanction is about
                # how many times the member has missed a class, and excluding the one being
                # decided would mean a policy that strikes after three never struck.
                count = _no_show_count(conn, person_id) + 1
                outcome = consequence.decide(
                    "no_show", no_show_count=count, policy=rules["policy"],
                    entitlement_cited=rules["forfeits_entitlement"])
                try:
                    conn.execute(
                        """
                        INSERT INTO plt01.bkg_no_shows
                            (tenant_id, booking_id, person_id, session_id, fee_due,
                             credit_forfeit, sanction, no_show_count,
                             policy_warn_after, policy_strike_after, recorded_at,
                             recorded_by, correlation_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (tenant_id, booking_id, person_id, session_id, outcome.fee_due,
                         outcome.credit_forfeit, outcome.sanction, count,
                         rules["policy"].warn_after_no_shows,
                         rules["policy"].strike_after_no_shows, moment, actor_id,
                         correlation_id))
                except errors.UniqueViolation:
                    raise Conflict("this_booking_already_has_a_no_show_record") from None
                except errors.CheckViolation as e:
                    raise InvalidRequest(_check_name(e)) from None
                _append(conn, tenant_id, "no_show.recorded", "booking", booking_id,
                        {"booking_id": booking_id, "session_id": session_id,
                         "person_id": person_id, "sanction": outcome.sanction,
                         "no_show_count": count},
                        correlation_id=correlation_id, actor_id=actor_id)
                settled.append({"booking_id": booking_id, "state": target,
                                "sanction": outcome.sanction, "no_show_count": count})
            else:
                settled.append({"booking_id": booking_id, "state": target,
                                "sanction": "none"})
    return {"session_id": session_id, "settled": len(settled), "bookings": settled,
            "as_of": moment.isoformat(),
            "charged": False,
            "note": ("fees and forfeited entitlements are decisions here; the modules that "
                     "own money and entitlements act on them")}


# ------------------------------------------------------------------ appeals

def raise_appeal(
    pool: Pool, tenant_id: str, *, subject_person_id: str, against: str,
    grounds: str, idempotency_key: str, actor_id: str, correlation_id: str,
    no_show_id: str | None = None, cancellation_id: str | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """A member disputes a sanction. OPS-02-R04's appeal, the first of two acts.

    **The subject is checked against the record, by the trigger as well as here.** Nothing
    relates `subject_person_id` to the `person_id` on the no-show, so without it one member
    could appeal another's strike -- and an upheld appeal would overturn it. MOD-013's finding:
    two keys that nothing relates are two halves of a control.

    **A sanction stands while the appeal is open.** Suspending it would make appealing free and
    automatic, and a tenant whose strikes never bite has no policy at all.
    """
    moment = at or _now()
    if not grounds.strip():
        raise InvalidRequest("an_appeal_states_its_grounds")
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    if (no_show_id is None) == (cancellation_id is None):
        raise InvalidRequest("an_appeal_is_about_one_record")
    if against not in appeals.APPEALABLE:
        raise InvalidRequest("unknown_appeal_subject")
    with tenant_scope(pool, tenant_id) as conn:
        prior = conn.execute(
            "SELECT appeal_id, state, subject_person_id, no_show_id, cancellation_id,"
            " against FROM plt01.bkg_appeals WHERE idempotency_key = %s",
            (idempotency_key.strip(),),
        ).fetchone()
        if prior is not None:
            # **Every field of the request is compared**, which this did not do at all. A
            # member with two strikes reusing a per-shift counter was handed the *first*
            # appeal back with 201 and `repeated: true` -- so their second strike had no
            # appeal, nobody saw one in the queue, they were told theirs had been heard and
            # rejected, and the thirty-day window then ran out. MOD-019's finding with the
            # comparison removed entirely, landing on the one remedy a sanction has.
            same = (str(prior[2]) == subject_person_id
                    and (None if prior[3] is None else str(prior[3])) == no_show_id
                    and (None if prior[4] is None else str(prior[4])) == cancellation_id
                    and str(prior[5]) == against)
            if not same:
                raise Conflict("this_idempotency_key_was_used_for_a_different_request")
            return {"appeal_id": str(prior[0]), "state": str(prior[1]),
                    "against": against, "subject_person_id": subject_person_id,
                    "repeated": True}
        record = _appealed_record(
            conn, no_show_id=no_show_id, cancellation_id=cancellation_id)
        if not appeals.within_appeal_window(record["at"], at=moment):
            raise Conflict(
                f"an appeal is raised within {appeals.APPEAL_WINDOW_DAYS} days; this was "
                f"recorded on {record['at'].date().isoformat()}")
        try:
            appeals.check_against(
                against, fee_due=record["fee_due"],
                credit_forfeit=record["credit_forfeit"], sanction=record["sanction"])
        except ValueError as e:
            raise Conflict(str(e)) from None
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.bkg_appeals
                    (tenant_id, subject_person_id, no_show_id, cancellation_id, against,
                     grounds, raised_at, raised_by, idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING appeal_id
                """,
                (tenant_id, subject_person_id, no_show_id, cancellation_id, against,
                 grounds.strip(), moment, actor_id, idempotency_key.strip(),
                 correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        assert row is not None
    return {"appeal_id": str(row[0]), "state": "open", "against": against,
            "subject_person_id": subject_person_id, "repeated": False}


def _appealed_record(
    conn: Connection[Any], *, no_show_id: str | None, cancellation_id: str | None,
) -> dict[str, Any]:
    """When the record was made and what it carries, so an appeal can be checked against it.

    Returns the figures as well as the date because `appeals.check_against` needs them: an
    appeal against a strike on a record whose sanction is `none` was accepted and upheld,
    which is a decision about something that never happened. A cancellation has no sanction,
    so that key is None for one.
    """
    if no_show_id is not None:
        row = conn.execute(
            "SELECT recorded_at, fee_due, credit_forfeit, sanction"
            " FROM plt01.bkg_no_shows WHERE no_show_id = %s",
            (no_show_id,),
        ).fetchone()
        if row is None:
            raise NotFound("no_show_record_not_found")
        return {"at": row[0], "fee_due": bool(row[1]),
                "credit_forfeit": bool(row[2]), "sanction": str(row[3])}
    row = conn.execute(
        "SELECT cancelled_at, fee_due, credit_forfeit"
        " FROM plt01.bkg_cancellations WHERE cancellation_id = %s",
        (cancellation_id,),
    ).fetchone()
    if row is None:
        raise NotFound("cancellation_not_found")
    return {"at": row[0], "fee_due": bool(row[1]),
            "credit_forfeit": bool(row[2]), "sanction": None}


def decide_appeal(
    pool: Pool, tenant_id: str, appeal_id: str, *, uphold: bool, note: str,
    actor_id: str, decider_person_id: str | None, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """The second act: somebody who is not the member decides. OPS-02-R04.

    **`decider_person_id` is derived by the route from the session, never taken from a body.**
    MOD-016's review found a separation of duties that no stricter check could rescue because
    the requester was a field on the approval; here the subject is on the appeal row and the
    decider comes from the authenticated identity, so the two sides are both the server's.

    **An upheld appeal overturns the record without unsaying it.** The no-show stays -- the
    member did miss the class -- and what changes is whether it counts towards a sanction,
    which is what `_no_show_count` reads. A fee is MOD-017's to credit, and this says so rather
    than claiming to have reversed one.
    """
    moment = at or _now()
    if not note.strip():
        raise InvalidRequest("a_decision_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT subject_person_id, against, state, no_show_id, cancellation_id"
            " FROM plt01.bkg_appeals WHERE appeal_id = %s FOR UPDATE",
            (appeal_id,),
        ).fetchone()
        if row is None:
            raise NotFound("appeal_not_found")
        against = str(row[1])
        appeal = appeals.Appeal(
            appeal_id=appeal_id, subject_person_id=str(row[0]), against=against,
            state=str(row[2]), raised_at=moment)
        if appeal.state != "open":
            raise Conflict(f"this_appeal_is_{appeal.state}")
        try:
            appeals.check_decider(appeal, decider_person_id=decider_person_id)
        except ValueError as e:
            raise Conflict(str(e)) from None
        target = "upheld" if uphold else "rejected"
        try:
            moved = conn.execute(
                "UPDATE plt01.bkg_appeals SET state = %s, decided_at = %s,"
                " decided_by = %s, decided_by_person_id = %s, decision_note = %s,"
                " decide_correlation_id = %s"
                " WHERE appeal_id = %s AND state = 'open'",
                (target, moment, actor_id, decider_person_id, note.strip(),
                 correlation_id, appeal_id),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if moved == 0:
            raise Conflict("this_appeal_was_decided_by_somebody_else")
        # **The remedy follows what the appeal is against.** The first version overturned the
        # record whenever an appeal was upheld and a no-show was cited, whatever `against`
        # said -- so waiving a fee also stopped the miss counting, and the member's next one
        # was their "first" again under the strike policy. Inverted in the other direction
        # too: a decider lifting a strike was told nothing about the fee because there was
        # nothing to tell. Found by review.
        overturned = False
        if uphold and against in appeals.SANCTION_APPEALS and row[3] is not None:
            overturned = bool(conn.execute(
                "UPDATE plt01.bkg_no_shows SET overturned_at = %s, overturned_by = %s,"
                " overturn_appeal_id = %s"
                " WHERE no_show_id = %s AND overturned_at IS NULL",
                (moment, actor_id, appeal_id, str(row[3])),
            ).rowcount)
        _append(conn, tenant_id, "appeal.decided", "appeal", appeal_id,
                {"appeal_id": appeal_id, "subject_person_id": appeal.subject_person_id,
                 "against": against, "state": target, "overturned": overturned},
                actor_id=actor_id, correlation_id=correlation_id)
    money = against in appeals.MONEY_APPEALS
    return {"appeal_id": appeal_id, "state": target, "against": against,
            "overturned": overturned,
            "decided_by_person_id": decider_person_id,
            "fee_reversed": False,
            "note": (
                "an upheld appeal against a warning or a strike stops the record counting "
                "against the member, which is what this module can do"
                if not money else
                "this appeal is about money, so nothing here reverses it: the decision is "
                "the evidence the module that charged it acts on, and no credit has been "
                "issued")}


# ------------------------------------------------------------------ reads

def booking_detail(
    pool: Pool, tenant_id: str, booking_id: str, *, may_read_reasons: bool,
    reader_person_id: str | None,
) -> dict[str, Any]:
    """One booking with its session, its consequence and what the member said.

    **The cancellation's reason and an appeal's grounds are prose the member wrote**, so they
    are masked unless the caller is staff or is the member themselves. MOD-019's finding: a
    reason column is where a health fact goes in practice -- "I cannot come, I am having
    treatment on Tuesdays" is the ordinary content of a cancellation note.

    **Both arguments are required**, MOD-014's lesson about `Decision.mask`: a read that can
    be called without the masking decision is a read somebody calls without it, and mypy is
    what stops the next one. `may_read_reasons` is the staff half; `reader_person_id` is the
    member's own, because a member reading back what they themselves typed is not a
    disclosure.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT b.session_id, b.person_id, b.hold_id, b.policy_id, b.state,"
            " b.source_kind, b.entitlement_grant_id, b.checked_in_at, b.checkin_source,"
            " b.settled_at, b.cancelled_at, b.booked_at, s.starts_at, s.ends_at,"
            " s.local_date, s.timezone, s.status"
            " FROM plt01.bkg_bookings b"
            " JOIN plt01.sch_sessions s ON s.session_id = b.session_id"
            " WHERE b.booking_id = %s",
            (booking_id,),
        ).fetchone()
        if row is None:
            raise NotFound("booking_not_found")
        # A member reading back what they typed themselves is not a disclosure, which is
        # why this takes who is asking as well as what they hold.
        if reader_person_id is not None and reader_person_id == str(row[1]):
            may_read_reasons = True
        cancellation = conn.execute(
            "SELECT occasion, policy_hours, hours_given, fee_due, credit_forfeit,"
            " reason, cancelled_at"
            " FROM plt01.bkg_cancellations WHERE booking_id = %s",
            (booking_id,),
        ).fetchone()
        no_show = conn.execute(
            "SELECT no_show_id, sanction, no_show_count, fee_due, credit_forfeit,"
            " overturned_at"
            " FROM plt01.bkg_no_shows WHERE booking_id = %s",
            (booking_id,),
        ).fetchone()
        intents = conn.execute(
            "SELECT intent, source, declared_at FROM plt01.bkg_attendance_intents"
            " WHERE booking_id = %s ORDER BY declared_at DESC",
            (booking_id,),
        ).fetchall()
    return {
        "booking_id": booking_id, "session_id": str(row[0]),
        "person_id": str(row[1]), "hold_id": str(row[2]),
        "policy_id": str(row[3]), "state": str(row[4]),
        "source_kind": str(row[5]),
        "entitlement_grant_id": None if row[6] is None else str(row[6]),
        "checked_in_at": row[7].isoformat() if row[7] else None,
        "checkin_source": str(row[8]) if row[8] else None,
        "settled_at": row[9].isoformat() if row[9] else None,
        "cancelled_at": row[10].isoformat() if row[10] else None,
        "booked_at": row[11].isoformat(),
        "session": {"starts_at": row[12].isoformat(), "ends_at": row[13].isoformat(),
                    "local_date": row[14].isoformat(), "timezone": str(row[15]),
                    "status": str(row[16])},
        "cancellation": None if cancellation is None else {
            "occasion": str(cancellation[0]), "policy_hours": int(cancellation[1]),
            "hours_given": int(cancellation[2]), "fee_due": bool(cancellation[3]),
            "credit_forfeit": bool(cancellation[4]),
            "reason": str(cancellation[5]) if may_read_reasons else None,
            "reason_masked": not may_read_reasons,
            "cancelled_at": cancellation[6].isoformat()},
        "no_show": None if no_show is None else {
            "no_show_id": str(no_show[0]), "sanction": str(no_show[1]),
            "no_show_count": int(no_show[2]), "fee_due": bool(no_show[3]),
            "credit_forfeit": bool(no_show[4]),
            "overturned_at": no_show[5].isoformat() if no_show[5] else None},
        #: Newest first, because the latest is the current intent and the rest are the history
        #: that distinguishes a member who always answers from one who never does.
        "intents": [{"intent": str(i[0]), "source": str(i[1]),
                     "declared_at": i[2].isoformat()} for i in intents],
    }


def _grace_only(minutes: int) -> policy.Policy:
    """A `Policy` carrying one real figure, for `checkin_window`.

    **It reads `checkin_grace_minutes` and nothing else**, and takes a `Policy` because
    `check_policy` validates the whole thing before it answers. Building one with the rest at
    their smallest legal values is the honest way to ask it a question about the grace --
    cheaper than widening its signature, and it keeps the window in one function rather than
    inlining the arithmetic at a second call site.
    """
    return policy.Policy(
        cancellation_hours=0, max_concurrent=1, quota=None,
        quota_period="rolling_7_days", checkin_grace_minutes=minutes,
        warn_after_no_shows=1, strike_after_no_shows=1,
        priority_rule="first_come", offer_minutes=1)


def session_roster(
    pool: Pool, tenant_id: str, session_id: str, *, include_settled: bool = False,
) -> dict[str, Any]:
    """Who is booked on a session, and who is waiting. For a coach and a front desk.

    **The counts are sums over the rows**, and the places come from MOD-019's session: there is
    no roster table and no cached total, for the reason this module has no capacity of its own.

    **No name, because this module holds none.** Every row is a `person_id` and MOD-014 owns
    who that is, masked through its own gate -- so a surface composes the two, which is what
    the Member 360 and the staff list already do. A join here would be the cross-domain read
    paragraph 1300 bars, and it would hand a `booking.booking.read` holder a lateral path
    around `people.person.read`.
    """
    with tenant_scope(pool, tenant_id) as conn:
        session = _session(conn, session_id)
        bookings = conn.execute(
            "SELECT b.booking_id, b.person_id, b.state, b.source_kind, b.checked_in_at,"
            "       b.booked_at, p.checkin_grace_minutes"
            "  FROM plt01.bkg_bookings b"
            "  JOIN plt01.bkg_policies p ON p.policy_id = b.policy_id"
            " WHERE b.session_id = %s"
            "   AND (%s OR b.state IN ('booked', 'attended'))"
            " ORDER BY b.booked_at",
            (session_id, include_settled),
        ).fetchall()
        entries = conn.execute(
            "SELECT entry_id, person_id, state, tier, joined_at, offer_expires_at"
            " FROM plt01.bkg_waitlist_entries WHERE session_id = %s"
            "   AND state IN ('waiting', 'offered', 'expired')"
            " ORDER BY tier, joined_at, entry_id",
            (session_id,),
        ).fetchall()
        held = conn.execute(
            "SELECT coalesce(sum(places), 0) FROM plt01.sch_capacity_holds"
            " WHERE session_id = %s AND status IN ('held', 'attended')",
            (session_id,),
        ).fetchone()
        # **One query for everybody on the roster, not one per person.** FD-06 draws it --
        # "Hala's two prior no-shows are shown without judgement, it is context for the coach,
        # not a flag on her" -- and a front desk reading eighteen rows is eighteen round
        # trips if each one asks separately, which is the problem `/authz/checks` exists for
        # one module over. The count is `_no_show_count`'s own predicate rather than a second
        # one: a sum over the rows, excluding what an appeal overturned.
        people = sorted({str(b[1]) for b in bookings})
        prior = dict(conn.execute(
            "SELECT person_id, count(*) FROM plt01.bkg_no_shows"
            " WHERE person_id = ANY(%s) AND overturned_at IS NULL"
            " GROUP BY person_id",
            (people,),
        ).fetchall()) if people else {}
    # The window per booking, from each one's own snapshotted grace: two members on one
    # class can hold different policy versions, because a booking snapshots the terms it was
    # made under and retiring a policy changes nothing about the last sale.
    windows = {
        str(b[0]): attendance.checkin_window(
            session["starts_at"], policy=_grace_only(int(b[6])))
        for b in bookings
    }
    places = session["capacity"] + session["overbook_places"]
    taken = int(held[0]) if held else 0
    return {
        "session_id": session_id, "status": session["status"],
        "starts_at": session["starts_at"].isoformat(),
        "capacity": session["capacity"],
        "overbook_places": session["overbook_places"], "places": places,
        "held": taken, "free": max(0, places - taken),
        "bookings": [
            {"booking_id": str(b[0]), "person_id": str(b[1]), "state": str(b[2]),
             "source_kind": str(b[3]),
             "checked_in_at": b[4].isoformat() if b[4] else None,
             "booked_at": b[5].isoformat(),
             #: **When this booking may be checked in**, from the window the write itself
             #: reads. FD-06 offers a Check in button and `may_check_in` refuses outside it
             #: -- it opens an hour before the session and closes after that booking's own
             #: snapshotted grace -- so without this a desk is offered a control the module
             #: will refuse, which is this build's own "a button that answered 403 is worse
             #: than its absence". One computation, shared with the refusal, because a
             #: screen and a refusal that disagree is worse than either.
             "checkin_opens_at": windows[str(b[0])][0].isoformat(),
             "checkin_closes_at": windows[str(b[0])][1].isoformat(),
             "prior_no_shows": int(prior.get(b[1], 0))} for b in bookings],
        "waitlist": [
            {"entry_id": str(e[0]), "person_id": str(e[1]), "state": str(e[2]),
             "tier": int(e[3]), "joined_at": e[4].isoformat(),
             "position": n,
             "offer_expires_at": e[5].isoformat() if e[5] else None}
            for n, e in enumerate(entries, 1)],
    }


def member_bookings(
    pool: Pool, tenant_id: str, person_id: str, *, from_date: datetime | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """A member's own bookings, newest session first.

    **No reasons and no grounds**, whatever the caller holds: this is a list, and a surface that
    needs the prose reads one booking. That is the narrower disclosure by default rather than a
    permission check repeated per row.
    """
    bounded = max(1, min(limit, 500))
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT b.booking_id, b.session_id, b.state, b.source_kind,"
            " b.checked_in_at, s.starts_at, s.local_date, s.status"
            " FROM plt01.bkg_bookings b"
            " JOIN plt01.sch_sessions s ON s.session_id = b.session_id"
            " WHERE b.person_id = %s AND (%s::timestamptz IS NULL OR s.starts_at >= %s)"
            " ORDER BY s.starts_at DESC LIMIT %s",
            (person_id, from_date, from_date, bounded),
        ).fetchall()
        counts = conn.execute(
            "SELECT count(*) FILTER (WHERE overturned_at IS NULL) FROM plt01.bkg_no_shows"
            " WHERE person_id = %s",
            (person_id,),
        ).fetchone()
    return {
        "person_id": person_id, "count": len(rows),
        "no_shows_counting": int(counts[0]) if counts else 0,
        "bookings": [
            {"booking_id": str(r[0]), "session_id": str(r[1]), "state": str(r[2]),
             "source_kind": str(r[3]),
             "checked_in_at": r[4].isoformat() if r[4] else None,
             "starts_at": r[5].isoformat(), "local_date": r[6].isoformat(),
             "session_status": str(r[7])} for r in rows],
    }


def open_appeals(pool: Pool, tenant_id: str, *, limit: int = 100) -> dict[str, Any]:
    """The appeals waiting for a decision, oldest first.

    **The grounds are the member's own words and are returned here**, because the person
    deciding has to read them -- which is why the route charges the deciding permission rather
    than the routine read.
    """
    bounded = max(1, min(limit, 500))
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT appeal_id, subject_person_id, against, grounds, raised_at,"
            " no_show_id, cancellation_id"
            " FROM plt01.bkg_appeals WHERE state = 'open' ORDER BY raised_at LIMIT %s",
            (bounded,),
        ).fetchall()
    return {"count": len(rows), "appeals": [
        {"appeal_id": str(r[0]), "subject_person_id": str(r[1]), "against": str(r[2]),
         "grounds": str(r[3]), "raised_at": r[4].isoformat(),
         "no_show_id": None if r[5] is None else str(r[5]),
         "cancellation_id": None if r[6] is None else str(r[6])} for r in rows]}

"""MOD-019 OPS-01: the I/O, and the three things about it that are load-bearing.

**The timezone comes from the location, never from the caller.** Paragraph 4150 makes it
location-specific, and a caller able to send one could schedule an 18:00 class in a zone the
site is not in -- which would read correctly in the admin screen and be an hour wrong on every
member's phone. `_location` is the only place it is read, and it is read inside the transaction
that writes the session.

**A session snapshots everything that describes it.** The rule version it was generated from,
the capacity it was published with, the resources it holds and the window they are held for.
Paragraph 4149 is the reason: "historical instances remain stable after template edits". A
service that joined through the template to the *current* rule would rewrite what last month's
class had been every time somebody fixed next month's.

**A conflict refusal and a conflict override are different acts with different permissions.**
Paragraph 1842: "Resource conflicts cannot be overridden without permission and reason." So
`generate_sessions` refuses and says what clashed; publishing over it needs
`scheduling.conflict.override` and a written reason, and the override is a row. A boolean on the
request body would be the shape every review in this build has found.

**A refusal that leaves evidence is raised after the commit.** `tenant_scope` rolls back when
the block raises, so a path that records a conflict detection and then refuses would throw its
own evidence away. The `_settled` shape is MOD-007's, and it is used here wherever a refusal has
a row behind it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from psycopg import Connection, errors

from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events
from app.scheduling import (
    availability,
    capacity,
    conflicts,
    publishing,
    recurrence,
    resources,
    substitution,
)
from app.scheduling.recurrence import ScheduleError


def _now() -> datetime:
    return datetime.now(UTC)


def _today() -> date:
    return _now().date()


def _check_name(error: errors.CheckViolation) -> str:
    name = getattr(error.diag, "constraint_name", None)
    return str(name) if name else "constraint_violation"


def _fk_subject(error: errors.ForeignKeyViolation) -> str:
    """Which parent a foreign-key violation was about, as a caller-readable name."""
    detail = str(getattr(error.diag, "message_detail", "") or "")
    for table, subject in (
        ("sch_resources", "scheduling_resource_not_found"),
        ("sch_templates", "schedule_template_not_found"),
        ("sch_recurrence_rules", "recurrence_rule_not_found"),
        ("sch_capacity_policies", "capacity_policy_not_found"),
        ("sch_sessions", "session_not_found"),
        ("locations", "location_not_found"),
        ("brands", "brand_not_found"),
        ("ppl_persons", "person_not_found"),
    ):
        if table in detail:
            return subject
    return "a_referenced_row_does_not_exist"


def _append(
    conn: Connection[Any], tenant_id: str, name: str, aggregate_type: str,
    aggregate_id: str, payload: dict[str, Any], *, correlation_id: str, actor_id: str,
) -> None:
    """Publish one event in the caller's transaction.

    On this connection, which is MOD-010's whole argument: a session that exists with no
    `session.created` is a schedule a consumer never learns about, and an event for a session
    the transaction rolled back is one for a class that does not exist.
    """
    events.append_event(
        conn, tenant_id, event_type=name, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, payload=payload, correlation_id=correlation_id,
        actor_id=actor_id)


def _location(conn: Connection[Any], location_id: str) -> dict[str, Any]:
    """A location's brand and timezone, from the table that owns them.

    **The timezone is read here and never taken from a caller.** Paragraph 4150 makes it
    location-specific; a caller-supplied one would schedule a class in a zone the site is not
    in, which reads correctly in an admin screen and is an hour wrong on every member's phone.
    """
    row = conn.execute(
        "SELECT brand_id, timezone, location_name FROM plt01.locations"
        " WHERE location_id = %s",
        (location_id,),
    ).fetchone()
    if row is None:
        raise NotFound("location_not_found")
    return {"brand_id": str(row[0]), "timezone": str(row[1]),
            "location_name": str(row[2])}


# ------------------------------------------------------------------ resources

def create_resource(
    pool: Pool, tenant_id: str, *, resource_code: str, resource_kind: str,
    display_name: str, actor_id: str, correlation_id: str, quantity: int = 1,
    location_id: str | None = None, person_id: str | None = None,
) -> dict[str, Any]:
    """CreateResource. OPS-01-R01.

    **The brand is derived from the location**, which is MOD-008's "derive a scope, never accept
    one" applied here: a caller sending both could put a location-scoped resource under a brand
    that does not own it, and a brand-scoped reader would then see a resource at a site outside
    their scope -- or miss one inside it.
    """
    try:
        resources.check_resource(resources.Resource(
            resource_id="pending", kind=resource_kind, quantity=quantity,
            location_id=location_id))
    except recurrence.ScheduleError as e:
        raise InvalidRequest(str(e)) from None
    if not display_name.strip():
        raise InvalidRequest("a_resource_has_a_name")
    with tenant_scope(pool, tenant_id) as conn:
        brand_id = None
        if location_id is not None:
            brand_id = _location(conn, location_id)["brand_id"]
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.sch_resources
                    (tenant_id, resource_code, resource_kind, display_name, brand_id,
                     location_id, quantity, person_id, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING resource_id
                """,
                (tenant_id, resource_code.upper(), resource_kind, display_name.strip(),
                 brand_id, location_id, quantity, person_id, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_resource_code_already_exists") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"resource_id": str(row[0]), "resource_code": resource_code.upper(),
            "resource_kind": resource_kind, "quantity": quantity,
            "location_id": location_id, "brand_id": brand_id, "status": "active"}


def retire_resource(
    pool: Pool, tenant_id: str, resource_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Withdraw a resource. Retired rather than deleted, for MOD-018's reason.

    **Scheduled sessions that hold it are listed rather than cancelled.** Retiring the only
    studio takes every class in it off the schedule, and doing that silently is the worst
    answer available: the sessions are reported and cancelling them is a separate decision
    somebody makes with the list in front of them.
    """
    moment = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status, resource_code FROM plt01.sch_resources WHERE resource_id = %s"
            " FOR UPDATE",
            (resource_id,),
        ).fetchone()
        if row is None:
            raise NotFound("scheduling_resource_not_found")
        if str(row[0]) == "retired":
            return {"resource_id": resource_id, "status": "retired", "repeated": True,
                    "affected_sessions": []}
        affected = conn.execute(
            "SELECT r.session_id, s.starts_at FROM plt01.sch_session_resources r"
            " JOIN plt01.sch_sessions s ON s.session_id = r.session_id"
            " WHERE r.resource_id = %s AND s.status = 'scheduled' AND s.starts_at >= %s"
            " ORDER BY s.starts_at LIMIT 200",
            (resource_id, moment),
        ).fetchall()
        conn.execute(
            "UPDATE plt01.sch_resources SET status = 'retired', retired_at = %s,"
            " retired_by = %s, retire_correlation_id = %s"
            " WHERE resource_id = %s AND status = 'active'",
            (moment, actor_id, correlation_id, resource_id))
    return {"resource_id": resource_id, "status": "retired", "repeated": False,
            "affected_sessions": [
                {"session_id": str(a[0]), "starts_at": a[1].isoformat()} for a in affected],
            "affected_count": len(affected)}


def set_availability(
    pool: Pool, tenant_id: str, *, resource_id: str, window_kind: str,
    starts_at: time, ends_at: time, actor_id: str, correlation_id: str,
    weekday: int | None = None, on_date: date | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """SetAvailability. OPS-01-R03.

    **The timezone comes from the resource's location**, for `_location`'s reason: a rota is
    written in local time, and one written in a zone the site is not in would move everybody's
    shift. A resource with no location takes the location of nothing, so it has no rota --
    which is correct for `equipment` and refused here for `staff`.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT location_id, resource_kind, status FROM plt01.sch_resources"
            " WHERE resource_id = %s",
            (resource_id,),
        ).fetchone()
        if row is None:
            raise NotFound("scheduling_resource_not_found")
        if str(row[2]) != "active":
            raise Conflict("this_resource_is_retired")
        if row[0] is None:
            raise Conflict(
                "a rota is local to a site and this resource is not at one; give it a "
                "location first")
        zone = _location(conn, str(row[0]))["timezone"]
        try:
            availability.check_window(availability.Window(
                kind=window_kind, timezone=zone, starts_at=starts_at, ends_at=ends_at,
                weekday=weekday, on_date=on_date))
        except recurrence.ScheduleError as e:
            raise InvalidRequest(str(e)) from None
        try:
            created = conn.execute(
                """
                INSERT INTO plt01.sch_availability_windows
                    (tenant_id, resource_id, window_kind, timezone, starts_at, ends_at,
                     weekday, on_date, reason, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING window_id
                """,
                (tenant_id, resource_id, window_kind, zone, starts_at, ends_at, weekday,
                 on_date, (reason or "").strip() or None, actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert created is not None
    return {"window_id": str(created[0]), "resource_id": resource_id,
            "window_kind": window_kind, "timezone": zone}


def _windows(conn: Connection[Any], resource_id: str) -> list[availability.Window]:
    """A resource's availability windows, as the decisions need them."""
    rows = conn.execute(
        "SELECT window_kind, timezone, starts_at, ends_at, weekday, on_date"
        " FROM plt01.sch_availability_windows WHERE resource_id = %s",
        (resource_id,),
    ).fetchall()
    return [availability.Window(
        kind=str(r[0]), timezone=str(r[1]), starts_at=r[2], ends_at=r[3],
        weekday=int(r[4]) if r[4] is not None else None, on_date=r[5]) for r in rows]


# ------------------------------------------------------------------ templates and rules

def draft_template(
    pool: Pool, tenant_id: str, *, template_code: str, display_name: str,
    service_resource_id: str, location_id: str, rule: dict[str, Any],
    policy: dict[str, Any], requirements: list[dict[str, Any]],
    restrictions: list[dict[str, Any]], actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Draft a schedule template with its first rule and policy. OPS-01-R02 and R04.

    **Drafting and publishing are two acts.** MOD-017's review found a contract version written
    and published in one command, which makes the author and the publisher the same person by
    definition -- and a schedule is what members plan their week around. So this writes a draft
    that generates nothing, and `publish_template` is a separate command with its own
    permission.

    The rule and the policy are validated by the decision functions before anything is written,
    because a draft that cannot generate is a draft somebody will try to publish.
    """
    if not display_name.strip():
        raise InvalidRequest("a_template_has_a_name")
    parsed_requirements = _parse_requirements(requirements)
    parsed_restrictions = _parse_restrictions(restrictions)
    with tenant_scope(pool, tenant_id) as conn:
        where = _location(conn, location_id)
        parsed_rule = _parse_rule(rule, timezone=where["timezone"])
        parsed_policy = _parse_policy(policy)
        # **Walked before anything is written, because that is what validating a rule means.**
        # This ran after the block, and the block had committed -- so a rule the generator
        # cannot walk (a mistyped year, which `check_rule` now refuses outright) answered 500
        # with the draft, its rule, its policy and its requirements all committed.
        # `sch_templates` has a unique index on the code, no DELETE grant for any runtime role,
        # and `retire_template` refuses a draft, so one typo took that template code for ever
        # and every later publish of the row was another 500. The docstring above already
        # claimed the validation happened before the write; it did not. Found by review.
        try:
            generates = recurrence.occurrence_count(parsed_rule)
        except recurrence.ScheduleError as e:
            raise InvalidRequest(str(e)) from None
        try:
            created = conn.execute(
                """
                INSERT INTO plt01.sch_templates
                    (tenant_id, template_code, display_name, service_resource_id,
                     location_id, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING template_id
                """,
                (tenant_id, template_code.upper(), display_name.strip(),
                 service_resource_id, location_id, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_template_code_already_exists") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert created is not None
        template_id = str(created[0])
        rule_id = _insert_rule(
            conn, tenant_id, template_id=template_id, version=1, rule=parsed_rule,
            effective_from=parsed_rule.starts_on, actor_id=actor_id,
            correlation_id=correlation_id)
        policy_id = _insert_policy(
            conn, tenant_id, template_id=template_id, version=1, policy=parsed_policy,
            restrictions=parsed_restrictions, actor_id=actor_id,
            correlation_id=correlation_id)
        _insert_requirements(
            conn, tenant_id, template_id=template_id, requirements=parsed_requirements,
            actor_id=actor_id, correlation_id=correlation_id)
    return {"template_id": template_id, "template_code": template_code.upper(),
            "status": "draft", "rule_id": rule_id, "policy_id": policy_id,
            "version": 1, "timezone": where["timezone"],
            "would_generate": generates}


def _parse_rule(rule: dict[str, Any], *, timezone: str) -> recurrence.Rule:
    """A request's recurrence as the decision functions take it.

    **The timezone is the location's and is never read from the request.** It is a parameter
    here rather than a key in `rule` so a caller cannot send one at all.
    """
    try:
        parsed = recurrence.Rule(
            frequency=str(rule["frequency"]),
            local_time=time.fromisoformat(str(rule["local_time"])),
            timezone=timezone,
            duration_minutes=int(rule["duration_minutes"]),
            starts_on=date.fromisoformat(str(rule["starts_on"])),
            until=date.fromisoformat(str(rule["until"])),
            weekdays=tuple(int(d) for d in rule.get("weekdays", ())),
            week_of_month=(int(rule["week_of_month"])
                           if rule.get("week_of_month") is not None else None),
            excluded_dates=tuple(
                date.fromisoformat(str(d)) for d in rule.get("excluded_dates", ())))
    except (KeyError, TypeError, ValueError) as e:
        raise InvalidRequest(str(e) or "a_recurrence_rule_is_malformed") from None
    try:
        recurrence.check_rule(parsed)
    except recurrence.ScheduleError as e:
        raise InvalidRequest(str(e)) from None
    return parsed


def _parse_policy(policy: dict[str, Any]) -> capacity.Policy:
    try:
        parsed = capacity.Policy(
            capacity=int(policy["capacity"]),
            setup_minutes=int(policy.get("setup_minutes", 0)),
            cleanup_minutes=int(policy.get("cleanup_minutes", 0)),
            waitlist_capacity=int(policy.get("waitlist_capacity", 0)),
            overbook_places=int(policy.get("overbook_places", 0)))
    except (KeyError, TypeError, ValueError) as e:
        raise InvalidRequest(str(e) or "a_capacity_policy_is_malformed") from None
    try:
        capacity.check_policy(parsed)
    except recurrence.ScheduleError as e:
        raise InvalidRequest(str(e)) from None
    return parsed


def _parse_requirements(raw: list[dict[str, Any]]) -> list[resources.Requirement]:
    parsed = []
    for item in raw:
        try:
            parsed.append(resources.Requirement(
                kind=str(item["kind"]),
                quantity=int(item.get("quantity", 1)),
                resource_id=(str(item["resource_id"])
                             if item.get("resource_id") is not None else None)))
        except (KeyError, TypeError, ValueError) as e:
            raise InvalidRequest(str(e) or "a_requirement_is_malformed") from None
    try:
        resources.check_requirements(parsed)
    except recurrence.ScheduleError as e:
        raise InvalidRequest(str(e)) from None
    return parsed


def _parse_restrictions(raw: list[dict[str, Any]]) -> list[capacity.Restriction]:
    parsed = []
    for item in raw:
        try:
            parsed.append(capacity.Restriction(
                kind=str(item["kind"]), value=str(item["value"])))
        except (KeyError, TypeError) as e:
            raise InvalidRequest(str(e) or "a_restriction_is_malformed") from None
    for restriction in parsed:
        try:
            capacity.check_restriction(restriction)
        except recurrence.ScheduleError as e:
            raise InvalidRequest(str(e)) from None
    return parsed


def _insert_rule(
    conn: Connection[Any], tenant_id: str, *, template_id: str, version: int,
    rule: recurrence.Rule, effective_from: date, actor_id: str, correlation_id: str,
) -> str:
    try:
        row = conn.execute(
            """
            INSERT INTO plt01.sch_recurrence_rules
                (tenant_id, template_id, version, frequency, local_time, timezone,
                 duration_minutes, starts_on, until_date, weekdays, week_of_month,
                 excluded_dates, effective_from, created_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING rule_id
            """,
            (tenant_id, template_id, version, rule.frequency, rule.local_time,
             rule.timezone, rule.duration_minutes, rule.starts_on, rule.until,
             list(rule.weekdays), rule.week_of_month, list(rule.excluded_dates),
             effective_from, actor_id, correlation_id),
        ).fetchone()
    except errors.UniqueViolation:
        raise Conflict("this_template_already_has_that_rule_version") from None
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return str(row[0])


def _insert_policy(
    conn: Connection[Any], tenant_id: str, *, template_id: str, version: int,
    policy: capacity.Policy, restrictions: list[capacity.Restriction], actor_id: str,
    correlation_id: str,
) -> str:
    try:
        row = conn.execute(
            """
            INSERT INTO plt01.sch_capacity_policies
                (tenant_id, template_id, version, capacity, setup_minutes,
                 cleanup_minutes, waitlist_capacity, overbook_places, created_by,
                 correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING policy_id
            """,
            (tenant_id, template_id, version, policy.capacity, policy.setup_minutes,
             policy.cleanup_minutes, policy.waitlist_capacity, policy.overbook_places,
             actor_id, correlation_id),
        ).fetchone()
    except errors.UniqueViolation:
        raise Conflict("this_template_already_has_that_policy_version") from None
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    policy_id = str(row[0])
    for restriction in restrictions:
        try:
            conn.execute(
                """
                INSERT INTO plt01.sch_restrictions
                    (tenant_id, policy_id, restriction_kind, restriction_value,
                     created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, policy_id, restriction.kind, restriction.value, actor_id,
                 correlation_id))
        except errors.UniqueViolation:
            raise Conflict("this_restriction_is_already_on_the_policy") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    return policy_id


def _insert_requirements(
    conn: Connection[Any], tenant_id: str, *, template_id: str,
    requirements: list[resources.Requirement], actor_id: str, correlation_id: str,
) -> None:
    """A template's requirements, stored against the template rather than the rule.

    **On the template, because they are what the session needs rather than when it runs.** A
    rule version is a change of time; a requirement change is a change of what the class is,
    and the session snapshots the expansion either way -- so the two do not have to be versioned
    together.
    """
    for requirement in requirements:
        try:
            conn.execute(
                """
                INSERT INTO plt01.sch_template_requirements
                    (tenant_id, template_id, requirement_kind, quantity, resource_id,
                     created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, template_id, requirement.kind, requirement.quantity,
                 requirement.resource_id, actor_id, correlation_id))
        except errors.UniqueViolation:
            raise Conflict("this_requirement_is_already_on_the_template") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None


def _template(conn: Connection[Any], template_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT template_code, display_name, service_resource_id, location_id, status,"
        " live_rule_id FROM plt01.sch_templates WHERE template_id = %s FOR UPDATE",
        (template_id,),
    ).fetchone()
    if row is None:
        raise NotFound("schedule_template_not_found")
    return {"template_code": str(row[0]), "display_name": str(row[1]),
            "service_resource_id": str(row[2]), "location_id": str(row[3]),
            "status": str(row[4]),
            "live_rule_id": str(row[5]) if row[5] else None}


def _rule_row(conn: Connection[Any], rule_id: str) -> recurrence.Rule:
    row = conn.execute(
        "SELECT frequency, local_time, timezone, duration_minutes, starts_on,"
        " until_date, weekdays, week_of_month, excluded_dates"
        " FROM plt01.sch_recurrence_rules WHERE rule_id = %s",
        (rule_id,),
    ).fetchone()
    if row is None:
        raise NotFound("recurrence_rule_not_found")
    return recurrence.Rule(
        frequency=str(row[0]), local_time=row[1], timezone=str(row[2]),
        duration_minutes=int(row[3]), starts_on=row[4], until=row[5],
        weekdays=tuple(int(d) for d in (row[6] or ())),
        week_of_month=int(row[7]) if row[7] is not None else None,
        excluded_dates=tuple(row[8] or ()))


def _latest_versions(conn: Connection[Any], template_id: str) -> tuple[int, int]:
    """The highest rule and policy version a template has, for the next one."""
    row = conn.execute(
        "SELECT coalesce(max(version), 0) FROM plt01.sch_recurrence_rules"
        " WHERE template_id = %s",
        (template_id,),
    ).fetchone()
    rules = int(row[0]) if row else 0
    row = conn.execute(
        "SELECT coalesce(max(version), 0) FROM plt01.sch_capacity_policies"
        " WHERE template_id = %s",
        (template_id,),
    ).fetchone()
    return rules, (int(row[0]) if row else 0)


def _live_policy(conn: Connection[Any], template_id: str) -> dict[str, Any]:
    """The template's newest capacity policy, which a session snapshots."""
    row = conn.execute(
        "SELECT policy_id, capacity, setup_minutes, cleanup_minutes, waitlist_capacity,"
        " overbook_places, opens_hours_before, closes_minutes_before"
        " FROM plt01.sch_capacity_policies WHERE template_id = %s"
        " ORDER BY version DESC LIMIT 1",
        (template_id,),
    ).fetchone()
    if row is None:
        raise NotFound("capacity_policy_not_found")
    return {
        "policy_id": str(row[0]),
        "policy": capacity.Policy(
            capacity=int(row[1]), setup_minutes=int(row[2]), cleanup_minutes=int(row[3]),
            waitlist_capacity=int(row[4]), overbook_places=int(row[5])),
        "opens_hours_before": int(row[6]), "closes_minutes_before": int(row[7]),
    }


def _template_requirements(
    conn: Connection[Any], template_id: str,
) -> list[resources.Requirement]:
    rows = conn.execute(
        "SELECT requirement_kind, quantity, resource_id"
        " FROM plt01.sch_template_requirements WHERE template_id = %s"
        " ORDER BY requirement_kind",
        (template_id,),
    ).fetchall()
    return [resources.Requirement(
        kind=str(r[0]), quantity=int(r[1]),
        resource_id=str(r[2]) if r[2] else None) for r in rows]


def _resource_chart(conn: Connection[Any]) -> dict[str, resources.Resource]:
    """Every active resource, as the conflict detector needs them.

    Active only: a retired studio cannot satisfy a requirement, and including it would let the
    detector find a free room that does not exist any more.
    """
    rows = conn.execute(
        "SELECT resource_id, resource_kind, quantity, location_id"
        " FROM plt01.sch_resources WHERE status = 'active'",
    ).fetchall()
    return {str(r[0]): resources.Resource(
        resource_id=str(r[0]), kind=str(r[1]), quantity=int(r[2]),
        location_id=str(r[3]) if r[3] else None) for r in rows}


def _held_over(
    conn: Connection[Any], *, holds_from: datetime, holds_until: datetime,
) -> list[conflicts.Held]:
    """What is already held over a window, from the sessions that hold it.

    **Only `scheduled` sessions hold anything, and only holds that still apply.** A cancelled
    class does not occupy its studio, and counting it would make the room unbookable for the
    hour nobody is using it. A superseded hold is the same argument one row down: a coach who
    was substituted out is not teaching, and leaving them held made them unschedulable
    everywhere else at that time.
    """
    rows = conn.execute(
        "SELECT r.resource_id, r.resource_kind, r.quantity, r.holds_from, r.holds_until,"
        " r.session_id, t.display_name"
        " FROM plt01.sch_session_resources r"
        " JOIN plt01.sch_sessions s ON s.session_id = r.session_id"
        " JOIN plt01.sch_templates t ON t.template_id = s.template_id"
        " WHERE s.status = 'scheduled' AND r.superseded_at IS NULL"
        "   AND r.holds_from < %s AND %s < r.holds_until",
        (holds_until, holds_from),
    ).fetchall()
    return [conflicts.Held(
        resource_id=str(r[0]), kind=str(r[1]), quantity=int(r[2]),
        placement=availability.Placement(starts_at=r[3], ends_at=r[4]),
        session_id=str(r[5]), session_label=str(r[6])) for r in rows]


def _assign(
    requirement: resources.Requirement, chart: dict[str, resources.Resource],
    held: list[conflicts.Held], window: availability.Placement,
) -> list[tuple[str, str, int]]:
    """Which resources satisfy a requirement, as (resource_id, kind, quantity).

    **The assignment is the service's choice and it is deterministic.** A requirement for "a
    room" is satisfied by whichever is free, and taking them in code order rather than in the
    planner's means two identical publishes assign the same room -- which is what makes a
    re-run of a generation produce the same schedule.
    """
    if requirement.resource_id is not None:
        return [(requirement.resource_id, requirement.kind, requirement.quantity)]
    # **Only resources at this session's site, or ones tied to no site.** The candidate list
    # was the whole chart, so a class at one location was auto-assigned a studio and an
    # instructor at another -- and `conflicts.detect` did not compare locations either, so
    # nothing objected. The room was then genuinely held, which refused it to the real class at
    # the site that owns it. A resource with no location travels: a service format and a coach
    # with no base are not tied to a building.
    candidates = sorted(
        (r for r in chart.values()
         if r.kind == requirement.kind
         and (window.location_id is None or r.location_id is None
              or r.location_id == window.location_id)),
        key=lambda r: r.resource_id)
    if resources.is_exclusive(requirement.kind):
        busy = {h.resource_id for h in held
                if h.kind == requirement.kind and conflicts.overlaps(h.placement, window)}
        free = [r for r in candidates if r.resource_id not in busy]
        return [(r.resource_id, r.kind, 1) for r in free[:requirement.quantity]]
    # Countable: take from the first candidates until the requirement is met.
    out: list[tuple[str, str, int]] = []
    wanted = requirement.quantity
    for resource in candidates:
        if wanted <= 0:
            break
        taken = sum(h.quantity for h in held
                    if h.resource_id == resource.resource_id
                    and conflicts.overlaps(h.placement, window))
        spare = max(0, resource.quantity - taken)
        if spare:
            take = min(spare, wanted)
            out.append((resource.resource_id, resource.kind, take))
            wanted -= take
    return out


# ------------------------------------------------------------------ publishing and generating

def preview_publish(
    pool: Pool, tenant_id: str, template_id: str, *, rule: dict[str, Any] | None = None,
    effective_from: date | None = None,
) -> dict[str, Any]:
    """What publishing would do, before anything is written. Paragraph 1841.

    **"All schedule changes are effective-dated and impact-assessed before publication."** The
    assessment has to be computable without writing, or there is nothing to show a human -- so
    this is a read, it takes the proposed rule rather than storing one, and `publish_template`
    computes the same thing again from what it is about to write.
    """
    today = _today()
    with tenant_scope(pool, tenant_id) as conn:
        template = _template(conn, template_id)
        where = _location(conn, template["location_id"])
        proposed_rule = (_parse_rule(rule, timezone=where["timezone"]) if rule is not None
                         else (_rule_row(conn, template["live_rule_id"])
                               if template["live_rule_id"] else None))
        if proposed_rule is None:
            raise Conflict("this_template_has_no_rule_to_publish")
        starts = effective_from or proposed_rule.starts_on
        existing = _instances(conn, template_id)
        proposed = [
            publishing.Instance(
                session_id="proposed", starts_at=o.starts_at, ends_at=o.ends_at)
            for o in recurrence.generate(proposed_rule)]
        try:
            impact = publishing.assess(
                existing, proposed, effective_from=starts, today=today)
        except recurrence.ScheduleError as e:
            raise InvalidRequest(str(e)) from None
    return {
        "template_id": template_id, "effective_from": impact.effective_from.isoformat(),
        "unchanged": impact.unchanged, "moved": impact.moved,
        "cancelled": impact.cancelled, "added": impact.added,
        "places_affected": impact.places_affected,
        "first_affected_at": (impact.first_affected_at.isoformat()
                              if impact.first_affected_at else None),
        "needs_notification": publishing.needs_notification(impact),
        "summary": publishing.describe(impact),
    }


def _instances(
    conn: Connection[Any], template_id: str,
) -> list[publishing.Instance]:
    """A template's live sessions with the places held on each.

    **The held count is a sum over the hold rows**, not a column: there is no `held_count` on a
    session, for COM-04-R07's reason one module over.
    """
    rows = conn.execute(
        "SELECT s.session_id, s.starts_at, s.ends_at, s.local_date,"
        " coalesce((SELECT sum(h.places) FROM plt01.sch_capacity_holds h"
        "            WHERE h.session_id = s.session_id"
        "              AND h.status IN ('held', 'attended')), 0)"
        " FROM plt01.sch_sessions s"
        " WHERE s.template_id = %s AND s.status = 'scheduled'"
        # **A tiebreak, because two sessions can share an instant.** A template with two rule
        # versions generates the same Monday twice, and leaving the order to the planner made
        # the impact assessment answer differently on identical data.
        " ORDER BY s.starts_at, s.session_id",
        (template_id,),
    ).fetchall()
    return [publishing.Instance(
        session_id=str(r[0]), starts_at=r[1], ends_at=r[2], local_date=r[3],
        held=int(r[4])) for r in rows]


def publish_template(
    pool: Pool, tenant_id: str, template_id: str, *, actor_id: str,
    correlation_id: str, rule: dict[str, Any] | None = None,
    effective_from: date | None = None, acknowledged_impact: bool = False,
) -> dict[str, Any]:
    """PublishSchedule. OPS-01-R06, and the first half of paragraph 1841's Critical Control.

    **A change that affects a held place is refused until it is acknowledged.** The impact is
    computed here, from the rule about to be written, and a publish that would move or cancel a
    session somebody has booked needs `acknowledged_impact` -- which the route charges a
    stepped-up permission for. Publishing over members without a word is the failure the
    Critical Control names.

    **Drafting and publishing are two acts** and this is the second; a new rule version
    published on an already-live template is the third, which is how a schedule changes.
    """
    today = _today()
    with tenant_scope(pool, tenant_id) as conn:
        template = _template(conn, template_id)
        where = _location(conn, template["location_id"])
        rule_versions, _ = _latest_versions(conn, template_id)
        if rule is not None:
            parsed = _parse_rule(rule, timezone=where["timezone"])
            starts = effective_from or max(parsed.starts_on, today)
            try:
                publishing.check_effective_from(starts, today=today)
            except recurrence.ScheduleError as e:
                raise InvalidRequest(str(e)) from None
        else:
            if template["live_rule_id"] is None and rule_versions == 0:
                raise Conflict("this_template_has_no_rule_to_publish")
            rule_id = template["live_rule_id"] or _newest_rule(conn, template_id)
            parsed = _rule_row(conn, rule_id)
            starts = effective_from or max(parsed.starts_on, today)
        existing = _instances(conn, template_id)
        proposed = [
            publishing.Instance("proposed", o.starts_at, o.ends_at)
            for o in recurrence.generate(parsed)]
        impact = publishing.assess(existing, proposed, effective_from=starts, today=today)
        if publishing.needs_notification(impact) and not acknowledged_impact:
            raise Conflict(
                f"this change affects {impact.places_affected} held place(s): "
                f"{publishing.describe(impact)}. Acknowledge the impact to publish it")
        if template["status"] == "retired":
            raise Conflict("this_template_is_retired")
        if rule is not None:
            new_rule_id = _insert_rule(
                conn, tenant_id, template_id=template_id, version=rule_versions + 1,
                rule=parsed, effective_from=starts, actor_id=actor_id,
                correlation_id=correlation_id)
        else:
            new_rule_id = template["live_rule_id"] or _newest_rule(conn, template_id)
        moment = _now()
        try:
            if template["status"] == "draft":
                conn.execute(
                    "UPDATE plt01.sch_templates SET status = 'published',"
                    " live_rule_id = %s, published_at = %s, published_by = %s,"
                    " publish_correlation_id = %s"
                    " WHERE template_id = %s AND status = 'draft'",
                    (new_rule_id, moment, actor_id, correlation_id, template_id))
            else:
                conn.execute(
                    "UPDATE plt01.sch_templates SET live_rule_id = %s"
                    " WHERE template_id = %s AND status = 'published'",
                    (new_rule_id, template_id))
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        _append(conn, tenant_id, "schedule.published", "template", template_id,
                {"template_id": template_id, "rule_id": new_rule_id,
                 "effective_from": starts.isoformat(),
                 "sessions_moved": impact.moved, "sessions_cancelled": impact.cancelled,
                 "sessions_added": impact.added,
                 "places_affected": impact.places_affected},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"template_id": template_id, "status": "published", "rule_id": new_rule_id,
            "effective_from": starts.isoformat(),
            "impact": {"unchanged": impact.unchanged, "moved": impact.moved,
                       "cancelled": impact.cancelled, "added": impact.added,
                       "places_affected": impact.places_affected},
            "summary": publishing.describe(impact)}


def _newest_rule(conn: Connection[Any], template_id: str) -> str:
    row = conn.execute(
        "SELECT rule_id FROM plt01.sch_recurrence_rules WHERE template_id = %s"
        " ORDER BY version DESC LIMIT 1",
        (template_id,),
    ).fetchone()
    if row is None:
        raise NotFound("recurrence_rule_not_found")
    return str(row[0])


def retire_template(
    pool: Pool, tenant_id: str, template_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Stop a recurring schedule. **Generated sessions are left standing.**

    Paragraph 4149 again: the sessions already generated are what happened or what is about to,
    and retiring the template that made them must not remove them. Cancelling the future ones
    is a separate decision, made with the list this returns in front of you.

    **The correlation is written.** It was taken and dropped -- the column did not exist, while
    `sch_resources` has carried one from the start -- so stopping a recurring class left no
    handle anybody could follow back to the request. MOD-008 audits denials rather than allowed
    actions and `veyro_cp_app` holds nothing in `iam`, so this row is the only record there is.
    """
    if not reason.strip():
        raise InvalidRequest("retiring_a_schedule_states_why")
    moment = _now()
    with tenant_scope(pool, tenant_id) as conn:
        template = _template(conn, template_id)
        if template["status"] == "retired":
            return {"template_id": template_id, "status": "retired", "repeated": True,
                    "future_sessions": 0}
        if template["status"] != "published":
            raise Conflict("a_draft_schedule_is_not_retired_it_is_abandoned")
        future = conn.execute(
            "SELECT count(*) FROM plt01.sch_sessions WHERE template_id = %s"
            "   AND status = 'scheduled' AND starts_at >= %s",
            (template_id, moment),
        ).fetchone()
        try:
            conn.execute(
                "UPDATE plt01.sch_templates SET status = 'retired', retired_at = %s,"
                " retired_by = %s, retire_reason = %s, retire_correlation_id = %s"
                " WHERE template_id = %s AND status = 'published'",
                (moment, actor_id, reason.strip(), correlation_id, template_id))
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
    return {"template_id": template_id, "status": "retired", "repeated": False,
            "future_sessions": int(future[0]) if future else 0}


def generate_sessions(
    pool: Pool, tenant_id: str, template_id: str, *, actor_id: str,
    correlation_id: str, override_reason: str | None = None,
    from_date: date | None = None,
) -> dict[str, Any]:
    """CreateSession, in bulk from the live rule. OPS-01-R02 and R05.

    **Idempotent by the unique key on (rule, instant).** Generating twice is the ordinary case
    -- a publish that was retried, a worker that ran again -- and the second run produces
    nothing rather than a duplicate class.

    **A conflict refuses the whole generation unless it is overridden with a reason.** Paragraph
    1842's Critical Control. Refusing the whole run rather than skipping the clashing sessions
    is deliberate: a partial schedule is one an operator cannot tell from a complete one, and
    the sessions that *would* clash are exactly the ones they need to see.

    **`from_date` only moves the window forward.** A generation that reached back before the
    rule's own start would make sessions outside the schedule anybody published.
    """
    moment = _now()
    today = _today()
    settled: Exception | None = None
    created: list[dict[str, Any]] = []
    detected: list[conflicts.Conflict] = []
    #: The reason, decided once. An override is a different permission at the route, so a
    #: blank one is the same as none and the route charged the cheaper permission for it.
    written = (override_reason or "").strip()
    overridden = 0
    with tenant_scope(pool, tenant_id) as conn:
        template = _template(conn, template_id)
        if template["status"] != "published":
            raise Conflict(f"this_template_is_{template['status']}")
        assert template["live_rule_id"] is not None
        rule_id = template["live_rule_id"]
        rule = _rule_row(conn, rule_id)
        policy = _live_policy(conn, template_id)
        requirements = _template_requirements(conn, template_id)
        if not requirements:
            raise Conflict(
                "this template requires nothing, so a session of it would hold no room and "
                "no instructor")
        chart = _resource_chart(conn)
        where = _location(conn, template["location_id"])
        existing = {
            r[0] for r in conn.execute(
                "SELECT starts_at FROM plt01.sch_sessions WHERE rule_id = %s", (rule_id,)
            ).fetchall()}
        floor = max(from_date, rule.starts_on) if from_date else rule.starts_on
        #: **How many occurrences were already there.** A retried generation reports
        #: `created: 0`, and without this a caller cannot tell "already done" from "nothing
        #: matched the rule" -- MOD-017's rule that an idempotent command has to be idempotent
        #: to the caller and not merely in the table.
        already = 0
        for occurrence in recurrence.generate(rule):
            if occurrence.local_date < floor:
                continue
            if occurrence.starts_at in existing:
                already += 1
                continue
            place = availability.Placement(
                starts_at=occurrence.starts_at, ends_at=occurrence.ends_at,
                location_id=template["location_id"])
            window = capacity.resource_window(place, policy["policy"])
            held = _held_over(
                conn, holds_from=window.starts_at, holds_until=window.ends_at)
            found = conflicts.detect(window, requirements, chart, held)
            # Availability is a different question from a clash, so it is asked separately and
            # reported as its own conflict kind: "the rota says no" and "the room is busy" have
            # different remedies.
            assignments: list[tuple[str, str, int]] = []
            for requirement in requirements:
                assignments.extend(_assign(requirement, chart, held, window))
            for resource_id, kind, _ in assignments:
                if kind != "staff":
                    continue
                # **Against the hold window, not the bare session.** A coach is held for the
                # setup and cleanup margins too, so checking only the session let the rota end
                # mid-cleanup with no objection -- and `conflicts.detect` was already using the
                # wider window, so the two questions were being asked about different spans.
                reason = availability.unavailable_reason(
                    window, _windows(conn, resource_id), timezone=where["timezone"])
                if reason is not None:
                    found.append(conflicts.Conflict(
                        kind="unavailable", resource_id=resource_id, detail=reason))
            # **An overridden occurrence is created; a refused one is not.** The first version
            # skipped every conflicting occurrence and *then*, if a reason had been given,
            # wrote an override row for each session in `created` -- which held only the
            # occurrences that had no conflict. So an override reason bought nothing at all:
            # the response said 201, nothing was created, and no override was recorded, while
            # paragraph 1842's Critical Control reads as satisfied. Found by the HTTP tests.
            if found and not written:
                detected.extend(found)
                continue
            session = _insert_session(
                conn, tenant_id, template=template, template_id=template_id,
                rule_id=rule_id, policy=policy, occurrence=occurrence,
                timezone=where["timezone"], window=window, assignments=assignments,
                actor_id=actor_id, correlation_id=correlation_id)
            created.append(session)
            if found:
                detected.extend(found)
                # **The override names this occurrence's own conflicts**, not the run's. A
                # summary of every clash in a sixty-day generation, copied onto each session,
                # is a row nobody can read back to "what was overridden here".
                conn.execute(
                    """
                    INSERT INTO plt01.sch_conflict_overrides
                        (tenant_id, session_id, conflict_summary, conflict_count,
                         reason, overridden_by, correlation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, session["session_id"],
                     conflicts.summarise(found)[:4000], len(found), written,
                     actor_id, correlation_id))
                overridden += 1
        if detected and not written:
            # **Recorded, then refused after the commit.** `tenant_scope` rolls back on a
            # raise, so publishing the detection inside the block and raising here would
            # throw away the evidence that the conflict was found at all.
            _append(conn, tenant_id, "resource.conflict.detected", "template",
                    template_id,
                    {"template_id": template_id, "rule_id": rule_id,
                     "conflict_count": len(detected),
                     "first_conflict_kind": detected[0].kind},
                    correlation_id=correlation_id, actor_id=actor_id)
            settled = Conflict(
                f"{len(detected)} conflict(s) and no override reason: "
                f"{conflicts.summarise(detected)}")
        if settled is None:
            for session in created:
                _append(conn, tenant_id, "session.created", "session",
                        session["session_id"],
                        {"session_id": session["session_id"],
                         "template_id": template_id,
                         "starts_at": session["starts_at"],
                         "location_id": template["location_id"],
                         "capacity": session["capacity"]},
                        correlation_id=correlation_id, actor_id=actor_id)
    if settled is not None:
        raise settled
    return {"template_id": template_id, "created": len(created),
            "existing": already, "sessions": created,
            # The overrides written, which is zero unless a reason was given -- a caller that
            # forced a generation has to be able to see that it was forced, and how often.
            "overridden": overridden,
            "conflicts": [{"kind": c.kind, "resource_id": c.resource_id,
                           "detail": c.detail} for c in detected],
            "generated_at": moment.isoformat(), "as_of": today.isoformat()}


def _insert_session(
    conn: Connection[Any], tenant_id: str, *, template: dict[str, Any],
    template_id: str, rule_id: str, policy: dict[str, Any],
    occurrence: recurrence.Occurrence, timezone: str,
    window: availability.Placement, assignments: list[tuple[str, str, int]],
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """One session and the resources it holds, in the caller's transaction."""
    try:
        row = conn.execute(
            """
            INSERT INTO plt01.sch_sessions
                (tenant_id, template_id, rule_id, policy_id, location_id, starts_at,
                 ends_at, local_date, timezone, dst_adjusted, capacity, overbook_places,
                 created_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, rule_id, starts_at) DO NOTHING
            RETURNING session_id
            """,
            (tenant_id, template_id, rule_id, policy["policy_id"],
             template["location_id"], occurrence.starts_at, occurrence.ends_at,
             occurrence.local_date, timezone, occurrence.adjusted,
             policy["policy"].capacity, policy["policy"].overbook_places, actor_id,
             correlation_id),
        ).fetchone()
    except errors.ForeignKeyViolation as e:
        raise NotFound(_fk_subject(e)) from None
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    if row is None:
        # Another transaction generated it between the read and the insert. `DO NOTHING` then a
        # re-read, never a caught `UniqueViolation`: a caught one leaves the transaction
        # aborted and the next statement raises `InFailedSqlTransaction`.
        again = conn.execute(
            "SELECT session_id FROM plt01.sch_sessions"
            " WHERE rule_id = %s AND starts_at = %s",
            (rule_id, occurrence.starts_at),
        ).fetchone()
        assert again is not None
        # **The same keys as the ordinary return.** Two shapes out of one function is a
        # `KeyError` in whichever caller iterates the list, and this branch is the rare one --
        # so it is the one nobody would see until a race in production.
        return {"session_id": str(again[0]),
                "starts_at": occurrence.starts_at.isoformat(),
                "local_date": occurrence.local_date.isoformat(),
                "timezone": timezone, "dst_adjusted": occurrence.adjusted,
                "capacity": policy["policy"].capacity, "repeated": True,
                "resources": [{"resource_id": r, "kind": k, "quantity": q}
                              for r, k, q in assignments]}
    session_id = str(row[0])
    for resource_id, kind, quantity in assignments:
        try:
            conn.execute(
                """
                INSERT INTO plt01.sch_session_resources
                    (tenant_id, session_id, resource_id, resource_kind, quantity,
                     holds_from, holds_until, assigned_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, session_id, resource_id, kind, quantity,
                 window.starts_at, window.ends_at, actor_id, correlation_id))
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    return {"session_id": session_id, "starts_at": occurrence.starts_at.isoformat(),
            "local_date": occurrence.local_date.isoformat(),
            "timezone": timezone, "dst_adjusted": occurrence.adjusted,
            "capacity": policy["policy"].capacity, "repeated": False,
            "resources": [{"resource_id": r, "kind": k, "quantity": q}
                          for r, k, q in assignments]}


# ------------------------------------------------------------------ changes to a session

def _session(
    conn: Connection[Any], session_id: str, *, for_update: bool = True,
) -> dict[str, Any]:
    """One session, locked by default.

    **A write locks the row and a read does not.** Every path that counts places or settles a
    status needs the lock -- that is what makes the count and the insert one decision. A read
    that took it would block every booking on the session for the length of an eligibility
    check, which is a read a booking surface makes on every page.
    """
    row = conn.execute(
        "SELECT template_id, location_id, starts_at, ends_at, status, capacity,"
        " overbook_places, timezone, policy_id"
        " FROM plt01.sch_sessions WHERE session_id = %s"
        + (" FOR UPDATE" if for_update else ""),
        (session_id,),
    ).fetchone()
    if row is None:
        raise NotFound("session_not_found")
    return {"template_id": str(row[0]), "location_id": str(row[1]), "starts_at": row[2],
            "ends_at": row[3], "status": str(row[4]), "capacity": int(row[5]),
            "overbook_places": int(row[6]), "timezone": str(row[7]),
            "policy_id": str(row[8])}


def substitute_instructor(
    pool: Pool, tenant_id: str, session_id: str, *, replacement_resource_id: str,
    reason: str, actor_id: str, correlation_id: str,
    override_reason: str | None = None,
) -> dict[str, Any]:
    """SubstituteInstructor. OPS-01-R07.

    **The substitute's availability and conflicts are checked, and overriding needs a reason.**
    A cover that clashes with the substitute's own class is two classes with one coach, which
    is exactly the conflict paragraph 1842 will not have silently overridden.

    **Nothing is written to the substitute's rota.** A coach covering one class on Tuesday has
    not had their working hours changed; editing availability to make the cover legal would
    leave a rota nobody could read back.
    """
    change = substitution.Change(
        kind="substitution", reason=reason, replacement_id=replacement_resource_id)
    try:
        substitution.check_change(change)
    except recurrence.ScheduleError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        session = _session(conn, session_id)
        try:
            substitution.check_session_transition(session["status"], "cancelled")
        except recurrence.ScheduleError as e:
            raise Conflict(str(e)) from None
        held_row = conn.execute(
            "SELECT resource_id, holds_from, holds_until FROM plt01.sch_session_resources"
            " WHERE session_id = %s AND resource_kind = 'staff'"
            "   AND superseded_at IS NULL",
            (session_id,),
        ).fetchone()
        if held_row is None:
            raise Conflict("this_session_holds_no_instructor_to_substitute")
        outgoing = str(held_row[0])
        if outgoing == replacement_resource_id:
            raise Conflict("that_instructor_is_already_teaching_this_session")
        chart = _resource_chart(conn)
        if replacement_resource_id not in chart:
            raise NotFound("scheduling_resource_not_found")
        if chart[replacement_resource_id].kind != "staff":
            raise Conflict("a_substitute_instructor_is_a_staff_resource")
        window = availability.Placement(
            starts_at=held_row[1], ends_at=held_row[2],
            location_id=session["location_id"])
        others = _held_over(
            conn, holds_from=window.starts_at, holds_until=window.ends_at)
        found = conflicts.detect(
            window, [resources.Requirement("staff", resource_id=replacement_resource_id)],
            chart, others, session_id=session_id)
        place = availability.Placement(
            starts_at=session["starts_at"], ends_at=session["ends_at"],
            location_id=session["location_id"])
        unavailable = availability.unavailable_reason(
            place, _windows(conn, replacement_resource_id),
            timezone=session["timezone"])
        if unavailable is not None:
            found.append(conflicts.Conflict(
                kind="unavailable", resource_id=replacement_resource_id,
                detail=unavailable))
        if found and not (override_reason or "").strip():
            raise Conflict(
                f"the substitute is not free: {conflicts.summarise(found)}. Overriding "
                f"needs a reason")
        # **The outgoing hold is superseded and the incoming one takes it.** The row stays, so
        # "who was teaching this before" is answerable from the rows as well as from the
        # change log -- and the coach who was substituted out stops reading as busy, which is
        # the whole point: leaving the hold live made an ill instructor unschedulable
        # everywhere else at that hour, for ever.
        conn.execute(
            "UPDATE plt01.sch_session_resources"
            "   SET superseded_at = now(), superseded_by = %s,"
            "       supersede_correlation_id = %s"
            " WHERE session_id = %s AND resource_id = %s"
            "   AND superseded_at IS NULL",
            (actor_id, correlation_id, session_id, outgoing))
        # **A plain insert.** A coach who recovered and is put back gets a new assignment row;
        # the superseded one keeps the name of whoever took them off the class. An earlier
        # version cleared the marker with `ON CONFLICT DO UPDATE`, which erased that name.
        conn.execute(
            """
            INSERT INTO plt01.sch_session_resources
                (tenant_id, session_id, resource_id, resource_kind, quantity,
                 holds_from, holds_until, assigned_by, correlation_id)
            VALUES (%s, %s, %s, 'staff', 1, %s, %s, %s, %s)
            """,
            (tenant_id, session_id, replacement_resource_id, window.starts_at,
             window.ends_at, actor_id, correlation_id))
        change_id = _record_change(
            conn, tenant_id, session_id=session_id, kind="substitution",
            replacement_id=replacement_resource_id, replaced_id=outgoing,
            reason=reason, actor_id=actor_id, correlation_id=correlation_id)
        if found:
            conn.execute(
                """
                INSERT INTO plt01.sch_conflict_overrides
                    (tenant_id, session_id, conflict_summary, conflict_count, reason,
                     overridden_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, session_id, conflicts.summarise(found)[:4000], len(found),
                 (override_reason or "").strip(), actor_id, correlation_id))
        _append(conn, tenant_id, "instructor.substituted", "session", session_id,
                {"session_id": session_id, "template_id": session["template_id"],
                 "from_resource_id": outgoing,
                 "to_resource_id": replacement_resource_id,
                 "overridden": bool(found)},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"session_id": session_id, "change_id": change_id,
            "from_resource_id": outgoing, "to_resource_id": replacement_resource_id,
            "overridden": bool(found),
            "conflicts": [{"kind": c.kind, "detail": c.detail} for c in found]}


def _record_change(
    conn: Connection[Any], tenant_id: str, *, session_id: str, kind: str,
    reason: str, actor_id: str, correlation_id: str,
    replacement_id: str | None = None, replaced_id: str | None = None,
) -> str:
    try:
        row = conn.execute(
            """
            INSERT INTO plt01.sch_session_changes
                (tenant_id, session_id, change_kind, replacement_id, replaced_id,
                 reason, recorded_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING change_id
            """,
            (tenant_id, session_id, kind, replacement_id, replaced_id, reason.strip(),
             actor_id, correlation_id),
        ).fetchone()
    except errors.RaiseException as e:
        raise Conflict(str(e).strip().splitlines()[0]) from None
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return str(row[0])


def cancel_session(
    pool: Pool, tenant_id: str, session_id: str, *, cancellation_reason: str,
    reason: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Cancel one session. OPS-01-R07.

    **The held places are released and the reason says whether they come back.** A declared
    reason rather than prose, because what a member is owed depends on it -- and `other` is the
    one that returns nothing, which is why it needs somebody to decide rather than being a
    default. MOD-020's booking reads the released holds; this module does not know what a
    booking is.
    """
    change = substitution.Change(
        kind="cancellation", reason=reason, cancellation_reason=cancellation_reason)
    try:
        substitution.check_change(change)
    except recurrence.ScheduleError as e:
        raise InvalidRequest(str(e)) from None
    returns = substitution.places_are_returned(change)
    moment = _now()
    with tenant_scope(pool, tenant_id) as conn:
        session = _session(conn, session_id)
        try:
            substitution.check_session_transition(session["status"], "cancelled")
        except recurrence.ScheduleError as e:
            raise Conflict(str(e)) from None
        released = conn.execute(
            "SELECT coalesce(sum(places), 0), count(*) FROM plt01.sch_capacity_holds"
            " WHERE session_id = %s AND status = 'held'",
            (session_id,),
        ).fetchone()
        try:
            conn.execute(
                "UPDATE plt01.sch_sessions SET status = 'cancelled', cancelled_at = %s,"
                " cancelled_by = %s, cancellation_reason = %s,"
                " cancel_correlation_id = %s"
                " WHERE session_id = %s AND status = 'scheduled'",
                (moment, actor_id, cancellation_reason, correlation_id, session_id))
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        conn.execute(
            "UPDATE plt01.sch_capacity_holds SET status = 'released', released_at = %s,"
            " released_by = %s, release_reason = %s, release_correlation_id = %s"
            " WHERE session_id = %s AND status = 'held'",
            (moment, actor_id, f"session cancelled: {cancellation_reason}",
             correlation_id, session_id))
        change_id = _record_change(
            conn, tenant_id, session_id=session_id, kind="cancellation", reason=reason,
            actor_id=actor_id, correlation_id=correlation_id)
        _append(conn, tenant_id, "session.changed", "session", session_id,
                {"session_id": session_id, "template_id": session["template_id"],
                 "change_kind": "cancellation"},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"session_id": session_id, "status": "cancelled", "change_id": change_id,
            "cancellation_reason": cancellation_reason,
            "places_released": int(released[0]) if released else 0,
            "holds_released": int(released[1]) if released else 0,
            "places_returned": returns}


def relocate_session(
    pool: Pool, tenant_id: str, session_id: str, *, to_location_id: str, reason: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Move a session to another location. OPS-01-R07.

    **Refused within an hour of the start.** A notice that cannot reach the members travelling
    to a class is worse than a cancellation, which tells them something true. The session's own
    time does not move -- only where it is -- because moving the time is a cancellation and a
    new session, which is what a member is told.

    **It moves the session, and it moves the room with it.** The first version recorded the
    change and left `sch_sessions.location_id` alone, with a `note` in the response explaining
    that a published session's identity does not move -- so the destination's calendar stayed
    empty, the origin's showed a class that was not there, and the old studio went on reading
    as occupied. A response field explaining why the module did not do what it was asked is
    not a design decision; it is the defect, written down. Found by the HTTP tests.

    So: the location-bound holds are superseded, a free room of each required kind is taken at
    the destination, and the refusal when nothing is free names what was missing. Nothing is
    half-moved -- the whole thing commits or none of it does.
    """
    moment = _now()
    with tenant_scope(pool, tenant_id) as conn:
        session = _session(conn, session_id)
        if session["status"] != "scheduled":
            raise Conflict(f"this_session_is_{session['status']}")
        try:
            substitution.check_relocation(
                from_location_id=session["location_id"],
                to_location_id=to_location_id, starts_at=session["starts_at"],
                at=moment)
        except recurrence.ScheduleError as e:
            raise Conflict(str(e)) from None
        where = _location(conn, to_location_id)
        # **The timezone has to match**, because the session's local date and time were
        # computed in the old one: moving a class to a site in another zone would leave the
        # row saying 18:00 local when it is 20:00 there. Cancelling and rescheduling is the
        # honest path and the refusal says so.
        if where["timezone"] != session["timezone"]:
            raise Conflict(
                f"{where['location_name']} is in {where['timezone']} and this session's "
                f"local time was computed in {session['timezone']}; cancel it and schedule "
                f"another there")
        # **What belongs to a building moves; what travels stays.** A studio, a zone, a court
        # and the bikes in it are the site; a coach and the class format are not, and
        # superseding a coach's hold here would read as the instructor having been taken off
        # the class. Keyed on the *kind* rather than on whether the resource has a location,
        # because a coach has one too -- which made the first version report that the
        # destination had no free staff and refuse every relocation.
        bound = conn.execute(
            "SELECT r.resource_id, r.resource_kind, r.quantity, r.holds_from,"
            " r.holds_until"
            " FROM plt01.sch_session_resources r"
            " JOIN plt01.sch_resources res ON res.resource_id = r.resource_id"
            " WHERE r.session_id = %s AND r.superseded_at IS NULL"
            "   AND r.resource_kind IN ('room', 'zone', 'court', 'equipment')"
            "   AND res.location_id IS NOT NULL AND res.location_id <> %s",
            (session_id, to_location_id),
        ).fetchall()
        moved: list[dict[str, Any]] = []
        if bound:
            window = availability.Placement(
                starts_at=bound[0][3], ends_at=bound[0][4],
                location_id=to_location_id)
            held = _held_over(
                conn, holds_from=window.starts_at, holds_until=window.ends_at)
            chart = {
                rid: res for rid, res in _resource_chart(conn).items()
                if res.location_id == to_location_id}
            for resource_id, kind, quantity, _, _ in bound:
                wanted = resources.Requirement(str(kind), quantity=int(quantity))
                picked = _assign(wanted, chart, held, window)
                if sum(q for _, _, q in picked) < int(quantity):
                    raise Conflict(
                        f"{where['location_name']} has no free {kind} for this session; "
                        f"cancel it and schedule another there")
                conn.execute(
                    "UPDATE plt01.sch_session_resources"
                    "   SET superseded_at = now(), superseded_by = %s,"
                    "       supersede_correlation_id = %s"
                    " WHERE session_id = %s AND resource_id = %s"
                    "   AND superseded_at IS NULL",
                    (actor_id, correlation_id, session_id, resource_id))
                for new_id, new_kind, new_quantity in picked:
                    conn.execute(
                        """
                        INSERT INTO plt01.sch_session_resources
                            (tenant_id, session_id, resource_id, resource_kind,
                             quantity, holds_from, holds_until, assigned_by,
                             correlation_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (tenant_id, session_id, new_id, new_kind, new_quantity,
                         window.starts_at, window.ends_at, actor_id, correlation_id))
                    held.append(conflicts.Held(
                        resource_id=new_id, kind=new_kind, quantity=new_quantity,
                        placement=window, session_id=session_id,
                        session_label="this session"))
                    moved.append({"from_resource_id": str(resource_id),
                                  "to_resource_id": new_id, "kind": new_kind})
        conn.execute(
            "UPDATE plt01.sch_sessions SET location_id = %s WHERE session_id = %s",
            (to_location_id, session_id))
        change_id = _record_change(
            conn, tenant_id, session_id=session_id, kind="relocation",
            replacement_id=to_location_id, replaced_id=session["location_id"],
            reason=reason, actor_id=actor_id, correlation_id=correlation_id)
        _append(conn, tenant_id, "session.changed", "session", session_id,
                {"session_id": session_id, "template_id": session["template_id"],
                 "change_kind": "relocation"},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"session_id": session_id, "change_id": change_id,
            "from_location_id": session["location_id"],
            "to_location_id": to_location_id, "resources_moved": moved}


def hand_off_attendance(
    pool: Pool, tenant_id: str, session_id: str, *, to_resource_id: str, reason: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Who takes the attendance for a session. OPS-01-R07's handoff.

    Separate from a substitution because they are different facts: a substitute teaches, and a
    handoff is who records who came. Paragraph 4189 keeps session completion and credit
    consumption as separate coordinated events, and this is the scheduling half.
    """
    with tenant_scope(pool, tenant_id) as conn:
        session = _session(conn, session_id)
        if session["status"] != "scheduled":
            raise Conflict(f"this_session_is_{session['status']}")
        chart = _resource_chart(conn)
        if to_resource_id not in chart:
            raise NotFound("scheduling_resource_not_found")
        if chart[to_resource_id].kind != "staff":
            raise Conflict("attendance_is_handed_to_a_staff_resource")
        change_id = _record_change(
            conn, tenant_id, session_id=session_id, kind="handoff",
            replacement_id=to_resource_id, reason=reason, actor_id=actor_id,
            correlation_id=correlation_id)
        _append(conn, tenant_id, "session.changed", "session", session_id,
                {"session_id": session_id, "template_id": session["template_id"],
                 "change_kind": "handoff"},
                correlation_id=correlation_id, actor_id=actor_id)
    return {"session_id": session_id, "change_id": change_id,
            "to_resource_id": to_resource_id}


# ------------------------------------------------------------------ capacity holds

def take_hold_on(
    conn: Connection[Any], tenant_id: str, session_id: str, *, person_id: str,
    source_kind: str, source_ref: str, idempotency_key: str, actor_id: str,
    correlation_id: str, places: int = 1, at: datetime | None = None,
    skills: list[str] | None = None,
) -> dict[str, Any]:
    """Take places on a session, **in the caller's transaction**.

    This is the form MOD-020 needs and the reason it exists: paragraph 4142 requires a
    reservation to be atomic against the scheduled instance, and the only way to mean that is
    to take the hold on the connection that writes the booking. A booking written in one
    transaction and its place taken in another is a member with a confirmed booking and no
    place, or a place nobody holds -- and no later reconciliation can tell which happened.
    MOD-010's `append_event` makes the same argument about an event and the state that caused
    it, and MOD-018's `post_journal` about a journal and the payment it records.

    `take_hold` is the pool-taking wrapper, correct where there is no state change to be atomic
    with -- a front desk walking somebody in.

    Take places on a session. The atomic reservation paragraph 4146 asks for.

    **Counted under a row lock on the session, inside the transaction that writes the hold.** A
    count read outside the lock is a count two bookings both read before either writes, which
    is overbooking by construction. The trigger beside the table holds for any other writer.

    **The restrictions are evaluated here, against facts this module derives.** They were not
    evaluated at all at first -- the only path that takes a place checked the places and the
    window and nothing else, so a fourteen-year-old could be given one on a sixteen-and-over
    class while this docstring said otherwise. A docstring is not an attribution.

    **Then they were evaluated against facts the caller sent, which was worse.** The defence
    was written down -- the age belongs to MOD-014 and the entitlements to MOD-017, and this
    module reads neither -- and it was false, which is the trap `CLAUDE.md` records as
    MOD-017's: when a module explains why it accepted something, check whether the danger it
    names is reachable. `ppl_persons` is in `plt01` under this role, `sch_capacity_holds`
    already carries a composite foreign key to it, and `mem_entitlement_grants` is one join
    further. So a routine AAL-1 session -- a front desk, a turnstile -- bought a child a place
    in an adult class by typing a number, and the hold row recorded for ever that they were
    there. Found by a reviewer, who did it.

    So the age comes from `ppl_persons.date_of_birth` and the entitlements from the grants that
    are active over this session. **`skills` is still the caller's word**, because nothing in
    this build stores a skill -- and that is said here rather than implied.

    `eligibility` refuses on a *missing* fact, so a member with no recorded birth date cannot
    take a place on an age-restricted session. That is the opposite of MOD-014's guardianship
    default, deliberately: there, treating every undated person as a minor would block reading
    most lead records, and here letting one into a class the insurer excluded is the harm.
    """
    moment = at or _now()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    prior = conn.execute(
        "SELECT hold_id, session_id, places, status, person_id, source_kind,"
        " source_ref FROM plt01.sch_capacity_holds WHERE idempotency_key = %s",
        (idempotency_key.strip(),),
    ).fetchone()
    if prior is not None:
        # **Every field of the request is compared, not just the session.** The first
        # version checked `session_id` alone and answered 201 with the *previous* caller's
        # hold id for a request naming a different person, a different count and a
        # different source -- and the repeated branch omitted `person_id`, so the caller
        # could not even tell whose hold it had been given. Bob got Alice's booking and
        # nothing said so. The realistic input is a till or a booking client reusing a
        # counter or a per-shift key across members, which is how a key gets reused in the
        # field. MOD-017's rule: a retry is answered from what was recorded, and a key
        # reused with different content is a conflict.
        if (str(prior[1]) != session_id or str(prior[4]) != person_id
                or int(prior[2]) != places or str(prior[5]) != source_kind
                or str(prior[6]) != source_ref.strip()):
            raise Conflict("this_idempotency_key_was_used_for_a_different_request")
        return {"hold_id": str(prior[0]), "session_id": session_id,
                "person_id": str(prior[4]), "places": int(prior[2]),
                "status": str(prior[3]), "repeated": True}
    session = _session(conn, session_id)
    if session["status"] != "scheduled":
        raise Conflict(f"this_session_is_{session['status']}")
    policy = conn.execute(
        "SELECT opens_hours_before, closes_minutes_before"
        " FROM plt01.sch_capacity_policies WHERE policy_id = %s",
        (session["policy_id"],),
    ).fetchone()
    place = availability.Placement(
        starts_at=session["starts_at"], ends_at=session["ends_at"],
        location_id=session["location_id"])
    if policy is not None:
        shut = capacity.booking_window_open(
            place, at=moment, opens_hours_before=int(policy[0]),
            closes_minutes_before=int(policy[1]))
        if shut is not None:
            raise Conflict(shut)
    taken = conn.execute(
        "SELECT coalesce(sum(places), 0) FROM plt01.sch_capacity_holds"
        " WHERE session_id = %s AND status IN ('held', 'attended')",
        (session_id,),
    ).fetchone()
    policy_object = capacity.Policy(
        capacity=session["capacity"], overbook_places=session["overbook_places"])
    try:
        capacity.check_hold(
            policy_object, held=int(taken[0]) if taken else 0, wanted=places)
    except recurrence.ScheduleError as e:
        raise Conflict(str(e)) from None
    restriction_rows = conn.execute(
        "SELECT restriction_kind, restriction_value FROM plt01.sch_restrictions"
        " WHERE policy_id = %s ORDER BY restriction_kind",
        (session["policy_id"],),
    ).fetchall()
    if restriction_rows:
        ineligible = capacity.eligibility(
            [capacity.Restriction(str(r[0]), str(r[1])) for r in restriction_rows],
            _candidate(conn, person_id, at=session["starts_at"], skills=skills))
        if ineligible is not None:
            raise Conflict(ineligible)
    try:
        row = conn.execute(
            """
            INSERT INTO plt01.sch_capacity_holds
                (tenant_id, session_id, person_id, places, source_kind, source_ref,
                 taken_by, idempotency_key, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING hold_id
            """,
            (tenant_id, session_id, person_id, places, source_kind,
             source_ref.strip(), actor_id, idempotency_key.strip(),
             correlation_id),
        ).fetchone()
    except errors.UniqueViolation:
        raise Conflict("this_person_already_holds_a_place_on_this_session") from None
    except errors.ForeignKeyViolation as e:
        raise NotFound(_fk_subject(e)) from None
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    except errors.RaiseException as e:
        raise Conflict(str(e).strip().splitlines()[0]) from None
    assert row is not None
    return {"hold_id": str(row[0]), "session_id": session_id, "person_id": person_id,
            "places": places, "status": "held", "repeated": False}


def take_hold(
    pool: Pool, tenant_id: str, session_id: str, *, person_id: str, source_kind: str,
    source_ref: str, idempotency_key: str, actor_id: str, correlation_id: str,
    places: int = 1, at: datetime | None = None, skills: list[str] | None = None,
) -> dict[str, Any]:
    """`take_hold_on` in a transaction of its own.

    **Correct only where there is no state change to be atomic with.** A front desk walking
    somebody into a class is that case: the hold is the whole act. A caller that also writes a
    row -- a booking, a waitlist confirmation -- has to use `take_hold_on` on its own
    connection, or the two commits can fail independently. MOD-010 calls the pool-taking
    wrapper around `append_event` the bug for the same reason, and names it accordingly.
    """
    with tenant_scope(pool, tenant_id) as conn:
        return take_hold_on(
            conn, tenant_id, session_id, person_id=person_id, source_kind=source_kind,
            source_ref=source_ref, idempotency_key=idempotency_key, actor_id=actor_id,
            correlation_id=correlation_id, places=places, at=at, skills=skills)


def _candidate(
    conn: Connection[Any], person_id: str, *, at: datetime,
    skills: list[str] | None = None,
) -> capacity.Candidate:
    """The facts a session's restrictions are evaluated against, derived rather than accepted.

    **The age is the person's own.** `ppl_persons` is in `plt01` under this role and the hold
    already carries a composite foreign key to it, so there is nothing for a caller to assert:
    a reviewer got a fourteen-year-old a place on an 18+ session by sending `age_years: 30` on
    the cheapest permission in the module. An unrecorded birth date yields None, and
    `capacity.eligibility` refuses on a missing fact -- which is the direction that matters
    here.

    **The entitlements are the grants that are live over this session.** MOD-017 owns them and
    they are on this plane; a restriction naming `class-pass` means the member holds an active
    grant whose policy key is `class-pass` at the moment the session runs, not that somebody
    typed the words.

    **The skills are the caller's**, and that is the one honest case: nothing in this build
    stores a skill, so there is no other source. Said out loud rather than left to be found.
    """
    row = conn.execute(
        "SELECT date_of_birth FROM plt01.ppl_persons WHERE person_id = %s",
        (person_id,),
    ).fetchone()
    if row is None:
        raise NotFound("person_not_found")
    age: int | None = None
    if row[0] is not None:
        born: date = row[0]
        local = at.date()
        age = local.year - born.year - (
            (local.month, local.day) < (born.month, born.day))
    granted = conn.execute(
        "SELECT p.policy_key FROM plt01.mem_entitlement_grants g"
        " JOIN plt01.mem_entitlement_policies p ON p.policy_id = g.policy_id"
        " WHERE g.person_id = %s AND g.status = 'active'"
        "   AND g.valid_from <= %s AND (g.valid_to IS NULL OR g.valid_to >= %s)",
        (person_id, at.date(), at.date()),
    ).fetchall()
    return capacity.Candidate(
        age_years=age, skills=frozenset(skills or ()),
        entitlements=frozenset(str(r[0]) for r in granted))


def check_eligibility_on(
    conn: Connection[Any], session_id: str, *, person_id: str,
    skills: list[str] | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """Whether somebody with these facts could take a place, and why not. OPS-01-R04.

    **A read, so a booking surface can explain before it asks.** Paragraph 1892 makes an
    understandable denial a Critical Control, and a surface that can only find out by trying
    gives a member a refusal with no reason attached.

    **In the caller's transaction**, so MOD-020's booking command can ask the same question
    its own eligibility read answers. The pool-taking `check_eligibility` below is MOD-019's
    own route; a booking that evaluated its own rule set was the shape a reviewer found --
    `may_book` answered `true` for a fourteen-year-old on an 18+ class and the command then
    refused it, which is the opposite of what an understandable denial means.

    **It answers about a named person, derived the same way `take_hold` derives them**, so the
    read and the write cannot disagree. An earlier version took the facts from the caller, and
    a surface could then be told a member was eligible on figures nobody held -- while the hold
    path, which is what actually matters, was taking the caller's word as well.
    """
    moment = at or _now()
    session = _session(conn, session_id, for_update=False)
    rows = conn.execute(
        "SELECT restriction_kind, restriction_value FROM plt01.sch_restrictions"
        " WHERE policy_id = %s ORDER BY restriction_kind",
        (session["policy_id"],),
    ).fetchall()
    policy = conn.execute(
        "SELECT opens_hours_before, closes_minutes_before"
        " FROM plt01.sch_capacity_policies WHERE policy_id = %s",
        (session["policy_id"],),
    ).fetchone()
    taken = conn.execute(
        "SELECT coalesce(sum(places), 0) FROM plt01.sch_capacity_holds"
        " WHERE session_id = %s AND status IN ('held', 'attended')",
        (session_id,),
    ).fetchone()
    candidate = _candidate(
        conn, person_id, at=session["starts_at"], skills=skills)
    restrictions = [capacity.Restriction(str(r[0]), str(r[1])) for r in rows]
    reasons: list[str] = []
    if session["status"] != "scheduled":
        reasons.append(f"this session is {session['status']}")
    ineligible = capacity.eligibility(restrictions, candidate)
    if ineligible is not None:
        reasons.append(ineligible)
    place = availability.Placement(
        starts_at=session["starts_at"], ends_at=session["ends_at"])
    if policy is not None:
        shut = capacity.booking_window_open(
            place, at=moment, opens_hours_before=int(policy[0]),
            closes_minutes_before=int(policy[1]))
        if shut is not None:
            reasons.append(shut)
    held = int(taken[0]) if taken else 0
    room = session["capacity"] + session["overbook_places"]
    if held >= room:
        reasons.append(f"this session has {room} places and {held} are held")
    return {"session_id": session_id, "eligible": not reasons, "reasons": reasons,
            # **The restriction answer on its own key, not just folded into the prose.** A
            # caller that needs to know whether the *member* is eligible -- as against the
            # window being shut or the room being full -- was left matching the start of a
            # sentence, which is the control-by-string-matching shape MOD-016 was bitten by.
            "ineligible": ineligible,
            "places": room, "held": held, "free": max(0, room - held),
            "as_of": moment.isoformat()}


def check_eligibility(
    pool: Pool, tenant_id: str, session_id: str, *, person_id: str,
    skills: list[str] | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """`check_eligibility_on` in its own transaction, for a route that reads nothing else."""
    with tenant_scope(pool, tenant_id) as conn:
        return check_eligibility_on(
            conn, session_id, person_id=person_id, skills=skills, at=at)


def release_hold_on(
    conn: Connection[Any], tenant_id: str, hold_id: str, *, reason: str, actor_id: str,
    correlation_id: str, attended: bool = False,
) -> dict[str, Any]:
    """Settle a held place **in the caller's transaction**, for `take_hold_on`'s reason.

    A cancellation that released the place in a second transaction could release it and then
    fail to record the cancellation, which is a member still booked on a class whose seat has
    been given away.

    Settle a held place: released, or attended.

    **Settled once.** Releasing a released place or re-marking an attended one would rewrite
    who was in the room, and the release carries the only attribution there is -- MOD-008
    audits denials rather than allowed actions, and this module's role holds nothing in `iam`.
    """
    if not reason.strip():
        raise InvalidRequest("settling_a_place_states_why")
    moment = _now()
    target = "attended" if attended else "released"
    row = conn.execute(
        "SELECT session_id, status, places FROM plt01.sch_capacity_holds"
        " WHERE hold_id = %s FOR UPDATE",
        (hold_id,),
    ).fetchone()
    if row is None:
        raise NotFound("capacity_hold_not_found")
    if str(row[1]) == target:
        return {"hold_id": hold_id, "status": target, "repeated": True}
    try:
        settled = conn.execute(
            "UPDATE plt01.sch_capacity_holds SET status = %s, released_at = %s,"
            " released_by = %s, release_reason = %s, release_correlation_id = %s"
            " WHERE hold_id = %s AND status = 'held'",
            (target, moment, actor_id, reason.strip(), correlation_id, hold_id),
        ).rowcount
    except errors.RaiseException as e:
        raise Conflict(str(e).strip().splitlines()[0]) from None
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    if settled == 0:
        raise Conflict("this_place_was_settled_by_somebody_else")
    return {"hold_id": hold_id, "session_id": str(row[0]), "status": target,
            "places": int(row[2]), "repeated": False}


def release_hold(
    pool: Pool, tenant_id: str, hold_id: str, *, reason: str, actor_id: str,
    correlation_id: str, attended: bool = False,
) -> dict[str, Any]:
    """`release_hold_on` in a transaction of its own, for `take_hold`'s reason."""
    with tenant_scope(pool, tenant_id) as conn:
        return release_hold_on(
            conn, tenant_id, hold_id, reason=reason, actor_id=actor_id,
            correlation_id=correlation_id, attended=attended)


# ------------------------------------------------------------------ reads

def list_resources(
    pool: Pool, tenant_id: str, *, kind: str | None = None,
    location_id: str | None = None, include_retired: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    """The resource list. OPS-01-R01."""
    bounded = max(1, min(limit, 1000))
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT resource_id, resource_code, resource_kind, display_name, quantity,"
            " brand_id, location_id, person_id, status"
            " FROM plt01.sch_resources"
            # **Every placeholder in a NULL test is cast.** `%s IS NULL` with a NULL text
            # parameter is `IndeterminateDatatype` at the server, which reaches the caller as
            # a 500 on the plainest read in the module -- and only when the filter is left
            # out, which is the default. The `uuid` cast beside it was there from the start;
            # this one was not.
            " WHERE (%s::text IS NULL OR resource_kind = %s)"
            "   AND (%s::uuid IS NULL OR location_id = %s)"
            "   AND (%s OR status = 'active')"
            " ORDER BY resource_kind, resource_code LIMIT %s",
            (kind, kind, location_id, location_id, include_retired, bounded),
        ).fetchall()
    return {"count": len(rows), "resources": [
        {"resource_id": str(r[0]), "resource_code": str(r[1]),
         "resource_kind": str(r[2]), "display_name": str(r[3]), "quantity": int(r[4]),
         "brand_id": str(r[5]) if r[5] else None,
         "location_id": str(r[6]) if r[6] else None,
         "person_id": str(r[7]) if r[7] else None, "status": str(r[8])}
        for r in rows]}


def session_detail(
    pool: Pool, tenant_id: str, session_id: str, *, may_read_reasons: bool = False,
) -> dict[str, Any]:
    """One session with what it holds, what changed about it and how full it is.

    **The held count is a sum over the holds**, and the places are the session's own snapshot:
    the two together are what a booking surface needs and neither is cached.

    **A change's reason is prose an operator wrote, so it is masked by default.** A reviewer
    wrote "she is having chemotherapy on Tuesdays" into a substitution reason through the
    ordinary route and read it back holding only `scheduling.schedule.read` -- the routine
    AAL-1 permission a front desk and a turnstile hold -- while `/people/{id}` refused the same
    session 403. That is MOD-017's blocking finding in this module's clothes: a health fact is
    a health fact whatever column it is in, and the sibling declaration in
    `app/privacy/classification.py` already says in as many words that a reason column is where
    one goes in practice.

    So the reason is returned only to a caller holding `scheduling.session.change` -- whoever
    can record a substitution can read why one happened -- and everybody else is told it exists
    and is masked. MOD-014's rule: a redacted record still exists, because telling a coach a
    class changed for no stated reason is worse than telling them there is one they cannot see.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT s.template_id, t.template_code, t.display_name, s.location_id,"
            " s.starts_at, s.ends_at, s.local_date, s.timezone, s.dst_adjusted,"
            " s.capacity, s.overbook_places, s.status, s.cancellation_reason, s.rule_id"
            " FROM plt01.sch_sessions s"
            " JOIN plt01.sch_templates t ON t.template_id = s.template_id"
            " WHERE s.session_id = %s",
            (session_id,),
        ).fetchone()
        if row is None:
            raise NotFound("session_not_found")
        resource_rows = conn.execute(
            "SELECT r.resource_id, r.resource_kind, r.quantity, r.holds_from,"
            " r.holds_until, res.resource_code, res.display_name, r.superseded_at"
            " FROM plt01.sch_session_resources r"
            " JOIN plt01.sch_resources res ON res.resource_id = r.resource_id"
            " WHERE r.session_id = %s"
            " ORDER BY r.resource_kind, res.resource_code, r.assigned_at",
            (session_id,),
        ).fetchall()
        change_rows = conn.execute(
            "SELECT change_kind, replacement_id, replaced_id, reason, recorded_at"
            " FROM plt01.sch_session_changes WHERE session_id = %s"
            " ORDER BY recorded_at",
            (session_id,),
        ).fetchall()
        held = conn.execute(
            "SELECT coalesce(sum(places), 0), count(*) FROM plt01.sch_capacity_holds"
            " WHERE session_id = %s AND status IN ('held', 'attended')",
            (session_id,),
        ).fetchone()
        overrides = conn.execute(
            "SELECT conflict_count, conflict_summary, reason, overridden_at"
            " FROM plt01.sch_conflict_overrides WHERE session_id = %s"
            " ORDER BY overridden_at",
            (session_id,),
        ).fetchall()
        # **How full this class usually is** -- ADM-SCH-02's fourth metric, "92% USUAL FILL".
        # Eighteen booked means nothing until you know whether this class normally fills: on
        # a twenty-bike spin class that is a good Thursday, and on one that normally turns
        # people away it is a problem somebody should look at.
        #
        # **Past occurrences of the same rule, and this one excluded.** The rule is the
        # version the session was generated from, which is immutable -- so "the same class"
        # is exactly the set that cites this rule, and a template edit starts a new baseline
        # rather than retroactively changing an old one. Cancelled occurrences are left out
        # because nobody could book them, which would drag the mean toward zero for a class
        # whose instructor was ill once.
        usual = conn.execute(
            "SELECT count(*),"
            "       coalesce(sum(h.taken), 0),"
            "       coalesce(sum(p.places), 0)"
            " FROM plt01.sch_sessions o"
            " CROSS JOIN LATERAL (SELECT o.capacity + o.overbook_places AS places) p"
            " CROSS JOIN LATERAL ("
            "   SELECT coalesce(sum(c.places), 0) AS taken"
            "     FROM plt01.sch_capacity_holds c"
            "    WHERE c.session_id = o.session_id"
            "      AND c.status IN ('held', 'attended')) h"
            " WHERE o.rule_id = %s AND o.session_id <> %s"
            "   AND o.starts_at < %s AND o.status <> 'cancelled'"
            "   AND o.capacity + o.overbook_places > 0",
            (row[13], session_id, row[4]),
        ).fetchone()
    places = int(row[9]) + int(row[10])
    taken = int(held[0]) if held else 0
    return {
        "session_id": session_id, "template_id": str(row[0]),
        "template_code": str(row[1]), "display_name": str(row[2]),
        "location_id": str(row[3]), "starts_at": row[4].isoformat(),
        "ends_at": row[5].isoformat(), "local_date": row[6].isoformat(),
        "timezone": str(row[7]), "dst_adjusted": bool(row[8]),
        "capacity": int(row[9]), "overbook_places": int(row[10]), "places": places,
        "held": taken, "free": max(0, places - taken),
        "status": str(row[11]),
        "cancellation_reason": str(row[12]) if row[12] else None,
        "rule_id": str(row[13]),
        # **Null rather than zero where there is no baseline**, which is this repository's
        # standing rule for a comparison: a class running for the first time has no usual
        # fill, and 0% would read as one that nobody ever books. The count is returned beside
        # it so a surface can say how many occurrences it is a mean over -- one prior class
        # is an anecdote and a board should be able to say so.
        "usual_fill_bp": (
            None if usual is None or int(usual[0]) == 0 or int(usual[2]) == 0
            else round(int(usual[1]) * 10_000 / int(usual[2]))),
        "usual_fill_over": 0 if usual is None else int(usual[0]),
        # **What it holds now, and what it used to.** Two lists rather than one with a flag,
        # because every caller wants the first and only a dispute wants the second -- and a
        # flag somebody forgets to filter on puts a substituted instructor back on the roster.
        "resources": [
            {"resource_id": str(r[0]), "resource_kind": str(r[1]),
             "quantity": int(r[2]), "holds_from": r[3].isoformat(),
             "holds_until": r[4].isoformat(), "resource_code": str(r[5]),
             "display_name": str(r[6])} for r in resource_rows if r[7] is None],
        "former_resources": [
            {"resource_id": str(r[0]), "resource_kind": str(r[1]),
             "quantity": int(r[2]), "resource_code": str(r[5]),
             "display_name": str(r[6]), "superseded_at": r[7].isoformat()}
            for r in resource_rows if r[7] is not None],
        "changes": [
            {"change_kind": str(c[0]),
             "replacement_id": str(c[1]) if c[1] else None,
             "replaced_id": str(c[2]) if c[2] else None,
             "reason": str(c[3]) if may_read_reasons else None,
             "reason_masked": not may_read_reasons,
             "recorded_at": c[4].isoformat()}
            for c in change_rows],
        "conflict_overrides": [
            {"conflict_count": int(o[0]), "conflict_summary": str(o[1]),
             "reason": str(o[2]), "overridden_at": o[3].isoformat()}
            for o in overrides],
    }


def schedule_for(
    pool: Pool, tenant_id: str, *, location_id: str, from_date: date, to_date: date,
    include_cancelled: bool = False,
) -> dict[str, Any]:
    """The calendar. Paragraph 1844: "One calendar coordinates every bookable service".

    **Bounded to 62 days**, because a schedule read is the hottest path in the module and an
    unbounded range is a table scan a tenant can ask for. Two months is the window an admin
    screen shows.
    """
    if to_date < from_date:
        raise InvalidRequest("a_schedule_window_does_not_end_before_it_starts")
    if (to_date - from_date).days > 62:
        raise InvalidRequest("a_schedule_window_is_at_most_62_days")
    with tenant_scope(pool, tenant_id) as conn:
        where = _location(conn, location_id)
        rows = conn.execute(
            "SELECT s.session_id, s.template_id, t.display_name, s.starts_at, s.ends_at,"
            " s.local_date, s.capacity, s.overbook_places, s.status, s.dst_adjusted,"
            " coalesce((SELECT sum(h.places) FROM plt01.sch_capacity_holds h"
            "            WHERE h.session_id = s.session_id"
            "              AND h.status IN ('held', 'attended')), 0),"
            # **The live staff assignment, which is what ADM-SCH-01's ClassCell carries.**
            # `superseded_at IS NULL` is what "has a coach" means: a substitution supersedes
            # the outgoing hold and leaves the row, so counting rows would show a class whose
            # coach went home ill as staffed. Aggregated rather than joined, because a class
            # may be taught by two and a join would duplicate the session.
            " (SELECT string_agg(r.display_name, ', ' ORDER BY r.display_name)"
            "    FROM plt01.sch_session_resources a"
            "    JOIN plt01.sch_resources r ON r.resource_id = a.resource_id"
            "   WHERE a.session_id = s.session_id AND a.resource_kind = 'staff'"
            "     AND a.superseded_at IS NULL)"
            " FROM plt01.sch_sessions s"
            " JOIN plt01.sch_templates t ON t.template_id = s.template_id"
            " WHERE s.location_id = %s AND s.local_date >= %s AND s.local_date <= %s"
            "   AND (%s OR s.status = 'scheduled')"
            " ORDER BY s.starts_at",
            (location_id, from_date, to_date, include_cancelled),
        ).fetchall()
    return {
        "location_id": location_id, "location_name": where["location_name"],
        "timezone": where["timezone"], "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(), "count": len(rows),
        "sessions": [
            {"session_id": str(r[0]), "template_id": str(r[1]),
             "display_name": str(r[2]), "starts_at": r[3].isoformat(),
             "ends_at": r[4].isoformat(), "local_date": r[5].isoformat(),
             "capacity": int(r[6]), "places": int(r[6]) + int(r[7]),
             "held": int(r[10]), "free": max(0, int(r[6]) + int(r[7]) - int(r[10])),
             "status": str(r[8]), "dst_adjusted": bool(r[9]),
             # `None` rather than an empty string: a class with no coach is a gap somebody
             # has to fill, and a blank cell reads as a name nobody typed.
             "staff": str(r[11]) if r[11] else None}
            for r in rows],
        "staff_is_the_live_assignment":
            "A substitution supersedes the outgoing assignment and leaves the row, so staff "
            "is null only when no live staff assignment exists."}


def detect_session_conflicts(
    pool: Pool, tenant_id: str, session_id: str,
) -> dict[str, Any]:
    """DetectConflict for one existing session, as a read. OPS-01-R05.

    **A read, so it can be asked about something already published.** A schedule that was clean
    when it was generated stops being clean when somebody else books the room, and the only way
    to find that is to ask again -- which is why detection is pure and takes what it compares.
    """
    with tenant_scope(pool, tenant_id) as conn:
        session = _session(conn, session_id)
        chart = _resource_chart(conn)
        rows = conn.execute(
            "SELECT resource_id, resource_kind, quantity, holds_from, holds_until"
            " FROM plt01.sch_session_resources WHERE session_id = %s",
            (session_id,),
        ).fetchall()
        if not rows:
            return {"session_id": session_id, "conflicts": [], "count": 0,
                    "note": "this session holds no resources"}
        window = availability.Placement(
            starts_at=min(r[3] for r in rows), ends_at=max(r[4] for r in rows),
            location_id=session["location_id"])
        held = _held_over(
            conn, holds_from=window.starts_at, holds_until=window.ends_at)
        requirements = [
            resources.Requirement(
                kind=str(r[1]), quantity=int(r[2]), resource_id=str(r[0]))
            for r in rows]
        found = conflicts.detect(
            window, requirements, chart, held, session_id=session_id)
        for row in rows:
            if str(row[1]) != "staff":
                continue
            reason = availability.unavailable_reason(
                availability.Placement(
                    starts_at=session["starts_at"], ends_at=session["ends_at"],
                    location_id=session["location_id"]),
                _windows(conn, str(row[0])), timezone=session["timezone"])
            if reason is not None:
                found.append(conflicts.Conflict(
                    kind="unavailable", resource_id=str(row[0]), detail=reason))
    return {"session_id": session_id, "count": len(found),
            "conflicts": [{"kind": c.kind, "resource_id": c.resource_id,
                           "detail": c.detail,
                           "with_session_id": c.with_session_id} for c in found],
            "needs_override": conflicts.requires_override(found),
            "summary": conflicts.summarise(found)}


def sessions_without_staff(
    pool: Pool, tenant_id: str, *, from_date: date | None = None, days: int = 7,
) -> dict[str, Any]:
    """Scheduled sessions with no live staff assignment, and how many places are held.

    ADM-CC-01's STAFFING attention item: "Spin 19:00 Thursday has no coach -- 18 members
    booked". Two facts, and the second is what decides whether it is urgent: a class nobody has
    booked and a class with eighteen members are the same gap and a very different morning.

    **A live assignment, which is not the presence of a row.** A substitution supersedes the
    outgoing hold rather than deleting it -- the row stays so the window a past conflict was
    decided against is still readable -- so `superseded_at IS NULL` is what "has a coach"
    means. Counting rows would report a class whose coach went home ill as staffed.

    **Only `scheduled` sessions.** A cancelled class needs no coach, and a completed one is
    over; both would be noise in a queue whose whole purpose is that it is short.

    **Tenant-wide, because the Command Center is.** `schedule_for` is per location and bounded
    to 62 days; this is bounded to `days` from `from_date` and ordered by when each starts, so
    the soonest gap is first -- which is the order somebody fixing them works in.
    """
    from_date = from_date or datetime.now(UTC).date()
    if days < 1 or days > 62:
        raise InvalidRequest("a_schedule_window_is_at_most_62_days")
    to_date = from_date + timedelta(days=days)
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT s.session_id, s.template_id, t.display_name, s.starts_at, s.ends_at,"
            " s.local_date, (s.starts_at AT TIME ZONE s.timezone), s.location_id,"
            " l.location_name, s.timezone, s.capacity, s.overbook_places,"
            " coalesce((SELECT sum(h.places) FROM plt01.sch_capacity_holds h"
            "            WHERE h.session_id = s.session_id"
            "              AND h.status IN ('held', 'attended')), 0)"
            " FROM plt01.sch_sessions s"
            " JOIN plt01.sch_templates t ON t.template_id = s.template_id"
            " JOIN plt01.locations l ON l.location_id = s.location_id"
            " WHERE s.status = 'scheduled'"
            "   AND s.local_date >= %s AND s.local_date <= %s"
            "   AND NOT EXISTS ("
            "     SELECT 1 FROM plt01.sch_session_resources r"
            "      WHERE r.session_id = s.session_id"
            "        AND r.resource_kind = 'staff'"
            "        AND r.superseded_at IS NULL)"
            " ORDER BY s.starts_at, s.session_id"
            " LIMIT 200",
            (from_date, to_date),
        ).fetchall()
    sessions = [
        {"session_id": str(r[0]), "template_id": str(r[1]), "display_name": str(r[2]),
         "starts_at": r[3].isoformat(), "ends_at": r[4].isoformat(),
         "local_date": r[5].isoformat(),
         # The local wall-clock the class is advertised at, converted in the session's **own**
         # recorded zone rather than the location's current one: MOD-019 stores both the
         # instant and the zone it was converted with precisely because neither is derivable
         # from the other, and a location that changed zone must not move a past class.
         "local_starts_at": r[6].isoformat(),
         "location_id": str(r[7]), "location_name": str(r[8]), "timezone": str(r[9]),
         "capacity": int(r[10]), "places": int(r[10]) + int(r[11]), "held": int(r[12])}
        for r in rows]
    return {
        "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
        "count": len(sessions),
        "sessions": sessions,
        "members_affected": sum(int(s["held"]) for s in sessions),
        "truncated": len(sessions) == 200,
        "a_superseded_assignment_is_not_a_coach":
            "A substitution supersedes the outgoing assignment and leaves the row, so a live "
            "assignment is one with no superseded_at. Counting rows would report a class "
            "whose coach was substituted away as staffed.",
    }


def _window_key(window: availability.Window) -> tuple[str, str, str, int | None, str | None]:
    """A window's identity for matching its stored reason, which the decisions do not carry."""
    return (window.kind, window.starts_at.isoformat(), window.ends_at.isoformat(),
            window.weekday, window.on_date.isoformat() if window.on_date else None)


#: The days ADM-SCH-04's grid draws, and the ceiling on how far a caller may ask back or on.
#: A week is the unit the canvas reads ("Week of 17 August") and a rota is weekly, so a month
#: of them is as much as a screen can show without becoming a different chart.
AVAILABILITY_WEEKS = 4


def resource_week(
    pool: Pool, tenant_id: str, *, resource_id: str, from_date: date | None = None,
    weeks: int = 1, may_read_reasons: bool = False,
) -> dict[str, Any]:
    """ADM-SCH-04: one resource's rota for a week, with what is already booked on top of it.

    **`sch_availability_windows` had a writer and no reader.** `set_availability` has existed
    since the module was built and nothing in the product could show what it wrote -- the
    schedule board's own gap note says "nothing here reads a resource's availability" -- so a
    rota could be set and the only way to find out what it said was to publish a template
    against it and read the refusal. The fifth instance of this build's "a writer with no
    reader" shape.

    **Every span is in the resource's own location zone, never the session's.** That is the
    defect this module shipped and a reviewer found: `Window.timezone` was declared, stored
    from the resource's own location and read by nothing, so a London coach rostered
    09:00-17:00 was available for an 09:00 class in Amman -- 06:00 their time. A *grid* of
    somebody's week is the place that error would be most visible and least questioned, so
    the windows are read in their own zone by `availability.windows_on` and each booked
    session is converted with `AT TIME ZONE` against the resource's location.

    **A booking inside a day off is flagged, never dropped**, which is the canvas's own
    requirement: "Thursday afternoon is an exception -- he asked for it off three weeks ago.
    His 17:30 with Hala sits inside it, so the grid shows both and the booking is flagged
    rather than silently honoured or silently dropped ... reducing availability never deletes
    a booking, because the member on the other end has already been told a time." So every
    held session comes back whatever the rota says, with `availability.unavailable_reason`
    beside it.

    **A time-off window states why, and that prose is masked like a session change's.** The
    schema requires a reason on `time_off` and forbids one on a rota row, so the one window
    kind that carries free text is the one about why a person is away -- which is exactly
    where a health fact goes in practice, and MOD-017's rule that it is a health fact whatever
    column it is in. A reviewer read "she is having chemotherapy on Tuesdays" out of
    `sch_session_changes.reason` holding only the routine schedule read; this is the same
    prose one table over, so it needs `scheduling.availability.write` -- whoever may set a
    rota may read why somebody is off it. The *exception itself* is never hidden, because a
    grid that dropped it would be the rota lying about who is working.

    **Open minutes are `null` where no rota binds, not zero.** A room, a court and a bike have
    no rota in any meaningful sense and on the day a gym opens nobody has one, so "26 of 0
    hours booked" is the figure a resource with no working hours would otherwise report.
    `availability.rota_binds_on` is the same three-case reading `_is_constrained` uses.
    """
    if weeks < 1 or weeks > AVAILABILITY_WEEKS:
        raise InvalidRequest(f"the window is 1 to {AVAILABILITY_WEEKS} weeks")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT r.resource_code, r.resource_kind, r.display_name, r.quantity,"
            "       r.status, r.location_id, r.person_id,"
            "       l.location_name, l.timezone,"
            "       (now() AT TIME ZONE coalesce(l.timezone, 'UTC'))::date"
            " FROM plt01.sch_resources r"
            " LEFT JOIN plt01.locations l ON l.location_id = r.location_id"
            " WHERE r.resource_id = %s",
            (resource_id,)).fetchone()
        if row is None:
            raise NotFound("resource_not_found")
        # **A resource with no location has no zone to read a rota in.** Every window carries
        # its own, written from the location at the time it was set, so the fallback here is
        # only for the resource row's own "today" and for a window whose zone is blank -- which
        # the schema does not allow and `_applicable` still guards against.
        tz = str(row[8]) if row[8] else "UTC"
        anchor = from_date or row[9]
        days = availability.week_from(anchor)
        if weeks > 1:
            last = days[-1]
            for extra in range(1, weeks):
                days = days + availability.week_from(last + timedelta(days=1 + 7 * (extra - 1)))
        first_day, last_day = days[0], days[-1]
        windows = _windows(conn, resource_id)
        # The reasons, keyed by the same shape the decision module carries, so a window that
        # states why is matched to its prose without the pure module learning about it.
        reasons = {
            _window_key(availability.Window(
                kind=str(r[0]), timezone=str(r[1]), starts_at=r[2], ends_at=r[3],
                weekday=int(r[4]) if r[4] is not None else None, on_date=r[5])): str(r[6])
            for r in conn.execute(
                "SELECT window_kind, timezone, starts_at, ends_at, weekday, on_date, reason"
                " FROM plt01.sch_availability_windows"
                " WHERE resource_id = %s AND reason IS NOT NULL",
                (resource_id,)).fetchall()}
        # **The sessions this resource holds, and only the holds that still apply.** A
        # cancelled class does not occupy anybody and a superseded hold is a coach who was
        # substituted out -- `_held_over`'s own reasoning, which is why the predicates match
        # it rather than being written again.
        booked = conn.execute(
            "SELECT a.session_id, t.display_name, a.holds_from, a.holds_until,"
            "       (a.holds_from AT TIME ZONE %s)::date,"
            "       (a.holds_from AT TIME ZONE %s)::time,"
            "       (a.holds_until AT TIME ZONE %s)::time,"
            "       s.location_id, s.status, a.quantity"
            " FROM plt01.sch_session_resources a"
            " JOIN plt01.sch_sessions s ON s.session_id = a.session_id"
            " JOIN plt01.sch_templates t ON t.template_id = s.template_id"
            " WHERE a.resource_id = %s"
            "   AND a.superseded_at IS NULL"
            "   AND s.status = 'scheduled'"
            "   AND (a.holds_from AT TIME ZONE %s)::date BETWEEN %s AND %s"
            " ORDER BY a.holds_from, a.session_id",
            (tz, tz, tz, resource_id, tz, first_day, last_day)).fetchall()
    sessions: list[dict[str, Any]] = []
    for b in booked:
        placement = availability.Placement(
            starts_at=b[2], ends_at=b[3],
            location_id=str(b[7]) if b[7] else None)
        # The rota's own verdict on a session that is already in the diary. `None` means the
        # rota admits it; a sentence means somebody has to resolve the two.
        try:
            refusal = availability.unavailable_reason(placement, windows, timezone=tz)
        except ScheduleError as e:
            # A session that crosses local midnight cannot be checked against a day's
            # availability -- the module refuses rather than guessing which day it belongs to.
            # It is still a booking and still drawn, so the refusal becomes the reason.
            refusal = str(e)
        sessions.append({
            "session_id": str(b[0]), "label": str(b[1]),
            "local_date": b[4].isoformat(),
            "starts_at_local": b[5].strftime("%H:%M"),
            "ends_at_local": b[6].strftime("%H:%M"),
            "minutes": availability._minutes(b[5], b[6]),
            "quantity": int(b[9]),
            "conflicts_with_availability": refusal is not None,
            "conflict_reason": refusal,
        })
    booked_by_day: dict[str, int] = {}
    for one in sessions:
        booked_by_day[one["local_date"]] = (
            booked_by_day.get(one["local_date"], 0) + int(one["minutes"]))
    grid = []
    for day in days:
        key = day.isoformat()
        binds = availability.rota_binds_on(windows, day)
        grid.append({
            "date": key,
            "weekday": day.weekday(),
            "rota_binds": binds,
            "open_minutes": availability.open_minutes_on(windows, day),
            "open_spans": [
                {"starts_at": s.strftime("%H:%M"), "ends_at": e.strftime("%H:%M")}
                for s, e in availability.open_spans_on(windows, day)],
            "windows": [
                {"kind": w.kind, "timezone": w.timezone,
                 "starts_at": w.starts_at.strftime("%H:%M"),
                 "ends_at": w.ends_at.strftime("%H:%M"),
                 "recurring": w.weekday is not None,
                 # Only `time_off` carries one -- the schema requires it there and forbids it
                 # on a rota row -- so this is `None` for a working window and a break
                 # whether or not the caller may read reasons.
                 "reason": reasons.get(_window_key(w)) if may_read_reasons else None,
                 "reason_masked": (
                     not may_read_reasons and _window_key(w) in reasons)}
                for w in availability.windows_on(windows, day)],
            "booked_minutes": booked_by_day.get(key, 0),
        })
    open_total = [d["open_minutes"] for d in grid if d["open_minutes"] is not None]
    return {
        "resource_id": resource_id,
        "resource_code": str(row[0]),
        "resource_kind": str(row[1]),
        "display_name": str(row[2]),
        "quantity": int(row[3]),
        "status": str(row[4]),
        "location_id": str(row[5]) if row[5] else None,
        "location_name": str(row[7]) if row[7] else None,
        # The zone every time on this grid is in, which is the resource's own and not any
        # session's.
        "timezone": tz,
        "weeks": weeks,
        "window": {"first_day": first_day.isoformat(), "last_day": last_day.isoformat()},
        "days": grid,
        "sessions": sessions,
        # The canvas's own figure, as two numbers rather than a ratio: a session outside the
        # rota is booked and not open, so the ratio can exceed one and that case is the whole
        # point of the screen. `null` where no day in the window has a rota that binds.
        "open_minutes": sum(open_total) if open_total else None,
        "booked_minutes": sum(int(one["minutes"]) for one in sessions),
        "conflicts": sum(1 for one in sessions if one["conflicts_with_availability"]),
        "an_unconstrained_resource_has_no_open_hours":
            "open_minutes is null where no working window binds in the window asked for. A "
            "room, a court and a bike have no rota in any meaningful sense, and on the day a "
            "gym opens nobody has one -- so zero would read as 'never available' rather than "
            "'nobody wrote a rota'.",
        "a_booking_is_never_dropped":
            "Every session this resource still holds is returned whatever the rota says, with "
            "the reason the rota refuses it where it does. Reducing availability does not "
            "delete a booking: the member on the other end has already been told a time.",
        "times_are_the_resources_own_zone":
            "Every window and every session time here is read in the resource's own location "
            "timezone, not the session's. A coach's rota is a statement about where they are.",
        "a_time_off_reason_is_masked":
            "Only a time-off window carries a reason and it is prose about why a person is "
            "away, so it needs scheduling.availability.write -- whoever may set a rota may "
            "read why somebody is off it. The exception itself is always shown.",
        "a_session_kind_is_not_recorded":
            "Nothing distinguishes a class from a personal-training session in this build, so "
            "a booked hour is one state rather than two. The design draws them apart.",
    }

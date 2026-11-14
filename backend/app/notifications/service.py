"""MOD-013 ENG-02 service: templates, preferences, notifications, deliveries, suppressions.

The decisions live in `app.notifications.templates`, `preferences` and `delivery`. This module
reads rows, calls those, and writes what they return.

**The consent check is a real cross-module reference, and it is the only one in this module the
database can enforce.** MOD-009's `sec_consent_records` is on this plane and under this role, so
a marketing notification cites the consent record that permitted it with a foreign key -- not a
boolean somebody set, and not a lookup in another service that could have moved on since. The
constraint `ntf_notifications_marketing_cites_consent` makes the citation mandatory for
marketing and forbidden for anything else, so a transactional receipt cannot ride on a marketing
consent and make it look used.

**What this module cannot do, stated here rather than discovered later.**

* **Nothing sends.** There is no provider, no outbound HTTP and no SMTP. `dispatch_notification`
  claims a delivery for whatever does the sending, and `record_outcome` is written by it. A
  module that wrote "delivered" with nothing having answered would be the fabricated-evidence
  shape this codebase has been bitten by four times now.
* **No column here is for a contact address.** Everything works on a digest of one; see
  `app/notifications/delivery.py`. The consequence is that this module cannot resolve a
  recipient to an address and never tries: the caller supplies the digest it computed from the
  address it already had, one per channel, and `ntf_recipient_channels` is what keeps that
  digest answering to the same person on every later request.

  What it *can* hold is an address a dispatcher typed into free text. `ntf_suppressions.detail`,
  `ntf_deliveries.last_error` and `ntf_deliveries.provider_ref` take whatever a provider
  returned, and a bounce ordinarily quotes the address it rejected. All three are declared in
  `SUBJECT_COLUMNS`; the delivery events carry none of it, because the outbox is the one store
  no erasure in this build can reach.
* **No localization beyond selecting a template by locale.** Paragraph 2456 asks for
  localization and brand styling; a template per locale is the mechanism, and a fallback chain
  for a missing locale is a product decision the sources do not state.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from psycopg import Connection, errors

from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events
from app.notifications import delivery, preferences, templates


def _now() -> datetime:
    return datetime.now(UTC)


def _check_name(exc: errors.CheckViolation) -> str:
    return getattr(exc.diag, "constraint_name", None) or "constraint_violated"


# ------------------------------------------------------------------------------- templates

def create_template(
    pool: Pool, tenant_id: str, *, template_key: str, version: int, category: str,
    channel: str, locale: str, body: str, actor_id: str, correlation_id: str,
    subject: str = "", variables: list[str] | None = None,
) -> dict[str, Any]:
    """CreateTemplate. A draft; nothing may be authored from it until it is published."""
    candidate = templates.TemplateVersion(
        template_key=template_key, version=version, category=category, channel=channel,
        locale=locale, subject=subject, body=body, variables=tuple(variables or ()),
    )
    try:
        templates.check_version(candidate)
    except templates.TemplateError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        # The category is a property of the *message*, not of a channel: a key whose email
        # version is transactional and whose SMS version is marketing would change what a
        # fallback is allowed to do, which is paragraph 2463's separation defeated by a
        # fallback.
        sibling = conn.execute(
            "SELECT category FROM plt01.ntf_templates WHERE template_key = %s LIMIT 1",
            (template_key,),
        ).fetchone()
        if sibling is not None and sibling[0] != category:
            raise Conflict("this_template_key_already_has_another_category")
        previous = _newest_template(conn, template_key, channel, locale)
        if previous is not None:
            if version <= previous.version:
                raise Conflict("a_version_must_be_higher_than_the_last")
            try:
                templates.check_succession(previous, candidate)
            except templates.TemplateError as e:
                raise InvalidRequest(str(e)) from None
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ntf_templates
                    (tenant_id, template_key, version, category, channel, locale, subject,
                     body, variables, authored_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING template_id, created_at
                """,
                (tenant_id, template_key, version, category, channel, locale, subject, body,
                 list(variables or ()), actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("template_version_already_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"template_id": str(row[0]), "template_key": template_key, "version": version,
            "category": category, "channel": channel, "locale": locale, "status": "draft",
            "created_at": row[1].isoformat()}


def _newest_template(
    conn: Connection[Any], template_key: str, channel: str, locale: str,
) -> templates.TemplateVersion | None:
    """The newest version of one (key, channel, locale), which is what a version is of.

    Comparing against the newest version of the *key* alone would refuse an SMS version of a
    message that already has an email one -- `check_succession` forbids a channel change
    between versions, correctly, and these are not versions of each other.
    """
    row = conn.execute(
        "SELECT template_key, version, category, channel, locale, subject, body, variables"
        " FROM plt01.ntf_templates"
        " WHERE template_key = %s AND channel = %s AND locale = %s"
        " ORDER BY version DESC LIMIT 1",
        (template_key, channel, locale),
    ).fetchone()
    return None if row is None else templates.TemplateVersion(
        template_key=row[0], version=int(row[1]), category=row[2], channel=row[3],
        locale=row[4], subject=row[5], body=row[6], variables=tuple(row[7]),
    )


def approve_template(
    pool: Pool, tenant_id: str, template_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Approve a draft. **The approver may not be the author**, which the constraint enforces.

    Paragraph 2456 lists approval beside versioning, and MOD-008's separation of duties is the
    reason it is a different person: a template goes out under the tenant's name to everybody.
    """
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "UPDATE plt01.ntf_templates SET approved_at = now(), approved_by = %s"
                " WHERE template_id = %s AND status = 'draft' AND approved_at IS NULL"
                " RETURNING template_key, version",
                (actor_id, template_id),
            ).fetchone()
        except errors.CheckViolation as e:
            name = _check_name(e)
            if name == "ntf_templates_approver_is_not_the_author":
                raise Conflict("an_author_cannot_approve_their_own_template") from None
            raise InvalidRequest(name) from None
        if row is None:
            raise NotFound("unapproved_draft_template_not_found")
    return {"template_id": template_id, "template_key": row[0], "version": int(row[1]),
            "approved": True}


def publish_template(
    pool: Pool, tenant_id: str, template_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Make a version authorable. Immutable from here, by grant and by trigger."""
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "UPDATE plt01.ntf_templates SET status = 'published', published_at = now()"
                " WHERE template_id = %s AND status = 'draft' AND approved_at IS NOT NULL"
                " RETURNING template_key, version",
                (template_id,),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if row is None:
            raise Conflict("template_is_not_an_approved_draft")
    return {"template_id": template_id, "template_key": row[0], "version": int(row[1]),
            "status": "published"}


def retire_template(
    pool: Pool, tenant_id: str, template_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "UPDATE plt01.ntf_templates SET status = 'retired', retired_at = now()"
            " WHERE template_id = %s AND status = 'published' RETURNING template_key, version",
            (template_id,),
        ).fetchone()
        if row is None:
            raise NotFound("published_template_not_found")
    return {"template_id": template_id, "template_key": row[0], "version": int(row[1]),
            "status": "retired"}


def list_templates(
    pool: Pool, tenant_id: str, *, status: str | None = None,
) -> list[dict[str, Any]]:
    sql = ("SELECT template_id, template_key, version, category, channel, locale, subject,"
           " variables, status, approved_at, published_at, retired_at"
           " FROM plt01.ntf_templates")
    args: tuple[Any, ...] = ()
    if status is not None:
        sql += " WHERE status = %s"
        args = (status,)
    sql += " ORDER BY template_key, version"
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [{"template_id": str(r[0]), "template_key": r[1], "version": int(r[2]),
             "category": r[3], "channel": r[4], "locale": r[5], "subject": r[6],
             "variables": sorted(r[7]), "status": r[8],
             "approved_at": r[9].isoformat() if r[9] else None,
             "published_at": r[10].isoformat() if r[10] else None,
             "retired_at": r[11].isoformat() if r[11] else None} for r in rows]


# ----------------------------------------------------------------------------- preferences

def set_preference(
    pool: Pool, tenant_id: str, *, recipient_id: str, category: str, channel: str,
    actor_id: str, correlation_id: str, allowed: bool = True,
    quiet_from: time | None = None, quiet_until: time | None = None,
    quiet_timezone: str | None = None, daily_cap: int | None = None,
    digest_mode: str = "immediate",
) -> dict[str, Any]:
    """SetPreference, and publish `preference.changed`.

    The decision module refuses an opt-out on a category a preference may not switch off, and
    the constraint refuses it again -- deliberately both, because the Python answer is the one
    that produces a usable error and the constraint is the one that holds when somebody writes
    a second code path.
    """
    candidate = preferences.Preference(
        category=category, channel=channel, allowed=allowed, quiet_from=quiet_from,
        quiet_until=quiet_until, timezone=quiet_timezone, daily_cap=daily_cap,
        digest_mode=digest_mode,
    )
    try:
        preferences.check_preference(candidate)
    except preferences.PreferenceError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ntf_preferences
                    (tenant_id, recipient_id, category, channel, allowed, quiet_from,
                     quiet_until, quiet_timezone, daily_cap, digest_mode, set_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, recipient_id, category, channel) DO UPDATE
                SET allowed = EXCLUDED.allowed, quiet_from = EXCLUDED.quiet_from,
                    quiet_until = EXCLUDED.quiet_until,
                    quiet_timezone = EXCLUDED.quiet_timezone,
                    daily_cap = EXCLUDED.daily_cap, digest_mode = EXCLUDED.digest_mode,
                    set_by = EXCLUDED.set_by, correlation_id = EXCLUDED.correlation_id,
                    updated_at = now()
                RETURNING preference_id
                """,
                (tenant_id, recipient_id, category, channel, allowed, quiet_from, quiet_until,
                 quiet_timezone, daily_cap, digest_mode, actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        events.append_event(
            conn, tenant_id, event_type="preference.changed",
            aggregate_type="notification_preference", aggregate_id=str(row[0]),
            payload={"preference_id": str(row[0]), "recipient_id": recipient_id,
                     "category": category, "channel": channel, "allowed": allowed,
                     "digest_mode": digest_mode},
            correlation_id=correlation_id, actor_id=actor_id,
        )
    return {"preference_id": str(row[0]), "recipient_id": recipient_id, "category": category,
            "channel": channel, "allowed": allowed, "digest_mode": digest_mode,
            "daily_cap": daily_cap}


def list_preferences(
    pool: Pool, tenant_id: str, *, recipient_id: str,
) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT preference_id, category, channel, allowed, quiet_from, quiet_until,"
            " quiet_timezone, daily_cap, digest_mode, updated_at FROM plt01.ntf_preferences"
            " WHERE recipient_id = %s ORDER BY category, channel",
            (recipient_id,),
        ).fetchall()
    return [{"preference_id": str(r[0]), "category": r[1], "channel": r[2], "allowed": r[3],
             "quiet_from": r[4].isoformat() if r[4] else None,
             "quiet_until": r[5].isoformat() if r[5] else None, "quiet_timezone": r[6],
             "daily_cap": r[7], "digest_mode": r[8], "updated_at": r[9].isoformat()}
            for r in rows]


def set_channel_policy(
    pool: Pool, tenant_id: str, *, channel: str, actor_id: str, correlation_id: str,
    enabled: bool = True, fallback_channel: str | None = None,
    cost_per_message_minor: int | None = None, currency: str | None = None,
) -> dict[str, Any]:
    if cost_per_message_minor is not None and (
            not isinstance(cost_per_message_minor, int)
            or isinstance(cost_per_message_minor, bool)):
        raise InvalidRequest("a_cost_is_an_integer_in_minor_units")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ntf_channel_policies
                    (tenant_id, channel, enabled, fallback_channel, cost_per_message_minor,
                     currency, set_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, channel) DO UPDATE
                SET enabled = EXCLUDED.enabled, fallback_channel = EXCLUDED.fallback_channel,
                    cost_per_message_minor = EXCLUDED.cost_per_message_minor,
                    currency = EXCLUDED.currency, set_by = EXCLUDED.set_by,
                    correlation_id = EXCLUDED.correlation_id, updated_at = now()
                RETURNING policy_id
                """,
                (tenant_id, channel, enabled, fallback_channel, cost_per_message_minor,
                 currency, actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"policy_id": str(row[0]), "channel": channel, "enabled": enabled,
            "fallback_channel": fallback_channel,
            "cost_per_message_minor": cost_per_message_minor, "currency": currency}


def list_channel_policies(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT policy_id, channel, enabled, fallback_channel, cost_per_message_minor,"
            " currency, updated_at FROM plt01.ntf_channel_policies ORDER BY channel"
        ).fetchall()
    return [{"policy_id": str(r[0]), "channel": r[1], "enabled": r[2],
             "fallback_channel": r[3],
             "cost_per_message_minor": int(r[4]) if r[4] is not None else None,
             "currency": r[5], "updated_at": r[6].isoformat()} for r in rows]


# ---------------------------------------------------------------------------- notifications

#: How long a digest window runs for each mode.
_DIGEST_WINDOWS = {"hourly": timedelta(hours=1), "daily": timedelta(days=1)}


def request_notification(
    pool: Pool, tenant_id: str, *, template_key: str, recipient_id: str,
    address_digests: dict[str, str], idempotency_key: str, actor_id: str, correlation_id: str,
    variables: dict[str, str] | None = None, locale: str | None = None,
    priority: str = "normal", bypass_policy_ref: str | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """RequestNotification: decide, render, author, and never send.

    The order matters and each step refuses for a different reason.

    1. **The template is resolved to a published version**, and its category is read from the
       row rather than taken from the caller. A caller able to declare the category would be
       able to declare a campaign transactional and escape both the consent requirement and the
       recipient's opt-out -- which is paragraph 2463's control, defeated by a request field.
    2. **A marketing notification needs a live consent record**, found here and cited by foreign
       key. Not a boolean, and not a call to another service that may have moved on.
    3. **The channel is resolved before anything is evaluated against it.** The channel
       policy may send this somewhere other than the template's own channel, and the
       preference, the suppression list, the frequency count and the address digest are all
       per-channel facts. Reading them for the channel the message is no longer going to is
       four controls defeated by one ordering, which is what the first version did.
    4. **The recipient and the address digest are bound to each other**, in both directions, so
       a suppression recorded against a digest is reachable from every later request for that
       person. Neither key can be verified against a real address here -- there is none on this
       plane -- but correspondence and stability are what the controls actually rest on.
    5. **The preference, the suppression list and the frequency cap decide the outcome**, in
       that order, in `preferences.decide`.
    6. **The text is rendered and stored.** The template may be retired tomorrow; what was sent
       is what somebody will ask about.
    7. The notification is authored whatever the outcome -- including `suppressed`. A request
       that vanished because a preference said no is a request nobody can account for when the
       member asks why they never heard anything.
    """
    moment = at or _now()
    if not idempotency_key.strip():
        raise InvalidRequest("an_idempotency_key_cannot_be_blank")
    if not address_digests:
        raise InvalidRequest("a_request_carries_an_address_digest_per_channel")
    for supplied_digest in address_digests.values():
        if not delivery.DIGEST_RE.fullmatch(supplied_digest):
            raise InvalidRequest("an_address_digest_is_a_sha256_hex_digest")
    with tenant_scope(pool, tenant_id) as conn:
        template_id, template = _published_template(conn, template_key, locale)
        requested_channel = template.channel

        consent_record_id: str | None = None
        if template.needs_consent:
            consent_record_id = _live_consent(conn, recipient_id, template.category)
            if consent_record_id is None:
                raise Conflict("no_live_consent_for_a_marketing_notification")

        # **Resolve the channel first.** Everything below is read for the channel this is
        # actually going to, which is the finding: a tenant falling back from email to SMS --
        # the ordinary response to a provider outage, and exactly when volume gets re-routed --
        # had the email preference, the email suppression check and the email address digest
        # applied to an SMS. A fallback also uses the text written for the channel it falls
        # back *to*: an email subject on an SMS is text that goes nowhere. No template there
        # means no fallback, suppressed with a reason somebody can read.
        enabled, fallback = _channel_policy(conn, requested_channel)
        channel, route_refusal = preferences.resolve_channel(
            requested_channel, channel_enabled=enabled, fallback_channel=fallback)
        if channel is not None and channel != requested_channel:
            try:
                template_id, template = _published_template(
                    conn, template_key, template.locale, channel)
            except NotFound:
                channel, route_refusal = None, "no_template_for_the_fallback_channel"
        # The channel reverts with the refusal: a suppressed notification labelled with a
        # channel it was never rendered for is internally inconsistent, which
        # `ntf_notifications_subject_matches_channel` refuses outright.
        send_channel = channel if channel is not None else requested_channel
        try:
            subject, body = templates.render(template, variables or {})
        except templates.TemplateError as e:
            raise InvalidRequest(str(e)) from None

        address_digest = address_digests.get(send_channel)
        if address_digest is None:
            raise InvalidRequest(f"no_address_digest_for_channel_{send_channel}")
        _bind_recipient_channel(
            conn, tenant_id, recipient_id=recipient_id, channel=send_channel,
            address_digest=address_digest, actor_id=actor_id, correlation_id=correlation_id)

        preference: preferences.Preference | None = None
        if route_refusal is not None:
            decided = preferences.Decision(
                outcome="suppress", reason=route_refusal, channel=send_channel)
        else:
            preference = _preference(conn, recipient_id, template.category, send_channel)
            suppressed = _is_suppressed(conn, send_channel, address_digest)
            sent_today = _sent_today(
                conn, recipient_id, template.category, send_channel, moment)
            try:
                decided = preferences.decide(
                    preferences.Request(
                        category=template.category, channel=send_channel, priority=priority,
                        bypass_policy_ref=bypass_policy_ref, sent_today=sent_today,
                        suppressed=suppressed),
                    preference, at=moment,
                )
            except preferences.PreferenceError as e:
                raise InvalidRequest(str(e)) from None
        status = {"send": "requested", "defer": "deferred", "digest": "digested",
                  "suppress": "suppressed"}[decided.outcome]
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.ntf_notifications
                    (tenant_id, template_id, template_key, template_version, category,
                     channel, locale, rendered_subject, rendered_body, recipient_id,
                     address_digest, priority, bypass_policy_ref, status, decision_reason,
                     consent_record_id, idempotency_key, scheduled_for, requested_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s)
                RETURNING notification_id, requested_at
                """,
                (tenant_id, template_id, template.template_key, template.version,
                 template.category, send_channel, template.locale,
                 subject, body, recipient_id, address_digest, priority, bypass_policy_ref,
                 status, decided.reason, consent_record_id, idempotency_key,
                 decided.send_after, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            # The request side of paragraph 2464: a caller that asks twice -- because its own
            # retry fired, or because MOD-010 redelivered the event -- authors one notification.
            raise Conflict("this_notification_was_already_requested") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        notification_id = str(row[0])

        if decided.outcome == "digest":
            _fold_into_digest(conn, tenant_id, notification_id=notification_id,
                              recipient_id=recipient_id, category=template.category,
                              channel=send_channel,
                              mode=(preference.digest_mode if preference else "daily"),
                              at=moment)
        # **A deferred notification gets its delivery row too, due when the quiet window
        # ends.** Without one `dispatch_notification` answered "no delivery is due" for ever,
        # so quiet hours silently dropped the message rather than delaying it -- including a
        # transactional one, and including the `status IN ('requested', 'deferred')` clause in
        # the dispatcher, which was unreachable. "Quiet hours defer, they do not suppress" was
        # a comment rather than a behaviour. Found by review.
        if decided.outcome in ("send", "defer"):
            conn.execute(
                "INSERT INTO plt01.ntf_deliveries"
                " (tenant_id, notification_id, channel, next_attempt_at)"
                " VALUES (%s, %s, %s, %s)",
                (tenant_id, notification_id, send_channel, decided.send_after),
            )
        events.append_event(
            conn, tenant_id, event_type="notification.requested",
            aggregate_type="notification", aggregate_id=notification_id,
            payload={"notification_id": notification_id, "template_key": template.template_key,
                     "category": template.category,
                     "channel": send_channel,
                     "recipient_id": recipient_id, "outcome": decided.outcome,
                     "reason": decided.reason},
            correlation_id=correlation_id, actor_id=actor_id,
        )
    return {"notification_id": notification_id, "status": status,
            "outcome": decided.outcome, "reason": decided.reason,
            "channel": send_channel,
            "category": template.category, "template_version": template.version,
            "scheduled_for": decided.send_after.isoformat() if decided.send_after else None,
            "consent_record_id": consent_record_id,
            "requested_at": row[1].isoformat()}


def _published_template(
    conn: Connection[Any], template_key: str, locale: str | None,
    channel: str | None = None,
) -> tuple[str, templates.TemplateVersion]:
    """The published version of a template, in the requested locale, with its row id.

    No fallback chain for a missing locale: picking one is a product decision the sources do not
    state, and quietly sending English to somebody who asked for Arabic is worse than refusing.

    The id travels beside the contract rather than inside it, so the thing passed to
    `templates.render` is the same dataclass the pure module validates and nothing else -- a
    near-identical lookalike would be a second definition of a template version.
    """
    sql = ("SELECT template_id, template_key, version, category, channel, locale, subject,"
           " body, variables FROM plt01.ntf_templates"
           " WHERE template_key = %s AND status = 'published'")
    args: list[Any] = [template_key]
    if locale is not None:
        sql += " AND locale = %s"
        args.append(locale)
    if channel is not None:
        sql += " AND channel = %s"
        args.append(channel)
    sql += " ORDER BY version DESC LIMIT 1"
    row = conn.execute(sql, tuple(args)).fetchone()
    if row is None:
        raise NotFound("no_published_template_for_this_key_and_locale")
    return str(row[0]), templates.TemplateVersion(
        template_key=row[1], version=int(row[2]), category=row[3], channel=row[4],
        locale=row[5], subject=row[6], body=row[7], variables=tuple(row[8]),
    )


def _live_consent(
    conn: Connection[Any], recipient_id: str, category: str,
) -> str | None:
    """The consent record that permits a marketing notification to this recipient.

    Reads MOD-009's table directly, which is allowed and correct: it is on this plane, under
    this role, and the alternative -- asking a service that may have moved on, or trusting a
    flag -- is what makes a consent check decorative. The *latest* action per definition wins,
    because a withdrawal after a grant is a withdrawal.

    **A tie goes to the withdrawal.** `signed_at` is caller-supplied, so two records can carry
    the same instant, and the first version let `ORDER BY signed_at DESC LIMIT 1` pick between
    them -- which means a recorded withdrawal could read as live consent depending on the plan.
    MOD-009's `consent.latest` resolves a tie the other way, keeping the later row in the order
    it was handed; that is right for a function reading a list somebody assembled and wrong
    here, where the only safe reading of "we cannot tell which came last" is that permission
    was not clearly given. Different on purpose, and said so because the divergence is the kind
    of thing a reader would otherwise take for a bug.
    """
    row = conn.execute(
        """
        SELECT record_id FROM plt01.sec_consent_records r
        WHERE r.subject_id = %s
          AND r.definition_id IN (
              SELECT definition_id FROM plt01.sec_consent_definitions
              WHERE consent_type = %s)
          AND r.action = 'granted'
          AND NOT EXISTS (
              SELECT 1 FROM plt01.sec_consent_records later
              WHERE later.subject_id = r.subject_id
                AND later.definition_id = r.definition_id
                AND (later.signed_at > r.signed_at
                     OR (later.signed_at = r.signed_at AND later.action <> 'granted')))
        ORDER BY r.signed_at DESC LIMIT 1
        """,
        (recipient_id, category),
    ).fetchone()
    return None if row is None else str(row[0])


def _bind_recipient_channel(
    conn: Connection[Any], tenant_id: str, *, recipient_id: str, channel: str,
    address_digest: str, actor_id: str, correlation_id: str,
) -> None:
    """Tie the recipient and the address digest together, and refuse a contradiction.

    The module is handed two caller-supplied keys: `recipient_id`, which the preference, the
    quiet window and the frequency cap are keyed on, and `address_digest`, which the
    suppression list is keyed on. Both were shape-checked and nothing related them, so every
    control split down the middle and each half failed open -- a digest that is not the
    recipient's finds no suppression and gets the complainant mailed, and a `person_id` where
    an `identity_id` was meant misses the preference while
    `GET /notifications/preferences` still shows the opt-out standing. Found by review.

    **This cannot check that a digest is really that person's address**, because there is no
    address on this plane to hash -- that is the point of the design. What it enforces is
    correspondence and stability, which is what those controls actually rest on: the first
    binding wins, and a later request contradicting it in either direction is refused.

    Rebinding is `rebind_recipient_channel`, under its own stronger permission.
    """
    try:
        conn.execute(
            """
            INSERT INTO plt01.ntf_recipient_channels
                (tenant_id, recipient_id, channel, address_digest, bound_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, recipient_id, channel) DO NOTHING
            """,
            (tenant_id, recipient_id, channel, address_digest, actor_id, correlation_id),
        )
    except errors.UniqueViolation:
        # `ntf_recipient_channels_one_owner`: this digest is already somebody else's on this
        # channel. The realistic input is a person id supplied where an identity id was meant.
        raise Conflict("this_address_digest_belongs_to_another_recipient") from None
    row = conn.execute(
        "SELECT address_digest FROM plt01.ntf_recipient_channels"
        " WHERE recipient_id = %s AND channel = %s",
        (recipient_id, channel),
    ).fetchone()
    assert row is not None
    if str(row[0]) != address_digest:
        raise Conflict("this_recipient_is_bound_to_a_different_address_on_this_channel")


def rebind_recipient_channel(
    pool: Pool, tenant_id: str, *, recipient_id: str, channel: str, address_digest: str,
    reason: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Move a recipient's address binding on one channel, with an actor and a written reason.

    An address does change, and without this a member who changes their email is unreachable
    for ever. It is a stronger permission than requesting a notification because it is the one
    act that moves a person away from a suppression recorded against them -- a bounce or a
    complaint is keyed on the digest, so rebinding is how somebody would walk around one.
    """
    if not reason.strip():
        raise InvalidRequest("a_rebinding_states_a_reason")
    if not delivery.DIGEST_RE.fullmatch(address_digest):
        raise InvalidRequest("an_address_digest_is_a_sha256_hex_digest")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            updated = conn.execute(
                "UPDATE plt01.ntf_recipient_channels SET address_digest = %s,"
                " rebound_at = now(), rebound_by = %s, rebind_reason = %s,"
                " rebind_correlation_id = %s WHERE recipient_id = %s AND channel = %s",
                (address_digest, actor_id, reason, correlation_id, recipient_id, channel),
            ).rowcount
        except errors.UniqueViolation:
            raise Conflict("this_address_digest_belongs_to_another_recipient") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if updated == 0:
            raise NotFound("this_recipient_has_no_binding_on_this_channel")
    return {"recipient_id": recipient_id, "channel": channel,
            "address_digest": address_digest, "rebound": True}


def list_recipient_channels(
    pool: Pool, tenant_id: str, recipient_id: str,
) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT channel, address_digest, bound_at, rebound_at, rebind_reason"
            " FROM plt01.ntf_recipient_channels WHERE recipient_id = %s ORDER BY channel",
            (recipient_id,),
        ).fetchall()
    return [{"channel": r[0], "address_digest": r[1], "bound_at": r[2].isoformat(),
             "rebound_at": r[3].isoformat() if r[3] else None,
             "rebind_reason": r[4]} for r in rows]


def _preference(
    conn: Connection[Any], recipient_id: str, category: str, channel: str,
) -> preferences.Preference | None:
    row = conn.execute(
        "SELECT allowed, quiet_from, quiet_until, quiet_timezone, daily_cap, digest_mode"
        " FROM plt01.ntf_preferences"
        " WHERE recipient_id = %s AND category = %s AND channel = %s",
        (recipient_id, category, channel),
    ).fetchone()
    return None if row is None else preferences.Preference(
        category=category, channel=channel, allowed=row[0], quiet_from=row[1],
        quiet_until=row[2], timezone=row[3], daily_cap=row[4], digest_mode=row[5],
    )


def _channel_policy(conn: Connection[Any], channel: str) -> tuple[bool, str | None]:
    row = conn.execute(
        "SELECT enabled, fallback_channel FROM plt01.ntf_channel_policies WHERE channel = %s",
        (channel,),
    ).fetchone()
    # No policy means the channel is usable. A tenant that has configured nothing should be
    # able to send, and a default of "disabled" would make the first notification a mystery.
    return (True, None) if row is None else (bool(row[0]), row[1])


def _is_suppressed(conn: Connection[Any], channel: str, address_digest: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM plt01.ntf_suppressions"
        " WHERE channel = %s AND address_digest = %s AND released_at IS NULL",
        (channel, address_digest),
    ).fetchone()
    return row is not None


def _sent_today(
    conn: Connection[Any], recipient_id: str, category: str, channel: str, at: datetime,
) -> int:
    """How many of this category this recipient has had on this channel in the rolling day.

    Counts notifications that were actually authored for sending -- `requested` and
    `dispatched` -- and not the ones a preference already suppressed or digested. A cap that
    counted suppressed notifications would tighten itself every time it fired.

    Per channel, because the cap it feeds is: `ntf_preferences` is keyed on category *and*
    channel, so a count across channels compared against one channel's cap is two different
    questions joined by a variable name.
    """
    row = conn.execute(
        "SELECT count(*) FROM plt01.ntf_notifications"
        " WHERE recipient_id = %s AND category = %s AND channel = %s AND requested_at > %s"
        "   AND status IN ('requested', 'dispatched')",
        (recipient_id, category, channel, at - timedelta(days=1)),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _fold_into_digest(
    conn: Connection[Any], tenant_id: str, *, notification_id: str, recipient_id: str,
    category: str, channel: str, mode: str, at: datetime,
) -> None:
    """Add a digested notification to the open batch for its window, opening one if needed."""
    span = _DIGEST_WINDOWS.get(mode, timedelta(days=1))
    window_start = at.replace(minute=0, second=0, microsecond=0)
    if span >= timedelta(days=1):
        window_start = window_start.replace(hour=0)
    row = conn.execute(
        """
        INSERT INTO plt01.ntf_digests
            (tenant_id, recipient_id, category, channel, window_start, window_end,
             notification_count)
        -- The count starts at one, because this statement is adding one. Omitting it took the
        -- column default of zero and only the DO UPDATE branch incremented, so every digest
        -- ever opened reported one fewer notification than it held.
        VALUES (%s, %s, %s, %s, %s, %s, 1)
        ON CONFLICT (tenant_id, recipient_id, category, channel, window_start)
            WHERE state = 'open'
        DO UPDATE SET notification_count = plt01.ntf_digests.notification_count + 1
        RETURNING digest_id
        """,
        (tenant_id, recipient_id, category, channel, window_start, window_start + span),
    ).fetchone()
    assert row is not None
    conn.execute(
        "INSERT INTO plt01.ntf_digest_entries (tenant_id, digest_id, notification_id)"
        " VALUES (%s, %s, %s)",
        (tenant_id, str(row[0]), notification_id),
    )


# ------------------------------------------------------------------- dispatch and outcomes

def dispatch_notification(
    pool: Pool, tenant_id: str, notification_id: str, *, actor_id: str, correlation_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """DispatchNotification: claim the delivery for whatever does the sending.

    **Nothing here sends.** This marks the delivery as attempted and counts the attempt; the
    provider is somebody else's and `record_outcome` is written by it.

    `AND state IN ('pending', 'failed')` and an explicit attempt count. The delivery row is
    unique per (notification, channel), which is the transport half of paragraph 2464: a
    dispatcher that sent a message, timed out and retried settles the row it already holds
    rather than creating a second delivery of one authored message.

    **The claim pushes `next_attempt_at` out by `delivery.CLAIM_LEASE`.** The first version set
    it to NULL, which the claim query reads as "due now", so five calls handed one message to
    five dispatchers and the row recorded five attempts against one send. A lease is not a
    lock -- a dispatcher slower than the lease can still be joined -- but the row is no longer
    handed out to everybody who asks.

    **The suppression list is re-read here, not only at request time.** A bounce or an
    unsubscribe between the request and the dispatch is the ordinary case: a quiet-hours defer
    can sit for eight hours. MOD-009's rule -- a control consulted once is a control with a
    window -- and the window here is the whole point of deferring.
    """
    at = now or _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT d.delivery_id, d.attempts, d.max_attempts, d.channel, n.status,"
            " n.address_digest"
            " FROM plt01.ntf_deliveries d"
            " JOIN plt01.ntf_notifications n ON n.notification_id = d.notification_id"
            " WHERE d.notification_id = %s AND d.state IN ('pending', 'failed')"
            "   AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= %s)",
            (notification_id, at),
        ).fetchone()
        if row is None:
            raise Conflict("no_delivery_is_due_for_this_notification")
        if row[4] == "suppressed":
            raise Conflict("notification_was_suppressed")
        if int(row[1]) >= int(row[2]):
            raise Conflict("delivery_has_no_attempts_left")
        if _is_suppressed(conn, str(row[3]), str(row[5])):
            # Settled rather than refused: the delivery records that it was considered and
            # deliberately not sent, which is the evidence a member's complaint needs.
            #
            # **And the refusal is raised after the commit, not here.** `tenant_scope` rolls
            # back on a raise, so raising inside this block would take the settlement with it
            # -- the rule MOD-007 and MOD-008 each paid for, and which this path reintroduced:
            # the test asserting the notification reads `suppressed` is what caught it.
            conn.execute(
                "UPDATE plt01.ntf_deliveries SET state = 'suppressed', next_attempt_at = NULL"
                " WHERE delivery_id = %s AND state IN ('pending', 'failed')",
                (row[0],),
            )
            conn.execute(
                "UPDATE plt01.ntf_notifications SET status = 'suppressed'"
                " WHERE notification_id = %s AND status IN ('requested', 'deferred')",
                (notification_id,),
            )
            refusal = Conflict("address_was_suppressed_after_this_was_requested")
        else:
            refusal = None
            claimed = conn.execute(
                "UPDATE plt01.ntf_deliveries SET attempts = attempts + 1,"
                " dispatched_at = now(), next_attempt_at = %s"
                " WHERE delivery_id = %s AND state IN ('pending', 'failed')"
                "   AND (next_attempt_at IS NULL OR next_attempt_at <= %s)",
                (at + delivery.CLAIM_LEASE, row[0], at),
            ).rowcount
            # Safe to raise inside the block: this one has written nothing worth keeping, and
            # rolling the whole thing back is what should happen when the claim was lost.
            if claimed == 0:
                raise Conflict("this_delivery_was_claimed_by_somebody_else")
            conn.execute(
                "UPDATE plt01.ntf_notifications SET status = 'dispatched'"
                " WHERE notification_id = %s AND status IN ('requested', 'deferred')",
                (notification_id,),
            )
    if refusal is not None:
        raise refusal
    return {"notification_id": notification_id, "delivery_id": str(row[0]),
            "channel": row[3], "attempts": int(row[1]) + 1,
            "claim_expires_at": (at + delivery.CLAIM_LEASE).isoformat(),
            "dispatched_at": at.isoformat()}


def record_outcome(
    pool: Pool, tenant_id: str, notification_id: str, *, outcome: str, actor_id: str,
    correlation_id: str, error: str | None = None, provider_ref: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """RecordDeliveryOutcome, written by whatever actually sent the message.

    A **bounce or a complaint suppresses the address in the same transaction**. That is
    paragraph 2460's requirement, and doing it here rather than in a later sweep is what stops
    the next notification to that address going out before anybody noticed: the suppression and
    the delivery that caused it commit together or neither does.

    Each outcome publishes its own event, because `notification.sent`, `.delivered` and
    `.failed` are different things to a consumer -- one is a handoff, one is a confirmation and
    one is a problem.
    """
    at = now or _now()
    if error is not None and not error.strip():
        raise InvalidRequest("an_error_cannot_be_blank")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT delivery_id, state, attempts, max_attempts, channel, dispatched_at"
            " FROM plt01.ntf_deliveries WHERE notification_id = %s",
            (notification_id,),
        ).fetchone()
        if row is None:
            raise NotFound("delivery_not_found")
        # **An outcome is reported by whoever claimed the delivery.** Without this the routine
        # AAL-1 dispatch permission reached further than "claim and settle": it could settle any
        # pending delivery in the tenant as delivered, or report a bounce on one and write the
        # suppression that follows -- irreversible state, since only an unsubscribe may be
        # released. Raised as non-blocking by review; the bound the catalogue claims for this
        # permission is only true with it.
        if row[5] is None:
            raise Conflict("this_delivery_has_not_been_dispatched")
        try:
            verdict = delivery.outcome_verdict(
                outcome=outcome, attempts=max(1, int(row[2])),
                max_attempts=int(row[3]), now=at)
            delivery.check_transition(str(row[1]), verdict.state)
        except delivery.DeliveryError as e:
            raise Conflict(str(e)) from None
        if verdict.state in ("failed", "dead") and not (error or "").strip():
            raise InvalidRequest("a_failed_delivery_records_what_went_wrong")
        # The guard is `state = <what we read>`, and **the row count is checked**. Without
        # that a dispatcher whose claim had already been settled by another one reported an
        # outcome nothing recorded -- and published the event for it, so a consumer saw a
        # delivery that the table never agreed had happened, and a redelivery could be
        # scheduled for a message already delivered.
        settled = conn.execute(
            "UPDATE plt01.ntf_deliveries SET state = %s, attempts = %s, last_error = %s,"
            " next_attempt_at = %s, provider_ref = coalesce(%s, provider_ref),"
            " delivered_at = CASE WHEN %s = 'delivered' THEN now() END"
            " WHERE delivery_id = %s AND state = %s",
            (verdict.state, verdict.attempts, (error or None), verdict.next_attempt_at,
             provider_ref, verdict.state, row[0], row[1]),
        ).rowcount
        if settled == 0:
            raise Conflict("this_delivery_was_settled_by_somebody_else")
        suppression_id: str | None = None
        if verdict.suppress_reason is not None:
            suppression_id = _suppress(
                conn, tenant_id, channel=str(row[4]),
                address_digest=_digest_of(conn, notification_id),
                reason=verdict.suppress_reason, actor_id=actor_id,
                correlation_id=correlation_id,
                detail=f"{verdict.suppress_reason} reported for delivery {row[0]}",
            )
        event = {"sent": "notification.sent", "delivered": "notification.delivered",
                 "failed": "notification.failed", "bounced": "notification.failed",
                 "complained": "notification.failed"}[outcome]
        events.append_event(
            conn, tenant_id, event_type=event, aggregate_type="notification",
            aggregate_id=notification_id,
            # **The provider's error text does not go in the event.** `error` is free text
            # from whatever sent the message, and the ordinary contents of an SMTP rejection
            # are `550 5.1.1 <jane@example.com>: Recipient address rejected` -- so the realistic
            # input, with nobody trying, put a contact address into `evt_outbox.payload`, the
            # one store no erasure here can reach, in the module whose defining property is
            # that it holds no contact address. MOD-010's rule: the restricted-field check
            # reads declared names and a value can carry anything. The text stays on
            # `ntf_deliveries.last_error`, where a holder of the delivery permission can read
            # it and an erasure can overwrite it; the event carries the outcome and the state,
            # which is what a consumer acts on.
            payload={"notification_id": notification_id, "channel": str(row[4]),
                     "state": verdict.state, "attempts": verdict.attempts,
                     "outcome": outcome},
            correlation_id=correlation_id, actor_id=actor_id,
        )
    return {"notification_id": notification_id, "state": verdict.state,
            "attempts": verdict.attempts,
            "next_attempt_at": (verdict.next_attempt_at.isoformat()
                                if verdict.next_attempt_at else None),
            "suppression_id": suppression_id}


def _digest_of(conn: Connection[Any], notification_id: str) -> str:
    row = conn.execute(
        "SELECT address_digest FROM plt01.ntf_notifications WHERE notification_id = %s",
        (notification_id,),
    ).fetchone()
    if row is None:
        raise NotFound("notification_not_found")
    return str(row[0])


def _suppress(
    conn: Connection[Any], tenant_id: str, *, channel: str, address_digest: str, reason: str,
    actor_id: str | None, correlation_id: str, detail: str | None = None,
) -> str:
    # `DO NOTHING`, then read the row that is already there. The upsert version wanted UPDATE
    # on `detail`, and granting it would let somebody rewrite the evidence behind a suppression
    # -- the opposite of what this table is for. An address already suppressed does not need
    # its reason restated, and the first record is the one that matters.
    row = conn.execute(
        """
        INSERT INTO plt01.ntf_suppressions
            (tenant_id, channel, address_digest, reason, detail, recorded_by, correlation_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, channel, address_digest) WHERE released_at IS NULL
        DO NOTHING
        RETURNING suppression_id
        """,
        (tenant_id, channel, address_digest, reason, detail, actor_id, correlation_id),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT suppression_id FROM plt01.ntf_suppressions"
            " WHERE channel = %s AND address_digest = %s AND released_at IS NULL",
            (channel, address_digest),
        ).fetchone()
    assert row is not None
    return str(row[0])


def suppress_address(
    pool: Pool, tenant_id: str, *, channel: str, address_digest: str, reason: str,
    correlation_id: str, actor_id: str | None = None, detail: str | None = None,
) -> dict[str, Any]:
    """SuppressNotification: add an address to the list without a delivery having failed.

    The ordinary caller is an unsubscribe link. `address_digest` rather than an address, because
    this module holds no contact data -- the caller computes the digest from the address it
    already has, and `delivery.address_digest` is the one function that does it.

    **Only `unsubscribed` may be recorded this way**, because only an unsubscribe may be
    released. A bounce or a complaint is the channel's judgement about deliverability and
    `release_suppression` refuses to lift one -- correctly -- so a route that let a caller
    *declare* one handed an AAL-1 routine permission the power to block an address from every
    transactional notice for ever, with no remedy anywhere in the module. The genuine ones are
    written by `record_outcome` from a reported delivery outcome, which is where the
    judgement actually comes from.
    """
    if reason != "unsubscribed":
        raise InvalidRequest("only_an_unsubscribe_may_be_recorded_by_hand")
    if reason not in delivery.SUPPRESSION_REASONS:
        raise InvalidRequest(f"unknown_suppression_reason_{reason}")
    if not delivery.DIGEST_RE.fullmatch(address_digest):
        raise InvalidRequest("an_address_digest_is_a_sha256_hex_digest")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            suppression_id = _suppress(
                conn, tenant_id, channel=channel, address_digest=address_digest,
                reason=reason, actor_id=actor_id, correlation_id=correlation_id, detail=detail)
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    return {"suppression_id": suppression_id, "channel": channel, "reason": reason}


def release_suppression(
    pool: Pool, tenant_id: str, suppression_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Lift a suppression. **Only an unsubscribe may be lifted.**

    A bounce or a complaint is the channel's judgement about deliverability, and a tenant that
    could clear those would be choosing to keep sending to an address that rejected them --
    which damages the chance of every other notification arriving, including the transactional
    ones nobody opted out of. The decision module refuses it and the constraint refuses it
    again.
    """
    if not reason.strip():
        raise InvalidRequest("a_release_states_a_reason")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT reason FROM plt01.ntf_suppressions"
            " WHERE suppression_id = %s AND released_at IS NULL",
            (suppression_id,),
        ).fetchone()
        if row is None:
            raise NotFound("live_suppression_not_found")
        try:
            delivery.check_release(str(row[0]))
        except delivery.DeliveryError as e:
            raise Conflict(str(e)) from None
        conn.execute(
            "UPDATE plt01.ntf_suppressions SET released_at = now(), released_by = %s,"
            " release_reason = %s, release_correlation_id = %s WHERE suppression_id = %s",
            (actor_id, reason, correlation_id, suppression_id),
        )
    return {"suppression_id": suppression_id, "released": True, "was": str(row[0])}


def list_suppressions(
    pool: Pool, tenant_id: str, *, channel: str | None = None,
    include_released: bool = False, limit: int = 50,
) -> list[dict[str, Any]]:
    sql = ["SELECT suppression_id, channel, address_digest, reason, detail, recorded_at,"
           " released_at FROM plt01.ntf_suppressions"]
    where: list[str] = []
    args: list[Any] = []
    if channel is not None:
        where.append("channel = %s")
        args.append(channel)
    if not include_released:
        where.append("released_at IS NULL")
    if where:
        sql.append(" WHERE " + " AND ".join(where))
    sql.append(" ORDER BY recorded_at DESC LIMIT %s")
    args.append(max(1, min(limit, 500)))
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute("".join(sql), tuple(args)).fetchall()
    return [{"suppression_id": str(r[0]), "channel": r[1], "address_digest": r[2],
             "reason": r[3], "detail": r[4], "recorded_at": r[5].isoformat(),
             "released_at": r[6].isoformat() if r[6] else None} for r in rows]


def list_notifications(
    pool: Pool, tenant_id: str, *, recipient_id: str | None = None,
    status: str | None = None, limit: int = 50,
) -> list[dict[str, Any]]:
    """The notification list. **The rendered body is not returned here.**

    A list route that carried the message text would be a read path to everything this tenant
    has ever said to anybody, under one permission -- which is MOD-010's lateral-read finding
    against `events.event.read`. The text is on the detail route, behind its own permission.
    """
    sql = ["SELECT notification_id, template_key, template_version, category, channel,"
           " locale, recipient_id, priority, status, decision_reason, requested_at"
           " FROM plt01.ntf_notifications"]
    where: list[str] = []
    args: list[Any] = []
    if recipient_id is not None:
        where.append("recipient_id = %s")
        args.append(recipient_id)
    if status is not None:
        where.append("status = %s")
        args.append(status)
    if where:
        sql.append(" WHERE " + " AND ".join(where))
    sql.append(" ORDER BY requested_at DESC LIMIT %s")
    args.append(max(1, min(limit, 500)))
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute("".join(sql), tuple(args)).fetchall()
    return [{"notification_id": str(r[0]), "template_key": r[1],
             "template_version": int(r[2]), "category": r[3], "channel": r[4],
             "locale": r[5], "recipient_id": str(r[6]), "priority": r[7], "status": r[8],
             "decision_reason": r[9], "requested_at": r[10].isoformat()} for r in rows]


def get_notification(pool: Pool, tenant_id: str, notification_id: str) -> dict[str, Any]:
    """One notification with the text that was sent, and its delivery state."""
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT n.template_key, n.template_version, n.category, n.channel, n.locale,"
            " n.rendered_subject, n.rendered_body, n.recipient_id, n.priority, n.status,"
            " n.decision_reason, n.bypass_policy_ref, n.consent_record_id, n.scheduled_for,"
            " n.requested_at, d.state, d.attempts, d.last_error, d.delivered_at"
            " FROM plt01.ntf_notifications n"
            " LEFT JOIN plt01.ntf_deliveries d ON d.notification_id = n.notification_id"
            " WHERE n.notification_id = %s",
            (notification_id,),
        ).fetchone()
        if row is None:
            raise NotFound("notification_not_found")
    return {"notification_id": notification_id, "template_key": row[0],
            "template_version": int(row[1]), "category": row[2], "channel": row[3],
            "locale": row[4], "rendered_subject": row[5], "rendered_body": row[6],
            "recipient_id": str(row[7]), "priority": row[8], "status": row[9],
            "decision_reason": row[10], "bypass_policy_ref": row[11],
            "consent_record_id": str(row[12]) if row[12] else None,
            "scheduled_for": row[13].isoformat() if row[13] else None,
            "requested_at": row[14].isoformat(),
            "delivery": None if row[15] is None else {
                "state": row[15], "attempts": int(row[16]), "last_error": row[17],
                "delivered_at": row[18].isoformat() if row[18] else None}}


def list_digests(
    pool: Pool, tenant_id: str, *, recipient_id: str | None = None,
    state: str | None = None, limit: int = 50,
) -> list[dict[str, Any]]:
    sql = ["SELECT digest_id, recipient_id, category, channel, window_start, window_end,"
           " state, notification_count FROM plt01.ntf_digests"]
    where: list[str] = []
    args: list[Any] = []
    if recipient_id is not None:
        where.append("recipient_id = %s")
        args.append(recipient_id)
    if state is not None:
        where.append("state = %s")
        args.append(state)
    if where:
        sql.append(" WHERE " + " AND ".join(where))
    sql.append(" ORDER BY window_start DESC LIMIT %s")
    args.append(max(1, min(limit, 500)))
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute("".join(sql), tuple(args)).fetchall()
    return [{"digest_id": str(r[0]), "recipient_id": str(r[1]), "category": r[2],
             "channel": r[3], "window_start": r[4].isoformat(),
             "window_end": r[5].isoformat(), "state": r[6],
             "notification_count": int(r[7])} for r in rows]

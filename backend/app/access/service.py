"""MOD-022's I/O: the access decision, its evidence, and the three planes it joins.

**The pipeline derives every fact it decides on.** `evaluate_access` takes a point and a
presented credential and nothing else that bears on the answer: the zone comes from the point,
the device from the point, the local time from the location's own timezone in SQL, the person
from the credential, the membership state from MOD-017, the entitlement from MOD-017's own
`entitlements.usable`, the age from MOD-014, the occupancy from this module's events and the
anti-passback window from the policy. **Every one of those was a field a caller could have
sent**, and six modules running have shipped a control keyed on exactly such a field.

What this file owns that the decision modules cannot:

  * **The decision and the unlock commit together.** A granted decision issues MOD-021's
    `unlock_momentary` on *this* connection, inside the transaction that records the decision.
    A door that opened with no decision row is an entry nobody can account for; a decision row
    with no command is a member standing at a locked door being told they were admitted.
    MOD-010's `append_event` argument, where the state is a barrier.
  * **The replay cache is written before the policy is read.** Paragraph 4183 puts the
    recent-token check before policy evaluation, and the reason is not only ordering: a
    replayed token that reached the policy would read a member's entitlements on the strength
    of a screenshot.
  * **An entitlement is checked and never drawn.** Walking through a door is not spending a
    class, so this module reads `entitlements.usable` and writes no reservation. The draw
    belongs to whatever books the session.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from psycopg import Connection, errors

from app.access import credentials, occupancy, offline, passback, policy, zones
from app.commercial import entitlements
from app.commercial import service as commercial
from app.db import Pool, tenant_scope
from app.devices import service as devices
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events


def _now() -> datetime:
    return datetime.now(UTC)


def _check_name(error: errors.CheckViolation) -> str:
    name = getattr(error.diag, "constraint_name", None)
    return str(name) if name else "constraint_violation"


# ------------------------------------------------------------------------- zones


def declare_zone(
    pool: Pool, tenant_id: str, *, location_id: str, zone_key: str, display_name: str,
    risk_class: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """An area a policy applies to, with the risk class that bounds its offline authorization.

    Paragraph 4160 makes a high-risk zone's snapshot TTL two hours against twelve. That is the
    only thing the risk class buys, and it is the reason the zone is a row.
    """
    try:
        zones.check_risk_class(risk_class)
        name = _required(display_name, "display_name", 120)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "INSERT INTO plt01.acc_zones"
                " (tenant_id, location_id, zone_key, display_name, risk_class,"
                "  created_by, correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING zone_id",
                (tenant_id, location_id, zone_key.strip().lower(), name, risk_class,
                 actor_id, correlation_id)).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_zone_key_is_already_declared") from None
        except errors.ForeignKeyViolation:
            raise NotFound("location_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    ceiling = zones.snapshot_ceiling(risk_class)
    return {"zone_id": str(row[0]), "zone_key": zone_key.strip().lower(),
            "risk_class": risk_class,
            "snapshot_ceiling_seconds": int(ceiling.total_seconds()),
            "detail": ("nothing decides anything here until a policy is published and an "
                       "access point is commissioned")}


def retire_zone(
    pool: Pool, tenant_id: str, zone_id: str, *, reason: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("retiring_a_zone_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        moved = conn.execute(
            "UPDATE plt01.acc_zones SET status = 'retired', retired_at = %s,"
            " retired_by = %s, retire_reason = %s, retire_correlation_id = %s"
            " WHERE zone_id = %s AND status = 'active'",
            (moment, actor_id, reason.strip(), correlation_id, zone_id)).rowcount
        if moved == 0:
            exists = conn.execute(
                "SELECT status FROM plt01.acc_zones WHERE zone_id = %s",
                (zone_id,)).fetchone()
            if exists is None:
                raise NotFound("zone_not_found")
            raise Conflict(f"this_zone_is_{exists[0]}")
    return {"zone_id": zone_id, "status": "retired",
            "detail": ("the decisions and events recorded here stay; what stops is new "
                       "policy and new points")}


def reclassify_zone(
    pool: Pool, tenant_id: str, zone_id: str, *, risk_class: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Tighten a zone's risk class. **Loosening is refused by the trigger, not here.**

    A gym that decides the weights room is high-risk is making an assessment; one that quietly
    moves it back is extending the life of every offline authorization issued for it
    afterwards with no record that the assessment changed. Retire the zone and declare the
    replacement.
    """
    try:
        zones.check_risk_class(risk_class)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        try:
            moved = conn.execute(
                "UPDATE plt01.acc_zones SET risk_class = %s WHERE zone_id = %s"
                " AND status = 'active'",
                (risk_class, zone_id)).rowcount
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if moved == 0:
            raise NotFound("zone_not_found")
    return {"zone_id": zone_id, "risk_class": risk_class,
            "snapshot_ceiling_seconds": int(
                zones.snapshot_ceiling(risk_class).total_seconds())}


# ------------------------------------------------------------------------ points


def commission_point(
    pool: Pool, tenant_id: str, *, zone_id: str, device_id: str, direction: str,
    display_name: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Put a MOD-021 device at a zone, facing one way.

    **The direction is the one field with a life-safety consequence.** Paragraph 4177 puts
    egress outside the Veyro application path, so an `exit` reader records that somebody left
    and never decides -- and `acc_decision_is_coherent` refuses a decision against one, in the
    database, rather than leaving it to a service that could be bypassed.

    **The device has to be able to move a barrier**, which the trigger checks: a point declared
    over a barcode reader is a zone whose policy nothing can enforce.
    """
    try:
        zones.check_direction(direction)
        name = _required(display_name, "display_name", 120)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "INSERT INTO plt01.acc_points"
                " (tenant_id, zone_id, device_id, direction, display_name, created_by,"
                "  correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING point_id",
                (tenant_id, zone_id, device_id, direction, name, actor_id,
                 correlation_id)).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_device_is_already_an_access_point") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(
                "zone_not_found" if "zone" in str(e) else "device_not_found") from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
    return {"point_id": str(row[0]), "zone_id": zone_id, "device_id": device_id,
            "direction": direction, "decides_entry": zones.decides_entry(direction),
            "detail": ("an exit reader records and never decides; egress is not conditioned "
                       "on membership, reachability or software authorization")}


def retire_point(
    pool: Pool, tenant_id: str, point_id: str, *, reason: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("retiring_an_access_point_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        moved = conn.execute(
            "UPDATE plt01.acc_points SET status = 'retired', retired_at = %s,"
            " retired_by = %s, retire_reason = %s, retire_correlation_id = %s"
            " WHERE point_id = %s AND status = 'active'",
            (moment, actor_id, reason.strip(), correlation_id, point_id)).rowcount
        if moved == 0:
            exists = conn.execute(
                "SELECT status FROM plt01.acc_points WHERE point_id = %s",
                (point_id,)).fetchone()
            if exists is None:
                raise NotFound("access_point_not_found")
            raise Conflict(f"this_access_point_is_{exists[0]}")
    return {"point_id": point_id, "status": "retired"}


def _required(value: str, what: str, limit: int) -> str:
    folded = (value or "").strip()
    if not folded:
        raise ValueError(f"{what} is stated")
    if len(folded) > limit:
        raise ValueError(f"{what} is at most {limit} characters")
    return folded


# ---------------------------------------------------------------------- policies


def draft_policy(
    pool: Pool, tenant_id: str, *, zone_id: str, opens_minute: int | None,
    closes_minute: int | None, requires_entitlement: bool,
    max_balance_minor: int | None, min_age_years: int | None,
    anti_passback_seconds: int, capacity: int | None, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """A draft of the terms a decision will cite. Nothing decides against it until published.

    **The version number is derived, not taken.** A caller choosing its own version is a
    caller that can overwrite the terms a past decision cited.
    """
    with tenant_scope(pool, tenant_id) as conn:
        zone = conn.execute(
            "SELECT status FROM plt01.acc_zones WHERE zone_id = %s FOR UPDATE",
            (zone_id,)).fetchone()
        if zone is None:
            raise NotFound("zone_not_found")
        # The status was selected and discarded -- MOD-016's "a status selected and discarded
        # is a control that does not exist". A retired zone has no active points, so the
        # release would answer `points_released: 0` and read as a success during an
        # evacuation. Saying which zone is retired is the useful answer.
        if str(zone[0]) != "active":
            raise Conflict(f"this_zone_is_{zone[0]}_and_releases_nothing")
        if zone[0] != "active":
            raise Conflict(f"this_zone_is_{zone[0]}")
        version = conn.execute(
            "SELECT coalesce(max(version), 0) + 1 FROM plt01.acc_policies"
            " WHERE zone_id = %s", (zone_id,)).fetchone()
        assert version is not None
        try:
            row = conn.execute(
                "INSERT INTO plt01.acc_policies"
                " (tenant_id, zone_id, version, opens_minute, closes_minute,"
                "  requires_entitlement, max_balance_minor, min_age_years,"
                "  anti_passback_seconds, capacity, created_by, correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " RETURNING policy_id",
                (tenant_id, zone_id, int(version[0]), opens_minute, closes_minute,
                 requires_entitlement, max_balance_minor, min_age_years,
                 anti_passback_seconds, capacity, actor_id, correlation_id)).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.DataError:
            raise InvalidRequest("a_policy_figure_is_out_of_range") from None
        assert row is not None
    return {"policy_id": str(row[0]), "zone_id": zone_id, "version": int(version[0]),
            "status": "draft",
            "detail": ("a draft decides nothing; publishing it is a second act by a second "
                       "person, because this is who gets through a door")}


def publish_policy(
    pool: Pool, tenant_id: str, policy_id: str, *, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Settle the terms, and retire whatever was live for this zone in the same transaction.

    **Two acts by two people**, which `acc_policies_publisher_is_not_author` holds and this
    refusal only explains. MOD-016's discount approval and MOD-017's contract version are the
    precedent; the thing being settled here is who gets through a door.

    **The outgoing policy is retired here, not separately.** `acc_policies_one_live_per_zone`
    admits one published row per zone, so a publication that left the old one live would fail
    the index -- and a two-call version would leave a window with no live policy at all, in
    which every decision refuses.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT zone_id, version, status, created_by, published_by"
            " FROM plt01.acc_policies WHERE policy_id = %s FOR UPDATE",
            (policy_id,)).fetchone()
        if row is None:
            raise NotFound("policy_not_found")
        zone_id, version, status, created_by, published_by = row
        if str(status) == "published":
            # Idempotent to the caller: a client whose request timed out after the commit is
            # told the policy is live rather than 409. MOD-017's finding, three commands.
            if str(published_by) != actor_id:
                raise Conflict("this_policy_was_published_by_somebody_else")
            return {"policy_id": policy_id, "zone_id": str(zone_id),
                    "version": int(version), "status": "published", "repeated": True}
        if str(status) != "draft":
            raise Conflict(f"this_policy_is_{status}")
        if str(created_by) == actor_id:
            raise Conflict("a_policy_is_published_by_somebody_other_than_its_author")
        superseded = conn.execute(
            "UPDATE plt01.acc_policies SET status = 'retired', retired_at = %s,"
            " retired_by = %s, retire_reason = %s, retire_correlation_id = %s"
            " WHERE zone_id = %s AND status = 'published'"
            " RETURNING policy_id",
            (moment, actor_id, f"superseded by version {int(version)}", correlation_id,
             zone_id)).fetchone()
        try:
            conn.execute(
                "UPDATE plt01.acc_policies SET status = 'published', published_at = %s,"
                " published_by = %s, publish_correlation_id = %s WHERE policy_id = %s",
                (moment, actor_id, correlation_id, policy_id))
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
    return {"policy_id": policy_id, "zone_id": str(zone_id), "version": int(version),
            "status": "published", "repeated": False,
            "superseded": None if superseded is None else str(superseded[0]),
            "detail": ("decisions from here on cite this version; the ones already recorded "
                       "keep citing the terms they were made against")}


# ------------------------------------------------------------------- credentials


def issue_credential(
    pool: Pool, tenant_id: str, *, person_id: str, kind: str, credential_value: str,
    expires_at: datetime | None, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Bind a credential to a person. **It identifies them and authorizes nothing.**

    The raw value is hashed here and nowhere stored: paragraph 4161 requires the edge snapshot
    to carry "only pseudonymous credential hashes", and a table that held the card number
    would be the copy the snapshot is forbidden to replicate.
    """
    try:
        credentials.check_kind(kind)
        digest = credentials.digest_of(credential_value)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "INSERT INTO plt01.acc_credentials"
                " (tenant_id, person_id, kind, credential_digest, expires_at, issued_by,"
                "  correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING credential_id",
                (tenant_id, person_id, kind, digest, expires_at, actor_id,
                 correlation_id)).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_credential_is_already_enrolled") from None
        except errors.ForeignKeyViolation:
            raise NotFound("person_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        credential_id = str(row[0])
        _append(conn, tenant_id, "access_credential.issued", "credential", credential_id,
                {"credential_id": credential_id, "person_id": person_id, "kind": kind},
                actor_id=actor_id, correlation_id=correlation_id)
    return {"credential_id": credential_id, "person_id": person_id, "kind": kind,
            "rotating": kind in credentials.ROTATING_KINDS,
            "detail": ("this credential identifies its holder; whether a door opens is a "
                       "policy decision made against facts it does not carry")}


def revoke_credential(
    pool: Pool, tenant_id: str, credential_id: str, *, reason: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Withdraw a credential, and bump its epoch so every stale snapshot is behind.

    **One transaction**, for MOD-021's reason: a gateway compares the epoch numerically, so a
    revocation committing before the bump is a window in which the credential still opens
    doors. Paragraph 4184's point is the other half -- revoking the credential does not
    change the member's identity, so the person keeps their record and gets a new card.
    """
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("revoking_a_credential_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT person_id, state FROM plt01.acc_credentials"
            " WHERE credential_id = %s FOR UPDATE", (credential_id,)).fetchone()
        if row is None:
            raise NotFound("credential_not_found")
        if str(row[1]) == "revoked":
            raise Conflict("this_credential_is_already_revoked")
        try:
            conn.execute(
                "UPDATE plt01.acc_credentials SET state = 'revoked', revoked_at = %s,"
                " revoked_by = %s, revoke_reason = %s, revoke_correlation_id = %s,"
                " revocation_epoch = revocation_epoch + 1"
                " WHERE credential_id = %s AND state <> 'revoked'",
                (moment, actor_id, reason.strip(), correlation_id, credential_id))
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        epoch = conn.execute(
            "SELECT revocation_epoch FROM plt01.acc_credentials WHERE credential_id = %s",
            (credential_id,)).fetchone()
        assert epoch is not None
        _append(conn, tenant_id, "access.revoked", "credential", credential_id,
                {"credential_id": credential_id, "person_id": str(row[0]),
                 "revocation_epoch": int(epoch[0])},
                actor_id=actor_id, correlation_id=correlation_id)
    return {"credential_id": credential_id, "state": "revoked",
            "revocation_epoch": int(epoch[0]),
            "person_identity_unchanged": True,
            "detail": ("every reader holding a snapshot built before this epoch is behind a "
                       "withdrawal and refuses rather than admits")}


def _append(
    conn: Connection[Any], tenant_id: str, event_type: str, aggregate_type: str,
    aggregate_id: str, payload: dict[str, Any], *, actor_id: str, correlation_id: str,
) -> None:
    """MOD-010's outbox, on this connection, in this transaction.

    A pool-taking wrapper here would be the bug: a decision that committed without its event,
    or an event for a decision that rolled back, is the state nothing can reconcile.
    """
    events.append_event(
        conn, tenant_id, event_type=event_type, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, payload=payload, actor_id=actor_id,
        correlation_id=correlation_id)


# -------------------------------------------------------------- the decision path


def _point(conn: Connection[Any], point_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT p.point_id, p.zone_id, p.device_id, p.direction, p.status,"
        "       z.risk_class, z.status, z.location_id,"
        "       extract(hour FROM now() AT TIME ZONE l.timezone) * 60"
        "       + extract(minute FROM now() AT TIME ZONE l.timezone)"
        " FROM plt01.acc_points p"
        " JOIN plt01.acc_zones z ON z.zone_id = p.zone_id AND z.tenant_id = p.tenant_id"
        " JOIN plt01.locations l ON l.location_id = z.location_id"
        "   AND l.tenant_id = z.tenant_id"
        " WHERE p.point_id = %s FOR UPDATE OF p",
        (point_id,)).fetchone()
    if row is None:
        raise NotFound("access_point_not_found")
    return {"point_id": str(row[0]), "zone_id": str(row[1]), "device_id": str(row[2]),
            "direction": str(row[3]), "status": str(row[4]), "risk_class": str(row[5]),
            "zone_status": str(row[6]), "location_id": str(row[7]),
            "local_minute": int(row[8])}


def _live_policy(conn: Connection[Any], zone_id: str) -> policy.ZonePolicy | None:
    row = conn.execute(
        "SELECT policy_id, version, opens_minute, closes_minute, requires_entitlement,"
        "       max_balance_minor, min_age_years, anti_passback_seconds, capacity"
        " FROM plt01.acc_policies WHERE zone_id = %s AND status = 'published'",
        (zone_id,)).fetchone()
    if row is None:
        return None
    return policy.ZonePolicy(
        policy_id=str(row[0]), version=int(row[1]),
        opens_minute=None if row[2] is None else int(row[2]),
        closes_minute=None if row[3] is None else int(row[3]),
        requires_entitlement=bool(row[4]),
        max_balance_minor=None if row[5] is None else int(row[5]),
        min_age_years=None if row[6] is None else int(row[6]),
        anti_passback_seconds=int(row[7]),
        capacity=None if row[8] is None else int(row[8]))


def _binding(conn: Connection[Any], digest: str) -> credentials.Binding | None:
    """The enrolment behind a presented value, read under a share lock.

    **`FOR SHARE`, which is the right strength here and not the wrong one.** This file's rules
    say a trigger deciding whether a child may be written needs `FOR UPDATE`, because two
    share locks do not conflict with each other. This is the other case: what must not happen
    is a revocation committing between this read and the unlock issued in the same
    transaction, and `revoke_credential` takes `FOR UPDATE` -- which a share lock does block.
    Taking `FOR UPDATE` here instead would serialise every presentation at every door against
    every other, which is the cost without the benefit.
    """
    row = conn.execute(
        "SELECT credential_id, person_id, kind, state, issued_at, expires_at,"
        "       revocation_epoch"
        " FROM plt01.acc_credentials WHERE credential_digest = %s FOR SHARE",
        (digest,)).fetchone()
    if row is None:
        return None
    return credentials.Binding(
        credential_id=str(row[0]), person_id=str(row[1]), kind=str(row[2]),
        state=str(row[3]), issued_at=row[4], expires_at=row[5],
        revocation_epoch=int(row[6]))


def _subject(
    conn: Connection[Any], person_id: str, *, location_id: str, at: datetime,
) -> policy.Subject:
    """Every fact the decision reads, from the module that owns it.

    **Not one of these came off the request**, which is the whole point. MOD-017 owns the
    membership and the entitlement, MOD-014 owns the date of birth, and the balance is a sum
    over MOD-017's own issued invoices. A credential carries none of them.
    """
    person = conn.execute(
        "SELECT date_of_birth FROM plt01.ppl_persons WHERE person_id = %s",
        (person_id,)).fetchone()
    if person is None:
        raise NotFound("person_not_found")
    dob = person[0]
    age = None
    if dob is not None:
        born = at.date()
        age = born.year - dob.year - ((born.month, born.day) < (dob.month, dob.day))
    # **The membership a door reads is one that is live *now*, not the newest row.**
    #
    # The first version took `ORDER BY starts_on DESC LIMIT 1` and read only `status`, which
    # was wrong in both directions and reachable without trying. Fail-open:
    # `activate_membership` writes `status = 'active'` whatever `starts_on` says, so a member
    # who signed up in advance was admitted months before their membership began.
    # Fail-closed: a member whose main membership is live and who cancelled a second one was
    # refused their own gym, because the cancelled row started later and won the sort -- and
    # told "see the front desk", with the real reason behind a permission a front desk does
    # not hold.
    #
    # And the standing one `CLAUDE.md` names: `cancel_membership` with a notice period writes
    # `ends_on` and leaves `status = 'active'`, and nothing in this build applies it on a
    # schedule -- so a row that reads `active` can be a membership that ended last month.
    # Reading the dates here is what makes "a cancelled membership whose entitlements still
    # work is access nobody is paying for" not also true of the door.
    #
    # The order is deliberate: **any live membership admits**, so a member with two is judged
    # on the one that lets them in rather than on whichever sorts first. Where none is live,
    # the most recently started row is what the refusal names, because that is the one the
    # front desk will be asked about.
    today = at.date()
    membership = conn.execute(
        "SELECT status FROM plt01.mem_memberships"
        " WHERE person_id = %s AND starts_on <= %s"
        "   AND (ends_on IS NULL OR ends_on >= %s)"
        "   AND status IN ('active', 'trialing')"
        " ORDER BY starts_on DESC, membership_number LIMIT 1",
        (person_id, today, today)).fetchone()
    if membership is None:
        membership = conn.execute(
            "SELECT status FROM plt01.mem_memberships WHERE person_id = %s"
            " ORDER BY starts_on DESC, membership_number LIMIT 1",
            (person_id,)).fetchone()
        if membership is not None and str(membership[0]) in ("active", "trialing"):
            # A row that calls itself active while its own dates say otherwise. Naming it
            # `expired` is the truth and keeps the refusal inside the closed reason set.
            membership = ("expired",)
    # **MOD-017 owns the figure.** Summing it here would be a second definition of one
    # balance, which is MOD-018's finding about two functions that disagreed about what was
    # in a till.
    owed = commercial.outstanding_minor_on(conn, person_id)
    has, reason = _entitled(conn, person_id, location_id=location_id, at=at)
    # **A health or safety hold is not a column in this build.** MOD-014's health classes are
    # unreachable to every caller, so a door cannot read one, and inventing a boolean here
    # would be a control with no writer -- MOD-020's "a declared value nothing writes". The
    # field stays on `Subject` because the decision order is part of the contract, and it is
    # always False with that said out loud in `access_gaps`.
    return policy.Subject(
        person_id=person_id,
        membership_state=None if membership is None else str(membership[0]),
        has_entitlement=has, entitlement_reason=reason,
        balance_minor=owed,
        age_years=age, safety_hold=False)


def _entitled(
    conn: Connection[Any], person_id: str, *, location_id: str, at: datetime,
) -> tuple[bool, str | None]:
    """Whether any grant admits this person here, now. **Checked, never drawn.**

    Walking through a door is not spending a class, so this reads `entitlements.usable` and
    writes no reservation. The draw belongs to whatever books the session; a module that
    consumed a credit per entry would charge a member for using the building.
    """
    scope = conn.execute(
        "SELECT b.brand_id,"
        "       extract(hour FROM %s AT TIME ZONE l.timezone) * 60"
        "       + extract(minute FROM %s AT TIME ZONE l.timezone)"
        " FROM plt01.locations l JOIN plt01.brands b ON b.brand_id = l.brand_id"
        "   AND b.tenant_id = l.tenant_id"
        " WHERE l.location_id = %s", (at, at, location_id)).fetchone()
    brand_id = None if scope is None else str(scope[0])
    local_minute = None if scope is None else int(scope[1])
    rows = conn.execute(
        "SELECT g.grant_id, g.person_id, g.is_counted, g.granted_quantity, g.valid_from,"
        "       g.valid_to, g.brand_id, g.location_id, g.status, g.usable_from_minute,"
        "       g.usable_to_minute,"
        "       coalesce((SELECT sum(e.delta) FROM plt01.mem_entitlement_ledger e"
        "                  WHERE e.grant_id = g.grant_id), 0)"
        " FROM plt01.mem_entitlement_grants g"
        " WHERE g.person_id = %s AND g.status = 'active'"
        " ORDER BY g.valid_from DESC", (person_id,)).fetchall()
    last: str | None = None
    for row in rows:
        grant = entitlements.Grant(
            grant_id=str(row[0]), is_counted=bool(row[2]),
            granted_quantity=None if row[3] is None else int(row[3]),
            valid_from=row[4], valid_to=row[5],
            brand_id=None if row[6] is None else str(row[6]),
            location_id=None if row[7] is None else str(row[7]),
            status=str(row[8]),
            usable_from_minute=None if row[9] is None else int(row[9]),
            usable_to_minute=None if row[10] is None else int(row[10]))
        verdict = entitlements.usable(
            grant, at=at, quantity=1,
            balance=int(row[11]) if grant.is_counted else None,
            location_id=location_id, brand_id=brand_id, local_minute=local_minute)
        if verdict.ok:
            return True, None
        # **The first refusal, not the last.** The rows are `ORDER BY valid_from DESC`, so
        # overwriting kept the *oldest* grant's reason -- a member whose current pass is out
        # of hours was told about a membership that lapsed two years ago.
        if last is None:
            last = verdict.reason
    return False, last or "this member holds nothing that admits them here"


def evaluate_access(
    pool: Pool, tenant_id: str, *, point_id: str, credential_value: str,
    idempotency_key: str, actor_id: str, correlation_id: str,
    reported_direction: str = "entry",
    rotation_counter: int | None = None,
    nonce: str | None = None, token_issued_at: datetime | None = None,
    token_expires_at: datetime | None = None,
    reader_clock_at: datetime | None = None, at: datetime | None = None,
) -> dict[str, Any]:
    """EvaluateAccess. Paragraph 1935's pipeline, in the order paragraph 4183 requires.

    Identify the person, resolve the credential, evaluate entitlement and policy, then actuate
    -- and the credential half finishes before the policy half starts, because evaluating
    policy for a replayed token would read a member's entitlements on the strength of a
    screenshot.

    **The decision and the unlock commit together.** A granted decision issues MOD-021's
    `unlock_momentary` on this connection. A door that opened with no decision is an entry
    nobody can account for; a decision with no command is a member being told they were
    admitted while standing at a locked door.

    **Every refusal is recorded**, and the way it is done here is that a refusal is a *row*
    rather than an exception: `_record` writes the decision and returns it, so there is no
    raise inside `tenant_scope` to roll the evidence back. MOD-007's `_settled` helper exists
    for modules whose refusals have to raise; this one had a copy of it that was never called,
    and a reviewer pointed out that the one raise which did happen inside the block -- the
    replay insert aborting the transaction -- was the case it was written to prevent. That is
    fixed with a savepoint in `_resolve`, which is the right tool, and the unused helper is
    gone rather than left as a claim.
    """
    moment = at or _now()
    key = _required(idempotency_key, "idempotency_key", 200)
    # **Measured against this server's instant, not taken from the device.** A reader that
    # sends no clock is treated as in step, which is the only honest default: an unknown skew
    # is not a large one, and refusing every reader that does not report its clock would shut
    # every door that predates the field.
    skew = timedelta(0) if reader_clock_at is None else reader_clock_at - moment
    with tenant_scope(pool, tenant_id) as conn:
        stored = _namespaced("evaluate", key)
        digest = credentials.digest_of(credential_value)
        prior = conn.execute(
            "SELECT decision_id, granted, code, public_reason, masked, point_id,"
            "       credential_id"
            " FROM plt01.acc_decisions WHERE idempotency_key = %s", (stored,)).fetchone()
        if prior is not None:
            # **The repeat is answered only when the request is the same request.** It used to
            # compare the key and nothing else, so a reader that reused a per-shift counter
            # with a *different, revoked* card was told "granted" and handed the previous
            # member's decision id. The point and the credential are what the command takes;
            # both are compared.
            seen = _binding(conn, digest)
            same_credential = (
                (None if seen is None else seen.credential_id)
                == (None if prior[6] is None else str(prior[6])))
            if str(prior[5]) != point_id or not same_credential:
                raise _repeat_mismatch("evaluate", key)
            return {"decision_id": str(prior[0]), "granted": bool(prior[1]),
                    "code": policy.public_code(str(prior[2])),
                    "public_reason": str(prior[3]),
                    "reason_withheld": bool(prior[4]), "repeated": True}
        point = _point(conn, point_id)
        # **Nothing is decided on the way out, at any reader.** An `exit` point never decides
        # -- a reader wired the wrong way round is a commissioning mistake somebody has to
        # see, so the refusal is recorded rather than thrown. A `both` lane decides on the way
        # in and not on the way out, which is the half this used to get wrong.
        if not zones.decides_for(point["direction"], reported_direction):
            facing_out = policy.refuse(
                "point_not_an_entry",
                "nothing is decided on the way out; egress is not conditioned on membership, "
                "reachability or software authorization")
            return _record(conn, tenant_id, point, facing_out, key=stored,
                           credential_id=None, person_id=None, at=moment,
                           actor_id=actor_id, correlation_id=correlation_id,
                           mode="online", scope="global", occupancy_seen=None,
                           snapshot_id=None)
        posture, mode = _posture(conn, point["device_id"], skew=skew, at=moment)
        binding = _binding(conn, digest)
        # **The kind is the enrolment's, and a reader does not get a say.**
        #
        # It used to be `kind or binding.kind`, taking the caller's word when one was sent --
        # and `kind` decides which controls run at all: `check_clock`, `check_presentation`
        # and the replay-cache insert are each guarded by `presented.kind in ROTATING_KINDS`.
        # So a free-text field on the request body switched off paragraph 4183's entire token
        # validation. A reviewer enrolled a `qr_rotating` credential, sent
        # `{"kind": "nfc_card"}` with a captured token and was admitted -- then again, and
        # again, with no window, no counter, no nonce, no replay cache and no clock refusal,
        # each repetition issuing MOD-021's unlock. `check_kind` was never reached either, so
        # any forty-character string did it.
        #
        # This is the module's own "derive, never accept" standard, broken on the one field
        # that chooses which rules apply -- MOD-017's `reserve_entitlement` finding, where a
        # caller sent the grant's own brand id, in a worse place. The fallback for an unknown
        # credential is irrelevant to the outcome: with no binding the decision is
        # `credential_unknown` whatever kind it is called.
        presented = credentials.Presented(
            digest=digest, kind=binding.kind if binding else "physical_card",
            presented_at=moment, rotation_counter=rotation_counter, nonce=nonce,
            issued_at=token_issued_at, expires_at=token_expires_at)
        resolved, credential_id, person_id = _resolve(
            conn, point, binding=binding, presented=presented, posture=posture,
            mode=mode, at=moment, correlation_id=correlation_id)
        decision: policy.Decision
        occupancy_seen: int | None = None
        if resolved is None:
            assert binding is not None
            live = _live_policy(conn, point["zone_id"])
            if live is None:
                decision = policy.refuse(
                    "zone_closed", "no published policy admits anybody to this zone")
            else:
                occupancy_seen = _capacity_seen(
                    conn, point["zone_id"], location_id=point["location_id"], at=moment)
                subject = _subject(conn, binding.person_id,
                                   location_id=point["location_id"], at=moment)
                decision = policy.decide(
                    subject=subject, policy=live, local_minute=point["local_minute"],
                    at=moment,
                    seconds_since_last_entry=_seconds_since_entry(
                        conn, binding.credential_id, zone_id=point["zone_id"], at=moment),
                    occupancy=occupancy_seen)
        else:
            decision = resolved
        return _record(
            conn, tenant_id, point, decision, key=stored, credential_id=credential_id,
            person_id=person_id, at=moment, actor_id=actor_id,
            correlation_id=correlation_id, mode=mode,
            # **`global` because this decision read every entry in the zone**, which is what
            # `passback.claim` is about -- not whether the device had filed a health report in
            # the last five minutes. Keying it on `mode` recorded `controller_group` on
            # essentially every server-side decision and understated the guarantee the module
            # actually made.
            scope=passback.claim(online=True),
            occupancy_seen=occupancy_seen, snapshot_id=posture_snapshot(posture))


def posture_snapshot(posture: offline.Posture | None) -> str | None:
    """The snapshot id a decision cites, where there is one. Paragraph 1952's reference."""
    return None if posture is None else getattr(posture, "snapshot_id", None)


def _posture_at(
    conn: Connection[Any], device_id: str, *, when: datetime,
) -> offline.Posture | None:
    """The device's posture **as it was when something happened**, for reconciliation.

    `_posture` reads the latest snapshot, which is the right answer for a decision being made
    now and the wrong one for judging a decision made hours ago: see the comment in
    `reconcile_offline_access`. This selects the snapshot whose own window covers `when`, so
    publishing a fresh one cannot retroactively excuse a decision taken on a stale one -- and
    a decision taken when the reader held nothing finds nothing here either.
    """
    row = conn.execute(
        "SELECT d.revocation_epoch, s.snapshot_id, s.revocation_epoch, s.issued_at,"
        "       s.expires_at"
        " FROM plt01.dev_devices d"
        " LEFT JOIN LATERAL ("
        "   SELECT snapshot_id, revocation_epoch, issued_at, expires_at"
        "     FROM plt01.dev_policy_snapshots"
        "    WHERE tenant_id = d.tenant_id AND device_id = d.device_id"
        "      AND issued_at <= %s AND expires_at > %s"
        "    ORDER BY issued_at DESC LIMIT 1) s ON true"
        " WHERE d.device_id = %s", (when, when, device_id)).fetchone()
    if row is None:
        return None
    return offline.Posture(
        mode="offline", snapshot_issued_at=row[3], snapshot_expires_at=row[4],
        snapshot_epoch=None if row[2] is None else int(row[2]),
        device_epoch=int(row[0]), clock_skew=timedelta(0),
        snapshot_id=None if row[1] is None else str(row[1]))


def _posture(
    conn: Connection[Any], device_id: str, *, skew: timedelta, at: datetime,
) -> tuple[offline.Posture | None, str]:
    """What this reader's own situation is, derived from facts the server can see.

    **A device that reports its own mode reports the mode it would like to be in**, so the
    posture comes from the clock skew measured against the server's instant and from when the
    device last reported -- not from a field. The snapshot is MOD-021's latest for this
    device, read here because the decision has to cite the exact one.
    """
    row = conn.execute(
        "SELECT d.revocation_epoch, d.last_seen_at, s.snapshot_id, s.revocation_epoch,"
        "       s.issued_at, s.expires_at"
        " FROM plt01.dev_devices d"
        " LEFT JOIN LATERAL ("
        "   SELECT snapshot_id, revocation_epoch, issued_at, expires_at"
        "     FROM plt01.dev_policy_snapshots"
        "    WHERE tenant_id = d.tenant_id AND device_id = d.device_id"
        "    ORDER BY issued_at DESC LIMIT 1) s ON true"
        " WHERE d.device_id = %s", (device_id,)).fetchone()
    if row is None:
        raise NotFound("device_not_found")
    mode = offline.mode_for(clock_skew=skew, last_sync_at=row[1], at=at)
    posture = offline.Posture(
        mode=mode, snapshot_issued_at=row[4], snapshot_expires_at=row[5],
        snapshot_epoch=None if row[3] is None else int(row[3]),
        device_epoch=int(row[0]), clock_skew=skew,
        snapshot_id=None if row[2] is None else str(row[2]))
    return posture, mode


def _resolve(
    conn: Connection[Any], point: dict[str, Any], *, binding: credentials.Binding | None,
    presented: credentials.Presented, posture: offline.Posture | None, mode: str,
    at: datetime, correlation_id: str,
) -> tuple[policy.Decision | None, str | None, str | None]:
    """The credential half. Returns `None` for the decision when the policy half should run.

    Paragraph 4183's order: signature, scope, revocation epoch and the recent-token replay
    cache, **before** policy evaluation. The signature is the reader's own claim and this
    build has no vault to check it against, which is said rather than implied; the window and
    the replay cache are checked here and are not the reader's word for anything.
    """
    if point["status"] != "active" or point["zone_status"] != "active":
        return policy.refuse(
            "device_untrusted",
            f"this access point is {point['status']} in a {point['zone_status']} zone",
        ), None, None
    try:
        credentials.check_clock(posture.clock_skew if posture else timedelta(0),
                                kind=presented.kind)
    except ValueError as e:
        return policy.refuse("reader_clock_unreliable", str(e)), None, None
    # **No snapshot gate here, and the first version had one.** `evaluate_access` is a
    # decision the *server* makes: the request reached this process, so the live policy, the
    # live credential state and the live revocation epoch are all in hand, and an offline
    # snapshot is a cache of exactly those. Requiring one meant a device that had never filed
    # a health report was judged `offline` by `mode_for` -- which is every freshly activated
    # turnstile -- and then refused for holding no snapshot. **The online path could not open
    # a door at all**, and the refusal read as `snapshot_stale`, which points an operator at
    # the sync rather than at the gate. Found by the first HTTP test that presented a card.
    #
    # The posture is still derived and still recorded, because how stale a reader's own cache
    # was is evidence worth keeping; and the clock check above is still a live refusal, since
    # a rotating token's whole protection is a window a bad clock cannot see. What moved is
    # the snapshot judgement, to `reconcile_offline_access`, which is where a decision a
    # reader made *on its own authority* is judged.
    if binding is None:
        # **No person is invented for an unknown credential**, which is the commonest denial
        # there is. A row naming somebody would be a decision about a member who was not
        # there.
        return policy.refuse(
            "credential_unknown", "this credential is not enrolled here"), None, None
    if binding.state == "revoked":
        return policy.refuse(
            "credential_revoked", "this credential was withdrawn",
        ), binding.credential_id, binding.person_id
    if not credentials.is_usable(binding, at=at):
        return policy.refuse(
            "credential_expired", "this credential has lapsed",
        ), binding.credential_id, binding.person_id
    try:
        credentials.check_presentation(presented, at=at)
    except ValueError as e:
        return policy.refuse("credential_window", str(e)), \
            binding.credential_id, binding.person_id
    if presented.kind in credentials.ROTATING_KINDS:
        # **Inside a savepoint**, because PostgreSQL aborts the whole transaction on a
        # constraint violation and this one is expected: a replayed token is the refusal, not
        # an error. The first version caught `UniqueViolation` and carried on in the aborted
        # transaction, so the very next statement -- writing the decision -- raised
        # `InFailedSqlTransaction`, which nothing catches. The result was that an honest
        # replay answered **500** and recorded nothing: `credential_replayed` was a declared
        # reason code no path could write, and the refusal paragraph 4183 calls the core of
        # the token design left no evidence at all. Found by a reviewer presenting the same
        # valid token twice.
        #
        # Every other `UniqueViolation` catch in this module raises immediately, which is why
        # none of them needed this; a catch that *continues* is the one that does.
        try:
            with conn.transaction():
                conn.execute(
                    "INSERT INTO plt01.acc_replay_tokens"
                    " (tenant_id, token_key, credential_id, point_id, seen_at, expires_at,"
                    "  correlation_id)"
                    " SELECT %s, %s, %s, %s, %s, %s, %s",
                    (point.get("tenant_id") or _tenant_of(conn),
                     credentials.replay_key(presented), binding.credential_id,
                     point["point_id"], at,
                     credentials.replay_expiry(presented, at=at), correlation_id))
        except errors.UniqueViolation:
            return policy.refuse(
                "credential_replayed",
                "this exact token has already been presented; the app will show a fresh one",
            ), binding.credential_id, binding.person_id
    return None, binding.credential_id, binding.person_id


def _tenant_of(conn: Connection[Any]) -> str:
    row = conn.execute("SELECT current_setting('app.tenant_id', true)").fetchone()
    assert row is not None and row[0]
    return str(row[0])


def _readers(conn: Connection[Any], zone_id: str) -> occupancy.Readers:
    row = conn.execute(
        "SELECT bool_or(direction IN ('entry', 'both')),"
        "       bool_or(direction IN ('exit', 'both'))"
        " FROM plt01.acc_points WHERE zone_id = %s AND status = 'active'",
        (zone_id,)).fetchone()
    assert row is not None
    return occupancy.Readers(has_entry_reader=bool(row[0]),
                             has_exit_reader=bool(row[1]))


def _inside(conn: Connection[Any], zone_id: str, *, since: datetime | None = None) -> int:
    """Occupancy, summed from the events. **No stored count anywhere.**

    `since` bounds the tally to the current local day where a caller supplies one. The
    unbounded form is the honest answer to "how many events has this zone ever seen"; it is
    not an answer to "how many people are inside", and the difference is a defect this module
    shipped -- see `_capacity_seen`.
    """
    row = conn.execute(
        "SELECT count(*) FILTER (WHERE direction = 'entry'),"
        "       count(*) FILTER (WHERE direction = 'exit')"
        " FROM plt01.acc_events WHERE zone_id = %s"
        "   AND (%s::timestamptz IS NULL OR occurred_at >= %s)",
        (zone_id, since, since)).fetchone()
    assert row is not None
    return occupancy.inside(
        int(row[0]), int(row[1]), readers=_readers(conn, zone_id))


def _capacity_seen(
    conn: Connection[Any], zone_id: str, *, location_id: str, at: datetime,
) -> int | None:
    """The occupancy a capacity refusal may be made on, or `None` for "do not refuse".

    **Two defects in one place, and both were reachable by a tenant doing nothing unusual.**
    `_inside` counted every event the zone had ever seen, with no time bound, and
    `policy.decide` refused on it -- so a studio with `capacity = 20` stopped admitting
    anybody after its twentieth lifetime entry. `acc_events` has no DELETE grant for any
    runtime role and an entry-only zone records no exits, so **no act inside this module could
    ever bring the number down**: the only remedy was drafting and publishing a new policy,
    which is two acts by two people. Both reviewers found it; one shut a door with three
    requests from the weakest write permission in the module.

    Two things fix it, and both are needed:

      * **The tally is the current local day**, in the location's own zone. A count that never
        resets ratchets toward refusal on every uncounted exit -- a held door, a fire escape, a
        reader outage, an emergency release -- and those are not rare.
      * **A capacity refusal needs a `measured` zone.** `occupancy.py` says an entry-only
        zone's number "rises all day and is wrong by closing time" and reports it as
        `advisory`; refusing entry on a number the module declares untrustworthy is the same
        contradiction MOD-011 refuses when it will not evaluate a percentile it cannot
        compute. Where the zone cannot see both directions, this returns `None` and
        `policy.decide` does not reach the capacity branch at all -- which `zone_detail`
        reports in `access_gaps` rather than leaving to be discovered.
    """
    readers = _readers(conn, zone_id)
    if occupancy.confidence(readers) != "measured":
        return None
    row = conn.execute(
        "SELECT date_trunc('day', %s AT TIME ZONE l.timezone) AT TIME ZONE l.timezone"
        " FROM plt01.locations l WHERE l.location_id = %s", (at, location_id)).fetchone()
    since = None if row is None else row[0]
    return _inside(conn, zone_id, since=since)


def _seconds_since_entry(
    conn: Connection[Any], credential_id: str, *, zone_id: str, at: datetime,
) -> int | None:
    """How long ago this credential last entered **this zone**.

    The zone predicate is the fix for a defect a reviewer found by walking through a building
    the ordinary way. The query was tenant-wide, and the window it is compared against belongs
    to one zone -- so a member who came through the front door could not enter the studio for
    the length of the studio's window, and the refusal said "**this zone** admits one entry
    every 300 seconds" about an entry that happened at a different door. Nested zones (building
    to studio to pool) are the normal arrangement, so this was every member, every visit.

    `passback.Entry` carried `zone_id` and `point_id` from the start and nothing compared
    them, which is MOD-019's "a field stored beside a decision and never read is not a
    parameter, it is a comment".
    """
    row = conn.execute(
        "SELECT occurred_at, zone_id, point_id FROM plt01.acc_events"
        " WHERE credential_id = %s AND zone_id = %s AND direction = 'entry'"
        " ORDER BY occurred_at DESC LIMIT 1", (credential_id, zone_id)).fetchone()
    if row is None:
        return None
    return passback.seconds_since(
        passback.Entry(at=row[0], zone_id=str(row[1]), point_id=str(row[2]),
                       scope="global"), at=at)


def _namespaced(command: str, key: str) -> str:
    """The stored idempotency key, prefixed by the command that wrote it.

    **An idempotency namespace a caller can write into is not a namespace** -- MOD-018's rule,
    and this module shipped it twice over. `acc_decisions.idempotency_key` is one column, so a
    presentation at a turnstile and a staff override shared it: a reviewer made an override
    under `shift-counter-12`, then presented a **revoked** card under the same key on the
    routine `access.decision.evaluate` permission and was answered
    `{"granted": true, "code": "granted_by_override"}`. The cheapest permission in the module
    read the authority of the most expensive one.

    The prefix is written here rather than by the caller, so the two keyspaces cannot meet
    however a till numbers its requests.
    """
    return f"{command}:{key}"


def _repeat_mismatch(command: str, key: str) -> Conflict:
    """A key reused for a *different* request is a conflict, not somebody else's answer.

    The alternative -- answering from whichever row happened to carry the key -- is what a
    reviewer found: a till reusing a per-shift counter presented a revoked card and was handed
    the previous member's grant, and a responder reusing a panic-button counter was told a
    second zone had been released when nothing had. A 409 naming the key is the only answer
    that is true, and the realistic input (a counter that wrapped) is exactly the case where
    silence is dangerous.
    """
    return Conflict(f"idempotency_key_already_used_for_a_different_{command}")


def _record(
    conn: Connection[Any], tenant_id: str, point: dict[str, Any],
    decision: policy.Decision, *, key: str, credential_id: str | None,
    person_id: str | None, at: datetime, actor_id: str, correlation_id: str,
    mode: str, scope: str, occupancy_seen: int | None, snapshot_id: str | None,
    override_by: str | None = None, override_reason: str | None = None,
) -> dict[str, Any]:
    """Write the decision, open the door if it opened, publish, and refuse afterwards.

    **The unlock is issued on this connection.** `devices.issue_command_on` takes it, so the
    command and the decision are one transaction -- which is what makes "a door that opened
    has a decision behind it" true rather than hoped for.
    """
    row = conn.execute(
        "INSERT INTO plt01.acc_decisions"
        " (tenant_id, point_id, zone_id, credential_id, person_id, granted, code,"
        "  public_reason, private_reason, masked, policy_id, policy_version, snapshot_id,"
        "  device_mode, passback_scope, occupancy_seen, override_reason, overridden_by,"
        "  decided_at, decided_by, correlation_id, idempotency_key)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
        "         %s, %s, %s, %s) RETURNING decision_id",
        (tenant_id, point["point_id"], point["zone_id"], credential_id, person_id,
         decision.granted, decision.code, decision.public_reason, decision.private_reason,
         decision.masked, decision.policy_id, decision.policy_version, snapshot_id,
         mode, scope, occupancy_seen, override_reason, override_by, at, actor_id,
         correlation_id, key)).fetchone()
    assert row is not None
    decision_id = str(row[0])
    command_id: str | None = None
    if decision.granted:
        issued = devices.issue_command_on(
            conn, tenant_id, device_id=point["device_id"], action="unlock_momentary",
            arguments={}, idempotency_key=f"access:{decision_id}",
            expires_in_seconds=None, actor_id=actor_id, correlation_id=correlation_id,
            at=at)
        command_id = str(issued["command_id"])
    _append(conn, tenant_id, "access.requested", "access_point", point["point_id"],
            {"point_id": point["point_id"], "zone_id": point["zone_id"],
             "decision_id": decision_id, "credential_id": credential_id},
            actor_id=actor_id, correlation_id=correlation_id)
    _append(conn, tenant_id,
            "access.overridden" if decision.code == "granted_by_override"
            else ("access.granted" if decision.granted else "access.denied"),
            "access_point", point["point_id"],
            {"point_id": point["point_id"], "zone_id": point["zone_id"],
             "decision_id": decision_id, "person_id": person_id,
             # **The code and never the reason.** `evt_outbox` is the one store no erasure
             # reaches, and a private reason names a member's membership state, their arrears
             # or a safety hold. MOD-013's `notification.failed` finding, in the module whose
             # Critical Control is that a denial reveals none of those.
             "code": decision.code},
            actor_id=actor_id, correlation_id=correlation_id)
    # **No private reason in the answer a reader gets.** This response goes to whatever is
    # standing at the door, and the module's Critical Control is paragraph 1944: a denial
    # never reveals sensitive financial or health information publicly. Returning it here
    # would hand "this member owes 45.00" to the device above the turnstile, which is the one
    # place in the product it must not reach. `reason_withheld` says a fuller reason exists
    # and `/access/decisions` is where somebody holding `access.decision.read_reason` reads
    # it. Found by the first HTTP test that asserted what a turnstile may show.
    return {"decision_id": decision_id, "granted": decision.granted,
            # **The public code, never the real one.** This payload goes to the device above
            # the turnstile; `age_restricted` beside "please see the front desk" tells whoever
            # is reading that screen that the person in front of them is a minor.
            "code": policy.public_code(decision.code),
            "public_reason": decision.public_reason,
            "reason_withheld": decision.masked,
            "policy_id": decision.policy_id, "policy_version": decision.policy_version,
            "device_mode": mode, "passback_scope": scope, "snapshot_id": snapshot_id,
            "command_id": command_id, "repeated": False,
            "detail": ("nothing here drives the barrier; the command is written for the "
                       "gateway to collect, and it expires in a minute if nothing does")}


def override_access(
    pool: Pool, tenant_id: str, *, point_id: str, person_id: str, reason: str,
    idempotency_key: str, actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """OverrideAccess. Paragraph 1938's staff override, as its own decision.

    **A different code and a different permission, not a flag on an ordinary grant.** A
    decision that read `granted` when somebody waved a member through is the shape MOD-013's
    `bypass_policy_ref` was blocked for, and `acc_decisions_override_attributed` makes the
    reason and the actor mandatory for this code and forbidden for every other -- so "how
    often was the policy overridden, by whom, and why" is one query.
    """
    moment = at or _now()
    key = _required(idempotency_key, "idempotency_key", 200)
    try:
        decision = policy.override(reason=reason)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        stored = _namespaced("override", key)
        prior = conn.execute(
            "SELECT decision_id, granted, code, public_reason, point_id, person_id"
            " FROM plt01.acc_decisions WHERE idempotency_key = %s", (stored,)).fetchone()
        if prior is not None:
            # **Answered from the row, not from the retry.** The first version returned a
            # fabricated `{"granted": true, "code": "granted_by_override"}` without reading
            # what had been recorded, so a staff member who reused a key was told an override
            # had succeeded while the member was still refused and no door had been
            # commanded. MOD-017's rule, verbatim.
            if str(prior[4]) != point_id or str(prior[5]) != person_id:
                raise _repeat_mismatch("override", key)
            return {"decision_id": str(prior[0]), "granted": bool(prior[1]),
                    "code": str(prior[2]), "public_reason": str(prior[3]),
                    "repeated": True}
        point = _point(conn, point_id)
        if not zones.decides_entry(point["direction"]):
            raise Conflict("this_access_point_faces_out_and_decides_nothing")
        live = _live_policy(conn, point["zone_id"])
        posture, mode = _posture(conn, point["device_id"], skew=timedelta(0), at=moment)
        decision = policy.override(reason=reason, policy=live)
        try:
            return _record(
                conn, tenant_id, point, decision, key=stored, credential_id=None,
                person_id=person_id, at=moment, actor_id=actor_id,
                correlation_id=correlation_id, mode=mode,
                scope=passback.claim(online=True), occupancy_seen=None,
                snapshot_id=posture.snapshot_id if posture else None,
                override_by=actor_id, override_reason=reason.strip())
        except errors.RaiseException as e:
            # The coherence trigger refuses a decision at a point that is not active, and
            # `granted_by_override` is not one of the codes it exempts. Every sibling command
            # catches this; `override_access` did not, so a duty manager overriding at a
            # retired lane was told the server was broken -- in the module where the next
            # action is deciding whether to let somebody in by hand.
            raise Conflict(str(e).strip().splitlines()[0]) from None
        except errors.ForeignKeyViolation:
            raise NotFound("person_not_found") from None


# ------------------------------------------------------------ entry, exit, occupancy


def record_entry_exit(
    pool: Pool, tenant_id: str, *, point_id: str, direction: str,
    credential_value: str | None, decision_id: str | None, occurred_at: datetime,
    source: str, local_sequence: int | None, idempotency_key: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """RecordEntryExit. What a reader saw, which is not what was decided.

    A granted decision whose member walked away is a decision with no entry, and occupancy and
    anti-passback both read these rows rather than the decisions for exactly that reason.

    **An entry citing a refusal is refused by the trigger.** A row saying somebody walked in on
    a decision that turned them away would make every occupancy and anti-passback read wrong
    in the direction nobody checks; a door held open is an incident, not an entry.
    """
    moment = at or _now()
    key = _required(idempotency_key, "idempotency_key", 200)
    if direction not in ("entry", "exit"):
        raise InvalidRequest("a_reader_sees_an_entry_or_an_exit")
    # **`occurred_at` is bounded forward and not backward.** An offline reader legitimately
    # reports an entry from an hour ago, which is the whole point of a local queue -- so there
    # is no lower bound. A *future* one is different: anti-passback reads the latest entry and
    # occupancy counts them, so an event dated next week makes both wrong until it arrives,
    # and a reader could post-date its way past a passback window. MOD-011's unbounded
    # `observed_at` and MOD-021's postdated unlock, in the module where the consequence is a
    # second entry on one credential.
    if occurred_at > moment + credentials.READER_CLOCK_TOLERANCE:
        raise InvalidRequest("an_access_event_is_not_dated_in_the_future")
    if source not in ("online", "offline"):
        raise InvalidRequest("an_event_is_online_or_offline")
    with tenant_scope(pool, tenant_id) as conn:
        stored = _namespaced("event", key)
        prior = conn.execute(
            "SELECT event_id, direction, point_id FROM plt01.acc_events"
            " WHERE idempotency_key = %s", (stored,)).fetchone()
        if prior is not None:
            if str(prior[2]) != point_id:
                raise _repeat_mismatch("event", key)
            point = _point(conn, point_id)
            # The same shape as the first answer. A repeat that dropped `inside` and `detail`
            # made a client branch on whether its own retry had fired.
            return {"event_id": str(prior[0]), "direction": str(prior[1]),
                    "inside": _inside(conn, point["zone_id"]),
                    "repeated": True,
                    "detail": occupancy.NEVER_A_MUSTER}
        point = _point(conn, point_id)
        credential_id: str | None = None
        person_id: str | None = None
        if credential_value is not None:
            binding = _binding(conn, credentials.digest_of(credential_value))
            if binding is None:
                raise NotFound("credential_not_found")
            credential_id, person_id = binding.credential_id, binding.person_id
        try:
            row = conn.execute(
                "INSERT INTO plt01.acc_events"
                " (tenant_id, point_id, zone_id, direction, credential_id, person_id,"
                "  decision_id, occurred_at, recorded_by, correlation_id, source,"
                "  local_sequence, idempotency_key)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " RETURNING event_id",
                (tenant_id, point_id, point["zone_id"], direction, credential_id,
                 person_id, decision_id, occurred_at, actor_id, correlation_id, source,
                 local_sequence, stored)).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        except errors.ForeignKeyViolation:
            raise NotFound("decision_not_found") from None
        assert row is not None
        inside = _inside(conn, point["zone_id"])
        _append(conn, tenant_id, "occupancy.changed", "access_zone", point["zone_id"],
                {"zone_id": point["zone_id"], "inside": inside, "direction": direction},
                actor_id=actor_id, correlation_id=correlation_id)
    return {"event_id": str(row[0]), "direction": direction, "inside": inside,
            "repeated": False,
            "detail": occupancy.NEVER_A_MUSTER}


def zone_occupancy(pool: Pool, tenant_id: str, zone_id: str) -> dict[str, Any]:
    """How many are inside, and whether the number may be relied on.

    **Derived, with its confidence derived too.** There is no occupancy table: a stored count
    is a second copy of the truth that can disagree with the events it came from, and here
    that is a number somebody might count heads against. `confidence` is `measured` only when
    the zone reads both directions.
    """
    with tenant_scope(pool, tenant_id) as conn:
        zone = conn.execute(
            "SELECT risk_class, status FROM plt01.acc_zones WHERE zone_id = %s",
            (zone_id,)).fetchone()
        if zone is None:
            raise NotFound("zone_not_found")
        readers = conn.execute(
            "SELECT bool_or(direction IN ('entry', 'both')),"
            "       bool_or(direction IN ('exit', 'both'))"
            " FROM plt01.acc_points WHERE zone_id = %s AND status = 'active'",
            (zone_id,)).fetchone()
        assert readers is not None
        seen = occupancy.Readers(has_entry_reader=bool(readers[0]),
                                 has_exit_reader=bool(readers[1]))
        inside = _inside(conn, zone_id)
    return {"zone_id": zone_id, "inside": inside,
            "confidence": occupancy.confidence(seen),
            "has_entry_reader": seen.has_entry_reader,
            "has_exit_reader": seen.has_exit_reader,
            "risk_class": str(zone[0]),
            "detail": occupancy.NEVER_A_MUSTER}


# ------------------------------------------------------- emergency and reconciliation


def emergency_unlock(
    pool: Pool, tenant_id: str, *, zone_id: str, reason: str, idempotency_key: str,
    actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """EmergencyUnlock. Paragraph 4178's privileged release of every point in a zone.

    **"Where time permits" is doing real work in that paragraph**, and the trade here is the
    opposite of MOD-016's discount approval, deliberately: a fire is not a moment to go
    looking for a second approver, so the release happens on one authority and the row stays
    unreviewed until somebody else looks at it. The harm of a wrongly-refused emergency unlock
    is not symmetric with the harm of a wrongly-granted one.

    **It is not gated on commissioning.** `emergency_unlock` is a release and paragraph 4177
    puts egress outside the Veyro application path, so a door whose fire-alarm test *failed*
    is still released -- refusing on that ground would be the fire code read backwards. That
    asymmetry lives in MOD-021's `check_issue` and in the capability trigger beside it.

    **And a local physical input remains the real answer.** Paragraph 4178's last sentence:
    when the network or the edge agent is unavailable nothing here reaches a door, which is
    why `local_emergency_input` is a commissioning claim MOD-021 refuses to activate without.
    """
    moment = at or _now()
    key = _required(idempotency_key, "idempotency_key", 200)
    if not reason.strip():
        raise InvalidRequest("an_emergency_unlock_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        stored = _namespaced("emergency", key)
        prior = conn.execute(
            "SELECT unlock_id, points_released, zone_id FROM plt01.acc_emergency_unlocks"
            " WHERE idempotency_key = %s", (stored,)).fetchone()
        if prior is not None:
            # **The zone is compared, and the answer names it.** The first version matched on
            # the key alone, so a responder who ordered a release for the north stair and
            # then, under the same panic-button counter, for the south stair was told the
            # south stair was open. It was shut, nothing had been written for it, and the
            # response omitted the zone so the caller could not tell. Paragraph 4178, during
            # an evacuation, with the harm all in one direction.
            if str(prior[2]) != zone_id:
                raise _repeat_mismatch("emergency", key)
            return {"unlock_id": str(prior[0]), "zone_id": zone_id,
                    "points_released": int(prior[1]), "repeated": True}
        zone = conn.execute(
            "SELECT status FROM plt01.acc_zones WHERE zone_id = %s FOR UPDATE",
            (zone_id,)).fetchone()
        if zone is None:
            raise NotFound("zone_not_found")
        # The status was selected and discarded -- MOD-016's "a status selected and discarded
        # is a control that does not exist". A retired zone has no active points, so the
        # release would answer `points_released: 0` and read as a success during an
        # evacuation. Saying which zone is retired is the useful answer.
        if str(zone[0]) != "active":
            raise Conflict(f"this_zone_is_{zone[0]}_and_releases_nothing")
        points = conn.execute(
            "SELECT point_id, device_id FROM plt01.acc_points"
            " WHERE zone_id = %s AND status = 'active' ORDER BY point_id",
            (zone_id,)).fetchall()
        released: list[str] = []
        refused: list[dict[str, str]] = []
        for point_id, device_id in points:
            try:
                devices.issue_command_on(
                    conn, tenant_id, device_id=str(device_id),
                    action="emergency_unlock", arguments={},
                    idempotency_key=f"emergency:{key}:{point_id}",
                    expires_in_seconds=None, actor_id=actor_id,
                    correlation_id=correlation_id, at=moment)
                released.append(str(point_id))
            except (Conflict, InvalidRequest) as e:
                # **A door that cannot be commanded is named, not hidden.** A unit out of
                # service or with no actuating capability is a point the order did not reach,
                # and an operator standing in a corridor needs to know which.
                refused.append({"point_id": str(point_id), "why": str(e)})
        row = conn.execute(
            "INSERT INTO plt01.acc_emergency_unlocks"
            " (tenant_id, zone_id, reason, points_released, ordered_at, ordered_by,"
            "  correlation_id, idempotency_key)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING unlock_id",
            (tenant_id, zone_id, reason.strip(), len(released), moment, actor_id,
             correlation_id, stored)).fetchone()
        assert row is not None
        _append(conn, tenant_id, "access.emergency_unlocked", "access_zone", zone_id,
                {"zone_id": zone_id, "unlock_id": str(row[0]),
                 "points_released": len(released)},
                actor_id=actor_id, correlation_id=correlation_id)
    return {"unlock_id": str(row[0]), "zone_id": zone_id,
            "points_released": len(released), "released": released,
            "not_reached": refused, "repeated": False,
            "detail": ("this is reviewed afterwards by somebody other than whoever ordered "
                       "it; a local physical emergency input is what works when nothing "
                       "here can reach a door")}


def review_emergency_unlock(
    pool: Pool, tenant_id: str, unlock_id: str, *, note: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """The second half of paragraph 4178's dual approval, moved to after the fact.

    `acc_emergency_unlocks_reviewer_is_not_orderer` is what makes it two people, and the
    trigger makes the review final: a review that could be rewritten is a review nobody can
    rely on in the enquiry it exists for.
    """
    moment = at or _now()
    if not note.strip():
        raise InvalidRequest("a_review_states_what_was_found")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT ordered_by, reviewed_at FROM plt01.acc_emergency_unlocks"
            " WHERE unlock_id = %s FOR UPDATE", (unlock_id,)).fetchone()
        if row is None:
            raise NotFound("emergency_unlock_not_found")
        if row[1] is not None:
            raise Conflict("this_emergency_unlock_was_already_reviewed")
        if str(row[0]) == actor_id:
            raise Conflict("an_emergency_unlock_is_reviewed_by_somebody_else")
        try:
            conn.execute(
                "UPDATE plt01.acc_emergency_unlocks SET reviewed_at = %s,"
                " reviewed_by = %s, review_note = %s, review_correlation_id = %s"
                " WHERE unlock_id = %s AND reviewed_at IS NULL",
                (moment, actor_id, note.strip(), correlation_id, unlock_id))
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
    return {"unlock_id": unlock_id, "reviewed": True}


def reconcile_offline_access(
    pool: Pool, tenant_id: str, *, point_id: str, actor_id: str, correlation_id: str,
    at: datetime | None = None, limit: int = 500,
) -> dict[str, Any]:
    """ReconcileOfflineAccess. Paragraph 4168: deduplicate and flag, never rewrite.

    **Nothing here deletes or edits an event.** A duplicate entry two readers both saw while
    disconnected is two rows, one flagged -- because an offline event is evidence of what a
    device observed, and deleting one to make a report tidy is rewriting history. The window
    is the policy's own anti-passback seconds, which is the only definition of "duplicate"
    this module has.
    """
    moment = at or _now()
    if not 1 <= limit <= 5000:
        raise InvalidRequest("a_reconciliation_takes_between_one_and_five_thousand")
    outcomes: dict[str, int] = {"accepted": 0, "duplicate": 0, "policy_conflict": 0,
                                "stale_snapshot": 0}
    with tenant_scope(pool, tenant_id) as conn:
        point = _point(conn, point_id)
        live = _live_policy(conn, point["zone_id"])
        window = 0 if live is None else live.anti_passback_seconds
        # **The snapshot is the one that covered the event, not the one the device holds
        # now.** Reading the latest made the ordinary reconnect order launder everything: a
        # reader comes back, syncs -- which is what reconnecting *is* -- and then somebody
        # reconciles, so every decision it made on an expired snapshot reports `accepted`.
        # A reviewer demonstrated both directions: an event reconciled before a sync was
        # flagged `stale_snapshot` and the same event after a sync was `accepted`. The
        # outcome this module added to close a "no writer" defect was defeated by the only
        # order of operations the product has.
        device_id = point["device_id"]
        rows = conn.execute(
            "SELECT event_id, credential_id, occurred_at, direction"
            " FROM plt01.acc_events"
            " WHERE point_id = %s AND source = 'offline' AND reconciled_outcome IS NULL"
            " ORDER BY local_sequence, occurred_at LIMIT %s",
            (point_id, limit)).fetchall()
        for event_id, credential_id, occurred_at, direction in rows:
            outcome = "accepted"
            if credential_id is not None and direction == "entry" and window > 0:
                earlier = conn.execute(
                    "SELECT occurred_at FROM plt01.acc_events"
                    " WHERE credential_id = %s AND direction = 'entry'"
                    "   AND event_id <> %s AND occurred_at <= %s"
                    " ORDER BY occurred_at DESC LIMIT 1",
                    (credential_id, event_id, occurred_at)).fetchone()
                if earlier is not None and passback.is_duplicate(
                        passback.Entry(at=earlier[0], zone_id=point["zone_id"],
                                       point_id=point_id, scope="controller_group"),
                        passback.Entry(at=occurred_at, zone_id=point["zone_id"],
                                       point_id=point_id, scope="controller_group"),
                        window_seconds=window):
                    outcome = "duplicate"
            at_the_time = _posture_at(conn, device_id, when=occurred_at)
            if outcome == "accepted" and (
                    at_the_time is None or not offline.may_decide_offline(
                        at_the_time, at=occurred_at, risk=point["risk_class"])):
                # **The outcome that had no writer.** `OUTCOMES` declared `stale_snapshot`
                # and the dict counted it from zero for ever: an offline reader that decided
                # on an expired snapshot, or on one minted before a revocation it never saw,
                # was reconciled as `accepted`. Paragraph 4168 says flag rather than rewrite,
                # so the event stays and the flag is what an operator reads.
                outcome = "stale_snapshot"
            if live is None and outcome == "accepted":
                outcome = "policy_conflict"
            conn.execute(
                "UPDATE plt01.acc_events SET reconciled_outcome = %s, reconciled_at = %s,"
                " reconciled_by = %s, reconcile_correlation_id = %s"
                " WHERE event_id = %s AND reconciled_outcome IS NULL",
                (outcome, moment, actor_id, correlation_id, event_id))
            outcomes[outcome] += 1
    return {"point_id": point_id, "reconciled": len(rows), "outcomes": outcomes,
            "anti_passback_window_seconds": window,
            "detail": ("duplicates are flagged and kept; cross-device anti-passback is not "
                       "claimed for anything that happened while a reader was disconnected")}


# ------------------------------------------------------------------------- reads


def publish_access_snapshot(
    pool: Pool, tenant_id: str, *, point_id: str, content_digest: str,
    ttl_minutes: int, signature_ref: str | None, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """PublishAccessSnapshot: MOD-021's snapshot, narrowed by this zone's risk class.

    **The ceiling is the zone's, and it is the only thing a risk class buys.** MOD-021's own
    `snapshots.check_ttl` refuses anything over twelve hours or under five minutes for every
    device; paragraph 4160 makes a high-risk zone two hours, and a high-risk zone issued a
    twelve-hour authorization is one that outlives the assessment made about it.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        point = _point(conn, point_id)
        # **The point's own state matters**, and this did not look at it: a snapshot
        # published for a retired lane is an authorization for a door nobody is maintaining.
        if point["status"] != "active":
            raise Conflict(f"this_access_point_is_{point['status']}")
        # **The ceiling and the write commit together.** They used to be two transactions --
        # the check here, the publication through the pool -- so a reclassification landing
        # between them issued a twelve-hour authorization for a zone that had just become
        # high-risk. That is the whole of what a risk class buys, lost to a race nobody had
        # to arrange. `publish_snapshot_on` is MOD-021's connection-taking core, split out
        # for this.
        try:
            zones.check_snapshot_ttl(timedelta(minutes=ttl_minutes),
                                     risk=point["risk_class"])
        except ValueError as e:
            raise Conflict(str(e)) from None
        published = devices.publish_snapshot_on(
            conn, tenant_id, point["device_id"], content_digest=content_digest,
            ttl_minutes=ttl_minutes, signature_ref=signature_ref, actor_id=actor_id,
            correlation_id=correlation_id, at=moment)
    published["point_id"] = point_id
    published["zone_risk_class"] = point["risk_class"]
    return published


def credential_status(
    pool: Pool, tenant_id: str, credential_id: str, *, at: datetime | None = None,
    may_read_reason: bool = False,
) -> dict[str, Any]:
    """CredentialStatus. **What it is, never what it opens.**

    The read returns the kind, the state, the window and the epoch. It does not return the
    holder's membership state, their arrears or their entitlements -- those are the facts a
    *decision* reads, and a credential read that returned them would be the credential
    carrying authorization after all.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT credential_id, person_id, kind, state, issued_at, expires_at,"
            "       revocation_epoch, revoked_at, revoke_reason"
            " FROM plt01.acc_credentials WHERE credential_id = %s",
            (credential_id,)).fetchone()
        if row is None:
            raise NotFound("credential_not_found")
    binding = credentials.Binding(
        credential_id=str(row[0]), person_id=str(row[1]), kind=str(row[2]),
        state=str(row[3]), issued_at=row[4], expires_at=row[5],
        revocation_epoch=int(row[6]))
    return {"credential_id": str(row[0]), "person_id": str(row[1]), "kind": str(row[2]),
            "state": str(row[3]), "usable": credentials.is_usable(binding, at=moment),
            "revocation_epoch": int(row[6]),
            "expires_at": None if row[5] is None else row[5].isoformat(),
            "revoked_at": None if row[7] is None else row[7].isoformat(),
            # **Prose a desk typed, so it follows the same permission as a decision's private
            # half.** "She left it at the oncology clinic on Tuesday" is this module's own
            # example of what goes in this column, and it was returned to the cheapest read
            # there is. `reason_withheld` says a reason exists rather than implying none does.
            "revoke_reason": row[8] if may_read_reason else None,
            "reason_withheld": row[8] is not None and not may_read_reason,
            "detail": ("usable here means this credential still identifies its holder; "
                       "whether a door opens is a policy decision made elsewhere")}


def decision_history(
    pool: Pool, tenant_id: str, *, zone_id: str | None, credential_id: str | None,
    person_id: str | None = None, may_read_private: bool, limit: int = 100,
) -> dict[str, Any]:
    """AccessDecision history, with the private reason behind a second permission.

    **The public reason is what a member or a screen may see; the private one names their
    membership state, their arrears or a safety hold.** Paragraph 1944's Critical Control is
    about a *denial* not revealing those publicly, and a read is the other place it would
    leak -- so the full reason needs `access.decision.read_reason`, and a caller without it
    gets the discreet line the door showed.
    """
    if not 1 <= limit <= 1000:
        raise InvalidRequest("a_decision_history_takes_between_one_and_a_thousand")
    # **Three ways in, and never none.** An unfiltered read is every decision this tenant has
    # ever taken at every door, which is a movement log for every member -- so the caller has
    # to say which question they are asking. The person filter is ADM-MEM-01's Access block
    # and discloses nothing the zone filter does not: a zone read already returns `person_id`
    # on every row, so narrowing by it is less disclosure rather than more.
    if zone_id is None and credential_id is None and person_id is None:
        raise InvalidRequest(
            "a_decision_history_is_read_by_zone_by_credential_or_by_person")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT decision_id, point_id, zone_id, credential_id, person_id, granted,"
            "       code, public_reason, private_reason, masked, policy_id,"
            "       policy_version, device_mode, passback_scope, decided_at"
            " FROM plt01.acc_decisions"
            " WHERE (%s::uuid IS NULL OR zone_id = %s)"
            "   AND (%s::uuid IS NULL OR credential_id = %s)"
            "   AND (%s::uuid IS NULL OR person_id = %s)"
            " ORDER BY decided_at DESC LIMIT %s",
            (zone_id, zone_id, credential_id, credential_id, person_id, person_id,
             limit)).fetchall()
    return {"decisions": [
        {"decision_id": str(r[0]), "point_id": str(r[1]), "zone_id": str(r[2]),
         "credential_id": None if r[3] is None else str(r[3]),
         "person_id": None if r[4] is None else str(r[4]),
         "granted": bool(r[5]),
         # The real code is the fact, so it follows the private reason rather than the
         # public one: both reviewers found that gating the sentence and not the code left
         # paragraph 1944 satisfied in wording only.
         "code": str(r[6]) if may_read_private else policy.public_code(str(r[6])),
         # **Absent rather than substituted.** The first version put the *public* text under
         # this key for a caller without the permission, so a consumer reading
         # `private_reason` got the discreet line and could not tell it from the real one --
         # which is how "the member was told the whole truth" ends up in a privacy report.
         # `None` is the honest answer, and `reason_withheld` says there is more to read.
         "public_reason": str(r[7]),
         "private_reason": str(r[8]) if may_read_private else None,
         "reason_withheld": bool(r[9]) and not may_read_private,
         "policy_id": None if r[10] is None else str(r[10]),
         "policy_version": None if r[11] is None else int(r[11]),
         "device_mode": str(r[12]), "passback_scope": str(r[13]),
         # **What a board counts this under.** ADM-ACC-02's two filters, classified by
         # MOD-022's own code vocabulary rather than by the surface: twenty-seven expired
         # memberships is the product working and four reader failures is a maintenance job,
         # and one count hides the second inside the first. Derived from `code` rather than
         # stored, so an old decision reclassifies with the rule rather than keeping an
         # answer somebody wrote down once.
         "bucket": policy.classify(str(r[6])),
         "decided_at": r[14].isoformat()} for r in rows],
        # The counts over the rows returned, so the filter chips say what they filter to.
        "counts": {
            bucket: sum(1 for r in rows if policy.classify(str(r[6])) == bucket)
            for bucket in ("granted", "policy", "fault")},
        "a_fault_is_not_a_refusal_the_product_meant":
            "policy counts the refusals the tenant configured; fault counts the ones that "
            "mean a reader, a clock or a point needs somebody.",
        "private_reasons_included": may_read_private}


def list_zones(pool: Pool, tenant_id: str, *, include_retired: bool = False,
               limit: int = 200) -> dict[str, Any]:
    """Every zone this tenant controls, with the counts a door board reads.

    **Added for the Front Desk surface**, which had no way to reach a zone without already
    knowing its id -- `zone_detail` existed and nothing enumerated. An operator looking at a
    board of doors is the ordinary use of this module, and a read path that cannot be entered
    is a read path nobody uses.

    It carries the point counts rather than the points: a board shows how many readers a zone
    has and whether any of them faces out, and the zone read is where the detail lives. The
    occupancy is deliberately **not** here -- it is a sum over the event ledger per zone, and
    a list route that ran it per row would be a slow query somebody would later cache, which
    is the stored count this module refuses to keep.
    """
    if not 1 <= limit <= 500:
        raise InvalidRequest("a_zone_list_returns_between_one_and_five_hundred")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT z.zone_id, z.location_id, z.zone_key, z.display_name, z.risk_class,"
            "       z.status,"
            "       count(p.point_id) FILTER (WHERE p.status = 'active') AS live_points,"
            "       count(p.point_id) FILTER (WHERE p.status = 'active'"
            "                                   AND p.direction IN ('entry', 'both'))"
            "           AS entry_points,"
            "       count(p.point_id) FILTER (WHERE p.status = 'active'"
            "                                   AND p.direction IN ('exit', 'both'))"
            "           AS exit_points,"
            "       max(l.version) AS live_policy_version"
            " FROM plt01.acc_zones z"
            " LEFT JOIN plt01.acc_points p ON p.zone_id = z.zone_id"
            " LEFT JOIN plt01.acc_policies l ON l.zone_id = z.zone_id"
            "                               AND l.status = 'published'"
            " WHERE (%s OR z.status = 'active')"
            " GROUP BY z.zone_id, z.location_id, z.zone_key, z.display_name, z.risk_class,"
            "          z.status"
            " ORDER BY z.display_name LIMIT %s",
            (include_retired, limit)).fetchall()
    return {"zones": [
        {"zone_id": str(r[0]), "location_id": str(r[1]), "zone_key": str(r[2]),
         "display_name": str(r[3]), "risk_class": str(r[4]), "status": str(r[5]),
         "live_points": int(r[6]), "entry_points": int(r[7]), "exit_points": int(r[8]),
         # **`None` means no policy is live**, which is a zone that decides nothing rather
         # than a zone with a permissive default. A board that showed a blank here would
         # read as "no restrictions".
         "live_policy_version": None if r[9] is None else int(r[9]),
         "snapshot_ceiling_seconds": int(zones.snapshot_ceiling(str(r[4])).total_seconds())}
        for r in rows]}


def zone_detail(pool: Pool, tenant_id: str, zone_id: str) -> dict[str, Any]:
    """A zone, its live policy and its points. The AccessPoint/AccessZone/AccessPolicy read."""
    with tenant_scope(pool, tenant_id) as conn:
        zone = conn.execute(
            "SELECT zone_id, location_id, zone_key, display_name, risk_class, status"
            " FROM plt01.acc_zones WHERE zone_id = %s", (zone_id,)).fetchone()
        if zone is None:
            raise NotFound("zone_not_found")
        live = _live_policy(conn, zone_id)
        points = conn.execute(
            "SELECT point_id, device_id, direction, display_name, status"
            " FROM plt01.acc_points WHERE zone_id = %s ORDER BY display_name",
            (zone_id,)).fetchall()
    ceiling = zones.snapshot_ceiling(str(zone[4]))
    return {
        "zone_id": str(zone[0]), "location_id": str(zone[1]), "zone_key": str(zone[2]),
        "display_name": str(zone[3]), "risk_class": str(zone[4]), "status": str(zone[5]),
        "snapshot_ceiling_seconds": int(ceiling.total_seconds()),
        "policy": None if live is None else {
            "policy_id": live.policy_id, "version": live.version,
            "opens_minute": live.opens_minute, "closes_minute": live.closes_minute,
            "requires_entitlement": live.requires_entitlement,
            "max_balance_minor": live.max_balance_minor,
            "min_age_years": live.min_age_years,
            "anti_passback_seconds": live.anti_passback_seconds,
            "capacity": live.capacity},
        "points": [{"point_id": str(p[0]), "device_id": str(p[1]),
                    "direction": str(p[2]), "display_name": str(p[3]),
                    "status": str(p[4]), "decides_entry": zones.decides_entry(str(p[2]))}
                   for p in points],
        "access_gaps": [
            "no signature is verified: a rotating credential's window and its replay cache "
            "are checked, and the signature is the reader's own claim, because this build "
            "has no key vault",
            "safety_hold is always false: MOD-014's health classes are unreachable to every "
            "caller in this build, so a door cannot read one and nothing writes a boolean "
            "that would stand in for it",
        ]}


# ------------------------------------------------------------------ the replay cache sweep

def sweep_replay_tokens(
    pool: Pool, tenant_id: str, *, at: datetime | None = None, limit: int = 5000,
) -> dict[str, Any]:
    """Delete replay-cache rows whose window has closed.

    **This is the one table in MOD-022 with a DELETE grant, and only `veyro_cp_worker` holds
    it.** Everything else here is insert-only or lifecycle-only because it is evidence; a
    replay token is not evidence, it is a claim that expires in ninety seconds, and a row that
    outlives its own window answers no question anybody can ask. So the table is meant to be
    swept, and until this function existed nothing swept it -- `CLAUDE.md` carried the gap in
    as many words.

    **A pool pinned to `veyro_cp_app` is refused here**, at the privilege layer rather than by
    a check in this function, which is the point of declaring the role per job: the process
    that sweeps a replay cache must not also be able to delete a tenant's feature flags.

    **Deleting an unexpired row would re-open the replay window**, so the predicate is the
    expiry and nothing else -- not a count, not an age, not a limit chosen to keep the table
    small. The limit bounds one pass; the next pass takes the rest, and a row that is still
    live is still there to refuse the second presentation of its token.
    """
    moment = at or _now()
    if not 1 <= limit <= 50_000:
        raise InvalidRequest("a_sweep_takes_between_one_and_fifty_thousand")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "DELETE FROM plt01.acc_replay_tokens"
            " WHERE token_key IN ("
            "   SELECT token_key FROM plt01.acc_replay_tokens"
            "    WHERE expires_at <= %s ORDER BY expires_at LIMIT %s)"
            " RETURNING token_key",
            (moment, limit)).fetchall()
    return {"deleted": len(rows), "as_of": moment.isoformat()}


def visits_on(
    pool: Pool, tenant_id: str, *, on: date | None = None, compare_weeks: int = 4,
) -> dict[str, Any]:
    """Entries per location for one local day, against the same weekday recently.

    ADM-CC-01's third metric: "VISITS TODAY · 218 · by 08:38 · usual for a Wednesday". The
    comparison is the second half of that sentence and it is the reason this is a read rather
    than a count -- 218 is a number, and "usual for a Wednesday" is what makes it meaningful.

    **The day is local to each location, converted per location.** `acc_events.occurred_at` is
    an instant and `locations.timezone` is the zone the club is in, so a tenant with clubs in
    two zones has two todays and one `date_trunc` in the host's zone would be wrong for both.
    That is MOD-019's first decision -- a rota window is read in its own zone -- and the
    schedule board shipped the other version and rendered 15:00 for an 18:00 class.

    **Entries, not decisions.** MOD-022 keeps those apart on purpose: a granted decision that
    nobody walked through is not a visit, and the event is what happened. A visit count built
    from decisions would count the turnstile's opinion rather than the member's arrival.

    **The comparison is the same weekday, not the mean of recent days.** Gyms are weekly, so
    comparing a Wednesday against a seven-day mean that includes Friday reports a story about
    the week rather than about today. `compare_weeks` prior same-weekdays, and the response
    says how many actually carried data -- a tenant four days old has no baseline and must not
    be shown one.
    """
    if compare_weeks < 1 or compare_weeks > 26:
        raise InvalidRequest("bad_compare_weeks")
    with tenant_scope(pool, tenant_id) as conn:
        # **"Today" is each location's own, and the first version took it from UTC.** The
        # comparison in the filter is a *local* date -- `occurred_at AT TIME ZONE
        # l.timezone` -- and the value it was compared against was `datetime.now(UTC).date()`.
        # Those agree for most of the day and disagree for the hours a club's local date has
        # already turned over: at 23:17 UTC an entry at a UTC+3 club has local date tomorrow,
        # so the day's count missed it and the location dropped out of the response
        # altogether. CI found it because CI runs at whatever hour it runs; this repository's
        # own rules file records the mirror of it ("a fixture that takes its own today from
        # the local clock disagrees with a service that takes it from UTC... CI never saw it,
        # because CI runs in UTC").
        #
        # The docstring above already said what the rule is -- "a tenant with clubs in two
        # zones has two todays" -- so the fix is to mean it: each location's day is resolved
        # in its own zone, and `on` overrides it only when a caller names a date.
        #
        # **Every location is listed, including one with nothing today.** The previous query
        # filtered events and grouped, so a club with no entries was absent rather than zero
        # -- which on a visits board reads as a club that does not exist.
        rows = conn.execute(
            "WITH loc AS ("
            "  SELECT l.location_id, l.location_name, l.timezone,"
            "         coalesce(%s::date, (now() AT TIME ZONE l.timezone)::date) AS today"
            "  FROM plt01.locations l"
            "), ev AS ("
            "  SELECT z.location_id AS loc_id,"
            "         (e.occurred_at AT TIME ZONE loc.timezone)::date AS local_date"
            "  FROM plt01.acc_events e"
            "  JOIN plt01.acc_zones z ON z.zone_id = e.zone_id"
            "  JOIN loc ON loc.location_id = z.location_id"
            "  WHERE e.direction = 'entry'"
            ")"
            " SELECT loc.location_id, loc.location_name, loc.timezone, loc.today,"
            "   count(ev.loc_id) FILTER (WHERE ev.local_date = loc.today),"
            "   count(ev.loc_id) FILTER (WHERE ev.local_date = ANY(p.prior)),"
            "   count(DISTINCT ev.local_date) FILTER (WHERE ev.local_date = ANY(p.prior))"
            " FROM loc"
            " CROSS JOIN LATERAL ("
            "   SELECT array_agg(loc.today - (7 * g)::integer) AS prior"
            "   FROM generate_series(1, %s) AS g"
            " ) p"
            " LEFT JOIN ev ON ev.loc_id = loc.location_id"
            " GROUP BY loc.location_id, loc.location_name, loc.timezone, loc.today"
            " ORDER BY loc.location_name, loc.location_id",
            (on, compare_weeks),
        ).fetchall()
    locations: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        local_day = row[3]
        days_seen = int(row[6])
        locations.append({
            "location_id": str(row[0]), "location_name": str(row[1]),
            "timezone": str(row[2]),
            # The day this club's figure is about, which is not always the day the next
            # club's figure is about.
            "date": local_day.isoformat(), "weekday": local_day.strftime("%A"),
            "entries": int(row[4]),
            # The mean over the days that actually carried entries, so a tenant with three
            # weeks of history is compared against three rather than against four with a zero.
            "usual_for_this_weekday": (
                round(int(row[5]) / days_seen) if days_seen else None),
            "weekdays_compared": days_seen,
        })
        total += int(row[4])
    # The top-level day is the one the locations share. A tenant whose clubs span zones can
    # be on two dates at once for a few hours, and `local_days_differ` says so rather than
    # letting one club's date stand for all of them.
    days = {row[3] for row in rows}
    headline = on or (min(days) if days else datetime.now(UTC).date())
    return {
        "date": headline.isoformat(), "weekday": headline.strftime("%A"),
        "local_days_differ": len(days) > 1,
        "compare_weeks": compare_weeks,
        "entries": total,
        "locations": locations,
        "a_day_is_local_to_each_location":
            "Each location's day is computed in its own timezone, so the total sums each "
            "club's own local day rather than one instant range. Where no date is asked for, "
            "each club's today is resolved in its own zone: for a few hours a tenant whose "
            "clubs span zones is on two dates at once, and local_days_differ says so.",
        "entries_are_events_not_decisions":
            "An entry is a recorded acc_event. A granted decision nobody walked through is "
            "not a visit.",
        "no_baseline_is_not_zero":
            "usual_for_this_weekday is null where no prior same-weekday carried entries.",
    }


#: The weeks ADM-MEM-07 draws on its chart, and the visits it lists under it.
CHART_WEEKS = 12
RECENT_VISITS = 10


def entries_between(
    pool: Pool, tenant_id: str, *, person_id: str, since: date, until: date,
) -> dict[str, Any]:
    """How many times this member came in between two dates, and on which days.

    ADM-PAY-10's first and strongest piece of evidence: *"11 check-ins in the billed month"*,
    against a chargeback claiming the service was not received. The canvas's own note says
    why it is first -- "the check-in record is the strongest evidence a gym has and Veyro
    assembles it automatically" -- and no read answered it. `person_attendance` answers "how
    often were they coming", which is a habit over the weeks before their last visit; this
    answers "did they come during *this* period", which is a different question with a
    caller-supplied window and is the only one a dispute can be answered with.

    **Entries, not decisions**, which is this module's standing rule and matters most here: a
    card failing at the door produces refused decisions for exactly the member whose
    attendance is being proved, so a count read from the decision log would overstate the
    evidence in the one place it is being used as evidence.

    **Each event's day is local to the door it was walked through**, not to UTC and not to
    one chosen zone. A member who trains at two clubs in two zones has each visit counted on
    the date that club would put on it, which is what "the billed month" means to whoever
    reads the dispute -- and counting against a UTC date is the frame mismatch this
    repository has already paid for once in `visits_on`.

    The days are returned as well as the count, because a dispute is answered with a record
    rather than with a number somebody has to trust.
    """
    if until < since:
        raise InvalidRequest("a_window_ends_before_it_starts")
    if (until - since).days > 400:
        raise InvalidRequest("an_attendance_window_is_at_most_four_hundred_days")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT (e.occurred_at AT TIME ZONE l.timezone)::date AS local_day,"
            "       l.location_name, count(*)"
            " FROM plt01.acc_events e"
            " JOIN plt01.acc_zones z ON z.zone_id = e.zone_id"
            " JOIN plt01.locations l ON l.location_id = z.location_id"
            " WHERE e.person_id = %s AND e.direction = 'entry'"
            "   AND (e.occurred_at AT TIME ZONE l.timezone)::date >= %s"
            "   AND (e.occurred_at AT TIME ZONE l.timezone)::date <= %s"
            " GROUP BY local_day, l.location_name"
            " ORDER BY local_day, l.location_name",
            (person_id, since, until),
        ).fetchall()
    days = [{"on": r[0].isoformat(), "location_name": str(r[1]), "entries": int(r[2])}
            for r in rows]
    return {
        "person_id": person_id, "since": since.isoformat(), "until": until.isoformat(),
        "entries": sum(int(d["entries"]) for d in days),
        "days_attended": len({d["on"] for d in days}),
        "days": days,
        "entries_not_decisions":
            "Counted from acc_events, which is what happened, not from acc_decisions, which"
            " is what was decided. A card failing at the door produces refused decisions for"
            " the same person, and counting those would overstate attendance in exactly the"
            " case somebody is checking it.",
        "each_day_is_local_to_its_door":
            "An event's date is computed in the timezone of the location whose zone it"
            " happened at, so a member training at two clubs has each visit on the date that"
            " club would put on it.",
    }


def person_attendance(
    pool: Pool, tenant_id: str, *, person_id: str, as_of: date | None = None,
    weeks: int = 8,
) -> dict[str, Any]:
    """When this member last came in, and how often they were coming before that.

    ADM-MEM-01's fourth metric cell: "LAST VISIT · 19d ago · was 3x a week". Both halves are
    needed and neither is the other -- a gap of nineteen days means nothing until you know
    whether this is somebody who trained three times a week or twice a year, and that second
    sentence is what a receptionist actually acts on.

    **Entries, not decisions**, which is the same rule `visits_on` states one function up and
    matters more here: a card that is failing at the door produces refused decisions for
    exactly the member whose attendance somebody is checking, so a visit count read from the
    decision log would overstate it in the one case where the figure is being looked at.

    **The rate is measured over the weeks before the last visit, not before today.** The
    canvas says "was", past tense, and that is the correct arithmetic: averaging the habit
    over a window that includes the gap reports a smaller number the longer somebody has been
    away, so every lapsed member reads as somebody who never came much. Measured to the last
    visit it says what stopped.

    The day is local to the location whose door they walked through -- `acc_events.occurred_at`
    is an instant and the club has a timezone, so "19d ago" is a count of local days.
    """
    if weeks < 1 or weeks > 52:
        raise InvalidRequest("bad_weeks")
    with tenant_scope(pool, tenant_id) as conn:
        # **"19 days ago" is counted in the club's local days, so both ends have to be in
        # them.** `last_entry_on` is the local date of the last entry and `as_of` was
        # `datetime.now(UTC).date()`, which agree for most of the day and disagree for the
        # hours after a club's local date has turned over -- at 23:17 UTC a UTC+3 club is
        # already on tomorrow, so the subtraction returned **-1 days since** the member's
        # last visit. Today is now read in the same zone as the entry it is measured from.
        # A caller that names `as_of` still gets the date they named.
        last = conn.execute(
            "SELECT (e.occurred_at AT TIME ZONE l.timezone)::date, l.location_name,"
            "       e.occurred_at, (now() AT TIME ZONE l.timezone)::date"
            " FROM plt01.acc_events e"
            " JOIN plt01.acc_zones z ON z.zone_id = e.zone_id"
            " JOIN plt01.locations l ON l.location_id = z.location_id"
            " WHERE e.person_id = %s AND e.direction = 'entry'"
            " ORDER BY e.occurred_at DESC LIMIT 1",
            (person_id,)).fetchone()
        if last is None:
            # **No entry is not a zero rate.** A member who has never used a door and one who
            # came daily until last month are different facts, and `null` is what keeps them
            # apart; a surface rendering 0 would say the second never trained.
            #
            # With no entry there is no club whose zone could settle "today", so this one
            # falls back to UTC -- and nothing here subtracts from it.
            return {
                "person_id": person_id, "as_of": (as_of or datetime.now(UTC).date()).isoformat(),
                "last_entry_on": None, "last_entry_at": None, "last_location": None,
                "days_since": None, "entries_in_window": 0, "weeks": weeks,
                "entries_per_week": None,
                # **The same keys, so a screen reads one shape.** A response that dropped
                # these for a member with no visits would make every caller branch on their
                # presence, and the first caller to forget renders `undefined`.
                "lifetime_entries": 0, "chart_weeks": CHART_WEEKS, "by_week": [],
                "recent": [], "recent_limit": RECENT_VISITS,
                "nothing_recorded_is_not_a_zero_rate":
                    "No entry has ever been recorded for this person, so there is no rate. "
                    "That is not the same as a member who stopped coming.",
            }
        last_on, last_location, last_at, today_there = last
        as_of = as_of or today_there
        window_start = last_on - timedelta(days=7 * weeks)
        counted = conn.execute(
            "SELECT count(*)"
            " FROM plt01.acc_events e"
            " JOIN plt01.acc_zones z ON z.zone_id = e.zone_id"
            " JOIN plt01.locations l ON l.location_id = z.location_id"
            " WHERE e.person_id = %s AND e.direction = 'entry'"
            "   AND (e.occurred_at AT TIME ZONE l.timezone)::date > %s"
            "   AND (e.occurred_at AT TIME ZONE l.timezone)::date <= %s",
            (person_id, window_start, last_on)).fetchone()
        entries = int(counted[0]) if counted else 0

        # **Lifetime, which is a different question from the window.** ADM-MEM-07 draws
        # `19d SINCE LAST · 2.8 WEEKLY AVG · 214 LIFETIME`, and the third is what makes the
        # first two mean something: a gap of nineteen days reads differently against two
        # hundred visits than against six.
        lifetime = conn.execute(
            "SELECT count(*) FROM plt01.acc_events"
            " WHERE person_id = %s AND direction = 'entry'",
            (person_id,)).fetchone()

        # The weeks behind the chart, and the recent visits under it. Both come from the same
        # rows, each converted in **its own club's** zone -- a member who trains in two cities
        # experienced each visit on that city's day, and bucketing both in one zone would put
        # a visit in the wrong week for one of them.
        recent_window = as_of - timedelta(days=7 * CHART_WEEKS)
        visits = conn.execute(
            "SELECT (e.occurred_at AT TIME ZONE l.timezone)::date,"
            "       to_char(e.occurred_at AT TIME ZONE l.timezone, 'HH24:MI'),"
            "       l.location_name, c.kind, e.source"
            " FROM plt01.acc_events e"
            " JOIN plt01.acc_zones z ON z.zone_id = e.zone_id"
            " JOIN plt01.locations l ON l.location_id = z.location_id"
            " LEFT JOIN plt01.acc_credentials c ON c.credential_id = e.credential_id"
            " WHERE e.person_id = %s AND e.direction = 'entry'"
            "   AND (e.occurred_at AT TIME ZONE l.timezone)::date > %s"
            " ORDER BY e.occurred_at DESC",
            (person_id, recent_window)).fetchall()

    # Weeks are counted back from `as_of`, so the last bucket is the one the member is in
    # now and an empty tail is a gap rather than a missing bar. The canvas's own reading of
    # this chart is "three weeks at zero", which only means something if the zeros are drawn.
    buckets: list[dict[str, Any]] = []
    for back in range(CHART_WEEKS - 1, -1, -1):
        ends = as_of - timedelta(days=7 * back)
        starts = ends - timedelta(days=6)
        buckets.append({
            "starts_on": starts.isoformat(), "ends_on": ends.isoformat(),
            "entries": sum(1 for v in visits if starts <= v[0] <= ends),
        })
    return {
        "person_id": person_id, "as_of": as_of.isoformat(),
        "lifetime_entries": int(lifetime[0]) if lifetime else 0,
        "chart_weeks": CHART_WEEKS,
        "by_week": buckets,
        "recent": [
            {"on": v[0].isoformat(), "at": str(v[1]), "location_name": str(v[2]),
             # The credential kind is how they got in -- a card, a rotating code -- and it is
             # null where the entry was recorded without one, which an offline reconciliation
             # can produce. Never the credential itself: the stored value is a SHA-256 and a
             # listing carrying it would let anybody with a candidate card confirm whose.
             "credential_kind": None if v[3] is None else str(v[3]),
             "source": str(v[4])}
            for v in visits[:RECENT_VISITS]],
        "recent_limit": RECENT_VISITS,
        "last_entry_on": last_on.isoformat(), "last_entry_at": last_at.isoformat(),
        "last_location": str(last_location),
        "days_since": (as_of - last_on).days,
        "entries_in_window": entries, "weeks": weeks,
        # One decimal, because "3 a week" and "3.5 a week" are different habits and rounding
        # to an integer makes every twice-weekly member read the same as a thrice-weekly one.
        "entries_per_week": round(entries / weeks, 1),
        "the_rate_ends_at_the_last_visit":
            "entries_per_week counts the weeks before last_entry_on, not before as_of, so a "
            "gap does not shrink the habit it interrupted.",
        "no_reading_of_the_chart_is_offered":
            "The design prints a sentence under this chart -- 'three weeks at zero, and the "
            "drop starts the week after his last PT session'. Nothing here produces one: "
            "relating a gap in attendance to a cause needs a module that reasons about it, "
            "and a plausible sentence written by the read would be a confident answer with "
            "nothing behind it.",
        "the_day_is_local_to_the_door_they_used":
            "days_since counts local days at the club whose door recorded the last entry, "
            "and as_of is today in that same zone unless a caller named a date.",
    }


def person_credentials(
    pool: Pool, tenant_id: str, *, person_id: str, include_revoked: bool = False,
) -> dict[str, Any]:
    """What this member can present at a door, and in what state.

    ADM-MEM-01's Access block: "Card ...8841 - active / App pass - active / Fingerprint -
    enrolled", under the canvas's own note that "biometric data is never displayed or
    exportable -- only whether enrolment exists".

    **There is no digest in the answer, and there is no column it could come from safely.**
    `credential_digest` is a SHA-256 of the card number, which is pseudonymous rather than
    anonymous: somebody holding a candidate card can test it. So the listing carries the kind,
    the state and the window and never the digest -- which is also why the canvas draws a
    last-four rather than a number, and this build has no last-four to draw, because it never
    stored one.

    **A revoked credential is left out by default and counted.** A member whose card was
    cancelled last year has a row that says so, and a board showing it beside a live one reads
    as two ways in.
    """
    with tenant_scope(pool, tenant_id) as conn:
        # **How often each one has been used, and when last.** ADM-ACC-03 draws
        # "Card ...8841 · Issued 4 Mar 2024 · 214 uses" and "App pass · Rotating QR · last
        # used 31 Jul", and both halves are what make the row actionable: a card issued two
        # years ago and never presented is a card somebody should cancel, and one used this
        # morning is not. Counted from entries rather than decisions, which is MOD-022's own
        # separation -- a granted decision nobody walked through is not a use.
        rows = conn.execute(
            "SELECT c.credential_id, c.kind, c.state, c.issued_at, c.expires_at,"
            "       c.revoked_at, c.revocation_epoch,"
            "       count(e.event_id), max(e.occurred_at)"
            " FROM plt01.acc_credentials c"
            " LEFT JOIN plt01.acc_events e"
            "   ON e.credential_id = c.credential_id AND e.direction = 'entry'"
            " WHERE c.person_id = %s AND (%s OR c.state <> 'revoked')"
            " GROUP BY c.credential_id, c.kind, c.state, c.issued_at, c.expires_at,"
            "          c.revoked_at, c.revocation_epoch"
            " ORDER BY c.issued_at DESC",
            (person_id, include_revoked)).fetchall()
    live = [r for r in rows if str(r[2]) == "active"]
    return {
        "person_id": person_id,
        "credentials": [
            {"credential_id": str(r[0]), "kind": str(r[1]), "state": str(r[2]),
             "issued_at": r[3].isoformat(),
             "expires_at": None if r[4] is None else r[4].isoformat(),
             "revoked_at": None if r[5] is None else r[5].isoformat(),
             # The credential's own epoch, not the device's: revoking one card must not
             # invalidate every policy snapshot in the building, so each carries its own and
             # a reader compares the one it was issued against.
             "revocation_epoch": int(r[6]),
             "uses": int(r[7]),
             # Null where it has never been presented, which is not the same as zero uses
             # long ago -- a card issued today and one issued in 2024 both read 0, and only
             # the date tells them apart.
             "last_used_at": None if r[8] is None else r[8].isoformat()}
            for r in rows],
        "live": len(live),
        "no_digest_is_returned":
            "The stored digest is a SHA-256 of the presented secret and is pseudonymous, so "
            "it is never read out of this module.",
        "a_live_credential_is_not_an_admission":
            "Whether this person gets in is decided per presentation against the zone's "
            "policy, their membership and their entitlement. This is only what they hold.",
    }


def entries_by_point(
    pool: Pool, tenant_id: str, *, on: date | None = None,
) -> dict[str, Any]:
    """Today's entries per reader, keyed by the device behind it.

    ADM-ACC-01's TODAY column: "9 devices across 3 clubs · 218 entries today", with a count
    beside each reader. A fleet board without it says which devices are answering and not
    whether anybody is walking through them, which is the difference between a device that is
    up and a door that is working.

    **This lives in MOD-022 rather than in MOD-021's fleet read.** A device knows nothing
    about doors by design -- MOD-021 has the turnstile and no idea who a member is, and
    `acc_points` is the join MOD-021 deliberately did not make. So the fleet board composes
    the two, the way the Member 360 composes MOD-014 and MOD-017, rather than MOD-021
    learning to count entries.

    **The day is local to each point's own location**, which is `visits_on`'s rule one
    function up and matters for the same reason: a tenant with clubs in two zones has two
    todays and one `date_trunc` in the host's zone is wrong for both.
    """
    on = on or datetime.now(UTC).date()
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT p.point_id, p.device_id,"
            "       count(e.event_id) FILTER ("
            "         WHERE e.direction = 'entry'"
            "           AND (e.occurred_at AT TIME ZONE l.timezone)::date = %s)"
            " FROM plt01.acc_points p"
            " JOIN plt01.acc_zones z ON z.zone_id = p.zone_id"
            " JOIN plt01.locations l ON l.location_id = z.location_id"
            " LEFT JOIN plt01.acc_events e ON e.point_id = p.point_id"
            " WHERE p.retired_at IS NULL"
            " GROUP BY p.point_id, p.device_id"
            " ORDER BY p.point_id",
            (on,)).fetchall()
    by_device: dict[str, int] = {}
    for row in rows:
        by_device[str(row[1])] = by_device.get(str(row[1]), 0) + int(row[2])
    return {
        "date": on.isoformat(),
        "points": [{"point_id": str(r[0]), "device_id": str(r[1]), "entries": int(r[2])}
                   for r in rows],
        # A device may stand at more than one reader, so the per-device figure is a sum.
        "by_device": by_device,
        "entries": sum(by_device.values()),
        "a_device_with_no_point_is_absent":
            "Only devices standing at a live access point appear here. A scanner that is "
            "not a door counts nothing, which is not the same as counting zero.",
    }

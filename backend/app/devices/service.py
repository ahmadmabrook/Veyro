"""MOD-021's I/O: the device registry, the commissioning gate and the command queue.

**The decisions are in the modules beside this one and the writes are here**, which is the
split every module in this build uses. What this file owns that they cannot:

  * **The commissioning gate is checked at activation, in the transaction that activates.**
    `safety.may_go_live` and `certificates.check_may_activate` are read together against rows
    this connection just locked, because a device brought live between the check and the write
    is a door open with no passing fire-alarm test.
  * **A revocation bumps the device's epoch in the same transaction as the certificate's
    revocation.** A gateway compares its snapshot's epoch numerically, so the two committing
    separately is a window in which a revoked certificate still authenticates -- MOD-010's
    `append_event` argument where the state is a door.
  * **A command is written with its digest**, computed from exactly what was asked, so the row
    the gateway reads cannot have been re-aimed since.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from psycopg import Connection, errors

from app.db import Pool, tenant_scope
from app.devices import (
    capabilities,
    certificates,
    commands,
    enrollment,
    fleet,
    safety,
    snapshots,
)
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events


def _now() -> datetime:
    return datetime.now(UTC)


def _check_name(error: errors.CheckViolation) -> str:
    name = getattr(error.diag, "constraint_name", None)
    return str(name) if name else "constraint_violation"


def _fk_subject(error: errors.ForeignKeyViolation) -> str:
    name = str(getattr(error.diag, "constraint_name", "") or "")
    for table, subject in (
            ("type_id", "device_type_not_found"),
            ("location_id", "location_not_found"),
            ("device_id", "device_not_found")):
        if table in name:
            return subject
    return "referenced_record_not_found"


def _append(
    conn: Connection[Any], tenant_id: str, event_type: str, subject_kind: str,
    subject_id: str, payload: dict[str, Any], *, actor_id: str, correlation_id: str,
) -> None:
    """Publish in the caller's transaction, which is the only way it is atomic."""
    events.append_event(
        conn, tenant_id, event_type=event_type, aggregate_type=subject_kind,
        aggregate_id=subject_id, payload=payload, actor_id=actor_id,
        correlation_id=correlation_id,
        idempotency_key=f"{event_type}:{subject_id}:{correlation_id}")


def _settled(error: Exception | None) -> None:
    """Raise after the commit, so a refusal that had to be recorded keeps its evidence.

    MOD-007's and MOD-008's rule: `tenant_scope` rolls back when the block raises, so a path
    that writes evidence and then refuses throws its own evidence away.
    """
    if error is not None:
        raise error


# ------------------------------------------------------------------ device types

def declare_device_type(
    pool: Pool, tenant_id: str, *, type_code: str, vendor: str, model: str, kind: str,
    display_name: str, declared: list[str], actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Declare a model of hardware and what it can be asked to do. Draft until published.

    **The capabilities are written in the same transaction as the type**, because a type with
    none is a model nothing can be commanded on and a second call could leave it that way --
    and once published the trigger refuses an addition, so a half-declared published type is
    permanently wrong.
    """
    code = capabilities.require_name(type_code, "type_code")
    wanted = frozenset(c.strip() for c in declared if c.strip())
    try:
        capabilities.check_declared(kind, wanted)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.dev_device_types
                    (tenant_id, type_code, vendor, model, kind, display_name,
                     created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING type_id
                """,
                (tenant_id, code, capabilities.require_name(vendor, "vendor"),
                 capabilities.require_name(model, "model"), kind,
                 capabilities.require_name(display_name, "display_name"), actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_device_type_code_is_taken") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        type_id = str(row[0])
        for name in sorted(wanted):
            conn.execute(
                "INSERT INTO plt01.dev_type_capabilities"
                " (tenant_id, type_id, capability, created_by, correlation_id)"
                " VALUES (%s, %s, %s, %s, %s)",
                (tenant_id, type_id, name, actor_id, correlation_id))
    return {"type_id": type_id, "type_code": code, "kind": kind, "status": "draft",
            "capabilities": sorted(wanted),
            "detail": ("a draft type takes no devices; publishing it is what settles what "
                       "its units may be asked to do")}


def publish_device_type(
    pool: Pool, tenant_id: str, type_id: str, *, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Settle what this model may be asked to do, so devices can be enrolled against it.

    **Two acts by two people.** Declaring `access.actuate` is what makes a model commandable
    as a barrier and the capability set freezes here, so the author cannot settle their own
    declaration -- `dev_device_types_publisher_is_not_author` is the half the service cannot
    weaken, and this refusal is only the readable message in front of it.

    **Idempotent to the caller.** A client whose request timed out after the commit is told
    the type is published rather than 409, which is MOD-017's finding about three commands
    that answered a conflict for work that had succeeded.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status, kind, created_by, published_by FROM plt01.dev_device_types"
            " WHERE type_id = %s FOR UPDATE",
            (type_id,),
        ).fetchone()
        if row is None:
            raise NotFound("device_type_not_found")
        if str(row[0]) == "published":
            if str(row[3]) != actor_id:
                raise Conflict("this_device_type_was_published_by_somebody_else")
            declared = {
                str(r[0]) for r in conn.execute(
                    "SELECT capability FROM plt01.dev_type_capabilities WHERE type_id = %s",
                    (type_id,)).fetchall()}
            return {"type_id": type_id, "status": "published", "kind": str(row[1]),
                    "capabilities": sorted(declared), "repeated": True}
        if str(row[0]) != "draft":
            raise Conflict(f"this_device_type_is_{row[0]}")
        if str(row[2]) == actor_id:
            raise Conflict("a_device_type_is_published_by_somebody_other_than_its_author")
        declared = {
            str(r[0]) for r in conn.execute(
                "SELECT capability FROM plt01.dev_type_capabilities WHERE type_id = %s",
                (type_id,)).fetchall()}
        if not declared:
            raise Conflict("a_device_type_declares_at_least_one_capability")
        moved = conn.execute(
            "UPDATE plt01.dev_device_types SET status = 'published', published_at = %s,"
            " published_by = %s, publish_correlation_id = %s"
            " WHERE type_id = %s AND status = 'draft'",
            (moment, actor_id, correlation_id, type_id),
        ).rowcount
        if moved == 0:
            raise Conflict("this_device_type_was_published_by_somebody_else")
    return {"type_id": type_id, "status": "published", "kind": str(row[1]),
            "capabilities": sorted(declared), "repeated": False}


def retire_device_type(
    pool: Pool, tenant_id: str, type_id: str, *, reason: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Stop new devices being enrolled against a model. Devices already enrolled keep theirs."""
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("retiring_a_device_type_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            moved = conn.execute(
                "UPDATE plt01.dev_device_types SET status = 'retired', retired_at = %s,"
                " retired_by = %s, retire_reason = %s, retire_correlation_id = %s"
                " WHERE type_id = %s AND status <> 'retired'",
                (moment, actor_id, reason.strip(), correlation_id, type_id),
            ).rowcount
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if moved == 0:
            exists = conn.execute(
                "SELECT 1 FROM plt01.dev_device_types WHERE type_id = %s",
                (type_id,)).fetchone()
            if exists is None:
                raise NotFound("device_type_not_found")
            raise Conflict("this_device_type_is_already_retired")
        live = int((conn.execute(
            "SELECT count(*) FROM plt01.dev_devices"
            " WHERE type_id = %s AND state <> 'retired'",
            (type_id,)).fetchone() or [0])[0])
    return {"type_id": type_id, "status": "retired", "devices_still_enrolled": live,
            "detail": ("devices already enrolled keep the capabilities they snapshotted; "
                       "this stops the next one being enrolled")}


# ---------------------------------------------------------------------- devices

def _device(
    conn: Connection[Any], device_id: str, *, for_update: bool = False,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT d.type_id, d.location_id, d.serial_number, d.display_name, d.state,"
        " d.config, d.last_seen_at, d.revocation_epoch, d.version, d.activated_at,"
        " t.kind, t.status"
        " FROM plt01.dev_devices d"
        " JOIN plt01.dev_device_types t ON t.type_id = d.type_id"
        " WHERE d.device_id = %s"
        + (" FOR UPDATE OF d" if for_update else ""),
        (device_id,),
    ).fetchone()
    if row is None:
        raise NotFound("device_not_found")
    return {"type_id": str(row[0]), "location_id": str(row[1]),
            "serial_number": str(row[2]), "display_name": str(row[3]),
            "state": str(row[4]), "config": row[5], "last_seen_at": row[6],
            "revocation_epoch": int(row[7]), "version": int(row[8]),
            "activated_at": row[9], "kind": str(row[10]), "type_status": str(row[11])}


def _device_capabilities(conn: Connection[Any], device_id: str) -> frozenset[str]:
    """What this unit snapshotted at registration, which is what bounds its commands."""
    return frozenset(
        str(r[0]) for r in conn.execute(
            "SELECT capability FROM plt01.dev_device_capabilities WHERE device_id = %s",
            (device_id,)).fetchall())


def _live_profile(
    conn: Connection[Any], device_id: str,
) -> safety.SafetyProfile | None:
    row = conn.execute(
        "SELECT profile, on_egress_path, fire_release_is_independent,"
        " local_emergency_input FROM plt01.dev_safety_profiles"
        " WHERE device_id = %s AND superseded_at IS NULL",
        (device_id,),
    ).fetchone()
    if row is None:
        return None
    return safety.SafetyProfile(
        profile=str(row[0]), on_egress_path=bool(row[1]),
        fire_release_is_independent=bool(row[2]), local_emergency_input=bool(row[3]))


def _passing_tests(conn: Connection[Any], device_id: str) -> frozenset[str]:
    """Which commissioning tests *most recently* passed.

    **The latest per name, not any pass ever.** A door that passed its fire-alarm test in
    March, failed a re-test in June and was never repaired has a passing row -- and reading
    "has it ever passed" would let it open. Paragraph 4175's words are that a *failed* test
    blocks opening it, which is only true if the latest answer is the one that counts.
    """
    rows = conn.execute(
        "SELECT DISTINCT ON (test_name) test_name, outcome"
        " FROM plt01.dev_commissioning_tests WHERE device_id = %s"
        " ORDER BY test_name, tested_at DESC, test_id DESC",
        (device_id,),
    ).fetchall()
    return frozenset(str(r[0]) for r in rows if str(r[1]) == "passed")


def _certificates(
    conn: Connection[Any], device_id: str,
) -> list[certificates.Certificate]:
    return [
        certificates.Certificate(
            fingerprint=str(r[0]), state=str(r[1]), not_before=r[2], not_after=r[3])
        for r in conn.execute(
            "SELECT fingerprint, state, not_before, not_after"
            " FROM plt01.dev_certificates WHERE device_id = %s ORDER BY issued_at",
            (device_id,)).fetchall()]


def register_device(
    pool: Pool, tenant_id: str, *, type_id: str, location_id: str, serial_number: str,
    display_name: str, config: dict[str, Any] | None, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """RegisterDevice. Paragraph 3077's enrollment, with the capability snapshot.

    **The capabilities are copied from the type in this transaction**, which is MOD-012's
    install shape: a command is bounded by *this unit's* list, so somebody has to be able to
    answer "what was this box authorised to do in March" without a join to a type whose
    declaration has since moved. A device with no capability rows would be one every command
    is refused for, which reads as a broken unit rather than an unfinished enrolment.

    **Only a published type takes devices.** A draft is a declaration somebody is still
    writing, and the trigger that freezes a published type's capabilities is what makes the
    snapshot meaningful -- taken from a draft it would be a copy of something still moving.
    """
    serial = capabilities.require_name(serial_number, "serial_number")
    try:
        capabilities.check_small_object(config or {}, "config")
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        kind_row = conn.execute(
            "SELECT kind, status FROM plt01.dev_device_types WHERE type_id = %s",
            (type_id,),
        ).fetchone()
        if kind_row is None:
            raise NotFound("device_type_not_found")
        if str(kind_row[1]) != "published":
            raise Conflict(f"this_device_type_is_{kind_row[1]}")
        declared = {
            str(r[0]) for r in conn.execute(
                "SELECT capability FROM plt01.dev_type_capabilities WHERE type_id = %s",
                (type_id,)).fetchall()}
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.dev_devices
                    (tenant_id, type_id, location_id, serial_number, display_name,
                     config, created_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING device_id
                """,
                (tenant_id, type_id, location_id, serial,
                 capabilities.require_name(display_name, "display_name"),
                 json.dumps(config or {}), actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_serial_number_is_already_enrolled") from None
        except errors.ForeignKeyViolation as e:
            raise NotFound(_fk_subject(e)) from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        device_id = str(row[0])
        for name in sorted(declared):
            conn.execute(
                "INSERT INTO plt01.dev_device_capabilities"
                " (tenant_id, device_id, capability, created_by, correlation_id)"
                " VALUES (%s, %s, %s, %s, %s)",
                (tenant_id, device_id, name, actor_id, correlation_id))
        _append(conn, tenant_id, "device.enrolled", "device", device_id,
                {"device_id": device_id, "type_id": type_id,
                 "location_id": location_id, "kind": str(kind_row[0]),
                 "capabilities": sorted(declared)},
                actor_id=actor_id, correlation_id=correlation_id)
    return {"device_id": device_id, "state": "registered", "kind": str(kind_row[0]),
            "capabilities": sorted(declared),
            "needs_safety_profile": capabilities.ACTUATING in declared,
            "detail": ("a registered device has no certificate and operates nothing; "
                       "provisioning gives it one")}


def provision_device(
    pool: Pool, tenant_id: str, device_id: str, *, fingerprint: str, vault_ref: str,
    not_before: datetime, not_after: datetime, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """ProvisionEdgeAgent: the device's first certificate, and its move out of `registered`.

    **The fingerprint is normalised before it is stored**, by the same function that checks it
    against the vendor-default list -- so a caller cannot have one spelling checked and another
    written, which is the derive-don't-accept shape five modules of this build have paid for.
    """
    with tenant_scope(pool, tenant_id) as conn:
        device = _device(conn, device_id, for_update=True)
        try:
            enrollment.check_transition(device["state"], "provisioned")
            folded = certificates.check_issue(
                fingerprint, not_before=not_before, not_after=not_after)
        except ValueError as e:
            raise Conflict(str(e)) from None
        try:
            cert = conn.execute(
                """
                INSERT INTO plt01.dev_certificates
                    (tenant_id, device_id, fingerprint, vault_ref, state, not_before,
                     not_after, issued_by, correlation_id)
                VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s)
                RETURNING certificate_id
                """,
                (tenant_id, device_id, folded, vault_ref.strip(), not_before, not_after,
                 actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict(
                "this_fingerprint_is_already_enrolled_in_this_tenant") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert cert is not None
        conn.execute(
            "UPDATE plt01.dev_devices SET state = 'provisioned', version = version + 1"
            " WHERE device_id = %s AND state = 'registered'",
            (device_id,))
    return {"device_id": device_id, "state": "provisioned",
            "certificate_id": str(cert[0]), "fingerprint": folded,
            "detail": ("the material itself is wherever the vault reference points; this "
                       "build holds no key and has no column for one")}


def configure_device(
    pool: Pool, tenant_id: str, device_id: str, *, display_name: str | None,
    config: dict[str, Any] | None, expected_version: int, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """ConfigureDevice, under paragraph 3092's optimistic concurrency.

    **The version the caller read is the version this writes against.** Two operators editing
    one device is the ordinary case; last-write-wins discards whichever finished first and
    leaves no trace, which is MOD-014's argument for the same column.
    """
    try:
        capabilities.check_small_object(config or {}, "config")
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        device = _device(conn, device_id, for_update=True)
        if device["state"] == "retired":
            raise Conflict("this_device_is_retired")
        name = (capabilities.require_name(display_name, "display_name")
                if display_name is not None else device["display_name"])
        try:
            moved = conn.execute(
                "UPDATE plt01.dev_devices SET display_name = %s, config = %s,"
                " version = version + 1"
                " WHERE device_id = %s AND version = %s",
                (name, json.dumps(device["config"] if config is None else config),
                 device_id, expected_version),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        if moved == 0:
            raise Conflict("this_device_was_changed_by_somebody_else")
    return {"device_id": device_id, "version": expected_version + 1,
            "display_name": name}


# ------------------------------------------------- commissioning and going live

def commission_access_point(
    pool: Pool, tenant_id: str, device_id: str, *, profile: str, on_egress_path: bool,
    fire_release_is_independent: bool, local_emergency_input: bool, evidence_ref: str,
    door_description: str, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Record the hardware safety profile. TSD paragraph 4172.

    **Refused rather than recorded with a warning when it claims software control of egress.**
    `safety.check_profile` and the constraint beside the table say the same thing, because a
    building whose records pass an audit it would fail is worse than one with no records: a
    fail-secure barrier on an egress path holds the door shut when the power goes.

    **A re-commissioning supersedes rather than edits**, in the same transaction, so there is
    never a moment with two live profiles or none.
    """
    moment = at or _now()
    claimed = safety.SafetyProfile(
        profile=profile, on_egress_path=on_egress_path,
        fire_release_is_independent=fire_release_is_independent,
        local_emergency_input=local_emergency_input)
    try:
        safety.check_profile(claimed)
    except ValueError as e:
        raise Conflict(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        _device(conn, device_id, for_update=True)
        prior = conn.execute(
            "SELECT profile_id FROM plt01.dev_safety_profiles"
            " WHERE device_id = %s AND superseded_at IS NULL FOR UPDATE",
            (device_id,),
        ).fetchone()
        # **Superseded before the replacement is inserted**, which is the only order
        # `one_live_per_device` admits -- and the self-reference is deferred so the outgoing
        # row may name a profile this transaction has not written yet.
        profile_id = str(uuid4())
        if prior is not None:
            conn.execute(
                "UPDATE plt01.dev_safety_profiles SET superseded_at = %s,"
                " superseded_by = %s, supersede_correlation_id = %s"
                " WHERE profile_id = %s AND superseded_at IS NULL",
                (moment, profile_id, correlation_id, str(prior[0])))
        try:
            conn.execute(
                """
                INSERT INTO plt01.dev_safety_profiles
                    (tenant_id, profile_id, device_id, profile, on_egress_path,
                     fire_release_is_independent, local_emergency_input, evidence_ref,
                     door_description, commissioned_at, commissioned_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, profile_id, device_id, profile, on_egress_path,
                 fire_release_is_independent, local_emergency_input,
                 evidence_ref.strip(),
                 capabilities.require_name(door_description, "door_description"),
                 moment, actor_id, correlation_id))
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        outstanding = safety.missing_tests(_passing_tests(conn, device_id))
    return {"device_id": device_id, "profile_id": profile_id, "profile": profile,
            "on_egress_path": on_egress_path,
            "superseded": None if prior is None else str(prior[0]),
            "outstanding_tests": list(outstanding),
            "detail": ("these are claims a named commissioner made; this software cannot "
                       "verify a building's wiring, and it will not open the door until "
                       "every commissioning test has a passing record")}


def record_commissioning_test(
    pool: Pool, tenant_id: str, device_id: str, *, test_name: str, passed: bool,
    detail: str | None, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Paragraph 4175's test record. Insert-only, so a failure cannot be edited into a pass.

    **A failure is recorded and it blocks**: `_passing_tests` reads the latest answer per
    name, so a re-test after a repair is another row and a door that failed in June does not
    open on a pass from March.

    **And a failure on a door already in service takes it out of service, here.** The first
    version recorded the row, recomputed `may_go_live`, returned `False` to the caller and
    changed nothing -- so an access point whose fire-alarm release failed its periodic
    re-test went on unlocking on request, because `safety.may_go_live` is read at activation
    and a live device never returns to that gate. That is this repository's own "a control
    consulted once is a control with a window", in the module whose rules are a fire code.
    The device is quarantined in the same transaction as the record, attributed to whoever
    recorded the failure, and `activate_device` is the only way back -- which re-enters the
    gate and refuses until the re-test passes.
    """
    moment = at or _now()
    try:
        safety.check_test_name(test_name)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    if not passed and not (detail or "").strip():
        raise InvalidRequest("a_failed_safety_test_says_what_happened")
    with tenant_scope(pool, tenant_id) as conn:
        _device(conn, device_id)
        try:
            conn.execute(
                "INSERT INTO plt01.dev_commissioning_tests"
                " (tenant_id, device_id, test_name, outcome, detail, tested_at,"
                "  tested_by, correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (tenant_id, device_id, test_name, "passed" if passed else "failed",
                 (detail or "").strip() or None, moment, actor_id, correlation_id))
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        passing = _passing_tests(conn, device_id)
        outstanding = safety.missing_tests(passing)
        withdrawn = False
        if not passed:
            device = _device(conn, device_id, for_update=True)
            if device["state"] == "active":
                conn.execute(
                    "UPDATE plt01.dev_devices SET state = 'quarantined',"
                    " version = version + 1, quarantined_at = %s, quarantined_by = %s,"
                    " quarantine_reason = %s, quarantine_correlation_id = %s"
                    " WHERE device_id = %s AND state = 'active'",
                    (moment, actor_id,
                     f"the {test_name} safety test failed; paragraph 4175 blocks opening "
                     f"this access point until it passes again",
                     correlation_id, device_id))
                withdrawn = True
    return {"device_id": device_id, "test_name": test_name,
            "outcome": "passed" if passed else "failed",
            "outstanding_tests": list(outstanding),
            "may_go_live": not outstanding,
            "withdrawn_from_service": withdrawn,
            "detail": (
                "this access point is quarantined and takes no command until it is "
                "re-activated, which re-runs the commissioning gate" if withdrawn
                else "nothing about this device's state changed")}


def activate_device(
    pool: Pool, tenant_id: str, device_id: str, *, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Bring a device into service. **This is the commissioning gate.**

    Paragraph 4175: "A failed safety test blocks opening the access point in production." The
    gate is here, where somebody is doing it deliberately, rather than on each command: a
    per-command check would leave a half-commissioned door live and refusing every request,
    which reads as a broken reader rather than an uncommissioned door.

    Two refusals, read together against rows this transaction locked:

      * `safety.may_go_live` -- is the *door* safe: a profile that does not claim software
        control of egress, and a passing record for every one of paragraph 4175's tests.
      * `certificates.check_may_activate` -- can the *device* prove who it is. Paragraph 3083
        with the word "rotating" removed is a device live with nothing to authenticate.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        device = _device(conn, device_id, for_update=True)
        try:
            enrollment.check_transition(device["state"], "active")
        except ValueError as e:
            raise Conflict(str(e)) from None
        declared = _device_capabilities(conn, device_id)
        try:
            safety.may_go_live(
                profile=_live_profile(conn, device_id),
                passed=_passing_tests(conn, device_id),
                actuates=capabilities.ACTUATING in declared)
            certificates.check_may_activate(
                _certificates(conn, device_id), at=moment)
        except ValueError as e:
            raise Conflict(str(e)) from None
        first = device["activated_at"] is None
        # **A return to service is a decision too.** `activated_*` is the first one and is
        # final by trigger, correctly -- but this function re-runs the commissioning gate on
        # every pass, so a quarantine-and-return is another passage through it. The first
        # version wrote nothing on that pass, and a live door's fire-code attribution named
        # whoever activated it months earlier.
        conn.execute(
            "UPDATE plt01.dev_devices SET state = 'active', version = version + 1"
            + (", activated_at = %s, activated_by = %s, activate_correlation_id = %s"
               if first
               else ", reactivated_at = %s, reactivated_by = %s,"
                    " reactivate_correlation_id = %s")
            + " WHERE device_id = %s AND state = %s",
            (moment, actor_id, correlation_id, device_id, device["state"]))
    return {"device_id": device_id, "state": "active", "first_activation": first,
            "detail": ("this device is in service; nothing in this build drives its "
                       "hardware, so what happens next is the edge agent's")}


def set_device_state(
    pool: Pool, tenant_id: str, device_id: str, *, target: str, reason: str | None,
    actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """QuarantineDevice, maintenance mode, and retirement -- one command for three moves.

    **One function because the lifecycle is one machine.** Three near-identical commands
    diverge: MOD-013's review found a `fail_run` that admitted a state its sibling refused, and
    the consequence was a run that could never reach `dead`. Here the machine is
    `enrollment.EDGES` and the trigger beside the table says the same thing.

    **Quarantine and retirement state why; maintenance does not.** Quarantine is what somebody
    does when a unit is suspect and retirement ends it, so both carry a reason onto a row with
    no UPDATE grant. Putting a device into maintenance is a shift decision, and demanding prose
    for it is how an operator learns to type a full stop.
    """
    moment = at or _now()
    if target in ("quarantined", "retired") and not (reason or "").strip():
        raise InvalidRequest(f"moving_a_device_to_{target}_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        device = _device(conn, device_id, for_update=True)
        try:
            enrollment.check_transition(device["state"], target)
        except ValueError as e:
            raise Conflict(str(e)) from None
        if target == "active":
            raise InvalidRequest("activating_a_device_runs_the_commissioning_gate")
        columns = {
            "quarantined": ("quarantined_at = %s, quarantined_by = %s,"
                            " quarantine_reason = %s, quarantine_correlation_id = %s"),
            "retired": ("retired_at = %s, retired_by = %s, retire_reason = %s,"
                        " retire_correlation_id = %s"),
        }.get(target)
        params: tuple[Any, ...]
        if columns is None:
            sql = ("UPDATE plt01.dev_devices SET state = %s, version = version + 1"
                   " WHERE device_id = %s AND state = %s")
            params = (target, device_id, device["state"])
        else:
            sql = (f"UPDATE plt01.dev_devices SET state = %s, version = version + 1,"
                   f" {columns} WHERE device_id = %s AND state = %s")
            params = (target, moment, actor_id, (reason or "").strip(), correlation_id,
                      device_id, device["state"])
        try:
            moved = conn.execute(sql, params).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if moved == 0:
            raise Conflict("this_device_was_moved_by_somebody_else")
        # **Retiring a device revokes what authenticates it, in this transaction.** A retired
        # unit whose certificate still works is a box somebody took off a wall that can still
        # talk to the registry -- and the epoch bump is what tells every gateway holding a
        # snapshot that something was withdrawn.
        revoked = 0
        if target == "retired":
            revoked = conn.execute(
                "UPDATE plt01.dev_certificates SET state = 'revoked', revoked_at = %s,"
                " revoked_by = %s, revoke_reason = 'the device was retired',"
                " revoke_correlation_id = %s"
                " WHERE device_id = %s AND state IN ('pending', 'active', 'superseded')",
                (moment, actor_id, correlation_id, device_id)).rowcount
            if revoked:
                conn.execute(
                    "UPDATE plt01.dev_devices"
                    "   SET revocation_epoch = revocation_epoch + 1"
                    " WHERE device_id = %s", (device_id,))
    return {"device_id": device_id, "state": target,
            "certificates_revoked": revoked,
            "detail": (None if target != "retired" else
                       "a retired device's certificates are revoked and every gateway's "
                       "snapshot is now behind the revocation epoch")}


# ----------------------------------------------------------------- certificates

def rotate_certificate(
    pool: Pool, tenant_id: str, device_id: str, *, fingerprint: str, vault_ref: str,
    not_before: datetime, not_after: datetime, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """RotateDeviceCertificate. Paragraph 3083's "rotating".

    **The outgoing certificate is superseded, not revoked.** It stays honoured until its own
    expiry, because a device whose certificate was replaced the instant the new one was issued
    is locked out for as long as it takes to receive the new one -- which for a gateway on a
    flaky link is long enough to shut a club. Revocation is the other path and is immediate;
    that is the difference between the two states.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        device = _device(conn, device_id, for_update=True)
        if device["state"] == "retired":
            raise Conflict("this_device_is_retired")
        try:
            folded = certificates.check_issue(
                fingerprint, not_before=not_before, not_after=not_after)
        except ValueError as e:
            raise Conflict(str(e)) from None
        outgoing = conn.execute(
            "SELECT certificate_id FROM plt01.dev_certificates"
            " WHERE device_id = %s AND state = 'active' FOR UPDATE",
            (device_id,),
        ).fetchone()
        # **The new id is generated here, so the outgoing row can point at it before it
        # exists.** Every other order breaks something: inserting first violates
        # `one_active_per_device`, and setting `superseded_at` with a null `superseded_by`
        # violates the pairing. The reference is `DEFERRABLE INITIALLY DEFERRED`, so the
        # pointer is checked at commit -- by which time the row is there.
        new_id = str(uuid4())
        if outgoing is not None:
            conn.execute(
                "UPDATE plt01.dev_certificates SET state = 'superseded',"
                " superseded_at = %s, superseded_by = %s"
                " WHERE certificate_id = %s AND state = 'active'",
                (moment, new_id, str(outgoing[0])))
        try:
            conn.execute(
                """
                INSERT INTO plt01.dev_certificates
                    (tenant_id, certificate_id, device_id, fingerprint, vault_ref,
                     state, not_before, not_after, issued_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s, %s)
                """,
                (tenant_id, new_id, device_id, folded, vault_ref.strip(), not_before,
                 not_after, actor_id, correlation_id))
        except errors.UniqueViolation:
            raise Conflict(
                "this_fingerprint_is_already_enrolled_in_this_tenant") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    return {"device_id": device_id, "certificate_id": new_id, "fingerprint": folded,
            "superseded": None if outgoing is None else str(outgoing[0]),
            "detail": ("the outgoing certificate is honoured until it expires, so a device "
                       "on a slow link is not locked out while it collects the new one")}


def revoke_certificate(
    pool: Pool, tenant_id: str, certificate_id: str, *, reason: str, actor_id: str,
    correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Withdraw a certificate now, and bump the device's revocation epoch with it.

    **One transaction, which is the whole point.** A gateway compares its snapshot's epoch
    numerically, so a revocation that committed before the epoch bump is a window in which
    every stale snapshot still looks current -- MOD-010's `append_event` argument where the
    state is a door.

    **And revoking the last usable certificate takes the device out of service.** The first
    version computed `device_can_still_authenticate`, returned it to the caller and acted on
    nothing: a live access point with no certificate went on accepting unlock commands and
    policy snapshots, which is exactly the state `certificates.check_may_activate` exists to
    refuse at the other end. A value returned to the caller and never recorded is the shape
    MOD-011 and MOD-012 were each blocked on.
    """
    moment = at or _now()
    if not reason.strip():
        raise InvalidRequest("revoking_a_certificate_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT device_id, state FROM plt01.dev_certificates"
            " WHERE certificate_id = %s FOR UPDATE",
            (certificate_id,),
        ).fetchone()
        if row is None:
            raise NotFound("certificate_not_found")
        if str(row[1]) == "revoked":
            raise Conflict("this_certificate_is_already_revoked")
        device_id = str(row[0])
        try:
            moved = conn.execute(
                "UPDATE plt01.dev_certificates SET state = 'revoked', revoked_at = %s,"
                " revoked_by = %s, revoke_reason = %s, revoke_correlation_id = %s"
                " WHERE certificate_id = %s AND state <> 'revoked'",
                (moment, actor_id, reason.strip(), correlation_id, certificate_id),
            ).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if moved == 0:
            raise Conflict("this_certificate_was_revoked_by_somebody_else")
        epoch = conn.execute(
            "UPDATE plt01.dev_devices SET revocation_epoch = revocation_epoch + 1"
            " WHERE device_id = %s RETURNING revocation_epoch",
            (device_id,)).fetchone()
        remaining = _certificates(conn, device_id)
        usable = any(certificates.is_usable(c, at=moment) for c in remaining)
        withdrawn = False
        if not usable:
            device = _device(conn, device_id, for_update=True)
            if device["state"] == "active":
                conn.execute(
                    "UPDATE plt01.dev_devices SET state = 'quarantined',"
                    " version = version + 1, quarantined_at = %s, quarantined_by = %s,"
                    " quarantine_reason = %s, quarantine_correlation_id = %s"
                    " WHERE device_id = %s AND state = 'active'",
                    (moment, actor_id,
                     "its last usable certificate was revoked, so nothing authenticates "
                     "what this device says or what is sent to it",
                     correlation_id, device_id))
                withdrawn = True
    return {"certificate_id": certificate_id, "device_id": device_id,
            "state": "revoked",
            "revocation_epoch": int(epoch[0]) if epoch else None,
            "device_can_still_authenticate": usable,
            "withdrawn_from_service": withdrawn,
            "detail": ("every gateway holding a snapshot built before this epoch has "
                       "missed a withdrawal and may refuse but not admit")}


# -------------------------------------------------------------------- firmware

def release_firmware(
    pool: Pool, tenant_id: str, *, type_id: str, version: str, image_ref: str,
    image_digest: str, release_notes: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """UpdateEdgeAgent's first half: a version exists and where its image is.

    **No binary here and no column for one.** `image_ref` locates it and `image_digest` is
    what a gateway checks what it fetched against, which is the same split as a certificate's
    `vault_ref` and for the same reason.
    """
    with tenant_scope(pool, tenant_id) as conn:
        kind = conn.execute(
            "SELECT status FROM plt01.dev_device_types WHERE type_id = %s",
            (type_id,)).fetchone()
        if kind is None:
            raise NotFound("device_type_not_found")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.dev_firmware
                    (tenant_id, type_id, version, image_ref, image_digest,
                     release_notes, released_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING firmware_id
                """,
                (tenant_id, type_id, capabilities.require_name(version, "version"),
                 image_ref.strip(), image_digest.strip().lower(),
                 capabilities.require_name(release_notes, "release_notes"), actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_version_is_already_released_for_this_type") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        firmware_id = str(row[0])
        _append(conn, tenant_id, "firmware.updated", "firmware", firmware_id,
                {"firmware_id": firmware_id, "type_id": type_id, "version": version,
                 "status": "available"},
                actor_id=actor_id, correlation_id=correlation_id)
    return {"firmware_id": firmware_id, "type_id": type_id, "version": version,
            "status": "available",
            "detail": ("nothing in this build installs firmware; a gateway fetches the "
                       "image and checks it against the digest")}


def set_firmware_status(
    pool: Pool, tenant_id: str, firmware_id: str, *, target: str, reason: str | None,
    actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Stage a version to part of the fleet, un-stage it, or withdraw it for good.

    Paragraph 3080's staged rollout. **A withdrawal is final**, by trigger: a fixed build is a
    new version, and a withdrawn one coming back is a gateway fetching an image somebody
    pulled for a reason.
    """
    moment = at or _now()
    if target not in ("available", "staged", "withdrawn"):
        raise InvalidRequest("unknown_firmware_status")
    if target == "withdrawn" and not (reason or "").strip():
        raise InvalidRequest("withdrawing_firmware_states_why")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT status, type_id, version FROM plt01.dev_firmware"
            " WHERE firmware_id = %s FOR UPDATE",
            (firmware_id,)).fetchone()
        if row is None:
            raise NotFound("firmware_not_found")
        if str(row[0]) == target:
            raise Conflict(f"this_firmware_is_already_{target}")
        sql = ("UPDATE plt01.dev_firmware SET status = %s"
               + (", withdrawn_at = %s, withdrawn_by = %s, withdraw_reason = %s,"
                  " withdraw_correlation_id = %s" if target == "withdrawn" else "")
               + " WHERE firmware_id = %s AND status = %s")
        params: tuple[Any, ...] = (
            (target, moment, actor_id, (reason or "").strip(), correlation_id,
             firmware_id, str(row[0])) if target == "withdrawn"
            else (target, firmware_id, str(row[0])))
        try:
            moved = conn.execute(sql, params).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if moved == 0:
            raise Conflict("this_firmware_was_changed_by_somebody_else")
        _append(conn, tenant_id, "firmware.updated", "firmware", firmware_id,
                {"firmware_id": firmware_id, "type_id": str(row[1]),
                 "version": str(row[2]), "status": target},
                actor_id=actor_id, correlation_id=correlation_id)
    return {"firmware_id": firmware_id, "status": target}


# ------------------------------------------------------------ policy snapshots

def publish_snapshot(
    pool: Pool, tenant_id: str, device_id: str, *, content_digest: str,
    signature_ref: str | None, ttl_minutes: int, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """PublishDevicePolicy: the signed authorization projection, with its bound.

    **The epoch is the device's own, read in this transaction.** A snapshot built at an older
    epoch has missed a revocation before it was even issued, which the trigger beside the
    table refuses as well -- the service deriving it correctly says nothing about the writer
    that is not the service.

    **The TTL is bounded here and in the schema.** Paragraph 1949 says "bounded" and names no
    number; `snapshots.MAX_TTL` is twelve hours and says why, read against paragraph 1953's
    sixty-second revocation target.
    """
    moment = at or _now()
    expires = moment + timedelta(minutes=ttl_minutes)
    try:
        snapshots.check_ttl(moment, expires)
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        device = _device(conn, device_id, for_update=True)
        if not enrollment.is_operable(device["state"]):
            raise Conflict(
                f"this_device_is_{device['state']}_and_takes_no_policy")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.dev_policy_snapshots
                    (tenant_id, device_id, revocation_epoch, content_digest,
                     signature_ref, issued_at, expires_at, issued_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING snapshot_id
                """,
                (tenant_id, device_id, device["revocation_epoch"],
                 content_digest.strip().lower(),
                 (signature_ref or "").strip() or None, moment, expires, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        assert row is not None
    return {"snapshot_id": str(row[0]), "device_id": device_id,
            "revocation_epoch": device["revocation_epoch"],
            "issued_at": moment.isoformat(), "expires_at": expires.isoformat(),
            "detail": ("this build signs nothing; the reference is where the signature a "
                       "gateway verifies lives, and the digest is what it covers")}


# -------------------------------------------------------------------- commands


def _prior_command(conn: Connection[Any], key: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT command_id, device_id, action, state, expires_at, arguments, issued_at"
        " FROM plt01.dev_commands WHERE idempotency_key = %s",
        (key,)).fetchone()
    if row is None:
        return None
    return {"command_id": str(row[0]), "device_id": str(row[1]), "action": str(row[2]),
            "state": str(row[3]), "expires_at": row[4], "arguments": row[5] or {},
            "issued_at": row[6]}


def _repeat_of(
    prior: dict[str, Any], *, device_id: str, action: str, args: dict[str, Any],
    expires_in_seconds: int | None, at: datetime,
) -> dict[str, Any]:
    """Answer a retry from what was recorded, or refuse it for being a different request.

    **Every field the command takes.** The device and the action were the only two compared
    in the first version, so one key reused across two doors returned the other door's
    command id with `repeated: True` -- the shape MOD-019 and MOD-020 each shipped once.

    **The window is computed last, and only here.** Computing it before the device is read
    would put `check_action` ahead of `check_command_safety`, and the whole argument for that
    ordering is that somebody probing the fire-code refusal must be told about the fire code
    rather than about a vocabulary. On this path the stored action is one that already
    passed, so the bound cannot be the first thing a caller hears about.
    """
    if (prior["device_id"] != device_id or prior["action"] != action
            or prior["arguments"] != args):
        raise Conflict("this_idempotency_key_was_used_for_a_different_request")
    try:
        requested = commands.requested_window(
            action,
            timedelta(seconds=expires_in_seconds) if expires_in_seconds is not None
            else None)
    except ValueError as e:
        raise Conflict(str(e)) from None
    if prior["expires_at"] - prior["issued_at"] != requested:
        raise Conflict("this_idempotency_key_was_used_for_a_different_request")
    state = prior["state"]
    if state == "issued" and at >= prior["expires_at"]:
        state = "expired"
    return {"command_id": prior["command_id"], "device_id": device_id, "action": action,
            "state": state, "expires_at": prior["expires_at"].isoformat(),
            "repeated": True}

def issue_command(
    pool: Pool, tenant_id: str, device_id: str, *, action: str,
    arguments: dict[str, Any] | None, idempotency_key: str, expires_in_seconds: int | None,
    actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """The pool-taking wrapper. Correct where there is no state change to be atomic with.

    MOD-010's rule about `append_event`, applied to a door: where a caller *is* writing state
    that must commit with the command -- MOD-022's access decision -- it calls
    `issue_command_on` with its own connection instead. A route that only queues a command has
    no such state, so this is the honest shape for it.
    """
    with tenant_scope(pool, tenant_id) as conn:
        return issue_command_on(
            conn, tenant_id, device_id=device_id, action=action, arguments=arguments,
            idempotency_key=idempotency_key, expires_in_seconds=expires_in_seconds,
            actor_id=actor_id, correlation_id=correlation_id, at=at)


def issue_command_on(
    conn: Connection[Any], tenant_id: str, *, device_id: str, action: str,
    arguments: dict[str, Any] | None, idempotency_key: str, expires_in_seconds: int | None,
    actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Paragraph 3084's command: scoped, signed, audited and bounded by device safety.

    **Takes the connection**, so a caller writing the state that justifies the command commits
    both or neither. MOD-022's `_record` is the first such caller: a door that opened with no
    decision row is an entry nobody can account for, and a decision row with no command is a
    member told they were admitted while standing at a locked door.

    **The safety refusal is first and has no override.** `commands.check_issue` calls
    `safety.check_command_safety` before it looks at the capability or the state, because the
    message somebody reads has to name the reason that matters -- and a reviewer probing
    paragraph 4173 must not be told about a state instead.

    **The key is compared on every field, and that now means every field.** MOD-019 shipped
    one checked on a single field and handed one member another's hold; MOD-020 shipped three
    compared against nothing; this one claimed all five in its docstring and compared two, so
    a console reusing its per-shift counter was told 201 `repeated` and shown a live command
    id while the command that exists targeted a different door with different arguments. The
    comparison is the device, the action, the arguments and the requested window -- the key
    itself is the fifth.

    **The repeat's state is derived, not read back raw.** An unlock whose minute has passed
    is `issued` in the column until something expires it, so answering a retry with the
    stored value tells a till the door was told to open when the command is already dead.
    """
    moment = at or _now()
    key = capabilities.require_name(idempotency_key, "idempotency_key")
    args = arguments or {}
    prior = _prior_command(conn, key)
    if prior is not None:
        return _repeat_of(prior, device_id=device_id, action=action, args=args,
                          expires_in_seconds=expires_in_seconds, at=moment)
    device = _device(conn, device_id, for_update=True)
    declared = _device_capabilities(conn, device_id)
    profile = _live_profile(conn, device_id)
    try:
        window = commands.check_issue(
            action, declared=declared, state=device["state"], profile=profile,
            arguments=args,
            expires_in=(timedelta(seconds=expires_in_seconds)
                        if expires_in_seconds is not None else None))
    except ValueError as e:
        raise Conflict(str(e)) from None
    expires = moment + window
    digest = commands.digest(
        device_id=device_id, action=action, arguments=args, issued_at=moment,
        expires_at=expires)
    try:
        # **The conflict target is named.** `ON CONFLICT DO NOTHING` with no target stays
        # valid SQL when the unique rule is dropped and silently stops deduplicating,
        # which is MOD-010's finding about `evt_deliveries`.
        row = conn.execute(
            """
            INSERT INTO plt01.dev_commands
                (tenant_id, device_id, action, arguments, payload_digest,
                 expires_at, idempotency_key, issued_at, issued_by, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING command_id
            """,
            (tenant_id, device_id, action, json.dumps(args), digest, expires, key,
             moment, actor_id, correlation_id),
        ).fetchone()
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    except errors.RaiseException as e:
        raise Conflict(str(e).strip().splitlines()[0]) from None
    if row is None:
        # A genuine retry that lost the race. The first version raised
        # "used for a different request" here, which is the opposite of what happened.
        prior = _prior_command(conn, key)
        assert prior is not None
        return _repeat_of(prior, device_id=device_id, action=action, args=args,
                          expires_in_seconds=expires_in_seconds, at=moment)
    return {"command_id": str(row[0]), "device_id": device_id, "action": action,
            "state": "issued", "payload_digest": digest,
            "expires_at": expires.isoformat(), "repeated": False,
            "detail": ("nothing here delivers this; a gateway collects it and reports what "
                       "happened, and it expires unsent if nothing does")}


def deliver_command(
    pool: Pool, tenant_id: str, command_id: str, *, signature_ref: str | None,
    actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """Hand a command over. **An expired one is settled as expired rather than delivered.**

    A device offline when an unlock was issued must not receive it a minute later and open a
    door for whoever is standing there now -- so the deadline is re-read here, under a lock on
    the row, and a stale command is settled on the spot. "A control consulted once is a
    control with a window" is MOD-009's rule, and a command queue is a window by construction.

    **And the device's own state is re-read with it.** `issue_command` refuses a command to
    a device out of service, and the first version of this function did not -- so quarantining
    a suspect door on a stepped-up permission did nothing about the unlock issued a minute
    earlier, which a routine agent session then collected. The window is up to twenty-four
    hours for a firmware or certificate command. Quarantine is the act that is *supposed* to
    stop a device being used, so a command it can still collect is the control with its own
    hole in it.
    """
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT device_id, action, state, issued_at, expires_at"
            " FROM plt01.dev_commands WHERE command_id = %s FOR UPDATE",
            (command_id,)).fetchone()
        if row is None:
            raise NotFound("command_not_found")
        device = _device(conn, str(row[0]))
        if not enrollment.is_operable(device["state"]):
            raise Conflict(
                f"this device is {device['state']}; a command is collected by a device in "
                f"service, and taking one out of service stops what was already queued")
        live = commands.Command(
            action=str(row[1]), state=str(row[2]), issued_at=row[3], expires_at=row[4])
        if commands.has_expired(live, at=moment):
            conn.execute(
                "UPDATE plt01.dev_commands SET state = 'expired', settled_at = %s,"
                " settled_by = %s, settle_correlation_id = %s,"
                " outcome_detail = 'nothing collected it before its deadline'"
                " WHERE command_id = %s AND state IN ('issued', 'delivered')",
                (moment, actor_id, correlation_id, command_id))
            return {"command_id": command_id, "state": "expired",
                    "detail": ("this command expired before the device collected it; issue "
                               "another if it is still wanted")}
        try:
            commands.may_deliver(live, at=moment)
        except ValueError as e:
            raise Conflict(str(e)) from None
        moved = conn.execute(
            "UPDATE plt01.dev_commands SET state = 'delivered', delivered_at = %s,"
            " delivered_by = %s, delivery_correlation_id = %s, signature_ref = %s"
            " WHERE command_id = %s AND state = 'issued'",
            (moment, actor_id, correlation_id, (signature_ref or "").strip() or None,
             command_id)).rowcount
        if moved == 0:
            raise Conflict("this_command_was_collected_by_somebody_else")
    return {"command_id": command_id, "device_id": str(row[0]), "state": "delivered",
            "action": str(row[1])}


def settle_command(
    pool: Pool, tenant_id: str, command_id: str, *, outcome: str, detail: str | None,
    actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """What the device reported. `acknowledged`, `completed` or `failed`.

    **Written by whatever drove the hardware, which is not this build.** A row saying a
    turnstile opened, written by nothing that drives a turnstile, is the fabricated-evidence
    shape this codebase has been bitten by six times -- so this takes a report and records who
    made it rather than performing anything.

    **And it now records them.** The first version took an `actor_id`, used it only for the
    `completed` event and left the row naming whoever *issued* the command -- so the only
    name on a record that a door opened was the party that did not make the claim, and
    `failed`, `acknowledged` and `expired` named nobody anywhere. `devices.agent.report` is
    routine, AAL 1 and tenant-wide, which is what makes the attribution the whole control.
    """
    moment = at or _now()
    if outcome not in ("acknowledged", "completed", "failed"):
        raise InvalidRequest("unknown_command_outcome")
    if outcome == "failed" and not (detail or "").strip():
        raise InvalidRequest("a_failed_command_says_what_happened")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT device_id, action, state FROM plt01.dev_commands"
            " WHERE command_id = %s FOR UPDATE",
            (command_id,)).fetchone()
        if row is None:
            raise NotFound("command_not_found")
        try:
            commands.check_transition(str(row[2]), outcome)
        except ValueError as e:
            raise Conflict(str(e)) from None
        settles = outcome in ("completed", "failed")
        sql = ("UPDATE plt01.dev_commands SET state = %s, outcome_detail = %s"
               + (", settled_at = %s, settled_by = %s, settle_correlation_id = %s"
                  if settles else ", acknowledged_at = %s")
               + " WHERE command_id = %s AND state = %s")
        values: tuple[Any, ...] = (
            (outcome, (detail or "").strip() or None, moment, actor_id, correlation_id,
             command_id, str(row[2])) if settles
            else (outcome, (detail or "").strip() or None, moment, command_id, str(row[2])))
        try:
            moved = conn.execute(sql, values).rowcount
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.RaiseException as e:
            raise Conflict(str(e).strip().splitlines()[0]) from None
        if moved == 0:
            raise Conflict("this_command_was_settled_by_somebody_else")
        if outcome == "completed":
            _append(conn, tenant_id, "device.command.completed", "device_command",
                    command_id,
                    {"command_id": command_id, "device_id": str(row[0]),
                     "action": str(row[1]), "outcome": outcome},
                    actor_id=actor_id, correlation_id=correlation_id)
    return {"command_id": command_id, "device_id": str(row[0]), "state": outcome}


def expire_commands(
    pool: Pool, tenant_id: str, *, actor_id: str, correlation_id: str,
    at: datetime | None = None, limit: int = 500,
) -> dict[str, Any]:
    """Settle commands nothing collected in time.

    **The twelfth place in this build that wants the worker runtime**, and here the absence has
    a cost worth naming: an unlock nobody expires sits `issued` for ever, so a queue read
    shows a door waiting to open. The deadline is what actually protects the door --
    `deliver_command` refuses a stale command whether or not this ran -- so this is tidying
    rather than the control.
    """
    moment = at or _now()
    if not 1 <= limit <= 5000:
        raise InvalidRequest("a_sweep_takes_between_one_and_five_thousand")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "UPDATE plt01.dev_commands SET state = 'expired', settled_at = %s,"
            " settled_by = %s, settle_correlation_id = %s,"
            " outcome_detail = 'nothing collected it before its deadline'"
            " WHERE command_id IN ("
            "   SELECT command_id FROM plt01.dev_commands"
            "    WHERE state IN ('issued', 'delivered') AND expires_at <= %s"
            "    ORDER BY expires_at LIMIT %s)"
            " RETURNING command_id, device_id, action",
            (moment, actor_id, correlation_id, moment, limit)).fetchall()
    return {"expired": len(rows),
            "commands": [{"command_id": str(r[0]), "device_id": str(r[1]),
                          "action": str(r[2])} for r in rows]}


# ------------------------------------------------------------ health and fleet

def record_health(
    pool: Pool, tenant_id: str, device_id: str, *, latency_ms: int, error_count: int,
    storage_free_bytes: int, agent_version: str, peripherals: dict[str, Any] | None,
    actor_id: str, correlation_id: str, at: datetime | None = None,
) -> dict[str, Any]:
    """RecordDeviceHealth. Paragraph 3079's dashboard numbers, as an insert-only ledger.

    **`device.online` is published here, where the transition is observable.** A device that
    was offline and has just reported is the one event an operator wants; computing it in a
    *read* would mean a GET publishing an event, and computing it on a schedule would need the
    worker runtime this build lacks. The matching `device.offline` is `sweep_offline`'s,
    because silence has no moment of its own.

    **`last_seen_at` is the only derived thing written**, and reachability is not stored:
    `fleet.reachability` computes it, because a cached flag is a second authority that
    disagrees with the last report and sends somebody to a working device.
    """
    moment = at or _now()
    try:
        capabilities.check_small_object(peripherals or {}, "peripherals")
        fleet.check_health(fleet.Health(
            latency_ms=latency_ms, error_count=error_count,
            storage_free_bytes=storage_free_bytes, agent_version=agent_version))
    except ValueError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(pool, tenant_id) as conn:
        device = _device(conn, device_id, for_update=True)
        if device["state"] == "retired":
            raise Conflict("this_device_is_retired")
        was = fleet.reachability(device["last_seen_at"], at=moment)
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.dev_health_reports
                    (tenant_id, device_id, latency_ms, error_count, storage_free_bytes,
                     agent_version, peripherals, reported_at, reported_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING report_id
                """,
                (tenant_id, device_id, latency_ms, error_count, storage_free_bytes,
                 agent_version.strip(), json.dumps(peripherals or {}), moment, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        # **Never backwards.** A late report from a gateway whose clock is behind must not
        # make a device that has spoken since look silent.
        conn.execute(
            "UPDATE plt01.dev_devices SET last_seen_at = %s"
            " WHERE device_id = %s AND (last_seen_at IS NULL OR last_seen_at < %s)",
            (moment, device_id, moment))
        if was in ("offline", "never_seen"):
            _append(conn, tenant_id, "device.online", "device", device_id,
                    {"device_id": device_id, "was": was,
                     "agent_version": agent_version.strip()},
                    actor_id=actor_id, correlation_id=correlation_id)
    return {"report_id": str(row[0]), "device_id": device_id,
            "reachability": fleet.reachability(moment, at=moment),
            "was": was}


def sweep_offline(
    pool: Pool, tenant_id: str, *, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Publish `device.offline` for devices in service that have gone quiet.

    **Silence has no moment of its own**, which is why this is a sweep rather than a trigger:
    nothing happens when a gateway stops reporting, so somebody has to look. Paragraph 3087's
    outcome is that "fleet failures are detected before they block club operation", and
    `fleet.blocks_operation` is what decides which of them is worth an event -- a device
    deliberately in maintenance is quiet on purpose.

    **Idempotent by the last-seen window, not by a flag.** A device already reported offline
    is not reported again until it comes back and goes quiet once more, because the event is
    keyed on the silence that produced it.

    **And the already-reported ones are filtered out before the loop, not caught inside it.**
    `events.append_event` raises on a duplicate key, deliberately -- its own comment says "a
    command that means to be idempotent checks before it acts" -- and the first version did
    not check. So the second sweep of a device that was *still* offline raised out of
    `tenant_scope`, rolled the whole batch back and answered 409, which means every other
    device that had gone quiet behind it was never reported. That is MOD-010's "a failure
    path inside a batch loop must not raise", and the permanent case -- the dead unit you
    actually care about -- is the one that triggers it.
    """
    moment = at or _now()
    cutoff = moment - fleet.OFFLINE_AFTER
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT device_id, last_seen_at FROM plt01.dev_devices"
            " WHERE state = 'active' AND last_seen_at IS NOT NULL AND last_seen_at <= %s"
            " ORDER BY last_seen_at",
            (cutoff,)).fetchall()
        keys = {f"device.offline:{row[0]}:{row[1].isoformat()}": str(row[0])
                for row in rows}
        already = set()
        if keys:
            already = {r[0] for r in conn.execute(
                "SELECT idempotency_key FROM plt01.evt_outbox"
                " WHERE event_type = 'device.offline' AND idempotency_key = ANY(%s)",
                (list(keys),)).fetchall()}
        published = []
        for row in rows:
            device_id = str(row[0])
            seen = row[1]
            key = f"device.offline:{device_id}:{seen.isoformat()}"
            if key in already:
                continue
            events.append_event(
                conn, tenant_id, event_type="device.offline", aggregate_type="device",
                aggregate_id=device_id,
                payload={"device_id": device_id,
                         "last_seen_at": seen.isoformat(),
                         "silent_for_seconds": int((moment - seen).total_seconds())},
                actor_id=actor_id, correlation_id=correlation_id,
                idempotency_key=key)
            published.append(device_id)
    return {"offline": len(published), "devices": published,
            "already_reported": len(already),
            "detail": ("nothing drives this; a device nobody sweeps is one whose silence "
                       "reaches no dashboard")}


def record_sync_conflict(
    pool: Pool, tenant_id: str, device_id: str, *, detail: str, local_digest: str,
    remote_digest: str, actor_id: str, correlation_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """A gateway reporting that its local copy and the registry's disagree.

    Paragraph 3078's "conflict handling", and paragraph 3059's `edge.sync.conflict`. **The
    gateway is what notices**: it holds the SQLite WAL, so the conflict exists there and this
    build only ever hears about it. Recording it as a reported event rather than resolving it
    is the honest shape -- a resolution needs the two copies, and this side has one.

    **It is a row, because the first version demanded a `detail` and threw it away.** The
    route validated it, answered "recorded, not resolved" and wrote nothing but the two
    digests into the outbox -- leaving an operator two hex strings and no statement of what
    diverged, under a response saying it had been recorded. That is MOD-012's `release_run`
    shape. The prose stays in `dev_sync_conflicts`, where an erasure can at least see it
    declared; the event carries the conflict's id and the digests, because `evt_outbox` is
    the one store no erasure reaches.
    """
    moment = at or _now()
    if not detail.strip():
        raise InvalidRequest("a_sync_conflict_says_what_disagreed")
    local = local_digest.strip().lower()
    remote = remote_digest.strip().lower()
    with tenant_scope(pool, tenant_id) as conn:
        _device(conn, device_id)
        try:
            row = conn.execute(
                "INSERT INTO plt01.dev_sync_conflicts"
                " (tenant_id, device_id, detail, local_digest, remote_digest,"
                "  reported_at, reported_by, correlation_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING conflict_id",
                (tenant_id, device_id, detail.strip(), local, remote, moment, actor_id,
                 correlation_id)).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        conflict_id = str(row[0])
        _append(conn, tenant_id, "edge.sync.conflict", "device", device_id,
                {"device_id": device_id, "conflict_id": conflict_id,
                 "local_digest": local, "remote_digest": remote},
                actor_id=actor_id, correlation_id=correlation_id)
    return {"device_id": device_id, "conflict_id": conflict_id,
            "reported_at": moment.isoformat(),
            "detail": ("recorded, not resolved: the two copies are the gateway's and the "
                       "registry's, and only one of them is here")}


# ----------------------------------------------------------------------- reads

def device_detail(
    pool: Pool, tenant_id: str, device_id: str, *, at: datetime | None = None,
) -> dict[str, Any]:
    """One device with everything an operator deciding whether to drive to a club needs."""
    moment = at or _now()
    with tenant_scope(pool, tenant_id) as conn:
        device = _device(conn, device_id)
        declared = _device_capabilities(conn, device_id)
        profile = _live_profile(conn, device_id)
        passing = _passing_tests(conn, device_id)
        certs = _certificates(conn, device_id)
        latest = conn.execute(
            "SELECT latency_ms, error_count, storage_free_bytes, agent_version,"
            " reported_at FROM plt01.dev_health_reports"
            " WHERE device_id = %s ORDER BY reported_at DESC LIMIT 1",
            (device_id,)).fetchone()
        snapshot = conn.execute(
            "SELECT snapshot_id, revocation_epoch, issued_at, expires_at"
            " FROM plt01.dev_policy_snapshots WHERE device_id = %s"
            " ORDER BY issued_at DESC LIMIT 1",
            (device_id,)).fetchone()
    actuates = capabilities.ACTUATING in declared
    reach = fleet.reachability(device["last_seen_at"], at=moment)
    return {
        "device_id": device_id, "serial_number": device["serial_number"],
        "display_name": device["display_name"], "state": device["state"],
        "kind": device["kind"], "location_id": device["location_id"],
        "type_id": device["type_id"], "version": device["version"],
        "capabilities": sorted(declared),
        "reachability": reach,
        "blocks_operation": fleet.blocks_operation(device["state"], reach),
        "last_seen_at": (device["last_seen_at"].isoformat()
                         if device["last_seen_at"] else None),
        "revocation_epoch": device["revocation_epoch"],
        "is_access_point": actuates,
        "safety": None if profile is None else {
            "profile": profile.profile, "on_egress_path": profile.on_egress_path,
            "fire_release_is_independent": profile.fire_release_is_independent,
            "local_emergency_input": profile.local_emergency_input},
        "outstanding_tests": list(safety.missing_tests(passing)) if actuates else [],
        "certificates": [
            {"fingerprint": c.fingerprint, "state": c.state,
             "usable": certificates.is_usable(c, at=moment),
             "due_for_rotation": certificates.due_for_rotation(c, at=moment),
             "not_after": c.not_after.isoformat()} for c in certs],
        "health": None if latest is None else {
            "latency_ms": int(latest[0]), "error_count": int(latest[1]),
            "storage_free_bytes": int(latest[2]), "agent_version": str(latest[3]),
            "reported_at": latest[4].isoformat()},
        "snapshot": None if snapshot is None else {
            "snapshot_id": str(snapshot[0]), "revocation_epoch": int(snapshot[1]),
            "issued_at": snapshot[2].isoformat(),
            "expires_at": snapshot[3].isoformat(),
            "stale": snapshot[3] <= moment,
            "behind_revocation": int(snapshot[1]) < device["revocation_epoch"]},
    }


def fleet_view(
    pool: Pool, tenant_id: str, *, location_id: str | None = None,
    at: datetime | None = None, limit: int = 200,
) -> dict[str, Any]:
    """Paragraph 3079's fleet dashboard: who is online, who is late, who needs somebody.

    **Reachability is derived per row from the last report**, not read from a column, which is
    the whole of why there is no `online` flag in the schema.
    """
    moment = at or _now()
    if not 1 <= limit <= 1000:
        raise InvalidRequest("a_fleet_view_takes_between_one_and_a_thousand")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT d.device_id, d.serial_number, d.display_name, d.state,"
            " d.last_seen_at, d.location_id, t.kind"
            " FROM plt01.dev_devices d"
            " JOIN plt01.dev_device_types t ON t.type_id = d.type_id"
            " WHERE (%s::uuid IS NULL OR d.location_id = %s::uuid)"
            " ORDER BY d.last_seen_at NULLS FIRST, d.serial_number"
            " LIMIT %s",
            (location_id, location_id, limit)).fetchall()
    devices = []
    for row in rows:
        reach = fleet.reachability(row[4], at=moment)
        devices.append({
            "device_id": str(row[0]), "serial_number": str(row[1]),
            "display_name": str(row[2]), "state": str(row[3]), "kind": str(row[6]),
            "location_id": str(row[5]), "reachability": reach,
            "blocks_operation": fleet.blocks_operation(str(row[3]), reach),
            "last_seen_at": row[4].isoformat() if row[4] else None})
    return {"devices": devices, "count": len(devices),
            "needs_attention": [d["device_id"] for d in devices
                                if d["blocks_operation"]],
            "as_of": moment.isoformat()}


def command_queue(
    pool: Pool, tenant_id: str, device_id: str, *, at: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """What is waiting for this device, with whether each is still deliverable."""
    moment = at or _now()
    if not 1 <= limit <= 500:
        raise InvalidRequest("a_command_queue_takes_between_one_and_five_hundred")
    with tenant_scope(pool, tenant_id) as conn:
        _device(conn, device_id)
        rows = conn.execute(
            "SELECT command_id, action, state, issued_at, expires_at, payload_digest"
            " FROM plt01.dev_commands WHERE device_id = %s"
            " ORDER BY issued_at DESC LIMIT %s",
            (device_id, limit)).fetchall()
    out = []
    for row in rows:
        live = commands.Command(
            action=str(row[1]), state=str(row[2]), issued_at=row[3], expires_at=row[4])
        out.append({
            "command_id": str(row[0]), "action": str(row[1]), "state": str(row[2]),
            "issued_at": row[3].isoformat(), "expires_at": row[4].isoformat(),
            "payload_digest": str(row[5]),
            "expired": commands.has_expired(live, at=moment)})
    return {"device_id": device_id, "commands": out, "count": len(out)}

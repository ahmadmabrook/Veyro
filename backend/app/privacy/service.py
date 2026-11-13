"""MOD-009 SEC-01 service: processing purposes, consent, retention, legal holds, DSARs.

The decisions live in `app.privacy.classification`, `consent`, `retention` and `dsar`. This
module reads rows, calls those, and writes what they return. No consent state, no retention
verdict and no workflow transition is decided here.

**A deletion crosses both planes and is not atomic across them.** The subject's identity rows
live in `iam` under `veyro_iam_app`; the tenant-plane rows live in `plt01` under `veyro_cp_app`;
neither role can reach the other's schema and neither is a member of the other. A single
transaction spanning both is therefore impossible by construction, and that is the design working
rather than failing. What makes a partial run survivable is `sec_dsar_actions`: one insert-only
row per target actually touched, written as each target completes, so an interrupted deletion
leaves a record of exactly how far it got and can be resumed without redoing what is done.

**What this module cannot do, stated here rather than discovered later:**

* **It cannot fully erase a subject.** `classification.SUBJECT_COLUMNS` names every column in
  either plane holding a person's identifier, and the ones marked `unreachable` carry no UPDATE
  and no DELETE for any runtime role -- the financial ledger, the audit chain, the authentication
  log and this module's own consent evidence. That is deliberate in each case and the reasons are
  on the registry entries. The consequence is that a deletion completes *with residue*, the
  residue is named in the response, and `backend/tests/test_privacy_reachability.py` fails if
  anybody quietly changes either side of that.
* **No key management.** SEC-01-R02 wants envelope encryption, rotation and a secret vault, and
  `RotateKey` is in the TSD's command inventory. There is no vault in this repository and no KMS,
  and a key registry holding no keys would be a table that reads as a control. Crypto-shred, the
  mechanism paragraph 4397 gives for making insert-only rows unreachable, needs exactly that
  missing piece.
* **No subprocessor propagation.** Paragraph 4384 requires a DSAR to reach subprocessors. There
  are none configured, so there is nothing to propagate to; the actions trail has room for it.
* **No outbox.** `consent.granted`, `consent.withdrawn`, `security.alert.detected`,
  `vulnerability.opened`, `data_subject_request.created` and `data_subject_request.completed` are
  named in the TSD and nothing publishes them, as in MOD-005 and MOD-015.
* **No DPIA record and no vulnerability register.** `RunDPIA` and the Vulnerability entity are
  process artefacts whose content is owner policy; a table for them with nothing in it would
  claim a control nobody operates.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events
from app.privacy import classification, consent, dsar, retention


def _now() -> datetime:
    return datetime.now(UTC)


def evidence_hash(payload: dict[str, Any]) -> str:
    """A stable digest of what an action did, for the evidence column.

    Sorted keys and a separator-tight encoding so that the same action produces the same digest
    on a different machine and a different Python version. This is a receipt, not a secret: it
    lets two copies of a deletion report be compared without comparing their prose.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------- processing purposes

def register_purpose(
    pool: Pool, tenant_id: str, *, purpose_code: str, description: str, lawful_basis: str,
    controller_role: str, data_classes: list[str], actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """RegisterProcessingPurpose. The lawful basis and the controller role are both required.

    Neither has a default. A purpose with no stated basis is processing nobody has justified, and
    a purpose with no stated role leaves it unclear who answers to the regulator -- TSD paragraph
    4389 puts Veyro on both sides depending on the purpose, so it cannot be inferred per tenant.
    """
    for value in data_classes:
        if value not in classification.CLASSES:
            raise InvalidRequest("unknown_data_class")
    if not data_classes:
        raise InvalidRequest("data_classes_required")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.sec_processing_purposes
                    (tenant_id, purpose_code, description, lawful_basis, controller_role,
                     data_classes, registered_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING purpose_id, registered_at
                """,
                (tenant_id, purpose_code, description, lawful_basis, controller_role,
                 data_classes, actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("purpose_code_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"purpose_id": str(row[0]), "purpose_code": purpose_code,
            "lawful_basis": lawful_basis, "controller_role": controller_role,
            "registered_at": row[1].isoformat()}


def retire_purpose(
    pool: Pool, tenant_id: str, *, purpose_id: str, actor_id: str, correlation_id: str
) -> dict[str, Any]:
    """Retire a purpose. The row stays so the consent that cited it still resolves.

    Attributed, because retiring a purpose withdraws the stated justification for processing and
    the question asked afterwards is who did it. Registering one has always recorded an actor;
    this did not, which an independent review found.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "UPDATE plt01.sec_processing_purposes"
            " SET retired_at = now(), retired_by = %s, retire_correlation_id = %s"
            " WHERE purpose_id = %s AND retired_at IS NULL RETURNING purpose_id, retired_at",
            (actor_id, correlation_id, purpose_id),
        ).fetchone()
    if row is None:
        raise NotFound("purpose_not_found_or_already_retired")
    return {"purpose_id": str(row[0]), "retired_at": row[1].isoformat(),
            "retired_by": actor_id}


def list_purposes(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT purpose_id, purpose_code, description, lawful_basis, controller_role,"
            " data_classes, registered_at, retired_at FROM plt01.sec_processing_purposes"
            " ORDER BY purpose_code",
        ).fetchall()
    return [{"purpose_id": str(r[0]), "purpose_code": r[1], "description": r[2],
             "lawful_basis": r[3], "controller_role": r[4], "data_classes": list(r[5]),
             "registered_at": r[6].isoformat(),
             "retired_at": r[7].isoformat() if r[7] else None} for r in rows]


# --------------------------------------------------------------------------------- consent

def define_consent(
    pool: Pool, tenant_id: str, *, consent_type: str, purpose_id: str, actor_id: str,
    correlation_id: str, requires_guardian: bool = False, withdrawable: bool = True,
) -> dict[str, Any]:
    """Define a consent kind. `requires_guardian` is the control that makes a minor's consent
    valid, so who set it and under which change is recorded like everything else here."""
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.sec_consent_definitions
                    (tenant_id, consent_type, purpose_id, requires_guardian, withdrawable,
                     defined_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING definition_id, registered_at
                """,
                (tenant_id, consent_type, purpose_id, requires_guardian, withdrawable,
                 actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("consent_type_already_defined") from None
        except errors.ForeignKeyViolation:
            raise NotFound("purpose_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"definition_id": str(row[0]), "consent_type": consent_type,
            "requires_guardian": requires_guardian, "withdrawable": withdrawable,
            "registered_at": row[1].isoformat()}


def publish_consent_version(
    pool: Pool, tenant_id: str, *, consent_type: str, language: str, document_ref: str,
    document_hash: str, effective_from: datetime, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Publish a new version of a consent document.

    The version number is assigned here rather than supplied: a caller that picks its own would
    eventually pick one that already exists, and the unique index would turn a race between two
    publishers into an error for whichever lost rather than the next number.
    """
    with tenant_scope(pool, tenant_id) as conn:
        definition = _definition_by_type(conn, consent_type)
        # Two publishers of the same consent type must serialise, or both read the same max and
        # both insert version n+1. A row lock is not available: `sec_consent_definitions` carries
        # SELECT and INSERT only, and `SELECT ... FOR UPDATE` requires the UPDATE privilege the
        # table deliberately withholds. An advisory lock needs no table privilege and is scoped
        # to the transaction, so it releases on commit or rollback either way.
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"consent_version:{tenant_id}:{definition['definition_id']}:{language}",),
        ).fetchone()
        current = conn.execute(
            "SELECT coalesce(max(version), 0) FROM plt01.sec_consent_versions"
            " WHERE definition_id = %s AND language = %s",
            (definition["definition_id"], language),
        ).fetchone()
        assert current is not None
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.sec_consent_versions
                    (tenant_id, definition_id, version, language, document_ref, document_hash,
                     effective_from, published_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING consent_version_id, version, published_at
                """,
                (tenant_id, definition["definition_id"], int(current[0]) + 1, language,
                 document_ref, document_hash, effective_from, actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"consent_version_id": str(row[0]), "consent_type": consent_type,
            "version": int(row[1]), "language": language,
            "published_at": row[2].isoformat()}


def register_consent(
    pool: Pool, tenant_id: str, *, subject_id: str, consent_type: str, language: str,
    signed_at: datetime, source: str, correlation_id: str,
    guardian_subject_id: str | None = None, evidence_hash_value: str | None = None,
    evidence_ref: str | None = None, consent_version_id: str | None = None,
) -> dict[str, Any]:
    """RegisterConsent. Binds to the version in force unless the caller names one.

    A caller may name an older version when importing a paper record signed before the current
    document was published -- that is the one legitimate case, and `consent.check_grant` still
    refuses a signature dated before the version it claims.
    """
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        definition = _definition_by_type(conn, consent_type)
        versions = _versions(conn, definition["definition_id"])
        if consent_version_id is None:
            in_force = consent.current_version(versions, definition["definition_id"], language,
                                               now)
            if in_force is None:
                raise NotFound("no_consent_version_in_force_for_this_language")
            chosen = in_force
        else:
            matching = [v for v in versions if v.consent_version_id == consent_version_id]
            if not matching:
                raise NotFound("consent_version_not_found")
            chosen = matching[0]

        try:
            consent.check_grant(
                _definition_of(definition), chosen, guardian_subject_id=guardian_subject_id,
                subject_id=subject_id, signed_at=signed_at, now=now,
            )
        except consent.ConsentError as e:
            raise InvalidRequest(str(e)) from None

        row = _append_consent(
            conn, tenant_id, subject_id=subject_id, definition_id=definition["definition_id"],
            consent_version_id=chosen.consent_version_id, action="granted", signed_at=signed_at,
            source=source, correlation_id=correlation_id, guardian=guardian_subject_id,
            evidence_hash_value=evidence_hash_value, evidence_ref=evidence_ref,
            locale=language, consent_type=consent_type,
        )
    return {"record_id": row, "subject_id": subject_id, "consent_type": consent_type,
            "consent_version_id": chosen.consent_version_id, "action": "granted",
            "signed_at": signed_at.isoformat()}


def withdraw_consent(
    pool: Pool, tenant_id: str, *, subject_id: str, consent_type: str, signed_at: datetime,
    source: str, correlation_id: str, evidence_ref: str | None = None,
) -> dict[str, Any]:
    """WithdrawConsent. A new row, never an edit of the grant it withdraws."""
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        definition = _definition_by_type(conn, consent_type)
        versions = _versions(conn, definition["definition_id"])
        records = _records(conn, subject_id, definition["definition_id"])
        in_force = consent.current_version(versions, definition["definition_id"],
                                           _DEFAULT_LANGUAGE, now)
        state = consent.state_of(records, definition["definition_id"],
                                 in_force.consent_version_id if in_force else None)
        try:
            consent.check_withdrawal(_definition_of(definition), state)
        except consent.ConsentError as e:
            raise Conflict(str(e)) from None
        if signed_at > now:
            raise InvalidRequest("signed_in_the_future")

        assert state.consent_version_id is not None
        row = _append_consent(
            conn, tenant_id, subject_id=subject_id, definition_id=definition["definition_id"],
            # The withdrawal names the version it withdraws, so the pair reads as one story.
            consent_version_id=state.consent_version_id, action="withdrawn",
            signed_at=signed_at, source=source, correlation_id=correlation_id, guardian=None,
            evidence_hash_value=None, evidence_ref=evidence_ref,
            locale=_DEFAULT_LANGUAGE, consent_type=consent_type,
        )
    return {"record_id": row, "subject_id": subject_id, "consent_type": consent_type,
            "action": "withdrawn", "signed_at": signed_at.isoformat()}


def consent_state(
    pool: Pool, tenant_id: str, *, subject_id: str, language: str = "en"
) -> dict[str, Any]:
    """Every consent kind for one subject, derived from the log rather than from a stored flag."""
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        definitions = _definitions(conn)
        versions = _all_versions(conn)
        records = _all_records(conn, subject_id)
    rows = []
    for definition in definitions:
        in_force = consent.current_version(versions, definition.definition_id, language, now)
        state = consent.state_of(records, definition.definition_id,
                                 in_force.consent_version_id if in_force else None)
        rows.append({
            "consent_type": definition.consent_type,
            "definition_id": definition.definition_id,
            "granted": state.granted,
            "stale": state.stale,
            "consent_version_id": state.consent_version_id,
            "signed_at": state.signed_at.isoformat() if state.signed_at else None,
            "current_version_id": in_force.consent_version_id if in_force else None,
        })
    return {
        "subject_id": subject_id,
        "language": language,
        "consents": rows,
        "outstanding": consent.outstanding(definitions, versions, records, language=language,
                                           now=now),
    }


def consent_history(pool: Pool, tenant_id: str, *, subject_id: str) -> list[dict[str, Any]]:
    """The whole log for one subject. This is what a regulator asks to see."""
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT r.record_id, d.consent_type, r.consent_version_id, r.action, r.signed_at,"
            " r.source, r.guardian_subject_id, r.evidence_hash, r.evidence_ref, r.locale,"
            " r.recorded_at"
            " FROM plt01.sec_consent_records r"
            " JOIN plt01.sec_consent_definitions d ON d.definition_id = r.definition_id"
            " WHERE r.subject_id = %s ORDER BY r.signed_at, r.recorded_at",
            (subject_id,),
        ).fetchall()
    return [{"record_id": str(r[0]), "consent_type": r[1], "consent_version_id": str(r[2]),
             "action": r[3], "signed_at": r[4].isoformat(), "source": r[5],
             "guardian_subject_id": str(r[6]) if r[6] else None, "evidence_hash": r[7],
             "evidence_ref": r[8], "locale": r[9], "recorded_at": r[10].isoformat()}
            for r in rows]


# ----------------------------------------------------------------- retention and legal hold

def set_retention_policy(
    pool: Pool, tenant_id: str, *, resource_type: str, data_class: str, retention_days: int,
    legal_basis: str, region: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """ApplyRetentionPolicy. Retires the live policy for this resource and region, then inserts.

    Both in one transaction, because a moment with no policy is a moment when `may_delete`
    answers `no_retention_policy` and a sweep running concurrently would skip every record.
    """
    with tenant_scope(pool, tenant_id) as conn:
        conn.execute(
            "UPDATE plt01.sec_retention_policies SET retired_at = now(), retired_by = %s,"
            " retire_correlation_id = %s"
            " WHERE resource_type = %s AND region = %s AND retired_at IS NULL",
            (actor_id, correlation_id, resource_type, region),
        )
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.sec_retention_policies
                    (tenant_id, resource_type, data_class, retention_days, legal_basis, region,
                     set_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING policy_id, set_at
                """,
                (tenant_id, resource_type, data_class, retention_days, legal_basis, region,
                 actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            # Two first-writes for the same (resource_type, region) race: the partial unique
            # index refuses the loser. `register_purpose` already maps this; this one leaked the
            # raw psycopg error out of the service layer.
            raise Conflict("retention_policy_already_set_for_this_resource") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"policy_id": str(row[0]), "resource_type": resource_type, "data_class": data_class,
            "retention_days": retention_days, "region": region, "set_at": row[1].isoformat()}


def list_retention_policies(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT policy_id, resource_type, data_class, retention_days, legal_basis, region,"
            " set_at, retired_at FROM plt01.sec_retention_policies"
            " WHERE retired_at IS NULL ORDER BY resource_type, region",
        ).fetchall()
    return [{"policy_id": str(r[0]), "resource_type": r[1], "data_class": r[2],
             "retention_days": int(r[3]), "legal_basis": r[4], "region": r[5],
             "set_at": r[6].isoformat()} for r in rows]


def place_legal_hold(
    pool: Pool, tenant_id: str, *, reason: str, reference: str, actor_id: str,
    correlation_id: str, subject_id: str | None = None, resource_type: str | None = None,
) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.sec_legal_holds
                    (tenant_id, subject_id, resource_type, reason, reference, placed_by,
                     correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING hold_id, placed_at
                """,
                (tenant_id, subject_id, resource_type, reason, reference, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    return {"hold_id": str(row[0]), "subject_id": subject_id, "resource_type": resource_type,
            "reason": reason, "reference": reference, "placed_at": row[1].isoformat()}


def release_legal_hold(
    pool: Pool, tenant_id: str, *, hold_id: str, release_reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Release a hold. Never deletes it: the evidence that deletion was suspended is the point.

    Attributed, and attributed in the row rather than only in an audit log this plane cannot
    reach: `veyro_cp_app` holds nothing in `iam`, so MOD-008's audit chain is not available here
    and a release recorded nowhere else would have no actor anywhere in the system. This is the
    single act that un-blocks destruction of preserved evidence.

    The `released_at IS NULL` predicate and the table's trigger say the same thing from two
    sides: this returns `hold_not_found_or_already_released` for a second attempt, and the
    trigger refuses any later change to a released row whatever path reaches it.
    """
    if not release_reason.strip():
        raise InvalidRequest("release_reason_required")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "UPDATE plt01.sec_legal_holds SET released_at = now(), release_reason = %s,"
            " released_by = %s, release_correlation_id = %s"
            " WHERE hold_id = %s AND released_at IS NULL RETURNING hold_id, released_at",
            (release_reason, actor_id, correlation_id, hold_id),
        ).fetchone()
    if row is None:
        raise NotFound("hold_not_found_or_already_released")
    return {"hold_id": str(row[0]), "released_at": row[1].isoformat(),
            "release_reason": release_reason, "released_by": actor_id}


def list_legal_holds(pool: Pool, tenant_id: str, *, include_released: bool = False
                     ) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT hold_id, subject_id, resource_type, reason, reference, placed_at,"
            " released_at, release_reason, placed_by, released_by"
            " FROM plt01.sec_legal_holds"
            " WHERE (%s OR released_at IS NULL) ORDER BY placed_at DESC",
            (include_released,),
        ).fetchall()
    # `placed_by` and `released_by` are in the projection because a hold with no actor on it is
    # a hold nobody can be asked about, and this plane cannot reach MOD-008's audit chain.
    return [{"hold_id": str(r[0]), "subject_id": str(r[1]) if r[1] else None,
             "resource_type": r[2], "reason": r[3], "reference": r[4],
             "placed_at": r[5].isoformat(),
             "released_at": r[6].isoformat() if r[6] else None,
             "release_reason": r[7], "placed_by": str(r[8]),
             "released_by": str(r[9]) if r[9] else None} for r in rows]


# ------------------------------------------------------------------ data subject requests

def open_dsar(
    pool: Pool, tenant_id: str, *, subject_id: str, request_type: str, response_days: int,
    actor_id: str, correlation_id: str, received_at: datetime | None = None,
) -> dict[str, Any]:
    """OpenDSAR. `response_days` is required; see the note in `app.privacy.dsar`."""
    arrived = received_at or _now()
    try:
        opened = dsar.open_request(request_type=request_type, received_at=arrived,
                                   response_days=response_days, now=_now())
    except dsar.DsarError as e:
        raise InvalidRequest(str(e)) from None
    due_at = opened["due_at"]
    assert isinstance(due_at, datetime)
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            """
            INSERT INTO plt01.sec_dsar_requests
                (tenant_id, subject_id, request_type, status, received_at, due_at, opened_by,
                 correlation_id)
            VALUES (%s, %s, %s, 'received', %s, %s, %s, %s)
            RETURNING request_id
            """,
            (tenant_id, subject_id, request_type, opened["received_at"], due_at,
             actor_id, correlation_id),
        ).fetchone()
        assert row is not None
        events.append_event(
            conn, tenant_id, event_type="data_subject_request.created",
            aggregate_type="dsar", aggregate_id=str(row[0]),
            payload={"request_id": str(row[0]), "subject_id": subject_id,
                     "request_type": request_type, "due_at": due_at.isoformat()},
            correlation_id=correlation_id, actor_id=actor_id,
        )
    assert row is not None
    return {"request_id": str(row[0]), "subject_id": subject_id, "request_type": request_type,
            "status": "received", "received_at": arrived.isoformat(),
            "due_at": due_at.isoformat()}


def verify_dsar_identity(
    pool: Pool, tenant_id: str, *, request_id: str, actor_id: str
) -> dict[str, Any]:
    """The first of the two gates. Records who verified, not only that somebody did."""
    return _advance(pool, tenant_id, request_id=request_id, target="legal_pending",
                    from_status="identity_pending",
                    sets={"identity_verified_at": _now(), "identity_verified_by": actor_id})


def check_dsar_legal(
    pool: Pool, tenant_id: str, *, request_id: str, actor_id: str
) -> dict[str, Any]:
    """The second gate: legal holds, checked against the subject the request names.

    A hold refuses the request here rather than at fulfilment, so a held subject gets a decision
    with the hold's reference in it instead of a half-finished erasure.
    """
    with tenant_scope(pool, tenant_id) as conn:
        request = _request(conn, request_id)
        if request["status"] != "legal_pending":
            raise Conflict("request_is_not_awaiting_the_legal_check")
        holds = _holds(conn)
        verdict = retention.may_delete_subject(holds, subject_id=request["subject_id"])
        blocking = list(verdict.blocking_hold_ids)
        if request["request_type"] == "deletion" and not verdict.deletable:
            conn.execute(
                "UPDATE plt01.sec_dsar_requests SET status = 'refused', refused_reason = %s,"
                " legal_checked_at = now(), legal_checked_by = %s WHERE request_id = %s",
                (f"legal_hold:{','.join(blocking)}", actor_id, request_id),
            )
            return {"request_id": request_id, "status": "refused", "reason": "legal_hold",
                    "blocking_hold_ids": blocking}
        conn.execute(
            "UPDATE plt01.sec_dsar_requests SET status = 'ready', legal_checked_at = now(),"
            " legal_checked_by = %s WHERE request_id = %s",
            (actor_id, request_id),
        )
    return {"request_id": request_id, "status": "ready", "blocking_hold_ids": blocking}


def start_dsar_identity_check(pool: Pool, tenant_id: str, *, request_id: str) -> dict[str, Any]:
    """Move a received request into identity verification."""
    return _advance(pool, tenant_id, request_id=request_id, target="identity_pending",
                    from_status="received", sets={})


def refuse_dsar(
    pool: Pool, tenant_id: str, *, request_id: str, reason: str
) -> dict[str, Any]:
    if not reason.strip():
        raise InvalidRequest("refusal_reason_required")
    with tenant_scope(pool, tenant_id) as conn:
        request = _request(conn, request_id)
        try:
            dsar.check_transition(request["status"], "refused")
        except dsar.DsarError as e:
            raise Conflict(str(e)) from None
        conn.execute(
            "UPDATE plt01.sec_dsar_requests SET status = 'refused', refused_reason = %s"
            " WHERE request_id = %s",
            (reason, request_id),
        )
    return {"request_id": request_id, "status": "refused", "reason": reason}


def plan_dsar(pool: Pool, tenant_id: str, *, request_id: str) -> dict[str, Any]:
    """What fulfilling this request would do, and what it could not do, before it runs."""
    with tenant_scope(pool, tenant_id) as conn:
        request = _request(conn, request_id)
    reachable = list(classification.reachable_columns())
    unreachable = list(classification.unreachable_columns())
    if request["request_type"] != "deletion":
        # Only a deletion is bounded by what the database will let go of; a read reaches
        # everything, because reading an insert-only row is exactly what it is for.
        reachable += unreachable
        unreachable = []
    return {
        "request_id": request_id,
        "request_type": request["request_type"],
        "steps": dsar.plan(request["request_type"], reachable, unreachable),
        "erasure_is_complete": classification.deletion_is_complete(),
    }


def fulfil_dsar(
    pool: Pool, tenant_id: str, *, request_id: str, identity_pool: Pool | None = None,
    actor_id: str | None = None, correlation_id: str | None = None,
) -> dict[str, Any]:
    """FulfillDSAR. Checks, acts, records one evidence row per target, then settles.

    **Four things are checked here and none of them is the status column.** The status is one
    column that one UPDATE moves; these are the facts it is supposed to stand for, and each was
    a defect before it was a check:

    1. Identity verified and the legal check done, re-read from the row (`check_ready_to_fulfil`).
    2. **No live legal hold**, re-read now rather than trusted from the legal check. `ready` is a
       durable state with no expiry, so the gap between the legal check and this call is however
       long an operator waits -- and litigation ordinarily starts *after* a request is queued. A
       hold placed in that window used to be ignored, and the erasure ran under a live
       preservation order and reported `completed`. Found by independent review, twice.
    3. **The subject resolves to somebody.** Nothing in the database checks that `subject_id`
       names a real identity -- it cannot, the planes are separate -- so an erasure against an
       unresolvable id updated zero rows, recorded `done`, and completed. The caller supplying a
       `person_id` where an `identity_id` was meant is the realistic case, and it told a live
       member their data was erased while every row stood. This is the `locate_by` defect one
       layer up: a locator that exists is not a locator that matched.
    4. **The request type is one this build executes.** Only a deletion is. That refusal used to
       happen *after* the status had been committed to `fulfilling`, from which the only exit is
       `refused` -- so attempting to answer an access request made it permanently unanswerable.
       A control that commits anything before it refuses is not a control.

    Nothing is written until all four pass, so a refusal leaves the request exactly where it was
    and the caller can act on the reason and try again.
    """
    with tenant_scope(pool, tenant_id) as conn:
        request = _request(conn, request_id)
        try:
            dsar.check_ready_to_fulfil(dsar.Request(
                request_id=request_id, subject_id=request["subject_id"],
                request_type=request["request_type"], status=request["status"],
                received_at=request["received_at"], due_at=request["due_at"],
                identity_verified_at=request["identity_verified_at"],
                legal_checked_at=request["legal_checked_at"],
            ))
        except dsar.DsarError as e:
            raise Conflict(str(e)) from None
        if request["request_type"] not in dsar.EXECUTABLE_REQUEST_TYPES:
            raise InvalidRequest("only_a_deletion_request_is_executed_in_this_build")
        verdict = retention.may_delete_subject(_holds(conn), subject_id=request["subject_id"])
        if not verdict.deletable:
            raise Conflict(
                "legal_hold:" + ",".join(verdict.blocking_hold_ids)
            )

    if identity_pool is None:
        raise InvalidRequest("identity_plane_not_available")
    if not _subject_exists(identity_pool, tenant_id, subject_id=request["subject_id"]):
        raise NotFound("subject_not_found_in_the_identity_plane")

    with tenant_scope(pool, tenant_id) as conn:
        conn.execute(
            "UPDATE plt01.sec_dsar_requests SET status = 'fulfilling' WHERE request_id = %s",
            (request_id,),
        )

    actions = _perform(pool, tenant_id, request_id=request_id,
                       subject_id=request["subject_id"],
                       request_type=request["request_type"], identity_pool=identity_pool,
                       actor_id=actor_id, correlation_id=correlation_id)
    settled = dsar.settle(request["request_type"], actions)

    with tenant_scope(pool, tenant_id) as conn:
        if settled["complete"]:
            conn.execute(
                "UPDATE plt01.sec_dsar_requests SET status = 'completed', completed_at = now()"
                " WHERE request_id = %s",
                (request_id,),
            )
            events.append_event(
                conn, tenant_id, event_type="data_subject_request.completed",
                aggregate_type="dsar", aggregate_id=request_id,
                payload={"request_id": request_id, "subject_id": request["subject_id"],
                         "request_type": request["request_type"],
                         "has_residue": bool(settled["has_residue"])},
                # The caller's correlation id when it sent one. A fulfilment reached through
                # a worker rather than a request has none, and minting one is better than
                # reaching for a column `_request` does not project.
                correlation_id=correlation_id or str(uuid4()),
                actor_id=actor_id,
            )
    return {"request_id": request_id, **settled}


def get_dsar(pool: Pool, tenant_id: str, *, request_id: str) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        request = _request(conn, request_id)
        actions = conn.execute(
            "SELECT store, target, mechanism, outcome, rows_affected, evidence_hash,"
            " performed_at FROM plt01.sec_dsar_actions WHERE request_id = %s"
            " ORDER BY performed_at, action_id",
            (request_id,),
        ).fetchall()
    return {
        **{key: (value.isoformat() if isinstance(value, datetime) else value)
           for key, value in request.items()},
        "actions": [{"store": a[0], "target": a[1], "mechanism": a[2], "outcome": a[3],
                     "rows_affected": int(a[4]), "evidence_hash": a[5],
                     "performed_at": a[6].isoformat()} for a in actions],
        "overdue": dsar.overdue(dsar.Request(
            request_id=request_id, subject_id=request["subject_id"],
            request_type=request["request_type"], status=request["status"],
            received_at=request["received_at"], due_at=request["due_at"]), _now()),
    }


def list_dsars(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT request_id, subject_id, request_type, status, received_at, due_at,"
            " completed_at FROM plt01.sec_dsar_requests ORDER BY received_at DESC",
        ).fetchall()
    return [{"request_id": str(r[0]), "subject_id": str(r[1]), "request_type": r[2],
             "status": r[3], "received_at": r[4].isoformat(), "due_at": r[5].isoformat(),
             "completed_at": r[6].isoformat() if r[6] else None,
             "overdue": r[3] not in ("completed", "refused") and now > r[5]} for r in rows]


# ------------------------------------------------------------------------ security incidents

def record_incident(
    pool: Pool, tenant_id: str, *, severity: str, category: str, summary: str,
    detected_at: datetime, personal_data_involved: str, actor_id: str, correlation_id: str,
    notification_assessment: str | None = None, detail: dict[str, Any] | None = None,
    supersedes_incident_id: str | None = None,
) -> dict[str, Any]:
    """RecordSecurityIncident. Insert-only: a correction is a later row naming the earlier one."""
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.sec_incidents
                    (tenant_id, supersedes_incident_id, severity, category, summary,
                     detected_at, personal_data_involved, notification_assessment, detail,
                     recorded_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING incident_id, recorded_at
                """,
                (tenant_id, supersedes_incident_id, severity, category, summary, detected_at,
                 personal_data_involved, notification_assessment, Jsonb(detail or {}), actor_id,
                 correlation_id),
            ).fetchone()
        except errors.ForeignKeyViolation:
            raise NotFound("superseded_incident_not_found") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        events.append_event(
            conn, tenant_id, event_type="security.alert.detected",
            aggregate_type="incident", aggregate_id=str(row[0]),
            payload={"incident_id": str(row[0]), "severity": severity, "category": category,
                     "personal_data_involved": personal_data_involved},
            correlation_id=correlation_id, actor_id=actor_id,
        )
    assert row is not None
    return {"incident_id": str(row[0]), "severity": severity, "category": category,
            "personal_data_involved": personal_data_involved,
            "recorded_at": row[1].isoformat()}


def list_incidents(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT incident_id, supersedes_incident_id, severity, category, summary,"
            " detected_at, personal_data_involved, notification_assessment, recorded_at"
            " FROM plt01.sec_incidents ORDER BY detected_at DESC",
        ).fetchall()
    return [{"incident_id": str(r[0]),
             "supersedes_incident_id": str(r[1]) if r[1] else None, "severity": r[2],
             "category": r[3], "summary": r[4], "detected_at": r[5].isoformat(),
             "personal_data_involved": r[6], "notification_assessment": r[7],
             "recorded_at": r[8].isoformat()} for r in rows]


# ------------------------------------------------------------------------------- internals

#: `sec_consent_definitions` carries no per-definition language, so a withdrawal resolves the
#: version in force in this one. It read as `definition.get("default_language", "en")`, a key
#: nothing ever set -- multilingual support that was not there. Named here so the limitation is
#: visible rather than disguised as a lookup.
_DEFAULT_LANGUAGE = "en"


def _check_name(error: errors.CheckViolation) -> str:
    """The constraint name a CHECK violation carries, so the caller learns which rule bit."""
    name = getattr(error.diag, "constraint_name", None)
    return name or "constraint_violated"


def _definition_by_type(conn: Connection, consent_type: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT definition_id, consent_type, requires_guardian, withdrawable"
        " FROM plt01.sec_consent_definitions WHERE consent_type = %s",
        (consent_type,),
    ).fetchone()
    if row is None:
        raise NotFound("consent_type_not_defined")
    return {"definition_id": str(row[0]), "consent_type": row[1], "requires_guardian": row[2],
            "withdrawable": row[3]}


def _definition_of(row: dict[str, Any]) -> consent.Definition:
    return consent.Definition(
        definition_id=row["definition_id"], consent_type=row["consent_type"],
        requires_guardian=bool(row["requires_guardian"]), withdrawable=bool(row["withdrawable"]),
    )


def _definitions(conn: Connection) -> list[consent.Definition]:
    rows = conn.execute(
        "SELECT definition_id, consent_type, requires_guardian, withdrawable"
        " FROM plt01.sec_consent_definitions ORDER BY consent_type",
    ).fetchall()
    return [consent.Definition(str(r[0]), r[1], bool(r[2]), bool(r[3])) for r in rows]


def _versions(conn: Connection, definition_id: str) -> list[consent.Version]:
    rows = conn.execute(
        "SELECT consent_version_id, definition_id, version, language, document_hash,"
        " effective_from FROM plt01.sec_consent_versions WHERE definition_id = %s",
        (definition_id,),
    ).fetchall()
    return [consent.Version(str(r[0]), str(r[1]), int(r[2]), r[3], r[4], r[5]) for r in rows]


def _all_versions(conn: Connection) -> list[consent.Version]:
    rows = conn.execute(
        "SELECT consent_version_id, definition_id, version, language, document_hash,"
        " effective_from FROM plt01.sec_consent_versions",
    ).fetchall()
    return [consent.Version(str(r[0]), str(r[1]), int(r[2]), r[3], r[4], r[5]) for r in rows]


def _records(conn: Connection, subject_id: str, definition_id: str) -> list[consent.Record]:
    rows = conn.execute(
        "SELECT record_id, subject_id, definition_id, consent_version_id, action, signed_at,"
        " guardian_subject_id FROM plt01.sec_consent_records"
        " WHERE subject_id = %s AND definition_id = %s ORDER BY signed_at, recorded_at",
        (subject_id, definition_id),
    ).fetchall()
    return [consent.Record(str(r[0]), str(r[1]), str(r[2]), str(r[3]), r[4], r[5],
                           str(r[6]) if r[6] else None) for r in rows]


def _all_records(conn: Connection, subject_id: str) -> list[consent.Record]:
    rows = conn.execute(
        "SELECT record_id, subject_id, definition_id, consent_version_id, action, signed_at,"
        " guardian_subject_id FROM plt01.sec_consent_records WHERE subject_id = %s"
        " ORDER BY signed_at, recorded_at",
        (subject_id,),
    ).fetchall()
    return [consent.Record(str(r[0]), str(r[1]), str(r[2]), str(r[3]), r[4], r[5],
                           str(r[6]) if r[6] else None) for r in rows]


def _append_consent(
    conn: Connection, tenant_id: str, *, subject_id: str, definition_id: str,
    consent_version_id: str, action: str, signed_at: datetime, source: str,
    correlation_id: str, guardian: str | None, evidence_hash_value: str | None,
    evidence_ref: str | None, locale: str, consent_type: str, actor_id: str | None = None,
) -> str:
    try:
        row = conn.execute(
            """
            INSERT INTO plt01.sec_consent_records
                (tenant_id, subject_id, definition_id, consent_version_id, action, signed_at,
                 evidence_hash, evidence_ref, source, guardian_subject_id, locale,
                 correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING record_id
            """,
            (tenant_id, subject_id, definition_id, consent_version_id, action, signed_at,
             evidence_hash_value, evidence_ref, source, guardian, locale, correlation_id),
        ).fetchone()
    except errors.CheckViolation as e:
        raise InvalidRequest(_check_name(e)) from None
    assert row is not None
    # MOD-010: the event is appended on this connection, inside the transaction that wrote the
    # consent record, so the two commit together or not at all. A consumer cannot learn that a
    # member consented to something the database then rolled back, and a consent that committed
    # cannot fail to tell anybody.
    events.append_event(
        conn, tenant_id,
        event_type="consent.granted" if action == "granted" else "consent.withdrawn",
        aggregate_type="consent", aggregate_id=subject_id,
        payload=({"subject_id": subject_id, "consent_type": consent_type,
                  "consent_version_id": consent_version_id,
                  "signed_at": signed_at.isoformat(), "source": source}
                 if action == "granted" else
                 {"subject_id": subject_id, "consent_type": consent_type,
                  "consent_version_id": consent_version_id,
                  "signed_at": signed_at.isoformat()}),
        correlation_id=correlation_id, actor_id=actor_id,
    )
    return str(row[0])


def _holds(conn: Connection) -> list[retention.Hold]:
    rows = conn.execute(
        "SELECT hold_id, subject_id, resource_type, reason, reference, released_at"
        " FROM plt01.sec_legal_holds",
    ).fetchall()
    return [retention.Hold(str(r[0]), str(r[1]) if r[1] else None, r[2], r[3], r[4],
                           released=r[5] is not None) for r in rows]


def _request(conn: Connection, request_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT request_id, subject_id, request_type, status, received_at, due_at,"
        " identity_verified_at, legal_checked_at, refused_reason, completed_at"
        " FROM plt01.sec_dsar_requests WHERE request_id = %s",
        (request_id,),
    ).fetchone()
    if row is None:
        raise NotFound("dsar_not_found")
    return {"request_id": str(row[0]), "subject_id": str(row[1]), "request_type": row[2],
            "status": row[3], "received_at": row[4], "due_at": row[5],
            "identity_verified_at": row[6], "legal_checked_at": row[7],
            "refused_reason": row[8], "completed_at": row[9]}


def _advance(
    pool: Pool, tenant_id: str, *, request_id: str, target: str, from_status: str,
    sets: dict[str, Any],
) -> dict[str, Any]:
    with tenant_scope(pool, tenant_id) as conn:
        request = _request(conn, request_id)
        if request["status"] != from_status:
            raise Conflict(f"request_is_{request['status']}_not_{from_status}")
        try:
            dsar.check_transition(request["status"], target)
        except dsar.DsarError as e:
            raise Conflict(str(e)) from None
        assignments = ", ".join(f"{column} = %s" for column in sets)
        clause = f"status = %s{', ' + assignments if assignments else ''}"
        conn.execute(
            f"UPDATE plt01.sec_dsar_requests SET {clause} WHERE request_id = %s",
            (target, *sets.values(), request_id),
        )
    return {"request_id": request_id, "status": target}


# How each column named in a `clears` tuple is overwritten. The expression is chosen for that
# column's actual constraints, which is why this is a table rather than one rule:
#
#   * NULL wherever the column is nullable -- the cleanest erasure, and `identities`' unique
#     indexes on the two contact columns permit many NULLs where they would permit only one of
#     any constant.
#   * a per-row tombstone, `'erased:' || <the row's own id>`, wherever the column is NOT NULL and
#     carries a unique index. A constant would collide the moment a subject had two devices.
#   * a constant wherever the column is NOT NULL and not unique.
#   * `gen_random_uuid()` for `person_id`, because severing the cross-tenant link means replacing
#     it with something unrelated, not emptying it: the column is what joins this person's
#     identities in other tenants, and a NULL there would read as "never linked".
_CLEAR_SQL: dict[tuple[str, str], str] = {
    # `identities_has_an_identifier` requires one of the two contact columns to survive, so the
    # email is replaced with a per-row tombstone rather than emptied. The unique index permits
    # it because the identity id makes it unique; the phone can then go to NULL.
    ("identities", "email_normalized"): "'erased:' || identity_id::text",
    ("identities", "phone_normalized"): "NULL",
    ("identities", "display_name"): "'erased'",
    ("identities", "person_id"): "gen_random_uuid()",
    # `salt` and `secret_hash` are bytea with minimum lengths (16 and 32), so the replacement has
    # to be bytea of at least that size. A digest of the credential's own id is unrelated to any
    # password and cannot be reversed into one; what matters is only that no supplied password
    # verifies against it, which is true of any value not derived from a password.
    ("credentials", "salt"): "sha256(('erased-salt:' || credential_id::text)::bytea)",
    ("credentials", "secret_hash"): "sha256(('erased-hash:' || credential_id::text)::bytea)",
    # Revoked in the same statement, and `consumed_at` cleared with it: the table has two
    # interlocking checks tying `status` to `revoked_at` and to `consumed_at`, and satisfying one
    # while breaking the other is how this first failed.
    ("credentials", "status"): "'revoked'",
    ("credentials", "revoked_at"): "coalesce(revoked_at, now())",
    ("credentials", "consumed_at"): "NULL",
    ("devices", "fingerprint"): "'erased:' || device_id::text",
    ("devices", "label"): "NULL",
    ("devices", "platform"): "NULL",
    # `token_hash` is bytea of exactly 32 bytes, and a digest of the session id keeps it unique
    # per row. Revoking alongside it means the session is dead by status as well as unmatchable.
    ("sessions", "token_hash"): "sha256(session_id::text::bytea)",
    ("sessions", "revoked_at"): "coalesce(revoked_at, now())",
    ("sessions", "revoke_reason"): "coalesce(revoke_reason, 'erased')",
    ("passkeys", "webauthn_credential_id"): "sha256(passkey_id::text::bytea)",
    ("passkeys", "public_key"): "sha256(('erased:' || passkey_id::text)::bytea)",
    ("passkeys", "aaguid"): "NULL",
    ("passkeys", "label"): "NULL",
    ("challenges", "nonce_hash"): "sha256(challenge_id::text::bytea)",
}


def _perform(
    pool: Pool, tenant_id: str, *, request_id: str, subject_id: str, request_type: str,
    identity_pool: Pool | None, actor_id: str | None = None,
    correlation_id: str | None = None,
) -> list[dsar.Action]:
    """Act on each declared target and write one evidence row per target as it completes.

    Written per target rather than once at the end: an interrupted run leaves the trail of what
    it did finish, so a half-erasure is visible in the evidence rather than only in the status.

    **Only a deletion reaches here.** `fulfil_dsar` refuses the other four types before anything
    is written; this function no longer raises for them, because raising after the caller has
    committed a status is how a request gets stranded.
    """
    performed: list[dsar.Action] = []
    actor = {"actor_id": actor_id, "correlation_id": correlation_id}

    for entry in classification.unreachable_columns():
        performed.append(_record_action(
            pool, tenant_id, request_id=request_id, store="postgresql",
            target=f"{entry.schema}.{entry.table}.{entry.column}", mechanism="pseudonymize",
            outcome="blocked", rows=0,
            detail={"reason": entry.reason, "subject_id": subject_id, **actor},
        ))

    for entry in classification.reachable_columns():
        target = f"{entry.schema}.{entry.table}.{entry.column}"
        if entry.schema != "iam":
            # Nothing outside the identity plane is reachable today. If that changes, whoever
            # adds the entry adds the executor for it here rather than finding this silently
            # reporting success.
            performed.append(_record_action(
                pool, tenant_id, request_id=request_id, store="postgresql", target=target,
                mechanism=entry.mechanism, outcome="failed", rows=0,
                detail={"reason": "no_executor_for_this_schema", **actor},
            ))
            continue
        assert identity_pool is not None  # fulfil_dsar refuses before reaching here
        try:
            affected = _anonymize(identity_pool, tenant_id, entry=entry, subject_id=subject_id)
        except Exception as e:  # noqa: BLE001 -- recorded as failed, then the run continues
            # Continuing rather than re-raising is deliberate: the targets after this one are
            # independent, and stopping would leave them neither done nor recorded. `settle`
            # sees the failure and refuses to complete the request.
            performed.append(_record_action(
                pool, tenant_id, request_id=request_id, store="postgresql", target=target,
                mechanism=entry.mechanism, outcome="failed", rows=0,
                detail={"reason": type(e).__name__, **actor},
            ))
            continue
        performed.append(_record_action(
            pool, tenant_id, request_id=request_id, store="postgresql", target=target,
            mechanism=entry.mechanism, outcome="done", rows=affected,
            detail={"cleared": list(entry.clears), **actor},
        ))
    return performed


def _subject_exists(identity_pool: Pool, tenant_id: str, *, subject_id: str) -> bool:
    """Does this subject_id name an identity in this tenant?

    The anchor of the whole erasure. `sec_dsar_requests.subject_id` is a bare uuid with no
    foreign key -- the planes are separate and one is not available -- so this is the only place
    the question is asked, and it is asked before anything is written. An id that resolves here
    is one `_anonymize`'s `WHERE identity_id = %s` will match; one that does not would have
    updated nothing and been recorded `done`.
    """
    with tenant_scope(identity_pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT 1 FROM iam.identities WHERE identity_id = %s", (subject_id,)
        ).fetchone()
    return row is not None


def _anonymize(
    identity_pool: Pool, tenant_id: str, *, entry: classification.Reachability, subject_id: str
) -> int:
    """Overwrite one table's identifying columns for one subject, and return the row count.

    The SQL is assembled from `_CLEAR_SQL`, which is a fixed table in this module -- the column
    names and the expressions are literals written here, never anything from a request. The only
    value that crosses the boundary is `subject_id`, which is bound as a parameter.
    """
    if not entry.clears:
        return 0
    assignments = []
    for column in entry.clears:
        expression = _CLEAR_SQL.get((entry.table, column))
        if expression is None:
            raise InvalidRequest(f"no_clear_rule_for_{entry.table}.{column}")
        assignments.append(f"{column} = {expression}")
    statement = (
        f"UPDATE iam.{entry.table} SET {', '.join(assignments)} WHERE {entry.locator()} = %s"
    )
    with tenant_scope(identity_pool, tenant_id) as conn:
        cursor = conn.execute(statement, (subject_id,))
        return int(cursor.rowcount)


def _record_action(
    pool: Pool, tenant_id: str, *, request_id: str, store: str, target: str, mechanism: str,
    outcome: str, rows: int, detail: dict[str, Any],
) -> dsar.Action:
    payload = {"request_id": request_id, "target": target, "mechanism": mechanism,
               "outcome": outcome, "rows_affected": rows, **detail}
    digest = evidence_hash(payload)
    with tenant_scope(pool, tenant_id) as conn:
        conn.execute(
            """
            INSERT INTO plt01.sec_dsar_actions
                (tenant_id, request_id, store, target, mechanism, outcome, rows_affected,
                 evidence_hash, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (tenant_id, request_id, store, target, mechanism, outcome, rows, digest,
             Jsonb(detail)),
        )
    return dsar.Action(store=store, target=target, mechanism=mechanism, outcome=outcome,
                       rows_affected=rows, detail=detail)

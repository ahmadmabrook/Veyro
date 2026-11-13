"""MOD-008 IAM-03 service: roles, scoped assignments, policies, approvals and the audit log.

Decisions live in `app.authorization.decision`, `app.authorization.approval` and
`app.authorization.gate`; the catalogue lives in `app.authorization.catalog`; the chain
arithmetic lives in `app.authorization.audit`. This module reads rows, calls those, and writes
the result.

**`require` is the only way anything in this codebase asks whether a caller may act.** The review
that approved MOD-007 named the shape behind every blocking defect it found -- a capability
granted in one place and bounded in another -- and said a third hand-written copy of the
condition was where that pattern would restart. So authorization has one entry point, it
consults one gate, and it writes the audit row for a denial itself, so a surface cannot ask the
question and forget to record the answer.

Appending to the audit log takes a row lock on `iam.audit_chain_heads` for the tenant. Two
concurrent appends would otherwise read the same previous digest and fork the chain, which
verification would correctly report as tampering -- a false alarm that would teach everyone to
ignore real ones.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from app.authorization import approval as approvals
from app.authorization import audit
from app.authorization import decision as authz
from app.authorization import gate as gating
from app.authorization.catalog import (
    PERMISSIONS,
    CatalogError,
    audit_category,
    require_permission,
)
from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound, ServiceError
from app.tenancy import service as tenancy

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.ASCII
)

DEFAULT_APPROVAL_WINDOW = timedelta(days=7)


class Forbidden(ServiceError):
    """Authorization refused. One code, so a caller cannot map the reason back to a role list."""

    status = 403


class StepUpRequired(ServiceError):
    status = 403


def _now() -> datetime:
    return datetime.now(UTC)


def _require_uuid(value: str, field: str) -> str:
    if not _UUID.fullmatch(value.lower()):
        raise InvalidRequest(f"bad_{field}")
    return value.lower()


def _settled(outcome: tuple[dict[str, Any], ServiceError | None]) -> dict[str, Any]:
    """Raise the refusal a transaction recorded, **after** that transaction has committed.

    `tenant_scope` rolls back when the block raises, so an audit row written just before a raise
    inside it goes down with the refusal. The erased rows are the highest-signal ones this module
    writes -- an attempted privilege escalation, a repeated attempt to approve one's own request
    -- and IAM-03-R06 lists access among the categories that must be audited, where the refusal
    is the event that matters most.

    **The rule, because this is the second module it has bitten:** anywhere `_append_audit`
    precedes a refusal, the function returns its error and the caller raises it here. `check` and
    `require` were already shaped that way; `assign_role`, `request_approval` and
    `decide_approval` were not, and a review proved all three wrote nothing. MOD-007 has the same
    helper for the same reason.
    """
    body, error = outcome
    if error is not None:
        raise error
    return body


def _permission(name: str) -> str:
    try:
        require_permission(name)
    except CatalogError:
        raise InvalidRequest("unknown_permission") from None
    return name


# --------------------------------------------------------------------------- the audit log

def _append_audit(
    conn: Connection[Any],
    tenant_id: str,
    *,
    category: str,
    action: str,
    outcome: str,
    correlation_id: str,
    actor_identity_id: str | None = None,
    on_behalf_of: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one entry, extending the tenant's hash chain under a row lock.

    The lock is on the head, not the log, so appends serialise per tenant while the log itself
    stays insert-only. `occurred_at` is generated here and goes into the digest, so what is
    hashed is exactly what is stored.
    """
    now = _now()
    conn.execute(
        "INSERT INTO iam.audit_chain_heads (tenant_id, sequence, head_hash)"
        " VALUES (%s, 0, %s) ON CONFLICT (tenant_id) DO NOTHING",
        (tenant_id, audit.GENESIS),
    )
    head = conn.execute(
        "SELECT sequence, head_hash FROM iam.audit_chain_heads WHERE tenant_id = %s FOR UPDATE",
        (tenant_id,),
    ).fetchone()
    assert head is not None
    sequence, prev_hash = int(head[0]) + 1, bytes(head[1])

    payload = {
        "category": category, "action": action, "outcome": outcome,
        "actor_identity_id": actor_identity_id, "on_behalf_of": on_behalf_of,
        "resource_type": resource_type, "resource_id": resource_id, "detail": detail or {},
        "correlation_id": correlation_id, "occurred_at": now.isoformat(),
    }
    entry_hash = audit.entry_digest(tenant_id, sequence, prev_hash, payload)

    conn.execute(
        """
        INSERT INTO iam.audit_events
            (tenant_id, sequence, category, action, outcome, actor_identity_id, on_behalf_of,
             resource_type, resource_id, detail, correlation_id, occurred_at, prev_hash,
             entry_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (tenant_id, sequence, category, action, outcome, actor_identity_id, on_behalf_of,
         resource_type, resource_id, Jsonb(detail or {}), correlation_id, now, prev_hash,
         entry_hash),
    )
    conn.execute(
        "UPDATE iam.audit_chain_heads SET sequence = %s, head_hash = %s, updated_at = %s"
        " WHERE tenant_id = %s",
        (sequence, entry_hash, now, tenant_id),
    )
    return {"sequence": sequence, "occurred_at": now.isoformat()}


def record_audit(
    pool: Pool, tenant_id: str, *, category: str, action: str, outcome: str,
    correlation_id: str, actor_identity_id: str | None = None, **fields: Any,
) -> dict[str, Any]:
    """RecordPrivilegedAction (IAM-03-R06), for a caller outside this module."""
    _require_uuid(correlation_id, "correlation_id")
    with tenant_scope(pool, tenant_id) as conn:
        return _append_audit(conn, tenant_id, category=category, action=action,
                             outcome=outcome, correlation_id=correlation_id,
                             actor_identity_id=actor_identity_id, **fields)


def read_audit(
    pool: Pool, tenant_id: str, *, limit: int = 100, category: str | None = None
) -> list[dict[str, Any]]:
    capped = max(1, min(int(limit), 500))
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT sequence, category, action, outcome, actor_identity_id, resource_type,"
            " resource_id, detail, correlation_id, occurred_at FROM iam.audit_events"
            " WHERE (%s::text IS NULL OR category = %s::text)"
            " ORDER BY sequence DESC LIMIT %s",
            (category, category, capped),
        ).fetchall()
    return [
        {"sequence": int(r[0]), "category": r[1], "action": r[2], "outcome": r[3],
         "actor_identity_id": str(r[4]) if r[4] else None, "resource_type": r[5],
         "resource_id": r[6], "detail": r[7], "correlation_id": str(r[8]),
         "occurred_at": r[9].isoformat()} for r in rows
    ]


def verify_audit_chain(pool: Pool, tenant_id: str) -> dict[str, Any]:
    """Recompute the whole chain from the stored rows (IAM-03-R06).

    This is the full verification: every digest recomputed from its own entry, where
    `backend/tests/sql/audit_chain.sql` checks only that the stored digests link up. Both exist
    because they fail differently -- the SQL one runs with no application present, this one
    notices an entry whose content was changed together with its digest.
    """
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT sequence, category, action, outcome, actor_identity_id, on_behalf_of,"
            " resource_type, resource_id, detail, correlation_id, occurred_at, prev_hash,"
            " entry_hash FROM iam.audit_events ORDER BY sequence",
        ).fetchall()
        head = conn.execute(
            "SELECT sequence, head_hash FROM iam.audit_chain_heads WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()

    entries = [
        audit.Entry(
            sequence=int(r[0]), category=r[1], action=r[2], outcome=r[3],
            actor_identity_id=str(r[4]) if r[4] else None,
            on_behalf_of=str(r[5]) if r[5] else None, resource_type=r[6],
            resource_id=r[7], detail=r[8], correlation_id=str(r[9]),
            occurred_at=r[10].isoformat(), prev_hash=bytes(r[11]), entry_hash=bytes(r[12]),
        )
        for r in rows
    ]
    try:
        audit.verify_chain(tenant_id, entries)
    except audit.AuditError as exc:
        return {"verified": False, "entries": len(entries), "problem": exc.code, "at": exc.at}

    expected_sequence, expected_head = audit.head_of(entries)
    head_sequence = int(head[0]) if head else 0
    head_hash = bytes(head[1]) if head else audit.GENESIS
    if (head_sequence, head_hash) != (expected_sequence, expected_head):
        return {"verified": False, "entries": len(entries), "problem": "head_mismatch",
                "at": expected_sequence}
    return {"verified": True, "entries": len(entries), "problem": None, "at": None}


# --------------------------------------------------------------------------- roles

def _refuse_escalation(
    conn: Connection[Any], tenant_id: str, *, actor_identity_id: str | None,
    wanted: set[str], correlation_id: str, role_key: str, resource_id: str | None = None,
) -> ServiceError | None:
    """Refuse to put a permission into a role unless the actor holds it themselves.

    The same rule `assign_role` applies to granting, applied to **writing** a role -- which is
    the adjacent door a review walked through after the first was shut. An actor holding only
    `authz.role.write` rewrote a role it already held to include refunds and session revocation,
    gaining them without any assignment being created, so the grant-time guard was never
    consulted.

    It binds whether or not the actor holds the role: putting a permission you do not have into
    somebody else's role is the same escalation performed on their behalf.

    `actor_identity_id` of None is the bootstrap and internal seeding, which hold everything by
    construction; every HTTP path supplies one.
    """
    if actor_identity_id is None:
        return None
    held = authz.permissions_of(_load_assignments(conn, actor_identity_id), now=_now())
    escalation = sorted(wanted - held)
    if not escalation:
        return None
    _append_audit(conn, tenant_id, category="access", action="authz.role.write",
                  outcome="denied", correlation_id=correlation_id,
                  actor_identity_id=actor_identity_id, resource_type="role",
                  resource_id=resource_id,
                  detail={"reason": "escalation", "role_key": role_key,
                          "not_held": escalation})
    return Forbidden("cannot_grant_what_you_do_not_hold")


def create_role(
    pool: Pool, tenant_id: str, *, role_key: str, display_name: str, correlation_id: str,
    permissions: list[str] | None = None, description: str | None = None,
    actor_identity_id: str | None = None,
) -> dict[str, Any]:
    """CreateRole (IAM-03-R01). Every permission is checked against the catalogue, and against
    what the actor holds.

    A typo in a role definition fails here rather than denying silently for ever afterwards, and
    a permission the author does not hold is refused outright -- see `_refuse_escalation`.
    """
    return _settled(_create_role_in_tx(
        pool, tenant_id, role_key=role_key, display_name=display_name,
        correlation_id=correlation_id, permissions=permissions, description=description,
        actor_identity_id=actor_identity_id,
    ))


def _create_role_in_tx(
    pool: Pool, tenant_id: str, *, role_key: str, display_name: str, correlation_id: str,
    permissions: list[str] | None, description: str | None, actor_identity_id: str | None,
) -> tuple[dict[str, Any], ServiceError | None]:
    _require_uuid(correlation_id, "correlation_id")
    wanted = [_permission(p) for p in (permissions or [])]
    if not display_name.strip():
        raise InvalidRequest("bad_display_name")
    with tenant_scope(pool, tenant_id) as conn:
        refusal = _refuse_escalation(conn, tenant_id, actor_identity_id=actor_identity_id,
                                     wanted=set(wanted), correlation_id=correlation_id,
                                     role_key=role_key)
        if refusal is not None:
            return {}, refusal
        try:
            row = conn.execute(
                "INSERT INTO iam.roles (tenant_id, role_key, display_name, description)"
                " VALUES (%s, %s, %s, %s) RETURNING role_id",
                (tenant_id, role_key, display_name, description),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("role_exists") from None
        except errors.CheckViolation:
            raise InvalidRequest("bad_role_key") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tenant_not_found") from None
        assert row is not None
        role_id = str(row[0])
        for permission in wanted:
            conn.execute(
                "INSERT INTO iam.role_permissions (tenant_id, role_id, permission)"
                " VALUES (%s, %s, %s)",
                (tenant_id, role_id, permission),
            )
        _append_audit(conn, tenant_id, category="access", action="role.created",
                      outcome="recorded", correlation_id=correlation_id,
                      actor_identity_id=actor_identity_id, resource_type="role",
                      resource_id=role_id, detail={"role_key": role_key,
                                                   "permissions": sorted(wanted)})
    return {"role_id": role_id, "role_key": role_key, "display_name": display_name,
            "permissions": sorted(wanted)}, None


def set_role_permissions(
    pool: Pool, tenant_id: str, *, role_key: str, permissions: list[str], correlation_id: str,
    actor_identity_id: str | None = None,
) -> dict[str, Any]:
    """Replace a role's permissions, recording what changed rather than only what it now holds.

    Bounded by what the actor holds, exactly as `create_role` and `assign_role` are. Editing a
    role you hold is a way of granting yourself, and it was the door left open when only the
    grant path was guarded.
    """
    _require_uuid(correlation_id, "correlation_id")
    wanted = {_permission(p) for p in permissions}
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _set_permissions_in_tx(conn, tenant_id, role_key=role_key, wanted=wanted,
                                         correlation_id=correlation_id,
                                         actor_identity_id=actor_identity_id)
    return _settled(outcome)


def _set_permissions_in_tx(
    conn: Connection[Any], tenant_id: str, *, role_key: str, wanted: set[str],
    correlation_id: str, actor_identity_id: str | None,
) -> tuple[dict[str, Any], ServiceError | None]:
    role = conn.execute(
        "SELECT role_id, builtin FROM iam.roles WHERE role_key = %s FOR UPDATE", (role_key,)
    ).fetchone()
    if role is None:
        raise NotFound("role_not_found")
    if role[1]:
        raise Conflict("builtin_role_is_not_editable")
    role_id = str(role[0])

    refusal = _refuse_escalation(conn, tenant_id, actor_identity_id=actor_identity_id,
                                 wanted=wanted, correlation_id=correlation_id,
                                 role_key=role_key, resource_id=role_id)
    if refusal is not None:
        return {}, refusal

    held = {
        r[0] for r in conn.execute(
            "SELECT permission FROM iam.role_permissions WHERE role_id = %s", (role_id,)
        ).fetchall()
    }
    for permission in sorted(wanted - held):
        conn.execute(
            "INSERT INTO iam.role_permissions (tenant_id, role_id, permission)"
            " VALUES (%s, %s, %s)",
            (tenant_id, role_id, permission),
        )
    for permission in sorted(held - wanted):
        conn.execute(
            "DELETE FROM iam.role_permissions WHERE role_id = %s AND permission = %s",
            (role_id, permission),
        )
    conn.execute("UPDATE iam.roles SET version = version + 1 WHERE role_id = %s", (role_id,))
    _append_audit(conn, tenant_id, category="access", action="role.permissions_changed",
                  outcome="recorded", correlation_id=correlation_id,
                  actor_identity_id=actor_identity_id, resource_type="role",
                  resource_id=role_id,
                  detail={"role_key": role_key, "granted": sorted(wanted - held),
                          "removed": sorted(held - wanted)})
    return ({"role_key": role_key, "permissions": sorted(wanted),
             "granted": sorted(wanted - held), "removed": sorted(held - wanted)}, None)


def list_roles(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT r.role_id, r.role_key, r.display_name, r.description, r.builtin, r.version,"
            " coalesce(array_agg(p.permission ORDER BY p.permission)"
            "          FILTER (WHERE p.permission IS NOT NULL), '{}') "
            " FROM iam.roles r LEFT JOIN iam.role_permissions p ON p.role_id = r.role_id"
            " GROUP BY r.role_id, r.role_key, r.display_name, r.description, r.builtin,"
            " r.version ORDER BY r.role_key"
        ).fetchall()
    return [
        {"role_id": str(r[0]), "role_key": r[1], "display_name": r[2], "description": r[3],
         "builtin": bool(r[4]), "version": int(r[5]), "permissions": list(r[6])} for r in rows
    ]


# --------------------------------------------------------------------------- assignments

def assign_role(
    pool: Pool,
    tenant_id: str,
    *,
    identity_id: str,
    role_key: str,
    granted_by: str,
    correlation_id: str,
    scope_type: str = "tenant",
    brand_id: str | None = None,
    location_id: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """GrantRole (IAM-03-R01/R04), at a scope and optionally for a time.

    **A grantor may only grant permissions they themselves hold, at a scope they themselves
    cover.** Without that rule `authz.assignment.write` is equivalent to every permission in the
    catalogue: a review took a clerk holding nothing else and had it grant itself the bootstrap
    owner role, arriving at 37 permissions including issuing refunds. Least privilege cannot
    survive a delegation model where the thing being delegated is unbounded.

    An expiring assignment needs no revocation to stop working, which is what makes temporary
    access temporary rather than a reminder somebody has to act on.
    """
    _require_uuid(correlation_id, "correlation_id")
    if scope_type not in ("tenant", "brand", "location"):
        raise InvalidRequest("bad_scope_type")
    if scope_type == "brand" and not brand_id:
        raise InvalidRequest("brand_scope_needs_brand_id")
    if scope_type == "location" and not location_id:
        raise InvalidRequest("location_scope_needs_location_id")
    if scope_type == "tenant" and (brand_id or location_id):
        raise InvalidRequest("tenant_scope_takes_no_target")

    target = authz.Scope(scope_type=scope_type, brand_id=brand_id, location_id=location_id)
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _assign_in_tx(
            conn, tenant_id, identity_id=identity_id, role_key=role_key,
            granted_by=granted_by, correlation_id=correlation_id, scope_type=scope_type,
            brand_id=brand_id, location_id=location_id, expires_at=expires_at, target=target,
        )
    return _settled(outcome)


def _assign_in_tx(
    conn: Connection[Any], tenant_id: str, *, identity_id: str, role_key: str, granted_by: str,
    correlation_id: str, scope_type: str, brand_id: str | None, location_id: str | None,
    expires_at: datetime | None, target: authz.Scope,
) -> tuple[dict[str, Any], ServiceError | None]:
    role = conn.execute("SELECT role_id FROM iam.roles WHERE role_key = %s",
                        (role_key,)).fetchone()
    if role is None:
        raise NotFound("role_not_found")
    role_id = str(role[0])
    wanted = {
        r[0] for r in conn.execute(
            "SELECT permission FROM iam.role_permissions WHERE role_id = %s", (role_id,)
        ).fetchall()
    }
    held = authz.permissions_of(_load_assignments(conn, granted_by), now=_now(),
                                scope=target)
    escalation = sorted(wanted - held)
    if escalation:
        _append_audit(conn, tenant_id, category="access", action="authz.assignment.write",
                      outcome="denied", correlation_id=correlation_id,
                      actor_identity_id=granted_by, resource_type="role",
                      resource_id=role_id,
                      detail={"reason": "escalation", "role_key": role_key,
                              "not_held": escalation})
        # Returned, not raised: the denial has to outlive the refusal. See `_settled`.
        return {}, Forbidden("cannot_grant_what_you_do_not_hold")
    try:
        row = conn.execute(
            """
            INSERT INTO iam.role_assignments
                (tenant_id, identity_id, role_id, scope_type, brand_id, location_id,
                 granted_by, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING assignment_id
            """,
            (tenant_id, identity_id, role_id, scope_type, brand_id, location_id,
             granted_by, expires_at),
        ).fetchone()
    except errors.UniqueViolation:
        raise Conflict("assignment_already_live") from None
    except errors.ForeignKeyViolation:
        raise NotFound("identity_role_or_scope_not_found") from None
    except errors.CheckViolation:
        raise InvalidRequest("bad_assignment") from None
    assert row is not None
    assignment_id = str(row[0])
    _append_audit(conn, tenant_id, category="access", action="role.assigned",
                  outcome="recorded", correlation_id=correlation_id,
                  actor_identity_id=granted_by, resource_type="assignment",
                  resource_id=assignment_id,
                  detail={"identity_id": identity_id, "role_key": role_key,
                          "scope_type": scope_type,
                          "expires_at": expires_at.isoformat() if expires_at else None})
    return ({"assignment_id": assignment_id, "identity_id": identity_id, "role_key": role_key,
             "scope_type": scope_type, "brand_id": brand_id, "location_id": location_id,
             "expires_at": expires_at.isoformat() if expires_at else None}, None)


def revoke_assignment(
    pool: Pool, tenant_id: str, *, assignment_id: str, correlation_id: str,
    actor_identity_id: str | None = None, reason: str = "revoked",
) -> dict[str, Any]:
    _require_uuid(correlation_id, "correlation_id")
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "UPDATE iam.role_assignments SET revoked_at = %s, revoked_reason = %s"
            " WHERE assignment_id = %s AND revoked_at IS NULL RETURNING identity_id",
            (now, reason, assignment_id),
        ).fetchone()
        if row is None:
            raise NotFound("assignment_not_found_or_already_revoked")
        _append_audit(conn, tenant_id, category="access", action="role.revoked",
                      outcome="recorded", correlation_id=correlation_id,
                      actor_identity_id=actor_identity_id, resource_type="assignment",
                      resource_id=assignment_id,
                      detail={"identity_id": str(row[0]), "reason": reason})
    return {"assignment_id": assignment_id, "revoked": True, "reason": reason}


def _load_assignments(conn: Connection[Any], identity_id: str) -> list[authz.Assignment]:
    rows = conn.execute(
        "SELECT r.role_key, a.scope_type, a.brand_id, a.location_id, a.expires_at,"
        " a.revoked_at,"
        " coalesce(array_agg(p.permission) FILTER (WHERE p.permission IS NOT NULL), '{}')"
        " FROM iam.role_assignments a"
        " JOIN iam.roles r ON r.role_id = a.role_id"
        " LEFT JOIN iam.role_permissions p ON p.role_id = a.role_id"
        " WHERE a.identity_id = %s"
        " GROUP BY a.assignment_id, r.role_key, a.scope_type, a.brand_id, a.location_id,"
        " a.expires_at, a.revoked_at",
        (identity_id,),
    ).fetchall()
    return [
        authz.Assignment(
            role_key=r[0],
            permissions=frozenset(r[6]),
            scope=authz.Scope(scope_type=r[1],
                              brand_id=str(r[2]) if r[2] else None,
                              location_id=str(r[3]) if r[3] else None),
            expires_at=r[4],
            revoked=r[5] is not None,
        )
        for r in rows
    ]


def _load_policies(conn: Connection[Any], action: str) -> list[authz.Policy]:
    rows = conn.execute(
        "SELECT policy_key, effect, action, match, masked_fields, priority FROM iam.policies"
        " WHERE action = %s AND retired_at IS NULL",
        (action,),
    ).fetchall()
    return [
        authz.Policy(policy_key=r[0], effect=r[1], action=r[2], match=r[3],
                     masked_fields=tuple(r[4]), priority=int(r[5]))
        for r in rows
    ]


def list_assignments(pool: Pool, tenant_id: str, *, identity_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT a.assignment_id, r.role_key, a.scope_type, a.brand_id, a.location_id,"
            " a.granted_at, a.expires_at, a.revoked_at, a.revoked_reason"
            " FROM iam.role_assignments a JOIN iam.roles r ON r.role_id = a.role_id"
            " WHERE a.identity_id = %s ORDER BY a.granted_at",
            (identity_id,),
        ).fetchall()
    return [
        {"assignment_id": str(r[0]), "role_key": r[1], "scope_type": r[2],
         "brand_id": str(r[3]) if r[3] else None,
         "location_id": str(r[4]) if r[4] else None,
         "granted_at": r[5].isoformat(),
         "expires_at": r[6].isoformat() if r[6] else None,
         "revoked_at": r[7].isoformat() if r[7] else None, "revoked_reason": r[8]}
        for r in rows
    ]


# --------------------------------------------------------------------------- policies

def write_policy(
    pool: Pool, tenant_id: str, *, policy_key: str, effect: str, action: str,
    correlation_id: str, match: dict[str, str] | None = None,
    masked_fields: list[str] | None = None, priority: int = 100,
    description: str | None = None, actor_identity_id: str | None = None,
) -> dict[str, Any]:
    """DefinePermissionPolicy (IAM-03-R02/R03). Replacing a key retires the old one."""
    _require_uuid(correlation_id, "correlation_id")
    if effect not in ("allow", "deny", "mask"):
        raise InvalidRequest("bad_effect")
    _permission(action)
    fields = masked_fields or []
    if (effect == "mask") != bool(fields):
        raise InvalidRequest("mask_policy_needs_masked_fields")

    with tenant_scope(pool, tenant_id) as conn:
        conn.execute(
            "UPDATE iam.policies SET retired_at = now()"
            " WHERE policy_key = %s AND retired_at IS NULL",
            (policy_key,),
        )
        try:
            row = conn.execute(
                """
                INSERT INTO iam.policies
                    (tenant_id, policy_key, effect, action, match, masked_fields, priority,
                     description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING policy_id
                """,
                (tenant_id, policy_key, effect, action, Jsonb(match or {}), fields, priority,
                 description),
            ).fetchone()
        except errors.CheckViolation:
            raise InvalidRequest("bad_policy") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tenant_not_found") from None
        assert row is not None
        _append_audit(conn, tenant_id, category="access", action="policy.written",
                      outcome="recorded", correlation_id=correlation_id,
                      actor_identity_id=actor_identity_id, resource_type="policy",
                      resource_id=str(row[0]),
                      detail={"policy_key": policy_key, "effect": effect, "action": action})
    return {"policy_id": str(row[0]), "policy_key": policy_key, "effect": effect,
            "action": action, "masked_fields": fields, "priority": priority}


def list_policies(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT policy_key, effect, action, match, masked_fields, priority, description"
            " FROM iam.policies WHERE retired_at IS NULL ORDER BY priority, policy_key"
        ).fetchall()
    return [
        {"policy_key": r[0], "effect": r[1], "action": r[2], "match": r[3],
         "masked_fields": list(r[4]), "priority": int(r[5]), "description": r[6]}
        for r in rows
    ]


def bootstrap(
    pool: Pool, tenant_id: str, *, identity_id: str, role_key: str, display_name: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Create the first role, holding every permission, and grant it to the caller. Once.

    Something has to break the circle: creating a role needs `authz.role.write`, which is held
    through a role, which has to be created. This is that something.

    It is bounded in the one way that matters -- **it refuses the moment any assignment exists in
    the tenant**, checked under a lock so two callers cannot both pass. The grant is tenant-wide
    and total, which is the opposite of least privilege, so it is also the first thing an access
    review should look at; opening one is how a tenant narrows it. The audit entry records what
    was granted and to whom.

    It is no weaker than the surface around it, because `X-Veyro-Tenant` is an unauthenticated
    claim and anyone who knows a tenant id can already register an identity in it. That is the
    real hole, it is recorded in CLAUDE.md, and when it closes this function needs revisiting
    with it rather than being forgotten.
    """
    _require_uuid(correlation_id, "correlation_id")
    with tenant_scope(pool, tenant_id) as conn:
        # Lock the head first: every write in this module appends to the chain, so taking that
        # lock before counting makes two concurrent bootstraps serialise on it.
        conn.execute(
            "INSERT INTO iam.audit_chain_heads (tenant_id, sequence, head_hash)"
            " VALUES (%s, 0, %s) ON CONFLICT (tenant_id) DO NOTHING",
            (tenant_id, audit.GENESIS),
        )
        conn.execute(
            "SELECT sequence FROM iam.audit_chain_heads WHERE tenant_id = %s FOR UPDATE",
            (tenant_id,),
        )
        existing = conn.execute("SELECT count(*) FROM iam.role_assignments").fetchone()
        assert existing is not None
        if int(existing[0]) > 0:
            raise Conflict("already_bootstrapped")

        try:
            role = conn.execute(
                "INSERT INTO iam.roles (tenant_id, role_key, display_name, description)"
                " VALUES (%s, %s, %s, %s) RETURNING role_id",
                (tenant_id, role_key, display_name,
                 "Created by the one-time authorization bootstrap"),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("role_exists") from None
        except errors.CheckViolation:
            raise InvalidRequest("bad_role_key") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tenant_not_found") from None
        assert role is not None
        role_id = str(role[0])
        for permission in sorted(PERMISSIONS):
            conn.execute(
                "INSERT INTO iam.role_permissions (tenant_id, role_id, permission)"
                " VALUES (%s, %s, %s)",
                (tenant_id, role_id, permission),
            )
        try:
            assignment = conn.execute(
                "INSERT INTO iam.role_assignments"
                " (tenant_id, identity_id, role_id, scope_type, granted_by)"
                " VALUES (%s, %s, %s, 'tenant', %s) RETURNING assignment_id",
                (tenant_id, identity_id, role_id, identity_id),
            ).fetchone()
        except errors.ForeignKeyViolation:
            raise NotFound("identity_not_found") from None
        assert assignment is not None
        _append_audit(conn, tenant_id, category="access", action="authorization.bootstrapped",
                      outcome="recorded", correlation_id=correlation_id,
                      actor_identity_id=identity_id, resource_type="role",
                      resource_id=role_id,
                      detail={"role_key": role_key, "permissions": len(PERMISSIONS),
                              "granted_to": identity_id})
    return {"role_id": role_id, "role_key": role_key,
            "assignment_id": str(assignment[0]), "permissions": len(PERMISSIONS),
            "granted_to": identity_id}


# --------------------------------------------------------------------------- the gate

def resolve_scope(
    tenant_pool: Pool, tenant_id: str, *, brand_id: str | None, location_id: str | None
) -> authz.Scope:
    """Turn request input into a scope, **deriving the brand from the location** rather than
    believing the caller about it.

    This is the only sanctioned way to build a `Scope` from anything a client sent. When a
    location is named, its brand is looked up in `plt01.locations`; any `brand_id` the caller
    also sent is discarded. A review demonstrated the alternative: a manager scoped to brand A
    acting on a location of brand B, allowed because they sent `brand_id=A` beside it, with the
    permission simulator confirming the escalation rather than exposing it.

    A location that does not exist in this tenant resolves to no brand, so a brand scope covers
    nothing and the request falls back to default deny.
    """
    if location_id is None:
        if brand_id is None:
            return authz.Scope()
        return authz.Scope(scope_type="brand", brand_id=brand_id)
    resolved = tenancy.brand_of_location(tenant_pool, tenant_id, location_id)
    return authz.Scope(scope_type="location", brand_id=resolved, location_id=location_id)



def check(
    pool: Pool,
    tenant_id: str,
    *,
    identity_id: str,
    session_aal: int,
    action: str,
    correlation_id: str,
    scope: authz.Scope | None = None,
    attributes: dict[str, str] | None = None,
    record_denial: bool = True,
) -> gating.Gate:
    """AuthorizeAction (IAM-03). The one question, asked in the one place.

    A denial is written to the audit log here rather than by the caller, so a surface cannot ask
    whether somebody may act and then forget to record that they were refused. IAM-03-R06 lists
    access among the categories that must be audited, and a refusal is the access event that
    matters most.
    """
    _require_uuid(correlation_id, "correlation_id")
    request = authz.Request(action=action, scope=scope or authz.Scope(),
                            attributes=attributes or {})
    with tenant_scope(pool, tenant_id) as conn:
        assignments = _load_assignments(conn, identity_id)
        policies = _load_policies(conn, action)
        decided = gating.may(session_aal=session_aal, request=request,
                             assignments=assignments, policies=policies, now=_now())
        if not decided.allowed and record_denial:
            try:
                category = audit_category(action)
            except CatalogError:
                category = "access"
            _append_audit(conn, tenant_id, category=category, action=action, outcome="denied",
                          correlation_id=correlation_id, actor_identity_id=identity_id,
                          detail={"reason": decided.reason,
                                  "required_aal": decided.required_aal})
    return decided


def require(
    pool: Pool, tenant_id: str, *, identity_id: str, session_aal: int, action: str,
    correlation_id: str, **context: Any,
) -> gating.Gate:
    """`check`, but it raises. For a caller that must fail closed rather than branch."""
    decided = check(pool, tenant_id, identity_id=identity_id, session_aal=session_aal,
                    action=action, correlation_id=correlation_id, **context)
    if decided.allowed:
        return decided
    if decided.step_up_required:
        raise StepUpRequired("step_up_required")
    raise Forbidden("forbidden")


def effective_permissions(
    pool: Pool, tenant_id: str, *, identity_id: str, scope: authz.Scope | None = None
) -> dict[str, Any]:
    """The permission simulator (IAM-03-R07), answered from the evaluator's own rules.

    Takes a `Scope` built by `resolve_scope`, not raw ids: a simulator that accepts a scope the
    evaluator would never see tells its reader something untrue, and the review found it
    confirming an escalation rather than exposing one.
    """
    target = scope or authz.Scope()
    with tenant_scope(pool, tenant_id) as conn:
        assignments = _load_assignments(conn, identity_id)
    granted = authz.permissions_of(assignments, now=_now(), scope=target)
    return {"identity_id": identity_id, "scope_type": target.scope_type,
            "brand_id": target.brand_id, "location_id": target.location_id,
            "permissions": sorted(granted)}


# --------------------------------------------------------------------------- approvals

def write_approval_policy(
    pool: Pool, tenant_id: str, *, action: str, required_permission: str, correlation_id: str,
    threshold_minor: int = 0, required_approvals: int = 1,
    separation_of_duties: bool = True, actor_identity_id: str | None = None,
) -> dict[str, Any]:
    _require_uuid(correlation_id, "correlation_id")
    _permission(action)
    _permission(required_permission)
    if required_approvals < 1:
        raise InvalidRequest("approval_policy_needs_an_approver")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO iam.approval_policies
                    (tenant_id, action, threshold_minor, required_permission,
                     required_approvals, separation_of_duties)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING approval_policy_id
                """,
                (tenant_id, action, threshold_minor, required_permission, required_approvals,
                 separation_of_duties),
            ).fetchone()
        except errors.CheckViolation:
            raise InvalidRequest("bad_approval_policy") from None
        assert row is not None
        _append_audit(conn, tenant_id, category="access", action="approval_policy.written",
                      outcome="recorded", correlation_id=correlation_id,
                      actor_identity_id=actor_identity_id, resource_type="approval_policy",
                      resource_id=str(row[0]), detail={"action": action,
                                                       "threshold_minor": threshold_minor})
    return {"approval_policy_id": str(row[0]), "action": action,
            "required_permission": required_permission,
            "threshold_minor": threshold_minor, "required_approvals": required_approvals,
            "separation_of_duties": separation_of_duties}


def _approval_policies(conn: Connection[Any], action: str) -> list[approvals.ApprovalPolicy]:
    """Every live policy for an action. `approvals.policy_for` combines them into the strictest
    terms; choosing one of them would let a lenient row above a strict one govern."""
    rows = conn.execute(
        "SELECT action, threshold_minor, required_permission, required_approvals,"
        " separation_of_duties FROM iam.approval_policies"
        " WHERE action = %s AND retired_at IS NULL",
        (action,),
    ).fetchall()
    return [
        approvals.ApprovalPolicy(action=r[0], threshold_minor=int(r[1]),
                                 required_permissions=frozenset({r[2]}),
                                 required_approvals=int(r[3]),
                                 separation_of_duties=bool(r[4]))
        for r in rows
    ]


def request_approval(
    pool: Pool, tenant_id: str, *, action: str, resource_type: str, requested_by: str,
    correlation_id: str, resource_id: str | None = None, amount_minor: int | None = None,
    currency: str | None = None, reason: str | None = None,
) -> dict[str, Any]:
    """RequestApproval (IAM-03-R05). Refuses when no policy requires one.

    **The requester must hold the action's own permission.** Approval gates an action somebody is
    authorized for but which exceeds a threshold; it is not a way in for somebody who is not
    authorized at all. Assurance is deliberately *not* required here -- stepping up belongs at
    the moment the approved action is performed, not at the moment it is asked for -- so this
    reads the authorization half of the decision and ignores the rest. Leaving it open let an
    identity with no roles fill the audit log with requests for actions it could never take.
    """
    _require_uuid(correlation_id, "correlation_id")
    _permission(action)
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _request_in_tx(
            conn, tenant_id, action=action, resource_type=resource_type,
            resource_id=resource_id, amount_minor=amount_minor, currency=currency,
            reason=reason, requested_by=requested_by, now=now,
            correlation_id=correlation_id,
        )
    return _settled(outcome)


def _request_in_tx(
    conn: Connection[Any], tenant_id: str, *, action: str, resource_type: str,
    resource_id: str | None, amount_minor: int | None, currency: str | None,
    reason: str | None, requested_by: str, now: datetime, correlation_id: str,
) -> tuple[dict[str, Any], ServiceError | None]:
    authorized = authz.authorize(
        authz.Request(action=action), _load_assignments(conn, requested_by),
        _load_policies(conn, action), now=now,
    )
    if not authorized.allowed:
        _append_audit(conn, tenant_id, category="access", action=action, outcome="denied",
                      correlation_id=correlation_id, actor_identity_id=requested_by,
                      detail={"reason": "cannot_request_what_you_cannot_do"})
        # Returned, not raised, so the refusal survives its own transaction. See `_settled`.
        return {}, Forbidden("forbidden")

    policy = approvals.policy_for(_approval_policies(conn, action), action, amount_minor)
    if policy is None:
        raise Conflict("no_approval_policy_applies")
    request_id, expires = _insert_request(
        conn, tenant_id, action=action, resource_type=resource_type, resource_id=resource_id,
        amount_minor=amount_minor, currency=currency, reason=reason,
        requested_by=requested_by, policy=policy, now=now, correlation_id=correlation_id,
    )
    return ({"request_id": request_id, "action": action, "state": "pending",
             "required_approvals": policy.required_approvals,
             "separation_of_duties": policy.separation_of_duties,
             "required_permissions": sorted(policy.required_permissions),
             "expires_at": expires.isoformat()}, None)


def _insert_request(
    conn: Connection[Any], tenant_id: str, *, action: str, resource_type: str,
    resource_id: str | None, amount_minor: int | None, currency: str | None,
    reason: str | None, requested_by: str, policy: approvals.ApprovalPolicy,
    now: datetime, correlation_id: str,
) -> tuple[str, datetime]:
    """Write the request and its audit entry. The terms come from `policy` and are snapshotted
    onto the row, because what governs a decision is what applied when it was asked for."""
    expires = now + DEFAULT_APPROVAL_WINDOW
    try:
        row = conn.execute(
            """
            INSERT INTO iam.approval_requests
                (tenant_id, action, resource_type, resource_id, amount_minor, currency,
                 reason, requested_by, required_approvals, separation_of_duties,
                 required_permissions, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING request_id
            """,
            (tenant_id, action, resource_type, resource_id, amount_minor, currency, reason,
             requested_by, policy.required_approvals, policy.separation_of_duties,
             sorted(policy.required_permissions), expires),
        ).fetchone()
    except errors.ForeignKeyViolation:
        raise NotFound("requester_not_found") from None
    except errors.CheckViolation:
        raise InvalidRequest("bad_approval_request") from None
    assert row is not None
    request_id = str(row[0])
    _append_audit(conn, tenant_id, category="access", action="approval.requested",
                  outcome="recorded", correlation_id=correlation_id,
                  actor_identity_id=requested_by, resource_type="approval_request",
                  resource_id=request_id,
                  detail={"action": action, "amount_minor": amount_minor,
                          "required_approvals": policy.required_approvals})
    return request_id, expires


def decide_approval(
    pool: Pool, tenant_id: str, *, request_id: str, decided_by: str, decision: str,
    correlation_id: str, reason: str | None = None,
) -> dict[str, Any]:
    """DecideApproval (IAM-03-R05), with separation of duties enforced here and in the schema."""
    _require_uuid(correlation_id, "correlation_id")
    if decision not in ("approved", "rejected"):
        raise InvalidRequest("bad_decision")
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _decide_in_tx(conn, tenant_id, request_id=request_id, decided_by=decided_by,
                                decision=decision, reason=reason,
                                correlation_id=correlation_id)
    return _settled(outcome)


def _decide_in_tx(
    conn: Connection[Any], tenant_id: str, *, request_id: str, decided_by: str, decision: str,
    reason: str | None, correlation_id: str,
) -> tuple[dict[str, Any], ServiceError | None]:
    now = _now()
    row = conn.execute(
        "SELECT action, requested_by, required_approvals, separation_of_duties, state,"
        " expires_at, required_permissions FROM iam.approval_requests"
        " WHERE request_id = %s FOR UPDATE",
        (request_id,),
    ).fetchone()
    if row is None:
        raise NotFound("approval_request_not_found")
    action, requested_by, required, sod, state, expires_at, required_permissions = (
        row[0], str(row[1]), int(row[2]), bool(row[3]), row[4], row[5], frozenset(row[6]),
    )
    if state != "pending":
        raise Conflict("approval_already_decided")

    # **The request's own snapshot governs, not today's policies.** Re-deriving the terms at
    # decision time let anybody holding `authz.policy.write` turn separation of duties off for a
    # request already in flight and then approve their own.
    effective = approvals.ApprovalPolicy(
        action=action, required_permissions=required_permissions,
        required_approvals=required, separation_of_duties=sod,
    )
    granted = authz.permissions_of(_load_assignments(conn, decided_by), now=now)
    try:
        approvals.check_decider(effective, requested_by=requested_by, decided_by=decided_by,
                                decider_permissions=granted)
    except approvals.ApprovalError as exc:
        _append_audit(conn, tenant_id, category="access", action="approval.denied",
                      outcome="denied", correlation_id=correlation_id,
                      actor_identity_id=decided_by, resource_type="approval_request",
                      resource_id=request_id, detail={"reason": exc.code})
        # Returned, not raised: repeated attempts to approve one's own request are exactly what
        # this log exists for, and raising here erased every one of them. See `_settled`.
        return {}, Forbidden(exc.code)

    try:
        conn.execute(
            "INSERT INTO iam.approval_decisions"
            " (tenant_id, request_id, decided_by, decision, reason)"
            " VALUES (%s, %s, %s, %s, %s)",
            (tenant_id, request_id, decided_by, decision, reason),
        )
    except errors.UniqueViolation:
        raise Conflict("already_decided_by_you") from None
    except errors.ForeignKeyViolation:
        raise NotFound("decider_not_found") from None

    recorded = [
        approvals.Decision(decided_by=str(r[0]), decision=r[1])
        for r in conn.execute(
            "SELECT decided_by, decision FROM iam.approval_decisions WHERE request_id = %s",
            (request_id,),
        ).fetchall()
    ]
    resolved = approvals.resolve(required_approvals=required, decisions=recorded,
                                 expires_at=expires_at, now=now)
    if resolved != "pending":
        conn.execute(
            "UPDATE iam.approval_requests SET state = %s, decided_at = %s WHERE request_id = %s",
            (resolved, now, request_id),
        )
    approved = len({d.decided_by for d in recorded if d.decision == "approved"})
    _append_audit(conn, tenant_id, category="access",
                  action="approval.completed" if resolved != "pending" else "approval.decided",
                  outcome="recorded", correlation_id=correlation_id,
                  actor_identity_id=decided_by, resource_type="approval_request",
                  resource_id=request_id,
                  detail={"decision": decision, "state": resolved, "approvals": approved})
    return ({"request_id": request_id, "decision": decision, "state": resolved,
             "approvals": approved, "required_approvals": required}, None)


def list_approval_requests(
    pool: Pool, tenant_id: str, *, state: str | None = None
) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT request_id, action, resource_type, resource_id, amount_minor, currency,"
            " requested_by, required_approvals, state, expires_at, created_at"
            " FROM iam.approval_requests WHERE (%s::text IS NULL OR state = %s::text)"
            " ORDER BY created_at DESC",
            (state, state),
        ).fetchall()
    return [
        {"request_id": str(r[0]), "action": r[1], "resource_type": r[2], "resource_id": r[3],
         "amount_minor": int(r[4]) if r[4] is not None else None, "currency": r[5],
         "requested_by": str(r[6]), "required_approvals": int(r[7]), "state": r[8],
         "expires_at": r[9].isoformat(), "created_at": r[10].isoformat()} for r in rows
    ]


# --------------------------------------------------------------------------- access review

def open_access_review(
    pool: Pool, tenant_id: str, *, title: str, opened_by: str, correlation_id: str
) -> dict[str, Any]:
    """Open a review over every live assignment (IAM-03-R07).

    The items are snapshotted when the review opens, so a reviewer certifies what was granted at
    a point in time rather than a list that moves while they read it.
    """
    _require_uuid(correlation_id, "correlation_id")
    if not title.strip():
        raise InvalidRequest("bad_title")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "INSERT INTO iam.access_reviews (tenant_id, title, opened_by)"
                " VALUES (%s, %s, %s) RETURNING review_id",
                (tenant_id, title, opened_by),
            ).fetchone()
        except errors.ForeignKeyViolation:
            raise NotFound("opener_not_found") from None
        assert row is not None
        review_id = str(row[0])
        items = conn.execute(
            "INSERT INTO iam.access_review_items (tenant_id, review_id, assignment_id)"
            " SELECT tenant_id, %s, assignment_id FROM iam.role_assignments"
            " WHERE revoked_at IS NULL RETURNING item_id",
            (review_id,),
        ).fetchall()
        _append_audit(conn, tenant_id, category="access", action="access_review.opened",
                      outcome="recorded", correlation_id=correlation_id,
                      actor_identity_id=opened_by, resource_type="access_review",
                      resource_id=review_id, detail={"title": title, "items": len(items)})
    return {"review_id": review_id, "title": title, "state": "open", "items": len(items)}


def decide_review_item(
    pool: Pool, tenant_id: str, *, item_id: str, decision: str, decided_by: str,
    correlation_id: str, note: str | None = None,
) -> dict[str, Any]:
    """Keep or revoke one assignment. Revoking here revokes the assignment itself."""
    _require_uuid(correlation_id, "correlation_id")
    if decision not in ("kept", "revoked"):
        raise InvalidRequest("bad_review_decision")
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "UPDATE iam.access_review_items SET decision = %s, decided_by = %s, decided_at = %s,"
            " note = %s WHERE item_id = %s AND decision = 'pending'"
            " RETURNING assignment_id",
            (decision, decided_by, now, note, item_id),
        ).fetchone()
        if row is None:
            raise NotFound("review_item_not_found_or_decided")
        assignment_id = str(row[0])
        if decision == "revoked":
            conn.execute(
                "UPDATE iam.role_assignments SET revoked_at = %s,"
                " revoked_reason = 'access_review' WHERE assignment_id = %s"
                " AND revoked_at IS NULL",
                (now, assignment_id),
            )
        _append_audit(conn, tenant_id, category="access", action="access_review.item_decided",
                      outcome="recorded", correlation_id=correlation_id,
                      actor_identity_id=decided_by, resource_type="assignment",
                      resource_id=assignment_id, detail={"decision": decision})
    return {"item_id": item_id, "assignment_id": assignment_id, "decision": decision}


def complete_access_review(
    pool: Pool, tenant_id: str, *, review_id: str, correlation_id: str,
    actor_identity_id: str | None = None,
) -> dict[str, Any]:
    """Close a review, refusing while anything in it is still undecided."""
    _require_uuid(correlation_id, "correlation_id")
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        pending = conn.execute(
            "SELECT count(*) FROM iam.access_review_items"
            " WHERE review_id = %s AND decision = 'pending'",
            (review_id,),
        ).fetchone()
        assert pending is not None
        if int(pending[0]) > 0:
            raise Conflict("access_review_has_undecided_items")
        row = conn.execute(
            "UPDATE iam.access_reviews SET state = 'completed', closed_at = %s"
            " WHERE review_id = %s AND state = 'open' RETURNING title",
            (now, review_id),
        ).fetchone()
        if row is None:
            raise NotFound("access_review_not_found_or_closed")
        _append_audit(conn, tenant_id, category="access", action="access_review.completed",
                      outcome="recorded", correlation_id=correlation_id,
                      actor_identity_id=actor_identity_id, resource_type="access_review",
                      resource_id=review_id, detail={"title": row[0]})
    return {"review_id": review_id, "state": "completed"}

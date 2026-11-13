"""MOD-004 PLT-01 tenancy service: tenant lifecycle and the organization hierarchy.

The lifecycle decision is **not** made here. ``app.tenancy.domain.lifecycle.apply_command`` owns
it, and this module persists whatever that function admits, so there is exactly one transition
table in the codebase. Two consequences of that table are worth knowing before reading the code:

* There is no ``SUSPENDED -> ACTIVE`` edge, so a suspended tenant cannot be reactivated here.
  TSD section 10.3 puts reactivation in PLT-03, which is another module's work; inventing the
  edge in this one would put a second, disagreeing lifecycle in the product.
* There is no deletion state at all. PLT-01-R07 bars hard deletion before legal, billing and
  retention gates pass, and the modules owning those gates do not exist. ``delete_tenant``
  therefore refuses, and refusing is the implemented behaviour rather than a stub.

Every hierarchy function takes a tenant pool and runs inside ``tenant_scope``, so row-level
security is in force for all of them. None of them filters by ``tenant_id`` in its own SQL --
that is deliberate. The database filters, and a missing WHERE clause in this file therefore
returns nothing rather than returning another tenant's rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import Connection, errors
from psycopg_pool import ConnectionPool

from app.db import platform_scope, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound, ServiceError
from app.tenancy.domain.lifecycle import (
    ACTIVATE,
    ARCHIVE,
    NO_TENANT,
    PROVISION,
    SUSPEND,
    LifecycleError,
    apply_command,
)
from app.tenancy_s0 import EnvelopeError, validate_provision_tenant

# Both planes hand out the same connection type; the plane is decided by the pool's role.
Pool = ConnectionPool[Connection[Any]]

COMMAND_FOR_ACTION = {"activate": ACTIVATE, "suspend": SUSPEND, "archive": ARCHIVE}


# Re-exported from `app.errors`, which MOD-005's service shares. Importing them from here still
# works, so the HTTP handler and the existing tests are unaffected.
__all__ = ["Conflict", "DeletionGated", "InvalidRequest", "NotFound", "ServiceError"]


class DeletionGated(ServiceError):
    """PLT-01-R07: hard deletion is barred until the legal, billing and retention gates exist."""

    status = 409


@dataclass(frozen=True, slots=True)
class Tenant:
    tenant_id: str
    external_key: str
    display_name: str
    status: str
    region: str
    version: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "external_key": self.external_key,
            "display_name": self.display_name,
            "status": self.status,
            "region": self.region,
            "version": self.version,
        }


def _tenant_from_row(row: tuple[Any, ...]) -> Tenant:
    return Tenant(
        tenant_id=str(row[0]),
        external_key=row[1],
        display_name=row[2],
        status=row[3],
        region=row[4],
        version=row[5],
    )


_SELECT_TENANT = """
    SELECT tenant_id, external_key, display_name, status, region, version
    FROM plt01_platform.tenants
"""


# --------------------------------------------------------------------------- lifecycle


def provision_tenant(
    pool: Pool, envelope: dict[str, Any], display_name: str, region: str
) -> tuple[Tenant, bool]:
    """Provision a tenant. Returns the tenant and whether this call created it.

    Idempotent on ``idempotency_key``: a replay returns the tenant the first call produced,
    without writing a second lifecycle row. A different key for an ``external_key`` that already
    exists is a conflict, not a second tenant -- the registry's unique constraint is what decides
    that, so two concurrent callers cannot both win.
    """
    try:
        valid = validate_provision_tenant(envelope)
    except EnvelopeError as exc:
        raise InvalidRequest(exc.code) from None
    if not display_name.strip():
        raise InvalidRequest("bad_display_name")
    if not region.strip():
        raise InvalidRequest("bad_region")

    # Admissibility is the domain's call even for the first transition, so that provisioning is
    # not the one lifecycle edge decided somewhere else.
    try:
        transition = apply_command(PROVISION, NO_TENANT)
    except LifecycleError as exc:  # pragma: no cover - PROVISION from NO_TENANT is admitted
        raise InvalidRequest(exc.code) from None

    with platform_scope(pool) as conn:
        replay = conn.execute(
            "SELECT tenant_id FROM plt01_platform.command_idempotency WHERE idempotency_key = %s",
            (valid.idempotency_key,),
        ).fetchone()
        if replay is not None:
            row = conn.execute(_SELECT_TENANT + " WHERE tenant_id = %s", (replay[0],)).fetchone()
            if row is None:  # pragma: no cover - foreign key makes this unreachable
                raise NotFound("tenant_missing")
            return _tenant_from_row(row), False

        tenant_id = str(uuid.uuid4())
        try:
            row = conn.execute(
                """
                INSERT INTO plt01_platform.tenants
                    (tenant_id, external_key, display_name, status, region)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id, external_key, display_name, status, region, version
                """,
                (tenant_id, valid.external_key, display_name, transition.to_state, region),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("external_key_exists") from None
        assert row is not None

        conn.execute(
            """
            INSERT INTO plt01_platform.tenant_lifecycle_history
                (tenant_id, from_status, to_status, command, actor_id, correlation_id)
            VALUES (%s, NULL, %s, %s, %s, %s)
            """,
            (tenant_id, transition.to_state, transition.command, valid.actor_id,
             valid.correlation_id),
        )
        conn.execute(
            """
            INSERT INTO plt01_platform.command_idempotency
                (idempotency_key, command, tenant_id, result_version)
            VALUES (%s, %s, %s, %s)
            """,
            (valid.idempotency_key, transition.command, tenant_id, row[5]),
        )
        return _tenant_from_row(row), True


def transition_tenant(
    pool: Pool,
    tenant_id: str,
    action: str,
    actor_id: str,
    correlation_id: str,
    expected_version: int | None = None,
) -> Tenant:
    """Move a tenant along the lifecycle. ``action`` is activate, suspend or archive."""
    command = COMMAND_FOR_ACTION.get(action)
    if command is None:
        raise InvalidRequest("unknown_action")

    with platform_scope(pool) as conn:
        # FOR UPDATE: the read of the current state and the write of the next one must not
        # interleave with a concurrent transition, or two commands could both see `active`.
        row = conn.execute(_SELECT_TENANT + " WHERE tenant_id = %s FOR UPDATE",
                           (tenant_id,)).fetchone()
        if row is None:
            raise NotFound("tenant_not_found")
        current = _tenant_from_row(row)

        if expected_version is not None and expected_version != current.version:
            raise Conflict("version_mismatch")

        try:
            transition = apply_command(command, current.status)
        except LifecycleError as exc:
            raise Conflict(exc.code) from None

        updated = conn.execute(
            """
            UPDATE plt01_platform.tenants
            SET status = %s, version = version + 1, updated_at = now()
            WHERE tenant_id = %s
            RETURNING tenant_id, external_key, display_name, status, region, version
            """,
            (transition.to_state, tenant_id),
        ).fetchone()
        assert updated is not None

        conn.execute(
            """
            INSERT INTO plt01_platform.tenant_lifecycle_history
                (tenant_id, from_status, to_status, command, actor_id, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (tenant_id, current.status, transition.to_state, transition.command, actor_id,
             correlation_id),
        )
        return _tenant_from_row(updated)


def get_tenant(pool: Pool, tenant_id: str) -> Tenant:
    with platform_scope(pool) as conn:
        row = conn.execute(_SELECT_TENANT + " WHERE tenant_id = %s", (tenant_id,)).fetchone()
    if row is None:
        raise NotFound("tenant_not_found")
    return _tenant_from_row(row)


def tenant_history(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with platform_scope(pool) as conn:
        rows = conn.execute(
            """
            SELECT from_status, to_status, command, occurred_at
            FROM plt01_platform.tenant_lifecycle_history
            WHERE tenant_id = %s ORDER BY event_id
            """,
            (tenant_id,),
        ).fetchall()
    return [
        {"from_status": r[0], "to_status": r[1], "command": r[2], "occurred_at": r[3].isoformat()}
        for r in rows
    ]


def delete_tenant(pool: Pool, tenant_id: str) -> None:
    """Always refuses. PLT-01-R07 bars hard deletion before the gates pass, and they do not exist.

    This is the implemented requirement, not an unfinished one: the tenant is confirmed to exist
    first, so a caller learns that deletion is gated rather than that the tenant is missing.
    """
    get_tenant(pool, tenant_id)
    raise DeletionGated("hard_deletion_gated")


# --------------------------------------------------------------------------- hierarchy


def create_organization(
    pool: Pool, tenant_id: str, legal_name: str, country_code: str
) -> dict[str, Any]:
    if not legal_name.strip():
        raise InvalidRequest("bad_legal_name")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.organizations (tenant_id, legal_name, country_code)
                VALUES (%s, %s, %s)
                RETURNING organization_id, legal_name, country_code
                """,
                (tenant_id, legal_name, country_code),
            ).fetchone()
        except errors.CheckViolation:
            raise InvalidRequest("bad_country_code") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tenant_not_found") from None
        assert row is not None
    return {"organization_id": str(row[0]), "legal_name": row[1], "country_code": row[2]}


def list_organizations(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT organization_id, legal_name, country_code FROM plt01.organizations"
            " ORDER BY created_at"
        ).fetchall()
    return [
        {"organization_id": str(r[0]), "legal_name": r[1], "country_code": r[2]} for r in rows
    ]


def create_brand(
    pool: Pool, tenant_id: str, organization_id: str, brand_name: str
) -> dict[str, Any]:
    if not brand_name.strip():
        raise InvalidRequest("bad_brand_name")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.brands (tenant_id, organization_id, brand_name)
                VALUES (%s, %s, %s)
                RETURNING brand_id, organization_id, brand_name
                """,
                (tenant_id, organization_id, brand_name),
            ).fetchone()
        except errors.ForeignKeyViolation:
            # The composite key carries tenant_id, so this also fires when the organization
            # belongs to another tenant -- which is the same answer as "does not exist".
            raise NotFound("organization_not_found") from None
        except errors.UniqueViolation:
            raise Conflict("brand_name_exists") from None
        assert row is not None
    return {"brand_id": str(row[0]), "organization_id": str(row[1]), "brand_name": row[2]}


def create_location(
    pool: Pool,
    tenant_id: str,
    brand_id: str,
    location_name: str,
    timezone: str,
) -> dict[str, Any]:
    if not location_name.strip():
        raise InvalidRequest("bad_location_name")
    if not timezone.strip():
        raise InvalidRequest("bad_timezone")
    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.locations (tenant_id, brand_id, location_name, timezone)
                VALUES (%s, %s, %s, %s)
                RETURNING location_id, brand_id, location_name, timezone
                """,
                (tenant_id, brand_id, location_name, timezone),
            ).fetchone()
        except errors.ForeignKeyViolation:
            raise NotFound("brand_not_found") from None
        assert row is not None
    return {
        "location_id": str(row[0]),
        "brand_id": str(row[1]),
        "location_name": row[2],
        "timezone": row[3],
    }


def list_locations(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT location_id, brand_id, location_name, timezone FROM plt01.locations"
            " ORDER BY created_at"
        ).fetchall()
    return [
        {
            "location_id": str(r[0]),
            "brand_id": str(r[1]),
            "location_name": r[2],
            "timezone": r[3],
        }
        for r in rows
    ]

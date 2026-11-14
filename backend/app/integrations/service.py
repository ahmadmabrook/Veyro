"""MOD-012 ECO-02 service: the definition catalogue, installs, connections and connector runs.

The decisions live in `app.integrations.contract`, `lifecycle` and `sync`. This module reads
rows, calls those, and writes what they return.

**It spans two planes and is not atomic across them**, the same shape `billing.start_subscription`
has. The definition catalogue is in `plt01_platform` under `veyro_cp_platform`; the install is in
`plt01` under `veyro_cp_app`; neither role can reach the other's schema and neither is a member
of the other, so a single transaction covering both is impossible by construction. What makes it
safe is the snapshot: the install carries what the definition said, so a failure after the read
and before the write leaves nothing half-done, and a success stays answerable without ever
joining across the planes again.

**What this module cannot do, stated here rather than discovered later.**

* **It cannot hold a credential.** `int_credential_refs` has no column a secret could go in --
  only a reference to one kept somewhere this build cannot read. There is no vault here, so every
  reference today points outside the repository, and `rotate_credential` records that a rotation
  happened rather than performing one.
* **Nothing syncs.** There is no provider, no outbound HTTP and no adapter code. `start_run`,
  `finish_run` and `fail_run` are written by whatever does the work; a module that wrote "synced
  40 records" with nothing having answered would be the fabricated-evidence shape this codebase
  has been bitten by three times now.
* **No inbound webhook receiver.** Receiving a provider callback means verifying its signature,
  which means holding the provider's signing secret -- the vault again. An endpoint that accepted
  unverified callbacks would be a forgery primitive, which is strictly worse than not having one.
* **No marketplace, no partner accounts, no listings or certification.** That is ECO-02's V2
  slice; this is the Foundation adapter core the EIP asks for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from app.db import Pool, platform_scope, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events
from app.integrations import contract, lifecycle, sync


def _now() -> datetime:
    return datetime.now(UTC)


def _check_name(exc: errors.CheckViolation) -> str:
    return getattr(exc.diag, "constraint_name", None) or "constraint_violated"


# ------------------------------------------------------------------ the definition catalogue

def register_definition(
    platform_pool: Pool, *, definition_key: str, version: int, provider: str,
    display_name: str, criticality: str, support_owner: str, description: str,
    capabilities: list[str], scopes: list[str], required_scopes: list[str],
    config_fields: list[dict[str, Any]] | None = None, regions: list[str] | None = None,
) -> dict[str, Any]:
    """Register a draft definition version. Nothing may install against a draft."""
    fields = tuple(
        contract.ConfigField(
            name=str(f["name"]), field_type=str(f["field_type"]),
            required=bool(f.get("required", False)),
            values=tuple(f.get("values", ())), description=str(f.get("description", "")),
        )
        for f in (config_fields or [])
    )
    candidate = contract.DefinitionVersion(
        definition_key=definition_key, version=version, capabilities=tuple(capabilities),
        scopes=tuple(scopes), required_scopes=tuple(required_scopes), config_fields=fields,
        regions=tuple(regions or ()),
    )
    try:
        contract.check_version(candidate)
    except contract.ContractError as e:
        raise InvalidRequest(str(e)) from None
    with platform_scope(platform_pool) as conn:
        # Succession is checked here rather than at publication, because a draft that cannot
        # legally succeed its predecessor is one somebody will finish writing before finding
        # out. The comparison is against the newest version, published or not.
        previous = _newest_version(conn, definition_key)
        if previous is not None:
            if version <= previous.version:
                raise Conflict("a_version_must_be_higher_than_the_last")
            try:
                contract.check_succession(previous, candidate)
            except contract.ContractError as e:
                raise InvalidRequest(str(e)) from None
        try:
            conn.execute(
                """
                INSERT INTO plt01_platform.int_definitions
                    (definition_key, version, provider, display_name, criticality,
                     support_owner, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (definition_key, version, provider, display_name, criticality, support_owner,
                 description),
            )
        except errors.UniqueViolation:
            raise Conflict("definition_version_already_exists") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.DataError:
            raise InvalidRequest("a_definition_field_is_out_of_range") from None
        rows: list[tuple[Any, ...]] = [
            (definition_key, version, "capability", name, False, None, None)
            for name in capabilities
        ] + [
            (definition_key, version, "scope", name, name in set(required_scopes), None, None)
            for name in scopes
        ] + [
            (definition_key, version, "region", name, False, None, None)
            for name in (regions or [])
        ] + [
            (definition_key, version, "config", f.name, f.required, f.field_type,
             list(f.values) or None)
            for f in fields
        ]
        for row in rows:
            # The entries insert gets the same handling as the head insert above. Without it a
            # duplicate region or a blank name -- neither of which `check_version` looked at --
            # reached the caller as a 500 on the platform plane.
            try:
                conn.execute(
                    "INSERT INTO plt01_platform.int_definition_versions"
                    " (definition_key, version, kind, name, required, field_type,"
                    "  enum_values)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    row,
                )
            except errors.UniqueViolation:
                raise Conflict("a_definition_declares_one_entry_twice") from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
    return {"definition_key": definition_key, "version": version, "status": "draft",
            "provider": provider, "criticality": criticality}


def publish_definition(
    platform_pool: Pool, *, definition_key: str, version: int,
) -> dict[str, Any]:
    """Make a version installable. Immutable from here: the grants are what enforce that."""
    with platform_scope(platform_pool) as conn:
        row = conn.execute(
            "UPDATE plt01_platform.int_definitions SET status = 'published',"
            " published_at = now()"
            " WHERE definition_key = %s AND version = %s AND status = 'draft'"
            " RETURNING published_at",
            (definition_key, version),
        ).fetchone()
        if row is None:
            raise NotFound("draft_definition_version_not_found")
    return {"definition_key": definition_key, "version": version, "status": "published",
            "published_at": row[0].isoformat()}


def retire_definition(
    platform_pool: Pool, *, definition_key: str, version: int,
) -> dict[str, Any]:
    """Stop new installs. Installs already made keep their snapshot and keep working."""
    with platform_scope(platform_pool) as conn:
        row = conn.execute(
            "UPDATE plt01_platform.int_definitions SET status = 'retired', retired_at = now()"
            " WHERE definition_key = %s AND version = %s AND status = 'published'"
            " RETURNING retired_at",
            (definition_key, version),
        ).fetchone()
        if row is None:
            raise NotFound("published_definition_version_not_found")
    return {"definition_key": definition_key, "version": version, "status": "retired",
            "retired_at": row[0].isoformat()}


def list_definitions(platform_pool: Pool, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT definition_key, version, provider, display_name, status, criticality,"
           " support_owner, description FROM plt01_platform.int_definitions")
    args: tuple[Any, ...] = ()
    if status is not None:
        sql += " WHERE status = %s"
        args = (status,)
    sql += " ORDER BY definition_key, version"
    with platform_scope(platform_pool) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [{"definition_key": r[0], "version": int(r[1]), "provider": r[2],
             "display_name": r[3], "status": r[4], "criticality": r[5], "support_owner": r[6],
             "description": r[7]} for r in rows]


def get_definition(
    platform_pool: Pool, *, definition_key: str, version: int | None = None,
) -> dict[str, Any]:
    with platform_scope(platform_pool) as conn:
        return _definition(conn, definition_key, version)


def _entries(
    conn: Connection[Any], definition_key: str, version: int,
) -> list[tuple[Any, ...]]:
    return conn.execute(
        "SELECT kind, name, required, field_type, enum_values"
        " FROM plt01_platform.int_definition_versions"
        " WHERE definition_key = %s AND version = %s ORDER BY kind, name",
        (definition_key, version),
    ).fetchall()


def _version_from(
    definition_key: str, version: int, entries: list[tuple[Any, ...]],
) -> contract.DefinitionVersion:
    return contract.DefinitionVersion(
        definition_key=definition_key, version=version,
        capabilities=tuple(e[1] for e in entries if e[0] == "capability"),
        scopes=tuple(e[1] for e in entries if e[0] == "scope"),
        required_scopes=tuple(e[1] for e in entries if e[0] == "scope" and e[2]),
        config_fields=tuple(
            contract.ConfigField(name=e[1], field_type=e[3], required=e[2],
                                 values=tuple(e[4] or ()))
            for e in entries if e[0] == "config"
        ),
        regions=tuple(e[1] for e in entries if e[0] == "region"),
    )


def _newest_version(
    conn: Connection[Any], definition_key: str,
) -> contract.DefinitionVersion | None:
    row = conn.execute(
        "SELECT version FROM plt01_platform.int_definitions"
        " WHERE definition_key = %s ORDER BY version DESC LIMIT 1",
        (definition_key,),
    ).fetchone()
    if row is None:
        return None
    version = int(row[0])
    return _version_from(definition_key, version, _entries(conn, definition_key, version))


def _definition(
    conn: Connection[Any], definition_key: str, version: int | None,
) -> dict[str, Any]:
    if version is None:
        row = conn.execute(
            "SELECT version FROM plt01_platform.int_definitions"
            " WHERE definition_key = %s AND status = 'published'"
            " ORDER BY version DESC LIMIT 1",
            (definition_key,),
        ).fetchone()
        if row is None:
            raise NotFound("no_published_definition_version")
        version = int(row[0])
    head = conn.execute(
        "SELECT provider, display_name, status, criticality, support_owner, description"
        " FROM plt01_platform.int_definitions WHERE definition_key = %s AND version = %s",
        (definition_key, version),
    ).fetchone()
    if head is None:
        raise NotFound("definition_version_not_found")
    entries = _entries(conn, definition_key, version)
    declared = _version_from(definition_key, version, entries)
    return {
        "definition_key": definition_key, "version": version, "provider": head[0],
        "display_name": head[1], "status": head[2], "criticality": head[3],
        "support_owner": head[4], "description": head[5],
        "capabilities": list(declared.capabilities), "scopes": list(declared.scopes),
        "required_scopes": list(declared.required_scopes),
        "regions": list(declared.regions),
        "config_fields": [
            {"name": f.name, "field_type": f.field_type, "required": f.required,
             "values": list(f.values)} for f in declared.config_fields
        ],
        "_declared": declared,
    }


# ------------------------------------------------------------------------------- installs

def install_integration(
    tenant_pool: Pool, platform_pool: Pool, tenant_id: str, *, definition_key: str,
    actor_id: str, correlation_id: str, version: int | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """InstallIntegration. Reads the catalogue, then snapshots it into the tenant plane.

    A draft or retired version cannot be installed: a draft is not a contract anybody has
    committed to, and a retired one is a contract whose publisher has said it is ending. An
    install already on a retired version keeps working, which is the point of the snapshot.
    """
    with platform_scope(platform_pool) as conn:
        definition = _definition(conn, definition_key, version)
    if definition["status"] != "published":
        raise Conflict("definition_version_not_published")
    declared: contract.DefinitionVersion = definition.pop("_declared")
    supplied = config or {}
    try:
        contract.check_config(declared, supplied)
    except contract.ContractError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(tenant_pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.int_installs
                    (tenant_id, definition_key, definition_version, definition_snapshot,
                     criticality, config, installed_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING install_id, installed_at
                """,
                (tenant_id, definition_key, definition["version"], Jsonb(definition),
                 definition["criticality"], Jsonb(supplied), actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_definition_is_already_installed") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        events.append_event(
            conn, tenant_id, event_type="integration.installed",
            aggregate_type="integration_install", aggregate_id=str(row[0]),
            payload={"install_id": str(row[0]), "definition_key": definition_key,
                     "definition_version": definition["version"],
                     "criticality": definition["criticality"]},
            correlation_id=correlation_id, actor_id=actor_id,
        )
    return {"install_id": str(row[0]), "definition_key": definition_key,
            "definition_version": definition["version"],
            "criticality": definition["criticality"], "state": "installed",
            "config": supplied, "installed_at": row[1].isoformat()}


def configure_install(
    tenant_pool: Pool, tenant_id: str, install_id: str, *, actor_id: str, correlation_id: str,
    config: dict[str, Any] | None = None, fallback_plan: str | None = None,
    reconciliation_plan: str | None = None, exit_plan: str | None = None,
) -> dict[str, Any]:
    """Configure, and write the obligations a critical integration needs before activation.

    The configuration is re-validated against **the snapshot**, not against today's catalogue:
    an install lives on the version it was made against, so validating against a newer one
    would refuse a value that is correct for this install, or accept one that is not.
    """
    with tenant_scope(tenant_pool, tenant_id) as conn:
        current = _install(conn, install_id)
        if current["state"] == "uninstalled":
            raise Conflict("install_is_uninstalled")
        # A blank plan is not a plan. `coalesce` replaces NULL and not `''`, so sending three
        # empty strings erased the fallback, the reconciliation procedure and the exit plan
        # from a **live critical** install -- the three things paragraph 3033 requires in
        # writing before it may carry traffic -- with the same permission that wrote them and
        # no refusal anywhere. "A control consulted once is a control with a window", which is
        # MOD-009's legal-hold finding in this module's clothes.
        for name, plan in (("fallback_plan", fallback_plan),
                           ("reconciliation_plan", reconciliation_plan),
                           ("exit_plan", exit_plan)):
            if plan is not None and not plan.strip():
                raise InvalidRequest(f"{name}_cannot_be_blank")
        merged = dict(current["config"])
        if config is not None:
            merged.update(config)
            declared = _declared_from_snapshot(current["definition_snapshot"])
            try:
                contract.check_config(declared, merged)
            except contract.ContractError as e:
                raise InvalidRequest(str(e)) from None
        conn.execute(
            "UPDATE plt01.int_installs SET config = %s,"
            " fallback_plan = coalesce(%s, fallback_plan),"
            " reconciliation_plan = coalesce(%s, reconciliation_plan),"
            " exit_plan = coalesce(%s, exit_plan)"
            " WHERE install_id = %s",
            (Jsonb(merged), fallback_plan, reconciliation_plan, exit_plan, install_id),
        )
    return {"install_id": install_id, "config": merged}


def _declared_from_snapshot(snapshot: dict[str, Any]) -> contract.DefinitionVersion:
    """Rebuild the contract from what the install stored, rather than from the catalogue."""
    return contract.DefinitionVersion(
        definition_key=snapshot["definition_key"], version=int(snapshot["version"]),
        capabilities=tuple(snapshot.get("capabilities", ())),
        scopes=tuple(snapshot.get("scopes", ())),
        required_scopes=tuple(snapshot.get("required_scopes", ())),
        config_fields=tuple(
            contract.ConfigField(name=f["name"], field_type=f["field_type"],
                                 required=bool(f.get("required")),
                                 values=tuple(f.get("values", ())))
            for f in snapshot.get("config_fields", [])
        ),
        regions=tuple(snapshot.get("regions", ())),
    )


def _install(conn: Connection[Any], install_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT install_id, definition_key, definition_version, definition_snapshot,"
        " criticality, config, state, fallback_plan, reconciliation_plan, exit_plan,"
        " installed_at, activated_at, disabled_at, uninstalled_at"
        " FROM plt01.int_installs WHERE install_id = %s",
        (install_id,),
    ).fetchone()
    if row is None:
        raise NotFound("install_not_found")
    return {"install_id": str(row[0]), "definition_key": row[1],
            "definition_version": int(row[2]), "definition_snapshot": row[3],
            "criticality": row[4], "config": row[5], "state": row[6],
            "fallback_plan": row[7], "reconciliation_plan": row[8], "exit_plan": row[9],
            "installed_at": row[10], "activated_at": row[11], "disabled_at": row[12],
            "uninstalled_at": row[13]}


def activate_install(
    tenant_pool: Pool, tenant_id: str, install_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Paragraph 3033's gate. A critical integration needs its three obligations in writing."""
    with tenant_scope(tenant_pool, tenant_id) as conn:
        current = _install(conn, install_id)
        try:
            lifecycle.check_install_transition(current["state"], "active")
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        validated = conn.execute(
            "SELECT count(*) FROM plt01.int_connections"
            " WHERE install_id = %s AND state = 'validated'",
            (install_id,),
        ).fetchone()
        assert validated is not None
        try:
            lifecycle.check_activation(lifecycle.ActivationCheck(
                criticality=current["criticality"],
                has_fallback=bool((current["fallback_plan"] or "").strip()),
                has_reconciliation=bool((current["reconciliation_plan"] or "").strip()),
                has_exit_plan=bool((current["exit_plan"] or "").strip()),
                validated_connections=int(validated[0]),
            ))
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        conn.execute(
            "UPDATE plt01.int_installs SET state = 'active', activated_at = now(),"
            " disabled_at = NULL WHERE install_id = %s",
            (install_id,),
        )
    return {"install_id": install_id, "state": "active"}


def disable_install(
    tenant_pool: Pool, tenant_id: str, install_id: str, *, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    with tenant_scope(tenant_pool, tenant_id) as conn:
        current = _install(conn, install_id)
        try:
            lifecycle.check_install_transition(current["state"], "disabled")
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        conn.execute(
            "UPDATE plt01.int_installs SET state = 'disabled', disabled_at = now()"
            " WHERE install_id = %s",
            (install_id,),
        )
    return {"install_id": install_id, "state": "disabled"}


def uninstall_integration(
    tenant_pool: Pool, tenant_id: str, install_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """UninstallIntegration. **Revokes every live connection in the same transaction.**

    An uninstall that left a connection authorized would be a tenant believing a third party no
    longer has access while it does, which is the worst failure available to this module. The
    rows stay -- revoked and attributed -- because the question afterwards is always what the
    provider could reach and until when.
    """
    if not reason.strip():
        raise InvalidRequest("an_uninstall_states_a_reason")
    with tenant_scope(tenant_pool, tenant_id) as conn:
        current = _install(conn, install_id)
        try:
            lifecycle.check_install_transition(current["state"], "uninstalled")
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        revoked = conn.execute(
            "UPDATE plt01.int_connections SET state = 'revoked', revoked_at = now(),"
            " revoked_by = %s, revoke_reason = %s"
            " WHERE install_id = %s AND revoked_at IS NULL",
            (actor_id, f"integration uninstalled: {reason}"[:500], install_id),
        ).rowcount
        conn.execute(
            "UPDATE plt01.int_credential_refs SET retired_at = now()"
            " WHERE retired_at IS NULL AND connection_id IN ("
            "   SELECT connection_id FROM plt01.int_connections WHERE install_id = %s)",
            (install_id,),
        )
        conn.execute(
            "UPDATE plt01.int_installs SET state = 'uninstalled', uninstalled_at = now(),"
            " uninstalled_by = %s, uninstall_correlation_id = %s, uninstall_reason = %s"
            " WHERE install_id = %s",
            (actor_id, correlation_id, reason[:500], install_id),
        )
        events.append_event(
            conn, tenant_id, event_type="integration.uninstalled",
            aggregate_type="integration_install", aggregate_id=install_id,
            # Bounded, because `evt_outbox` has no DELETE grant for any runtime role: an
            # unbounded caller string in a payload is permanent.
            payload={"install_id": install_id, "definition_key": current["definition_key"],
                     "reason": reason[:500], "connections_revoked": revoked},
            correlation_id=correlation_id, actor_id=actor_id,
        )
    return {"install_id": install_id, "state": "uninstalled", "connections_revoked": revoked}


def list_installs(
    tenant_pool: Pool, tenant_id: str, *, include_uninstalled: bool = False,
) -> list[dict[str, Any]]:
    sql = ("SELECT install_id, definition_key, definition_version, criticality, state, config,"
           " fallback_plan, reconciliation_plan, exit_plan, installed_at, uninstalled_at"
           " FROM plt01.int_installs")
    if not include_uninstalled:
        sql += " WHERE uninstalled_at IS NULL"
    sql += " ORDER BY definition_key"
    with tenant_scope(tenant_pool, tenant_id) as conn:
        rows = conn.execute(sql).fetchall()
    return [{"install_id": str(r[0]), "definition_key": r[1], "definition_version": int(r[2]),
             "criticality": r[3], "state": r[4], "config": r[5],
             "has_fallback": bool((r[6] or "").strip()),
             "has_reconciliation": bool((r[7] or "").strip()),
             "has_exit_plan": bool((r[8] or "").strip()),
             "installed_at": r[9].isoformat(),
             "uninstalled_at": r[10].isoformat() if r[10] else None} for r in rows]


# ---------------------------------------------------------------------------- connections

def authorize_connection(
    tenant_pool: Pool, tenant_id: str, *, install_id: str, external_account_ref: str,
    region: str, granted_scopes: list[str], vault_ref: str, actor_id: str,
    correlation_id: str, issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """AuthorizeProvider. Creates the connection and its first credential reference together.

    A connection without a credential reference is one nothing can ever use, and a credential
    reference without a connection is a secret pointing at nothing -- so they are one
    transaction and one command.

    The granted scopes are checked **against the install's snapshot**, in both directions: a
    scope the definition never declared is either a typo or an escalation and neither should
    reach a provider, and the scopes the definition marks required have to be present or the
    install fails in the middle of its first sync rather than here.

    `vault_ref` names a secret kept somewhere this build cannot read. There is no column
    anywhere in this module a secret itself could go in, and check 52 asserts that.
    """
    if not vault_ref.strip():
        raise InvalidRequest("a_connection_names_where_its_credential_lives")
    with tenant_scope(tenant_pool, tenant_id) as conn:
        install = _install(conn, install_id)
        if install["state"] == "uninstalled":
            raise Conflict("install_is_uninstalled")
        declared = _declared_from_snapshot(install["definition_snapshot"])
        try:
            contract.check_grant(declared, granted_scopes)
            contract.check_region(declared, region)
        except contract.ContractError as e:
            raise InvalidRequest(str(e)) from None
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.int_connections
                    (tenant_id, install_id, external_account_ref, region, granted_scopes,
                     state, authorized_at, authorized_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, 'authorized', now(), %s, %s)
                RETURNING connection_id
                """,
                (tenant_id, install_id, external_account_ref, region, granted_scopes,
                 actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_account_is_already_connected") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert row is not None
        connection_id = str(row[0])
        try:
            credential = conn.execute(
                """
                INSERT INTO plt01.int_credential_refs
                    (tenant_id, connection_id, vault_ref, scopes, issued_at, expires_at,
                     recorded_by, correlation_id)
                VALUES (%s, %s, %s, %s, coalesce(%s, now()), %s, %s, %s)
                RETURNING credential_ref_id
                """,
                (tenant_id, connection_id, vault_ref, granted_scopes, issued_at, expires_at,
                 actor_id, correlation_id),
            ).fetchone()
        except errors.CheckViolation as e:
            # The connection insert above had this and the credential insert did not, so a
            # `vault_ref` that is not a locator -- which is the whole point of the constraint,
            # and the shape somebody pastes a live key into -- reached the caller as a 500.
            raise InvalidRequest(_check_name(e)) from None
        assert credential is not None
        events.append_event(
            conn, tenant_id, event_type="integration.connected",
            aggregate_type="integration_connection", aggregate_id=connection_id,
            payload={"install_id": install_id, "connection_id": connection_id,
                     "definition_key": install["definition_key"], "region": region,
                     "granted_scopes": sorted(granted_scopes)},
            correlation_id=correlation_id, actor_id=actor_id,
        )
    return {"connection_id": connection_id, "install_id": install_id, "state": "authorized",
            "region": region, "granted_scopes": sorted(granted_scopes),
            "credential_ref_id": str(credential[0])}


def validate_connection(
    tenant_pool: Pool, tenant_id: str, connection_id: str, *, evidence: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Record that somebody validated this connection, with what they saw.

    **This build validates nothing.** There is no provider to call, so the state means a named
    party recorded a successful check at a time and wrote down what it was. The evidence is
    required for that reason: a validation with nothing behind it is a state change anybody can
    assert for free, and activation depends on this state.
    """
    if not evidence.strip():
        raise InvalidRequest("a_validation_records_what_was_seen")
    with tenant_scope(tenant_pool, tenant_id) as conn:
        state = _connection_state(conn, connection_id)
        try:
            lifecycle.check_connection_transition(state, "validated")
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        conn.execute(
            "UPDATE plt01.int_connections SET state = 'validated', validated_at = now(),"
            " validated_by = %s, validation_evidence = %s WHERE connection_id = %s",
            (actor_id, evidence[:2000], connection_id),
        )
    return {"connection_id": connection_id, "state": "validated"}


def revoke_connection(
    tenant_pool: Pool, tenant_id: str, connection_id: str, *, reason: str, actor_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Revoke, and retire the credential reference with it.

    A revoked connection whose credential reference still reads as live is a secret somebody
    will not think to rotate, pointing at an account this tenant believes is disconnected.
    """
    if not reason.strip():
        raise InvalidRequest("a_revocation_states_a_reason")
    with tenant_scope(tenant_pool, tenant_id) as conn:
        state = _connection_state(conn, connection_id)
        try:
            lifecycle.check_connection_transition(state, "revoked")
        except lifecycle.LifecycleError as e:
            raise Conflict(str(e)) from None
        conn.execute(
            "UPDATE plt01.int_connections SET state = 'revoked', revoked_at = now(),"
            " revoked_by = %s, revoke_reason = %s WHERE connection_id = %s",
            (actor_id, reason, connection_id),
        )
        conn.execute(
            "UPDATE plt01.int_credential_refs SET retired_at = now()"
            " WHERE connection_id = %s AND retired_at IS NULL",
            (connection_id,),
        )
    return {"connection_id": connection_id, "state": "revoked"}


def _connection_state(conn: Connection[Any], connection_id: str) -> str:
    row = conn.execute(
        "SELECT state FROM plt01.int_connections WHERE connection_id = %s", (connection_id,)
    ).fetchone()
    if row is None:
        raise NotFound("connection_not_found")
    return str(row[0])


def list_connections(
    tenant_pool: Pool, tenant_id: str, *, install_id: str | None = None,
    include_revoked: bool = False,
) -> list[dict[str, Any]]:
    sql = ["SELECT connection_id, install_id, external_account_ref, region, granted_scopes,"
           " state, authorized_at, validated_at, revoked_at FROM plt01.int_connections"]
    where: list[str] = []
    args: list[Any] = []
    if install_id is not None:
        where.append("install_id = %s")
        args.append(install_id)
    if not include_revoked:
        where.append("revoked_at IS NULL")
    if where:
        sql.append(" WHERE " + " AND ".join(where))
    sql.append(" ORDER BY created_at")
    with tenant_scope(tenant_pool, tenant_id) as conn:
        rows = conn.execute("".join(sql), tuple(args)).fetchall()
    return [{"connection_id": str(r[0]), "install_id": str(r[1]), "external_account_ref": r[2],
             "region": r[3], "granted_scopes": sorted(r[4]), "state": r[5],
             "authorized_at": r[6].isoformat() if r[6] else None,
             "validated_at": r[7].isoformat() if r[7] else None,
             "revoked_at": r[8].isoformat() if r[8] else None} for r in rows]


# --------------------------------------------------------------------- credential references

def rotate_credential(
    tenant_pool: Pool, tenant_id: str, connection_id: str, *, vault_ref: str, actor_id: str,
    correlation_id: str, issued_at: datetime | None = None,
    expires_at: datetime | None = None, scopes: list[str] | None = None,
) -> dict[str, Any]:
    """RotateIntegrationSecret. **Records that a rotation happened; it does not perform one.**

    There is no vault here, so nothing in this process can mint or install a secret. What this
    writes is the new reference, superseding the old one, with the scopes it carries and when
    it expires -- which is what a breach review reads. The old row stays and is retired, because
    the question is always which reference was live on a given day.

    The new scopes default to the old reference's. Narrowing them is allowed and widening them
    is refused: a rotation is a new secret for the same access, and more access is a new
    authorization with its own decision.
    """
    if not vault_ref.strip():
        raise InvalidRequest("a_rotation_names_where_the_new_secret_lives")
    with tenant_scope(tenant_pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT credential_ref_id, scopes FROM plt01.int_credential_refs"
            " WHERE connection_id = %s AND retired_at IS NULL",
            (connection_id,),
        ).fetchone()
        if row is None:
            raise NotFound("no_live_credential_reference")
        previous_scopes = set(row[1])
        new_scopes = list(scopes) if scopes is not None else list(row[1])
        widened = set(new_scopes) - previous_scopes
        if widened:
            raise InvalidRequest("a_rotation_cannot_widen_scopes")
        conn.execute(
            "UPDATE plt01.int_credential_refs SET retired_at = now()"
            " WHERE credential_ref_id = %s",
            (row[0],),
        )
        try:
            created = conn.execute(
                """
                INSERT INTO plt01.int_credential_refs
                    (tenant_id, connection_id, vault_ref, scopes, issued_at, expires_at,
                     supersedes_credential_ref_id, recorded_by, correlation_id)
                VALUES (%s, %s, %s, %s, coalesce(%s, now()), %s, %s, %s, %s)
                RETURNING credential_ref_id, issued_at
                """,
                (tenant_id, connection_id, vault_ref, new_scopes, issued_at, expires_at,
                 row[0], actor_id, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            # Two rotations racing: both read the same live reference, both retired it, and
            # the loser's insert collides on `int_credential_refs_live`. A refusal, not a 500.
            raise Conflict("credential_was_rotated_concurrently") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert created is not None
    return {"credential_ref_id": str(created[0]), "connection_id": connection_id,
            "supersedes": str(row[0]), "scopes": sorted(new_scopes),
            "issued_at": created[1].isoformat()}


def list_credentials(
    tenant_pool: Pool, tenant_id: str, *, connection_id: str | None = None,
    include_retired: bool = False,
) -> list[dict[str, Any]]:
    """Reads the metadata and never a secret, because there is no secret here to read."""
    sql = ["SELECT credential_ref_id, connection_id, vault_ref, scopes, issued_at, expires_at,"
           " retired_at, supersedes_credential_ref_id FROM plt01.int_credential_refs"]
    where: list[str] = []
    args: list[Any] = []
    if connection_id is not None:
        where.append("connection_id = %s")
        args.append(connection_id)
    if not include_retired:
        where.append("retired_at IS NULL")
    if where:
        sql.append(" WHERE " + " AND ".join(where))
    sql.append(" ORDER BY recorded_at DESC")
    with tenant_scope(tenant_pool, tenant_id) as conn:
        rows = conn.execute("".join(sql), tuple(args)).fetchall()
    return [{"credential_ref_id": str(r[0]), "connection_id": str(r[1]), "vault_ref": r[2],
             "scopes": sorted(r[3]), "issued_at": r[4].isoformat(),
             "expires_at": r[5].isoformat() if r[5] else None,
             "retired_at": r[6].isoformat() if r[6] else None,
             "supersedes": str(r[7]) if r[7] else None} for r in rows]


def credentials_due(
    tenant_pool: Pool, tenant_id: str, *, correlation_id: str, actor_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Paragraph 3027's rotation reminder: which live references are inside their window.

    Publishes `credential.expiring` once per reference per call. **Not idempotent across calls**
    and deliberately not: there is no worker driving this, so the only thing that would make it
    safe to loop is a record of what has already been announced, and a table of announcements
    nobody consumes is the shape this codebase refuses elsewhere. A caller that loops will
    publish repeatedly, which is why no caller loops.
    """
    at = now or _now()
    announced = []
    with tenant_scope(tenant_pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT c.credential_ref_id, c.connection_id, n.install_id, c.expires_at"
            " FROM plt01.int_credential_refs c"
            " JOIN plt01.int_connections n ON n.connection_id = c.connection_id"
            " WHERE c.retired_at IS NULL AND n.revoked_at IS NULL"
            "   AND c.expires_at IS NOT NULL ORDER BY c.expires_at",
        ).fetchall()
        for credential_ref_id, connection_id, install_id, expires_at in rows:
            verdict = lifecycle.rotation_due(expires_at=expires_at, now=at)
            if not verdict.due:
                continue
            payload = {"credential_ref_id": str(credential_ref_id),
                       "connection_id": str(connection_id), "install_id": str(install_id),
                       "days_remaining": verdict.days_remaining, "expired": verdict.expired}
            events.append_event(
                conn, tenant_id, event_type="credential.expiring",
                aggregate_type="integration_credential",
                aggregate_id=str(credential_ref_id), payload=payload,
                correlation_id=correlation_id, actor_id=actor_id,
            )
            announced.append(payload)
    return {"announced": announced, "checked_at": at.isoformat()}


# ---------------------------------------------------------------------- cursors and runs

def set_conflict_policy(
    tenant_pool: Pool, tenant_id: str, *, connection_id: str, resource: str, policy: str,
    actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Create or re-point a cursor's conflict policy without moving the cursor itself."""
    if policy not in sync.CONFLICT_POLICIES:
        raise InvalidRequest(f"unknown_conflict_policy_{policy}")
    with tenant_scope(tenant_pool, tenant_id) as conn:
        if _connection_state(conn, connection_id) == "revoked":
            raise Conflict("connection_is_revoked")
        row = conn.execute(
            "UPDATE plt01.int_sync_cursors SET conflict_policy = %s, updated_at = now()"
            " WHERE connection_id = %s AND resource = %s RETURNING cursor_id",
            (policy, connection_id, resource),
        ).fetchone()
        if row is None:
            # Created rather than refused. The policy is the tenant's decision and it has to be
            # settable *before* the first sync, or the only way to get one other than `manual`
            # is to let a connector create the cursor first -- which is how the routine
            # permission came to be the one choosing.
            row = conn.execute(
                "INSERT INTO plt01.int_sync_cursors"
                " (tenant_id, connection_id, resource, position, observed_at,"
                "  conflict_policy)"
                " VALUES (%s, %s, %s, NULL, to_timestamp(0), %s)"
                " ON CONFLICT (tenant_id, connection_id, resource) DO UPDATE"
                " SET conflict_policy = EXCLUDED.conflict_policy, updated_at = now()"
                " RETURNING cursor_id",
                (tenant_id, connection_id, resource, policy),
            ).fetchone()
        assert row is not None
    return {"cursor_id": str(row[0]), "resource": resource, "conflict_policy": policy}


def advance_cursor(
    tenant_pool: Pool, tenant_id: str, *, connection_id: str, resource: str, position: str,
    observed_at: datetime, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Move a cursor forward. An advance observed before the stored one is refused.

    The position is opaque -- a provider's cursor may be a timestamp, a token or a sequence
    number, and ordering one is the provider's business -- so what is compared is when each was
    observed. A late or replayed run settling over a newer result means the next sync re-reads
    a window that was already read, which for a provider that bills per call is money and for
    one with a rate limit is an outage.

    **This does not set the conflict policy.** It used to take one, which handed the routine,
    AAL-1 `integrations.sync.run` permission the decision that `set_conflict_policy` charges a
    financial, stepped-up `integrations.sync.reset` for -- and since the default is `manual`,
    the machine permission was the one actually *choosing* whether a provider's copy may
    overwrite a tenant's records. That decision is the tenant's, not the adapter's.
    """
    with tenant_scope(tenant_pool, tenant_id) as conn:
        state = _connection_state(conn, connection_id)
        if state == "revoked":
            raise Conflict("connection_is_revoked")
        existing = conn.execute(
            "SELECT cursor_id, position, observed_at, conflict_policy"
            " FROM plt01.int_sync_cursors WHERE connection_id = %s AND resource = %s",
            (connection_id, resource),
        ).fetchone()
        # A cursor that exists only to carry a policy has no position yet, so there is nothing
        # to compare against and this advance is the first one.
        current = (sync.Cursor(resource=resource, position=existing[1],
                               observed_at=existing[2])
                   if existing and existing[1] is not None else None)
        try:
            sync.check_advance(current, sync.Cursor(resource=resource, position=position,
                                                    observed_at=observed_at))
        except sync.SyncError as e:
            raise Conflict(str(e)) from None
        if existing is None:
            try:
                row = conn.execute(
                    "INSERT INTO plt01.int_sync_cursors"
                    " (tenant_id, connection_id, resource, position, observed_at)"
                    " VALUES (%s, %s, %s, %s, %s) RETURNING cursor_id",
                    (tenant_id, connection_id, resource, position, observed_at),
                ).fetchone()
            except errors.UniqueViolation:
                # Two first advances for one resource racing: the read above found nothing for
                # both, and one insert loses. A refusal rather than a 500, and the loser
                # retries into the update path with the comparison it should have had.
                raise Conflict("cursor_was_created_concurrently") from None
            except errors.CheckViolation as e:
                raise InvalidRequest(_check_name(e)) from None
            assert row is not None
            cursor_id = str(row[0])
        else:
            cursor_id = str(existing[0])
            # `AND observed_at < %s` rather than a blind update: two advances racing both pass
            # the comparison above against the same pre-image under READ COMMITTED, and the
            # older observation could land last -- the regression this function exists to
            # prevent. The same `status = 'running'` shape `finish_run` uses.
            moved = conn.execute(
                "UPDATE plt01.int_sync_cursors SET position = %s, observed_at = %s,"
                " updated_at = now() WHERE cursor_id = %s"
                " AND (position IS NULL OR observed_at < %s)",
                (position, observed_at, cursor_id, observed_at),
            )
            if moved.rowcount == 0:
                raise Conflict("cursor_was_advanced_concurrently")
    return {"cursor_id": cursor_id, "resource": resource, "position": position,
            "observed_at": observed_at.isoformat()}


def reset_cursor(
    tenant_pool: Pool, tenant_id: str, *, connection_id: str, resource: str, position: str,
    observed_at: datetime, reason: str, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Move a cursor deliberately, including backwards. Reconciliation goes through here.

    Separate from `advance_cursor` because the two are different decisions wearing the same
    shape: an advance is a connector reporting progress, and a reset is a person deciding to
    re-read something. The reason is required, since re-reading a window costs whatever the
    provider charges for it.
    """
    if not reason.strip():
        raise InvalidRequest("a_cursor_reset_states_a_reason")
    with tenant_scope(tenant_pool, tenant_id) as conn:
        if _connection_state(conn, connection_id) == "revoked":
            raise Conflict("connection_is_revoked")
        row = conn.execute(
            "UPDATE plt01.int_sync_cursors SET position = %s, observed_at = %s,"
            " reset_at = now(), reset_by = %s, reset_reason = %s, updated_at = now()"
            " WHERE connection_id = %s AND resource = %s RETURNING cursor_id",
            (position, observed_at, actor_id, reason, connection_id, resource),
        ).fetchone()
        if row is None:
            raise NotFound("cursor_not_found")
    return {"cursor_id": str(row[0]), "resource": resource, "position": position,
            "reset_reason": reason}


def list_cursors(
    tenant_pool: Pool, tenant_id: str, *, connection_id: str | None = None,
) -> list[dict[str, Any]]:
    sql = ("SELECT cursor_id, connection_id, resource, position, observed_at,"
           " conflict_policy, reset_at, updated_at FROM plt01.int_sync_cursors")
    args: tuple[Any, ...] = ()
    if connection_id is not None:
        sql += " WHERE connection_id = %s"
        args = (connection_id,)
    sql += " ORDER BY resource"
    with tenant_scope(tenant_pool, tenant_id) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [{"cursor_id": str(r[0]), "connection_id": str(r[1]), "resource": r[2],
             "position": r[3], "observed_at": r[4].isoformat(), "conflict_policy": r[5],
             "reset_at": r[6].isoformat() if r[6] else None,
             "updated_at": r[7].isoformat()} for r in rows]


def start_run(
    tenant_pool: Pool, tenant_id: str, *, connection_id: str, resource: str, actor_id: str,
    correlation_id: str, max_attempts: int = 5,
) -> dict[str, Any]:
    """SyncIntegration, as far as this build can honestly take it: it opens a run.

    Nothing here calls a provider. The run is the record that somebody started one, and
    `finish_run` or `fail_run` is written by whatever did the work.

    A run against a connection that is not validated, or whose install is not active, is
    refused: a connector reaching a provider on behalf of an install nobody activated is the
    integration operating outside the decision that authorized it.
    """
    with tenant_scope(tenant_pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT n.state, i.state, n.install_id FROM plt01.int_connections n"
            " JOIN plt01.int_installs i ON i.install_id = n.install_id"
            " WHERE n.connection_id = %s",
            (connection_id,),
        ).fetchone()
        if row is None:
            raise NotFound("connection_not_found")
        if row[0] != "validated":
            raise Conflict("connection_is_not_validated")
        if row[1] != "active":
            raise Conflict("install_is_not_active")
        try:
            created = conn.execute(
                "INSERT INTO plt01.int_connector_runs"
                " (tenant_id, connection_id, resource, max_attempts, claimed_until,"
                "  started_by, correlation_id)"
                " VALUES (%s, %s, %s, %s, now() + %s, %s, %s) RETURNING run_id, started_at",
                (tenant_id, connection_id, resource, max_attempts, sync.CLAIM_LEASE, actor_id,
                 correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            # One running run per resource, enforced by a partial unique index. Two concurrent
            # syncs of one resource read the same window and both advance the same cursor, so
            # one of them ends up having skipped records it never saw.
            raise Conflict("this_resource_is_already_syncing") from None
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        assert created is not None
    return {"run_id": str(created[0]), "connection_id": connection_id, "resource": resource,
            "status": "running", "attempts": 1, "started_at": created[1].isoformat()}


def finish_run(
    tenant_pool: Pool, tenant_id: str, run_id: str, *, records_read: int,
    records_written: int, actor_id: str, correlation_id: str, conflicts: int = 0,
) -> dict[str, Any]:
    """Settle a run as succeeded, guarded on it still being the one that is running.

    `AND status = 'running'`, not a blind update. The claim is a lease rather than a lock, so a
    runner slower than its lease can have its row settled by another; without the guard a late
    success overwrites that settlement, which is MOD-010's finding in this module's clothes.

    **`settled_by` is who made the claim, which is not who started the run.**
    `integrations.sync.run` is routine and tenant-wide, so any holder can finish any running
    run -- and without this column the only name on a fabricated "synced four million records"
    would be the name of the party that did not make the claim. MOD-008 audits denials and not
    allowed actions, so there is no second record to fall back on. Found by review; it is
    MOD-011's probe-result finding, one module later.
    """
    with tenant_scope(tenant_pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "UPDATE plt01.int_connector_runs SET status = 'succeeded',"
                " finished_at = now(), records_read = %s, records_written = %s,"
                " conflicts = %s, last_error = NULL, next_attempt_at = NULL,"
                " settled_by = %s, settle_correlation_id = %s"
                " WHERE run_id = %s AND status = 'running' RETURNING attempts",
                (records_read, records_written, conflicts, actor_id, correlation_id, run_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.DataError:
            # `NumericValueOutOfRange` is a `DataError` and not a `CheckViolation`, so a count
            # past the column's width reached the caller as a 500 until review pointed it out.
            raise InvalidRequest("a_record_count_is_out_of_range") from None
        if row is None:
            raise Conflict("run_is_not_running")
    return {"run_id": run_id, "status": "succeeded", "attempts": int(row[0]),
            "records_read": records_read, "records_written": records_written,
            "conflicts": conflicts}


def fail_run(
    tenant_pool: Pool, tenant_id: str, run_id: str, *, error: str, correlation_id: str,
    actor_id: str, now: datetime | None = None,
) -> dict[str, Any]:
    """Record a failure, decide retry or quarantine, and publish either way.

    `integration.sync.failed` carries the status, so a consumer can tell a run that will be
    tried again from one that has been quarantined -- those are different alerts, and a
    consumer that could not distinguish them would page on both or neither.
    """
    if not error.strip():
        raise InvalidRequest("a_failure_records_what_went_wrong")
    at = now or _now()
    with tenant_scope(tenant_pool, tenant_id) as conn:
        # `status = 'running'`, not `IN ('running', 'failed')`. `fail_run` does not increment
        # the attempt count -- `retry_run` does -- so accepting a run that is already `failed`
        # froze `attempts` for ever: every later report produced the same verdict, pushed the
        # backoff out again, published another event claiming attempt one, and the run **could
        # never reach `dead`**. An operator reading the dead-letter board saw it clean while a
        # connector failed continuously, which is MOD-010's `outbox_health` finding in this
        # module's clothes. `finish_run` already guards exactly this way and says why.
        row = conn.execute(
            "SELECT attempts, max_attempts, connection_id, resource"
            " FROM plt01.int_connector_runs WHERE run_id = %s AND status = 'running'",
            (run_id,),
        ).fetchone()
        if row is None:
            raise Conflict("run_is_not_running")
        try:
            verdict = sync.failure_verdict(attempts=int(row[0]), max_attempts=int(row[1]),
                                           now=at)
        except sync.SyncError as e:
            raise InvalidRequest(str(e)) from None
        # `finished_at` on a retryable failure as well as on a quarantine. The column means
        # "this run stopped running", and a run awaiting its backoff has stopped -- `retry_run`
        # clears it when the next attempt starts. Setting it only for `dead` left a `failed`
        # row claiming to be running and still in flight, which
        # `int_connector_runs_finished` refused outright; the constraint caught a real
        # inconsistency rather than an awkward shape.
        conn.execute(
            "UPDATE plt01.int_connector_runs SET status = %s, last_error = %s,"
            " next_attempt_at = %s, finished_at = now(), claimed_until = NULL,"
            " settled_by = %s, settle_correlation_id = %s WHERE run_id = %s",
            (verdict.status, error[:2000], verdict.next_attempt_at, actor_id, correlation_id,
             run_id),
        )
        events.append_event(
            conn, tenant_id, event_type="integration.sync.failed",
            aggregate_type="connector_run", aggregate_id=run_id,
            payload={"run_id": run_id, "connection_id": str(row[2]), "resource": row[3],
                     "attempts": verdict.attempts, "status": verdict.status,
                     "reason": error[:500]},
            correlation_id=correlation_id, actor_id=actor_id,
        )
    return {"run_id": run_id, "status": verdict.status, "attempts": verdict.attempts,
            "next_attempt_at": verdict.next_attempt_at.isoformat()}


def retry_run(
    tenant_pool: Pool, tenant_id: str, run_id: str, *, actor_id: str, correlation_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Claim a failed run whose backoff has elapsed, counting the attempt.

    A `dead` run is not retryable from here: releasing one is a decision somebody makes about a
    connector that has failed its whole budget, and it goes through `release_run` so the
    decision carries a name and a reason.
    """
    at = now or _now()
    with tenant_scope(tenant_pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "UPDATE plt01.int_connector_runs SET status = 'running',"
                " attempts = attempts + 1, claimed_until = %s, next_attempt_at = NULL,"
                " finished_at = NULL, settled_by = NULL, settle_correlation_id = NULL"
                " WHERE run_id = %s AND status = 'failed' AND next_attempt_at <= %s"
                "   AND attempts < max_attempts RETURNING attempts",
                (at + sync.CLAIM_LEASE, run_id, at),
            ).fetchone()
        except errors.UniqueViolation:
            # Another run already holds this (connection, resource) slot. Nothing stops a
            # caller starting a second run for the resource while this one waits out its
            # backoff -- `start_run` looks at the connection and the install, not at other
            # runs -- so this collision is reachable with no concurrency at all, and it was a
            # 500 until review walked the sequence.
            raise Conflict("this_resource_is_already_syncing") from None
        if row is None:
            raise Conflict("run_is_not_due_for_retry")
    return {"run_id": run_id, "status": "running", "attempts": int(row[0])}


def release_run(
    tenant_pool: Pool, tenant_id: str, run_id: str, *, reason: str, actor_id: str,
    correlation_id: str, now: datetime | None = None,
) -> dict[str, Any]:
    """Take a quarantined run out of the dead letter, attributed on the row.

    **The attribution is columns, not a docstring.** The first version validated the reason,
    returned it to the caller and discarded it, took an `actor_id` it never used, and published
    nothing -- while both this docstring and the route's claimed it was recorded. There is
    nowhere else it could land: MOD-008 audits denials and not allowed actions, and
    `veyro_cp_app` holds nothing in `iam`, which is verbatim MOD-009's legal-hold finding.
    This is the act that puts a connector which burned its entire retry budget back in front of
    a third-party provider, and it resets the attempt count, so without the columns the row
    afterwards reads as a fresh run with a stale error and no trace of a decision.

    The attempt count is reset, because the decision being recorded is that whatever broke has
    been fixed -- a release that kept the exhausted budget would quarantine again on the next
    failure without ever having had a chance.
    """
    if not reason.strip():
        raise InvalidRequest("a_release_states_a_reason")
    at = now or _now()
    with tenant_scope(tenant_pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "UPDATE plt01.int_connector_runs SET status = 'running', attempts = 1,"
                " claimed_until = %s, next_attempt_at = NULL, finished_at = NULL,"
                " settled_by = NULL, settle_correlation_id = NULL, released_at = now(),"
                " released_by = %s, release_reason = %s, release_correlation_id = %s"
                " WHERE run_id = %s AND status = 'dead' RETURNING connection_id",
                (at + sync.CLAIM_LEASE, actor_id, reason[:500], correlation_id, run_id),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("this_resource_is_already_syncing") from None
        if row is None:
            raise NotFound("quarantined_run_not_found")
    return {"run_id": run_id, "status": "running", "attempts": 1, "released_because": reason}


def record_reconciliation(
    tenant_pool: Pool, tenant_id: str, run_id: str, *, local_count: int, provider_count: int,
    matched: int, actor_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Paragraph 3028's reconciliation, recorded against the run that performed it.

    The counts are a caller's, as every number in this module is: nothing here can count the
    provider's side. What this adds is the arithmetic check -- `matched` above either total is a
    caller confusing an intersection with a total, and the resulting difference would read as
    "the provider is ahead" on a report nobody could reproduce.

    **The totals are stored and the claim carries a name.** The first version folded the two
    sides into `conflicts` and discarded them, and recorded nobody: a difference with no totals
    behind it is a number nobody can reproduce, and a claim about a third party's data with no
    author is the shape MOD-011's probe results were blocked for. Written **once** per run, so
    a second pass cannot quietly replace the first one's figures.
    """
    try:
        found = sync.check_reconciliation(sync.Reconciliation(
            local_count=local_count, provider_count=provider_count, matched=matched))
    except sync.SyncError as e:
        raise InvalidRequest(str(e)) from None
    with tenant_scope(tenant_pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "UPDATE plt01.int_connector_runs SET conflicts = %s, reconciled_at = now(),"
                " reconciled_by = %s, reconcile_correlation_id = %s, reconciled_local = %s,"
                " reconciled_provider = %s, reconciled_matched = %s"
                " WHERE run_id = %s AND reconciled_at IS NULL RETURNING resource",
                (min(found.local_only + found.provider_only, 2147483647), actor_id,
                 correlation_id, found.local_count, found.provider_count, found.matched,
                 run_id),
            ).fetchone()
        except errors.CheckViolation as e:
            raise InvalidRequest(_check_name(e)) from None
        except errors.DataError:
            raise InvalidRequest("a_reconciliation_count_is_out_of_range") from None
        if row is None:
            # Either there is no such run or it has already been reconciled. Distinguishing
            # the two would be a read this does not need, and both answers are "not again".
            raise Conflict("run_not_found_or_already_reconciled")
    return {"run_id": run_id, "resource": row[0], "local_only": found.local_only,
            "provider_only": found.provider_only, "matched": found.matched,
            "reconciled": found.reconciled}


def list_runs(
    tenant_pool: Pool, tenant_id: str, *, connection_id: str | None = None,
    status: str | None = None, limit: int = 50,
) -> list[dict[str, Any]]:
    sql = ["SELECT run_id, connection_id, resource, status, attempts, max_attempts,"
           " records_read, records_written, conflicts, last_error, next_attempt_at,"
           " started_at, finished_at FROM plt01.int_connector_runs"]
    where: list[str] = []
    args: list[Any] = []
    if connection_id is not None:
        where.append("connection_id = %s")
        args.append(connection_id)
    if status is not None:
        where.append("status = %s")
        args.append(status)
    if where:
        sql.append(" WHERE " + " AND ".join(where))
    sql.append(" ORDER BY started_at DESC LIMIT %s")
    args.append(max(1, min(limit, 500)))
    with tenant_scope(tenant_pool, tenant_id) as conn:
        rows = conn.execute("".join(sql), tuple(args)).fetchall()
    return [{"run_id": str(r[0]), "connection_id": str(r[1]), "resource": r[2],
             "status": r[3], "attempts": r[4], "max_attempts": r[5], "records_read": int(r[6]),
             "records_written": int(r[7]), "conflicts": r[8], "last_error": r[9],
             "next_attempt_at": r[10].isoformat() if r[10] else None,
             "started_at": r[11].isoformat(),
             "finished_at": r[12].isoformat() if r[12] else None} for r in rows]

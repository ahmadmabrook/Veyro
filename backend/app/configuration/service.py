"""MOD-005 PLT-02 service: configuration registry, feature flags, kill switches, experiments.

This module does the I/O. Every decision it reports -- which value applies at a scope, which
variant a subject gets, whether a value is valid -- is made by `app.configuration.evaluation`,
which is pure. Nothing here re-implements one of those decisions, so there is exactly one
definition of each in the codebase and the unit tests exercise the real thing.

Like `app.tenancy.service`, no function filters by `tenant_id` in its own SQL. Row-level security
does it. A missing WHERE clause here returns nothing rather than another tenant's rows, which is
the behaviour the isolation suite proves rather than assumes.

Two tables are insert-only in the privilege layer, `cfg_values` and `cfg_exposures`, so the usual
read-modify-write is not available for them:

* publishing a configuration value appends the next version, and the unique constraint over
  (definition, scope, version) is what refuses a concurrent second writer -- the service reports
  that as a conflict rather than silently winning;
* a rollback appends a further version carrying the old payload and records which version it came
  from in `rolled_back_from`. Nothing is overwritten, so the audit trail reads forward.

PLT-02 names six requirements. Five are implemented here; the parts not built are listed at the
end of this docstring rather than left for a reader to discover:

* **R01** typed registry with defaults, validation, ownership, versioning and inheritance -- built.
* **R02** flags targeted by environment, tenant, plan, brand, location, user, role and percentage
  rollout -- built; targeting attributes are free-form strings, so all seven dimensions are
  expressible without the module needing to know their names.
* **R03** kill switches -- built, and ordered ahead of every rule in evaluation.
* **R04** experiment assignment and exposure events -- built. **Metrics, guardrails and
  statistical decision records are not.** They need a metrics pipeline that does not exist in this
  repository yet; inventing a decision record with no measurements behind it would be a worse
  answer than the gap.
* **R05** preview and rollback -- built. **Approval workflow is not**: approval needs an
  authenticated principal and MOD-002 is not wired in, so there is nobody to approve as. The TSD's
  own control (paragraph 1020) requires authorized change control for financial and security flag
  changes in production; this service runs in local, development and staging only, and that
  control is not satisfied by anything here.
* **R06** remote configuration for mobile, kiosks and managed devices -- built as `bundle`, which
  returns resolved values and flag decisions together with a version a device can cache against.

The transactional outbox named in paragraph 1007 is not built: no consumer exists, and an outbox
nothing drains is a table that grows. `configuration.changed`, `feature_flag.evaluated`,
`experiment.exposed` and `experiment.completed` are therefore not published yet.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any
from uuid import uuid4

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from app.configuration import evaluation as ev
from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound
from app.events import service as events

SCOPES = ("tenant", "brand", "location")


def _check_scope(scope_type: str, brand_id: str | None, location_id: str | None) -> None:
    """Mirror the migration's CHECK in the service so a bad scope is a 422, not a 500."""
    if scope_type not in SCOPES:
        raise InvalidRequest("bad_scope_type")
    if scope_type == "tenant" and (brand_id or location_id):
        raise InvalidRequest("tenant_scope_takes_no_target")
    if scope_type == "brand" and (not brand_id or location_id):
        raise InvalidRequest("brand_scope_needs_brand_id")
    if scope_type == "location" and (not location_id or brand_id):
        raise InvalidRequest("location_scope_needs_location_id")


def _validated(value_type: str, validation: dict[str, Any], value: Any) -> None:
    try:
        ev.validate_value(value_type, validation, value)
    except ev.ValidationError as exc:
        raise InvalidRequest(exc.code) from None


# --------------------------------------------------------------------------- definitions

def define_config(
    pool: Pool,
    tenant_id: str,
    *,
    config_key: str,
    value_type: str,
    default_value: Any,
    owner_module: str,
    validation: dict[str, Any] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Register a typed configuration key (PLT-02-R01).

    The default is validated against the definition's own constraints at registration time. A
    definition whose default its own rules reject would make every unset scope invalid, and the
    failure would surface far from here.
    """
    rules = validation or {}
    try:
        ev.validate_key(config_key)
    except ev.ValidationError as exc:
        raise InvalidRequest(exc.code) from None
    _validated(value_type, rules, default_value)
    if not owner_module.strip():
        raise InvalidRequest("bad_owner_module")

    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cfg_definitions
                    (tenant_id, config_key, value_type, default_value, validation,
                     owner_module, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING definition_id, config_key, value_type, default_value, validation,
                          owner_module, description
                """,
                (tenant_id, config_key, value_type, _json(default_value), _json(rules),
                 owner_module, description),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("config_key_exists") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tenant_not_found") from None
        except errors.CheckViolation:
            raise InvalidRequest("bad_definition") from None
        assert row is not None
    return _definition_dict(row)


def list_definitions(pool: Pool, tenant_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            """
            SELECT definition_id, config_key, value_type, default_value, validation,
                   owner_module, description
            FROM plt01.cfg_definitions ORDER BY config_key
            """
        ).fetchall()
    return [_definition_dict(r) for r in rows]


def _definition_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "definition_id": str(row[0]), "config_key": row[1], "value_type": row[2],
        "default_value": row[3], "validation": row[4], "owner_module": row[5],
        "description": row[6],
    }


def _json(value: Any) -> Jsonb:
    """A bare dict is ambiguous to psycopg; Jsonb says jsonb for scalars and containers alike."""
    return Jsonb(value)


# --------------------------------------------------------------------------- values

def _definition_row(conn: Connection[Any], config_key: str) -> tuple[Any, ...]:
    row = conn.execute(
        "SELECT definition_id, value_type, default_value, validation"
        " FROM plt01.cfg_definitions WHERE config_key = %s",
        (config_key,),
    ).fetchone()
    if row is None:
        raise NotFound("config_key_not_found")
    return tuple(row)


def _value_row(row: tuple[Any, ...]) -> ev.ValueRow:
    scope_type, brand_id, location_id, value, version = row
    return ev.ValueRow(
        scope_type=scope_type,
        brand_id=str(brand_id) if brand_id else None,
        location_id=str(location_id) if location_id else None,
        value=value, version=int(version),
    )


def _value_rows(conn: Connection[Any], definition_id: Any) -> list[ev.ValueRow]:
    rows = conn.execute(
        "SELECT scope_type, brand_id, location_id, value, version FROM plt01.cfg_values"
        " WHERE definition_id = %s",
        (definition_id,),
    ).fetchall()
    return [_value_row(r) for r in rows]


def _next_version(
    conn: Connection[Any], definition_id: Any, scope_type: str,
    brand_id: str | None, location_id: str | None,
) -> int:
    row = conn.execute(
        """
        SELECT coalesce(max(version), 0) FROM plt01.cfg_values
        WHERE definition_id = %s AND scope_type = %s
          AND brand_id IS NOT DISTINCT FROM %s AND location_id IS NOT DISTINCT FROM %s
        """,
        (definition_id, scope_type, brand_id, location_id),
    ).fetchone()
    assert row is not None
    return int(row[0]) + 1


def publish_config_version(
    pool: Pool,
    tenant_id: str,
    *,
    config_key: str,
    scope_type: str,
    value: Any,
    published_by: str,
    correlation_id: str,
    brand_id: str | None = None,
    location_id: str | None = None,
    expected_version: int | None = None,
    rolled_back_from: int | None = None,
) -> dict[str, Any]:
    """Append a new version of a value at one scope (PublishConfigVersion, PLT-02-R01/R05).

    `expected_version` is the optimistic-concurrency check TSD paragraph 1029 asks for: pass the
    version you believe is current and the publish is refused if someone else moved it. Omit it to
    publish unconditionally.
    """
    _check_scope(scope_type, brand_id, location_id)
    with tenant_scope(pool, tenant_id) as conn:
        definition_id, value_type, _default, validation = _definition_row(conn, config_key)
        _validated(value_type, validation, value)
        current = _next_version(conn, definition_id, scope_type, brand_id, location_id) - 1
        if expected_version is not None and expected_version != current:
            raise Conflict("version_mismatch")
        try:
            row = conn.execute(
                """
                INSERT INTO plt01.cfg_values
                    (tenant_id, definition_id, scope_type, brand_id, location_id, value,
                     version, rolled_back_from, published_by, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING value_id, version, published_at
                """,
                (tenant_id, definition_id, scope_type, brand_id, location_id, _json(value),
                 current + 1, rolled_back_from, published_by, correlation_id),
            ).fetchone()
        except errors.UniqueViolation:
            # Another writer appended the same version between the read and the insert.
            raise Conflict("version_conflict") from None
        except errors.ForeignKeyViolation:
            raise NotFound("scope_not_found") from None
        assert row is not None
        # MOD-010: in the same transaction as the value, so a consumer cannot be told about a
        # configuration change that did not commit.
        events.append_event(
            conn, tenant_id, event_type="configuration.changed", aggregate_type="config_value",
            aggregate_id=str(row[0]),
            payload={"config_key": config_key, "scope_type": scope_type,
                     "scope_id": brand_id or location_id, "version": int(row[1]),
                     "published_by": published_by},
            correlation_id=correlation_id, actor_id=published_by,
        )
    return {
        "value_id": str(row[0]), "config_key": config_key, "scope_type": scope_type,
        "brand_id": brand_id, "location_id": location_id, "value": value,
        "version": int(row[1]), "rolled_back_from": rolled_back_from,
        "published_at": row[2].isoformat(),
    }


def config_history(pool: Pool, tenant_id: str, config_key: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        definition_id = _definition_row(conn, config_key)[0]
        rows = conn.execute(
            """
            SELECT version, scope_type, brand_id, location_id, value, rolled_back_from,
                   published_by, correlation_id, published_at
            FROM plt01.cfg_values WHERE definition_id = %s
            ORDER BY scope_type, brand_id, location_id, version
            """,
            (definition_id,),
        ).fetchall()
    return [
        {
            "version": int(r[0]), "scope_type": r[1],
            "brand_id": str(r[2]) if r[2] else None,
            "location_id": str(r[3]) if r[3] else None,
            "value": r[4], "rolled_back_from": int(r[5]) if r[5] is not None else None,
            "published_by": str(r[6]), "correlation_id": str(r[7]),
            "published_at": r[8].isoformat(),
        }
        for r in rows
    ]


def rollback_config(
    pool: Pool,
    tenant_id: str,
    *,
    config_key: str,
    scope_type: str,
    to_version: int,
    published_by: str,
    correlation_id: str,
    brand_id: str | None = None,
    location_id: str | None = None,
) -> dict[str, Any]:
    """Republish an earlier version's payload as a new version (RollbackConfig, PLT-02-R05).

    Nothing is deleted or rewritten: the history keeps the version being rolled back from, and the
    new row records where its payload came from. That is what "repair without history rewrite"
    (TSD paragraph 1034) means in practice, and the absence of an UPDATE grant on `cfg_values`
    means no other implementation is available.
    """
    _check_scope(scope_type, brand_id, location_id)
    with tenant_scope(pool, tenant_id) as conn:
        definition_id = _definition_row(conn, config_key)[0]
        row = conn.execute(
            """
            SELECT value FROM plt01.cfg_values
            WHERE definition_id = %s AND scope_type = %s
              AND brand_id IS NOT DISTINCT FROM %s AND location_id IS NOT DISTINCT FROM %s
              AND version = %s
            """,
            (definition_id, scope_type, brand_id, location_id, to_version),
        ).fetchone()
        if row is None:
            raise NotFound("version_not_found")
        payload = row[0]
    return publish_config_version(
        pool, tenant_id, config_key=config_key, scope_type=scope_type, value=payload,
        published_by=published_by, correlation_id=correlation_id, brand_id=brand_id,
        location_id=location_id, rolled_back_from=to_version,
    )


def _resolve_all(
    conn: Connection[Any], brand_id: str | None, location_id: str | None
) -> dict[str, dict[str, Any]]:
    definitions = conn.execute(
        "SELECT definition_id, config_key, default_value FROM plt01.cfg_definitions"
    ).fetchall()
    values = conn.execute(
        "SELECT definition_id, scope_type, brand_id, location_id, value, version"
        " FROM plt01.cfg_values"
    ).fetchall()
    by_definition: dict[Any, list[ev.ValueRow]] = {}
    for row in values:
        by_definition.setdefault(row[0], []).append(_value_row(row[1:]))
    out: dict[str, dict[str, Any]] = {}
    for definition_id, config_key, default_value in definitions:
        got = ev.resolve_value(
            default_value, by_definition.get(definition_id, []),
            brand_id=brand_id, location_id=location_id,
        )
        out[config_key] = {
            "value": got.value, "scope_type": got.scope_type, "version": got.version,
        }
    return out


def resolve_config(
    pool: Pool, tenant_id: str, *, brand_id: str | None = None, location_id: str | None = None
) -> dict[str, dict[str, Any]]:
    """Resolve every definition for one scope (PLT-02-R01 inheritance)."""
    with tenant_scope(pool, tenant_id) as conn:
        return _resolve_all(conn, brand_id, location_id)


def preview_config(
    pool: Pool,
    tenant_id: str,
    *,
    config_key: str,
    value: Any,
    scope_type: str = "tenant",
    brand_id: str | None = None,
    location_id: str | None = None,
) -> dict[str, Any]:
    """Show what publishing `value` at this scope would do, without writing (PLT-02-R05).

    The question asked is the one that matters before a publish: at the scope you are publishing
    to, what resolves now, what would resolve after, and would the new value actually be the one
    served. `shadowed` answers the last of those -- a tenant-level value is shadowed by an
    existing brand or location value, and discovering that before publishing is cheaper than
    discovering it from a support ticket.

    The value is validated against its definition here too, so a preview of an invalid value
    fails the same way the publish would rather than reporting a result nobody could publish.
    """
    _check_scope(scope_type, brand_id, location_id)
    with tenant_scope(pool, tenant_id) as conn:
        definition_id, value_type, default_value, validation = _definition_row(conn, config_key)
        _validated(value_type, validation, value)
        rows = _value_rows(conn, definition_id)
        next_version = _next_version(conn, definition_id, scope_type, brand_id, location_id)

    at = {"brand_id": brand_id, "location_id": location_id}
    before = ev.resolve_value(default_value, rows, **at)
    after = ev.resolve_value(
        default_value,
        [*rows, ev.ValueRow(scope_type=scope_type, brand_id=brand_id, location_id=location_id,
                            value=value, version=next_version)],
        **at,
    )
    return {
        "config_key": config_key,
        "proposed_scope": scope_type,
        "proposed_version": next_version,
        "current": {"value": before.value, "scope_type": before.scope_type,
                    "version": before.version},
        "resolves_to": {"value": after.value, "scope_type": after.scope_type,
                        "version": after.version},
        "shadowed": after.value != value,
        "changes": after.value != before.value,
    }


# --------------------------------------------------------------------------- flags

def set_feature_policy(
    pool: Pool,
    tenant_id: str,
    *,
    flag_key: str,
    enabled: bool,
    default_variant: str = "off",
    rules: list[dict[str, Any]] | None = None,
    description: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Create or update a flag and replace its live targeting rules (SetFeaturePolicy, R02).

    The whole policy moves in one transaction: a caller never sees the old rules against the new
    flag state. Replaced rules are retired, not deleted, so the previous targeting stays readable.

    This does not touch the kill switch. Engaging and releasing a switch is a separate, narrower
    command precisely so an ordinary policy edit cannot clear one by omission.
    """
    try:
        ev.validate_key(flag_key)
    except ev.ValidationError as exc:
        raise InvalidRequest(exc.code) from None
    wanted = rules or []
    for rule in wanted:
        if not isinstance(rule.get("match", {}), dict):
            raise InvalidRequest("bad_rule_match")
        if not 0 <= int(rule.get("rollout_bp", ev.BUCKETS)) <= ev.BUCKETS:
            raise InvalidRequest("bad_rollout_bp")
        if not str(rule.get("variant", "")).strip():
            raise InvalidRequest("bad_rule_variant")

    with tenant_scope(pool, tenant_id) as conn:
        existing = conn.execute(
            "SELECT flag_id, version FROM plt01.cfg_flags WHERE flag_key = %s", (flag_key,)
        ).fetchone()
        if existing is None:
            if expected_version is not None:
                raise NotFound("flag_not_found")
            try:
                created = conn.execute(
                    """
                    INSERT INTO plt01.cfg_flags
                        (tenant_id, flag_key, description, enabled, default_variant)
                    VALUES (%s, %s, %s, %s, %s) RETURNING flag_id, version
                    """,
                    (tenant_id, flag_key, description, enabled, default_variant),
                ).fetchone()
            except errors.ForeignKeyViolation:
                raise NotFound("tenant_not_found") from None
            except errors.CheckViolation:
                raise InvalidRequest("bad_flag") from None
            assert created is not None
            flag_id, version = created[0], int(created[1])
        else:
            flag_id, version = existing[0], int(existing[1])
            if expected_version is not None and expected_version != version:
                raise Conflict("version_mismatch")
            updated = conn.execute(
                """
                UPDATE plt01.cfg_flags
                SET enabled = %s, default_variant = %s,
                    description = coalesce(%s, description),
                    version = version + 1, updated_at = now()
                WHERE flag_id = %s RETURNING version
                """,
                (enabled, default_variant, description, flag_id),
            ).fetchone()
            assert updated is not None
            version = int(updated[0])
            conn.execute(
                "UPDATE plt01.cfg_flag_rules SET retired_at = now()"
                " WHERE flag_id = %s AND retired_at IS NULL",
                (flag_id,),
            )
        for priority, rule in enumerate(wanted, start=1):
            conn.execute(
                """
                INSERT INTO plt01.cfg_flag_rules
                    (tenant_id, flag_id, priority, match, rollout_bp, variant)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, flag_id, priority, _json(rule.get("match", {})),
                 int(rule.get("rollout_bp", ev.BUCKETS)), rule["variant"]),
            )
    return {"flag_key": flag_key, "enabled": enabled, "default_variant": default_variant,
            "version": version, "rules": len(wanted)}


def set_kill_switch(
    pool: Pool, tenant_id: str, *, flag_key: str, engaged: bool, reason: str | None = None
) -> dict[str, Any]:
    """Engage or release a kill switch (PLT-02-R03).

    Engaging requires a reason, enforced by the table as well as here. Releasing clears it.
    """
    if engaged and not (reason or "").strip():
        raise InvalidRequest("kill_switch_needs_reason")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            """
            UPDATE plt01.cfg_flags
            SET kill_switch_engaged = %s, kill_switch_reason = %s,
                version = version + 1, updated_at = now()
            WHERE flag_key = %s
            RETURNING flag_key, kill_switch_engaged, kill_switch_reason, version
            """,
            (engaged, reason if engaged else None, flag_key),
        ).fetchone()
        if row is None:
            raise NotFound("flag_not_found")
    return {"flag_key": row[0], "kill_switch_engaged": row[1], "kill_switch_reason": row[2],
            "version": int(row[3])}


def _evaluate_all(
    conn: Connection[Any], tenant_id: str, subject_id: str, context: dict[str, str]
) -> dict[str, dict[str, Any]]:
    flags = conn.execute(
        "SELECT flag_id, flag_key, enabled, default_variant, kill_switch_engaged, version"
        " FROM plt01.cfg_flags"
    ).fetchall()
    rules = conn.execute(
        "SELECT flag_id, rule_id, priority, match, rollout_bp, variant"
        " FROM plt01.cfg_flag_rules WHERE retired_at IS NULL"
    ).fetchall()
    by_flag: dict[Any, list[ev.Rule]] = {}
    for flag_id, rule_id, priority, match, rollout_bp, variant in rules:
        by_flag.setdefault(flag_id, []).append(
            ev.Rule(rule_id=str(rule_id), priority=int(priority), match=match,
                    rollout_bp=int(rollout_bp), variant=variant)
        )
    out: dict[str, dict[str, Any]] = {}
    for flag_id, flag_key, enabled, default_variant, killed, version in flags:
        decision = ev.evaluate_flag(
            ev.Flag(flag_key=flag_key, enabled=enabled, default_variant=default_variant,
                    kill_switch_engaged=killed, version=int(version)),
            by_flag.get(flag_id, []),
            context=context, subject_id=subject_id, tenant_id=tenant_id,
        )
        out[flag_key] = {"variant": decision.variant, "reason": decision.reason,
                         "version": int(version)}
    return out


def evaluate_flags(
    pool: Pool, tenant_id: str, *, subject_id: str, context: dict[str, str] | None = None
) -> dict[str, dict[str, Any]]:
    if not subject_id.strip():
        raise InvalidRequest("bad_subject_id")
    with tenant_scope(pool, tenant_id) as conn:
        return _evaluate_all(conn, tenant_id, subject_id, context or {})


# --------------------------------------------------------------------------- experiments

def create_experiment(
    pool: Pool,
    tenant_id: str,
    *,
    experiment_key: str,
    variants: list[dict[str, Any]],
    salt: str | None = None,
) -> dict[str, Any]:
    """Create a draft experiment with its variants (CreateExperiment, PLT-02-R04).

    The salt is generated once here and never changes afterwards; see the column comment in the
    migration for why changing it would be the one unacceptable edit.
    """
    try:
        ev.validate_key(experiment_key)
    except ev.ValidationError as exc:
        raise InvalidRequest(exc.code) from None
    if len(variants) < 2:
        raise InvalidRequest("experiment_needs_two_variants")
    for variant in variants:
        if int(variant.get("weight", 0)) <= 0 or not str(variant.get("variant_key", "")).strip():
            raise InvalidRequest("bad_variant")

    with tenant_scope(pool, tenant_id) as conn:
        try:
            row = conn.execute(
                "INSERT INTO plt01.cfg_experiments (tenant_id, experiment_key, salt)"
                " VALUES (%s, %s, %s) RETURNING experiment_id, status, salt",
                (tenant_id, experiment_key, salt or secrets.token_hex(8)),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("experiment_key_exists") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tenant_not_found") from None
        except errors.CheckViolation:
            raise InvalidRequest("bad_experiment") from None
        assert row is not None
        experiment_id = row[0]
        for variant in variants:
            try:
                conn.execute(
                    "INSERT INTO plt01.cfg_variants"
                    " (tenant_id, experiment_id, variant_key, weight) VALUES (%s, %s, %s, %s)",
                    (tenant_id, experiment_id, variant["variant_key"], int(variant["weight"])),
                )
            except errors.UniqueViolation:
                raise Conflict("duplicate_variant_key") from None
    return {"experiment_id": str(experiment_id), "experiment_key": experiment_key,
            "status": row[1], "variants": [v["variant_key"] for v in variants]}


def set_experiment_status(
    pool: Pool, tenant_id: str, *, experiment_key: str, status: str
) -> dict[str, Any]:
    """Move an experiment between draft, running and completed (PLT-02-R04).

    Only draft -> running -> completed is admitted. A completed experiment does not restart: its
    recorded exposures describe a population that was shown a variant under one configuration, and
    resuming would mix two populations in one result set.
    """
    if status not in ("running", "completed"):
        raise InvalidRequest("bad_experiment_status")
    required = "draft" if status == "running" else "running"
    with tenant_scope(pool, tenant_id) as conn:
        current = conn.execute(
            "SELECT status FROM plt01.cfg_experiments WHERE experiment_key = %s FOR UPDATE",
            (experiment_key,),
        ).fetchone()
        if current is None:
            raise NotFound("experiment_not_found")
        if current[0] != required:
            raise Conflict("illegal_experiment_transition")
        row = conn.execute(
            """
            UPDATE plt01.cfg_experiments
            SET status = %s, version = version + 1,
                completed_at = CASE WHEN %s = 'completed' THEN now() ELSE NULL END
            WHERE experiment_key = %s RETURNING experiment_key, status, version
            """,
            (status, status, experiment_key),
        ).fetchone()
        assert row is not None
    return {"experiment_key": row[0], "status": row[1], "version": int(row[2])}


def allocate_experiment(
    pool: Pool, tenant_id: str, *, experiment_key: str, subject_id: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Assign a subject and record the exposure (AllocateExperiment, PLT-02-R04).

    Idempotent, and idempotent in the database rather than by convention: a subject already
    exposed keeps the variant that was recorded for it, even if the weights have since moved.
    Recomputing would retroactively change what an analysis believes a subject saw.
    """
    if not subject_id.strip():
        raise InvalidRequest("bad_subject_id")
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT experiment_id, status, salt FROM plt01.cfg_experiments"
            " WHERE experiment_key = %s",
            (experiment_key,),
        ).fetchone()
        if row is None:
            raise NotFound("experiment_not_found")
        experiment_id, status, salt = row

        recorded = conn.execute(
            "SELECT variant_key, occurred_at FROM plt01.cfg_exposures"
            " WHERE experiment_id = %s AND subject_id = %s",
            (experiment_id, subject_id),
        ).fetchone()
        if recorded is not None:
            return {"experiment_key": experiment_key, "subject_id": subject_id,
                    "variant": recorded[0], "exposed": True, "newly_exposed": False}

        variants = conn.execute(
            "SELECT variant_key, weight FROM plt01.cfg_variants WHERE experiment_id = %s",
            (experiment_id,),
        ).fetchall()
        assigned = ev.assign_variant(
            ev.Experiment(experiment_key=experiment_key, status=status, salt=salt),
            [ev.Variant(variant_key=v[0], weight=int(v[1])) for v in variants],
            subject_id=subject_id, tenant_id=tenant_id,
        )
        if assigned is None:
            return {"experiment_key": experiment_key, "subject_id": subject_id,
                    "variant": None, "exposed": False, "newly_exposed": False}
        try:
            conn.execute(
                "INSERT INTO plt01.cfg_exposures"
                " (tenant_id, experiment_id, subject_id, variant_key) VALUES (%s, %s, %s, %s)",
                (tenant_id, experiment_id, subject_id, assigned),
            )
        except errors.UniqueViolation:
            # A concurrent first exposure won the unique constraint. Assignment is deterministic,
            # so that row holds the same variant this call computed; the caller can simply repeat
            # the request and will be handed the recorded exposure. The transaction is already
            # aborted at this point, so re-reading it here is not available.
            raise Conflict("exposure_race") from None
        # The exposure row and the event commit together: an analysis that reads the events and
        # one that reads `cfg_exposures` must not be able to disagree about who saw what.
        # `correlation_id` comes from the caller when there is one -- the HTTP route always sends
        # it -- and is minted only for a caller that has none, which is a worker rather than a
        # request. A minted one traces to nothing, so it is the fallback and not the rule.
        events.append_event(
            conn, tenant_id, event_type="experiment.exposed", aggregate_type="experiment",
            aggregate_id=str(experiment_id),
            payload={"experiment_key": experiment_key,
                     # Hashed, never the raw string: `subject_id` here is caller-chosen free
                     # text, and an event is the one store this build cannot erase from.
                     "subject_hash": hashlib.sha256(subject_id.encode()).hexdigest(),
                     "variant": assigned},
            correlation_id=correlation_id or str(uuid4()),
        )
    return {"experiment_key": experiment_key, "subject_id": subject_id, "variant": assigned,
            "exposed": True, "newly_exposed": True}


def experiment_exposures(
    pool: Pool, tenant_id: str, *, experiment_key: str
) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT experiment_id FROM plt01.cfg_experiments WHERE experiment_key = %s",
            (experiment_key,),
        ).fetchone()
        if row is None:
            raise NotFound("experiment_not_found")
        rows = conn.execute(
            "SELECT subject_id, variant_key, occurred_at FROM plt01.cfg_exposures"
            " WHERE experiment_id = %s ORDER BY occurred_at, subject_id",
            (row[0],),
        ).fetchall()
    return [{"subject_id": r[0], "variant": r[1], "occurred_at": r[2].isoformat()} for r in rows]


# --------------------------------------------------------------------------- remote config

def bundle(
    pool: Pool,
    tenant_id: str,
    *,
    subject_id: str,
    context: dict[str, str] | None = None,
    brand_id: str | None = None,
    location_id: str | None = None,
) -> dict[str, Any]:
    """Everything a mobile app, kiosk or managed device needs in one read (PLT-02-R06).

    Values and flags are read in the same transaction, so a device never receives a configuration
    from before a change together with a flag from after it. `version` is the sum of the parts'
    versions: it changes whenever any input changes, which is all a cache validator has to do.
    """
    if not subject_id.strip():
        raise InvalidRequest("bad_subject_id")
    with tenant_scope(pool, tenant_id) as conn:
        values = _resolve_all(conn, brand_id, location_id)
        flags = _evaluate_all(conn, tenant_id, subject_id, context or {})
    version = sum(v["version"] or 0 for v in values.values()) + sum(
        f["version"] for f in flags.values()
    )
    return {"subject_id": subject_id, "brand_id": brand_id, "location_id": location_id,
            "configuration": values, "flags": flags, "version": version}

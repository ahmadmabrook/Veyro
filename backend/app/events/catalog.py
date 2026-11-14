"""MOD-010 DAT-01: the event catalogue, and what a payload is allowed to carry.

**Event types live in code, not in a table**, for the reason MOD-008 gives about permissions and
for one more besides. TSD paragraph 3217 names EventSchema an authoritative entity; this module
is it. An event type is a fact about what the software emits, so a per-tenant registry would let
two tenants disagree about what `invoice.issued` means with only the producing code able to
settle it -- and a consumer written against one tenant's idea of the schema would break silently
against another's. `evt_outbox` references these names and a CHECK constrains their shape. The
deviation is recorded in CLAUDE.md, as MOD-008's is.

The extra reason is compatibility. TSD paragraph 3245 requires schema changes to follow a
compatibility and consumer-migration policy. A policy enforced at the moment somebody edits this
file, where a reviewer sees it, is worth more than one enforced at a registration endpoint
somebody calls once; `_check_compatibility` runs at import, so an incompatible version cannot be
written down at all.

**A payload carries only its declared fields** (TSD paragraph 3244: "events contain only data
needed by approved consumers"). `validate_payload` refuses an undeclared key, which makes
accidental leakage into an event a loud failure rather than a quiet one: an event is fanned out
to consumers, archived, and replayed, so a field that should not be in it is in more places than
any other kind of mistake. And no declared field may be one MOD-008 classifies as restricted --
checked here at import, so the catalogue cannot name one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.authorization.catalog import SENSITIVE_FIELDS
from app.privacy.classification import KIND_CLASS, PURPOSE_REQUIRED_AT

#: `module.resource.action`-ish, but events are named for what happened rather than what was
#: asked, so the grammar is looser than a permission's: two or more dot-separated segments.
EVENT_NAME = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+$", re.ASCII)

STATUSES = ("active", "deprecated")


class CatalogError(ValueError):
    """An event type, version or payload this build does not define."""


@dataclass(frozen=True)
class EventType:
    name: str
    version: int
    owner_module: str
    classification: str
    """The data class of the payload as a whole, from TSD section 21.2. It decides where the
    event may be archived and how long it is kept; nothing enforces that here, because there is
    no archive, but the answer is recorded so the archive does not have to guess later."""
    fields: tuple[str, ...]
    """Exactly the payload keys this version carries. Not a minimum: `validate_payload` refuses
    an undeclared key and a missing one alike, because a consumer reading an absent field and a
    consumer ignoring an unexpected one are the same bug seen from two sides."""
    description: str
    status: str = "active"
    superseded_by: int | None = None


def _e(name: str, version: int, owner_module: str, classification: str,
       fields: tuple[str, ...], description: str, status: str = "active",
       superseded_by: int | None = None) -> tuple[tuple[str, int], EventType]:
    if not EVENT_NAME.fullmatch(name):
        raise CatalogError(f"{name!r} is not a dotted event name")
    if version < 1:
        raise CatalogError(f"{name!r} version {version} is not positive")
    if status not in STATUSES:
        raise CatalogError(f"{status!r} is not an event status")
    if classification not in ("public", "internal", "confidential", "restricted"):
        raise CatalogError(f"{classification!r} is not a data class")
    if not fields:
        raise CatalogError(f"{name!r} declares no payload fields")
    if len(set(fields)) != len(fields):
        raise CatalogError(f"{name!r} declares a field twice")
    for field in fields:
        kind = SENSITIVE_FIELDS.get(field)
        if kind is not None and KIND_CLASS.get(kind) == PURPOSE_REQUIRED_AT:
            # An event is fanned out, archived and replayed, so a restricted field in one is in
            # more places than the same field anywhere else, and the erasure registry reaches
            # none of them. Carry the identifier and let a consumer that holds the permission
            # read the value from the owning module.
            raise CatalogError(
                f"{name!r} carries {field!r}, which is {kind} data and must not travel in an "
                f"event payload; send an identifier instead"
            )
    return (name, version), EventType(
        name=name, version=version, owner_module=owner_module, classification=classification,
        fields=fields, description=description, status=status, superseded_by=superseded_by,
    )


#: Every event type this build emits, keyed by (name, version). The lists come from the TSD's
#: own "Published events" line for each module -- §10.9 (PLT-01), §10.10 (PLT-02), §10.11
#: (PLT-03), §10.13 (IAM-01), §10.15 (IAM-03), §10.47 (SEC-01) and §10.45 (DAT-01) -- rather
#: than from what the implementation happened to find convenient to emit.
EVENT_TYPES: dict[tuple[str, int], EventType] = dict([
    # ---------------------------------------------------------------- MOD-004, PLT-01
    _e("tenant.provisioned", 1, "MOD-004", "internal",
       ("tenant_id", "external_key", "display_name", "region"),
       "A tenant exists and can be configured"),
    _e("tenant.activated", 1, "MOD-004", "internal",
       ("tenant_id", "from_status"), "A tenant became usable"),
    _e("tenant.suspended", 1, "MOD-004", "internal",
       ("tenant_id", "from_status", "reason"), "A tenant was suspended"),
    _e("organization.updated", 1, "MOD-004", "internal",
       ("organization_id", "legal_name", "country_code"),
       "An organization was created or changed"),
    _e("brand.created", 1, "MOD-004", "internal",
       ("brand_id", "organization_id", "brand_name"), "A brand was created"),
    _e("location.opened", 1, "MOD-004", "internal",
       ("location_id", "brand_id", "location_name", "timezone"), "A location was opened"),
    # ---------------------------------------------------------------- MOD-005, PLT-02
    _e("configuration.changed", 1, "MOD-005", "internal",
       ("config_key", "scope_type", "scope_id", "version", "published_by"),
       "A configuration value was published or rolled back"),
    _e("feature_flag.evaluated", 1, "MOD-005", "internal",
       ("flag_key", "subject_id", "variant", "reason"),
       "A feature flag was evaluated for one subject"),
    # `subject_hash`, not `subject_id`. `cfg_exposures.subject_id` is free text a kiosk
    # chooses at AAL 1, and an independent reviewer put an email address, a date of birth, a
    # national id and a lab result in it -- which the name-based restricted-field rule above
    # cannot see, because the *value* is what carries the data. A fanned-out, archived,
    # replayable, un-erasable copy of that string is the worst place for it. The hash still
    # joins by equality, and a consumer that holds `config.experiment.allocate`'s read side can
    # resolve the subject from MOD-005 -- which is what this module's docstring prescribes for
    # restricted fields: send an identifier instead.
    _e("experiment.exposed", 1, "MOD-005", "internal",
       ("experiment_key", "subject_hash", "variant"),
       "A subject was assigned to an experiment variant"),
    _e("experiment.completed", 1, "MOD-005", "internal",
       ("experiment_key", "from_status"), "An experiment stopped running"),
    # ---------------------------------------------------------------- MOD-015, PLT-03
    _e("saas.subscription.started", 1, "MOD-015", "confidential",
       ("subscription_id", "plan_code", "plan_version", "currency", "billing_interval",
        "started_on"),
       "A tenant subscription began"),
    _e("saas.subscription.changed", 1, "MOD-015", "confidential",
       ("subscription_id", "change_kind", "to_plan_code", "to_plan_version", "to_status",
        "effective_on"),
       "A tenant subscription changed plan or lifecycle state"),
    _e("saas.usage.recorded", 1, "MOD-015", "internal",
       ("meter_code", "quantity", "occurred_at", "idempotency_key"),
       "Metered usage was accepted"),
    _e("saas.quota.reached", 1, "MOD-015", "internal",
       ("meter_code", "limit_quantity", "used_quantity", "hard_stop"),
       "A usage quota was reached or exceeded"),
    _e("saas.payment.failed", 1, "MOD-015", "confidential",
       ("subscription_id", "reason", "attempt"), "A subscription payment failed"),
    # ---------------------------------------------------------------- MOD-007, IAM-01
    _e("identity.created", 1, "MOD-007", "confidential",
       ("identity_id", "person_id"), "An identity was registered"),
    _e("authentication.succeeded", 1, "MOD-007", "confidential",
       ("identity_id", "device_id", "aal", "factors"), "Somebody signed in"),
    _e("authentication.failed", 1, "MOD-007", "confidential",
       ("identity_id", "device_id", "reason"), "A sign-in attempt was refused"),
    _e("session.revoked", 1, "MOD-007", "confidential",
       ("identity_id", "session_id", "reason"), "A session was ended before its expiry"),
    _e("passkey.registered", 1, "MOD-007", "confidential",
       ("identity_id", "passkey_id", "label"), "A passkey was enrolled"),
    _e("risk.challenge.required", 1, "MOD-007", "confidential",
       ("identity_id", "device_id", "kind"), "A sign-in was challenged"),
    # ---------------------------------------------------------------- MOD-008, IAM-03
    _e("role.assigned", 1, "MOD-008", "confidential",
       ("identity_id", "role_key", "scope_type", "scope_id", "granted_by"),
       "A role was granted to an identity"),
    _e("permission.denied", 1, "MOD-008", "confidential",
       ("identity_id", "action", "reason"), "An authorization decision refused an action"),
    _e("approval.requested", 1, "MOD-008", "confidential",
       ("request_id", "action", "requested_by", "required_approvals"),
       "An action that needs approval was requested"),
    _e("approval.completed", 1, "MOD-008", "confidential",
       ("request_id", "action", "state"), "An approval request was decided"),
    _e("audit_event.recorded", 1, "MOD-008", "confidential",
       ("sequence", "category", "action", "outcome"), "An audit entry was appended"),
    # ---------------------------------------------------------------- MOD-009, SEC-01
    _e("consent.granted", 1, "MOD-009", "confidential",
       ("subject_id", "consent_type", "consent_version_id", "signed_at", "source"),
       "A subject consented to something"),
    _e("consent.withdrawn", 1, "MOD-009", "confidential",
       ("subject_id", "consent_type", "consent_version_id", "signed_at"),
       "A subject withdrew a consent"),
    _e("data_subject_request.created", 1, "MOD-009", "confidential",
       ("request_id", "subject_id", "request_type", "due_at"),
       "A data subject request was opened"),
    _e("data_subject_request.completed", 1, "MOD-009", "confidential",
       ("request_id", "subject_id", "request_type", "has_residue"),
       "A data subject request was fulfilled"),
    _e("security.alert.detected", 1, "MOD-009", "confidential",
       ("incident_id", "severity", "category", "personal_data_involved"),
       "A security incident was recorded"),
    # ---------------------------------------------------------------- MOD-010, DAT-01
    _e("event.delivery.failed", 1, "MOD-010", "internal",
       ("event_id", "consumer", "attempts", "reason"),
       "A delivery was quarantined after exhausting its attempts"),
    _e("event.replayed", 1, "MOD-010", "internal",
       ("job_id", "consumer", "events_replayed", "side_effects"),
       "A replay job finished"),
    _e("event_schema.changed", 1, "MOD-010", "internal",
       ("event_type", "version", "status"),
       "An event type gained a version or was deprecated"),
    # ---------------------------------------------------------------- MOD-011, REL-02
    # Paragraph 3513's four, and all four are produced in this build. Each carries the owner and
    # the runbook where it has one, because paragraph 3504 makes actionability a control and an
    # alert whose recipient has to go and look up who owns it is one that waits.
    _e("synthetic_check.failed", 1, "MOD-011", "internal",
       ("check_id", "check_key", "duration_ms", "detail"),
       "A synthetic probe reported a failure"),
    # `dimensions` carries which series breached. Without it the page names a metric and the
    # recipient has no way to tell which consumer or which check failed, which is the
    # actionability control at paragraph 3504 defeated by an omission.
    _e("performance_budget.exceeded", 1, "MOD-011", "internal",
       ("objective_id", "objective_key", "kind", "metric_key", "dimensions", "observed",
        "threshold", "comparison", "owner", "runbook_ref"),
       "An objective was evaluated over its window and breached"),
    _e("capacity.threshold.reached", 1, "MOD-011", "internal",
       ("forecast_id", "resource", "horizon_days", "headroom_bp", "projected_value"),
       "A capacity forecast projects less headroom than the alert threshold"),
    _e("cost.anomaly.detected", 1, "MOD-011", "confidential",
       ("budget_id", "budget_key", "period_start", "threshold_bp", "consumed_bp",
        "spent_minor", "budget_minor", "currency", "owner"),
       "Spend against a budget crossed a notification threshold"),
    # ---------------------------------------------------------------- MOD-012, ECO-02
    # Paragraph 3042's list, less `marketplace.listing.approved`, which belongs to the V2
    # marketplace slice this module does not build. **No payload carries a vault reference**:
    # a credential reference is the one field in this module that names where a secret lives,
    # and an event is fanned out, archived and replayed into more places than any other row.
    _e("integration.installed", 1, "MOD-012", "internal",
       ("install_id", "definition_key", "definition_version", "criticality"),
       "A tenant installed an integration definition"),
    _e("integration.connected", 1, "MOD-012", "internal",
       ("install_id", "connection_id", "definition_key", "region", "granted_scopes"),
       "A connection to a provider account was authorized"),
    _e("integration.sync.failed", 1, "MOD-012", "internal",
       ("run_id", "connection_id", "resource", "attempts", "status", "reason"),
       "A connector run failed, and whether it will be retried or was quarantined"),
    _e("credential.expiring", 1, "MOD-012", "confidential",
       ("credential_ref_id", "connection_id", "install_id", "days_remaining", "expired"),
       "A credential reference is inside its rotation window or has expired"),
    _e("integration.uninstalled", 1, "MOD-012", "internal",
       ("install_id", "definition_key", "reason", "connections_revoked"),
       "A tenant removed an integration, revoking every connection it held"),
])


def _check_compatibility() -> None:
    """Run at import. A new version of an event type may add fields; it may not drop one.

    A consumer written against version n reads the fields version n declared. If version n+1
    stops carrying one, that consumer breaks the moment a producer upgrades -- silently, because
    the field is simply absent rather than wrong. Adding is safe: a consumer ignores what it
    does not know about. This is the whole of the compatibility policy, and it is checked where
    somebody would write the incompatible change rather than where they would deploy it.
    """
    by_name: dict[str, list[EventType]] = {}
    for event in EVENT_TYPES.values():
        by_name.setdefault(event.name, []).append(event)
    for name, versions in by_name.items():
        versions.sort(key=lambda e: e.version)
        numbers = [e.version for e in versions]
        if numbers != list(range(1, len(numbers) + 1)):
            raise CatalogError(f"{name!r} versions are not contiguous from 1: {numbers}")
        for earlier, later in zip(versions, versions[1:], strict=False):
            dropped = set(earlier.fields) - set(later.fields)
            if dropped:
                raise CatalogError(
                    f"{name!r} v{later.version} drops {sorted(dropped)} that v{earlier.version} "
                    f"declared; a consumer on v{earlier.version} would read nothing there"
                )
        for event in versions:
            if event.status == "deprecated" and event.superseded_by is None:
                raise CatalogError(
                    f"{name!r} v{event.version} is deprecated and names no successor, so a "
                    f"consumer has nowhere to migrate to"
                )
            if event.superseded_by is not None and (name, event.superseded_by) not in EVENT_TYPES:
                raise CatalogError(
                    f"{name!r} v{event.version} is superseded by v{event.superseded_by}, "
                    f"which does not exist"
                )


_check_compatibility()


def require_event(name: str, version: int) -> EventType:
    """Look an event type up, refusing one this build does not define.

    An unknown event type cannot be appended to the outbox. A typo in a producer therefore fails
    at the moment it is written rather than filling the outbox with something no consumer has a
    subscription for and no archive knows how to read.
    """
    try:
        return EVENT_TYPES[(name, version)]
    except KeyError:
        raise CatalogError(
            f"{name!r} v{version} is not an event type this build defines"
        ) from None


def latest(name: str) -> EventType:
    """The highest active version of an event type. What a producer emits unless it says."""
    candidates = [e for (n, _), e in EVENT_TYPES.items() if n == name and e.status == "active"]
    if not candidates:
        raise CatalogError(f"{name!r} has no active version")
    return max(candidates, key=lambda e: e.version)


def validate_payload(name: str, version: int, payload: dict[str, object]) -> None:
    """Refuse a payload that is not exactly the declared fields.

    Both directions. An undeclared key is data travelling further than anybody approved -- into
    every consumer, the archive and every replay. A missing key is a consumer reading `None`
    from a field the schema promised, which is the failure that shows up weeks later in whatever
    read the value.
    """
    event = require_event(name, version)
    supplied = set(payload)
    declared = set(event.fields)
    if supplied - declared:
        raise CatalogError(
            f"{name!r} v{version} does not declare {sorted(supplied - declared)}"
        )
    if declared - supplied:
        raise CatalogError(
            f"{name!r} v{version} requires {sorted(declared - supplied)}"
        )


def owner_module(name: str, version: int) -> str:
    return require_event(name, version).owner_module


def classification(name: str, version: int) -> str:
    return require_event(name, version).classification


def deprecated_types() -> tuple[EventType, ...]:
    """What a consumer still reading these has to migrate off, and where to."""
    return tuple(e for e in EVENT_TYPES.values() if e.status == "deprecated")

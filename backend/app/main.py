"""Veyro API: the HTTP surface over all four planes.

**Every tenant-plane route is gated.** A caller presents a bearer session, and `permit` asks
MOD-008 whether that identity holds the route's permission at the request's scope and whether the
session's assurance level is high enough for the action's class. A refusal is written to the audit
log by the authorization service itself, before the error leaves it. `/healthz` and the MOD-007
authentication routes are the exceptions, because they are how a caller gets a session in the
first place.

**The platform plane is not.** `/platform/*` provisions tenants, moves them through their
lifecycle and reads their history, and none of it asks for anything. Anyone who can reach that
surface can create a tenant, and can **suspend or archive an existing one** -- denial of service
against a live customer, not merely self-service signup. Authenticating it is a different problem
from authorizing a tenant's own users: there is no platform identity to be yet, and inventing one
here would be inventing product.

**`X-Veyro-Tenant` is still a claim.** It is read and shape-checked, and nothing proves the caller
belongs to the tenant it names. What has changed is that naming a tenant now buys nothing on its
own: with no session the gate refuses, and `authz.bootstrap` -- the one call that mints the first
role -- refuses once any assignment exists. Isolation never rested on the header being honest. It
rests on row-level security, which confines whatever tenant the header names and returns nothing
at all when it names none.

The environments this service accepts are local, development and staging; there is no production
value, so the claim never reaches real member data.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from datetime import time as clock_time
from time import time
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app import db
from app.access import service as access
from app.authorization import catalog as authz_catalog
from app.authorization import gate as authz_gate
from app.authorization import service as authz
from app.billing import service as billing
from app.booking import service as booking
from app.catalog import service as catalog
from app.commercial import service as commercial
from app.config import Settings, load_settings
from app.configuration import service as config
from app.crm import pipeline as crm_pipeline
from app.crm import service as crm
from app.devices import service as devices
from app.errors import InvalidRequest, NotFound, ServiceError, TooManyRequests
from app.events import service as events
from app.identity import policy as identity_policy
from app.identity import secrets
from app.identity import service as identity
from app.identity import webauthn as identity_webauthn
from app.integrations import service as integrations
from app.ledger import service as ledger
from app.notifications import service as notifications
from app.observability import metrics as obs_metrics
from app.observability import ratelimit
from app.observability import service as observability
from app.people import service as people
from app.privacy import service as privacy
from app.scheduling import service as scheduling
from app.tasks import service as tasks
from app.tenancy import service
from app.worker import registry as worker_registry

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", re.ASCII
)

#: Consent provenances only a member of staff is in a position to assert: both say a signed
#: document exists off-system and somebody keyed it in. A self-service session claiming one is
#: writing an insert-only record that reads as evidence nobody produced, so it is charged the
#: `record_on_behalf` permission like naming another subject is.
STAFF_ASSERTED_SOURCES = frozenset({"staff_entry", "paper_import"})


class ProvisionTenantBody(BaseModel):
    external_key: str
    display_name: str
    region: str
    actor_id: str
    correlation_id: str
    idempotency_key: str
    expected_version: int | None = None


class TransitionBody(BaseModel):
    actor_id: str
    correlation_id: str
    expected_version: int | None = None


class OrganizationBody(BaseModel):
    """`correlation_id` is optional and threaded through to the event MOD-010 appends.

    Without it the route minted one for `permit` and the producer minted a second, so the same
    request produced two unrelated correlation ids and `/events/trace` could never join an
    organization creation to the decision that authorized it -- which is the whole purpose of
    the trace route. Optional rather than required, because requiring it would break every
    existing caller of a route that has never asked for one.
    """

    legal_name: str
    country_code: str = Field(min_length=2, max_length=2)
    correlation_id: str | None = None


class BrandBody(BaseModel):
    organization_id: str
    brand_name: str


class LegalEntityBody(BaseModel):
    """The entity that invoices. PLT-01-R02's hierarchy leaf, reachable at last."""

    organization_id: str
    registered_name: str = Field(min_length=1, max_length=200)
    tax_number: str | None = Field(default=None, min_length=1, max_length=64)
    correlation_id: str


class LocationBody(BaseModel):
    brand_id: str
    location_name: str
    timezone: str


class DefinitionBody(BaseModel):
    config_key: str
    value_type: str
    default_value: Any
    owner_module: str
    validation: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class PublishValueBody(BaseModel):
    config_key: str
    value: Any
    scope_type: str = "tenant"
    brand_id: str | None = None
    location_id: str | None = None
    published_by: str
    correlation_id: str
    expected_version: int | None = None


class RollbackBody(BaseModel):
    scope_type: str = "tenant"
    brand_id: str | None = None
    location_id: str | None = None
    to_version: int
    published_by: str
    correlation_id: str


class PreviewBody(BaseModel):
    config_key: str
    value: Any
    scope_type: str = "tenant"
    brand_id: str | None = None
    location_id: str | None = None


class FeaturePolicyBody(BaseModel):
    enabled: bool
    default_variant: str = "off"
    description: str | None = None
    rules: list[dict[str, Any]] = Field(default_factory=list)
    expected_version: int | None = None


class KillSwitchBody(BaseModel):
    engaged: bool
    reason: str | None = None


class ExperimentBody(BaseModel):
    experiment_key: str
    variants: list[dict[str, Any]]


class ExperimentStatusBody(BaseModel):
    status: str


class AllocateBody(BaseModel):
    subject_id: str
    # Optional, unlike the command bodies above, because this one is called by a device on a
    # member's first screen rather than by an operator running a command -- but it writes a
    # permanent `cfg_exposures` row, so a caller that does carry a correlation id should be able
    # to join the gate's audit entry to it.
    correlation_id: str | None = None


def evaluation_context(request: Request) -> dict[str, str]:
    """Targeting attributes arrive as query parameters, minus the two the route itself owns.

    PLT-02-R02 names seven dimensions (environment, tenant, plan, brand, location, user, role).
    They are not enumerated here on purpose: a caller sending `cohort` or `channel` should be able
    to target on it without this file changing, and the evaluator treats every attribute the same
    way. `subject_id` and the scope parameters are excluded because they are arguments, not
    attributes to match on.
    """
    reserved = {"subject_id", "brand_id", "location_id"}
    return {k: v for k, v in request.query_params.items() if k not in reserved}


class PlanBody(BaseModel):
    plan_code: str
    plan_version: int
    edition: str
    currency: str = Field(min_length=3, max_length=3)
    region: str
    billing_interval: str
    base_price_minor: int
    trial_days: int = 0
    contract_months: int | None = None
    prices: list[dict[str, Any]] = Field(default_factory=list)
    entitlements: list[dict[str, Any]] = Field(default_factory=list)


class PlanStatusBody(BaseModel):
    status: str


class StartSubscriptionBody(BaseModel):
    plan_code: str
    plan_version: int | None = None
    actor_id: str
    correlation_id: str
    start_on: date | None = None
    partner_code: str | None = None
    revenue_share_bp: int | None = None


class SubscriptionCommandBody(BaseModel):
    command: str
    actor_id: str
    correlation_id: str
    reason: str | None = None
    expected_version: int | None = None


class ChangePlanBody(BaseModel):
    plan_code: str
    plan_version: int | None = None
    actor_id: str
    correlation_id: str
    effective_on: date | None = None
    in_use: dict[str, int] = Field(default_factory=dict)
    acknowledge_reductions: bool = False


class EntitlementGrantBody(BaseModel):
    feature_code: str
    limit_value: int | None = None
    unlimited: bool = False


class MeterBody(BaseModel):
    meter_code: str
    unit: str
    aggregation: str = "sum"


class QuotaBody(BaseModel):
    period: str
    limit_quantity: int
    overage_allowed: bool = False
    hard_stop: bool = False


class UsageBody(BaseModel):
    meter_code: str
    quantity: int
    idempotency_key: str
    actor_id: str
    correlation_id: str
    occurred_at: datetime | None = None
    corrects_record_id: str | None = None


class InvoiceBody(BaseModel):
    actor_id: str
    correlation_id: str
    tax_rate_bp: int | None = None


class CreditNoteBody(BaseModel):
    amount_minor: int
    reason: str
    actor_id: str
    correlation_id: str


class RegisterIdentityBody(BaseModel):
    display_name: str
    correlation_id: str
    email: str | None = None
    phone: str | None = None
    password: str | None = None
    person_id: str | None = None


class PasswordBody(BaseModel):
    password: str
    correlation_id: str
    current_password: str | None = None


class LoginBody(BaseModel):
    identifier: str
    password: str
    correlation_id: str
    device_fingerprint: str | None = None
    device_label: str | None = None


class LoginChallengeBody(BaseModel):
    identifier: str
    challenge: str
    recovery_code: str
    correlation_id: str


class StepUpBody(BaseModel):
    """Credentials, never factor names.

    The first version of this body carried a `factors: list[str]`, which the service believed.
    Anyone could post `["passkey_hardware"]` and be handed the highest assurance level with
    nothing presented. What a caller holds is now proved, not declared.
    """

    challenge: str
    correlation_id: str
    password: str | None = None
    recovery_code: str | None = None


class RecoverBody(BaseModel):
    identifier: str
    code: str
    correlation_id: str


class RevokeBody(BaseModel):
    correlation_id: str
    reason: str = "revoked_by_user"


class CorrelationBody(BaseModel):
    """`correlation_id` travels in the body, not the query string, so access logs do not
    keep it."""

    correlation_id: str


class IdentityStatusBody(BaseModel):
    """Suspend, deactivate or reinstate somebody else's identity.

    `reason` is required and bounded here rather than only in the service: the row it lands on
    is insert-only and it is the only record of why somebody was shut out.
    """

    status: str
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class RecoveryCodesBody(BaseModel):
    correlation_id: str
    current_password: str | None = None


class PasskeyBody(BaseModel):
    webauthn_credential_id: str
    public_key: str
    correlation_id: str
    label: str | None = None
    aaguid: str | None = None
    transports: list[str] | None = None
    backed_up: bool = False


class AssertionBody(BaseModel):
    sign_count: int
    correlation_id: str


class PasskeyChallengeBody(BaseModel):
    identifier: str
    correlation_id: str


class PasskeyLoginBody(BaseModel):
    """One assertion, as the browser hands it over.

    Every binary field is base64url, which is what `PublicKeyCredential.toJSON()` produces --
    and `_b64` is strict about it, so a value written with the standard alphabet is a 422
    rather than a signature that verifies over different bytes.
    """

    identifier: str
    challenge: str
    credential_id: str
    client_data_json: str
    authenticator_data: str
    signature: str
    correlation_id: str
    device_fingerprint: str | None = None
    device_label: str | None = None


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    """Read the session token from an Authorization header and nothing else.

    A token in a query string ends up in access logs, browser history and referrer headers, so
    this is the only place a session token is accepted.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise InvalidRequest("missing_bearer_token")
    token = authorization[7:].strip()
    if not token:
        raise InvalidRequest("missing_bearer_token")
    return token


BearerToken = Annotated[str, Depends(bearer_token)]


def _b64(value: str, field: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidRequest(f"bad_{field}") from None


def _b64url(value: str, field: str) -> bytes:
    """Strict unpadded base64url, which is the only encoding WebAuthn speaks.

    **Every binary field in a WebAuthn ceremony is base64url** -- that is what
    `PublicKeyCredential.toJSON()` produces and what `clientDataJSON` carries its challenge
    as. `_b64` above is *standard* base64, and the two alphabets agree on most byte strings
    and differ on the rest, so accepting either would mean one value decoding to two
    different byte strings depending on which decoder saw it. In a challenge comparison that
    is a replay window, which is why `webauthn.b64url_decode` is strict and why this wraps it
    rather than reimplementing the leniency.
    """
    try:
        return identity_webauthn.b64url_decode(value)
    except identity_webauthn.WebAuthnError:
        raise InvalidRequest(f"bad_{field}") from None


class RoleBody(BaseModel):
    role_key: str
    display_name: str
    correlation_id: str
    permissions: list[str] = Field(default_factory=list)
    description: str | None = None


class RolePermissionsBody(BaseModel):
    permissions: list[str]
    correlation_id: str


class AssignRoleBody(BaseModel):
    identity_id: str
    role_key: str
    correlation_id: str
    scope_type: str = "tenant"
    brand_id: str | None = None
    location_id: str | None = None
    expires_at: datetime | None = None


class AuthzPolicyBody(BaseModel):
    policy_key: str
    effect: str
    action: str
    correlation_id: str
    match: dict[str, str] = Field(default_factory=dict)
    masked_fields: list[str] = Field(default_factory=list)
    priority: int = 100
    description: str | None = None


class ApprovalStageBody(BaseModel):
    """One step of a staged approval: N holders of one permission.

    **No ordinal.** The order is the list's, because a caller-supplied ordinal admits a gap --
    and `sequential` walks "every earlier stage", so a gap would make "earlier" depend on how
    somebody numbered a row rather than on the order they wrote.
    """

    required_permission: str
    required_approvals: int = Field(default=1, ge=1, le=20)


class ApprovalPolicyBody(BaseModel):
    """**`stages` is AUT-02-R05's "sequential, parallel", and absent means single-stage** --
    the existing meaning, whose stage is `required_permission` and `required_approvals`. Those
    two stay required so a staged policy still says what one approver of it looks like."""

    action: str
    required_permission: str
    correlation_id: str
    threshold_minor: int = 0
    required_approvals: int = 1
    separation_of_duties: bool = True
    stages: list[ApprovalStageBody] = Field(default_factory=list, max_length=8)
    sequential: bool = False


class ApprovalRequestBody(BaseModel):
    action: str
    resource_type: str
    correlation_id: str
    resource_id: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    reason: str | None = None


class ApprovalDecisionBody(BaseModel):
    """`on_behalf_of` is AUT-02-R05's delegation: the identity whose approval authority this
    decision carries. It is checked against a live delegation by the schema, so a caller
    cannot claim one -- "a cited authority is the authority, or it is decoration"."""

    decision: str
    correlation_id: str
    reason: str | None = None
    on_behalf_of: str | None = None
    # **Which step this decision is for**, defaulted to the single-stage case so every
    # existing caller keeps working. The request's own snapshot says which stages it has, and
    # both this module and a trigger refuse one it has not got.
    stage_ordinal: int = Field(default=1, ge=1, le=8)


class ApprovalDelegationBody(BaseModel):
    """**No `from_identity_id`.** The delegator is the session, because a body field here
    would let anybody delegate anybody's authority to themselves -- the whole approval
    machinery bought with one uuid. Derive a scope, never accept one."""

    to_identity_id: str
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class AccessReviewBody(BaseModel):
    title: str
    correlation_id: str


class ReviewItemBody(BaseModel):
    decision: str
    correlation_id: str
    note: str | None = None


# ------------------------------------------------------------------ MOD-010 request bodies


class SubscriptionBody(BaseModel):
    consumer: str
    event_type: str
    correlation_id: str
    replay_safety: str = "suppress"
    max_attempts: int = Field(default=5, ge=1, le=100)


class ReplayBody(BaseModel):
    """`side_effects` defaults to `suppress` here as well as in the schema.

    Two defaults for one value is usually a smell. Here it is deliberate: a caller that omits
    the field and a caller that sends the column's default must get the same answer, and the
    answer has to be the safe one at both ends. TSD paragraph 200.
    """

    consumer: str
    event_types: list[str]
    from_time: datetime
    to_time: datetime
    correlation_id: str
    side_effects: str = "suppress"
    side_effects_reason: str | None = None


class ReleaseDeadLetterBody(BaseModel):
    reason: str
    correlation_id: str


# ------------------------------------------------------------------ MOD-009 request bodies


class PurposeBody(BaseModel):
    purpose_code: str
    description: str
    lawful_basis: str
    controller_role: str
    data_classes: list[str]
    correlation_id: str


class ConsentDefinitionBody(BaseModel):
    consent_type: str
    purpose_id: str
    correlation_id: str
    requires_guardian: bool = False
    withdrawable: bool = True


class ConsentVersionBody(BaseModel):
    consent_type: str
    language: str
    document_ref: str
    document_hash: str
    effective_from: datetime
    correlation_id: str


class ConsentRecordBody(BaseModel):
    """`subject_id` is optional and defaults to the session's own identity.

    Naming somebody else is a separate, stronger permission -- see the catalogue note on
    `privacy.consent.record_on_behalf`. Defaulting rather than requiring it means the ordinary
    case, a member agreeing to something on their own phone, cannot name the wrong person.
    """

    consent_type: str
    language: str = "en"
    signed_at: datetime
    source: str
    correlation_id: str
    subject_id: str | None = None
    guardian_subject_id: str | None = None
    evidence_hash: str | None = None
    evidence_ref: str | None = None
    consent_version_id: str | None = None


class ConsentWithdrawalBody(BaseModel):
    consent_type: str
    signed_at: datetime
    source: str
    correlation_id: str
    subject_id: str | None = None
    evidence_ref: str | None = None


class RetentionPolicyBody(BaseModel):
    resource_type: str
    data_class: str
    retention_days: int
    legal_basis: str
    region: str
    correlation_id: str


class LegalHoldBody(BaseModel):
    reason: str
    reference: str
    correlation_id: str
    subject_id: str | None = None
    resource_type: str | None = None


class ReleaseHoldBody(BaseModel):
    release_reason: str
    correlation_id: str


class DsarBody(BaseModel):
    """`response_days` has no default here either; see `app.privacy.dsar`."""

    subject_id: str
    request_type: str
    response_days: int
    correlation_id: str
    received_at: datetime | None = None


class RefuseDsarBody(BaseModel):
    reason: str
    correlation_id: str


class IncidentBody(BaseModel):
    severity: str
    category: str
    summary: str
    detected_at: datetime
    personal_data_involved: str
    correlation_id: str
    notification_assessment: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    supersedes_incident_id: str | None = None


class IntegrationDefinitionBody(BaseModel):
    """A draft integration definition version, registered on the platform plane.

    `config_fields` declares a type per field and **there is no secret type**: a credential
    goes through a credential reference, which names where a secret lives rather than holding
    one. See `app/integrations/contract.py`.
    """

    definition_key: str
    version: int = Field(ge=1, le=2_000_000_000)
    provider: str
    display_name: str
    criticality: str
    support_owner: str
    description: str
    capabilities: list[str]
    scopes: list[str] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    config_fields: list[dict[str, Any]] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)


class InstallBody(BaseModel):
    definition_key: str
    correlation_id: str
    version: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ConfigureInstallBody(BaseModel):
    correlation_id: str
    config: dict[str, Any] | None = None
    fallback_plan: str | None = None
    reconciliation_plan: str | None = None
    exit_plan: str | None = None


class UninstallBody(BaseModel):
    reason: str
    correlation_id: str


class ConnectionBody(BaseModel):
    """`vault_ref` names a secret kept somewhere this build cannot read, and never holds one."""

    install_id: str
    external_account_ref: str
    region: str
    granted_scopes: list[str]
    vault_ref: str
    correlation_id: str
    issued_at: datetime | None = None
    expires_at: datetime | None = None


class ValidateConnectionBody(BaseModel):
    evidence: str
    correlation_id: str


class RevokeConnectionBody(BaseModel):
    reason: str
    correlation_id: str


class RotateCredentialBody(BaseModel):
    vault_ref: str
    correlation_id: str
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    scopes: list[str] | None = None


class CursorBody(BaseModel):
    """No `conflict_policy`. It has its own route and its own permission.

    Carrying it here handed the routine, AAL-1 `integrations.sync.run` permission the decision
    that `/integrations/cursors/policy` charges a financial, stepped-up
    `integrations.sync.reset` for -- and since the default is `manual`, the machine permission
    was the one actually choosing whether a provider's copy may overwrite a tenant's records.
    """

    connection_id: str
    resource: str
    position: str
    observed_at: datetime
    correlation_id: str


class CursorResetBody(BaseModel):
    connection_id: str
    resource: str
    position: str
    observed_at: datetime
    reason: str
    correlation_id: str


class ConflictPolicyBody(BaseModel):
    connection_id: str
    resource: str
    policy: str
    correlation_id: str


class StartRunBody(BaseModel):
    connection_id: str
    resource: str
    correlation_id: str
    # Bounded like MOD-010's `SubscriptionBody.max_attempts`, which is the same field with the
    # same meaning 230 lines up this file. Unbounded, it overflowed `integer` into a
    # `NumericValueOutOfRange` -- a `DataError`, not the `CheckViolation` the handler caught.
    max_attempts: int = Field(default=5, ge=1, le=100)


class FinishRunBody(BaseModel):
    #: Bounded at the boundary. These are reachable at AAL-1 with the routine
    #: `integrations.sync.run` permission, and a negative or oversized count reached psycopg as
    #: a 500 rather than a 422.
    records_read: int = Field(ge=0, le=10**12)
    records_written: int = Field(ge=0, le=10**12)
    correlation_id: str
    conflicts: int = Field(default=0, ge=0, le=2_000_000_000)


class FailRunBody(BaseModel):
    error: str
    correlation_id: str


class ReleaseRunBody(BaseModel):
    reason: str
    correlation_id: str


class ReconciliationBody(BaseModel):
    local_count: int = Field(ge=0, le=10**12)
    provider_count: int = Field(ge=0, le=10**12)
    matched: int = Field(ge=0, le=10**12)
    correlation_id: str


class TemplateBody(BaseModel):
    """A draft notification template version.

    The category may not be changed by a later version, and no request field overrides it: a
    caller able to declare a campaign `transactional` would escape both the consent requirement
    and the recipient's opt-out, which is paragraph 2463's control defeated by a body field.
    """

    template_key: str
    version: int = Field(ge=1, le=2_000_000_000)
    category: str
    channel: str
    locale: str
    body: str
    correlation_id: str
    subject: str = ""
    variables: list[str] = Field(default_factory=list)


class PreferenceBody(BaseModel):
    recipient_id: str
    category: str
    channel: str
    correlation_id: str
    allowed: bool = True
    quiet_from: clock_time | None = None
    quiet_until: clock_time | None = None
    quiet_timezone: str | None = None
    daily_cap: int | None = Field(default=None, ge=0, le=10_000)
    digest_mode: str = "immediate"


class ChannelPolicyBody(BaseModel):
    channel: str
    correlation_id: str
    enabled: bool = True
    fallback_channel: str | None = None
    cost_per_message_minor: int | None = Field(default=None, ge=0, le=10**12)
    # `char(3)`. Unbounded, psycopg raises StringDataRightTruncation -- a DataError, not the
    # CheckViolation the handlers catch -- so a four-letter currency answered 500.
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class NotificationBody(BaseModel):
    """Address digests, never addresses -- and **one per channel**.

    This module holds no contact data: the caller computes the digest from the address it
    already has, so a bounce can be remembered and a recipient matched without a second copy of
    everyone's email beside the one MOD-007 and MOD-014 own.

    A map rather than a single value, because the channel policy may send this somewhere other
    than the template's own channel. A single digest meant the fallback carried the digest
    computed for the channel it fell back *from*, so the suppression check ran against a key
    the other channel can never produce and the eventual bounce was recorded against a key no
    later request would ever match. The map has to carry the channel actually used; a fallback
    to a channel the caller gave no digest for is refused rather than guessed at.
    """

    template_key: str
    recipient_id: str
    #: Channel to the SHA-256 of `channel:address`, from `delivery.address_digest`.
    address_digests: dict[str, str] = Field(min_length=1, max_length=8)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str
    variables: dict[str, str] = Field(default_factory=dict)
    locale: str | None = Field(default=None, max_length=35)
    priority: str = "normal"
    bypass_policy_ref: str | None = Field(default=None, max_length=200)


class OutcomeBody(BaseModel):
    outcome: str
    correlation_id: str
    #: The provider's own text. It stays on `ntf_deliveries.last_error` and is **not** put into
    #: an event: an SMTP rejection quotes the address it rejected, and the event outbox is the
    #: one store no erasure in this build can reach.
    error: str | None = Field(default=None, max_length=2000)
    provider_ref: str | None = Field(default=None, max_length=200)


class SuppressionBody(BaseModel):
    channel: str
    address_digest: str
    #: Only `unsubscribed`; the service refuses the rest and says why. A bounce or a complaint
    #: is written by `record_outcome` from a reported delivery, because only a release can
    #: undo one and a release refuses anything else.
    reason: str
    correlation_id: str
    detail: str | None = Field(default=None, max_length=1000)


class RebindBody(BaseModel):
    """Move a recipient's address binding on one channel.

    Stronger than requesting a notification, because it is the one act that moves a person away
    from a suppression recorded against them.
    """

    channel: str
    address_digest: str
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class ReleaseSuppressionBody(BaseModel):
    reason: str
    correlation_id: str


class PersonContactBody(BaseModel):
    """A contact point inside a CreatePerson command, which carries its own correlation id."""

    kind: str
    value: str = Field(min_length=1, max_length=320)
    is_primary: bool = False


class ContactPointBody(PersonContactBody):
    """The same, as a command of its own."""

    correlation_id: str


class PersonBody(BaseModel):
    """CreatePerson, with the contact points in the same command.

    A person with no way to reach them is a record nobody can use, and two commands would leave
    a window where the duplicate detector sees somebody with no signals at all.
    """

    legal_name: str = Field(min_length=1, max_length=200)
    correlation_id: str
    preferred_name: str | None = Field(default=None, max_length=200)
    date_of_birth: date | None = None
    contacts: list[PersonContactBody] = Field(default_factory=list, max_length=12)


class PersonUpdateBody(BaseModel):
    """UpdateProfile's person half. `expected_version` is required, not optional.

    Paragraph 1331 asks for optimistic concurrency and two front-desk staff editing one profile
    is the ordinary case; a caller that could omit the version would be a caller whose write
    silently discards somebody else's.
    """

    expected_version: int = Field(ge=1, le=10**9)
    correlation_id: str
    legal_name: str | None = Field(default=None, max_length=200)
    preferred_name: str | None = Field(default=None, max_length=200)
    date_of_birth: date | None = None


class IdentityLinkBody(BaseModel):
    identity_id: str
    correlation_id: str


class TenantProfileBody(BaseModel):
    correlation_id: str
    expected_version: int | None = Field(default=None, ge=1, le=10**9)
    brand_id: str | None = None
    location_id: str | None = None
    acquisition_source: str | None = Field(default=None, max_length=200)
    preferred_language: str | None = Field(default=None, max_length=10)
    notes_internal: str | None = Field(default=None, max_length=2000)


class MemberProfileBody(BaseModel):
    correlation_id: str
    lifecycle_state: str = "lead"
    member_number: str | None = Field(default=None, max_length=60)
    joined_on: date | None = None


class LifecycleBody(BaseModel):
    to_state: str
    expected_version: int = Field(ge=1, le=10**9)
    correlation_id: str
    reason: str | None = Field(default=None, max_length=500)


class StaffProfileBody(BaseModel):
    correlation_id: str
    job_title: str | None = Field(default=None, max_length=120)
    location_id: str | None = None
    started_on: date | None = None


class StaffEndBody(BaseModel):
    expected_version: int = Field(ge=1, le=10**9)
    ended_on: date
    correlation_id: str


class RelationshipBody(BaseModel):
    kind: str
    from_person_id: str
    to_person_id: str
    correlation_id: str


class ReasonBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class NoteBody(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    correlation_id: str
    note_class: str = "general"


class TagBody(BaseModel):
    tag_key: str = Field(min_length=2, max_length=63)
    display_name: str = Field(min_length=1, max_length=120)
    correlation_id: str
    is_internal: bool = False


class ApplyTagBody(BaseModel):
    tag_id: str
    correlation_id: str


class CustomFieldOptionBody(BaseModel):
    value: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=120)


class CustomFieldBody(BaseModel):
    field_key: str = Field(min_length=2, max_length=63)
    display_name: str = Field(min_length=1, max_length=120)
    value_type: str
    correlation_id: str
    sensitivity: str = "none"
    is_required: bool = False
    options: list[CustomFieldOptionBody] = Field(default_factory=list, max_length=100)


class CustomFieldValueBody(BaseModel):
    field_key: str = Field(min_length=2, max_length=63)
    value: str = Field(min_length=1, max_length=1000)
    correlation_id: str


class MergeBody(BaseModel):
    source_person_id: str
    target_person_id: str
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str
    candidate_id: str | None = None


class VariantBody(BaseModel):
    variant_key: str = Field(min_length=1, max_length=63)
    display_name: str = Field(min_length=1, max_length=200)
    entitlement_quantity: int | None = Field(default=None, ge=1, le=1000000)
    term_days: int | None = Field(default=None, ge=1, le=36500)
    sku: str | None = Field(default=None, min_length=1, max_length=64)


class ProductTextBody(BaseModel):
    locale: str = Field(min_length=2, max_length=5)
    display_name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    terms: str | None = Field(default=None, max_length=20000)


class ProductBody(BaseModel):
    """CreateProduct, with its text and variants in one command.

    A product with no variant cannot be priced and one with no text cannot be displayed, so
    three commands would leave two windows in which the catalogue holds something unsellable.
    """

    product_key: str = Field(min_length=2, max_length=63)
    product_type: str
    correlation_id: str
    tax_category_id: str | None = None
    brand_id: str | None = None
    merchandising_rank: int = Field(default=1000, ge=0, le=1000000)
    texts: list[ProductTextBody] = Field(default_factory=list, max_length=40)
    variants: list[VariantBody] = Field(default_factory=list, max_length=100)


class TaxCategoryBody(BaseModel):
    """A tax regime's name. **It holds no rate**, which is paragraph 4077's requirement."""

    category_key: str = Field(min_length=2, max_length=63)
    display_name: str = Field(min_length=1, max_length=120)
    correlation_id: str
    jurisdiction_note: str | None = Field(default=None, max_length=500)


class VersionedBody(BaseModel):
    expected_version: int = Field(ge=1, le=10**9)
    correlation_id: str


class PriceBookBody(BaseModel):
    """COM-02-R02's seven dimensions."""

    price_book_key: str = Field(min_length=2, max_length=63)
    display_name: str = Field(min_length=1, max_length=120)
    currency: str = Field(min_length=3, max_length=3)
    effective_from: datetime
    correlation_id: str
    brand_id: str | None = None
    location_id: str | None = None
    channel: str = "any"
    customer_segment: str = Field(default="any", min_length=2, max_length=63)
    tax_category_id: str | None = None
    effective_to: datetime | None = None
    priority: int = Field(default=0, ge=-1000, le=1000)


class PriceBody(BaseModel):
    """A new price. **Never an edit**, which is COM-02-R07.

    The currency is not here: it comes from the book, because a price in a currency its book
    does not use is a row the resolver would refuse at read time.
    """

    price_book_id: str
    variant_id: str
    amount_minor: int = Field(ge=0, le=10**12)
    effective_from: datetime
    correlation_id: str
    effective_to: datetime | None = None


class SupersedeBody(BaseModel):
    replacement_price_id: str
    correlation_id: str


class EligibilityRuleBody(BaseModel):
    """One named condition. Each kind carries exactly one operand, which the schema enforces."""

    rule_kind: str
    amount_minor: int | None = Field(default=None, ge=1, le=10**12)
    quantity: int | None = Field(default=None, ge=1, le=1000000)
    text_value: str | None = Field(default=None, min_length=1, max_length=200)
    date_from: date | None = None
    date_to: date | None = None


class PromotionBody(BaseModel):
    """A promotion and its rules in one command.

    The rules come together because a promotion whose conditions arrive a moment later is a
    promotion that is briefly unconditional, and `cat_eligibility_rules` is insert-only so
    there is no way to tighten one afterwards.
    """

    promotion_key: str = Field(min_length=2, max_length=63)
    display_name: str = Field(min_length=1, max_length=120)
    promotion_kind: str
    effective_from: datetime
    correlation_id: str
    percent_bp: int | None = Field(default=None, ge=1, le=10000)
    amount_minor: int | None = Field(default=None, ge=1, le=10**12)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    stacking_group: str = Field(default="default", min_length=2, max_length=63)
    priority: int = Field(default=0, ge=-1000, le=1000)
    approval_threshold_bp: int = Field(default=0, ge=0, le=10000)
    effective_to: datetime | None = None
    rules: list[EligibilityRuleBody] = Field(default_factory=list, max_length=20)


class CouponBody(BaseModel):
    promotion_id: str
    code: str = Field(min_length=3, max_length=32)
    correlation_id: str


class ResolvePriceBody(BaseModel):
    """ResolvePrice.

    **An override needs an approval id that resolves to a real approval** for this variant at
    this list amount, in this currency, unexpired and unspent; the service checks the row
    rather than believing the field. A discount field with no approval behind it would be the
    authority bought with a body field, which is the shape MOD-009, MOD-013 and MOD-014 each
    shipped once.

    **There is no `customer_segment` and no `brand_id` here, and their absence is the fix for a
    finding.** Both chose which price book the sale priced from, and both were free strings:
    a routine AAL-1 session took a 90% reduction by sending `"customer_segment": "staff"`, with
    the stored resolution citing the staff book as its authority. The segment is now derived
    from the subject's own tags and the brand from the location -- MOD-008's "derive a scope,
    never accept one", which this module had to learn separately.

    `channel` remains the caller's word, bounded to the seven. There is no server-side source
    for what kind of client is calling, so a channel-scoped book is only as trustworthy as the
    client; that is recorded as a gap rather than papered over.
    """

    variant_id: str
    currency: str = Field(min_length=3, max_length=3)
    correlation_id: str
    quantity: int = Field(default=1, ge=1, le=1000000)
    channel: Literal["any", "pos", "member_app", "admin_web", "crm", "kiosk", "web"] = "any"
    location_id: str | None = None
    subject_id: str | None = None
    coupon_code: str | None = Field(default=None, min_length=3, max_length=32)
    #: Required when a coupon is applied and the resolution is stored, because the redemption
    #: is written in the same transaction. See `catalog.service.resolve_price`.
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)
    override_amount_minor: int | None = Field(default=None, ge=0, le=10**12)
    override_reason: str | None = Field(default=None, max_length=500)
    approval_id: str | None = None


class QuotePriceBody(BaseModel):
    """QuotePrice: what a sale would cost, with nothing recorded.

    **`ResolvePriceBody`'s fields minus the four that are sale decisions.** There is no
    `coupon_code` (a coupon is quoted by `/catalog/promotions/validate`, which is where its
    usage rules are explained -- two coupon-quoting paths are two answers to "is this code
    still good"), no `idempotency_key` (nothing is written), and no override or approval,
    because an override needs an approval row that covers the variant at the list amount and a
    figure nobody may charge is not a quote.

    `customer_segment` and `brand_id` are absent for the same reason they are absent from the
    sale: both chose which book the price came from and both were free strings, so a routine
    session took a 90% reduction by sending one. The segment is derived from the subject's own
    tags and the brand from the location.

    **This is the one body in this application that forbids unknown fields, and the reason is
    that its distinguishing feature is an absence.** Pydantic ignores an extra by default, so
    a caller that sent `coupon_code` here got a figure with the coupon *not* applied -- and a
    till that showed that figure while believing the code had been taken is a worse outcome
    than a refusal, because the number is plausible. An absence that is silently tolerated is
    a convention rather than a control, which is MOD-012's `vault_ref` lesson applied to a
    request body; `extra="forbid"` is what makes the four missing fields mean something. The
    cost is that a client sending a field this route does not have gets a 422 instead of a
    quiet success, which is the direction worth failing in.
    """

    model_config = ConfigDict(extra="forbid")

    variant_id: str
    currency: str = Field(min_length=3, max_length=3)
    correlation_id: str
    quantity: int = Field(default=1, ge=1, le=1000000)
    channel: Literal["any", "pos", "member_app", "admin_web", "crm", "kiosk", "web"] = "any"
    location_id: str | None = None
    subject_id: str | None = None


class ValidatePromotionBody(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    subtotal_minor: int = Field(ge=0, le=10**12)
    currency: str = Field(min_length=3, max_length=3)
    channel: Literal["any", "pos", "member_app", "admin_web", "crm", "kiosk", "web"] = "any"
    product_type: str = ""
    subject_id: str | None = None


class RequestDiscountBody(BaseModel):
    """Ask for an override. The requester is the caller's own session, never a field."""

    variant_id: str
    list_amount_minor: int = Field(ge=1, le=10**12)
    override_amount_minor: int = Field(ge=0, le=10**12)
    currency: str = Field(min_length=3, max_length=3)
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class ApproveDiscountBody(BaseModel):
    """Decide a recorded request. Paragraph 10220's approval.

    **Only the request and the approver's own reason are here.** Every figure comes from the
    request row, and `requested_by` with it -- so the schema's `approved_by <> requested_by`
    compares two identities the server derived. While `requested_by` was a field on this body
    the constraint compared one derived identity against one the approver typed, and all three
    reviewers independently demonstrated a single person approving their own override naming a
    requester who does not exist.
    """

    request_id: str
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class RedeemCouponBody(BaseModel):
    """Consume a code for a sale priced outside this module.

    **No `discount_minor`.** The service computes it from the promotion and the subtotal: this
    field let the caller write any figure into an insert-only ledger with no correction path,
    and the same invented figure was then what a minimum-spend rule was compared against.
    """

    code: str = Field(min_length=3, max_length=32)
    subtotal_minor: int = Field(ge=1, le=10**12)
    currency: str = Field(min_length=3, max_length=3)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str
    channel: Literal["any", "pos", "member_app", "admin_web", "crm", "kiosk", "web"] = "any"
    subject_id: str | None = None
    order_reference: str | None = Field(default=None, min_length=1, max_length=200)


class BundleItemBody(BaseModel):
    variant_id: str
    quantity: int = Field(default=1, ge=1, le=1000)
    fulfilment_kind: str


class BundleBody(BaseModel):
    product_id: str
    items: list[BundleItemBody] = Field(min_length=1, max_length=50)
    correlation_id: str


class FulfilmentBody(BaseModel):
    """What somebody says was delivered. **Nothing in this build delivers anything.**"""

    bundle_id: str
    variant_id: str
    order_reference: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=1000)
    outcome: Literal["delivered", "failed", "cancelled", "reversed"]
    #: What makes a retried report free. The unique index that used to be on
    #: (order, bundle, variant) made a failed delivery permanently unfixable instead.
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str
    subject_id: str | None = None
    external_reference: str | None = Field(default=None, min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=2000)

# ---------------------------------------------------------------- MOD-017, COM-01 and COM-03


class CommercialActionBody(BaseModel):
    """A command whose only input is who is asking and under which correlation.

    Publication and revocation both have one: every other figure is on the row already, and a
    body field beside it would be a second place for the same fact to come from.
    """

    correlation_id: str


class RevokeEntitlementBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class ContractVersionBody(BaseModel):
    """COM-01-R02's contract terms, as a draft somebody else publishes.

    **The policy numbers are here beside the prose**, because the lifecycle arithmetic reads
    them and the member agreed to both halves. A version whose prose said thirty days' notice
    while its `notice_days` said seven would be two contracts in one row.
    """

    contract_key: str = Field(min_length=2, max_length=63)
    body: str = Field(min_length=1, max_length=100_000)
    locale: str = Field(default="en", min_length=2, max_length=5)
    minimum_term_months: int = Field(default=0, ge=0, le=120)
    notice_days: int = Field(default=0, ge=0, le=365)
    renewal_mode: Literal["manual", "automatic", "none"] = "manual"
    cancellation_mode: Literal["immediate", "end_of_notice", "end_of_term"] = "end_of_term"
    freeze_days_per_year: int = Field(default=0, ge=0, le=365)
    grace_days: int = Field(default=0, ge=0, le=180)
    # **Nullable, and the null is the default this build has always had.** Omitted means the
    # contract holds the member to the minimum term, which is what `cancellation_effective_on`
    # enforced for every contract until ADM-MSH-07 showed the design buying out of one. A
    # value is the buy-out in months of the agreement amount, and 0 is a free early exit --
    # three states in one field, because zero is a term rather than an absence.
    early_termination_months: int | None = Field(default=None, ge=0, le=120)
    correlation_id: str


class MembershipTermsBody(BaseModel):  # noqa: D101
    product_id: str
    contract_key: str = Field(min_length=2, max_length=63)
    membership_kind: Literal[
        "fixed_term", "recurring", "installment", "prepaid", "off_peak", "family",
        "student", "corporate", "class_credit", "unlimited"]
    billing_period: Literal["weekly", "monthly", "quarterly", "annual", "one_off"] = "monthly"
    installment_count: int | None = Field(default=None, ge=2, le=120)
    prepaid_days: int | None = Field(default=None, ge=1, le=3650)
    # **The one thing that marks a product as a trial** -- ADR-0010 D7. Bounded at the
    # boundary rather than left to the CHECK, because a bound reached as a `DataError` is a
    # 500 the handlers do not catch, which this build has paid for in MOD-011, MOD-012 and
    # MOD-013. `None` is "not a trial"; zero is refused, because a zero-day trial is a
    # declared value nothing can mean.
    trial_days: int | None = Field(default=None, ge=1, le=90)
    # **Which boundary this contract's billing period falls on** -- ADR-0011. `agreement_start`
    # is what this build did before the anchor existed and stays the default, so a contract
    # written without the field is billed exactly as it was. A `Literal` refuses an unknown
    # value at the request boundary rather than leaving the CHECK to answer, which is this
    # application's own rule: a 422 naming the request beats a `CheckViolation` the handlers
    # turn into one anyway, and the `calendar`-on-weekly pairing is still the schema's to
    # refuse because the service is the half that can be wrong.
    billing_anchor: Literal["agreement_start", "calendar"] = "agreement_start"
    correlation_id: str


class AgreementBody(BaseModel):
    """CreateMembershipAgreement.

    **There is no `contract_version_id` here.** The terms say which contract key applies and
    the service pins the latest published version of it. A caller able to name the version
    could name an older one with a shorter minimum term -- the authority bought with a body
    field, which is the shape this repository has shipped four times.
    """

    person_id: str
    membership_terms_id: str
    variant_id: str
    #: Used only when no `price_resolution_id` is cited. A cited resolution is the authority
    #: on the figure and on the currency, and a resolution for a different variant is refused
    #: rather than quietly used: an agreement that named MOD-016's receipt for 45.00 and
    #: recorded 4.50 read as priced and approved.
    amount_minor: int = Field(ge=0, le=10**12)
    currency: str = Field(min_length=3, max_length=3)
    starts_on: date
    price_resolution_id: str | None = None
    supersedes_agreement_id: str | None = None
    correlation_id: str


class SignatureBody(BaseModel):
    """**A signature is recorded, not captured.** Nothing in this build takes one."""

    signature_kind: Literal["wet_ink", "click_through", "drawn", "witnessed", "imported"]
    signature_evidence_ref: str = Field(min_length=1, max_length=500)
    signed_by_person_id: str
    correlation_id: str


class ActivationBody(BaseModel):
    agreement_id: str
    membership_number: str = Field(min_length=3, max_length=32)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class FreezeBody(BaseModel):
    """COM-01-R04's freeze, pause and medical hold."""

    freeze_kind: Literal["freeze", "pause", "medical_hold"]
    starts_on: date
    days: int = Field(ge=1, le=365)
    reason: str = Field(min_length=1, max_length=500)
    #: A locator for the note, never the note: a diagnosis is health data under MOD-008's
    #: classification and this module has no business holding one.
    evidence_ref: str | None = Field(default=None, min_length=1, max_length=500)
    requested_by_person_id: str | None = None
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class ResumeBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class LeadSourceBody(BaseModel):
    """Where leads come from, as a tenant's own row.

    A row rather than a string because ADM-RPT-03 groups conversions by source, and free text
    would make the one report this field exists for a group-by over typos.
    """

    source_key: str = Field(min_length=2, max_length=63)
    display_name: str = Field(min_length=1, max_length=200)
    location_id: str | None = None
    correlation_id: str


class RetireSourceBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class LeadBody(BaseModel):
    """ADM-CRM-04's form, which is two fields and two optional ones.

    **No name and no phone number.** "Name and phone are enough" is about the *screen*: the
    person is MOD-014's and is created there, and this body cites them. A name here would be
    the second copy MOD-013 refuses to hold.

    **No idempotency key**, because the person is the key: a lead already open for them is
    returned, which is the canvas's own behaviour rather than a convenience.
    """

    person_id: str
    source_id: str | None = None
    interests: list[str] = Field(default_factory=list, max_length=3)
    owner_person_id: str | None = None
    # True to claim the lead for the caller. Derived from the session, like MOD-026's
    # `to_self`: a request that could name a person would let a reader claim a lead as
    # somebody else, and both fields together is a caller that does not know what it meant.
    owner_is_me: bool = False
    correlation_id: str

    @model_validator(mode="after")
    def one_owner(self) -> LeadBody:
        if self.owner_is_me and self.owner_person_id is not None:
            raise ValueError("name an owner or claim it yourself, not both")
        return self


class WalkInTrialBody(BaseModel):
    """FD-05's two fields, plus the escapes the duplicate check needs. ADR-0010 D12.

    **A person or a name and a number, never both.** The desk types two fields; the screen's
    own contact check may then resolve them to a record that already exists, and starting the
    trial on *that* record is one of ADM-MEM-10's two escapes. A body carrying both is a
    caller that does not know which it meant, which is MOD-026's `to_self` rule.

    **`different_person` is the other escape and it is deliberately not a default.** Two
    siblings at one address with one family line is MOD-014's ordinary case, so the server
    refuses a number somebody already holds and this is the field that says a human looked at
    the match and decided.

    **`variant_id` is absent on the drawn screen and present here**, because a tenant
    publishing two trial plans is a case the canvas does not draw: with one, the command
    derives it and the field is unused.
    """

    summary: str = Field(min_length=1, max_length=2000)
    correlation_id: str
    person_id: str | None = None
    legal_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=64)
    different_person: bool = False
    variant_id: str | None = None
    source_id: str | None = None
    owner_is_me: bool = False

    @model_validator(mode="after")
    def one_subject(self) -> WalkInTrialBody:
        if self.person_id is not None and (self.legal_name or self.phone):
            raise ValueError("name a person or type a name and a number, not both")
        if self.person_id is None and not (self.legal_name and self.phone):
            raise ValueError("a walk-in needs a person, or a name and a number")
        return self


class TouchpointBody(BaseModel):
    """A conversation, written up. The kind decides which stage it reaches."""

    kind: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=2000)
    # Optional, because a salesperson writes up Friday's open day on Monday. It may not be in
    # the future: "No contact · 2 days" is counted from it.
    occurred_at: datetime | None = None
    correlation_id: str


class LeadLostBody(BaseModel):
    """ADM-CRM-07's reason picker and its one free-text field.

    **`reason` is a `Literal` over the four the canvas draws**, so an unknown one is a 422
    naming the request rather than a `CheckViolation` the handlers turn into one anyway --
    and the four here, the four in `pipeline.LOST_REASONS` and the four in the CHECK are
    compared by a test, which is MOD-026's precedent for a vocabulary in three places.

    **`detail` is the canvas's "which gym, if he said".** Optional, bounded here as well as in
    the schema because a bound reached as a `DataError` is a 500 the handlers do not catch.
    """

    reason: Literal[
        "too_expensive", "joined_elsewhere", "location_or_hours", "no_longer_responding"]
    correlation_id: str
    detail: str | None = Field(default=None, min_length=1, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


class LeadReopenBody(BaseModel):
    correlation_id: str
    expected_version: int | None = Field(default=None, ge=1)


class LeadInterestWithdrawBody(BaseModel):
    interest: Literal["classes", "pt", "gym_only"]
    correlation_id: str


class LeadStageBody(BaseModel):
    to_stage: str = Field(min_length=1, max_length=40)
    expected_version: int | None = Field(default=None, ge=1)
    correlation_id: str


class LeadAssignBody(BaseModel):
    """Claim a lead, hand it over, or release it."""

    owner_person_id: str | None = None
    to_self: bool = False
    # True to release: a null owner is the release, and a body that said nothing would be
    # indistinguishable from one that meant to clear it.
    release: bool = False
    expected_version: int | None = Field(default=None, ge=1)
    correlation_id: str

    @model_validator(mode="after")
    def one_intent(self) -> LeadAssignBody:
        named = [self.owner_person_id is not None, self.to_self, self.release]
        if sum(1 for n in named if n) != 1:
            raise ValueError("name an owner, claim it yourself, or release it -- exactly one")
        return self


class NextActionBody(BaseModel):
    """ADM-CRM-02's NEXT ACTION column. Both halves or neither."""

    next_action: str | None = Field(default=None, max_length=200)
    next_action_on: date | None = None
    expected_version: int | None = Field(default=None, ge=1)
    correlation_id: str


class LeadInterestsBody(BaseModel):
    interests: list[str] = Field(min_length=1, max_length=3)
    correlation_id: str


class PlanChangeBody(BaseModel):
    """COM-01-R04's upgrade or downgrade, confirmed against what was disclosed.

    **There is no `kind` field, and that is the point.** `lifecycle.plan_change` derives the
    direction from the two prices, because the two acts differ in when they take effect *and*
    in what is charged -- so a caller able to declare `downgrade` on a dearer plan would take
    the rest of the period on the better plan for nothing. This build has shipped that shape
    in six modules.

    `acknowledged_due_minor` is the figure the preview showed. The service recomputes it and
    refuses a mismatch, so the number on the button and the number recorded are provably one.
    """

    to_agreement_id: str
    reason: str = Field(min_length=1, max_length=500)
    # The member signs the new agreement as part of the act, and this command is the only
    # signer of it: a successor signed beforehand would already govern, so there would be
    # nothing left for the change to record.
    signature_kind: str = Field(min_length=1, max_length=40)
    signature_evidence_ref: str = Field(min_length=1, max_length=500)
    acknowledged_due_minor: int | None = Field(default=None, ge=-10**12, le=10**12)
    requested_by_person_id: str | None = None
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class CancelMembershipBody(BaseModel):
    """COM-01-R06's disclosure, confirmed.

    `acknowledged_fee_minor` is the figure the member was shown by the preview. The service
    recomputes the fee and refuses a mismatch, so the figure quoted and the figure applied are
    provably the same one -- without it the preview and the command are two independent
    calculations and a member can be shown one number and charged another.
    """

    reason: str = Field(min_length=1, max_length=500)
    acknowledged_fee_minor: int | None = Field(default=None, ge=0, le=10**12)
    requested_by_person_id: str | None = None
    expected_version: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class EntitlementPolicyBody(BaseModel):
    policy_key: str = Field(min_length=2, max_length=63)
    display_name: str = Field(min_length=1, max_length=200)
    entitlement_type: Literal[
        "location_access", "schedule_access", "zone_access", "class_credit",
        "facility_access", "service_credit", "guest_pass", "discount", "digital_content"]
    is_counted: bool = True
    reservation_ttl_seconds: int = Field(default=900, ge=30, le=86400)
    carryover_mode: Literal["none", "capped", "unlimited"] = "none"
    carryover_limit: int | None = Field(default=None, ge=1, le=100_000)
    correlation_id: str


class GrantBody(BaseModel):
    """GrantEntitlement.

    **No `is_counted` field.** It comes from the policy, because a caller able to send it could
    make an unlimited grant of something the tenant sells by the ten.
    """

    person_id: str
    policy_id: str
    source_kind: Literal["membership", "bundle_fulfilment", "goodwill", "migration",
                         "corporate"]
    valid_from: datetime
    valid_to: datetime | None = None
    quantity: int | None = Field(default=None, ge=1, le=100_000)
    membership_id: str | None = None
    source_id: str | None = None
    brand_id: str | None = None
    location_id: str | None = None
    usable_from_minute: int | None = Field(default=None, ge=0, le=1439)
    usable_to_minute: int | None = Field(default=None, ge=1, le=1440)
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class ReserveBody(BaseModel):
    """ReserveEntitlement.

    **No `brand_id` and no `local_minute`.** Both gate the draw -- a brand-scoped grant and an
    off-peak window -- and both were caller-supplied, so a grant for one brand was drawn on at
    another by sending the grant's own brand id, and an off-peak grant was drawn on in the
    evening by sending `600`. The service derives them from the location: its brand, and the
    time of day in *its* timezone, which is the conversion PostgreSQL has the zone database
    for. A draw that names no location cannot evaluate a time window and is refused by one.
    """

    grant_id: str
    purpose_kind: Literal["booking", "guest_entry", "service_delivery", "manual"]
    quantity: int = Field(default=1, ge=1, le=1000)
    purpose_ref: str | None = Field(default=None, min_length=1, max_length=200)
    location_id: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class SettleReservationBody(BaseModel):
    outcome: Literal["consumed", "released"]
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    correlation_id: str

class BillingAccountBody(BaseModel):
    payer_person_id: str
    account_number: str = Field(min_length=3, max_length=32)
    currency: str = Field(min_length=3, max_length=3)
    legal_entity_id: str
    account_kind: Literal["individual", "household", "corporate"] = "individual"
    payment_terms_days: int = Field(default=0, ge=0, le=180)
    correlation_id: str


class FiscalSeriesBody(BaseModel):
    legal_entity_id: str
    series_code: str = Field(min_length=1, max_length=16)
    document_kind: Literal["invoice", "credit_note", "receipt"] = "invoice"
    correlation_id: str


class InvoiceLineBody(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    quantity: int = Field(default=1, ge=1, le=1_000_000)
    unit_net_minor: int = Field(ge=0, le=10**12)
    #: The rate applied, per line. COM-03-R07's regional taxation: two lines on one invoice
    #: routinely carry different rates, and the rate that applied on the day has to survive a
    #: rate change. The sources state no rates, which is MOD-015's precedent.
    tax_rate_bp: int = Field(ge=0, le=10_000)
    variant_id: str | None = None
    price_resolution_id: str | None = None
    tax_category_id: str | None = None


class IssueInvoiceBody(BaseModel):
    """IssueInvoice.

    **No `legal_entity_id` and no currency.** Both come from the billing account, so a serial
    cannot be drawn from another entity's series and an invoice cannot be issued in a currency
    the account is not billed in.
    """

    billing_account_id: str
    series_id: str
    lines: list[InvoiceLineBody] = Field(min_length=1, max_length=500)
    issued_on: date
    due_on: date
    jurisdiction: str = Field(min_length=2, max_length=11)
    membership_id: str | None = None
    schedule_id: str | None = None
    #: Set to issue a credit note, which needs a series whose `document_kind` is
    #: `credit_note`. The schema makes those the same fact, so a credit-note series was
    #: unusable until this field existed -- and a credit note is the only correction an
    #: insert-only ledger has.
    credits_invoice_id: str | None = None
    #: The part of the net not yet delivered, which MOD-018's bridge credits to
    #: `unearned_revenue` instead of `revenue`. Paragraph 1695: a prepaid year is not
    #: day-one revenue, and only the caller knows what was sold.
    unearned_minor: int = Field(default=0, ge=0, le=1_000_000_000_000)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class PaymentIntentBody(BaseModel):
    """CreatePaymentIntent.

    **There is no card number, expiry or CVV field and the table has no column for one.**
    Paragraph 1597: sensitive card data never enters Veyro systems unless explicitly certified.
    `payment_method_ref` is a token somebody else holds -- MOD-012's `vault_ref` shape, where
    the control is an absence.

    **No currency either**: it comes from the billing account, so an intent for 4500 USD cannot
    be raised against an invoice for 4500 JOD.
    """

    billing_account_id: str
    amount_minor: int = Field(ge=1, le=10**12)
    method: Literal["card", "direct_debit", "bank_transfer", "cash", "wallet",
                    "gift_card", "other"]
    provider_key: str = Field(min_length=2, max_length=63)
    invoice_id: str | None = None
    payment_method_ref: str | None = Field(default=None, min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class SettleIntentBody(BaseModel):
    """What the provider says happened.

    `unknown` is a real outcome and not a synonym for failed: a provider that answered nothing
    has told us nothing, and recording that as declined is how a member is dunned for a payment
    that succeeded. Paragraph 1609.

    `failure_code` is a declared code the retry policy branches on; `failure_detail` is the
    provider's own sentence and **nothing branches on it**, because a control decided by
    matching words in prose is one anybody can change by editing a string.
    """

    outcome: Literal["succeeded", "failed", "cancelled", "unknown"]
    provider_ref: str | None = Field(default=None, min_length=1, max_length=200)
    failure_code: str | None = Field(default=None, min_length=2, max_length=63)
    failure_detail: str | None = Field(default=None, min_length=1, max_length=1000)
    #: Required for a cash payment and meaningless otherwise: the till's own `cash` account,
    #: which is per location, so only whatever took the money knows which one. Without it the
    #: payment is recorded and the ledger posting is skipped with a reason.
    cash_account_id: str | None = None
    correlation_id: str


class RefundRequestBody(BaseModel):
    """Ask for a refund. The requester is the caller's own session, never a field."""

    payment_id: str
    amount_minor: int = Field(ge=1, le=10**12)
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class ApproveRefundBody(BaseModel):
    """Decide a recorded request. Every figure comes from the request row.

    `acknowledged_amount_minor` is the approver saying which figure they are approving. The
    separation of duties establishes that two people were involved and says nothing about what
    the second one read.
    """

    request_id: str
    approval_reason: str = Field(min_length=1, max_length=500)
    acknowledged_amount_minor: int | None = Field(default=None, ge=1, le=10**12)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class SettleRefundBody(BaseModel):
    outcome: Literal["succeeded", "failed", "unknown"]
    provider_ref: str | None = Field(default=None, min_length=1, max_length=200)
    failure_code: str | None = Field(default=None, min_length=2, max_length=63)
    correlation_id: str


class DunningBody(BaseModel):
    invoice_id: str
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class AdvanceDunningBody(BaseModel):
    notification_ref: str | None = Field(default=None, min_length=1, max_length=200)
    correlation_id: str


class DisputeBody(BaseModel):
    """A chargeback the scheme has opened, as reported by whoever read the notice.

    **Bounded at the boundary**, because `NumericValueOutOfRange` is a `DataError` rather
    than the `CheckViolation` the handlers catch -- MOD-011's, MOD-012's and MOD-013's
    finding, and this is the fourth body to answer it. The amount is additionally compared
    against the payment, which is the control a `le=` cannot express.

    The billing account is **not** a field: it is derived from the payment, so a dispute
    cannot be recorded against another payer's account.
    """

    payment_id: str
    provider_case_ref: str = Field(min_length=1, max_length=200)
    dispute_kind: str
    reason_code: str = Field(min_length=1, max_length=63)
    amount_minor: int = Field(ge=1, le=10**12)
    currency: str = Field(min_length=3, max_length=3)
    opened_on: date
    respond_due_on: date
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class DisputeResponseBody(BaseModel):
    #: A locator for what was sent, never the evidence: the column is `write_once` and
    #: un-erasable, which is where a member's medical note ends up if the field invites prose.
    response_ref: str = Field(min_length=1, max_length=200)
    correlation_id: str


class DisputeOutcomeBody(BaseModel):
    outcome: Literal["won", "lost", "withdrawn"]
    correlation_id: str


class ReconcileBody(BaseModel):
    """COM-03-R06. `provider_status` of null means the provider did not answer."""

    provider_status: Literal["succeeded", "failed", "pending", "cancelled"] | None = None
    provider_ref: str | None = Field(default=None, min_length=1, max_length=200)
    correlation_id: str


class FiscalizeBody(BaseModel):
    """Move the *fiscal* state, which is not the payment state. Paragraph 1607.

    `fiscal_complete` requires `ack_ref`: a server-allocated serial means the document is
    numbered, and numbering is not filing. Every invoice has a serial, so the serial alone
    could never be the test.
    """

    target: Literal["submitted", "acknowledged", "fiscal_complete", "rejected",
                    "not_required"]
    ack_ref: str | None = Field(default=None, min_length=1, max_length=200)
    #: Required for `not_required`, which is terminal, needs no acknowledgement and sidesteps
    #: the one control this table is proud of -- so it is the transition that most needs a
    #: written reason on the row.
    exemption_reason: str | None = Field(default=None, min_length=1, max_length=500)
    correlation_id: str




class LedgerAccountBody(BaseModel):
    """One account in the tenant's chart.

    **No balance field and no opening balance.** COM-04-R07: a balance is the sum of the
    postings, and an opening figure is a journal like any other -- one that debits the account
    and credits an equity or suspense account, so the ledger still balances.
    """

    account_code: str = Field(min_length=2, max_length=32)
    #: One of `app.ledger.accounts.KINDS`. Not free text: the catalogue is the authority on
    #: what this software posts, and a per-tenant set would let two tenants disagree with the
    #: code about whether `unearned_revenue` is a liability.
    account_kind: str = Field(min_length=2, max_length=32)
    display_name: str = Field(min_length=1, max_length=200)
    currency: str = Field(min_length=3, max_length=3)
    brand_id: str | None = None
    location_id: str | None = None
    legal_entity_id: str | None = None
    correlation_id: str


class PostingLineBody(BaseModel):
    """One line of a journal. **One signed amount, because two columns can disagree.**

    Positive is a debit and negative is a credit, so "this journal balances" is exactly
    `sum(amount_minor) = 0` -- which the database checks with a deferred constraint trigger.
    """

    account_id: str
    amount_minor: int = Field(le=10**12, ge=-(10**12))
    subject_person_id: str | None = None
    memo: str | None = Field(default=None, min_length=1, max_length=500)


class PostJournalBody(BaseModel):
    """PostJournal.

    **No `period_id`.** The period is derived from `posted_on` and opened by the first posting
    into it, because there is no worker here to open months ahead -- and a caller able to name
    the period could post January's trade into February's open month and make both wrong.
    """

    legal_entity_id: str
    lines: list[PostingLineBody] = Field(min_length=2, max_length=1000)
    posted_on: date
    currency: str = Field(min_length=3, max_length=3)
    #: **`manual` only.** The other source kinds belong to the commands that produce them --
    #: a journal claiming to come from an invoice, when it came from this route, is a journal
    #: nobody can trace -- and the idempotency namespace is per source kind, so a caller able
    #: to send `wallet` here could pre-empt a wallet credit's own journal and be handed the
    #: decoy back as a repeat.
    source_kind: Literal["manual"] = "manual"
    source_ref: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    #: **`close` costs a different permission**, which is the only honest way to have this
    #: field at all: a `closing` period admits the close's own entries and no trade, and with
    #: `purpose` free the identical journal went in as `close` after being refused as `trade`
    #: -- COM-04-R06's lock on the month finance is signing off, defeated by a word. The other
    #: three purposes are produced by the commands that own them and are derived from the
    #: source kind, never sent.
    purpose: Literal["trade", "close"] = "trade"
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class CorrectJournalBody(BaseModel):
    """Reverse a posted journal. **The only correction paragraph 1685 admits.**"""

    reason: str = Field(min_length=1, max_length=500)
    #: Defaults to today, which is the open period. A correction discovered in December for a
    #: November mistake belongs in December, because that is the period whose figures change.
    posted_on: date | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class WalletCreditBody(BaseModel):
    """CreditWallet.

    **`value_kind` chooses which liability**, and the liability account is derived from it
    rather than named: promotional value and cash value are different accounts and paragraph
    1686 makes the distinction a Critical Control. The *counterpart* is named, because what the
    value came from -- a till, a provider, a marketing expense -- is the caller's to say.
    """

    person_id: str
    value_kind: Literal["cash", "promotional", "referral", "refund_credit"]
    amount_minor: int = Field(ge=1, le=10**12)
    currency: str = Field(min_length=3, max_length=3)
    legal_entity_id: str
    counterpart_account_id: str
    source_kind: Literal["purchase", "refund", "goodwill", "referral", "promotion",
                         "correction", "migration"]
    source_ref: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)
    #: **Cash value does not expire**, and the service refuses one that tries: it is money the
    #: member paid in, so an expiry on it would be the tenant keeping money it owes.
    expires_on: date | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class WalletDebitBody(BaseModel):
    """DebitWallet. **There is no `value_kind` field.**

    `wallet.plan_debit` decides, in the member's interest: promotional first because it expires
    and is worth nothing lapsed, cash last because cash is the only kind they can ask for back.
    A caller able to name the kind could spend the refundable balance first and leave the member
    holding value they can never get back.
    """

    person_id: str
    amount_minor: int = Field(ge=1, le=10**12)
    currency: str = Field(min_length=3, max_length=3)
    legal_entity_id: str
    counterpart_account_id: str
    reason: str = Field(min_length=1, max_length=500)
    source_kind: Literal["spend", "refund", "expiry", "correction"] = "spend"
    source_ref: str | None = Field(default=None, min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class RecognitionScheduleBody(BaseModel):
    """Declare how a sale earns. Paragraph 1695.

    The basis decides which fields are present: `straight_line` earns over a period,
    `on_delivery` over a number of units, `immediate` when sold. A schedule carrying both is
    one nothing can evaluate.
    """

    legal_entity_id: str
    source_kind: Literal["invoice_line", "entitlement_grant", "agreement", "manual"]
    source_ref: str = Field(min_length=1, max_length=200)
    basis: Literal["straight_line", "on_delivery", "immediate"]
    total_minor: int = Field(ge=1, le=10**12)
    currency: str = Field(min_length=3, max_length=3)
    unearned_account_id: str
    revenue_account_id: str
    subject_person_id: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    units_total: int | None = Field(default=None, ge=1, le=100_000)
    correlation_id: str


class PostRecognitionBody(BaseModel):
    """PostRevenueRecognition. **Cumulative, so running it twice posts once.**"""

    #: For an `on_delivery` schedule. Only the module that owns the delivery can say.
    units_delivered: int | None = Field(default=None, ge=0, le=100_000)
    as_of: date | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class SettlementLineBody(BaseModel):
    line_kind: Literal["payment", "refund", "fee", "chargeback", "chargeback_reversal",
                       "adjustment", "payout"]
    provider_ref: str = Field(min_length=1, max_length=200)
    amount_minor: int = Field(le=10**12, ge=-(10**12))
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class ImportSettlementBody(BaseModel):
    """ImportSettlement. COM-04-R04.

    **`claimed_total_minor` is the file's own header figure**, and it is compared against the
    lines: a file whose header disagrees with its body was truncated or edited in transit, and
    importing it would post half a day's takings as all of them.
    """

    legal_entity_id: str
    provider_key: str = Field(min_length=2, max_length=63)
    provider_batch_ref: str = Field(min_length=1, max_length=200)
    settled_on: date
    currency: str = Field(min_length=3, max_length=3)
    claimed_total_minor: int = Field(le=10**12, ge=-(10**12))
    lines: list[SettlementLineBody] = Field(min_length=1, max_length=5000)
    #: A locator, never the file. This build has no object store, and a column that could hold
    #: the bytes is a column somebody puts card numbers in.
    document_ref: str | None = Field(default=None, min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class ResolveCaseBody(BaseModel):
    """**`written_off` is a decision about money and it says so in the status.**"""

    outcome: Literal["investigating", "resolved", "written_off", "abandoned"]
    resolution: str = Field(min_length=1, max_length=500)
    resolution_journal_id: str | None = None
    correlation_id: str


class CashSessionBody(BaseModel):
    """**A float that is not posted is cash the ledger does not know about.**

    So a non-zero float names where it came from -- the safe, another `cash` account -- and
    the open posts it across. Without that the drawer's account balance is not the money in
    the drawer, which is the property the close's variance posting exists to keep.
    """

    location_id: str
    cash_account_id: str
    drawer_label: str = Field(min_length=1, max_length=63)
    currency: str = Field(min_length=3, max_length=3)
    #: What the person counted. On an empty drawer it is the float being drawn from the safe;
    #: on a handover it is the money the last shift left, and the two are told apart by the
    #: drawer account's own balance rather than by anything on this body.
    opening_float_minor: int = Field(ge=0, le=10**12)
    #: Required when the float is non-zero on an *empty* drawer: the `cash` account it is
    #: drawn from. **Refused on a handover**, where nothing is drawn -- a field accepted and
    #: then not used is worse than no field.
    float_source_account_id: str | None = None
    #: Required with a float, and with a handover that does not balance, because both post.
    legal_entity_id: str | None = None
    #: Required when a handover count differs from what the ledger says is in the drawer:
    #: the difference goes here, as it does at the close.
    suspense_account_id: str | None = None
    #: FD-07: "If your count differs, say so now -- a discrepancy found at open belongs to the
    #: previous shift." Required when it does differ.
    handover_reason: str | None = Field(default=None, min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class CloseCashSessionBody(BaseModel):
    """**There is no `expected_minor` field.** The ledger says what should be in the drawer;
    the clerk says what is there. A caller able to send both could make any till balance."""

    counted_minor: int = Field(ge=0, le=10**12)
    legal_entity_id: str
    suspense_account_id: str
    variance_reason: str | None = Field(default=None, min_length=1, max_length=500)
    #: What to pass to the next shift. FD-07: "The handover note is part of the shift, not a
    #: WhatsApp message that leaves with the person who wrote it."
    handover_note: str | None = Field(default=None, min_length=1, max_length=2000)
    correlation_id: str


class DepositBody(BaseModel):
    location_id: str
    cash_account_id: str
    bank_account_id: str
    currency: str = Field(min_length=3, max_length=3)
    declared_minor: int = Field(ge=1, le=10**12)
    #: What is deliberately left in the drawer rather than banked: the next shift's float.
    #: Declared, because `declared + retained = counted` is the arithmetic that keeps banking
    #: less than the till held from being tolerated silently.
    retained_minor: int = Field(default=0, ge=0, le=10**12)
    deposited_on: date
    session_ids: list[str] = Field(min_length=1, max_length=100)
    legal_entity_id: str
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class ConfirmDepositBody(BaseModel):
    """What the bank says it received. A different figure makes the deposit `short`."""

    credited_minor: int = Field(ge=0, le=10**12)
    credited_on: date
    legal_entity_id: str
    suspense_account_id: str
    bank_reference: str | None = Field(default=None, min_length=1, max_length=200)
    correlation_id: str


class PeriodBody(BaseModel):
    legal_entity_id: str
    period_key: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    target: Literal["closing", "closed", "open"] = "closed"
    correlation_id: str


class ReopenPeriodBody(BaseModel):
    """**A reopening states why**, because it is the one act that lets a filed figure change."""

    legal_entity_id: str
    period_key: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class ExportPeriodBody(BaseModel):
    """ReconcileControlTotal, as an export record. **Not the file: this build has no object
    store, and `target_ref` is the other system's own handle for the batch.**"""

    legal_entity_id: str
    period_key: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    target_system: str = Field(min_length=2, max_length=63)
    target_ref: str = Field(min_length=1, max_length=200)
    currency: str = Field(min_length=3, max_length=3)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str

class ObjectiveBody(BaseModel):
    """DefineSLI and SetSLO, which are one row.

    `aggregate_as` has no default. The same series answers different questions depending on how
    the window is reduced -- a counter's `sum` is a volume and its `rate_per_hour` is a load --
    and an objective that meant one and silently got the other still reads as a verdict.
    """

    objective_key: str
    kind: str
    metric_key: str
    comparison: str
    # `allow_inf_nan=False`, because `json.loads` accepts the non-standard `NaN` and `Infinity`
    # literals and pydantic passes them through to a `float`. A NaN threshold stores into
    # `numeric`, then every comparison in `objectives.evaluate` is False, so the objective
    # breaches on every evaluation and the event payload carries a value `jsonb` refuses.
    threshold: float = Field(allow_inf_nan=False)
    window_hours: int
    aggregate_as: str
    owner: str
    runbook_ref: str
    correlation_id: str
    #: The exact dimension set this objective is about -- every dimension the metric declares,
    #: with a value. An objective across all of them is not expressible, deliberately: the
    #: merged number measures nothing anybody defined, and a breach of it names nothing anybody
    #: can act on.
    dimensions: dict[str, str] = Field(default_factory=dict)


class SyntheticCheckBody(BaseModel):
    check_key: str
    description: str
    workflow: str
    interval_seconds: int
    correlation_id: str


class SyntheticToggleBody(BaseModel):
    enabled: bool
    correlation_id: str


class SyntheticResultBody(BaseModel):
    outcome: str
    duration_ms: int
    correlation_id: str
    detail: str | None = None
    observed_at: datetime | None = None


class ForecastBody(BaseModel):
    """`limit_value` is the capacity the projection is measured against.

    The headroom is derived from it rather than accepted, which is MOD-008's derive-don't-accept
    finding applied to a number: a caller that supplies its own headroom is supplying a
    conclusion, and the alert threshold would then be comparing against whatever it felt like.
    """

    resource: str
    horizon_days: int
    current_value: float = Field(allow_inf_nan=False)
    projected_value: float = Field(allow_inf_nan=False)
    basis: str
    correlation_id: str
    limit_value: float | None = Field(default=None, allow_inf_nan=False)


class CostBody(BaseModel):
    period_start: date
    period_end: date
    dimension: str
    dimension_value: str
    currency: str
    amount_minor: int
    source: str
    correlation_id: str
    corrects_cost_record_id: str | None = None


class BudgetBody(BaseModel):
    budget_key: str
    dimension: str
    currency: str
    amount_minor: int
    period: str
    owner: str
    correlation_id: str
    dimension_value: str | None = None
    warn_at_bp: int = 8000


class BudgetBurnBody(BaseModel):
    period_start: date
    correlation_id: str


class BootstrapBody(BaseModel):
    """The one-time grant that makes a tenant administrable at all."""

    role_key: str = "tenant_admin"
    display_name: str = "Tenant Administrator"
    correlation_id: str


def current_session(
    request: Request, tenant_id: TenantId, token: BearerToken
) -> dict[str, Any]:
    """Resolve the bearer token into the session it names, or refuse.

    Module level on purpose. `from __future__ import annotations` turns every annotation into a
    string and FastAPI resolves those against this module's globals, so a dependency defined
    inside `create_app` is never found -- FastAPI falls back to treating the parameter as a query
    field, and the route ends up unauthenticated while looking authenticated.
    """
    return identity.resolve_session(request.app.state.identity_pool, tenant_id, token=token)


def require_uuid(value: str, field: str) -> str:
    """Shape-check an identifier at the trust boundary, the way `tenant_claim` does the header.

    Every id in a MOD-009 body or path was a bare `str`, so a malformed one reached psycopg and
    came back as an uncaught `InvalidTextRepresentation` -- a 500 carrying a database exception
    rather than a 422. `field` is a fixed identifier written here, never the input, so nothing
    from the request travels in the error code.
    """
    if not _UUID.fullmatch(value):
        raise InvalidRequest(f"bad_{field}")
    return value


def optional_uuid(value: str | None, field: str) -> str | None:
    return None if value is None else require_uuid(value, field)


def _require_person(person_id: str | None) -> str:
    """The caller's own person record, or a refusal naming what is missing.

    **An identity with no person record cannot assign work to itself**, and saying so is the
    point: staff hold permissions and do not have to be anybody in particular, so this is
    ordinary rather than exceptional -- but the alternatives are both wrong. Falling through to
    a release would silently do the opposite of what the reader pressed, and writing a null
    assignee would read as a release in `tsk_cases` afterwards. The link is MOD-014's to make.
    """
    if person_id is None:
        raise InvalidRequest("no_person_record_for_this_identity")
    return person_id


def _currency(value: str) -> str:
    """Shape-check a currency code arriving in a query string.

    Every other currency in this application reaches a body, where
    `Field(min_length=3, max_length=3)` refuses a bad one at the boundary. A query parameter
    has no such field, so without this a four-letter code would travel to a `char(3)` column
    and come back as `StringDataRightTruncation` -- a `DataError` rather than the
    `CheckViolation` the handlers catch, which is MOD-011's, MOD-012's and MOD-013's finding
    for the fourth time. Upper-cased because the figures are compared against a book's own
    currency and `jod` is the same money as `JOD`.
    """
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise InvalidRequest("bad_currency")
    return code


def require_uuids(values: list[str], field: str, *, limit: int) -> list[str]:
    """Shape-check a repeated query parameter, and bound how many may be sent.

    **A batched read takes a list of ids, and the id sweep reads names.** A comprehension
    calling `require_uuid` on each element passes the loop variable rather than the parameter,
    so `test_id_validation`'s structural sweep would report the parameter unwrapped -- which
    is the sweep working correctly on a shape it has no name for. This is that name: one call
    taking the parameter itself, so the sweep sees it and the check is real.

    The bound is here rather than only in the service because an unbounded repeated parameter
    is a request whose cost the caller chooses.
    """
    if len(values) > limit:
        raise InvalidRequest(f"too_many_{field}")
    for value in values:
        require_uuid(value, field)
    return list(values)


def tenant_claim(x_veyro_tenant: Annotated[str | None, Header()] = None) -> str:
    """Shape-check the claimed tenant. Rejecting here keeps a malformed value out of the pool."""
    if x_veyro_tenant is None or not _UUID.fullmatch(x_veyro_tenant):
        raise service.InvalidRequest("bad_tenant_header")
    return x_veyro_tenant


TenantId = Annotated[str, Depends(tenant_claim)]
Session = Annotated[dict[str, Any], Depends(current_session)]


def owned(session: dict[str, Any], identity_id: str) -> str:
    """Refuse unless the session belongs to the identity being acted on.

    A 404 rather than a 403: whether an identity id exists in this tenant is not something a
    caller holding the wrong session gets to learn.
    """
    if session["identity_id"] != identity_id:
        raise NotFound("identity_not_found")
    return identity_id



# ------------------------------------------------------------------ MOD-019 scheduling
#
# **No `timezone` on any body.** Paragraph 4150 makes it location-specific and the service
# reads it from the location: a caller able to send one could schedule an 18:00 class in a zone
# the site is not in, which reads correctly in an admin screen and is an hour wrong on every
# member's phone.


class RecurrenceBody(BaseModel):
    """A recurrence, as a caller states it. **The timezone is absent on purpose.**"""

    frequency: Literal["once", "daily", "weekly", "monthly_by_weekday"]
    #: Local to the location, as HH:MM or HH:MM:SS.
    local_time: str = Field(min_length=4, max_length=8)
    duration_minutes: int = Field(ge=1, le=1440)
    starts_on: date
    until: date
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    week_of_month: int | None = Field(default=None, ge=-1, le=4)
    excluded_dates: list[date] = Field(default_factory=list, max_length=200)


class CapacityPolicyBody(BaseModel):
    capacity: int = Field(ge=1, le=10000)
    setup_minutes: int = Field(default=0, ge=0, le=120)
    cleanup_minutes: int = Field(default=0, ge=0, le=120)
    waitlist_capacity: int = Field(default=0, ge=0, le=10000)
    overbook_places: int = Field(default=0, ge=0, le=10000)


class RequirementBody(BaseModel):
    """What a session needs: a kind and a count, or a particular resource."""

    kind: Literal["staff", "room", "zone", "court", "equipment", "service", "composite"]
    quantity: int = Field(default=1, ge=1, le=10000)
    resource_id: str | None = None


class RestrictionBody(BaseModel):
    kind: Literal["min_age", "max_age", "skill", "entitlement"]
    value: str = Field(min_length=1, max_length=63)


class SchedulingResourceBody(BaseModel):
    """**No `brand_id`.** It is derived from the location, which is MOD-008's "derive a scope,
    never accept one": a caller sending both could put a location-scoped resource under a brand
    that does not own it."""

    resource_code: str = Field(min_length=2, max_length=48)
    resource_kind: Literal[
        "staff", "room", "zone", "court", "equipment", "service", "composite"]
    display_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1, le=10000)
    location_id: str | None = None
    person_id: str | None = None
    correlation_id: str


class AvailabilityBody(BaseModel):
    """A rota window. Weekly or dated, never both -- "every Tuesday" and "this Tuesday" are
    different rows."""

    resource_id: str
    window_kind: Literal["working", "break", "time_off"]
    starts_at: str = Field(min_length=4, max_length=8)
    ends_at: str = Field(min_length=4, max_length=8)
    weekday: int | None = Field(default=None, ge=0, le=6)
    on_date: date | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    correlation_id: str


class ScheduleTemplateBody(BaseModel):
    template_code: str = Field(min_length=2, max_length=48)
    display_name: str = Field(min_length=1, max_length=200)
    service_resource_id: str
    location_id: str
    rule: RecurrenceBody
    policy: CapacityPolicyBody
    requirements: list[RequirementBody] = Field(min_length=1, max_length=20)
    restrictions: list[RestrictionBody] = Field(default_factory=list, max_length=20)
    correlation_id: str


class ConflictCheckBody(BaseModel):
    """ADM-SCH-03's live check: a class that does not exist yet, asked about.

    **The same three blocks `ScheduleTemplateBody` takes**, so the dry run and the draft cannot
    be asked different questions -- which is `PreviewScheduleBody`'s own reason for mirroring
    the publish. What it does not take is a code, a name or a service resource: those are
    facts about the template rather than about the hour, and a read that demanded them could
    not answer until the form was finished.
    """

    location_id: str
    rule: RecurrenceBody
    policy: CapacityPolicyBody
    requirements: list[RequirementBody] = Field(min_length=1, max_length=20)
    #: **Bounded by the service rather than by this field**, which is `sellable_plans`'
    #: precedent: a `le` here would make the ceiling two numbers that can disagree, and the
    #: service is callable from somewhere other than a route. The sweep found it -- with the
    #: field bound, removing the service's guard changed nothing a caller could observe.
    limit: int = Field(default=scheduling.CONFLICT_PREVIEW, ge=1)


class PreviewScheduleBody(BaseModel):
    """What a publish would do, before it does it. The same fields the publish takes, so the
    two cannot be asked different questions."""

    rule: RecurrenceBody | None = None
    effective_from: date | None = None


class PublishScheduleBody(BaseModel):
    """**`acknowledged_impact` is what paragraph 1841's Critical Control costs.** A publish
    that moves or cancels a session somebody has booked is refused until it is acknowledged,
    and the preview is a separate read so the acknowledgement is informed."""

    rule: RecurrenceBody | None = None
    effective_from: date | None = None
    acknowledged_impact: bool = False
    correlation_id: str


class GenerateSessionsBody(BaseModel):
    """**`override_reason` is a permission, not a flag.** Sending one routes the request to
    `scheduling.conflict.override`, which is paragraph 1842's "permission and reason"."""

    from_date: date | None = None
    override_reason: str | None = Field(default=None, min_length=1, max_length=500)
    correlation_id: str


class SubstituteBody(BaseModel):
    replacement_resource_id: str
    reason: str = Field(min_length=1, max_length=500)
    override_reason: str | None = Field(default=None, min_length=1, max_length=500)
    correlation_id: str


class CancelSessionBody(BaseModel):
    """**The cancellation reason is a declared value**, because what a member is owed depends
    on it: an instructor's illness and a weather closure are different conversations."""

    cancellation_reason: Literal[
        "instructor_unavailable", "resource_unavailable", "insufficient_bookings",
        "facility_closed", "weather", "other"]
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class RelocateSessionBody(BaseModel):
    to_location_id: str
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class HandoffBody(BaseModel):
    to_resource_id: str
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class TakeHoldBody(BaseModel):
    """Take places on a session. MOD-020 will be the main caller; a front desk is the other.

    **No `age_years` and no `entitlements`.** The session's restrictions are evaluated here and
    the facts are derived from the person this hold names: their birth date is in
    `ppl_persons`, on this plane, behind the foreign key the hold already carries, and their
    entitlement grants are one join further. An earlier version took both from the body with a
    written defence that this module could not reach them, and a reviewer used it to put a
    fourteen-year-old in an 18+ class on the cheapest permission in the module.

    `skills` stays, because nothing in this build stores a skill -- so the caller's word is the
    only source there is, which is the one case where accepting it is honest.
    """

    person_id: str
    places: int = Field(default=1, ge=1, le=100)
    source_kind: Literal["booking", "walk_in", "migration"]
    source_ref: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)
    skills: list[str] = Field(default_factory=list, max_length=20)
    correlation_id: str


class SettleHoldBody(BaseModel):
    attended: bool = False
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class RetireBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


# ------------------------------------------------------------------ MOD-020 booking
#
# **No `age_years`, no `entitlement_grant_id` and no `no_show_count` on any body.** Each is a
# fact about the member that this build can read: the age is `ppl_persons.date_of_birth`, the
# grant is MOD-017's and is found by key, and the count is a sum over insert-only records.
# MOD-019 shipped the first of those as a body field with a written defence that turned out to
# be false, and a reviewer used it to put a fourteen-year-old in an 18+ class.


class BookingPolicyBody(BaseModel):
    """A version of the booking policy. **Rules only: a version is never edited.**"""

    policy_key: str = Field(min_length=2, max_length=48)
    display_name: str = Field(min_length=1, max_length=200)
    cancellation_hours: int = Field(default=12, ge=0, le=168)
    max_concurrent: int = Field(default=10, ge=1, le=100)
    quota: int | None = Field(default=None, ge=1, le=10000)
    quota_period: Literal["day", "week", "rolling_7_days", "rolling_30_days"] = (
        "rolling_7_days")
    checkin_grace_minutes: int = Field(default=15, ge=0, le=240)
    warn_after_no_shows: int = Field(default=2, ge=1, le=1000)
    strike_after_no_shows: int = Field(default=3, ge=1, le=1000)
    priority_rule: Literal["first_come", "membership_tier"] = "first_come"
    offer_minutes: int = Field(default=60, ge=1, le=1440)
    forfeits_entitlement: bool = True
    correlation_id: str


class CreateBookingBody(BaseModel):
    """**`entitlement_key` is a kind, not a grant.** Which grant a member holds is read from
    MOD-017; naming one would be naming somebody else's entitlement, which is the shape four
    modules have now shipped."""

    person_id: str
    policy_key: str = Field(min_length=2, max_length=48)
    source_kind: Literal["member", "waitlist", "front_desk", "migration"] = "member"
    entitlement_key: str | None = Field(default=None, min_length=1, max_length=63)
    #: Nothing in this build stores a skill, so a skill restriction on the session is only as
    #: good as whoever answers it. MOD-019's gap, inherited and named rather than hidden.
    skills: list[str] = Field(default_factory=list, max_length=20)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class CancelBookingBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class JoinWaitlistBody(BaseModel):
    """**No `tier`.** It was a field here, bounded `0..1000` and compared with nothing, so a
    basic member sent a zero and took the place a premium member had paid priority for. The
    tier is read from the member's own MOD-014 tags by `_tier_for`, which is where MOD-016
    reads the customer segment that chooses a price book."""

    person_id: str
    policy_key: str = Field(min_length=2, max_length=48)
    entitlement_key: str | None = Field(default=None, min_length=1, max_length=64)
    skills: list[str] = Field(default_factory=list, max_length=20)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class RetirePolicyBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class DeviceTypeBody(BaseModel):
    """A model of hardware and what it can be asked to do.

    **The capabilities are declared here and frozen when the type is published**, because a
    device snapshots them at registration -- MOD-012's review found the same shape open and a
    *required* scope could be added to a published version."""

    type_code: str = Field(min_length=2, max_length=48)
    vendor: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    kind: str
    display_name: str = Field(min_length=1, max_length=200)
    capabilities: list[str] = Field(min_length=1, max_length=7)
    correlation_id: str


class RegisterDeviceBody(BaseModel):
    """**No capabilities field.** A device can do what its model can do: the list is copied
    from the published type, because a caller naming its own would be a barcode reader that
    declares `access.actuate` and then asks to open a door nobody commissioned."""

    type_id: str
    location_id: str
    serial_number: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str


class ProvisionDeviceBody(BaseModel):
    """**`vault_ref` locates the key material and is not the key.** The pattern is checked by
    a constraint, because MOD-012 shipped a `vault_ref` that was merely non-blank -- which
    made a live secret a valid "reference" and the absence of a key column a convention."""

    fingerprint: str = Field(min_length=32, max_length=160)
    vault_ref: str = Field(min_length=4, max_length=400)
    not_before: datetime
    not_after: datetime
    correlation_id: str


class ConfigureDeviceBody(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict[str, Any] | None = None
    expected_version: int = Field(ge=1, le=1_000_000)
    correlation_id: str


class CommissionBody(BaseModel):
    """TSD paragraph 4172's hardware safety profile.

    The three booleans are claims a named commissioner makes about a building, which this
    software cannot verify -- and a profile claiming software control of egress is refused
    outright by `safety.check_profile` and by the constraint beside the table."""

    profile: str
    on_egress_path: bool
    fire_release_is_independent: bool
    local_emergency_input: bool
    evidence_ref: str = Field(min_length=4, max_length=400)
    door_description: str = Field(min_length=1, max_length=400)
    correlation_id: str


class CommissioningTestBody(BaseModel):
    test_name: str
    passed: bool
    detail: str | None = Field(default=None, max_length=1000)
    correlation_id: str


class DeviceStateBody(BaseModel):
    target: str
    reason: str | None = Field(default=None, max_length=500)
    correlation_id: str


class RotateCertificateBody(BaseModel):
    fingerprint: str = Field(min_length=32, max_length=160)
    vault_ref: str = Field(min_length=4, max_length=400)
    not_before: datetime
    not_after: datetime
    correlation_id: str


class RevokeCertificateBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


#: A version somebody names a build by, and nothing else. It reaches `firmware.updated` in
#: the outbox, which no erasure can clear, and a reviewer put a member's address in it.
_VERSION = r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$"
#: A SHA-256, lowercase hex. `content_digest` and `image_digest` already had this as a CHECK
#: because they land in a table; the sync-conflict digests land only in the outbox and so had
#: none, which is the validation applied in exactly the wrong places.
_SHA256 = r"^[0-9a-f]{64}$"


class FirmwareBody(BaseModel):
    type_id: str
    version: str = Field(min_length=1, max_length=64, pattern=_VERSION)
    image_ref: str = Field(min_length=4, max_length=400)
    image_digest: str = Field(min_length=64, max_length=64)
    release_notes: str = Field(min_length=1, max_length=2000)
    correlation_id: str


class FirmwareStatusBody(BaseModel):
    target: str
    reason: str | None = Field(default=None, max_length=500)
    correlation_id: str


class SnapshotBody(BaseModel):
    """**The TTL is minutes and is bounded at both ends.** Paragraph 1949 says "bounded" and
    names no number; five minutes to twelve hours is `snapshots.MIN_TTL` and `MAX_TTL`, read
    against paragraph 1953's sixty-second revocation target."""

    content_digest: str = Field(min_length=64, max_length=64)
    signature_ref: str | None = Field(default=None, max_length=400)
    ttl_minutes: int = Field(ge=5, le=720)
    correlation_id: str


class IssueCommandBody(BaseModel):
    """**`expires_in_seconds` is bounded and an unlock's is bounded harder.** A door opened a
    minute after somebody asked is a door opened for whoever is standing there now."""

    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_in_seconds: int | None = Field(default=None, ge=1, le=86_400)
    correlation_id: str


class DeliverCommandBody(BaseModel):
    signature_ref: str | None = Field(default=None, max_length=400)
    correlation_id: str


class SettleCommandBody(BaseModel):
    outcome: str
    detail: str | None = Field(default=None, max_length=1000)
    correlation_id: str


class HealthReportBody(BaseModel):
    latency_ms: int = Field(ge=0, le=600_000)
    error_count: int = Field(ge=0, le=1_000_000_000)
    storage_free_bytes: int = Field(ge=0, le=1 << 50)
    agent_version: str = Field(min_length=1, max_length=64, pattern=_VERSION)
    peripherals: dict[str, str] = Field(default_factory=dict)
    correlation_id: str


class SyncConflictBody(BaseModel):
    detail: str = Field(min_length=1, max_length=1000)
    local_digest: str = Field(min_length=64, max_length=64, pattern=_SHA256)
    remote_digest: str = Field(min_length=64, max_length=64, pattern=_SHA256)
    correlation_id: str


class DeviceSweepBody(BaseModel):
    limit: int = Field(default=500, ge=1, le=5000)
    correlation_id: str


class LeaveWaitlistBody(BaseModel):
    """A member's own exit. From `waiting` it is a withdrawal; from `offered` it is a decline,
    which releases the place as well."""

    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class SettleOfferBody(BaseModel):
    """**`declined` is the member's choice and the default is the clock.** An expiry returns
    the entry to the queue keeping its place; a decline ends it."""

    declined: bool = False
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class ConfirmOfferBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class CheckInBody(BaseModel):
    source: Literal["front_desk", "self_service", "device", "migration"] = "front_desk"
    correlation_id: str


class AttendanceIntentBody(BaseModel):
    intent: Literal["attending", "not_attending", "unsure"]
    source: Literal["app", "reminder_reply", "front_desk", "migration"] = "app"
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class RaiseAppealBody(BaseModel):
    """**One record, and the subject is the member the record is about.** The service and a
    trigger both check that, because nothing else relates the two."""

    subject_person_id: str
    against: Literal["fee", "credit_forfeit", "warning", "strike"]
    grounds: str = Field(min_length=1, max_length=2000)
    no_show_id: str | None = None
    cancellation_id: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class DecideAppealBody(BaseModel):
    """**No `decided_by`.** The decider is the authenticated identity and the person it is,
    both derived -- MOD-016's finding was a separation of duties compared against a field the
    caller supplied."""

    uphold: bool
    note: str = Field(min_length=1, max_length=2000)
    correlation_id: str


class SweepBody(BaseModel):
    """A sweep nothing drives. The limit is the caller's, bounded here."""

    limit: int = Field(default=200, ge=1, le=1000)
    correlation_id: str


# ------------------------------------------------------------------ MOD-022 access control
#
# **Nothing here takes a `person_id` for a decision, and nothing takes a policy.** A reader
# presents a credential value; the service resolves whose it is, reads the zone's live policy,
# and decides. A body that could name the subject would let a kiosk open a door as whoever it
# liked, and a body that could name the terms would let it choose the rules it is judged by --
# which is MOD-017's `reserve_entitlement` finding and MOD-013's `bypass_policy_ref` finding in
# a building. The one place a person is named is the staff override, where somebody is being
# admitted *against* the policy and the point of the row is that a named actor let a named
# person through.


#: **Every datetime a caller sends is bounded here, not in psycopg.**
#:
#: A naive timestamp -- no zone offset, which is what an embedded reader usually emits -- made
#: `at < presented.issued_at` raise `TypeError`, and a year-1 one made the arithmetic raise
#: `OverflowError`. Neither is `ValueError`, which is what the service catches, so both reached
#: the caller as a **500** on the two highest-volume routes in the module: the decision and the
#: event. The offline-queue path was unusable for that wire format.
#:
#: This is the repository's own rule -- "bound it at the boundary, or psycopg does it with a
#: 500" -- which `AccessPolicyBody` cites for its integers and which nothing applied to the
#: timestamps beside them. `AwareDatetime` refuses a naive value at the boundary with a 422
#: naming the field; the year bound keeps the arithmetic inside what `date` can represent.
ReaderMoment = Annotated[
    AwareDatetime,
    Field(ge=datetime(2000, 1, 1, tzinfo=UTC), le=datetime(2100, 1, 1, tzinfo=UTC)),
]


class ZoneBody(BaseModel):
    location_id: str
    zone_key: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=200)
    risk_class: str = Field(min_length=1, max_length=40)
    correlation_id: str


class ReclassifyZoneBody(BaseModel):
    """Tightening only. Loosening is refused by a trigger, not by this shape."""

    risk_class: str = Field(min_length=1, max_length=40)
    correlation_id: str


class AccessPointBody(BaseModel):
    zone_id: str
    device_id: str
    direction: str = Field(min_length=1, max_length=20)
    display_name: str = Field(min_length=1, max_length=200)
    correlation_id: str


class AccessPolicyBody(BaseModel):
    """The terms a decision cites.

    Every bound is checked here as well as in the schema, because an unbounded integer reaches
    psycopg as a `DataError` rather than the `CheckViolation` the handlers catch -- MOD-011's,
    MOD-012's and MOD-013's finding, three times over.
    """

    zone_id: str
    opens_minute: int | None = Field(default=None, ge=0, le=1439)
    # **1440, not 1439.** The window is half-open -- `opens <= minute < closes` -- so a
    # 24-hour club needs a close *at* midnight, and capping both ends at 1439 meant the only
    # way to express "always open" shut the zone for the last minute of every day. A
    # fence-post error in the one setting a gym that never closes has to use.
    closes_minute: int | None = Field(default=None, ge=0, le=1440)
    requires_entitlement: bool = True
    max_balance_minor: int | None = Field(default=None, ge=0, le=10**12)
    min_age_years: int | None = Field(default=None, ge=0, le=120)
    anti_passback_seconds: int = Field(default=0, ge=0, le=86400)
    capacity: int | None = Field(default=None, ge=0, le=10**6)
    correlation_id: str


class IssueCredentialBody(BaseModel):
    """`credential_value` is the thing presented. **Nothing stores it**: the service keeps a
    digest, which is why there is no column it could sit in."""

    person_id: str
    kind: str = Field(min_length=1, max_length=40)
    credential_value: str = Field(min_length=1, max_length=512)
    expires_at: ReaderMoment | None = None
    correlation_id: str


class EvaluateAccessBody(BaseModel):
    """What a reader saw. **Nothing in here decides anything.**

    **There is no `signature_verified` and no `kind`.** The first carried the reader's claim
    that it had checked a WebAuthn-style signature; nothing read it and nothing could, since
    this build has no key vault -- a field that claims to record an assertion and records none
    is worse than no field. The second decided which controls ran at all and is now read from
    the enrolment.

    `reader_clock_at` is the reader's own clock, which the server subtracts from its own to
    get the skew. It used to be the skew, which is a number a device chooses about itself.
    """

    point_id: str
    credential_value: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=200)
    # **Which way the member is walking**, at a lane that reads both. Taking it from the
    # reader is safe because lying is self-defeating: a presentation claiming `exit` is not a
    # decision and issues no unlock, so the only thing a false `exit` achieves is a door that
    # stays shut. Without it, a `both` lane evaluated every presentation as an entry and could
    # refuse a member on the way out -- paragraph 4177, reached by wiring the ordinary
    # hardware.
    reported_direction: Literal["entry", "exit"] = "entry"
    # **No `kind`.** It was here and it decided which controls ran: `check_clock`,
    # `check_presentation` and the replay cache are each guarded on the credential being a
    # rotating one, so a reader sending `{"kind": "nfc_card"}` with a captured QR token
    # turned off paragraph 4183's whole validation and replayed it for ever. The kind is a
    # fact about the enrolment and the service reads it from the binding.
    rotation_counter: int | None = Field(default=None, ge=0, le=2**31 - 1)
    nonce: str | None = Field(default=None, max_length=200)
    token_issued_at: ReaderMoment | None = None
    token_expires_at: ReaderMoment | None = None
    # **The reader's own clock, from which the server computes the skew.** It used to be the
    # skew itself, which is a number the device chooses about itself -- so paragraph 4162's
    # refusal was defeated by a device claiming zero, while `offline.mode_for`'s docstring
    # said "a device that reports its own mode reports the mode it would like to be in" and
    # derived the posture from exactly that claim. A clock is a fact the server can subtract
    # from its own; a skew is an assertion.
    reader_clock_at: ReaderMoment | None = None
    correlation_id: str


class OverrideAccessBody(BaseModel):
    """The one body in the module that names a person, because admitting somebody against the
    policy is exactly what it records."""

    point_id: str
    person_id: str
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class EntryExitBody(BaseModel):
    """What a reader *saw*, which is not what was decided.

    `occurred_at` is the reader's clock and it is required, because an event the server times
    cannot be reconciled against an offline queue. `decision_id` is optional for the same
    reason: an offline reader decided from a snapshot and has no server decision to cite.
    """

    point_id: str
    direction: str = Field(min_length=1, max_length=20)
    occurred_at: ReaderMoment
    source: str = Field(min_length=1, max_length=20)
    credential_value: str | None = Field(default=None, max_length=512)
    decision_id: str | None = None
    local_sequence: int | None = Field(default=None, ge=0, le=2**31 - 1)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class EmergencyUnlockBody(BaseModel):
    zone_id: str
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=200)
    correlation_id: str


class ReviewUnlockBody(BaseModel):
    note: str = Field(min_length=1, max_length=1000)
    correlation_id: str


class ReconcileAccessBody(BaseModel):
    point_id: str
    limit: int = Field(default=500, ge=1, le=5000)
    correlation_id: str


class AccessSnapshotBody(BaseModel):
    """`ttl_minutes` is a request, not the answer: the zone's risk class narrows it, and a
    high-risk zone's ceiling is two hours whatever is asked for here."""

    point_id: str
    content_digest: str = Field(min_length=64, max_length=64, pattern=_SHA256)
    ttl_minutes: int = Field(ge=1, le=720)
    signature_ref: str | None = Field(default=None, max_length=500)
    correlation_id: str


# ---------------------------------------------------------------- MOD-026 (AUT-02)
#
# **Every subject and status is a `Literal`, not a string.** The schema carries the same
# closed sets and `app/tasks/` carries them a third time; what a `Literal` adds is a refusal
# at the boundary instead of a 500 from a CHECK, which is the id-validation lesson applied to
# an enumeration. **It does not name the field**: this application replaced FastAPI's
# validation handler because the default echoed the offending input into its own 422 and
# `json.dumps` then refused a `NaN` the parser had accepted -- a 500 from inside a 422 on
# every route -- so the answer is `{"error": "invalid_request"}` and nothing more. The three
# encodings are compared by `test_tasks_domain.py` so they cannot drift: MOD-020 shipped two
# that agreed with each other and not with the service.
_SUBJECT_KIND = Literal[
    "member", "lead", "tenant", "invoice", "incident", "device", "booking", "asset",
    "workflow"]
_WORK_PRIORITY = Literal["low", "normal", "high", "urgent"]
#: ADM-TSK-01's three: "assigned by a person, generated by an automation, or suggested by
#: Veyro". A `Literal` on the body buys a refusal at the boundary rather than a 500 from a
#: CHECK, which is what this application's own 422 handler is for.
_WORK_SOURCE = Literal["manual", "automation", "ai"]


class TaskQueueBody(BaseModel):
    """A work queue. `location_id` is a label rather than a boundary; see the listing."""

    queue_key: str = Field(min_length=2, max_length=63)
    display_name: str = Field(min_length=1, max_length=200)
    location_id: str | None = None
    correlation_id: str


class BusinessHoursBody(BaseModel):
    """One window on a location's calendar.

    **Exactly one of `weekday` and `on_date`**, which the schema also refuses: a row with both
    is two rules and a row with neither binds nothing while reading as a calendar entry.
    `opens_at` and `closes_at` are `HH:MM`, parsed at the boundary so a malformed one is a 422
    naming the field rather than a 500 from `psycopg`.
    """

    location_id: str
    kind: Literal["open", "closed"]
    weekday: int | None = Field(default=None, ge=0, le=6)
    on_date: date | None = None
    opens_at: str | None = Field(default=None, max_length=8)
    closes_at: str | None = Field(default=None, max_length=8)
    note: str | None = Field(default=None, max_length=500)
    correlation_id: str


class TaskCaseBody(BaseModel):
    """COM-02-R03's container. `idempotency_key` is required, because a create that is not
    idempotent to the caller tells a client whose request timed out that the work failed."""

    case_number: str = Field(min_length=2, max_length=32)
    title: str = Field(min_length=1, max_length=500)
    queue_id: str
    subject_kind: _SUBJECT_KIND
    subject_id: str | None = None
    priority: _WORK_PRIORITY = "normal"
    recurs_from_case_id: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)
    # **Required, with no default.** ADM-TSK-01: "The source is always named -- a task nobody
    # can account for gets ignored." A default of `manual` would name it for a caller that
    # forgot, which is the state the column exists to prevent, and this build has exactly two
    # producers: a person on a screen and the SLA sweep.
    source: _WORK_SOURCE
    correlation_id: str


class CaseEntryBody(BaseModel):
    """A line on a case's timeline. `document_ref` is a locator for a file this build does
    not hold -- there is no object store -- so the shape is what keeps the absence of a
    payload column a control rather than a naming convention."""

    entry_kind: Literal["note", "communication", "document", "status_change", "escalation"]
    summary: str = Field(min_length=1, max_length=5000)
    document_ref: str | None = Field(default=None, max_length=500)
    occurred_at: datetime | None = None
    correlation_id: str


class CaseSettleBody(BaseModel):
    """Resolve or close. A case moves forward only; a problem that returns is a new case
    citing this one."""

    target: Literal["resolved", "closed"]
    resolution_reason: str = Field(min_length=1, max_length=2000)
    correlation_id: str


#: An affected record's kinds: the subject vocabulary minus `tenant`. An affected record
#: names a specific thing, and a case about the tenant is about the row's own `tenant_id`,
#: which RLS already bounds -- so the value is refused at the boundary rather than by a CHECK.
_AFFECTED_KIND = Literal[
    "member", "lead", "invoice", "incident", "device", "booking", "asset", "workflow"]


class CaseAssignBody(BaseModel):
    """ADM-CC-06's assign, take over and release. `null` is the release.

    **`to_self` is a flag and the person is derived**, which is "Assign to me" and the one of
    the three actions a client cannot express: a browser holds an `identity_id` and the link
    to a person is MOD-014's, so there is no person id for it to send. A reader who could name
    themselves could also name somebody else and call it a self-assignment -- derive, never
    accept, and the two fields are refused together because a request carrying both is a
    caller that does not know which it meant.
    """

    assignee_person_id: str | None = None
    to_self: bool = False
    correlation_id: str

    @model_validator(mode="after")
    def _one_or_the_other(self) -> CaseAssignBody:
        if self.to_self and self.assignee_person_id is not None:
            raise ValueError("to_self names the caller, so no person id goes with it")
        return self


class CaseSnoozeBody(BaseModel):
    """A deferral, which the canvas requires to carry both a date and an account of why."""

    snoozed_until: datetime
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class CaseReturnBody(BaseModel):
    """Bringing a deferred case back early, which also states why."""

    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class CaseAffectedBody(BaseModel):
    """One of the records an exception is about."""

    affected_kind: _AFFECTED_KIND
    affected_id: str
    correlation_id: str


class CaseAffectedWithdrawBody(BaseModel):
    """Taking one off, with the reason the row keeps."""

    affected_kind: _AFFECTED_KIND
    affected_id: str
    reason: str = Field(min_length=1, max_length=500)
    correlation_id: str


class TaskBody(BaseModel):
    """AUT-02-R01 and R02."""

    queue_id: str
    case_id: str | None = None
    title: str = Field(min_length=1, max_length=500)
    subject_kind: _SUBJECT_KIND
    subject_id: str | None = None
    assignee_person_id: str | None = None
    priority: _WORK_PRIORITY = "normal"
    due_at: datetime | None = None
    evidence_ref: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=200)
    source: _WORK_SOURCE
    correlation_id: str


class TaskStatusBody(BaseModel):
    """`reason` is required by the service for a settlement and refused as blank there, which
    is where the rule can say why: "why was this not done" is the question the outcome
    reporting exists to answer."""

    target: Literal["open", "in_progress", "blocked", "done", "cancelled"]
    reason: str | None = Field(default=None, max_length=2000)
    correlation_id: str


class TaskAssignBody(BaseModel):
    """`None` is a real value: unassigning returns the work to its queue, which is a state the
    workload report has to be able to count rather than an incomplete row."""

    assignee_person_id: str | None = None
    correlation_id: str


class SlaClockBody(BaseModel):
    """A target on one task or one case.

    **No `location_id`.** It is derived from the subject's queue, because a caller able to
    name one could measure a promise against a calendar the work is not done in -- MOD-017's
    `brand_id` finding, where an off-peak grant was drawn on at seven in the evening.
    `warn_at_basis_points` is basis points rather than a float: a fraction stored as a double
    is a figure that renders differently in two places.
    """

    task_id: str | None = None
    case_id: str | None = None
    target_seconds: int = Field(ge=60, le=31_536_000)
    escalate_to_queue_id: str | None = None
    warn_at_basis_points: int = Field(default=8000, ge=1, le=9999)
    correlation_id: str


class SlaSettleBody(BaseModel):
    """`breached` is here as well as `met`, because a target can be judged missed by somebody
    who saw it happen rather than only by arithmetic -- and the judgement is final either
    way, with a new target on the same subject as the remedy."""

    status: Literal["met", "breached", "cancelled"]
    reason: str = Field(min_length=1, max_length=2000)
    correlation_id: str


class TaskDependencyBody(BaseModel):  # noqa: D101
    depends_on_task_id: str
    correlation_id: str


class ChecklistItemBody(BaseModel):  # noqa: D101
    ordinal: int = Field(ge=1, le=200)
    label: str = Field(min_length=1, max_length=500)
    correlation_id: str


def _recurrence(rule: RecurrenceBody) -> dict[str, Any]:
    """A recurrence body as the service takes it.

    **No timezone**: the service reads it from the location, and leaving it out of this
    conversion is what makes that impossible to bypass from a route.
    """
    return {
        "frequency": rule.frequency, "local_time": rule.local_time,
        "duration_minutes": rule.duration_minutes,
        "starts_on": rule.starts_on.isoformat(), "until": rule.until.isoformat(),
        "weekdays": rule.weekdays, "week_of_month": rule.week_of_month,
        "excluded_dates": [d.isoformat() for d in rule.excluded_dates],
    }


def create_app(
    settings: Settings | None = None,
    *,
    tenant_pool: Any = None,
    platform_pool: Any = None,
    identity_pool: Any = None,
    clock: Callable[[], float] = time,
) -> FastAPI:
    """Build the application.

    `clock` is the seam the rate limiter reads its window from. It exists because the limiter's
    window is fixed-length and every refused login deliberately costs one scrypt: a test that
    proves the bound by making thirty-two real attempts is a test whose green depends on the
    machine finishing them inside one window, and a slower runner rolls the window, resets the
    count and never sees a 429. That is the same family as the budget-consuming tests this
    repository already records -- a green that depends on something other than the behaviour
    under test -- and it cost one red CI run to find. Production passes nothing and gets
    `time`.
    """
    cfg = settings or load_settings()
    owned_pools: list[Any] = []
    # One limiter per application. In this process's memory, which `app.observability.ratelimit`
    # argues for at length: the login path is reachable without authentication and its subject
    # is caller-supplied, so a durable counter would be an unbounded-growth primitive written by
    # anybody. The cost is that two replicas each allow the full budget.
    #
    # **The budget is the table's unless `local` says otherwise.** `config.load_settings`
    # refuses `VEYRO_API_REQUEST_BUDGET` outside the local environment, so this override
    # cannot widen a control in development or staging; it exists because the browser suite
    # makes more requests in a minute than any operator does, and raising the table's own
    # number to suit a test is the mistake that number's comment names.
    limiter = ratelimit.Limiter(
        budgets=None if cfg.api_request_budget is None
        else {**ratelimit.BUDGETS, "api.request": cfg.api_request_budget})

    # **And the scrypt work factor, for the same reason one paragraph up.** It is process-wide
    # rather than a parameter because the cost is a deployment fact and because the test
    # harness builds an owner through the *service* layer, reaching past this app -- an
    # override most call sites did not pass would apply to some hashes and not others, which
    # tells you nothing about either cost. `config.load_settings` refuses the setting outside
    # `local` and `secrets.use_cost_log2` bounds it again, so lowering it is two refusals away
    # from a deployed environment. Set unconditionally, because `None` is the deployed cost and
    # a process that skipped the call would keep whatever a previous one had set.
    secrets.use_cost_log2(cfg.scrypt_cost_log2)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal tenant_pool, platform_pool, identity_pool
        if identity_pool is None:
            identity_pool = db.make_identity_pool(cfg.database_url)
            owned_pools.append(identity_pool)
        if tenant_pool is None:
            tenant_pool = db.make_tenant_pool(cfg.database_url)
            owned_pools.append(tenant_pool)
        if platform_pool is None:
            platform_pool = db.make_platform_pool(cfg.database_url)
            owned_pools.append(platform_pool)
        app.state.identity_pool = identity_pool
        app.state.tenant_pool = tenant_pool
        app.state.platform_pool = platform_pool
        try:
            yield
        finally:
            for pool in owned_pools:
                pool.close()

    app = FastAPI(
        title="Veyro API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        """A fixed 422, with none of the request echoed back.

        FastAPI's default handler puts the offending *input* into the response. Two problems.
        It renders with `json.dumps`, which refuses the non-standard `NaN` and `Infinity`
        literals that `json.loads` happily accepted on the way in -- so a body carrying one
        produced a 500 from inside the 422, on every route in this application rather than
        only the new ones. And echoing raw input is the shape that turns a validation error
        into a reflection primitive. Every other error in this API is `{"error": <fixed
        code>}`; this one now matches.
        """
        return JSONResponse(status_code=422, content={"error": "invalid_request"})

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        # `Retry-After` on a 429, because computing a backoff and not sending it leaves the
        # client nothing to back off by -- which makes choosing 429 over 403 decorative.
        headers = ({"Retry-After": str(exc.retry_after_seconds)}
                   if isinstance(exc, TooManyRequests) else None)
        return JSONResponse(status_code=exc.status, content={"error": exc.code},
                            headers=headers)

    def permit(session: dict[str, Any], action: str, correlation_id: str | None = None,
               **context: Any) -> authz_gate.Gate:
        """The one way a route asks whether its caller may act.

        **It returns the gate, not the session, because the gate carries the mask.** MOD-008
        computes `masked_fields` on every allowed decision and from MOD-008 to MOD-013 nothing
        read it -- "computed, not applied" was a standing gap in CLAUDE.md for five modules.
        MOD-014 is the first module with a read path that has fields worth masking, and it takes
        the list from here. A route that ignores the return value is unchanged.

        Every gated route in this file goes through here, and `authz.require` writes the denial
        to the audit log itself, so a surface cannot ask the question and forget to record the
        answer. The tenant comes from the resolved session rather than the header, so the two
        cannot drift.

        A caller that supplies no `correlation_id` gets one minted here. Most read routes carry
        none, and an audit row with a handle nobody can trace back is still better than a row
        that could not be written at all -- but a caller that wants its denials findable should
        send one.

        Two MOD-011 concerns ride here because this is the one chokepoint every gated route
        passes: the per-identity request limit, checked before the gate because a limiter that
        runs after the expensive part is not protecting anything, and the denial counter.
        """
        rate_limit(limit_key="api.request", tenant_id=session["tenant_id"],
                   subject=str(session["identity_id"]))
        try:
            gate = authz.require(identity_pool, session["tenant_id"],
                                 identity_id=session["identity_id"],
                                 session_aal=session["aal"], action=action,
                                 correlation_id=correlation_id or str(uuid4()), **context)
        except ServiceError:
            _count_denial(session["tenant_id"], action)
            raise
        return gate

    def _count_denial(tenant_id: str, action: str) -> None:
        """Roll a refusal into `authz.denials`, and never let the bookkeeping outrank the answer.

        The swallow below is narrow and deliberate, not a general policy for metric failures. A
        refusal has already been written to MOD-008's audit chain, which is the evidence; this
        point is a convenience rollup. If recording it raised, the caller would receive 500
        instead of 403 -- and 500 reads as "try again", which is exactly the wrong advice when
        the answer is "you may not". A refusal outranks its own counter.
        """
        permission = authz_catalog.PERMISSIONS.get(action)
        if permission is None:
            return
        try:
            obs_metrics.observe(tenant_pool, tenant_id, metric_key="authz.denials", total=1.0,
                                dimensions={"category": permission.category})
        except Exception:  # noqa: BLE001 -- see the docstring; the refusal is what must arrive
            pass

    def rate_limit(*, limit_key: str, tenant_id: str, subject: str) -> None:
        """ApplyRateLimit at a surface, refusing with 429 when the window budget is spent.

        `subject` is whatever bounds the budget: an identity on a gated route, and a **hash** of
        the identifier on the unauthenticated ones, because the limiter would otherwise hold a
        map of every address anybody has tried to log in as.
        """
        verdict = limiter.check(tenant_id=tenant_id, limit_key=limit_key, subject=subject,
                                now_epoch=clock())
        if not verdict.allowed:
            raise TooManyRequests("rate_limited", verdict.retry_after_seconds)

    def limit_subject(value: str) -> str:
        """A stable, non-reversible handle for an unauthenticated caller's own identifier.

        **Normalized the way the lookup normalizes, not the way the caller typed it.** The first
        version lowercased and stripped the ends, which agrees with `normalize_email` and does
        not agree with `normalize_phone` -- that one removes whitespace, parentheses and hyphens
        from anywhere in the string. So eight spellings of one phone number resolved to one
        identity and took eight full login budgets, and a reviewer walked past the limit without
        ever seeing a 429 while every attempt still cost the server a scrypt. Derive, never
        accept, applied to a rate-limit key.
        """
        return hashlib.sha256(
            identity.normalize_identifier(value).encode("utf-8")
        ).hexdigest()

    def token_subject(token: str) -> str:
        """The same for a bearer token, which is **not** an identifier and is case-sensitive.

        Routing a token through `limit_subject` would lowercase it, and two distinct tokens
        differing only in case would then share one budget. Small, and the wrong kind of small:
        a limiter key that merges two callers is the shape the phone-spelling finding was,
        pointing the other way.
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "veyro-api",
            "environment": cfg.environment,
            "release": cfg.release,
        }

    # ------------------------------------------------------------------ platform plane

    @app.post("/platform/tenants", status_code=201)
    def provision(body: ProvisionTenantBody) -> JSONResponse:
        envelope: dict[str, Any] = {
            "external_key": body.external_key,
            "actor_id": body.actor_id,
            "correlation_id": body.correlation_id,
            "idempotency_key": body.idempotency_key,
        }
        if body.expected_version is not None:
            envelope["expected_version"] = body.expected_version
        tenant, created = service.provision_tenant(
            platform_pool, envelope, body.display_name, body.region
        )
        return JSONResponse(status_code=201 if created else 200, content=tenant.as_dict())

    @app.get("/platform/tenants/{tenant_id}")
    def read_tenant(tenant_id: str) -> dict[str, Any]:
        return service.get_tenant(platform_pool, tenant_id).as_dict()

    @app.get("/platform/tenants/{tenant_id}/history")
    def read_history(tenant_id: str) -> list[dict[str, Any]]:
        service.get_tenant(platform_pool, tenant_id)
        return service.tenant_history(platform_pool, tenant_id)

    @app.post("/platform/tenants/{tenant_id}/{action}")
    def transition(tenant_id: str, action: str, body: TransitionBody) -> dict[str, Any]:
        tenant = service.transition_tenant(
            platform_pool, tenant_id, action,
            require_uuid(body.actor_id, "actor_id"), body.correlation_id,
            body.expected_version,
        )
        return tenant.as_dict()

    @app.delete("/platform/tenants/{tenant_id}")
    def remove_tenant(tenant_id: str) -> None:
        service.delete_tenant(platform_pool, tenant_id)

    # ------------------------------------------------------------------ tenant plane

    @app.post("/organizations", status_code=201)
    def add_organization(
        tenant_id: TenantId,
        session: Session,
        body: OrganizationBody,
    ) -> dict[str, Any]:
        permit(session, "tenancy.organization.write", body.correlation_id)
        return service.create_organization(
            tenant_pool, tenant_id, body.legal_name, body.country_code,
            correlation_id=body.correlation_id
        )

    @app.get("/organizations")
    def get_organizations(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "tenancy.organization.read")
        return service.list_organizations(tenant_pool, tenant_id)

    @app.post("/brands", status_code=201)
    def add_brand(tenant_id: TenantId, session: Session, body: BrandBody) -> dict[str, Any]:
        permit(session, "tenancy.brand.write")
        return service.create_brand(
            tenant_pool, tenant_id,
            require_uuid(body.organization_id, "organization_id"), body.brand_name)

    @app.post("/legal-entities", status_code=201)
    def add_legal_entity(
        tenant_id: TenantId, session: Session, body: LegalEntityBody
    ) -> dict[str, Any]:
        """The legal entity that invoices. MOD-004 built the table and left it unreachable.

        COM-03-R07 requires fiscal series and serial uniqueness per legal entity, so MOD-017
        cannot number an invoice without one -- which is how a two-module-old gap surfaced.
        """
        permit(session, "tenancy.organization.write", body.correlation_id)
        return service.create_legal_entity(
            tenant_pool, tenant_id,
            require_uuid(body.organization_id, "organization_id"),
            body.registered_name, tax_number=body.tax_number,
        )

    @app.get("/legal-entities")
    def get_legal_entities(
        tenant_id: TenantId, session: Session
    ) -> list[dict[str, Any]]:
        permit(session, "tenancy.organization.read")
        return service.list_legal_entities(tenant_pool, tenant_id)

    @app.get("/brands")
    def get_brands(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        """The tier that had a writer and no reader. Same permission as its siblings."""
        permit(session, "tenancy.organization.read")
        return service.list_brands(tenant_pool, tenant_id)

    @app.post("/locations", status_code=201)
    def add_location(tenant_id: TenantId, session: Session, body: LocationBody) -> dict[str, Any]:
        permit(session, "tenancy.location.write")
        return service.create_location(
            tenant_pool, tenant_id, require_uuid(body.brand_id, "brand_id"),
            body.location_name, body.timezone
        )

    @app.get("/locations")
    def get_locations(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "tenancy.organization.read")
        return service.list_locations(tenant_pool, tenant_id)

    # --------------------------------------------------- MOD-005 configuration and flags

    @app.post("/config/definitions", status_code=201)
    def define_config(
        tenant_id: TenantId,
        session: Session,
        body: DefinitionBody,
    ) -> dict[str, Any]:
        permit(session, "config.definition.write")
        return config.define_config(
            tenant_pool, tenant_id, config_key=body.config_key, value_type=body.value_type,
            default_value=body.default_value, owner_module=body.owner_module,
            validation=body.validation, description=body.description,
        )

    @app.get("/config/definitions")
    def get_definitions(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "config.definition.read")
        return config.list_definitions(tenant_pool, tenant_id)

    @app.post("/config/values", status_code=201)
    def publish_value(
        tenant_id: TenantId,
        session: Session,
        body: PublishValueBody,
    ) -> dict[str, Any]:
        permit(session, "config.value.publish", body.correlation_id)
        return config.publish_config_version(
            tenant_pool, tenant_id, config_key=body.config_key, scope_type=body.scope_type,
            value=body.value, published_by=body.published_by,
            correlation_id=body.correlation_id,
            brand_id=optional_uuid(body.brand_id, "brand_id"),
            location_id=optional_uuid(body.location_id, "location_id"),
            expected_version=body.expected_version,
        )

    @app.get("/config/values/{config_key}/history")
    def value_history(
        tenant_id: TenantId,
        session: Session,
        config_key: str,
    ) -> list[dict[str, Any]]:
        permit(session, "config.definition.read")
        return config.config_history(tenant_pool, tenant_id, config_key)

    @app.post("/config/values/{config_key}/rollback", status_code=201)
    def rollback_value(
        tenant_id: TenantId, session: Session, config_key: str, body: RollbackBody
    ) -> dict[str, Any]:
        permit(session, "config.value.rollback", body.correlation_id)
        return config.rollback_config(
            tenant_pool, tenant_id, config_key=config_key, scope_type=body.scope_type,
            to_version=body.to_version, published_by=body.published_by,
            correlation_id=body.correlation_id,
            brand_id=optional_uuid(body.brand_id, "brand_id"),
            location_id=optional_uuid(body.location_id, "location_id"),
        )

    @app.get("/config/resolved")
    def resolved_config(
        tenant_id: TenantId,
        session: Session,
        brand_id: str | None = None,
        location_id: str | None = None,
    ) -> dict[str, Any]:
        permit(session, "config.definition.read")
        return config.resolve_config(
            tenant_pool, tenant_id,
            brand_id=optional_uuid(brand_id, "brand_id"),
            location_id=optional_uuid(location_id, "location_id"),
        )

    @app.post("/config/preview")
    def preview_value(tenant_id: TenantId, session: Session, body: PreviewBody) -> dict[str, Any]:
        permit(session, "config.definition.read")
        return config.preview_config(
            tenant_pool, tenant_id, config_key=body.config_key, value=body.value,
            scope_type=body.scope_type,
            brand_id=optional_uuid(body.brand_id, "brand_id"),
            location_id=optional_uuid(body.location_id, "location_id"),
        )

    @app.put("/flags/{flag_key}")
    def set_flag(
        tenant_id: TenantId,
        session: Session,
        flag_key: str,
        body: FeaturePolicyBody,
    ) -> dict[str, Any]:
        permit(session, "config.flag.write")
        return config.set_feature_policy(
            tenant_pool, tenant_id, flag_key=flag_key, enabled=body.enabled,
            default_variant=body.default_variant, rules=body.rules,
            description=body.description, expected_version=body.expected_version,
        )

    @app.post("/flags/{flag_key}/kill-switch")
    def kill_switch(
        tenant_id: TenantId,
        session: Session,
        flag_key: str,
        body: KillSwitchBody,
    ) -> dict[str, Any]:
        permit(session, "config.kill_switch.engage")
        return config.set_kill_switch(
            tenant_pool, tenant_id, flag_key=flag_key, engaged=body.engaged, reason=body.reason
        )

    @app.get("/flags")
    def evaluate_flags(
        tenant_id: TenantId, session: Session,
        context: Annotated[dict[str, str], Depends(evaluation_context)],
        subject_id: str,
    ) -> dict[str, Any]:
        permit(session, "config.flag.read")
        return config.evaluate_flags(
            tenant_pool, tenant_id, subject_id=subject_id, context=context
        )

    @app.post("/experiments", status_code=201)
    def create_experiment(
        tenant_id: TenantId,
        session: Session,
        body: ExperimentBody,
    ) -> dict[str, Any]:
        permit(session, "config.experiment.write")
        return config.create_experiment(
            tenant_pool, tenant_id, experiment_key=body.experiment_key, variants=body.variants
        )

    @app.post("/experiments/{experiment_key}/status")
    def experiment_status(
        tenant_id: TenantId, session: Session, experiment_key: str, body: ExperimentStatusBody
    ) -> dict[str, Any]:
        permit(session, "config.experiment.write")
        return config.set_experiment_status(
            tenant_pool, tenant_id, experiment_key=experiment_key, status=body.status
        )

    @app.post("/experiments/{experiment_key}/allocate")
    def allocate(
        tenant_id: TenantId, session: Session, experiment_key: str, body: AllocateBody
    ) -> dict[str, Any]:
        permit(session, "config.experiment.allocate", body.correlation_id)
        return config.allocate_experiment(
            tenant_pool, tenant_id, experiment_key=experiment_key, subject_id=body.subject_id,
            correlation_id=body.correlation_id,
        )

    @app.get("/experiments/{experiment_key}/exposures")
    def exposures(
        tenant_id: TenantId,
        session: Session,
        experiment_key: str,
    ) -> list[dict[str, Any]]:
        permit(session, "config.flag.read")
        return config.experiment_exposures(
            tenant_pool, tenant_id, experiment_key=experiment_key
        )

    @app.get("/config/bundle")
    def config_bundle(
        tenant_id: TenantId, session: Session,
        context: Annotated[dict[str, str], Depends(evaluation_context)],
        subject_id: str,
        brand_id: str | None = None,
        location_id: str | None = None,
    ) -> dict[str, Any]:
        """PLT-02-R06: one read for a mobile app, kiosk or managed device."""
        permit(session, "config.flag.read")
        return config.bundle(
            tenant_pool, tenant_id, subject_id=subject_id, context=context,
            brand_id=optional_uuid(brand_id, "brand_id"),
            location_id=optional_uuid(location_id, "location_id"),
        )

    # --------------------------------------------------- MOD-015 plans and billing

    @app.post("/platform/plans", status_code=201)
    def create_plan(body: PlanBody) -> dict[str, Any]:
        return billing.create_plan(
            platform_pool, plan_code=body.plan_code, plan_version=body.plan_version,
            edition=body.edition, currency=body.currency, region=body.region,
            billing_interval=body.billing_interval, base_price_minor=body.base_price_minor,
            trial_days=body.trial_days, contract_months=body.contract_months,
            prices=body.prices, entitlements=body.entitlements,
        )

    @app.post("/platform/plans/{plan_code}/{plan_version}/status")
    def plan_status(plan_code: str, plan_version: int, body: PlanStatusBody) -> dict[str, Any]:
        return billing.set_plan_status(
            platform_pool, plan_code=plan_code, plan_version=plan_version, status=body.status
        )

    @app.get("/platform/plans")
    def get_plans() -> list[dict[str, Any]]:
        return billing.list_plans(platform_pool)

    @app.get("/platform/plans/{plan_code}")
    def get_one_plan(plan_code: str, plan_version: int | None = None) -> dict[str, Any]:
        return billing.get_plan(platform_pool, plan_code=plan_code, plan_version=plan_version)

    @app.post("/subscription", status_code=201)
    def start_subscription(
        tenant_id: TenantId, session: Session, body: StartSubscriptionBody
    ) -> dict[str, Any]:
        permit(session, "billing.subscription.write", body.correlation_id)
        return billing.start_subscription(
            tenant_pool, platform_pool, tenant_id, plan_code=body.plan_code,
            plan_version=body.plan_version, actor_id=require_uuid(body.actor_id, "actor_id"),
            correlation_id=body.correlation_id, start_on=body.start_on,
            partner_code=body.partner_code, revenue_share_bp=body.revenue_share_bp,
        )

    @app.get("/subscription")
    def read_subscription(tenant_id: TenantId, session: Session) -> dict[str, Any]:
        permit(session, "billing.subscription.read")
        return billing.get_subscription(tenant_pool, tenant_id)

    @app.get("/subscription/history")
    def read_subscription_history(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "billing.subscription.read")
        return billing.subscription_history(tenant_pool, tenant_id)

    @app.post("/subscription/transition")
    def transition_subscription(
        tenant_id: TenantId, session: Session, body: SubscriptionCommandBody
    ) -> dict[str, Any]:
        permit(session, "billing.subscription.write", body.correlation_id)
        return billing.transition_subscription(
            tenant_pool, tenant_id, command=body.command,
            actor_id=require_uuid(body.actor_id, "actor_id"),
            correlation_id=body.correlation_id, reason=body.reason,
            expected_version=body.expected_version,
        )

    @app.post("/subscription/plan")
    def change_subscription_plan(
        tenant_id: TenantId,
        session: Session,
        body: ChangePlanBody,
    ) -> dict[str, Any]:
        permit(session, "billing.subscription.write", body.correlation_id)
        return billing.change_plan(
            tenant_pool, platform_pool, tenant_id, plan_code=body.plan_code,
            plan_version=body.plan_version, actor_id=require_uuid(body.actor_id, "actor_id"),
            correlation_id=body.correlation_id, effective_on=body.effective_on,
            in_use=body.in_use, acknowledge_reductions=body.acknowledge_reductions,
        )

    @app.post("/entitlements", status_code=201)
    def grant_entitlement(
        tenant_id: TenantId,
        session: Session,
        body: EntitlementGrantBody,
    ) -> dict[str, Any]:
        permit(session, "billing.subscription.write")
        return billing.grant_entitlement(
            tenant_pool, tenant_id, feature_code=body.feature_code,
            limit_value=body.limit_value, unlimited=body.unlimited,
        )

    @app.get("/entitlements")
    def get_entitlements(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "billing.subscription.read")
        return billing.list_entitlements(tenant_pool, tenant_id)

    @app.get("/entitlements/{feature_code}/check")
    def entitlement_check(
        tenant_id: TenantId, session: Session, feature_code: str, quantity: int
    ) -> dict[str, Any]:
        permit(session, "billing.subscription.read")
        return billing.check_entitlement(
            tenant_pool, tenant_id, feature_code=feature_code, quantity=quantity
        )

    @app.post("/meters", status_code=201)
    def define_meter(tenant_id: TenantId, session: Session, body: MeterBody) -> dict[str, Any]:
        permit(session, "billing.meter.write")
        return billing.define_meter(
            tenant_pool, tenant_id, meter_code=body.meter_code, unit=body.unit,
            aggregation=body.aggregation,
        )

    @app.post("/meters/{meter_code}/quota")
    def set_quota(
        tenant_id: TenantId,
        session: Session,
        meter_code: str,
        body: QuotaBody,
    ) -> dict[str, Any]:
        permit(session, "billing.quota.write")
        return billing.set_quota(
            tenant_pool, tenant_id, meter_code=meter_code, period=body.period,
            limit_quantity=body.limit_quantity, overage_allowed=body.overage_allowed,
            hard_stop=body.hard_stop,
        )

    @app.post("/usage", status_code=201)
    def record_usage(tenant_id: TenantId, session: Session, body: UsageBody) -> dict[str, Any]:
        permit(session, "billing.usage.record", body.correlation_id)
        return billing.record_usage(
            tenant_pool, tenant_id, meter_code=body.meter_code, quantity=body.quantity,
            idempotency_key=body.idempotency_key, actor_id=require_uuid(body.actor_id, "actor_id"),
            correlation_id=body.correlation_id, occurred_at=body.occurred_at,
            corrects_record_id=optional_uuid(body.corrects_record_id, "corrects_record_id"),
        )

    @app.get("/usage/{meter_code}")
    def get_usage(tenant_id: TenantId, session: Session, meter_code: str) -> dict[str, Any]:
        permit(session, "billing.subscription.read")
        return billing.usage_summary(tenant_pool, tenant_id, meter_code=meter_code)

    @app.post("/invoices", status_code=201)
    def issue_invoice(tenant_id: TenantId, session: Session, body: InvoiceBody) -> dict[str, Any]:
        permit(session, "billing.invoice.issue", body.correlation_id)
        return billing.issue_invoice(
            tenant_pool, tenant_id, actor_id=require_uuid(body.actor_id, "actor_id"),
            correlation_id=body.correlation_id, tax_rate_bp=body.tax_rate_bp,
        )

    @app.get("/invoices")
    def get_invoices(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "billing.invoice.read")
        return billing.list_invoices(tenant_pool, tenant_id)

    @app.get("/invoices/{invoice_id}")
    def get_one_invoice(tenant_id: TenantId, session: Session, invoice_id: str) -> dict[str, Any]:
        permit(session, "billing.invoice.read")
        return billing.get_invoice(
            tenant_pool, tenant_id, require_uuid(invoice_id, "invoice_id"))

    @app.post("/invoices/{invoice_id}/credit-notes", status_code=201)
    def credit_invoice(
        tenant_id: TenantId, session: Session, invoice_id: str, body: CreditNoteBody
    ) -> dict[str, Any]:
        permit(session, "billing.credit_note.issue", body.correlation_id)
        return billing.issue_credit_note(
            tenant_pool, tenant_id,
            invoice_id=require_uuid(invoice_id, "invoice_id"),
            amount_minor=body.amount_minor,
            reason=body.reason, actor_id=require_uuid(body.actor_id, "actor_id"),
            correlation_id=body.correlation_id,
        )

    # --------------------------------------------------- MOD-007 identity and sessions
    #
    # **Every route that touches one identity requires a session belonging to that identity.**
    # `owned` is the check, and it is on every one of them. An independent review found the first
    # version left password changes, recovery-code issuing, session listing and device revocation
    # open to anyone holding the tenant UUID -- which is an unauthenticated claim, not a secret --
    # and demonstrated a full takeover from it. The open routes below are open on purpose:
    # registration, login, the login challenge and recovery are the paths a caller uses precisely
    # because it has no session yet.

    @app.post("/identities", status_code=201)
    def register_identity(tenant_id: TenantId, body: RegisterIdentityBody) -> dict[str, Any]:
        return identity.register_identity(
            identity_pool, tenant_id, display_name=body.display_name,
            correlation_id=body.correlation_id, email=body.email, phone=body.phone,
            password=body.password, person_id=optional_uuid(body.person_id, "person_id"),
        )

    @app.post("/identities/{identity_id}/password")
    def set_password(
        tenant_id: TenantId, session: Session, identity_id: str, body: PasswordBody
    ) -> dict[str, Any]:
        return identity.set_password(
            identity_pool, tenant_id, identity_id=owned(session, identity_id),
            password=body.password, correlation_id=body.correlation_id,
            current_password=body.current_password,
            session_factors=session["factors"], session_aal=session["aal"],
        )

    @app.post("/auth/login")
    def login(tenant_id: TenantId, body: LoginBody) -> dict[str, Any]:
        """Rate-limited by the identifier being attempted, which is MOD-007's named gap.

        Lockout already bounds guessing against one identity; nothing bounded volume, so an
        attacker who knew an address could still lock its owner out, and addresses that do not
        exist were free to spray at. The budget is keyed on a hash of the identifier so the
        limiter never holds the addresses anybody tried.
        """
        rate_limit(limit_key="auth.login", tenant_id=tenant_id,
                   subject=limit_subject(body.identifier))
        return identity.authenticate(
            identity_pool, tenant_id, identifier=body.identifier, password=body.password,
            correlation_id=body.correlation_id, device_fingerprint=body.device_fingerprint,
            device_label=body.device_label,
        )

    @app.post("/auth/challenge")
    def answer_login_challenge(
        tenant_id: TenantId, body: LoginChallengeBody
    ) -> dict[str, Any]:
        """Answer the challenge `/auth/login` returned. Open, because the caller has no session."""
        rate_limit(limit_key="auth.login", tenant_id=tenant_id,
                   subject=limit_subject(body.identifier))
        return identity.complete_login_challenge(
            identity_pool, tenant_id, identifier=body.identifier, challenge=body.challenge,
            recovery_code=body.recovery_code, correlation_id=body.correlation_id,
        )

    @app.get("/auth/session")
    def read_session(session: Session) -> dict[str, Any]:
        return session

    @app.post("/auth/rotate")
    def rotate(
        tenant_id: TenantId, token: BearerToken, body: CorrelationBody
    ) -> dict[str, Any]:
        return identity.rotate_session(
            identity_pool, tenant_id, token=token, correlation_id=body.correlation_id
        )

    @app.get("/auth/require/{action_class}")
    def require_assurance(
        tenant_id: TenantId, token: BearerToken, action_class: str
    ) -> dict[str, Any]:
        return identity.require_assurance(
            identity_pool, tenant_id, token=token, action_class=action_class
        )

    @app.post("/auth/step-up")
    def step_up(tenant_id: TenantId, token: BearerToken, body: StepUpBody) -> dict[str, Any]:
        """Keyed on the bearer token's own digest rather than on an identity.

        Resolving the token first to get an identity would mean doing the work the limit exists
        to bound. The digest is per-session, which is the right grain anyway: MOD-007's own
        note says somebody holding a stolen session can burn the victim's lockout budget here,
        and a per-session ceiling bounds how fast.
        """
        rate_limit(limit_key="auth.recover", tenant_id=tenant_id,
                   subject=token_subject(token))
        return identity.complete_step_up(
            identity_pool, tenant_id, token=token, challenge=body.challenge,
            password=body.password, recovery_code=body.recovery_code,
            correlation_id=body.correlation_id,
        )

    @app.post("/auth/recover")
    def recover(tenant_id: TenantId, body: RecoverBody) -> dict[str, Any]:
        rate_limit(limit_key="auth.recover", tenant_id=tenant_id,
                   subject=limit_subject(body.identifier))
        return identity.recover_with_code(
            identity_pool, tenant_id, identifier=body.identifier, code=body.code,
            correlation_id=body.correlation_id,
        )

    @app.post("/identities/{identity_id}/status")
    def set_identity_status(
        tenant_id: TenantId, session: Session, identity_id: str, body: IdentityStatusBody
    ) -> dict[str, Any]:
        """End or restore somebody's ability to sign in. IAM-01's missing writer.

        **Four controls read `iam.identities.status` and nothing could set it**, so two of its
        three declared states were unreachable and this product could not shut anybody out.
        Found by building ADM-STF-01, which shows an owner that a departed employee can still
        sign in -- a board naming a problem the product cannot act on.

        `identity.identity.write` is `financial` class, so this needs a stepped-up session as
        well as the permission. That is the right price: it ends somebody's access to
        everything, and `revoke_assignment` -- which ends what they may *do* -- costs the
        same.
        """
        permit(session, "identity.identity.write", body.correlation_id)
        return identity.set_identity_status(
            identity_pool, tenant_id,
            identity_id=require_uuid(identity_id, "identity_id"),
            status=body.status, reason=body.reason,
            actor_identity_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/identities/{identity_id}/recovery-codes", status_code=201)
    def issue_recovery_codes(
        tenant_id: TenantId, session: Session, identity_id: str, body: RecoveryCodesBody
    ) -> dict[str, Any]:
        return identity.issue_recovery_codes(
            identity_pool, tenant_id, identity_id=owned(session, identity_id),
            correlation_id=body.correlation_id, current_password=body.current_password,
            session_factors=session["factors"], session_aal=session["aal"],
        )

    @app.get("/identities/{identity_id}/sessions")
    def identity_sessions(
        tenant_id: TenantId, session: Session, identity_id: str,
        limit: int = identity.SESSION_PAGE, live_only: bool = False,
    ) -> list[dict[str, Any]]:
        """The caller's own sessions, newest first and bounded.

        A session row is written on every sign-in and every rotation, and `iam.sessions` has
        no DELETE grant for any role -- so this returned every session an identity had ever
        held. `live_only` is the filter a member wants and a reviewer does not: a revoked row
        is the evidence a sign-out happened.
        """
        return identity.list_sessions(
            identity_pool, tenant_id, identity_id=owned(session, identity_id),
            limit=limit, live_only=live_only,
        )

    @app.post("/sessions/{session_id}/revoke")
    def revoke_session(
        tenant_id: TenantId, session: Session, session_id: str, body: RevokeBody
    ) -> dict[str, Any]:
        return identity.revoke_session(
            identity_pool, tenant_id,
            session_id=require_uuid(session_id, "session_id"),
            identity_id=session["identity_id"], correlation_id=body.correlation_id,
            reason=body.reason,
        )

    @app.get("/identities/last-seen")
    def get_last_seen(
        tenant_id: TenantId, session: Session, correlation_id: str,
        identity_id: Annotated[list[str], Query()],
    ) -> dict[str, Any]:
        """When each of several identities was last active, and whether a login still works.

        **ADM-STF-01's LAST SEEN column, and the design states its purpose**: "Last seen
        exists so a departed employee with a live login is visible rather than discovered."
        So this answers both halves -- the timestamp and whether anything still opens -- and
        neither is derivable from the other.

        `identity.identity.read`, which is the permission for a fact about an identity, and
        **not** the session inventory: no device, no factor, no assurance, no address. A
        column on a list must not buy the page describing every device somebody has signed in
        from, which is the bound `list_sessions` had to grow once something rendered it.
        """
        permit(session, "identity.identity.read", correlation_id)
        return {
            "identities": identity.last_seen_for(
                identity_pool, tenant_id,
                identity_ids=require_uuids(
                    identity_id, "identity_id", limit=identity.LAST_SEEN_BATCH)),
            "a_live_session_after_employment_ended_is_the_finding":
                "the design's own reason for the column; the staff list and this read are "
                "on different planes under different permissions, so the surface is the only "
                "place that can put the two together for one reader",
        }

    @app.get("/identities/{identity_id}/devices")
    def identity_devices(
        tenant_id: TenantId, session: Session, identity_id: str
    ) -> list[dict[str, Any]]:
        return identity.list_devices(
            identity_pool, tenant_id, identity_id=owned(session, identity_id)
        )

    @app.post("/devices/{device_id}/revoke")
    def revoke_device(
        tenant_id: TenantId, session: Session, device_id: str, body: RevokeBody
    ) -> dict[str, Any]:
        return identity.revoke_device(
            identity_pool, tenant_id,
            device_id=require_uuid(device_id, "device_id"),
            identity_id=session["identity_id"], correlation_id=body.correlation_id,
            reason=body.reason,
        )

    @app.post("/devices/{device_id}/trust")
    def trust_device(
        tenant_id: TenantId, session: Session, device_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        return identity.trust_device(
            identity_pool, tenant_id,
            device_id=require_uuid(device_id, "device_id"),
            identity_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/identities/{identity_id}/passkeys", status_code=201)
    def enroll_passkey(
        tenant_id: TenantId, session: Session, identity_id: str, body: PasskeyBody
    ) -> dict[str, Any]:
        return identity.enroll_passkey(
            identity_pool, tenant_id, identity_id=owned(session, identity_id),
            # **base64url here too, which is a change.** These two were standard base64,
            # so one surface of the same ceremony spoke a different alphabet from the other --
            # and a credential id written one way at enrolment and the other at sign-in is a
            # credential nothing can find.
            webauthn_credential_id=_b64url(body.webauthn_credential_id, "credential_id"),
            public_key=_b64url(body.public_key, "public_key"),
            correlation_id=body.correlation_id, label=body.label, aaguid=body.aaguid,
            transports=body.transports, backed_up=body.backed_up,
        )

    @app.get("/identities/{identity_id}")
    def read_identity(
        tenant_id: TenantId, session: Session, identity_id: str
    ) -> dict[str, Any]:
        """The caller's own identity. Scoped by `owned`, so there is nothing to authorize.

        It exists because a WebAuthn ceremony names the account to the authenticator, and
        nothing here returned the signed-in person's own display name -- so the browser would
        offer a uuid when somebody later picks between credentials.
        """
        return identity.read_own_identity(
            identity_pool, tenant_id, identity_id=owned(session, identity_id))

    @app.get("/identities/{identity_id}/passkeys")
    def identity_passkeys(
        tenant_id: TenantId, session: Session, identity_id: str
    ) -> list[dict[str, Any]]:
        return identity.list_passkeys(
            identity_pool, tenant_id, identity_id=owned(session, identity_id)
        )

    @app.post("/passkeys/{passkey_id}/revoke")
    def revoke_passkey(
        tenant_id: TenantId, session: Session, passkey_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        """Withdraw one of the caller's own passkeys.

        Scoped to the caller rather than gated: `revoke_passkey` refuses a passkey that is not
        this identity's with the same 404 it gives for one that does not exist, so there is
        nothing to authorize. **This is the remedy that had to exist before any screen could
        offer to enrol one** -- the only writer of `revoked_at` was clone detection, so a lost
        authenticator could not be withdrawn.
        """
        return identity.revoke_passkey(
            identity_pool, tenant_id,
            passkey_id=require_uuid(passkey_id, "passkey_id"),
            identity_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/passkeys/{passkey_id}/assertion")
    def passkey_assertion(
        tenant_id: TenantId, session: Session, passkey_id: str, body: AssertionBody
    ) -> dict[str, Any]:
        return identity.record_passkey_assertion(
            identity_pool, tenant_id,
            passkey_id=require_uuid(passkey_id, "passkey_id"),
            identity_id=session["identity_id"], sign_count=body.sign_count,
            correlation_id=body.correlation_id,
        )

    @app.post("/auth/passkey/challenge")
    def begin_passkey_login(
        tenant_id: TenantId, body: PasskeyChallengeBody
    ) -> dict[str, Any]:
        """The challenge a passkey sign-in is verified against. Open, like `/auth/login`.

        **The response is identical for every identifier**, including one nobody has
        registered: a ceremony that said "no passkey here" would be a directory of which
        addresses exist. Rate-limited on the `auth.login` budget and keyed the same way,
        because this is the unauthenticated front door's other half.
        """
        rate_limit(limit_key="auth.login", tenant_id=tenant_id,
                   subject=limit_subject(body.identifier))
        return identity.begin_passkey_assertion(
            identity_pool, tenant_id, identifier=body.identifier,
            correlation_id=body.correlation_id,
        )

    @app.post("/auth/passkey/login")
    def login_with_passkey(tenant_id: TenantId, body: PasskeyLoginBody) -> dict[str, Any]:
        """Sign in with a verified WebAuthn assertion, which is how AAL 3 is reached.

        The relying party id and the origins come from configuration and are passed in rather
        than read inside the service: they are deployment facts, so the service stays free of
        the environment like every other function here, and a build that has not stated them
        answers 422 naming that rather than 401 naming a credential.
        """
        rate_limit(limit_key="auth.login", tenant_id=tenant_id,
                   subject=limit_subject(body.identifier))
        return identity.authenticate_with_passkey(
            identity_pool, tenant_id, identifier=body.identifier, challenge=body.challenge,
            credential_id=_b64url(body.credential_id, "credential_id"),
            client_data_json=_b64url(body.client_data_json, "client_data_json"),
            authenticator_data=_b64url(body.authenticator_data, "authenticator_data"),
            signature=_b64url(body.signature, "signature"),
            rp_id=cfg.webauthn_rp_id, allowed_origins=cfg.webauthn_origins,
            correlation_id=body.correlation_id,
            device_fingerprint=body.device_fingerprint, device_label=body.device_label,
        )

    @app.get("/auth/events")
    def auth_events(
        tenant_id: TenantId, session: Session, limit: int = 100
    ) -> list[dict[str, Any]]:
        """The caller's own log. There is no tenant-wide view until MOD-008 can authorize one."""
        return identity.auth_events(
            identity_pool, tenant_id, identity_id=session["identity_id"], limit=limit
        )

    # --------------------------------------------------- MOD-008 authorization and audit
    #
    # Every route here needs a session, and all but the bootstrap need a permission. The
    # permission check goes through `authz.require`, which is the single gate: it asks
    # authorization and assurance together and writes the denial to the audit log itself, so a
    # surface cannot ask whether somebody may act and then forget to record that they were
    # refused.

    @app.post("/authz/bootstrap", status_code=201)
    def bootstrap_authorization(
        tenant_id: TenantId, session: Session, body: BootstrapBody
    ) -> dict[str, Any]:
        """Create the first role and grant it to the caller. Works **only while a tenant has no
        assignments at all**, and refuses afterwards.

        Something has to break the circle: creating a role needs `authz.role.write`, which is
        held through a role, which has to be created. This is that something, and it is narrow --
        one tenant-wide grant, once, recorded in the audit log, refused the moment any assignment
        exists. It is no weaker than the surface around it, since `X-Veyro-Tenant` is still an
        unauthenticated claim; when that changes this route needs revisiting with it.
        """
        return authz.bootstrap(
            identity_pool, tenant_id, identity_id=session["identity_id"],
            role_key=body.role_key, display_name=body.display_name,
            correlation_id=body.correlation_id,
        )

    @app.post("/authz/roles", status_code=201)
    def create_role(tenant_id: TenantId, session: Session, body: RoleBody) -> dict[str, Any]:
        permit(session, "authz.role.write", body.correlation_id)
        return authz.create_role(
            identity_pool, tenant_id, role_key=body.role_key,
            display_name=body.display_name, correlation_id=body.correlation_id,
            permissions=body.permissions, description=body.description,
            actor_identity_id=session["identity_id"],
        )

    @app.get("/authz/roles")
    def get_roles(tenant_id: TenantId, session: Session, correlation_id: str
                  ) -> list[dict[str, Any]]:
        permit(session, "authz.role.read", correlation_id)
        return authz.list_roles(identity_pool, tenant_id)

    @app.get("/authz/catalog")
    def read_permission_catalog(tenant_id: TenantId, session: Session) -> dict[str, Any]:
        """Every permission this software has, what it means and what it costs to exercise.

        **A statement about the software, not about a tenant.** Permissions live in code
        rather than in a table precisely so that two tenants cannot disagree about which
        exist, so this takes no pool and reads nobody's rows -- the same shape as
        `/privacy/erasure-reach`, and asserted the same way: two tenants get identical bytes.

        ADM-STF-04 is why it exists. The design draws roles and capabilities as a matrix with
        a mark in each cell, and a matrix needs the row headings: what a permission *is*, and
        whether holding it is enough to use it. Without this the only thing a surface could
        render was each role's raw permission list, which is what it did -- a four-thousand
        pixel wall of comma-separated names that nobody can compare two roles in.

        Gated on `authz.role.read`, because a reader who may see which permissions a role
        holds is the reader who needs to know what those permissions mean.
        """
        permit(session, "authz.role.read")
        return {
            "permissions": [
                {"name": name, "description": one.description, "category": one.category,
                 "action_class": one.action_class,
                 # **What the action class costs, resolved here rather than in the client.**
                 # A surface deciding that `financial` means level 2 would be a second copy
                 # of a rule MOD-007 owns, and the day either moved nobody could say which
                 # was the policy.
                 "required_aal": identity_policy.required_aal(one.action_class)}
                for name, one in sorted(authz_catalog.PERMISSIONS.items())],
            "count": len(authz_catalog.PERMISSIONS),
            # **The highest level any session in this build can reach, derived rather than
            # written down.** It was the literal `2`, with a comment explaining that level 3
            # needed a hardware authenticator nothing could verify -- and the day WebAuthn
            # verification landed, this response went on telling a permissions matrix that a
            # `privileged` permission was held by nobody who could use it. A ceiling computed
            # from `VERIFIABLE_FACTORS` moves when the factors do; a number in a response
            # moves when somebody remembers.
            "reachable_aal": identity_policy.assurance_for(
                list(identity.VERIFIABLE_FACTORS)),
            "a_permission_is_a_fact_about_the_software":
                "Permissions are code, not rows, so every tenant sees this same list. A "
                "per-tenant registry would let two tenants disagree about which exist.",
        }

    @app.put("/authz/roles/{role_key}/permissions")
    def set_role_permissions(
        tenant_id: TenantId, session: Session, role_key: str, body: RolePermissionsBody
    ) -> dict[str, Any]:
        permit(session, "authz.role.write", body.correlation_id)
        return authz.set_role_permissions(
            identity_pool, tenant_id, role_key=role_key, permissions=body.permissions,
            correlation_id=body.correlation_id, actor_identity_id=session["identity_id"],
        )

    @app.post("/authz/assignments", status_code=201)
    def assign_role(
        tenant_id: TenantId, session: Session, body: AssignRoleBody
    ) -> dict[str, Any]:
        permit(session, "authz.assignment.write", body.correlation_id)
        return authz.assign_role(
            identity_pool, tenant_id,
            identity_id=require_uuid(body.identity_id, "identity_id"),
            role_key=body.role_key,
            granted_by=session["identity_id"], correlation_id=body.correlation_id,
            scope_type=body.scope_type,
            brand_id=optional_uuid(body.brand_id, "brand_id"),
            location_id=optional_uuid(body.location_id, "location_id"),
            expires_at=body.expires_at,
        )

    @app.get("/authz/assignments/{identity_id}")
    def get_assignments(
        tenant_id: TenantId, session: Session, identity_id: str, correlation_id: str
    ) -> list[dict[str, Any]]:
        permit(session, "authz.role.read", correlation_id)
        return authz.list_assignments(
            identity_pool, tenant_id,
            identity_id=require_uuid(identity_id, "identity_id"))

    @app.get("/authz/assignments")
    def get_assignments_for(
        tenant_id: TenantId, session: Session, correlation_id: str,
        identity_id: Annotated[list[str], Query()],
    ) -> dict[str, Any]:
        """The role each of several identities holds, in one request.

        **ADM-STF-01 draws a ROLE column and a staff list has fifty rows.** Asking
        `/authz/assignments/{identity_id}` per row is fifty round trips against the same
        600-a-minute `api.request` budget the browser suite already tripped once, which is
        what `/authz/checks` exists for. Same semantics as the single read, batched.

        Bounded by the ids the caller sends, which are ids a list it already read gave it, so
        this discloses nothing that read did not. There is still no tenant-wide assignment
        listing: "who holds what in this tenant" is a different read and deciding whether
        `authz.role.read` buys it is a decision nobody has made.
        """
        permit(session, "authz.role.read", correlation_id)
        return {
            "assignments": authz.assignments_for(
                identity_pool, tenant_id,
                identity_ids=require_uuids(
                    identity_id, "identity_id", limit=authz.ASSIGNMENT_BATCH)),
            "live_is_derived_here":
                "an assignment stops working when it expires with nothing writing a row, so "
                "the server compares rather than leaving two timestamps to each reader",
        }

    @app.post("/authz/assignments/{assignment_id}/revoke")
    def revoke_assignment(
        tenant_id: TenantId, session: Session, assignment_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "authz.assignment.write", body.correlation_id)
        return authz.revoke_assignment(
            identity_pool, tenant_id,
            assignment_id=require_uuid(assignment_id, "assignment_id"),
            correlation_id=body.correlation_id, actor_identity_id=session["identity_id"],
        )

    @app.post("/authz/policies", status_code=201)
    def write_policy(
        tenant_id: TenantId, session: Session, body: AuthzPolicyBody
    ) -> dict[str, Any]:
        permit(session, "authz.policy.write", body.correlation_id)
        return authz.write_policy(
            identity_pool, tenant_id, policy_key=body.policy_key, effect=body.effect,
            action=body.action, correlation_id=body.correlation_id, match=body.match,
            masked_fields=body.masked_fields, priority=body.priority,
            description=body.description, actor_identity_id=session["identity_id"],
        )

    @app.get("/authz/policies")
    def get_policies(tenant_id: TenantId, session: Session, correlation_id: str
                     ) -> list[dict[str, Any]]:
        permit(session, "authz.role.read", correlation_id)
        return authz.list_policies(identity_pool, tenant_id)

    @app.get("/authz/simulate")
    def simulate(
        tenant_id: TenantId, session: Session, identity_id: str, correlation_id: str,
        brand_id: str | None = None, location_id: str | None = None,
    ) -> dict[str, Any]:
        """The permission simulator (IAM-03-R07), answered from the evaluator's own rules.

        The scope goes through `resolve_scope`, so a location's brand is looked up rather than
        taken from the query string. A simulator that accepts a scope the evaluator would never
        see is worse than none: it confirms an escalation instead of exposing it.
        """
        permit(session, "authz.role.read", correlation_id)
        return authz.effective_permissions(
            identity_pool, tenant_id,
            identity_id=require_uuid(identity_id, "identity_id"),
            scope=authz.resolve_scope(
                tenant_pool, tenant_id,
                brand_id=optional_uuid(brand_id, "brand_id"),
                location_id=optional_uuid(location_id, "location_id")),
        )

    @app.get("/authz/check")
    def check_action(
        tenant_id: TenantId, session: Session, action: str, correlation_id: str,
        brand_id: str | None = None, location_id: str | None = None,
    ) -> dict[str, Any]:
        """Ask the gate about the caller's own session. No permission needed to ask about self."""
        decided = authz.check(
            identity_pool, tenant_id, identity_id=session["identity_id"],
            session_aal=session["aal"], action=action, correlation_id=correlation_id,
            scope=authz.resolve_scope(
                tenant_pool, tenant_id,
                brand_id=optional_uuid(brand_id, "brand_id"),
                location_id=optional_uuid(location_id, "location_id")),
            record_denial=False,
        )
        return {"action": action, "allowed": decided.allowed, "reason": decided.reason,
                "step_up_required": decided.step_up_required,
                "required_aal": decided.required_aal, "reachable": decided.reachable,
                "masked_fields": list(decided.masked_fields)}

    @app.get("/authz/checks")
    def check_actions(
        tenant_id: TenantId, session: Session, correlation_id: str,
        action: Annotated[list[str], Query()],
        brand_id: str | None = None, location_id: str | None = None,
    ) -> dict[str, Any]:
        """The same question about several actions, in one request.

        **A page asks the gate once per control, and a rich page has many.** The Command
        Center asks about six reads and the shell asks about thirteen navigation entries, so
        rendering it cost nineteen round trips -- each one a scope resolution and an
        evaluation -- against `api.request`'s 600-a-minute per-identity budget. That budget
        is noisy-neighbour protection and its own comment says "a limit that trips during
        ordinary use is a limit somebody will raise to infinity rather than investigate";
        raising it would have been exactly that. The browser suite tripped it first, which is
        the cheap way to find out.

        **The semantics are unchanged, deliberately.** This is the same `authz.check` per
        action, with the same scope and the same assurance weighing -- not a permission list.
        A client that fetched `effective_permissions` and decided for itself would be
        MOD-014's "a grant is not a session" finding, where a permission held on a session too
        weak for the action read as held.

        The scope is resolved once rather than per action, which is the actual saving: it is a
        database read and the answer is the same for every action in the batch.
        """
        if not action:
            raise InvalidRequest("no_action")
        if len(action) > 40:
            raise InvalidRequest("too_many_actions")
        # **An action the catalogue does not declare is refused, not denied.** `authz.check`
        # answers a name it has never heard by finding no assignment that grants it, which is
        # indistinguishable from a real refusal -- so a surface that misspells a permission
        # renders "you do not hold this" and nothing anywhere says otherwise. This screen's
        # own metric row did exactly that within an hour of being written, asking for a
        # `finance.invoice.read` that has never existed, and the page said the reader lacked
        # a permission rather than that the author had invented one.
        #
        # It is MOD-022's rate-limit finding one module over: a budget `BUDGETS` does not
        # declare is not a limit, and a permission the catalogue does not declare is not a
        # gate. The whole batch is refused rather than the one entry, because a page that
        # rendered four of five cells would hide the fault it is meant to surface.
        unknown = sorted({one for one in action if one not in authz_catalog.PERMISSIONS})
        if unknown:
            raise InvalidRequest(f"unknown_action:{','.join(unknown)}")
        scope = authz.resolve_scope(
            tenant_pool, tenant_id,
            brand_id=optional_uuid(brand_id, "brand_id"),
            location_id=optional_uuid(location_id, "location_id"))
        checks = []
        for one in action:
            decided = authz.check(
                identity_pool, tenant_id, identity_id=session["identity_id"],
                session_aal=session["aal"], action=one, correlation_id=correlation_id,
                scope=scope, record_denial=False,
            )
            checks.append({
                "action": one, "allowed": decided.allowed, "reason": decided.reason,
                "step_up_required": decided.step_up_required,
                "required_aal": decided.required_aal, "reachable": decided.reachable,
                "masked_fields": list(decided.masked_fields)})
        return {"checks": checks, "count": len(checks)}

    @app.post("/authz/approval-policies", status_code=201)
    def write_approval_policy(
        tenant_id: TenantId, session: Session, body: ApprovalPolicyBody
    ) -> dict[str, Any]:
        permit(session, "authz.policy.write", body.correlation_id)
        return authz.write_approval_policy(
            identity_pool, tenant_id, action=body.action,
            required_permission=body.required_permission,
            correlation_id=body.correlation_id, threshold_minor=body.threshold_minor,
            required_approvals=body.required_approvals,
            separation_of_duties=body.separation_of_duties,
            actor_identity_id=session["identity_id"],
            stages=[stage.model_dump() for stage in body.stages],
            sequential=body.sequential,
        )

    @app.post("/authz/approvals", status_code=201)
    def request_approval(
        tenant_id: TenantId, session: Session, body: ApprovalRequestBody
    ) -> dict[str, Any]:
        """The service checks the requester holds the action's own permission; see its
        docstring for why assurance is deliberately not required at this point."""
        return authz.request_approval(
            identity_pool, tenant_id, action=body.action, resource_type=body.resource_type,
            requested_by=session["identity_id"], correlation_id=body.correlation_id,
            resource_id=body.resource_id, amount_minor=body.amount_minor,
            currency=body.currency, reason=body.reason,
        )

    @app.get("/authz/approvals")
    def get_approvals(
        tenant_id: TenantId, session: Session, correlation_id: str, state: str | None = None
    ) -> list[dict[str, Any]]:
        permit(session, "authz.role.read", correlation_id)
        return authz.list_approval_requests(identity_pool, tenant_id, state=state)

    @app.post("/authz/approvals/{request_id}/decide")
    def decide_approval(
        tenant_id: TenantId, session: Session, request_id: str, body: ApprovalDecisionBody
    ) -> dict[str, Any]:
        permit(session, "authz.approval.decide", body.correlation_id)
        return authz.decide_approval(
            identity_pool, tenant_id,
            request_id=require_uuid(request_id, "request_id"),
            decided_by=session["identity_id"], decision=body.decision,
            correlation_id=body.correlation_id, reason=body.reason,
            on_behalf_of=optional_uuid(body.on_behalf_of, "on_behalf_of"),
            stage_ordinal=body.stage_ordinal,
        )

    @app.post("/authz/delegations", status_code=201)
    def delegate_approvals(
        tenant_id: TenantId, session: Session, body: ApprovalDelegationBody
    ) -> dict[str, Any]:
        """Hand this session's own approval authority to somebody for a window.

        **Gated on `authz.approval.decide`**, which is the authority being handed over: a
        caller who may not decide has nothing to delegate, and a separate permission would
        let somebody who cannot approve grant approving to somebody else. It is financial
        class, so this needs a stepped-up session -- which is the right trade for an act that
        widens who may approve a refund.
        """
        permit(session, "authz.approval.decide", body.correlation_id)
        return authz.delegate_approvals(
            identity_pool, tenant_id,
            to_identity_id=require_uuid(body.to_identity_id, "to_identity_id"),
            starts_at=body.starts_at,
            ends_at=body.ends_at, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/authz/delegations/{delegation_id}/revoke")
    def revoke_approval_delegation(
        tenant_id: TenantId, session: Session, delegation_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        """Take a delegation back. Only the delegator; the service refuses anybody else."""
        permit(session, "authz.approval.decide", body.correlation_id)
        return authz.revoke_delegation(
            identity_pool, tenant_id, require_uuid(delegation_id, "delegation_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/authz/delegations")
    def list_approval_delegations(
        tenant_id: TenantId, session: Session, include_ended: bool = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> dict[str, Any]:
        """Who is holding whose approval authority.

        **On `authz.role.read` rather than on the decide permission**, because this is the
        list somebody checks when asking who *could* have approved something, and a reader
        who may see who holds which role but may not decide under them is exactly who asks.
        There is no `authz.policy.read` in the catalogue -- the first version of this route
        named one and it does not exist, which the catalogue would have refused at the gate
        rather than at import, so it is worth saying that the permission was checked against
        the list rather than assumed.
        """
        permit(session, "authz.role.read")
        return authz.list_delegations(
            identity_pool, tenant_id, include_ended=include_ended, limit=limit)

    @app.get("/authz/audit")
    def read_audit(
        tenant_id: TenantId, session: Session, correlation_id: str,
        category: str | None = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        permit(session, "authz.audit.read", correlation_id)
        return authz.read_audit(identity_pool, tenant_id, limit=limit, category=category)

    @app.get("/authz/audit/verify")
    def verify_audit(tenant_id: TenantId, session: Session, correlation_id: str
                     ) -> dict[str, Any]:
        permit(session, "authz.audit.read", correlation_id)
        return authz.verify_audit_chain(identity_pool, tenant_id)

    @app.post("/authz/access-reviews", status_code=201)
    def open_access_review(
        tenant_id: TenantId, session: Session, body: AccessReviewBody
    ) -> dict[str, Any]:
        permit(session, "authz.access_review.conduct", body.correlation_id)
        return authz.open_access_review(
            identity_pool, tenant_id, title=body.title, opened_by=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/authz/access-reviews/items/{item_id}")
    def decide_review_item(
        tenant_id: TenantId, session: Session, item_id: str, body: ReviewItemBody
    ) -> dict[str, Any]:
        permit(session, "authz.access_review.conduct", body.correlation_id)
        return authz.decide_review_item(
            identity_pool, tenant_id,
            item_id=require_uuid(item_id, "item_id"), decision=body.decision,
            decided_by=session["identity_id"], correlation_id=body.correlation_id,
            note=body.note,
        )

    @app.post("/authz/access-reviews/{review_id}/complete")
    def complete_access_review(
        tenant_id: TenantId, session: Session, review_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "authz.access_review.conduct", body.correlation_id)
        return authz.complete_access_review(
            identity_pool, tenant_id,
            review_id=require_uuid(review_id, "review_id"),
            correlation_id=body.correlation_id, actor_identity_id=session["identity_id"],
        )

    # --------------------------------------------------- MOD-009 privacy, consent and DSARs

    def consent_subject(
        session: dict[str, Any], supplied: str | None, correlation_id: str, *,
        guardian: str | None = None, source: str = "member_app",
    ) -> str:
        """Decide whose consent this is, and charge the right permission for it.

        Derived, not accepted: a caller that names nobody is recording its own consent, and a
        caller that names somebody else is making a permanent, insert-only claim about a person
        who is not present. That needs `privacy.consent.record_on_behalf`, which is
        financial-class. MOD-008's rule -- derive, never accept -- applied to a consent record.

        **`subject_id` is not the only field that makes a claim about somebody else**, which is
        what an independent review found. Two others do:

        * `guardian_subject_id` asserts that a named person consented *for* this subject. It is
          the entire control behind `requires_guardian`, the thing that makes a minor's health
          consent valid, and nothing can check it -- the guardian is an identity in another
          plane, so there is no foreign key, and the row is insert-only so nobody can correct
          it afterwards. A member on an AAL-1 session could satisfy it by typing any UUID.
        * `source` declares provenance. `staff_entry` and `paper_import` say a member of staff
          keyed this in from a signed document, which a self-service session is not in a
          position to assert; with an `evidence_ref` of the caller's choosing it reads as a
          scanned waiver that nobody scanned.

        So the stronger permission is charged for any of the three, not only for a foreign
        subject. The ordinary case -- a member agreeing to something on their own phone, from
        their own app -- is untouched and still routine, which is the point.
        """
        subject = optional_uuid(supplied, "subject_id")
        on_behalf = (
            (subject is not None and subject != session["identity_id"])
            or guardian is not None
            or source in STAFF_ASSERTED_SOURCES
        )
        permit(session,
               "privacy.consent.record_on_behalf" if on_behalf else "privacy.consent.record",
               correlation_id)
        return subject if subject is not None else str(session["identity_id"])

    @app.get("/privacy/purposes")
    def read_purposes(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "privacy.purpose.read")
        return privacy.list_purposes(tenant_pool, tenant_id)

    @app.post("/privacy/purposes", status_code=201)
    def register_purpose(
        tenant_id: TenantId, session: Session, body: PurposeBody
    ) -> dict[str, Any]:
        permit(session, "privacy.purpose.write", body.correlation_id)
        return privacy.register_purpose(
            tenant_pool, tenant_id, purpose_code=body.purpose_code,
            description=body.description, lawful_basis=body.lawful_basis,
            controller_role=body.controller_role, data_classes=body.data_classes,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/privacy/purposes/{purpose_id}/retire")
    def retire_purpose(
        tenant_id: TenantId, session: Session, purpose_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "privacy.purpose.write", body.correlation_id)
        return privacy.retire_purpose(
            tenant_pool, tenant_id, purpose_id=require_uuid(purpose_id, "purpose_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/privacy/consent/definitions", status_code=201)
    def define_consent(
        tenant_id: TenantId, session: Session, body: ConsentDefinitionBody
    ) -> dict[str, Any]:
        permit(session, "privacy.consent.define", body.correlation_id)
        return privacy.define_consent(
            tenant_pool, tenant_id, consent_type=body.consent_type,
            purpose_id=require_uuid(body.purpose_id, "purpose_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
            requires_guardian=body.requires_guardian, withdrawable=body.withdrawable,
        )

    @app.post("/privacy/consent/versions", status_code=201)
    def publish_consent_version(
        tenant_id: TenantId, session: Session, body: ConsentVersionBody
    ) -> dict[str, Any]:
        permit(session, "privacy.consent.define", body.correlation_id)
        return privacy.publish_consent_version(
            tenant_pool, tenant_id, consent_type=body.consent_type, language=body.language,
            document_ref=body.document_ref, document_hash=body.document_hash,
            effective_from=body.effective_from, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/privacy/consent/records", status_code=201)
    def record_consent(
        tenant_id: TenantId, session: Session, body: ConsentRecordBody
    ) -> dict[str, Any]:
        subject_id = consent_subject(
            session, body.subject_id, body.correlation_id,
            guardian=body.guardian_subject_id, source=body.source,
        )
        return privacy.register_consent(
            tenant_pool, tenant_id, subject_id=subject_id, consent_type=body.consent_type,
            language=body.language, signed_at=body.signed_at, source=body.source,
            correlation_id=body.correlation_id,
            guardian_subject_id=optional_uuid(body.guardian_subject_id, "guardian_subject_id"),
            evidence_hash_value=body.evidence_hash, evidence_ref=body.evidence_ref,
            consent_version_id=optional_uuid(body.consent_version_id, "consent_version_id"),
        )

    @app.post("/privacy/consent/withdrawals", status_code=201)
    def withdraw_consent(
        tenant_id: TenantId, session: Session, body: ConsentWithdrawalBody
    ) -> dict[str, Any]:
        subject_id = consent_subject(session, body.subject_id, body.correlation_id,
                                     source=body.source)
        return privacy.withdraw_consent(
            tenant_pool, tenant_id, subject_id=subject_id, consent_type=body.consent_type,
            signed_at=body.signed_at, source=body.source,
            correlation_id=body.correlation_id, evidence_ref=body.evidence_ref,
        )

    @app.get("/privacy/consent/state")
    def read_consent_state(
        tenant_id: TenantId, session: Session, subject_id: str, language: str = "en"
    ) -> dict[str, Any]:
        permit(session, "privacy.consent.read")
        return privacy.consent_state(
            tenant_pool, tenant_id, subject_id=require_uuid(subject_id, "subject_id"),
            language=language,
        )

    @app.get("/privacy/consent/history")
    def read_consent_history(
        tenant_id: TenantId, session: Session, subject_id: str
    ) -> list[dict[str, Any]]:
        permit(session, "privacy.consent.read")
        return privacy.consent_history(
            tenant_pool, tenant_id, subject_id=require_uuid(subject_id, "subject_id")
        )

    @app.get("/privacy/retention")
    def read_retention(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "privacy.retention.read")
        return privacy.list_retention_policies(tenant_pool, tenant_id)

    @app.post("/privacy/retention", status_code=201)
    def set_retention(
        tenant_id: TenantId, session: Session, body: RetentionPolicyBody
    ) -> dict[str, Any]:
        permit(session, "privacy.retention.write", body.correlation_id)
        return privacy.set_retention_policy(
            tenant_pool, tenant_id, resource_type=body.resource_type,
            data_class=body.data_class, retention_days=body.retention_days,
            legal_basis=body.legal_basis, region=body.region,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/privacy/legal-holds")
    def read_legal_holds(
        tenant_id: TenantId, session: Session, include_released: bool = False
    ) -> list[dict[str, Any]]:
        permit(session, "privacy.retention.read")
        return privacy.list_legal_holds(
            tenant_pool, tenant_id, include_released=include_released
        )

    @app.post("/privacy/legal-holds", status_code=201)
    def place_legal_hold(
        tenant_id: TenantId, session: Session, body: LegalHoldBody
    ) -> dict[str, Any]:
        permit(session, "privacy.legal_hold.write", body.correlation_id)
        return privacy.place_legal_hold(
            tenant_pool, tenant_id, reason=body.reason, reference=body.reference,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
            subject_id=optional_uuid(body.subject_id, "subject_id"),
            resource_type=body.resource_type,
        )

    @app.post("/privacy/legal-holds/{hold_id}/release")
    def release_legal_hold(
        tenant_id: TenantId, session: Session, hold_id: str, body: ReleaseHoldBody
    ) -> dict[str, Any]:
        permit(session, "privacy.legal_hold.write", body.correlation_id)
        return privacy.release_legal_hold(
            tenant_pool, tenant_id, hold_id=require_uuid(hold_id, "hold_id"),
            release_reason=body.release_reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/privacy/erasure-reach")
    def read_erasure_reach(tenant_id: TenantId, session: Session) -> dict[str, Any]:
        """What this build can and cannot erase. A statement about the software, not a tenant.

        Gated on `privacy.dsar.read` -- "see data subject requests **and their evidence**" --
        because this registry is the evidence behind every request's plan. It took no tenant
        and no pool, so it reads nobody's rows; the tenant header is still required, because
        an unauthenticated route is a different decision from an unparameterised one.
        """
        permit(session, "privacy.dsar.read")
        return privacy.erasure_reach()

    @app.get("/privacy/requests")
    def read_dsars(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "privacy.dsar.read")
        return privacy.list_dsars(tenant_pool, tenant_id)

    @app.post("/privacy/requests", status_code=201)
    def open_dsar(tenant_id: TenantId, session: Session, body: DsarBody) -> dict[str, Any]:
        permit(session, "privacy.dsar.open", body.correlation_id)
        return privacy.open_dsar(
            tenant_pool, tenant_id, subject_id=require_uuid(body.subject_id, "subject_id"),
            request_type=body.request_type, response_days=body.response_days,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
            received_at=body.received_at,
        )

    @app.get("/privacy/requests/{request_id}")
    def read_dsar(tenant_id: TenantId, session: Session, request_id: str) -> dict[str, Any]:
        permit(session, "privacy.dsar.read")
        return privacy.get_dsar(
            tenant_pool, tenant_id, request_id=require_uuid(request_id, "request_id")
        )

    @app.get("/privacy/requests/{request_id}/plan")
    def read_dsar_plan(
        tenant_id: TenantId, session: Session, request_id: str
    ) -> dict[str, Any]:
        permit(session, "privacy.dsar.read")
        return privacy.plan_dsar(
            tenant_pool, tenant_id, request_id=require_uuid(request_id, "request_id")
        )

    @app.post("/privacy/requests/{request_id}/identity-check")
    def start_dsar_identity_check(
        tenant_id: TenantId, session: Session, request_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "privacy.dsar.verify", body.correlation_id)
        return privacy.start_dsar_identity_check(
            tenant_pool, tenant_id, request_id=require_uuid(request_id, "request_id")
        )

    @app.post("/privacy/requests/{request_id}/verify-identity")
    def verify_dsar_identity(
        tenant_id: TenantId, session: Session, request_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "privacy.dsar.verify", body.correlation_id)
        return privacy.verify_dsar_identity(
            tenant_pool, tenant_id, request_id=require_uuid(request_id, "request_id"),
            actor_id=session["identity_id"],
        )

    @app.post("/privacy/requests/{request_id}/legal-check")
    def check_dsar_legal(
        tenant_id: TenantId, session: Session, request_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "privacy.dsar.verify", body.correlation_id)
        return privacy.check_dsar_legal(
            tenant_pool, tenant_id, request_id=require_uuid(request_id, "request_id"),
            actor_id=session["identity_id"],
        )

    @app.post("/privacy/requests/{request_id}/fulfil")
    def fulfil_dsar(
        tenant_id: TenantId, session: Session, request_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "privacy.dsar.fulfil", body.correlation_id)
        return privacy.fulfil_dsar(
            tenant_pool, tenant_id, request_id=require_uuid(request_id, "request_id"),
            identity_pool=identity_pool, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/privacy/requests/{request_id}/refuse")
    def refuse_dsar(
        tenant_id: TenantId, session: Session, request_id: str, body: RefuseDsarBody
    ) -> dict[str, Any]:
        permit(session, "privacy.dsar.fulfil", body.correlation_id)
        return privacy.refuse_dsar(
            tenant_pool, tenant_id, request_id=require_uuid(request_id, "request_id"),
            reason=body.reason,
        )

    @app.get("/privacy/incidents")
    def read_incidents(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "privacy.incident.read")
        return privacy.list_incidents(tenant_pool, tenant_id)

    @app.post("/privacy/incidents", status_code=201)
    def record_incident(
        tenant_id: TenantId, session: Session, body: IncidentBody
    ) -> dict[str, Any]:
        permit(session, "privacy.incident.record", body.correlation_id)
        return privacy.record_incident(
            tenant_pool, tenant_id, severity=body.severity, category=body.category,
            summary=body.summary, detected_at=body.detected_at,
            personal_data_involved=body.personal_data_involved,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
            notification_assessment=body.notification_assessment, detail=body.detail,
            supersedes_incident_id=optional_uuid(
                body.supersedes_incident_id, "supersedes_incident_id"),
        )

    # --------------------------------------------------- MOD-010 domain events

    # There is no route that runs a consumer's handlers. Delivery needs handlers registered in
    # this process, and this build registers none -- a `POST /events/deliver` that found an
    # empty registry would be a route that reads as a control and does nothing. `deliver_pending`
    # is exercised by the tests with their own handlers, and the transport that will register
    # real ones is the gap recorded in CLAUDE.md.

    @app.get("/events/health")
    def event_health(tenant_id: TenantId, session: Session) -> dict[str, Any]:
        permit(session, "events.event.read")
        return events.outbox_health(tenant_pool, tenant_id)

    @app.get("/events/trace")
    def event_trace(
        tenant_id: TenantId, session: Session, correlation_id: str
    ) -> list[dict[str, Any]]:
        permit(session, "events.event.read", correlation_id)
        return events.trace(tenant_pool, tenant_id,
                            correlation_id=require_uuid(correlation_id, "correlation_id"))

    @app.get("/events/aggregate")
    def event_aggregate(
        tenant_id: TenantId, session: Session, aggregate_type: str, aggregate_id: str
    ) -> list[dict[str, Any]]:
        permit(session, "events.event.read")
        return events.aggregate_history(
            tenant_pool, tenant_id, aggregate_type=aggregate_type,
            aggregate_id=require_uuid(aggregate_id, "aggregate_id"),
        )

    @app.get("/events/{event_id}")
    def read_event(tenant_id: TenantId, session: Session, event_id: str) -> dict[str, Any]:
        permit(session, "events.event.read")
        return events.get_event(tenant_pool, tenant_id,
                                event_id=require_uuid(event_id, "event_id"))

    @app.get("/events/subscriptions/all")
    def read_subscriptions(
        tenant_id: TenantId, session: Session, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        permit(session, "events.subscription.read")
        return events.list_subscriptions(tenant_pool, tenant_id,
                                         include_inactive=include_inactive)

    @app.post("/events/subscriptions", status_code=201)
    def create_subscription(
        tenant_id: TenantId, session: Session, body: SubscriptionBody
    ) -> dict[str, Any]:
        permit(session, "events.subscription.write", body.correlation_id)
        return events.subscribe(
            tenant_pool, tenant_id, consumer=body.consumer, event_type=body.event_type,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
            replay_safety=body.replay_safety, max_attempts=body.max_attempts,
        )

    @app.post("/events/subscriptions/{subscription_id}/deactivate")
    def deactivate_subscription(
        tenant_id: TenantId, session: Session, subscription_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "events.subscription.write", body.correlation_id)
        return events.unsubscribe(
            tenant_pool, tenant_id,
            subscription_id=require_uuid(subscription_id, "subscription_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/events/dispatch")
    def run_dispatch(
        tenant_id: TenantId, session: Session, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "events.dispatch.run", body.correlation_id)
        return events.dispatch_pending(tenant_pool, tenant_id)

    @app.get("/events/dead-letters/all")
    def read_dead_letters(
        tenant_id: TenantId, session: Session, include_released: bool = False
    ) -> list[dict[str, Any]]:
        permit(session, "events.dead_letter.read")
        return events.list_dead_letters(tenant_pool, tenant_id,
                                        include_released=include_released)

    @app.post("/events/dead-letters/{dead_letter_id}/release")
    def release_dead_letter(
        tenant_id: TenantId, session: Session, dead_letter_id: str,
        body: ReleaseDeadLetterBody,
    ) -> dict[str, Any]:
        permit(session, "events.dead_letter.release", body.correlation_id)
        return events.release_dead_letter(
            tenant_pool, tenant_id,
            dead_letter_id=require_uuid(dead_letter_id, "dead_letter_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/events/replays", status_code=201)
    def create_replay(
        tenant_id: TenantId, session: Session, body: ReplayBody
    ) -> dict[str, Any]:
        permit(session, "events.replay.request", body.correlation_id)
        return events.request_replay(
            tenant_pool, tenant_id, consumer=body.consumer, event_types=body.event_types,
            from_time=body.from_time, to_time=body.to_time,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
            side_effects=body.side_effects, side_effects_reason=body.side_effects_reason,
        )

    @app.post("/events/replays/{job_id}/run")
    def execute_replay(
        tenant_id: TenantId, session: Session, job_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "events.replay.run", body.correlation_id)
        return events.run_replay(
            tenant_pool, tenant_id, job_id=require_uuid(job_id, "job_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    # ------------------------------------- MOD-011 observability, capacity and FinOps

    @app.get("/ops/metrics/{metric_key}")
    def read_series(
        tenant_id: TenantId, session: Session, metric_key: str,
        window_hours: Annotated[int, Query(ge=1, le=8760)] = 24,
    ) -> dict[str, Any]:
        """One declared series over a window.

        There is no route that lists arbitrary dimension values, and that is deliberate: a
        consumer name and a check key are tenant-chosen strings, and an endpoint that enumerated
        them would turn the metric store into a directory of what a tenant has configured for a
        permission that only says "read a series".
        """
        permit(session, "ops.metric.read")
        return obs_metrics.series(tenant_pool, tenant_id, metric_key=metric_key,
                                  window_hours=window_hours)

    @app.get("/ops/worker")
    def read_worker_jobs(
        tenant_id: TenantId, session: Session,
        window_hours: Annotated[int, Query(ge=1, le=8760)] = 24,
    ) -> dict[str, Any]:
        """What each scheduled job did for this tenant over a window.

        **This is the one read where a dimension may be named**, and the reason is the reason
        `read_series` gives for refusing one: a consumer name and a check key are tenant-chosen
        strings, so enumerating them would turn the metric store into a directory of what a
        tenant has configured. A job name is neither -- it is code, declared as a closed set in
        `app.worker.names`, and this route can only ever return the six names that are in this
        build whatever the tenant has done.

        **A zero here is a real signal rather than an absence.** Every job runs at least every
        five minutes for every schedulable tenant, so a job with no runs over a 24-hour window
        is a worker that is not running -- which is precisely the question an operator opens
        this page to ask, and the one a backlog count alone cannot answer.

        **And a count of runs against an *expected* count is deliberately not returned.** The
        arithmetic is trivial -- the window over the cadence -- and every reading of it is
        wrong unless the worker was up for the whole window, which is the thing being tested.
        A worker started ten minutes ago would report 40 runs against an expected 5,760 and
        read as broken. The zero is actionable; the ratio is a number that looks like one.
        """
        permit(session, "ops.metric.read")
        jobs: list[dict[str, Any]] = []
        for job in worker_registry.JOBS:
            success = obs_metrics.series(
                tenant_pool, tenant_id, metric_key="worker.job_success",
                window_hours=window_hours, dimensions={"job": job.name})
            duration = obs_metrics.series(
                tenant_pool, tenant_id, metric_key="worker.job_duration",
                window_hours=window_hours, dimensions={"job": job.name})
            runs = sum(int(b["observations"]) for b in success["buckets"])
            succeeded = sum(float(b["total"]) for b in success["buckets"])
            observed = sum(int(b["observations"]) for b in duration["buckets"])
            total_ms = sum(float(b["total"]) for b in duration["buckets"])
            jobs.append({
                "job": job.name,
                "summary": job.summary,
                "role": job.role,
                "every_seconds": int(job.every.total_seconds()),
                "runs": runs,
                "failed": runs - int(succeeded),
                "mean_duration_ms": round(total_ms / observed, 1) if observed else None,
            })
        return {
            "window_hours": window_hours,
            "jobs": jobs,
            "worker_gaps": [
                "a run is recorded by the worker itself, so this says what the worker "
                "reported and not that a job's effect reached anything outside the database",
                "the schedule lives in the worker process's memory, so a restart makes every "
                "job due at once -- which is safe because every job is idempotent, and it "
                "means a burst here after a deployment is expected rather than a fault",
            ],
        }

    @app.get("/ops/objectives")
    def read_objectives(
        tenant_id: TenantId, session: Session, include_retired: bool = False
    ) -> list[dict[str, Any]]:
        permit(session, "ops.objective.read")
        return observability.list_objectives(tenant_pool, tenant_id,
                                             include_retired=include_retired)

    @app.post("/ops/objectives", status_code=201)
    def add_objective(
        tenant_id: TenantId, session: Session, body: ObjectiveBody
    ) -> dict[str, Any]:
        permit(session, "ops.objective.write", body.correlation_id)
        return observability.define_objective(
            tenant_pool, tenant_id, objective_key=body.objective_key, kind=body.kind,
            metric_key=body.metric_key, comparison=body.comparison, threshold=body.threshold,
            window_hours=body.window_hours, aggregate_as=body.aggregate_as, owner=body.owner,
            runbook_ref=body.runbook_ref, dimensions=body.dimensions,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ops/objectives/{objective_id}/retire")
    def end_objective(
        tenant_id: TenantId, session: Session, objective_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "ops.objective.write", body.correlation_id)
        return observability.retire_objective(
            tenant_pool, tenant_id, require_uuid(objective_id, "objective_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ops/objectives/{objective_id}/evaluate")
    def check_objective(
        tenant_id: TenantId, session: Session, objective_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        """Evaluating publishes `performance_budget.exceeded` when it breaches, so it is a
        write even though it reads like a query -- which is why it is a POST and why it needs
        the write permission rather than the read one."""
        permit(session, "ops.objective.write", body.correlation_id)
        return observability.evaluate_objective(
            tenant_pool, tenant_id, require_uuid(objective_id, "objective_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/ops/synthetic-checks")
    def read_checks(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "ops.synthetic.read")
        return observability.list_checks(tenant_pool, tenant_id)

    @app.post("/ops/synthetic-checks", status_code=201)
    def add_check(
        tenant_id: TenantId, session: Session, body: SyntheticCheckBody
    ) -> dict[str, Any]:
        permit(session, "ops.synthetic.write", body.correlation_id)
        return observability.register_check(
            tenant_pool, tenant_id, check_key=body.check_key, description=body.description,
            workflow=body.workflow, interval_seconds=body.interval_seconds,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ops/synthetic-checks/{check_id}/enabled")
    def toggle_check(
        tenant_id: TenantId, session: Session, check_id: str, body: SyntheticToggleBody
    ) -> dict[str, Any]:
        permit(session, "ops.synthetic.write", body.correlation_id)
        return observability.set_check_enabled(
            tenant_pool, tenant_id, require_uuid(check_id, "check_id"), enabled=body.enabled,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/ops/synthetic-checks/{check_id}/results")
    def read_results(
        tenant_id: TenantId, session: Session, check_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        permit(session, "ops.synthetic.read")
        return observability.list_results(
            tenant_pool, tenant_id, require_uuid(check_id, "check_id"), limit=limit
        )

    @app.post("/ops/synthetic-checks/{check_id}/results", status_code=201)
    def add_result(
        tenant_id: TenantId, session: Session, check_id: str, body: SyntheticResultBody
    ) -> dict[str, Any]:
        """Written by whatever runs the probe. Nothing in this build runs one."""
        permit(session, "ops.metric.record", body.correlation_id)
        return observability.record_result(
            tenant_pool, tenant_id, check_id=require_uuid(check_id, "check_id"),
            outcome=body.outcome, duration_ms=body.duration_ms, detail=body.detail,
            observed_at=body.observed_at, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/ops/capacity")
    def read_forecasts(
        tenant_id: TenantId, session: Session, resource: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        permit(session, "ops.capacity.read")
        return observability.list_forecasts(tenant_pool, tenant_id, resource=resource,
                                            limit=limit)

    @app.post("/ops/capacity", status_code=201)
    def add_forecast(
        tenant_id: TenantId, session: Session, body: ForecastBody
    ) -> dict[str, Any]:
        permit(session, "ops.capacity.write", body.correlation_id)
        return observability.record_forecast(
            tenant_pool, tenant_id, resource=body.resource, horizon_days=body.horizon_days,
            current_value=body.current_value, projected_value=body.projected_value,
            basis=body.basis, limit_value=body.limit_value,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ops/costs", status_code=201)
    def add_cost(tenant_id: TenantId, session: Session, body: CostBody) -> dict[str, Any]:
        permit(session, "ops.cost.write", body.correlation_id)
        return observability.allocate_cost(
            tenant_pool, tenant_id, period_start=body.period_start,
            period_end=body.period_end, dimension=body.dimension,
            dimension_value=body.dimension_value, currency=body.currency,
            amount_minor=body.amount_minor, source=body.source,
            corrects_cost_record_id=optional_uuid(body.corrects_cost_record_id,
                                                  "corrects_cost_record_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/ops/costs")
    def read_costs(
        tenant_id: TenantId, session: Session, period_start: date, period_end: date
    ) -> dict[str, Any]:
        permit(session, "ops.cost.read")
        return observability.cost_summary(tenant_pool, tenant_id, period_start=period_start,
                                          period_end=period_end)

    @app.get("/ops/margin")
    def read_margin(
        tenant_id: TenantId, session: Session, period_start: date, period_end: date
    ) -> dict[str, Any]:
        """Paragraph 3507. Revenue is net of tax and of the partner share; currencies are
        reported apart, because there is no exchange rate in this build to combine them with."""
        permit(session, "ops.cost.read")
        return observability.gross_margin(tenant_pool, tenant_id, period_start=period_start,
                                          period_end=period_end)

    @app.get("/ops/budgets")
    def read_budgets(
        tenant_id: TenantId, session: Session, include_retired: bool = False
    ) -> list[dict[str, Any]]:
        permit(session, "ops.budget.read")
        return observability.list_budgets(tenant_pool, tenant_id,
                                          include_retired=include_retired)

    @app.post("/ops/budgets", status_code=201)
    def add_budget(tenant_id: TenantId, session: Session, body: BudgetBody) -> dict[str, Any]:
        permit(session, "ops.budget.write", body.correlation_id)
        return observability.set_budget(
            tenant_pool, tenant_id, budget_key=body.budget_key, dimension=body.dimension,
            dimension_value=body.dimension_value, currency=body.currency,
            amount_minor=body.amount_minor, period=body.period, owner=body.owner,
            warn_at_bp=body.warn_at_bp, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/ops/budgets/{budget_id}/retire")
    def end_budget(
        tenant_id: TenantId, session: Session, budget_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "ops.budget.write", body.correlation_id)
        return observability.retire_budget(
            tenant_pool, tenant_id, require_uuid(budget_id, "budget_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ops/budgets/{budget_id}/burn")
    def check_budget(
        tenant_id: TenantId, session: Session, budget_id: str, body: BudgetBurnBody
    ) -> dict[str, Any]:
        """AlertBudgetBurn. Safe to run on a loop: the alert rows are unique per budget, period
        and threshold, so a second pass in the same period raises nothing."""
        permit(session, "ops.budget.write", body.correlation_id)
        return observability.evaluate_budget(
            tenant_pool, tenant_id, require_uuid(budget_id, "budget_id"),
            period_start=body.period_start, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/ops/budget-alerts")
    def read_budget_alerts(
        tenant_id: TenantId, session: Session, limit: int = 50
    ) -> list[dict[str, Any]]:
        permit(session, "ops.budget.read")
        return observability.list_budget_alerts(tenant_pool, tenant_id, limit=limit)

    # --------------------------------------- MOD-012 integration adapters (platform plane)

    @app.post("/platform/integrations", status_code=201)
    def register_integration_definition(body: IntegrationDefinitionBody) -> dict[str, Any]:
        """Register a draft definition version.

        On the platform plane, which is unauthenticated in this build like the rest of it --
        the largest open gap here and recorded as such in CLAUDE.md.
        """
        return integrations.register_definition(
            platform_pool, definition_key=body.definition_key, version=body.version,
            provider=body.provider, display_name=body.display_name,
            criticality=body.criticality, support_owner=body.support_owner,
            description=body.description, capabilities=body.capabilities,
            scopes=body.scopes, required_scopes=body.required_scopes,
            config_fields=body.config_fields, regions=body.regions,
        )

    @app.get("/platform/integrations")
    def list_integration_definitions(status: str | None = None) -> list[dict[str, Any]]:
        return integrations.list_definitions(platform_pool, status=status)

    @app.get("/platform/integrations/{definition_key}")
    def read_integration_definition(
        definition_key: str, version: int | None = None
    ) -> dict[str, Any]:
        found = integrations.get_definition(platform_pool, definition_key=definition_key,
                                            version=version)
        found.pop("_declared", None)
        return found

    @app.post("/platform/integrations/{definition_key}/{version}/{action}")
    def move_integration_definition(
        definition_key: str, version: int, action: str
    ) -> dict[str, Any]:
        if action == "publish":
            return integrations.publish_definition(
                platform_pool, definition_key=definition_key, version=version)
        if action == "retire":
            return integrations.retire_definition(
                platform_pool, definition_key=definition_key, version=version)
        raise InvalidRequest("unknown_definition_action")

    # ----------------------------------------- MOD-012 integration adapters (tenant plane)

    @app.get("/integrations")
    def read_installs(
        tenant_id: TenantId, session: Session, include_uninstalled: bool = False
    ) -> list[dict[str, Any]]:
        permit(session, "integrations.install.read")
        return integrations.list_installs(tenant_pool, tenant_id,
                                          include_uninstalled=include_uninstalled)

    @app.post("/integrations", status_code=201)
    def install_integration(
        tenant_id: TenantId, session: Session, body: InstallBody
    ) -> dict[str, Any]:
        permit(session, "integrations.install.write", body.correlation_id)
        return integrations.install_integration(
            tenant_pool, platform_pool, tenant_id, definition_key=body.definition_key,
            version=body.version, config=body.config, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/integrations/{install_id}/configure")
    def configure_integration(
        tenant_id: TenantId, session: Session, install_id: str, body: ConfigureInstallBody
    ) -> dict[str, Any]:
        permit(session, "integrations.install.write", body.correlation_id)
        return integrations.configure_install(
            tenant_pool, tenant_id, require_uuid(install_id, "install_id"), config=body.config,
            fallback_plan=body.fallback_plan, reconciliation_plan=body.reconciliation_plan,
            exit_plan=body.exit_plan, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/integrations/{install_id}/activate")
    def activate_integration(
        tenant_id: TenantId, session: Session, install_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        """A critical integration needs a fallback, a reconciliation procedure and an exit plan
        in writing before it may carry traffic."""
        permit(session, "integrations.install.write", body.correlation_id)
        return integrations.activate_install(
            tenant_pool, tenant_id, require_uuid(install_id, "install_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/integrations/{install_id}/disable")
    def disable_integration(
        tenant_id: TenantId, session: Session, install_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "integrations.install.write", body.correlation_id)
        return integrations.disable_install(
            tenant_pool, tenant_id, require_uuid(install_id, "install_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/integrations/{install_id}/uninstall")
    def uninstall_integration(
        tenant_id: TenantId, session: Session, install_id: str, body: UninstallBody
    ) -> dict[str, Any]:
        """Revokes every live connection in the same transaction: an uninstall that left one
        authorized would be a tenant believing a third party no longer has access while it
        does."""
        permit(session, "integrations.install.uninstall", body.correlation_id)
        return integrations.uninstall_integration(
            tenant_pool, tenant_id, require_uuid(install_id, "install_id"), reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/integrations/connections")
    def read_connections(
        tenant_id: TenantId, session: Session, install_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[dict[str, Any]]:
        permit(session, "integrations.connection.read")
        return integrations.list_connections(
            tenant_pool, tenant_id, install_id=optional_uuid(install_id, "install_id"),
            include_revoked=include_revoked,
        )

    @app.post("/integrations/connections", status_code=201)
    def authorize_connection(
        tenant_id: TenantId, session: Session, body: ConnectionBody
    ) -> dict[str, Any]:
        """The one command that hands a third party reach into a tenant's data."""
        permit(session, "integrations.connection.authorize", body.correlation_id)
        return integrations.authorize_connection(
            tenant_pool, tenant_id, install_id=require_uuid(body.install_id, "install_id"),
            external_account_ref=body.external_account_ref, region=body.region,
            granted_scopes=body.granted_scopes, vault_ref=body.vault_ref,
            issued_at=body.issued_at, expires_at=body.expires_at,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/integrations/connections/{connection_id}/validate")
    def validate_connection(
        tenant_id: TenantId, session: Session, connection_id: str,
        body: ValidateConnectionBody,
    ) -> dict[str, Any]:
        """Records that somebody validated it, with what they saw. This build validates
        nothing: there is no provider here to answer."""
        permit(session, "integrations.connection.authorize", body.correlation_id)
        return integrations.validate_connection(
            tenant_pool, tenant_id, require_uuid(connection_id, "connection_id"),
            evidence=body.evidence, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/integrations/connections/{connection_id}/revoke")
    def revoke_connection(
        tenant_id: TenantId, session: Session, connection_id: str, body: RevokeConnectionBody
    ) -> dict[str, Any]:
        permit(session, "integrations.connection.authorize", body.correlation_id)
        return integrations.revoke_connection(
            tenant_pool, tenant_id, require_uuid(connection_id, "connection_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/integrations/credentials")
    def read_credentials(
        tenant_id: TenantId, session: Session, connection_id: str | None = None,
        include_retired: bool = False,
    ) -> list[dict[str, Any]]:
        """Metadata only. There is no secret in this module to read."""
        permit(session, "integrations.credential.read")
        return integrations.list_credentials(
            tenant_pool, tenant_id,
            connection_id=optional_uuid(connection_id, "connection_id"),
            include_retired=include_retired,
        )

    @app.post("/integrations/connections/{connection_id}/rotate", status_code=201)
    def rotate_credential(
        tenant_id: TenantId, session: Session, connection_id: str, body: RotateCredentialBody
    ) -> dict[str, Any]:
        """Records that a rotation happened. Nothing here can mint or install a secret."""
        permit(session, "integrations.credential.rotate", body.correlation_id)
        return integrations.rotate_credential(
            tenant_pool, tenant_id, require_uuid(connection_id, "connection_id"),
            vault_ref=body.vault_ref, issued_at=body.issued_at, expires_at=body.expires_at,
            scopes=body.scopes, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/integrations/credentials/due")
    def announce_expiring_credentials(
        tenant_id: TenantId, session: Session, body: CorrelationBody
    ) -> dict[str, Any]:
        """Publishes `credential.expiring` for each live reference inside its window. A POST
        because it publishes, and not idempotent across calls -- nothing loops on it."""
        permit(session, "integrations.credential.rotate", body.correlation_id)
        return integrations.credentials_due(
            tenant_pool, tenant_id, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/integrations/cursors")
    def read_cursors(
        tenant_id: TenantId, session: Session, connection_id: str | None = None
    ) -> list[dict[str, Any]]:
        permit(session, "integrations.sync.read")
        return integrations.list_cursors(
            tenant_pool, tenant_id,
            connection_id=optional_uuid(connection_id, "connection_id"),
        )

    @app.post("/integrations/cursors")
    def advance_cursor(
        tenant_id: TenantId, session: Session, body: CursorBody
    ) -> dict[str, Any]:
        permit(session, "integrations.sync.run", body.correlation_id)
        return integrations.advance_cursor(
            tenant_pool, tenant_id,
            connection_id=require_uuid(body.connection_id, "connection_id"),
            resource=body.resource, position=body.position, observed_at=body.observed_at,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/integrations/cursors/reset")
    def reset_cursor(
        tenant_id: TenantId, session: Session, body: CursorResetBody
    ) -> dict[str, Any]:
        """Moving a cursor backwards re-reads a window, which for a provider that bills per
        call is money -- so it is a different permission from advancing one, and it carries a
        reason."""
        permit(session, "integrations.sync.reset", body.correlation_id)
        return integrations.reset_cursor(
            tenant_pool, tenant_id,
            connection_id=require_uuid(body.connection_id, "connection_id"),
            resource=body.resource, position=body.position, observed_at=body.observed_at,
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/integrations/cursors/policy")
    def set_conflict_policy(
        tenant_id: TenantId, session: Session, body: ConflictPolicyBody
    ) -> dict[str, Any]:
        permit(session, "integrations.sync.reset", body.correlation_id)
        return integrations.set_conflict_policy(
            tenant_pool, tenant_id,
            connection_id=require_uuid(body.connection_id, "connection_id"),
            resource=body.resource, policy=body.policy, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/integrations/runs")
    def read_runs(
        tenant_id: TenantId, session: Session, connection_id: str | None = None,
        status: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        permit(session, "integrations.sync.read")
        return integrations.list_runs(
            tenant_pool, tenant_id,
            connection_id=optional_uuid(connection_id, "connection_id"), status=status,
            limit=limit,
        )

    @app.post("/integrations/runs", status_code=201)
    def start_run(
        tenant_id: TenantId, session: Session, body: StartRunBody
    ) -> dict[str, Any]:
        """Opens a run. Nothing in this build calls a provider."""
        permit(session, "integrations.sync.run", body.correlation_id)
        return integrations.start_run(
            tenant_pool, tenant_id,
            connection_id=require_uuid(body.connection_id, "connection_id"),
            resource=body.resource, max_attempts=body.max_attempts,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/integrations/runs/{run_id}/finish")
    def finish_run(
        tenant_id: TenantId, session: Session, run_id: str, body: FinishRunBody
    ) -> dict[str, Any]:
        permit(session, "integrations.sync.run", body.correlation_id)
        return integrations.finish_run(
            tenant_pool, tenant_id, require_uuid(run_id, "run_id"),
            records_read=body.records_read, records_written=body.records_written,
            conflicts=body.conflicts, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/integrations/runs/{run_id}/fail")
    def fail_run(
        tenant_id: TenantId, session: Session, run_id: str, body: FailRunBody
    ) -> dict[str, Any]:
        permit(session, "integrations.sync.run", body.correlation_id)
        return integrations.fail_run(
            tenant_pool, tenant_id, require_uuid(run_id, "run_id"), error=body.error,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/integrations/runs/{run_id}/retry")
    def retry_run(
        tenant_id: TenantId, session: Session, run_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "integrations.sync.run", body.correlation_id)
        return integrations.retry_run(
            tenant_pool, tenant_id, require_uuid(run_id, "run_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/integrations/runs/{run_id}/release")
    def release_run(
        tenant_id: TenantId, session: Session, run_id: str, body: ReleaseRunBody
    ) -> dict[str, Any]:
        """Taking a quarantined run out of the dead letter is a decision about a connector that
        has failed its whole budget, so it carries a name and a reason."""
        permit(session, "integrations.sync.reset", body.correlation_id)
        return integrations.release_run(
            tenant_pool, tenant_id, require_uuid(run_id, "run_id"), reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/integrations/runs/{run_id}/reconciliation")
    def record_reconciliation(
        tenant_id: TenantId, session: Session, run_id: str, body: ReconciliationBody
    ) -> dict[str, Any]:
        permit(session, "integrations.sync.reset", body.correlation_id)
        return integrations.record_reconciliation(
            tenant_pool, tenant_id, require_uuid(run_id, "run_id"),
            local_count=body.local_count, provider_count=body.provider_count,
            matched=body.matched, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    # ------------------------------------------------- MOD-013 notification platform

    @app.get("/notifications/templates")
    def read_templates(
        tenant_id: TenantId, session: Session, status: str | None = None
    ) -> list[dict[str, Any]]:
        permit(session, "notifications.template.read")
        return notifications.list_templates(tenant_pool, tenant_id, status=status)

    @app.get("/notifications/templates/published")
    def read_published_template(
        tenant_id: TenantId, session: Session, template_key: str,
        locale: str | None = None, channel: str | None = None,
    ) -> dict[str, Any]:
        """The published template a key would send, including its body.

        The listing beside this one returns no body, which left the text with no reader at
        all: a template could be drafted, approved and published and the only way to see what
        it said was to send a message with it. ADM-PAY-05's "the message they receive" is the
        first surface to need it.
        """
        permit(session, "notifications.template.read")
        return notifications.published_template_for_key(
            tenant_pool, tenant_id, template_key=template_key, locale=locale,
            channel=channel)

    @app.post("/notifications/templates", status_code=201)
    def create_template(
        tenant_id: TenantId, session: Session, body: TemplateBody
    ) -> dict[str, Any]:
        permit(session, "notifications.template.write", body.correlation_id)
        return notifications.create_template(
            tenant_pool, tenant_id, template_key=body.template_key, version=body.version,
            category=body.category, channel=body.channel, locale=body.locale, body=body.body,
            subject=body.subject, variables=body.variables,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/notifications/templates/{template_id}/approve")
    def approve_template(
        tenant_id: TenantId, session: Session, template_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        """An author cannot approve their own template: it goes out under the tenant's name to
        everybody, which is MOD-008's separation of duties applied to content."""
        permit(session, "notifications.template.approve", body.correlation_id)
        return notifications.approve_template(
            tenant_pool, tenant_id, require_uuid(template_id, "template_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/notifications/templates/{template_id}/publish")
    def publish_template(
        tenant_id: TenantId, session: Session, template_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "notifications.template.write", body.correlation_id)
        return notifications.publish_template(
            tenant_pool, tenant_id, require_uuid(template_id, "template_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/notifications/templates/{template_id}/retire")
    def retire_template(
        tenant_id: TenantId, session: Session, template_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "notifications.template.write", body.correlation_id)
        return notifications.retire_template(
            tenant_pool, tenant_id, require_uuid(template_id, "template_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/notifications/preferences")
    def read_preferences(
        tenant_id: TenantId, session: Session, recipient_id: str
    ) -> list[dict[str, Any]]:
        permit(session, "notifications.preference.read")
        return notifications.list_preferences(
            tenant_pool, tenant_id, recipient_id=require_uuid(recipient_id, "recipient_id")
        )

    @app.put("/notifications/preferences")
    def set_preference(
        tenant_id: TenantId, session: Session, body: PreferenceBody
    ) -> dict[str, Any]:
        """A preference can switch off `coaching` and `marketing` and nothing else: a member who
        mutes marketing still gets their invoice."""
        permit(session, "notifications.preference.write", body.correlation_id)
        return notifications.set_preference(
            tenant_pool, tenant_id,
            recipient_id=require_uuid(body.recipient_id, "recipient_id"),
            category=body.category, channel=body.channel, allowed=body.allowed,
            quiet_from=body.quiet_from, quiet_until=body.quiet_until,
            quiet_timezone=body.quiet_timezone, daily_cap=body.daily_cap,
            digest_mode=body.digest_mode, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/notifications/channels")
    def read_channel_policies(
        tenant_id: TenantId, session: Session
    ) -> list[dict[str, Any]]:
        permit(session, "notifications.policy.read")
        return notifications.list_channel_policies(tenant_pool, tenant_id)

    @app.put("/notifications/channels")
    def set_channel_policy(
        tenant_id: TenantId, session: Session, body: ChannelPolicyBody
    ) -> dict[str, Any]:
        permit(session, "notifications.policy.write", body.correlation_id)
        return notifications.set_channel_policy(
            tenant_pool, tenant_id, channel=body.channel, enabled=body.enabled,
            fallback_channel=body.fallback_channel,
            cost_per_message_minor=body.cost_per_message_minor, currency=body.currency,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/notifications")
    def read_notifications(
        tenant_id: TenantId, session: Session, recipient_id: str | None = None,
        status: str | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> list[dict[str, Any]]:
        """The list carries no message text. A list route that did would be a read path to
        everything this tenant has ever said to anybody, under one permission."""
        permit(session, "notifications.notification.read")
        return notifications.list_notifications(
            tenant_pool, tenant_id,
            recipient_id=optional_uuid(recipient_id, "recipient_id"), status=status,
            limit=limit,
        )

    @app.get("/notifications/{notification_id}")
    def read_notification(
        tenant_id: TenantId, session: Session, notification_id: str
    ) -> dict[str, Any]:
        """The text that was sent, behind its own permission."""
        permit(session, "notifications.notification.read_content")
        return notifications.get_notification(
            tenant_pool, tenant_id, require_uuid(notification_id, "notification_id")
        )

    @app.post("/notifications", status_code=201)
    def request_notification(
        tenant_id: TenantId, session: Session, body: NotificationBody
    ) -> dict[str, Any]:
        """RequestNotification. Decides, renders, authors -- and never sends."""
        # **A critical alert is a different permission.** `priority: "critical"` with any
        # non-blank `bypass_policy_ref` overrides the opt-out, the quiet window and the
        # frequency cap, and the first version charged the same routine, AAL-1 permission as an
        # ordinary request -- so paragraph 2461's "only under documented policy" was satisfied
        # by typing one character. The repository's own remedy for that shape is MOD-009's
        # `privacy.consent.record_on_behalf`: route the claim to a stronger permission rather
        # than trust the field. Nothing here resolves the reference against a real policy; that
        # is a gap, and it is now a gap behind a stepped-up, financial-class permission.
        action = ("notifications.notification.request_critical"
                  if body.priority == "critical" else "notifications.notification.request")
        permit(session, action, body.correlation_id)
        return notifications.request_notification(
            tenant_pool, tenant_id, template_key=body.template_key,
            recipient_id=require_uuid(body.recipient_id, "recipient_id"),
            address_digests=body.address_digests, idempotency_key=body.idempotency_key,
            variables=body.variables, locale=body.locale, priority=body.priority,
            bypass_policy_ref=body.bypass_policy_ref, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/notifications/{notification_id}/dispatch")
    def dispatch_notification(
        tenant_id: TenantId, session: Session, notification_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        """Claims the delivery for whatever does the sending. Nothing here sends."""
        permit(session, "notifications.delivery.dispatch", body.correlation_id)
        return notifications.dispatch_notification(
            tenant_pool, tenant_id, require_uuid(notification_id, "notification_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/notifications/{notification_id}/outcome")
    def record_outcome(
        tenant_id: TenantId, session: Session, notification_id: str, body: OutcomeBody
    ) -> dict[str, Any]:
        """A bounce or a complaint suppresses the address in the same transaction, which is
        what stops the next notification going out before anybody noticed."""
        permit(session, "notifications.delivery.dispatch", body.correlation_id)
        return notifications.record_outcome(
            tenant_pool, tenant_id, require_uuid(notification_id, "notification_id"),
            outcome=body.outcome, error=body.error, provider_ref=body.provider_ref,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/notifications/suppressions/all")
    def read_suppressions(
        tenant_id: TenantId, session: Session, channel: str | None = None,
        include_released: bool = False, limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> list[dict[str, Any]]:
        permit(session, "notifications.suppression.read")
        return notifications.list_suppressions(
            tenant_pool, tenant_id, channel=channel, include_released=include_released,
            limit=limit,
        )

    @app.post("/notifications/suppressions", status_code=201)
    def suppress_address(
        tenant_id: TenantId, session: Session, body: SuppressionBody
    ) -> dict[str, Any]:
        permit(session, "notifications.suppression.write", body.correlation_id)
        return notifications.suppress_address(
            tenant_pool, tenant_id, channel=body.channel,
            address_digest=body.address_digest, reason=body.reason, detail=body.detail,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/notifications/suppressions/{suppression_id}/release")
    def release_suppression(
        tenant_id: TenantId, session: Session, suppression_id: str,
        body: ReleaseSuppressionBody,
    ) -> dict[str, Any]:
        """Only an unsubscribe may be released: a bounce or a complaint is the channel's
        judgement, and overriding it damages every other notification's chance of arriving."""
        permit(session, "notifications.suppression.release", body.correlation_id)
        return notifications.release_suppression(
            tenant_pool, tenant_id, require_uuid(suppression_id, "suppression_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/notifications/digests/all")
    def read_digests(
        tenant_id: TenantId, session: Session, recipient_id: str | None = None,
        state: str | None = None, limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        permit(session, "notifications.notification.read")
        return notifications.list_digests(
            tenant_pool, tenant_id,
            recipient_id=optional_uuid(recipient_id, "recipient_id"), state=state,
            limit=limit,
        )

    @app.get("/notifications/recipients/{recipient_id}/channels")
    def read_recipient_channels(
        tenant_id: TenantId, session: Session, recipient_id: str
    ) -> list[dict[str, Any]]:
        """Which address digest this recipient is bound to on each channel."""
        permit(session, "notifications.preference.read")
        return notifications.list_recipient_channels(
            tenant_pool, tenant_id, require_uuid(recipient_id, "recipient_id")
        )

    def held_permissions(session: dict[str, Any]) -> set[str]:
        """Which permissions this caller can **exercise**, for the field masking to read.

        One extra query per masked read, and the honest way to answer "which sensitivity classes
        may this caller see". The gate answers one action at a time; the mask is about five
        classes at once, so asking the evaluator for the set is cheaper and more truthful than
        five more gate calls -- and it goes through `effective_permissions`, which is the
        evaluator's own rules rather than a second reading of the assignment rows.

        **Filtered by the session's assurance, which is the half that was missing.**
        `effective_permissions` answers from role assignments alone; nothing on that path looks
        at `session["aal"]`, and `permit` assurance-checks only the *route's* action -- which for
        every masked read is routine. So every permission the masking consulted was effectively
        routine-class however the catalogue declared it: a password-only session holding
        `member.health.read` read medical notes, and `member.identity.read` and
        `member.finance.read` opened their classes with no second factor. All three are declared
        for AAL 2 or 3, and the catalogue, `visibility` and CLAUDE.md all said so; the claim was
        false until this filter existed. Found by review.

        `member.health.read` is `biometric_sensitive`, so it needs AAL 3 -- **which is
        reachable now**, by signing in with a device-bound passkey. This filter removed it from
        every session in the build for as long as nothing could verify a WebAuthn assertion,
        and that was the dead end `visibility.UNREACHABLE_CLASSES` named; what it does now is
        the thing it was always written to do, which is to let the level decide.
        """
        answer = authz.effective_permissions(
            identity_pool, session["tenant_id"], identity_id=session["identity_id"])
        aal = int(session["aal"])
        return {
            name for name in answer["permissions"]
            if identity_policy.ACTION_ASSURANCE[authz_catalog.action_class(name)] <= aal
        }

    def actor_person_id(tenant_id: str, session: dict[str, Any]) -> str | None:
        """Which person this caller *is*, where one is linked.

        It decides whether a guardian may read their own dependent's record without holding
        staff permissions, so it is derived from the link table rather than taken from the
        request -- MOD-008's rule, and the one its review found four separate violations of.
        """
        return people.person_of_identity(
            tenant_pool, tenant_id, identity_id=session["identity_id"])

    @app.put("/notifications/recipients/{recipient_id}/channels")
    def rebind_recipient_channel(
        tenant_id: TenantId, session: Session, recipient_id: str, body: RebindBody
    ) -> dict[str, Any]:
        """Move a recipient's address binding, with an actor and a written reason.

        A separate, stronger permission from requesting a notification: a suppression is keyed
        on the digest, so rebinding is how somebody would walk a complainant's address away
        from the bounce recorded against it.
        """
        permit(session, "notifications.recipient.rebind", body.correlation_id)
        return notifications.rebind_recipient_channel(
            tenant_pool, tenant_id,
            recipient_id=require_uuid(recipient_id, "recipient_id"),
            channel=body.channel, address_digest=body.address_digest, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    # ------------------------------------------------------------ MOD-014, people

    @app.post("/people", status_code=201)
    def create_person(
        tenant_id: TenantId, session: Session, body: PersonBody
    ) -> dict[str, Any]:
        """CreatePerson, with its contact points, publishing `person.created`."""
        permit(session, "people.person.write", body.correlation_id)
        return people.create_person(
            tenant_pool, tenant_id, legal_name=body.legal_name,
            preferred_name=body.preferred_name, date_of_birth=body.date_of_birth,
            contacts=[c.model_dump() for c in body.contacts],
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/people")
    def list_people(
        tenant_id: TenantId, session: Session,
        lifecycle_state: str | None = None, tag_key: str | None = None, limit: int = 50,
    ) -> dict[str, Any]:
        """The members list, **masked**, bounded, and honest about what it cannot answer.

        ADM-MEM-05 specifies seven columns; this module owns two of them. The rest are other
        modules' and the surface composes them from each module's own list route -- paragraph
        1300 bars a cross-domain join, not a surface that asks twice. The response names the
        ones nothing in this build can answer at all, so a page cannot render an empty cell
        as a fact about a member.
        """
        gate = permit(session, "people.person.read")
        return people.list_people(
            tenant_pool, tenant_id,
            masked_fields=gate.masked_fields, held_permissions=held_permissions(session),
            lifecycle_state=lifecycle_state, tag_key=tag_key, limit=limit,
        )

    @app.get("/people/contact-match")
    def match_contact(
        tenant_id: TenantId, session: Session, kind: str, value: str, limit: int = 5,
    ) -> dict[str, Any]:
        """Who already holds this contact value, asked **before** a record is created.

        ADM-MEM-10 calls this as the phone is typed. `find_duplicates` scores pairs that
        already exist, so the moment a duplicate is cheapest to prevent had nothing to ask;
        the index this uses has existed since MOD-014 with no route able to pass it a value.

        `people.person.read` rather than a permission of its own: the same credential already
        reads any person by id and lists every member, and the name comes back through the
        gate's masked-field list like every other read of a person here.

        **Not in `UNGATED` and not a search.** The value is normalized by the write's own
        function and compared for equality, so a mistyped digit finds nothing -- which is
        `dedup`'s own reason for having no fuzzy match.
        """
        gate = permit(session, "people.person.read")
        return people.match_contact(
            tenant_pool, tenant_id, kind=kind, value=value,
            masked_fields=gate.masked_fields, held_permissions=held_permissions(session),
            limit=limit,
        )

    @app.get("/people/lookup")
    def lookup_people(
        tenant_id: TenantId, session: Session, q: str, limit: int = 5,
    ) -> dict[str, Any]:
        """Find the person at the desk by the start of their name. FD-02. ADR-0012.

        **A lookup, not a search.** Paragraph 4218's permission-aware search index with a
        mandatory query pre-filter is ENG-01's, and MOD-014's own gap list sends it there; this
        read has none of the four properties that objection is about -- one entity, one tenant
        enforced by RLS below the query, no index to be stale because it reads the table of
        record, and a bounded page every row of which goes through this module's gate.

        `people.person.read`, masked through the same gate as every other read here, so a
        routine front-desk session gets the withheld marker and the rest of the row: enough to
        say two people match, with the step-up offered rather than a column of markers.
        """
        gate = permit(session, "people.person.read")
        return people.lookup_people(
            tenant_pool, tenant_id, query=q, limit=limit,
            masked_fields=gate.masked_fields,
            held_permissions=held_permissions(session),
        )

    @app.get("/people/names")
    def read_people_names(
        tenant_id: TenantId, session: Session,
        person_id: Annotated[list[str], Query()],
    ) -> dict[str, Any]:
        """Who these people are, for a surface that already holds a list of ids.

        **FD-06's roster is MOD-020's and the names are MOD-014's.** Paragraph 1300 bars the
        join and a surface asking twice is not a join -- but eighteen rows asking one at a
        time is the round-trip problem `/authz/checks` exists for, which the staff list
        already paid for once. One request, one answer per id.

        `people.person.read`, masked through this module's own gate, so a routine front-desk
        session gets the withheld marker and a stepped-up one gets the name: the same answer
        `GET /people/{id}` gives for each of them, which is what makes a batch a list of
        single reads rather than a weaker one.
        """
        gate = permit(session, "people.person.read")
        return people.names_of(
            tenant_pool, tenant_id,
            require_uuids(person_id, "person_id", limit=people.NAMES_BATCH),
            masked_fields=gate.masked_fields, held_permissions=held_permissions(session),
        )

    @app.get("/people/by-identity")
    def read_people_of_identities(
        tenant_id: TenantId, session: Session,
        identity_id: Annotated[list[str], Query()],
    ) -> dict[str, Any]:
        """Which person each of these MOD-007 identities signs in as.

        **The reverse of what `GET /staff` composes, and nothing in the build had it.** A
        till's `opened_by`, a shift's `closed_by` and an attendance's `recorded_by` are
        identities, so a screen rendering an actor needs identity, then person, then
        `/people/names` -- and FD-07's "HANDED OVER FROM KAREEM" is exactly that chain.

        It returns no names, so `people.person.read` is the gate and there is nothing to mask:
        what it discloses is the link between a sign-in and a person, which is what that
        permission is about.
        """
        permit(session, "people.person.read")
        return people.people_of_identities(
            tenant_pool, tenant_id,
            identity_ids=require_uuids(
                identity_id, "identity_id", limit=people.IDENTITY_LINK_PAGE),
        )

    @app.get("/staff")
    def list_staff(
        tenant_id: TenantId, session: Session, employment_state: str | None = None,
        location_id: str | None = None, limit: int = 50,
    ) -> dict[str, Any]:
        """ADM-STF-01's staff list, **masked**, bounded, and honest about its three gaps.

        `ppl_staff_profiles` has been written since MOD-014 and read by nothing: this is its
        first reader. Two of the design's four columns are on other planes and the response
        names them with the permission that answers each, because a column rendered empty
        reads as a fact about the person.
        """
        gate = permit(session, "people.person.read")
        return people.list_staff(
            tenant_pool, tenant_id,
            masked_fields=gate.masked_fields, held_permissions=held_permissions(session),
            employment_state=employment_state,
            location_id=optional_uuid(location_id, "location_id"), limit=limit,
        )

    @app.get("/staff/{person_id}")
    def read_staff_profile(
        tenant_id: TenantId, session: Session, person_id: str
    ) -> dict[str, Any]:
        """One staff profile -- the employment half, with no name in it.

        The person is `GET /people/{person_id}`, which applies the gate's mask, this module's
        class mask and the guardianship check. A second read returning a name under its own
        rules would be a second place the mask has to be right.
        """
        permit(session, "people.person.read")
        return people.read_staff_profile(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"))

    @app.get("/people/{person_id}")
    def read_person(
        tenant_id: TenantId, session: Session, person_id: str
    ) -> dict[str, Any]:
        """One person, **masked**.

        This is the first read path in the build that applies `Decision.mask`: the gate's
        `masked_fields` and the caller's permission set both go into the service, and a field
        the caller may not see comes back as `***` rather than being omitted -- because "you may
        not see this" and "there is none" lead a front desk to different next actions.
        """
        gate = permit(session, "people.person.read")
        return people.get_person(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            masked_fields=gate.masked_fields, held_permissions=held_permissions(session),
            actor_person_id=actor_person_id(tenant_id, session),
        )

    @app.patch("/people/{person_id}")
    def update_person(
        tenant_id: TenantId, session: Session, person_id: str, body: PersonUpdateBody
    ) -> dict[str, Any]:
        permit(session, "people.person.write", body.correlation_id)
        return people.update_person(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            expected_version=body.expected_version, legal_name=body.legal_name,
            preferred_name=body.preferred_name, date_of_birth=body.date_of_birth,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/identity-links", status_code=201)
    def link_identity(
        tenant_id: TenantId, session: Session, person_id: str, body: IdentityLinkBody
    ) -> dict[str, Any]:
        """LinkIdentity. Unverifiable from this plane, which is the isolation working."""
        permit(session, "people.person.write", body.correlation_id)
        return people.link_identity(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            identity_id=require_uuid(body.identity_id, "identity_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.put("/people/{person_id}/profile")
    def set_tenant_profile(
        tenant_id: TenantId, session: Session, person_id: str, body: TenantProfileBody
    ) -> dict[str, Any]:
        permit(session, "people.person.write", body.correlation_id)
        return people.upsert_tenant_profile(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            expected_version=body.expected_version,
            brand_id=optional_uuid(body.brand_id, "brand_id"),
            location_id=optional_uuid(body.location_id, "location_id"),
            acquisition_source=body.acquisition_source,
            preferred_language=body.preferred_language, notes_internal=body.notes_internal,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/member-profile", status_code=201)
    def create_member_profile(
        tenant_id: TenantId, session: Session, person_id: str, body: MemberProfileBody
    ) -> dict[str, Any]:
        permit(session, "people.person.write", body.correlation_id)
        return people.create_member_profile(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            lifecycle_state=body.lifecycle_state, member_number=body.member_number,
            joined_on=body.joined_on, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/lifecycle")
    def change_lifecycle(
        tenant_id: TenantId, session: Session, person_id: str, body: LifecycleBody
    ) -> dict[str, Any]:
        """Move a member through the lifecycle. The moves that take something away say why."""
        permit(session, "people.person.write", body.correlation_id)
        return people.change_member_lifecycle(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            to_state=body.to_state, expected_version=body.expected_version,
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/staff-profile", status_code=201)
    def create_staff_profile(
        tenant_id: TenantId, session: Session, person_id: str, body: StaffProfileBody
    ) -> dict[str, Any]:
        permit(session, "people.person.write", body.correlation_id)
        return people.upsert_staff_profile(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            job_title=body.job_title,
            location_id=optional_uuid(body.location_id, "location_id"),
            started_on=body.started_on, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/staff-profile/end")
    def end_staff_employment(
        tenant_id: TenantId, session: Session, person_id: str, body: StaffEndBody
    ) -> dict[str, Any]:
        permit(session, "people.person.write", body.correlation_id)
        return people.end_staff_employment(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            expected_version=body.expected_version, ended_on=body.ended_on,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/contacts", status_code=201)
    def add_contact_point(
        tenant_id: TenantId, session: Session, person_id: str, body: ContactPointBody
    ) -> dict[str, Any]:
        permit(session, "people.person.write", body.correlation_id)
        return people.add_contact_point(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"), kind=body.kind,
            value=body.value, is_primary=body.is_primary, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/people/contacts/{contact_point_id}/verify")
    def verify_contact_point(
        tenant_id: TenantId, session: Session, contact_point_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        """Records that a named actor asserted a verification. Nothing here verifies."""
        permit(session, "people.person.write", body.correlation_id)
        return people.verify_contact_point(
            tenant_pool, tenant_id, require_uuid(contact_point_id, "contact_point_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/people/relationships", status_code=201)
    def add_relationship(
        tenant_id: TenantId, session: Session, body: RelationshipBody
    ) -> dict[str, Any]:
        permit(session, "people.relationship.write", body.correlation_id)
        return people.add_relationship(
            tenant_pool, tenant_id, kind=body.kind,
            from_person_id=require_uuid(body.from_person_id, "from_person_id"),
            to_person_id=require_uuid(body.to_person_id, "to_person_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/people/relationships/{relationship_id}/end")
    def end_relationship(
        tenant_id: TenantId, session: Session, relationship_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        permit(session, "people.relationship.write", body.correlation_id)
        return people.end_relationship(
            tenant_pool, tenant_id, require_uuid(relationship_id, "relationship_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/notes", status_code=201)
    def record_note(
        tenant_id: TenantId, session: Session, person_id: str, body: NoteBody
    ) -> dict[str, Any]:
        """RecordMemberNote. Insert-only: a correction is a new note."""
        permit(session, "people.note.write", body.correlation_id)
        return people.record_note(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"), body=body.body,
            note_class=body.note_class, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/people/{person_id}/notes")
    def read_notes(
        tenant_id: TenantId, session: Session, person_id: str,
        include_withdrawn: bool = False, limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        """A person's notes, with the body of each class the caller may not read replaced.

        The record survives and only its content goes: telling a coach that a member has no
        health notes when they have three is worse than telling them there are three they
        cannot read.
        """
        gate = permit(session, "people.person.read")
        return people.list_notes(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            masked_fields=gate.masked_fields,
            held_permissions=held_permissions(session),
            actor_person_id=actor_person_id(tenant_id, session),
            include_withdrawn=include_withdrawn, limit=limit,
        )

    @app.post("/people/notes/{note_id}/withdraw")
    def withdraw_note(
        tenant_id: TenantId, session: Session, note_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        permit(session, "people.note.write", body.correlation_id)
        return people.withdraw_note(
            tenant_pool, tenant_id, require_uuid(note_id, "note_id"), reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/people/tags", status_code=201)
    def create_tag(
        tenant_id: TenantId, session: Session, body: TagBody
    ) -> dict[str, Any]:
        permit(session, "people.schema.write", body.correlation_id)
        return people.create_tag(
            tenant_pool, tenant_id, tag_key=body.tag_key, display_name=body.display_name,
            is_internal=body.is_internal, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/tags", status_code=201)
    def apply_tag(
        tenant_id: TenantId, session: Session, person_id: str, body: ApplyTagBody
    ) -> dict[str, Any]:
        permit(session, "people.person.write", body.correlation_id)
        return people.apply_tag(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            tag_id=require_uuid(body.tag_id, "tag_id"), actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/tags/remove")
    def remove_tag(
        tenant_id: TenantId, session: Session, person_id: str, body: ApplyTagBody
    ) -> dict[str, Any]:
        permit(session, "people.person.write", body.correlation_id)
        return people.remove_tag(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            tag_id=require_uuid(body.tag_id, "tag_id"), actor_id=session["identity_id"],
        )

    @app.post("/people/custom-fields", status_code=201)
    def define_custom_field(
        tenant_id: TenantId, session: Session, body: CustomFieldBody
    ) -> dict[str, Any]:
        """Declare a custom field. Its type and sensitivity are final once written."""
        permit(session, "people.schema.write", body.correlation_id)
        return people.define_custom_field(
            tenant_pool, tenant_id, field_key=body.field_key,
            display_name=body.display_name, value_type=body.value_type,
            sensitivity=body.sensitivity, is_required=body.is_required,
            options=[{"value": o.value, "display_name": o.display_name or o.value}
                     for o in body.options],
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.put("/people/{person_id}/custom-fields")
    def set_custom_field_value(
        tenant_id: TenantId, session: Session, person_id: str, body: CustomFieldValueBody
    ) -> dict[str, Any]:
        permit(session, "people.person.write", body.correlation_id)
        return people.set_custom_field_value(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            field_key=body.field_key, value=body.value, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/people/{person_id}/duplicates")
    def find_duplicates(
        tenant_id: TenantId, session: Session, person_id: str, body: CorrelationBody
    ) -> list[dict[str, Any]]:
        """Score this person against everybody who shares an exact signal, and queue the pairs.

        Every signal is named and the weights are in `dedup.WEIGHTS`: an operator asked to merge
        two records is being asked to destroy one of them, and a score with no reasons behind it
        is not something to do that on.
        """
        permit(session, "people.duplicate.review", body.correlation_id)
        return people.find_duplicates(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/people/duplicates/all")
    def read_duplicate_candidates(
        tenant_id: TenantId, session: Session, status: str = "open",
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        permit(session, "people.duplicate.review")
        return people.list_duplicate_candidates(
            tenant_pool, tenant_id, status=status, limit=limit
        )

    @app.post("/people/duplicates/{candidate_id}/dismiss")
    def dismiss_duplicate(
        tenant_id: TenantId, session: Session, candidate_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        permit(session, "people.duplicate.review", body.correlation_id)
        return people.dismiss_duplicate_candidate(
            tenant_pool, tenant_id, require_uuid(candidate_id, "candidate_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/people/merges/plan")
    def plan_merge(
        tenant_id: TenantId, session: Session, source_person_id: str, target_person_id: str
    ) -> dict[str, Any]:
        """What a merge would move, and what it would leave behind, before anybody agrees."""
        permit(session, "people.merge.decide")
        return people.plan_merge(
            tenant_pool, tenant_id,
            source_person_id=require_uuid(source_person_id, "source_person_id"),
            target_person_id=require_uuid(target_person_id, "target_person_id"),
        )

    @app.post("/people/merges", status_code=201)
    def merge_persons(
        tenant_id: TenantId, session: Session, body: MergeBody
    ) -> dict[str, Any]:
        """MergePerson. Nothing is deleted; the losing record points at the survivor."""
        permit(session, "people.merge.decide", body.correlation_id)
        return people.merge_persons(
            tenant_pool, tenant_id,
            source_person_id=require_uuid(body.source_person_id, "source_person_id"),
            target_person_id=require_uuid(body.target_person_id, "target_person_id"),
            reason=body.reason, candidate_id=optional_uuid(body.candidate_id, "candidate_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/people/merges/{merge_id}/reverse")
    def reverse_merge(
        tenant_id: TenantId, session: Session, merge_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        """Undo a merge as far as this module can, and say what does not come back."""
        permit(session, "people.merge.decide", body.correlation_id)
        return people.reverse_merge(
            tenant_pool, tenant_id, require_uuid(merge_id, "merge_id"), reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/people/timeline/project")
    def project_timeline(
        tenant_id: TenantId, session: Session, body: CorrelationBody,
        limit: int = Query(default=500, ge=1, le=5000),
    ) -> dict[str, Any]:
        """Build timeline entries from events in the outbox. Idempotent, and nothing loops."""
        permit(session, "people.timeline.read", body.correlation_id)
        return people.project_timeline(tenant_pool, tenant_id, limit=limit)

    @app.get("/people/{person_id}/timeline")
    def read_timeline(
        tenant_id: TenantId, session: Session, person_id: str,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        """Paragraph 4224: masking is applied **at read time**, which is why it is here."""
        gate = permit(session, "people.timeline.read")
        return people.read_timeline(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            masked_fields=gate.masked_fields,
            held_permissions=held_permissions(session),
            actor_person_id=actor_person_id(tenant_id, session), limit=limit,
        )

    @app.get("/people/{person_id}/360")
    def member_360(
        tenant_id: TenantId, session: Session, person_id: str
    ) -> dict[str, Any]:
        """PPL-01-R02, composed rather than stored -- and every section names its source.

        The sections whose owning module does not exist in this build say so. Returning an empty
        list for them would read as "none", which is the difference between "this member has no
        outstanding balance" and "nothing here knows".
        """
        gate = permit(session, "people.person.read")
        return people.member_360(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"),
            masked_fields=gate.masked_fields, held_permissions=held_permissions(session),
            actor_person_id=actor_person_id(tenant_id, session),
        )

    # ------------------------------------------------------------ MOD-016, catalog

    @app.post("/catalog/tax-categories", status_code=201)
    def register_tax_category(
        tenant_id: TenantId, session: Session, body: TaxCategoryBody
    ) -> dict[str, Any]:
        """Name a tax regime. It holds no rate; paragraph 4077 puts rates elsewhere."""
        permit(session, "catalog.product.write", body.correlation_id)
        return catalog.register_tax_category(
            tenant_pool, tenant_id, category_key=body.category_key,
            display_name=body.display_name, jurisdiction_note=body.jurisdiction_note,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/catalog/products", status_code=201)
    def create_product(
        tenant_id: TenantId, session: Session, body: ProductBody
    ) -> dict[str, Any]:
        """CreateProduct, with its localized text and its variants."""
        permit(session, "catalog.product.write", body.correlation_id)
        return catalog.create_product(
            tenant_pool, tenant_id, product_key=body.product_key,
            product_type=body.product_type,
            tax_category_id=optional_uuid(body.tax_category_id, "tax_category_id"),
            brand_id=optional_uuid(body.brand_id, "brand_id"),
            merchandising_rank=body.merchandising_rank,
            texts=[t.model_dump() for t in body.texts],
            variants=[v.model_dump() for v in body.variants],
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/catalog/products")
    def read_products(
        tenant_id: TenantId, session: Session, status: str | None = None,
        locale: str = "en", limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        """The listing, in COM-02-R06's merchandising order, with no locale fallback."""
        permit(session, "catalog.product.read")
        return catalog.list_products(
            tenant_pool, tenant_id, status=status, locale=locale, limit=limit
        )

    @app.get("/catalog/products/{product_id}")
    def get_catalog_product(
        tenant_id: TenantId, session: Session, product_id: str, locale: str = "en",
    ) -> dict[str, Any]:
        """One product with its variants. A price needs `catalog.price.read`, not this."""
        permit(session, "catalog.product.read")
        return catalog.get_product(
            tenant_pool, tenant_id, require_uuid(product_id, "product_id"), locale=locale)

    @app.post("/catalog/products/{product_id}/publish")
    def publish_product(
        tenant_id: TenantId, session: Session, product_id: str, body: VersionedBody
    ) -> dict[str, Any]:
        """PublishCatalog, for one product. A product with no price anywhere is refused."""
        permit(session, "catalog.product.publish", body.correlation_id)
        return catalog.publish_product(
            tenant_pool, tenant_id, require_uuid(product_id, "product_id"),
            expected_version=body.expected_version, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/catalog/products/{product_id}/retire")
    def retire_product(
        tenant_id: TenantId, session: Session, product_id: str, body: VersionedBody
    ) -> dict[str, Any]:
        """Stop selling it. Sales already made keep resolving, which is COM-02-R07."""
        permit(session, "catalog.product.publish", body.correlation_id)
        return catalog.retire_product(
            tenant_pool, tenant_id, require_uuid(product_id, "product_id"),
            expected_version=body.expected_version, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/catalog/price-books", status_code=201)
    def create_price_book(
        tenant_id: TenantId, session: Session, body: PriceBookBody
    ) -> dict[str, Any]:
        permit(session, "catalog.price.write", body.correlation_id)
        return catalog.create_price_book(
            tenant_pool, tenant_id, price_book_key=body.price_book_key,
            display_name=body.display_name, currency=body.currency,
            effective_from=body.effective_from, effective_to=body.effective_to,
            brand_id=optional_uuid(body.brand_id, "brand_id"),
            location_id=optional_uuid(body.location_id, "location_id"),
            channel=body.channel, customer_segment=body.customer_segment,
            tax_category_id=optional_uuid(body.tax_category_id, "tax_category_id"),
            priority=body.priority, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.get("/catalog/price-books")
    def read_price_books(
        tenant_id: TenantId, session: Session,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        """The pricing structure: keys, currencies, channels, segments and priorities.

        Gated on `catalog.price.read` rather than on `catalog.product.read`, whose description
        is "see the product catalog". Promotions have their own read permission; price books
        were riding on the product one and returning a different thing from what it says.
        """
        permit(session, "catalog.price.read")
        return catalog.list_price_books(tenant_pool, tenant_id, limit=limit)

    @app.post("/catalog/price-books/{price_book_id}/activate")
    def activate_price_book(
        tenant_id: TenantId, session: Session, price_book_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "catalog.price.write", body.correlation_id)
        return catalog.activate_price_book(
            tenant_pool, tenant_id, require_uuid(price_book_id, "price_book_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/catalog/prices")
    def list_catalog_prices(
        tenant_id: TenantId, session: Session, price_book_id: str | None = None,
        variant_id: str | None = None, include_superseded: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        """The price rows that were written. `resolve_price` is the sale, not a lookup."""
        permit(session, "catalog.price.read")
        return catalog.list_prices(
            tenant_pool, tenant_id,
            price_book_id=optional_uuid(price_book_id, "price_book_id"),
            variant_id=optional_uuid(variant_id, "variant_id"),
            include_superseded=include_superseded, limit=limit)

    @app.post("/catalog/prices", status_code=201)
    def create_price(
        tenant_id: TenantId, session: Session, body: PriceBody
    ) -> dict[str, Any]:
        """CreatePrice. A new row, never an edit -- COM-02-R07 as a privilege."""
        permit(session, "catalog.price.write", body.correlation_id)
        return catalog.create_price(
            tenant_pool, tenant_id,
            price_book_id=require_uuid(body.price_book_id, "price_book_id"),
            variant_id=require_uuid(body.variant_id, "variant_id"),
            amount_minor=body.amount_minor, effective_from=body.effective_from,
            effective_to=body.effective_to, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/catalog/prices/{price_id}/supersede")
    def supersede_price(
        tenant_id: TenantId, session: Session, price_id: str, body: SupersedeBody
    ) -> dict[str, Any]:
        """Withdraw a price in favour of another, without editing either."""
        permit(session, "catalog.price.write", body.correlation_id)
        return catalog.supersede_price(
            tenant_pool, tenant_id, require_uuid(price_id, "price_id"),
            replacement_price_id=require_uuid(
                body.replacement_price_id, "replacement_price_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/catalog/promotions", status_code=201)
    def create_promotion(
        tenant_id: TenantId, session: Session, body: PromotionBody
    ) -> dict[str, Any]:
        permit(session, "catalog.promotion.write", body.correlation_id)
        return catalog.create_promotion(
            tenant_pool, tenant_id, promotion_key=body.promotion_key,
            display_name=body.display_name, promotion_kind=body.promotion_kind,
            effective_from=body.effective_from, effective_to=body.effective_to,
            percent_bp=body.percent_bp, amount_minor=body.amount_minor,
            currency=body.currency, stacking_group=body.stacking_group,
            priority=body.priority, approval_threshold_bp=body.approval_threshold_bp,
            rules=[r.model_dump() for r in body.rules],
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/catalog/promotions")
    def read_promotions(
        tenant_id: TenantId, session: Session,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        permit(session, "catalog.promotion.read")
        return catalog.list_promotions(tenant_pool, tenant_id, limit=limit)

    @app.post("/catalog/promotions/{promotion_id}/activate")
    def activate_promotion(
        tenant_id: TenantId, session: Session, promotion_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "catalog.promotion.write", body.correlation_id)
        return catalog.activate_promotion(
            tenant_pool, tenant_id, require_uuid(promotion_id, "promotion_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/catalog/coupons", status_code=201)
    def issue_coupon(
        tenant_id: TenantId, session: Session, body: CouponBody
    ) -> dict[str, Any]:
        permit(session, "catalog.promotion.write", body.correlation_id)
        return catalog.issue_coupon(
            tenant_pool, tenant_id,
            promotion_id=require_uuid(body.promotion_id, "promotion_id"),
            code=body.code, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/catalog/coupons/{coupon_id}/revoke")
    def revoke_coupon(
        tenant_id: TenantId, session: Session, coupon_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        """Stop a code working without ending the campaign it reaches."""
        permit(session, "catalog.promotion.write", body.correlation_id)
        return catalog.revoke_coupon(
            tenant_pool, tenant_id, require_uuid(coupon_id, "coupon_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/catalog/promotions/validate")
    def validate_promotion(
        tenant_id: TenantId, session: Session, body: ValidatePromotionBody
    ) -> dict[str, Any]:
        """ValidatePromotion: would this code work, and if not, why not? A read, no side effect."""
        permit(session, "catalog.price.resolve")
        return catalog.validate_promotion(
            tenant_pool, tenant_id, code=body.code, subtotal_minor=body.subtotal_minor,
            currency=body.currency, channel=body.channel,
            product_type=body.product_type,
            subject_id=optional_uuid(body.subject_id, "subject_id"),
        )

    @app.post("/catalog/prices/quote")
    def quote_price(
        tenant_id: TenantId, session: Session, body: QuotePriceBody
    ) -> dict[str, Any]:
        """QuotePrice: what a sale would cost, recording nothing.

        **The reader `catalog.price.read` was described as granting and did not have.** Its
        own line in the catalogue is "See price books and what a sale would cost", and until
        now the only thing that could answer the second half was `/catalog/prices/resolve` --
        which *is* the sale: it stores the explanation insert-only and redeems the coupon it
        applies, so a screen that wanted a figure before anybody agreed had to make one.

        **It is a read, so it is on the read permission and not the sale's.** Both are
        `data_access` with no financial class, so neither needs a step-up; what separates them
        is that one writes. `catalog.price.resolve` stays the permission that can spend a
        coupon and consume an approval.
        """
        permit(session, "catalog.price.read", body.correlation_id)
        return catalog.quote_price(
            tenant_pool, tenant_id,
            variant_id=require_uuid(body.variant_id, "variant_id"),
            currency=body.currency, quantity=body.quantity, channel=body.channel,
            location_id=optional_uuid(body.location_id, "location_id"),
            subject_id=optional_uuid(body.subject_id, "subject_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/catalog/prices/resolve", status_code=201)
    def resolve_price(
        tenant_id: TenantId, session: Session, body: ResolvePriceBody
    ) -> dict[str, Any]:
        """ResolvePrice: the number, and the whole reasoning, recorded.

        Paragraph 10220's two controls meet here: the resolution is deterministic and its
        explanation is stored insert-only, and an override or a deep discount is refused
        without an approval row that covers this variant at this list amount.
        """
        permit(session, "catalog.price.resolve", body.correlation_id)
        return catalog.resolve_price(
            tenant_pool, tenant_id,
            variant_id=require_uuid(body.variant_id, "variant_id"),
            currency=body.currency, quantity=body.quantity, channel=body.channel,
            location_id=optional_uuid(body.location_id, "location_id"),
            subject_id=optional_uuid(body.subject_id, "subject_id"),
            coupon_code=body.coupon_code, idempotency_key=body.idempotency_key,
            override_amount_minor=body.override_amount_minor,
            override_reason=body.override_reason,
            approval_id=optional_uuid(body.approval_id, "approval_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/catalog/resolutions/{resolution_id}")
    def read_resolution(
        tenant_id: TenantId, session: Session, resolution_id: str
    ) -> dict[str, Any]:
        """One stored resolution with its whole explanation."""
        permit(session, "catalog.price.resolve")
        return catalog.get_resolution(
            tenant_pool, tenant_id, require_uuid(resolution_id, "resolution_id")
        )

    @app.post("/catalog/discount-requests", status_code=201)
    def request_discount(
        tenant_id: TenantId, session: Session, body: RequestDiscountBody
    ) -> dict[str, Any]:
        """Ask for an override. The requester is this session, not a field in the body."""
        permit(session, "catalog.discount.request", body.correlation_id)
        return catalog.request_discount(
            tenant_pool, tenant_id,
            variant_id=require_uuid(body.variant_id, "variant_id"),
            list_amount_minor=body.list_amount_minor,
            override_amount_minor=body.override_amount_minor, currency=body.currency,
            reason=body.reason, requester_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/catalog/discount-approvals", status_code=201)
    def approve_discount(
        tenant_id: TenantId, session: Session, body: ApproveDiscountBody
    ) -> dict[str, Any]:
        """The audit half of paragraph 10220. Decides a request somebody else recorded."""
        permit(session, "catalog.discount.approve", body.correlation_id)
        return catalog.approve_discount(
            tenant_pool, tenant_id,
            request_id=require_uuid(body.request_id, "request_id"),
            reason=body.reason, approver_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/catalog/coupons/redeem", status_code=201)
    def redeem_coupon(
        tenant_id: TenantId, session: Session, body: RedeemCouponBody
    ) -> dict[str, Any]:
        """RedeemCoupon, for a sale priced outside this module.

        The limits are re-checked here, by reason code rather than by words in the reason, and
        the discount is computed rather than supplied. Where the price comes from this module,
        `/catalog/prices/resolve` redeems in the same transaction instead.
        """
        permit(session, "catalog.coupon.redeem", body.correlation_id)
        return catalog.redeem_coupon(
            tenant_pool, tenant_id, code=body.code, subtotal_minor=body.subtotal_minor,
            currency=body.currency, idempotency_key=body.idempotency_key,
            channel=body.channel,
            subject_id=optional_uuid(body.subject_id, "subject_id"),
            order_reference=body.order_reference, actor_id=session["identity_id"],
            correlation_id=body.correlation_id,
        )

    @app.post("/catalog/bundles", status_code=201)
    def define_bundle(
        tenant_id: TenantId, session: Session, body: BundleBody
    ) -> dict[str, Any]:
        """Declare what a sale of this product owes."""
        permit(session, "catalog.bundle.write", body.correlation_id)
        return catalog.define_bundle(
            tenant_pool, tenant_id,
            product_id=require_uuid(body.product_id, "product_id"),
            items=[{"variant_id": require_uuid(i.variant_id, "variant_id"),
                    "quantity": i.quantity, "fulfilment_kind": i.fulfilment_kind}
                   for i in body.items],
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/catalog/bundles/fulfilments", status_code=201)
    def record_fulfilment(
        tenant_id: TenantId, session: Session, body: FulfilmentBody
    ) -> dict[str, Any]:
        """FulfillBundle, as a record. Nothing in this build delivers anything."""
        permit(session, "catalog.bundle.fulfil", body.correlation_id)
        return catalog.record_fulfilment(
            tenant_pool, tenant_id,
            bundle_id=require_uuid(body.bundle_id, "bundle_id"),
            variant_id=require_uuid(body.variant_id, "variant_id"),
            order_reference=body.order_reference, quantity=body.quantity,
            outcome=body.outcome, idempotency_key=body.idempotency_key,
            subject_id=optional_uuid(body.subject_id, "subject_id"),
            external_reference=body.external_reference, detail=body.detail,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/catalog/bundles/{bundle_id}/status")
    def read_bundle_status(
        tenant_id: TenantId, session: Session, bundle_id: str, order_reference: str
    ) -> dict[str, Any]:
        """What this sale of this bundle still owes."""
        permit(session, "catalog.bundle.fulfil")
        return catalog.bundle_status(
            tenant_pool, tenant_id, require_uuid(bundle_id, "bundle_id"),
            order_reference=order_reference,
        )


    # ------------------------------------------------------------ MOD-017, COM-01

    @app.post("/memberships/contract-versions", status_code=201)
    def draft_contract_version(
        tenant_id: TenantId, session: Session, body: ContractVersionBody
    ) -> dict[str, Any]:
        """COM-01-R02's terms, as a draft. Somebody else publishes it.

        Two acts and not one: an agreement resolves only a published version, so a draft is
        unsignable by construction -- and the one-command version made the author and the
        publisher the same person by definition, on a document with legal effect.
        """
        permit(session, "membership.contract.write", body.correlation_id)
        return commercial.draft_contract_version(
            tenant_pool, tenant_id, contract_key=body.contract_key, body=body.body,
            locale=body.locale, minimum_term_months=body.minimum_term_months,
            notice_days=body.notice_days, renewal_mode=body.renewal_mode,
            cancellation_mode=body.cancellation_mode,
            freeze_days_per_year=body.freeze_days_per_year, grace_days=body.grace_days,
            early_termination_months=body.early_termination_months,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/memberships/contract-versions/{contract_version_id}/publish")
    def publish_contract_version(
        tenant_id: TenantId, session: Session, contract_version_id: str,
        body: CommercialActionBody,
    ) -> dict[str, Any]:
        """Publish a drafted contract version, by somebody other than its author."""
        permit(session, "membership.contract.publish", body.correlation_id)
        return commercial.publish_contract_version(
            tenant_pool, tenant_id,
            require_uuid(contract_version_id, "contract_version_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/memberships/terms", status_code=201)
    def define_membership_terms(
        tenant_id: TenantId, session: Session, body: MembershipTermsBody
    ) -> dict[str, Any]:
        """Attach membership terms to a catalogue product. The product must be a membership."""
        permit(session, "membership.agreement.write", body.correlation_id)
        return commercial.define_membership_terms(
            tenant_pool, tenant_id,
            product_id=require_uuid(body.product_id, "product_id"),
            contract_key=body.contract_key, membership_kind=body.membership_kind,
            billing_period=body.billing_period,
            installment_count=body.installment_count, prepaid_days=body.prepaid_days,
            trial_days=body.trial_days, billing_anchor=body.billing_anchor,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/memberships/agreements", status_code=201)
    def create_agreement(
        tenant_id: TenantId, session: Session, body: AgreementBody
    ) -> dict[str, Any]:
        """CreateMembershipAgreement: the contract, unsigned, with its version pinned."""
        permit(session, "membership.agreement.write", body.correlation_id)
        return commercial.create_agreement(
            tenant_pool, tenant_id,
            person_id=require_uuid(body.person_id, "person_id"),
            membership_terms_id=require_uuid(
                body.membership_terms_id, "membership_terms_id"),
            variant_id=require_uuid(body.variant_id, "variant_id"),
            amount_minor=body.amount_minor, currency=body.currency,
            starts_on=body.starts_on,
            price_resolution_id=optional_uuid(
                body.price_resolution_id, "price_resolution_id"),
            supersedes_agreement_id=optional_uuid(
                body.supersedes_agreement_id, "supersedes_agreement_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/memberships/agreements/{agreement_id}/sign")
    def sign_agreement(
        tenant_id: TenantId, session: Session, agreement_id: str, body: SignatureBody
    ) -> dict[str, Any]:
        """Record the member's signature. COM-01-R02."""
        permit(session, "membership.agreement.write", body.correlation_id)
        return commercial.sign_agreement(
            tenant_pool, tenant_id, require_uuid(agreement_id, "agreement_id"),
            signature_kind=body.signature_kind,
            signature_evidence_ref=body.signature_evidence_ref,
            signed_by_person_id=require_uuid(
                body.signed_by_person_id, "signed_by_person_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/memberships", status_code=201)
    def activate_membership(
        tenant_id: TenantId, session: Session, body: ActivationBody
    ) -> dict[str, Any]:
        """ActivateMembership. A signed agreement, never a draft."""
        permit(session, "membership.agreement.activate", body.correlation_id)
        return commercial.activate_membership(
            tenant_pool, tenant_id,
            agreement_id=require_uuid(body.agreement_id, "agreement_id"),
            membership_number=body.membership_number,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/memberships/{membership_id}/freeze-allowance")
    def read_freeze_allowance(
        tenant_id: TenantId, session: Session, membership_id: str
    ) -> dict[str, Any]:
        """What is left of the contract's freeze allowance. COM-01-R04.

        **`allowance_days_used_before` came back from the *write* and from nothing else**, so
        the only way to learn how much of it a member had spent was to spend more of it. The
        seventh "a writer with no reader" in this build, and ADM-MSH-03 cannot be drawn
        without it -- the canvas puts "2 of 3 freeze months used this year" in the
        consequence panel, *before* the button, which is ADM-PAY-09's decision about a till
        in another module: the figure that bounds the act is shown before the act.

        **Behind `membership.record.read`, which is routine**, and that is the right side of
        the line: this returns a day count, a date window and nothing about the person. A
        front desk that may see a membership may see how much of its allowance is left --
        and `membership.lifecycle.change`, which is financial, is what the act itself costs.
        """
        permit(session, "membership.record.read")
        return commercial.freeze_allowance(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"))

    @app.post("/memberships/{membership_id}/freeze", status_code=201)
    def freeze_membership(
        tenant_id: TenantId, session: Session, membership_id: str, body: FreezeBody
    ) -> dict[str, Any]:
        """FreezeMembership, with the contract's annual allowance enforced. COM-01-R04."""
        permit(session, "membership.lifecycle.change", body.correlation_id)
        return commercial.freeze_membership(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"),
            freeze_kind=body.freeze_kind, starts_on=body.starts_on, days=body.days,
            reason=body.reason, evidence_ref=body.evidence_ref,
            requested_by_person_id=optional_uuid(
                body.requested_by_person_id, "requested_by_person_id"),
            expected_version=body.expected_version,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/memberships/{membership_id}/resume")
    def resume_membership(
        tenant_id: TenantId, session: Session, membership_id: str, body: ResumeBody
    ) -> dict[str, Any]:
        """ResumeMembership, extending the term by the days actually frozen. COM-01-R05."""
        permit(session, "membership.lifecycle.change", body.correlation_id)
        return commercial.resume_membership(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"),
            reason=body.reason, expected_version=body.expected_version,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/memberships/{membership_id}/cancellation-preview")
    def preview_cancellation(
        tenant_id: TenantId, session: Session, membership_id: str
    ) -> dict[str, Any]:
        """COM-01-R06's fee disclosure, as a read with no side effect.

        Gated on the *read* permission, deliberately: showing a member what cancelling would
        cost changes nothing, and requiring the lifecycle permission to quote a figure would
        mean a front desk could cancel but not explain.
        """
        permit(session, "membership.record.read")
        return commercial.preview_cancellation(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"))

    @app.post("/memberships/{membership_id}/cancel")
    def cancel_membership(
        tenant_id: TenantId, session: Session, membership_id: str,
        body: CancelMembershipBody
    ) -> dict[str, Any]:
        """CancelMembership. The acknowledged fee is compared against the fee that is due."""
        permit(session, "membership.lifecycle.change", body.correlation_id)
        return commercial.cancel_membership(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"),
            reason=body.reason, acknowledged_fee_minor=body.acknowledged_fee_minor,
            requested_by_person_id=optional_uuid(
                body.requested_by_person_id, "requested_by_person_id"),
            expected_version=body.expected_version,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/memberships/{membership_id}/plan-change-preview")
    def preview_plan_change(
        tenant_id: TenantId, session: Session, membership_id: str, to_agreement_id: str
    ) -> dict[str, Any]:
        """ADM-MSH-05's and ADM-MSH-06's two figures, as a read with no side effect.

        Gated on the *read* permission for the same reason the cancellation preview is: a
        front desk that could change a plan but not quote what it costs would be a desk
        guessing at the one number the member is about to agree to.

        It takes a drafted agreement rather than an amount, so the figures come from a row
        somebody wrote -- and it answers which of the two acts this is, which no client can
        work out for itself.
        """
        permit(session, "membership.record.read")
        return commercial.preview_plan_change(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"),
            require_uuid(to_agreement_id, "to_agreement_id"))

    @app.post("/memberships/{membership_id}/plan-change")
    def change_membership_plan(
        tenant_id: TenantId, session: Session, membership_id: str, body: PlanChangeBody
    ) -> dict[str, Any]:
        """UpgradeMembership and DowngradeMembership, which were two declared change kinds
        with no writer at all. COM-01-R04."""
        permit(session, "membership.lifecycle.change", body.correlation_id)
        return commercial.change_membership_plan(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"),
            to_agreement_id=require_uuid(body.to_agreement_id, "to_agreement_id"),
            reason=body.reason, signature_kind=body.signature_kind,
            signature_evidence_ref=body.signature_evidence_ref,
            acknowledged_due_minor=body.acknowledged_due_minor,
            requested_by_person_id=optional_uuid(
                body.requested_by_person_id, "requested_by_person_id"),
            expected_version=body.expected_version,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/memberships/{membership_id}/as-of")
    def read_membership_as_of(
        tenant_id: TenantId, session: Session, membership_id: str, moment: date
    ) -> dict[str, Any]:
        """COM-01-R07's as-of reconstruction, replayed from the history."""
        permit(session, "membership.record.read")
        return commercial.membership_as_of(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"),
            moment=moment)

    # ------------------------------------------------------------ MOD-017, the reads
    #
    # Until these existed the module could only be read by somebody who already held the id,
    # so nothing could list a member's memberships, grants, accounts or invoices -- the same
    # "a writer with no reader" gap `GET /brands` closed for MOD-004. Each is gated on the
    # permission that already describes it: `finance.account.read` is literally "See a member
    # billing account, **its invoices** and its schedule", so no permission is invented here.
    #
    # **A person id is a filter, never an authorization.** Passing one narrows the list; it
    # does not make a weaker permission sufficient, and it does not reach anything about the
    # person. MOD-014 answers who they are, through its own gate.

    @app.get("/catalog/variants/{variant_id}/price-impact")
    def price_change_impact(
        tenant_id: TenantId, session: Session, variant_id: str,
    ) -> dict[str, Any]:
        """Who a price rise on this variant reaches, before it is saved. ADM-MSH-09.

        **The count is the point of the screen**, and its own note says so: "the affected count
        is computed before the change is saved, not reported after. A price rise is the most
        consequential action in Admin and the only one where the blast radius is stated in
        members rather than currency."

        **Gated on `membership.record.read` rather than on the catalogue**, because what it
        counts is memberships: it answers how many people are on a plan and how many of them a
        rise cannot reach, which is a fact about agreements. Gating it on `catalog.price.read`
        would make "see what a sale would cost" buy a census of the tenant's membership base --
        MOD-013's `GET /notifications/channels` finding.
        """
        permit(session, "membership.record.read")
        return commercial.price_change_impact(
            tenant_pool, tenant_id,
            variant_id=require_uuid(variant_id, "variant_id"))

    @app.get("/memberships/plans")
    def list_sellable_plans(
        tenant_id: TenantId, session: Session, trials: str = "exclude",
        locale: str = "en", limit: int = commercial.SELLABLE_PLANS,
    ) -> dict[str, Any]:
        """Which membership plans can be sold: ADM-CRM-06's plan pick, and ADM-MSH-01's.

        **`catalog.product.read`, because everything here is a product and its contract
        shape.** There is no figure in the answer -- a price needs `catalog.price.read` and
        only a quote may name it -- and no member data of any kind, so the narrower of the two
        catalogue reads is the right one and the one that would also buy "what every sale
        costs" is not.

        **`trials` is one field with three values and `exclude` is the default**, which is
        what makes this a conversion list. A product whose terms declare `trial_days` is what
        somebody converts *from*, so offering it as a target would let a trial be converted
        into another trial. `include` is "every membership this gym sells", which is a
        different and equally real question; `only` is FD-05's, which trial a walk-in can be
        started on. One field rather than two flags, because two could contradict and the
        answer would be an empty list reading as "this gym sells nothing".

        **The product's name is here as well as the variant's, and the first version carried
        only the variant's.** ADM-MSH-09 found it by rendering the table: six of eight rows
        read "Monthly", because a variant is a term length and a product is the thing a member
        buys. Both of this read's callers are pickers, so a plan nothing can tell apart from
        another is the one defect that makes the read useless. `locale` is joined with **no
        fallback**, which is `list_products`' own rule -- a tenant that has not translated a
        product gets no name rather than an English one -- and `product_text_locale` says
        which, so a surface shows `product_key` rather than a name in a language nobody asked
        for.
        """
        permit(session, "catalog.product.read")
        return commercial.sellable_plans(
            tenant_pool, tenant_id, trials=trials, locale=locale, limit=limit)

    @app.get("/memberships")
    def list_memberships(
        tenant_id: TenantId, session: Session, person_id: str | None = None,
        status: str | None = None, limit: int = 50,
    ) -> dict[str, Any]:
        """The tenant's memberships, newest first, optionally one person's."""
        permit(session, "membership.record.read")
        return commercial.list_memberships(
            tenant_pool, tenant_id,
            person_id=optional_uuid(person_id, "person_id"), status=status, limit=limit)

    # **Declared before `/memberships/{membership_id}`, and that is load-bearing.** FastAPI
    # matches in declaration order, so a literal segment behind a path parameter is never
    # reached: with this route below, `/memberships/summary` was matched by the one under it
    # and answered 422 `bad_membership_id`. Found by the test, not by reading.
    @app.get("/memberships/summary")
    def read_membership_summary(
        tenant_id: TenantId, session: Session, as_of: date | None = None,
        expiring_within_days: int = 7,
    ) -> dict[str, Any]:
        """How many memberships are live, what moved this month, and what is about to expire.

        ADM-CC-01's second metric and its RETENTION item. Behind the same permission as the
        membership list, because it is a count over the rows that list returns.
        """
        permit(session, "membership.record.read")
        return commercial.membership_summary(
            tenant_pool, tenant_id, as_of=as_of,
            expiring_within_days=expiring_within_days)

    @app.get("/memberships/{membership_id}")
    def get_membership(
        tenant_id: TenantId, session: Session, membership_id: str
    ) -> dict[str, Any]:
        """One membership with the agreement it was sold on, its terms and its history.

        The history's medical-hold reasons are masked here exactly as `membership_as_of`
        masks them, because a health fact is a health fact whatever read returns it.
        """
        permit(session, "membership.record.read")
        return commercial.get_membership(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"))


    # ------------------------------------------------------------ MOD-017, entitlements
    #
    # **`/member-entitlements`, not `/entitlements`.** That prefix is MOD-015's: a *plan*
    # entitlement is what a tenant's Veyro subscription allows. These are what a member may
    # do. The two are different things owed to different parties, and one prefix for both
    # would read as one surface.

    @app.get("/member-entitlements")
    def list_entitlement_grants(
        tenant_id: TenantId, session: Session, person_id: str | None = None,
        membership_id: str | None = None, status: str | None = None, limit: int = 50,
    ) -> dict[str, Any]:
        """What members may use, with each grant's remaining balance.

        The balance is summed without sweeping lapsed holds, because a sweep writes -- see
        `list_entitlement_grants`. A draw settles against the number taken under the grant's
        own lock, which is the only one that decides anything.
        """
        permit(session, "membership.entitlement.read")
        return commercial.list_entitlement_grants(
            tenant_pool, tenant_id,
            person_id=optional_uuid(person_id, "person_id"),
            membership_id=optional_uuid(membership_id, "membership_id"),
            status=status, limit=limit)

    @app.post("/member-entitlements/policies", status_code=201)
    def define_entitlement_policy(
        tenant_id: TenantId, session: Session, body: EntitlementPolicyBody
    ) -> dict[str, Any]:
        """Declare what one kind of entitlement means in this tenant. COM-01-R03."""
        permit(session, "membership.entitlement.grant", body.correlation_id)
        return commercial.define_entitlement_policy(
            tenant_pool, tenant_id, policy_key=body.policy_key,
            display_name=body.display_name, entitlement_type=body.entitlement_type,
            is_counted=body.is_counted,
            reservation_ttl_seconds=body.reservation_ttl_seconds,
            carryover_mode=body.carryover_mode, carryover_limit=body.carryover_limit,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/member-entitlements/grants", status_code=201)
    def grant_member_entitlement(
        tenant_id: TenantId, session: Session, body: GrantBody
    ) -> dict[str, Any]:
        """GrantEntitlement, with its opening ledger movement in the same transaction."""
        permit(session, "membership.entitlement.grant", body.correlation_id)
        return commercial.grant_entitlement(
            tenant_pool, tenant_id,
            person_id=require_uuid(body.person_id, "person_id"),
            policy_id=require_uuid(body.policy_id, "policy_id"),
            source_kind=body.source_kind, source_id=optional_uuid(
                body.source_id, "source_id"),
            membership_id=optional_uuid(body.membership_id, "membership_id"),
            quantity=body.quantity, valid_from=body.valid_from, valid_to=body.valid_to,
            brand_id=optional_uuid(body.brand_id, "brand_id"),
            location_id=optional_uuid(body.location_id, "location_id"),
            usable_from_minute=body.usable_from_minute,
            usable_to_minute=body.usable_to_minute, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/member-entitlements/reservations", status_code=201)
    def reserve_entitlement(
        tenant_id: TenantId, session: Session, body: ReserveBody
    ) -> dict[str, Any]:
        """ReserveEntitlement: hold quantity atomically, with an expiry. Paragraph 1506."""
        permit(session, "membership.entitlement.draw", body.correlation_id)
        return commercial.reserve_entitlement(
            tenant_pool, tenant_id,
            grant_id=require_uuid(body.grant_id, "grant_id"),
            purpose_kind=body.purpose_kind, quantity=body.quantity,
            purpose_ref=body.purpose_ref,
            location_id=optional_uuid(body.location_id, "location_id"),
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/member-entitlements/reservations/{reservation_id}/settle")
    def settle_reservation(
        tenant_id: TenantId, session: Session, reservation_id: str,
        body: SettleReservationBody
    ) -> dict[str, Any]:
        """ConsumeEntitlement or ReleaseEntitlement. A consumption moves nothing."""
        permit(session, "membership.entitlement.draw", body.correlation_id)
        return commercial.settle_reservation(
            tenant_pool, tenant_id, require_uuid(reservation_id, "reservation_id"),
            outcome=body.outcome, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/member-entitlements/grants/{grant_id}")
    def read_entitlement_balance(
        tenant_id: TenantId, session: Session, grant_id: str,
        correlation_id: str = Query(min_length=1),
    ) -> dict[str, Any]:
        """What is left on a grant, and how much of it is held.

        **This read takes a correlation id because it can write.** Sweeping lapsed holds
        inserts ledger rows and every row in that ledger names who caused it, so a sweep
        attributed to nobody would be the "evidence with nobody's name on it" shape reached by
        the side door of calling it a read.
        """
        permit(session, "membership.entitlement.read")
        return commercial.entitlement_balance(
            tenant_pool, tenant_id, require_uuid(grant_id, "grant_id"),
            actor_id=session["identity_id"],
            correlation_id=require_uuid(correlation_id, "correlation_id"))

    # ------------------------------------------------------------ MOD-017, COM-03

    @app.get("/finance/accounts")
    def list_billing_accounts(
        tenant_id: TenantId, session: Session, person_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Member billing accounts. `person_id` is who *pays*, which is not always who trains."""
        permit(session, "finance.account.read")
        return commercial.list_billing_accounts(
            tenant_pool, tenant_id,
            person_id=optional_uuid(person_id, "person_id"), limit=limit)

    @app.post("/finance/accounts", status_code=201)
    def create_billing_account(
        tenant_id: TenantId, session: Session, body: BillingAccountBody
    ) -> dict[str, Any]:
        """CreateBillingAccount. The account is who pays, not always who owes."""
        permit(session, "finance.account.write", body.correlation_id)
        return commercial.create_billing_account(
            tenant_pool, tenant_id,
            payer_person_id=require_uuid(body.payer_person_id, "payer_person_id"),
            account_number=body.account_number, currency=body.currency,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            account_kind=body.account_kind,
            payment_terms_days=body.payment_terms_days,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/fiscal-series", status_code=201)
    def open_fiscal_series(
        tenant_id: TenantId, session: Session, body: FiscalSeriesBody
    ) -> dict[str, Any]:
        """Open a numbering series for one legal entity. COM-03-R07."""
        permit(session, "finance.fiscal.manage", body.correlation_id)
        return commercial.open_fiscal_series(
            tenant_pool, tenant_id,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            series_code=body.series_code, document_kind=body.document_kind,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/invoices", status_code=201)
    def issue_member_invoice(
        tenant_id: TenantId, session: Session, body: IssueInvoiceBody
    ) -> dict[str, Any]:
        """IssueInvoice: the document, its lines, its serial and its tax, atomically."""
        permit(session, "finance.invoice.issue", body.correlation_id)
        return commercial.issue_invoice(
            tenant_pool, tenant_id,
            billing_account_id=require_uuid(
                body.billing_account_id, "billing_account_id"),
            series_id=require_uuid(body.series_id, "series_id"),
            lines=[{"description": line.description, "quantity": line.quantity,
                    "unit_net_minor": line.unit_net_minor,
                    "tax_rate_bp": line.tax_rate_bp,
                    "variant_id": optional_uuid(line.variant_id, "variant_id"),
                    "price_resolution_id": optional_uuid(
                        line.price_resolution_id, "price_resolution_id"),
                    "tax_category_id": optional_uuid(
                        line.tax_category_id, "tax_category_id")}
                   for line in body.lines],
            issued_on=body.issued_on, due_on=body.due_on,
            jurisdiction=body.jurisdiction,
            membership_id=optional_uuid(body.membership_id, "membership_id"),
            schedule_id=optional_uuid(body.schedule_id, "schedule_id"),
            credits_invoice_id=optional_uuid(
                body.credits_invoice_id, "credits_invoice_id"),
            unearned_minor=body.unearned_minor,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/finance/invoices")
    def list_invoices(
        tenant_id: TenantId, session: Session, billing_account_id: str | None = None,
        person_id: str | None = None, payment_status: str | None = None,
        fiscal_status: str | None = None, limit: int = 50,
    ) -> dict[str, Any]:
        """Issued documents with what has been paid against each. There is no draft state.

        **The two statuses filter separately**, because they move independently: ADM-CC-01's
        COMPLIANCE item is "three invoices were rejected by the tax authority", which is a
        question about filing and not about money.
        """
        permit(session, "finance.account.read")
        return commercial.list_invoices(
            tenant_pool, tenant_id,
            billing_account_id=optional_uuid(billing_account_id, "billing_account_id"),
            person_id=optional_uuid(person_id, "person_id"),
            payment_status=payment_status, fiscal_status=fiscal_status, limit=limit)

    @app.get("/finance/invoices/{invoice_id}")
    def read_invoice(
        tenant_id: TenantId, session: Session, invoice_id: str
    ) -> dict[str, Any]:
        """One invoice with its lines and **both** statuses. Paragraph 1607."""
        permit(session, "finance.account.read")
        return commercial.get_invoice(
            tenant_pool, tenant_id, require_uuid(invoice_id, "invoice_id"))

    @app.get("/finance/invoices/{invoice_id}/history")
    def read_invoice_history(
        tenant_id: TenantId, session: Session, invoice_id: str
    ) -> dict[str, Any]:
        """What has happened to one invoice, in order -- ADM-PAY-03's middle section.

        Composed from the insert-only tables rather than from the invoice's status, which is
        a cache of what they add up to. A timeline built from the cache says what is true now
        and nothing about how it got there, which is the opposite of what the screen is for.
        """
        permit(session, "finance.account.read")
        return commercial.invoice_history(
            tenant_pool, tenant_id, require_uuid(invoice_id, "invoice_id"))

    @app.post("/finance/payment-intents", status_code=201)
    def create_payment_intent(
        tenant_id: TenantId, session: Session, body: PaymentIntentBody
    ) -> dict[str, Any]:
        """CreatePaymentIntent: what a provider is about to be asked to do.

        **Nothing here talks to a provider.** Taking money is owner-reserved, so what is built
        is the half that must be correct whatever the provider turns out to be.
        """
        permit(session, "finance.payment.take", body.correlation_id)
        return commercial.create_payment_intent(
            tenant_pool, tenant_id,
            billing_account_id=require_uuid(
                body.billing_account_id, "billing_account_id"),
            amount_minor=body.amount_minor, method=body.method,
            provider_key=body.provider_key,
            invoice_id=optional_uuid(body.invoice_id, "invoice_id"),
            payment_method_ref=body.payment_method_ref,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/payment-intents/{intent_id}/settle")
    def settle_payment_intent(
        tenant_id: TenantId, session: Session, intent_id: str, body: SettleIntentBody
    ) -> dict[str, Any]:
        """ApplyPayment or RecordPaymentFailure. `unknown` settles nothing."""
        permit(session, "finance.payment.take", body.correlation_id)
        return commercial.settle_payment_intent(
            tenant_pool, tenant_id, require_uuid(intent_id, "intent_id"),
            outcome=body.outcome, provider_ref=body.provider_ref,
            failure_code=body.failure_code, failure_detail=body.failure_detail,
            cash_account_id=optional_uuid(body.cash_account_id, "cash_account_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/payment-intents/{intent_id}/reconcile")
    def reconcile_intent(
        tenant_id: TenantId, session: Session, intent_id: str, body: ReconcileBody
    ) -> dict[str, Any]:
        """COM-03-R06. A provider answer that contradicts a settled record is escalated."""
        permit(session, "finance.payment.reconcile", body.correlation_id)
        return commercial.reconcile_intent(
            tenant_pool, tenant_id, require_uuid(intent_id, "intent_id"),
            provider_status=body.provider_status, provider_ref=body.provider_ref,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/refund-requests", status_code=201)
    def request_refund(
        tenant_id: TenantId, session: Session, body: RefundRequestBody
    ) -> dict[str, Any]:
        """Ask for a refund. The requester is this session, not a field in the body."""
        permit(session, "finance.refund.request", body.correlation_id)
        return commercial.request_refund(
            tenant_pool, tenant_id,
            payment_id=require_uuid(body.payment_id, "payment_id"),
            amount_minor=body.amount_minor, reason=body.reason,
            requester_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/refunds", status_code=201)
    def approve_refund(
        tenant_id: TenantId, session: Session, body: ApproveRefundBody
    ) -> dict[str, Any]:
        """RefundPayment: decide a recorded request. Paragraph 1598's approval."""
        permit(session, "finance.refund.approve", body.correlation_id)
        return commercial.approve_refund(
            tenant_pool, tenant_id,
            request_id=require_uuid(body.request_id, "request_id"),
            approval_reason=body.approval_reason,
            acknowledged_amount_minor=body.acknowledged_amount_minor,
            idempotency_key=body.idempotency_key,
            approver_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/refunds/{refund_id}/settle")
    def settle_refund(
        tenant_id: TenantId, session: Session, refund_id: str, body: SettleRefundBody
    ) -> dict[str, Any]:
        """What the provider says became of a refund."""
        # **The refund permission, not the payment one.** `finance.payment.take` is for money
        # coming in; this settles money going out, and the permission that exists for exactly
        # that act is the one the refund approval is gated on. A role holding only "take
        # payments" could mark a refund succeeded, which is the last state anybody checks.
        permit(session, "finance.refund.approve", body.correlation_id)
        return commercial.settle_refund(
            tenant_pool, tenant_id, require_uuid(refund_id, "refund_id"),
            outcome=body.outcome, provider_ref=body.provider_ref,
            failure_code=body.failure_code,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    # ------------------------------------------------- ADM-CC-01's figures and its queue
    #
    # **Aggregates, because the lists are bounded.** `list_invoices` and `list_memberships`
    # stop at 200 rows, so a surface that summed one would report the first page as the
    # month. A balance with two definitions has two answers the day either moves, which is
    # the finding MOD-018's till close shipped and `list_entitlement_grants` records.

    @app.get("/finance/payments")
    def read_payments_ledger(
        tenant_id: TenantId, session: Session, since: date | None = None,
        until: date | None = None, needs_action: bool = False, limit: int = 100,
    ) -> dict[str, Any]:
        """ADM-PAY-01: money in, money out and money contested, on one axis.

        A refund is a negative amount on the same axis as a payment, never a payment of a
        different colour -- the canvas's own rule, and the reason the four tables are unioned
        rather than returned as four lists.
        """
        permit(session, "finance.payment.read")
        return commercial.payments_ledger(
            tenant_pool, tenant_id, since=since, until=until,
            needs_action_only=needs_action, limit=limit)

    @app.get("/finance/collections")
    def read_collections(
        tenant_id: TenantId, session: Session, as_of: date | None = None,
        weeks: int = 12, week_start: int = 5,
    ) -> dict[str, Any]:
        """Collected this month against the same point last month, per currency.

        ADM-CC-01's first metric and its twelve-week chart. `week_start` is a market token --
        the component source says "Week starts Saturday -- a market setting, not a default" --
        and no MOD-005 configuration key declares it yet, so the caller passes it.
        """
        permit(session, "finance.revenue.read")
        return commercial.collections_summary(
            tenant_pool, tenant_id, as_of=as_of, weeks=weeks, week_start=week_start)

    @app.get("/reports/revenue")
    def read_revenue_report(
        tenant_id: TenantId, session: Session, as_of: date | None = None,
    ) -> dict[str, Any]:
        """ADM-RPT-02: collected, invoiced, outstanding and refunded, and what earned it.

        Four figures rather than one labelled "revenue", which the canvas gives its own
        reason for: "A report showing one number labelled revenue is the reason operators
        cannot reconcile their own books."

        Gated on `finance.revenue.read`, the same permission as `/finance/collections`: this
        is the same money read at a different grain, and a second permission for it would be
        a role that can see the month's total but not what made it up.
        """
        permit(session, "finance.revenue.read")
        return commercial.revenue_report(tenant_pool, tenant_id, as_of=as_of)

    @app.get("/reports/attendance")
    def read_attendance_report(
        tenant_id: TenantId, session: Session, location_id: str,
        weekday: Annotated[list[int], Query()],
        zone_id: str | None = None, weeks: int = 4, until: date | None = None,
    ) -> dict[str, Any]:
        """ADM-RPT-04: entries per local hour at one club, and the actionable hour in words.

        **`weekday` is required and repeated, because a weekend is jurisdictional.** The
        canvas scopes its chart to "WEEKDAYS", which is Monday to Friday in one market and
        Sunday to Thursday in the one this product is built for, and nothing in this build
        declares which. MOD-009's `response_days` and MOD-015's tax rate are the precedent:
        a defaulted value would be the server picking a market convention and then labelling
        a chart with it. The values are 0 (Monday) to 6 (Sunday), which is MOD-019's rota
        convention rather than a second one.

        Behind `access.zone.read`, like `/access/visits`, `/access/entries` and a zone's
        occupancy: all four are figures derived from the event ledger with nobody named in
        them, and a reports-only permission beside them would be a role that may see the
        day's total but not the hours it is made of.
        """
        permit(session, "access.zone.read")
        return access.visits_by_hour(
            tenant_pool, tenant_id,
            location_id=require_uuid(location_id, "location_id"),
            zone_id=None if zone_id is None else require_uuid(zone_id, "zone_id"),
            weekdays=weekday, weeks=weeks, until=until)

    @app.get("/finance/dunning-cases")
    def read_dunning_cases(
        tenant_id: TenantId, session: Session, status: str = "open", limit: int = 50,
    ) -> dict[str, Any]:
        """The recovery journeys, with what each is chasing and how far it has got.

        The module's last writer with no reader: a case could be opened and advanced and
        there was no way to see one.
        """
        permit(session, "finance.dunning.read")
        return commercial.list_dunning_cases(
            tenant_pool, tenant_id, status=status, limit=limit)

    @app.get("/finance/recovery")
    def read_recovery_workspace(
        tenant_id: TenantId, session: Session, limit: int = 50,
    ) -> dict[str, Any]:
        """ADM-PAY-05: the failed payments as one decision, sorted by what each one wants.

        `finance.dunning.read`, the same permission as the listing beside it, because this is
        the same rows with the failure that opened each one and the standing of the membership
        its invoice cites. Nothing here sends anything and the response says so.
        """
        permit(session, "finance.dunning.read")
        return commercial.recovery_workspace(tenant_pool, tenant_id, limit=limit)

    @app.post("/finance/dunning-cases", status_code=201)
    def start_dunning(
        tenant_id: TenantId, session: Session, body: DunningBody
    ) -> dict[str, Any]:
        """StartDunning. COM-03-R04. The access recommendation is recorded, not applied."""
        permit(session, "finance.dunning.manage", body.correlation_id)
        return commercial.start_dunning(
            tenant_pool, tenant_id,
            invoice_id=require_uuid(body.invoice_id, "invoice_id"),
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/dunning-cases/{case_id}/advance")
    def advance_dunning(
        tenant_id: TenantId, session: Session, case_id: str, body: AdvanceDunningBody
    ) -> dict[str, Any]:
        """Move a case on, or close it as recovered when the invoice has been paid."""
        permit(session, "finance.dunning.manage", body.correlation_id)
        return commercial.advance_dunning(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            notification_ref=body.notification_ref,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/finance/disputes")
    def read_disputes(
        tenant_id: TenantId, session: Session, status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """ADM-PAY-10: the chargebacks, with how long is left to answer each one.

        The module's last writer with no reader: three routes could record, answer and
        settle a dispute and nothing could list one, so a chargeback existed only for
        whoever had just written it.

        **`finance.dispute.read` is routine, and that is MOD-018's rule applied here**: a
        read behind a step-up is a read nobody does until the month-end panic, and a
        chargeback is worse than a wrong balance because the response window expires. The
        writes beside it stay financial.
        """
        permit(session, "finance.dispute.read")
        return commercial.list_disputes(
            tenant_pool, tenant_id, status=status, limit=limit)

    @app.post("/finance/disputes", status_code=201)
    def record_dispute(
        tenant_id: TenantId, session: Session, body: DisputeBody
    ) -> dict[str, Any]:
        """A card dispute the scheme has opened. COM-03-R06.

        **Recorded, not performed**, like every other provider-facing state in this module:
        there is nothing here that speaks to a scheme, so the row is a named actor's
        statement that a case exists, with the scheme's own reference on it. The amount, the
        currency and the billing account are all checked against the payment rather than
        taken from the body.
        """
        permit(session, "finance.dispute.manage", body.correlation_id)
        return commercial.record_dispute(
            tenant_pool, tenant_id,
            payment_id=require_uuid(body.payment_id, "payment_id"),
            provider_case_ref=body.provider_case_ref, dispute_kind=body.dispute_kind,
            reason_code=body.reason_code, amount_minor=body.amount_minor,
            currency=body.currency, opened_on=body.opened_on,
            respond_due_on=body.respond_due_on,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/disputes/{dispute_id}/respond")
    def respond_to_dispute(
        tenant_id: TenantId, session: Session, dispute_id: str, body: DisputeResponseBody
    ) -> dict[str, Any]:
        """Evidence has been sent to the scheme.

        A response after the deadline is recorded rather than refused -- "we answered late"
        is the fact a later argument turns on -- and `window_has_closed` comes back so
        nothing can read it as timely.
        """
        permit(session, "finance.dispute.manage", body.correlation_id)
        return commercial.respond_to_dispute(
            tenant_pool, tenant_id, require_uuid(dispute_id, "dispute_id"),
            response_ref=body.response_ref,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/disputes/{dispute_id}/settle")
    def settle_dispute(
        tenant_id: TenantId, session: Session, dispute_id: str, body: DisputeOutcomeBody
    ) -> dict[str, Any]:
        """The scheme's decision. `lost` is money gone and this module does not move it."""
        permit(session, "finance.dispute.manage", body.correlation_id)
        return commercial.settle_dispute(
            tenant_pool, tenant_id, require_uuid(dispute_id, "dispute_id"),
            outcome=body.outcome,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/finance/invoices/{invoice_id}/fiscalize")
    def fiscalize_invoice(
        tenant_id: TenantId, session: Session, invoice_id: str, body: FiscalizeBody
    ) -> dict[str, Any]:
        """Move the fiscal state. `fiscal_complete` needs the authority's acknowledgement."""
        permit(session, "finance.fiscal.manage", body.correlation_id)
        return commercial.fiscalize_invoice(
            tenant_pool, tenant_id, require_uuid(invoice_id, "invoice_id"),
            target=body.target, ack_ref=body.ack_ref,
            exemption_reason=body.exemption_reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/member-entitlements/grants/{grant_id}/revoke")
    def revoke_member_entitlement(
        tenant_id: TenantId, session: Session, grant_id: str,
        body: RevokeEntitlementBody,
    ) -> dict[str, Any]:
        """RevokeEntitlement: stop a grant being drawable and write off what was left."""
        permit(session, "membership.entitlement.grant", body.correlation_id)
        return commercial.revoke_entitlement(
            tenant_pool, tenant_id, require_uuid(grant_id, "grant_id"),
            reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/finance/payments/{payment_id}/refunds")
    def refunds_of_payment(
        tenant_id: TenantId, session: Session, payment_id: str
    ) -> dict[str, Any]:
        """Every refund request and decision against one payment, and what is refundable.

        **The read the approval needs.** There was no way to read a refund at all: four
        commands wrote one and nothing returned one, so the second person in the separation
        of duties approved a figure they could not see.
        """
        permit(session, "finance.account.read")
        return commercial.refunds_of_payment(
            tenant_pool, tenant_id, require_uuid(payment_id, "payment_id"))


    # ------------------------------------------------------------ MOD-018, COM-04

    @app.post("/ledger/accounts", status_code=201)
    def open_ledger_account(
        tenant_id: TenantId, session: Session, body: LedgerAccountBody
    ) -> dict[str, Any]:
        """One account in the tenant's chart. The kinds are in code; the accounts are rows."""
        permit(session, "finance.ledger.chart", body.correlation_id)
        return ledger.open_account(
            tenant_pool, tenant_id, account_code=body.account_code,
            account_kind=body.account_kind, display_name=body.display_name,
            currency=body.currency,
            brand_id=optional_uuid(body.brand_id, "brand_id"),
            location_id=optional_uuid(body.location_id, "location_id"),
            legal_entity_id=optional_uuid(body.legal_entity_id, "legal_entity_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/accounts/{account_id}/retire")
    def retire_ledger_account(
        tenant_id: TenantId, session: Session, account_id: str,
        body: CommercialActionBody,
    ) -> dict[str, Any]:
        """Stop an account being posted to. Its postings stay exactly where they are."""
        permit(session, "finance.ledger.chart", body.correlation_id)
        return ledger.retire_account(
            tenant_pool, tenant_id, require_uuid(account_id, "account_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/ledger/accounts/{account_id}/balance")
    def ledger_account_balance(
        tenant_id: TenantId, session: Session, account_id: str,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """One account's balance, summed from the postings. Never a stored total."""
        permit(session, "finance.ledger.read")
        return ledger.account_balance(
            tenant_pool, tenant_id, require_uuid(account_id, "account_id"), as_of=as_of)

    @app.get("/ledger/accounts")
    def list_ledger_accounts(
        tenant_id: TenantId, session: Session, legal_entity_id: str | None = None,
        status: str | None = None, limit: int = 200,
    ) -> dict[str, Any]:
        """The chart of accounts, by code.

        **There is deliberately no journal listing beside this.** `finance.ledger.read` is a
        narrow lateral read around `finance.invoice.read` -- `get_journal` returns an
        invoice's figures and the payer's `person_id` -- and it stays a gap rather than a
        defect only because journal ids are not enumerable from any route this permission
        reaches. A listing would make it MOD-010's `events.event.read` finding.
        """
        permit(session, "finance.ledger.read")
        return ledger.list_accounts(
            tenant_pool, tenant_id,
            legal_entity_id=optional_uuid(legal_entity_id, "legal_entity_id"),
            status=status, limit=limit)

    @app.get("/ledger/periods")
    def list_ledger_periods(
        tenant_id: TenantId, session: Session, legal_entity_id: str | None = None,
        status: str | None = None, limit: int = 50,
    ) -> dict[str, Any]:
        """COM-04-R06's lock, made observable. A month with no row has never been opened."""
        permit(session, "finance.ledger.read")
        return ledger.list_periods(
            tenant_pool, tenant_id,
            legal_entity_id=optional_uuid(legal_entity_id, "legal_entity_id"),
            status=status, limit=limit)

    @app.get("/ledger/trial-balance")
    def ledger_trial_balance(
        tenant_id: TenantId, session: Session, legal_entity_id: str,
        currency: Annotated[str, Query(min_length=3, max_length=3)],
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """Every balance, and the proof that the ledger balances. COM-04-R07.

        **Scoped to the entity and the date.** Both predicates once sat in a `LEFT JOIN`'s
        `ON` clause, where a posting whose journal matched neither survived the join and was
        summed anyway -- so this read, which is what a close is signed off against, moved
        whenever a later month was posted.
        """
        permit(session, "finance.ledger.read")
        return ledger.trial_balance(
            tenant_pool, tenant_id,
            legal_entity_id=require_uuid(legal_entity_id, "legal_entity_id"),
            currency=currency, as_of=as_of)

    @app.post("/ledger/journals", status_code=201)
    def post_ledger_journal(
        tenant_id: TenantId, session: Session, body: PostJournalBody
    ) -> dict[str, Any]:
        """PostJournal: a balanced, insert-only movement. Paragraph 1685.

        **A closing entry is charged to the close's own permission.** `purpose: "close"` is
        what gets a journal into a period that has stopped admitting trade, so it costs
        `finance.period.close` rather than `finance.ledger.post` -- the same remedy MOD-009
        applied to `consent_subject` and MOD-013 to a critical notification, for the same
        reason: a body field that buys an authority is a permission, so charge one.
        """
        permit(session,
               "finance.period.close" if body.purpose == "close"
               else "finance.ledger.post",
               body.correlation_id)
        return ledger.post_journal_in_its_own_transaction(
            tenant_pool, tenant_id,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            lines=[{"account_id": require_uuid(line.account_id, "account_id"),
                    "amount_minor": line.amount_minor,
                    "subject_person_id": optional_uuid(
                        line.subject_person_id, "subject_person_id"),
                    "memo": line.memo}
                   for line in body.lines],
            posted_on=body.posted_on, currency=body.currency, purpose=body.purpose,
            source_kind=body.source_kind, source_ref=body.source_ref,
            description=body.description, idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/ledger/journals/{journal_id}")
    def get_ledger_journal(
        tenant_id: TenantId, session: Session, journal_id: str
    ) -> dict[str, Any]:
        """One journal with its postings, which is how a balance is explained."""
        permit(session, "finance.ledger.read")
        return ledger.get_journal(
            tenant_pool, tenant_id, require_uuid(journal_id, "journal_id"))

    @app.post("/ledger/journals/{journal_id}/correct", status_code=201)
    def correct_ledger_journal(
        tenant_id: TenantId, session: Session, journal_id: str,
        body: CorrectJournalBody,
    ) -> dict[str, Any]:
        """Reverse a posted journal with a compensating entry, dated in the open period."""
        permit(session, "finance.ledger.correct", body.correlation_id)
        return ledger.correct_journal(
            tenant_pool, tenant_id, require_uuid(journal_id, "journal_id"),
            reason=body.reason, posted_on=body.posted_on,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/wallet-credits", status_code=201)
    def credit_member_wallet(
        tenant_id: TenantId, session: Session, body: WalletCreditBody
    ) -> dict[str, Any]:
        """CreditWallet. The liability account comes from the value kind, not from the body."""
        permit(session, "finance.wallet.credit", body.correlation_id)
        return ledger.credit_wallet(
            tenant_pool, tenant_id,
            person_id=require_uuid(body.person_id, "person_id"),
            value_kind=body.value_kind, amount_minor=body.amount_minor,
            currency=body.currency,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            counterpart_account_id=require_uuid(
                body.counterpart_account_id, "counterpart_account_id"),
            source_kind=body.source_kind, source_ref=body.source_ref,
            reason=body.reason, expires_on=body.expires_on,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/wallet-debits", status_code=201)
    def debit_member_wallet(
        tenant_id: TenantId, session: Session, body: WalletDebitBody
    ) -> dict[str, Any]:
        """DebitWallet. The spend order decides which value goes, not the caller."""
        permit(session, "finance.wallet.debit", body.correlation_id)
        return ledger.debit_wallet(
            tenant_pool, tenant_id,
            person_id=require_uuid(body.person_id, "person_id"),
            amount_minor=body.amount_minor, currency=body.currency,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            counterpart_account_id=require_uuid(
                body.counterpart_account_id, "counterpart_account_id"),
            reason=body.reason, source_kind=body.source_kind,
            source_ref=body.source_ref, idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/ledger/wallets/{person_id}")
    def get_member_wallet(
        tenant_id: TenantId, session: Session, person_id: str,
        currency: Annotated[str, Query(min_length=3, max_length=3)],
        as_of: date | None = None,
    ) -> dict[str, Any]:
        """A wallet statement, reconstructed from the entries. COM-04-R07.

        **The lines carry the reason each movement was made**, which is a tenant's own prose,
        to a routine tenant-wide reader -- the same disclosure MOD-013 records for
        `privacy.consent.read`, and the place `Decision.mask` would apply if a read path here
        asked the gate for one. It does not; that is a declared gap rather than an oversight.
        """
        permit(session, "finance.wallet.read")
        return ledger.wallet_statement(
            tenant_pool, tenant_id,
            person_id=require_uuid(person_id, "person_id"), currency=currency,
            at=as_of)

    @app.get("/ledger/wallets/{person_id}/statements")
    def get_member_wallets(
        tenant_id: TenantId, session: Session, person_id: str, as_of: date | None = None,
    ) -> dict[str, Any]:
        """Every wallet one person holds — ADM-PAY-07.

        The read beside this one takes a currency, which a till settling a sale has and a
        member's record does not: `led_wallets` is one row per (person, currency) and nothing
        told the screen which rows exist. A page that guessed at one would silently omit the
        rest. Same permission, because it is the same data at a different grain.
        """
        permit(session, "finance.wallet.read")
        return ledger.person_wallets(
            tenant_pool, tenant_id,
            person_id=require_uuid(person_id, "person_id"), at=as_of)

    @app.post("/ledger/recognition-schedules", status_code=201)
    def open_recognition_schedule(
        tenant_id: TenantId, session: Session, body: RecognitionScheduleBody
    ) -> dict[str, Any]:
        """Declare how a sale earns. Paragraph 1695: prepaid cash is not day-one revenue."""
        permit(session, "finance.recognition.manage", body.correlation_id)
        return ledger.open_recognition_schedule(
            tenant_pool, tenant_id,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            source_kind=body.source_kind, source_ref=body.source_ref,
            basis=body.basis, total_minor=body.total_minor, currency=body.currency,
            unearned_account_id=require_uuid(
                body.unearned_account_id, "unearned_account_id"),
            revenue_account_id=require_uuid(
                body.revenue_account_id, "revenue_account_id"),
            subject_person_id=optional_uuid(
                body.subject_person_id, "subject_person_id"),
            starts_on=body.starts_on, ends_on=body.ends_on,
            units_total=body.units_total,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/recognition-schedules/{schedule_id}/post")
    def post_revenue_recognition(
        tenant_id: TenantId, session: Session, schedule_id: str,
        body: PostRecognitionBody,
    ) -> dict[str, Any]:
        """PostRevenueRecognition. Cumulative, so running it twice posts once."""
        permit(session, "finance.recognition.manage", body.correlation_id)
        return ledger.post_recognition(
            tenant_pool, tenant_id, require_uuid(schedule_id, "schedule_id"),
            units_delivered=body.units_delivered, at=body.as_of,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/ledger/recognition-due")
    def recognition_due(
        tenant_id: TenantId, session: Session, as_of: date | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Which live schedules have something to recognise. For the sweep nothing runs."""
        permit(session, "finance.ledger.read")
        return ledger.recognition_due(tenant_pool, tenant_id, at=as_of, limit=limit)

    @app.post("/ledger/settlements", status_code=201)
    def import_settlement(
        tenant_id: TenantId, session: Session, body: ImportSettlementBody
    ) -> dict[str, Any]:
        """ImportSettlement. COM-04-R04: the file, the verdicts and the cases, together."""
        permit(session, "finance.settlement.import", body.correlation_id)
        return ledger.import_settlement(
            tenant_pool, tenant_id,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            provider_key=body.provider_key,
            provider_batch_ref=body.provider_batch_ref,
            settled_on=body.settled_on, currency=body.currency,
            claimed_total_minor=body.claimed_total_minor,
            lines=[{"line_kind": line.line_kind, "provider_ref": line.provider_ref,
                    "amount_minor": line.amount_minor,
                    "currency": line.currency or body.currency}
                   for line in body.lines],
            document_ref=body.document_ref, idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/ledger/reconciliation-cases")
    def open_reconciliation_cases(
        tenant_id: TenantId, session: Session, legal_entity_id: str | None = None,
        as_of: date | None = None, limit: int = 200,
    ) -> dict[str, Any]:
        """Every unanswered question, with how long it has been open."""
        permit(session, "finance.ledger.read")
        return ledger.open_cases(
            tenant_pool, tenant_id,
            legal_entity_id=optional_uuid(legal_entity_id, "legal_entity_id"),
            at=as_of, limit=limit)

    @app.post("/ledger/reconciliation-cases/{case_id}/resolve")
    def resolve_reconciliation_case(
        tenant_id: TenantId, session: Session, case_id: str, body: ResolveCaseBody
    ) -> dict[str, Any]:
        """Work a case. `written_off` is a decision about money and says so in the status."""
        permit(session, "finance.reconciliation.manage", body.correlation_id)
        return ledger.resolve_case(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            outcome=body.outcome, resolution=body.resolution,
            resolution_journal_id=optional_uuid(
                body.resolution_journal_id, "resolution_journal_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/ledger/cash-sessions")
    def list_cash_sessions(
        tenant_id: TenantId, session: Session, status: str | None = None,
        location_id: str | None = None, limit: int = 50,
    ) -> dict[str, Any]:
        """The drawers. COM-04-R05, and ADM-PAY-09 cannot be drawn without it.

        **`open_cash_session` and `close_cash_session` had no reader at all**, so a drawer
        could be opened and the only way to learn what was in it was to close it and read the
        refusal -- the sixth instance of this build's "a writer with no reader" shape.

        **Behind `finance.cash.session`, which is the drawer permission and is routine.**
        The catalogue leaves it routine because a front desk opens a drawer every shift, and
        whoever may close one may certainly see it; what bounds that permission is the
        suspense posting and the case, not the reading. An accountant holding only
        `finance.ledger.read` does not get this list and does not need it -- the drawer's
        balance is a line on the trial balance that permission already returns.

        A status outside the domain is refused rather than returning nothing, because
        "status=opne" and "no drawer is open" are different answers and a list that renders
        both as empty is a list nobody can trust.
        """
        permit(session, "finance.cash.session")
        if status is not None and status not in ("open", "closed"):
            raise InvalidRequest("a_cash_session_status_is_open_or_closed")
        return ledger.list_cash_sessions(
            tenant_pool, tenant_id, status=status,
            location_id=optional_uuid(location_id, "location_id"), limit=limit)

    @app.get("/ledger/drawers")
    def list_drawers(
        tenant_id: TenantId, session: Session, location_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """The tills at one site and what is standing in each. FD-07's own read.

        **The expected figure comes back for a drawer nobody has opened yet**, which is the
        whole point: the canvas shows the previous shift's own figure -- "Kareem left JOD
        50.00 at 16:04" -- before a count is entered, and it is derived from that account's
        postings rather than from any number a caller sent.
        """
        permit(session, "finance.cash.session")
        return ledger.list_drawers(
            tenant_pool, tenant_id,
            location_id=require_uuid(location_id, "location_id"), limit=limit,
        )

    @app.post("/ledger/cash-sessions", status_code=201)
    def open_cash_session(
        tenant_id: TenantId, session: Session, body: CashSessionBody
    ) -> dict[str, Any]:
        """Open a till. One open session per drawer. COM-04-R05."""
        permit(session, "finance.cash.session", body.correlation_id)
        return ledger.open_cash_session(
            tenant_pool, tenant_id,
            location_id=require_uuid(body.location_id, "location_id"),
            cash_account_id=require_uuid(body.cash_account_id, "cash_account_id"),
            drawer_label=body.drawer_label, currency=body.currency,
            opening_float_minor=body.opening_float_minor,
            float_source_account_id=optional_uuid(
                body.float_source_account_id, "float_source_account_id"),
            legal_entity_id=optional_uuid(body.legal_entity_id, "legal_entity_id"),
            suspense_account_id=optional_uuid(
                body.suspense_account_id, "suspense_account_id"),
            handover_reason=body.handover_reason,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/cash-sessions/{session_id}/close")
    def close_cash_session(
        tenant_id: TenantId, session: Session, session_id: str,
        body: CloseCashSessionBody,
    ) -> dict[str, Any]:
        """Count a till and close it. An unexplained variance refuses the close."""
        permit(session, "finance.cash.session", body.correlation_id)
        return ledger.close_cash_session(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            counted_minor=body.counted_minor,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            suspense_account_id=require_uuid(
                body.suspense_account_id, "suspense_account_id"),
            variance_reason=body.variance_reason,
            handover_note=body.handover_note,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/deposits", status_code=201)
    def create_deposit(
        tenant_id: TenantId, session: Session, body: DepositBody
    ) -> dict[str, Any]:
        """Bank a bag of cash. Posted on the way out, reconciled when the bank answers."""
        permit(session, "finance.cash.deposit", body.correlation_id)
        return ledger.create_deposit(
            tenant_pool, tenant_id,
            location_id=require_uuid(body.location_id, "location_id"),
            cash_account_id=require_uuid(body.cash_account_id, "cash_account_id"),
            bank_account_id=require_uuid(body.bank_account_id, "bank_account_id"),
            currency=body.currency, declared_minor=body.declared_minor,
            retained_minor=body.retained_minor,
            deposited_on=body.deposited_on,
            session_ids=[require_uuid(s, "session_id") for s in body.session_ids],
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/deposits/{deposit_id}/confirm")
    def confirm_deposit(
        tenant_id: TenantId, session: Session, deposit_id: str,
        body: ConfirmDepositBody,
    ) -> dict[str, Any]:
        """What the bank credited. A different figure makes the deposit `short`."""
        permit(session, "finance.cash.deposit", body.correlation_id)
        return ledger.confirm_deposit(
            tenant_pool, tenant_id, require_uuid(deposit_id, "deposit_id"),
            credited_minor=body.credited_minor, credited_on=body.credited_on,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            suspense_account_id=require_uuid(
                body.suspense_account_id, "suspense_account_id"),
            bank_reference=body.bank_reference,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/periods/close")
    def close_financial_period(
        tenant_id: TenantId, session: Session, body: PeriodBody
    ) -> dict[str, Any]:
        """Close a period, or begin closing it. COM-04-R06's lock control."""
        permit(session, "finance.period.close", body.correlation_id)
        return ledger.close_period(
            tenant_pool, tenant_id,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            period_key=body.period_key, target=body.target,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/periods/reopen")
    def reopen_financial_period(
        tenant_id: TenantId, session: Session, body: ReopenPeriodBody
    ) -> dict[str, Any]:
        """Reopen a closed period, with a reason that goes on the row."""
        permit(session, "finance.period.reopen", body.correlation_id)
        return ledger.reopen_period(
            tenant_pool, tenant_id,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            period_key=body.period_key, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/ledger/exports", status_code=201)
    def export_financial_period(
        tenant_id: TenantId, session: Session, body: ExportPeriodBody
    ) -> dict[str, Any]:
        """Record that a closed period reached an accounting system, and with what totals."""
        permit(session, "finance.export.run", body.correlation_id)
        return ledger.export_period(
            tenant_pool, tenant_id,
            legal_entity_id=require_uuid(body.legal_entity_id, "legal_entity_id"),
            period_key=body.period_key, target_system=body.target_system,
            target_ref=body.target_ref, currency=body.currency,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    # ------------------------------------------------------------- MOD-019 scheduling
    #
    # **Every route asks the gate, and four of them charge a different permission depending on
    # what the body says.** `override_reason` on a generation or a substitution buys the right
    # to publish over a conflict, which paragraph 1842 makes a Critical Control; and
    # `acknowledged_impact` on a publish buys the right to move or cancel a session somebody has
    # booked, which is paragraph 1841's. Neither is free. That is the remedy MOD-009 applied to
    # `consent_subject` and MOD-013 to a critical notification: a body field that buys an
    # authority is a permission, so charge one.
    #
    # The count in this comment was three and two routes did it -- which is the kind of claim
    # `CLAUDE.md` records as a finding in its own right, so it is checked by
    # `test_gating.py` rather than asserted here.

    @app.post("/scheduling/resources", status_code=201)
    def create_scheduling_resource(
        tenant_id: TenantId, session: Session, body: SchedulingResourceBody
    ) -> dict[str, Any]:
        """CreateResource. OPS-01-R01."""
        permit(session, "scheduling.resource.write", body.correlation_id)
        return scheduling.create_resource(
            tenant_pool, tenant_id, resource_code=body.resource_code,
            resource_kind=body.resource_kind, display_name=body.display_name,
            quantity=body.quantity,
            location_id=optional_uuid(body.location_id, "location_id"),
            person_id=optional_uuid(body.person_id, "person_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/scheduling/resources")
    def list_scheduling_resources(
        tenant_id: TenantId, session: Session, kind: str | None = None,
        location_id: str | None = None, include_retired: bool = False,
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    ) -> dict[str, Any]:
        """The resource list."""
        permit(session, "scheduling.schedule.read")
        return scheduling.list_resources(
            tenant_pool, tenant_id, kind=kind,
            location_id=optional_uuid(location_id, "location_id"),
            include_retired=include_retired, limit=limit)

    @app.post("/scheduling/resources/{resource_id}/retire")
    def retire_scheduling_resource(
        tenant_id: TenantId, session: Session, resource_id: str, body: CommercialActionBody
    ) -> dict[str, Any]:
        """Withdraw a resource. The sessions that hold it are listed, not cancelled."""
        permit(session, "scheduling.resource.write", body.correlation_id)
        return scheduling.retire_resource(
            tenant_pool, tenant_id, require_uuid(resource_id, "resource_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/scheduling/availability", status_code=201)
    def set_scheduling_availability(
        tenant_id: TenantId, session: Session, body: AvailabilityBody
    ) -> dict[str, Any]:
        """SetAvailability. OPS-01-R03."""
        permit(session, "scheduling.availability.write", body.correlation_id)
        try:
            starts = clock_time.fromisoformat(body.starts_at)
            ends = clock_time.fromisoformat(body.ends_at)
        except ValueError:
            raise InvalidRequest("a_window_time_is_hh_mm") from None
        return scheduling.set_availability(
            tenant_pool, tenant_id,
            resource_id=require_uuid(body.resource_id, "resource_id"),
            window_kind=body.window_kind, starts_at=starts, ends_at=ends,
            weekday=body.weekday, on_date=body.on_date, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/scheduling/availability/{window_id}/withdraw")
    def withdraw_scheduling_availability(
        tenant_id: TenantId, session: Session, window_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        """Take back a rota window. OPS-01-R03.

        **The remedy ADM-SCH-04's write form needs**, and it did not exist: the table carried
        `GRANT SELECT, INSERT` and nothing else, so a day off entered on the wrong date was
        permanent. A routine, AAL-1 permission whose every act is uncorrectable is MOD-013's
        "an irreversible act must not be declarable on a routine permission" from the other
        side.

        The same permission that writes a window, because correcting your own typo is the
        same job as making it and a step-up between the two would make the rota wrong rather
        than safe -- which is the catalogue's own argument for `scheduling.availability.write`
        being routine at all.
        """
        permit(session, "scheduling.availability.write", body.correlation_id)
        return scheduling.withdraw_availability_window(
            tenant_pool, tenant_id, window_id=require_uuid(window_id, "window_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/scheduling/availability")
    def read_resource_availability(
        tenant_id: TenantId, session: Session, resource_id: str,
        from_date: date | None = None, weeks: int = 1,
    ) -> dict[str, Any]:
        """ADM-SCH-04: one resource's rota for a week, with what is booked on top of it.

        **`set_availability` has had no reader since the module was built.** The schedule
        board's own gap note says "nothing here reads a resource's availability", so a rota
        could be written and the only way to learn what it said was to publish a template
        against it and read the refusal.

        Behind `scheduling.schedule.read`, the module's own routine read: a rota is who works
        when, and it is strictly less disclosing than the session detail that permission
        already returns -- which carries the holds and, for a caller who may change a session,
        the prose on every change.

        **A time-off reason is masked unless the caller could have written one.** It is the
        one window kind the schema requires a reason on, and it is prose about why a person is
        away. The exception itself is never hidden; only the sentence is.
        """
        permit(session, "scheduling.schedule.read")
        return scheduling.resource_week(
            tenant_pool, tenant_id,
            resource_id=require_uuid(resource_id, "resource_id"),
            from_date=from_date, weeks=weeks,
            may_read_reasons=(
                "scheduling.availability.write" in held_permissions(session)))

    @app.post("/scheduling/templates", status_code=201)
    def draft_schedule_template(
        tenant_id: TenantId, session: Session, body: ScheduleTemplateBody
    ) -> dict[str, Any]:
        """Draft a schedule template. **Drafting and publishing are two acts.**"""
        permit(session, "scheduling.template.write", body.correlation_id)
        return scheduling.draft_template(
            tenant_pool, tenant_id, template_code=body.template_code,
            display_name=body.display_name,
            service_resource_id=require_uuid(
                body.service_resource_id, "service_resource_id"),
            location_id=require_uuid(body.location_id, "location_id"),
            rule=_recurrence(body.rule), policy=body.policy.model_dump(),
            requirements=[
                {"kind": r.kind, "quantity": r.quantity,
                 "resource_id": optional_uuid(r.resource_id, "resource_id")}
                for r in body.requirements],
            restrictions=[{"kind": r.kind, "value": r.value} for r in body.restrictions],
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/scheduling/conflict-check")
    def check_schedule_conflicts(
        tenant_id: TenantId, session: Session, body: ConflictCheckBody,
    ) -> dict[str, Any]:
        """What a class would clash with, before a template exists. ADM-SCH-03's live check.

        **`/templates/{id}/preview` could not answer this**, which is why this is a second
        read rather than a parameter on that one: the preview takes a template id and assesses
        what republishing it would move, and this screen is the one where there is no template
        yet. The canvas says when the answer has to arrive -- "conflicts surface as the coach
        field changes, not on save" -- so it is asked per change rather than at the end.

        **A POST that writes nothing**, for the preview's reason: the rule, the policy and the
        requirements are structured bodies and a GET cannot carry them honestly. Gated on the
        read permission, and the gating sweep knows it is a read.

        **It warns and does not block**, which is the canvas's own sentence. Publishing over a
        clash still costs `scheduling.conflict.override` and a written reason; this is the read
        that informs whoever decides.
        """
        permit(session, "scheduling.schedule.read")
        return scheduling.check_schedule(
            tenant_pool, tenant_id,
            location_id=require_uuid(body.location_id, "location_id"),
            rule=_recurrence(body.rule), policy=body.policy.model_dump(),
            requirements=[
                {"kind": r.kind, "quantity": r.quantity,
                 "resource_id": optional_uuid(r.resource_id, "resource_id")}
                for r in body.requirements],
            limit=body.limit)

    @app.post("/scheduling/templates/{template_id}/preview")
    def preview_schedule_publish(
        tenant_id: TenantId, session: Session, template_id: str,
        body: PreviewScheduleBody,
    ) -> dict[str, Any]:
        """The impact preview paragraph 1841 requires *before* publication.

        **It takes the rule somebody is about to publish.** `preview_publish` has had a `rule`
        parameter from the start and nothing passed it, so the preview re-derived the live rule
        and compared it with itself: an operator who did the right thing -- read the preview,
        then publish -- was told "nothing changes" and then moved eight classes and cancelled
        one a member had booked. A read that cannot answer about the proposed change is not the
        informed half of an acknowledgement.

        **A POST that writes nothing**, because the rule is a structured body and a GET cannot
        carry one honestly. It is gated on the read permission, and the gating sweep knows it
        is a read.
        """
        permit(session, "scheduling.schedule.read")
        return scheduling.preview_publish(
            tenant_pool, tenant_id, require_uuid(template_id, "template_id"),
            rule=_recurrence(body.rule) if body.rule is not None else None,
            effective_from=body.effective_from)

    @app.post("/scheduling/templates/{template_id}/publish")
    def publish_schedule_template(
        tenant_id: TenantId, session: Session, template_id: str,
        body: PublishScheduleBody,
    ) -> dict[str, Any]:
        """PublishSchedule. OPS-01-R06."""
        # **Acknowledging impact is a different permission.** Paragraph 1841 makes the
        # assessment a Critical Control, and a bool on the body bought the authority to move
        # eight classes and cancel one somebody had booked for the price of an ordinary
        # publish. That is MOD-013's `priority: "critical"` finding, and the remedy there was
        # the same: a body field that buys an authority is a permission, so charge one.
        permit(session,
               "scheduling.schedule.publish_disruptive" if body.acknowledged_impact
               else "scheduling.schedule.publish",
               body.correlation_id)
        return scheduling.publish_template(
            tenant_pool, tenant_id, require_uuid(template_id, "template_id"),
            rule=_recurrence(body.rule) if body.rule is not None else None,
            effective_from=body.effective_from,
            acknowledged_impact=body.acknowledged_impact,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/scheduling/templates/{template_id}/retire")
    def retire_schedule_template(
        tenant_id: TenantId, session: Session, template_id: str, body: RetireBody
    ) -> dict[str, Any]:
        """Stop a recurring schedule. Generated sessions are left standing."""
        permit(session, "scheduling.template.write", body.correlation_id)
        return scheduling.retire_template(
            tenant_pool, tenant_id, require_uuid(template_id, "template_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/scheduling/templates/{template_id}/sessions", status_code=201)
    def generate_schedule_sessions(
        tenant_id: TenantId, session: Session, template_id: str,
        body: GenerateSessionsBody,
    ) -> dict[str, Any]:
        """CreateSession, in bulk from the live rule. OPS-01-R02.

        **An override costs the override permission.** Paragraph 1842: "Resource conflicts
        cannot be overridden without permission and reason", so sending a reason routes this
        to `scheduling.conflict.override` instead of the publish permission.
        """
        permit(session,
               "scheduling.conflict.override" if body.override_reason
               else "scheduling.schedule.publish",
               body.correlation_id)
        return scheduling.generate_sessions(
            tenant_pool, tenant_id, require_uuid(template_id, "template_id"),
            override_reason=body.override_reason, from_date=body.from_date,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.get("/scheduling/calendar")
    def read_schedule_calendar(
        tenant_id: TenantId, session: Session, location_id: str, from_date: date,
        to_date: date, include_cancelled: bool = False,
    ) -> dict[str, Any]:
        """The calendar. Paragraph 1844's "one calendar", bounded to 62 days."""
        permit(session, "scheduling.schedule.read")
        return scheduling.schedule_for(
            tenant_pool, tenant_id,
            location_id=require_uuid(location_id, "location_id"),
            from_date=from_date, to_date=to_date,
            include_cancelled=include_cancelled)

    @app.get("/scheduling/unstaffed")
    def read_unstaffed_sessions(
        tenant_id: TenantId, session: Session, from_date: date | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Scheduled sessions with no live coach, soonest first, and the places held.

        ADM-CC-01's STAFFING item: "Spin 19:00 Thursday has no coach -- 18 members booked".
        Tenant-wide, where `/scheduling/calendar` is per location, because the Command Center
        is -- and a gap nobody has booked and a gap with eighteen members are the same gap
        and a very different morning, so the held count comes back with it.
        """
        permit(session, "scheduling.schedule.read")
        return scheduling.sessions_without_staff(
            tenant_pool, tenant_id, from_date=from_date, days=days)

    @app.get("/scheduling/sessions/{session_id}")
    def read_schedule_session(
        tenant_id: TenantId, session: Session, session_id: str
    ) -> dict[str, Any]:
        """One session with its resources, its changes and how full it is.

        **A change's reason is masked unless the caller could have written one.** It is prose
        an operator typed about why a class changed, which is where a health fact goes in
        practice -- a reviewer read "she is having chemotherapy on Tuesdays" out of this route
        holding only the routine schedule read, while `/people/{id}` refused them. So the
        reason needs `scheduling.session.change`, and the masking is the gate's own permission
        set rather than a second reading of the assignment rows.
        """
        permit(session, "scheduling.schedule.read")
        return scheduling.session_detail(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            may_read_reasons=(
                "scheduling.session.change" in held_permissions(session)))

    @app.get("/scheduling/sessions/{session_id}/conflicts")
    def read_session_conflicts(
        tenant_id: TenantId, session: Session, session_id: str
    ) -> dict[str, Any]:
        """DetectConflict for a published session. OPS-01-R05.

        A read, because a schedule that was clean when it was generated stops being clean when
        somebody else books the room.
        """
        permit(session, "scheduling.schedule.read")
        return scheduling.detect_session_conflicts(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"))

    @app.get("/scheduling/sessions/{session_id}/eligibility")
    def read_session_eligibility(
        tenant_id: TenantId, session: Session, session_id: str, person_id: str,
        skills: Annotated[list[str] | None, Query(max_length=20)] = None,
    ) -> dict[str, Any]:
        """Whether this person could take a place, and why not.

        **It names a person and the facts are derived from them**, so this read and the hold it
        precedes cannot disagree. Paragraph 1892 makes an understandable denial a Critical
        Control, and a denial computed from figures the caller sent is not one.

        `skills` is the exception and the reason is in `TakeHoldBody`.
        """
        permit(session, "scheduling.schedule.read")
        return scheduling.check_eligibility(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            person_id=require_uuid(person_id, "person_id"), skills=skills)

    @app.post("/scheduling/sessions/{session_id}/substitute")
    def substitute_session_instructor(
        tenant_id: TenantId, session: Session, session_id: str, body: SubstituteBody
    ) -> dict[str, Any]:
        """SubstituteInstructor. OPS-01-R07."""
        permit(session,
               "scheduling.conflict.override" if body.override_reason
               else "scheduling.session.change",
               body.correlation_id)
        return scheduling.substitute_instructor(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            replacement_resource_id=require_uuid(
                body.replacement_resource_id, "replacement_resource_id"),
            reason=body.reason, override_reason=body.override_reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/scheduling/sessions/{session_id}/cancel")
    def cancel_schedule_session(
        tenant_id: TenantId, session: Session, session_id: str, body: CancelSessionBody
    ) -> dict[str, Any]:
        """Cancel a session and release its held places. OPS-01-R07."""
        permit(session, "scheduling.session.change", body.correlation_id)
        return scheduling.cancel_session(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            cancellation_reason=body.cancellation_reason, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/scheduling/sessions/{session_id}/relocate")
    def relocate_schedule_session(
        tenant_id: TenantId, session: Session, session_id: str,
        body: RelocateSessionBody,
    ) -> dict[str, Any]:
        """Move a session to another location. Refused within an hour of the start."""
        permit(session, "scheduling.session.change", body.correlation_id)
        return scheduling.relocate_session(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            to_location_id=require_uuid(body.to_location_id, "to_location_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/scheduling/sessions/{session_id}/handoff")
    def hand_off_session_attendance(
        tenant_id: TenantId, session: Session, session_id: str, body: HandoffBody
    ) -> dict[str, Any]:
        """Who takes the attendance. OPS-01-R07's handoff."""
        permit(session, "scheduling.session.change", body.correlation_id)
        return scheduling.hand_off_attendance(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            to_resource_id=require_uuid(body.to_resource_id, "to_resource_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/scheduling/sessions/{session_id}/holds", status_code=201)
    def take_session_hold(
        tenant_id: TenantId, session: Session, session_id: str, body: TakeHoldBody
    ) -> dict[str, Any]:
        """Take places on a session. The atomic reservation paragraph 4146 asks for."""
        permit(session, "scheduling.place.hold", body.correlation_id)
        return scheduling.take_hold(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            person_id=require_uuid(body.person_id, "person_id"), places=body.places,
            source_kind=body.source_kind, source_ref=body.source_ref,
            idempotency_key=body.idempotency_key, skills=body.skills,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/scheduling/holds/{hold_id}/settle")
    def settle_session_hold(
        tenant_id: TenantId, session: Session, hold_id: str, body: SettleHoldBody
    ) -> dict[str, Any]:
        """Settle a held place: released, or attended. Settled once."""
        permit(session, "scheduling.place.hold", body.correlation_id)
        return scheduling.release_hold(
            tenant_pool, tenant_id, require_uuid(hold_id, "hold_id"),
            attended=body.attended, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    # ------------------------------------------------------------- MOD-021 the device fleet
    #
    # **`/fleet`, not `/devices`.** MOD-007 already owns `/devices/{id}` for a *member's* own
    # phone or tablet -- its trust and revoke routes -- and a fleet of turnstiles under the
    # same prefix would have shadowed them: `GET /devices` for a club's hardware against
    # `POST /devices/{id}/trust` for somebody's handset is two modules' authority on one path.
    # Found by listing the routes rather than by reading them, which is the only way a
    # collision like this shows up.
    #
    # **Every route asks the gate, and the two that touch a door ask for more.** Issuing a
    # reboot and issuing an unlock are the same route with a different word in the body, so
    # the route reads the word and charges `devices.command.unlock` -- financial class, a
    # stepped-up session -- for the one that moves a barrier. That is MOD-009's
    # `consent_subject` lesson and MOD-013's `priority: "critical"` lesson: a body field that
    # buys an authority is a permission.
    #
    # **And nothing here drives any hardware.** A gateway collects its queue and reports what
    # happened; this surface is the registry and the queue. A row saying a turnstile opened,
    # written by nothing that drives a turnstile, is the fabricated-evidence shape this
    # codebase has been bitten by six times.

    @app.post("/fleet/types", status_code=201)
    def declare_device_type(
        tenant_id: TenantId, session: Session, body: DeviceTypeBody
    ) -> dict[str, Any]:
        """Declare a model of hardware and what it can be asked to do.

        **A draft**, on the routine `devices.type.write`: nothing can be enrolled against it
        and its capability set is still editable. What makes the model commandable as a door
        is the publication, which is the next route and a different permission.
        """
        permit(session, "devices.type.write", body.correlation_id)
        return devices.declare_device_type(
            tenant_pool, tenant_id, type_code=body.type_code, vendor=body.vendor,
            model=body.model, kind=body.kind, display_name=body.display_name,
            declared=body.capabilities, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/fleet/types/{type_id}/publish")
    def publish_device_type(
        tenant_id: TenantId, session: Session, type_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        """Settle what this model may be asked to do, so devices can be enrolled against it.

        **A second act by a second person.** Declaring `access.actuate` is what makes a model
        commandable as a barrier and the capability set freezes here, so the author cannot be
        the publisher -- `dev_device_types_publisher_is_not_author` is the half the service
        cannot weaken. MOD-017's contract version, one module later.
        """
        permit(session, "devices.type.publish", body.correlation_id)
        return devices.publish_device_type(
            tenant_pool, tenant_id, require_uuid(type_id, "type_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/types/{type_id}/retire")
    def retire_device_type(
        tenant_id: TenantId, session: Session, type_id: str, body: RevokeCertificateBody
    ) -> dict[str, Any]:
        """Stop new devices being enrolled against a model."""
        permit(session, "devices.type.publish", body.correlation_id)
        return devices.retire_device_type(
            tenant_pool, tenant_id, require_uuid(type_id, "type_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/fleet", status_code=201)
    def register_device(
        tenant_id: TenantId, session: Session, body: RegisterDeviceBody
    ) -> dict[str, Any]:
        """RegisterDevice. Paragraph 3077's enrollment, with the capability snapshot."""
        permit(session, "devices.device.write", body.correlation_id)
        return devices.register_device(
            tenant_pool, tenant_id, type_id=require_uuid(body.type_id, "type_id"),
            location_id=require_uuid(body.location_id, "location_id"),
            serial_number=body.serial_number, display_name=body.display_name,
            config=body.config, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/provision", status_code=201)
    def provision_device(
        tenant_id: TenantId, session: Session, device_id: str, body: ProvisionDeviceBody
    ) -> dict[str, Any]:
        """ProvisionEdgeAgent: the device's first certificate."""
        permit(session, "devices.certificate.write", body.correlation_id)
        return devices.provision_device(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            fingerprint=body.fingerprint, vault_ref=body.vault_ref,
            not_before=body.not_before, not_after=body.not_after,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/configure")
    def configure_device(
        tenant_id: TenantId, session: Session, device_id: str, body: ConfigureDeviceBody
    ) -> dict[str, Any]:
        """ConfigureDevice, under paragraph 3092's optimistic concurrency."""
        permit(session, "devices.device.write", body.correlation_id)
        return devices.configure_device(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            display_name=body.display_name, config=body.config,
            expected_version=body.expected_version,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/commission", status_code=201)
    def commission_device_safety(
        tenant_id: TenantId, session: Session, device_id: str, body: CommissionBody
    ) -> dict[str, Any]:
        """Record the hardware safety profile. TSD paragraph 4172.

        **A profile claiming software control of egress is refused**, not stored with a
        warning: a building whose records pass an audit it would fail is worse than one with
        no records.
        """
        permit(session, "devices.commissioning.record", body.correlation_id)
        return devices.commission_access_point(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            profile=body.profile, on_egress_path=body.on_egress_path,
            fire_release_is_independent=body.fire_release_is_independent,
            local_emergency_input=body.local_emergency_input,
            evidence_ref=body.evidence_ref, door_description=body.door_description,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/commissioning-tests", status_code=201)
    def record_commissioning_test(
        tenant_id: TenantId, session: Session, device_id: str,
        body: CommissioningTestBody,
    ) -> dict[str, Any]:
        """Paragraph 4175's test record. Insert-only: a failure cannot be edited into a pass."""
        permit(session, "devices.commissioning.record", body.correlation_id)
        return devices.record_commissioning_test(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            test_name=body.test_name, passed=body.passed, detail=body.detail,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/activate")
    def activate_device(
        tenant_id: TenantId, session: Session, device_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        """**The commissioning gate.** Paragraph 4175: a failed safety test blocks opening the
        access point in production."""
        permit(session, "devices.device.activate", body.correlation_id)
        return devices.activate_device(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/state")
    def set_device_state(
        tenant_id: TenantId, session: Session, device_id: str, body: DeviceStateBody
    ) -> dict[str, Any]:
        """Maintenance mode, quarantine or retirement.

        **One permission, because all three do the same thing to a club.**
        `enrollment.OPERABLE` is `{"active"}`, so maintenance stops commands and policy
        snapshots exactly as quarantine does, and the way back is `devices.device.activate`.
        The first version charged the routine write for maintenance on the argument that it
        is "a shift decision"; a reviewer then put every door and kiosk in a tenant into
        maintenance on that permission, could not reverse it, and the fleet view reported the
        tenant healthy throughout. Denial of service against a working door is the same harm
        whichever word the body carries.
        """
        permit(session, "devices.device.retire", body.correlation_id)
        return devices.set_device_state(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            target=body.target, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/certificates", status_code=201)
    def rotate_certificate(
        tenant_id: TenantId, session: Session, device_id: str, body: RotateCertificateBody
    ) -> dict[str, Any]:
        """RotateDeviceCertificate. The outgoing one is honoured until it expires."""
        permit(session, "devices.certificate.write", body.correlation_id)
        return devices.rotate_certificate(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            fingerprint=body.fingerprint, vault_ref=body.vault_ref,
            not_before=body.not_before, not_after=body.not_after,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/certificates/{certificate_id}/revoke")
    def revoke_certificate(
        tenant_id: TenantId, session: Session, certificate_id: str,
        body: RevokeCertificateBody,
    ) -> dict[str, Any]:
        """Withdraw a certificate now, and bump the device's revocation epoch with it."""
        permit(session, "devices.certificate.write", body.correlation_id)
        return devices.revoke_certificate(
            tenant_pool, tenant_id, require_uuid(certificate_id, "certificate_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/fleet/firmware", status_code=201)
    def release_firmware(
        tenant_id: TenantId, session: Session, body: FirmwareBody
    ) -> dict[str, Any]:
        """UpdateEdgeAgent's first half: a version exists and where its image is."""
        permit(session, "devices.firmware.write", body.correlation_id)
        return devices.release_firmware(
            tenant_pool, tenant_id, type_id=require_uuid(body.type_id, "type_id"),
            version=body.version, image_ref=body.image_ref,
            image_digest=body.image_digest, release_notes=body.release_notes,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/firmware/{firmware_id}/status")
    def set_firmware_status(
        tenant_id: TenantId, session: Session, firmware_id: str, body: FirmwareStatusBody
    ) -> dict[str, Any]:
        """Paragraph 3080's staged rollout. A withdrawal is final."""
        permit(session, "devices.firmware.write", body.correlation_id)
        return devices.set_firmware_status(
            tenant_pool, tenant_id, require_uuid(firmware_id, "firmware_id"),
            target=body.target, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/snapshots", status_code=201)
    def publish_snapshot(
        tenant_id: TenantId, session: Session, device_id: str, body: SnapshotBody
    ) -> dict[str, Any]:
        """PublishDevicePolicy: the signed authorization projection, with its bound."""
        permit(session, "devices.policy.publish", body.correlation_id)
        return devices.publish_snapshot(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            content_digest=body.content_digest, signature_ref=body.signature_ref,
            ttl_minutes=body.ttl_minutes, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/commands", status_code=201)
    def issue_command(
        tenant_id: TenantId, session: Session, device_id: str, body: IssueCommandBody
    ) -> dict[str, Any]:
        """Paragraph 3084's command: scoped, signed, audited and bounded by device safety.

        **The unlock costs a different permission**, chosen from the body: a reboot is
        operational and constant, and telling a barrier to release is not. There is no action
        in the vocabulary that holds one shut, and `safety.HOLD_COMMANDS` is the list of words
        refused if somebody adds one -- paragraph 4173 is a fire code and a fire code is not
        delegable to a permission.
        """
        if body.action == "unlock_momentary":
            permit(session, "devices.command.unlock", body.correlation_id)
        else:
            permit(session, "devices.command.issue", body.correlation_id)
        return devices.issue_command(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            action=body.action, arguments=body.arguments,
            idempotency_key=body.idempotency_key,
            expires_in_seconds=body.expires_in_seconds,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/commands/{command_id}/deliver")
    def deliver_command(
        tenant_id: TenantId, session: Session, command_id: str, body: DeliverCommandBody
    ) -> dict[str, Any]:
        """A gateway collecting a command. An expired one is settled expired, not delivered."""
        permit(session, "devices.agent.report", body.correlation_id)
        return devices.deliver_command(
            tenant_pool, tenant_id, require_uuid(command_id, "command_id"),
            signature_ref=body.signature_ref, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/fleet/commands/{command_id}/settle")
    def settle_command(
        tenant_id: TenantId, session: Session, command_id: str, body: SettleCommandBody
    ) -> dict[str, Any]:
        """What the device reported, written by whatever drove the hardware."""
        permit(session, "devices.agent.report", body.correlation_id)
        return devices.settle_command(
            tenant_pool, tenant_id, require_uuid(command_id, "command_id"),
            outcome=body.outcome, detail=body.detail,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/commands/expire")
    def expire_commands(
        tenant_id: TenantId, session: Session, body: DeviceSweepBody
    ) -> dict[str, Any]:
        """Settle commands nothing collected in time. **Nothing drives this.**"""
        permit(session, "devices.command.issue", body.correlation_id)
        return devices.expire_commands(
            tenant_pool, tenant_id, actor_id=session["identity_id"],
            correlation_id=body.correlation_id, limit=body.limit)

    @app.post("/fleet/{device_id}/health", status_code=201)
    def record_health(
        tenant_id: TenantId, session: Session, device_id: str, body: HealthReportBody
    ) -> dict[str, Any]:
        """RecordDeviceHealth. Paragraph 3079's numbers, as an insert-only ledger."""
        permit(session, "devices.agent.report", body.correlation_id)
        return devices.record_health(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            latency_ms=body.latency_ms, error_count=body.error_count,
            storage_free_bytes=body.storage_free_bytes,
            agent_version=body.agent_version, peripherals=body.peripherals,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/fleet/offline-sweep")
    def sweep_offline(
        tenant_id: TenantId, session: Session, body: CorrelationBody
    ) -> dict[str, Any]:
        """Publish `device.offline` for devices in service that have gone quiet.

        **Silence has no moment of its own**, which is why this is a sweep -- and nothing
        drives it, which is the twelfth place in this build that wants a worker runtime.
        """
        permit(session, "devices.agent.report", body.correlation_id)
        return devices.sweep_offline(
            tenant_pool, tenant_id, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/fleet/{device_id}/sync-conflicts", status_code=201)
    def record_sync_conflict(
        tenant_id: TenantId, session: Session, device_id: str, body: SyncConflictBody
    ) -> dict[str, Any]:
        """A gateway reporting that its local copy and the registry's disagree."""
        permit(session, "devices.agent.report", body.correlation_id)
        return devices.record_sync_conflict(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"),
            detail=body.detail, local_digest=body.local_digest,
            remote_digest=body.remote_digest, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/fleet/{device_id}")
    def read_device(
        tenant_id: TenantId, session: Session, device_id: str
    ) -> dict[str, Any]:
        """One device, with its commissioning state, its certificates and its last report."""
        permit(session, "devices.device.read")
        return devices.device_detail(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"))

    @app.get("/fleet")
    def read_fleet(
        tenant_id: TenantId, session: Session, location_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Paragraph 3079's fleet dashboard. Reachability is derived, never stored."""
        permit(session, "devices.device.read")
        return devices.fleet_view(
            tenant_pool, tenant_id,
            location_id=(require_uuid(location_id, "location_id")
                         if location_id else None),
            limit=limit)

    @app.get("/fleet/{device_id}/commands")
    def read_command_queue(
        tenant_id: TenantId, session: Session, device_id: str, limit: int = 50
    ) -> dict[str, Any]:
        """What is waiting for this device, with whether each is still deliverable."""
        permit(session, "devices.device.read")
        return devices.command_queue(
            tenant_pool, tenant_id, require_uuid(device_id, "device_id"), limit=limit)

    # ------------------------------------------------------------- MOD-020 booking
    #
    # **Every route asks the gate, and the member's own facts are never on a body.** The
    # booking permission is routine because a member books on their phone and a front desk
    # books a walk-in, and what bounds it is that MOD-019 counts the capacity under a row lock
    # and refuses the hold -- the same argument `scheduling.place.hold` rests on, and true for
    # the same reason rather than by assertion.

    def _acting_for(
        tenant_id: str, session: dict[str, Any], subject_person_id: str,
        *, correlation_id: str,
    ) -> str | None:
        """Refuse a member acting for somebody else, and return who the caller is.

        **`booking.booking.write` is held by every member's own app**, so a route that took a
        `person_id` and asked for nothing more let any member act for any other: a reviewer
        cancelled another member's class, which releases their seat and records a late fee and
        a forfeited credit against them in an insert-only table, booked classes in their name
        against their quota, and declared their attendance. Raising an appeal was the same,
        with `subject_person_id` on the body.

        So acting for another member needs `booking.booking.act_for_another` as well, which a
        member's app is not granted. One function rather than a copy per route, for
        `_require_guardianship`'s reason: the next route somebody adds calls this one too.

        **An unlinked identity cannot act for anybody, including itself.** `person_of_identity`
        answers None when no `ppl_identity_links` row exists, and treating that as "this is
        them" would make the whole check vacuous for exactly the caller it is about -- so it
        falls through to the staff permission, which is the fail-closed direction.
        """
        caller = actor_person_id(tenant_id, session)
        if caller is not None and caller == subject_person_id:
            return caller
        permit(session, "booking.booking.act_for_another", correlation_id)
        return caller

    @app.post("/booking/policies", status_code=201)
    def publish_booking_policy(
        tenant_id: TenantId, session: Session, body: BookingPolicyBody
    ) -> dict[str, Any]:
        """A version of the booking policy. OPS-02-R02.

        **Financial class**, because it decides what a member owes for cancelling late and how
        many no-shows cost them a strike -- paragraph 1020's change control applied to a rule
        members are held to.
        """
        permit(session, "booking.policy.write", body.correlation_id)
        return booking.set_policy(
            tenant_pool, tenant_id, policy_key=body.policy_key,
            display_name=body.display_name,
            rules=body.model_dump(exclude={"policy_key", "display_name",
                                           "correlation_id"}),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/booking/policies/{policy_key}/retire")
    def retire_booking_policy(
        tenant_id: TenantId, session: Session, policy_key: str,
        body: RetirePolicyBody,
    ) -> dict[str, Any]:
        """Withdraw a policy version, so nothing new is sold on it.

        **Financial class, like publishing one**, for the same reason: it decides which terms
        the next booking is made under. It is also the writer the grant was waiting for --
        nothing retired a policy, so `create_booking`'s own "this policy is retired" refusal
        could never fire.
        """
        permit(session, "booking.policy.write", body.correlation_id)
        return booking.retire_policy(
            tenant_pool, tenant_id, policy_key, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/booking/sessions/{session_id}/bookings", status_code=201)
    def create_booking(
        tenant_id: TenantId, session: Session, session_id: str, body: CreateBookingBody
    ) -> dict[str, Any]:
        """CreateBooking. OPS-02-R01.

        **The place and the booking commit together**, which is paragraph 4142's atomic
        reservation: the service takes MOD-019's hold on its own connection.
        """
        permit(session, "booking.booking.write", body.correlation_id)
        person_id = require_uuid(body.person_id, "person_id")
        _acting_for(tenant_id, session, person_id,
                    correlation_id=body.correlation_id)
        return booking.create_booking(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            person_id=person_id,
            policy_key=body.policy_key, source_kind=body.source_kind,
            entitlement_key=body.entitlement_key, skills=body.skills,
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.get("/booking/sessions/{session_id}/eligibility")
    def read_booking_eligibility(
        tenant_id: TenantId, session: Session, session_id: str, person_id: str,
        policy_key: str, entitlement_key: str | None = None,
    ) -> dict[str, Any]:
        """Whether this member could book, and why not. OPS-02's first Critical Control.

        **The same evaluation the command runs**, returned rather than raised. A read that
        computed its own answer from a different rule set is MOD-019's eligibility read
        disagreeing with its own write path -- which is what this was: `_evaluate` left the
        session's restrictions to `take_hold_on` and the entitlement to its own lookup, both
        of which run after it, so a reviewer was told `may_book: true` for a fourteen-year-old
        on an 18+ class and for a member with no pass. It takes `entitlement_key` for the same
        reason the command does: the answer depends on which pass the member means to spend.
        """
        permit(session, "booking.booking.read")
        return booking.may_book(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            person_id=require_uuid(person_id, "person_id"), policy_key=policy_key,
            entitlement_key=entitlement_key)

    @app.post("/booking/bookings/{booking_id}/cancel")
    def cancel_booking(
        tenant_id: TenantId, session: Session, booking_id: str, body: CancelBookingBody
    ) -> dict[str, Any]:
        """CancelBooking, with the consequence the booking's own policy declares."""
        permit(session, "booking.booking.write", body.correlation_id)
        return booking.cancel_booking(
            tenant_pool, tenant_id, require_uuid(booking_id, "booking_id"),
            acting_person_id=actor_person_id(tenant_id, session),
            may_act_for_another=(
                "booking.booking.act_for_another" in held_permissions(session)),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/booking/bookings/{booking_id}")
    def read_booking(
        tenant_id: TenantId, session: Session, booking_id: str
    ) -> dict[str, Any]:
        """One booking with its session, its consequence and what the member said.

        **A cancellation's reason is masked unless the caller is staff, or is the member.** It
        is prose a member typed about why they could not come, which is where a medical reason
        goes in practice -- MOD-019's finding, one module over.

        **Not keyed on `booking.booking.write`**, which was the first version and was the
        cheapest and most widely held permission in the module: cancelling your own booking
        needs it, so every member in the tenant held the key to every other member's
        cancellation prose -- in a build where `member.health.read` is unreachable by anybody
        and `/people/{id}` refuses the same caller. A reviewer read "I am having chemotherapy
        on Tuesdays" with it. The quantifier was the defect: anybody who could write *a*
        reason read *every* reason.
        """
        permit(session, "booking.booking.read")
        held = held_permissions(session)
        caller = actor_person_id(tenant_id, session)
        return booking.booking_detail(
            tenant_pool, tenant_id, require_uuid(booking_id, "booking_id"),
            may_read_reasons=("booking.booking.act_for_another" in held
                              or "booking.appeal.decide" in held),
            reader_person_id=caller)

    @app.get("/booking/sessions/{session_id}/roster")
    def read_session_roster(
        tenant_id: TenantId, session: Session, session_id: str,
        include_settled: bool = False,
    ) -> dict[str, Any]:
        """Who is booked and who is waiting. For a coach and a front desk."""
        permit(session, "booking.booking.read")
        return booking.session_roster(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            include_settled=include_settled)

    @app.get("/booking/members/{person_id}/bookings")
    def read_member_bookings(
        tenant_id: TenantId, session: Session, person_id: str,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        """A member's own bookings, newest session first. No prose, whatever the caller
        holds."""
        permit(session, "booking.booking.read")
        return booking.member_bookings(
            tenant_pool, tenant_id, require_uuid(person_id, "person_id"), limit=limit)

    @app.post("/booking/sessions/{session_id}/waitlist", status_code=201)
    def join_waitlist(
        tenant_id: TenantId, session: Session, session_id: str, body: JoinWaitlistBody
    ) -> dict[str, Any]:
        """JoinWaitlist. OPS-02-R03. **Only a full session has one.**"""
        permit(session, "booking.booking.write", body.correlation_id)
        _acting_for(tenant_id, session, require_uuid(body.person_id, "person_id"),
                    correlation_id=body.correlation_id)
        return booking.join_waitlist(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            person_id=require_uuid(body.person_id, "person_id"),
            policy_key=body.policy_key, entitlement_key=body.entitlement_key,
            skills=body.skills, idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/booking/sessions/{session_id}/waitlist/promote")
    def promote_waitlist(
        tenant_id: TenantId, session: Session, session_id: str, body: SweepBody
    ) -> dict[str, Any]:
        """PromoteWaitlist. **Reserves, then does not notify.**

        Paragraph 5031's order: the place is held here and MOD-013's message goes out
        afterwards, reading the row. The response says `notified: false` rather than leaving a
        caller to assume.
        """
        permit(session, "booking.waitlist.manage", body.correlation_id)
        return booking.promote_waitlist(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/booking/waitlist/{entry_id}/leave")
    def leave_waitlist(
        tenant_id: TenantId, session: Session, entry_id: str, body: LeaveWaitlistBody
    ) -> dict[str, Any]:
        """A member takes themselves off a waitlist, or declines the offer they hold.

        **The act that makes `withdrawn` reachable.** It and `lapsed` were declared states
        nothing wrote, so a member could not leave a queue: a reviewer watched one
        auto-promoted into a seat they no longer wanted while somebody who did want it was
        told the class was full.

        On `booking.booking.write` rather than `booking.waitlist.manage`, because declining is
        the member's own choice -- the first version let a member accept an offer and not
        decline it.
        """
        permit(session, "booking.booking.write", body.correlation_id)
        return booking.leave_waitlist(
            tenant_pool, tenant_id, require_uuid(entry_id, "entry_id"),
            reason=body.reason, actor_id=session["identity_id"],
            acting_person_id=actor_person_id(tenant_id, session),
            may_act_for_another=(
                "booking.booking.act_for_another" in held_permissions(session)),
            correlation_id=body.correlation_id)

    @app.post("/booking/waitlist/{entry_id}/confirm", status_code=201)
    def confirm_waitlist_offer(
        tenant_id: TenantId, session: Session, entry_id: str, body: ConfirmOfferBody
    ) -> dict[str, Any]:
        """A member takes the place they were offered. The place is already theirs."""
        permit(session, "booking.booking.write", body.correlation_id)
        return booking.confirm_offer(
            tenant_pool, tenant_id, require_uuid(entry_id, "entry_id"),
            acting_person_id=actor_person_id(tenant_id, session),
            may_act_for_another=(
                "booking.booking.act_for_another" in held_permissions(session)),
            idempotency_key=body.idempotency_key, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/booking/waitlist/{entry_id}/settle")
    def settle_waitlist_offer(
        tenant_id: TenantId, session: Session, entry_id: str, body: SettleOfferBody
    ) -> dict[str, Any]:
        """An offer declined, or expired. **A decline ends the entry; an expiry keeps its
        place.**"""
        permit(session, "booking.waitlist.manage", body.correlation_id)
        return booking.settle_offer(
            tenant_pool, tenant_id, require_uuid(entry_id, "entry_id"),
            declined=body.declined, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/booking/waitlist/expire")
    def expire_waitlist_offers(
        tenant_id: TenantId, session: Session, body: SweepBody
    ) -> dict[str, Any]:
        """ReleaseCapacity: release the places held by offers nobody answered.

        **Nothing drives this.** The twelfth sweep in this build waiting on a worker runtime.
        """
        permit(session, "booking.waitlist.manage", body.correlation_id)
        return booking.expire_offers(
            tenant_pool, tenant_id, actor_id=session["identity_id"],
            correlation_id=body.correlation_id, limit=body.limit)

    @app.post("/booking/bookings/{booking_id}/check-in")
    def check_in_booking(
        tenant_id: TenantId, session: Session, booking_id: str, body: CheckInBody
    ) -> dict[str, Any]:
        """CheckInBooking. **Recorded, not performed**: nothing here reads a turnstile."""
        permit(session, "booking.attendance.write", body.correlation_id)
        return booking.check_in_booking(
            tenant_pool, tenant_id, require_uuid(booking_id, "booking_id"),
            source=body.source, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/booking/bookings/{booking_id}/intent", status_code=201)
    def declare_attendance_intent(
        tenant_id: TenantId, session: Session, booking_id: str,
        body: AttendanceIntentBody,
    ) -> dict[str, Any]:
        """The AttendanceIntent entity: a member says whether they are coming.

        **Insert-only**, so a change of mind is a new row -- which is what makes the history of
        who answers a reminder readable at all.
        """
        permit(session, "booking.booking.write", body.correlation_id)
        return booking.declare_intent(
            tenant_pool, tenant_id, require_uuid(booking_id, "booking_id"),
            acting_person_id=actor_person_id(tenant_id, session),
            may_act_for_another=(
                "booking.booking.act_for_another" in held_permissions(session)),
            intent=body.intent, source=body.source,
            idempotency_key=body.idempotency_key, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/booking/sessions/{session_id}/settle")
    def settle_session_bookings(
        tenant_id: TenantId, session: Session, session_id: str, body: SweepBody
    ) -> dict[str, Any]:
        """RecordNoShow, for every booking on a finished session. OPS-02-R04.

        **Derived from three facts and settable by nobody**, because it carries a sanction.
        """
        permit(session, "booking.attendance.settle", body.correlation_id)
        return booking.settle_session_bookings(
            tenant_pool, tenant_id, require_uuid(session_id, "session_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/booking/appeals", status_code=201)
    def raise_booking_appeal(
        tenant_id: TenantId, session: Session, body: RaiseAppealBody
    ) -> dict[str, Any]:
        """A member disputes a sanction. The first of two acts."""
        permit(session, "booking.booking.write", body.correlation_id)
        _acting_for(tenant_id, session,
                    require_uuid(body.subject_person_id, "subject_person_id"),
                    correlation_id=body.correlation_id)
        return booking.raise_appeal(
            tenant_pool, tenant_id,
            subject_person_id=require_uuid(body.subject_person_id,
                                           "subject_person_id"),
            against=body.against, grounds=body.grounds,
            no_show_id=optional_uuid(body.no_show_id, "no_show_id"),
            cancellation_id=optional_uuid(body.cancellation_id, "cancellation_id"),
            idempotency_key=body.idempotency_key, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/booking/appeals")
    def read_open_appeals(
        tenant_id: TenantId, session: Session,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        """The appeals waiting for a decision.

        **Behind the deciding permission, not the routine read**, because the grounds are the
        member's own words about why a sanction is wrong -- which is where a medical reason
        goes.
        """
        permit(session, "booking.appeal.decide")
        return booking.open_appeals(tenant_pool, tenant_id, limit=limit)

    @app.post("/booking/appeals/{appeal_id}/decide")
    def decide_booking_appeal(
        tenant_id: TenantId, session: Session, appeal_id: str, body: DecideAppealBody
    ) -> dict[str, Any]:
        """The second act: somebody who is not the member decides.

        **The decider is derived from the session**, both the identity and the person it is --
        MOD-016's finding was a separation of duties compared against a body field.
        """
        permit(session, "booking.appeal.decide", body.correlation_id)
        return booking.decide_appeal(
            tenant_pool, tenant_id, require_uuid(appeal_id, "appeal_id"),
            uphold=body.uphold, note=body.note, actor_id=session["identity_id"],
            decider_person_id=actor_person_id(tenant_id, session),
            correlation_id=body.correlation_id)

    # ------------------------------------------------------------------ MOD-022 access control
    #
    # OPS-03: who may go through which door, right now, and what was recorded about it.
    #
    # **The read permission and the reason permission are different**, and the split is the
    # module's one disclosure decision. A refusal's *public* half is a closed set of codes a
    # turnstile may display; its private half can say "this member's balance is overdue" or
    # "this is a minor without a guardian", which is a health-adjacent fact about a named
    # person standing in a lobby. `access.decision.read` returns the public half to anybody
    # who can see the door; `access.decision.read_reason` is financial class and returns the
    # rest. MOD-013's `privacy.consent.read` disclosure, decided the other way.
    #
    # **Four of the thirteen permissions are routine on purpose**, and
    # `test_the_routine_exceptions_are_deliberate` is where the reasoning lives: a turnstile
    # cannot answer a step-up challenge, a stolen card has to be killable by whoever is on the
    # desk, and a step-up that fails during an evacuation is a door that stays shut.

    @app.post("/access/zones", status_code=201)
    def declare_access_zone(
        tenant_id: TenantId, session: Session, body: ZoneBody
    ) -> dict[str, Any]:
        """An area a policy applies to, and the risk class that bounds its offline authority."""
        permit(session, "access.zone.write", body.correlation_id)
        return access.declare_zone(
            tenant_pool, tenant_id,
            location_id=require_uuid(body.location_id, "location_id"),
            zone_key=body.zone_key, display_name=body.display_name,
            risk_class=body.risk_class, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/access/zones/{zone_id}/retire")
    def retire_access_zone(
        tenant_id: TenantId, session: Session, zone_id: str, body: RetireBody
    ) -> dict[str, Any]:
        """Stop a zone deciding anything. Its points go with it, in the same transaction."""
        permit(session, "access.zone.write", body.correlation_id)
        return access.retire_zone(
            tenant_pool, tenant_id, require_uuid(zone_id, "zone_id"), reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/access/zones/{zone_id}/reclassify")
    def reclassify_access_zone(
        tenant_id: TenantId, session: Session, zone_id: str, body: ReclassifyZoneBody
    ) -> dict[str, Any]:
        """Tighten a zone's risk class.

        **Loosening is refused by a trigger**, not here: the risk class is what bounds how long
        an offline snapshot may authorise at this zone, so relaxing it retroactively extends
        authority somebody has already been given. A looser zone is a new zone.
        """
        permit(session, "access.zone.write", body.correlation_id)
        return access.reclassify_zone(
            tenant_pool, tenant_id, require_uuid(zone_id, "zone_id"),
            risk_class=body.risk_class, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/access/points", status_code=201)
    def commission_access_point(
        tenant_id: TenantId, session: Session, body: AccessPointBody
    ) -> dict[str, Any]:
        """Put a MOD-021 device at a zone, facing one way.

        The direction is the point's, not the request's: an exit-facing point decides nothing,
        which `acc_decision_is_coherent` enforces at the row rather than trusting this service.
        """
        permit(session, "access.zone.write", body.correlation_id)
        return access.commission_point(
            tenant_pool, tenant_id, zone_id=require_uuid(body.zone_id, "zone_id"),
            device_id=require_uuid(body.device_id, "device_id"), direction=body.direction,
            display_name=body.display_name, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/access/points/{point_id}/retire")
    def retire_access_point(
        tenant_id: TenantId, session: Session, point_id: str, body: RetireBody
    ) -> dict[str, Any]:
        permit(session, "access.zone.write", body.correlation_id)
        return access.retire_point(
            tenant_pool, tenant_id, require_uuid(point_id, "point_id"), reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/access/policies", status_code=201)
    def draft_access_policy(
        tenant_id: TenantId, session: Session, body: AccessPolicyBody
    ) -> dict[str, Any]:
        """A draft of the terms. Nothing decides against it until it is published."""
        permit(session, "access.policy.write", body.correlation_id)
        return access.draft_policy(
            tenant_pool, tenant_id, zone_id=require_uuid(body.zone_id, "zone_id"),
            opens_minute=body.opens_minute, closes_minute=body.closes_minute,
            requires_entitlement=body.requires_entitlement,
            max_balance_minor=body.max_balance_minor, min_age_years=body.min_age_years,
            anti_passback_seconds=body.anti_passback_seconds, capacity=body.capacity,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/access/policies/{policy_id}/publish")
    def publish_access_policy(
        tenant_id: TenantId, session: Session, policy_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        """Settle the terms, and retire whatever was live for this zone in the same transaction.

        **A second act by a second person**, which the constraint enforces rather than this
        route: these terms decide who gets through a door, and MOD-017's contract version is
        the same argument about a document somebody is held to.
        """
        permit(session, "access.policy.publish", body.correlation_id)
        return access.publish_policy(
            tenant_pool, tenant_id, require_uuid(policy_id, "policy_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/access/credentials", status_code=201)
    def issue_access_credential(
        tenant_id: TenantId, session: Session, body: IssueCredentialBody
    ) -> dict[str, Any]:
        """Bind a credential to a person. **It identifies them and authorizes nothing.**

        Financial class, because issuing one is how somebody gets a card at all. Revoking is
        routine for the opposite reason: killing a stolen card must not wait for a step-up.
        """
        permit(session, "access.credential.issue", body.correlation_id)
        return access.issue_credential(
            tenant_pool, tenant_id, person_id=require_uuid(body.person_id, "person_id"),
            kind=body.kind, credential_value=body.credential_value,
            expires_at=body.expires_at, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/access/credentials/{credential_id}/revoke")
    def revoke_access_credential(
        tenant_id: TenantId, session: Session, credential_id: str, body: RetireBody
    ) -> dict[str, Any]:
        """Withdraw a credential and bump its epoch, so every offline snapshot is behind."""
        permit(session, "access.credential.revoke", body.correlation_id)
        return access.revoke_credential(
            tenant_pool, tenant_id, require_uuid(credential_id, "credential_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/access/credentials/{credential_id}")
    def read_credential_status(
        tenant_id: TenantId, session: Session, credential_id: str
    ) -> dict[str, Any]:
        """CredentialStatus. **What it is, never what it opens.**

        A route answering "which doors would this card open" is a reconnaissance tool: it
        turns one found card into a map of a building. The zones are not in the answer.

        **The revocation reason follows the same permission as a decision's private half.**
        It is prose somebody at a desk types -- "she left it at the oncology clinic on
        Tuesday" is the module's own example of what goes there -- and it was returned on the
        cheapest read in the module.
        """
        permit(session, "access.credential.read")
        return access.credential_status(
            tenant_pool, tenant_id, require_uuid(credential_id, "credential_id"),
            may_read_reason="access.decision.read_reason" in held_permissions(session))

    @app.post("/access/decisions", status_code=201)
    def evaluate_access(
        tenant_id: TenantId, session: Session, body: EvaluateAccessBody
    ) -> dict[str, Any]:
        """EvaluateAccess. Paragraph 1935's pipeline, in the order paragraph 4183 requires.

        Rate-limited on the point rather than the credential: a reader stuck in a loop is the
        realistic failure, and limiting by credential would let somebody lock a member out of
        their own gym by presenting a copy of their card at speed.
        """
        rate_limit(limit_key="access.evaluate", tenant_id=tenant_id, subject=body.point_id)
        permit(session, "access.decision.evaluate", body.correlation_id)
        return access.evaluate_access(
            tenant_pool, tenant_id, point_id=require_uuid(body.point_id, "point_id"),
            credential_value=body.credential_value, idempotency_key=body.idempotency_key,
            reported_direction=body.reported_direction,
            rotation_counter=body.rotation_counter, nonce=body.nonce,
            token_issued_at=body.token_issued_at, token_expires_at=body.token_expires_at,
            reader_clock_at=body.reader_clock_at,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/access/decisions/override", status_code=201)
    def override_access(
        tenant_id: TenantId, session: Session, body: OverrideAccessBody
    ) -> dict[str, Any]:
        """OverrideAccess. Paragraph 1938's staff override, as its own decision.

        Financial class and a written reason, because this is the one path that admits
        somebody the policy refused. It is recorded as a decision of its own rather than as a
        re-run of the refused one, so the refusal stays in the history beside it.
        """
        permit(session, "access.decision.override", body.correlation_id)
        return access.override_access(
            tenant_pool, tenant_id, point_id=require_uuid(body.point_id, "point_id"),
            person_id=require_uuid(body.person_id, "person_id"), reason=body.reason,
            idempotency_key=body.idempotency_key, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/access/events", status_code=201)
    def record_entry_exit(
        tenant_id: TenantId, session: Session, body: EntryExitBody
    ) -> dict[str, Any]:
        """RecordEntryExit. What a reader saw, which is not what was decided.

        An entry citing a refusal is refused by `acc_event_is_coherent`: a door that opened
        after a denial is either a defect or a tailgate, and a row recording both as ordinary
        would hide whichever it was.
        """
        permit(session, "access.event.record", body.correlation_id)
        return access.record_entry_exit(
            tenant_pool, tenant_id, point_id=require_uuid(body.point_id, "point_id"),
            direction=body.direction, credential_value=body.credential_value,
            decision_id=optional_uuid(body.decision_id, "decision_id"),
            occurred_at=body.occurred_at, source=body.source,
            local_sequence=body.local_sequence, idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/access/events/reconcile")
    def reconcile_offline_access(
        tenant_id: TenantId, session: Session, body: ReconcileAccessBody
    ) -> dict[str, Any]:
        """ReconcileOfflineAccess. Paragraph 4168: deduplicate and flag, never rewrite.

        A reader that was offline decided from a snapshot and queued what it did. Reconciling
        says which of those the server would have refused -- it does not undo them, because
        the person already walked through the door and a row claiming otherwise is a lie.
        """
        permit(session, "access.event.reconcile", body.correlation_id)
        return access.reconcile_offline_access(
            tenant_pool, tenant_id, point_id=require_uuid(body.point_id, "point_id"),
            limit=body.limit, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/access/snapshots", status_code=201)
    def publish_access_snapshot(
        tenant_id: TenantId, session: Session, body: AccessSnapshotBody
    ) -> dict[str, Any]:
        """MOD-021's policy snapshot, narrowed by this zone's risk class.

        The TTL asked for here is a request: `zones.SNAPSHOT_CEILING` is the answer, and a
        high-risk zone's ceiling is two hours however long a caller asks for.
        """
        permit(session, "access.policy.publish", body.correlation_id)
        return access.publish_access_snapshot(
            tenant_pool, tenant_id, point_id=require_uuid(body.point_id, "point_id"),
            content_digest=body.content_digest, ttl_minutes=body.ttl_minutes,
            signature_ref=body.signature_ref, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/access/emergency", status_code=201)
    def emergency_unlock(
        tenant_id: TenantId, session: Session, body: EmergencyUnlockBody
    ) -> dict[str, Any]:
        """EmergencyUnlock. Paragraph 4178's release of every point in a zone.

        **Routine class, deliberately**: paragraph 4178 says dual approval "where time
        permits", and a fire is the case where it does not. A step-up that fails during an
        evacuation is a door that stays shut. The second person moves to the review
        afterwards, which the row stays unreviewed without.
        """
        permit(session, "access.emergency.unlock", body.correlation_id)
        return access.emergency_unlock(
            tenant_pool, tenant_id, zone_id=require_uuid(body.zone_id, "zone_id"),
            reason=body.reason, idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/access/emergency/{unlock_id}/review")
    def review_emergency_unlock(
        tenant_id: TenantId, session: Session, unlock_id: str, body: ReviewUnlockBody
    ) -> dict[str, Any]:
        """The second half of paragraph 4178's dual approval, after the fact.

        The reviewer may not be whoever ordered it -- a constraint, not a convention, because
        an unlock nobody independent looked at is an unlock with one person's word behind it.
        """
        permit(session, "access.emergency.unlock", body.correlation_id)
        return access.review_emergency_unlock(
            tenant_pool, tenant_id, require_uuid(unlock_id, "unlock_id"), note=body.note,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.get("/access/zones")
    def list_access_zones(
        tenant_id: TenantId, session: Session, include_retired: bool = False,
        limit: int = 200,
    ) -> dict[str, Any]:
        """The door board: every zone, how many readers it has and whether a policy is live.

        A zone with `live_policy_version: null` decides nothing -- it is not a zone with a
        permissive default, and a board that rendered the gap as blank would read as "no
        restrictions".
        """
        permit(session, "access.zone.read")
        return access.list_zones(
            tenant_pool, tenant_id, include_retired=include_retired,
            limit=max(1, min(limit, 500)))

    @app.get("/access/zones/{zone_id}")
    def read_access_zone(
        tenant_id: TenantId, session: Session, zone_id: str
    ) -> dict[str, Any]:
        """A zone, its live policy and its points."""
        permit(session, "access.zone.read")
        return access.zone_detail(tenant_pool, tenant_id, require_uuid(zone_id, "zone_id"))

    @app.get("/access/zones/{zone_id}/occupancy")
    def read_zone_occupancy(
        tenant_id: TenantId, session: Session, zone_id: str
    ) -> dict[str, Any]:
        """How many are inside, and whether the number may be relied on.

        **There is no occupancy table.** The count is derived from the event ledger, and the
        answer carries whether it is trustworthy -- an unreconciled offline queue or an
        emergency unlock means people went through doors nothing counted. `NEVER_A_MUSTER` is
        the name of the rule that this must never be used as a fire-roll: a number that is
        usually right is worse than no number when somebody is deciding whether a building is
        empty.
        """
        permit(session, "access.zone.read")
        return access.zone_occupancy(tenant_pool, tenant_id, require_uuid(zone_id, "zone_id"))

    @app.get("/access/visits")
    def read_visits(
        tenant_id: TenantId, session: Session, on: date | None = None,
        compare_weeks: int = 4,
    ) -> dict[str, Any]:
        """Entries per location for one local day, against the same weekday recently.

        ADM-CC-01's third metric. Behind `access.zone.read` like the occupancy count beside
        it: both are figures derived from events with nobody named in them.
        """
        permit(session, "access.zone.read")
        return access.visits_on(
            tenant_pool, tenant_id, on=on, compare_weeks=compare_weeks)

    @app.get("/access/entries")
    def read_entries_by_point(
        tenant_id: TenantId, session: Session, on: date | None = None,
    ) -> dict[str, Any]:
        """Today's entries per reader, keyed by the device behind it.

        ADM-ACC-01's TODAY column. Behind `access.zone.read` like `/access/visits` and the
        occupancy count: all three are figures derived from events with nobody named in them.
        """
        permit(session, "access.zone.read")
        return access.entries_by_point(tenant_pool, tenant_id, on=on)

    @app.get("/access/attendance")
    def read_person_attendance(
        tenant_id: TenantId, session: Session, person_id: str,
        weeks: int = 8, from_date: date | None = None, to_date: date | None = None,
    ) -> dict[str, Any]:
        """When this member last came in, and how often they were coming before that.

        ADM-MEM-01's fourth metric cell. Behind `access.decision.read` -- the access plane's
        own read permission -- because an entry record is strictly less disclosing than the
        decision rows that permission already returns: no code, no reason, no policy. It is
        still a statement about one named person, which is why it is filtered rather than
        listed and why the Member 360 asks this gate separately from `people.person.read`.
        """
        permit(session, "access.decision.read")
        # **Both dates or neither.** A half-named window would have the read choose the other
        # end, and the figure is "visits between these two days" -- a count whose bounds the
        # caller only half stated is a count nobody can check.
        if (from_date is None) != (to_date is None):
            raise InvalidRequest("a_window_needs_both_dates")
        between = None if from_date is None or to_date is None else (from_date, to_date)
        if between is not None and between[1] < between[0]:
            raise InvalidRequest("a_window_cannot_end_before_it_starts")
        return access.person_attendance(
            tenant_pool, tenant_id, person_id=require_uuid(person_id, "person_id"),
            weeks=weeks, between=between)

    @app.get("/access/attendance/window")
    def read_entries_between(
        tenant_id: TenantId, session: Session, person_id: str, since: date,
        until: date,
    ) -> dict[str, Any]:
        """How many times this member came in between two dates, and on which days.

        ADM-PAY-10's strongest evidence against a chargeback. Behind
        `access.decision.read`, the same permission as the attendance read beside it and for
        the same reason: an entry record is strictly less disclosing than the decision rows
        that permission already returns, and it is still a statement about one named person,
        which is why it is filtered rather than listed.
        """
        permit(session, "access.decision.read")
        return access.entries_between(
            tenant_pool, tenant_id, person_id=require_uuid(person_id, "person_id"),
            since=since, until=until)

    @app.get("/access/credentials")
    def read_person_credentials(
        tenant_id: TenantId, session: Session, person_id: str,
        include_revoked: bool = False,
    ) -> dict[str, Any]:
        """What this member can present at a door, and in what state.

        ADM-MEM-01's Access block. **No digest is returned**: the stored value is a SHA-256 of
        the presented secret, which is pseudonymous rather than anonymous, so a listing that
        carried it would let anybody holding a candidate card number confirm whose it is.
        """
        permit(session, "access.credential.read")
        return access.person_credentials(
            tenant_pool, tenant_id, person_id=require_uuid(person_id, "person_id"),
            include_revoked=include_revoked)

    @app.get("/access/decisions")
    def read_access_decisions(
        tenant_id: TenantId, session: Session, zone_id: str | None = None,
        credential_id: str | None = None, person_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """The decisions recorded at a zone, against a credential, or for one person.

        **The private reason is behind a second permission**, and the gate decides which the
        caller gets rather than the caller asking for it: `access.decision.read` returns the
        public code a turnstile may display, and only `access.decision.read_reason` -- which
        is financial class -- returns the rest. A refusal's full reason can say that a named
        person standing in a lobby is overdue, or a minor with no guardian on file.
        """
        permit(session, "access.decision.read")
        # `held_permissions` rather than a second `permit`: it is assurance-filtered, which is
        # the half MOD-014's review found missing. `access.decision.read_reason` is financial
        # class, so a password-only session does not hold it however its roles are written --
        # and asking `permit` would refuse the whole request rather than narrowing the answer.
        may_read_private = "access.decision.read_reason" in held_permissions(session)
        return access.decision_history(
            tenant_pool, tenant_id, zone_id=optional_uuid(zone_id, "zone_id"),
            credential_id=optional_uuid(credential_id, "credential_id"),
            person_id=optional_uuid(person_id, "person_id"),
            may_read_private=may_read_private, limit=max(1, min(limit, 500)))

    # ------------------------------------------------------------ MOD-026 (AUT-02)
    #
    # **Every one of these is routine**, which is stated in the catalogue and worth repeating
    # where somebody reads the routes: a queue and a calendar are edited by the people who
    # run the floor, and raising or settling a task is the ordinary work of a shift. What
    # bounds the write permissions is that both configuration acts are correctable -- a
    # retirement can be lifted and a calendar window is withdrawn rather than deleted.
    #
    # **The two prose columns are masked by the gate, not by the caller.** A read asks
    # `held_permissions` whether this session could write the thing it is reading the reason
    # for, which is MOD-019's trade: whoever may settle a task may read why one was settled.

    @app.post("/tasks/queues", status_code=201)
    def create_task_queue(
        tenant_id: TenantId, session: Session, body: TaskQueueBody
    ) -> dict[str, Any]:
        """Open a work queue. Idempotent on `queue_key`, which is the queue's identity."""
        permit(session, "tasks.queue.write", body.correlation_id)
        return tasks.create_queue(
            tenant_pool, tenant_id, queue_key=body.queue_key,
            display_name=body.display_name,
            location_id=optional_uuid(body.location_id, "location_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/tasks/queues/{queue_id}/retire")
    def retire_task_queue(
        tenant_id: TenantId, session: Session, queue_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        """Stop a queue taking work. The work left in it is counted, not refused."""
        permit(session, "tasks.queue.write", body.correlation_id)
        return tasks.retire_queue(
            tenant_pool, tenant_id, require_uuid(queue_id, "queue_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/tasks/queues")
    def list_task_queues(
        tenant_id: TenantId, session: Session, include_retired: bool = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> dict[str, Any]:
        """The tenant's queues. A retired one is a state a surface has to be able to show."""
        permit(session, "tasks.queue.read")
        return tasks.list_queues(
            tenant_pool, tenant_id, include_retired=include_retired, limit=limit)

    @app.post("/tasks/calendar", status_code=201)
    def set_task_business_hours(
        tenant_id: TenantId, session: Session, body: BusinessHoursBody
    ) -> dict[str, Any]:
        """When a club's people are at work. INV-AUT-02's calendar half."""
        permit(session, "tasks.calendar.write", body.correlation_id)
        try:
            opens = clock_time.fromisoformat(body.opens_at) if body.opens_at else None
            closes = clock_time.fromisoformat(body.closes_at) if body.closes_at else None
        except ValueError:
            raise InvalidRequest("a_calendar_time_is_hh_mm") from None
        return tasks.set_business_hours(
            tenant_pool, tenant_id,
            location_id=require_uuid(body.location_id, "location_id"), kind=body.kind,
            weekday=body.weekday, on_date=body.on_date, opens_at=opens, closes_at=closes,
            note=body.note, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/tasks/calendar/{window_id}/withdraw")
    def withdraw_task_business_hours(
        tenant_id: TenantId, session: Session, window_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        """Take a window back. A withdrawal, not a delete."""
        permit(session, "tasks.calendar.write", body.correlation_id)
        return tasks.withdraw_business_hours(
            tenant_pool, tenant_id, require_uuid(window_id, "window_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/tasks/calendar")
    def read_task_business_hours(
        tenant_id: TenantId, session: Session, location_id: str,
        include_withdrawn: bool = False,
    ) -> dict[str, Any]:
        """A location's calendar, read in the location's own timezone."""
        permit(session, "tasks.calendar.read")
        return tasks.read_business_hours(
            tenant_pool, tenant_id,
            location_id=require_uuid(location_id, "location_id"),
            include_withdrawn=include_withdrawn)

    @app.post("/tasks/cases", status_code=201)
    def open_task_case(
        tenant_id: TenantId, session: Session, body: TaskCaseBody
    ) -> dict[str, Any]:
        """AUT-02-R03's container."""
        permit(session, "tasks.case.write", body.correlation_id)
        return tasks.open_case(
            tenant_pool, tenant_id, case_number=body.case_number, title=body.title,
            queue_id=require_uuid(body.queue_id, "queue_id"),
            subject_kind=body.subject_kind,
            subject_id=optional_uuid(body.subject_id, "subject_id"),
            priority=body.priority,
            recurs_from_case_id=optional_uuid(
                body.recurs_from_case_id, "recurs_from_case_id"),
            idempotency_key=body.idempotency_key, source=body.source,
            actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/tasks/cases/{case_id}/entries", status_code=201)
    def add_task_case_entry(
        tenant_id: TenantId, session: Session, case_id: str, body: CaseEntryBody
    ) -> dict[str, Any]:
        """A line on the timeline. Insert-only: a correction is another entry."""
        permit(session, "tasks.case.write", body.correlation_id)
        return tasks.add_case_entry(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            entry_kind=body.entry_kind, summary=body.summary,
            document_ref=body.document_ref, occurred_at=body.occurred_at,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/tasks/cases/{case_id}/settle")
    def settle_task_case(
        tenant_id: TenantId, session: Session, case_id: str, body: CaseSettleBody
    ) -> dict[str, Any]:
        """Resolve or close. Forward only; the first resolution's attribution stays."""
        permit(session, "tasks.case.write", body.correlation_id)
        return tasks.settle_case(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"), target=body.target,
            resolution_reason=body.resolution_reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/tasks/cases")
    def list_task_cases(
        tenant_id: TenantId, session: Session, queue_id: str | None = None,
        status: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> dict[str, Any]:
        """The tenant's cases, newest first."""
        permit(session, "tasks.case.read")
        return tasks.list_cases(
            tenant_pool, tenant_id,
            may_read_reasons=("tasks.case.write" in held_permissions(session)),
            queue_id=optional_uuid(queue_id, "queue_id"), status=status, limit=limit)

    @app.get("/tasks/cases/{case_id}")
    def read_task_case(
        tenant_id: TenantId, session: Session, case_id: str
    ) -> dict[str, Any]:
        """One case with its timeline and the tasks filed under it."""
        permit(session, "tasks.case.read")
        return tasks.read_case(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            may_read_reasons=("tasks.case.write" in held_permissions(session)))

    @app.get("/tasks/cases/{case_id}/attention")
    def read_attention_item(
        tenant_id: TenantId, session: Session, case_id: str
    ) -> dict[str, Any]:
        """ADM-CC-06's sheet: one case the way the Command Center reads it.

        **The viewer is derived, never accepted.** The sheet's five states include "assigned
        to me" and "assigned to someone else", so the answer depends on who is asking --
        and a `viewer_person_id` on the query string would let a reader ask the question as
        somebody else, which is MOD-020's four caller-supplied person ids in one route.
        `actor_person_id` resolves it through `ppl_identity_links`, and None is the ordinary
        answer for a staff session: an assigned item then reads as somebody else's, which is
        true.
        """
        permit(session, "tasks.case.read")
        return tasks.read_attention_item(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            viewer_person_id=actor_person_id(tenant_id, session),
            may_read_reasons=("tasks.case.write" in held_permissions(session)))

    @app.post("/tasks/cases/{case_id}/assign")
    def assign_task_case(
        tenant_id: TenantId, session: Session, case_id: str, body: CaseAssignBody
    ) -> dict[str, Any]:
        """Assign, take over or release. ADM-CC-06's three assignment actions.

        One route, because they are one fact changing and which one it was is derived from
        what the column held -- a caller cannot declare a release and perform a handover.
        """
        permit(session, "tasks.case.write", body.correlation_id)
        return tasks.assign_case(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            assignee_person_id=(
                # Derived where the body says "me", validated where it names somebody, and
                # None where it says neither -- which is the release.
                _require_person(actor_person_id(tenant_id, session))
                if body.to_self
                else (require_uuid(body.assignee_person_id, "assignee_person_id")
                      if body.assignee_person_id else None)),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/tasks/cases/{case_id}/snooze")
    def snooze_task_case(
        tenant_id: TenantId, session: Session, case_id: str, body: CaseSnoozeBody
    ) -> dict[str, Any]:
        """Defer an exception with an account of why. ADM-CC-06.

        Both the reason and the return date are required by the body *and* by the schema:
        "an exception cannot be dismissed, only deferred with an account of why", and a
        control stated in one layer only is a control the other layer can be wrong about.
        """
        permit(session, "tasks.case.write", body.correlation_id)
        return tasks.snooze_case(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            until=body.snoozed_until, reason=body.reason,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/tasks/cases/{case_id}/return")
    def return_task_case(
        tenant_id: TenantId, session: Session, case_id: str, body: CaseReturnBody
    ) -> dict[str, Any]:
        """Bring a deferred case back early. The remedy the routine deferral needs."""
        permit(session, "tasks.case.write", body.correlation_id)
        return tasks.return_case_to_queue(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/tasks/cases/{case_id}/affected", status_code=201)
    def add_case_affected(
        tenant_id: TenantId, session: Session, case_id: str, body: CaseAffectedBody
    ) -> dict[str, Any]:
        """One of the records an exception is about. ADM-CC-06's "THE SIX RECORDS"."""
        permit(session, "tasks.case.write", body.correlation_id)
        return tasks.add_affected(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            affected_kind=body.affected_kind,
            affected_id=require_uuid(body.affected_id, "affected_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/tasks/cases/{case_id}/affected/withdraw")
    def withdraw_case_affected(
        tenant_id: TenantId, session: Session, case_id: str, body: CaseAffectedWithdrawBody
    ) -> dict[str, Any]:
        """Take a record off an exception. A withdrawal rather than a delete, because "was
        this member ever on this exception" is asked when somebody was contacted by
        mistake."""
        permit(session, "tasks.case.write", body.correlation_id)
        return tasks.withdraw_affected(
            tenant_pool, tenant_id, require_uuid(case_id, "case_id"),
            affected_kind=body.affected_kind,
            affected_id=require_uuid(body.affected_id, "affected_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/tasks/resolved")
    def list_resolved_cases(
        tenant_id: TenantId, session: Session, window_hours: int = 24, limit: int = 100
    ) -> dict[str, Any]:
        """ADM-CC-07: what was resolved in the window, with the median time it took.

        **Read-only for every role, including the owner**, which is the canvas's own line:
        there is no un-resolve here and no route that offers one, because reopening happens
        on the case and arrives in this list as its own row.
        """
        permit(session, "tasks.case.read")
        return tasks.list_resolved(
            tenant_pool, tenant_id, window_hours=window_hours, limit=limit,
            may_read_reasons=("tasks.case.write" in held_permissions(session)))

    @app.get("/tasks/workload")
    def read_task_workload(
        tenant_id: TenantId, session: Session, window_hours: int = 168,
        queue_id: str | None = None
    ) -> dict[str, Any]:
        """AUT-02-R07, and ADM-TSK-01's three chips.

        Counts and ids, never names: `tasks.task.read` is routine, so a name here would be a
        lateral read path around `people.person.read`.
        """
        permit(session, "tasks.task.read")
        return tasks.workload(
            tenant_pool, tenant_id,
            viewer_person_id=actor_person_id(tenant_id, session),
            window_hours=window_hours,
            queue_id=require_uuid(queue_id, "queue_id") if queue_id else None)

    @app.post("/tasks", status_code=201)
    def create_work_task(
        tenant_id: TenantId, session: Session, body: TaskBody
    ) -> dict[str, Any]:
        """Raise a task. AUT-02-R01 and R02."""
        permit(session, "tasks.task.write", body.correlation_id)
        return tasks.create_task(
            tenant_pool, tenant_id, queue_id=require_uuid(body.queue_id, "queue_id"),
            case_id=optional_uuid(body.case_id, "case_id"), title=body.title,
            subject_kind=body.subject_kind,
            subject_id=optional_uuid(body.subject_id, "subject_id"),
            assignee_person_id=optional_uuid(
                body.assignee_person_id, "assignee_person_id"),
            priority=body.priority, due_at=body.due_at, evidence_ref=body.evidence_ref,
            idempotency_key=body.idempotency_key, source=body.source,
            actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/tasks/{task_id}/status")
    def change_work_task_status(
        tenant_id: TenantId, session: Session, task_id: str, body: TaskStatusBody
    ) -> dict[str, Any]:
        """Move a task. A settlement states why; an ordinary move does not."""
        permit(session, "tasks.task.write", body.correlation_id)
        return tasks.change_task_status(
            tenant_pool, tenant_id, require_uuid(task_id, "task_id"), target=body.target,
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/tasks/{task_id}/assign")
    def assign_work_task(
        tenant_id: TenantId, session: Session, task_id: str, body: TaskAssignBody
    ) -> dict[str, Any]:
        """Point a task at somebody, or at nobody."""
        permit(session, "tasks.task.write", body.correlation_id)
        return tasks.assign_task(
            tenant_pool, tenant_id, require_uuid(task_id, "task_id"),
            assignee_person_id=optional_uuid(
                body.assignee_person_id, "assignee_person_id"))

    @app.post("/tasks/{task_id}/dependencies", status_code=201)
    def add_work_task_dependency(
        tenant_id: TenantId, session: Session, task_id: str, body: TaskDependencyBody
    ) -> dict[str, Any]:
        """Say this task waits on that one. A cycle is refused here, not by the schema."""
        permit(session, "tasks.task.write", body.correlation_id)
        return tasks.add_dependency(
            tenant_pool, tenant_id, require_uuid(task_id, "task_id"),
            depends_on_task_id=require_uuid(
                body.depends_on_task_id, "depends_on_task_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/tasks/{task_id}/checklist", status_code=201)
    def add_work_task_checklist_item(
        tenant_id: TenantId, session: Session, task_id: str, body: ChecklistItemBody
    ) -> dict[str, Any]:
        """One step on a task's checklist."""
        permit(session, "tasks.task.write", body.correlation_id)
        return tasks.add_checklist_item(
            tenant_pool, tenant_id, require_uuid(task_id, "task_id"), ordinal=body.ordinal,
            label=body.label, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/tasks/checklist/{item_id}/complete")
    def complete_work_task_checklist_item(
        tenant_id: TenantId, session: Session, item_id: str, body: CommercialActionBody
    ) -> dict[str, Any]:
        """Tick a step, once, with a name on it."""
        permit(session, "tasks.task.write", body.correlation_id)
        return tasks.complete_checklist_item(
            tenant_pool, tenant_id, require_uuid(item_id, "item_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.get("/tasks")
    def list_work_tasks(
        tenant_id: TenantId, session: Session, queue_id: str | None = None,
        assignee_person_id: str | None = None, status: str | None = None,
        mine: bool = False, overdue: bool = False, in_hand: bool = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> dict[str, Any]:
        """The tenant's tasks: a queue's backlog, or one person's work.

        **No name, no address and no birth date**: this permission is routine, so a legal
        name here would be a lateral read path around `people.person.read`.

        **`mine` is a flag and the person is derived**, which is ADM-TSK-01's first chip and
        the one a client cannot express: a browser holds an `identity_id` and the link to a
        person is MOD-014's through `ppl_identity_links`, so there is nothing for it to
        filter by. Accepting a person id for it would also let a reader ask the question as
        somebody else, which is MOD-020's four caller-supplied person ids in one route --
        and `assignee_person_id` stays beside it because asking about *another* named
        person's queue is a different, legitimate question a manager has.

        **`mine` with an unlinked identity returns nothing rather than everything.** Staff
        hold permissions and do not have to be anybody in particular, so an identity with no
        person record is ordinary here -- but it is also not everybody's work, which is what
        falling back to the unfiltered list would have made it. `/tasks/workload` answers the
        same way and says so in `mine_is_zero_without_a_person_record`.
        """
        permit(session, "tasks.task.read")
        own = actor_person_id(tenant_id, session) if mine else None
        if mine and own is None:
            # The empty answer, in the shape of the answer. A surface reads the flag on
            # `/tasks/workload` to say why it is empty.
            return {"tasks": []}
        return tasks.list_tasks(
            tenant_pool, tenant_id,
            may_read_reasons=("tasks.task.write" in held_permissions(session)),
            queue_id=optional_uuid(queue_id, "queue_id"),
            assignee_person_id=own or optional_uuid(
                assignee_person_id, "assignee_person_id"),
            status=status, in_hand=in_hand, overdue=overdue, limit=limit)

    @app.post("/tasks/clocks", status_code=201)
    def start_task_clock(
        tenant_id: TenantId, session: Session, body: SlaClockBody
    ) -> dict[str, Any]:
        """Put a target on a task or a case. AUT-02-R06."""
        permit(session, "tasks.sla.write", body.correlation_id)
        return tasks.start_clock(
            tenant_pool, tenant_id,
            task_id=optional_uuid(body.task_id, "task_id"),
            case_id=optional_uuid(body.case_id, "case_id"),
            target_seconds=body.target_seconds,
            escalate_to_queue_id=optional_uuid(
                body.escalate_to_queue_id, "escalate_to_queue_id"),
            warn_at_basis_points=body.warn_at_basis_points,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/tasks/clocks/{clock_id}/pause")
    def pause_task_clock(
        tenant_id: TenantId, session: Session, clock_id: str, body: ReasonBody
    ) -> dict[str, Any]:
        """Stop a clock, with a stated reason: "why did this stop" is asked precisely when a
        target was missed."""
        permit(session, "tasks.sla.write", body.correlation_id)
        return tasks.pause_clock(
            tenant_pool, tenant_id, require_uuid(clock_id, "clock_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.post("/tasks/clocks/{clock_id}/resume")
    def resume_task_clock(
        tenant_id: TenantId, session: Session, clock_id: str, body: CommercialActionBody
    ) -> dict[str, Any]:
        """Start it again. The pause row keeps when it stopped and why."""
        permit(session, "tasks.sla.write", body.correlation_id)
        return tasks.resume_clock(
            tenant_pool, tenant_id, require_uuid(clock_id, "clock_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/tasks/clocks/{clock_id}/settle")
    def settle_task_clock(
        tenant_id: TenantId, session: Session, clock_id: str, body: SlaSettleBody
    ) -> dict[str, Any]:
        """Judge a target once. A re-judgement is a new target on the same subject."""
        permit(session, "tasks.sla.write", body.correlation_id)
        return tasks.settle_clock(
            tenant_pool, tenant_id, require_uuid(clock_id, "clock_id"),
            status=body.status, reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/tasks/clocks/{clock_id}")
    def read_task_clock(
        tenant_id: TenantId, session: Session, clock_id: str
    ) -> dict[str, Any]:
        """What this target is and where it stands, computed rather than stored.

        **A club with no stated business hours falls back to elapsed wall-clock time and the
        answer says so**, because a business-hours clock against an empty calendar would
        never advance -- which is a breach that never fires.
        """
        permit(session, "tasks.sla.read")
        return tasks.read_clock(
            tenant_pool, tenant_id, require_uuid(clock_id, "clock_id"))

    @app.get("/tasks/{task_id}")
    def read_work_task(
        tenant_id: TenantId, session: Session, task_id: str
    ) -> dict[str, Any]:
        """One task with its checklist and what is in its way."""
        permit(session, "tasks.task.read")
        return tasks.read_task(
            tenant_pool, tenant_id, require_uuid(task_id, "task_id"),
            may_read_reasons=("tasks.task.write" in held_permissions(session)))

    # ------------------------------------------------------------ MOD-027, the leads
    #
    # **Routine throughout.** Raising, claiming and writing up a lead is the ordinary work of a
    # sales shift, and a step-up on every logged phone call would make the pipeline wrong
    # instead -- MOD-026's reason, in the module whose screens are the first a stranger passes
    # through. Nothing here moves money or opens a door.
    #
    # **No name, no number, no address.** A lead is a `ppl_persons` row; MOD-014 answers who
    # they are, through its own gate and under its own masking.

    @app.post("/crm/sources", status_code=201)
    def declare_lead_source(
        tenant_id: TenantId, session: Session, body: LeadSourceBody
    ) -> dict[str, Any]:
        """Declare where leads come from. Idempotent on the key."""
        permit(session, "crm.source.write", body.correlation_id)
        return crm.create_source(
            tenant_pool, tenant_id, source_key=body.source_key,
            display_name=body.display_name,
            location_id=optional_uuid(body.location_id, "location_id"),
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/crm/sources/{source_id}/retire")
    def retire_lead_source(
        tenant_id: TenantId, session: Session, source_id: str, body: RetireSourceBody
    ) -> dict[str, Any]:
        """Stop offering a source without losing the leads that came through it."""
        permit(session, "crm.source.write", body.correlation_id)
        return crm.retire_source(
            tenant_pool, tenant_id, require_uuid(source_id, "source_id"),
            reason=body.reason, actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    @app.get("/crm/sources")
    def list_lead_sources(
        tenant_id: TenantId, session: Session, include_retired: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        """ADM-CRM-04's dropdown, and the groups ADM-RPT-03 will read."""
        permit(session, "crm.source.read")
        return crm.list_sources(
            tenant_pool, tenant_id, include_retired=include_retired, limit=limit)

    # **Declared before `/crm/leads/{lead_id}`**, because FastAPI matches in declaration order
    # and a literal segment behind a path parameter is never reached -- which cost
    # `/memberships/summary` a 422 once.
    @app.get("/crm/board")
    def read_lead_board(
        tenant_id: TenantId, session: Session, mine: bool = False
    ) -> dict[str, Any]:
        """ADM-CRM-01's five columns and the header's two counts."""
        permit(session, "crm.lead.read")
        own = actor_person_id(tenant_id, session) if mine else None
        if mine and own is None:
            return {"columns": [{"stage": c, "count": 0}
                                for c in crm_pipeline.BOARD_COLUMNS],
                    "open_leads": 0, "going_cold": 0,
                    "mine_is_zero_without_a_person_record": (
                        "this identity is not linked to a person, so it owns no leads. "
                        "Staff hold permissions and do not have to be anybody in particular")}
        return crm.board(tenant_pool, tenant_id, owner_person_id=own)

    @app.post("/crm/leads", status_code=201)
    def open_lead(
        tenant_id: TenantId, session: Session, body: LeadBody
    ) -> dict[str, Any]:
        """ADM-CRM-04. A person who already has a lead gets theirs back, which is the
        canvas's own behaviour: "that record would open instead of a second one being
        created"."""
        permit(session, "crm.lead.write", body.correlation_id)
        owner = (_require_person(actor_person_id(tenant_id, session)) if body.owner_is_me
                 else optional_uuid(body.owner_person_id, "owner_person_id"))
        return crm.create_lead(
            tenant_pool, tenant_id, person_id=require_uuid(body.person_id, "person_id"),
            source_id=optional_uuid(body.source_id, "source_id"),
            interests=tuple(body.interests), owner_person_id=owner,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/crm/walk-in-trial", status_code=201)
    def start_walk_in_trial(
        tenant_id: TenantId, session: Session, body: WalkInTrialBody
    ) -> dict[str, Any]:
        """FD-05: "Two fields. Sales will get the rest later." ADR-0010 D12 is the record.

        **Five permissions, because one press writes across four modules.** The person is
        MOD-014's, the lead and its touchpoint are MOD-027's, the figure is MOD-016's quote and
        the agreement and its activation are MOD-017's -- so a session holding only the lead
        write would be creating a person and a membership out of a CRM route, which is
        MOD-010's `events.event.read` finding pointed at writes.

        **Three of the five are financial class, so this needs a stepped-up session**, and
        that is the honest cost rather than a reason to withhold the screen: one step-up per
        twelve-hour window is a receptionist stepping up once at the start of a shift, which
        is ADM-MSH-03's precedent. A button that answered 403 would be worse than its absence;
        a button that asks for the step-up first is what this app already does for a masked
        read.

        **`owner_is_me` is derived from the session**, like ADM-CRM-04's: a body able to name
        an owner would let a desk claim a walk-in as somebody else, and the canvas's own
        "Yasmin picks it up on her pipeline within the minute" is the unowned case.
        """
        permit(session, "crm.lead.write", body.correlation_id)
        permit(session, "people.person.write", body.correlation_id)
        permit(session, "catalog.price.read", body.correlation_id)
        permit(session, "membership.agreement.write", body.correlation_id)
        permit(session, "membership.agreement.activate", body.correlation_id)
        owner = (_require_person(actor_person_id(tenant_id, session)) if body.owner_is_me
                 else None)
        return crm.start_walk_in_trial(
            tenant_pool, tenant_id, summary=body.summary,
            person_id=optional_uuid(body.person_id, "person_id"),
            legal_name=body.legal_name, phone=body.phone,
            different_person=body.different_person,
            variant_id=optional_uuid(body.variant_id, "variant_id"),
            source_id=optional_uuid(body.source_id, "source_id"),
            owner_person_id=owner,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.get("/crm/leads")
    def list_leads(
        tenant_id: TenantId, session: Session, stage: str | None = None,
        owner_person_id: str | None = None, mine: bool = False, unowned: bool = False,
        going_cold: bool = False, limit: int = 50, lost: bool = False,
    ) -> dict[str, Any]:
        """ADM-CRM-02's table and its chips, oldest contact first.

        **`lost` is off by default**, because ADM-CRM-01 draws five columns and no sixth: the
        ordinary list is the live pipeline. With it on, this is the refusals a salesperson
        reviews and ADM-RPT-03 groups by source -- one list of one thing behind a filter
        rather than two routes.
        """
        permit(session, "crm.lead.read")
        own = actor_person_id(tenant_id, session) if mine else None
        if mine and own is None:
            return {"leads": [], "count": 0, "limit": limit, "truncated": False,
                    "mine_is_zero_without_a_person_record": (
                        "this identity is not linked to a person, so it owns no leads")}
        return crm.list_leads(
            tenant_pool, tenant_id, stage=stage,
            owner_person_id=own or optional_uuid(owner_person_id, "owner_person_id"),
            unowned=unowned, going_cold=going_cold, limit=limit, lost=lost)

    @app.get("/crm/leads/{lead_id}")
    def read_lead(
        tenant_id: TenantId, session: Session, lead_id: str, limit: int = 50
    ) -> dict[str, Any]:
        """ADM-CRM-03's profile. A touchpoint's prose is masked for a reader who could not
        have written one -- it is where a health fact goes in practice."""
        permit(session, "crm.lead.read")
        return crm.read_lead(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            may_read_summaries=("crm.touchpoint.write" in held_permissions(session)),
            limit=limit)

    @app.get("/crm/leads/{lead_id}/trial")
    def read_lead_trial(
        tenant_id: TenantId, session: Session, lead_id: str
    ) -> dict[str, Any]:
        """ADM-CRM-05: the trial card on a lead's profile, or why there is not one.

        **Four permissions, because the card carries four modules' facts.** The visits are
        MOD-022's entry events, the classes are MOD-020's settled bookings and the window is
        MOD-017's membership row -- so a reader holding only the lead read would otherwise get
        all three out of a CRM route, which is MOD-010's `events.event.read` finding. All four,
        rather than a partial card: the canvas draws four cells together and three of them is
        not the card, and `issue_command` is the precedent for a route charging more than one.

        **`membership.record.read` was missing when this route was written, and that was the
        same finding one module short.** The docstring said three and named MOD-017's window as
        one of the three facts; the card returns a `membership_id`, a start, an end and the
        terms' `trial_days`, which is verbatim what that permission is described as granting --
        "See a membership, its history and its terms". It is routine and AAL 1, so a
        salesperson holds it anyway and nothing real is refused by adding it; what is closed is
        a sales permission reaching a membership row.
        """
        permit(session, "crm.lead.read")
        permit(session, "access.decision.read")
        permit(session, "booking.booking.read")
        permit(session, "membership.record.read")
        return crm.read_trial(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"))

    @app.get("/crm/leads/{lead_id}/conversion-quote")
    def read_conversion_quote(
        tenant_id: TenantId, session: Session, lead_id: str, variant_id: str,
        currency: str = "JOD",
    ) -> dict[str, Any]:
        """ADM-CRM-06: what it costs this person to become a member on this plan, today.

        **Five permissions, because the card carries five modules' facts.** The recurring
        figure is MOD-016's resolution, the part-period boundary is MOD-017's contract, the
        membership window is MOD-017's row, the class attendances are MOD-020's settled
        bookings and the visits are MOD-022's entry events -- so a reader holding only the
        lead read would get four other modules' data out of a CRM route, which is MOD-010's
        `events.event.read` finding. All five rather than a partial card, for ADM-CRM-05's
        reason: the canvas draws the money and the carry-over together and one without the
        other is not the screen.

        **`catalog.price.read` and not `catalog.price.resolve`**, because this quotes and does
        not sell: nothing is recorded and no coupon is redeemed. Charging the sale's permission
        would make a figure unreadable by the salesperson who needs it before anybody agrees.
        """
        permit(session, "crm.lead.read")
        permit(session, "catalog.price.read")
        permit(session, "membership.record.read")
        permit(session, "booking.booking.read")
        permit(session, "access.decision.read")
        return crm.read_conversion_quote(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            variant_id=require_uuid(variant_id, "variant_id"),
            currency=_currency(currency),
            actor_id=session["identity_id"], correlation_id=str(uuid4()))

    @app.post("/crm/leads/{lead_id}/touchpoints", status_code=201)
    def record_lead_touchpoint(
        tenant_id: TenantId, session: Session, lead_id: str, body: TouchpointBody
    ) -> dict[str, Any]:
        """Write up a conversation. The kind decides which stage it reaches, in the same
        transaction, because the board counts what the timeline says."""
        permit(session, "crm.touchpoint.write", body.correlation_id)
        return crm.record_touchpoint(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            kind=body.kind, summary=body.summary, occurred_at=body.occurred_at,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/crm/leads/{lead_id}/stage")
    def move_lead_stage(
        tenant_id: TenantId, session: Session, lead_id: str, body: LeadStageBody
    ) -> dict[str, Any]:
        """The explicit stage move, for what a touchpoint does not cover. Forward only."""
        permit(session, "crm.lead.write", body.correlation_id)
        return crm.advance_stage(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            to_stage=body.to_stage, expected_version=body.expected_version,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/crm/leads/{lead_id}/lost")
    def mark_lead_lost(
        tenant_id: TenantId, session: Session, lead_id: str, body: LeadLostBody
    ) -> dict[str, Any]:
        """ADM-CRM-07: why did this person not join?

        **The stage is not touched**, which is ADR-0010 D8: the pipeline runs forward only, so
        a lost lead keeps the stage it reached and a reopening resumes it exactly. The loss
        also writes a touchpoint, in the same transaction, because D4 says the history is the
        timeline -- a refusal with nothing in the timeline is one nobody can account for.
        """
        permit(session, "crm.lead.write", body.correlation_id)
        return crm.mark_lead_lost(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            reason=body.reason, detail=body.detail,
            expected_version=body.expected_version,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/crm/leads/{lead_id}/reopen")
    def reopen_lead(
        tenant_id: TenantId, session: Session, lead_id: str, body: LeadReopenBody
    ) -> dict[str, Any]:
        """Put a lost lead back in the pipeline, at the stage it was already at.

        **Always permitted and never gated on the ninety days**, which is ADR-0010 D10: the
        canvas's emphasis is on "rather than a fresh record", and locking this for a quarter
        would make a lead marked lost by mistake uncorrectable on a routine permission.
        `recontactable` on the read says which are worth another try.
        """
        permit(session, "crm.lead.write", body.correlation_id)
        return crm.reopen_lead(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            expected_version=body.expected_version,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/crm/leads/{lead_id}/interests/withdraw")
    def withdraw_lead_interest(
        tenant_id: TenantId, session: Session, lead_id: str,
        body: LeadInterestWithdrawBody
    ) -> dict[str, Any]:
        """Take back an interest recorded by mistake -- the remedy `0027` said slice 3 owed.

        A withdrawal rather than a delete, because "was this lead ever interested in PT" is
        asked precisely when somebody has changed their mind. Until this existed,
        `crm.lead.write` was a routine permission whose every act was permanent.
        """
        permit(session, "crm.lead.write", body.correlation_id)
        return crm.withdraw_interest(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            interest=body.interest,
            actor_id=session["identity_id"], correlation_id=body.correlation_id)

    @app.post("/crm/leads/{lead_id}/assign")
    def assign_lead(
        tenant_id: TenantId, session: Session, lead_id: str, body: LeadAssignBody
    ) -> dict[str, Any]:
        """Claim a lead, hand it over, or release it. Which act it was is derived from what
        the column held, so a caller cannot report a release and perform a handover."""
        permit(session, "crm.lead.write", body.correlation_id)
        owner = (_require_person(actor_person_id(tenant_id, session)) if body.to_self
                 else None if body.release
                 else optional_uuid(body.owner_person_id, "owner_person_id"))
        return crm.assign_lead(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            owner_person_id=owner, expected_version=body.expected_version)

    @app.post("/crm/leads/{lead_id}/next-action")
    def set_lead_next_action(
        tenant_id: TenantId, session: Session, lead_id: str, body: NextActionBody
    ) -> dict[str, Any]:
        """ADM-CRM-02's NEXT ACTION column, or clear it. Both halves or neither."""
        permit(session, "crm.lead.write", body.correlation_id)
        return crm.set_next_action(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            next_action=body.next_action, next_action_on=body.next_action_on,
            expected_version=body.expected_version)

    @app.post("/crm/leads/{lead_id}/interests")
    def record_lead_interests(
        tenant_id: TenantId, session: Session, lead_id: str, body: LeadInterestsBody
    ) -> dict[str, Any]:
        """Add to what a lead is interested in. The set only grows in this slice, which the
        module's own note records as the gap it is."""
        permit(session, "crm.lead.write", body.correlation_id)
        return crm.record_interests(
            tenant_pool, tenant_id, require_uuid(lead_id, "lead_id"),
            interests=tuple(body.interests), actor_id=session["identity_id"],
            correlation_id=body.correlation_id)

    return app


def _default_app() -> FastAPI:
    return create_app()


# Served with `uvicorn --factory app.main:_default_app`; importing this module never reads env.

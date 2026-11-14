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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from datetime import time as clock_time
from time import time
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import db
from app.authorization import catalog as authz_catalog
from app.authorization import gate as authz_gate
from app.authorization import service as authz
from app.billing import service as billing
from app.catalog import service as catalog
from app.commercial import service as commercial
from app.config import Settings, load_settings
from app.configuration import service as config
from app.errors import InvalidRequest, NotFound, ServiceError, TooManyRequests
from app.events import service as events
from app.identity import policy as identity_policy
from app.identity import service as identity
from app.integrations import service as integrations
from app.notifications import service as notifications
from app.observability import metrics as obs_metrics
from app.observability import ratelimit
from app.observability import service as observability
from app.people import service as people
from app.privacy import service as privacy
from app.tenancy import service

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


class ApprovalPolicyBody(BaseModel):
    action: str
    required_permission: str
    correlation_id: str
    threshold_minor: int = 0
    required_approvals: int = 1
    separation_of_duties: bool = True


class ApprovalRequestBody(BaseModel):
    action: str
    resource_type: str
    correlation_id: str
    resource_id: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    reason: str | None = None


class ApprovalDecisionBody(BaseModel):
    decision: str
    correlation_id: str
    reason: str | None = None


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


def create_app(
    settings: Settings | None = None,
    *,
    tenant_pool: Any = None,
    platform_pool: Any = None,
    identity_pool: Any = None,
) -> FastAPI:
    cfg = settings or load_settings()
    owned_pools: list[Any] = []
    # One limiter per application. In this process's memory, which `app.observability.ratelimit`
    # argues for at length: the login path is reachable without authentication and its subject
    # is caller-supplied, so a durable counter would be an unbounded-growth primitive written by
    # anybody. The cost is that two replicas each allow the full budget.
    limiter = ratelimit.Limiter()

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
                                now_epoch=time())
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
            platform_pool, tenant_id, action, body.actor_id, body.correlation_id,
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
        return service.create_brand(tenant_pool, tenant_id, body.organization_id, body.brand_name)

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

    @app.post("/locations", status_code=201)
    def add_location(tenant_id: TenantId, session: Session, body: LocationBody) -> dict[str, Any]:
        permit(session, "tenancy.location.write")
        return service.create_location(
            tenant_pool, tenant_id, body.brand_id, body.location_name, body.timezone
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
            correlation_id=body.correlation_id, brand_id=body.brand_id,
            location_id=body.location_id, expected_version=body.expected_version,
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
            correlation_id=body.correlation_id, brand_id=body.brand_id,
            location_id=body.location_id,
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
            tenant_pool, tenant_id, brand_id=brand_id, location_id=location_id
        )

    @app.post("/config/preview")
    def preview_value(tenant_id: TenantId, session: Session, body: PreviewBody) -> dict[str, Any]:
        permit(session, "config.definition.read")
        return config.preview_config(
            tenant_pool, tenant_id, config_key=body.config_key, value=body.value,
            scope_type=body.scope_type, brand_id=body.brand_id, location_id=body.location_id,
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
            brand_id=brand_id, location_id=location_id,
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
            plan_version=body.plan_version, actor_id=body.actor_id,
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
            tenant_pool, tenant_id, command=body.command, actor_id=body.actor_id,
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
            plan_version=body.plan_version, actor_id=body.actor_id,
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
            idempotency_key=body.idempotency_key, actor_id=body.actor_id,
            correlation_id=body.correlation_id, occurred_at=body.occurred_at,
            corrects_record_id=body.corrects_record_id,
        )

    @app.get("/usage/{meter_code}")
    def get_usage(tenant_id: TenantId, session: Session, meter_code: str) -> dict[str, Any]:
        permit(session, "billing.subscription.read")
        return billing.usage_summary(tenant_pool, tenant_id, meter_code=meter_code)

    @app.post("/invoices", status_code=201)
    def issue_invoice(tenant_id: TenantId, session: Session, body: InvoiceBody) -> dict[str, Any]:
        permit(session, "billing.invoice.issue", body.correlation_id)
        return billing.issue_invoice(
            tenant_pool, tenant_id, actor_id=body.actor_id,
            correlation_id=body.correlation_id, tax_rate_bp=body.tax_rate_bp,
        )

    @app.get("/invoices")
    def get_invoices(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "billing.invoice.read")
        return billing.list_invoices(tenant_pool, tenant_id)

    @app.get("/invoices/{invoice_id}")
    def get_one_invoice(tenant_id: TenantId, session: Session, invoice_id: str) -> dict[str, Any]:
        permit(session, "billing.invoice.read")
        return billing.get_invoice(tenant_pool, tenant_id, invoice_id)

    @app.post("/invoices/{invoice_id}/credit-notes", status_code=201)
    def credit_invoice(
        tenant_id: TenantId, session: Session, invoice_id: str, body: CreditNoteBody
    ) -> dict[str, Any]:
        permit(session, "billing.credit_note.issue", body.correlation_id)
        return billing.issue_credit_note(
            tenant_pool, tenant_id, invoice_id=invoice_id, amount_minor=body.amount_minor,
            reason=body.reason, actor_id=body.actor_id, correlation_id=body.correlation_id,
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
            password=body.password, person_id=body.person_id,
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
        tenant_id: TenantId, session: Session, identity_id: str
    ) -> list[dict[str, Any]]:
        return identity.list_sessions(
            identity_pool, tenant_id, identity_id=owned(session, identity_id)
        )

    @app.post("/sessions/{session_id}/revoke")
    def revoke_session(
        tenant_id: TenantId, session: Session, session_id: str, body: RevokeBody
    ) -> dict[str, Any]:
        return identity.revoke_session(
            identity_pool, tenant_id, session_id=session_id,
            identity_id=session["identity_id"], correlation_id=body.correlation_id,
            reason=body.reason,
        )

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
            identity_pool, tenant_id, device_id=device_id,
            identity_id=session["identity_id"], correlation_id=body.correlation_id,
            reason=body.reason,
        )

    @app.post("/devices/{device_id}/trust")
    def trust_device(
        tenant_id: TenantId, session: Session, device_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        return identity.trust_device(
            identity_pool, tenant_id, device_id=device_id,
            identity_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.post("/identities/{identity_id}/passkeys", status_code=201)
    def enroll_passkey(
        tenant_id: TenantId, session: Session, identity_id: str, body: PasskeyBody
    ) -> dict[str, Any]:
        return identity.enroll_passkey(
            identity_pool, tenant_id, identity_id=owned(session, identity_id),
            webauthn_credential_id=_b64(body.webauthn_credential_id, "credential_id"),
            public_key=_b64(body.public_key, "public_key"),
            correlation_id=body.correlation_id, label=body.label, aaguid=body.aaguid,
            transports=body.transports, backed_up=body.backed_up,
        )

    @app.get("/identities/{identity_id}/passkeys")
    def identity_passkeys(
        tenant_id: TenantId, session: Session, identity_id: str
    ) -> list[dict[str, Any]]:
        return identity.list_passkeys(
            identity_pool, tenant_id, identity_id=owned(session, identity_id)
        )

    @app.post("/passkeys/{passkey_id}/assertion")
    def passkey_assertion(
        tenant_id: TenantId, session: Session, passkey_id: str, body: AssertionBody
    ) -> dict[str, Any]:
        return identity.record_passkey_assertion(
            identity_pool, tenant_id, passkey_id=passkey_id,
            identity_id=session["identity_id"], sign_count=body.sign_count,
            correlation_id=body.correlation_id,
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
            identity_pool, tenant_id, identity_id=body.identity_id, role_key=body.role_key,
            granted_by=session["identity_id"], correlation_id=body.correlation_id,
            scope_type=body.scope_type, brand_id=body.brand_id,
            location_id=body.location_id, expires_at=body.expires_at,
        )

    @app.get("/authz/assignments/{identity_id}")
    def get_assignments(
        tenant_id: TenantId, session: Session, identity_id: str, correlation_id: str
    ) -> list[dict[str, Any]]:
        permit(session, "authz.role.read", correlation_id)
        return authz.list_assignments(identity_pool, tenant_id, identity_id=identity_id)

    @app.post("/authz/assignments/{assignment_id}/revoke")
    def revoke_assignment(
        tenant_id: TenantId, session: Session, assignment_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "authz.assignment.write", body.correlation_id)
        return authz.revoke_assignment(
            identity_pool, tenant_id, assignment_id=assignment_id,
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
            identity_pool, tenant_id, identity_id=identity_id,
            scope=authz.resolve_scope(tenant_pool, tenant_id, brand_id=brand_id,
                                      location_id=location_id),
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
            scope=authz.resolve_scope(tenant_pool, tenant_id, brand_id=brand_id,
                                      location_id=location_id),
            record_denial=False,
        )
        return {"action": action, "allowed": decided.allowed, "reason": decided.reason,
                "step_up_required": decided.step_up_required,
                "required_aal": decided.required_aal, "reachable": decided.reachable,
                "masked_fields": list(decided.masked_fields)}

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
            identity_pool, tenant_id, request_id=request_id,
            decided_by=session["identity_id"], decision=body.decision,
            correlation_id=body.correlation_id, reason=body.reason,
        )

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
            identity_pool, tenant_id, item_id=item_id, decision=body.decision,
            decided_by=session["identity_id"], correlation_id=body.correlation_id,
            note=body.note,
        )

    @app.post("/authz/access-reviews/{review_id}/complete")
    def complete_access_review(
        tenant_id: TenantId, session: Session, review_id: str, body: CorrelationBody
    ) -> dict[str, Any]:
        permit(session, "authz.access_review.conduct", body.correlation_id)
        return authz.complete_access_review(
            identity_pool, tenant_id, review_id=review_id,
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

        `member.health.read` is `biometric_sensitive`, so it needs AAL 3, which needs a hardware
        authenticator MOD-007 cannot verify -- which means this filter removes it from every
        session in this build. That is the deliberate dead end `visibility.UNREACHABLE_CLASSES`
        names, and it is now enforced rather than asserted.
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

    @app.get("/memberships/{membership_id}/as-of")
    def read_membership_as_of(
        tenant_id: TenantId, session: Session, membership_id: str, moment: date
    ) -> dict[str, Any]:
        """COM-01-R07's as-of reconstruction, replayed from the history."""
        permit(session, "membership.record.read")
        return commercial.membership_as_of(
            tenant_pool, tenant_id, require_uuid(membership_id, "membership_id"),
            moment=moment)


    # ------------------------------------------------------------ MOD-017, entitlements
    #
    # **`/member-entitlements`, not `/entitlements`.** That prefix is MOD-015's: a *plan*
    # entitlement is what a tenant's Veyro subscription allows. These are what a member may
    # do. The two are different things owed to different parties, and one prefix for both
    # would read as one surface.

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
            idempotency_key=body.idempotency_key,
            actor_id=session["identity_id"], correlation_id=body.correlation_id,
        )

    @app.get("/finance/invoices/{invoice_id}")
    def read_invoice(
        tenant_id: TenantId, session: Session, invoice_id: str
    ) -> dict[str, Any]:
        """One invoice with its lines and **both** statuses. Paragraph 1607."""
        permit(session, "finance.account.read")
        return commercial.get_invoice(
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

    return app


def _default_app() -> FastAPI:
    return create_app()


# Served with `uvicorn --factory app.main:_default_app`; importing this module never reads env.

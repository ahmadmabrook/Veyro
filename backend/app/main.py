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
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import db
from app.authorization import service as authz
from app.billing import service as billing
from app.config import Settings, load_settings
from app.configuration import service as config
from app.errors import InvalidRequest, NotFound, ServiceError
from app.identity import service as identity
from app.tenancy import service

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", re.ASCII
)


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
    legal_name: str
    country_code: str = Field(min_length=2, max_length=2)


class BrandBody(BaseModel):
    organization_id: str
    brand_name: str


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

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"error": exc.code})

    def permit(session: dict[str, Any], action: str, correlation_id: str | None = None,
               **context: Any) -> dict[str, Any]:
        """The one way a route asks whether its caller may act.

        Every gated route in this file goes through here, and `authz.require` writes the denial
        to the audit log itself, so a surface cannot ask the question and forget to record the
        answer. The tenant comes from the resolved session rather than the header, so the two
        cannot drift.

        A caller that supplies no `correlation_id` gets one minted here. Most read routes carry
        none, and an audit row with a handle nobody can trace back is still better than a row
        that could not be written at all -- but a caller that wants its denials findable should
        send one.
        """
        authz.require(identity_pool, session["tenant_id"], identity_id=session["identity_id"],
                      session_aal=session["aal"], action=action,
                      correlation_id=correlation_id or str(uuid4()), **context)
        return session

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
        permit(session, "tenancy.organization.write")
        return service.create_organization(
            tenant_pool, tenant_id, body.legal_name, body.country_code
        )

    @app.get("/organizations")
    def get_organizations(tenant_id: TenantId, session: Session) -> list[dict[str, Any]]:
        permit(session, "tenancy.organization.read")
        return service.list_organizations(tenant_pool, tenant_id)

    @app.post("/brands", status_code=201)
    def add_brand(tenant_id: TenantId, session: Session, body: BrandBody) -> dict[str, Any]:
        permit(session, "tenancy.brand.write")
        return service.create_brand(tenant_pool, tenant_id, body.organization_id, body.brand_name)

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
            tenant_pool, tenant_id, experiment_key=experiment_key, subject_id=body.subject_id
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
        return identity.complete_step_up(
            identity_pool, tenant_id, token=token, challenge=body.challenge,
            password=body.password, recovery_code=body.recovery_code,
            correlation_id=body.correlation_id,
        )

    @app.post("/auth/recover")
    def recover(tenant_id: TenantId, body: RecoverBody) -> dict[str, Any]:
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

    return app


def _default_app() -> FastAPI:
    return create_app()


# Served with `uvicorn --factory app.main:_default_app`; importing this module never reads env.

"""Veyro API: the HTTP surface over all four planes.

**`X-Veyro-Tenant` is a claim, not an authentication.** It is read, shape-checked, and nothing
more. No caller proves which tenant it is, so anyone who knows a tenant UUID can address that
tenant's API. Isolation does not rest on the header being honest -- it rests on row-level
security, which confines whatever tenant the header names and returns nothing at all when it
names none -- but **authorization does not exist**, and the header is why.

MOD-007 changes part of that picture and not all of it. Its own routes now authenticate: every
operation on an identity resolves a bearer token and refuses unless the session belongs to that
identity. An independent review of the first version found that they did not, and demonstrated a
full account takeover from the tenant UUID alone. What is still missing is the other direction --
nothing ties a session to the tenant header, and no route outside MOD-007 asks for a session at
all. MOD-008 owns roles, permissions and approvals, and is unbuilt.

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

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import db
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
    def add_organization(tenant_id: TenantId, body: OrganizationBody) -> dict[str, Any]:
        return service.create_organization(
            tenant_pool, tenant_id, body.legal_name, body.country_code
        )

    @app.get("/organizations")
    def get_organizations(tenant_id: TenantId) -> list[dict[str, Any]]:
        return service.list_organizations(tenant_pool, tenant_id)

    @app.post("/brands", status_code=201)
    def add_brand(tenant_id: TenantId, body: BrandBody) -> dict[str, Any]:
        return service.create_brand(tenant_pool, tenant_id, body.organization_id, body.brand_name)

    @app.post("/locations", status_code=201)
    def add_location(tenant_id: TenantId, body: LocationBody) -> dict[str, Any]:
        return service.create_location(
            tenant_pool, tenant_id, body.brand_id, body.location_name, body.timezone
        )

    @app.get("/locations")
    def get_locations(tenant_id: TenantId) -> list[dict[str, Any]]:
        return service.list_locations(tenant_pool, tenant_id)

    # --------------------------------------------------- MOD-005 configuration and flags

    @app.post("/config/definitions", status_code=201)
    def define_config(tenant_id: TenantId, body: DefinitionBody) -> dict[str, Any]:
        return config.define_config(
            tenant_pool, tenant_id, config_key=body.config_key, value_type=body.value_type,
            default_value=body.default_value, owner_module=body.owner_module,
            validation=body.validation, description=body.description,
        )

    @app.get("/config/definitions")
    def get_definitions(tenant_id: TenantId) -> list[dict[str, Any]]:
        return config.list_definitions(tenant_pool, tenant_id)

    @app.post("/config/values", status_code=201)
    def publish_value(tenant_id: TenantId, body: PublishValueBody) -> dict[str, Any]:
        return config.publish_config_version(
            tenant_pool, tenant_id, config_key=body.config_key, scope_type=body.scope_type,
            value=body.value, published_by=body.published_by,
            correlation_id=body.correlation_id, brand_id=body.brand_id,
            location_id=body.location_id, expected_version=body.expected_version,
        )

    @app.get("/config/values/{config_key}/history")
    def value_history(tenant_id: TenantId, config_key: str) -> list[dict[str, Any]]:
        return config.config_history(tenant_pool, tenant_id, config_key)

    @app.post("/config/values/{config_key}/rollback", status_code=201)
    def rollback_value(
        tenant_id: TenantId, config_key: str, body: RollbackBody
    ) -> dict[str, Any]:
        return config.rollback_config(
            tenant_pool, tenant_id, config_key=config_key, scope_type=body.scope_type,
            to_version=body.to_version, published_by=body.published_by,
            correlation_id=body.correlation_id, brand_id=body.brand_id,
            location_id=body.location_id,
        )

    @app.get("/config/resolved")
    def resolved_config(
        tenant_id: TenantId, brand_id: str | None = None, location_id: str | None = None
    ) -> dict[str, Any]:
        return config.resolve_config(
            tenant_pool, tenant_id, brand_id=brand_id, location_id=location_id
        )

    @app.post("/config/preview")
    def preview_value(tenant_id: TenantId, body: PreviewBody) -> dict[str, Any]:
        return config.preview_config(
            tenant_pool, tenant_id, config_key=body.config_key, value=body.value,
            scope_type=body.scope_type, brand_id=body.brand_id, location_id=body.location_id,
        )

    @app.put("/flags/{flag_key}")
    def set_flag(tenant_id: TenantId, flag_key: str, body: FeaturePolicyBody) -> dict[str, Any]:
        return config.set_feature_policy(
            tenant_pool, tenant_id, flag_key=flag_key, enabled=body.enabled,
            default_variant=body.default_variant, rules=body.rules,
            description=body.description, expected_version=body.expected_version,
        )

    @app.post("/flags/{flag_key}/kill-switch")
    def kill_switch(tenant_id: TenantId, flag_key: str, body: KillSwitchBody) -> dict[str, Any]:
        return config.set_kill_switch(
            tenant_pool, tenant_id, flag_key=flag_key, engaged=body.engaged, reason=body.reason
        )

    @app.get("/flags")
    def evaluate_flags(
        tenant_id: TenantId,
        context: Annotated[dict[str, str], Depends(evaluation_context)],
        subject_id: str,
    ) -> dict[str, Any]:
        return config.evaluate_flags(
            tenant_pool, tenant_id, subject_id=subject_id, context=context
        )

    @app.post("/experiments", status_code=201)
    def create_experiment(tenant_id: TenantId, body: ExperimentBody) -> dict[str, Any]:
        return config.create_experiment(
            tenant_pool, tenant_id, experiment_key=body.experiment_key, variants=body.variants
        )

    @app.post("/experiments/{experiment_key}/status")
    def experiment_status(
        tenant_id: TenantId, experiment_key: str, body: ExperimentStatusBody
    ) -> dict[str, Any]:
        return config.set_experiment_status(
            tenant_pool, tenant_id, experiment_key=experiment_key, status=body.status
        )

    @app.post("/experiments/{experiment_key}/allocate")
    def allocate(
        tenant_id: TenantId, experiment_key: str, body: AllocateBody
    ) -> dict[str, Any]:
        return config.allocate_experiment(
            tenant_pool, tenant_id, experiment_key=experiment_key, subject_id=body.subject_id
        )

    @app.get("/experiments/{experiment_key}/exposures")
    def exposures(tenant_id: TenantId, experiment_key: str) -> list[dict[str, Any]]:
        return config.experiment_exposures(
            tenant_pool, tenant_id, experiment_key=experiment_key
        )

    @app.get("/config/bundle")
    def config_bundle(
        tenant_id: TenantId,
        context: Annotated[dict[str, str], Depends(evaluation_context)],
        subject_id: str,
        brand_id: str | None = None,
        location_id: str | None = None,
    ) -> dict[str, Any]:
        """PLT-02-R06: one read for a mobile app, kiosk or managed device."""
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
        tenant_id: TenantId, body: StartSubscriptionBody
    ) -> dict[str, Any]:
        return billing.start_subscription(
            tenant_pool, platform_pool, tenant_id, plan_code=body.plan_code,
            plan_version=body.plan_version, actor_id=body.actor_id,
            correlation_id=body.correlation_id, start_on=body.start_on,
            partner_code=body.partner_code, revenue_share_bp=body.revenue_share_bp,
        )

    @app.get("/subscription")
    def read_subscription(tenant_id: TenantId) -> dict[str, Any]:
        return billing.get_subscription(tenant_pool, tenant_id)

    @app.get("/subscription/history")
    def read_subscription_history(tenant_id: TenantId) -> list[dict[str, Any]]:
        return billing.subscription_history(tenant_pool, tenant_id)

    @app.post("/subscription/transition")
    def transition_subscription(
        tenant_id: TenantId, body: SubscriptionCommandBody
    ) -> dict[str, Any]:
        return billing.transition_subscription(
            tenant_pool, tenant_id, command=body.command, actor_id=body.actor_id,
            correlation_id=body.correlation_id, reason=body.reason,
            expected_version=body.expected_version,
        )

    @app.post("/subscription/plan")
    def change_subscription_plan(tenant_id: TenantId, body: ChangePlanBody) -> dict[str, Any]:
        return billing.change_plan(
            tenant_pool, platform_pool, tenant_id, plan_code=body.plan_code,
            plan_version=body.plan_version, actor_id=body.actor_id,
            correlation_id=body.correlation_id, effective_on=body.effective_on,
            in_use=body.in_use, acknowledge_reductions=body.acknowledge_reductions,
        )

    @app.post("/entitlements", status_code=201)
    def grant_entitlement(tenant_id: TenantId, body: EntitlementGrantBody) -> dict[str, Any]:
        return billing.grant_entitlement(
            tenant_pool, tenant_id, feature_code=body.feature_code,
            limit_value=body.limit_value, unlimited=body.unlimited,
        )

    @app.get("/entitlements")
    def get_entitlements(tenant_id: TenantId) -> list[dict[str, Any]]:
        return billing.list_entitlements(tenant_pool, tenant_id)

    @app.get("/entitlements/{feature_code}/check")
    def entitlement_check(
        tenant_id: TenantId, feature_code: str, quantity: int
    ) -> dict[str, Any]:
        return billing.check_entitlement(
            tenant_pool, tenant_id, feature_code=feature_code, quantity=quantity
        )

    @app.post("/meters", status_code=201)
    def define_meter(tenant_id: TenantId, body: MeterBody) -> dict[str, Any]:
        return billing.define_meter(
            tenant_pool, tenant_id, meter_code=body.meter_code, unit=body.unit,
            aggregation=body.aggregation,
        )

    @app.post("/meters/{meter_code}/quota")
    def set_quota(tenant_id: TenantId, meter_code: str, body: QuotaBody) -> dict[str, Any]:
        return billing.set_quota(
            tenant_pool, tenant_id, meter_code=meter_code, period=body.period,
            limit_quantity=body.limit_quantity, overage_allowed=body.overage_allowed,
            hard_stop=body.hard_stop,
        )

    @app.post("/usage", status_code=201)
    def record_usage(tenant_id: TenantId, body: UsageBody) -> dict[str, Any]:
        return billing.record_usage(
            tenant_pool, tenant_id, meter_code=body.meter_code, quantity=body.quantity,
            idempotency_key=body.idempotency_key, actor_id=body.actor_id,
            correlation_id=body.correlation_id, occurred_at=body.occurred_at,
            corrects_record_id=body.corrects_record_id,
        )

    @app.get("/usage/{meter_code}")
    def get_usage(tenant_id: TenantId, meter_code: str) -> dict[str, Any]:
        return billing.usage_summary(tenant_pool, tenant_id, meter_code=meter_code)

    @app.post("/invoices", status_code=201)
    def issue_invoice(tenant_id: TenantId, body: InvoiceBody) -> dict[str, Any]:
        return billing.issue_invoice(
            tenant_pool, tenant_id, actor_id=body.actor_id,
            correlation_id=body.correlation_id, tax_rate_bp=body.tax_rate_bp,
        )

    @app.get("/invoices")
    def get_invoices(tenant_id: TenantId) -> list[dict[str, Any]]:
        return billing.list_invoices(tenant_pool, tenant_id)

    @app.get("/invoices/{invoice_id}")
    def get_one_invoice(tenant_id: TenantId, invoice_id: str) -> dict[str, Any]:
        return billing.get_invoice(tenant_pool, tenant_id, invoice_id)

    @app.post("/invoices/{invoice_id}/credit-notes", status_code=201)
    def credit_invoice(
        tenant_id: TenantId, invoice_id: str, body: CreditNoteBody
    ) -> dict[str, Any]:
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

    return app


def _default_app() -> FastAPI:
    return create_app()


# Served with `uvicorn --factory app.main:_default_app`; importing this module never reads env.

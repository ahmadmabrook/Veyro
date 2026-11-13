"""Veyro API: MOD-004 tenancy control plane.

**The tenant on a request is a claim, not an authentication.** ``X-Veyro-Tenant`` is read and
shape-checked and nothing more; no principal is authenticated and no permission is evaluated,
because authentication and AAL-3 belong to MOD-002, which is not wired in. The environments this
service accepts are local, development and staging -- there is no production value -- so the
claim never reaches real member data. Isolation does not rest on this header being honest: it
rests on row-level security, which confines whatever tenant the header names and returns nothing
at all when it names none.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import db
from app.config import Settings, load_settings
from app.configuration import service as config
from app.errors import ServiceError
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


def tenant_claim(x_veyro_tenant: Annotated[str | None, Header()] = None) -> str:
    """Shape-check the claimed tenant. Rejecting here keeps a malformed value out of the pool."""
    if x_veyro_tenant is None or not _UUID.fullmatch(x_veyro_tenant):
        raise service.InvalidRequest("bad_tenant_header")
    return x_veyro_tenant


TenantId = Annotated[str, Depends(tenant_claim)]


def create_app(
    settings: Settings | None = None,
    *,
    tenant_pool: Any = None,
    platform_pool: Any = None,
) -> FastAPI:
    cfg = settings or load_settings()
    owned_pools: list[Any] = []

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal tenant_pool, platform_pool
        if tenant_pool is None:
            tenant_pool = db.make_tenant_pool(cfg.database_url)
            owned_pools.append(tenant_pool)
        if platform_pool is None:
            platform_pool = db.make_platform_pool(cfg.database_url)
            owned_pools.append(platform_pool)
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

    return app


def _default_app() -> FastAPI:
    return create_app()


# Served with `uvicorn --factory app.main:_default_app`; importing this module never reads env.

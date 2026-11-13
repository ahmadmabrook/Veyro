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

    @app.exception_handler(service.ServiceError)
    async def _service_error(_: Request, exc: service.ServiceError) -> JSONResponse:
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

    return app


def _default_app() -> FastAPI:
    return create_app()


# Served with `uvicorn --factory app.main:_default_app`; importing this module never reads env.

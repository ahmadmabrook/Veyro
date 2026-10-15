"""Veyro API shell: health only. No domains, no database, no customer data."""

from fastapi import FastAPI

from app.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or load_settings()
    app = FastAPI(title="Veyro API", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "veyro-api",
            "environment": cfg.environment,
            "release": cfg.release,
        }

    return app


def _default_app() -> FastAPI:
    return create_app()


# Served with `uvicorn --factory app.main:_default_app`; importing this module never reads env.

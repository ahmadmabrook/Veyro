"""Explicit environment configuration. Fails closed on unknown values; holds no secrets."""

import os
from dataclasses import dataclass

ENVIRONMENTS = ("local", "development", "staging")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    environment: str
    release: str
    database_url: str
    #: An override for MOD-011's `api.request` budget, or None for the table's own number.
    #:
    #: **Admitted in `local` only, and refused everywhere else.** The budget is 600 requests a
    #: minute per identity and its own comment says why it is generous: "a limit that trips
    #: during ordinary use is a limit somebody will raise to infinity rather than
    #: investigate". A browser suite is not ordinary use -- 300 tests in three minutes makes
    #: more requests per minute than any operator will -- and raising the table's number to
    #: suit it would be exactly the mistake that comment names.
    #:
    #: So the knob exists, it is bounded, and it fails closed: setting it in development or
    #: staging refuses to start rather than quietly widening a control. That is the same shape
    #: as every other setting in this file, which holds no secrets and admits no unknown value.
    api_request_budget: int | None = None


def load_settings(env: dict[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env
    environment = source.get("VEYRO_ENV", "")
    if environment not in ENVIRONMENTS:
        raise ConfigError(
            f"VEYRO_ENV must be one of {', '.join(ENVIRONMENTS)}; got {environment!r}"
        )
    release = source.get("VEYRO_RELEASE", "unversioned")
    if not release.strip():
        raise ConfigError("VEYRO_RELEASE must not be blank")
    database_url = source.get("VEYRO_DATABASE_URL", "")
    if not database_url.strip():
        raise ConfigError("VEYRO_DATABASE_URL must be set")
    raw_budget = source.get("VEYRO_API_REQUEST_BUDGET", "").strip()
    budget: int | None = None
    if raw_budget:
        if environment != "local":
            raise ConfigError(
                "VEYRO_API_REQUEST_BUDGET is a local-only test setting; "
                f"VEYRO_ENV is {environment!r}")
        try:
            budget = int(raw_budget)
        except ValueError:
            raise ConfigError(
                f"VEYRO_API_REQUEST_BUDGET must be an integer; got {raw_budget!r}") from None
        if not 1 <= budget <= 100_000:
            raise ConfigError(
                "VEYRO_API_REQUEST_BUDGET must be between 1 and 100000; "
                f"got {budget}")
    return Settings(environment=environment, release=release, database_url=database_url,
                    api_request_budget=budget)

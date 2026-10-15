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
    return Settings(environment=environment, release=release)

"""Explicit environment configuration. Fails closed on unknown values; holds no secrets."""

import os
from dataclasses import dataclass

# **The band comes from where the crypto reasoning is, not from a second pair of literals
# here.** `app.identity.secrets` imports nothing beyond the standard library, so this is a
# leaf dependency with no cycle -- and the alternative is two definitions of a password
# hash's floor, which is the one-module-two-definitions shape this build refuses everywhere
# else. What stays here is the refusal outside `local`, which is this file's own job.
from app.identity import secrets

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
    #: An override for the scrypt work factor as a power of two, or None for the deployed one.
    #:
    #: **Admitted in `local` only, and refused everywhere else** -- the same shape as the
    #: request budget above, and for a sharper reason. `secrets.DEFAULT_SCRYPT_PARAMS` is
    #: 2**14 because a password is low-entropy and the only defence against an offline attack
    #: on a stolen table is making each guess expensive; lowering it in a deployed environment
    #: would make every stored password cheap, which is the regression
    #: `ScryptParameterTests` exists to catch.
    #:
    #: **It exists because the suite spends half its wall-clock hashing, measured**: 147 scrypt
    #: calls in one twelve-test file, 5.2 seconds of 10.2, and CI's backend step reached 22.5
    #: minutes and cancelled the job in its last step with every check green. The parameters
    #: are stored per credential and `verify_secret` reads them off the row, so a cheap hash
    #: verifies cheaply and nothing about the mechanism goes untested -- only the number, which
    #: is asserted directly.
    #:
    #: Bounded again in `app.identity.secrets`, where the crypto reasoning is: two independent
    #: refusals, because one of them is a string in an environment.
    scrypt_cost_log2: int | None = None
    #: The WebAuthn relying party id, or None where no passkey may authenticate.
    #:
    #: **A deployment fact with no default, which is why it is here and not in the code.** The
    #: RP id is the domain an authenticator binds a credential to -- a passkey created for
    #: `veyro.example` will not sign for anything else, which is the whole anti-phishing
    #: property -- and guessing it would either break every credential or, worse, accept one
    #: created for a domain nobody controls. The same precedent as MOD-015's tax rate and
    #: MOD-009's `response_days`: the sources state none, so the caller states it or the
    #: feature refuses.
    #:
    #: Absent, the passkey authentication paths answer that no relying party is configured.
    #: Enrolment still works, because storing a credential is not authenticating with one.
    webauthn_rp_id: str | None = None
    #: The exact origins a ceremony may run at. Empty where `webauthn_rp_id` is None.
    #:
    #: **Exact strings, compared with `in`, never a suffix.** `https://veyro.example.evil.com`
    #: ends with the RP id's own domain and `http://veyro.example` differs only in scheme; a
    #: suffix or a substring match admits both. The RP id bounds which credentials will sign at
    #: all and this bounds where the ceremony may happen, and they are different checks.
    webauthn_origins: tuple[str, ...] = ()


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
    raw_cost = source.get("VEYRO_SCRYPT_COST_LOG2", "").strip()
    cost: int | None = None
    if raw_cost:
        if environment != "local":
            raise ConfigError(
                "VEYRO_SCRYPT_COST_LOG2 is a local-only test setting; "
                f"VEYRO_ENV is {environment!r}")
        try:
            cost = int(raw_cost)
        except ValueError:
            raise ConfigError(
                f"VEYRO_SCRYPT_COST_LOG2 must be an integer; got {raw_cost!r}") from None
        if not secrets.MIN_COST_LOG2 <= cost <= secrets.COST_LOG2:
            raise ConfigError(
                f"VEYRO_SCRYPT_COST_LOG2 must be between {secrets.MIN_COST_LOG2} and "
                f"{secrets.COST_LOG2}; got {cost}")
    rp_id = source.get("VEYRO_WEBAUTHN_RP_ID", "").strip()
    raw_origins = source.get("VEYRO_WEBAUTHN_ORIGINS", "").strip()
    origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip())
    if rp_id:
        # **Both or neither.** An RP id with no origins would refuse every ceremony while
        # reading as configured, and origins with no RP id would check where a ceremony ran
        # without checking which relying party the credential was made for -- the half that
        # carries the anti-phishing property.
        if not origins:
            raise ConfigError(
                "VEYRO_WEBAUTHN_RP_ID needs VEYRO_WEBAUTHN_ORIGINS: an origin list is what "
                "says where a ceremony may run, and an empty one refuses every assertion")
        for origin in origins:
            if not origin.startswith(("https://", "http://")):
                raise ConfigError(
                    f"VEYRO_WEBAUTHN_ORIGINS entries are full origins; got {origin!r}")
            if origin.rstrip("/") != origin or origin.count("/") != 2:
                raise ConfigError(
                    f"a WebAuthn origin carries no path and no trailing slash; got {origin!r}")
            if origin.startswith("http://") and environment != "local":
                # WebAuthn permits `http://localhost` for development and nothing else, and a
                # plaintext origin in staging is a ceremony an observer can replay.
                raise ConfigError(
                    f"a plaintext WebAuthn origin is admitted in local only; got {origin!r} "
                    f"with VEYRO_ENV={environment!r}")
    elif origins:
        raise ConfigError(
            "VEYRO_WEBAUTHN_ORIGINS is set without VEYRO_WEBAUTHN_RP_ID, so nothing says "
            "which relying party a credential must have been created for")
    return Settings(environment=environment, release=release, database_url=database_url,
                    api_request_budget=budget, scrypt_cost_log2=cost,
                    webauthn_rp_id=rp_id or None, webauthn_origins=origins)

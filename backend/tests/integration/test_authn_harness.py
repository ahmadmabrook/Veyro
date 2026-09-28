"""GOV-01-R02 authentication harness against a real Postgres, as the runtime role.

SCN-MOD001-097  valid credential -> session issued + success audit event.
SCN-MOD001-027  every negative credential -> rejected, no session, state unchanged.
Self-check      a deliberately broken authenticator is caught by the same assertions.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

import psycopg
import pytest

from tests.harness.authn import (
    FixtureAuthenticator,
    assert_authenticated,
    assert_rejected_without_side_effects,
    mint,
    negative_credentials,
)
from tests.harness.tenant_isolation import Conn

NOW = 1_900_000_000  # fixed clock: deterministic expiry boundaries
SUBJECT = "synthetic-member-0001"
DISABLED = "synthetic-member-0002"
CASE_NAMES = [
    c.name for c in negative_credentials(b"k", now=NOW, subject=SUBJECT, disabled_subject=DISABLED)
]


def _evidence(tag: str, payload: Any) -> None:
    print(f"{tag}-EVIDENCE {json.dumps(payload, sort_keys=True, default=str)}")


@pytest.fixture(scope="module")
def signing_key() -> bytes:
    return secrets.token_bytes(32)  # per-run; never committed


@pytest.fixture(scope="module")
def identities(admin: Conn, runtime_password: str) -> None:
    admin.execute(
        "INSERT INTO harness_auth.identity (subject, disabled) VALUES (%s, false), (%s, true)",
        (SUBJECT, DISABLED),
    )


@pytest.fixture
def auth(runtime: Conn, signing_key: bytes, identities: None) -> FixtureAuthenticator:
    return FixtureAuthenticator(runtime, signing_key, now=lambda: NOW)


def test_scn097_valid_credential_issues_session_and_audits(
    auth: FixtureAuthenticator, admin: Conn, signing_key: bytes
) -> None:
    credential = mint(signing_key, subject=SUBJECT, issued_at=NOW - 60, expires_at=NOW + 600)
    _evidence("SCN-MOD001-097", assert_authenticated(auth, admin, credential, SUBJECT))


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_scn027_negative_credential_rejected_without_side_effects(
    auth: FixtureAuthenticator, admin: Conn, signing_key: bytes, case_name: str
) -> None:
    cases = negative_credentials(signing_key, now=NOW, subject=SUBJECT, disabled_subject=DISABLED)
    case = next(c for c in cases if c.name == case_name)
    _evidence(f"SCN-MOD001-027[{case_name}]", assert_rejected_without_side_effects(auth, admin, case))


class _AcceptsExpired(FixtureAuthenticator):
    def _is_expired(self, exp: int, now: int) -> bool:
        return False  # deliberately broken


def test_harness_detects_authenticator_accepting_expired_credential(
    runtime: Conn, admin: Conn, signing_key: bytes, identities: None
) -> None:
    broken = _AcceptsExpired(runtime, signing_key, now=lambda: NOW)
    cases = negative_credentials(signing_key, now=NOW, subject=SUBJECT, disabled_subject=DISABLED)
    expired = next(c for c in cases if c.name == "expired")
    with pytest.raises(AssertionError, match="SESSION_ISSUED") as caught:
        assert_rejected_without_side_effects(broken, admin, expired)
    _evidence("AUTHN-HARNESS-SELF-CHECK[accepts_expired]", str(caught.value))


@pytest.mark.parametrize(
    "stmt",
    [
        "SELECT * FROM harness_auth.audit_event",
        "DELETE FROM harness_auth.audit_event",
        "UPDATE harness_auth.audit_event SET reason = 'OK'",
        "SELECT * FROM harness_auth.session",
    ],
)
def test_runtime_role_cannot_read_back_or_rewrite_auth_state(runtime: Conn, stmt: str) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="permission denied"):
        runtime.execute(stmt)

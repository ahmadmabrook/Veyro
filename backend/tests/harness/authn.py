"""Authentication harness — GOV-01-R02's negative-credential fixture pattern.

TSD ADR-009: Veyro does not implement credential cryptography; a managed
OIDC/passkey provider does. So `FixtureAuthenticator` is NOT an authenticator
for product code. It is the smallest fixture endpoint that lets the harness
prove the contract MOD-007/008 must meet against their real provider:

  valid credential  -> exactly one session row + one `authentication.succeeded`
                       audit row
  negative case     -> no session; session/identity state byte-identical
                       before/after; exactly one `authentication.failed` audit
                       row carrying the reason code; raw credential never stored

State lives in the disposable Postgres and is written by the same
non-privileged runtime role the tenant-isolation harness uses (append-only:
INSERT on session/audit, SELECT on identity, nothing else).

Plug-in point: implement `Authenticator`, mint the same `NegativeCredential`
case names in your real token format, and run `assert_rejected_without_side_effects`
/ `assert_authenticated` (swapping in your own state/audit queries).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

from psycopg import sql

from .tenant_isolation import OWNER_ROLE, RUNTIME_ROLE, Conn, as_schema_owner, one_row

AUDIENCE = "veyro-harness"
SESSION_TTL_S = 900
OK = "OK"


def provision_auth_schema(admin: Conn) -> None:
    rt = sql.Identifier(RUNTIME_ROLE)
    admin.execute(
        sql.SQL("CREATE SCHEMA harness_auth AUTHORIZATION {}").format(sql.Identifier(OWNER_ROLE))
    )
    with as_schema_owner(admin):
        admin.execute(
            "CREATE TABLE harness_auth.identity"
            " (subject text PRIMARY KEY, disabled boolean NOT NULL DEFAULT false)"
        )
        admin.execute(
            "CREATE TABLE harness_auth.session (id uuid PRIMARY KEY,"
            " subject text NOT NULL REFERENCES harness_auth.identity,"
            " issued_at timestamptz NOT NULL, expires_at timestamptz NOT NULL)"
        )
        admin.execute(
            "CREATE TABLE harness_auth.audit_event"
            " (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, event_type text NOT NULL,"
            " subject text, reason text NOT NULL,"
            " occurred_at timestamptz NOT NULL DEFAULT clock_timestamp())"
        )
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA harness_auth TO {}").format(rt))
        admin.execute(sql.SQL("GRANT SELECT ON harness_auth.identity TO {}").format(rt))
        admin.execute(
            sql.SQL("GRANT INSERT ON harness_auth.session, harness_auth.audit_event TO {}").format(rt)
        )


# --- fixture credential format: base64url(claims).base64url(HMAC-SHA256) -----


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(key: bytes, body: str) -> str:
    return _b64e(hmac.new(key, body.encode(), hashlib.sha256).digest())


def mint(
    key: bytes, *, subject: str, issued_at: int, expires_at: int, audience: str = AUDIENCE
) -> str:
    claims = {"sub": subject, "aud": audience, "iat": issued_at, "exp": expires_at}
    body = _b64e(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode())
    return f"{body}.{_sign(key, body)}"


# --- the fixture endpoint ------------------------------------------------------


@dataclass(frozen=True)
class AuthResult:
    session_id: UUID | None
    reason: str


class Authenticator(Protocol):
    def authenticate(self, credential: str) -> AuthResult: ...


class FixtureAuthenticator:
    def __init__(
        self, conn: Conn, key: bytes, now: Callable[[], int], audience: str = AUDIENCE
    ) -> None:
        self._conn, self._key, self._now, self._audience = conn, key, now, audience

    def authenticate(self, credential: str) -> AuthResult:
        with self._conn.transaction():
            subject, reason = self._verify(credential)
            if reason != OK or subject is None:
                self._audit("authentication.failed", subject, reason)
                return AuthResult(None, reason)
            session_id, now = uuid4(), self._now()
            self._conn.execute(
                "INSERT INTO harness_auth.session (id, subject, issued_at, expires_at)"
                " VALUES (%s, %s, to_timestamp(%s), to_timestamp(%s))",
                (session_id, subject, now, now + SESSION_TTL_S),
            )
            self._audit("authentication.succeeded", subject, OK)
            return AuthResult(session_id, OK)

    def _verify(self, credential: str) -> tuple[str | None, str]:
        body, dot, sig = credential.partition(".")
        if not (dot and body and sig) or "." in sig:
            return None, "MALFORMED"
        # Signature first: no attacker-controlled claim is parsed before it's authenticated.
        if not hmac.compare_digest(sig.encode(), _sign(self._key, body).encode()):
            return None, "BAD_SIGNATURE"
        try:
            claims = json.loads(_b64d(body))
        except ValueError:
            return None, "MALFORMED"
        if not isinstance(claims, dict) or not isinstance(claims.get("sub"), str):
            return None, "MALFORMED"
        subject: str = claims["sub"]
        reason = self._check_claims(claims)
        if reason != OK:
            return subject, reason
        row = self._conn.execute(
            "SELECT disabled FROM harness_auth.identity WHERE subject = %s", (subject,)
        ).fetchone()
        if row is None:
            return subject, "UNKNOWN_SUBJECT"
        return subject, "DISABLED_SUBJECT" if row[0] else OK

    def _check_claims(self, claims: dict[str, Any]) -> str:
        now = self._now()
        iat, exp = claims.get("iat"), claims.get("exp")
        if claims.get("aud") != self._audience:
            return "WRONG_AUDIENCE"
        if not isinstance(iat, int) or not isinstance(exp, int):
            return "MALFORMED"
        if iat > now:
            return "NOT_YET_VALID"
        if self._is_expired(exp, now):
            return "EXPIRED"
        return OK

    def _is_expired(self, exp: int, now: int) -> bool:
        return exp <= now

    def _audit(self, event_type: str, subject: str | None, reason: str) -> None:
        self._conn.execute(
            "INSERT INTO harness_auth.audit_event (event_type, subject, reason)"
            " VALUES (%s, %s, %s)",
            (event_type, subject, reason),
        )


# --- the negative-credential catalog -------------------------------------------


@dataclass(frozen=True)
class NegativeCredential:
    name: str
    credential: str
    expected_reason: str


def negative_credentials(
    key: bytes, *, now: int, subject: str, disabled_subject: str
) -> list[NegativeCredential]:
    def tok(sub: str = subject, aud: str = AUDIENCE, iat: int = now - 60,
            exp: int = now + 600, k: bytes = key) -> str:
        return mint(k, subject=sub, audience=aud, issued_at=iat, expires_at=exp)

    body, _, sig = tok().partition(".")
    forged_body = tok(sub="synthetic-attacker").partition(".")[0]
    n = NegativeCredential
    return [
        n("expired", tok(iat=now - 1200, exp=now - 1), "EXPIRED"),
        n("expires_exactly_now", tok(exp=now), "EXPIRED"),
        n("not_yet_valid", tok(iat=now + 600, exp=now + 1200), "NOT_YET_VALID"),
        n("wrong_signing_key", tok(k=secrets.token_bytes(32)), "BAD_SIGNATURE"),
        n("tampered_claims", f"{forged_body}.{sig}", "BAD_SIGNATURE"),
        n("signature_stripped", f"{body}.", "MALFORMED"),
        n("extra_segment", f"{body}.{sig}.x", "MALFORMED"),
        n("garbage", "not-a-credential", "MALFORMED"),
        n("empty", "", "MALFORMED"),
        n("non_ascii", "ü.ü", "BAD_SIGNATURE"),
        n("wrong_audience", tok(aud="some-other-service"), "WRONG_AUDIENCE"),
        n("unknown_subject", tok(sub="synthetic-nobody"), "UNKNOWN_SUBJECT"),
        n("disabled_subject", tok(sub=disabled_subject), "DISABLED_SUBJECT"),
    ]


# --- harness assertions (observer = superuser ground truth) --------------------


def state_fingerprint(observer: Conn) -> tuple[Any, ...]:
    return tuple(
        one_row(
            observer.execute(
                "SELECT (SELECT count(*) FROM harness_auth.session),"
                " (SELECT md5(coalesce(string_agg(s::text, ',' ORDER BY s::text), ''))"
                "  FROM harness_auth.session s),"
                " (SELECT md5(coalesce(string_agg(i::text, ',' ORDER BY i::text), ''))"
                "  FROM harness_auth.identity i)"
            )
        )
    )


def _audit_mark(observer: Conn) -> int:
    return int(
        one_row(observer.execute("SELECT coalesce(max(id), 0) FROM harness_auth.audit_event"))[0]
    )


def _audit_since(observer: Conn, mark: int) -> list[tuple[Any, ...]]:
    return [
        tuple(r)
        for r in observer.execute(
            "SELECT event_type, subject, reason FROM harness_auth.audit_event"
            " WHERE id > %s ORDER BY id",
            (mark,),
        ).fetchall()
    ]


def assert_rejected_without_side_effects(
    auth: Authenticator, observer: Conn, case: NegativeCredential
) -> dict[str, Any]:
    before, mark = state_fingerprint(observer), _audit_mark(observer)
    result = auth.authenticate(case.credential)
    after, audit = state_fingerprint(observer), _audit_since(observer, mark)
    problems = []
    if result.session_id is not None:
        problems.append("SESSION_ISSUED")
    if result.reason != case.expected_reason:
        problems.append(f"REASON:{result.reason}!={case.expected_reason}")
    if after != before:
        problems.append("SESSION_OR_IDENTITY_STATE_CHANGED")
    if [(e, r) for e, _, r in audit] != [("authentication.failed", case.expected_reason)]:
        problems.append(f"AUDIT:{audit}")
    if case.credential and any(case.credential in str(col) for row in audit for col in row):
        problems.append("RAW_CREDENTIAL_IN_AUDIT")
    if problems:
        raise AssertionError(f"negative credential {case.name!r} not cleanly rejected: {problems}")
    return {"case": case.name, "reason": result.reason, "state_unchanged": True, "audit": audit}


def assert_authenticated(
    auth: Authenticator, observer: Conn, credential: str, subject: str
) -> dict[str, Any]:
    before, mark = state_fingerprint(observer), _audit_mark(observer)
    result = auth.authenticate(credential)
    audit = _audit_since(observer, mark)
    problems = []
    session = None
    if result.session_id is None or result.reason != OK:
        problems.append(f"NOT_AUTHENTICATED:{result.reason}")
    else:
        session = observer.execute(
            "SELECT subject, issued_at::text, expires_at::text FROM harness_auth.session"
            " WHERE id = %s",
            (result.session_id,),
        ).fetchone()
        if session is None or session[0] != subject:
            problems.append(f"SESSION_ROW:{session}")
    if state_fingerprint(observer)[0] != before[0] + 1:
        problems.append("SESSION_COUNT_NOT_PLUS_ONE")
    if audit != [("authentication.succeeded", subject, OK)]:
        problems.append(f"AUDIT:{audit}")
    if problems:
        raise AssertionError(f"valid credential not cleanly authenticated: {problems}")
    return {"session_id": str(result.session_id), "session": session, "audit": audit}

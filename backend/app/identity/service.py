"""MOD-007 IAM-01 service: registration, authentication, sessions, devices and step-up.

Decisions live in `app.identity.policy`; cryptography lives in `app.identity.secrets`. This module
reads rows, calls those, and writes the result.

**This file was rewritten after an independent security review found an account-takeover chain in
its first version.** The properties below are the ones that review showed were missing, so each is
stated with the mistake it exists to prevent:

* **Nothing the caller says about itself is believed.** A step-up presents credentials and this
  module verifies them; it does not accept a list of factor names. The first version took
  `factors` from the request body, so `{"factors": ["passkey_hardware"]}` bought AAL-3 from a
  password session, and the module's own test asserted that as correct behaviour.
* **Every operation on an identity requires a session belonging to that identity.** Enforced at
  the HTTP surface by `app.main`, which resolves the bearer token and compares. The first version
  left password changes, recovery-code issuing and session listing open to anyone holding the
  tenant UUID, which is a claim, not a secret.
* **A refusal is a refusal whatever caused it.** A locked account and a wrong password return the
  same status, the same body and comparable work -- the locked path runs the same dummy scrypt as
  the unknown-address path. The first version answered 423 in 1.7 ms against 401 in 49 ms, which
  told an attacker which addresses were registered and let them lock the owner out.
* **A risk challenge cannot be answered by repeating the request.** A device is recorded on first
  sight but is not *confirmed*, and only a confirmed device counts as known. The first version
  committed the device row in the challenged branch, so sending the same login twice skipped the
  challenge entirely.
* **A failure path commits before it refuses.** `tenant_scope` rolls back when the block raises,
  so an exception thrown inside it takes the failure's own evidence with it. See `_settled`.

Not implemented, and named rather than left to be discovered:

* **WebAuthn signature verification.** Enrolment keeps the credential, the public key and the
  signature counter, and the counter check is real clone detection. The signature is not verified,
  so **a passkey is not an authentication factor** and no code path accepts one as proof.
* **AAL-3 is unreachable.** It requires a hardware authenticator, which needs the verification
  above. `required_aal("privileged")` is 3, so a privileged action cannot be stepped up to today;
  that is the honest state rather than a level handed out on request.
* **TOTP enrolment**, for want of a vault to hold a reversible shared secret.
* **OIDC/SAML federation and SCIM** (IAM-01-R04): both need an external identity provider.
* **No rate limiting.** Lockout bounds guessing against one identity; nothing bounds request
  volume. A caller can still lock an account they know the address of, and `recover_with_code`
  remains the most expensive unauthenticated path. Both want a limiter this repository has not
  got, and the second now at least counts failures and respects the lock.
* **A refused bearer token writes no audit row.** Recording one would let anybody grow an
  insert-only table without limit. It wants the same rate limiter.
* **No outbox.** IAM-01's six events are written to `iam.auth_events`, the audit trail, but
  nothing publishes them to other modules.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from app.db import Pool, tenant_scope
from app.errors import Conflict, InvalidRequest, NotFound, ServiceError
from app.identity import policy, secrets

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.ASCII)
_PHONE = re.compile(r"^\+[1-9]\d{6,14}$", re.ASCII)
_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.ASCII
)

MIN_PASSWORD_LENGTH = 12

# One fixed hash to verify against when there is no credential to check, so a refusal costs what
# an acceptance costs. Built once at import; its plaintext is used nowhere else.
_DUMMY = secrets.hash_secret("dummy-credential-for-constant-time-failure")

PASSWORD = "password"
RECOVERY_CODE = "recovery_code"
VERIFIABLE_FACTORS = (PASSWORD, RECOVERY_CODE)
"""The only factors any code path accepts as proof. A passkey is not here, and saying its name
does not add it: `complete_step_up` takes credentials, never factor names."""


class AuthenticationFailed(ServiceError):
    """One code for every reason. Which part was wrong is not the caller's business.

    A locked identity, a wrong password, an unknown address, a suspended account and a malformed
    identifier all arrive here. Distinguishing them is what turns a login form into a directory.
    """

    status = 401


class StepUpRequired(ServiceError):
    status = 403


def _now() -> datetime:
    return datetime.now(UTC)


def _settled(outcome: tuple[dict[str, Any], ServiceError | None]) -> dict[str, Any]:
    """Raise the failure a transaction recorded, **after** that transaction has committed.

    This is load-bearing. `tenant_scope` rolls back when the block raises, so an exception thrown
    inside it takes the failure's own evidence down with it -- the attempt counter never climbs,
    the lock is never written, and `iam.auth_events` never learns that anyone tried. Lockout
    would be unreachable and the audit trail would show only successes.

    So every path that must both record something and refuse returns its error, and the caller
    raises it here once the write is durable. The inverse matters too: a path whose writes must
    *not* survive its refusal raises inside the block on purpose, and there are two --
    `register_identity` and `enroll_passkey`, where a conflict means nothing should be kept.
    """
    body, error = outcome
    if error is not None:
        raise error
    return body


def _require_uuid(value: str, field: str) -> str:
    """Reject a malformed identifier here rather than letting the database raise a 500."""
    if not _UUID.fullmatch(value.lower()):
        raise InvalidRequest(f"bad_{field}")
    return value.lower()


def normalize_email(value: str) -> str:
    cleaned = value.strip().lower()
    if not _EMAIL.fullmatch(cleaned):
        raise InvalidRequest("bad_email")
    return cleaned


def normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[\s()-]", "", value.strip())
    if not _PHONE.fullmatch(cleaned):
        raise InvalidRequest("bad_phone")
    return cleaned


def validate_password(password: str) -> str:
    """One floor, applied wherever a password is set.

    The first version checked the length in `set_password` and not in `register_identity`, so a
    one-character password could be registered and then used; only changing it was constrained.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidRequest("password_too_short")
    return password


def _event(
    conn: Connection[Any], tenant_id: str, *, kind: str, outcome: str, correlation_id: str,
    identity_id: str | None = None, factor: str | None = None, device_id: str | None = None,
    session_id: str | None = None, reason: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO iam.auth_events
            (tenant_id, identity_id, kind, outcome, factor, device_id, session_id, reason,
             correlation_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (tenant_id, identity_id, kind, outcome, factor, device_id, session_id, reason,
         correlation_id),
    )


# --------------------------------------------------------------------------- credentials

def _store_credential(
    conn: Connection[Any], tenant_id: str, identity_id: str, kind: str,
    hashed: secrets.HashedSecret,
) -> str:
    row = conn.execute(
        """
        INSERT INTO iam.credentials
            (tenant_id, identity_id, kind, algorithm, salt, secret_hash, params)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING credential_id
        """,
        (tenant_id, identity_id, kind, hashed.algorithm, hashed.salt, hashed.digest,
         Jsonb(secrets.serialize_params(hashed.params))),
    ).fetchone()
    assert row is not None
    return str(row[0])


def _load(row: tuple[Any, ...], offset: int = 0) -> secrets.HashedSecret:
    return secrets.HashedSecret(
        algorithm=row[offset], salt=bytes(row[offset + 1]), digest=bytes(row[offset + 2]),
        params={k: int(v) for k, v in row[offset + 3].items()},
    )


def _active_password(
    conn: Connection[Any], identity_id: str
) -> tuple[str, secrets.HashedSecret] | None:
    row = conn.execute(
        "SELECT credential_id, algorithm, salt, secret_hash, params FROM iam.credentials"
        " WHERE identity_id = %s AND kind = 'password' AND status = 'active'",
        (identity_id,),
    ).fetchone()
    return (str(row[0]), _load(tuple(row), 1)) if row is not None else None


def _verify_password(conn: Connection[Any], identity_id: str, candidate: str) -> bool:
    """Check a password, always paying for one scrypt whether or not one is stored."""
    stored = _active_password(conn, identity_id)
    if stored is None:
        secrets.verify_secret(_DUMMY, candidate or "x")
        return False
    return secrets.verify_secret(stored[1], candidate)


def _match_recovery_code(conn: Connection[Any], identity_id: str, candidate: str) -> str | None:
    """Find the active recovery code matching this candidate. **Does not consume it.**

    Verifying and burning used to be one step, so a step-up that verified a code and was then
    refused for some other reason destroyed it anyway -- a recovered user lost one code per
    attempt at a password reset they could never complete. The caller consumes only once it has
    decided to accept.
    """
    rows = conn.execute(
        "SELECT credential_id, algorithm, salt, secret_hash, params FROM iam.credentials"
        " WHERE identity_id = %s AND kind = 'recovery_code' AND status = 'active'",
        (identity_id,),
    ).fetchall()
    if not rows:
        secrets.verify_secret(_DUMMY, candidate or "x")
        return None
    for row in rows:
        if secrets.verify_secret(_load(tuple(row), 1), candidate):
            return str(row[0])
    return None


def _consume_credential(conn: Connection[Any], credential_id: str, now: datetime) -> None:
    conn.execute(
        "UPDATE iam.credentials SET status = 'consumed', consumed_at = %s"
        " WHERE credential_id = %s",
        (now, credential_id),
    )


def _lock_state(conn: Connection[Any], identity_id: str) -> tuple[policy.LockoutState,
                                                                  policy.LockoutState]:
    row = conn.execute(
        "SELECT failed_attempts, locked_until, recovery_failed_attempts, recovery_locked_until"
        " FROM iam.identities WHERE identity_id = %s",
        (identity_id,),
    ).fetchone()
    if row is None:
        raise NotFound("identity_not_found")
    return (policy.LockoutState(int(row[0]), row[1]),
            policy.LockoutState(int(row[2]), row[3]))


def _count_password_failure(conn: Connection[Any], tenant_id: str, identity_id: str,
                            now: datetime, reason: str, correlation_id: str) -> None:
    password_lock, _ = _lock_state(conn, identity_id)
    after = policy.after_failure(password_lock, now)
    conn.execute(
        "UPDATE iam.identities SET failed_attempts = %s, locked_until = %s,"
        " version = version + 1 WHERE identity_id = %s",
        (after.failed_attempts, after.locked_until, identity_id),
    )
    _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
           identity_id=identity_id, factor=PASSWORD, reason=reason,
           correlation_id=correlation_id)
    if policy.locked(after, now):
        _event(conn, tenant_id, kind="identity.locked", outcome="failed",
               identity_id=identity_id, reason="too_many_failures",
               correlation_id=correlation_id)


def _count_recovery_failure(conn: Connection[Any], tenant_id: str, identity_id: str,
                            now: datetime, reason: str, correlation_id: str) -> None:
    _, recovery_lock = _lock_state(conn, identity_id)
    after = policy.after_failure(recovery_lock, now)
    conn.execute(
        "UPDATE iam.identities SET recovery_failed_attempts = %s, recovery_locked_until = %s,"
        " version = version + 1 WHERE identity_id = %s",
        (after.failed_attempts, after.locked_until, identity_id),
    )
    _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
           identity_id=identity_id, factor=RECOVERY_CODE, reason=reason,
           correlation_id=correlation_id)
    if policy.locked(after, now):
        _event(conn, tenant_id, kind="identity.locked", outcome="failed",
               identity_id=identity_id, reason="too_many_recovery_failures",
               correlation_id=correlation_id)


def _verify_presented(
    conn: Connection[Any], tenant_id: str, identity_id: str, *, now: datetime,
    correlation_id: str, password: str | None = None, recovery_code: str | None = None,
) -> tuple[list[str], str | None, ServiceError | None]:
    """Verify whatever was presented, **metered**: locks are read and failures are counted.

    Every re-authentication path goes through here -- step-up, a password change, issuing
    recovery codes. They used to call the verifier directly, which made a stolen session token an
    unmetered password oracle at twenty guesses a second against the very credential the
    "current password required" rule exists to protect, with no lock and no sign of one.

    Returns the factor kinds that verified, the recovery credential to consume if the caller
    accepts, and an error when the identity is locked out.
    """
    password_lock, recovery_lock = _lock_state(conn, identity_id)
    verified: list[str] = []
    pending_code: str | None = None

    if password is not None:
        if policy.locked(password_lock, now):
            secrets.verify_secret(_DUMMY, password or "x")
            return [], None, AuthenticationFailed("authentication_failed")
        if _verify_password(conn, identity_id, password):
            verified.append(PASSWORD)
        else:
            _count_password_failure(conn, tenant_id, identity_id, now, "bad_password",
                                    correlation_id)
            return [], None, AuthenticationFailed("authentication_failed")

    if recovery_code is not None:
        if policy.locked(recovery_lock, now):
            secrets.verify_secret(_DUMMY, recovery_code or "x")
            return [], None, AuthenticationFailed("authentication_failed")
        pending_code = _match_recovery_code(conn, identity_id, recovery_code)
        if pending_code is None:
            _count_recovery_failure(conn, tenant_id, identity_id, now, "bad_code",
                                    correlation_id)
            return [], None, AuthenticationFailed("authentication_failed")
        verified.append(RECOVERY_CODE)

    return verified, pending_code, None


def _rehash_if_weak(conn: Connection[Any], tenant_id: str, identity_id: str,
                    credential_id: str, stored: secrets.HashedSecret, password: str) -> None:
    """Re-hash a verified password that was stored under weaker parameters.

    This is what makes `secrets.DEFAULT_SCRYPT_PARAMS` raisable without invalidating everyone at
    once -- and without a caller it was only a claim in a docstring, which is what the review
    found. The old row is revoked rather than deleted, so the change stays visible.
    """
    if not secrets.needs_rehash(stored):
        return
    conn.execute(
        "UPDATE iam.credentials SET status = 'revoked', revoked_at = now()"
        " WHERE credential_id = %s",
        (credential_id,),
    )
    _store_credential(conn, tenant_id, identity_id, PASSWORD, secrets.hash_secret(password))


# --------------------------------------------------------------------------- identities

def register_identity(
    pool: Pool,
    tenant_id: str,
    *,
    display_name: str,
    correlation_id: str,
    email: str | None = None,
    phone: str | None = None,
    password: str | None = None,
    person_id: str | None = None,
) -> dict[str, Any]:
    """RegisterIdentity (IAM-01-R01).

    `person_id` links this identity to one in another tenant, which is how one human holds roles
    in several tenants without being duplicated. It is a bare key with no table behind it: see the
    migration for why a foreign key there would secure nothing.
    """
    _require_uuid(correlation_id, "correlation_id")
    if not display_name.strip():
        raise InvalidRequest("bad_display_name")
    if email is None and phone is None:
        raise InvalidRequest("identity_needs_an_email_or_phone")
    email_normalized = normalize_email(email) if email else None
    phone_normalized = normalize_phone(phone) if phone else None
    hashed = secrets.hash_secret(validate_password(password)) if password else None
    if person_id is not None:
        _require_uuid(person_id, "person_id")

    with tenant_scope(pool, tenant_id) as conn:
        columns = "tenant_id, email_normalized, phone_normalized, display_name"
        values: tuple[Any, ...] = (tenant_id, email_normalized, phone_normalized, display_name)
        if person_id is not None:
            columns += ", person_id"
            values += (person_id,)
        try:
            row = conn.execute(
                f"INSERT INTO iam.identities ({columns})"  # noqa: S608 - fixed column names
                f" VALUES ({', '.join(['%s'] * len(values))})"
                f" RETURNING identity_id, person_id",
                values,
            ).fetchone()
        except errors.UniqueViolation:
            # Raised inside the block on purpose: nothing about a rejected registration should
            # survive it.
            raise Conflict("identifier_already_registered") from None
        except errors.ForeignKeyViolation:
            raise NotFound("tenant_not_found") from None
        except errors.CheckViolation:
            raise InvalidRequest("bad_identity") from None
        assert row is not None
        identity_id, created_person = str(row[0]), str(row[1])

        if hashed is not None:
            _store_credential(conn, tenant_id, identity_id, PASSWORD, hashed)
        _event(conn, tenant_id, kind="identity.created", outcome="succeeded",
               identity_id=identity_id, correlation_id=correlation_id)
    return {"identity_id": identity_id, "person_id": created_person,
            "email": email_normalized, "phone": phone_normalized,
            "display_name": display_name, "has_password": hashed is not None}


def _require_identity(conn: Connection[Any], identity_id: str) -> tuple[Any, ...]:
    row = conn.execute(
        "SELECT identity_id, status, failed_attempts, locked_until, version"
        " FROM iam.identities WHERE identity_id = %s",
        (identity_id,),
    ).fetchone()
    if row is None:
        raise NotFound("identity_not_found")
    return tuple(row)


def set_password(
    pool: Pool,
    tenant_id: str,
    *,
    identity_id: str,
    password: str,
    correlation_id: str,
    current_password: str | None = None,
    session_factors: list[str] | None = None,
    session_aal: int = policy.AAL_ROUTINE,
) -> dict[str, Any]:
    """Replace a password, and log every session out, this one included.

    **Something must be proved beyond holding the session**: the current password, an elevated
    session, or a session opened with a recovery code. A session cookie alone must not be enough
    to take an account over permanently, which is what the first version allowed.

    The recovery allowance is not a loophole, it is the point of recovery: somebody who forgot
    their password proves possession of a single-use code and then sets a new one. Without it a
    recovered user could never reset -- they had no current password to give, could not step up
    because a second recovery code is the same kind of factor, and burned a code on every
    attempt until the account was unreachable. That was the second blocking defect of review
    round two.
    """
    _require_uuid(correlation_id, "correlation_id")
    validate_password(password)
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _set_password_in_tx(
            conn, tenant_id, identity_id=identity_id, password=password,
            correlation_id=correlation_id, current_password=current_password,
            session_factors=session_factors or [], session_aal=session_aal,
        )
    return _settled(outcome)


def _set_password_in_tx(
    conn: Connection[Any], tenant_id: str, *, identity_id: str, password: str,
    correlation_id: str, current_password: str | None, session_factors: list[str],
    session_aal: int,
) -> tuple[dict[str, Any], ServiceError | None]:
    now = _now()
    failed: dict[str, Any] = {}
    _require_identity(conn, identity_id)
    has_password = _active_password(conn, identity_id) is not None
    already_proved = (session_aal >= policy.AAL_ELEVATED
                      or RECOVERY_CODE in session_factors)

    if has_password and not already_proved:
        if current_password is None:
            return failed, AuthenticationFailed("authentication_failed")
        _, _, error = _verify_presented(conn, tenant_id, identity_id, now=now,
                                        correlation_id=correlation_id,
                                        password=current_password)
        if error is not None:
            return failed, error

    conn.execute(
        "UPDATE iam.credentials SET status = 'revoked', revoked_at = %s"
        " WHERE identity_id = %s AND kind = 'password' AND status = 'active'",
        (now, identity_id),
    )
    credential_id = _store_credential(conn, tenant_id, identity_id, PASSWORD,
                                      secrets.hash_secret(password))
    revoked = _revoke_chain(conn, tenant_id, identity_id, now, "password_changed")
    _event(conn, tenant_id, kind="password.changed", outcome="succeeded",
           identity_id=identity_id, factor=PASSWORD, correlation_id=correlation_id)
    return ({"identity_id": identity_id, "credential_id": credential_id,
             "sessions_revoked": revoked}, None)


# --------------------------------------------------------------------------- authentication

def _find_identity(conn: Connection[Any], identifier: str) -> tuple[Any, ...] | None:
    column = "email_normalized" if "@" in identifier else "phone_normalized"
    try:
        value = normalize_email(identifier) if column == "email_normalized" \
            else normalize_phone(identifier)
    except InvalidRequest:
        return None
    row = conn.execute(
        f"SELECT identity_id, status, failed_attempts, locked_until,"  # noqa: S608 - fixed column
        f" recovery_failed_attempts, recovery_locked_until"
        f" FROM iam.identities WHERE {column} = %s",
        (value,),
    ).fetchone()
    return tuple(row) if row is not None else None


def _has_second_factor(conn: Connection[Any], identity_id: str) -> bool:
    """Whether this identity has anything it could answer a challenge with.

    Recovery codes count: a password plus a code is two kinds of thing. A passkey does not, and
    will not until its signature is verified somewhere.
    """
    row = conn.execute(
        "SELECT count(*) FROM iam.credentials"
        " WHERE identity_id = %s AND kind = 'recovery_code' AND status = 'active'",
        (identity_id,),
    ).fetchone()
    assert row is not None
    return int(row[0]) > 0


def authenticate(
    pool: Pool,
    tenant_id: str,
    *,
    identifier: str,
    password: str,
    correlation_id: str,
    device_fingerprint: str | None = None,
    device_label: str | None = None,
) -> dict[str, Any]:
    """Authenticate (IAM-01-R02), returning a session token exactly once.

    Order is deliberate: the lock is read before the password is checked, every refusal costs one
    scrypt and returns the same 401, a revoked device is refused outright, and a risk challenge
    leaves the device unconfirmed so that repeating the request cannot answer it.
    """
    _require_uuid(correlation_id, "correlation_id")
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _authenticate_in_tx(
            conn, tenant_id, identifier=identifier, password=password,
            correlation_id=correlation_id, device_fingerprint=device_fingerprint,
            device_label=device_label,
        )
    return _settled(outcome)


def _authenticate_in_tx(
    conn: Connection[Any],
    tenant_id: str,
    *,
    identifier: str,
    password: str,
    correlation_id: str,
    device_fingerprint: str | None,
    device_label: str | None,
) -> tuple[dict[str, Any], ServiceError | None]:
    now = _now()
    failed: dict[str, Any] = {}
    refused = AuthenticationFailed("authentication_failed")
    found = _find_identity(conn, identifier)

    if found is None:
        secrets.verify_secret(_DUMMY, password or "x")
        _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
               factor=PASSWORD, reason="unknown_identifier", correlation_id=correlation_id)
        return failed, refused

    identity_id, status, failed_attempts, locked_until = (
        str(found[0]), found[1], int(found[2]), found[3],
    )
    lock = policy.LockoutState(failed_attempts=failed_attempts, locked_until=locked_until)

    if policy.locked(lock, now) or status != "active":
        # Same work, same status, same body as a wrong password. The first version answered 423
        # here in under two milliseconds, which identified every registered address in five
        # requests and let the attacker keep the owner locked out.
        secrets.verify_secret(_DUMMY, password or "x")
        _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
               identity_id=identity_id, factor=PASSWORD,
               reason="locked" if policy.locked(lock, now) else f"status_{status}",
               correlation_id=correlation_id)
        return failed, refused

    stored = _active_password(conn, identity_id)
    if stored is None or not secrets.verify_secret(stored[1], password):
        after = policy.after_failure(lock, now)
        conn.execute(
            "UPDATE iam.identities SET failed_attempts = %s, locked_until = %s,"
            " version = version + 1 WHERE identity_id = %s",
            (after.failed_attempts, after.locked_until, identity_id),
        )
        _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
               identity_id=identity_id, factor=PASSWORD, reason="bad_password",
               correlation_id=correlation_id)
        if policy.locked(after, now):
            _event(conn, tenant_id, kind="identity.locked", outcome="failed",
                   identity_id=identity_id, reason="too_many_failures",
                   correlation_id=correlation_id)
        return failed, refused

    device = _touch_device(conn, tenant_id, identity_id, device_fingerprint, device_label, now)
    if device.revoked:
        _event(conn, tenant_id, kind="device.readmission_refused", outcome="failed",
               identity_id=identity_id, device_id=device.device_id, factor=PASSWORD,
               reason="device_revoked", correlation_id=correlation_id)
        return failed, refused

    _rehash_if_weak(conn, tenant_id, identity_id, stored[0], stored[1], password)

    signals = policy.RiskSignals(known_device=device.known, recent_failures=failed_attempts)
    challenged, why = policy.risk_requires_challenge(signals)
    if challenged and not _has_second_factor(conn, identity_id):
        # Every first login is from an unknown device, so an unconditional challenge would lock
        # out anyone holding only a password -- there would be nothing to answer it with. The
        # signal is recorded on the success event instead, and the device is confirmed because
        # this login is the best evidence available.
        challenged, why = False, f"{why}_unanswerable_no_second_factor"

    if challenged:
        # Nothing about the attempt is cleared and the device stays unconfirmed, so repeating
        # this exact request reaches this branch again rather than skipping past it.
        nonce = secrets.mint_nonce()
        conn.execute(
            """
            INSERT INTO iam.challenges
                (tenant_id, identity_id, device_id, kind, nonce_hash, required_aal, expires_at)
            VALUES (%s, %s, %s, 'risk', %s, %s, %s)
            """,
            (tenant_id, identity_id, device.device_id, nonce.digest, policy.AAL_ELEVATED,
             policy.challenge_expiry(now)),
        )
        _event(conn, tenant_id, kind="risk.challenge.required", outcome="failed",
               identity_id=identity_id, factor=PASSWORD, device_id=device.device_id, reason=why,
               correlation_id=correlation_id)
        return ({"authenticated": False, "challenge_required": True, "reason": why,
                 "challenge": nonce.token, "identity_id": identity_id,
                 "device_id": device.device_id}, None)

    _confirm_device(conn, device.device_id, now)
    cleared = policy.after_success(lock)
    conn.execute(
        "UPDATE iam.identities SET failed_attempts = %s, locked_until = NULL,"
        " version = version + 1 WHERE identity_id = %s",
        (cleared.failed_attempts, identity_id),
    )
    session = _open_session(conn, tenant_id, identity_id, device.device_id, [PASSWORD], now)
    _event(conn, tenant_id, kind="authentication.succeeded", outcome="succeeded",
           identity_id=identity_id, factor=PASSWORD, device_id=device.device_id,
           session_id=session["session_id"],
           reason=None if why == "no_signal" else why, correlation_id=correlation_id)
    return ({"authenticated": True, "challenge_required": False, **session,
             "identity_id": identity_id, "device_id": device.device_id}, None)


def complete_login_challenge(
    pool: Pool,
    tenant_id: str,
    *,
    identifier: str,
    challenge: str,
    recovery_code: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Answer the challenge `authenticate` raised, and finish logging in (IAM-01-R03).

    The first version had no route for this at all: the nonce it returned was consumable only by
    the step-up endpoint, which needs a bearer token the caller does not yet have. So an honest
    user could not answer the challenge and an attacker did not have to.

    The challenge nonce is itself the evidence that the password step succeeded -- it is issued
    only after a correct password, is single use, and expires in minutes -- so a recovery code
    presented here is the second factor and the session opens at level 2.
    """
    _require_uuid(correlation_id, "correlation_id")
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _login_challenge_in_tx(
            conn, tenant_id, identifier=identifier, challenge=challenge,
            recovery_code=recovery_code, correlation_id=correlation_id,
        )
    return _settled(outcome)


def _login_challenge_in_tx(
    conn: Connection[Any], tenant_id: str, *, identifier: str, challenge: str,
    recovery_code: str, correlation_id: str,
) -> tuple[dict[str, Any], ServiceError | None]:
    now = _now()
    failed: dict[str, Any] = {}
    refused = AuthenticationFailed("authentication_failed")
    found = _find_identity(conn, identifier)
    if found is None:
        secrets.verify_secret(_DUMMY, recovery_code or "x")
        return failed, refused
    identity_id, status = str(found[0]), found[1]
    if status != "active":
        secrets.verify_secret(_DUMMY, recovery_code or "x")
        return failed, refused

    pending = _pending_challenge(conn, identity_id, challenge, "risk", now)
    if pending is None:
        _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
               identity_id=identity_id, reason="challenge_invalid",
               correlation_id=correlation_id)
        return failed, refused
    challenge_id, challenge_device = pending

    # A wrong code here spends the **recovery** budget, not the password one. The mistake is a
    # mistyped recovery code, and charging it to the password counter would lock the ordinary
    # login of somebody already struggling to get in.
    verified, pending_code, error = _verify_presented(
        conn, tenant_id, identity_id, now=now, correlation_id=correlation_id,
        recovery_code=recovery_code,
    )
    if error is not None:
        return failed, error
    assert pending_code is not None
    _consume_credential(conn, pending_code, now)

    conn.execute("UPDATE iam.challenges SET consumed_at = %s WHERE challenge_id = %s",
                 (now, challenge_id))
    # **The device the challenge was issued for**, not whichever was seen most recently. With no
    # binding, an attacker holding the password kept their own device newest by retrying, and the
    # victim answering their own challenge whitelisted the attacker's device instead of their
    # own. That was the first blocking defect of review round two.
    _confirm_device(conn, challenge_device, now)
    conn.execute(
        "UPDATE iam.identities SET failed_attempts = 0, locked_until = NULL,"
        " recovery_failed_attempts = 0, recovery_locked_until = NULL,"
        " version = version + 1 WHERE identity_id = %s",
        (identity_id,),
    )
    session = _open_session(conn, tenant_id, identity_id, challenge_device,
                            [PASSWORD, RECOVERY_CODE], now)
    _event(conn, tenant_id, kind="authentication.succeeded", outcome="succeeded",
           identity_id=identity_id, factor=f"{PASSWORD}+{RECOVERY_CODE}",
           device_id=challenge_device, session_id=session["session_id"],
           reason="risk_challenge_answered", correlation_id=correlation_id)
    return ({"authenticated": True, "challenge_required": False, **session,
             "identity_id": identity_id, "device_id": challenge_device}, None)


# --------------------------------------------------------------------------- devices

class _Device:
    __slots__ = ("device_id", "known", "revoked")

    def __init__(self, device_id: str | None, known: bool, revoked: bool) -> None:
        self.device_id, self.known, self.revoked = device_id, known, revoked


def _touch_device(
    conn: Connection[Any], tenant_id: str, identity_id: str, fingerprint: str | None,
    label: str | None, now: datetime,
) -> _Device:
    """Record the device and report whether it is known, and whether it is revoked.

    **Created is not confirmed.** A row appears on first sight so the login can be attributed,
    but `known` stays false until `confirmed_at` is set, which happens only on a login that did
    not need a challenge or on one whose challenge was answered. The first version returned a
    freshly created device as merely unknown and committed it in the challenged branch, so the
    identical next request found it and sailed through.

    A caller that sends no fingerprint is never known: treating an absent device as trusted would
    let anyone skip the challenge by omitting a field.
    """
    if not fingerprint:
        return _Device(None, False, False)
    row = conn.execute(
        "SELECT device_id, revoked_at, confirmed_at FROM iam.devices"
        " WHERE identity_id = %s AND fingerprint = %s",
        (identity_id, fingerprint),
    ).fetchone()
    if row is None:
        created = conn.execute(
            "INSERT INTO iam.devices (tenant_id, identity_id, fingerprint, label)"
            " VALUES (%s, %s, %s, %s) RETURNING device_id",
            (tenant_id, identity_id, fingerprint, label),
        ).fetchone()
        assert created is not None
        return _Device(str(created[0]), False, False)
    device_id = str(row[0])
    if row[1] is not None:
        return _Device(device_id, False, True)
    conn.execute("UPDATE iam.devices SET last_seen_at = %s WHERE device_id = %s",
                 (now, device_id))
    return _Device(device_id, row[2] is not None, False)


def _confirm_device(conn: Connection[Any], device_id: str | None, now: datetime) -> None:
    if device_id is None:
        return
    conn.execute(
        "UPDATE iam.devices SET confirmed_at = coalesce(confirmed_at, %s)"
        " WHERE device_id = %s AND revoked_at IS NULL",
        (now, device_id),
    )


def revoke_device(
    pool: Pool, tenant_id: str, *, device_id: str, identity_id: str, correlation_id: str,
    reason: str = "revoked_by_user",
) -> dict[str, Any]:
    """RevokeDevice (IAM-01-R05): the device and every session on it, in one transaction.

    Idempotent, and permanent. A revoked device is refused at login -- `_authenticate_in_tx`
    checks it before anything else succeeds -- so the stolen phone cannot simply sign in again
    with the password it already knows. The first version revoked the sessions, left the
    fingerprint usable, and then answered 404 when the owner pressed the button a second time.
    """
    _require_uuid(correlation_id, "correlation_id")
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        existing = conn.execute(
            "SELECT identity_id, revoked_at FROM iam.devices WHERE device_id = %s",
            (device_id,),
        ).fetchone()
        if existing is None or str(existing[0]) != identity_id:
            # Same answer for "no such device" and "not yours": whether a device id exists in
            # this tenant is not something a caller gets to probe.
            raise NotFound("device_not_found")
        already = existing[1]
        if already is not None:
            return {"device_id": device_id, "revoked": True, "sessions_revoked": 0,
                    "already_revoked": True}
        conn.execute(
            "UPDATE iam.devices SET revoked_at = %s, revoked_reason = %s, trusted = false,"
            " trusted_at = NULL, confirmed_at = NULL WHERE device_id = %s",
            (now, reason, device_id),
        )
        killed = conn.execute(
            "UPDATE iam.sessions SET revoked_at = %s, revoke_reason = 'device_revoked'"
            " WHERE device_id = %s AND revoked_at IS NULL RETURNING session_id",
            (now, device_id),
        ).fetchall()
        _event(conn, tenant_id, kind="device.revoked", outcome="succeeded",
               identity_id=identity_id, device_id=device_id, reason=reason,
               correlation_id=correlation_id)
    return {"device_id": device_id, "revoked": True, "sessions_revoked": len(killed),
            "already_revoked": False}


def trust_device(
    pool: Pool, tenant_id: str, *, device_id: str, identity_id: str, correlation_id: str
) -> dict[str, Any]:
    """Mark a device trusted so it stops drawing a risk challenge (IAM-01-R03)."""
    _require_uuid(correlation_id, "correlation_id")
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "UPDATE iam.devices SET trusted = true, trusted_at = %s,"
            " confirmed_at = coalesce(confirmed_at, %s)"
            " WHERE device_id = %s AND identity_id = %s AND revoked_at IS NULL"
            " RETURNING identity_id",
            (now, now, device_id, identity_id),
        ).fetchone()
        if row is None:
            raise NotFound("device_not_found_or_revoked")
        _event(conn, tenant_id, kind="device.trusted", outcome="succeeded",
               identity_id=identity_id, device_id=device_id, correlation_id=correlation_id)
    return {"device_id": device_id, "trusted": True}


def list_devices(pool: Pool, tenant_id: str, *, identity_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        _require_identity(conn, identity_id)
        rows = conn.execute(
            "SELECT device_id, label, platform, trusted, confirmed_at, first_seen_at,"
            " last_seen_at, revoked_at, revoked_reason FROM iam.devices"
            " WHERE identity_id = %s ORDER BY first_seen_at",
            (identity_id,),
        ).fetchall()
    return [
        {"device_id": str(r[0]), "label": r[1], "platform": r[2], "trusted": bool(r[3]),
         "confirmed": r[4] is not None, "first_seen_at": r[5].isoformat(),
         "last_seen_at": r[6].isoformat(), "revoked_at": r[7].isoformat() if r[7] else None,
         "revoked_reason": r[8]}
        for r in rows
    ]


# --------------------------------------------------------------------------- sessions

def _open_session(
    conn: Connection[Any], tenant_id: str, identity_id: str, device_id: str | None,
    factors: list[str], now: datetime, rotated_from: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Open a session at the level its **verified** factors reach.

    `expires_at` overrides the computed lifetime, and rotation passes it so that an elevated
    session keeps its original deadline. Without that, rotating every twelve hours held level 2
    forever without re-presenting a factor, while `policy.SESSION_LIFETIME` claimed a stepped-up
    session was "a window opened for one job, not a state the user stays in".
    """
    unknown = set(factors) - set(VERIFIABLE_FACTORS)
    if unknown:
        raise InvalidRequest("unverifiable_factor")
    aal = policy.assurance_for(factors)
    minted = secrets.mint_session_token()
    row = conn.execute(
        """
        INSERT INTO iam.sessions
            (tenant_id, identity_id, device_id, token_hash, aal, factors, issued_at,
             expires_at, rotated_from)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING session_id, expires_at
        """,
        (tenant_id, identity_id, device_id, minted.digest, aal, sorted(set(factors)), now,
         expires_at or policy.session_expiry(now, aal, factors), rotated_from),
    ).fetchone()
    assert row is not None
    # The token leaves here and is never recoverable afterwards.
    return {"session_id": str(row[0]), "token": minted.token, "aal": aal,
            "factors": sorted(set(factors)), "expires_at": row[1].isoformat()}


def _session_by_token(conn: Connection[Any], token: str) -> tuple[Any, ...]:
    """Resolve a bearer token, refusing unless its identity is still active.

    The status check lives **here**, where every caller passes, rather than in `resolve_session`.
    It was in that one function, so `/auth/rotate` and `/auth/step-up` -- which resolve a token
    directly -- let a suspended identity refresh its token indefinitely and raise its own
    assurance level, keeping the chain alive until the suspension was lifted.
    """
    row = conn.execute(
        "SELECT s.session_id, s.identity_id, s.device_id, s.aal, s.expires_at, s.revoked_at,"
        " s.rotated_from, s.factors, i.status"
        " FROM iam.sessions s JOIN iam.identities i ON i.identity_id = s.identity_id"
        " WHERE s.token_hash = %s",
        (secrets.digest_token(token),),
    ).fetchone()
    if row is None or row[8] != "active":
        raise AuthenticationFailed("authentication_failed")
    return tuple(row)


def resolve_session(pool: Pool, tenant_id: str, *, token: str) -> dict[str, Any]:
    """Who a bearer token belongs to, or refuse. The token is never echoed back."""
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = _session_by_token(conn, token)
        state = policy.SessionState(aal=int(row[3]), expires_at=row[4], revoked_at=row[5])
        usable, why = policy.session_usable(state, now)
        if not usable:
            raise AuthenticationFailed("authentication_failed")
        conn.execute("UPDATE iam.sessions SET last_seen_at = %s WHERE session_id = %s",
                     (now, row[0]))
    return {"session_id": str(row[0]), "identity_id": str(row[1]),
            "device_id": str(row[2]) if row[2] else None, "aal": int(row[3]),
            "factors": list(row[7]), "expires_at": row[4].isoformat(), "reason": why,
            # The tenant the session was resolved under. Defence in depth rather than a fix:
            # row-level security already means a token from another tenant does not resolve at
            # all. What it buys is that a caller downstream reads the tenant from the resolved
            # session instead of re-reading the header, so the two cannot drift.
            "tenant_id": tenant_id}


def rotate_session(
    pool: Pool, tenant_id: str, *, token: str, correlation_id: str
) -> dict[str, Any]:
    """RotateSession (IAM-01-R05), with reuse detection.

    Reuse means a *successor exists* -- somebody rotated this token and somebody is presenting it
    again, so two parties hold it. A session that was merely revoked (signed out, superseded by a
    password change) is refused on its own without burning the rest: the first version treated the
    two alike, so an ordinary sign-out followed by one stale refresh logged the user out
    everywhere and wrote a fabricated security incident into the audit trail.
    """
    _require_uuid(correlation_id, "correlation_id")
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _rotate_in_tx(conn, tenant_id, token=token, correlation_id=correlation_id)
    return _settled(outcome)


def _rotate_in_tx(
    conn: Connection[Any], tenant_id: str, *, token: str, correlation_id: str
) -> tuple[dict[str, Any], ServiceError | None]:
    now = _now()
    failed: dict[str, Any] = {}
    row = _session_by_token(conn, token)
    session_id, identity_id, device_id, aal, expires_at, revoked_at, factors = (
        str(row[0]), str(row[1]), str(row[2]) if row[2] else None, int(row[3]), row[4],
        row[5], list(row[7]),
    )
    successor = conn.execute(
        "SELECT session_id FROM iam.sessions WHERE rotated_from = %s", (session_id,)
    ).fetchone()
    if successor is not None:
        _revoke_chain(conn, tenant_id, identity_id, now, "token_reuse_detected")
        _event(conn, tenant_id, kind="session.revoked", outcome="failed",
               identity_id=identity_id, session_id=session_id, reason="token_reuse_detected",
               correlation_id=correlation_id)
        return failed, AuthenticationFailed("authentication_failed")

    state = policy.SessionState(aal=aal, expires_at=expires_at, revoked_at=revoked_at)
    usable, _ = policy.session_usable(state, now)
    if not usable:
        return failed, AuthenticationFailed("authentication_failed")

    # A session whose window is fixed -- elevated, or routine but carrying a reset capability --
    # keeps the deadline it started with. Only an ordinary routine session gets a fresh window,
    # which is what rotation is for.
    carried = expires_at if policy.window_is_fixed(aal, factors) else None
    fresh = _open_session(conn, tenant_id, identity_id, device_id, factors, now,
                          rotated_from=session_id, expires_at=carried)
    conn.execute(
        "UPDATE iam.sessions SET revoked_at = %s, revoke_reason = 'rotated'"
        " WHERE session_id = %s",
        (now, session_id),
    )
    _event(conn, tenant_id, kind="session.rotated", outcome="succeeded",
           identity_id=identity_id, session_id=fresh["session_id"],
           correlation_id=correlation_id)
    return {**fresh, "identity_id": identity_id, "rotated_from": session_id}, None


def _revoke_chain(
    conn: Connection[Any], tenant_id: str, identity_id: str, now: datetime, reason: str
) -> int:
    """Revoke every live session for an identity. There is deliberately no way to spare one."""
    rows = conn.execute(
        "UPDATE iam.sessions SET revoked_at = %s, revoke_reason = %s"
        " WHERE identity_id = %s AND revoked_at IS NULL RETURNING session_id",
        (now, reason, identity_id),
    ).fetchall()
    return len(rows)


def list_sessions(pool: Pool, tenant_id: str, *, identity_id: str) -> list[dict[str, Any]]:
    """Session inventory (IAM-01-R05). No token or digest is ever returned."""
    with tenant_scope(pool, tenant_id) as conn:
        _require_identity(conn, identity_id)
        rows = conn.execute(
            "SELECT session_id, device_id, aal, factors, issued_at, expires_at, last_seen_at,"
            " revoked_at, revoke_reason FROM iam.sessions WHERE identity_id = %s"
            " ORDER BY issued_at DESC",
            (identity_id,),
        ).fetchall()
    return [
        {"session_id": str(r[0]), "device_id": str(r[1]) if r[1] else None, "aal": int(r[2]),
         "factors": list(r[3]), "issued_at": r[4].isoformat(), "expires_at": r[5].isoformat(),
         "last_seen_at": r[6].isoformat() if r[6] else None,
         "revoked_at": r[7].isoformat() if r[7] else None, "revoke_reason": r[8]}
        for r in rows
    ]


def revoke_session(
    pool: Pool, tenant_id: str, *, session_id: str, identity_id: str, correlation_id: str,
    reason: str = "revoked_by_user",
) -> dict[str, Any]:
    """Revoke one session. Only the identity that owns it may."""
    _require_uuid(correlation_id, "correlation_id")
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "UPDATE iam.sessions SET revoked_at = %s, revoke_reason = %s"
            " WHERE session_id = %s AND identity_id = %s AND revoked_at IS NULL"
            " RETURNING identity_id",
            (now, reason, session_id, identity_id),
        ).fetchone()
        if row is None:
            raise NotFound("session_not_found_or_already_revoked")
        _event(conn, tenant_id, kind="session.revoked", outcome="succeeded",
               identity_id=identity_id, session_id=session_id, reason=reason,
               correlation_id=correlation_id)
    return {"session_id": session_id, "revoked": True, "reason": reason}


# --------------------------------------------------------------------------- step-up

def _pending_challenge(
    conn: Connection[Any], identity_id: str, nonce: str, kind: str, now: datetime
) -> tuple[str, str | None] | None:
    """The challenge id and the device it was issued for, if it is live, unconsumed and of kind.

    Filtering on identity, nonce and kind together is what stops a step-up nonce being spent as
    a login challenge, or one identity's nonce being presented with another's identifier.
    """
    row = conn.execute(
        "SELECT challenge_id, device_id, expires_at, consumed_at FROM iam.challenges"
        " WHERE identity_id = %s AND nonce_hash = %s AND kind = %s",
        (identity_id, secrets.digest_token(nonce), kind),
    ).fetchone()
    if row is None:
        return None
    ok, _ = policy.challenge_usable(row[2], row[3], now)
    return (str(row[0]), str(row[1]) if row[1] else None) if ok else None


def require_assurance(
    pool: Pool, tenant_id: str, *, token: str, action_class: str
) -> dict[str, Any]:
    """Gate an action behind an assurance level (IAM-01-R06).

    Returns the session when it already meets the bar; otherwise mints a challenge and returns it
    with `step_up_required` true, because a 403 carrying no challenge tells a client to step up
    while withholding the one value it needs.

    `reachable` says whether stepping up can actually succeed. A privileged action needs level 3,
    which needs a hardware authenticator, which needs the WebAuthn verification this module does
    not have -- so the honest answer is that the bar cannot be met today, not a level issued on
    request.
    """
    _now_ = _now()
    session = resolve_session(pool, tenant_id, token=token)
    try:
        needed = policy.required_aal(action_class)
    except policy.PolicyError as exc:
        raise InvalidRequest(exc.code) from None
    if session["aal"] >= needed:
        return {**session, "step_up_required": False, "required_aal": needed,
                "reachable": True}

    reachable = needed <= policy.assurance_for(list(VERIFIABLE_FACTORS))
    with tenant_scope(pool, tenant_id) as conn:
        nonce = secrets.mint_nonce()
        conn.execute(
            """
            INSERT INTO iam.challenges
                (tenant_id, identity_id, kind, nonce_hash, required_aal, expires_at)
            VALUES (%s, %s, 'step_up', %s, %s, %s)
            """,
            (tenant_id, session["identity_id"], nonce.digest, needed,
             policy.challenge_expiry(_now_)),
        )
    return {**session, "step_up_required": True, "required_aal": needed,
            "reachable": reachable, "challenge": nonce.token}


def assert_assurance(
    pool: Pool, tenant_id: str, *, token: str, action_class: str
) -> dict[str, Any]:
    """The same gate for a caller that must fail closed rather than branch.

    `require_assurance` returns a flag a caller can forget to read; this raises. It can fail
    closed now that the level on a session reflects verified factors -- while the level could be
    had by naming a factor, as it could in the first version, this function could not refuse
    anybody and the promise in this docstring was false.
    """
    decided = require_assurance(pool, tenant_id, token=token, action_class=action_class)
    if decided["step_up_required"]:
        raise StepUpRequired("step_up_required")
    return decided


def complete_step_up(
    pool: Pool,
    tenant_id: str,
    *,
    token: str,
    challenge: str,
    correlation_id: str,
    password: str | None = None,
    recovery_code: str | None = None,
) -> dict[str, Any]:
    """StepUp (IAM-01-R06): present credentials, not claims.

    **The caller no longer says which factors it has.** It supplies them and this function checks
    each one against a stored credential; the level comes from what verified, combined with what
    the session records as having opened it. That is the fix for the review's first finding, where
    `{"factors": ["passkey_hardware"]}` raised a password session to AAL-3 with nothing presented.

    The old session is revoked and a new token issued rather than the row edited in place: a
    session's level is part of what its token means, so raising it silently would leave anything
    that already read the session believing the lower level.
    """
    _require_uuid(correlation_id, "correlation_id")
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _step_up_in_tx(conn, tenant_id, token=token, challenge=challenge,
                                 password=password, recovery_code=recovery_code,
                                 correlation_id=correlation_id)
    return _settled(outcome)


def _step_up_in_tx(
    conn: Connection[Any], tenant_id: str, *, token: str, challenge: str,
    password: str | None, recovery_code: str | None, correlation_id: str,
) -> tuple[dict[str, Any], ServiceError | None]:
    now = _now()
    failed: dict[str, Any] = {}
    row = _session_by_token(conn, token)
    session_id, identity_id, device_id, factors = (
        str(row[0]), str(row[1]), str(row[2]) if row[2] else None, list(row[7]),
    )
    state = policy.SessionState(aal=int(row[3]), expires_at=row[4], revoked_at=row[5])
    usable, _ = policy.session_usable(state, now)
    if not usable:
        return failed, AuthenticationFailed("authentication_failed")

    pending = _pending_challenge(conn, identity_id, challenge, "step_up", now)
    if pending is None:
        _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
               identity_id=identity_id, reason="challenge_invalid",
               correlation_id=correlation_id)
        return failed, AuthenticationFailed("authentication_failed")
    challenge_id, _ = pending

    # Metered: a stolen session token used to buy an unlimited password oracle here, because
    # this path verified credentials without reading a lock or counting a failure.
    presented, pending_code, error = _verify_presented(
        conn, tenant_id, identity_id, now=now, correlation_id=correlation_id,
        password=password, recovery_code=recovery_code,
    )
    if error is not None:
        return failed, error

    verified = [*factors, *presented]
    required_row = conn.execute(
        "SELECT required_aal FROM iam.challenges WHERE challenge_id = %s", (challenge_id,)
    ).fetchone()
    required = int(required_row[0]) if required_row and required_row[0] is not None \
        else policy.AAL_ELEVATED
    reached = policy.assurance_for(verified)
    if reached < required:
        # **Decided before anything is consumed.** A verified recovery code used to be burnt on
        # the way in, so a refusal here destroyed it for nothing -- and a recovered user, who can
        # never reach level 2 from recovery codes alone, lost one on every attempt until the
        # account was unreachable.
        _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
               identity_id=identity_id, reason="insufficient_factors",
               factor="+".join(sorted(set(verified))) or None,
               correlation_id=correlation_id)
        return failed, StepUpRequired("step_up_required")

    if pending_code is not None:
        _consume_credential(conn, pending_code, now)
    conn.execute("UPDATE iam.challenges SET consumed_at = %s WHERE challenge_id = %s",
                 (now, challenge_id))
    conn.execute(
        "UPDATE iam.sessions SET revoked_at = %s, revoke_reason = 'stepped_up'"
        " WHERE session_id = %s",
        (now, session_id),
    )
    fresh = _open_session(conn, tenant_id, identity_id, device_id, verified, now,
                          rotated_from=session_id)
    _event(conn, tenant_id, kind="step_up.succeeded", outcome="succeeded",
           identity_id=identity_id, session_id=fresh["session_id"],
           factor="+".join(sorted(set(verified))), correlation_id=correlation_id)
    return {**fresh, "identity_id": identity_id, "step_up_required": False}, None


# --------------------------------------------------------------------------- recovery

def issue_recovery_codes(
    pool: Pool, tenant_id: str, *, identity_id: str, correlation_id: str,
    current_password: str | None = None, session_factors: list[str] | None = None,
    session_aal: int = policy.AAL_ROUTINE, count: int = 10,
) -> dict[str, Any]:
    """Replace an identity's recovery codes and return the plaintext once (IAM-01-R07).

    **The current password, or an elevated session. A recovery-code session is not enough here**,
    though it is enough for `set_password`. The asymmetry is deliberate and was learnt the hard
    way: while this endpoint accepted a recovery session, somebody holding a stolen one could
    mint ten fresh codes with no password, and those codes survived the owner's own password
    reset -- a backdoor that the obvious remediation does not close.

    Nothing is lost by the restriction now that resetting works. A recovered user sets a new
    password first, which revokes every session including the one that did it, and then has a
    current password to mint codes with. The reset is the step that needs the allowance, and it
    is self-limiting; this one is not.

    Existing codes are revoked first: someone regenerating because they think the old set leaked
    gets nothing from it if the old set still works.
    """
    _require_uuid(correlation_id, "correlation_id")
    codes = secrets.generate_recovery_codes(count)
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _issue_codes_in_tx(
            conn, tenant_id, identity_id=identity_id, codes=codes,
            correlation_id=correlation_id, current_password=current_password,
            session_factors=session_factors or [], session_aal=session_aal,
        )
    return _settled(outcome)


def _issue_codes_in_tx(
    conn: Connection[Any], tenant_id: str, *, identity_id: str, codes: list[str],
    correlation_id: str, current_password: str | None, session_factors: list[str],
    session_aal: int,
) -> tuple[dict[str, Any], ServiceError | None]:
    now = _now()
    failed: dict[str, Any] = {}
    _require_identity(conn, identity_id)
    # No recovery allowance here -- see the docstring. Only a real password or a stepped-up
    # session mints permanent credentials.
    del session_factors
    already_proved = session_aal >= policy.AAL_ELEVATED

    if _active_password(conn, identity_id) is not None and not already_proved:
        if current_password is None:
            return failed, AuthenticationFailed("authentication_failed")
        # Metered and recorded. The first version raised inside the transaction, so a failed
        # guess against the endpoint that hands out permanent credentials left no audit row at
        # all -- measured zero, while the same failure on `set_password` wrote one.
        _, _, error = _verify_presented(conn, tenant_id, identity_id, now=now,
                                        correlation_id=correlation_id,
                                        password=current_password)
        if error is not None:
            return failed, error

    conn.execute(
        "UPDATE iam.credentials SET status = 'revoked', revoked_at = %s"
        " WHERE identity_id = %s AND kind = 'recovery_code' AND status = 'active'",
        (now, identity_id),
    )
    for code in codes:
        _store_credential(conn, tenant_id, identity_id, RECOVERY_CODE,
                          secrets.hash_secret(code))
    _event(conn, tenant_id, kind="recovery.codes_issued", outcome="succeeded",
           identity_id=identity_id, correlation_id=correlation_id)
    return {"identity_id": identity_id, "codes": codes, "count": len(codes)}, None


def recover_with_code(
    pool: Pool, tenant_id: str, *, identifier: str, code: str, correlation_id: str
) -> dict[str, Any]:
    """RecoverIdentity (IAM-01-R07). Single use, lockout-aware, and it logs everything else out.

    Three things the first version got wrong, all found by review: it ignored the lock and never
    counted a failure, so it was an unbounded guessing oracle costing ten scrypt hashes a try; it
    ignored `status`, so an identity suspended out of the login path could still recover through
    this one; and it left every existing session alive, though the reason to use a recovery code
    is usually that someone else has the account.
    """
    _require_uuid(correlation_id, "correlation_id")
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _recover_in_tx(conn, tenant_id, identifier=identifier, code=code,
                                 correlation_id=correlation_id)
    return _settled(outcome)


def _recover_in_tx(
    conn: Connection[Any], tenant_id: str, *, identifier: str, code: str, correlation_id: str
) -> tuple[dict[str, Any], ServiceError | None]:
    now = _now()
    failed: dict[str, Any] = {}
    refused = AuthenticationFailed("authentication_failed")
    found = _find_identity(conn, identifier)
    if found is None:
        secrets.verify_secret(_DUMMY, code or "x")
        _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
               factor=RECOVERY_CODE, reason="unknown_identifier",
               correlation_id=correlation_id)
        return failed, refused

    identity_id, status = str(found[0]), found[1]
    # Recovery reads its **own** lock, not the password one. Being locked out of the password is
    # the usual reason to reach for a recovery code, so honouring that lock here would shut the
    # only door left. Bounding recovery is a separate budget, below.
    recovery_lock = policy.LockoutState(failed_attempts=int(found[4]), locked_until=found[5])
    if policy.locked(recovery_lock, now) or status != "active":
        secrets.verify_secret(_DUMMY, code or "x")
        _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
               identity_id=identity_id, factor=RECOVERY_CODE,
               reason="recovery_locked" if policy.locked(recovery_lock, now)
                      else f"status_{status}",
               correlation_id=correlation_id)
        return failed, refused

    matched = _match_recovery_code(conn, identity_id, code)
    if matched is None:
        _count_recovery_failure(conn, tenant_id, identity_id, now, "bad_code", correlation_id)
        return failed, refused
    _consume_credential(conn, matched, now)

    # A correct code clears both budgets: the account is back in its owner's hands.
    conn.execute(
        "UPDATE iam.identities SET failed_attempts = 0, locked_until = NULL,"
        " recovery_failed_attempts = 0, recovery_locked_until = NULL,"
        " version = version + 1 WHERE identity_id = %s",
        (identity_id,),
    )
    revoked = _revoke_chain(conn, tenant_id, identity_id, now, "recovered")
    session = _open_session(conn, tenant_id, identity_id, None, [RECOVERY_CODE], now)
    _event(conn, tenant_id, kind="recovery.used", outcome="succeeded",
           identity_id=identity_id, factor=RECOVERY_CODE,
           session_id=session["session_id"], correlation_id=correlation_id)
    return {**session, "identity_id": identity_id, "sessions_revoked": revoked}, None


# --------------------------------------------------------------------------- passkeys

def enroll_passkey(
    pool: Pool,
    tenant_id: str,
    *,
    identity_id: str,
    webauthn_credential_id: bytes,
    public_key: bytes,
    correlation_id: str,
    label: str | None = None,
    aaguid: str | None = None,
    transports: list[str] | None = None,
    backed_up: bool = False,
) -> dict[str, Any]:
    """EnrollPasskey (IAM-01-R02), storing what a verifier would later need.

    **The attestation is not verified**, so an enrolled passkey is not an authentication factor:
    no code path accepts one as proof and `VERIFIABLE_FACTORS` does not contain it. What is kept
    is the credential id, the public key and the starting signature counter -- the inputs a
    WebAuthn library needs. Pretending to verify would be worse than not verifying.
    """
    _require_uuid(correlation_id, "correlation_id")
    if len(webauthn_credential_id) < 16 or len(public_key) < 32:
        raise InvalidRequest("bad_passkey_material")
    with tenant_scope(pool, tenant_id) as conn:
        _require_identity(conn, identity_id)
        try:
            row = conn.execute(
                """
                INSERT INTO iam.passkeys
                    (tenant_id, identity_id, webauthn_credential_id, public_key, aaguid,
                     transports, backed_up, label)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING passkey_id
                """,
                (tenant_id, identity_id, webauthn_credential_id, public_key, aaguid,
                 transports, backed_up, label),
            ).fetchone()
        except errors.UniqueViolation:
            raise Conflict("passkey_already_enrolled") from None
        assert row is not None
        _event(conn, tenant_id, kind="passkey.registered", outcome="succeeded",
               identity_id=identity_id, factor="passkey", correlation_id=correlation_id)
    return {"passkey_id": str(row[0]), "identity_id": identity_id, "label": label,
            "verified": False,
            "note": "signature verification is not implemented; this is not an auth factor"}


def record_passkey_assertion(
    pool: Pool, tenant_id: str, *, passkey_id: str, identity_id: str, sign_count: int,
    correlation_id: str,
) -> dict[str, Any]:
    """Advance a passkey's signature counter, refusing a clone (IAM-01-R02).

    The half of passkey handling that is pure logic: an authenticator repeating or lowering its
    counter is presenting a credential that exists in two places. The passkey is revoked on sight,
    every session for that identity goes with it, and the refusal is raised only after those
    revocations commit. It authenticates nobody -- no signature was checked.
    """
    _require_uuid(correlation_id, "correlation_id")
    with tenant_scope(pool, tenant_id) as conn:
        outcome = _assertion_in_tx(conn, tenant_id, passkey_id=passkey_id,
                                   identity_id=identity_id, sign_count=sign_count,
                                   correlation_id=correlation_id)
    return _settled(outcome)


def _assertion_in_tx(
    conn: Connection[Any], tenant_id: str, *, passkey_id: str, identity_id: str,
    sign_count: int, correlation_id: str,
) -> tuple[dict[str, Any], ServiceError | None]:
    now = _now()
    failed: dict[str, Any] = {}
    row = conn.execute(
        "SELECT identity_id, sign_count, revoked_at FROM iam.passkeys WHERE passkey_id = %s",
        (passkey_id,),
    ).fetchone()
    if row is None or str(row[0]) != identity_id:
        return failed, NotFound("passkey_not_found")
    stored, revoked_at = int(row[1]), row[2]
    if revoked_at is not None:
        return failed, Conflict("passkey_revoked")
    try:
        acceptable = policy.sign_count_acceptable(stored, sign_count)
    except policy.PolicyError as exc:
        return failed, InvalidRequest(exc.code)
    if not acceptable:
        conn.execute("UPDATE iam.passkeys SET revoked_at = %s WHERE passkey_id = %s",
                     (now, passkey_id))
        _revoke_chain(conn, tenant_id, identity_id, now, "passkey_clone_suspected")
        _event(conn, tenant_id, kind="passkey.revoked", outcome="failed",
               identity_id=identity_id, factor="passkey", reason="sign_count_regression",
               correlation_id=correlation_id)
        return failed, Conflict("passkey_clone_suspected")
    conn.execute(
        "UPDATE iam.passkeys SET sign_count = %s, last_used_at = %s WHERE passkey_id = %s",
        (sign_count, now, passkey_id),
    )
    return {"passkey_id": passkey_id, "sign_count": sign_count, "accepted": True}, None


def list_passkeys(pool: Pool, tenant_id: str, *, identity_id: str) -> list[dict[str, Any]]:
    with tenant_scope(pool, tenant_id) as conn:
        _require_identity(conn, identity_id)
        rows = conn.execute(
            "SELECT passkey_id, label, sign_count, backed_up, created_at, last_used_at,"
            " revoked_at FROM iam.passkeys WHERE identity_id = %s ORDER BY created_at",
            (identity_id,),
        ).fetchall()
    return [
        {"passkey_id": str(r[0]), "label": r[1], "sign_count": int(r[2]),
         "backed_up": bool(r[3]), "created_at": r[4].isoformat(),
         "last_used_at": r[5].isoformat() if r[5] else None,
         "revoked_at": r[6].isoformat() if r[6] else None}
        for r in rows
    ]


# --------------------------------------------------------------------------- audit

def auth_events(
    pool: Pool, tenant_id: str, *, identity_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    """One identity's authentication log, and only that identity's.

    `identity_id` is required. The first version let it default to None and returned every event
    in the tenant to an unauthenticated caller, which handed out the identity ids that made the
    rest of the takeover chain possible.
    """
    capped = max(1, min(int(limit), 500))
    with tenant_scope(pool, tenant_id) as conn:
        _require_identity(conn, identity_id)
        rows = conn.execute(
            "SELECT identity_id, kind, outcome, factor, reason, occurred_at"
            " FROM iam.auth_events WHERE identity_id = %s"
            " ORDER BY occurred_at DESC, event_id DESC LIMIT %s",
            (identity_id, capped),
        ).fetchall()
    return [
        {"identity_id": str(r[0]) if r[0] else None, "kind": r[1], "outcome": r[2],
         "factor": r[3], "reason": r[4], "occurred_at": r[5].isoformat()} for r in rows
    ]

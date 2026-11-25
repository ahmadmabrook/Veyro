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

* **WebAuthn attestation**, which is a different claim from the signature: the assertion is
  verified now (`app/identity/webauthn.py`), so a passkey is a factor and AAL 3 is reachable.
  What is not checked is *which model* of authenticator a credential came from, which would
  need an AAGUID metadata service and a policy about which keys a tenant accepts -- neither
  exists here, and neither is needed to know that whoever signed in holds the private key.
* **Passkey step-up.** `complete_step_up` takes a password or a recovery code, so a session is
  raised to level 2 and no higher; level 3 is reached by signing in with a device-bound
  passkey rather than by raising an existing session. Verifying an assertion inside the
  step-up path is the next piece and is deliberately not half-built.
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
from app.identity import policy, secrets, webauthn

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
PASSKEY_HARDWARE = "passkey_hardware"
PASSKEY_SYNCED = "passkey_synced"
VERIFIABLE_FACTORS = (PASSWORD, RECOVERY_CODE, PASSKEY_HARDWARE, PASSKEY_SYNCED)
"""The only factors any code path accepts as proof, and saying a factor's name does not add it:
`complete_step_up` takes credentials, never factor names.

**The two passkey factors are here now, and nothing but `app.identity.webauthn` puts one in a
session.** They arrived with signature verification and not before: for as long as the
signature was unchecked, a passkey proved nothing, so this tuple held two entries and
`require_assurance` answered that AAL 3 was unreachable by anybody. Which of the two an
assertion presents is decided by the `BE` flag the authenticator signed over -- never by a
request field -- so a caller cannot ask for the hardware one."""


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


def normalize_identifier(value: str) -> str:
    """The identifier as `_find_identity` will see it, or the stripped value when it is not one.

    **Anything keyed on an identifier has to key on this, not on what the caller typed.** A phone
    number has unlimited spellings that resolve to one identity -- `normalize_phone` strips
    whitespace, parentheses and hyphens from anywhere in the string -- so a rate limiter keyed on
    the raw value hands every spelling its own budget and bounds nothing. Found by review, with
    eight spellings of one number taking eight full login budgets.

    An unparseable value still gets a stable key rather than an exception: a limiter that refused
    to count what it could not parse would be a limiter an attacker turns off by sending
    nonsense.
    """
    try:
        return normalize_email(value) if "@" in value else normalize_phone(value)
    except InvalidRequest:
        return value.strip().lower()


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

def register_identity_on(
    conn: Connection[Any],
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

    **In the caller's transaction**, which ADM-STF-03 is why (ADR-0017 D2): accepting a staff
    invitation creates the identity *and* its role assignments, and an identity created with the
    assignments rolled back is a login with no permissions that the retry cannot repair -- the
    identifier is taken by then, so the second attempt answers
    `identifier_already_registered`. Both tables are in `iam` under one role, so one
    transaction is available. `register_identity` is the pool-taking wrapper.
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
    """`register_identity_on` in a transaction of its own."""
    with tenant_scope(pool, tenant_id) as conn:
        return register_identity_on(
            conn, tenant_id, display_name=display_name, correlation_id=correlation_id,
            email=email, phone=phone, password=password, person_id=person_id)


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
        # **An unknown *tenant* arrives here too, and it used to answer 500.**
        # `X-Veyro-Tenant` is an unauthenticated claim that is shape-checked and nothing
        # more, so anybody can present a well-formed uuid for a tenant that does not exist.
        # RLS then hides every identity, this branch is taken, and the event's own foreign
        # key to the tenant registry refuses the row -- a `ForeignKeyViolation` out of an
        # unauthenticated route, with a stack trace per attempt.
        #
        # **The foreign key is the only thing in reach that knows.** `veyro_iam_app` holds
        # no USAGE on `plt01_platform`, deliberately, so the service cannot ask whether a
        # tenant exists; the database answers as it enforces the reference. A savepoint
        # keeps that answer from poisoning the caller's transaction, and the refusal is
        # **the same refusal** -- one scrypt already spent above, the same
        # `authentication_failed`, no new way to tell a real tenant from an invented one.
        # MOD-007's rule: a refusal must not say why.
        try:
            with conn.transaction():
                _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
                       factor=PASSWORD, reason="unknown_identifier",
                       correlation_id=correlation_id)
        except errors.ForeignKeyViolation:
            pass
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


#: The most sessions one read returns. A session row is written on every sign-in and every
#: rotation and `iam.sessions` has no DELETE grant, so an identity that has signed in a
#: thousand times has a thousand rows -- and this read had no bound at all, which made the
#: honest answer to "show me my sessions" a page thirteen thousand pixels tall. Newest first,
#: so the bound keeps the rows a person came for.
SESSION_PAGE = 50

#: The authentication log's ceiling. Larger than the session page because the log is the read
#: somebody does when investigating an account rather than managing one, and it is insert-only.
EVENT_PAGE = 500


def list_sessions(
    pool: Pool, tenant_id: str, *, identity_id: str, limit: int = SESSION_PAGE,
    live_only: bool = False,
) -> list[dict[str, Any]]:
    """Session inventory (IAM-01-R05). No token or digest is ever returned.

    **`live_only` is the filter an account page wants and a reviewer does not.** A revoked or
    expired session is the evidence that a sign-out happened, which is exactly what somebody
    investigating an account asks for; a member looking at "where am I signed in" wants the
    ones that still work. Both are real reads, so the caller says which.
    """
    if limit < 1 or limit > 500:
        raise InvalidRequest("bad_limit")
    where = "identity_id = %s"
    if live_only:
        where += " AND revoked_at IS NULL AND expires_at > now()"
    with tenant_scope(pool, tenant_id) as conn:
        _require_identity(conn, identity_id)
        rows = conn.execute(
            "SELECT session_id, device_id, aal, factors, issued_at, expires_at, last_seen_at,"
            f" revoked_at, revoke_reason FROM iam.sessions WHERE {where}"
            " ORDER BY issued_at DESC LIMIT %s",
            (identity_id, limit),
        ).fetchall()
    return [
        {"session_id": str(r[0]), "device_id": str(r[1]) if r[1] else None, "aal": int(r[2]),
         "factors": list(r[3]), "issued_at": r[4].isoformat(), "expires_at": r[5].isoformat(),
         "last_seen_at": r[6].isoformat() if r[6] else None,
         "revoked_at": r[7].isoformat() if r[7] else None, "revoke_reason": r[8]}
        for r in rows
    ]


#: How many identities one batched last-seen read may be asked about. The same ceiling as the
#: staff list it serves, for the same reason the assignment batch has it.
LAST_SEEN_BATCH = 200


def last_seen_for(
    pool: Pool, tenant_id: str, *, identity_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """When each of several identities was last active, and whether a login still works.

    **ADM-STF-01's LAST SEEN column, and the design says what it is for**: "Last seen exists so
    a departed employee with a live login is visible rather than discovered." So the useful
    answer is two facts rather than one -- when they were last here, and whether anything they
    hold still opens the door -- and the second is the one that makes the column a control.
    Neither is derivable from the other: an account nobody has used for a year still works, and
    a session used this morning may have been revoked since.

    **Strictly less than `list_sessions`, deliberately.** That read returns one row per session
    with its device, its assurance, its factors and why it was revoked, and its own docstring
    records why it had to be bounded and filtered once something rendered it: an unbounded read
    of every session an identity ever opened is a page describing every device that person has
    signed in from. This returns one timestamp, one count and the identity's status -- no
    device, no factor, no token, no digest, no address, and nothing a reader could use to tell
    where somebody was. A staff list does not need any of that and should not be able to see
    it with the permission that draws a column.

    Bounded by the ids the caller passes rather than by a page over the tenant, like the
    assignment batch beside it.
    """
    if not identity_ids:
        return {}
    if len(identity_ids) > LAST_SEEN_BATCH:
        raise InvalidRequest("too_many_identities")
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            # `last_seen_at` is null on a session that was issued and never used again, so the
            # issue time is the floor: an account used once is not an account never seen.
            "SELECT i.identity_id, i.status,"
            " max(coalesce(s.last_seen_at, s.issued_at)),"
            " count(s.session_id) FILTER ("
            "     WHERE s.revoked_at IS NULL AND s.expires_at > now())"
            " FROM iam.identities i"
            " LEFT JOIN iam.sessions s ON s.identity_id = i.identity_id"
            " WHERE i.identity_id = ANY(%s)"
            " GROUP BY i.identity_id, i.status",
            (list(identity_ids),),
        ).fetchall()
    return {
        str(r[0]): {
            "identity_id": str(r[0]),
            "status": r[1],
            "last_seen_at": r[2].isoformat() if r[2] else None,
            "live_sessions": int(r[3]),
            #: Said once, here, rather than implied by the absence of the fields.
            "no_device_or_address_is_returned":
                "this read is a timestamp, a count and a status; where somebody signed in "
                "from is identity.session.read's and is not bought by a staff list",
        }
        for r in rows
    }


#: The states `iam.identities.status` admits, and what each one means for signing in.
#:
#: **All three were declared and two were unreachable.** `authenticate`, the risk challenge,
#: `recover_with_code` and `_session_by_token` each refuse an identity that is not `active` --
#: four independent controls, each correct -- and nothing in the build could set the column.
#: So the product could not shut anybody out. That is MOD-012's "a column implying a control
#: nobody implemented" and MOD-020's "a declared state nothing writes", in the module whose
#: subject is who may sign in, and it was found by building the staff list that shows an owner
#: a departed employee still has access.
#:
#: `suspended` and `deactivated` behave identically to every control that reads the column;
#: the difference is what somebody means by it, and the schema has carried both from the start.
IDENTITY_STATUSES = ("active", "suspended", "deactivated")

#: The status a reinstatement returns an identity to.
ACTIVE = "active"


def set_identity_status(
    pool: Pool, tenant_id: str, *, identity_id: str, status: str, reason: str,
    actor_identity_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Suspend, deactivate or reinstate an identity -- IAM-01's missing writer.

    **Suspending revokes every live session in the same transaction.** It does not have to:
    `_session_by_token` reads the status, so an existing bearer token stops working the moment
    the column moves. It is done anyway, for two reasons -- the revocation rows are the
    evidence an operator means by "I ended their access", and a session reading `live` beside
    a suspended identity is a row two readers would disagree about. MOD-010's argument applied
    to a credential: the control and the state it bounds commit together.

    **A session cannot suspend the identity it is using.** This build has no platform identity
    and no path that reinstates one from outside the tenant, so an owner who suspended
    themselves would lock the tenant out with no remedy anywhere in the product. The refusal
    is recoverable; the act would not be.

    **The evidence is written inside the transaction that moves the column.** `iam.auth_events`
    is insert-only and its `kind` is a closed set -- which is why this needed a migration
    before it could be allowed at all: an act whose record cannot be named is an act with
    nobody's name on it, this build's most-repeated finding.
    """
    _require_uuid(correlation_id, "correlation_id")
    if status not in IDENTITY_STATUSES:
        raise InvalidRequest("bad_status")
    if not reason.strip():
        raise InvalidRequest("reason_required")
    if len(reason) > 500:
        raise InvalidRequest("reason_too_long")
    if identity_id == actor_identity_id:
        raise InvalidRequest("cannot_change_your_own_status")
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        current = conn.execute(
            "SELECT status FROM iam.identities WHERE identity_id = %s FOR UPDATE",
            (identity_id,),
        ).fetchone()
        if current is None:
            raise NotFound("identity_not_found")
        was = str(current[0])
        if was == status:
            # Idempotent to the caller, which is the rule MOD-017 paid for three times: a
            # client whose request timed out after the commit must not be told the work
            # failed. Nothing is recorded twice and no session is revoked a second time.
            return {"identity_id": identity_id, "status": status, "was": was,
                    "sessions_revoked": 0, "repeated": True}
        conn.execute(
            "UPDATE iam.identities SET status = %s, version = version + 1"
            " WHERE identity_id = %s",
            (status, identity_id),
        )
        revoked = 0
        if status != ACTIVE:
            rows = conn.execute(
                "UPDATE iam.sessions SET revoked_at = %s, revoke_reason = %s"
                " WHERE identity_id = %s AND revoked_at IS NULL AND expires_at > %s"
                " RETURNING session_id",
                (now, f"identity_{status}", identity_id, now),
            ).fetchall()
            revoked = len(rows)
        kind = (
            "identity.reinstated" if status == ACTIVE
            else f"identity.{status}"
        )
        _event(conn, tenant_id, kind=kind, outcome="succeeded", identity_id=identity_id,
               reason=reason, correlation_id=correlation_id)
        # The actor, on its own row, because `iam.auth_events` records the identity an event
        # is *about* and has no column for the identity that caused it. Two rows under one
        # correlation id is the join, and the log is insert-only so neither can be edited to
        # disagree with the other.
        _event(conn, tenant_id, kind=kind, outcome="succeeded",
               identity_id=actor_identity_id, reason=f"acted_on:{identity_id}",
               correlation_id=correlation_id)
    return {"identity_id": identity_id, "status": status, "was": was,
            "sessions_revoked": revoked, "repeated": False,
            #: Said rather than implied: a suspension stops the login and leaves every role
            #: assignment in place, because what somebody may do and whether they may sign in
            #: are different questions and MOD-008 owns the first.
            "roles_are_unchanged":
                "this ends the login and revokes nothing in authorization; a role assignment "
                "is revoked separately and the two are deliberately different acts"}


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

    `reachable` says whether stepping up can actually succeed, computed from
    `VERIFIABLE_FACTORS` rather than written down. **It answers true for level 3 now**, and for
    five modules it answered false: a privileged action needs a hardware authenticator, which
    needed the WebAuthn signature verification this module deliberately did not have. It does
    now, so `passkey_hardware` is a verifiable factor and the bar can be met.

    **What that does not mean is that `/auth/step-up` can raise a session to it.** Step-up
    takes a password or a recovery code, neither of which reaches level 3, so the way to a
    level-3 session is signing in with a device-bound passkey at `/auth/passkey/login`. A
    stepped-up *passkey* assertion is the obvious next piece and is named as a gap rather than
    half-built -- and `reachable` is honest either way, because it is about whether any factor
    in this build reaches the level rather than about which route gets there.
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
    """EnrollPasskey (IAM-01-R02), keeping a key this build can actually verify against.

    **`public_key` is SPKI DER**, which is what `AuthenticatorAttestationResponse.getPublicKey()`
    returns, and it is loaded here rather than stored as opaque bytes: a key that cannot be
    parsed, or is of a type this build does not verify, is refused at enrolment -- where
    somebody can read the reason -- rather than at the moment they are trying to sign in. That
    is the only thing standing between "a passkey is enrolled" and "a passkey can be used",
    and the first version of this function stored whatever it was handed.

    **The attestation is still not verified**, and that is a different claim from the signature.
    Attestation says *which model of authenticator* this is, which matters for a policy like
    "only these certified keys"; this build has no such policy and no metadata service to
    resolve an AAGUID against. What is verified is the assertion -- that whoever is signing
    in holds the private key for this public one -- which is what makes a passkey a factor.
    """
    _require_uuid(correlation_id, "correlation_id")
    if len(webauthn_credential_id) < 16 or len(public_key) < 32:
        raise InvalidRequest("bad_passkey_material")
    try:
        algorithm = webauthn.algorithm_for_key(public_key)
        webauthn.load_public_key(public_key, algorithm)
    except webauthn.WebAuthnError as exc:
        raise InvalidRequest(exc.code) from None
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
            "cose_algorithm": algorithm, "verifiable": True,
            # **Which factor this will present is not knowable here.** The `BE` flag comes
            # from an assertion the authenticator signs, and enrolment sees no assertion -- so
            # whether this credential reaches level 2 or level 3 is answered the first time
            # somebody signs in with it, by the flag rather than by anything stored.
            "factor": "decided per assertion by the backup-eligibility flag"}


def begin_passkey_assertion(
    pool: Pool, tenant_id: str, *, identifier: str, correlation_id: str,
) -> dict[str, Any]:
    """Issue the challenge a passkey sign-in will be verified against.

    **The response is the same shape for every identifier, and that is the whole design.** A
    ceremony that answered "no passkey is enrolled for this address" would be a directory of
    which addresses exist and which have a passkey -- MOD-007's own rule, which cost this
    module a blocking defect when a locked identity answered 423 in two milliseconds while
    everything else answered 401 in fifty. So a challenge is minted and returned whatever the
    identifier is; a row is stored only when there is an identity to store it against, and an
    assertion against an unstored challenge is refused at verification like any other.

    **No credential list is returned either.** WebAuthn's `allowCredentials` would name this
    person's credential ids to anybody who typed their address. Every passkey this build can
    verify is discoverable -- the browser finds it from the relying party id -- so the list is
    not needed, and leaving it out is what keeps the response uniform.

    Nothing is spent by calling this: an unstored nonce is a random string, and a stored one
    expires. The route is rate-limited because the path is unauthenticated, which is the bound
    that matters here.
    """
    _require_uuid(correlation_id, "correlation_id")
    now = _now()
    nonce = secrets.mint_nonce()
    with tenant_scope(pool, tenant_id) as conn:
        found = _find_identity(conn, identifier)
        if found is not None and found[1] == "active":
            conn.execute(
                """
                INSERT INTO iam.challenges
                    (tenant_id, identity_id, kind, nonce_hash, required_aal, expires_at)
                VALUES (%s, %s, 'passkey_assertion', %s, NULL, %s)
                """,
                (tenant_id, str(found[0]), nonce.digest, policy.challenge_expiry(now)),
            )
    return {"challenge": nonce.token, "expires_in_seconds": int(
        (policy.challenge_expiry(now) - now).total_seconds())}


def authenticate_with_passkey(
    pool: Pool,
    tenant_id: str,
    *,
    identifier: str,
    challenge: str,
    credential_id: bytes,
    client_data_json: bytes,
    authenticator_data: bytes,
    signature: bytes,
    rp_id: str | None,
    allowed_origins: tuple[str, ...],
    correlation_id: str,
    device_fingerprint: str | None = None,
    device_label: str | None = None,
) -> dict[str, Any]:
    """Sign in with a passkey, verifying the signature (IAM-01-R02).

    **This is the function MOD-007 refused to write until it could write it honestly**, and
    what it buys is the whole of AAL 3: a device-bound credential with user verification opens
    a level-3 session, so break-glass support access and the actions MOD-008 classifies
    `privileged` stop being a deliberate dead end.

    The order is: resolve the identity, find the challenge, **consume it**, find the credential,
    verify, then advance the counter and open the session.

    **The challenge is consumed before the signature is checked, and that is deliberate** --
    the opposite of MOD-007's "verify, decide, then consume", because a nonce is not a
    credential. A recovery code destroyed by a refusal is a credential the honest owner has
    lost; a challenge destroyed by a refusal costs one more round trip, and a challenge that
    survived a failed attempt is a replay window. The rule is about not spending what the user
    cannot replace.

    **Every refusal is one `AuthenticationFailed`.** `webauthn.REASONS` has twelve codes and
    the caller is told none of them: which part was wrong is exactly the oracle paragraph
    1944's sibling rule in MOD-022 is about, and here it would say whether an address, a
    credential or a signature was the problem. The reason lands on the insert-only auth log,
    where somebody holding the permission can read it.
    """
    _require_uuid(correlation_id, "correlation_id")
    if rp_id is None or not allowed_origins:
        # **Not an authentication failure.** A deployment that has not stated its relying party
        # cannot verify anything, and answering 401 would read as "wrong credential" to the one
        # person who could fix it.
        raise InvalidRequest("webauthn_not_configured")
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        outcome, error = _passkey_login_in_tx(
            conn, tenant_id, identifier=identifier, challenge=challenge,
            credential_id=credential_id, client_data_json=client_data_json,
            authenticator_data=authenticator_data, signature=signature, rp_id=rp_id,
            allowed_origins=allowed_origins, device_fingerprint=device_fingerprint,
            device_label=device_label, now=now, correlation_id=correlation_id)
    return _settled((outcome, error))


def _passkey_login_in_tx(
    conn: Connection[Any], tenant_id: str, *, identifier: str, challenge: str,
    credential_id: bytes, client_data_json: bytes, authenticator_data: bytes,
    signature: bytes, rp_id: str, allowed_origins: tuple[str, ...],
    device_fingerprint: str | None, device_label: str | None, now: datetime,
    correlation_id: str,
) -> tuple[dict[str, Any], ServiceError | None]:
    """The transaction, so every refusal commits its own evidence before it is raised.

    `tenant_scope` rolls back when the block raises, which is why this returns the error for
    `_settled` to raise outside -- MOD-007's and MOD-008's standing rule, and the reason three
    denial paths in this module once wrote an audit row and threw it away.
    """
    failed: dict[str, Any] = {}
    refused = AuthenticationFailed("authentication_failed")

    def refuse(reason: str, identity_id: str | None) -> tuple[dict[str, Any], ServiceError]:
        _event(conn, tenant_id, kind="authentication.failed", outcome="failed",
               identity_id=identity_id, factor="passkey", reason=reason,
               correlation_id=correlation_id)
        return failed, refused

    found = _find_identity(conn, identifier)
    if found is None or found[1] != "active":
        # No identity to attribute an event to, and `iam.auth_events` requires one -- so the
        # refusal is silent here, exactly as the password path's unknown-identifier branch is.
        return failed, refused
    identity_id = str(found[0])

    pending = _pending_challenge(conn, identity_id, challenge, "passkey_assertion", now)
    if pending is None:
        return refuse("challenge_invalid", identity_id)
    conn.execute("UPDATE iam.challenges SET consumed_at = %s WHERE challenge_id = %s",
                 (now, pending[0]))

    row = conn.execute(
        "SELECT passkey_id, public_key, revoked_at FROM iam.passkeys"
        " WHERE identity_id = %s AND webauthn_credential_id = %s",
        (identity_id, credential_id),
    ).fetchone()
    if row is None:
        return refuse("credential_unknown", identity_id)
    passkey_id, public_key = str(row[0]), bytes(row[1])
    if row[2] is not None:
        return refuse("credential_revoked", identity_id)

    try:
        verified = webauthn.check_assertion(
            client_data_json=client_data_json, authenticator_data=authenticator_data,
            # **The bytes the browser signed are this token's own base64url decoding.**
            # `mint_nonce` returns `token_urlsafe`, which is unpadded base64url with no
            # `+` or `/`, so the client decodes the string it was handed and signs those
            # bytes -- and the strict decoder here produces the same ones. A lenient one
            # would let a single challenge be written two ways.
            signature=signature, expected_challenge=webauthn.b64url_decode(challenge),
            rp_id=rp_id, allowed_origins=allowed_origins, public_key_spki=public_key,
            algorithm=webauthn.algorithm_for_key(public_key))
    except webauthn.WebAuthnError as exc:
        return refuse(exc.code, identity_id)

    # The clone check, and the revocation it causes, are `record_passkey_assertion`'s -- one
    # implementation, because two counters compared in two places drift and the day they
    # disagree nobody can say which one is the policy.
    advanced, counter_error = _assertion_in_tx(
        conn, tenant_id, passkey_id=passkey_id, identity_id=identity_id,
        sign_count=verified.sign_count, correlation_id=correlation_id)
    if counter_error is not None:
        # A clone has already revoked the passkey and every session for this identity inside
        # `_assertion_in_tx`; the caller is told the same thing as every other refusal.
        return failed, refused
    assert advanced

    device = _touch_device(conn, tenant_id, identity_id, device_fingerprint, device_label, now)
    if device.revoked:
        return refuse("device_revoked", identity_id)
    # **A verified passkey confirms the device**, for the reason a password login that needed
    # no challenge does: the assertion is stronger evidence than anything a risk challenge
    # could ask for, and leaving the device unconfirmed would challenge the next password
    # login of somebody who just proved possession of a hardware authenticator.
    _confirm_device(conn, device.device_id, now)
    cleared = policy.after_success(policy.LockoutState(
        failed_attempts=int(found[2]), locked_until=found[3]))
    conn.execute(
        "UPDATE iam.identities SET failed_attempts = %s, locked_until = NULL,"
        " version = version + 1 WHERE identity_id = %s",
        (cleared.failed_attempts, identity_id),
    )
    session = _open_session(conn, tenant_id, identity_id, device.device_id,
                            [verified.factor], now)
    _event(conn, tenant_id, kind="authentication.succeeded", outcome="succeeded",
           identity_id=identity_id, factor=verified.factor, device_id=device.device_id,
           session_id=session["session_id"], reason="passkey_verified",
           correlation_id=correlation_id)
    return ({"authenticated": True, "challenge_required": False, **session,
             "identity_id": identity_id, "device_id": device.device_id,
             "passkey_id": passkey_id, "backed_up": verified.backed_up}, None)


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


def read_own_identity(pool: Pool, tenant_id: str, *, identity_id: str) -> dict[str, Any]:
    """Who this session is, for a screen that has to say so.

    **Added because a WebAuthn ceremony has to name the account to the authenticator.** The
    browser shows `user.name` when somebody later picks between credentials, and with no route
    returning the signed-in person's own display name the only value available was the identity
    uuid -- so an authenticator would offer "veyro: 3f7c…" and a member would have to guess.
    Every other page in this app knew who it was reading about; the account page is the one
    that reads about *you* and had nothing to say it.

    Self-scoped rather than gated, like every other read behind `owned`: there is nothing to
    authorize when the only readable subject is the caller. **The contact identifiers are the
    caller's own**, which is why they are returned unmasked here and by nothing else -- MOD-014
    masks a *member's* identity fields from a staff reader, and this is neither.
    """
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT display_name, email_normalized, phone_normalized, status, created_at"
            " FROM iam.identities WHERE identity_id = %s", (identity_id,)).fetchone()
        if row is None:
            raise NotFound("identity_not_found")
    return {"identity_id": identity_id, "display_name": str(row[0]),
            "email": row[1], "phone": row[2], "status": str(row[3]),
            "created_at": row[4].isoformat()}


def revoke_passkey(
    pool: Pool, tenant_id: str, *, passkey_id: str, identity_id: str, correlation_id: str,
) -> dict[str, Any]:
    """Withdraw a passkey, which until now nothing but clone detection could do.

    **A write form needs its remedy before it needs its button**, and this is the remedy.
    Enrolling a passkey is a routine, self-scoped act -- `owned(session, identity_id)` refuses
    any subject but the caller's own -- and the only writer of `revoked_at` was the clone
    check, so a lost authenticator left a credential that could open a level-3 session for
    ever and a stolen one could not be withdrawn at all. That is MOD-013's rule ("an
    irreversible act must not be declarable on a routine permission") from the side this
    repository has paid for once already, in MOD-019's insert-only rota.

    **A revocation, not a delete**, because `veyro_iam_app` holds DELETE on nothing in `iam`
    by design: revocation here is a status change that leaves evidence. The evidence is the
    `passkey.revoked` row on the insert-only log with this identity and a reason that says a
    person did it -- which is what distinguishes it from the same event the clone path writes,
    and the difference matters because that one is a security incident.

    **Sessions already opened with it are left alone**, deliberately and unlike the clone path.
    A clone means the credential exists in two places, so every session for the identity is
    suspect; losing a phone means this credential should not open another session, and ending
    the one the owner is sitting in to tell them so would be a worse answer than the problem.
    Revoking a session is a separate act on the same screen.
    """
    _require_uuid(correlation_id, "correlation_id")
    now = _now()
    with tenant_scope(pool, tenant_id) as conn:
        row = conn.execute(
            "SELECT identity_id, revoked_at FROM iam.passkeys WHERE passkey_id = %s",
            (passkey_id,),
        ).fetchone()
        if row is None or str(row[0]) != identity_id:
            # The same 404 for "no such passkey" and "not yours", which is `owned`'s rule: a
            # different answer would say whether a passkey id exists in another account.
            raise NotFound("passkey_not_found")
        if row[1] is not None:
            # Idempotent rather than a conflict: a reader who pressed twice, or whose request
            # timed out after the commit, wanted this credential gone and it is.
            return {"passkey_id": passkey_id, "revoked_at": row[1].isoformat(),
                    "repeated": True}
        conn.execute("UPDATE iam.passkeys SET revoked_at = %s WHERE passkey_id = %s",
                     (now, passkey_id))
        _event(conn, tenant_id, kind="passkey.revoked", outcome="succeeded",
               identity_id=identity_id, factor="passkey", reason="withdrawn_by_owner",
               correlation_id=correlation_id)
    return {"passkey_id": passkey_id, "revoked_at": now.isoformat(), "repeated": False}


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
    if limit < 1 or limit > EVENT_PAGE:
        # **Refuse rather than clamp**, which is what this did and what `list_sessions` beside
        # it does not. A silent clamp answers a request for a thousand rows with five hundred
        # and says nothing, so a caller that asked for everything renders what it got and
        # believes it has the lot -- the same shape as "a default is not a setting". MOD-017's
        # and MOD-018's listing reads both refuse, which makes this the odd one in the build.
        raise InvalidRequest("bad_limit")
    with tenant_scope(pool, tenant_id) as conn:
        _require_identity(conn, identity_id)
        rows = conn.execute(
            "SELECT identity_id, kind, outcome, factor, reason, occurred_at"
            " FROM iam.auth_events WHERE identity_id = %s"
            " ORDER BY occurred_at DESC, event_id DESC LIMIT %s",
            (identity_id, limit),
        ).fetchall()
    return [
        {"identity_id": str(r[0]) if r[0] else None, "kind": r[1], "outcome": r[2],
         "factor": r[3], "reason": r[4], "occurred_at": r[5].isoformat()} for r in rows
    ]

"""MOD-007 IAM-01: the cryptographic primitives, kept in one small file on purpose.

Everything here is pure and uses only the standard library. No secret in this module is ever
logged, returned in an error, or compared with `==`.

**What is implemented, and what deliberately is not.** Password and recovery-code hashing, session
token minting and digesting, and the TOTP algorithm are here and tested. WebAuthn signature
verification is **not**: verifying an assertion means parsing CBOR, decoding COSE keys and
checking ECDSA or RSA signatures, and hand-rolling that is how authentication bypasses get
written. `app.identity.policy` carries the parts of passkey handling that are pure logic -- the
sign-count clone check, challenge expiry and single use -- and the signature step waits for a
vetted library. The schema stores what such a library would need.

**Why scrypt and not a bare hash.** A password is low-entropy, so the only defence against an
offline attack on a stolen table is making each guess expensive. `hashlib.scrypt` is memory-hard
and in the standard library, so it needs no dependency and no build step. Parameters are stored
alongside each hash, so raising them later re-hashes on next use instead of invalidating
everyone's password at once.

**Why a session token is only SHA-256'd.** It is 256 bits straight from the system CSPRNG, so
there is no dictionary to slow down and nothing to be gained by a memory-hard function -- while
a slow hash on every authenticated request would be a denial-of-service surface of its own. What
matters is that the digest is what is stored, so a copy of the table cannot be used to log in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets as stdlib_secrets
import struct
import unicodedata
from dataclasses import dataclass
from typing import Any

SCRYPT = "scrypt"

# n=2**14, r=8, p=1 costs about 16 MiB and a few milliseconds per hash. Stored per credential,
# so these can be raised without a migration: an old hash keeps verifying under its own
# parameters and is re-hashed the next time its owner proves it.
DEFAULT_SCRYPT_PARAMS: dict[str, int] = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}

SALT_BYTES = 16
TOKEN_BYTES = 32


class SecretError(ValueError):
    """A stored credential is malformed. Never carries the secret or any part of it."""


@dataclass(frozen=True)
class HashedSecret:
    algorithm: str
    salt: bytes
    digest: bytes
    params: dict[str, int]


def _normalize(secret: str) -> bytes:
    """NFKC, so a password typed on a different keyboard still matches.

    Without normalisation the same characters entered through different input methods produce
    different byte strings and a correct password is rejected. Composed and decomposed forms of
    accented characters are the common case.
    """
    return unicodedata.normalize("NFKC", secret).encode("utf-8")


def hash_secret(secret: str, *, params: dict[str, int] | None = None) -> HashedSecret:
    """Hash a password or recovery code with a fresh random salt."""
    if not secret:
        raise SecretError("secret must not be empty")
    chosen = {**DEFAULT_SCRYPT_PARAMS, **(params or {})}
    salt = stdlib_secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        _normalize(secret), salt=salt, n=chosen["n"], r=chosen["r"], p=chosen["p"],
        dklen=chosen["dklen"], maxmem=_maxmem(chosen),
    )
    return HashedSecret(algorithm=SCRYPT, salt=salt, digest=digest, params=chosen)


def _maxmem(params: dict[str, int]) -> int:
    """scrypt needs roughly 128 * n * r bytes; OpenSSL refuses above its own default of 32 MiB."""
    return 128 * params["n"] * params["r"] * 2


def verify_secret(stored: HashedSecret, candidate: str) -> bool:
    """Constant-time check of a candidate against a stored hash.

    `hmac.compare_digest` rather than `==`: a byte-by-byte comparison returns sooner for a wrong
    first byte than for a wrong last one, and that difference is measurable over enough attempts.
    A malformed stored row raises rather than returning False, because "this credential is
    corrupt" and "this password is wrong" are different problems and must not look alike.
    """
    if stored.algorithm != SCRYPT:
        raise SecretError(f"unsupported algorithm {stored.algorithm!r}")
    if len(stored.salt) < SALT_BYTES:
        raise SecretError("stored salt is too short")
    if not candidate:
        return False
    computed = hashlib.scrypt(
        _normalize(candidate), salt=stored.salt, n=stored.params["n"], r=stored.params["r"],
        p=stored.params["p"], dklen=stored.params.get("dklen", 32),
        maxmem=_maxmem(stored.params),
    )
    return hmac.compare_digest(computed, stored.digest)


def needs_rehash(stored: HashedSecret, *, params: dict[str, int] | None = None) -> bool:
    """Whether a verified credential was hashed under weaker parameters than today's."""
    wanted = {**DEFAULT_SCRYPT_PARAMS, **(params or {})}
    return any(stored.params.get(k, 0) < v for k, v in wanted.items())


# --------------------------------------------------------------------------- session tokens

@dataclass(frozen=True)
class MintedToken:
    token: str
    """Returned to the caller once. Never stored, never logged."""
    digest: bytes
    """What goes in the database."""


def mint_session_token() -> MintedToken:
    return MintedToken(token=(raw := stdlib_secrets.token_urlsafe(TOKEN_BYTES)),
                       digest=digest_token(raw))


def digest_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def tokens_match(presented: str, stored_digest: bytes) -> bool:
    return hmac.compare_digest(digest_token(presented), stored_digest)


def mint_nonce() -> MintedToken:
    """A challenge nonce. Same shape as a session token and stored the same way."""
    return mint_session_token()


# --------------------------------------------------------------------------- recovery codes

def generate_recovery_codes(count: int = 10, *, groups: int = 3, group_size: int = 4) -> list[str]:
    """Human-transcribable one-time codes, from the system CSPRNG.

    The alphabet omits characters that are read wrongly off a screen or a printout -- 0/O and
    1/I/L -- because a recovery code is used exactly when the user is already locked out and has
    no way to check a typo against anything.
    """
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    if count < 1 or groups < 1 or group_size < 1:
        raise SecretError("recovery code shape must be positive")
    codes = []
    for _ in range(count):
        parts = [
            "".join(stdlib_secrets.choice(alphabet) for _ in range(group_size))
            for _ in range(groups)
        ]
        codes.append("-".join(parts))
    return codes


# --------------------------------------------------------------------------- TOTP (RFC 6238)

def hotp(secret: bytes, counter: int, *, digits: int = 6, algorithm: str = "sha1") -> str:
    """RFC 4226 HOTP. The building block for TOTP; tested against the RFC's own vectors."""
    if counter < 0:
        raise SecretError("counter must not be negative")
    mac = hmac.new(secret, struct.pack(">Q", counter), algorithm).digest()
    offset = mac[-1] & 0x0F
    truncated = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


def totp(secret: bytes, timestamp: int, *, step: int = 30, digits: int = 6,
         algorithm: str = "sha1") -> str:
    """RFC 6238 TOTP.

    Implemented and tested, but **nothing in this codebase enrols a TOTP factor**: verifying a
    code needs the shared secret back in plaintext, which means encryption at rest with a key
    from a vault the repository does not have. The migration says the same thing where the column
    would be. This function exists so that wiring it up later is a service change rather than a
    cryptography exercise.
    """
    if step <= 0:
        raise SecretError("step must be positive")
    return hotp(secret, timestamp // step, digits=digits, algorithm=algorithm)


def totp_matches(secret: bytes, timestamp: int, presented: str, *, step: int = 30,
                 digits: int = 6, algorithm: str = "sha1", drift_steps: int = 1) -> bool:
    """Compare in constant time, allowing a small clock drift either way.

    `drift_steps` widens the window the code is accepted in, and widening it costs security
    linearly: every extra step is another code an attacker may guess. One step each way is the
    usual compromise for a 30-second period.
    """
    if drift_steps < 0:
        raise SecretError("drift must not be negative")
    accepted = False
    for offset in range(-drift_steps, drift_steps + 1):
        candidate = totp(secret, timestamp + offset * step, step=step, digits=digits,
                         algorithm=algorithm)
        # No early exit: checking every window keeps the running time independent of which one
        # matched, so the response does not say how far the client's clock is out.
        accepted |= hmac.compare_digest(candidate, presented)
    return accepted


def base32_secret(secret: bytes) -> str:
    """The form an authenticator app expects in a provisioning URI."""
    return base64.b32encode(secret).decode("ascii").rstrip("=")


def serialize_params(params: dict[str, int]) -> dict[str, Any]:
    """Stored as jsonb; kept explicit so a stray value cannot reach the column."""
    return {k: int(params[k]) for k in ("n", "r", "p", "dklen") if k in params}

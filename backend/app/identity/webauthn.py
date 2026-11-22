"""WebAuthn assertion verification -- the decision half, with no I/O.

**This closes MOD-007's longest-standing deliberate gap**, and the gap's own wording is why the
shape here is what it is: "the WebAuthn signature is not verified -- CBOR, COSE and ECDSA, and
hand-rolling it is how authentication bypasses get written". So nothing here is hand-rolled
crypto: the signature check is `cryptography`'s, and the parsing is of two fixed binary shapes
that the specification pins byte for byte.

**And no CBOR is parsed at all.** A COSE_Key is CBOR, and this module never sees one:
`enroll_passkey` takes the SPKI DER that `AuthenticatorAttestationResponse.getPublicKey()`
returns in every browser that can do WebAuthn Level 2, which `cryptography` loads directly. A
CBOR decoder in the authentication path is a larger attack surface than the key it decodes, and
the signature is what proves possession either way -- a client that substituted a public key it
did not hold could only enrol a credential it does hold, which is what the endpoint is for.

**What this module refuses rather than decides:**

* **A passkey with no user verification is not a factor.** `UV` means the authenticator checked
  a biometric or a PIN; without it an assertion proves possession of a device and nothing about
  who is holding it. WebAuthn allows that case and this build has no factor name for it, so it
  is refused with a reason rather than quietly counted as one -- which would be inventing a
  level.
* **The RP id and the origins come from configuration with no default.** They are deployment
  facts, not engineering ones: the same precedent as MOD-015's tax rate and MOD-009's
  `response_days`. `check_assertion` takes them and `config` refuses to guess them.
* **`alg` is a closed set.** ES256, Ed25519 and RS256 cover every shipping authenticator;
  anything else is refused at enrolment, where somebody can read the reason, rather than at the
  moment they are trying to sign in.

Every refusal is a code from `REASONS`, and `check_split` runs at import to keep the two in
agreement -- MOD-010's argument, applied to a vocabulary the service turns into one uniform
401. The caller never sees which code: a refusal that said why would be an oracle about which
credentials exist, which is MOD-007's own rule.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Final

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.serialization import load_der_public_key


class WebAuthnError(Exception):
    """A refusal, carrying a code from `REASONS` and nothing a caller may be told."""

    def __init__(self, code: str, detail: str) -> None:
        if code not in REASONS:
            raise AssertionError(f"{code!r} is not a declared WebAuthn reason")
        super().__init__(detail)
        self.code = code
        self.detail = detail


#: Every way an assertion can be refused. A closed set, because the service logs the code and
#: answers the caller with one shape -- so a code added without a thought about what the log
#: will say is a code nobody can act on.
REASONS: Final[frozenset[str]] = frozenset({
    "client_data_unparseable",
    "wrong_ceremony",
    "challenge_mismatch",
    "origin_not_allowed",
    "cross_origin",
    "authenticator_data_short",
    "rp_id_mismatch",
    "user_not_present",
    "user_not_verified",
    "unsupported_algorithm",
    "public_key_unusable",
    "signature_invalid",
})

#: COSE algorithm identifiers this build will verify. ES256 is what every platform
#: authenticator uses; Ed25519 is what several security keys use; RS256 is what the older
#: Windows Hello implementations use. Anything else is refused at enrolment.
ES256: Final = -7
ED25519: Final = -8
RS256: Final = -257
SUPPORTED_ALGORITHMS: Final[tuple[int, ...]] = (ES256, ED25519, RS256)

#: `authenticatorData` is 37 bytes before any attested credential data: 32 of RP id hash, one
#: of flags, four of signature counter, big-endian. Fixed by the specification.
_RP_ID_HASH_LENGTH: Final = 32
_FLAGS_AT: Final = 32
_SIGN_COUNT_AT: Final = 33
_MINIMUM_AUTH_DATA: Final = 37

_FLAG_UP: Final = 0x01
_FLAG_UV: Final = 0x04
_FLAG_BE: Final = 0x08
_FLAG_BS: Final = 0x10
_FLAG_AT: Final = 0x40
_FLAG_ED: Final = 0x80


@dataclass(frozen=True)
class AuthenticatorData:
    """The authenticator's own 37-byte preamble, parsed and nothing more."""

    rp_id_hash: bytes
    user_present: bool
    user_verified: bool
    backup_eligible: bool
    backed_up: bool
    attested_credential_data: bool
    extension_data: bool
    sign_count: int


@dataclass(frozen=True)
class ClientData:
    """What the browser signed over, as the browser serialised it."""

    type: str
    challenge: bytes
    origin: str
    cross_origin: bool


@dataclass(frozen=True)
class Verified:
    """An assertion that verified, and the two facts the caller acts on."""

    factor: str
    sign_count: int
    user_verified: bool
    backed_up: bool


def rp_id_hash(rp_id: str) -> bytes:
    """The hash an authenticator puts in `authenticatorData`, for comparison."""
    return hashlib.sha256(rp_id.encode("utf-8")).digest()


def b64url_decode(value: str) -> bytes:
    """Decode WebAuthn's unpadded base64url, refusing anything that is not that.

    **Strict, because `base64.urlsafe_b64decode` is not.** It accepts the standard alphabet's
    `+` and `/` as well, and ignores trailing garbage in some inputs -- so a challenge written
    two ways could compare equal to two different byte strings. A lenient decoder in a nonce
    comparison is how a replay gets in.
    """
    if value.strip("=") != value or any(c in value for c in "+/"):
        raise WebAuthnError("client_data_unparseable",
                            "a base64url value carries no padding and no + or /")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise WebAuthnError("client_data_unparseable", f"not base64url: {exc}") from None


def parse_client_data(raw: bytes) -> ClientData:
    """Parse `clientDataJSON` without trusting a single field in it."""
    try:
        parsed: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebAuthnError("client_data_unparseable", f"not JSON: {exc}") from None
    if not isinstance(parsed, dict):
        raise WebAuthnError("client_data_unparseable", "clientData is not an object")
    for field in ("type", "challenge", "origin"):
        if not isinstance(parsed.get(field), str):
            raise WebAuthnError("client_data_unparseable", f"{field} is missing or not a string")
    cross = parsed.get("crossOrigin", False)
    if not isinstance(cross, bool):
        raise WebAuthnError("client_data_unparseable", "crossOrigin is not a boolean")
    return ClientData(type=str(parsed["type"]), challenge=b64url_decode(str(parsed["challenge"])),
                      origin=str(parsed["origin"]), cross_origin=cross)


def parse_authenticator_data(raw: bytes) -> AuthenticatorData:
    """Parse the fixed preamble. Anything after byte 37 is not this module's business."""
    if len(raw) < _MINIMUM_AUTH_DATA:
        raise WebAuthnError("authenticator_data_short",
                            f"authenticatorData is {len(raw)} bytes, under {_MINIMUM_AUTH_DATA}")
    flags = raw[_FLAGS_AT]
    return AuthenticatorData(
        rp_id_hash=raw[:_RP_ID_HASH_LENGTH],
        user_present=bool(flags & _FLAG_UP),
        user_verified=bool(flags & _FLAG_UV),
        backup_eligible=bool(flags & _FLAG_BE),
        backed_up=bool(flags & _FLAG_BS),
        attested_credential_data=bool(flags & _FLAG_AT),
        extension_data=bool(flags & _FLAG_ED),
        sign_count=int.from_bytes(raw[_SIGN_COUNT_AT:_MINIMUM_AUTH_DATA], "big"),
    )


def factor_for(*, backup_eligible: bool) -> str:
    """Which factor name an assertion presents, from the flag that decides it.

    **`BE`, not `BS`.** Backup *eligibility* is a property of the credential -- whether this
    private key may ever leave the authenticator -- and it is set at creation and never
    changes. `BS` says whether it currently *is* backed up, which flips the first time somebody
    turns on a keychain: a credential that reached level 3 on Monday would reach it again on
    Tuesday having been synced in between. The eligibility is the durable fact, and
    `FACTOR_ASSURANCE`'s own comment is about exactly this distinction -- "a passkey synced to a
    cloud keychain is a strong factor but not a hardware-bound one".
    """
    return "passkey_synced" if backup_eligible else "passkey_hardware"


def load_public_key(spki_der: bytes, algorithm: int) -> Any:
    """Load an SPKI DER public key and check it matches the algorithm it claims.

    **The algorithm and the key have to agree**, or the claim decides the verification: a caller
    naming Ed25519 over an RSA key would otherwise reach a branch that was never going to check
    an RSA signature. This is the "never believe a caller's description of itself" rule applied
    to a format rather than to a factor.
    """
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise WebAuthnError("unsupported_algorithm", f"COSE algorithm {algorithm} is not one of "
                                                     f"{SUPPORTED_ALGORITHMS}")
    try:
        key = load_der_public_key(spki_der)
    except (ValueError, UnsupportedAlgorithm) as exc:
        raise WebAuthnError("public_key_unusable", f"not an SPKI public key: {exc}") from None
    if algorithm == ES256:
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(
                key.curve, ec.SECP256R1):
            raise WebAuthnError("public_key_unusable", "ES256 needs a P-256 key")
    elif algorithm == ED25519:
        if not isinstance(key, ed25519.Ed25519PublicKey):
            raise WebAuthnError("public_key_unusable", "Ed25519 needs an Ed25519 key")
    elif not isinstance(key, rsa.RSAPublicKey):
        raise WebAuthnError("public_key_unusable", "RS256 needs an RSA key")
    elif key.key_size < 2048:
        raise WebAuthnError("public_key_unusable", f"an RSA key of {key.key_size} bits is short")
    return key


def algorithm_for_key(spki_der: bytes) -> int:
    """Which COSE algorithm the stored key is for, derived from the key itself.

    **Derive, never accept.** The alternative is a request field saying which algorithm to
    verify with, and a caller choosing how their own signature is checked is this
    repository's most-repeated finding. The derivation is exact *because the set is closed*:
    one key type per supported algorithm, so there is nothing to choose. The day a second
    algorithm over the same key type is admitted -- PS256 beside RS256, say -- this stops being
    derivable and the algorithm needs a column on `iam.passkeys`, which is why the closed set
    is stated here rather than inferred from a mapping somewhere else.
    """
    try:
        key = load_der_public_key(spki_der)
    except (ValueError, UnsupportedAlgorithm) as exc:
        raise WebAuthnError("public_key_unusable", f"not an SPKI public key: {exc}") from None
    if isinstance(key, ec.EllipticCurvePublicKey) and isinstance(key.curve, ec.SECP256R1):
        return ES256
    if isinstance(key, ed25519.Ed25519PublicKey):
        return ED25519
    if isinstance(key, rsa.RSAPublicKey):
        return RS256
    raise WebAuthnError("unsupported_algorithm",
                        f"{type(key).__name__} is not a key this build verifies")


def verify_signature(
    *, public_key: Any, algorithm: int, signed: bytes, signature: bytes,
) -> None:
    """Check the signature, or raise `signature_invalid`. The one place crypto happens."""
    try:
        if algorithm == ES256:
            public_key.verify(signature, signed, ec.ECDSA(hashes.SHA256()))
        elif algorithm == ED25519:
            public_key.verify(signature, signed)
        else:
            public_key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise WebAuthnError("signature_invalid", "the signature does not verify") from None
    except (ValueError, TypeError) as exc:
        # A malformed DER signature reaches `cryptography` as a ValueError rather than an
        # InvalidSignature, and a caller controls those bytes -- so it is a refusal, not a 500.
        raise WebAuthnError("signature_invalid", f"unusable signature: {exc}") from None


def signed_bytes(authenticator_data: bytes, client_data_json: bytes) -> bytes:
    """What an authenticator signs: the raw authenticatorData then the clientData hash."""
    return authenticator_data + hashlib.sha256(client_data_json).digest()


def check_assertion(
    *,
    client_data_json: bytes,
    authenticator_data: bytes,
    signature: bytes,
    expected_challenge: bytes,
    rp_id: str,
    allowed_origins: tuple[str, ...],
    public_key_spki: bytes,
    algorithm: int,
    require_user_verification: bool = True,
) -> Verified:
    """Verify one assertion, in the order the specification puts the checks in.

    Cheapest and most structural first, the signature last: a malformed origin should not cost
    an elliptic-curve verification, and nothing after a failed check is evaluated.

    **The challenge is compared in constant time**, because it is a secret the server issued and
    a timing difference on a nonce comparison is a replay oracle. `hmac.compare_digest` is the
    stdlib's answer and `secrets.py` already uses it for every other digest here.
    """
    client = parse_client_data(client_data_json)
    if client.type != "webauthn.get":
        # **The cross-ceremony binding.** A registration ceremony's clientData says
        # `webauthn.create`, so without this check a signature made while enrolling would
        # verify as a sign-in.
        raise WebAuthnError("wrong_ceremony", f"clientData type is {client.type!r}")
    if not hmac.compare_digest(client.challenge, expected_challenge):
        raise WebAuthnError("challenge_mismatch", "the challenge is not the one issued")
    if client.origin not in allowed_origins:
        raise WebAuthnError("origin_not_allowed", f"{client.origin!r} is not an allowed origin")
    if client.cross_origin:
        raise WebAuthnError("cross_origin", "the ceremony ran in a cross-origin frame")

    auth = parse_authenticator_data(authenticator_data)
    if not hmac.compare_digest(auth.rp_id_hash, rp_id_hash(rp_id)):
        raise WebAuthnError("rp_id_mismatch", "the authenticator signed for another relying party")
    if not auth.user_present:
        raise WebAuthnError("user_not_present", "the user-present flag is not set")
    if require_user_verification and not auth.user_verified:
        # **A passkey with no user verification is not a factor here.** It proves possession of
        # a device and says nothing about who holds it, and this build has no factor name for
        # that -- so it is refused rather than counted as one, which would be inventing a level.
        raise WebAuthnError("user_not_verified", "the authenticator did not verify the user")

    key = load_public_key(public_key_spki, algorithm)
    verify_signature(public_key=key, algorithm=algorithm,
                     signed=signed_bytes(authenticator_data, client_data_json),
                     signature=signature)
    return Verified(factor=factor_for(backup_eligible=auth.backup_eligible),
                    sign_count=auth.sign_count, user_verified=auth.user_verified,
                    backed_up=auth.backed_up)


def check_split() -> None:
    """Every code `WebAuthnError` can be raised with is declared, and every declared code is
    raised somewhere.

    MOD-010's check-at-import argument: a reason nobody raises is a branch nobody wrote, and a
    raise with an undeclared code would be a refusal the service's own mapping has no entry
    for -- found at the moment somebody is trying to sign in rather than at import.
    """
    import inspect
    import re

    source = inspect.getsource(inspect.getmodule(check_split) or check_split)
    raised = set(re.findall(r'WebAuthnError\(\s*"([a-z_]+)"', source))
    undeclared = raised - REASONS
    if undeclared:
        raise AssertionError(f"undeclared WebAuthn reasons raised: {sorted(undeclared)}")
    unraised = REASONS - raised
    if unraised:
        raise AssertionError(f"declared WebAuthn reasons nobody raises: {sorted(unraised)}")


check_split()

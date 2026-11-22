"""WebAuthn assertion verification, against signatures and against every way to break one.

**There are no published signed vectors for this, and saying so is better than implying
there are.** MOD-007's TOTP work could assert all eighteen RFC 4226 and RFC 6238 vectors;
WebAuthn's specification publishes the *structures* byte for byte and no signed examples, and
the FIDO conformance vectors are a licensed test suite rather than something to embed. So the
assertions here are built from a key pair this module generates, which proves the verifier
accepts a correct signature -- and what makes that evidence rather than a tautology is the
negative space: **every field, every flag and the signature itself is mutated by one byte or
one bit from an assertion that verifies, and each mutation has to be refused with its own
reason.** A verifier that accepted a signature it generated and nothing else would pass the
first test and fail twenty of the rest.

The structural halves are pinned against the specification directly: a 37-byte
`authenticatorData` with the flag bits at their stated positions, and `clientDataJSON`'s three
mandatory fields.
"""

from __future__ import annotations

import base64
import hashlib
import json
import unittest
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

from app.identity import webauthn

RP_ID = "veyro.example"
ORIGIN = "https://veyro.example"
CHALLENGE = b"\x01" * 32


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def client_data(
    *, kind: str = "webauthn.get", challenge: bytes = CHALLENGE, origin: str = ORIGIN,
    cross: bool | None = None,
) -> bytes:
    body: dict[str, Any] = {"type": kind, "challenge": b64url(challenge), "origin": origin}
    if cross is not None:
        body["crossOrigin"] = cross
    return json.dumps(body).encode("utf-8")


def auth_data(
    *, rp_id: str = RP_ID, up: bool = True, uv: bool = True, be: bool = False,
    bs: bool = False, sign_count: int = 7,
) -> bytes:
    flags = (0x01 if up else 0) | (0x04 if uv else 0) | (0x08 if be else 0) | (0x10 if bs else 0)
    return (hashlib.sha256(rp_id.encode()).digest() + bytes([flags])
            + sign_count.to_bytes(4, "big"))


class Credential:
    """A key pair and the SPKI DER a browser's `getPublicKey()` would hand over."""

    def __init__(self, algorithm: int) -> None:
        self.algorithm = algorithm
        if algorithm == webauthn.ES256:
            self.private: Any = ec.generate_private_key(ec.SECP256R1())
        elif algorithm == webauthn.ED25519:
            self.private = ed25519.Ed25519PrivateKey.generate()
        else:
            self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.spki = self.private.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)

    def sign(self, signed: bytes) -> bytes:
        if self.algorithm == webauthn.ES256:
            return bytes(self.private.sign(signed, ec.ECDSA(hashes.SHA256())))
        if self.algorithm == webauthn.ED25519:
            return bytes(self.private.sign(signed))
        return bytes(self.private.sign(signed, padding.PKCS1v15(), hashes.SHA256()))


# One ES256 credential for the bulk of the suite: generating an RSA key per test is seconds of
# wall clock for no extra property, and the algorithm-specific cases have their own below.
ES256_CREDENTIAL = Credential(webauthn.ES256)


def assertion(
    *, credential: Credential = ES256_CREDENTIAL, client: bytes | None = None,
    authenticator: bytes | None = None, signature: bytes | None = None,
) -> dict[str, Any]:
    """An assertion that verifies, unless the caller replaced a part of it."""
    client = client_data() if client is None else client
    authenticator = auth_data() if authenticator is None else authenticator
    signed = webauthn.signed_bytes(authenticator, client)
    return {
        "client_data_json": client,
        "authenticator_data": authenticator,
        "signature": credential.sign(signed) if signature is None else signature,
        "expected_challenge": CHALLENGE,
        "rp_id": RP_ID,
        "allowed_origins": (ORIGIN,),
        "public_key_spki": credential.spki,
        "algorithm": credential.algorithm,
    }


class StructureTests(unittest.TestCase):
    """The two binary shapes, pinned against the specification rather than against a library."""

    def test_authenticator_data_is_thirty_seven_bytes_before_anything_else(self) -> None:
        raw = auth_data()
        self.assertEqual(len(raw), 37)
        parsed = webauthn.parse_authenticator_data(raw)
        self.assertEqual(parsed.rp_id_hash, hashlib.sha256(RP_ID.encode()).digest())
        self.assertEqual(parsed.sign_count, 7)

    def test_every_flag_is_read_from_its_stated_bit(self) -> None:
        # UP 0x01, UV 0x04, BE 0x08, BS 0x10, AT 0x40, ED 0x80. A flag read from the wrong bit
        # is a control that fires on an unrelated authenticator property.
        for bit, field in ((0x01, "user_present"), (0x04, "user_verified"),
                           (0x08, "backup_eligible"), (0x10, "backed_up"),
                           (0x40, "attested_credential_data"), (0x80, "extension_data")):
            raw = bytearray(auth_data(up=False, uv=False))
            raw[32] = bit
            parsed = webauthn.parse_authenticator_data(bytes(raw))
            for other in ("user_present", "user_verified", "backup_eligible", "backed_up",
                          "attested_credential_data", "extension_data"):
                self.assertEqual(getattr(parsed, other), other == field,
                                 f"bit {bit:#04x} set {other}")

    def test_a_short_authenticator_data_is_refused_rather_than_sliced(self) -> None:
        # 36 bytes slices without raising in Python and yields a sign count of whatever is
        # left, which is a counter an attacker chooses.
        with self.assertRaises(webauthn.WebAuthnError) as caught:
            webauthn.parse_authenticator_data(auth_data()[:36])
        self.assertEqual(caught.exception.code, "authenticator_data_short")

    def test_the_signed_message_is_the_data_then_the_client_hash(self) -> None:
        # Paragraph 7.2 step 19. Hashing the authenticatorData too, or concatenating the other
        # way round, produces a verifier that agrees with nothing.
        client, authenticator = client_data(), auth_data()
        self.assertEqual(
            webauthn.signed_bytes(authenticator, client),
            authenticator + hashlib.sha256(client).digest())

    def test_base64url_is_strict_about_its_own_alphabet(self) -> None:
        # **`base64.urlsafe_b64decode` is not.** It accepts `+` and `/` as well, so one
        # challenge could be written two ways and compare equal to two different byte
        # strings -- a lenient decoder in a nonce comparison is how a replay gets in.
        self.assertEqual(webauthn.b64url_decode(b64url(CHALLENGE)), CHALLENGE)
        for bad in ("AAAA=", "++++", "a/a/"):
            with self.assertRaises(webauthn.WebAuthnError, msg=bad):
                webauthn.b64url_decode(bad)


class AcceptanceTests(unittest.TestCase):
    """What a correct assertion is, for each algorithm this build will verify."""

    def test_every_supported_algorithm_verifies(self) -> None:
        for algorithm in webauthn.SUPPORTED_ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                verified = webauthn.check_assertion(**assertion(credential=Credential(algorithm)))
                self.assertEqual(verified.sign_count, 7)
                self.assertTrue(verified.user_verified)

    def test_a_device_bound_credential_is_the_hardware_factor(self) -> None:
        verified = webauthn.check_assertion(**assertion(authenticator=auth_data(be=False)))
        self.assertEqual(verified.factor, "passkey_hardware")

    def test_a_backup_eligible_credential_is_the_synced_factor(self) -> None:
        # **`BE`, not `BS`.** Eligibility is set at creation and never changes; `BS` flips the
        # first time somebody turns a keychain on, so a credential that reached level 3 on
        # Monday would reach it again on Tuesday having been synced in between.
        self.assertEqual(
            webauthn.check_assertion(**assertion(authenticator=auth_data(be=True))).factor,
            "passkey_synced")
        self.assertEqual(
            webauthn.check_assertion(
                **assertion(authenticator=auth_data(be=True, bs=True))).factor,
            "passkey_synced")
        self.assertEqual(
            webauthn.check_assertion(
                **assertion(authenticator=auth_data(be=False, bs=True))).factor,
            "passkey_hardware")

    def test_an_absent_cross_origin_field_is_not_cross_origin(self) -> None:
        # The field is optional and its default is false. Treating absence as true would refuse
        # every assertion from a browser that omits it.
        webauthn.check_assertion(**assertion(client=client_data(cross=None)))
        webauthn.check_assertion(**assertion(client=client_data(cross=False)))


class RefusalTests(unittest.TestCase):
    """Every way to break an assertion that verifies, one change at a time.

    This is the half that makes the suite evidence. Each case starts from the assertion
    `AcceptanceTests` proves, changes exactly one thing, and requires its own reason -- so a
    check removed from `check_assertion` fails here by name rather than by a signature that
    happens to stop verifying.
    """

    def refused(self, code: str, **overrides: Any) -> None:
        with self.assertRaises(webauthn.WebAuthnError) as caught:
            webauthn.check_assertion(**{**assertion(), **overrides})
        self.assertEqual(caught.exception.code, code)

    def test_a_registration_ceremony_does_not_verify_as_a_sign_in(self) -> None:
        # **The cross-ceremony binding.** Without the type check, a signature made while
        # enrolling -- over a challenge the server also issued -- would open a session.
        self.refused("wrong_ceremony", **_resigned(client_data(kind="webauthn.create")))

    def test_another_challenge_is_refused(self) -> None:
        self.refused("challenge_mismatch", **_resigned(client_data(challenge=b"\x02" * 32)))

    def test_a_challenge_of_the_right_length_but_the_wrong_value_is_refused(self) -> None:
        # The comparison is over bytes rather than over lengths, which a `len` check would pass.
        other = bytearray(CHALLENGE)
        other[31] ^= 0x01
        self.refused("challenge_mismatch", **_resigned(client_data(challenge=bytes(other))))

    def test_an_origin_outside_the_allow_list_is_refused(self) -> None:
        self.refused("origin_not_allowed", **_resigned(client_data(origin="https://evil.example")))

    def test_a_lookalike_origin_is_refused_because_the_match_is_exact(self) -> None:
        for origin in ("https://veyro.example.evil.com", "http://veyro.example",
                       "https://veyro.example:8443", "https://sub.veyro.example"):
            with self.subTest(origin=origin):
                self.refused("origin_not_allowed", **_resigned(client_data(origin=origin)))

    def test_a_cross_origin_ceremony_is_refused(self) -> None:
        self.refused("cross_origin", **_resigned(client_data(cross=True)))

    def test_an_assertion_signed_for_another_relying_party_is_refused(self) -> None:
        self.refused("rp_id_mismatch", **_resigned(authenticator=auth_data(rp_id="evil.example")))

    def test_an_absent_user_present_flag_is_refused(self) -> None:
        self.refused("user_not_present", **_resigned(authenticator=auth_data(up=False)))

    def test_an_unverified_user_is_refused_rather_than_counted_as_a_weaker_factor(self) -> None:
        # This build has no factor name for "a device was present and nobody was checked", so
        # counting it would be inventing a level.
        self.refused("user_not_verified", **_resigned(authenticator=auth_data(uv=False)))

    def test_user_verification_can_be_waived_only_by_the_caller_saying_so(self) -> None:
        verified = webauthn.check_assertion(
            **{**assertion(), **_resigned(authenticator=auth_data(uv=False)),
               "require_user_verification": False})
        self.assertFalse(verified.user_verified)

    def test_a_tampered_signature_is_refused(self) -> None:
        signature = bytearray(assertion()["signature"])
        signature[-1] ^= 0x01
        self.refused("signature_invalid", signature=bytes(signature))

    def test_an_empty_or_malformed_signature_is_a_refusal_rather_than_a_crash(self) -> None:
        # A malformed DER signature reaches `cryptography` as a ValueError rather than an
        # InvalidSignature, and a caller controls those bytes -- so it is a 401, not a 500.
        for signature in (b"", b"\x00", b"not der at all"):
            with self.subTest(signature=signature):
                self.refused("signature_invalid", signature=signature)

    def test_another_credential_cannot_sign_for_this_one(self) -> None:
        self.refused("signature_invalid", signature=Credential(webauthn.ES256).sign(
            webauthn.signed_bytes(auth_data(), client_data())))

    def test_changing_the_authenticator_data_after_signing_is_refused(self) -> None:
        # The signature covers authenticatorData verbatim, so a sign count raised by hand --
        # the obvious way past the clone check -- breaks the signature.
        self.refused("signature_invalid", authenticator_data=auth_data(sign_count=9999))

    def test_changing_the_client_data_after_signing_is_refused(self) -> None:
        # And it covers the hash of clientDataJSON, so re-serialising it differently fails too.
        self.refused("signature_invalid",
                     client_data_json=client_data().replace(b'"type"', b'"type" '))

    def test_unparseable_client_data_is_refused_with_its_own_reason(self) -> None:
        for raw in (b"", b"not json", b"[]", b'{"type":1}', b'"a string"',
                    b"\xff\xfe", b'{"type":"webauthn.get"}'):
            with self.subTest(raw=raw):
                self.refused("client_data_unparseable", client_data_json=raw)

    def test_a_non_boolean_cross_origin_is_refused_rather_than_coerced(self) -> None:
        # `if "true"` is truthy and `if "false"` is too, so coercion here would make a string
        # the control. The field is a boolean or it is nothing.
        raw = json.dumps({"type": "webauthn.get", "challenge": b64url(CHALLENGE),
                          "origin": ORIGIN, "crossOrigin": "false"}).encode()
        self.refused("client_data_unparseable", client_data_json=raw)


class KeyTests(unittest.TestCase):
    """The key and the algorithm have to agree, which is derive-don't-accept over a format."""

    def test_an_algorithm_outside_the_closed_set_is_refused(self) -> None:
        with self.assertRaises(webauthn.WebAuthnError) as caught:
            webauthn.load_public_key(ES256_CREDENTIAL.spki, -65535)
        self.assertEqual(caught.exception.code, "unsupported_algorithm")

    def test_a_key_that_is_not_spki_der_is_refused(self) -> None:
        for raw in (b"", b"\x30\x00", b"-----BEGIN PUBLIC KEY-----", b"\x01" * 64):
            with self.subTest(raw=raw):
                with self.assertRaises(webauthn.WebAuthnError) as caught:
                    webauthn.load_public_key(raw, webauthn.ES256)
                self.assertEqual(caught.exception.code, "public_key_unusable")

    def test_an_algorithm_that_disagrees_with_the_key_is_refused(self) -> None:
        # **Never believe a caller's description of itself**, applied to a format: naming
        # Ed25519 over a P-256 key would otherwise reach a branch that was never going to
        # check an ECDSA signature.
        es256, ed, rsa_key = (ES256_CREDENTIAL, Credential(webauthn.ED25519),
                              Credential(webauthn.RS256))
        for spki, algorithm in ((es256.spki, webauthn.ED25519), (es256.spki, webauthn.RS256),
                                (ed.spki, webauthn.ES256), (ed.spki, webauthn.RS256),
                                (rsa_key.spki, webauthn.ES256), (rsa_key.spki, webauthn.ED25519)):
            with self.subTest(algorithm=algorithm):
                with self.assertRaises(webauthn.WebAuthnError) as caught:
                    webauthn.load_public_key(spki, algorithm)
                self.assertEqual(caught.exception.code, "public_key_unusable")

    def test_a_curve_other_than_p256_is_refused_for_es256(self) -> None:
        # ES256 is P-256 by definition, and `cryptography` would happily verify a P-384 key
        # against a SHA-256 ECDSA signature -- a different algorithm wearing the same number.
        other = ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)
        with self.assertRaises(webauthn.WebAuthnError) as caught:
            webauthn.load_public_key(other, webauthn.ES256)
        self.assertEqual(caught.exception.code, "public_key_unusable")

    def test_a_short_rsa_key_is_refused(self) -> None:
        short = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        spki = short.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)
        with self.assertRaises(webauthn.WebAuthnError) as caught:
            webauthn.load_public_key(spki, webauthn.RS256)
        self.assertEqual(caught.exception.code, "public_key_unusable")


class VocabularyTests(unittest.TestCase):
    def test_every_declared_reason_is_raised_and_every_raise_is_declared(self) -> None:
        webauthn.check_split()

    def test_an_undeclared_reason_cannot_be_raised(self) -> None:
        # The constructor refuses, so a service mapping over `REASONS` cannot be handed a code
        # it has no entry for at the moment somebody is signing in.
        with self.assertRaises(AssertionError):
            raise webauthn.WebAuthnError("made_up", "nope")


def _resigned(client: bytes | None = None, authenticator: bytes | None = None) -> dict[str, Any]:
    """An assertion part replaced *and re-signed*, so the change under test is the only one.

    **Without this every structural case would pass on `signature_invalid`**, which is the
    "a case answered by a sibling" trap this repository records for SQL constraints: the
    signature covers both blobs, so changing the origin and leaving the old signature proves
    the signature check and nothing about the origin check.
    """
    client = client_data() if client is None else client
    authenticator = auth_data() if authenticator is None else authenticator
    return {
        "client_data_json": client,
        "authenticator_data": authenticator,
        "signature": ES256_CREDENTIAL.sign(webauthn.signed_bytes(authenticator, client)),
    }


if __name__ == "__main__":
    unittest.main()

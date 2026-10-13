"""Unit tests for `app.version_negotiation` — GOV-01-R07, `SCN-MOD001-115`.

Stdlib only (`unittest`, `hmac`, `hashlib`, `json`), so these run under
`python -m unittest` without the project's pytest harness, while still
being collectable by it later. Pure functions, no database, no network, no
mocking of the subject.

Every value here is synthetic: the verifying key is an explicitly-labeled
fake per `.claude/rules/infra/secrets.md` control 1, the release decisions
are fabricated, and no real client version, store, or Production target is
touched.

Coverage maps to `SCN-MOD001-115`'s three recorded negotiation outcomes
(within-minimum / below-minimum-optional / below-minimum-forced) plus the
authorization negatives `REQUIREMENTS.md` GOV-01-R07's security-
implications text requires: absent and tampered authorization are denied.
"""

from __future__ import annotations

import hmac
import json
import unittest
from hashlib import sha256

from app.version_negotiation import (
    API_VERSION,
    PROBLEM_CONTENT_TYPE,
    PROBLEM_TYPE_BASE,
    AppVersion,
    Disposition,
    ForcedUpdateReason,
    ForcedUpdateReasonNotReserved,
    HmacSha256Verifier,
    MalformedReleaseDecision,
    NegotiationOutcome,
    NegotiationRequest,
    ProblemDetails,
    SignedReleaseDecision,
    negotiate,
    parse_release_decision,
)

# Synthetic, non-secret, never a real credential.
SYNTHETIC_KEY = b"EXAMPLE_NOT_A_REAL_KEY-release-authorization"
SYNTHETIC_OTHER_KEY = b"EXAMPLE_NOT_A_REAL_KEY-different-authority"
SYNTHETIC_DECISION_ID = "SYNTHETIC-RELEASE-DECISION-0001"


def _sign(payload: bytes, key: bytes = SYNTHETIC_KEY) -> str:
    """The issuing authority's half. Deliberately lives in the test, not in
    `version_negotiation.py`, which verifies and never signs."""
    return hmac.new(key, payload, sha256).hexdigest()


def _decision_payload(
    *,
    minimum: str = "2.0.0",
    forced: bool = False,
    reason: str | None = None,
    decision_id: str = SYNTHETIC_DECISION_ID,
    extra: dict[str, object] | None = None,
) -> bytes:
    body: dict[str, object] = {
        "decision_id": decision_id,
        "minimum_supported_version": minimum,
        "forced_update_required": forced,
        "forced_update_reason": reason,
    }
    if extra:
        body.update(extra)
    return json.dumps(body, sort_keys=True).encode("utf-8")


def _request(
    *,
    client: str,
    payload: bytes,
    signature: str | None = None,
    api_version: str = API_VERSION,
) -> NegotiationRequest:
    return NegotiationRequest(
        api_version=api_version,
        client_app_version=client,
        signed_decision=SignedReleaseDecision(
            payload=payload,
            signature=_sign(payload) if signature is None else signature,
        ),
    )


def _verifier() -> HmacSha256Verifier:
    return HmacSha256Verifier(key=SYNTHETIC_KEY)


class _NeverCalledVerifier:
    """Fails the test if authorization is consulted at all."""

    def verify(self, payload: bytes, signature: str) -> bool:
        raise AssertionError("authorization must not be consulted for this request")


class ThreeDispositionsTest(unittest.TestCase):
    """`SCN-MOD001-115`'s three recorded negotiation outcomes."""

    def test_within_minimum_operates_normally(self) -> None:
        payload = _decision_payload(minimum="2.0.0")
        result = negotiate(_request(client="2.3.1", payload=payload), _verifier())

        assert isinstance(result, NegotiationOutcome)
        self.assertEqual(result.disposition, Disposition.ALLOWED)
        self.assertFalse(result.blocked)
        self.assertIsNone(result.forced_update_reason)
        self.assertEqual(result.api_version, API_VERSION)
        self.assertEqual(result.decision_id, SYNTHETIC_DECISION_ID)

    def test_exactly_at_minimum_operates_normally(self) -> None:
        payload = _decision_payload(minimum="2.0.0")
        result = negotiate(_request(client="2.0.0", payload=payload), _verifier())

        assert isinstance(result, NegotiationOutcome)
        self.assertEqual(result.disposition, Disposition.ALLOWED)

    def test_below_minimum_with_only_an_optional_update_operates_with_a_prompt(self) -> None:
        payload = _decision_payload(minimum="2.0.0", forced=False, reason=None)
        result = negotiate(_request(client="1.9.9", payload=payload), _verifier())

        assert isinstance(result, NegotiationOutcome)
        self.assertEqual(result.disposition, Disposition.ALLOWED_WITH_UPDATE_PROMPT)
        self.assertFalse(result.blocked)
        self.assertIsNone(result.forced_update_reason)

    def test_below_minimum_with_an_authorized_security_forced_update_is_blocked(self) -> None:
        payload = _decision_payload(minimum="2.0.0", forced=True, reason="security")
        result = negotiate(_request(client="1.0.0", payload=payload), _verifier())

        assert isinstance(result, NegotiationOutcome)
        self.assertEqual(result.disposition, Disposition.BLOCKED_FORCED_UPDATE)
        self.assertTrue(result.blocked)
        self.assertEqual(result.forced_update_reason, ForcedUpdateReason.SECURITY)
        self.assertEqual(result.minimum_supported_version, AppVersion(2, 0, 0))

    def test_below_minimum_with_an_authorized_critical_incompatibility_is_blocked(self) -> None:
        payload = _decision_payload(minimum="2.0.0", forced=True, reason="critical_incompatibility")
        result = negotiate(_request(client="1.0.0", payload=payload), _verifier())

        assert isinstance(result, NegotiationOutcome)
        self.assertEqual(result.disposition, Disposition.BLOCKED_FORCED_UPDATE)
        self.assertEqual(result.forced_update_reason, ForcedUpdateReason.CRITICAL_INCOMPATIBILITY)

    def test_a_forced_update_cannot_block_a_client_at_or_above_the_minimum(self) -> None:
        """The blast radius of a kill switch is the below-minimum population
        only (`mobile/RELEASE_POLICY.md` §2) — it cannot block the fleet."""
        payload = _decision_payload(minimum="2.0.0", forced=True, reason="security")
        result = negotiate(_request(client="2.0.0", payload=payload), _verifier())

        assert isinstance(result, NegotiationOutcome)
        self.assertEqual(result.disposition, Disposition.ALLOWED)
        self.assertFalse(result.blocked)
        self.assertIsNone(result.forced_update_reason)


class AuthorizationNegativeTest(unittest.TestCase):
    """GOV-01-R07: a forced update/kill switch must not be activatable
    without an authorized release decision. Every case here is a forced-update
    decision that would block if it were trusted."""

    def _forced_payload(self) -> bytes:
        return _decision_payload(minimum="2.0.0", forced=True, reason="security")

    def _assert_denied(self, result: object) -> ProblemDetails:
        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.status, 401)
        self.assertEqual(result.problem_type, f"{PROBLEM_TYPE_BASE}release-decision-unauthorized")
        self.assertEqual(result.content_type, PROBLEM_CONTENT_TYPE)
        return result

    def test_absent_authorization_is_denied(self) -> None:
        payload = self._forced_payload()
        result = negotiate(_request(client="1.0.0", payload=payload, signature=""), _verifier())
        self._assert_denied(result)

    def test_tampered_payload_under_a_valid_signature_is_denied(self) -> None:
        """A signature genuinely issued for one decision does not authorize a
        different one: verification is over the exact received bytes."""
        signed_payload = _decision_payload(minimum="2.0.0", forced=False, reason=None)
        swapped_payload = self._forced_payload()
        result = negotiate(
            _request(
                client="1.0.0",
                payload=swapped_payload,
                signature=_sign(signed_payload),
            ),
            _verifier(),
        )
        self._assert_denied(result)

    def test_tampered_signature_is_denied(self) -> None:
        payload = self._forced_payload()
        valid = _sign(payload)
        flipped = ("0" if valid[0] != "0" else "1") + valid[1:]
        result = negotiate(
            _request(client="1.0.0", payload=payload, signature=flipped), _verifier()
        )
        self._assert_denied(result)

    def test_a_signature_from_a_different_key_is_denied(self) -> None:
        payload = self._forced_payload()
        result = negotiate(
            _request(
                client="1.0.0",
                payload=payload,
                signature=_sign(payload, key=SYNTHETIC_OTHER_KEY),
            ),
            _verifier(),
        )
        self._assert_denied(result)

    def test_a_non_ascii_signature_is_denied_rather_than_raising(self) -> None:
        payload = self._forced_payload()
        result = negotiate(
            _request(client="1.0.0", payload=payload, signature="ü" * 64), _verifier()
        )
        self._assert_denied(result)

    def test_absent_and_tampered_authorization_are_indistinguishable(self) -> None:
        """No oracle for *why* authorization failed."""
        payload = self._forced_payload()
        absent = negotiate(_request(client="1.0.0", payload=payload, signature=""), _verifier())
        tampered = negotiate(
            _request(
                client="1.0.0",
                payload=payload,
                signature=_sign(payload, key=SYNTHETIC_OTHER_KEY),
            ),
            _verifier(),
        )
        assert isinstance(absent, ProblemDetails)
        assert isinstance(tampered, ProblemDetails)
        self.assertEqual(absent.to_body(), tampered.to_body())

    def test_unauthorized_denial_precedes_any_payload_validation(self) -> None:
        """An unauthorized caller gets a uniform 401, not input feedback about
        a payload the server never trusted."""
        result = negotiate(
            _request(client="not-a-version", payload=b"{ not json at all", signature=""),
            _verifier(),
        )
        self._assert_denied(result)

    def test_a_verifier_refuses_an_empty_key(self) -> None:
        with self.assertRaises(ValueError):
            HmacSha256Verifier(key=b"")


class ForcedUpdateReservationTest(unittest.TestCase):
    """TSD §24.3: forced update is reserved for security/critical
    incompatibility. An authorized decision is still rejected if it asserts a
    forced update for anything else."""

    def _assert_not_reserved(self, result: object) -> None:
        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.status, 422)
        self.assertEqual(
            result.problem_type, f"{PROBLEM_TYPE_BASE}forced-update-reason-not-reserved"
        )

    def test_a_forced_update_for_an_unreserved_reason_is_rejected(self) -> None:
        payload = _decision_payload(minimum="2.0.0", forced=True, reason="marketing_campaign")
        result = negotiate(_request(client="1.0.0", payload=payload), _verifier())
        self._assert_not_reserved(result)

    def test_a_forced_update_with_no_reason_is_rejected(self) -> None:
        payload = _decision_payload(minimum="2.0.0", forced=True, reason=None)
        result = negotiate(_request(client="1.0.0", payload=payload), _verifier())
        self._assert_not_reserved(result)

    def test_rejection_is_not_downgraded_to_an_update_prompt(self) -> None:
        """Fail closed: an unreserved forced update is refused outright, not
        quietly relaxed into the optional-update disposition."""
        payload = _decision_payload(minimum="2.0.0", forced=True, reason="convenience")
        result = negotiate(_request(client="1.0.0", payload=payload), _verifier())
        self.assertNotIsInstance(result, NegotiationOutcome)

    def test_the_reserved_set_is_exactly_two(self) -> None:
        self.assertEqual(
            {reason.value for reason in ForcedUpdateReason},
            {"security", "critical_incompatibility"},
        )


class ClosedDecisionContractTest(unittest.TestCase):
    """The signed payload's field set is closed, so remote-config-flavoured
    data cannot ride along inside a decision (TSD §24.3)."""

    def test_an_unrecognized_field_is_rejected_even_when_correctly_signed(self) -> None:
        payload = _decision_payload(extra={"rollout_percentage": 100})
        result = negotiate(_request(client="1.0.0", payload=payload), _verifier())

        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.status, 422)
        self.assertEqual(result.problem_type, f"{PROBLEM_TYPE_BASE}malformed-release-decision")

    def test_a_missing_field_is_rejected(self) -> None:
        payload = json.dumps(
            {"decision_id": SYNTHETIC_DECISION_ID, "minimum_supported_version": "2.0.0"}
        ).encode("utf-8")
        with self.assertRaises(MalformedReleaseDecision):
            parse_release_decision(payload)

    def test_a_duplicated_field_is_rejected(self) -> None:
        payload = (
            b'{"decision_id": "A", "minimum_supported_version": "2.0.0", '
            b'"forced_update_required": false, "forced_update_reason": null, '
            b'"forced_update_required": true}'
        )
        with self.assertRaises(MalformedReleaseDecision):
            parse_release_decision(payload)

    def test_an_integer_is_not_accepted_for_a_boolean_field(self) -> None:
        payload = (
            b'{"decision_id": "A", "minimum_supported_version": "2.0.0", '
            b'"forced_update_required": 1, "forced_update_reason": "security"}'
        )
        with self.assertRaises(MalformedReleaseDecision):
            parse_release_decision(payload)

    def test_a_reason_without_a_forced_update_is_rejected_as_contradictory(self) -> None:
        payload = _decision_payload(forced=False, reason="security")
        with self.assertRaises(MalformedReleaseDecision):
            parse_release_decision(payload)

    def test_an_oversized_payload_is_rejected(self) -> None:
        payload = _decision_payload(decision_id="A" * 5000)
        with self.assertRaises(MalformedReleaseDecision):
            parse_release_decision(payload)

    def test_a_non_object_payload_is_rejected(self) -> None:
        with self.assertRaises(MalformedReleaseDecision):
            parse_release_decision(b'["not", "an", "object"]')

    def test_a_malformed_minimum_version_is_rejected(self) -> None:
        payload = _decision_payload(minimum="2.0")
        with self.assertRaises(MalformedReleaseDecision):
            parse_release_decision(payload)

    def test_the_two_rejection_classes_are_distinguishable(self) -> None:
        with self.assertRaises(ForcedUpdateReasonNotReserved):
            parse_release_decision(_decision_payload(forced=True, reason="not_reserved"))


class VersionedSurfaceTest(unittest.TestCase):
    """ADR-004 (`ADR_CONFORMANCE.md`): versioned surface, RFC 7807 errors."""

    def test_an_unsupported_api_version_is_rejected_before_authorization(self) -> None:
        payload = _decision_payload()
        request = _request(client="2.0.0", payload=payload, api_version="v99")
        result = negotiate(request, _NeverCalledVerifier())

        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.status, 400)
        self.assertEqual(result.problem_type, f"{PROBLEM_TYPE_BASE}unsupported-api-version")

    def test_a_problem_body_carries_the_rfc7807_members(self) -> None:
        payload = _decision_payload()
        result = negotiate(_request(client="2.0.0", payload=payload, signature=""), _verifier())

        assert isinstance(result, ProblemDetails)
        body = result.to_body()
        self.assertEqual(set(body), {"type", "title", "status", "detail"})
        assert isinstance(body["type"], str)
        self.assertTrue(body["type"].startswith(PROBLEM_TYPE_BASE))
        self.assertEqual(result.content_type, "application/problem+json")

    def test_a_malformed_client_version_is_rejected(self) -> None:
        payload = _decision_payload()
        result = negotiate(_request(client="2.0", payload=payload), _verifier())

        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.status, 400)
        self.assertEqual(result.problem_type, f"{PROBLEM_TYPE_BASE}malformed-client-version")


class AppVersionTest(unittest.TestCase):
    def test_ordering_is_by_major_then_minor_then_patch(self) -> None:
        self.assertLess(AppVersion.parse("1.9.9"), AppVersion.parse("2.0.0"))
        self.assertLess(AppVersion.parse("2.0.9"), AppVersion.parse("2.1.0"))
        self.assertGreater(AppVersion.parse("2.0.1"), AppVersion.parse("2.0.0"))
        self.assertEqual(AppVersion.parse("2.0.0"), AppVersion(2, 0, 0))

    def test_str_round_trips(self) -> None:
        self.assertEqual(str(AppVersion.parse("10.2.33")), "10.2.33")

    def test_rejects_non_canonical_and_malformed_input(self) -> None:
        for raw in (
            "2.0",
            "2.0.0.0",
            "2.0.01",
            "v2.0.0",
            "2.0.0-beta",
            " 2.0.0",
            "-2.0.0",
            "2.0.x",
            "",
            "1" * 20 + ".0.0",
            "٢.٠.٠",  # non-ASCII digits, which `str.isdigit()` alone accepts
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                AppVersion.parse(raw)


if __name__ == "__main__":
    unittest.main()

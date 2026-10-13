"""Backend version-negotiation contract — GOV-01-R07, `SCN-MOD001-115`.

The *enforcement* half of `mobile/RELEASE_POLICY.md`, per
`IMPLEMENTATION.md` §12's own split: that file is the policy document,
this file is "the real backend-side enforcement code TSD §24.3 actually
assigns to the backend, not to the mobile app: minimum-supported-version
check, optional-vs-forced-update decision, and the kill-switch's own
authorization check (only an authorized release decision — a signed
release-evidence record — may activate it)."

Governing source, TSD §24.3 (`TSD_MIRROR.md` lines 11670-11700), verbatim:
"Backend APIs preserve compatibility for minimum supported app versions;
server can expose capability/version negotiation"; "Remote config
controls rollout but cannot repair an incompatible API contract";
"Minimum supported version, optional/forced update and kill-switch policy
are explicit; forced update is reserved for security/critical
incompatibility." Plus `REQUIREMENTS.md` GOV-01-R07's security-
implications text: forced-update/kill-switch "must not be triggerable
without the equivalent of an authorized release decision."

What this module is, exactly:

- A **pure decision function** (`negotiate`). It is not a FastAPI route,
  binds no network endpoint, opens no socket, reads no environment
  variable, no file and no database, and emits no log line. The HTTP
  binding for this contract is not created by this slice.
- **Versioned** (`API_VERSION`/`SUPPORTED_API_VERSIONS`) and failing with
  RFC 7807 `application/problem+json` bodies, per
  `ADR_CONFORMANCE.md`'s ADR-004 obligation on this exact file. That
  ADR's conformance state stays PLANNED until `SCN-MOD001-119`(a)
  executes; this module satisfies the obligation at the contract level,
  which is not the same as that scenario having run.
- **Verify-only interface.** It exposes no signing method and verifies
  release-decision authorization. HMAC is symmetric: a process holding
  its verification key could also compute signatures. This synthetic
  contract does not establish production signer/verifier separation.
  The verifying key is injected by the caller
  (`ReleaseAuthorizationVerifier`); this module has no default key and
  no key-loading path of any kind, per
  `.claude/rules/infra/secrets.md` control 1.
- **Fail-closed.** Absent or non-matching authorization is *denied*, never
  downgraded to an optional-update prompt and never defaulted to allow.
  Authorization is verified over the exact received bytes *before* those
  bytes are parsed, so no untrusted field is ever trusted.
- **Structurally immune to remote config.** There is no rollout/
  remote-config parameter, and the signed payload's field set is closed —
  an unrecognized field is rejected, not ignored. This is TSD §24.3's
  "remote config... cannot repair an incompatible API contract" expressed
  as an absent input rather than a check that could be forgotten.

Synthetic only: no real key, no real release decision, no real client
version, no store action, no Production activation.
"""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Final, Protocol

# --- Versioned surface (ADR-004: "Versioned REST command/query APIs") ------

API_VERSION: Final = "v1"
SUPPORTED_API_VERSIONS: Final[frozenset[str]] = frozenset({API_VERSION})

# --- RFC 7807 problem surface (ADR-004: "RFC 7807 errors") -----------------

PROBLEM_CONTENT_TYPE: Final = "application/problem+json"

# RFC 2606 `.invalid` TLD: a deliberately non-resolvable base, so no real
# Veyro domain is committed to by a synthetic slice.
PROBLEM_TYPE_BASE: Final = "https://veyro.invalid/problems/version-negotiation/"

# Bounds. Both are fail-closed input guards, not tuning knobs.
MAX_DECISION_PAYLOAD_BYTES: Final = 4096
MAX_VERSION_PART_DIGITS: Final = 9
MAX_DECISION_ID_LENGTH: Final = 128


class Disposition(Enum):
    """The three — and only three — outcomes `SCN-MOD001-115` enumerates."""

    ALLOWED = "allowed"
    ALLOWED_WITH_UPDATE_PROMPT = "allowed_with_update_prompt"
    BLOCKED_FORCED_UPDATE = "blocked_forced_update"


class ForcedUpdateReason(Enum):
    """TSD §24.3: "forced update is reserved for security/critical
    incompatibility." This enum *is* that reservation — a closed set of
    two, not an illustrative list. A decision naming anything else cannot
    authorize a forced update.
    """

    SECURITY = "security"
    CRITICAL_INCOMPATIBILITY = "critical_incompatibility"


class MalformedReleaseDecision(ValueError):
    """An authorized payload whose shape/types are not the closed contract."""


class ForcedUpdateReasonNotReserved(ValueError):
    """An authorized decision asserting a forced update for an unreserved reason.

    Distinct from `MalformedReleaseDecision` because it is the specific
    TSD §24.3 reservation being violated, and the caller maps it to its own
    problem type rather than a generic malformed-body response.
    """


@dataclass(frozen=True, order=True)
class AppVersion:
    """A comparable `MAJOR.MINOR.PATCH` client/minimum app version.

    `order=True` on the declared field order gives exactly the precedence
    comparison the minimum-supported-version check needs.
    """

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str) -> AppVersion:
        """Parse a strict, canonical `MAJOR.MINOR.PATCH` string.

        Strict on purpose: no pre-release/build suffix, no leading zeros, no
        surrounding whitespace, no sign, and a digit-count bound so an
        unbounded-integer input cannot be handed to `int()`. A version that
        does not parse is rejected, never coerced to a default.
        """
        parts = raw.split(".")
        if len(parts) != 3:
            raise ValueError("expected exactly three dot-separated version parts")
        numbers = []
        for part in parts:
            if not part.isascii() or not part.isdigit():
                raise ValueError("every version part must be ASCII digits")
            if len(part) > MAX_VERSION_PART_DIGITS:
                raise ValueError("version part exceeds the permitted digit count")
            if part != str(int(part)):
                raise ValueError("version parts must be canonical (no leading zeros)")
            numbers.append(int(part))
        return cls(numbers[0], numbers[1], numbers[2])

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ProblemDetails:
    """An RFC 7807 problem detail. Rendered as `application/problem+json`.

    `detail` is always a fixed, authored string — never untrusted input
    echoed back, and never a secret, a key, or a signature value.
    """

    problem_type: str
    title: str
    status: int
    detail: str

    @property
    def content_type(self) -> str:
        return PROBLEM_CONTENT_TYPE

    def to_body(self) -> dict[str, object]:
        """The RFC 7807 member names, which differ from the field names here
        (`type` is a Python builtin, so the field is `problem_type`)."""
        return {
            "type": self.problem_type,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class _ProblemKind:
    slug: str
    title: str
    status: int

    def detailed(self, detail: str) -> ProblemDetails:
        return ProblemDetails(
            problem_type=f"{PROBLEM_TYPE_BASE}{self.slug}",
            title=self.title,
            status=self.status,
            detail=detail,
        )


UNSUPPORTED_API_VERSION: Final = _ProblemKind(
    slug="unsupported-api-version",
    title="Unsupported negotiation API version",
    status=400,
)
RELEASE_DECISION_UNAUTHORIZED: Final = _ProblemKind(
    slug="release-decision-unauthorized",
    title="Release decision is not authorized",
    status=401,
)
MALFORMED_RELEASE_DECISION: Final = _ProblemKind(
    slug="malformed-release-decision",
    title="Malformed release decision",
    status=422,
)
FORCED_UPDATE_REASON_NOT_RESERVED: Final = _ProblemKind(
    slug="forced-update-reason-not-reserved",
    title="Forced update is reserved for security/critical incompatibility",
    status=422,
)
MALFORMED_CLIENT_VERSION: Final = _ProblemKind(
    slug="malformed-client-version",
    title="Malformed client app version",
    status=400,
)

# One identical body for both absent and non-matching authorization. Keeping
# them indistinguishable denies a caller an oracle for *why* authorization
# failed; the two cases are distinguished by the request made, not by the
# response.
_UNAUTHORIZED_DETAIL: Final = (
    "The release decision was not accompanied by verifiable authorization. "
    "A forced update or kill switch can only be activated by an authorized "
    "release decision."
)


# --- Authorization ---------------------------------------------------------


class ReleaseAuthorizationVerifier(Protocol):
    """Verifies that a release-decision payload carries authorization.

    Narrow by design: one method, over raw bytes, returning a bool. The
    verifier — and therefore the key — is injected by the caller, so this
    module never holds, loads, or defaults a key.
    """

    def verify(self, payload: bytes, signature: str) -> bool: ...


@dataclass(frozen=True)
class HmacSha256Verifier:
    """HMAC-SHA256 verifier over the exact received payload bytes.

    Verify-only: there is deliberately no `sign` method here. Signing
    belongs to whichever authority issues release decisions, and that
    authority's custody is an open, DC-16 owner-reserved question per
    `mobile/RELEASE_POLICY.md` §4 — so MOD-001 proves this with a
    synthetic key injected by a test, never a real credential.
    """

    key: bytes

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("a verifying key is required; refusing to verify with an empty key")

    def verify(self, payload: bytes, signature: str) -> bool:
        if not signature or not signature.isascii():
            # `compare_digest` raises on non-ASCII str input; an absent or
            # non-ASCII signature is simply unauthorized.
            return False
        expected = hmac.new(self.key, payload, sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


# --- Request / decision / result shapes ------------------------------------


@dataclass(frozen=True)
class SignedReleaseDecision:
    """An *untrusted* release decision as received, plus its authorization.

    `payload` is kept as the exact received bytes so authorization is
    verified over what actually arrived — never over a re-serialization of
    a parsed object, which is where canonicalization mismatches hide. An
    absent authorization is the empty signature.
    """

    payload: bytes
    signature: str


@dataclass(frozen=True)
class ReleaseDecision:
    """A release decision *after* authorization and shape validation."""

    decision_id: str
    minimum_supported_version: AppVersion
    forced_update_required: bool
    forced_update_reason: ForcedUpdateReason | None


@dataclass(frozen=True)
class NegotiationRequest:
    """Note what is absent: no rollout percentage, no remote-config handle,
    no feature flag. Remote config cannot reach this decision because there
    is nowhere for it to enter (TSD §24.3)."""

    api_version: str
    client_app_version: str
    signed_decision: SignedReleaseDecision


@dataclass(frozen=True)
class NegotiationOutcome:
    """A successful negotiation. `reason` is populated only for a block."""

    api_version: str
    disposition: Disposition
    client_app_version: AppVersion
    minimum_supported_version: AppVersion
    decision_id: str
    forced_update_reason: ForcedUpdateReason | None = None

    @property
    def blocked(self) -> bool:
        return self.disposition is Disposition.BLOCKED_FORCED_UPDATE


NegotiationResult = NegotiationOutcome | ProblemDetails

_DECISION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "decision_id",
        "minimum_supported_version",
        "forced_update_required",
        "forced_update_reason",
    }
)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """JSON's last-key-wins default would let a duplicated field shadow the
    one that was reviewed. Reject instead."""
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise MalformedReleaseDecision("duplicate field in release decision")
        seen[key] = value
    return seen


def parse_release_decision(payload: bytes) -> ReleaseDecision:
    """Validate an **already-authorized** payload into a `ReleaseDecision`.

    Closed field set: a missing *or* unrecognized field is rejected. That
    closure is what stops a rollout-flavoured field from riding along
    inside a decision (TSD §24.3), and it is the same intent as
    `.claude/rules/backend/api.md` control 3's `extra="forbid"` for request
    schemas — expressed without Pydantic, which this backend does not yet
    depend on.

    Raises `MalformedReleaseDecision` or `ForcedUpdateReasonNotReserved`.
    """
    if len(payload) > MAX_DECISION_PAYLOAD_BYTES:
        raise MalformedReleaseDecision("release decision payload exceeds the permitted size")
    try:
        parsed = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MalformedReleaseDecision("release decision is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise MalformedReleaseDecision("release decision must be a JSON object")

    present = frozenset(parsed)
    if present != _DECISION_FIELDS:
        missing = sorted(_DECISION_FIELDS - present)
        unrecognized = sorted(present - _DECISION_FIELDS)
        # Only field *names*, and only ones drawn from the closed contract or
        # reported as a count — never a field value.
        raise MalformedReleaseDecision(
            f"release decision field set is not the closed contract "
            f"(missing={missing}, unrecognized={len(unrecognized)})"
        )

    decision_id = parsed["decision_id"]
    if not isinstance(decision_id, str) or not decision_id:
        raise MalformedReleaseDecision("decision_id must be a non-empty string")
    if len(decision_id) > MAX_DECISION_ID_LENGTH:
        raise MalformedReleaseDecision("decision_id exceeds the permitted length")

    raw_minimum = parsed["minimum_supported_version"]
    if not isinstance(raw_minimum, str):
        raise MalformedReleaseDecision("minimum_supported_version must be a string")
    try:
        minimum = AppVersion.parse(raw_minimum)
    except ValueError as exc:
        raise MalformedReleaseDecision("minimum_supported_version is not a valid version") from exc

    forced = parsed["forced_update_required"]
    # `isinstance(True, int)` is True, so an exact type check is required to
    # keep `1` from being read as `true`.
    if forced is not True and forced is not False:
        raise MalformedReleaseDecision("forced_update_required must be a JSON boolean")

    raw_reason = parsed["forced_update_reason"]
    if forced:
        if not isinstance(raw_reason, str):
            raise ForcedUpdateReasonNotReserved(
                "a forced update requires a reserved forced_update_reason"
            )
        try:
            reason: ForcedUpdateReason | None = ForcedUpdateReason(raw_reason)
        except ValueError as exc:
            raise ForcedUpdateReasonNotReserved(
                "forced_update_reason is outside the reserved security/critical-incompatibility set"
            ) from exc
    else:
        if raw_reason is not None:
            raise MalformedReleaseDecision(
                "forced_update_reason must be null when no forced update is required"
            )
        reason = None

    return ReleaseDecision(
        decision_id=decision_id,
        minimum_supported_version=minimum,
        forced_update_required=forced,
        forced_update_reason=reason,
    )


def negotiate(
    request: NegotiationRequest,
    verifier: ReleaseAuthorizationVerifier,
) -> NegotiationResult:
    """Negotiate one client version against an authorized release decision.

    Returns a `NegotiationOutcome` on success or `ProblemDetails` (RFC 7807)
    on failure. Step order is itself a control:

    1. API version — the versioned surface rejects what it does not speak.
    2. **Authorization, over the exact received bytes.** Nothing below this
       line runs for an unauthorized caller, so neither the decision
       payload nor the client version produces any pre-authorization
       validation feedback.
    3. Decision shape, against the closed contract.
    4. Client version.
    5. The disposition.
    """
    if request.api_version not in SUPPORTED_API_VERSIONS:
        return UNSUPPORTED_API_VERSION.detailed(
            f"This endpoint speaks only API version(s): "
            f"{', '.join(sorted(SUPPORTED_API_VERSIONS))}."
        )

    signed = request.signed_decision
    if not verifier.verify(signed.payload, signed.signature):
        return RELEASE_DECISION_UNAUTHORIZED.detailed(_UNAUTHORIZED_DETAIL)

    try:
        decision = parse_release_decision(signed.payload)
    except ForcedUpdateReasonNotReserved as exc:
        return FORCED_UPDATE_REASON_NOT_RESERVED.detailed(str(exc))
    except MalformedReleaseDecision as exc:
        return MALFORMED_RELEASE_DECISION.detailed(str(exc))

    try:
        client_version = AppVersion.parse(request.client_app_version)
    except ValueError:
        return MALFORMED_CLIENT_VERSION.detailed(
            "client_app_version must be a canonical MAJOR.MINOR.PATCH version."
        )

    if client_version >= decision.minimum_supported_version:
        # At or above the minimum: normal operation, even while a forced
        # update is authorized. A release decision's blast radius is the
        # below-minimum population only (`mobile/RELEASE_POLICY.md` §2).
        disposition = Disposition.ALLOWED
        reason = None
    elif decision.forced_update_required:
        disposition = Disposition.BLOCKED_FORCED_UPDATE
        reason = decision.forced_update_reason
    else:
        # Below the minimum with no authorized forced update: operates, with
        # a prompt. The minimum is a prompt threshold, never a block
        # threshold on its own.
        disposition = Disposition.ALLOWED_WITH_UPDATE_PROMPT
        reason = None

    return NegotiationOutcome(
        api_version=request.api_version,
        disposition=disposition,
        client_app_version=client_version,
        minimum_supported_version=decision.minimum_supported_version,
        decision_id=decision.decision_id,
        forced_update_reason=reason,
    )

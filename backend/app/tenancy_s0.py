"""MOD-004 S0: pure ``ProvisionTenant`` envelope shape validation.

Scope: S0 input-shape slice only. Success means the envelope is *shape-valid*; it is
never an authenticated principal, an authorization, a tenant selection or creation,
idempotency deduplication, tenant context or tenant-isolation evidence. This module
performs no I/O, keeps no state, logs nothing and echoes no raw input.

Public API
    ``validate_provision_tenant(envelope)`` -> ``ProvisionTenantEnvelope``
    ``EnvelopeError`` (a ``ValueError``) with a fixed generic message and a fixed ``code``.

Input: a Python mapping only (JSON text is not accepted; ``str``/``bytes`` are rejected).
Mapping policy: only an exact built-in ``dict`` is accepted. ``dict`` subclasses,
``MappingProxyType`` and custom ``Mapping`` implementations are REJECTED without calling
any of their methods, so they cannot influence validation. Nested values are never
traversed: every value must be a flat scalar of an exact expected type, so nesting and
cycles are rejected by type and cannot cause recursion.

Flat schema (all keys are exact ``str``; any other key is rejected):
    external_key      required str; opaque tenant key, never interpreted as a path or
                      identifier for I/O. Policy: 1..EXTERNAL_KEY_MAX_LENGTH ASCII
                      characters matching ``[A-Za-z0-9][A-Za-z0-9._:-]*``. Everything
                      else (empty, whitespace, non-ASCII/Unicode, control, NUL, newline,
                      bidi and surrogate code points) is rejected; no Unicode
                      normalization is attempted.
    actor_id          required str; CLAIMED actor UUID (caller claim, not authenticated).
    correlation_id    required str; CLAIMED correlation UUID.
    idempotency_key   required str; idempotency UUID shape metadata, retained only.
    expected_version  OPTIONAL int. Absent -> ``None`` ("no version"). Present ``None``
                      is REJECTED (present-null differs from absent). Accepted range is
                      0..EXPECTED_VERSION_MAX inclusive; bool, float, str, containers,
                      negatives and larger ints are rejected.

UUID policy (for the three claimed UUIDs): exact ``str`` in hyphenated 8-4-4-4-12 hex
form; upper- or lower-case hex is accepted and normalized to lower case. Braces, URN
prefix, hyphenless form, surrounding whitespace and ``UUID`` instances are rejected. The
nil UUID and any non-RFC-4122 variant or version outside 1..8 are rejected.

Bounds: at most MAX_FIELDS top-level entries and MAX_FIELD_NAME_LENGTH per key name,
checked before the content is looked at.

Open discrepancy (kept explicit, NOT resolved here): TSD paragraph 1237 and ADR-0002
D6.3 disagree on whether an expected version applies to initial provisioning. S0 invents
no requirement and treats ``expected_version`` as optional metadata.

Failure: ``EnvelopeError`` is raised from a bare ``raise`` site (no chained cause or
context) with a generic message that contains only constants from this module. Nothing
is returned on failure, so there is never a partially built object.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EXTERNAL_KEY_MAX_LENGTH = 128
EXPECTED_VERSION_MAX = 2**31 - 1
MAX_FIELDS = 16
MAX_FIELD_NAME_LENGTH = 32

_REQUIRED = ("external_key", "actor_id", "correlation_id", "idempotency_key")
_ALLOWED = frozenset(_REQUIRED) | {"expected_version"}
_EXTERNAL_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*", re.ASCII)
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
    re.ASCII,
)
_UUID_LENGTH = 36


class EnvelopeError(ValueError):
    """Generic rejection of a malformed envelope; never carries raw input."""

    def __init__(self, code: str) -> None:
        super().__init__("invalid ProvisionTenant envelope")
        self.code = code


@dataclass(frozen=True, slots=True)
class ProvisionTenantEnvelope:
    """Immutable, shape-valid result. All UUIDs are CLAIMS in canonical lower case."""

    external_key: str
    actor_id: str
    correlation_id: str
    idempotency_key: str
    expected_version: int | None


def _external_key_ok(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= EXTERNAL_KEY_MAX_LENGTH
        and _EXTERNAL_KEY.fullmatch(value) is not None
    )


def _uuid_ok(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _UUID_LENGTH
        and _UUID.fullmatch(value) is not None
    )


def _version_ok(value: object) -> bool:
    return type(value) is int and 0 <= value <= EXPECTED_VERSION_MAX


def validate_provision_tenant(envelope: object) -> ProvisionTenantEnvelope:
    """Validate the shape of a ProvisionTenant envelope; shape-valid only, nothing more."""
    if type(envelope) is not dict:
        raise EnvelopeError("not_mapping")
    if len(envelope) > MAX_FIELDS:
        raise EnvelopeError("too_many_fields")
    for key in envelope:
        if type(key) is not str:
            raise EnvelopeError("bad_key_type")
        if len(key) > MAX_FIELD_NAME_LENGTH or key not in _ALLOWED:
            raise EnvelopeError("unexpected_field")
    for name in _REQUIRED:
        if name not in envelope:
            raise EnvelopeError("missing_field")

    if not _external_key_ok(envelope["external_key"]):
        raise EnvelopeError("bad_external_key")
    if not _uuid_ok(envelope["actor_id"]):
        raise EnvelopeError("bad_actor_id")
    if not _uuid_ok(envelope["correlation_id"]):
        raise EnvelopeError("bad_correlation_id")
    if not _uuid_ok(envelope["idempotency_key"]):
        raise EnvelopeError("bad_idempotency_key")

    version = None
    if "expected_version" in envelope:
        version = envelope["expected_version"]
        if not _version_ok(version):
            raise EnvelopeError("bad_expected_version")

    return ProvisionTenantEnvelope(
        external_key=envelope["external_key"],
        actor_id=envelope["actor_id"].lower(),
        correlation_id=envelope["correlation_id"].lower(),
        idempotency_key=envelope["idempotency_key"].lower(),
        expected_version=version,
    )

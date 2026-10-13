"""
Offline-mode signed-snapshot/TTL fixture pattern (MOD-001, GOV-01-R03;
`SCN-MOD001-032`).

`REQUIREMENTS.md` GOV-01-R03 lists among MOD-001's implementation obligations
"an offline-mode fixture pattern for later edge/mobile consumers", with
offline-testing patterns scoped as "relevant to later edge/mobile/POS
modules". `SCN-MOD001-032` names the thing to exercise: "the offline-mode
fixture-pattern harness itself (the thing later edge/mobile/POS modules will
build real offline scenarios on top of) against a synthetic
signed-snapshot/TTL fixture", expecting that it "correctly distinguishes a
valid unexpired snapshot from an expired one".

## What this is, and deliberately is not

It is the *fixture pattern* only: a pure, offline, stdlib-only builder and
validator for a synthetic signed snapshot envelope, used by tests. It is NOT
a production offline/degraded-mode mechanism, NOT a session or token system,
NOT a crypto library, and NOT a key-management or credential facility. The
signature exists so a test can prove the validator distinguishes an intact
snapshot from a tampered or wrongly-keyed one — nothing here is a security
control for real data.

Scope kept deliberately narrow: one algorithm (HMAC-SHA256), one envelope
shape, no algorithm/option negotiation, no plugin or policy extension point,
no CLI. Adding a second algorithm or envelope variant is a source change
here, not a configuration surface. Real offline-flow *content* belongs to the
later edge/mobile/POS module that owns that flow — the same split
`IMPLEMENTATION.md` applies to the abuse-negative fixture harness.

## Envelope shape

    {
      "fixture_kind": "synthetic-offline-snapshot",  # exact label, required
      "synthetic": true,                             # must be literally true
      "snapshot_id": "...",
      "issued_at": 1700000000,                       # integer, required
      "ttl_seconds": 300,                            # positive integer
      "payload": {...},                              # synthetic, never echoed
      "signature": "<hex HMAC-SHA256>"
    }

The signature covers the deterministic canonical JSON (sorted keys, compact
separators, no NaN/Infinity) of the whole envelope minus `signature`, so
tampering with any metadata field — not just the payload — breaks it.

## Validity window and fail-closed behavior

A snapshot is valid at an explicitly injected integer `now` when
`issued_at <= now < issued_at + ttl_seconds`. Expiry is the inclusive
boundary `now >= issued_at + ttl_seconds`, and `now < issued_at` is a
future-issued snapshot — both DENY.

Everything the validator cannot fully understand is DENIED, never accepted:
a non-mapping envelope, a missing or extra field, a missing/incorrect
synthetic marker or fixture kind, non-integer `issued_at`, non-positive or
non-integer `ttl_seconds`, a non-mapping or non-serializable payload, a
malformed or non-ASCII signature, a wrong key, any tampering, and a
non-integer `now` or an empty key passed by the caller. Structural checks run
before the signature check, which runs before the time checks — so a tampered
snapshot is never reported as merely "expired".

Fail-closed means DENY, never an exception: an envelope the validator cannot
understand still yields a `SnapshotVerdict`, so a later edge/mobile/POS test
built on this pattern can never mistake a crash for a verdict.

Verdict details are value-free by construction: they name known fields, codes
and integer time arithmetic only. The signing key, the payload's values and
any unexpected key (which is counted, never named) are never placed in a
verdict, so a DENY cannot republish fixture content or key material into a
test log. This module never reads or writes a file.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SNAPSHOT_FIXTURE_KIND = "synthetic-offline-snapshot"

# An explicitly-fake, clearly-labeled test-only key, per
# `.claude/rules/infra/secrets.md` control 1 — never a real credential and
# deliberately not shaped like one. Callers always pass a key explicitly;
# this is just the canonical one for this fixture pattern's own tests.
TEST_ONLY_SIGNING_KEY = b"EXAMPLE_NOT_A_REAL_KEY-offline-snapshot-fixture"

SIGNATURE_FIELD = "signature"
SNAPSHOT_FIELDS = (
    "fixture_kind",
    "synthetic",
    "snapshot_id",
    "issued_at",
    "ttl_seconds",
    "payload",
    SIGNATURE_FIELD,
)

VERDICT_VALID = "VALID"
VERDICT_DENY = "DENY"

UNKNOWN_SNAPSHOT_ID = "<unknown>"


@dataclass(frozen=True)
class SnapshotVerdict:
    """One validation outcome. `detail` is value-free by construction."""

    verdict: str
    code: str
    detail: str
    snapshot_id: str = UNKNOWN_SNAPSHOT_ID

    @property
    def is_valid(self) -> bool:
        return self.verdict == VERDICT_VALID


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators, no NaN/Infinity."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _is_int(value: Any) -> bool:
    """True for a real integer. `bool` is excluded — it is not a timestamp."""
    return isinstance(value, int) and not isinstance(value, bool)


def _deny(code: str, detail: str, snapshot_id: str = UNKNOWN_SNAPSHOT_ID) -> SnapshotVerdict:
    return SnapshotVerdict(VERDICT_DENY, code, detail, snapshot_id)


def _signature_over(unsigned: Mapping[str, Any], key: bytes) -> str:
    """HMAC-SHA256 over the canonical JSON of the envelope minus its signature."""
    material = canonical_json({k: v for k, v in unsigned.items() if k != SIGNATURE_FIELD})
    return hmac.new(key, material.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_envelope(envelope: Mapping[str, Any], key: bytes) -> dict[str, Any]:
    """Return a copy of `envelope` carrying a signature over its other fields.

    Deliberately signs whatever it is given, so a test can build a
    correctly-signed but structurally-malformed fixture and prove the
    validator rejects it on its own merits rather than on the signature.
    Raises on a caller-side contract breach (bad key, unserializable
    envelope) rather than minting an unusable fixture.
    """
    if not isinstance(key, bytes) or not key:
        raise ValueError("signing key must be non-empty bytes")
    signed = dict(envelope)
    signed[SIGNATURE_FIELD] = _signature_over(signed, key)
    return signed


def make_snapshot(
    *,
    snapshot_id: str,
    payload: Mapping[str, Any],
    issued_at: int,
    ttl_seconds: int,
    key: bytes,
) -> dict[str, Any]:
    """Build and sign a well-formed synthetic snapshot envelope."""
    if not _is_int(issued_at):
        raise ValueError("issued_at must be an integer")
    if not _is_int(ttl_seconds) or ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be a positive integer")
    return sign_envelope(
        {
            "fixture_kind": SNAPSHOT_FIXTURE_KIND,
            "synthetic": True,
            "snapshot_id": snapshot_id,
            "issued_at": issued_at,
            "ttl_seconds": ttl_seconds,
            "payload": dict(payload),
        },
        key,
    )


def _check_structure(envelope: Mapping[str, Any]) -> SnapshotVerdict | None:
    """Structural and synthetic-marker checks. Returns a DENY, or None if sound."""
    if set(envelope) != set(SNAPSHOT_FIELDS):
        missing = sorted(set(SNAPSHOT_FIELDS) - set(envelope))
        # Unexpected keys are caller-supplied: they are counted, never sorted
        # or named. Sorting them would raise on a heterogeneous key set (e.g.
        # a str and an int key together), and naming them could republish
        # fixture content through the key itself.
        unexpected = sum(1 for key in envelope if key not in SNAPSHOT_FIELDS)
        return _deny("FIELD_SET_MISMATCH", f"missing={missing} unexpected_count={unexpected}")
    if envelope["fixture_kind"] != SNAPSHOT_FIXTURE_KIND:
        return _deny("NOT_A_SYNTHETIC_SNAPSHOT", f"fixture_kind is not {SNAPSHOT_FIXTURE_KIND!r}")
    if envelope["synthetic"] is not True:
        return _deny("SYNTHETIC_MARKER_MISSING", "synthetic must be literally true")
    if not isinstance(envelope["snapshot_id"], str) or not envelope["snapshot_id"]:
        return _deny("SNAPSHOT_ID_MALFORMED", "snapshot_id must be a non-empty string")
    if not _is_int(envelope["issued_at"]):
        return _deny("ISSUED_AT_NOT_INTEGER", "issued_at must be an integer")
    if not _is_int(envelope["ttl_seconds"]) or envelope["ttl_seconds"] <= 0:
        return _deny("TTL_NOT_POSITIVE_INTEGER", "ttl_seconds must be a positive integer")
    if not isinstance(envelope["payload"], Mapping):
        return _deny("PAYLOAD_MALFORMED", "payload must be a mapping")
    if not isinstance(envelope[SIGNATURE_FIELD], str) or not envelope[SIGNATURE_FIELD]:
        return _deny("SIGNATURE_MALFORMED", "signature must be a non-empty string")
    # A hex digest is ASCII by construction, and `hmac.compare_digest` raises
    # TypeError on a non-ASCII str — so a non-ASCII signature is denied here,
    # structurally, rather than being allowed to reach the comparison.
    if not envelope[SIGNATURE_FIELD].isascii():
        return _deny("SIGNATURE_NOT_ASCII", "signature must be an ASCII hex digest")
    return None


def validate_snapshot(
    envelope: Any,
    *,
    key: bytes,
    now: int,
) -> SnapshotVerdict:
    """Validate a synthetic snapshot envelope at an explicitly injected `now`.

    `now` is always supplied by the caller — this module never reads a clock,
    so every test is deterministic and the expiry boundary is exact.
    """
    if not isinstance(key, bytes) or not key:
        return _deny("KEY_MALFORMED", "validation key must be non-empty bytes")
    if not _is_int(now):
        return _deny("NOW_NOT_INTEGER", "now must be an explicitly injected integer")
    if not isinstance(envelope, Mapping):
        return _deny("ENVELOPE_NOT_A_MAPPING", "envelope must be a mapping")

    structural = _check_structure(envelope)
    if structural is not None:
        return structural

    snapshot_id = envelope["snapshot_id"]
    try:
        expected = _signature_over(envelope, key)
    except (TypeError, ValueError):
        return _deny(
            "ENVELOPE_NOT_CANONICALIZABLE",
            "envelope is not serializable as canonical JSON",
            snapshot_id,
        )
    if not hmac.compare_digest(expected, envelope[SIGNATURE_FIELD]):
        return _deny(
            "SIGNATURE_MISMATCH",
            "signature does not match this envelope under the supplied key",
            snapshot_id,
        )

    issued_at = envelope["issued_at"]
    expires_at = issued_at + envelope["ttl_seconds"]
    if now < issued_at:
        return _deny("SNAPSHOT_ISSUED_IN_FUTURE", f"now={now} < issued_at={issued_at}", snapshot_id)
    if now >= expires_at:
        return _deny("SNAPSHOT_EXPIRED", f"now={now} >= expires_at={expires_at}", snapshot_id)
    return SnapshotVerdict(
        VERDICT_VALID,
        "SNAPSHOT_VALID",
        f"issued_at={issued_at} <= now={now} < expires_at={expires_at}",
        snapshot_id,
    )

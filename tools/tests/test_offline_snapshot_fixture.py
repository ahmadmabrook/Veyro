"""
Unit tests for tools/offline_snapshot_fixture.py (MOD-001, GOV-01-R03;
`SCN-MOD001-032`).

`SCN-MOD001-032`'s own steps drive tests 1-2: exercise the offline-mode
fixture-pattern harness itself "against a synthetic signed-snapshot/TTL
fixture", expecting it to "correctly distinguish a valid unexpired snapshot
from an expired one". Tests 3-6 are the fail-closed and non-echo obligations
the pattern carries as a fixture later edge/mobile/POS modules will build on.

  1. test_unexpired_snapshot_validates - the positive: valid at issued_at, at
     mid-window, and at the last valid second (issued_at + ttl - 1).
  2. test_expiry_boundary_denies - DENY exactly at now == issued_at + ttl and
     beyond, deterministically distinct from the last valid second.
  3. test_wrong_key_and_tampering_deny - a correct envelope under a different
     key, and payload/metadata tampering that leaves the signature in place,
     all DENY with SIGNATURE_MISMATCH; re-signing tampered metadata is still
     judged on the metadata's own merits.
  4. test_malformed_and_future_metadata_deny - the fail-closed sweep across
     correctly-signed-but-malformed envelopes, plus a future-issued snapshot
     and a caller-side bad `now`/key. Never a VALID.
  5. test_verdict_never_echoes_key_or_payload - the proof: distinctive key and
     payload sentinels are classified across every verdict class and appear
     nowhere in any verdict's fields or repr.
  6. test_canonical_json_is_deterministic - key insertion order does not
     change the canonical form or the resulting signature.
  7. test_non_ascii_signature_denies_without_raising - BUG-054 regression: a
     non-ASCII signature DENIES instead of raising TypeError out of
     `hmac.compare_digest`.
  8. test_heterogeneous_extra_keys_deny_without_raising - BUG-054 regression:
     an envelope carrying unexpected keys of mixed types DENIES instead of
     raising TypeError while ordering them, and names none of them.

Nothing here reads a clock, a file or the network: `now` is injected as an
explicit integer in every case.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from offline_snapshot_fixture import (
    SIGNATURE_FIELD,
    SNAPSHOT_FIXTURE_KIND,
    TEST_ONLY_SIGNING_KEY,
    VERDICT_DENY,
    canonical_json,
    make_snapshot,
    sign_envelope,
    validate_snapshot,
)

# Explicitly-fake, clearly-labeled test values, per
# `.claude/rules/infra/secrets.md` control 1 - never credential-shaped.
WRONG_KEY = b"EXAMPLE_NOT_A_REAL_KEY-different-offline-snapshot-key"
KEY_SENTINEL = b"EXAMPLE_NOT_A_REAL_KEY-SENTINEL-MUST-NOT-APPEAR"
PAYLOAD_SENTINEL = "SYNTHETIC-SENTINEL-VALUE-DO-NOT-ECHO"

ISSUED_AT = 1_700_000_000
TTL = 300
EXPIRES_AT = ISSUED_AT + TTL
SNAPSHOT_ID = "synthetic-offline-snapshot-032"
PAYLOAD = {"synthetic_catalog_version": 7, "synthetic_note": "fixture-only"}


def _snapshot(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "snapshot_id": SNAPSHOT_ID,
        "payload": PAYLOAD,
        "issued_at": ISSUED_AT,
        "ttl_seconds": TTL,
        "key": TEST_ONLY_SIGNING_KEY,
    }
    kwargs.update(overrides)
    return make_snapshot(**kwargs)


def _validate(envelope: Any, now: int, key: bytes = TEST_ONLY_SIGNING_KEY) -> Any:
    return validate_snapshot(envelope, key=key, now=now)


def test_unexpired_snapshot_validates() -> None:
    envelope = _snapshot()
    for now in (ISSUED_AT, ISSUED_AT + 1, ISSUED_AT + TTL // 2, EXPIRES_AT - 1):
        verdict = _validate(envelope, now)
        assert verdict.is_valid, (now, verdict)
        assert verdict.code == "SNAPSHOT_VALID"
        assert verdict.snapshot_id == SNAPSHOT_ID

    # A one-second TTL is still a real validity window of exactly one second.
    assert _validate(_snapshot(ttl_seconds=1), ISSUED_AT).is_valid


def test_expiry_boundary_denies() -> None:
    envelope = _snapshot()
    assert _validate(envelope, EXPIRES_AT - 1).is_valid

    for now in (EXPIRES_AT, EXPIRES_AT + 1, EXPIRES_AT + 10_000):
        verdict = _validate(envelope, now)
        assert verdict.verdict == VERDICT_DENY, (now, verdict)
        assert verdict.code == "SNAPSHOT_EXPIRED"
        assert verdict.snapshot_id == SNAPSHOT_ID

    # The boundary is the TTL's, not a fixed constant: a shorter TTL expires
    # sooner against the same `now`.
    assert _validate(_snapshot(ttl_seconds=1), ISSUED_AT + 1).code == "SNAPSHOT_EXPIRED"


def test_wrong_key_and_tampering_deny() -> None:
    envelope = _snapshot()
    now = ISSUED_AT + 1

    # Right envelope, wrong key.
    assert _validate(envelope, now, key=WRONG_KEY).code == "SIGNATURE_MISMATCH"

    # Tampering with any field, signature left as issued.
    tampers: list[tuple[str, Any]] = [
        ("payload", {"synthetic_catalog_version": 8, "synthetic_note": "fixture-only"}),
        ("ttl_seconds", TTL * 100),
        ("issued_at", ISSUED_AT - 100),
        ("snapshot_id", "synthetic-offline-snapshot-swapped"),
        ("signature", "0" * 64),
    ]
    for field, value in tampers:
        tampered = dict(envelope)
        tampered[field] = value
        verdict = _validate(tampered, now)
        assert verdict.verdict == VERDICT_DENY, (field, verdict)
        assert verdict.code == "SIGNATURE_MISMATCH", (field, verdict)

    # Tampering plus a re-signature under the wrong key still fails.
    extended = dict(envelope)
    extended["ttl_seconds"] = TTL * 100
    assert _validate(sign_envelope(extended, WRONG_KEY), now).code == "SIGNATURE_MISMATCH"

    # Tampering plus a re-signature under the right key is judged on the
    # metadata's own merits - a TTL extension is honored, so the signature is
    # proven to be the only thing binding the window (hence the fixture's
    # key must stay test-only).
    assert _validate(sign_envelope(extended, TEST_ONLY_SIGNING_KEY), EXPIRES_AT).is_valid


def test_malformed_and_future_metadata_deny() -> None:
    base = {
        "fixture_kind": SNAPSHOT_FIXTURE_KIND,
        "synthetic": True,
        "snapshot_id": SNAPSHOT_ID,
        "issued_at": ISSUED_AT,
        "ttl_seconds": TTL,
        "payload": PAYLOAD,
    }
    # Each is correctly signed, so the DENY is on the metadata, not the HMAC.
    malformed: list[tuple[str, dict[str, Any]]] = [
        ("SYNTHETIC_MARKER_MISSING", {"synthetic": False}),
        ("SYNTHETIC_MARKER_MISSING", {"synthetic": "true"}),
        ("NOT_A_SYNTHETIC_SNAPSHOT", {"fixture_kind": "offline-snapshot"}),
        ("SNAPSHOT_ID_MALFORMED", {"snapshot_id": ""}),
        ("SNAPSHOT_ID_MALFORMED", {"snapshot_id": None}),
        ("ISSUED_AT_NOT_INTEGER", {"issued_at": str(ISSUED_AT)}),
        ("ISSUED_AT_NOT_INTEGER", {"issued_at": float(ISSUED_AT)}),
        ("ISSUED_AT_NOT_INTEGER", {"issued_at": True}),
        ("TTL_NOT_POSITIVE_INTEGER", {"ttl_seconds": 0}),
        ("TTL_NOT_POSITIVE_INTEGER", {"ttl_seconds": -1}),
        ("TTL_NOT_POSITIVE_INTEGER", {"ttl_seconds": 300.0}),
        ("TTL_NOT_POSITIVE_INTEGER", {"ttl_seconds": True}),
        ("PAYLOAD_MALFORMED", {"payload": "not-a-mapping"}),
        ("PAYLOAD_MALFORMED", {"payload": None}),
        ("SIGNATURE_MALFORMED", {"signature": ""}),
        ("SIGNATURE_MALFORMED", {"signature": None}),
    ]
    for expected_code, override in malformed:
        envelope = sign_envelope({**base, **override}, TEST_ONLY_SIGNING_KEY)
        if "signature" in override:
            envelope["signature"] = override["signature"]
        verdict = _validate(envelope, ISSUED_AT + 1)
        assert verdict.verdict == VERDICT_DENY, (override, verdict)
        assert verdict.code == expected_code, (override, verdict)

    # Missing and extra fields.
    dropped = {k: v for k, v in base.items() if k != "ttl_seconds"}
    missing = sign_envelope(dropped, TEST_ONLY_SIGNING_KEY)
    assert _validate(missing, ISSUED_AT + 1).code == "FIELD_SET_MISMATCH"
    extra = sign_envelope({**base, "unexpected_field": 1}, TEST_ONLY_SIGNING_KEY)
    assert _validate(extra, ISSUED_AT + 1).code == "FIELD_SET_MISMATCH"

    # A future-issued snapshot, at the boundary and beyond.
    envelope = _snapshot()
    for now in (ISSUED_AT - 1, ISSUED_AT - 10_000):
        assert _validate(envelope, now).code == "SNAPSHOT_ISSUED_IN_FUTURE", now

    # Caller-side contract breaches fail closed rather than passing.
    assert _validate("not-a-mapping", ISSUED_AT + 1).code == "ENVELOPE_NOT_A_MAPPING"
    assert _validate(None, ISSUED_AT + 1).code == "ENVELOPE_NOT_A_MAPPING"
    for bad_now in (float(ISSUED_AT), str(ISSUED_AT), True, None):
        assert _validate(envelope, bad_now).code == "NOW_NOT_INTEGER", bad_now  # type: ignore[arg-type]
    for bad_key in (b"", "string-key", None):
        assert _validate(envelope, ISSUED_AT + 1, key=bad_key).code == "KEY_MALFORMED"  # type: ignore[arg-type]

    # An unserializable payload cannot be signed, and is denied if injected.
    unserializable = {**base, "payload": {"bad": {1, 2}}, "signature": "0" * 64}
    assert _validate(unserializable, ISSUED_AT + 1).code == "ENVELOPE_NOT_CANONICALIZABLE"


def test_verdict_never_echoes_key_or_payload() -> None:
    payload = {"synthetic_secret_shaped_value": PAYLOAD_SENTINEL}
    envelope = _snapshot(payload=payload, key=KEY_SENTINEL)
    tampered = dict(envelope)
    tampered["ttl_seconds"] = TTL * 2

    verdicts = [
        _validate(envelope, ISSUED_AT + 1, key=KEY_SENTINEL),  # VALID
        _validate(envelope, EXPIRES_AT, key=KEY_SENTINEL),  # expired
        _validate(envelope, ISSUED_AT - 1, key=KEY_SENTINEL),  # future
        _validate(envelope, ISSUED_AT + 1),  # wrong key
        _validate(tampered, ISSUED_AT + 1, key=KEY_SENTINEL),  # tampered
    ]
    assert verdicts[0].is_valid
    assert all(v.verdict == VERDICT_DENY for v in verdicts[1:])

    for verdict in verdicts:
        rendered = f"{verdict!r} {verdict.detail} {verdict.code} {verdict.snapshot_id}"
        assert PAYLOAD_SENTINEL not in rendered, verdict
        assert KEY_SENTINEL.decode() not in rendered, verdict
        assert envelope["signature"] not in rendered, verdict


def test_canonical_json_is_deterministic() -> None:
    first = {"b": 1, "a": {"d": 2, "c": [3, 4]}}
    second = {"a": {"c": [3, 4], "d": 2}, "b": 1}
    assert canonical_json(first) == canonical_json(second)
    assert " " not in canonical_json(first)

    # Insertion order changes nothing: the re-signature of a reordered
    # envelope matches the original's, and it still validates.
    reordered = dict(reversed(list(_snapshot().items())))
    assert _validate(reordered, ISSUED_AT + 1).is_valid
    resigned = sign_envelope(reordered, TEST_ONLY_SIGNING_KEY)
    assert resigned["signature"] == _snapshot()["signature"]


def test_non_ascii_signature_denies_without_raising() -> None:
    """BUG-054: a non-ASCII signature denied, not raised out of compare_digest."""
    valid = _snapshot()
    assert _validate(valid, ISSUED_AT + 1).is_valid  # the fixture itself is sound

    for signature in ("é", "é" * 64, "0" * 63 + "é", "0" * 64 + "é"):
        envelope = dict(valid)
        envelope[SIGNATURE_FIELD] = signature
        # A raised TypeError here is the bug; a verdict is the fix.
        verdict = _validate(envelope, ISSUED_AT + 1)
        assert verdict.verdict == VERDICT_DENY, (signature, verdict)
        assert verdict.code == "SIGNATURE_NOT_ASCII", (signature, verdict)
        assert not verdict.is_valid
        assert signature not in f"{verdict!r} {verdict.detail}", verdict

    # The same envelope with its issued signature is unaffected, at both the
    # last valid second and the expiry boundary.
    assert _validate(valid, EXPIRES_AT - 1).is_valid
    assert _validate(valid, EXPIRES_AT).code == "SNAPSHOT_EXPIRED"


def test_heterogeneous_extra_keys_deny_without_raising() -> None:
    """BUG-054: unexpected keys of mixed types denied, not raised while sorting."""
    envelope: dict[Any, Any] = dict(_snapshot())
    envelope["extra"] = "synthetic-extra"
    envelope[42] = "synthetic-extra-under-int-key"

    # A raised TypeError here is the bug; a verdict is the fix.
    verdict = _validate(envelope, ISSUED_AT + 1)
    assert verdict.verdict == VERDICT_DENY, verdict
    assert verdict.code == "FIELD_SET_MISMATCH", verdict
    assert not verdict.is_valid

    # Unexpected keys are counted, never named - an unknown key could itself
    # carry fixture content, so it must not reach a verdict.
    rendered = f"{verdict!r} {verdict.detail}"
    assert "unexpected_count=2" in verdict.detail, verdict
    assert "extra" not in rendered, verdict
    assert "42" not in rendered, verdict

    # Mixed-type keys that are themselves payload-shaped are equally unnamed,
    # and a mixed key set is still denied when fields are also missing.
    sentinel_keyed: dict[Any, Any] = dict(_snapshot())
    sentinel_keyed[PAYLOAD_SENTINEL] = 1
    sentinel_keyed[0] = 2
    del sentinel_keyed["ttl_seconds"]
    verdict = _validate(sentinel_keyed, ISSUED_AT + 1)
    assert verdict.code == "FIELD_SET_MISMATCH", verdict
    rendered = f"{verdict!r} {verdict.detail}"
    assert PAYLOAD_SENTINEL not in rendered, verdict
    assert "missing=['ttl_seconds'] unexpected_count=2" == verdict.detail, verdict

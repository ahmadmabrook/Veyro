"""MOD-008 IAM-03-R06: the audit log's hash chain, as pure functions.

IAM-03's second critical control is that audit records are "write-once, integrity-protected and
retention-controlled". Insert-only grants make them write-once for the application. This module
is the integrity half, and it is worth being exact about what it buys:

* It **detects** any edit to a stored entry, any deletion from the middle, a rewritten anchor and
  a deletion from the end that forgets to move the chain head.
* It does **not** detect truncation from the end by somebody who also moves the head, because
  every value the verifier compares lives in the same database that actor already controls.
  Closing that needs the head digest published somewhere the database cannot reach, on a
  schedule. This repository has no such place, and CLAUDE.md records the gap rather than this
  module implying otherwise. It was found by tamper-testing `backend/tests/sql/audit_chain.sql`,
  not reasoned about afterwards.
* It is not retention control, which is a policy about deleting old records on purpose and has
  no implementation here.

So the honest summary is that the chain stops an administrator rewriting history *quietly*. That
is less than tamper-proof and considerably more than insert-only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

DIGEST_BYTES = 32
GENESIS = b"\x00" * DIGEST_BYTES
"""What the first entry in a tenant's chain links to.

A fixed anchor rather than a random one: the beginning has to be a value the verifier knows
independently, or rewriting entry one would be undetectable.
"""


class AuditError(ValueError):
    """A chain that does not verify. `code` is stable; `at` is the sequence number it broke at."""

    def __init__(self, code: str, detail: str, at: int | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.at = at


@dataclass(frozen=True)
class Entry:
    sequence: int
    category: str
    action: str
    outcome: str
    actor_identity_id: str | None
    on_behalf_of: str | None
    resource_type: str | None
    resource_id: str | None
    detail: dict[str, Any]
    correlation_id: str
    occurred_at: str
    prev_hash: bytes
    entry_hash: bytes


def canonical(payload: dict[str, Any]) -> bytes:
    """One byte string per payload, whatever order the fields arrived in.

    `sort_keys` and fixed separators, because a digest over a dict that serialises differently on
    two machines is a digest that reports tampering when nothing was tampered with. `ensure_ascii`
    keeps the bytes stable regardless of the writer's locale.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str).encode("utf-8")


def entry_digest(
    tenant_id: str, sequence: int, prev_hash: bytes, payload: dict[str, Any]
) -> bytes:
    """The digest covering an entry and its position in the chain.

    `tenant_id` and `sequence` are inside the digest, not merely beside it, so an entry cannot be
    moved between tenants or reordered within one and still verify.
    """
    if len(prev_hash) != DIGEST_BYTES:
        raise AuditError("bad_prev_hash", "the previous digest is not 32 bytes")
    if sequence < 1:
        raise AuditError("bad_sequence", "a chain starts at 1")
    body = canonical({"tenant_id": tenant_id, "sequence": sequence, "payload": payload})
    return hashlib.sha256(prev_hash + body).digest()


def payload_of(entry: Entry) -> dict[str, Any]:
    """The fields a digest covers: **every column the row stores**, and nothing derived.

    A column stored outside the digest is a column an administrator can change without breaking
    verification, so a new column is added here in the same change that adds it to the table.
    """
    return {
        "category": entry.category,
        "action": entry.action,
        "outcome": entry.outcome,
        "actor_identity_id": entry.actor_identity_id,
        # Covered deliberately. An earlier draft stored this column outside the digest, so the
        # field recording an AI or a support agent acting as a member -- the attribution most
        # worth forging -- was the one field an administrator could edit undetected.
        "on_behalf_of": entry.on_behalf_of,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "detail": entry.detail,
        "correlation_id": entry.correlation_id,
        "occurred_at": entry.occurred_at,
    }


def verify_chain(tenant_id: str, entries: list[Entry]) -> None:
    """Recompute a tenant's chain end to end, raising at the first entry that does not hold.

    This is the full check: it recomputes every digest from the entry's own content, where
    `audit_chain.sql` verifies only that the stored digests link up. Both are worth having -- the
    SQL one runs against any database with no application present, and this one notices an entry
    whose content was changed together with its stored digest.
    """
    expected_prev = GENESIS
    for position, entry in enumerate(sorted(entries, key=lambda e: e.sequence), start=1):
        if entry.sequence != position:
            raise AuditError("gap", f"expected sequence {position}, found {entry.sequence}",
                             at=entry.sequence)
        if entry.prev_hash != expected_prev:
            raise AuditError("broken_link", f"entry {entry.sequence} does not link to its"
                                            " predecessor", at=entry.sequence)
        recomputed = entry_digest(tenant_id, entry.sequence, entry.prev_hash, payload_of(entry))
        if recomputed != entry.entry_hash:
            raise AuditError("content_changed",
                             f"entry {entry.sequence} does not match its own digest",
                             at=entry.sequence)
        expected_prev = entry.entry_hash


def head_of(entries: list[Entry]) -> tuple[int, bytes]:
    """The sequence and digest a chain head should hold for these entries."""
    if not entries:
        return 0, GENESIS
    last = max(entries, key=lambda e: e.sequence)
    return last.sequence, last.entry_hash

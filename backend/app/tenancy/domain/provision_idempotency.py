"""MOD-004: the ProvisionTenant idempotency decision, as a pure function of its inputs.

TSD paragraph 1237 states that every command declares idempotency. ADR-0002 D6.3 states the
contract for `ProvisionTenant` in four cases, and this module decides exactly those four and
nothing else. Quoted from D6.3 rather than paraphrased, because the vocabulary is its:

    "**Payload** is `p_external_key`."
    "**First call:** ... a row returned means `replayed = false`."
    "**Replay (same key, same payload):** ... returns the existing `tenant_id` with
     `replayed = true`."
    "**Same idempotency key, different payload:** the function raises a dedicated, documented
     error ... and writes nothing. A different idempotency key with an already-registered
     `external_key` raises the same error (unique violation mapped to it); neither case returns a
     `tenant_id`."

That last sentence is why this decision takes four inputs rather than two: a payload mismatch
arises from either direction.

**D6.3's status is disclosed rather than resolved, and the disclosure is not symmetric.** Its
section header reads "D6.3 Function allowlist for S1 [PROPOSAL]". Against that, ADR-0002's
accepted-scope statement names "provisioning" in its accepted parenthetical and excludes D4.3, the
D6.4 access-log seam, D6.7 and D6.8 by name -- **D6.3 is not in that exclusion list** -- and
`.claude/rules/backend/mod004-rls.md` lists D1-D6 the same way. So the weight of the record tilts
toward D6.3's provisioning contract sitting inside the accepted narrow scope, with the section
header's marker most plausibly governing the function allowlist's contents. This module does not
decide which reading governs, and nothing here is evidence for either. It takes the **shape** from
D6.3 and claims no **permission** from it: the obligation it rests on is paragraph 1237's, which is
pinned baseline text, and permission to write a lane slice comes from the lane record. An earlier
revision wrote "authority" where it means permission, and presented the conflict as a balanced
standoff; paragraph 1237 supplies none of this module's specifics, which are D6.3's throughout.

Scope. The result is a decision about the four values handed in. It is **not** a uniqueness
constraint, not a registry lookup, not a transaction, not idempotency *enforcement*, and not
evidence that any prior state reported to it is real. D6.3 places uniqueness on two database
constraints and serialization on a unique index; none of that is here and none of it is implied by
a result from this module. It performs no I/O, keeps no state, logs nothing and echoes no raw
input. It establishes no authenticated principal, no authorization of a real caller, no tenant
context and no tenant isolation.

Inputs, all caller claims:
    idempotency_key           required str; idempotency UUID shape.
    external_key              required str; the D6.3 payload.
    registered_external_key   OPTIONAL str; the external key already registered under THIS
                              idempotency key, or `None` for "this key is not registered".
    external_key_taken        required bool; whether `external_key` is registered under a
                              DIFFERENT idempotency key.

Outcomes, one of `OUTCOMES`:
    FIRST             no row for this key, and the payload is not taken elsewhere.
    REPLAY            this key is registered and its payload equals the request's.
    PAYLOAD_MISMATCH  this key is registered with a different payload, or the payload is taken
                      under another key. D6.3 gives both the same error.

Fail closed, and narrowly. Any shape violation is refused. One registry state is refused as
impossible rather than decided: **the same** payload registered under this key and simultaneously
reported as taken under a different key, which would put one `external_key` on two rows against
D6.3's unique constraint on it. An earlier revision refused a wider condition -- any "taken
elsewhere" claim while this key was registered -- which swallowed a legal state D6.3 answers
explicitly: this key holding one payload while the request's payload is registered under another
key keeps both constraints satisfied and is a documented PAYLOAD_MISMATCH. A review caught it by
flipping one flag against a control.

The two shape predicates are duplicated rather than imported. Both originate in
`backend/app/tenancy_s0.py`, the published S0 slice; `_uuid_ok` also appears in
`command_envelope.py`. The external-key predicate cannot be imported at all, because
`tenancy_s0.py` sits outside the lane root and outside the four-module import allowlist.
`_uuid_ok` could be, by `from .command_envelope import _uuid_ok`, and is duplicated by choice: a
cross-module underscore-private import couples two slices, and the lane favours small independent
files. Duplicating a predicate duplicates the obligation to test it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EXTERNAL_KEY_MAX_LENGTH = 128
FIRST = "first"
REPLAY = "replay"
PAYLOAD_MISMATCH = "payload_mismatch"
OUTCOMES = (FIRST, REPLAY, PAYLOAD_MISMATCH)

_EXTERNAL_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*", re.ASCII)
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
    re.ASCII,
)
_UUID_LENGTH = 36
_MESSAGE = "invalid ProvisionTenant idempotency inputs"


class IdempotencyError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    """Immutable decision. `replayed` is D6.3's own field name for the REPLAY case."""

    outcome: str
    replayed: bool


def _uuid_ok(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _UUID_LENGTH
        and _UUID.fullmatch(value) is not None
    )


def _external_key_ok(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= EXTERNAL_KEY_MAX_LENGTH
        and _EXTERNAL_KEY.fullmatch(value) is not None
    )


def decide_provision_idempotency(
    idempotency_key: object,
    external_key: object,
    registered_external_key: object,
    external_key_taken: object,
) -> IdempotencyDecision:
    """Decide the D6.3 idempotency case for these four claims; a decision only, nothing more."""
    if not _uuid_ok(idempotency_key):
        raise IdempotencyError("bad_idempotency_key")
    if not _external_key_ok(external_key):
        raise IdempotencyError("bad_external_key")
    if type(external_key_taken) is not bool:
        raise IdempotencyError("bad_external_key_taken")
    if registered_external_key is not None and not _external_key_ok(registered_external_key):
        raise IdempotencyError("bad_registered_external_key")

    if registered_external_key is None:
        if external_key_taken:
            return IdempotencyDecision(outcome=PAYLOAD_MISMATCH, replayed=False)
        return IdempotencyDecision(outcome=FIRST, replayed=False)

    # This key is registered, so D6.3 compares the payload.
    if registered_external_key == external_key:
        # The same payload reported as also taken under a DIFFERENT key would put one
        # external_key on two registry rows, which D6.3's unique constraint on external_key
        # makes impossible. That state is refused rather than reconciled.
        if external_key_taken:
            raise IdempotencyError("contradictory_registry_state")
        return IdempotencyDecision(outcome=REPLAY, replayed=True)
    # This key holds a different payload. Whether the request's payload is also registered under
    # another key is immaterial: the registry holds each of the two payloads once, so the state is
    # legal, and D6.3 gives both "same idempotency key, different payload" and "a different
    # idempotency key with an already-registered external_key" the same error.
    return IdempotencyDecision(outcome=PAYLOAD_MISMATCH, replayed=False)

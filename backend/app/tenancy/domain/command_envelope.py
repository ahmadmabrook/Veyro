"""MOD-004: the TSD paragraph 1237 common command envelope, as a pure shape decision.

TSD paragraph 1237 states the command inventory -- ProvisionTenant, ActivateTenant,
SuspendTenant, ChangeOrgHierarchy, AssignRegion, RelocateTenant, ArchiveTenant -- and then
states one obligation over all of them: "Every command declares permission, idempotency,
expected aggregate version and transaction boundary." This module decides the two of those four
that are expressible as envelope shape (an idempotency key is present and well formed; an
expected aggregate version, when supplied, is in range) and **refuses to decide the other two**.
Permission is MOD-007/MOD-008 and does not exist; a transaction boundary is the database's and
this lane has none.

Scope. Success means the envelope is *shape-valid* and names a command the source states. It is
never an authenticated principal, an authorization of a real caller, a tenant selection or
creation, idempotency deduplication, an aggregate-version check against any stored version,
tenant context, a database constraint or tenant-isolation evidence. This module performs no I/O,
keeps no state, logs nothing and echoes no raw input.

No command payload is validated, and that is deliberate rather than unfinished. Paragraph 1237
states no payload for any command, and `MOD-004.md` records the contents that would make one up
-- hierarchy cardinalities, region and residency policy, template and default contents -- as
owner-reserved. Validating an invented payload would breach the MOD-004 RLS Rule's obligation 8
(no invention of product behaviour or owner policy), so this module validates the common
envelope and stops.

`ArchiveTenant` is refused although paragraph 1237 names it. **TSD** paragraph 1231 -- pinned
baseline source text, not a proposal -- requires approvals, retention checks and an immutable
audit record for destructive lifecycle actions; `MOD-004.md` records that no destructive lifecycle
command is built or accepted before the MOD-008 immutable audit exists, and MOD-008 does not
exist. The name is therefore known rather than unknown -- `unknown_command` would misreport it --
and the refusal is its own code. Fail closed: a gate that does not exist is not a gate that
passed.

`DESTRUCTIVE_COMMANDS` names the paragraph 1237 commands **this module refuses** on paragraph
1231 grounds. It is not a classification of destructive acts, and a later slice must not read it
as evidence that any other command needs no paragraph 1231 gate. Relocation is the case to be
careful with: TSD paragraph 777 makes "source deletion after retention gate" the last of twelve
relocation stages, and that stage is not a paragraph 1237 command, so it is outside this module's
subject in both directions -- not refused here, and not licensed here either.

Why this docstring argues no further. Two successive independent reviews each found one false
claim about a pinned document in this prose, and none in the code; the deciding logic was correct
both times. Source interpretation beyond a single-step citation therefore lives in the publishing
commit message, not here.

Flat schema (all keys are exact `str`; any other key is refused):
    command           required str; one of `COMMANDS`, spelled as paragraph 1237 spells it.
    actor_id          required str; CLAIMED actor UUID (caller claim, not authenticated).
    correlation_id    required str; CLAIMED correlation UUID.
    idempotency_key   required str; idempotency UUID shape metadata, retained only.
    expected_version  OPTIONAL int. Absent -> `None` ("no version supplied"). Present `None` is
                      REFUSED (present-null differs from absent). Range 0..EXPECTED_VERSION_MAX.

Open discrepancy, kept explicit and NOT resolved here. TSD paragraph 1237 says every command
declares an expected aggregate version and paragraph 1239 ties that version to optimistic
concurrency, while ADR-0002 D6.3 has initial provisioning take none; ADR-0002 records that
discrepancy as explicit and bars S0 from inventing a required version. This module treats
`expected_version` as optional for all seven commands and assigns absence the meaning "no version
supplied", never "no version required". Stated plainly because the permissive reading here is
**wider than the conflict it inherits**: the conflict is about initial provisioning, and six of
the seven commands act on an existing aggregate, where the sources do not conflict. Deciding
per-command requiredness needs an aggregate to version and belongs to the slice that implements
the lifecycle transitions. This module declines it rather than settling it by omission.

Mapping, UUID and bounds policy follow `backend/app/tenancy_s0.py`, the **published** S0 slice --
published is what `CLAUDE.md` says, and no record calls it accepted, which in this project is a
distinct status. Only an exact built-in `dict`; no nested value is traversed; UUIDs are exact
hyphenated 8-4-4-4-12 hex, normalized to lower case. The nil UUID and any non-RFC-4122 variant or
version outside 1..8 are rejected -- `[1-8]` is the version nibble and `[89abAB]` the variant
nibble, stated separately because an earlier revision here conflated them.

`type(value) is str` rather than `isinstance`, in `_uuid_ok` and for every key: a `str` subclass
satisfies the length and regex checks, and the accept path calls `.lower()`, so an overridden
`lower()` would write caller-chosen content into the frozen result. The exact-type check is the
only thing refusing that, and a test pins it.

One idiom departs from that slice, and the reason is the lane rather than taste. `EnvelopeError`
sets `args` directly instead of calling `super().__init__(...)`: the lane's closure check refuses
every `__dunder__` attribute access except `__doc__` and `__name__`, so the S0 spelling is
unwritable here. The observable behaviour is the same -- a generic message built only from
constants in this module, and a fixed `code`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COMMANDS = (
    "ProvisionTenant",
    "ActivateTenant",
    "SuspendTenant",
    "ChangeOrgHierarchy",
    "AssignRegion",
    "RelocateTenant",
    "ArchiveTenant",
)
DESTRUCTIVE_COMMANDS = ("ArchiveTenant",)
EXPECTED_VERSION_MAX = 2**31 - 1
MAX_FIELDS = 16
MAX_FIELD_NAME_LENGTH = 32

_COMMANDS = frozenset(COMMANDS)
_DESTRUCTIVE = frozenset(DESTRUCTIVE_COMMANDS)
_REQUIRED = ("command", "actor_id", "correlation_id", "idempotency_key")
_ALLOWED = frozenset(_REQUIRED) | {"expected_version"}
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
    re.ASCII,
)
_UUID_LENGTH = 36
_MESSAGE = "invalid MOD-004 command envelope"


class EnvelopeError(ValueError):
    """Generic refusal of a malformed or gated envelope; never carries raw input."""

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    """Immutable, shape-valid result. All UUIDs are CLAIMS in canonical lower case."""

    command: str
    actor_id: str
    correlation_id: str
    idempotency_key: str
    expected_version: int | None


def _uuid_ok(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _UUID_LENGTH
        and _UUID.fullmatch(value) is not None
    )


def _version_ok(value: object) -> bool:
    return type(value) is int and 0 <= value <= EXPECTED_VERSION_MAX


def validate_command_envelope(envelope: object) -> CommandEnvelope:
    """Decide the shape of a paragraph 1237 command envelope; shape only, nothing more."""
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

    command = envelope["command"]
    if type(command) is not str or command not in _COMMANDS:
        raise EnvelopeError("unknown_command")
    if command in _DESTRUCTIVE:
        raise EnvelopeError("destructive_command_gated")

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

    return CommandEnvelope(
        command=command,
        actor_id=envelope["actor_id"].lower(),
        correlation_id=envelope["correlation_id"].lower(),
        idempotency_key=envelope["idempotency_key"].lower(),
        expected_version=version,
    )

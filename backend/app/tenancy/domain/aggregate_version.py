"""MOD-004: the expected-aggregate-version comparison, as a pure decision.

TSD paragraph 1237 states that every command declares an expected aggregate version. TSD
paragraph 1239 states what the version is for: "Indexes/concurrency: tenant-leading indexes for
primary list/detail paths; unique external/provider identifiers are scoped by tenant/provider;
aggregate version supports optimistic concurrency." This module decides the comparison those two
sentences imply and nothing beyond it.

Both are rows of §10.1 "PLT-01 - Tenant, Organization, Brand & Location Management": paragraph
1237 is its `Command inventory` row and paragraph 1239 its `Indexes/concurrency` row. The row
labels are given because the paragraph numbers alone do not survive a baseline renumbering here.
Paragraph 1239's sentence is cross-module boilerplate that recurs in 49 paragraphs of the pinned
TSD -- 57 sections carry an `Indexes/concurrency` row -- so matching on its text cannot identify
which one is PLT-01's. The §10.1 heading occurs exactly once, and each of these labels occurs
exactly once inside that section, so heading plus label is a unique pair where the number is not.

Scope. The result is a comparison of two numbers the caller supplies. It is **not** a concurrency
control, not a lock, not a read of any stored version, and not evidence that the `current_version`
handed in is the aggregate's real version -- that is the database's, under D6.3's serialization on
a unique index. A MATCH is not permission to write, and **neither is NO_EXPECTATION**: a caller
writing `if outcome != MISMATCH` would read an absent expectation as agreement, which is the
resolution this module declines. This module performs no I/O, keeps no state,
logs nothing and echoes no raw input. It establishes no authenticated principal, no authorization
of a real caller, no tenant context and no tenant isolation.

Three outcomes, one of `OUTCOMES`:
    MATCH            the expectation was supplied and equals `current_version`.
    MISMATCH         the expectation was supplied and differs from `current_version`.
    NO_EXPECTATION   no expectation was supplied.

NO_EXPECTATION reports a state rather than deciding it, and the reason is a recorded open
discrepancy. ADR-0002 states: "The TSD paragraph 1237 versus D6.3 initial-provisioning
expected-version discrepancy remains explicit; S0 may not invent a required version." Paragraph
1237 says every command declares a version; D6.3's `provision_tenant` signature takes none. So
whether an absent expectation is admissible is unresolved in the sources, and a module that
returned MATCH or MISMATCH for it would be resolving it. It returns the third outcome instead and
leaves the decision to the caller that has an aggregate and a policy. `backend/app/tenancy_s0.py`
and `command_envelope.py` take the same position by treating `expected_version` as optional
metadata.

**MISMATCH is not subdivided, deliberately.** A supplied expectation below `current_version` and
one above it are both MISMATCH. No pinned source distinguishes a stale expectation from one ahead
of the aggregate, so naming them separately would invent a distinction the sources do not state.

Inputs, both caller claims:
    expected_version  OPTIONAL int, or `None` for "no expectation supplied". Accepted range
                      0..VERSION_MAX inclusive; `bool`, `float`, `str`, containers and negatives
                      are refused.
    current_version   required int in the same range. `None` is refused: an absent current version
                      is not a comparison this module can make.

Fail closed. Any shape violation is refused rather than resolved.

`VERSION_MAX` matches `command_envelope.EXPECTED_VERSION_MAX` and
`tenancy_s0.EXPECTED_VERSION_MAX`, both 2**31 - 1, and a test pins the value here rather than
only its relation to this module's own symbol. The bound is duplicated rather than imported.
`tenancy_s0.py` sits outside the lane root and outside the four-module import allowlist, so the
closure check refuses every spelling that reaches it -- a rule about spellings, not a property of
the import graph, which the lane record's section 3.1 states in those terms. Python itself
imports the file perfectly well. `command_envelope.py` could be imported with the check's
permission, and is not, because a cross-module import couples
two slices and the lane favours small independent files.
"""

from __future__ import annotations

from dataclasses import dataclass

VERSION_MAX = 2**31 - 1
MATCH = "match"
MISMATCH = "mismatch"
NO_EXPECTATION = "no_expectation"
OUTCOMES = (MATCH, MISMATCH, NO_EXPECTATION)

_MESSAGE = "invalid aggregate version comparison inputs"


class VersionError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class VersionComparison:
    """Immutable comparison. `expectation_supplied` distinguishes the third outcome's cause."""

    outcome: str
    expectation_supplied: bool


def _version_ok(value: object) -> bool:
    return type(value) is int and 0 <= value <= VERSION_MAX


def compare_expected_version(
    expected_version: object,
    current_version: object,
) -> VersionComparison:
    """Compare a claimed expectation against a claimed current version; a comparison only."""
    if not _version_ok(current_version):
        raise VersionError("bad_current_version")
    if expected_version is None:
        return VersionComparison(outcome=NO_EXPECTATION, expectation_supplied=False)
    if not _version_ok(expected_version):
        raise VersionError("bad_expected_version")
    if expected_version == current_version:
        return VersionComparison(outcome=MATCH, expectation_supplied=True)
    return VersionComparison(outcome=MISMATCH, expectation_supplied=True)

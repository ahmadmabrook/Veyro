"""MOD-004: the relocation-stage name closure, as a pure decision.

TSD paragraph 777 is labelled "Relocation stages:" and states twelve, arrow-separated and in
order, from "preflight" to "source deletion after retention gate". This module admits exactly
those twelve and refuses every other name.

**The trap this exists for is in the very next paragraph.** Paragraph 778 opens "The cutover uses
a relocation_epoch included in requests/events", so the source's own word for the thing in the
adjacent paragraph is `cutover` -- and `cutover` is not one of the twelve stage names. The
eighth stage is `route switch`, which is the only one of the twelve paragraph 778 names. So an
author reading the epoch rule and reaching for a stage name lands outside the enumeration, and
the surrounding vocabulary pulls the same way: `rollback` occurs 41 times in the pinned TSD,
`validation` 68, `failover` 32, `cutover` 30, `dry run` 5, `canary` 4, while the real stage names
are rare -- `preflight` once, `write freeze` twice, `route switch` three times. Refusing an
unstated stage is what the MOD-004 RLS Rule's obligation 8 requires: an unsupported workflow
stage is a gap to raise, not to fill.

**The twelfth name excludes the sentence's final period.** Paragraph 777 ends "... source
deletion after retention gate." and that period closes the sentence rather than belonging to the
name, so the stored name omits it. A transcription that keeps it is refused, which is pinned,
because it is the most likely way to get one of these twelve slightly wrong.

**Membership only, not precedence.** Paragraph 777 states a sequence rather than a set, and this
module answers only whether a name is a stated stage. A caller that needs "does A precede B"
computes it from `RELOCATION_STAGES`, which it already holds: both are pure values, so declining
to answer withholds a label rather than data. That argument depends on a property of this
module's public surface rather than of the caller's inputs, which is what a sequence adds over a
set -- for a set, membership is the whole stated content, while here the order is stated content
too. So the constant is an **immutable ordered tuple**, and the test suite pins that it is: were
it exported as a frozenset the order would be gone and declining would withhold data rather than
a label, and were it a list any code in the process could append to or sort it and destroy the
order while every refusal still behaved correctly. Deciding precedence here would also invite
reading it as a claim about a running relocation, which no pure function can make; that reason
holds independently of the first.

Scope. Success means the name is one the sources state as a relocation stage. It is **not** a
relocation, not an executed stage, not a transition, not a workflow engine, not a freeze, not a
copy and not a reconciliation. Paragraph 778's epoch rule -- that commands carrying the old
epoch are rejected after route switch -- is a different decision over different inputs and is
not made here. This module performs no I/O, keeps no state, logs nothing and echoes no raw
input. It establishes no authenticated principal, no authorization of a real caller, no tenant
context and no tenant isolation.

Input, a caller claim:
    name   required str; exact `str` only, so a `str` subclass cannot smuggle a different value
           through the set membership or the return.

Returns the name unchanged on success. It is not normalized: paragraph 777 spells every stage in
lower case, and eleven of the twelve contain a space, a hyphen or a solidus that a caller might
rewrite -- four of them a hyphen or a solidus, which are the separators most likely to be
normalised away, and `preflight` alone is a single bare word. Case-folding, trimming or
collapsing any of those would admit spellings the sources do not state.

Fail closed. A non-`str`, an over-long name and an unstated name are refused with distinct codes,
so a caller can tell a malformed input from a name outside the stated set.
"""

from __future__ import annotations

RELOCATION_STAGES = (
    "preflight",
    "target provision",
    "snapshot/copy",
    "change-data catch-up",
    "write freeze",
    "final delta",
    "integrity/financial reconciliation",
    "route switch",
    "cache/session invalidation",
    "observation window",
    "source quarantine",
    "source deletion after retention gate",
)
# Not a claim about name length: the longest stated name is 36 characters. The bound refuses an
# unbounded input before the set lookup, which is the only operation here whose cost grows.
MAX_STAGE_NAME_LENGTH = 64

_STAGES = frozenset(RELOCATION_STAGES)
_MESSAGE = "invalid relocation stage name"


class StageNameError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


def validate_relocation_stage(name: object) -> str:
    """Return `name` unchanged if the sources state it as a relocation stage; else refuse."""
    if type(name) is not str:
        raise StageNameError("bad_stage_name_type")
    if len(name) > MAX_STAGE_NAME_LENGTH:
        raise StageNameError("stage_name_too_long")
    if name not in _STAGES:
        raise StageNameError("unstated_stage")
    return name

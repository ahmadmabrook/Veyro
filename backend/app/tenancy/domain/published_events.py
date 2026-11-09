"""MOD-004: the published-event name closure, as a pure decision.

TSD paragraph 1206 and paragraph 1241 each state the same six names, in the same order:
"tenant.provisioned, tenant.activated, tenant.suspended, organization.updated,
location.opened, brand.created". Paragraph 1241 labels them "Published events". This module
admits exactly those six and refuses every other name.

**The guard's value is the names it refuses, not the ones it admits.**
`knowledge/03-Modules/MOD-004/MOD-004.md` records "Delete command and archived/deleted events
absent from paragraph 1237/paragraph 1206" as a source gap under PLT-01-R01. So an author
implementing a lifecycle is pulled toward `tenant.archived` and `tenant.deleted`, and neither is
stated. Refusing them is refusing to fill a recorded source gap in code, which is what the
MOD-004 RLS Rule's obligation 8 requires: unsupported events are a gap to raise, not to fill.

Scope. Success means the name is one the sources state. It is **not** an emitted event, not an
outbox row, not a delivery, not an ordering, not a schema and not a payload. No envelope field is
validated here: paragraph 1241 states the names and nothing about an envelope's shape, and the
module declines to supply one. Paragraph 1241's further requirement that "dependencies are
accessed by stable contracts/projections, never direct write-table joins" is an architectural
constraint on how code is written rather than a decision over a caller's input, so it is outside
this module and is not evidenced by it. This module performs no I/O, keeps no state, logs nothing
and echoes no raw input. It establishes no authenticated principal, no authorization of a real
caller, no tenant context and no tenant isolation.

Input, a caller claim:
    name   required str; exact `str` only, so a `str` subclass cannot smuggle a different value
           through the set membership or the return.

Returns the name unchanged on success. It is not normalized: paragraph 1206 and paragraph 1241
both spell these names in lower case with a single dot, and case-folding or trimming an input to
match would admit spellings the sources do not state.

Fail closed. A non-`str` and an unstated name are refused with distinct codes, so a caller can
tell a malformed input from a name outside the stated set.
"""

from __future__ import annotations

PUBLISHED_EVENTS = (
    "tenant.provisioned",
    "tenant.activated",
    "tenant.suspended",
    "organization.updated",
    "location.opened",
    "brand.created",
)
MAX_EVENT_NAME_LENGTH = 64

_PUBLISHED = frozenset(PUBLISHED_EVENTS)
_MESSAGE = "invalid published event name"


class EventNameError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


def validate_published_event(name: object) -> str:
    """Return `name` unchanged if the sources state it as a published event; else refuse."""
    if type(name) is not str:
        raise EventNameError("bad_event_name_type")
    if len(name) > MAX_EVENT_NAME_LENGTH:
        raise EventNameError("event_name_too_long")
    if name not in _PUBLISHED:
        raise EventNameError("unstated_event")
    return name

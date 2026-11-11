"""MOD-004 PLT-01-R01: the tenant lifecycle transition decision, as a pure function.

TSD paragraph 1222 states the requirement in one sentence: "Provision, activate, suspend, archive
and delete tenants through a controlled lifecycle." Five verbs. Paragraph 1237's command inventory
names seven commands -- "ProvisionTenant, ActivateTenant, SuspendTenant, ChangeOrgHierarchy,
AssignRegion, RelocateTenant, ArchiveTenant" -- and paragraph 1241's published events name six:
"tenant.provisioned, tenant.activated, tenant.suspended, organization.updated, location.opened,
brand.created". This module decides, for a command and a current state, whether the pair lies on
**this module's reading** of paragraph 1222's verb order. It decides nothing else.

**That reading is an engineering inference, not a source statement, and every admitted transition
says so.** The sources state no transition table anywhere: no paragraph says which state a command
may be issued from. Paragraph 1237 attaches four obligations to each command -- permission,
idempotency, expected aggregate version, transaction boundary -- and no from-state to any of them.
Paragraph 1222 is a prose capability sentence. So the four pairs in `_READ_ORDER` are chosen by
reading the verb enumeration as a sequence, and `Transition.order_sourced` is `False` on every one
of them. A caller that needs a sourced transition table is reading a gap. If a later baseline states
one, `_READ_ORDER` is the one tuple that changes.

`order_sourced` borrows the *form* of the sibling `hierarchy_containment`'s `shape_decided`, and the
two are **not** equally grounded -- a later reader must not cite them as equivalent. There,
`shape_decided=False` marks one dimension the decision does not cover while the decision itself
rests on two sourced grounds, paragraph 1223's kinds and paragraph 1230's containment. Here,
`order_sourced=False` marks the *entire basis* of the decision: every answer `apply_command` gives,
admission and refusal alike, is author-grounded. No downstream slice may treat an admitted
`Transition` as a fact about PLT-01.

**That the pinned baseline is not silent about tenant lifecycle elsewhere is the strongest argument
against this reading, and is recorded rather than omitted.** TSD section 10.53 LIF-03 (Offboarding,
Data Portability, Archival & Deletion) states "Tenant lifecycle from active to past due, suspended,
cancelled, read-only, archived and deleted" -- a seven-state progression written as an explicit
"from X to Y" ordering, naming `past due`, `cancelled` and `read-only`, which `STATES` below does
not carry. Section 10.3 PLT-03 states "Trial conversion, dunning, grace periods, suspension,
**reactivation** and offboarding coordination". Neither is a PLT-01 transition table and neither is
in the paragraph 1194-1245 block this module is scoped to, so neither is adopted here -- but if a
bare enumeration can be read as an ordering, LIF-03's explicit one has the better claim, and the two
disagree. The refusal codes below are therefore named for the reading, never for the sources.

**Two source gaps are refused rather than filled**, which is what the MOD-004 RLS Rule's obligation
8 requires of an unsupported construct, and what `knowledge/03-Modules/MOD-004/MOD-004.md` already
records under PLT-01-R01 as "Delete command and archived/deleted events absent from paragraph 1237 /
paragraph 1206".

* **Deletion has no PLT-01 command and no PLT-01 event.** Paragraph 1222 names the verb; paragraph
  1237 carries no `DeleteTenant` and paragraph 1241 no `tenant.deleted`. A deletion request is
  refused with its own code rather than modelled as a state. `hard_deletion_gates` separately
  decides the paragraph 1228 gate question; this module does not duplicate or answer it.
* **Archival has a PLT-01 command but no PLT-01 event.** `ArchiveTenant` is in paragraph 1237;
  paragraph 1241 publishes nothing for it, so an admitted archival transition carries
  `event_stated=False` and `event=None`. Scoped deliberately: the name `tenant.archived` **does**
  exist in the pinned baseline, in section 10.53 LIF-03's published events, owned by another domain.
  What is absent is a PLT-01 event, and that is all this module reports.

**Reconciliation with `command_envelope`, which refuses `ArchiveTenant` outright.** That sibling
declares `DESTRUCTIVE_COMMANDS = ("ArchiveTenant",)` and raises `destructive_command_gated`, on the
reasoning that paragraph 1231 requires "approvals, retention checks and an immutable audit record",
that MOD-008 does not exist, and that a gate which does not exist is not a gate that passed. This
module admits the archival transition instead, and the two are answering different questions: an
envelope decision is about whether a command may be **carried**, and a transition decision is about
where a command would **land** if it ever were. Neither composes into permission. A caller running
both gets `destructive_command_gated` from the envelope and an admitted transition here, and the
envelope's refusal is the operative one -- this module never overrides it and must not be read as
relaxing it.

Scope. Success means the pair lies on this module's reading of the verb order. It is **not**
permission, not authorization of a caller, not an approval, not a retention or billing gate, not an
audit record, and not a persisted state change. None of paragraph 1231's three requirements exists
in this module or anywhere in the lane, and an admitted transition satisfies none of them. The
module performs no I/O, keeps no state, logs nothing and echoes no raw input. It establishes no
authenticated principal, no tenant context and no tenant isolation.

Inputs, both caller claims:
    command        required str; exact `str` only, so a `str` subclass cannot smuggle a different
                   value through the membership test or the returned transition.
    current_state  required str, or `None` for "no tenant exists yet", which is the only state this
                   reading has `ProvisionTenant` act from.

Fail closed. A malformed command token, a deletion request, a non-lifecycle command, an unknown
command, a malformed state token, an unknown state and a pair off the read order are refused with
distinct codes. A non-`str` and an over-long token deliberately share one code per input, because
both mean the same thing to a caller: the token never entered the vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass

TOKEN_MAX = 64

NO_TENANT = "no_tenant"
PROVISIONED = "provisioned"
ACTIVE = "active"
SUSPENDED = "suspended"
ARCHIVED = "archived"
# The five states PLT-01's four lifecycle commands reach, and no others. Section 10.53 LIF-03 names
# a wider tenant lifecycle, quoted in the module docstring and deliberately not adopted here.
STATES = (NO_TENANT, PROVISIONED, ACTIVE, SUSPENDED, ARCHIVED)

PROVISION = "ProvisionTenant"
ACTIVATE = "ActivateTenant"
SUSPEND = "SuspendTenant"
ARCHIVE = "ArchiveTenant"
LIFECYCLE_COMMANDS = (PROVISION, ACTIVATE, SUSPEND, ARCHIVE)

# Paragraph 1237's other three commands. They are stated commands of this module, so they are not
# unknown, but they name no lifecycle state and are refused with their own code.
NON_LIFECYCLE_COMMANDS = ("ChangeOrgHierarchy", "AssignRegion", "RelocateTenant")

# Paragraph 1241's three tenant events, each tied to the state its command reaches. `ARCHIVED` is
# absent from paragraph 1241 and is therefore absent here.
STATE_EVENTS = {
    PROVISIONED: "tenant.provisioned",
    ACTIVE: "tenant.activated",
    SUSPENDED: "tenant.suspended",
}

# This module's reading of paragraph 1222's verb order. Not a sourced transition table; see the
# module docstring. `order_sourced` is `False` on every transition built from it.
_READ_ORDER = (
    (PROVISION, NO_TENANT, PROVISIONED),
    (ACTIVATE, PROVISIONED, ACTIVE),
    (SUSPEND, ACTIVE, SUSPENDED),
    (ARCHIVE, SUSPENDED, ARCHIVED),
)

# Spellings of the paragraph 1222 verb that has neither a PLT-01 command nor a PLT-01 event. Matched
# after the token test, so the refusal names the gap rather than reporting an unknown token.
_DELETION_SPELLINGS = ("DeleteTenant", "delete", "Delete", "deleteTenant", "HardDeleteTenant")

_MESSAGE = "invalid tenant lifecycle transition inputs"


class LifecycleError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class Transition:
    """An admitted transition.

    `event_stated` distinguishes a withheld event from one PLT-01 does not publish. `order_sourced`
    is always `False` and says so to the caller: the ordering is this module's reading of paragraph
    1222, not a transition the sources state.
    """

    command: str
    from_state: str
    to_state: str
    event: object
    event_stated: bool
    order_sourced: bool


def apply_command(command: object, current_state: object) -> Transition:
    """Decide whether this command from this state lies on the read order. A decision only.

    The two type tests are written inline rather than behind a shared `_token_ok` helper: a helper
    returning `bool` does not narrow `object` to `str` for the type checker, and `typing.TypeGuard`
    is not reachable -- the lane's allowed-import closure is `__future__`, `dataclasses`, `enum`
    and `re`. `authoritative_entities` inlines the same test for the same reason.
    """
    if type(command) is not str or not 0 < len(command) <= TOKEN_MAX:
        raise LifecycleError("bad_command")
    if command in _DELETION_SPELLINGS:
        raise LifecycleError("deletion_not_sourced")
    if command in NON_LIFECYCLE_COMMANDS:
        raise LifecycleError("command_not_a_lifecycle_command")
    if command not in LIFECYCLE_COMMANDS:
        raise LifecycleError("unknown_command")

    state = NO_TENANT if current_state is None else current_state
    if type(state) is not str or not 0 < len(state) <= TOKEN_MAX:
        raise LifecycleError("bad_state")
    if state not in STATES:
        raise LifecycleError("unknown_state")

    for read_command, from_state, to_state in _READ_ORDER:
        if read_command == command and from_state == state:
            event = STATE_EVENTS.get(to_state)
            return Transition(
                command=command,
                from_state=from_state,
                to_state=to_state,
                event=event,
                event_stated=event is not None,
                order_sourced=False,
            )
    raise LifecycleError("transition_outside_read_order")

"""MOD-004: the role-attribute name closure, as a pure decision.

TSD paragraph 743 is labelled "Role model:" and states five role attributes: "LOGIN,
NOSUPERUSER, NOCREATEDB, NOCREATEROLE and NOBYPASSRLS". They are PostgreSQL attributes, which
paragraph 743 does not itself say: the word comes from paragraph 742, the heading "PostgreSQL RLS
enforcement contract" directly above it, under paragraph 741's "7.3 Data Isolation Model". This
module admits exactly those five names and refuses every other. It is a decision about a
**name**, and the sections below say at length what it is therefore not, because this is the one
closure in this lane whose subject has a security consequence.

**The trap is that the dangerous answers are substrings of the stated ones.** `SUPERUSER` is
inside `NOSUPERUSER`, `BYPASSRLS` inside `NOBYPASSRLS`, `CREATEDB` inside `NOCREATEDB` and
`CREATEROLE` inside `NOCREATEROLE`. So a guard matching loosely reports all four as stated, while
whole-word matching finds each of them **zero** times in paragraph 743 and zero across the whole
pinned TSD. Refusing `BYPASSRLS` therefore rests on a measured absence **from the pinned
sources** rather than on a judgment -- not on any measurement of a database, which this module
cannot make. It is the one wrong answer here that would matter: `BYPASSRLS` is the exact negation
of a required attribute, and the MOD-004 RLS Rule's rule 4 requires runtime roles to be
NOBYPASSRLS.

**It decides the attribute name only, and says nothing about which role carries it.** Paragraph
743 attaches these five to named roles, and ADR-0002 marks that step in its own Decision section:
it records the five flags as `[SRC]` from paragraph 743, then records as `[INFERENCE]` that
"Extending these flags to the control-plane runtime and worker roles is an engineering
inference", because paragraph 743 names the product-plane roles while MOD-004 is the control
plane. The names are sourced; attaching them to any particular role is not. This module closes
over the sourced part and leaves the inference where its own record keeps it.

**This is not a step toward the obligation it sits next to.** The MOD-004 RLS Rule requires
"A role-privilege test proving the runtime role is not a table owner and has no BYPASSRLS or
role-membership escape (rule 4)", and says of that test and its companion that they "are
obligations, not existing PASS; none is recorded today". Nothing here contributes to it. That
test must run as the actual runtime role against a real database; this module never connects to
one, never reads a role's configuration, and cannot tell whether any role anywhere has any
attribute. Admitting the name `NOBYPASSRLS` says only that paragraph 743 states it. A caller that
treats a success here as evidence about a role has made exactly the error this paragraph exists
to foreclose.

Scope. Success means the name is one the sources state as a role attribute. It is **not** a role,
not a grant, not a privilege, not a policy, not RLS, not a migration, not a database
configuration and not a verification of anything. This module performs no I/O, keeps no state,
logs nothing and echoes no raw input. It establishes no authenticated principal, no authorization
of a real caller, no tenant context and no tenant isolation.

Input, a caller claim:
    name   required str; exact `str` only, so a `str` subclass cannot smuggle a different value
           through the set membership or the return.

Returns the name unchanged on success. It is not normalized, and case-folding has a concrete cost
rather than a theoretical one: paragraph 743 spells all five in upper case, while lower-case
"login" occurs eight times in the pinned TSD as an ordinary English word. Folding would make
every one of those an occurrence of a stated role attribute.

Fail closed. A non-`str`, an over-long name and an unstated name are refused with distinct codes,
so a caller can tell a malformed input from a name outside the stated set.
"""

from __future__ import annotations

ROLE_ATTRIBUTES = (
    "LOGIN",
    "NOSUPERUSER",
    "NOCREATEDB",
    "NOCREATEROLE",
    "NOBYPASSRLS",
)
# Not a claim about name length: the longest stated name is 12 characters. The bound refuses an
# unbounded input before the set lookup, which is the only operation here whose cost grows.
MAX_ATTRIBUTE_NAME_LENGTH = 64

_ATTRIBUTES = frozenset(ROLE_ATTRIBUTES)
_MESSAGE = "invalid role attribute name"


class RoleAttributeError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


def stated_role_attribute(name: object) -> str:
    """Return `name` unchanged if paragraph 743 states it as a role attribute; else refuse.

    Named `stated_` rather than `validate_` deliberately. A `validate_role_attribute` would read
    as "this role attribute has been validated", which is one step from a false security claim in
    a log or a status report. The only thing established here is what the source states.
    """
    if type(name) is not str:
        raise RoleAttributeError("bad_attribute_name_type")
    if len(name) > MAX_ATTRIBUTE_NAME_LENGTH:
        raise RoleAttributeError("attribute_name_too_long")
    if name not in _ATTRIBUTES:
        raise RoleAttributeError("unstated_attribute")
    return name

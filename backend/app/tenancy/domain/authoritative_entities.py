"""MOD-004: the authoritative-entity name closure, as a pure decision.

TSD paragraph 1204 and paragraph 1236 each state the same nine names, in the same order:
"Tenant, Organization, LegalEntity, Brand, Region, Location, Department, CostCenter,
TenantConfiguration". Paragraph 1203 labels them "Authoritative entities" and paragraph 1236
calls them "Authoritative entities/tables". This module admits exactly those nine and refuses
every other name.

**The guard's value is the names it refuses, not the ones it admits**, and this block pulls an
author two ways at once. `knowledge/03-Modules/MOD-004/MOD-004.md` records under PLT-01-R02 that
paragraph 1237 carries "no maintenance command for LegalEntity, Department, CostCenter or
TenantConfiguration", and records separately that "Read models: paragraph 1238 covers four of
nine entities" -- paragraph 1238 names Tenant, Organization, LegalEntity and Brand only. So four
of the nine have no command and five have no projection. The first pull is to invent an entity:
`Franchise`, `Chain`, `Facility`, `Gym` and `Club` each occur elsewhere in the TSD and zero times
in the paragraph 1194-1245 block, so they are the product's own vocabulary and not this module's
entities. The second pull is the opposite -- to take paragraph 1238's four-name projection subset
for the entity set and drop the other five. A closure over the nine refuses both. Refusing is
refusing to fill a recorded source gap in code, which is what the MOD-004 RLS Rule's obligation 8
requires: unsupported tables are a gap to raise, not to fill.

Scope. Success means the name is one the sources state as an authoritative entity. It is **not**
a table, not a schema, not a column, not a migration, not an aggregate, not a projection and not
a command. Paragraph 1236's phrase joins entities and tables, but neither it nor paragraph 1208
states a single table spelling: both say only "module-prefixed tables". This module therefore
decides entity names and answers nothing about table names, which belong to the RLS layer it
cannot write. It performs no I/O, keeps no state, logs nothing and echoes no raw input. It
establishes no authenticated principal, no authorization of a real caller, no tenant context and
no tenant isolation.

Input, a caller claim:
    name   required str; exact `str` only, so a `str` subclass cannot smuggle a different value
           through the set membership or the return.

Returns the name unchanged on success. It is not normalized, and here case is load-bearing rather
than a matter of taste: paragraph 1204 capitalises all nine entity names while paragraph 1206
lower-cases all six event names, so the sources draw the distinction themselves. Case-folding
would also admit tokens the TSD uses for other things entirely -- lower-case "tenant" occurs 638
times in it, as the `tenant.` event prefix and as an adjective in "tenant-scoped" and "tenant
context", "location" 77 times and "brand" 45. Folding would turn each of those into an
authoritative entity name.

Fail closed. A non-`str`, an over-long name and an unstated name are refused with distinct codes,
so a caller can tell a malformed input from a name outside the stated set.
"""

from __future__ import annotations

AUTHORITATIVE_ENTITIES = (
    "Tenant",
    "Organization",
    "LegalEntity",
    "Brand",
    "Region",
    "Location",
    "Department",
    "CostCenter",
    "TenantConfiguration",
)
# Not a claim about name length: the longest stated name is 19 characters. The bound refuses an
# unbounded input before the set lookup, and matches the sibling event-name module's bound.
MAX_ENTITY_NAME_LENGTH = 64

_AUTHORITATIVE = frozenset(AUTHORITATIVE_ENTITIES)
_MESSAGE = "invalid authoritative entity name"


class EntityNameError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


def validate_authoritative_entity(name: object) -> str:
    """Return `name` unchanged if the sources state it as an authoritative entity; else refuse."""
    if type(name) is not str:
        raise EntityNameError("bad_entity_name_type")
    if len(name) > MAX_ENTITY_NAME_LENGTH:
        raise EntityNameError("entity_name_too_long")
    if name not in _AUTHORITATIVE:
        raise EntityNameError("unstated_entity")
    return name

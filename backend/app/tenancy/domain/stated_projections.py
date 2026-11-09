"""MOD-004: whether the source states a read-model projection for an entity, as a pure decision.

TSD paragraph 1238's first clause states "List/detail and history projections for Tenant,
Organization, LegalEntity, Brand". Those four are the only entity names it carries. This module
answers whether that clause states a projection for a given name, and nothing else.

**The value is the answer it refuses to give.**
`knowledge/03-Modules/MOD-004/MOD-004.md` records "Read models: paragraph 1238 covers four of
nine entities" as a source gap, and its Search/read models row records the same as OPEN. The nine
authoritative entities of paragraph 1204 therefore include five -- Region, Location, Department,
CostCenter, TenantConfiguration -- for which no projection is stated anywhere in the pinned
sources. That last claim is a universal negative, so the measurement behind it is recorded here
rather than left for a reader to redo, and it was taken over the capitalised names rather than by
hunting for projection terms, because a term list can only ever be incomplete in one direction.
Of the 32 paragraphs carrying a capitalised `Region`, `Location`, `Department`, `CostCenter` or
`TenantConfiguration`, not one states a projection or read model. `Location` is the only one of
the five that shares a paragraph with such a term at all, and it is lower-case in every one: a
scope adjective in "location/time/state indexes", the event name "location.exception.detected",
and "the owning location/domain command". Its 18 capitalised occurrences are the entity lists,
eleven headings and module-title repetitions, ordinary prose such as "Location opening/closing
playbooks", and one scenario title, "Franchise Leader Reviews and Resolves a Location Exception".
That title is why capitalisation is not quite the whole distinction: a title-cased noun is no
more an entity reference than a lower-cased adjective is.
An author building a list view for one of those is pulled toward assuming a projection
exists because the other four have one. This module answers `NO_PROJECTION_STATED` for them,
which is the recorded gap rather than an invention, and is what the MOD-004 RLS Rule's
obligation 8 requires: unsupported read models are a gap to raise, not to fill.

**What `NO_PROJECTION_STATED` deliberately does not distinguish.** It does not say whether the
name is an authoritative entity. An entity of paragraph 1204 with no stated projection and a name
that is no entity at all both get that one outcome, because telling them apart needs paragraph
1204, which is a different closure over a different paragraph. A caller that needs both answers
calls both modules. Collapsing the two here would make this module assert something its own
paragraph does not state, which is the mistake the outcome's name exists to avoid.

Paragraph 1238 states list/detail and history jointly, and states neither alone for any entity,
so this module treats the pair as one stated thing and does not offer a list-detail-without-
history answer the source does not support.

Scope. Success means the clause names the entity. It is **not** a projection that exists, not a
query, not a read model, not a table, not a schema and not a migration. Paragraph 1238's further
requirements -- role- and surface-specific attention and summary read models, and that "every
projection exposes freshness/version metadata when asynchronously built" -- are outside this
module: the freshness rule is paragraph 1242's staleness decision, and the surface list is its
own closure. This module performs no I/O, keeps no state, logs nothing and echoes no raw input.
It establishes no authenticated principal, no authorization of a real caller, no tenant context
and no tenant isolation.

Input, a caller claim:
    name   required str; exact `str` only, so a `str` subclass cannot smuggle a different value
           through the set membership.

Returns one of `OUTCOMES`. The name is not normalized: paragraph 1238 spells these four exactly
as paragraph 1204 does, and case-folding would admit spellings the sources do not state.

Fail closed. A non-`str` and an over-long name are refused rather than answered, so a caller
cannot read a malformed input as an absent projection. An empty string is *answered*, not
refused, which diverges from the sibling event-name and entity-name closures on purpose: those
two return the name and have no outcome space, so refusing is their only way to say "not
stated", whereas here `NO_PROJECTION_STATED` is the precise answer for any well-formed `str` the
clause does not carry. Refusing it instead would need a minimum-length rule, which would be a
semantic claim about valid entity names that no pinned source makes.
"""

from __future__ import annotations

PROJECTED_ENTITIES = (
    "Tenant",
    "Organization",
    "LegalEntity",
    "Brand",
)
# Not a claim about name length, and not tied to any other module's bound: it refuses an
# unbounded input before the set lookup, which is the only operation here whose cost grows.
MAX_NAME_LENGTH = 64

PROJECTION_STATED = "projection_stated"
NO_PROJECTION_STATED = "no_projection_stated"
OUTCOMES = (PROJECTION_STATED, NO_PROJECTION_STATED)

_PROJECTED = frozenset(PROJECTED_ENTITIES)
_MESSAGE = "invalid projection lookup input"


class ProjectionLookupError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


def stated_projection(name: object) -> str:
    """Whether paragraph 1238's first clause states list/detail and history projections."""
    if type(name) is not str:
        raise ProjectionLookupError("bad_name_type")
    if len(name) > MAX_NAME_LENGTH:
        raise ProjectionLookupError("name_too_long")
    if name in _PROJECTED:
        return PROJECTION_STATED
    return NO_PROJECTION_STATED

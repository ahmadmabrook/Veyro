"""MOD-004 PLT-01-R02: whether a proposed hierarchy link stays inside one tenant.

TSD paragraph 1223 states the requirement: "Model organization, legal entity, brand, region,
location, department and cost-center hierarchies." Seven node kinds. Paragraph 1230 states the
critical control the link must not break: "No cross-tenant query, cache, file, event or search
result is permitted." Paragraph 1237 carries one command that edits the shape, `ChangeOrgHierarchy`.
This module decides whether a proposed parent/child link is admissible on the two grounds the
sources state -- both ends are hierarchy node kinds, and both ends sit in the same tenant -- and it
decides nothing else.

**It deliberately does not decide the hierarchy's shape, and that refusal is the point.**
`knowledge/03-Modules/MOD-004/MOD-004.md` records under PLT-01-R02 that "Cardinalities
owner-reserved if the Blueprint is silent" and that paragraph 1237 carries "no maintenance command
for LegalEntity, Department, CostCenter or TenantConfiguration". So which kind may parent which,
how deep a branch may run, and whether a kind may repeat on a path are **owner-reserved and
unstated**. A plausible table -- Organization parents Brand, Brand parents Location, Location
parents Department -- is exactly the invention the MOD-004 RLS Rule's obligation 8 bars, and this
module therefore returns `shape_decided=False` on every admitted link so a caller cannot mistake
containment for shape. A caller that needs the shape is reading an owner-reserved gap.

Two of the nine authoritative entities of paragraph 1204 are absent from paragraph 1223's seven and
are refused as node kinds, **on that ground alone**: `Tenant` and `TenantConfiguration` are not
among the seven kinds paragraph 1223 names. No stronger mechanism is claimed for either. In
particular, admitting the kind `Tenant` would not make the containment test a tautology -- the
comparison below reads only the two tenant ids and never the kinds, so a `Tenant`/`Tenant` link
would be compared exactly as a `Brand`/`Brand` link is. Both refusals carry their own code, so a
caller can tell a stated entity used in the wrong place from an unknown token.

Scope. Success means the link is inside one tenant between two stated node kinds. It is **not**
authorization to make the link, not the `ChangeOrgHierarchy` command, not tenant isolation, not a
foreign key, not a uniqueness constraint and not a cycle check over a stored graph. **Isolation is
enforced by PostgreSQL row-level security, which this lane cannot write**: comparing two tenant ids
a caller supplied is a comparison of two caller claims, and a caller that supplies the same wrong id
twice gets an admissible link. The module performs no I/O, keeps no state, logs nothing and echoes
no raw input. It establishes no authenticated principal and no tenant context.

Inputs, all four caller claims:
    child_kind, parent_kind            required str; exact `str` only, so a `str` subclass cannot
                                       smuggle a different value through the membership test.
    child_tenant_id, parent_tenant_id  required str in the RFC 4122 hyphenated form, then compared
                                       for equality.

**The identifier shape is the project's, not this paragraph's.** Paragraph 1223 and paragraph 1230
impose no format for this decision, but the pinned baseline is not silent: TSD section 9.3 (Physical
Persistence Contract) states "All mutable aggregate roots carry id UUIDv7, tenant_id, version
BIGINT, created_at, updated_at", and the MOD-004 RLS Rule's rule 3 requires "`tenant_id UUID NOT
NULL`" with the policy casting `current_setting('app.tenant_id', true)::uuid`, while rule 1 says to
"Refuse autocommit and non-UUID values". Accepting an arbitrary bounded token here would set
validation below the project's own standard at the one boundary this module exists to guard, so the
`_UUID` predicate is duplicated from `command_envelope`/`provision_idempotency` rather than relaxed.
It is duplicated rather than imported for the reason those two give: a cross-module
underscore-private import couples two slices, and the lane favours small independent files.
Duplicating a predicate
duplicates the obligation to test it. The version and variant nibbles are constrained, so the nil
UUID is refused; UUIDv7 specifically is **not** required here, because nothing in paragraph 1223 or
paragraph 1230 makes a version the condition of containment.

**Because the tokens are interpreted as UUIDs, they are compared as UUIDs.** RFC 4122 hex is
case-insensitive, so `0191F1C2-...` and `0191f1c2-...` are one tenant; comparing them byte-exactly
would return `cross_tenant_link` for a single tenant, which is a false positive on the one
security-labelled verdict this module produces. The comparison therefore case-folds both ends, as
`command_envelope` and `tenancy_s0` do on their accept paths. A module that validates a version
nibble cannot also treat the token as an opaque byte string. `command_envelope` records why the
exact-type test must precede `.lower()` -- an overridden `lower()` on a `str` subclass would
otherwise choose the compared content -- and the `type(...) is str` tests below sit first for that
reason. Here the folded value is used only for the comparison and is never returned, so nothing a
`lower()` override produced could reach the result.

Fail closed. A malformed kind token, a stated entity outside the seven, an unknown kind, a
non-UUID tenant id and a link whose ends sit in different tenants are refused with distinct codes.
A non-`str` and an over-long token share one code per input, because both mean the same thing to a
caller: the token never entered the vocabulary.

**Self-parenting is not refused, because this module cannot see it.** The inputs are kinds and
tenant ids, never node identities, so `Brand` under `Brand` is admitted -- and whether a kind may
repeat on a path is a shape question, which is owner-reserved and refused above. A caller holding
node identities must make that check itself; a test pins the admission so the limit is not mistaken
for an oversight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN_MAX = 64
TENANT_ID_LENGTH = 36

# Duplicated from `command_envelope` / `provision_idempotency` by choice; see the module docstring.
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
    re.ASCII,
)

# Paragraph 1223's seven node kinds, spelled as paragraph 1204 spells the entities.
ORGANIZATION = "Organization"
LEGAL_ENTITY = "LegalEntity"
BRAND = "Brand"
REGION = "Region"
LOCATION = "Location"
DEPARTMENT = "Department"
COST_CENTER = "CostCenter"
HIERARCHY_KINDS = (
    ORGANIZATION,
    LEGAL_ENTITY,
    BRAND,
    REGION,
    LOCATION,
    DEPARTMENT,
    COST_CENTER,
)

# Stated by paragraph 1204 as authoritative entities, absent from paragraph 1223's seven. Named so
# the refusal reports a stated entity in the wrong place rather than an unknown token.
NON_HIERARCHY_ENTITIES = ("Tenant", "TenantConfiguration")

_MESSAGE = "invalid hierarchy link inputs"


class ContainmentError(ValueError):
    """Generic refusal; never carries raw input, and in particular never a tenant id.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class AdmissibleLink:
    """An admitted link. `shape_decided` is always False and says so to the caller."""

    child_kind: str
    parent_kind: str
    shape_decided: bool


def link_is_admissible(
    child_kind: object,
    child_tenant_id: object,
    parent_kind: object,
    parent_tenant_id: object,
) -> AdmissibleLink:
    """Decide whether a proposed parent/child link stays inside one tenant. A decision only.

    The type tests are written inline rather than behind shared helpers: a helper returning `bool`
    does not narrow `object` to `str` for the type checker, and `typing.TypeGuard` is not reachable
    -- the lane's allowed-import closure is `__future__`, `dataclasses`, `enum` and `re`.
    `authoritative_entities` inlines the same test for the same reason. Both kinds are judged before
    either tenant id so that one malformed input reports one unambiguous code.
    """
    if type(child_kind) is not str or not 0 < len(child_kind) <= TOKEN_MAX:
        raise ContainmentError("bad_child_kind")
    if child_kind in NON_HIERARCHY_ENTITIES:
        raise ContainmentError("child_kind_not_a_hierarchy_node")
    if child_kind not in HIERARCHY_KINDS:
        raise ContainmentError("unknown_child_kind")

    if type(parent_kind) is not str or not 0 < len(parent_kind) <= TOKEN_MAX:
        raise ContainmentError("bad_parent_kind")
    if parent_kind in NON_HIERARCHY_ENTITIES:
        raise ContainmentError("parent_kind_not_a_hierarchy_node")
    if parent_kind not in HIERARCHY_KINDS:
        raise ContainmentError("unknown_parent_kind")

    if (
        type(child_tenant_id) is not str
        or len(child_tenant_id) != TENANT_ID_LENGTH
        or _UUID.fullmatch(child_tenant_id) is None
    ):
        raise ContainmentError("bad_child_tenant_id")
    if (
        type(parent_tenant_id) is not str
        or len(parent_tenant_id) != TENANT_ID_LENGTH
        or _UUID.fullmatch(parent_tenant_id) is None
    ):
        raise ContainmentError("bad_parent_tenant_id")
    if child_tenant_id.lower() != parent_tenant_id.lower():
        raise ContainmentError("cross_tenant_link")
    return AdmissibleLink(
        child_kind=child_kind,
        parent_kind=parent_kind,
        shape_decided=False,
    )

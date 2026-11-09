"""MOD-004: the primary-surface name closure, as a pure decision.

TSD paragraph 1199 labels the row "Primary surfaces" and paragraph 1200 states three:
"Internal SaaS Console; Admin Web; APIs". Paragraph 1238 repeats the same three, in the same
order, for its "role/surface-specific attention/summary read models". This module admits exactly
those three and refuses every other name. Paragraph 1245 also mentions APIs, in "contract tests
for APIs/events", but that is a test obligation rather than a surface enumeration and is not a
third statement of the set.

**The guard's value is the names it refuses**, and surface attribution is the one place in this
module where `knowledge/03-Modules/MOD-004/MOD-004.md` records inference rather than source. Its
screen-ownership mapping is labelled "engineering decision; unreviewed, not an owner decision,
not Ready", it carries ten explicit `[INFERENCE]` markers, and it names only Internal SaaS
Console and Admin Web for MOD-004's own screens. Meanwhile the product's other surfaces are heavy
vocabulary elsewhere in the TSD and absent from this module's block entirely: Member App occurs
49 times in the document, POS 47, Front Desk 44, Coach App 30, Kiosk 21, and each occurs zero
times in paragraphs 1194-1245. So an author mapping a screen is pulled toward a surface the
sources never give this module, and refusing is what the MOD-004 RLS Rule's obligation 8
requires: an unstated surface is a gap to raise, not to fill.

Scope. Success means the name is one of the three the sources state as this module's primary
surfaces. It is **not** a screen, not a screen identifier, not a route, not an owning module, not
a permission, not a read model and not a judgment about whether a surface is a "card surface" --
that last is an inference MOD-004.md marks as such, and this module does not make it. Deciding a
name is also not deciding that MOD-004 owns any particular screen on that surface, which
MOD-004.md leaves to an unreviewed mapping and to `contracts/ui/screen-contracts.yaml`, whose
every contract field is null. This module performs no I/O, keeps no state, logs nothing and
echoes no raw input. It establishes no authenticated principal, no authorization of a real
caller, no tenant context and no tenant isolation.

Input, a caller claim:
    name   required str; exact `str` only, so a `str` subclass cannot smuggle a different value
           through the set membership or the return.

Returns the name unchanged on success. It is not normalized. Case and internal spacing are both
load-bearing here in a way they are not for a single-word name: the sources spell these as
"Internal SaaS Console" with that exact capitalisation, including the acronym `SaaS`, and as
"APIs" rather than "API" or "Apis". Folding case or collapsing whitespace would admit spellings
the sources do not state, and "API" singular is not a stated surface name.

Fail closed. A non-`str`, an over-long name and an unstated name are refused with distinct codes,
so a caller can tell a malformed input from a name outside the stated set.
"""

from __future__ import annotations

PRIMARY_SURFACES = (
    "Internal SaaS Console",
    "Admin Web",
    "APIs",
)
# Not a claim about name length: the longest stated name is 21 characters. The bound refuses an
# unbounded input before the set lookup, which is the only operation here whose cost grows.
MAX_SURFACE_NAME_LENGTH = 64

_PRIMARY = frozenset(PRIMARY_SURFACES)
_MESSAGE = "invalid primary surface name"


class SurfaceNameError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


def validate_primary_surface(name: object) -> str:
    """Return `name` unchanged if the sources state it as a primary surface; else refuse."""
    if type(name) is not str:
        raise SurfaceNameError("bad_surface_name_type")
    if len(name) > MAX_SURFACE_NAME_LENGTH:
        raise SurfaceNameError("surface_name_too_long")
    if name not in _PRIMARY:
        raise SurfaceNameError("unstated_surface")
    return name

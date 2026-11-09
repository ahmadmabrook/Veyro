"""MOD-004: the release-gate isolation-layer name closure, as a pure decision.

TSD paragraph 741 opens "7.3 Data Isolation Model" and paragraphs 749-751 head a table with
"Layer", "Isolation Mechanism" and "Release Gate". Its Layer column states seven: PostgreSQL at
paragraph 752, Cache at 755, Search at 758, Object storage at 761, Events/jobs at 764, Telemetry
at 767 and AI at 770, one row every three paragraphs, ending before paragraph 774's "7.4 Shared
vs Dedicated Enterprise Isolation". This module admits exactly those seven names and refuses
every other.

**Admitting a name here says nothing whatever about the layer.** This is the strongest form of a
limit every slice in this lane carries, and it needs saying plainly because the subject is
tenant isolation. Returning "Cache" means paragraph 755 lists Cache in that column. It does not
mean cache isolation exists, is designed, is implemented, is mapped, is tested, is evidenced or
has passed its release gate. The MOD-004 RLS Rule's rule 7 is explicit about which of the seven
are which: "Only the PostgreSQL layer is mapped in S1; the other layers are OPEN, so do not build
or claim them from this rule." `knowledge/03-Modules/MOD-004/MOD-004.md` carries a status column
for the same seven rows and records the other six as OPEN, each with its own reason -- for Cache,
that no cache platform exists.

**And "mapped" is not "evidenced", including for PostgreSQL.** Quoting six of that table's seven
statuses and not the seventh would leave the one layer rule 7 calls mapped looking better than
the record says, so the seventh is here too: MOD-004.md qualifies that row "mapped (S1 proposal
only); no code, no test, not accepted", and adds that "the capability manifest (EIP ¶754) remains
OPEN" -- quoted with its own pilcrow, since altering it to this file's usual "paragraph 754"
would be editing a quotation. So none of the seven is evidenced, and rule 7's distinction is
between mapped and OPEN rather than between done and not done. Nothing here changes any of that,
and a caller treating a success as evidence about a layer has inverted the module's purpose.

**The likeliest wrong name is in MOD-004.md, not in the sources.** That file's own release-gate
table labels its rows PostgreSQL/RLS, Cache keys, Search/read models, Object storage,
Events/jobs/queues, Telemetry/log correlation and AI/retrieval context. Six of those seven are
not the TSD's spelling -- only Object storage matches -- and none of the six occurs anywhere in
the pinned TSD. They are that document's own descriptive expansions, cited against the TSD
paragraph numbers for the mechanisms rather than quoted from the Layer column, so they are not
wrong there; they are simply not what this closure is over. An author looking the layer names up
in the module's own document therefore finds six names the sources never use.

Scope. Success means the name is one the sources state in that Layer column. It is **not** a
layer, not an isolation mechanism, not a release gate, not a gate result, not a test, not a
platform and not evidence for or about any of them. This module performs no I/O, keeps no state,
logs nothing and echoes no raw input. It establishes no authenticated principal, no authorization
of a real caller, no tenant context and no tenant isolation -- and in this slice, unlike the
others, that last clause is the subject matter rather than a boilerplate denial.

Input, a caller claim:
    name   required str; exact `str` only, so a `str` subclass cannot smuggle a different value
           through the set membership or the return.

Returns the name unchanged on success. It is not normalized. Two of the seven contain a solidus
or a space that a caller might rewrite, and the sources' capitalisation is irregular in a way no
rule can be inferred from: "PostgreSQL" carries internal capitals, "AI" is an acronym, "Object
storage" capitalises only its first word. Folding or rewriting any of that would admit spellings
the sources do not state.

Unlike the relocation-stage and role-attribute closures, these seven are not one sentence, so no
single round-trip assertion can pin them. The pin is the literal tuple, with the table's layout
recorded above so a reader can locate every row.

Fail closed. A non-`str`, an over-long name and an unstated name are refused with distinct codes,
so a caller can tell a malformed input from a name outside the stated set.
"""

from __future__ import annotations

ISOLATION_LAYERS = (
    "PostgreSQL",
    "Cache",
    "Search",
    "Object storage",
    "Events/jobs",
    "Telemetry",
    "AI",
)
# Not a claim about name length: the longest stated name is 14 characters. The bound refuses an
# unbounded input before the set lookup, which is the only operation here whose cost grows.
MAX_LAYER_NAME_LENGTH = 64

_LAYERS = frozenset(ISOLATION_LAYERS)
_MESSAGE = "invalid isolation layer name"


class LayerNameError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


def stated_isolation_layer(name: object) -> str:
    """Return `name` unchanged if the Layer column states it; else refuse.

    Named `stated_` rather than `validate_`, following the same reasoning as the role-attribute
    closure: a `validate_isolation_layer` would read as "this isolation layer has been
    validated", which for this subject is the most misleading thing the function could be called.
    """
    if type(name) is not str:
        raise LayerNameError("bad_layer_name_type")
    if len(name) > MAX_LAYER_NAME_LENGTH:
        raise LayerNameError("layer_name_too_long")
    if name not in _LAYERS:
        raise LayerNameError("unstated_layer")
    return name

"""MOD-004: whether TSD paragraph 779's write-freeze target is met, as a pure decision.

TSD paragraph 779, pinned baseline text, all three sentences: "Target for standard tenants is <15
minutes write freeze after pre-copy. Large/dedicated tenants use an agreed maintenance window.
Rollback before source deletion switches routing back only after target writes are reconciled or
discarded." This module reads the first two sentences. The third is a different rule about
rollback ordering and is **not** implemented here.

Every citation in this file carries an explicit `TSD` prefix, and TSD paragraph 779 is the reason
the convention exists rather than an instance of it. Both pinned baselines number paragraphs through
741-783 and there the two texts are unrelated: **EIP** paragraph 779 opens the scenario-category
supplement that `knowledge/03-Modules/MOD-004/MOD-004.md` cites as "EIP ¶779-857" for application
and session lifecycle, while **TSD** paragraph 779 is this write-freeze target. A bare "paragraph
779" would therefore name two different rules, which is the defect
`tools/module_docs/cite_check.py` exists to catch -- though it reads a module document rather than
a Python source, so nothing automated holds this file to the convention. The surrounding rows are
given too, since the number alone does not survive a renumbering: TSD paragraph 775 heads "7.5
Tenant Placement and Relocation Workflow", TSD paragraph 777 lists the twelve relocation stages
and TSD paragraph 778 states the relocation_epoch rule.

This module answers one question: for the tenant class and the write-freeze figure handed in, does
TSD paragraph 779's stated target hold?

**For a large or dedicated tenant it refuses to answer, and that is the whole point of the second
outcome.** TSD paragraph 779 states no figure for that class -- it states an "agreed maintenance
window" -- and `MOD-004.md` lists "dedicated-tenant maintenance window (R02, R04, R06; TSD
¶779-781)" as item 3 under "Unresolved owner-reserved choices (not decided here)", to be resolved
"from the Blueprint first, otherwise the owner decides". So no window exists to compare against,
and supplying one would be both an invention under the MOD-004 RLS Rule's obligation 8 and an
owner-reserved choice taken by an agent. `NO_STATED_TARGET` is the only answer available, and it
is returned for every freeze figure, including a figure under fifteen minutes.

**The class is a caller claim this module cannot check.** No pinned source states how a tenant
becomes standard or large/dedicated: `MOD-004.md` lists "plan tiers and dedicated-placement
eligibility" in the same owner-reserved item 3. TSD paragraph 782 is adjacent and worth reading
beside it -- "Domain code never assumes whether the tenant is shared or dedicated" -- which is
consistent with taking the class as an input rather than deriving one, and is also why this module
derives nothing from it beyond which sentence of TSD paragraph 779 applies.

**Why the class is an enum and not a name closure.** The lane's six existing name closures admit
the sources' exact spellings, which works because the sources spell those names in a fixed list or
table position. TSD paragraph 779 does not: "standard" appears mid-sentence in lower case while
"Large/dedicated" is sentence-initial, so its capital is positional and there is no stated
canonical spelling to admit. A string closure would have to invent one. `TenantClass` names the
two classes the source states and nothing else: there is deliberately **no third member**, because
the source names no third class, and a caller whose tenant fits neither has a source gap to raise
rather than a value to pass.

**Fifteen minutes exactly is beyond the target.** The source writes "<15 minutes", not "<=15", so
the comparison is strict and the boundary falls outside. This is the one place where a reader's
intuition and the stated text can part, so it is pinned by its own test.

**Minutes only, and no rounding.** The unit is the source's: "15 minutes". No sub-minute precision
is stated, so `minutes` is a whole number of minutes and a caller holding seconds must convert
before calling. The reason this module will not convert for them is that the source states no
rounding rule and the choice is not neutral: flooring happens to be verdict-preserving, since
`floor(x) < 15` exactly when `x < 15`, but rounding to nearest turns a freeze of 14.6 minutes --
under the target as stated -- into a 15 that is beyond it. An earlier revision of this paragraph
offered flooring as the reason and was wrong about which way it cuts; a review falsified it by
execution, and the claim is corrected here rather than dropped.

Scope. The result is a reading of two caller claims against one stated sentence. It is **not** a
measurement of any write freeze, not a relocation, not a relocation stage, not a placement
resolution, not a service-level objective, and not authority to freeze writes, to cut over or to
proceed with any stage of TSD paragraph 777. A `WITHIN_TARGET` result says the figure handed in is
under the stated target and nothing else; the relocation workflow itself is undesigned, which
`MOD-004.md` records as "no owner or design exists for provisioning and relocation workflows".
This module performs no I/O, keeps no state, logs nothing and echoes no raw input. It establishes
no authenticated principal, no authorization of a real caller, no tenant context and no tenant
isolation.

Three outcomes, one of `OUTCOMES`:
    WITHIN_TARGET      the tenant is standard and the freeze is strictly under
                       `STANDARD_TARGET_MINUTES`.
    BEYOND_TARGET      the tenant is standard and the freeze is at or over that figure. The
                       stated target does not hold.
    NO_STATED_TARGET   the tenant is large/dedicated, so the source states no figure and this
                       module compares nothing. Not a finding that the freeze is acceptable.

Inputs, both caller claims:
    tenant_class   required `TenantClass` member; exact type only, so no subclass and no bare
                   string reaches the comparison.
    minutes        required int in 0..MINUTES_MAX inclusive, whole minutes. Exact `int` only, so
                   `bool` is refused. Zero is admitted: the source states an upper target and no
                   lower bound, so a zero-minute claim is under the target as written, and reading
                   anything further into it would be invention.

Fail closed. Both shapes are validated before any comparison and before the class is read, so a
malformed figure is refused even for the class that compares nothing. Each refusal carries a
distinct `code`, so a caller can tell a malformed class from a malformed figure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# The stated figure, in minutes, from TSD paragraph 779's first sentence. The comparison against
# it is strict; the name says "target" rather than "limit" or "maximum" because the source says
# "Target".
STANDARD_TARGET_MINUTES = 15
MINUTES_MAX = 2**31 - 1

WITHIN_TARGET = "within_target"
BEYOND_TARGET = "beyond_target"
NO_STATED_TARGET = "no_stated_target"
OUTCOMES = (WITHIN_TARGET, BEYOND_TARGET, NO_STATED_TARGET)

_MESSAGE = "invalid write freeze target inputs"


class TenantClass(Enum):
    """The two tenant classes TSD paragraph 779 states, and no others.

    The member values are lower-case identifiers chosen for this module; they are not quotations
    and no source states a canonical spelling, which is the reason this is an enum at all.
    """

    STANDARD = "standard"
    LARGE_DEDICATED = "large_dedicated"


class WriteFreezeError(ValueError):
    """Generic refusal; never carries raw input.

    `args` is set directly rather than through `super().__init__(...)`: the lane's closure check
    refuses every dunder attribute access except `__doc__` and `__name__`.
    """

    def __init__(self, code: str) -> None:
        self.args = (_MESSAGE,)
        self.code = code


@dataclass(frozen=True, slots=True)
class WriteFreezeDecision:
    """Immutable decision.

    `target_exceeded` is true only for `BEYOND_TARGET`. It is false for `NO_STATED_TARGET` because
    no stated figure was exceeded there, which is not the same as the freeze being acceptable --
    read `outcome`, not this flag, to tell those two cases apart.
    """

    outcome: str
    target_exceeded: bool


def _minutes_or_refuse(value: object) -> int:
    """Return `value` as whole minutes, or refuse.

    The leading `isinstance` is what lets a type checker carry the narrowing out of this function,
    so the caller can compare the returned value with `<`; the `type(value) is not int` beside it
    is what refuses `bool` and every other `int` subclass, so no comparison downstream can reach a
    subclass's operators. Slice 4 learned this the hard way.
    """
    if not isinstance(value, int) or type(value) is not int:
        raise WriteFreezeError("bad_minutes")
    if not 0 <= value <= MINUTES_MAX:
        raise WriteFreezeError("bad_minutes")
    return value


def evaluate_write_freeze_target(
    tenant_class: object,
    minutes: object,
) -> WriteFreezeDecision:
    """Decide whether TSD paragraph 779's write-freeze target holds for these two claims."""
    if type(tenant_class) is not TenantClass:
        raise WriteFreezeError("bad_tenant_class")
    freeze = _minutes_or_refuse(minutes)

    if tenant_class is TenantClass.LARGE_DEDICATED:
        return WriteFreezeDecision(outcome=NO_STATED_TARGET, target_exceeded=False)
    if freeze < STANDARD_TARGET_MINUTES:
        return WriteFreezeDecision(outcome=WITHIN_TARGET, target_exceeded=False)
    return WriteFreezeDecision(outcome=BEYOND_TARGET, target_exceeded=True)

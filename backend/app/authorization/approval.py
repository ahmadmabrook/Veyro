"""MOD-008 IAM-03-R05: approval policies, and the separation of duties that makes them mean
something.

Pure functions over rows the caller has read.

An approval requirement that the requester can satisfy is not an approval requirement, so
separation of duties is enforced here rather than left to the surface. The database carries the
other half -- `UNIQUE (tenant_id, request_id, decided_by)` -- so "two approvals" cannot be one
person pressing a button twice even if this module were bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
EXPIRED = "expired"
WITHDRAWN = "withdrawn"


class ApprovalError(ValueError):
    """A decision that cannot be recorded. `code` is stable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


#: The ceiling the schema carries, stated here so a decision function and a CHECK cannot
#: disagree about it. Eight is more stages than any approval anybody describes.
MAX_STAGES = 8


@dataclass(frozen=True)
class Stage:
    """One step of an approval: N holders of one permission.

    **Keyed by the permission, which is what makes the combination rule survive.** `policy_for`
    combines every applicable policy and never chooses between them, because a single column
    naming one permission had to pick by row order when two policies applied at the same
    strictness. A stage *list* has that problem one level up -- concatenating two policies'
    stages is order-dependent, the exact dependence combining was built to remove. Keyed by
    permission it is not: the count is the most any policy asks for, and the ordinal the
    highest any gives it.
    """

    ordinal: int
    required_permission: str
    required_approvals: int = 1


@dataclass(frozen=True)
class ApprovalPolicy:
    action: str
    threshold_minor: int = 0
    required_permissions: frozenset[str] = frozenset()
    """**All** of them, not one of them. A single column had to choose between two policies
    naming different permissions at the same strictness, and every rule for choosing -- row
    order, or a sort -- is arbitrary and weaker than one of the two policies."""
    required_approvals: int = 1
    separation_of_duties: bool = True
    stages: tuple[Stage, ...] = ()
    """**Empty is a single-stage policy**, whose stage is this policy's own permission and
    count. That is the existing meaning rather than a state to migrate, which is why the
    migration backfills no rows and nothing already written changes behaviour."""
    sequential: bool = False
    """Whether the stages must be satisfied in order. On the policy rather than on each stage,
    because R05 names sequential and parallel as properties of an approval -- a per-stage flag
    would admit "stage 2 is sequential and stage 3 is not", which is not a thing anybody
    means."""


@dataclass(frozen=True)
class Decision:
    decided_by: str
    decision: str
    stage_ordinal: int = 1
    """**Defaulted, because a single-stage request's one stage is ordinal 1.** Every decision
    recorded before stages existed means exactly that, which is why the column defaults to it
    in the schema as well."""


def policy_for(
    policies: list[ApprovalPolicy], action: str, amount_minor: int | None
) -> ApprovalPolicy | None:
    """The terms that apply: the **strictest of every applicable policy**, combined.

    Thresholds overlap on purpose -- refunds over 100 need one approval, over 10000 need two --
    so every policy the amount clears applies, and what governs is the hardest requirement among
    them: the most approvals any of them asks for, and separation of duties if any of them
    demands it.

    An earlier version took the policy with the highest threshold, which a docstring called "the
    strictest". Those are the same only until somebody writes a lenient policy above a strict one
    -- a review demonstrated a `threshold_minor = 1` policy with one approval and no separation of
    duties silently governing a million-unit refund that a `threshold_minor = 0` policy had
    required two signatures for. Combining rather than choosing removes the possibility instead
    of relying on nobody writing that row.
    """
    amount = amount_minor or 0
    applicable = [p for p in policies if p.action == action and amount >= p.threshold_minor]
    if not applicable:
        return None
    # **Staged if anybody declared stages, and not otherwise.** The first version collapsed a
    # one-stage combination to nothing so the response and the snapshot would agree -- and that
    # silently lost a count, because a policy whose single stage asks for two approvers has
    # `required_approvals = 1` on its own row. "Did anybody declare stages" is the question
    # that keeps both true, and a plain policy in the mix still contributes its own stage.
    combined = combine_stages(applicable) if any(p.stages for p in applicable) else ()
    return ApprovalPolicy(
        action=action,
        threshold_minor=max(p.threshold_minor for p in applicable),
        # The union, so the result does not depend on which policy happened to come first. An
        # earlier version took this field from whichever policy had the most approvals, which on
        # a tie meant row order -- the exact dependence combining was meant to remove, surviving
        # in one field.
        required_permissions=frozenset().union(*(p.required_permissions for p in applicable)),
        required_approvals=max(p.required_approvals for p in applicable),
        separation_of_duties=any(p.separation_of_duties for p in applicable),
        stages=combined,
        # `any()`, like separation of duties: a policy that demands an order governs, because
        # the alternative is a lenient policy quietly switching off a strict one's sequencing.
        sequential=any(p.sequential for p in applicable),
    )


def stages_of(policy: ApprovalPolicy) -> tuple[Stage, ...]:
    """A policy's stages, with the single-stage case made explicit.

    **The absence is the existing meaning**, so every caller sees a list rather than branching
    on emptiness -- which is how a second definition of "how many approvals does this need"
    gets written.
    """
    if policy.stages:
        return tuple(sorted(policy.stages, key=lambda stage: stage.ordinal))
    permission = next(iter(sorted(policy.required_permissions)), None)
    if permission is None:
        return ()
    return (Stage(ordinal=1, required_permission=permission,
                  required_approvals=policy.required_approvals),)


def combine_stages(policies: list[ApprovalPolicy]) -> tuple[Stage, ...]:
    """The stages of several applicable policies, keyed by permission.

    **Order-independent by construction**, which is the whole reason a stage is a permission
    and a count rather than a position in a list: for each distinct permission the count is the
    most any policy asks for and the ordinal is the highest any gives it, and the result is
    then renumbered 1..N in ordinal order. Concatenating two policies' stage lists would
    reintroduce the row-order dependence `policy_for` exists to remove.

    **A policy with no stages contributes its own single stage**, so a staged policy and a
    plain one combine without a special case -- and a plain policy whose permission is already
    a stage of another simply raises that stage's count where it asks for more.

    **The order is a topological sort of every policy's own order, not the highest ordinal
    anybody gave each permission.** Taking the max was the first version and it is arbitrary
    on a case no pairwise check sees: three policies ordering A before B, B before C and C
    before A each agree with the others on their one shared permission, and the maxima then
    come out equal so the result falls back to the alphabet -- a policy's stated order
    silently violated, which is the row-order dependence this function exists to remove
    wearing a different hat. Found by working through the cycle rather than by a test, which
    is why `order_conflict` refuses it at the policy write as well.

    Deterministic: ties among the ready set are broken by permission name, so the answer does
    not depend on which policy came first.

    A cycle is unorderable and this does not try. `order_conflict` refuses it where the policy
    is written -- MOD-012's succession rule, because catching it at the moment somebody needs
    an approval is catching it too late to do anything about -- and the fallback here is the
    ordinal-then-name sort, which is at least stable.
    """
    counts: dict[str, int] = {}
    for policy in policies:
        for stage in stages_of(policy):
            counts[stage.required_permission] = max(
                counts.get(stage.required_permission, 0), stage.required_approvals)
    if not counts:
        return ()
    ordered = _topological(list(policies), counts)
    return tuple(
        Stage(ordinal=index, required_permission=permission,
              required_approvals=counts[permission])
        for index, permission in enumerate(ordered, start=1))


def _edges(policies: list[ApprovalPolicy]) -> set[tuple[str, str]]:
    """Every "this permission comes before that one" any of these policies states.

    Each policy's own stages are totally ordered -- one permission per ordinal within a policy,
    which the schema's primary key and unique rule together enforce -- so every pair of its
    stages is an edge.
    """
    out: set[tuple[str, str]] = set()
    for policy in policies:
        stages = stages_of(policy)
        for left in stages:
            for right in stages:
                if left.ordinal < right.ordinal:
                    out.add((left.required_permission, right.required_permission))
    return out


def order_conflict(policies: list[ApprovalPolicy]) -> tuple[str, ...] | None:
    """The permissions these policies cannot agree an order for, or None if they can.

    **One cycle check and nothing else.** An earlier version looked first for a pair ordered
    both ways and then for a cycle -- and the mutation sweep reported the pair check as
    uncaught, correctly: a pair ordered both ways *is* a two-cycle, so the second check already
    answers it. Deleted rather than tested harder, which is the judgement this repository makes
    for a constraint a sibling already names.

    **Pairwise is not enough**, which is why it is a cycle check at all: A before B, B before C
    and C before A is three policies that agree with each other on every *pair* they share and
    cannot be satisfied together. The maxima then come out equal and the combination falls back
    to the alphabet, so a policy's stated order would be silently dropped.
    """
    edges = _edges(policies)
    nodes = {node for edge in edges for node in edge}
    placed = set(_order(edges, nodes))
    unplaceable = tuple(sorted(nodes - placed))
    return unplaceable or None


def _topological(policies: list[ApprovalPolicy], counts: dict[str, int]) -> list[str]:
    edges = _edges(policies)
    nodes = set(counts)
    ordered = _order(edges, nodes)
    if len(ordered) == len(nodes):
        return ordered
    # Unorderable, which `order_conflict` refuses at the write. Stable rather than clever.
    placed = {permission: index for index, permission in enumerate(ordered)}
    return ordered + sorted(node for node in nodes if node not in placed)


def _order(edges: set[tuple[str, str]], nodes: set[str]) -> list[str]:
    """Kahn's algorithm with a sorted ready set, so the answer is deterministic."""
    incoming = {node: 0 for node in nodes}
    after: dict[str, list[str]] = {node: [] for node in nodes}
    for left, right in edges:
        if left not in nodes or right not in nodes:
            continue
        incoming[right] += 1
        after[left].append(right)
    ready = sorted(node for node in nodes if incoming[node] == 0)
    out: list[str] = []
    while ready:
        node = ready.pop(0)
        out.append(node)
        for next_node in sorted(after[node]):
            incoming[next_node] -= 1
            if incoming[next_node] == 0:
                ready.append(next_node)
                ready.sort()
    return out


def requires_approval(
    policies: list[ApprovalPolicy], action: str, amount_minor: int | None
) -> bool:
    return policy_for(policies, action, amount_minor) is not None


def check_stage(
    stages: tuple[Stage, ...], *, stage_ordinal: int, decisions: list[Decision],
    sequential: bool, decider_permissions: frozenset[str],
) -> None:
    """Whether this stage may be decided now, and by this person. Raises rather than returning.

    Three refusals, and the third is the only one `sequential` adds:

    - **The stage has to exist.** A single-stage request has no stage rows at all, so ordinal 1
      is the one admissible absence and every other ordinal is a decision about nothing.
    - **The decider holds that stage's own permission**, which is what makes a stage a *kind*
      of approver rather than one more body. `check_decider` still charges every permission the
      combined policies name; this charges the one this step is for.
    - **A sequential stage is open only when every earlier one has its count.** Parallel
      requests skip it, which is the whole difference between the two words R05 names.

    The schema refuses all three as well, because this build's premise is that the schema is
    the half that holds when the service is wrong -- and the service is where the caller gets a
    sentence instead of a constraint name.
    """
    if not stages:
        if stage_ordinal != 1:
            raise ApprovalError(
                "no_such_stage",
                "this request has one stage, so a decision on another is about nothing")
        return
    here = next((s for s in stages if s.ordinal == stage_ordinal), None)
    if here is None:
        raise ApprovalError("no_such_stage", f"this request has no stage {stage_ordinal}")
    if here.required_permission not in decider_permissions:
        raise ApprovalError(
            "decider_lacks_stage_permission",
            "the decider does not hold the permission this stage is for")
    if not sequential:
        return
    for earlier in stages:
        if earlier.ordinal >= stage_ordinal:
            continue
        if stage_approvals(decisions, earlier.ordinal) < earlier.required_approvals:
            raise ApprovalError(
                "stage_not_open",
                f"stage {stage_ordinal} is not open: stage {earlier.ordinal} has not been "
                "approved, and this approval is sequential")


def stage_approvals(decisions: list[Decision], ordinal: int) -> int:
    """How many distinct people have approved this stage.

    Distinct, because `UNIQUE (tenant_id, request_id, decided_by)` already makes one decision
    per person per *request* -- so counting rows and counting people is the same number today,
    and writing it as people is what keeps it true if that index is ever relaxed.
    """
    return len({d.decided_by for d in decisions
                if d.decision == APPROVED and d.stage_ordinal == ordinal})


def check_decider(
    policy: ApprovalPolicy, *, requested_by: str, decided_by: str,
    decider_permissions: frozenset[str], acting_for: str | None = None,
) -> None:
    """Whether this person may decide this request. Raises rather than returning False.

    Three conditions now, all of which have been quietly dropped in real systems: the decider
    holds **every** permission the applicable policies name; and -- when separation of duties
    applies -- neither the decider **nor the authority they are acting on** is the requester.

    **The third is MOD-026's delegation half and it is the one a delegation silently buys.**
    `acting_for` is the identity whose approval authority is being exercised, which is only
    ever set where a live delegation grants it. If Alice raises a request and has delegated to
    Bob, Bob deciding it is Alice approving her own request through a proxy: separation of
    duties intact in the column and gone in fact. The schema refuses it too, because this
    build's premise is that the schema is the half that holds when the service is wrong --
    but the service is where the caller gets a sentence instead of a constraint name.

    That is MOD-007's "a remedy is new capability, so review it as such", applied to a
    convenience that exists to keep approvals moving while somebody is away.
    """
    # **With stages, the authority is the stage's and not the union.** Charging every
    # applicable policy's permission to every decider would mean each approver needs every
    # stage's permission -- which is to say one person could satisfy all of them, the exact
    # opposite of what a stage is for. `check_stage` charges the one this step is about.
    # Found by a test where a finance approver could not decide the finance stage.
    if not policy.stages:
        missing = policy.required_permissions - decider_permissions
        if missing:
            raise ApprovalError(
                "decider_lacks_permission",
                "the decider does not hold every permission these policies require")
    if not policy.separation_of_duties:
        return
    if decided_by == requested_by:
        raise ApprovalError("separation_of_duties",
                            "the requester may not decide their own request")
    if acting_for is not None and acting_for == requested_by:
        raise ApprovalError(
            "separation_of_duties_through_a_delegate",
            "the requester may not decide their own request through a delegate")


def resolve(
    *,
    required_approvals: int,
    decisions: list[Decision],
    expires_at: datetime,
    now: datetime,
    stages: tuple[Stage, ...] = (),
) -> str:
    """The state a request is in, given the decisions recorded against it.

    A single rejection settles it: requiring two approvals and treating one rejection as a tie to
    be broken would mean a request could be approved over a recorded objection. Expiry is checked
    before approval so that a request which ran out of time does not become approved by a late
    decision.

    **With stages, approved means every stage has its count** -- not that the total reaches
    `required_approvals`, which would let three signatures on stage 1 satisfy a two-stage
    approval and so make "a club manager and then finance" mean "two people". A rejection
    anywhere still settles the whole request, because a stage is a condition rather than a vote.
    """
    if any(d.decision == REJECTED for d in decisions):
        return REJECTED
    if expires_at <= now:
        return EXPIRED
    if stages:
        if all(stage_approvals(decisions, stage.ordinal) >= stage.required_approvals
               for stage in stages):
            return APPROVED
        return PENDING
    approvals = {d.decided_by for d in decisions if d.decision == APPROVED}
    if len(approvals) >= required_approvals:
        return APPROVED
    return PENDING

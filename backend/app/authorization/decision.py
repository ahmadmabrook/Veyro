"""MOD-008 IAM-03-R01..R04: the authorization decision, as a pure function.

Nothing here reads a database or a clock -- `now` is an argument -- so "why was that allowed" is
answerable after the fact by calling `authorize` again with the same rows.

IAM-03's first critical control is that **default deny and least privilege are mandatory**, and
this module is where that is true or false:

* `authorize` starts from a denial and needs a reason to move. Every path that does not find one
  returns the denial it started with, so a bug that forgets a case denies rather than allows.
* **There is no wildcard**, in the catalogue's grammar or here. A role that needs three
  permissions names three.
* **A deny policy outranks everything** -- role grants, allow policies, and priority. IAM-03-R02
  exists for assigned clients, sensitive notes, minors and health data, and a protection that can
  be overridden by writing a higher-priority allow is not a protection.
* **Scope is matched, never assumed.** A brand-scoped assignment authorises nothing at a location
  of another brand, and an assignment with no scope match contributes nothing at all.
* **An expired or revoked assignment contributes nothing**, so temporary access needs no
  revocation to stop working (IAM-03-R04).

Masking (IAM-03-R03) rides along with an allow rather than being a separate question: a caller
that is allowed to read a profile may still not be allowed to read the health notes on it, and
returning the decision and the mask together means no call site can take one without the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.authorization.catalog import CatalogError, require_permission

ALLOW = "allow"
DENY = "deny"
MASK = "mask"

TENANT = "tenant"
BRAND = "brand"
LOCATION = "location"


@dataclass(frozen=True)
class Scope:
    """Where an assignment applies, or where a request is aimed."""

    scope_type: str = TENANT
    brand_id: str | None = None
    location_id: str | None = None

    def covers(self, target: Scope) -> bool:
        """Whether an assignment at this scope reaches a request aimed at `target`.

        A tenant scope reaches everything in the tenant. A brand scope reaches that brand, and a
        location inside it -- which the caller establishes by sending the location's brand along
        with it, because this module does not know the hierarchy and must not guess at it. A
        location scope reaches only that location.
        """
        if self.scope_type == TENANT:
            return True
        if self.scope_type == BRAND:
            return self.brand_id is not None and self.brand_id == target.brand_id
        if self.scope_type == LOCATION:
            return self.location_id is not None and self.location_id == target.location_id
        return False


@dataclass(frozen=True)
class Assignment:
    role_key: str
    permissions: frozenset[str]
    scope: Scope = field(default_factory=Scope)
    expires_at: datetime | None = None
    revoked: bool = False

    def live(self, now: datetime) -> bool:
        return not self.revoked and (self.expires_at is None or self.expires_at > now)


@dataclass(frozen=True)
class Policy:
    policy_key: str
    effect: str
    action: str
    match: dict[str, str] = field(default_factory=dict)
    masked_fields: tuple[str, ...] = ()
    priority: int = 100

    def matches(self, action: str, attributes: dict[str, str]) -> bool:
        """Whether this policy applies. **The rule for an absent attribute depends on the
        effect, and getting that symmetric was a real security defect.**

        An `allow` needs every attribute it names to be present and equal. An absent attribute is
        not a wildcard: a policy written for one clinician's assigned clients must not apply to
        every caller that forgot to send `assigned_to`.

        A `deny` or a `mask` is the opposite. It fires **unless the request positively
        contradicts it** -- an absent attribute still matches. The party supplying the attributes
        is the party the policy constrains, so treating "I did not say whether this record is a
        minor's" as "therefore not a minor's" let anybody evade a deny by leaving a field out.
        That is exactly what an independent review demonstrated against the first version of this
        file, and the reasoning that produced it was an allow-shaped example applied to both.

        The asymmetry is the safe direction in each case: an unknown attribute must not grant,
        and must not excuse.
        """
        if self.action != action:
            return False
        if self.effect == ALLOW:
            return all(attributes.get(name) == want for name, want in self.match.items())
        return all(
            attributes.get(name) is None or attributes[name] == want
            for name, want in self.match.items()
        )


@dataclass(frozen=True)
class Request:
    action: str
    scope: Scope = field(default_factory=Scope)
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    """`default_deny`, `unknown_action`, `role:<key>`, `policy:<key>`."""
    matched_policy: str | None = None
    matched_role: str | None = None
    masked_fields: tuple[str, ...] = ()

    def mask(self, record: dict[str, object]) -> dict[str, object]:
        """Apply this decision's mask to a record, so a caller cannot take the data without it."""
        if not self.allowed:
            raise PermissionError("a denied decision has no record to mask")
        return {k: ("***" if k in self.masked_fields else v) for k, v in record.items()}


def authorize(
    request: Request,
    assignments: list[Assignment],
    policies: list[Policy],
    *,
    now: datetime,
) -> Decision:
    """Decide one action. Starts denied and stays denied unless something says otherwise."""
    try:
        require_permission(request.action)
    except CatalogError:
        # An action this build does not define is denied, not passed through. A future evaluator
        # that treated an unknown action as unconstrained would be a wildcard by accident.
        return Decision(allowed=False, reason="unknown_action")

    ordered = sorted(policies, key=lambda p: (p.priority, p.policy_key))

    # Deny first and on its own pass, so no ordering, priority or later allow can get past one.
    for policy in ordered:
        if policy.effect == DENY and policy.matches(request.action, request.attributes):
            return Decision(allowed=False, reason=f"policy:{policy.policy_key}",
                            matched_policy=policy.policy_key)

    granted_by: str | None = None
    for assignment in assignments:
        if not assignment.live(now):
            continue
        if request.action not in assignment.permissions:
            continue
        if not assignment.scope.covers(request.scope):
            continue
        granted_by = assignment.role_key
        break

    allowed_by_policy: str | None = None
    if granted_by is None:
        for policy in ordered:
            if policy.effect == ALLOW and policy.matches(request.action, request.attributes):
                allowed_by_policy = policy.policy_key
                break

    if granted_by is None and allowed_by_policy is None:
        return Decision(allowed=False, reason="default_deny")

    masked: list[str] = []
    for policy in ordered:
        if policy.effect == MASK and policy.matches(request.action, request.attributes):
            masked.extend(f for f in policy.masked_fields if f not in masked)

    if granted_by is not None:
        return Decision(allowed=True, reason=f"role:{granted_by}", matched_role=granted_by,
                        masked_fields=tuple(masked))
    return Decision(allowed=True, reason=f"policy:{allowed_by_policy}",
                    matched_policy=allowed_by_policy, masked_fields=tuple(masked))


def permissions_of(assignments: list[Assignment], *, now: datetime,
                   scope: Scope | None = None) -> frozenset[str]:
    """Everything a set of assignments actually grants right now, for a permission simulator.

    IAM-03-R07 asks for one. Answering it from the same `live` and `covers` the evaluator uses --
    rather than from a second query somewhere -- is what stops the simulator and the enforcement
    disagreeing, which is the one way a simulator is worse than none.
    """
    target = scope or Scope()
    granted: set[str] = set()
    for assignment in assignments:
        if assignment.live(now) and assignment.scope.covers(target):
            granted |= assignment.permissions
    return frozenset(granted)

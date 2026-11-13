"""MOD-009 SEC-01-R08: retention periods and legal holds, decided without touching the database.

Two rules carry this module, and the second outranks the first.

A retention policy says how long a resource may be kept. A legal hold says that a particular
subject's or resource's data must not be deleted whatever the schedule says, because somebody
with authority has told the tenant to preserve it. TSD paragraph 4392 pairs "backup residue" and
"legal hold conflict" as the two ways a deletion story fails; this module exists so the second
one is a decision somebody wrote down rather than an omission.

The ordering is: a hold blocks, always, and it blocks a data subject's erasure request exactly as
it blocks a scheduled expiry. That is the uncomfortable case and it is the correct one -- the
subject's right to erasure does not override a court's instruction to preserve, and a system that
let it would hand the tenant a legal problem while reporting success.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Policy:
    """How long one kind of resource is kept, in one region."""

    policy_id: str
    resource_type: str
    data_class: str
    retention_days: int
    legal_basis: str
    region: str
    retired: bool = False


@dataclass(frozen=True)
class Hold:
    """An instruction not to delete. A null subject or resource means "all of them"."""

    hold_id: str
    subject_id: str | None
    resource_type: str | None
    reason: str
    reference: str
    released: bool = False


@dataclass(frozen=True)
class Verdict:
    """Why a record may or may not be deleted, in terms a report can print."""

    deletable: bool
    reason: str
    blocking_hold_ids: tuple[str, ...] = ()
    expires_at: datetime | None = None


class RetentionError(ValueError):
    """A retention decision that cannot be made from what was supplied."""


def policy_for(policies: list[Policy], resource_type: str, region: str) -> Policy | None:
    """The live policy for a resource in a region, or None when nobody has set one.

    None is not "keep forever" and it is not "delete now". It is a gap, and the caller must
    refuse rather than pick one of those two readings -- silently defaulting either way makes a
    retention decision on the tenant's behalf that the tenant never made.
    """
    for policy in policies:
        if policy.retired:
            continue
        if policy.resource_type == resource_type and policy.region == region:
            return policy
    return None


def blocking_holds(holds: list[Hold], *, subject_id: str | None,
                   resource_type: str | None) -> tuple[Hold, ...]:
    """Every live hold that covers this subject and resource.

    A hold matches when it is unreleased and each of its two dimensions either names the thing in
    question or is null, which means "every one". The null case is the common one: a preservation
    order usually names a matter, not a table.

    **A null on the request side matches every hold on that dimension.** Asking "may I delete
    this subject's data" without naming a resource is asking about all of them, so a hold on any
    one of them blocks. The asymmetry is deliberate and is the fail-closed direction: the
    alternative would let a caller slip past a hold by leaving a field out, which is the exact
    shape MOD-008's review found in its policy evaluator.
    """
    matched = []
    for hold in holds:
        if hold.released:
            continue
        if hold.subject_id is not None and subject_id is not None \
                and hold.subject_id != subject_id:
            continue
        if hold.resource_type is not None and resource_type is not None \
                and hold.resource_type != resource_type:
            continue
        matched.append(hold)
    return tuple(matched)


def may_delete(
    policies: list[Policy], holds: list[Hold], *, resource_type: str, region: str,
    created_at: datetime, now: datetime, on_request: bool = False,
) -> Verdict:
    """Whether one record may be deleted now.

    `on_request` marks an erasure asked for by the data subject rather than a scheduled expiry.
    It skips the age test -- a subject asking for erasure is not asking to wait out the retention
    period -- and it does not skip the hold test, for the reason in the module docstring.
    """
    blocked = blocking_holds(holds, subject_id=None, resource_type=resource_type)
    if blocked:
        return Verdict(False, "legal_hold", tuple(h.hold_id for h in blocked))

    policy = policy_for(policies, resource_type, region)
    if policy is None:
        return Verdict(False, "no_retention_policy")

    if on_request:
        return Verdict(True, "subject_request")

    expires_at = created_at + timedelta(days=policy.retention_days)
    if now < expires_at:
        return Verdict(False, "within_retention", expires_at=expires_at)
    return Verdict(True, "retention_expired", expires_at=expires_at)


def may_delete_subject(
    holds: list[Hold], *, subject_id: str, now: datetime | None = None
) -> Verdict:
    """Whether a subject's data may be erased at all, before any per-resource question.

    This is the gate `app.privacy.dsar` consults before it starts a deletion. Checking once at
    the top means a held subject is refused with the hold named, rather than discovering it
    halfway through and leaving a partial erasure behind.
    """
    blocked = blocking_holds(holds, subject_id=subject_id, resource_type=None)
    if blocked:
        return Verdict(False, "legal_hold", tuple(h.hold_id for h in blocked))
    return Verdict(True, "no_hold")


def due_for_expiry(
    policies: list[Policy], holds: list[Hold], records: list[tuple[str, str, datetime]],
    *, region: str, now: datetime,
) -> list[dict[str, object]]:
    """Which of a batch of records are past their retention period and not held.

    `records` is (record_id, resource_type, created_at). The result carries the verdict for every
    record, not only the deletable ones: paragraph 4385 says retention jobs "do not silently
    ignore failures", and a job that returns only what it can delete has no way to report the
    ones it could not.
    """
    rows: list[dict[str, object]] = []
    for record_id, resource_type, created_at in records:
        verdict = may_delete(policies, holds, resource_type=resource_type, region=region,
                             created_at=created_at, now=now)
        rows.append({
            "record_id": record_id,
            "resource_type": resource_type,
            "deletable": verdict.deletable,
            "reason": verdict.reason,
            "blocking_hold_ids": list(verdict.blocking_hold_ids),
            "expires_at": verdict.expires_at.isoformat() if verdict.expires_at else None,
        })
    return rows

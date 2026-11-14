"""MOD-012 ECO-02: sync state, cursors, conflict policy, retries and reconciliation.

Paragraph 3028 asks for sync state, cursor, retries, conflict policy, dead-letter, reconciliation
and diagnostics. Everything here is a decision about those; nothing here talks to a provider,
because there is none, and a module that wrote "synced 40 records" without a provider having
answered would be the fabricated-evidence shape this codebase has been bitten by.

**The backoff is MOD-010's, imported rather than copied.** Two retry curves in one repository
drift, and the day they disagree nobody can say which one is the policy. `app.events.dispatch`
owns it; this module decides what a connector run does with the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.events import dispatch

RUN_STATES = ("running", "succeeded", "failed", "dead")

#: What happens when the provider and Veyro both changed the same record since the last sync.
#: Written per install because it is a tenant's decision about their own data, not a property of
#: the adapter: a gym that edits member records in Veyro wants `local_wins`, one that treats the
#: access-control system as the source of truth wants `provider_wins`, and `manual` is for the
#: tenant who would rather see the conflict than lose either side.
CONFLICT_POLICIES = ("local_wins", "provider_wins", "manual")


class SyncError(ValueError):
    """A sync decision this module will not make."""


@dataclass(frozen=True)
class Cursor:
    """Where a resource's sync got to. Opaque to this build: the provider defines its meaning."""

    resource: str
    position: str
    observed_at: datetime


def check_advance(current: Cursor | None, proposed: Cursor) -> None:
    """A cursor moves forward in time, and never backwards by accident.

    **The position is opaque**, so this cannot compare positions -- a provider's cursor may be a
    timestamp, an opaque token or a sequence number, and ordering one is the provider's business.
    What it can compare is when each was observed, and an advance observed *before* the one
    already stored is a late or replayed run settling over a newer result. Letting that through
    means the next sync re-reads a window that was already read, which for a provider that bills
    per call is money and for one with a rate limit is an outage.

    Moving a cursor deliberately backwards is reconciliation, and goes through `reset_cursor`,
    which records who did it and why.
    """
    if not proposed.position.strip():
        raise SyncError("a_cursor_position_cannot_be_blank")
    if current is None:
        return
    if current.resource != proposed.resource:
        raise SyncError("an_advance_compares_one_resource")
    if proposed.observed_at < current.observed_at:
        raise SyncError("a_cursor_cannot_be_advanced_by_an_older_observation")
    # Equal timestamps with a *different* position are two claims about one moment, and which
    # one wins would be whichever arrived last. Equal with the same position is a repeat of an
    # advance already applied, which is harmless and is allowed.
    if (proposed.observed_at == current.observed_at
            and proposed.position != current.position):
        raise SyncError("two_positions_cannot_share_one_observation_time")


@dataclass(frozen=True)
class RunVerdict:
    """What happens to a connector run that just failed."""

    status: str
    """`failed` to try again, `dead` to quarantine for a human."""
    attempts: int
    next_attempt_at: datetime


def failure_verdict(
    *, attempts: int, max_attempts: int, now: datetime,
) -> RunVerdict:
    """Retry or quarantine, with the wait MOD-010's dispatch decides.

    `attempts` counts the one that just failed. A run that has exhausted its budget becomes
    `dead` rather than looping: a connector failing the same way forty times is a connector
    whose provider has changed something, and the thing a tenant needs is somebody looking at
    it, not a tighter loop.
    """
    if attempts < 1:
        raise SyncError("a_failure_is_at_least_one_attempt")
    if max_attempts < 1:
        raise SyncError("max_attempts_must_be_positive")
    if attempts >= max_attempts:
        return RunVerdict(status="dead", attempts=attempts, next_attempt_at=now)
    wait = dispatch.backoff_seconds(attempts)
    return RunVerdict(status="failed", attempts=attempts, next_attempt_at=now + wait)


@dataclass(frozen=True)
class Reconciliation:
    """What a reconciliation pass found between the two sides."""

    local_count: int
    provider_count: int
    matched: int

    @property
    def local_only(self) -> int:
        return self.local_count - self.matched

    @property
    def provider_only(self) -> int:
        return self.provider_count - self.matched

    @property
    def reconciled(self) -> bool:
        return self.local_only == 0 and self.provider_only == 0


def check_reconciliation(found: Reconciliation) -> Reconciliation:
    """Refuse a reconciliation whose arithmetic cannot describe two sets.

    `matched` above either count is not a tighter match, it is a caller that has confused a
    total with an intersection -- and the resulting `local_only` would be negative, which would
    read as "the provider is ahead" on a report nobody could reproduce.
    """
    if found.local_count < 0 or found.provider_count < 0 or found.matched < 0:
        raise SyncError("a_reconciliation_counts_cannot_be_negative")
    if found.matched > min(found.local_count, found.provider_count):
        raise SyncError("more_matched_than_exist_on_one_side")
    return found


def conflict_resolution(
    *, policy: str, local_changed: bool, provider_changed: bool,
) -> str:
    """Which side wins, or whether a human has to look.

    Returns `local`, `provider`, `manual` or `none`. The `manual` policy is the one worth
    stating: it does not resolve, it *refuses to*, and the caller is expected to record the
    conflict rather than pick a side. A policy that silently picked under `manual` would be the
    worst of the three, because the tenant chose it precisely to be asked.
    """
    if policy not in CONFLICT_POLICIES:
        raise SyncError(f"unknown_conflict_policy_{policy}")
    if not local_changed and not provider_changed:
        return "none"
    if local_changed and not provider_changed:
        return "local"
    if provider_changed and not local_changed:
        return "provider"
    return {"local_wins": "local", "provider_wins": "provider", "manual": "manual"}[policy]


#: How long a run may be claimed before another runner may take it, the same lease-not-a-lock
#: shape MOD-010's relay uses and for the same reason: the work happens outside the claiming
#: transaction, so without a reservation a second runner takes a row that is still in flight.
CLAIM_LEASE = timedelta(minutes=15)

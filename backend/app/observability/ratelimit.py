"""MOD-011 REL-02: ApplyRateLimit, hot-tenant protection and noisy-neighbour control.

Paragraph 3498 asks for "scaling policy, hot-tenant protection and noisy-neighbor controls", and
MOD-007 names the matching gap from the other side: lockout bounds guessing against one identity
and **nothing bounds request volume**, so an attacker who knows an address can lock its owner out,
and a refused bearer token writes no audit row because recording one would let anyone grow an
insert-only table without limit. Both wanted the same missing limiter. This is it.

**The counter is in this process's memory, and that is a deliberate choice rather than a
shortcut.** The obvious alternative -- a `plt01` table keyed by (tenant, subject, window) with an
upsert per request -- fails on the thing a limiter exists for. The login path is reachable
without authentication and its subject is a caller-supplied address, so an attacker sending a
million distinct addresses writes a million rows into a table whose runtime roles hold no DELETE:
the limiter becomes the unbounded-growth primitive it was added to prevent. A durable limiter
needs either a store with expiry (Redis) or a sweeper, and this build has neither.

So the window counters live in a dict with a hard cap on how many distinct subjects it tracks,
and the cap is enforced by evicting the oldest window rather than by refusing to track -- an
eviction loses a limiter's memory of one subject, which is the least-bad failure available and
is bounded by `_MAX_TRACKED`.

**What this does not do, stated here rather than discovered in production:** it does not
coordinate across processes. Two replicas each allow the full budget, so the effective limit is
the budget times the replica count, and the counters reset when a process restarts. That is
honest for a build that runs one process and is the first thing to revisit when it runs two. The
decision functions below are pure and take the count as an argument precisely so that a shared
store can be swapped underneath them without the policy moving.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

#: A fixed window rather than a sliding one or a token bucket. A fixed window admits up to twice
#: the budget across a window boundary, which is the well-known flaw and is acceptable here: the
#: job is to stop one tenant or one attacker saturating a shared process, not to meter billing.
#: A token bucket would be the right upgrade and needs the same counter store either way.
WINDOW_SECONDS = 60

#: Named budgets, per window, per subject. Written here rather than per call site so that a new
#: surface inherits a limit instead of inventing one -- and so that the numbers are reviewable in
#: one place, which is the only way anybody notices that a limit is too generous to bite.
BUDGETS: dict[str, int] = {
    # Authentication, keyed by the address being attempted. Five failures already lock an
    # identity out (MOD-007), so this is about volume against the process and against addresses
    # that do not exist, which lockout cannot see at all.
    "auth.login": 30,
    # Recovery and step-up, keyed by identity. Lower, because each one costs a scrypt.
    "auth.recover": 10,
    # Everything behind the gate, keyed by identity. Generous: this is noisy-neighbour
    # protection, not a product limit, and a limit that trips during ordinary use is a limit
    # somebody will raise to infinity rather than investigate.
    "api.request": 600,
}

#: How many distinct subjects one process tracks before it evicts. Each entry is a key, an
#: integer and a window start, so this bound is about memory, and the number is chosen to be
#: far above any honest tenant's concurrent user count and far below anything that matters.
_MAX_TRACKED = 50_000


class RateLimitError(ValueError):
    """A limit this module does not define."""


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    limit: int
    used: int
    """How many requests this subject has made in the current window, including this one."""
    retry_after_seconds: int
    """Zero when allowed. Otherwise how long until the window turns over."""


def window_start(now_epoch: float, *, window_seconds: int = WINDOW_SECONDS) -> int:
    """Which fixed window a moment falls in, as an integer so it can be a dict key."""
    if window_seconds <= 0:
        raise RateLimitError("window_must_be_positive")
    return int(now_epoch) // window_seconds * window_seconds


def decide(*, limit_key: str, used: int, now_epoch: float,
           window_seconds: int = WINDOW_SECONDS) -> Verdict:
    """Is this request within budget? Pure, so the counter can live anywhere.

    `used` counts this request. A budget of 30 admits the 30th and refuses the 31st, which is
    the reading that makes "30 per minute" mean what it says.
    """
    try:
        limit = BUDGETS[limit_key]
    except KeyError:
        raise RateLimitError(f"{limit_key!r} is not a rate limit this build defines") from None
    if used <= limit:
        return Verdict(allowed=True, limit=limit, used=used, retry_after_seconds=0)
    turnover = window_start(now_epoch, window_seconds=window_seconds) + window_seconds
    return Verdict(allowed=False, limit=limit, used=used,
                   retry_after_seconds=max(1, int(turnover - now_epoch)))


class Limiter:
    """The in-process counter. One per application; the request path holds a reference.

    Thread-safe because FastAPI runs synchronous route functions in a thread pool, so two
    requests for the same subject genuinely do arrive concurrently. The lock is held for a
    dictionary update and nothing else.
    """

    def __init__(self, *, window_seconds: int = WINDOW_SECONDS,
                 max_tracked: int = _MAX_TRACKED) -> None:
        self._window_seconds = window_seconds
        self._max_tracked = max_tracked
        self._counts: dict[tuple[str, str, str], tuple[int, int]] = {}
        self._lock = Lock()

    def check(self, *, tenant_id: str, limit_key: str, subject: str,
              now_epoch: float) -> Verdict:
        """Count this request against the subject's budget and say whether it is within it.

        The subject is **hashed by the caller when it is personal data**; this module stores
        whatever string it is given and never logs it. The tenant is part of the key so one
        tenant's traffic cannot consume another's budget, which is the whole of the
        noisy-neighbour requirement that a per-process limiter can satisfy.
        """
        if limit_key not in BUDGETS:
            raise RateLimitError(f"{limit_key!r} is not a rate limit this build defines")
        start = window_start(now_epoch, window_seconds=self._window_seconds)
        key = (tenant_id, limit_key, subject)
        with self._lock:
            window, count = self._counts.get(key, (start, 0))
            if window != start:
                window, count = start, 0
            count += 1
            self._counts[key] = (window, count)
            if len(self._counts) > self._max_tracked:
                self._evict(start)
        return decide(limit_key=limit_key, used=count, now_epoch=now_epoch,
                      window_seconds=self._window_seconds)

    def _evict(self, current_window: int) -> None:
        """Drop everything from an earlier window; if that is not enough, drop arbitrarily.

        Called under the lock. Entries from a past window are dead by definition, so the first
        pass is free. The second pass only runs when more than `max_tracked` distinct subjects
        are active inside one window, which is a flood -- and losing a counter during a flood
        admits one extra window's budget for that subject rather than failing the request.
        """
        stale = [k for k, (window, _) in self._counts.items() if window != current_window]
        for k in stale:
            del self._counts[k]
        overflow = len(self._counts) - self._max_tracked
        for k in list(self._counts)[:max(0, overflow)]:
            del self._counts[k]

    def tracked(self) -> int:
        with self._lock:
            return len(self._counts)

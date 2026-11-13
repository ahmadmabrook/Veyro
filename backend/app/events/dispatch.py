"""MOD-010 DAT-01: what to do with a delivery, decided without touching the database.

Three questions live here, and each is a decision somebody can disagree with in review rather
than discover in production: how long to wait before the next attempt, when to stop attempting,
and whether a replay may let a consumer act.

**Backoff is deterministic and has no jitter.** That is a real tradeoff, stated rather than
hidden: identical failures retry in lockstep, so a dependency that fell over gets every pending
delivery at once when it comes back. Jitter is the usual answer and it would make this function
untestable without injecting a clock *and* a random source. At this scale the lockstep is
cheaper than the indirection; the day a relay runs against a shared dependency at volume, this
is the function to change, and `backoff_seconds` is the only place to change it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

#: What a consumer says about re-running its own effects, as TSD paragraph 200 requires of every
#: consumer. Ordered weakest to strongest guarantee.
REPLAY_SAFETY = ("suppress", "idempotent", "safe")

#: What a replay job is allowed to do. `suppress` is the default everywhere, per paragraph 200.
SIDE_EFFECT_POLICIES = ("suppress", "allow")

#: First retry after 2s, then 4, 8, 16... capped. The cap matters more than the curve: without
#: it, attempt 20 would be scheduled for some time next year and the delivery would read as
#: pending for ever rather than as dead.
_BASE_SECONDS = 2
_CAP = timedelta(hours=1)


class DispatchError(ValueError):
    """A dispatch decision that cannot be made as asked."""


def backoff_seconds(attempts: int) -> timedelta:
    """How long to wait before attempt number `attempts + 1`.

    `attempts` is how many have already been made, so zero means "the first attempt failed".
    """
    if attempts < 0:
        raise DispatchError("attempts_cannot_be_negative")
    # Shifting rather than exponentiating keeps this exact and bounded: 1 << 40 is still an int,
    # where 2.0 ** 1000 is an overflow.
    seconds = _BASE_SECONDS << min(attempts, 20)
    return min(timedelta(seconds=seconds), _CAP)


@dataclass(frozen=True)
class Verdict:
    """What happens to a delivery that just failed."""

    status: str
    """`pending` to try again, `dead` to quarantine."""
    attempts: int
    wait: timedelta
    reason: str


def after_failure(*, attempts: int, max_attempts: int, error: str) -> Verdict:
    """Decide whether a failed delivery retries or goes to the dead-letter table.

    `attempts` is the count *before* this failure, so the caller passes what the row holds and
    this returns what it should hold. Counting here rather than at the call site is deliberate:
    the off-by-one between "attempts made" and "attempts allowed" is how a consumer gets one
    more try than its budget, or one fewer.
    """
    if max_attempts < 1:
        raise DispatchError("max_attempts_must_be_positive")
    if not error.strip():
        raise DispatchError("a_failure_must_say_why")
    made = attempts + 1
    if made >= max_attempts:
        return Verdict(status="dead", attempts=made, wait=timedelta(0),
                       reason=f"exhausted_after_{made}_attempts")
    return Verdict(status="pending", attempts=made, wait=backoff_seconds(made),
                   reason="retry")


def replay_action(*, replay_safety: str, side_effects: str) -> str:
    """Whether a replay delivers an event to this consumer, or records that it did not.

    Two independent statements have to agree, and they are about different things. The job's
    `side_effects` policy is the operator saying what this particular replay is for. The
    subscription's `replay_safety` is the consumer's author saying what re-running their code
    does. Neither one alone is enough:

    * A consumer whose class is `suppress` sends messages, takes money or drives a door. Under
      the default policy it is **not delivered** -- it gets a `suppressed` row instead, so the
      evidence says the event was considered and deliberately skipped rather than lost.
    * A consumer whose class is `safe` only rebuilds something it would rebuild anyway, so it
      is delivered even under the default policy. That is the ordinary use of replay and a rule
      that suppressed it would make the feature useless.
    * `allow` is the operator overriding the consumer's own caution -- "yes, really send those
      messages again". It needs a written reason, which the schema requires.

    Returns `deliver` or `suppress`.
    """
    if replay_safety not in REPLAY_SAFETY:
        raise DispatchError(f"unknown_replay_safety_{replay_safety}")
    if side_effects not in SIDE_EFFECT_POLICIES:
        raise DispatchError(f"unknown_side_effect_policy_{side_effects}")
    if side_effects == "allow":
        return "deliver"
    return "suppress" if replay_safety == "suppress" else "deliver"


"""MOD-007 IAM-01: the authentication decisions, as pure functions.

Nothing here reads a database or a clock -- `now` is always an argument -- so every decision is
reproducible from its inputs. After an incident, "why was that session accepted" is answerable by
calling the same function with the same row.

The assurance levels are IAM-01-R06: "separate authentication assurance levels for routine,
financial, privileged and biometric-sensitive actions". The sources name four *action classes*
and no levels, so the mapping below is this module's reading and is marked as one. It follows NIST
SP 800-63B's shape, where level 2 means a second factor and level 3 means a hardware authenticator
that resists verifier impersonation:

    routine              -> 1   a password alone will do
    financial            -> 2   money moves; a second factor
    privileged           -> 3   administration; hardware-backed
    biometric_sensitive  -> 3   the same, because IAM-01's own control says biometric templates
                                never leave the device, so the thing being protected is the
                                decision rather than the template

Collapsing four classes onto three levels is deliberate: inventing a fourth level the sources do
not describe would put a number in the product that nothing else agrees with.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

AAL_ROUTINE = 1
AAL_ELEVATED = 2
AAL_HARDWARE = 3

ACTION_ASSURANCE: dict[str, int] = {
    "routine": AAL_ROUTINE,
    "financial": AAL_ELEVATED,
    "privileged": AAL_HARDWARE,
    "biometric_sensitive": AAL_HARDWARE,
}

# A factor's own ceiling. A password can never reach level 2 on its own, and only a hardware
# authenticator reaches 3; a passkey synced to a cloud keychain is a strong factor but not a
# hardware-bound one, so it stops at 2.
FACTOR_ASSURANCE: dict[str, int] = {
    "password": AAL_ROUTINE,
    "recovery_code": AAL_ROUTINE,
    "totp": AAL_ELEVATED,
    "passkey_synced": AAL_ELEVATED,
    "passkey_hardware": AAL_HARDWARE,
}

# Higher assurance expires sooner: a stepped-up session is a window opened for one job, not a
# state the user stays in.
SESSION_LIFETIME: dict[int, timedelta] = {
    AAL_ROUTINE: timedelta(days=14),
    AAL_ELEVATED: timedelta(hours=12),
    AAL_HARDWARE: timedelta(minutes=15),
}

RESET_CAPABLE_FACTORS = ("recovery_code",)
"""Factors that let a session reset a password without presenting the old one.

A session opened with a recovery code is level 1 by the factor table -- one kind of thing -- but
it can do something a password session cannot. Lifetime follows capability rather than level, or
a fortnight-long routine session would carry a reset power and renew it on every rotation.
"""


def carries_reset_capability(factors: list[str]) -> bool:
    return any(f in RESET_CAPABLE_FACTORS for f in factors)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
CHALLENGE_LIFETIME = timedelta(minutes=5)


class PolicyError(ValueError):
    """An argument that no policy answer exists for. `code` is stable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def required_aal(action_class: str) -> int:
    try:
        return ACTION_ASSURANCE[action_class]
    except KeyError:
        # An unknown action class is not assumed to be routine. Defaulting downwards here would
        # mean every action nobody classified runs at the lowest bar.
        raise PolicyError(
            "unknown_action_class", f"{action_class!r} has no assurance level"
        ) from None


def assurance_for(factors: list[str]) -> int:
    """The level a set of presented factors reaches.

    The highest single factor sets the level, and two independent factors raise a level-1 result
    to level 2 -- that is what "multi-factor" means. Two passwords are not two factors: they are
    the same kind of thing twice, so `FACTOR_ASSURANCE` is read over the distinct *kinds*.
    """
    if not factors:
        return 0
    kinds = {f for f in factors}
    unknown = kinds - set(FACTOR_ASSURANCE)
    if unknown:
        raise PolicyError("unknown_factor", f"unknown factors: {sorted(unknown)}")
    best = max(FACTOR_ASSURANCE[kind] for kind in kinds)
    if best == AAL_ROUTINE and len(kinds) > 1:
        return AAL_ELEVATED
    return best


def needs_step_up(session_aal: int, action_class: str) -> bool:
    return session_aal < required_aal(action_class)


def session_expiry(issued_at: datetime, aal: int, factors: list[str] | None = None) -> datetime:
    """When a session stops being usable.

    The shorter of what its level allows and what its capability allows. A recovery-code session
    is level 1 but can reset a password, so it gets the elevated window rather than the routine
    fortnight.
    """
    if aal not in SESSION_LIFETIME:
        raise PolicyError("unknown_assurance_level", f"no lifetime for assurance level {aal}")
    lifetime = SESSION_LIFETIME[aal]
    if carries_reset_capability(factors or []):
        lifetime = min(lifetime, SESSION_LIFETIME[AAL_ELEVATED])
    return issued_at + lifetime


def window_is_fixed(aal: int, factors: list[str] | None = None) -> bool:
    """Whether rotation must carry the original deadline instead of opening a fresh window.

    True for anything above routine, and for a routine session that carries a reset capability:
    otherwise rotating before expiry renews that power for ever without re-presenting anything,
    which is how a stolen recovery session became permanent.
    """
    return aal > AAL_ROUTINE or carries_reset_capability(factors or [])


@dataclass(frozen=True)
class SessionState:
    aal: int
    expires_at: datetime
    revoked_at: datetime | None = None


def session_usable(session: SessionState, now: datetime) -> tuple[bool, str]:
    """Whether a session may authorize anything, and why not when it may not.

    Revocation is checked before expiry so a revoked session that has also expired reports the
    revocation: that is the fact worth seeing in a log.
    """
    if session.revoked_at is not None and session.revoked_at <= now:
        return False, "revoked"
    if session.expires_at <= now:
        return False, "expired"
    return True, "active"


# --------------------------------------------------------------------------- lockout

@dataclass(frozen=True)
class LockoutState:
    failed_attempts: int
    locked_until: datetime | None = None


def locked(state: LockoutState, now: datetime) -> bool:
    return state.locked_until is not None and state.locked_until > now


def after_failure(state: LockoutState, now: datetime, *,
                  max_attempts: int = MAX_FAILED_ATTEMPTS,
                  duration: timedelta = LOCKOUT_DURATION) -> LockoutState:
    """Count a failure and lock once the threshold is reached.

    The counter keeps climbing past the threshold rather than resetting, so repeated attempts
    against a locked account stay visible in the row rather than looking like a fresh first try.
    """
    attempts = state.failed_attempts + 1
    if attempts >= max_attempts:
        return LockoutState(failed_attempts=attempts, locked_until=now + duration)
    return LockoutState(failed_attempts=attempts, locked_until=state.locked_until)


def after_success(_: LockoutState) -> LockoutState:
    """A correct credential clears both the count and any lock."""
    return LockoutState(failed_attempts=0, locked_until=None)


# --------------------------------------------------------------------------- passkeys

def sign_count_acceptable(stored: int, presented: int) -> bool:
    """WebAuthn clone detection, as the specification states it.

    An authenticator that supports a signature counter must increase it on every assertion, so a
    value that repeats or goes backwards means two things are presenting the same credential --
    the credential has been copied. An authenticator that does not support counters reports zero
    every time, and the specification says to accept that rather than treat every assertion as a
    clone; `stored == 0 and presented == 0` is that case and only that case.
    """
    if stored < 0 or presented < 0:
        raise PolicyError("negative_sign_count", "a signature counter cannot be negative")
    if stored == 0 and presented == 0:
        return True
    return presented > stored


def challenge_expiry(created_at: datetime, *, lifetime: timedelta = CHALLENGE_LIFETIME) -> datetime:
    return created_at + lifetime


def challenge_usable(expires_at: datetime, consumed_at: datetime | None,
                     now: datetime) -> tuple[bool, str]:
    """A challenge is single use and short lived; replay and expiry are reported apart."""
    if consumed_at is not None:
        return False, "already_used"
    if expires_at <= now:
        return False, "expired"
    return True, "pending"


# --------------------------------------------------------------------------- risk

@dataclass(frozen=True)
class RiskSignals:
    known_device: bool
    recent_failures: int
    new_country: bool = False
    impossible_travel: bool = False


def risk_requires_challenge(signals: RiskSignals) -> tuple[bool, str]:
    """A deliberately small, legible rule rather than a score nobody can explain.

    IAM-01-R03 asks for risk-based challenges. What counts as risk is a product decision the
    sources do not make, so this names the three signals that can be derived from what the schema
    actually stores and stops there. A model with weights would look more capable and would be
    answering a question nobody has asked yet.
    """
    if signals.impossible_travel:
        return True, "impossible_travel"
    if signals.new_country and not signals.known_device:
        return True, "new_country_new_device"
    if not signals.known_device:
        return True, "unknown_device"
    if signals.recent_failures >= 3:
        return True, "recent_failures"
    return False, "no_signal"

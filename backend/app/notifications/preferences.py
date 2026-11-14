"""MOD-013 ENG-02: whose preferences stop a notification, and whose cannot.

Paragraph 2458 asks for preferences, quiet hours, frequency caps, digesting, priority and
channel fallback. Everything here is a decision about those and nothing here reads a row.

**A preference cannot switch off a transactional message.** `templates.OPTIONAL_CATEGORIES` is
the whole list a recipient may mute, and a receipt is not on it: a tenant unable to tell
somebody their payment failed because they muted marketing is a product that has confused
courtesy with correctness. The separation is paragraph 2463's control and it lives in the
category, not in a per-call flag somebody could forget.

**A critical alert may bypass preferences only when it names the policy that allows it.**
Paragraph 2461 says "only under documented policy", so the bypass takes a reference and refuses
without one -- the same shape MOD-012's critical integrations use for their fallback and exit
plan. A boolean `urgent: true` would be a field every caller sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.notifications import templates

#: How a recipient wants several notifications of one category handled.
DIGEST_MODES = ("immediate", "hourly", "daily")

#: What a decision can come back as. `defer` carries a time; the others do not.
OUTCOMES = ("send", "defer", "digest", "suppress")


class PreferenceError(ValueError):
    """A preference or a decision input this module will not accept."""


@dataclass(frozen=True)
class Preference:
    """One recipient's wishes for one category on one channel."""

    category: str
    channel: str
    allowed: bool = True
    quiet_from: time | None = None
    quiet_until: time | None = None
    #: An IANA zone name. **Required when quiet hours are set**, and supplied by the caller
    #: rather than inferred: this module has no person record to read a timezone from -- that is
    #: MOD-014's -- and a quiet hour in the server's zone is a quiet hour for nobody.
    timezone: str | None = None
    #: How many of this category this recipient may receive per rolling day. None is no cap.
    daily_cap: int | None = None
    digest_mode: str = "immediate"


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str
    #: Set when the outcome is `defer`: the moment the quiet window ends.
    send_after: datetime | None = None
    #: Which channel to use, after fallback. Equal to the requested one unless it fell back.
    channel: str | None = None


def check_preference(preference: Preference) -> None:
    if preference.category not in templates.CATEGORIES:
        raise PreferenceError(f"{preference.category!r} is not a notification category")
    if preference.channel not in templates.CHANNELS:
        raise PreferenceError(f"{preference.channel!r} is not a channel")
    if preference.digest_mode not in DIGEST_MODES:
        raise PreferenceError(f"{preference.digest_mode!r} is not a digest mode")
    if preference.daily_cap is not None and preference.daily_cap < 0:
        raise PreferenceError("a_daily_cap_cannot_be_negative")
    quiet = (preference.quiet_from, preference.quiet_until)
    if (quiet[0] is None) != (quiet[1] is None):
        raise PreferenceError("quiet_hours_need_both_ends")
    if quiet[0] is not None and preference.timezone is None:
        raise PreferenceError("quiet_hours_need_a_timezone")
    if preference.timezone is not None:
        try:
            ZoneInfo(preference.timezone)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise PreferenceError(f"{preference.timezone!r} is not an IANA timezone") from e
    if not preference.allowed and preference.category not in templates.OPTIONAL_CATEGORIES:
        raise PreferenceError(
            f"a {preference.category} notification cannot be switched off by a preference; "
            f"only {list(templates.OPTIONAL_CATEGORIES)} may be"
        )


def in_quiet_hours(preference: Preference, at: datetime) -> bool:
    """Is this moment inside the recipient's quiet window, in the recipient's own zone?

    The window may wrap midnight -- 22:00 to 07:00 is the ordinary case and the one a naive
    `start <= t <= end` gets wrong, by treating the quietest hours of the night as the only
    ones that are loud.
    """
    if preference.quiet_from is None or preference.quiet_until is None:
        return False
    if preference.timezone is None:
        raise PreferenceError("quiet_hours_need_a_timezone")
    if at.tzinfo is None:
        raise PreferenceError("a_moment_needs_a_timezone")
    local = at.astimezone(ZoneInfo(preference.timezone)).time()
    if preference.quiet_from <= preference.quiet_until:
        return preference.quiet_from <= local < preference.quiet_until
    return local >= preference.quiet_from or local < preference.quiet_until


def quiet_window_ends(preference: Preference, at: datetime) -> datetime:
    """When the quiet window containing `at` ends, in UTC."""
    if preference.quiet_until is None or preference.timezone is None:
        raise PreferenceError("quiet_hours_need_both_ends")
    zone = ZoneInfo(preference.timezone)
    local = at.astimezone(zone)
    end = local.replace(hour=preference.quiet_until.hour,
                        minute=preference.quiet_until.minute, second=0, microsecond=0)
    if end <= local:
        end = end + timedelta(days=1)
    return end.astimezone(at.tzinfo or zone)


@dataclass(frozen=True)
class Request:
    """What is being asked for, from this module's point of view."""

    category: str
    channel: str
    #: `critical` is the only priority that may bypass a preference, and only with a policy.
    priority: str = "normal"
    bypass_policy_ref: str | None = None
    #: How many of this category the recipient has already had in the rolling window.
    sent_today: int = 0
    #: Whether the address this would go to is on the suppression list for this channel.
    suppressed: bool = False


PRIORITIES = ("normal", "high", "critical")


def resolve_channel(
    requested: str, *, channel_enabled: bool, fallback_channel: str | None,
) -> tuple[str | None, str | None]:
    """Which channel this will actually go to, decided **before** anything is evaluated.

    Returns `(channel, None)`, or `(None, reason)` when there is nowhere to send.

    **This is separate from `decide` because the ordering is the whole control.** The first
    version resolved the fallback in the middle of the decision, after the preference, the
    suppression check and the address digest had already been read for the channel the message
    was no longer going to. Every one of those is a per-channel fact, so a tenant falling back
    from email to SMS -- the ordinary response to a provider outage, which is exactly when
    volume gets re-routed -- sent to a member who had opted out of SMS, to a number that had
    reported the tenant as spam, over a channel that was itself disabled, and stored the email
    digest against the SMS row so the eventual bounce wrote a suppression key no later request
    could ever produce. Four controls, all defeated by one ordering. Found by review.

    Fallback happens once. Chaining it would mean a message arriving somewhere nobody chose.
    """
    if channel_enabled:
        return requested, None
    if fallback_channel is None:
        return None, "channel_disabled_and_no_fallback"
    return fallback_channel, None


def decide(request: Request, preference: Preference | None, *, at: datetime) -> Decision:
    """The one place a notification's fate is decided before it is authored.

    `request.channel` is the **resolved** channel from `resolve_channel`, and the preference,
    the suppression flag and the sent-today count must all be the ones read for that channel.

    The order is deliberate and each step is a different kind of refusal:

    1. **Suppression wins over everything, including a critical alert.** A bounce or a complaint
       is the channel telling us the address is wrong or the recipient reported us; sending
       anyway damages the sending reputation every other notification depends on. A critical
       alert that cannot reach somebody is a routing problem, not a licence to keep sending.
    2. **A critical alert may then bypass** the preference and the quiet window -- with a policy
       reference, refused without one. The permission that buys this is not the one that buys an
       ordinary request; see `notifications.notification.request_critical`.
    3. **An opt-out suppresses**, but only for a category a preference may switch off.
    4. **Quiet hours defer**, they do not suppress: the member still wants the message, later.
    5. **A frequency cap digests** rather than dropping, so nothing is lost -- which is what
       makes a cap safe to set low.
    """
    if request.priority not in PRIORITIES:
        raise PreferenceError(f"{request.priority!r} is not a priority")
    if request.category not in templates.CATEGORIES:
        raise PreferenceError(f"{request.category!r} is not a notification category")
    if preference is not None and preference.category != request.category:
        raise PreferenceError("a_preference_applies_to_its_own_category")

    if request.suppressed:
        return Decision(outcome="suppress", reason="address_is_suppressed_on_this_channel")

    channel = request.channel

    if request.priority == "critical":
        if not (request.bypass_policy_ref or "").strip():
            raise PreferenceError(
                "a critical notification bypasses preferences only under a documented policy, "
                "so it must name one"
            )
        return Decision(outcome="send", reason="critical_bypass", channel=channel)

    if preference is not None and not preference.allowed:
        return Decision(outcome="suppress", reason="recipient_opted_out", channel=channel)

    if preference is not None and in_quiet_hours(preference, at):
        return Decision(outcome="defer", reason="quiet_hours",
                        send_after=quiet_window_ends(preference, at), channel=channel)

    cap = preference.daily_cap if preference is not None else None
    if cap is not None and request.sent_today >= cap:
        return Decision(outcome="digest", reason="daily_cap_reached", channel=channel)

    if preference is not None and preference.digest_mode != "immediate":
        return Decision(outcome="digest", reason=f"digest_{preference.digest_mode}",
                        channel=channel)

    return Decision(outcome="send", reason="no_preference_stops_it", channel=channel)

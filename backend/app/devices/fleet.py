"""Paragraph 3079's fleet view and paragraph 3087's required outcome: "fleet failures are
detected before they block club operation."

**Online is derived from when the device last spoke, not stored.** MOD-018 spent four reviews
learning not to keep a cached total, and this is the same argument about a boolean: a stored
`online` flag is a second authority that disagrees with the last health record, and the
disagreement surfaces as an operator driving to a club whose turnstile is fine.

**`offline` is not one threshold.** A gateway that has not reported for two minutes is late; a
turnstile that has not reported for an hour is a problem; a device that has never reported is
neither -- it has not been commissioned. Three states rather than a boolean, because the
action differs: wait, investigate, or finish installing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.devices.capabilities import DeviceError

#: How often a device in service is expected to report. Paragraph 3079 asks for "last sync" on
#: the dashboard; this is what makes a stale one meaningful.
EXPECTED_INTERVAL = timedelta(minutes=5)

#: Late, but not yet a problem: two missed reports.
LATE_AFTER = EXPECTED_INTERVAL * 2

#: Offline: six missed reports, half an hour. Short enough that a club opening at six finds
#: out before the first class and long enough that a gateway rebooting for a firmware update
#: does not page anybody.
OFFLINE_AFTER = EXPECTED_INTERVAL * 6

#: What a health record carries, from paragraph 3079: "online status, latency, errors,
#: storage, version, peripherals and last sync". Online status is derived here rather than
#: reported, and last sync *is* the record's own time -- so what a device sends is the rest.
HEALTH_FIELDS: tuple[str, ...] = (
    "latency_ms", "error_count", "storage_free_bytes", "agent_version", "peripherals",
)

#: Bounds, so a caller cannot drive a column past `integer` into a 500 rather than a 422.
MAX_LATENCY_MS = 600_000
MAX_ERROR_COUNT = 1_000_000_000
MAX_STORAGE_BYTES = 1 << 50


@dataclass(frozen=True)
class Health:
    """One health report's numbers."""

    latency_ms: int
    error_count: int
    storage_free_bytes: int
    agent_version: str


def check_health(health: Health) -> None:
    if not 0 <= health.latency_ms <= MAX_LATENCY_MS:
        raise DeviceError("a reported latency is between zero and ten minutes")
    if not 0 <= health.error_count <= MAX_ERROR_COUNT:
        raise DeviceError("a reported error count is not negative and is bounded")
    if not 0 <= health.storage_free_bytes <= MAX_STORAGE_BYTES:
        raise DeviceError("reported free storage is not negative and is bounded")
    if not health.agent_version.strip():
        raise DeviceError("a health report names the agent version that sent it")
    if len(health.agent_version.strip()) > 64:
        raise DeviceError("an agent version is at most 64 characters")


def reachability(last_seen_at: datetime | None, *, at: datetime) -> str:
    """`never_seen`, `online`, `late` or `offline`, derived from the last report.

    **A report from the future is `online`, deliberately.** A gateway whose clock runs fast is
    a clock problem rather than a reachability one, and calling it offline would send somebody
    to a working device. `snapshots.check_fresh_enough` is what refuses to *trust* such a
    device's own idea of expiry.
    """
    if last_seen_at is None:
        return "never_seen"
    silence = at - last_seen_at
    if silence < LATE_AFTER:
        return "online"
    if silence < OFFLINE_AFTER:
        return "late"
    return "offline"


def blocks_operation(state: str, reach: str) -> bool:
    """Whether this device's condition stops a club doing something, which is what to page on.

    Paragraph 3087's outcome is about detection *before* it blocks operation, so the thing
    worth an alert is a device that is supposed to be working and is not -- not a device
    deliberately in maintenance, and not one nobody has finished installing.
    """
    return state == "active" and reach == "offline"

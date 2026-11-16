"""TSD section 16.4: the hardware safety profile, the commissioning gate and egress.

**This is the module's load-bearing half and all of it is refusals.** Paragraph 4172: every
access point is commissioned with a profile "according to door type, fire code,
landlord/civil-defence requirements and vendor certification", and "software cannot override
required egress behavior". Paragraph 4173: "Egress is never conditioned on Veyro membership,
cloud reachability or software authorization", and the fire-alarm release wiring is "outside
the Veyro application path". Paragraph 4175: a failed safety test "blocks opening the access
point in production".

So the shape here is not a feature with a setting. It is three things the software **cannot**
do:

  * It cannot issue a command that holds a barrier shut against egress, on any device, in any
  state, with any permission. `HOLD_COMMANDS` is the list and `check_command_safety` is the
  refusal -- there is no flag that turns it off, because paragraph 4173 is a fire code rather
  than a preference.
  * It cannot activate an access point whose commissioning has not passed every required
  test. `may_go_live` is the gate and `REQUIRED_TESTS` is paragraph 4175's own list.
  * It cannot *record* a profile that claims software control of egress. A
  `mechanical_free_egress` door has no software path by construction, and a fail-secure door on
  an egress route is refused outright rather than recorded with a warning.

**What this module does not do is just as deliberate.** It cannot verify that the fire-alarm
wiring exists, because that is a physical fact about a building; what it does is make the
*claim* an attributed, insert-only record that a named person made at a time, and refuse to
bring the access point live until that claim exists for every required test. That is MOD-012's
`validated` shape applied to the one place in this build where getting it wrong traps somebody
in a burning room.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.devices.capabilities import DeviceError

#: Paragraph 4172's three, and nothing else. **`fail_safe` releases on power loss** (the door
#: unlocks), `fail_secure` stays locked, and `mechanical_free_egress` has no electric hold on
#: the egress side at all -- a push bar or a turnstile that free-wheels outward.
SAFETY_PROFILES: tuple[str, ...] = ("fail_safe", "fail_secure", "mechanical_free_egress")

#: The profiles that may be commissioned on a door somebody leaves through. **`fail_secure` is
#: not one of them**: a fail-secure maglock on an egress path holds the door shut when the
#: power goes, which is the failure paragraph 4173 exists to forbid. A fail-secure door is
#: legitimate on an entry-only path -- a delivery door, a plant room -- and that is why the
#: profile exists at all rather than being deleted.
EGRESS_PROFILES: tuple[str, ...] = ("fail_safe", "mechanical_free_egress")

#: Paragraph 4175's own list: "power loss, edge-agent crash, controller disconnect, fire-alarm
#: input, emergency unlock, recovery and manual override". Every one has to be recorded as
#: passed before the access point may go live, and the list is here rather than configurable
#: because a tenant that could shorten it could commission a door that fails closed on a fire
#: alarm.
REQUIRED_TESTS: tuple[str, ...] = (
    "power_loss",
    "edge_agent_crash",
    "controller_disconnect",
    "fire_alarm_input",
    "emergency_unlock",
    "recovery",
    "manual_override",
)

#: What a command may ask of an access point. **`hold` and `lock_down` are not here**, and
#: there is no code path that adds them: a command that holds a barrier shut is the one thing
#: paragraph 4173 forbids software from doing, so the vocabulary does not contain it. Declared
#: as the forbidden list as well as by absence, so that a reviewer reading either sees the
#: intent and `check_command_safety` has something to name in its refusal.
HOLD_COMMANDS: frozenset[str] = frozenset({
    "hold", "hold_closed", "lock_down", "lockdown", "maglock_engage",
    "disable_egress", "secure_egress", "inhibit_exit",
})


@dataclass(frozen=True)
class SafetyProfile:
    """What was commissioned at one access point.

    `on_egress_path` is a fact about the building, not a setting: whether people leave through
    this door. It is recorded because every rule here turns on it, and it is the reason a
    profile is per access point rather than per device type.
    """

    profile: str
    on_egress_path: bool
    #: Whether the fire-alarm release is wired outside the application path, which paragraph
    #: 4173 requires of any maglock or turnstile on an egress route. A claim by a named
    #: commissioner, which this software cannot verify and will not proceed without.
    fire_release_is_independent: bool
    #: Whether a local physical emergency input remains available with the network or the edge
    #: agent down -- paragraph 4174's last sentence.
    local_emergency_input: bool


def check_profile(profile: SafetyProfile) -> None:
    """Refuse a profile that claims software control of egress.

    **Refused rather than recorded with a warning**, because the row is what a commissioning
    certificate is checked against later: a profile that says a fail-secure maglock sits on an
    egress path, stored and flagged, is a building that passes an audit of its records and
    traps somebody in a fire.
    """
    if profile.profile not in SAFETY_PROFILES:
        raise DeviceError(f"{profile.profile!r} is not a hardware safety profile")
    if not profile.on_egress_path:
        return
    if profile.profile not in EGRESS_PROFILES:
        raise DeviceError(
            f"a {profile.profile} barrier on an egress path holds the door shut when the "
            f"power fails; an egress path is fail-safe or mechanically free")
    if not profile.fire_release_is_independent:
        raise DeviceError(
            "a barrier on an egress path has its fire-alarm release wired outside this "
            "application; egress is never conditioned on software")
    if not profile.local_emergency_input:
        raise DeviceError(
            "an egress path keeps a local physical emergency input, available when the "
            "network and the edge agent are not")


def check_command_safety(action: str, *, profile: SafetyProfile | None) -> None:
    """Refuse a command that would make egress conditional on this software.

    **There is no permission that buys this and no state in which it is allowed.** Every other
    control in this build is a permission, a step-up or an approval; this one is a refusal,
    because paragraph 4173 is a fire code and a fire code is not delegable. A tenant that
    genuinely needs a door held shut needs a door that is not on an egress path, which is a
    commissioning decision made with a fire officer rather than a request body.
    """
    lowered = action.strip().lower().replace("-", "_").replace(" ", "_")
    if lowered in HOLD_COMMANDS:
        raise DeviceError(
            f"{action!r} would hold a barrier shut, and egress is never conditioned on this "
            f"software; a door that must stay locked is commissioned off the egress path")
    if profile is not None and profile.on_egress_path and lowered == "unlock_disable":
        raise DeviceError(
            "an egress path's emergency release cannot be disabled from here")


def missing_tests(passed: frozenset[str]) -> tuple[str, ...]:
    """Which of paragraph 4175's tests have no passing record yet."""
    return tuple(name for name in REQUIRED_TESTS if name not in passed)


def may_go_live(
    *, profile: SafetyProfile | None, passed: frozenset[str], actuates: bool,
) -> None:
    """Refuse to bring an actuating device live before its commissioning passed.

    Paragraph 4175: "A failed safety test blocks opening the access point in production." So
    the gate is on the *activation*, where somebody is doing it deliberately, rather than on
    each command -- a per-command check would let a half-commissioned door sit live and refuse
    every request, which looks like a broken reader rather than an uncommissioned door.

    **Only a device that actuates needs one.** A scanner, a printer and a payment terminal
    have no barrier to fail closed, and demanding a fire-alarm test of a receipt printer is how
    a safety gate gets routed around.
    """
    if not actuates:
        return
    if profile is None:
        raise DeviceError(
            "an access point is commissioned with a hardware safety profile before it opens")
    check_profile(profile)
    outstanding = missing_tests(passed)
    if outstanding:
        raise DeviceError(
            "this access point has no passing commissioning record for "
            + ", ".join(outstanding)
            + "; a failed or missing safety test blocks opening it")


def check_test_name(name: str) -> None:
    if name not in REQUIRED_TESTS:
        raise DeviceError(
            f"{name!r} is not one of the commissioning tests; they are "
            f"{', '.join(REQUIRED_TESTS)}")

"""MOD-021 ECO-03's decision functions, with no database.

**Most of this module is refusals, so most of these tests are refusals.** TSD section 16.4 is
a fire code: egress is never conditioned on software, a failed safety test blocks opening an
access point, and no command may hold a barrier shut. Each of those is implemented as
something the software cannot do, and a test that only checked the happy path would pass with
every one of them deleted.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.devices import (
    capabilities,
    certificates,
    commands,
    enrollment,
    fleet,
    safety,
    snapshots,
)
from app.devices.capabilities import DeviceError

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


def profile(**kw) -> safety.SafetyProfile:
    fields = {"profile": "fail_safe", "on_egress_path": True,
              "fire_release_is_independent": True, "local_emergency_input": True}
    fields.update(kw)
    return safety.SafetyProfile(**fields)  # type: ignore[arg-type]


class CapabilityTests(unittest.TestCase):
    def test_the_vocabulary_is_paragraph_3075s_seven(self):
        """Code-resident, like MOD-008's permissions: two tenants disagreeing about what
        `access.actuate` means is unresolvable by anything but the code that drives it."""
        self.assertEqual(len(capabilities.CAPABILITIES), 7)
        self.assertIn(capabilities.ACTUATING, capabilities.CAPABILITIES)

    def test_a_capability_this_software_cannot_ask_for_is_refused(self):
        with self.assertRaises(DeviceError):
            capabilities.check_capability("door.weld_shut")

    def test_a_gateway_is_not_a_door(self):
        """The edge agent runs on it and drives the devices beside it; a gateway declaring
        `access.actuate` would be a door with no door, and the safety profile -- commissioned
        per access point -- would have nothing physical to describe."""
        with self.assertRaises(DeviceError):
            capabilities.check_declared(
                "gateway", frozenset({capabilities.ACTUATING}))
        capabilities.check_declared("gateway", frozenset({"telemetry"}))

    def test_a_type_declares_at_least_one_capability(self):
        with self.assertRaises(DeviceError):
            capabilities.check_declared("kiosk", frozenset())

    def test_a_kiosk_may_take_payment_and_print(self):
        """Deliberately unconstrained beyond the gateway rule: guessing which combinations a
        vendor sells is how a registry refuses real hardware."""
        capabilities.check_declared(
            "kiosk", frozenset({"payment", "print", "scan", "credential.read"}))


class SafetyTests(unittest.TestCase):
    """TSD section 16.4. **The module's load-bearing half, and all of it is refusals.**"""

    def test_a_fail_secure_barrier_on_an_egress_path_is_refused(self):
        """Paragraph 4173. A fail-secure maglock holds the door shut when the power fails,
        which is the failure the paragraph exists to forbid -- and it is refused rather than
        stored with a warning, because a building whose records pass an audit it would fail is
        worse than one with no records."""
        with self.assertRaises(DeviceError):
            safety.check_profile(profile(profile="fail_secure"))
        # Legitimate off an egress path: a delivery door, a plant room.
        safety.check_profile(profile(profile="fail_secure", on_egress_path=False))

    def test_an_egress_path_needs_an_independent_fire_release(self):
        with self.assertRaises(DeviceError):
            safety.check_profile(profile(fire_release_is_independent=False))

    def test_an_egress_path_keeps_a_local_emergency_input(self):
        """Paragraph 4174's last sentence: available when the network and the edge agent are
        not."""
        with self.assertRaises(DeviceError):
            safety.check_profile(profile(local_emergency_input=False))

    def test_a_mechanically_free_door_is_admitted_on_an_egress_path(self):
        safety.check_profile(profile(profile="mechanical_free_egress"))

    def test_no_command_may_hold_a_barrier_shut(self):
        """**There is no permission that buys this and no state in which it is allowed.**
        Every other control in this build is a permission, a step-up or an approval; this one
        is a refusal, because paragraph 4173 is a fire code and a fire code is not delegable.
        """
        for action in ("hold", "lock_down", "lockdown", "maglock_engage",
                       "disable_egress", "inhibit_exit", "HOLD_CLOSED", "lock down",
                       "lock-down"):
            with self.assertRaises(DeviceError, msg=action):
                safety.check_command_safety(action, profile=profile())
        # And with no profile at all, which is the state somebody would try next.
        with self.assertRaises(DeviceError):
            safety.check_command_safety("lock_down", profile=None)

    def test_a_momentary_release_is_the_one_thing_allowed(self):
        safety.check_command_safety("unlock_momentary", profile=profile())

    def test_an_egress_releases_emergency_path_cannot_be_disabled(self):
        with self.assertRaises(DeviceError):
            safety.check_command_safety("unlock_disable", profile=profile())
        safety.check_command_safety(
            "unlock_disable", profile=profile(on_egress_path=False))

    def test_every_commissioning_test_must_pass_before_a_door_opens(self):
        """Paragraph 4175: "A failed safety test blocks opening the access point in
        production." Each of the seven, one at a time, so a missing one is caught rather than
        only an empty set."""
        self.assertEqual(len(safety.REQUIRED_TESTS), 7)
        everything = frozenset(safety.REQUIRED_TESTS)
        safety.may_go_live(profile=profile(), passed=everything, actuates=True)
        for name in safety.REQUIRED_TESTS:
            short = everything - {name}
            with self.assertRaises(DeviceError, msg=name):
                safety.may_go_live(profile=profile(), passed=short, actuates=True)
            self.assertEqual(safety.missing_tests(short), (name,))

    def test_an_access_point_with_no_profile_cannot_go_live(self):
        with self.assertRaises(DeviceError):
            safety.may_go_live(
                profile=None, passed=frozenset(safety.REQUIRED_TESTS), actuates=True)

    def test_a_printer_needs_no_fire_alarm_test(self):
        """Only a device that actuates needs one. Demanding a fire-alarm test of a receipt
        printer is how a safety gate gets routed around."""
        safety.may_go_live(profile=None, passed=frozenset(), actuates=False)

    def test_an_unknown_commissioning_test_is_refused(self):
        with self.assertRaises(DeviceError):
            safety.check_test_name("looked_at_it")


class EnrollmentTests(unittest.TestCase):
    def test_every_state_is_reachable_and_retirement_is_final(self):
        reachable = {"registered"}
        changed = True
        while changed:
            changed = False
            for state in list(reachable):
                for nxt in enrollment.EDGES[state]:
                    if nxt not in reachable:
                        reachable.add(nxt)
                        changed = True
        self.assertEqual(reachable, set(enrollment.DEVICE_STATES))
        self.assertEqual(enrollment.EDGES["retired"], ())

    def test_a_device_cannot_go_live_without_being_provisioned(self):
        with self.assertRaises(DeviceError):
            enrollment.check_transition("registered", "active")

    def test_maintenance_and_quarantine_are_reversible(self):
        """Paragraph 3080's replacement workflow is a swap rather than a scrapping: the old
        unit is quarantined and may come back from the bench."""
        enrollment.check_transition("active", "maintenance")
        enrollment.check_transition("maintenance", "active")
        enrollment.check_transition("quarantined", "active")

    def test_only_an_active_device_operates(self):
        self.assertTrue(enrollment.is_operable("active"))
        for state in ("registered", "provisioned", "maintenance", "quarantined",
                      "retired"):
            self.assertFalse(enrollment.is_operable(state), state)


class CertificateTests(unittest.TestCase):
    """Paragraph 3083, a Critical Control, and both halves of it."""

    def test_a_placeholder_is_refused_at_any_length(self):
        """**The other half of "default credentials are forbidden", and the first version was
        the wrong shape.** It held a list of exact strings including `deadbeef` repeated to 32
        characters -- so a reviewer's `DE:AD:BE:EF:` repeated *eight* times, which normalises
        to 64, was the same placeholder at a different length and walked straight through. A
        vendor default is a pattern somebody typed rather than a particular string, so what is
        checked is whether the whole value is one short block repeated. Found by the HTTP test
        that was written to prove the list.
        """
        for spelling in ("0" * 32, "DE:AD:BE:EF:" * 4, "DE:AD:BE:EF:" * 8,
                         "de-ad-be-ef-" * 4, "F" * 32, "0" * 40, "ab" * 16,
                         "abcd" * 16, "12345678" * 8, "a" * 64):
            with self.assertRaises(DeviceError, msg=spelling):
                certificates.check_issue(
                    spelling, not_before=NOW, not_after=NOW + timedelta(days=90))

    def test_a_real_digest_has_no_short_period(self):
        """The other direction, which is what stops the rule refusing real hardware: the
        probability that a SHA-256 output is a sixteen-character block repeated is nil."""
        for real in ("74c8cd3f464b4b3091e2a5d7f0c81b6e",
                     "9f2b4c8e1a7d63540fe8b2c19a3d7e05" * 2,
                     "0123456789abcdef" + "fedcba9876543210" * 2):
            certificates.check_issue(
                real, not_before=NOW, not_after=NOW + timedelta(days=90))

    def test_a_fingerprint_is_normalised_before_it_is_stored(self):
        """Returned rather than taken on trust, so a caller cannot have one spelling checked
        and another written -- which is the derive-don't-accept shape five modules have paid
        for."""
        folded = certificates.check_issue(
            "AB:CD:EF:12:34:56:78:9A:BC:DE:F0:11:22:33:44:55",
            not_before=NOW, not_after=NOW + timedelta(days=90))
        self.assertEqual(folded, "abcdef123456789abcdef0112233 4455".replace(" ", ""))

    def test_a_fingerprint_that_is_not_a_digest_is_refused(self):
        for bad in ("", "   ", "abc", "z" * 32, "a" * 200):
            with self.assertRaises(DeviceError, msg=bad):
                certificates.normalise_fingerprint(bad)

    def test_a_certificate_lifetime_is_a_rotation(self):
        """Paragraph 3083's word is "rotating", so a decade is refused -- and an hour is
        refused too, because that is a device on a slow link that cannot finish installing
        it."""
        good = "74c8cd3f464b4b3091e2a5d7f0c81b6e"
        certificates.check_issue(
            good, not_before=NOW, not_after=NOW + certificates.MAX_LIFETIME)
        certificates.check_issue(
            good, not_before=NOW, not_after=NOW + certificates.MIN_LIFETIME)
        for life in (timedelta(hours=1), timedelta(days=400), timedelta(0),
                     timedelta(seconds=-1)):
            with self.assertRaises(DeviceError, msg=str(life)):
                certificates.check_issue(
                    good, not_before=NOW, not_after=NOW + life)

    def test_a_superseded_certificate_is_honoured_and_a_revoked_one_is_not(self):
        """**That is the difference between the two states and the reason both exist.** A
        device whose certificate was replaced the instant the new one was issued is locked out
        for as long as it takes to receive it, which for a gateway on a flaky link is long
        enough to shut a club."""
        window = (NOW - timedelta(days=1), NOW + timedelta(days=1))
        self.assertTrue(certificates.is_usable(
            certificates.Certificate("a" * 32, "superseded", *window), at=NOW))
        self.assertFalse(certificates.is_usable(
            certificates.Certificate("a" * 32, "revoked", *window), at=NOW))
        self.assertFalse(certificates.is_usable(
            certificates.Certificate("a" * 32, "pending", *window), at=NOW))

    def test_a_certificate_outside_its_window_is_not_usable(self):
        cert = certificates.Certificate(
            "a" * 32, "active", NOW, NOW + timedelta(days=1))
        self.assertFalse(certificates.is_usable(cert, at=NOW - timedelta(seconds=1)))
        self.assertTrue(certificates.is_usable(cert, at=NOW))
        self.assertFalse(certificates.is_usable(cert, at=NOW + timedelta(days=1)))

    def test_rotation_is_due_in_the_last_quarter_of_its_life(self):
        """A fraction rather than a fixed warning, so a year-long certificate is announced
        three months out and a day-long one six hours out."""
        cert = certificates.Certificate(
            "a" * 32, "active", NOW, NOW + timedelta(days=100))
        self.assertFalse(certificates.due_for_rotation(
            cert, at=NOW + timedelta(days=74)))
        self.assertTrue(certificates.due_for_rotation(
            cert, at=NOW + timedelta(days=76)))

    def test_a_device_with_no_usable_certificate_cannot_go_live(self):
        """The other half of `safety.may_go_live`: that one asks whether the door is safe and
        this asks whether the device can prove who it is."""
        with self.assertRaises(DeviceError):
            certificates.check_may_activate([], at=NOW)
        with self.assertRaises(DeviceError):
            certificates.check_may_activate(
                [certificates.Certificate(
                    "a" * 32, "revoked", NOW, NOW + timedelta(days=1))], at=NOW)
        certificates.check_may_activate(
            [certificates.Certificate(
                "a" * 32, "active", NOW, NOW + timedelta(days=1))], at=NOW)


class CommandTests(unittest.TestCase):
    """Paragraph 3084, a Critical Control with four named properties."""

    def test_the_vocabulary_contains_nothing_that_holds_a_barrier(self):
        """Paragraph 4173 as an absence from a vocabulary rather than a rule somebody enforces.

        **Three properties of every actuating action, not a list of one name.** The first
        version asserted `touching == {"unlock_momentary"}`, which was true of MOD-021 and
        was a per-name list of exactly the kind this repository keeps finding too narrow:
        MOD-022 adds `emergency_unlock` for paragraph 4178, and the assertion failed for a
        reason that had nothing to do with a barrier being held.

        What actually has to hold is that *every* door-touching word is momentary, and
        "momentary" is three things rather than a naming convention:

          * no word in the vocabulary is one that secures a barrier (`HOLD_COMMANDS` is
            about locking down and disabling egress, which is the fire-code direction);
          * every actuating action has a bounded `ISSUE_WINDOW`, so a command cannot be
            parked and delivered on some later night;
          * **no actuating action takes any argument at all.** This is the one the review
            found: `arguments` was an unvalidated passthrough and a reviewer sent
            `{"mode": "hold_open", "hold_seconds": 86400}` on an unlock, so the row an edge
            agent parameterises its relay from carried hold-the-door semantics. A door this
            software can parameterise is a door it can hold.
        """
        touching = {a for a, needs in commands.COMMAND_ACTIONS.items()
                    if needs == capabilities.ACTUATING}
        self.assertTrue(touching, "the vocabulary must have something that opens a door")
        self.assertFalse(
            set(commands.COMMAND_ACTIONS) & safety.HOLD_COMMANDS)
        for action in sorted(touching):
            self.assertIn(action, commands.ISSUE_WINDOW, action)
            self.assertLessEqual(
                commands.ISSUE_WINDOW[action], timedelta(minutes=5), action)
            self.assertEqual(commands.COMMAND_ARGUMENTS[action], frozenset(), action)

    def test_a_command_the_device_cannot_perform_is_refused(self):
        with self.assertRaises(DeviceError):
            commands.check_issue(
                "unlock_momentary", declared=frozenset({"print"}), state="active",
                profile=profile(), arguments={})

    def test_a_command_to_a_device_out_of_service_is_refused(self):
        for state in ("registered", "provisioned", "maintenance", "quarantined",
                      "retired"):
            with self.assertRaises(DeviceError, msg=state):
                commands.check_issue(
                    "reboot", declared=frozenset({"telemetry"}), state=state,
                    profile=None, arguments={})

    def test_an_unlock_needs_a_commissioned_access_point(self):
        with self.assertRaises(DeviceError):
            commands.check_issue(
                "unlock_momentary", declared=frozenset({capabilities.ACTUATING}),
                state="active", profile=None, arguments={})

    def test_the_safety_refusal_comes_before_the_capability_and_the_state(self):
        """**The message somebody reads has to name the reason that matters**, and a reviewer
        probing paragraph 4173 must not be told about a state instead."""
        with self.assertRaises(DeviceError) as caught:
            commands.check_issue(
                "lock_down", declared=frozenset(), state="retired", profile=None,
                arguments={})
        self.assertIn("egress", str(caught.exception))

    def test_an_unlock_is_deliverable_for_a_minute_and_no_longer(self):
        """A door opened a minute after somebody asked is a door opened for whoever is
        standing there now."""
        self.assertEqual(
            commands.window_for("unlock_momentary"), timedelta(seconds=60))
        with self.assertRaises(DeviceError):
            commands.check_issue(
                "unlock_momentary", declared=frozenset({capabilities.ACTUATING}),
                state="active", profile=profile(), arguments={},
                expires_in=timedelta(minutes=2))

    def test_a_command_window_is_bounded_at_a_day(self):
        with self.assertRaises(DeviceError):
            commands.check_issue(
                "reboot", declared=frozenset(), state="active", profile=None,
                arguments={}, expires_in=timedelta(days=2))
        with self.assertRaises(DeviceError):
            commands.check_issue(
                "reboot", declared=frozenset(), state="active", profile=None,
                arguments={}, expires_in=timedelta(0))

    def test_an_expired_command_is_not_delivered(self):
        """A device offline when an unlock was issued must not receive it three days later and
        open a door for whoever is standing there now."""
        cmd = commands.Command(
            "unlock_momentary", "issued", NOW, NOW + timedelta(seconds=60))
        commands.may_deliver(cmd, at=NOW + timedelta(seconds=59))
        self.assertTrue(commands.has_expired(cmd, at=NOW + timedelta(seconds=60)))
        with self.assertRaises(DeviceError):
            commands.may_deliver(cmd, at=NOW + timedelta(seconds=60))

    def test_an_acknowledged_command_never_expires_by_the_clock(self):
        """The device has it; whether it worked is the device's to report, and timing it out
        here would record "expired" for an unlock that opened the door."""
        cmd = commands.Command(
            "unlock_momentary", "acknowledged", NOW, NOW + timedelta(seconds=60))
        self.assertFalse(commands.has_expired(cmd, at=NOW + timedelta(days=1)))
        with self.assertRaises(DeviceError):
            commands.check_transition("acknowledged", "expired")

    def test_the_digest_is_stable_whatever_order_the_arguments_come_in(self):
        """A digest that depended on dict ordering would make tamper detection depend on the
        Python version."""
        first = commands.digest(
            device_id="d", action="reboot", arguments={"a": 1, "b": 2},
            issued_at=NOW, expires_at=NOW + timedelta(hours=1))
        second = commands.digest(
            device_id="d", action="reboot", arguments={"b": 2, "a": 1},
            issued_at=NOW, expires_at=NOW + timedelta(hours=1))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_the_digest_changes_with_everything_it_covers(self):
        base = dict(device_id="d", action="reboot", arguments={},
                    issued_at=NOW, expires_at=NOW + timedelta(hours=1))
        reference = commands.digest(**base)  # type: ignore[arg-type]
        for field, value in (("device_id", "other"), ("action", "sync_now"),
                             ("arguments", {"force": True}),
                             ("issued_at", NOW + timedelta(seconds=1)),
                             ("expires_at", NOW + timedelta(hours=2))):
            changed = dict(base) | {field: value}
            self.assertNotEqual(
                commands.digest(**changed), reference, field)  # type: ignore[arg-type]


class SnapshotTests(unittest.TestCase):
    def test_a_snapshot_lives_between_five_minutes_and_twelve_hours(self):
        snapshots.check_ttl(NOW, NOW + snapshots.MIN_TTL)
        snapshots.check_ttl(NOW, NOW + snapshots.MAX_TTL)
        for ttl in (timedelta(minutes=1), timedelta(days=1), timedelta(0)):
            with self.assertRaises(DeviceError, msg=str(ttl)):
                snapshots.check_ttl(NOW, NOW + ttl)

    def test_a_stale_snapshot_may_deny_and_may_not_admit(self):
        """Paragraph 3094: a stale read model "cannot authorize a consequence-bearing
        mutation". Read as a list rather than a sentence -- reporting and refusing are both
        safe."""
        snap = snapshots.Snapshot(NOW, NOW + timedelta(hours=1), 3, "a" * 64)
        later = NOW + timedelta(hours=2)
        snapshots.check_fresh_enough(
            snap, at=later, purpose="deny", current_epoch=3)
        snapshots.check_fresh_enough(
            snap, at=later, purpose="report", current_epoch=3)
        with self.assertRaises(DeviceError):
            snapshots.check_fresh_enough(
                snap, at=later, purpose="admit", current_epoch=3)

    def test_a_snapshot_behind_the_revocation_epoch_may_not_admit(self):
        """A different failure from staleness, reported separately because the remedy
        differs: an operator reading a denial needs to know whether to re-sync a gateway or to
        look at its clock."""
        snap = snapshots.Snapshot(NOW, NOW + timedelta(hours=1), 3, "a" * 64)
        snapshots.check_fresh_enough(snap, at=NOW, purpose="admit", current_epoch=3)
        with self.assertRaises(DeviceError) as caught:
            snapshots.check_fresh_enough(
                snap, at=NOW, purpose="admit", current_epoch=4)
        self.assertIn("revocation epoch", str(caught.exception))

    def test_a_snapshot_from_the_future_is_not_trusted(self):
        """Paragraph 1951's clock bound: past the tolerated skew, "is this expired" stops
        having one answer."""
        snap = snapshots.Snapshot(
            NOW + timedelta(hours=1), NOW + timedelta(hours=2), 0, "a" * 64)
        with self.assertRaises(DeviceError):
            snapshots.check_fresh_enough(
                snap, at=NOW, purpose="admit", current_epoch=0)
        # Inside the tolerance it is fine, because a gateway's clock is never exact.
        close = snapshots.Snapshot(
            NOW + timedelta(minutes=1), NOW + timedelta(hours=1), 0, "a" * 64)
        snapshots.check_fresh_enough(
            close, at=NOW, purpose="admit", current_epoch=0)

    def test_an_epoch_only_goes_up_and_is_bounded(self):
        self.assertEqual(snapshots.next_epoch(0), 1)
        with self.assertRaises(DeviceError):
            snapshots.next_epoch(-1)
        with self.assertRaises(DeviceError):
            snapshots.next_epoch(2_000_000_000)


class FleetTests(unittest.TestCase):
    def test_reachability_is_three_states_and_never_seen(self):
        """Three rather than a boolean, because the action differs: wait, investigate, or
        finish installing it."""
        self.assertEqual(fleet.reachability(None, at=NOW), "never_seen")
        self.assertEqual(
            fleet.reachability(NOW - timedelta(minutes=1), at=NOW), "online")
        self.assertEqual(
            fleet.reachability(NOW - timedelta(minutes=12), at=NOW), "late")
        self.assertEqual(
            fleet.reachability(NOW - timedelta(hours=1), at=NOW), "offline")

    def test_the_boundaries_are_where_the_constants_say(self):
        for silence, want in ((fleet.LATE_AFTER - timedelta(seconds=1), "online"),
                              (fleet.LATE_AFTER, "late"),
                              (fleet.OFFLINE_AFTER - timedelta(seconds=1), "late"),
                              (fleet.OFFLINE_AFTER, "offline")):
            self.assertEqual(
                fleet.reachability(NOW - silence, at=NOW), want, str(silence))

    def test_a_report_from_the_future_is_online(self):
        """A gateway whose clock runs fast is a clock problem rather than a reachability one,
        and calling it offline would send somebody to a working device."""
        self.assertEqual(
            fleet.reachability(NOW + timedelta(hours=1), at=NOW), "online")

    def test_only_a_device_that_is_supposed_to_be_working_blocks_operation(self):
        """Paragraph 3087's outcome is detection *before* it blocks operation, so the thing
        worth an alert is a device in service that is not working -- not one deliberately in
        maintenance, and not one nobody has finished installing."""
        self.assertTrue(fleet.blocks_operation("active", "offline"))
        for state in ("maintenance", "quarantined", "provisioned", "registered",
                      "retired"):
            self.assertFalse(fleet.blocks_operation(state, "offline"), state)
        for reach in ("online", "late", "never_seen"):
            self.assertFalse(fleet.blocks_operation("active", reach), reach)

    def test_a_health_report_is_bounded_at_every_number(self):
        """Bounded in the decision as well as the column, because `NumericValueOutOfRange` is
        a `DataError` rather than the `CheckViolation` the handlers catch -- a finding in five
        modules now."""
        fleet.check_health(fleet.Health(10, 0, 1_000, "1.2.3"))
        for bad in (fleet.Health(-1, 0, 0, "v"),
                    fleet.Health(fleet.MAX_LATENCY_MS + 1, 0, 0, "v"),
                    fleet.Health(0, -1, 0, "v"),
                    fleet.Health(0, fleet.MAX_ERROR_COUNT + 1, 0, "v"),
                    fleet.Health(0, 0, -1, "v"),
                    fleet.Health(0, 0, fleet.MAX_STORAGE_BYTES + 1, "v"),
                    fleet.Health(0, 0, 0, "   "),
                    fleet.Health(0, 0, 0, "v" * 65)):
            with self.assertRaises(DeviceError, msg=str(bad)):
                fleet.check_health(bad)


if __name__ == "__main__":
    unittest.main()

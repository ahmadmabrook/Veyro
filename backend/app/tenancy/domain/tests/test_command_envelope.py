"""Unit tests for the paragraph 1237 common command envelope.

These evidence the pure decisions `command_envelope` makes about a mapping it is handed. They
evidence no database behaviour, no tenant isolation, no authentication, no authorization of a
real caller and no integration of any kind. Every refusal below is asserted by its `code`, so a
test cannot pass because some unrelated refusal fired.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import command_envelope as ce

ACTOR = "3f8b2c14-5d6e-4a7b-8c9d-0e1f2a3b4c5d"
CORRELATION = "7a1b2c3d-4e5f-4061-8273-849506a7b8c9"
IDEMPOTENCY = "b2c3d4e5-f607-4819-aa2b-3c4d5e6f7081"


def _envelope(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "command": "ProvisionTenant",
        "actor_id": ACTOR,
        "correlation_id": CORRELATION,
        "idempotency_key": IDEMPOTENCY,
    }
    base.update(overrides)
    return base


class EnvelopeCase(unittest.TestCase):
    def refusal(self, envelope: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(ce.EnvelopeError) as caught:
            ce.validate_command_envelope(envelope)
        return caught.exception.code


class TestTheSourceInventory(EnvelopeCase):
    def test_the_inventory_is_exactly_paragraph_1237s_seven_commands(self) -> None:
        """Membership, not only that each member is present: adding an eighth invents a command."""
        self.assertEqual(ce.COMMANDS, (
            "ProvisionTenant",
            "ActivateTenant",
            "SuspendTenant",
            "ChangeOrgHierarchy",
            "AssignRegion",
            "RelocateTenant",
            "ArchiveTenant",
        ))
        self.assertEqual(ce.DESTRUCTIVE_COMMANDS, ("ArchiveTenant",))

    def test_every_non_destructive_command_in_the_inventory_is_accepted(self) -> None:
        for command in ce.COMMANDS:
            if command in ce.DESTRUCTIVE_COMMANDS:
                continue
            with self.subTest(command=command):
                result = ce.validate_command_envelope(_envelope(command=command))
                self.assertEqual(result.command, command)

    def test_a_command_outside_the_inventory_is_refused(self) -> None:
        for command in ("DeleteTenant", "CloneTenant", "CreateBrandTheme", "provisiontenant", ""):
            with self.subTest(command=command):
                self.assertEqual(self.refusal(_envelope(command=command)), "unknown_command")

    def test_a_non_string_command_is_refused_without_being_compared(self) -> None:
        for command in (None, 1, True, ["ProvisionTenant"], {"ProvisionTenant": 1}):
            with self.subTest(command=command):
                self.assertEqual(self.refusal(_envelope(command=command)), "unknown_command")


class TestTheDestructiveGate(EnvelopeCase):
    """TSD paragraph 1231 approvals, retention and immutable audit; MOD-008 does not exist."""

    def test_archive_tenant_is_refused_by_its_own_code(self) -> None:
        """Not `unknown_command`: the source names it, so misreporting it as unknown would lie."""
        self.assertEqual(self.refusal(_envelope(command="ArchiveTenant")),
                         "destructive_command_gated")

    def test_the_gate_is_not_reachable_around_by_a_valid_envelope(self) -> None:
        """Fail closed: every other field being perfect does not open it."""
        envelope = _envelope(command="ArchiveTenant", expected_version=7)
        self.assertEqual(self.refusal(envelope), "destructive_command_gated")

    def test_the_gate_fires_before_the_uuid_checks_and_still_refuses(self) -> None:
        """A destructive command with bad UUIDs is still refused; the order does not matter, the
        refusal does. Asserted as a set membership so this does not pin an arbitrary order."""
        envelope = _envelope(command="ArchiveTenant", actor_id="not-a-uuid")
        self.assertIn(self.refusal(envelope), {"destructive_command_gated", "bad_actor_id"})


class TestMappingPolicy(EnvelopeCase):
    def test_only_an_exact_dict_is_accepted(self) -> None:
        class Subclass(dict[str, object]):
            pass

        for value in ("{}", b"{}", None, 1, [], Subclass(_envelope())):
            with self.subTest(value=type(value).__name__):
                self.assertEqual(self.refusal(value), "not_mapping")

    def test_json_text_is_not_accepted(self) -> None:
        text = '{"command": "ProvisionTenant"}'
        self.assertEqual(self.refusal(text), "not_mapping")

    def test_too_many_fields_is_refused_before_the_content_is_read(self) -> None:
        envelope: dict[str, object] = {}
        for index in range(ce.MAX_FIELDS + 1):
            envelope["k" + str(index)] = 1
        self.assertEqual(self.refusal(envelope), "too_many_fields")

    def test_a_non_string_key_is_refused(self) -> None:
        envelope: dict[object, object] = dict(_envelope())
        envelope[1] = "x"
        self.assertEqual(self.refusal(envelope), "bad_key_type")

    def test_an_unexpected_field_is_refused(self) -> None:
        self.assertEqual(self.refusal(_envelope(tenant_id="x")), "unexpected_field")

    def test_an_overlong_key_name_is_refused(self) -> None:
        envelope = _envelope()
        envelope["k" * (ce.MAX_FIELD_NAME_LENGTH + 1)] = 1
        self.assertEqual(self.refusal(envelope), "unexpected_field")

    def test_each_required_field_is_required(self) -> None:
        for name in ("command", "actor_id", "correlation_id", "idempotency_key"):
            with self.subTest(name=name):
                envelope = _envelope()
                del envelope[name]
                self.assertEqual(self.refusal(envelope), "missing_field")


class TestClaimedUuids(EnvelopeCase):
    def test_each_uuid_field_is_checked_and_reports_its_own_field(self) -> None:
        for name, code in (("actor_id", "bad_actor_id"),
                           ("correlation_id", "bad_correlation_id"),
                           ("idempotency_key", "bad_idempotency_key")):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(_envelope(**{name: "not-a-uuid"})), code)

    def test_the_rejected_uuid_spellings(self) -> None:
        rejected = (
            "00000000-0000-0000-0000-000000000000",
            "{3f8b2c14-5d6e-4a7b-8c9d-0e1f2a3b4c5d}",
            "urn:uuid:3f8b2c14-5d6e-4a7b-8c9d-0e1f2a3b4c5d",
            "3f8b2c145d6e4a7b8c9d0e1f2a3b4c5d",
            " 3f8b2c14-5d6e-4a7b-8c9d-0e1f2a3b4c5d",
            "3f8b2c14-5d6e-4a7b-8c9d-0e1f2a3b4c5d ",
            "3f8b2c14-5d6e-0a7b-8c9d-0e1f2a3b4c5d",
            "3f8b2c14-5d6e-9a7b-8c9d-0e1f2a3b4c5d",
            "3f8b2c14-5d6e-4a7b-0c9d-0e1f2a3b4c5d",
            "3f8b2c14-5d6e-4a7b-8c9d-0e1f2a3b4c5",
        )
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(_envelope(actor_id=value)), "bad_actor_id")

    def test_upper_case_hex_is_accepted_and_normalized(self) -> None:
        result = ce.validate_command_envelope(_envelope(actor_id=ACTOR.upper()))
        self.assertEqual(result.actor_id, ACTOR)

    def test_a_str_subclass_cannot_smuggle_content_through_normalization(self) -> None:
        """`type(value) is str`, not `isinstance`: the result must never be caller-controlled.

        A `str` subclass passes the length and regex checks, and the accept path calls `.lower()`
        on the value -- so an overridden `lower()` writes caller-chosen content into the frozen
        envelope. The exact-type check is the only thing refusing it, and a review found it pinned
        by nothing: swapping it for `isinstance` left the whole suite green. Without this test a
        later lint-driven simplification to `isinstance` would pass CI and the closure check and
        make the normalized output caller-controlled.
        """
        class Sneaky(str):
            def lower(self) -> str:
                return "INJECTED"

        self.assertEqual(self.refusal(_envelope(actor_id=Sneaky(ACTOR))), "bad_actor_id")
        self.assertEqual(self.refusal(_envelope(correlation_id=Sneaky(CORRELATION))),
                         "bad_correlation_id")
        self.assertEqual(self.refusal(_envelope(idempotency_key=Sneaky(IDEMPOTENCY))),
                         "bad_idempotency_key")


class TestExpectedAggregateVersion(EnvelopeCase):
    def test_absent_means_no_version(self) -> None:
        self.assertIsNone(ce.validate_command_envelope(_envelope()).expected_version)

    def test_present_null_is_refused_because_it_differs_from_absent(self) -> None:
        self.assertEqual(self.refusal(_envelope(expected_version=None)), "bad_expected_version")

    def test_the_accepted_range_ends_where_it_says(self) -> None:
        for value in (0, 1, ce.EXPECTED_VERSION_MAX):
            with self.subTest(value=value):
                result = ce.validate_command_envelope(_envelope(expected_version=value))
                self.assertEqual(result.expected_version, value)

    def test_out_of_range_and_wrong_types_are_refused(self) -> None:
        for value in (-1, ce.EXPECTED_VERSION_MAX + 1, True, 1.0, "1", [1]):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(_envelope(expected_version=value)),
                                 "bad_expected_version")


class TestTheResult(EnvelopeCase):
    def test_the_result_is_frozen(self) -> None:
        result = ce.validate_command_envelope(_envelope())
        with self.assertRaises(FrozenInstanceError):
            result.command = "SuspendTenant"  # type: ignore

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "3f8b2c14-5d6e-4a7b-8c9d-ffffffffffff"
        with self.assertRaises(ce.EnvelopeError) as caught:
            ce.validate_command_envelope(_envelope(actor_id=secret + "-overflow"))
        self.assertEqual(str(caught.exception), "invalid MOD-004 command envelope")
        self.assertNotIn(secret, str(caught.exception))

    def test_nothing_is_returned_on_a_refusal(self) -> None:
        """No partially built object: the refusal is raised, so there is no value to inspect."""
        with self.assertRaises(ce.EnvelopeError):
            ce.validate_command_envelope(_envelope(command="ArchiveTenant"))


if __name__ == "__main__":
    unittest.main()

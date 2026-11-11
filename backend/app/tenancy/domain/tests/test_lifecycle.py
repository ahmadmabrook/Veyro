"""Unit tests for the tenant lifecycle transition decision.

These evidence the pure decision `lifecycle` makes about a command and a state handed to it. They
evidence no persisted state change, no approval, no retention or billing gate, no audit record, no
authorization, no database behaviour, no tenant isolation and no integration. Every refusal is
asserted by its `code`, so no test can pass because an unrelated refusal fired.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import lifecycle as lc


class LifecycleCase(unittest.TestCase):
    def refusal(self, command: object, current_state: object = lc.NO_TENANT) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(lc.LifecycleError) as caught:
            lc.apply_command(command, current_state)
        return caught.exception.code


class TestTheStatedVocabulary(LifecycleCase):
    def test_the_states_are_exactly_these_five(self) -> None:
        """Membership, not only presence.

        These five are PLT-01-scoped and are this module's own coinages for a vocabulary the
        paragraph 1194-1245 block never names. They are **not** the pinned baseline's only tenant
        lifecycle: section 10.53 LIF-03 states "Tenant lifecycle from active to past due, suspended,
        cancelled, read-only, archived and deleted", so `past due`, `cancelled` and `read-only` are
        states the document carries and this module does not. A sixth state here would therefore not
        invent one from nothing; it would widen PLT-01's scope to another domain's lifecycle, which
        is why the tuple is pinned.
        """
        self.assertEqual(
            lc.STATES,
            (lc.NO_TENANT, lc.PROVISIONED, lc.ACTIVE, lc.SUSPENDED, lc.ARCHIVED),
        )

    def test_the_lifecycle_commands_are_exactly_paragraph_1237s_four(self) -> None:
        self.assertEqual(
            lc.LIFECYCLE_COMMANDS,
            ("ProvisionTenant", "ActivateTenant", "SuspendTenant", "ArchiveTenant"),
        )

    def test_the_other_three_paragraph_1237_commands_are_named_and_not_lifecycle(self) -> None:
        self.assertEqual(
            lc.NON_LIFECYCLE_COMMANDS,
            ("ChangeOrgHierarchy", "AssignRegion", "RelocateTenant"),
        )

    def test_state_events_carry_exactly_paragraph_1241s_three_tenant_events(self) -> None:
        self.assertEqual(
            lc.STATE_EVENTS,
            {
                lc.PROVISIONED: "tenant.provisioned",
                lc.ACTIVE: "tenant.activated",
                lc.SUSPENDED: "tenant.suspended",
            },
        )

    def test_no_plt01_event_is_invented_for_archival(self) -> None:
        """Paragraph 1241 publishes nothing for `ArchiveTenant`; the gap stays visible.

        `tenant.archived` does exist in the pinned baseline, in section 10.53 LIF-03's published
        events, owned by another domain. What is absent is a PLT-01 event.
        """
        self.assertNotIn(lc.ARCHIVED, lc.STATE_EVENTS)

    def test_the_deletion_spellings_are_pinned_by_value(self) -> None:
        """Pinned literally, like the other four tuples.

        Without this, the loop in `test_deletion_is_refused...` iterates the tuple itself and a
        removed spelling -- `DeleteTenant`, the one MOD-004.md names as the gap -- would silently
        degrade from `deletion_not_sourced` to `unknown_command` with the suite still green.
        """
        self.assertEqual(
            lc._DELETION_SPELLINGS,
            ("DeleteTenant", "delete", "Delete", "deleteTenant", "HardDeleteTenant"),
        )

    def test_the_read_order_is_pinned_by_value(self) -> None:
        self.assertEqual(
            lc._READ_ORDER,
            (
                (lc.PROVISION, lc.NO_TENANT, lc.PROVISIONED),
                (lc.ACTIVATE, lc.PROVISIONED, lc.ACTIVE),
                (lc.SUSPEND, lc.ACTIVE, lc.SUSPENDED),
                (lc.ARCHIVE, lc.SUSPENDED, lc.ARCHIVED),
            ),
        )


class TestTheReadOrder(LifecycleCase):
    """The four pairs this module reads off paragraph 1222's verb order.

    Each is admitted with `order_sourced=False`: the ordering is this module's inference, and no
    paragraph states a transition table.
    """

    def test_provision_from_no_tenant(self) -> None:
        result = lc.apply_command(lc.PROVISION, None)
        self.assertEqual(result.from_state, lc.NO_TENANT)
        self.assertEqual(result.to_state, lc.PROVISIONED)
        self.assertEqual(result.event, "tenant.provisioned")
        self.assertTrue(result.event_stated)

    def test_none_and_the_no_tenant_token_are_the_same_starting_state(self) -> None:
        self.assertEqual(
            lc.apply_command(lc.PROVISION, None),
            lc.apply_command(lc.PROVISION, lc.NO_TENANT),
        )

    def test_activate_from_provisioned(self) -> None:
        result = lc.apply_command(lc.ACTIVATE, lc.PROVISIONED)
        self.assertEqual(result.to_state, lc.ACTIVE)
        self.assertEqual(result.event, "tenant.activated")

    def test_suspend_from_active(self) -> None:
        result = lc.apply_command(lc.SUSPEND, lc.ACTIVE)
        self.assertEqual(result.to_state, lc.SUSPENDED)
        self.assertEqual(result.event, "tenant.suspended")

    def test_archive_from_suspended_admits_the_transition_with_no_event(self) -> None:
        result = lc.apply_command(lc.ARCHIVE, lc.SUSPENDED)
        self.assertEqual(result.to_state, lc.ARCHIVED)
        self.assertIsNone(result.event)
        self.assertFalse(result.event_stated)

    def test_no_admitted_transition_claims_the_order_is_sourced(self) -> None:
        for command, from_state, _ in lc._READ_ORDER:
            with self.subTest(command=command):
                self.assertFalse(lc.apply_command(command, from_state).order_sourced)


class TestTheGapsAreRefusedRatherThanFilled(LifecycleCase):
    def test_deletion_is_refused_because_no_plt01_command_or_event_states_it(self) -> None:
        for spelling in lc._DELETION_SPELLINGS:
            with self.subTest(spelling=spelling):
                self.assertEqual(self.refusal(spelling), "deletion_not_sourced")

    def test_deletion_is_never_a_state(self) -> None:
        self.assertNotIn("deleted", lc.STATES)

    def test_the_three_non_lifecycle_commands_get_their_own_code(self) -> None:
        """Stated commands of this module, so not unknown, but they reach no lifecycle state."""
        for command in lc.NON_LIFECYCLE_COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(self.refusal(command), "command_not_a_lifecycle_command")


class TestWhatLiesOffTheReadOrder(LifecycleCase):
    """Each pair below is refused because it is off this module's reading, not because a source
    forbids it. The code is named `transition_outside_read_order` for exactly that reason.
    """

    def test_reactivation_is_refused_although_the_baseline_mentions_reactivation(self) -> None:
        """Section 10.3 PLT-03 states "suspension, reactivation and offboarding coordination".

        So reactivation is not absent from the pinned baseline. What is absent is a PLT-01
        reactivation command in paragraph 1237, which is the narrower and sufficient reason to
        refuse it here rather than invent one.
        """
        self.assertEqual(
            self.refusal(lc.ACTIVATE, lc.SUSPENDED), "transition_outside_read_order"
        )

    def test_archiving_straight_from_active_is_refused(self) -> None:
        self.assertEqual(self.refusal(lc.ARCHIVE, lc.ACTIVE), "transition_outside_read_order")

    def test_archiving_a_provisioned_tenant_is_refused(self) -> None:
        self.assertEqual(self.refusal(lc.ARCHIVE, lc.PROVISIONED), "transition_outside_read_order")

    def test_suspending_a_provisioned_tenant_is_refused(self) -> None:
        self.assertEqual(self.refusal(lc.SUSPEND, lc.PROVISIONED), "transition_outside_read_order")

    def test_an_archived_tenant_is_terminal_for_every_command(self) -> None:
        for command in lc.LIFECYCLE_COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(
                    self.refusal(command, lc.ARCHIVED), "transition_outside_read_order"
                )

    def test_provisioning_an_existing_tenant_is_refused(self) -> None:
        for state in (lc.PROVISIONED, lc.ACTIVE, lc.SUSPENDED, lc.ARCHIVED):
            with self.subTest(state=state):
                self.assertEqual(
                    self.refusal(lc.PROVISION, state), "transition_outside_read_order"
                )

    def test_every_pair_off_the_read_order_is_refused(self) -> None:
        """Exhaustive over the product of the vocabulary; only the four read pairs are admitted."""
        admitted = set()
        for command in lc.LIFECYCLE_COMMANDS:
            for state in lc.STATES:
                try:
                    lc.apply_command(command, state)
                except lc.LifecycleError:
                    continue
                admitted.add((command, state))
        self.assertEqual(
            admitted,
            {(command, from_state) for command, from_state, _ in lc._READ_ORDER},
        )
        self.assertEqual(len(admitted), 4)


class TestMalformedInputFailsClosed(LifecycleCase):
    def test_a_non_string_command_is_refused(self) -> None:
        for value in (None, 1, b"ProvisionTenant", ["ProvisionTenant"], object()):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(value), "bad_command")

    def test_a_string_subclass_cannot_smuggle_a_command_through(self) -> None:
        class Sneaky(str):
            pass

        self.assertEqual(self.refusal(Sneaky(lc.PROVISION)), "bad_command")

    def test_an_empty_or_over_long_command_is_refused(self) -> None:
        self.assertEqual(self.refusal(""), "bad_command")
        self.assertEqual(self.refusal("x" * (lc.TOKEN_MAX + 1)), "bad_command")

    def test_an_unknown_command_is_refused_as_unknown(self) -> None:
        self.assertEqual(self.refusal("RenameTenant"), "unknown_command")

    def test_a_non_string_state_is_refused(self) -> None:
        for value in (1, b"active", ["active"], object()):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(lc.ACTIVATE, value), "bad_state")

    def test_a_string_subclass_cannot_smuggle_a_state_through(self) -> None:
        class Sneaky(str):
            pass

        self.assertEqual(self.refusal(lc.ACTIVATE, Sneaky(lc.PROVISIONED)), "bad_state")

    def test_an_unknown_state_is_refused_as_unknown(self) -> None:
        self.assertEqual(self.refusal(lc.ACTIVATE, "pending"), "unknown_state")

    def test_the_lif03_states_are_unknown_here(self) -> None:
        """Named by section 10.53, outside PLT-01's scope, so refused not silently admitted."""
        for state in ("past due", "cancelled", "read-only"):
            with self.subTest(state=state):
                self.assertEqual(self.refusal(lc.ACTIVATE, state), "unknown_state")

    def test_the_command_is_judged_before_the_state(self) -> None:
        """A bad command and a bad state together report the command, so codes stay unambiguous."""
        self.assertEqual(self.refusal(None, "pending"), "bad_command")


class TestTheResultIsAFactNotAPermission(LifecycleCase):
    def test_the_transition_is_immutable(self) -> None:
        result = lc.apply_command(lc.PROVISION, None)
        with self.assertRaises(FrozenInstanceError):
            result.to_state = lc.ACTIVE  # type: ignore

    def test_the_transition_carries_no_approval_or_audit_field(self) -> None:
        """Paragraph 1231's approvals, retention checks and audit record are not decided here."""
        result = lc.apply_command(lc.ARCHIVE, lc.SUSPENDED)
        for absent in ("approved", "approval", "audit", "retention", "authorized", "actor"):
            with self.subTest(absent=absent):
                self.assertFalse(hasattr(result, absent))

    def test_the_command_is_returned_unchanged(self) -> None:
        result = lc.apply_command(lc.SUSPEND, lc.ACTIVE)
        self.assertEqual(result.command, lc.SUSPEND)

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "SmuggleThisCommandName"
        with self.assertRaises(lc.LifecycleError) as caught:
            lc.apply_command(secret, lc.ACTIVE)
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn(secret, caught.exception.code)

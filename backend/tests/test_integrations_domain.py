"""MOD-012 ECO-02 decisions, tested without a database.

The adapter contract, the connector lifecycle and the sync rules: what each refuses, and why
the refusal is the point rather than a formality.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.integrations import contract, lifecycle, sync

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def version(**kwargs: object) -> contract.DefinitionVersion:
    body: dict = {
        "definition_key": "acme.payments", "version": 1, "capabilities": ("payments",),
        "scopes": ("payments.charge", "payments.refund"),
        "required_scopes": ("payments.charge",),
        "config_fields": (contract.ConfigField(name="merchant_id", field_type="reference",
                                               required=True),),
        "regions": ("eu-west",),
    }
    body.update(kwargs)
    return contract.DefinitionVersion(**body)  # type: ignore[arg-type]


class ContractTests(unittest.TestCase):
    def test_a_credential_cannot_be_a_configuration_field(self) -> None:
        """There is no vault here, so a definition inviting a tenant to paste an API key into a
        config value would be inviting this build to store one in a table every list route
        reads. The absence of the type is the control."""
        self.assertNotIn("secret", contract.FIELD_TYPES)
        with self.assertRaises(contract.ContractError) as caught:
            contract.check_field(contract.ConfigField(name="api_key", field_type="secret"))
        self.assertIn("credential is not a configuration value", str(caught.exception))

    def test_a_required_scope_has_to_be_declared(self) -> None:
        with self.assertRaises(contract.ContractError):
            contract.check_version(version(required_scopes=("payments.settle",)))

    def test_a_capability_outside_the_closed_set_is_refused(self) -> None:
        with self.assertRaises(contract.ContractError):
            contract.check_version(version(capabilities=("teleportation",)))

    def test_a_later_version_may_not_drop_a_capability(self) -> None:
        """A tenant installed this definition *for* a capability; removing it turns their
        install into one that no longer does what they chose it for."""
        with self.assertRaises(contract.ContractError) as caught:
            contract.check_succession(
                version(capabilities=("payments", "accounting")),
                version(version=2, capabilities=("payments",)),
            )
        self.assertIn("silently stop doing it", str(caught.exception))

    def test_a_later_version_may_not_newly_require_configuration(self) -> None:
        """Every existing install has no value for it, so they all become invalid at once --
        discovered at the next sync rather than at publication."""
        with self.assertRaises(contract.ContractError):
            contract.check_succession(
                version(config_fields=()),
                version(version=2, config_fields=(
                    contract.ConfigField(name="webhook_url", field_type="string",
                                         required=True),)),
            )

    def test_a_later_version_may_not_newly_require_a_scope(self) -> None:
        """A connection authorized on the old set cannot satisfy it, and the install would read
        as active while being silently under-privileged."""
        with self.assertRaises(contract.ContractError):
            contract.check_succession(
                version(),
                version(version=2, required_scopes=("payments.charge", "payments.refund")),
            )

    def test_a_later_version_may_add_freely(self) -> None:
        contract.check_succession(
            version(),
            version(version=2, capabilities=("payments", "accounting"),
                    scopes=("payments.charge", "payments.refund", "accounting.read"),
                    config_fields=(
                        contract.ConfigField(name="merchant_id", field_type="reference",
                                             required=True),
                        contract.ConfigField(name="label", field_type="string"))),
        )

    def test_a_grant_is_checked_in_both_directions(self) -> None:
        with self.assertRaises(contract.ContractError):
            contract.check_grant(version(), ["payments.charge", "payments.settle"])
        with self.assertRaises(contract.ContractError):
            contract.check_grant(version(), ["payments.refund"])
        contract.check_grant(version(), ["payments.charge"])

    def test_configuration_is_checked_in_both_directions(self) -> None:
        with self.assertRaises(contract.ContractError):
            contract.check_config(version(), {})
        with self.assertRaises(contract.ContractError):
            contract.check_config(version(), {"merchant_id": "m", "extra": "x"})
        contract.check_config(version(), {"merchant_id": "m"})

    def test_an_enum_value_outside_the_set_is_refused(self) -> None:
        declared = version(config_fields=(
            contract.ConfigField(name="mode", field_type="enum", required=True,
                                 values=("live", "test")),))
        with self.assertRaises(contract.ContractError):
            contract.check_config(declared, {"mode": "sandbox"})
        contract.check_config(declared, {"mode": "test"})

    def test_a_region_the_definition_does_not_serve_is_refused(self) -> None:
        """Residency belongs to the definition's publisher, not to whoever is installing."""
        with self.assertRaises(contract.ContractError):
            contract.check_region(version(), "us-east")
        contract.check_region(version(), "eu-west")
        contract.check_region(version(regions=()), "anywhere")


class LifecycleTests(unittest.TestCase):
    def test_an_uninstalled_integration_cannot_come_back(self) -> None:
        """A state that could return from it means an integration somebody removed is one a
        later command can revive -- with the scopes it used to hold."""
        for target in lifecycle.INSTALL_STATES:
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.check_install_transition("uninstalled", target)

    def test_disabling_and_reactivating_is_the_ordinary_pair(self) -> None:
        lifecycle.check_install_transition("active", "disabled")
        lifecycle.check_install_transition("disabled", "active")

    def test_a_revoked_connection_is_terminal(self) -> None:
        for target in lifecycle.CONNECTION_STATES:
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.check_connection_transition("revoked", target)

    def test_revalidation_is_allowed_because_it_is_a_new_fact(self) -> None:
        lifecycle.check_connection_transition("validated", "validated")

    def test_a_connection_cannot_be_validated_before_it_is_authorized(self) -> None:
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_connection_transition("pending", "validated")

    def test_a_critical_integration_needs_all_three_obligations(self) -> None:
        base = {"criticality": "critical", "validated_connections": 1}
        for missing in ("has_fallback", "has_reconciliation", "has_exit_plan"):
            flags = {"has_fallback": True, "has_reconciliation": True, "has_exit_plan": True}
            flags[missing] = False
            with self.assertRaises(lifecycle.LifecycleError) as caught:
                lifecycle.check_activation(lifecycle.ActivationCheck(**base, **flags))
            self.assertIn(missing.removeprefix("has_"), str(caught.exception))

    def test_a_convenience_integration_needs_none_of_them(self) -> None:
        lifecycle.check_activation(lifecycle.ActivationCheck(
            criticality="convenience", has_fallback=False, has_reconciliation=False,
            has_exit_plan=False, validated_connections=1))

    def test_nothing_activates_without_a_validated_connection(self) -> None:
        """An active integration that cannot reach the provider is one whose failures read as
        the provider's."""
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.check_activation(lifecycle.ActivationCheck(
                criticality="convenience", has_fallback=True, has_reconciliation=True,
                has_exit_plan=True, validated_connections=0))

    def test_a_credential_with_no_expiry_is_never_due(self) -> None:
        """Inventing an expiry would produce a reminder about a date nobody set."""
        verdict = lifecycle.rotation_due(expires_at=None, now=NOW)
        self.assertFalse(verdict.due)
        self.assertIsNone(verdict.days_remaining)

    def test_the_lead_window_is_what_makes_a_credential_due(self) -> None:
        self.assertFalse(
            lifecycle.rotation_due(expires_at=NOW + timedelta(days=30), now=NOW).due)
        self.assertTrue(
            lifecycle.rotation_due(expires_at=NOW + timedelta(days=3), now=NOW).due)
        expired = lifecycle.rotation_due(expires_at=NOW - timedelta(days=1), now=NOW)
        self.assertTrue(expired.due)
        self.assertTrue(expired.expired)


class SyncTests(unittest.TestCase):
    def cursor(self, position: str, at: datetime) -> sync.Cursor:
        return sync.Cursor(resource="members", position=position, observed_at=at)

    def test_an_older_observation_cannot_advance_a_cursor(self) -> None:
        """A late or replayed run settling over a newer result makes the next sync re-read a
        window that was already read -- money with a provider that bills per call."""
        with self.assertRaises(sync.SyncError):
            sync.check_advance(self.cursor("b", NOW), self.cursor("a", NOW - timedelta(1)))
        sync.check_advance(self.cursor("a", NOW - timedelta(1)), self.cursor("b", NOW))

    def test_the_first_advance_has_nothing_to_compare_against(self) -> None:
        sync.check_advance(None, self.cursor("a", NOW))

    def test_a_blank_position_is_refused(self) -> None:
        with self.assertRaises(sync.SyncError):
            sync.check_advance(None, self.cursor("  ", NOW))

    def test_a_run_retries_until_its_budget_is_gone_and_then_quarantines(self) -> None:
        early = sync.failure_verdict(attempts=1, max_attempts=3, now=NOW)
        self.assertEqual(early.status, "failed")
        self.assertGreater(early.next_attempt_at, NOW)
        last = sync.failure_verdict(attempts=3, max_attempts=3, now=NOW)
        self.assertEqual(last.status, "dead")

    def test_the_backoff_grows(self) -> None:
        first = sync.failure_verdict(attempts=1, max_attempts=9, now=NOW).next_attempt_at
        later = sync.failure_verdict(attempts=4, max_attempts=9, now=NOW).next_attempt_at
        self.assertGreater(later, first)

    def test_a_reconciliation_cannot_match_more_than_exists(self) -> None:
        """`matched` above either count is a caller confusing an intersection with a total, and
        the difference would read as "the provider is ahead" on an unreproducible report."""
        with self.assertRaises(sync.SyncError):
            sync.check_reconciliation(sync.Reconciliation(local_count=5, provider_count=3,
                                                          matched=4))
        found = sync.check_reconciliation(
            sync.Reconciliation(local_count=5, provider_count=3, matched=3))
        self.assertEqual((found.local_only, found.provider_only), (2, 0))
        self.assertFalse(found.reconciled)

    def test_a_clean_reconciliation_says_so(self) -> None:
        found = sync.check_reconciliation(
            sync.Reconciliation(local_count=4, provider_count=4, matched=4))
        self.assertTrue(found.reconciled)

    def test_manual_refuses_to_pick_rather_than_picking_quietly(self) -> None:
        """A policy that silently picked under `manual` would be the worst of the three,
        because the tenant chose it precisely to be asked."""
        self.assertEqual(sync.conflict_resolution(policy="manual", local_changed=True,
                                                  provider_changed=True), "manual")
        self.assertEqual(sync.conflict_resolution(policy="local_wins", local_changed=True,
                                                  provider_changed=True), "local")
        self.assertEqual(sync.conflict_resolution(policy="provider_wins", local_changed=True,
                                                  provider_changed=True), "provider")

    def test_one_sided_changes_need_no_policy(self) -> None:
        for policy in sync.CONFLICT_POLICIES:
            self.assertEqual(sync.conflict_resolution(policy=policy, local_changed=True,
                                                      provider_changed=False), "local")
            self.assertEqual(sync.conflict_resolution(policy=policy, local_changed=False,
                                                      provider_changed=True), "provider")
            self.assertEqual(sync.conflict_resolution(policy=policy, local_changed=False,
                                                      provider_changed=False), "none")


if __name__ == "__main__":
    unittest.main()

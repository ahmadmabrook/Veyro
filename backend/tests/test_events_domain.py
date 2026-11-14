"""MOD-010 DAT-01: the catalogue and the dispatch decisions, with no database.

These are the parts that can be wrong without any row existing: an event type whose payload
carries something it should not, a version that drops a field a consumer reads, a backoff that
schedules the next attempt in a year, a replay that re-sends a month of messages because two
policies were read as one.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from app.events import catalog, dispatch


class CatalogShapeTests(unittest.TestCase):
    def test_every_declared_event_is_well_formed(self):
        for (name, version), event in catalog.EVENT_TYPES.items():
            self.assertEqual(event.name, name)
            self.assertEqual(event.version, version)
            self.assertTrue(catalog.EVENT_NAME.fullmatch(name), name)
            self.assertTrue(event.fields, name)
            self.assertTrue(event.description.strip(), name)
            self.assertIn(event.status, catalog.STATUSES, name)
            self.assertRegex(event.owner_module, r"^MOD-\d{3}$")

    def test_the_catalogue_covers_every_module_that_has_one(self):
        """The event lists come from the TSD's own "Published events" line per module. If a
        module is built and emits nothing, that is a gap worth seeing rather than inferring."""
        owners = {e.owner_module for e in catalog.EVENT_TYPES.values()}
        self.assertEqual(
            owners,
            {"MOD-004", "MOD-005", "MOD-007", "MOD-008", "MOD-009", "MOD-010",
             "MOD-011", "MOD-012", "MOD-013", "MOD-014", "MOD-015"},
        )

    def test_an_unknown_event_type_cannot_be_looked_up(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.require_event("tenant.exploded", 1)
        with self.assertRaises(catalog.CatalogError):
            catalog.require_event("tenant.provisioned", 99)
        with self.assertRaises(catalog.CatalogError):
            catalog.latest("nothing.at.all")

    def test_a_bad_name_is_refused_at_declaration(self):
        for bad in ("Tenant.Provisioned", "tenant", "tenant..provisioned", "tenant provisioned"):
            with self.assertRaises(catalog.CatalogError, msg=bad):
                catalog._e(bad, 1, "MOD-004", "internal", ("a",), "d")

    def test_a_restricted_field_cannot_travel_in_a_payload(self):
        """An event is fanned out, archived and replayed, so a restricted field in one is in
        more places than the same field anywhere else -- and the deletion-reachability registry
        reaches none of them. Carry the identifier, not the value."""
        for field in ("national_id", "iban", "health_notes", "biometric_template"):
            with self.assertRaises(catalog.CatalogError, msg=field) as caught:
                catalog._e("member.updated", 1, "MOD-014", "confidential", (field,), "d")
            self.assertIn("identifier instead", str(caught.exception))

    def test_a_contact_field_is_allowed_because_it_is_not_restricted(self):
        """The line is drawn at restricted, not at "anything sensitive". A confirmation email
        has to carry an address somewhere, and a rule that forbade it would be worked around."""
        _, event = catalog._e("member.invited", 1, "MOD-014", "confidential", ("email",), "d")
        self.assertEqual(event.fields, ("email",))

    def test_a_duplicate_or_empty_field_list_is_refused(self):
        with self.assertRaises(catalog.CatalogError):
            catalog._e("a.b", 1, "MOD-004", "internal", (), "d")
        with self.assertRaises(catalog.CatalogError):
            catalog._e("a.b", 1, "MOD-004", "internal", ("x", "x"), "d")


class CompatibilityTests(unittest.TestCase):
    """The policy TSD paragraph 3245 asks for, enforced where somebody would write the change."""

    def _check(self, types):
        original = dict(catalog.EVENT_TYPES)
        try:
            catalog.EVENT_TYPES.clear()
            catalog.EVENT_TYPES.update(types)
            catalog._check_compatibility()
        finally:
            catalog.EVENT_TYPES.clear()
            catalog.EVENT_TYPES.update(original)

    def test_the_shipped_catalogue_is_compatible(self):
        catalog._check_compatibility()

    def test_a_later_version_may_add_a_field(self):
        self._check(dict([
            catalog._e("a.b", 1, "MOD-004", "internal", ("x",), "d"),
            catalog._e("a.b", 2, "MOD-004", "internal", ("x", "y"), "d"),
        ]))

    def test_a_later_version_may_not_drop_a_field(self):
        """A consumer on v1 reads the dropped field as absent rather than wrong, which is why
        this has to be refused at the catalogue instead of noticed in production."""
        with self.assertRaises(catalog.CatalogError) as caught:
            self._check(dict([
                catalog._e("a.b", 1, "MOD-004", "internal", ("x", "y"), "d"),
                catalog._e("a.b", 2, "MOD-004", "internal", ("x",), "d"),
            ]))
        self.assertIn("drops ['y']", str(caught.exception))

    def test_versions_must_start_at_one_and_be_contiguous(self):
        with self.assertRaises(catalog.CatalogError):
            self._check(dict([catalog._e("a.b", 2, "MOD-004", "internal", ("x",), "d")]))
        with self.assertRaises(catalog.CatalogError):
            self._check(dict([
                catalog._e("a.b", 1, "MOD-004", "internal", ("x",), "d"),
                catalog._e("a.b", 3, "MOD-004", "internal", ("x",), "d"),
            ]))

    def test_a_deprecated_version_must_name_its_successor(self):
        """Deprecation with nowhere to migrate to is a consumer stranded on a version somebody
        has already stopped maintaining."""
        with self.assertRaises(catalog.CatalogError) as caught:
            self._check(dict([
                catalog._e("a.b", 1, "MOD-004", "internal", ("x",), "d", "deprecated"),
                catalog._e("a.b", 2, "MOD-004", "internal", ("x",), "d"),
            ]))
        self.assertIn("nowhere to migrate", str(caught.exception))

    def test_a_successor_that_does_not_exist_is_refused(self):
        with self.assertRaises(catalog.CatalogError):
            self._check(dict([
                catalog._e("a.b", 1, "MOD-004", "internal", ("x",), "d", "deprecated", 7),
            ]))

    def test_latest_skips_a_deprecated_version(self):
        original = dict(catalog.EVENT_TYPES)
        try:
            catalog.EVENT_TYPES.clear()
            catalog.EVENT_TYPES.update(dict([
                catalog._e("a.b", 1, "MOD-004", "internal", ("x",), "d"),
                catalog._e("a.b", 2, "MOD-004", "internal", ("x",), "d", "deprecated", 1),
            ]))
            self.assertEqual(catalog.latest("a.b").version, 1)
            self.assertEqual(len(catalog.deprecated_types()), 1)
        finally:
            catalog.EVENT_TYPES.clear()
            catalog.EVENT_TYPES.update(original)


class PayloadTests(unittest.TestCase):
    def test_a_payload_must_be_exactly_the_declared_fields(self):
        catalog.validate_payload("tenant.activated", 1,
                                 {"tenant_id": "t", "from_status": "provisioned"})

    def test_an_undeclared_key_is_refused(self):
        """Data in an event is in every consumer, the archive and every later replay. A field
        nobody approved travelling there is the leak that is hardest to take back."""
        with self.assertRaises(catalog.CatalogError) as caught:
            catalog.validate_payload("tenant.activated", 1,
                                     {"tenant_id": "t", "from_status": "p", "secret": "x"})
        self.assertIn("does not declare ['secret']", str(caught.exception))

    def test_a_missing_key_is_refused(self):
        with self.assertRaises(catalog.CatalogError) as caught:
            catalog.validate_payload("tenant.activated", 1, {"tenant_id": "t"})
        self.assertIn("requires ['from_status']", str(caught.exception))

    def test_classification_and_owner_are_answerable_per_event(self):
        self.assertEqual(catalog.owner_module("consent.granted", 1), "MOD-009")
        self.assertEqual(catalog.classification("consent.granted", 1), "confidential")
        self.assertEqual(catalog.classification("tenant.provisioned", 1), "internal")


class BackoffTests(unittest.TestCase):
    def test_backoff_grows_and_is_capped(self):
        self.assertEqual(dispatch.backoff_seconds(0), timedelta(seconds=2))
        self.assertEqual(dispatch.backoff_seconds(1), timedelta(seconds=4))
        self.assertEqual(dispatch.backoff_seconds(2), timedelta(seconds=8))
        self.assertEqual(dispatch.backoff_seconds(60), timedelta(hours=1))

    def test_a_large_attempt_count_does_not_overflow_or_run_away(self):
        """Without the cap, attempt 40 is scheduled for some time next year and the delivery
        reads as pending for ever rather than as dead."""
        self.assertEqual(dispatch.backoff_seconds(1000), timedelta(hours=1))

    def test_a_negative_attempt_count_is_refused(self):
        with self.assertRaises(dispatch.DispatchError):
            dispatch.backoff_seconds(-1)


class AfterFailureTests(unittest.TestCase):
    def test_a_failure_inside_the_budget_retries_with_backoff(self):
        verdict = dispatch.after_failure(attempts=0, max_attempts=5, error="boom")
        self.assertEqual(verdict.status, "pending")
        self.assertEqual(verdict.attempts, 1)
        self.assertEqual(verdict.wait, timedelta(seconds=4))

    def test_the_last_allowed_attempt_dead_letters(self):
        """The off-by-one between "attempts made" and "attempts allowed" is how a consumer gets
        one more try than its budget, or one fewer. Asserted at the boundary on purpose."""
        self.assertEqual(
            dispatch.after_failure(attempts=3, max_attempts=5, error="boom").status, "pending")
        verdict = dispatch.after_failure(attempts=4, max_attempts=5, error="boom")
        self.assertEqual(verdict.status, "dead")
        self.assertEqual(verdict.attempts, 5)
        self.assertEqual(verdict.wait, timedelta(0))

    def test_a_single_attempt_budget_dead_letters_immediately(self):
        verdict = dispatch.after_failure(attempts=0, max_attempts=1, error="boom")
        self.assertEqual(verdict.status, "dead")
        self.assertEqual(verdict.attempts, 1)

    def test_a_failure_must_say_why(self):
        for blank in ("", "   "):
            with self.assertRaises(dispatch.DispatchError):
                dispatch.after_failure(attempts=0, max_attempts=5, error=blank)

    def test_a_zero_budget_is_refused(self):
        with self.assertRaises(dispatch.DispatchError):
            dispatch.after_failure(attempts=0, max_attempts=0, error="boom")


class ReplayActionTests(unittest.TestCase):
    """Two statements about different things, which have to agree before an effect re-runs."""

    def test_a_suppress_consumer_is_not_delivered_under_the_default_policy(self):
        """This is the case the whole feature exists to prevent: replaying a month of
        `saas.payment.failed` into a consumer that sends email."""
        self.assertEqual(
            dispatch.replay_action(replay_safety="suppress", side_effects="suppress"),
            "suppress")

    def test_a_safe_consumer_is_delivered_under_the_default_policy(self):
        """Rebuilding a projection is the ordinary use of replay. A rule that suppressed it
        would make the feature useless."""
        self.assertEqual(
            dispatch.replay_action(replay_safety="safe", side_effects="suppress"), "deliver")

    def test_an_idempotent_consumer_is_delivered_under_the_default_policy(self):
        self.assertEqual(
            dispatch.replay_action(replay_safety="idempotent", side_effects="suppress"),
            "deliver")

    def test_allow_overrides_the_consumers_own_caution(self):
        """The escape hatch -- "yes, really send those again" -- which the schema makes carry a
        written reason."""
        for safety in dispatch.REPLAY_SAFETY:
            self.assertEqual(
                dispatch.replay_action(replay_safety=safety, side_effects="allow"),
                "deliver", safety)

    def test_an_unknown_class_or_policy_is_refused_rather_than_defaulted(self):
        with self.assertRaises(dispatch.DispatchError):
            dispatch.replay_action(replay_safety="probably_fine", side_effects="suppress")
        with self.assertRaises(dispatch.DispatchError):
            dispatch.replay_action(replay_safety="safe", side_effects="whatever")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

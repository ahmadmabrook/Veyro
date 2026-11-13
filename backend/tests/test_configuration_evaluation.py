"""MOD-005 PLT-02 evaluation: the decisions, with no database in the way.

These run everywhere, including without a DSN, because the module under test is pure. The
integration suite in `test_configuration_api.py` checks that the service feeds it the right rows;
this file checks that the answers are right.
"""

import unittest

from app.configuration import evaluation as ev

TENANT = "11111111-1111-4111-8111-111111111111"
OTHER_TENANT = "22222222-2222-4222-8222-222222222222"


class BucketTests(unittest.TestCase):
    def test_bucket_is_in_range_and_stable(self):
        for subject in (f"user-{i}" for i in range(200)):
            drawn = ev.bucket(TENANT, "a.flag", "rule-1", subject)
            self.assertTrue(0 <= drawn < ev.BUCKETS)
            self.assertEqual(drawn, ev.bucket(TENANT, "a.flag", "rule-1", subject))

    def test_bucket_is_roughly_uniform(self):
        """A rollout percentage is a lie if the hash clumps. 20000 draws, 10 deciles."""
        deciles = [0] * 10
        for i in range(20_000):
            deciles[ev.bucket(TENANT, "a.flag", "rule-1", f"user-{i}") // 1000] += 1
        for count in deciles:
            self.assertGreater(count, 1_700, deciles)
            self.assertLess(count, 2_300, deciles)

    def test_separate_rules_select_different_subsets(self):
        """Two rules at 50% must not pick the same half, or layered rollouts would be useless."""
        a = {s for i in range(2_000) if ev.bucket(TENANT, "f", "rule-a", s := f"u{i}") < 5_000}
        b = {s for i in range(2_000) if ev.bucket(TENANT, "f", "rule-b", s := f"u{i}") < 5_000}
        overlap = len(a & b) / max(len(a | b), 1)
        self.assertLess(overlap, 0.45, "rule ids are not separating the subsets")

    def test_tenants_do_not_correlate(self):
        a = {s for i in range(2_000) if ev.bucket(TENANT, "f", "r", s := f"u{i}") < 5_000}
        b = {s for i in range(2_000) if ev.bucket(OTHER_TENANT, "f", "r", s := f"u{i}") < 5_000}
        self.assertLess(len(a & b) / max(len(a | b), 1), 0.45)

    def test_parts_cannot_be_shifted_across_the_separator(self):
        self.assertNotEqual(ev.bucket("ab", "c"), ev.bucket("a", "bc"))


class ValidateValueTests(unittest.TestCase):
    def test_each_type_accepts_its_own_and_rejects_a_string(self):
        for value_type, good in (
            ("boolean", True), ("integer", 3), ("number", 1.5), ("string", "x"),
            ("json", {"a": 1}),
        ):
            ev.validate_value(value_type, {}, good)
        for value_type in ("boolean", "integer", "number"):
            with self.assertRaises(ev.ValidationError):
                ev.validate_value(value_type, {}, "not a number")

    def test_boolean_is_not_an_integer(self):
        """True == 1 in Python. An integer definition that accepts True is a latent bug."""
        with self.assertRaises(ev.ValidationError) as caught:
            ev.validate_value("integer", {}, True)
        self.assertEqual(caught.exception.code, "type_mismatch")
        with self.assertRaises(ev.ValidationError):
            ev.validate_value("number", {}, False)

    def test_unknown_constraints_are_refused_not_ignored(self):
        with self.assertRaises(ev.ValidationError) as caught:
            ev.validate_value("integer", {"multipleOf": 2}, 4)
        self.assertEqual(caught.exception.code, "unknown_constraint")

    def test_enum_minimum_maximum_and_max_length(self):
        ev.validate_value("string", {"enum": ["a", "b"]}, "a")
        with self.assertRaises(ev.ValidationError):
            ev.validate_value("string", {"enum": ["a", "b"]}, "c")
        ev.validate_value("integer", {"minimum": 1, "maximum": 10}, 10)
        with self.assertRaises(ev.ValidationError):
            ev.validate_value("integer", {"minimum": 1}, 0)
        with self.assertRaises(ev.ValidationError):
            ev.validate_value("integer", {"maximum": 10}, 11)
        with self.assertRaises(ev.ValidationError):
            ev.validate_value("string", {"max_length": 2}, "abc")

    def test_constraints_need_an_applicable_type(self):
        for value_type, validation in (("string", {"minimum": 1}), ("integer", {"max_length": 2})):
            with self.assertRaises(ev.ValidationError) as caught:
                ev.validate_value(value_type, validation, "x" if value_type == "string" else 1)
            self.assertEqual(caught.exception.code, "constraint_not_applicable")

    def test_unknown_value_type_is_refused(self):
        with self.assertRaises(ev.ValidationError):
            ev.validate_value("timestamp", {}, "now")


BRAND = "b1"
LOCATION = "l1"


def _row(scope_type, value, version, brand=None, location=None):
    return ev.ValueRow(scope_type=scope_type, brand_id=brand, location_id=location,
                       value=value, version=version)


class ResolveValueTests(unittest.TestCase):
    def test_default_is_used_when_nothing_is_published(self):
        got = ev.resolve_value(7, [])
        self.assertEqual((got.value, got.scope_type, got.version), (7, "default", None))

    def test_more_specific_scope_wins(self):
        rows = [
            _row("tenant", "t", 1),
            _row("brand", "b", 1, brand=BRAND),
            _row("location", "l", 1, location=LOCATION),
        ]
        self.assertEqual(ev.resolve_value("d", rows).value, "t")
        self.assertEqual(ev.resolve_value("d", rows, brand_id=BRAND).value, "b")
        self.assertEqual(
            ev.resolve_value("d", rows, brand_id=BRAND, location_id=LOCATION).value, "l"
        )

    def test_highest_version_wins_within_a_scope(self):
        """Versions arrive in no particular order; the newest must win regardless."""
        rows = [_row("tenant", "v2", 2), _row("tenant", "v1", 1), _row("tenant", "v3", 3)]
        got = ev.resolve_value("d", rows)
        self.assertEqual((got.value, got.version), ("v3", 3))

    def test_another_brands_row_is_not_picked_up(self):
        rows = [_row("tenant", "t", 1), _row("brand", "other", 1, brand="b2")]
        self.assertEqual(ev.resolve_value("d", rows, brand_id=BRAND).value, "t")

    def test_a_rollback_version_outranks_what_it_replaced(self):
        """Rollback republishes the old payload at a higher version; it must win."""
        rows = [_row("tenant", "good", 1), _row("tenant", "bad", 2), _row("tenant", "good", 3)]
        got = ev.resolve_value("d", rows)
        self.assertEqual((got.value, got.version), ("good", 3))


def _flag(**kw):
    base = dict(flag_key="pay.new_provider", enabled=True, default_variant="off",
                kill_switch_engaged=False, version=1)
    return ev.Flag(**{**base, **kw})


class EvaluateFlagTests(unittest.TestCase):
    def evaluate(self, flag, rules, context=None, subject="user-1"):
        return ev.evaluate_flag(flag, rules, context=context or {}, subject_id=subject,
                                tenant_id=TENANT)

    def test_kill_switch_beats_an_enabled_flag_and_a_full_rollout_rule(self):
        rule = ev.Rule(rule_id="r1", priority=1, variant="on")
        got = self.evaluate(_flag(kill_switch_engaged=True), [rule])
        self.assertEqual((got.variant, got.reason), ("off", "kill_switch"))

    def test_disabled_flag_returns_its_default_variant(self):
        got = self.evaluate(_flag(enabled=False, default_variant="legacy"), [])
        self.assertEqual((got.variant, got.reason), ("legacy", "disabled"))

    def test_full_rollout_rule_applies_to_everyone(self):
        rule = ev.Rule(rule_id="r1", priority=1, variant="on")
        for i in range(50):
            self.assertEqual(self.evaluate(_flag(), [rule], subject=f"u{i}").variant, "on")

    def test_zero_rollout_rule_applies_to_nobody(self):
        rule = ev.Rule(rule_id="r1", priority=1, variant="on", rollout_bp=0)
        for i in range(50):
            got = self.evaluate(_flag(), [rule], subject=f"u{i}")
            self.assertEqual((got.variant, got.reason), ("off", "default"))

    def test_targeting_needs_every_named_attribute_to_match(self):
        rule = ev.Rule(rule_id="r1", priority=1, variant="on", match={"plan": "pro"})
        self.assertEqual(self.evaluate(_flag(), [rule], {"plan": "pro"}).variant, "on")
        self.assertEqual(self.evaluate(_flag(), [rule], {"plan": "free"}).variant, "off")
        self.assertEqual(self.evaluate(_flag(), [rule], {}).variant, "off",
                         "an absent attribute must not act as a wildcard")

    def test_lower_priority_number_is_evaluated_first(self):
        first = ev.Rule(rule_id="r2", priority=1, variant="first")
        second = ev.Rule(rule_id="r1", priority=2, variant="second")
        self.assertEqual(self.evaluate(_flag(), [second, first]).variant, "first")

    def test_a_subject_outside_a_partial_rollout_falls_through_to_the_next_rule(self):
        narrow = ev.Rule(rule_id="r1", priority=1, variant="new", rollout_bp=1)
        fallback = ev.Rule(rule_id="r2", priority=2, variant="fallback")
        variants = {self.evaluate(_flag(), [narrow, fallback], subject=f"u{i}").variant
                    for i in range(200)}
        self.assertIn("fallback", variants)
        self.assertNotIn("off", variants, "the second rule must catch what the first did not")

    def test_partial_rollout_hits_about_the_requested_share(self):
        rule = ev.Rule(rule_id="r1", priority=1, variant="on", rollout_bp=2_500)
        on = sum(self.evaluate(_flag(), [rule], subject=f"u{i}").variant == "on"
                 for i in range(4_000))
        self.assertTrue(850 <= on <= 1_150, on)

    def test_evaluation_is_deterministic(self):
        rule = ev.Rule(rule_id="r1", priority=1, variant="on", rollout_bp=5_000)
        first = [self.evaluate(_flag(), [rule], subject=f"u{i}").variant for i in range(100)]
        again = [self.evaluate(_flag(), [rule], subject=f"u{i}").variant for i in range(100)]
        self.assertEqual(first, again)

    def test_reason_names_the_deciding_rule(self):
        rule = ev.Rule(rule_id="r1", priority=1, variant="on")
        got = self.evaluate(_flag(), [rule])
        self.assertEqual((got.reason, got.rule_id), ("rule:r1", "r1"))


class AssignVariantTests(unittest.TestCase):
    def experiment(self, status="running"):
        return ev.Experiment(experiment_key="checkout.copy", status=status, salt="s1")

    def assign(self, exp, variants, subject="u1"):
        return ev.assign_variant(exp, variants, subject_id=subject, tenant_id=TENANT)

    def test_a_draft_or_completed_experiment_assigns_nobody(self):
        variants = [ev.Variant("a", 1), ev.Variant("b", 1)]
        for status in ("draft", "completed"):
            self.assertIsNone(self.assign(self.experiment(status), variants))

    def test_no_variants_assigns_nobody(self):
        self.assertIsNone(self.assign(self.experiment(), []))

    def test_assignment_is_stable_for_a_subject(self):
        variants = [ev.Variant("a", 1), ev.Variant("b", 1)]
        for i in range(100):
            got = self.assign(self.experiment(), variants, f"u{i}")
            self.assertEqual(got, self.assign(self.experiment(), variants, f"u{i}"))

    def test_weights_shape_the_split(self):
        variants = [ev.Variant("control", 9), ev.Variant("treatment", 1)]
        treated = sum(self.assign(self.experiment(), variants, f"u{i}") == "treatment"
                      for i in range(4_000))
        self.assertTrue(250 <= treated <= 550, treated)

    def test_every_subject_lands_on_a_declared_variant(self):
        variants = [ev.Variant("a", 3), ev.Variant("b", 5), ev.Variant("c", 2)]
        keys = {v.variant_key for v in variants}
        for i in range(500):
            self.assertIn(self.assign(self.experiment(), variants, f"u{i}"), keys)

    def test_order_the_rows_arrive_in_does_not_change_the_answer(self):
        forward = [ev.Variant("a", 1), ev.Variant("b", 1), ev.Variant("c", 1)]
        for i in range(100):
            self.assertEqual(
                self.assign(self.experiment(), forward, f"u{i}"),
                self.assign(self.experiment(), list(reversed(forward)), f"u{i}"),
            )


if __name__ == "__main__":
    unittest.main()

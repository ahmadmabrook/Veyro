"""MOD-016 COM-02: the decision modules, with no database anywhere.

The two tests that matter most are the ones about paragraph 10220's control: that resolution is
deterministic whatever order the inputs arrive in, and that the explanation names every step
including the rejections. Everything else here protects a smaller rule.
"""

from __future__ import annotations

import random
import unittest
from datetime import UTC, date, datetime

from app.catalog import bundles, pricing, products, promotions

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def book(key: str, **kwargs: object) -> pricing.PriceBook:
    body: dict = {"price_book_id": f"book-{key}", "price_book_key": key,
                  "currency": "JOD", "effective_from": datetime(2026, 1, 1, tzinfo=UTC)}
    body.update(kwargs)
    return pricing.PriceBook(**body)  # type: ignore[arg-type]


def price(book_key: str, amount: int, **kwargs: object) -> pricing.Price:
    body: dict = {"price_id": f"price-{book_key}-{amount}",
                  "price_book_id": f"book-{book_key}", "variant_id": "v1",
                  "amount_minor": amount, "currency": "JOD",
                  "effective_from": datetime(2026, 1, 1, tzinfo=UTC)}
    body.update(kwargs)
    return pricing.Price(**body)  # type: ignore[arg-type]


def request(**kwargs: object) -> pricing.Request:
    body: dict = {"variant_id": "v1", "currency": "JOD", "at": NOW}
    body.update(kwargs)
    return pricing.Request(**body)  # type: ignore[arg-type]


def promotion(key: str, **kwargs: object) -> promotions.Promotion:
    body: dict = {"promotion_key": key, "kind": "automatic", "percent_bp": 1000}
    body.update(kwargs)
    return promotions.Promotion(**body)  # type: ignore[arg-type]


class BookMatchingTests(unittest.TestCase):
    def test_a_dimension_the_book_sets_must_match_and_scores(self):
        """A book for the `pos` channel is not a candidate for a `member_app` sale."""
        pos = book("pos", channel="pos")
        self.assertEqual(book_specificity_of(pos, request(channel="pos")), 1)
        self.assertIsNone(book_specificity_of(pos, request(channel="member_app")))

    def test_a_dimension_left_wide_matches_anything_and_scores_nothing(self):
        """Scoring the wide match would make a book that specifies nothing beat one that
        specifies a brand, which is backwards."""
        wide = book("wide")
        self.assertEqual(book_specificity_of(wide, request(channel="pos")), 0)
        self.assertEqual(book_specificity_of(wide, request(channel="web")), 0)

    def test_a_draft_or_expired_or_wrong_currency_book_is_no_candidate(self):
        self.assertIsNone(book_specificity_of(book("d", status="draft"), request()))
        self.assertIsNone(
            book_specificity_of(book("e", effective_to=datetime(2026, 2, 1, tzinfo=UTC)),
                                request()))
        self.assertIsNone(
            book_specificity_of(book("f", effective_from=datetime(2027, 1, 1, tzinfo=UTC)),
                                request()))
        self.assertIsNone(book_specificity_of(book("g", currency="USD"), request()))

    def test_the_most_specific_book_wins_then_priority_then_the_key(self):
        chosen, steps = pricing.choose_book(
            [book("wide"), book("pos", channel="pos"),
             book("pos_low", channel="pos", priority=-5)],
            request(channel="pos"))
        self.assertEqual(chosen.price_book_key, "pos")
        self.assertTrue(any("price_book_chosen" in s.code for s in steps))
        self.assertTrue(any("price_book_not_chosen" in s.code for s in steps))

    def test_the_choice_does_not_depend_on_the_order_the_books_arrive_in(self):
        """**Determinism, which is the requirement.** A resolver whose answer depended on row
        order fails in the way nobody notices until two tills disagree."""
        candidates = [book("a", channel="pos"), book("b", channel="pos"),
                      book("c", channel="pos", priority=3), book("wide")]
        answers = set()
        rng = random.Random(7)
        for _ in range(20):
            shuffled = candidates[:]
            rng.shuffle(shuffled)
            answers.add(pricing.choose_book(shuffled, request(channel="pos"))[0].price_book_key)
        self.assertEqual(answers, {"c"})

    def test_no_matching_book_is_a_refusal_rather_than_a_guess(self):
        with self.assertRaises(pricing.PricingError):
            pricing.choose_book([book("usd", currency="USD")], request())


def book_specificity_of(b: pricing.PriceBook, r: pricing.Request) -> int | None:
    return pricing.book_specificity(b, r)


class PriceSelectionTests(unittest.TestCase):
    def test_the_latest_start_at_or_before_the_moment_wins(self):
        """This is what makes COM-02-R07 work: re-pricing writes a new row and an order
        resolved last March re-derives by asking with March's timestamp."""
        old = price("a", 5000, price_id="old",
                    effective_from=datetime(2026, 1, 1, tzinfo=UTC))
        new = price("a", 6000, price_id="new",
                    effective_from=datetime(2026, 5, 1, tzinfo=UTC))
        chosen = pricing.choose_price([old, new], book("a"), request())
        self.assertEqual(chosen.price_id, "new")
        march = pricing.choose_price(
            [old, new], book("a"), request(at=datetime(2026, 3, 1, tzinfo=UTC)))
        self.assertEqual(march.price_id, "old")

    def test_a_superseded_price_is_skipped_even_inside_its_window(self):
        withdrawn = price("a", 9999, price_id="bad", superseded_by="good")
        good = price("a", 5000, price_id="good")
        self.assertEqual(
            pricing.choose_price([withdrawn, good], book("a"), request()).price_id, "good")

    def test_no_price_in_force_is_a_refusal(self):
        with self.assertRaises(pricing.PricingError):
            pricing.choose_price([], book("a"), request())
        future = price("a", 100, effective_from=datetime(2027, 1, 1, tzinfo=UTC))
        with self.assertRaises(pricing.PricingError):
            pricing.choose_price([future], book("a"), request())


class ResolutionTests(unittest.TestCase):
    def test_a_resolution_explains_every_step(self):
        """Paragraph 10220. A resolver that returned a number and no reasoning would be
        impossible to dispute at a counter, which is where these are read out loud."""
        resolved = pricing.resolve(
            request=request(quantity=2), books=[book("a")], prices=[price("a", 2500)])
        self.assertEqual(resolved.list_amount_minor, 5000)
        self.assertEqual(resolved.final_amount_minor, 5000)
        codes = [s.code for s in resolved.steps]
        self.assertIn("price_book_chosen", codes)
        self.assertIn("list_price", codes)
        self.assertIn("final_amount", codes)
        self.assertTrue(all(isinstance(line, str) for line in resolved.explanation))

    def test_the_parts_add_up(self):
        resolved = pricing.resolve(
            request=request(), books=[book("a")], prices=[price("a", 10000)],
            discounts=[("ten", 1000, [])])
        self.assertEqual(
            resolved.final_amount_minor,
            resolved.list_amount_minor - resolved.discount_minor)
        self.assertEqual(resolved.discount_bp, 1000)

    def test_a_discount_larger_than_the_line_is_clamped_and_said_so(self):
        """Two promotions that between them exceed the price is a real configuration, and a
        negative total is an arithmetic failure an invoice is one unit from being wrong about."""
        resolved = pricing.resolve(
            request=request(), books=[book("a")], prices=[price("a", 1000)],
            discounts=[("big", 5000, [])])
        self.assertEqual(resolved.discount_minor, 1000)
        self.assertEqual(resolved.final_amount_minor, 0)
        self.assertTrue(any(s.code == "discount_clamped" for s in resolved.steps))

    def test_a_zero_discount_is_recorded_as_rejected_rather_than_applied(self):
        resolved = pricing.resolve(
            request=request(), books=[book("a")], prices=[price("a", 1000)],
            discounts=[("nothing", 0, [])])
        self.assertEqual(resolved.applied_promotions, ())
        self.assertEqual(resolved.rejected_promotions, ("nothing",))

    def test_a_quantity_below_one_and_an_unknown_channel_are_refused(self):
        with self.assertRaises(pricing.PricingError):
            pricing.resolve(request=request(quantity=0), books=[book("a")],
                            prices=[price("a", 100)])
        with self.assertRaises(pricing.PricingError):
            pricing.resolve(request=request(channel="carrier_pigeon"), books=[book("a")],
                            prices=[price("a", 100)])


class OverrideTests(unittest.TestCase):
    def base(self) -> pricing.Resolution:
        return pricing.resolve(
            request=request(), books=[book("a")], prices=[price("a", 10000)])

    def test_an_override_keeps_the_whole_explanation_and_adds_its_own_step(self):
        """Folding it into the promotion list would make a manual decision indistinguishable
        from a campaign on the receipt, which is what the audit requirement exists to prevent."""
        done = pricing.override(self.base(), override_amount_minor=7500,
                                reason="long-standing member")
        self.assertEqual(done.final_amount_minor, 7500)
        self.assertEqual(done.discount_minor, 2500)
        self.assertEqual(done.discount_bp, 2500)
        self.assertEqual(done.applied_promotions, ())
        self.assertTrue(any(s.code == "manual_override" for s in done.steps))
        self.assertIn("long-standing member", " ".join(done.explanation))

    def test_an_override_upwards_is_refused(self):
        """Charging more than the catalogue says is a different act, and nothing in COM-02 asks
        for it."""
        with self.assertRaises(pricing.PricingError):
            pricing.override(self.base(), override_amount_minor=20000, reason="because")

    def test_an_override_states_a_reason_and_is_not_negative(self):
        with self.assertRaises(pricing.PricingError):
            pricing.override(self.base(), override_amount_minor=100, reason="   ")
        with self.assertRaises(pricing.PricingError):
            pricing.override(self.base(), override_amount_minor=-1, reason="x")

    def test_a_threshold_of_zero_never_demands_approval(self):
        """Otherwise every undiscounted sale in the tenant would need one."""
        plain = self.base()
        self.assertFalse(pricing.needs_approval(plain, 0))
        deep = pricing.override(plain, override_amount_minor=0, reason="free")
        self.assertFalse(pricing.needs_approval(deep, 0))
        self.assertTrue(pricing.needs_approval(deep, 5000))


class EligibilityTests(unittest.TestCase):
    def check(self, promo: promotions.Promotion, **kwargs: object) -> promotions.Eligibility:
        body: dict = {"subtotal_minor": 10000, "currency": "JOD", "channel": "pos",
                      "customer_segment": "any", "product_type": "service", "at": NOW,
                      "usage": promotions.Usage(subject_known=True)}
        body.update(kwargs)
        return promotions.check_eligibility(promo, **body)  # type: ignore[arg-type]

    def test_a_rejection_names_the_rule_and_the_numbers(self):
        """"Not eligible" is useless to the person being asked why the code did not work."""
        promo = promotion("spend", rules=(
            promotions.Rule("minimum_spend", amount_minor=50000),))
        verdict = self.check(promo)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.code, promotions.MINIMUM_SPEND_NOT_MET)
        self.assertIn("50000", verdict.reason)
        self.assertIn("10000", verdict.reason)

    def test_each_rule_kind_refuses_for_its_own_reason(self):
        cases = [
            (promotions.Rule("customer_segment", text_value="corporate"), "segment"),
            (promotions.Rule("product_type", text_value="membership"), "membership"),
            (promotions.Rule("channel", text_value="web"), "channel"),
            (promotions.Rule("blackout_dates", date_from=date(2026, 5, 1),
                             date_to=date(2026, 7, 1)), "blacked out"),
        ]
        for rule, fragment in cases:
            verdict = self.check(promotion("p", rules=(rule,)))
            self.assertFalse(verdict.ok, rule.kind)
            self.assertIn(fragment, verdict.reason)

    def test_a_usage_limit_counts_from_the_ledger(self):
        promo = promotion("limited", rules=(
            promotions.Rule("max_total_redemptions", quantity=2),))
        self.assertTrue(self.check(
            promo, usage=promotions.Usage(total=1, subject_known=True)).ok)
        verdict = self.check(promo, usage=promotions.Usage(total=2, subject_known=True))
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.code, promotions.TOTAL_LIMIT_REACHED)
        self.assertIn("allows 2", verdict.reason)

    def test_a_per_person_limit_is_separate_from_the_total(self):
        promo = promotion("once_each", rules=(
            promotions.Rule("max_per_subject", quantity=1),))
        self.assertTrue(self.check(
            promo, usage=promotions.Usage(total=99, subject_known=True)).ok)
        self.assertFalse(self.check(
            promo, usage=promotions.Usage(total=99, by_subject=1, subject_known=True)).ok)

    def test_a_per_person_limit_refuses_when_nobody_is_named(self):
        """**A rule whose input is missing refuses.** `by_subject` reads 0 both for "never used
        it" and for "nobody said who this is", so taking the second reading meant a per-person
        limit was turned off by leaving a field out -- refusing the honest caller and waving
        through the other one. Found by review."""
        promo = promotion("once_each", rules=(
            promotions.Rule("max_per_subject", quantity=1),))
        verdict = self.check(promo, usage=promotions.Usage(subject_known=False))
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.code, promotions.SUBJECT_REQUIRED)
        self.assertIsNotNone(verdict.blocks_redemption())

    def test_every_rule_is_evaluated_so_a_limit_is_always_reached(self):
        """Returning on the first failure made the answer depend on the order the rules came
        back in: a coupon carrying a channel rule *and* a one-use limit failed on the channel,
        produced a reason the redemption path did not recognise, and the limit was never
        reached at all. A single-use code was unlimited, and which rule you added decided it."""
        promo = promotion("both", rules=(
            promotions.Rule("channel", text_value="web"),
            promotions.Rule("max_total_redemptions", quantity=1)))
        verdict = self.check(promo, usage=promotions.Usage(total=1, subject_known=True))
        codes = [f.code for f in verdict.failures]
        self.assertIn(promotions.CHANNEL_MISMATCH, codes)
        self.assertIn(promotions.TOTAL_LIMIT_REACHED, codes)
        blocking = verdict.blocks_redemption()
        assert blocking is not None
        self.assertEqual(blocking.code, promotions.TOTAL_LIMIT_REACHED)

    def test_only_the_basket_conditions_may_be_skipped_at_redemption(self):
        """A redemption has no basket, so it skips the four basket rules and refuses on
        everything else -- including a draft promotion, whose reason reads "is draft, not
        active" and matched none of the four English words the first version grepped for."""
        self.assertIsNone(self.check(promotion(
            "basket", rules=(promotions.Rule("channel", text_value="web"),)),
        ).blocks_redemption())
        draft = self.check(promotion("quiet", status="draft"))
        blocking = draft.blocks_redemption()
        assert blocking is not None
        self.assertEqual(blocking.code, promotions.NOT_ACTIVE)

    def test_an_unknown_rule_kind_refuses_rather_than_being_ignored(self):
        """Ignoring a condition somebody wrote would turn it into a discount nobody meant to
        give -- MOD-008's "an unknown attribute must not grant", applied to money."""
        verdict = self.check(promotion("odd", rules=(promotions.Rule("phase_of_moon"),)))
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.code, promotions.UNKNOWN_RULE_KIND)
        self.assertIn("does not evaluate", verdict.reason)

    def test_a_fixed_amount_in_another_currency_does_not_apply(self):
        promo = promotion("usd", percent_bp=None, amount_minor=500, currency="USD")
        verdict = self.check(promo)
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.code, promotions.CURRENCY_MISMATCH)
        self.assertIn("USD", verdict.reason)

    def test_a_draft_or_expired_promotion_does_not_apply(self):
        self.assertEqual(self.check(promotion("d", status="draft")).code,
                         promotions.NOT_ACTIVE)
        self.assertEqual(
            self.check(promotion("e", effective_to=datetime(2026, 1, 1, tzinfo=UTC))).code,
            promotions.ENDED)
        self.assertEqual(
            self.check(promotion("f", effective_from=datetime(2027, 1, 1, tzinfo=UTC))).code,
            promotions.NOT_STARTED)


class StackingTests(unittest.TestCase):
    def select(self, promos: list[promotions.Promotion], **kwargs: object):
        body: dict = {"subtotal_minor": 10000, "currency": "JOD", "channel": "pos",
                      "customer_segment": "any", "product_type": "service", "at": NOW}
        body.update(kwargs)
        return promotions.select(promos, **body)  # type: ignore[arg-type]

    def test_only_one_promotion_per_stacking_group_applies(self):
        applied, verdicts = self.select([
            promotion("first", percent_bp=1000, priority=5),
            promotion("second", percent_bp=2000, priority=1),
        ])
        self.assertEqual([key for key, _, _ in applied], ["first"])
        rejected = {v.promotion_key: v.reason for v in verdicts if not v.eligible}
        self.assertIn("second", rejected)
        self.assertIn("stacking group", rejected["second"])

    def test_a_tie_on_priority_goes_to_the_larger_discount(self):
        """Between two promotions the tenant ranked equally, the member gets the better one."""
        applied, _ = self.select([
            promotion("small", percent_bp=500),
            promotion("large", percent_bp=2500),
        ])
        self.assertEqual([key for key, _, _ in applied], ["large"])

    def test_promotions_in_different_groups_combine_and_compound(self):
        """A percentage applies to whatever is left when it is reached, which is the ordinary
        commercial meaning."""
        applied, _ = self.select([
            promotion("ten", percent_bp=1000, stacking_group="seasonal", priority=10),
            promotion("fixed", percent_bp=None, amount_minor=500, currency="JOD",
                      stacking_group="loyalty", priority=5),
        ])
        self.assertEqual([key for key, _, _ in applied], ["ten", "fixed"])
        self.assertEqual([amount for _, amount, _ in applied], [1000, 500])

    def test_the_selection_does_not_depend_on_the_order_the_promotions_arrive_in(self):
        candidates = [
            promotion("a", percent_bp=1000, stacking_group="g1", priority=1),
            promotion("b", percent_bp=1000, stacking_group="g1", priority=1),
            promotion("c", percent_bp=500, stacking_group="g2", priority=9),
            promotion("d", percent_bp=None, amount_minor=250, currency="JOD",
                      stacking_group="g3"),
        ]
        rng = random.Random(11)
        answers = set()
        for _ in range(20):
            shuffled = candidates[:]
            rng.shuffle(shuffled)
            applied, _ = self.select(shuffled)
            answers.add(tuple((key, amount) for key, amount, _ in applied))
        self.assertEqual(len(answers), 1)

    def test_every_promotion_gets_a_verdict_eligible_or_not(self):
        _, verdicts = self.select([
            promotion("applies", percent_bp=1000),
            promotion("expired", status="ended"),
        ])
        self.assertEqual({v.promotion_key for v in verdicts}, {"applies", "expired"})

    def test_the_strictest_threshold_among_the_applied_ones_wins(self):
        """Taking the highest would let a looser policy beside a stricter one turn the stricter
        one off -- MOD-008's own finding about combining policies."""
        promos = [
            promotion("loose", approval_threshold_bp=5000),
            promotion("strict", approval_threshold_bp=2000),
            promotion("none", approval_threshold_bp=0),
        ]
        self.assertEqual(
            promotions.highest_threshold_bp(promos, ["loose", "strict", "none"]), 2000)
        self.assertEqual(promotions.highest_threshold_bp(promos, ["none"]), 0)
        self.assertEqual(promotions.highest_threshold_bp(promos, []), 0)

    def test_a_promotion_with_neither_a_percentage_nor_an_amount_is_an_error(self):
        with self.assertRaises(promotions.PromotionError):
            promotions.discount_for(promotion("broken", percent_bp=None), 1000)


class ProductTests(unittest.TestCase):
    def test_the_eight_types_are_com_02_r01s_list(self):
        self.assertEqual(len(products.PRODUCT_TYPES), 8)
        for expected in ("membership", "session_credit", "retail_sku", "gift_card"):
            self.assertIn(expected, products.PRODUCT_TYPES)

    def test_a_quantitative_variant_says_how_many(self):
        """A ten-session pack whose quantity is empty is a sale nothing can fulfil, and the
        module that would fulfil it is not built -- so nothing downstream would catch it."""
        with self.assertRaises(products.ProductError):
            products.check_variant(
                products.Variant("ten", "Ten sessions"), "session_credit")
        products.check_variant(
            products.Variant("ten", "Ten sessions", entitlement_quantity=10),
            "session_credit")

    def test_a_membership_variant_says_how_long_it_runs(self):
        with self.assertRaises(products.ProductError):
            products.check_variant(products.Variant("annual", "Annual"), "membership")
        products.check_variant(
            products.Variant("annual", "Annual", term_days=365), "membership")

    def test_a_retail_variant_needs_neither(self):
        products.check_variant(products.Variant("large", "Large shirt"), "retail_sku")

    def test_a_product_never_goes_back_to_draft(self):
        """Un-publishing something that has been sold would make the sale unexplainable."""
        products.check_transition("draft", "published")
        products.check_transition("published", "retired")
        with self.assertRaises(products.ProductError):
            products.check_transition("published", "draft")
        with self.assertRaises(products.ProductError):
            products.check_transition("retired", "published")

    def test_a_key_is_lowercase_and_a_type_is_known(self):
        with self.assertRaises(products.ProductError):
            products.check_product(product_key="Membership", product_type="membership")
        with self.assertRaises(products.ProductError):
            products.check_product(product_key="thing", product_type="subscription")

    def test_a_locale_is_a_tag(self):
        products.check_text("en-GB", "Annual membership")
        with self.assertRaises(products.ProductError):
            products.check_text("english", "Annual membership")
        with self.assertRaises(products.ProductError):
            products.check_text("en", "   ")

    def test_the_listing_order_is_rank_then_key(self):
        """The key is the tiebreak so a listing is stable between runs; two products a tenant
        gave the same rank would otherwise swap places depending on the planner."""
        self.assertEqual(
            products.listing_order([(10, "b"), (1, "z"), (10, "a")]),
            [(1, "z"), (10, "a"), (10, "b")])


class BundleTests(unittest.TestCase):
    def test_a_bundle_with_no_items_is_refused(self):
        with self.assertRaises(bundles.BundleError):
            bundles.check_items([])

    def test_the_same_variant_twice_is_refused(self):
        with self.assertRaises(bundles.BundleError):
            bundles.check_items([
                bundles.Item("v1", 1, "entitlement_grant"),
                bundles.Item("v1", 1, "entitlement_grant"),
            ])

    def test_an_unknown_fulfilment_kind_is_refused(self):
        with self.assertRaises(bundles.BundleError):
            bundles.check_items([bundles.Item("v1", 1, "telepathy")])

    def test_outstanding_counts_only_what_was_delivered(self):
        """A failed or cancelled fulfilment leaves the obligation standing, which is the
        direction that cannot silently lose a member something they paid for."""
        items = [bundles.Item("v1", 3, "entitlement_grant"),
                 bundles.Item("v2", 1, "physical_goods")]
        out = bundles.outstanding(items, {"v1": 1})
        self.assertEqual([(o.variant_id, o.remaining) for o in out], [("v1", 2), ("v2", 1)])
        self.assertEqual(
            [o.remaining for o in bundles.outstanding(items, {"v1": 3, "v2": 1})], [0, 0])

    def test_over_delivery_is_refused(self):
        """For an entitlement grant that is a member with more sessions than they bought, and
        nothing downstream would catch it."""
        item = bundles.Item("v1", 2, "entitlement_grant")
        bundles.check_fulfilment(item, already_delivered=1, quantity=1,
                                 outcome="delivered", detail=None)
        with self.assertRaises(bundles.BundleError):
            bundles.check_fulfilment(item, already_delivered=2, quantity=1,
                                     outcome="delivered", detail=None)

    def test_a_failure_says_why(self):
        item = bundles.Item("v1", 2, "entitlement_grant")
        with self.assertRaises(bundles.BundleError):
            bundles.check_fulfilment(item, already_delivered=0, quantity=1,
                                     outcome="failed", detail=None)
        bundles.check_fulfilment(item, already_delivered=0, quantity=1,
                                outcome="failed", detail="the grant service refused")

    def test_an_unknown_outcome_is_refused(self):
        with self.assertRaises(bundles.BundleError):
            bundles.check_fulfilment(
                bundles.Item("v1", 1, "entitlement_grant"), already_delivered=0,
                quantity=1, outcome="probably", detail="x")


if __name__ == "__main__":
    unittest.main()

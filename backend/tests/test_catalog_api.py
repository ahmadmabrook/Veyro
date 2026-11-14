"""MOD-016 COM-02 over HTTP, with the credentials a real caller would hold.

**Written before the review this time.** MOD-014's reviewers found four defects in its request
path that a green suite could not see, because every test reached past the gate and called the
service directly. So the catalogue's tests drive the routes: the gate, the permission
resolution, the action classes and the approval check all live on that path, and a test that
skips it proves the decision rather than the product.

The two paragraph 10220 controls are what most of this file is about: a resolution is
deterministic and explained, and nobody chooses a price without a recorded approval.
"""

from __future__ import annotations

import unittest
import uuid

from tests.support import GatedApiTestCase

FROM = "2026-01-01T00:00:00+00:00"


class CatalogApiTestCase(GatedApiTestCase):
    def scoped(self, tenant_id: str, permissions: list[str]) -> dict[str, str]:
        """Headers for a session holding exactly these permissions, at AAL 1."""
        return self.headers(tenant_id, self.grant(tenant_id, permissions))

    def product(
        self, tenant_id: str, *, key: str | None = None, product_type: str = "service",
        variants: list[dict] | None = None,
    ) -> dict:
        owner = self.headers(tenant_id)
        body = {
            "product_key": key or f"p{uuid.uuid4().hex[:8]}",
            "product_type": product_type,
            "texts": [{"locale": "en", "display_name": "Personal training"}],
            "variants": variants or [{"variant_key": "single", "display_name": "One hour"}],
            **self.correlation(),
        }
        created = self.client.post("/catalog/products", json=body, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        return dict(created.json())

    def book(
        self, tenant_id: str, *, key: str | None = None, channel: str = "any",
        segment: str = "any", priority: int = 0, currency: str = "JOD",
    ) -> str:
        owner = self.headers(tenant_id)
        created = self.client.post("/catalog/price-books", json={
            "price_book_key": key or f"b{uuid.uuid4().hex[:8]}",
            "display_name": "Book", "currency": currency, "effective_from": FROM,
            "channel": channel, "customer_segment": segment, "priority": priority,
            **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        book_id = str(created.json()["price_book_id"])
        activated = self.client.post(
            f"/catalog/price-books/{book_id}/activate",
            json=self.correlation(), headers=owner)
        self.assertEqual(activated.status_code, 200, activated.text)
        return book_id

    def price(self, tenant_id: str, book_id: str, variant_id: str, amount: int,
              effective_from: str = FROM) -> dict:
        created = self.client.post("/catalog/prices", json={
            "price_book_id": book_id, "variant_id": variant_id,
            "amount_minor": amount, "effective_from": effective_from,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return dict(created.json())

    def promotion(self, tenant_id: str, **kwargs) -> str:
        owner = self.headers(tenant_id)
        body = {
            "promotion_key": f"pr{uuid.uuid4().hex[:8]}", "display_name": "Promo",
            "promotion_kind": "automatic", "percent_bp": 1000, "effective_from": FROM,
            **self.correlation(),
        }
        body.update(kwargs)
        created = self.client.post("/catalog/promotions", json=body, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        promotion_id = str(created.json()["promotion_id"])
        activated = self.client.post(
            f"/catalog/promotions/{promotion_id}/activate",
            json=self.correlation(), headers=owner)
        self.assertEqual(activated.status_code, 200, activated.text)
        return promotion_id

    def publish(self, tenant_id: str, product_id: str, version: int = 1) -> None:
        """**Nothing sells until it is published.** `resolve_price` refuses a draft or retired
        product, which is what makes `catalog.product.publish` buy anything on the sales path;
        the first version read the status and discarded it, so a product nobody had published
        sold and a product explicitly retired went on selling."""
        published = self.client.post(
            f"/catalog/products/{product_id}/publish",
            json={"expected_version": version, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(published.status_code, 200, published.text)

    def sellable(self, tenant_id: str, *, amount: int = 4500, book_id: str | None = None,
                 **kwargs) -> tuple[dict, str]:
        """A published product with a live price. Returns `(product, variant_id)`."""
        created = self.product(tenant_id, **kwargs)
        variant_id = created["variants"][0]["variant_id"]
        self.price(tenant_id, book_id or self.book(tenant_id), variant_id, amount)
        self.publish(tenant_id, created["product_id"])
        return created, variant_id

    def ask(self, tenant_id: str, variant_id: str, *, listed: int, override: int,
            currency: str = "JOD") -> str:
        """A discount request, by somebody other than the approver.

        **The two acts are separate and both identities are derived.** While `requested_by` was
        a field on the approval body the separation of duties was satisfied by typing a uuid,
        and all three reviewers independently demonstrated one person approving their own
        override. So a request comes from its own session holding its own permission."""
        asked = self.client.post("/catalog/discount-requests", json={
            "variant_id": variant_id, "list_amount_minor": listed,
            "override_amount_minor": override, "currency": currency,
            "reason": "long-standing member", **self.correlation()},
            headers=self.scoped(tenant_id, ["catalog.discount.request"]))
        self.assertEqual(asked.status_code, 201, asked.text)
        return str(asked.json()["request_id"])

    def approve(self, tenant_id: str, variant_id: str, *, listed: int, override: int,
                currency: str = "JOD") -> str:
        request_id = self.ask(tenant_id, variant_id, listed=listed, override=override,
                              currency=currency)
        approved = self.client.post("/catalog/discount-approvals", json={
            "request_id": request_id, "reason": "approved at the counter",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(approved.status_code, 201, approved.text)
        return str(approved.json()["approval_id"])

    def resolve(self, tenant_id: str, variant_id: str, **kwargs) -> dict:
        body = {"variant_id": variant_id, "currency": "JOD", **self.correlation()}
        body.update(kwargs)
        response = self.client.post(
            "/catalog/prices/resolve", json=body, headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 201, response.text)
        return dict(response.json())


class ProductLifecycleTests(CatalogApiTestCase):
    def test_a_product_with_no_price_anywhere_cannot_be_published(self):
        """Publishing is what makes something sellable on every channel, and a sellable thing
        nobody can price is a till that stops working in front of a customer."""
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        refused = self.client.post(
            f"/catalog/products/{created['product_id']}/publish",
            json={"expected_version": 1, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("no_live_price", refused.text)

    def test_a_priced_product_publishes_and_never_returns_to_draft(self):
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        self.price(tenant_id, self.book(tenant_id), variant_id, 4500)
        published = self.client.post(
            f"/catalog/products/{created['product_id']}/publish",
            json={"expected_version": 1, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()["status"], "published")
        again = self.client.post(
            f"/catalog/products/{created['product_id']}/publish",
            json={"expected_version": 2, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 409, again.text)

    def test_a_quantitative_product_needs_a_quantity_on_its_variant(self):
        tenant_id = self.tenant()
        refused = self.client.post("/catalog/products", json={
            "product_key": "ten.pack", "product_type": "session_credit",
            "variants": [{"variant_key": "ten", "display_name": "Ten sessions"}],
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("how many", refused.text)

    def test_the_listing_is_in_merchandising_order_with_no_locale_fallback(self):
        tenant_id = self.tenant()
        for key, rank in (("zebra", 1), ("apple", 9)):
            owner = self.headers(tenant_id)
            self.client.post("/catalog/products", json={
                "product_key": key, "product_type": "retail_sku",
                "merchandising_rank": rank,
                "texts": [{"locale": "en", "display_name": key.title()}],
                "variants": [{"variant_key": "one", "display_name": "One"}],
                **self.correlation()}, headers=owner)
        listed = self.client.get(
            "/catalog/products", headers=self.headers(tenant_id)).json()
        self.assertEqual([p["product_key"] for p in listed], ["zebra", "apple"])
        # No fallback chain: a missing translation shows as missing.
        arabic = self.client.get(
            "/catalog/products?locale=ar", headers=self.headers(tenant_id)).json()
        self.assertTrue(all(p["display_name"] is None for p in arabic))
        self.assertTrue(all(p["text_locale"] is None for p in arabic))


class PriceVersioningTests(CatalogApiTestCase):
    def test_a_price_is_never_edited_and_history_still_resolves(self):
        """COM-02-R07. The table carries no UPDATE on the amount, so re-pricing is a new row
        and an order resolved in March re-derives from March's row."""
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        book_id = self.book(tenant_id)
        self.price(tenant_id, book_id, variant_id, 5000, FROM)
        self.price(tenant_id, book_id, variant_id, 6000, "2026-05-01T00:00:00+00:00")
        self.publish(tenant_id, created["product_id"])
        march = self.resolve(tenant_id, variant_id, at=None)
        self.assertEqual(march["list_amount_minor"], 6000)
        self.assertEqual(march["final_amount_minor"], 6000)

    def test_two_prices_from_the_same_moment_in_one_book_are_refused(self):
        """Two would make the resolution depend on which row the planner returned first, and
        deterministic is the requirement."""
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        book_id = self.book(tenant_id)
        self.price(tenant_id, book_id, variant_id, 5000, FROM)
        clash = self.client.post("/catalog/prices", json={
            "price_book_id": book_id, "variant_id": variant_id, "amount_minor": 7000,
            "effective_from": FROM, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(clash.status_code, 409, clash.text)

    def test_a_superseded_price_stops_applying_and_the_row_stays(self):
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        book_id = self.book(tenant_id)
        wrong = self.price(tenant_id, book_id, variant_id, 50, FROM)
        right = self.price(tenant_id, book_id, variant_id, 5000,
                           "2026-01-02T00:00:00+00:00")
        self.publish(tenant_id, created["product_id"])
        done = self.client.post(
            f"/catalog/prices/{wrong['price_id']}/supersede",
            json={"replacement_price_id": right["price_id"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(self.resolve(tenant_id, variant_id)["price_id"],
                         right["price_id"])

    def test_a_replacement_prices_the_same_variant_in_the_same_book(self):
        """Pointing a withdrawn price at an unrelated row would make the chain meaningless to
        anybody auditing why a price stopped applying."""
        tenant_id = self.tenant()
        first = self.product(tenant_id)
        second = self.product(tenant_id)
        book_id = self.book(tenant_id)
        a = self.price(tenant_id, book_id, first["variants"][0]["variant_id"], 100)
        b = self.price(tenant_id, book_id, second["variants"][0]["variant_id"], 200)
        refused = self.client.post(
            f"/catalog/prices/{a['price_id']}/supersede",
            json={"replacement_price_id": b["price_id"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_the_most_specific_book_prices_the_sale_and_the_choice_is_explained(self):
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        wide = self.book(tenant_id, key="wide")
        pos = self.book(tenant_id, key="pos.only", channel="pos")
        self.price(tenant_id, wide, variant_id, 5000)
        self.price(tenant_id, pos, variant_id, 4000)
        self.publish(tenant_id, created["product_id"])
        at_till = self.resolve(tenant_id, variant_id, channel="pos")
        self.assertEqual(at_till["price_book_id"], pos)
        self.assertEqual(at_till["final_amount_minor"], 4000)
        self.assertTrue(any("pos.only" in line for line in at_till["explanation"]))
        on_app = self.resolve(tenant_id, variant_id, channel="member_app")
        self.assertEqual(on_app["price_book_id"], wide)


class ResolutionExplanationTests(CatalogApiTestCase):
    def test_the_stored_resolution_carries_the_whole_explanation(self):
        """Paragraph 10220. A number with no reasoning is impossible to dispute at a counter."""
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        self.price(tenant_id, self.book(tenant_id), variant_id, 10000)
        self.publish(tenant_id, created["product_id"])
        self.promotion(tenant_id, percent_bp=1500)
        resolved = self.resolve(tenant_id, variant_id, quantity=2)
        self.assertEqual(resolved["list_amount_minor"], 20000)
        self.assertEqual(resolved["discount_minor"], 3000)
        self.assertEqual(resolved["final_amount_minor"], 17000)
        stored = self.client.get(
            f"/catalog/resolutions/{resolved['resolution_id']}",
            headers=self.headers(tenant_id))
        self.assertEqual(stored.status_code, 200, stored.text)
        body = stored.json()
        self.assertEqual(body["explanation"], resolved["explanation"])
        self.assertEqual(body["policy_version"], resolved["policy_version"])
        self.assertTrue(any("list_price" in line for line in body["explanation"]))
        self.assertTrue(any("final_amount" in line for line in body["explanation"]))

    def test_a_rejected_promotion_is_explained_by_name(self):
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        self.price(tenant_id, self.book(tenant_id), variant_id, 4000)
        self.publish(tenant_id, created["product_id"])
        self.promotion(tenant_id, promotion_key="big.spend", percent_bp=2000,
                       rules=[{"rule_kind": "minimum_spend", "amount_minor": 50000}])
        resolved = self.resolve(tenant_id, variant_id)
        self.assertEqual(resolved["discount_minor"], 0)
        reasons = {v["promotion_key"]: v["reason"] for v in resolved["verdicts"]}
        self.assertIn("big.spend", reasons)
        self.assertIn("50000", reasons["big.spend"])
        self.assertIn("4000", reasons["big.spend"])

    def test_the_same_request_twice_gives_the_same_answer(self):
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        self.price(tenant_id, self.book(tenant_id), variant_id, 7777)
        self.publish(tenant_id, created["product_id"])
        for _ in range(3):
            self.promotion(tenant_id, percent_bp=700, stacking_group="g1")
        first = self.resolve(tenant_id, variant_id)
        second = self.resolve(tenant_id, variant_id)
        self.assertEqual(first["final_amount_minor"], second["final_amount_minor"])
        self.assertEqual(first["applied_promotions"], second["applied_promotions"])
        self.assertEqual(first["explanation"], second["explanation"])

    def test_a_variant_with_no_price_is_a_conflict_not_a_guess(self):
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        # Priced and published in JOD, then asked for in a currency no book covers. The
        # resolver refuses and says which half is missing rather than falling back to a
        # figure nobody wrote.
        self.price(tenant_id, self.book(tenant_id), variant_id, 100, FROM)
        self.publish(tenant_id, created["product_id"])
        response = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "EUR", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("no_price_book_matches", response.text)


class OverrideApprovalTests(CatalogApiTestCase):
    """**Paragraph 10220's second control.** Nobody chooses a price without a recorded
    approval, and the approval is checked against the row rather than believed."""

    def setup_line(self, tenant_id: str, amount: int = 10000) -> str:
        _, variant_id = self.sellable(tenant_id, amount=amount)
        return variant_id

    def test_an_override_without_an_approval_is_refused(self):
        tenant_id = self.tenant()
        variant_id = self.setup_line(tenant_id)
        refused = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD",
            "override_amount_minor": 1, "override_reason": "because I said so",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("needs_a_recorded_approval", refused.text)

    def test_an_override_with_an_approval_is_applied_and_kept_separate(self):
        tenant_id = self.tenant()
        variant_id = self.setup_line(tenant_id)
        approval_id = self.approve(
            tenant_id, variant_id, listed=10000, override=7500)
        resolved = self.resolve(
            tenant_id, variant_id, override_amount_minor=7500,
            override_reason="long-standing member", approval_id=approval_id)
        self.assertEqual(resolved["final_amount_minor"], 7500)
        # The override is its own step, not folded into the promotion list: a manual decision
        # has to be distinguishable from a campaign on the receipt.
        self.assertEqual(resolved["applied_promotions"], [])
        self.assertTrue(any("manual_override" in line for line in resolved["explanation"]))

    def test_an_approval_for_another_variant_does_not_count(self):
        """An approval id that merely exists would be the authority bought with a body field,
        which is the shape MOD-009, MOD-013 and MOD-014 each shipped once."""
        tenant_id = self.tenant()
        variant_id = self.setup_line(tenant_id)
        other = self.setup_line(tenant_id)
        approval_id = self.approve(tenant_id, other, listed=10000, override=7500)
        refused = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", "override_amount_minor": 7500,
            "override_reason": "goodwill", "approval_id": approval_id,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("another_variant", refused.text)

    def test_an_approval_measured_against_a_different_list_price_does_not_count(self):
        tenant_id = self.tenant()
        variant_id = self.setup_line(tenant_id)
        approval_id = self.approve(
            tenant_id, variant_id, listed=500, override=100)
        refused = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", "override_amount_minor": 100,
            "override_reason": "goodwill", "approval_id": approval_id,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("different_list_price", refused.text)

    def test_an_approval_does_not_cover_a_deeper_discount_than_it_approved(self):
        tenant_id = self.tenant()
        variant_id = self.setup_line(tenant_id)
        approval_id = self.approve(
            tenant_id, variant_id, listed=10000, override=9000)
        refused = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", "override_amount_minor": 1000,
            "override_reason": "goodwill", "approval_id": approval_id,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("this_deep", refused.text)

    def test_an_approver_cannot_approve_the_request_they_made(self):
        """MOD-008's separation of duties, applied to the one act that lets somebody choose the
        price. **Both identities are now derived**, which is what makes the constraint mean
        anything: while `requested_by` was a field on the approval body all three reviewers
        independently approved their own override by typing a uuid."""
        tenant_id = self.tenant()
        variant_id = self.setup_line(tenant_id)
        owner = self.headers(tenant_id)
        asked = self.client.post("/catalog/discount-requests", json={
            "variant_id": variant_id, "list_amount_minor": 10000,
            "override_amount_minor": 5000, "currency": "JOD", "reason": "mine",
            **self.correlation()}, headers=owner)
        self.assertEqual(asked.status_code, 201, asked.text)
        refused = self.client.post("/catalog/discount-approvals", json={
            "request_id": asked.json()["request_id"], "reason": "mine too",
            **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)

    def test_an_approval_is_spendable_once(self):
        """Without this the approval is a bearer token: `_check_approval` verified the variant,
        the list amount and the depth, and then nothing ever happened to the row -- so a
        one-off goodwill decision became a standing authority to sell that variant at that
        price for ever. Three reviewers found it independently."""
        tenant_id = self.tenant()
        variant_id = self.setup_line(tenant_id)
        approval_id = self.approve(tenant_id, variant_id, listed=10000, override=7500)
        self.resolve(tenant_id, variant_id, override_amount_minor=7500,
                     override_reason="goodwill", approval_id=approval_id)
        again = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", "override_amount_minor": 7500,
            "override_reason": "goodwill", "approval_id": approval_id,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("already_been_used", again.text)

    def test_an_approval_granted_in_another_currency_does_not_count(self):
        """The currency is the third thing that makes an amount an amount: an approval
        recorded as "100.00 JOD down to 75.00 JOD" authorised the same minor-unit counts in
        USD, which is the one comparison MOD-015's money discipline forbids."""
        tenant_id = self.tenant()
        created = self.product(tenant_id)
        variant_id = created["variants"][0]["variant_id"]
        self.price(tenant_id, self.book(tenant_id, key="jod.book"), variant_id, 10000)
        self.price(tenant_id, self.book(tenant_id, key="usd.book", currency="USD"),
                   variant_id, 10000)
        self.publish(tenant_id, created["product_id"])
        approval_id = self.approve(tenant_id, variant_id, listed=10000, override=7500)
        refused = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "USD", "override_amount_minor": 7500,
            "override_reason": "goodwill", "approval_id": approval_id,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("another_currency", refused.text)

    def test_an_approval_nobody_needed_is_refused_rather_than_recorded(self):
        """The first version validated the id only when an approval was needed and inserted it
        either way, so a resolution could permanently cite an unrelated approval and the one
        table that *is* the audit read as though it had authorised a price it has nothing to
        do with."""
        tenant_id = self.tenant()
        variant_id = self.setup_line(tenant_id)
        other = self.setup_line(tenant_id)
        approval_id = self.approve(tenant_id, other, listed=10000, override=7500)
        refused = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", "approval_id": approval_id,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("needs_no_approval", refused.text)

    def test_a_discount_above_the_promotions_threshold_needs_an_approval(self):
        """The campaign itself says how deep a discount may go unreviewed."""
        tenant_id = self.tenant()
        _, variant_id = self.sellable(tenant_id, amount=10000)
        self.promotion(tenant_id, percent_bp=5000, approval_threshold_bp=2000)
        refused = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("needs_a_recorded_approval", refused.text)


class CouponTests(CatalogApiTestCase):
    def issue(self, tenant_id: str, promotion_id: str, code: str) -> str:
        response = self.client.post("/catalog/coupons", json={
            "promotion_id": promotion_id, "code": code, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(response.status_code, 201, response.text)
        return str(response.json()["coupon_id"])

    def test_a_code_matches_whatever_case_it_was_typed_in(self):
        tenant_id = self.tenant()
        promotion_id = self.promotion(tenant_id, promotion_kind="coupon", percent_bp=1000)
        self.issue(tenant_id, promotion_id, "save10")
        checked = self.client.post("/catalog/promotions/validate", json={
            "code": "SaVe10", "subtotal_minor": 10000, "currency": "JOD"},
            headers=self.headers(tenant_id))
        self.assertEqual(checked.status_code, 200, checked.text)
        self.assertTrue(checked.json()["eligible"], checked.text)

    def test_validation_says_why_a_code_does_not_work(self):
        """"Minimum spend of 50.00 not met" is something a member can act on and "invalid code"
        is not."""
        tenant_id = self.tenant()
        promotion_id = self.promotion(
            tenant_id, promotion_kind="coupon", percent_bp=1000,
            rules=[{"rule_kind": "minimum_spend", "amount_minor": 50000}])
        self.issue(tenant_id, promotion_id, "BIGSPEND")
        checked = self.client.post("/catalog/promotions/validate", json={
            "code": "BIGSPEND", "subtotal_minor": 1000, "currency": "JOD"},
            headers=self.headers(tenant_id)).json()
        self.assertFalse(checked["eligible"])
        self.assertIn("50000", checked["reason"])

    def test_an_unknown_code_is_a_reason_rather_than_a_404(self):
        tenant_id = self.tenant()
        checked = self.client.post("/catalog/promotions/validate", json={
            "code": "NOSUCHCODE", "subtotal_minor": 1000, "currency": "JOD"},
            headers=self.headers(tenant_id))
        self.assertEqual(checked.status_code, 200, checked.text)
        self.assertFalse(checked.json()["eligible"])

    def test_a_coupon_only_applies_when_its_code_is_presented(self):
        """Loading every coupon promotion would apply a campaign to somebody who never
        presented the code, which is the discount nobody meant to give."""
        tenant_id = self.tenant()
        _, variant_id = self.sellable(tenant_id, amount=10000)
        promotion_id = self.promotion(tenant_id, promotion_kind="coupon", percent_bp=2500)
        self.issue(tenant_id, promotion_id, "QUARTER")
        without = self.resolve(tenant_id, variant_id)
        self.assertEqual(without["discount_minor"], 0)
        # **Applying a coupon redeems it in the same transaction**, so the resolution needs an
        # idempotency key. The first version wrote the ledger on a separate route nobody had
        # to call, which made every usage limit in the module decorative.
        with_code = self.resolve(tenant_id, variant_id, coupon_code="QUARTER",
                                 idempotency_key=f"till-{uuid.uuid4().hex[:8]}")
        self.assertEqual(with_code["discount_minor"], 2500)

    def test_applying_a_coupon_moves_the_ledger_the_limits_are_counted_from(self):
        """**The finding this module was rebuilt around.** `resolve_price` applied a coupon's
        discount and read the usage count, and only the separate redeem route wrote the rows
        that count came from -- so one single-use 90% code priced six sales on the routine till
        permission. The redemption is now inserted beside the resolution."""
        tenant_id = self.tenant()
        _, variant_id = self.sellable(tenant_id, amount=10000)
        promotion_id = self.promotion(
            tenant_id, promotion_kind="coupon", percent_bp=9000,
            rules=[{"rule_kind": "max_total_redemptions", "quantity": 1}])
        self.issue(tenant_id, promotion_id, "LAUNCH1")
        first = self.resolve(tenant_id, variant_id, coupon_code="LAUNCH1",
                             idempotency_key="sale-1")
        self.assertEqual(first["final_amount_minor"], 1000)
        second = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", "coupon_code": "LAUNCH1",
            "idempotency_key": "sale-2", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(second.status_code, 409, second.text)
        self.assertIn("redeemed", second.text)

    def test_a_coupon_cannot_be_applied_without_an_idempotency_key(self):
        """Because the redemption is written in the same transaction, there is nothing for a
        retry to recognise without one -- and a retried till request would take a second use."""
        tenant_id = self.tenant()
        _, variant_id = self.sellable(tenant_id, amount=10000)
        promotion_id = self.promotion(tenant_id, promotion_kind="coupon", percent_bp=1000)
        self.issue(tenant_id, promotion_id, "NOKEY")
        refused = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", "coupon_code": "NOKEY",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("idempotency_key", refused.text)

    def test_a_code_on_a_promotion_nobody_activated_does_not_redeem(self):
        """The refusal is decided by reason code, not by whether the prose happens to contain
        one of four English words. A draft promotion reads "is draft, not active" and matched
        none of them, so the module told the caller the code did not work and took the
        redemption anyway."""
        tenant_id = self.tenant()
        created = self.client.post("/catalog/promotions", json={
            "promotion_key": f"pr{uuid.uuid4().hex[:8]}", "display_name": "Quiet",
            "promotion_kind": "coupon", "percent_bp": 1000, "effective_from": FROM,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        self.issue(tenant_id, str(created.json()["promotion_id"]), "NOTLIVE")
        refused = self.client.post("/catalog/coupons/redeem", json={
            "code": "NOTLIVE", "subtotal_minor": 10000, "currency": "JOD",
            "idempotency_key": "draft-1", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("not active", refused.text)

    def test_a_per_person_limit_is_not_turned_off_by_omitting_the_subject(self):
        """The control was keyed on a value the caller supplies and never checked against
        anything: with the field it refused, and without it it waved the same caller through."""
        tenant_id = self.tenant()
        promotion_id = self.promotion(
            tenant_id, promotion_kind="coupon", percent_bp=1000,
            rules=[{"rule_kind": "max_per_subject", "quantity": 1}])
        self.issue(tenant_id, promotion_id, "ONEEACH")
        refused = self.client.post("/catalog/coupons/redeem", json={
            "code": "ONEEACH", "subtotal_minor": 10000, "currency": "JOD",
            "idempotency_key": "anon-1", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("names nobody", refused.text)

    def test_a_redemption_is_idempotent_on_its_key(self):
        """A retried till request must not take a second use off a single-use coupon."""
        tenant_id = self.tenant()
        promotion_id = self.promotion(tenant_id, promotion_kind="coupon", percent_bp=1000)
        self.issue(tenant_id, promotion_id, "ONCE")
        key = f"till-{uuid.uuid4().hex[:8]}"
        first = self.client.post("/catalog/coupons/redeem", json={
            "code": "ONCE", "subtotal_minor": 10000, "currency": "JOD",
            "idempotency_key": key, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(first.status_code, 201, first.text)
        self.assertFalse(first.json()["repeated"])
        again = self.client.post("/catalog/coupons/redeem", json={
            "code": "ONCE", "subtotal_minor": 10000, "currency": "JOD",
            "idempotency_key": key, **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["redemption_id"], first.json()["redemption_id"])

    def test_a_usage_limit_is_counted_from_the_ledger_and_re_checked_at_redemption(self):
        """A control consulted once is a control with a window: between the validation and the
        sale, the last use of a single-use code can go to somebody else."""
        tenant_id = self.tenant()
        promotion_id = self.promotion(
            tenant_id, promotion_kind="coupon", percent_bp=1000,
            rules=[{"rule_kind": "max_total_redemptions", "quantity": 1}])
        self.issue(tenant_id, promotion_id, "SINGLEUSE")
        first = self.client.post("/catalog/coupons/redeem", json={
            "code": "SINGLEUSE", "subtotal_minor": 10000, "currency": "JOD",
            "idempotency_key": f"a{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(first.status_code, 201, first.text)
        second = self.client.post("/catalog/coupons/redeem", json={
            "code": "SINGLEUSE", "subtotal_minor": 10000, "currency": "JOD",
            "idempotency_key": f"b{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(second.status_code, 409, second.text)
        self.assertIn("redeemed", second.text)

    def test_the_discount_recorded_is_the_one_the_promotion_grants(self):
        """`discount_minor` used to come from the request body, so the ledger the module calls
        authoritative recorded whatever figure the caller typed -- 9,999,999,999.99 against a
        5% coupon -- in a table with no UPDATE grant and so no correction path."""
        tenant_id = self.tenant()
        promotion_id = self.promotion(tenant_id, promotion_kind="coupon", percent_bp=500)
        self.issue(tenant_id, promotion_id, "FIVEOFF")
        taken = self.client.post("/catalog/coupons/redeem", json={
            "code": "FIVEOFF", "subtotal_minor": 20000, "currency": "JOD",
            "idempotency_key": "five-1", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(taken.status_code, 201, taken.text)
        self.assertEqual(taken.json()["discount_minor"], 1000)

    def test_revoking_a_code_does_not_end_the_campaign(self):
        tenant_id = self.tenant()
        promotion_id = self.promotion(tenant_id, promotion_kind="coupon", percent_bp=1000)
        leaked = self.issue(tenant_id, promotion_id, "LEAKED")
        self.issue(tenant_id, promotion_id, "STILLGOOD")
        revoked = self.client.post(
            f"/catalog/coupons/{leaked}/revoke",
            json={"reason": "posted on a forum", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(revoked.status_code, 200, revoked.text)
        dead = self.client.post("/catalog/promotions/validate", json={
            "code": "LEAKED", "subtotal_minor": 10000, "currency": "JOD"},
            headers=self.headers(tenant_id)).json()
        self.assertFalse(dead["eligible"])
        alive = self.client.post("/catalog/promotions/validate", json={
            "code": "STILLGOOD", "subtotal_minor": 10000, "currency": "JOD"},
            headers=self.headers(tenant_id)).json()
        self.assertTrue(alive["eligible"])


class BundleTests(CatalogApiTestCase):
    def build(self, tenant_id: str) -> tuple[str, str]:
        owner = self.headers(tenant_id)
        pack = self.product(
            tenant_id, product_type="session_credit",
            variants=[{"variant_key": "ten", "display_name": "Ten sessions",
                       "entitlement_quantity": 10}])
        variant_id = pack["variants"][0]["variant_id"]
        bundle = self.client.post("/catalog/bundles", json={
            "product_id": pack["product_id"],
            "items": [{"variant_id": variant_id, "quantity": 2,
                       "fulfilment_kind": "entitlement_grant"}],
            **self.correlation()}, headers=owner)
        self.assertEqual(bundle.status_code, 201, bundle.text)
        return str(bundle.json()["bundle_id"]), variant_id

    def test_a_bundle_reports_what_a_sale_still_owes(self):
        tenant_id = self.tenant()
        bundle_id, variant_id = self.build(tenant_id)
        owner = self.headers(tenant_id)
        status = self.client.get(
            f"/catalog/bundles/{bundle_id}/status?order_reference=order-1",
            headers=owner).json()
        self.assertFalse(status["complete"])
        self.assertEqual(status["items"][0]["remaining"], 2)
        for _ in range(1):
            recorded = self.client.post("/catalog/bundles/fulfilments", json={
                "bundle_id": bundle_id, "variant_id": variant_id,
                "order_reference": "order-1", "quantity": 2, "outcome": "delivered",
                "idempotency_key": f"f{uuid.uuid4().hex[:8]}",
                **self.correlation()}, headers=owner)
            self.assertEqual(recorded.status_code, 201, recorded.text)
        status = self.client.get(
            f"/catalog/bundles/{bundle_id}/status?order_reference=order-1",
            headers=owner).json()
        self.assertTrue(status["complete"])

    def record(self, tenant_id: str, bundle_id: str, variant_id: str, *, order: str,
               quantity: int, outcome: str, detail: str | None = None):
        body = {"bundle_id": bundle_id, "variant_id": variant_id,
                "order_reference": order, "quantity": quantity, "outcome": outcome,
                "idempotency_key": f"f{uuid.uuid4().hex[:10]}", **self.correlation()}
        if detail is not None:
            body["detail"] = detail
        return self.client.post("/catalog/bundles/fulfilments", json=body,
                                headers=self.headers(tenant_id))

    def test_over_delivery_is_refused(self):
        """For an entitlement grant that is a member with more sessions than they bought."""
        tenant_id = self.tenant()
        bundle_id, variant_id = self.build(tenant_id)
        self.assertEqual(self.record(tenant_id, bundle_id, variant_id, order="order-2",
                                     quantity=2, outcome="delivered").status_code, 201)
        again = self.record(tenant_id, bundle_id, variant_id, order="order-2",
                            quantity=1, outcome="delivered")
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("over-deliver", again.text)

    def test_partial_deliveries_add_up(self):
        """`check_fulfilment` sums them, and the index that said "one row per item per order"
        made that unreachable -- two contradictory statements, one of which was enforced."""
        tenant_id = self.tenant()
        bundle_id, variant_id = self.build(tenant_id)
        for _ in range(2):
            self.assertEqual(self.record(tenant_id, bundle_id, variant_id, order="order-6",
                                         quantity=1, outcome="delivered").status_code, 201)
        status = self.client.get(
            f"/catalog/bundles/{bundle_id}/status?order_reference=order-6",
            headers=self.headers(tenant_id)).json()
        self.assertTrue(status["complete"])

    def test_a_failed_fulfilment_says_why_and_does_not_block_the_retry(self):
        """**The review finding.** The obligation standing was already asserted; that the
        retry could then satisfy it was not, and it could not: the unique index on (order,
        bundle, variant) refused every later row, with no UPDATE and no DELETE grant to undo
        the failure. A transient provider outage left a member who had paid with an obligation
        no call in the module could ever meet."""
        tenant_id = self.tenant()
        bundle_id, variant_id = self.build(tenant_id)
        silent = self.record(tenant_id, bundle_id, variant_id, order="order-3",
                             quantity=2, outcome="failed")
        self.assertEqual(silent.status_code, 409, silent.text)
        explained = self.record(tenant_id, bundle_id, variant_id, order="order-3",
                                quantity=2, outcome="failed",
                                detail="the grant service refused")
        self.assertEqual(explained.status_code, 201, explained.text)
        status = self.client.get(
            f"/catalog/bundles/{bundle_id}/status?order_reference=order-3",
            headers=self.headers(tenant_id)).json()
        self.assertEqual(status["items"][0]["remaining"], 2)
        retried = self.record(tenant_id, bundle_id, variant_id, order="order-3",
                              quantity=2, outcome="delivered")
        self.assertEqual(retried.status_code, 201, retried.text)
        after = self.client.get(
            f"/catalog/bundles/{bundle_id}/status?order_reference=order-3",
            headers=self.headers(tenant_id)).json()
        self.assertTrue(after["complete"])

    def test_a_delivery_recorded_in_error_is_reversed_rather_than_edited(self):
        """The only correction path there is: no UPDATE and no DELETE grant, so `reversed`
        subtracts. It is what makes recording a delivery a recoverable mistake, and therefore
        what lets `catalog.bundle.fulfil` be a permission somebody can hold."""
        tenant_id = self.tenant()
        bundle_id, variant_id = self.build(tenant_id)
        self.record(tenant_id, bundle_id, variant_id, order="order-4", quantity=2,
                    outcome="delivered")
        too_much = self.record(tenant_id, bundle_id, variant_id, order="order-4",
                               quantity=3, outcome="reversed", detail="wrong order")
        self.assertEqual(too_much.status_code, 409, too_much.text)
        undone = self.record(tenant_id, bundle_id, variant_id, order="order-4",
                             quantity=2, outcome="reversed", detail="wrong order")
        self.assertEqual(undone.status_code, 201, undone.text)
        status = self.client.get(
            f"/catalog/bundles/{bundle_id}/status?order_reference=order-4",
            headers=self.headers(tenant_id)).json()
        self.assertEqual(status["items"][0]["remaining"], 2)


class PermissionClassTests(CatalogApiTestCase):
    def test_every_catalogue_write_needs_a_stepped_up_session(self):
        """Writing the catalogue has a financial consequence for every sale that follows."""
        tenant_id = self.tenant()
        headers = self.scoped(tenant_id, [
            "catalog.product.write", "catalog.price.write", "catalog.promotion.write",
            "catalog.discount.approve", "catalog.bundle.write",
            "catalog.product.publish"])
        attempts = [
            ("/catalog/products",
             {"product_key": "blocked", "product_type": "service", **self.correlation()}),
            ("/catalog/price-books",
             {"price_book_key": "blocked", "display_name": "B", "currency": "JOD",
              "effective_from": FROM, **self.correlation()}),
            ("/catalog/promotions",
             {"promotion_key": "blocked", "display_name": "P",
              "promotion_kind": "automatic", "percent_bp": 100,
              "effective_from": FROM, **self.correlation()}),
        ]
        for path, body in attempts:
            response = self.client.post(path, json=body, headers=headers)
            self.assertEqual(response.status_code, 403, f"{path}: {response.text}")

    def test_the_two_reads_a_till_does_are_routine(self):
        """A step-up requirement on resolving a price would mean nothing is ever sold."""
        tenant_id = self.tenant()
        _, variant_id = self.sellable(tenant_id, amount=4500)
        headers = self.scoped(tenant_id, ["catalog.price.resolve"])
        resolved = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", **self.correlation()},
            headers=headers)
        self.assertEqual(resolved.status_code, 201, resolved.text)
        self.assertEqual(resolved.json()["final_amount_minor"], 4500)

    def test_a_malformed_id_is_a_422_on_every_route_that_takes_one(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        for path in ("/catalog/resolutions/not-a-uuid",
                     "/catalog/bundles/not-a-uuid/status?order_reference=x"):
            response = self.client.get(path, headers=owner)
            self.assertEqual(response.status_code, 422, f"{path}: {response.text}")


if __name__ == "__main__":
    unittest.main()

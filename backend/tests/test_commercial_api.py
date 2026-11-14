"""MOD-017 COM-01 and COM-03 over HTTP, with the credentials a real caller would hold.

**Driven through the routes, not the service.** MOD-014's reviewers found four defects in its
request path that a green suite could not see, because every test reached past the gate and
called the service directly -- and MOD-016's reviewers then found that no test had ever called
a `/catalog` route successfully, which is why four of its findings survived a green suite. The
gate, the permission resolution, the action classes and the derived fields all live on this
path.

Risk class for this module is Financial Critical, so the tests that matter most are the ones
about money and about access: that a balance cannot be spent twice, that a serial is never
reused, that the two invoice statuses move independently, and that an unknown provider answer
settles nothing.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, date, datetime, timedelta

from app.commercial import service as commercial
from app.errors import Conflict
from tests.support import GatedApiTestCase

FROM = "2026-01-01T00:00:00+00:00"

#: **The lifecycle dates are relative to today, not literals.** A freeze has to start inside
#: the contract year it is decided in -- that bound is what stops a member who has spent their
#: allowance reaching back into last year's -- so a suite with hard-coded 2026 dates would
#: start failing on a date nobody chose. Every membership here starts ninety days ago, which
#: puts today comfortably inside its first contract year whenever the suite is run.
TODAY = date.today()
MEMBERSHIP_START = TODAY - timedelta(days=90)


def day(offset: int) -> str:
    """A date `offset` days from today, as the API spells one."""
    return (TODAY + timedelta(days=offset)).isoformat()


class CommercialApiTestCase(GatedApiTestCase):
    def scoped(self, tenant_id: str, permissions: list[str]) -> dict[str, str]:
        """Headers for a session holding exactly these permissions, at AAL 1."""
        return self.headers(tenant_id, self.grant(tenant_id, permissions))

    # ---------------------------------------------------------------- fixtures

    def person(self, tenant_id: str, name: str = "Jane Smith") -> str:
        created = self.client.post("/people", json={
            "legal_name": name, "profile_kinds": ["member"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["person_id"])

    def legal_entity(self, tenant_id: str) -> str:
        """The entity that invoices. **MOD-004 built the table and nothing filled it** until
        COM-03-R07 needed per-entity fiscal uniqueness, which is how a two-module-old gap
        surfaced -- a foreign key nobody could satisfy."""
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Fitness Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        self.assertEqual(org.status_code, 201, org.text)
        entity = self.client.post("/legal-entities", json={
            "organization_id": org.json()["organization_id"],
            "registered_name": "Veyro Fitness Ltd", "tax_number": "JO-123456",
            **self.correlation()}, headers=owner)
        self.assertEqual(entity.status_code, 201, entity.text)
        return str(entity.json()["legal_entity_id"])

    def location(self, tenant_id: str, *, timezone: str = "Asia/Amman",
                 brand_id: str | None = None) -> tuple[str, str]:
        """A location with a timezone. Returns `(location_id, brand_id)`.

        **The entitlement scope checks need a real location now**, because the service derives
        the brand and the local time from one rather than taking them from the caller. The
        timezone is the point: an off-peak window is stated in the member's local time.
        """
        owner = self.headers(tenant_id)
        if brand_id is None:
            org = self.client.post("/organizations", json={
                "legal_name": "Scoped Ltd", "country_code": "JO", **self.correlation()},
                headers=owner)
            self.assertEqual(org.status_code, 201, org.text)
            brand = self.client.post("/brands", json={
                "organization_id": org.json()["organization_id"], "brand_name": "North"},
                headers=owner)
            self.assertEqual(brand.status_code, 201, brand.text)
            brand_id = str(brand.json()["brand_id"])
        created = self.client.post("/locations", json={
            "brand_id": brand_id, "location_name": "Downtown", "timezone": timezone},
            headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["location_id"]), brand_id

    def local_minute_at(self, timezone: str) -> int:
        """Minutes since midnight at that location, right now, the way the service computes it.

        Read through PostgreSQL rather than Python's `zoneinfo`, because PostgreSQL's zone
        database is the one the service uses and a test that agreed with a different one would
        pass or fail by the month.
        """
        with self._tenant_pool.connection() as conn:
            row = conn.execute(
                "SELECT extract(hour FROM now() AT TIME ZONE %s) * 60"
                " + extract(minute FROM now() AT TIME ZONE %s)",
                (timezone, timezone)).fetchone()
        assert row is not None
        return int(row[0])

    def contract(self, tenant_id: str, **kwargs) -> str:
        """A published contract version, drafted by the owner and published by somebody else.

        **Two identities, because the schema compares them.** `mem_contract_versions_
        publisher_is_not_author` makes the separation a fact about the row rather than a habit
        of the service, so a fixture that used one session could not write the fixture at all.
        """
        body = {"contract_key": f"c{uuid.uuid4().hex[:8]}", "body": "Standard terms.",
                **self.correlation()}
        body.update(kwargs)
        created = self.client.post(
            "/memberships/contract-versions", json=body,
            headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        self.publish_contract(tenant_id, str(created.json()["contract_version_id"]))
        return str(body["contract_key"])

    def publisher(self, tenant_id: str) -> dict[str, str]:
        """Headers for a stepped-up session that may publish a contract and nothing else."""
        if tenant_id not in getattr(self, "_publishers", {}):
            if not hasattr(self, "_publishers"):
                self._publishers: dict[str, str] = {}
            self._publishers[tenant_id] = self.stepped_grant(
                tenant_id, ["membership.contract.publish"])
        return self.headers(tenant_id, self._publishers[tenant_id])

    def publish_contract(self, tenant_id: str, version_id: str) -> dict:
        published = self.client.post(
            f"/memberships/contract-versions/{version_id}/publish",
            json=self.correlation(), headers=self.publisher(tenant_id))
        self.assertEqual(published.status_code, 200, published.text)
        return dict(published.json())

    def membership_product(self, tenant_id: str) -> tuple[str, str]:
        """A published membership product with a live price. Returns `(product_id, variant)`."""
        owner = self.headers(tenant_id)
        created = self.client.post("/catalog/products", json={
            "product_key": f"m{uuid.uuid4().hex[:8]}", "product_type": "membership",
            "texts": [{"locale": "en", "display_name": "Gold membership"}],
            "variants": [{"variant_key": "monthly", "display_name": "Monthly",
                          "term_days": 30}],
            **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        product_id = str(created.json()["product_id"])
        variant_id = str(created.json()["variants"][0]["variant_id"])
        book = self.client.post("/catalog/price-books", json={
            "price_book_key": f"b{uuid.uuid4().hex[:8]}", "display_name": "Standard",
            "currency": "JOD", "effective_from": FROM, **self.correlation()},
            headers=owner)
        self.assertEqual(book.status_code, 201, book.text)
        book_id = str(book.json()["price_book_id"])
        self.assertEqual(self.client.post(
            f"/catalog/price-books/{book_id}/activate", json=self.correlation(),
            headers=owner).status_code, 200)
        priced = self.client.post("/catalog/prices", json={
            "price_book_id": book_id, "variant_id": variant_id, "amount_minor": 4500,
            "effective_from": FROM, **self.correlation()}, headers=owner)
        self.assertEqual(priced.status_code, 201, priced.text)
        published = self.client.post(
            f"/catalog/products/{product_id}/publish",
            json={"expected_version": 1, **self.correlation()}, headers=owner)
        self.assertEqual(published.status_code, 200, published.text)
        return product_id, variant_id

    def terms(self, tenant_id: str, contract_key: str, product_id: str, **kwargs) -> str:
        body = {"product_id": product_id, "contract_key": contract_key,
                "membership_kind": "recurring", **self.correlation()}
        body.update(kwargs)
        created = self.client.post(
            "/memberships/terms", json=body, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["membership_terms_id"])

    def membership(self, tenant_id: str, *, contract: dict | None = None,
                   starts_on: str = "") -> dict:
        """A live membership, from contract through activation. Returns the activation body
        plus the ids needed to drive the lifecycle."""
        owner = self.headers(tenant_id)
        starts_on = starts_on or MEMBERSHIP_START.isoformat()
        contract_key = self.contract(tenant_id, **(contract or {}))
        product_id, variant_id = self.membership_product(tenant_id)
        terms_id = self.terms(tenant_id, contract_key, product_id)
        person_id = self.person(tenant_id)
        agreement = self.client.post("/memberships/agreements", json={
            "person_id": person_id, "membership_terms_id": terms_id,
            "variant_id": variant_id, "amount_minor": 4500, "currency": "JOD",
            "starts_on": starts_on, **self.correlation()}, headers=owner)
        self.assertEqual(agreement.status_code, 201, agreement.text)
        agreement_id = str(agreement.json()["agreement_id"])
        signed = self.client.post(
            f"/memberships/agreements/{agreement_id}/sign", json={
                "signature_kind": "click_through",
                "signature_evidence_ref": f"s3://signatures/{agreement_id}",
                "signed_by_person_id": person_id, **self.correlation()}, headers=owner)
        self.assertEqual(signed.status_code, 200, signed.text)
        active = self.client.post("/memberships", json={
            "agreement_id": agreement_id,
            "membership_number": f"M{uuid.uuid4().hex[:8].upper()}",
            "idempotency_key": f"act-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner)
        self.assertEqual(active.status_code, 201, active.text)
        return {"membership_id": str(active.json()["membership_id"]),
                "agreement_id": agreement_id, "person_id": person_id,
                "variant_id": variant_id, "terms_id": terms_id,
                "contract_key": contract_key,
                "current_period_start": active.json()["current_period_start"],
                "current_period_end": active.json()["current_period_end"]}

    def policy(self, tenant_id: str, **kwargs) -> str:
        body = {"policy_key": f"p{uuid.uuid4().hex[:8]}", "display_name": "Classes",
                "entitlement_type": "class_credit", **self.correlation()}
        body.update(kwargs)
        created = self.client.post(
            "/member-entitlements/policies", json=body, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["policy_id"])

    def entitlement_grant(
        self, tenant_id: str, policy_id: str, person_id: str, **kwargs,
    ) -> str:
        body = {"person_id": person_id, "policy_id": policy_id,
                "source_kind": "goodwill", "valid_from": FROM, "quantity": 10,
                "reason": "ten class pack", **self.correlation()}
        body.update(kwargs)
        created = self.client.post(
            "/member-entitlements/grants", json=body, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["grant_id"])

    def intent(self, tenant_id: str, billing: dict, invoice: dict | None = None,
               **kwargs) -> dict:
        body = {"billing_account_id": billing["billing_account_id"],
                "amount_minor": invoice["gross_minor"] if invoice else 5220,
                "method": "card", "provider_key": "acme.payments",
                "idempotency_key": f"pi-{uuid.uuid4().hex[:8]}", **self.correlation()}
        if invoice is not None:
            body["invoice_id"] = invoice["invoice_id"]
        body.update(kwargs)
        created = self.client.post(
            "/finance/payment-intents", json=body, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return dict(created.json())

    def paid(self, tenant_id: str) -> dict:
        """A billing account with an invoice that has been paid in full."""
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": issued["invoice_id"], "amount_minor": issued["gross_minor"],
            "method": "card", "provider_key": "acme.payments",
            "idempotency_key": f"pi-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner)
        self.assertEqual(intent.status_code, 201, intent.text)
        settled = self.client.post(
            f"/finance/payment-intents/{intent.json()['intent_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()}, headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        return {"billing": billing, "invoice": issued,
                "payment_id": str(settled.json()["payment_id"])}

    def billing(self, tenant_id: str, person_id: str) -> dict:
        """A billing account with an open fiscal series. Returns both ids."""
        owner = self.headers(tenant_id)
        entity_id = self.legal_entity(tenant_id)
        account = self.client.post("/finance/accounts", json={
            "payer_person_id": person_id,
            "account_number": f"A{uuid.uuid4().hex[:8].upper()}", "currency": "JOD",
            "legal_entity_id": entity_id, **self.correlation()}, headers=owner)
        self.assertEqual(account.status_code, 201, account.text)
        series = self.client.post("/finance/fiscal-series", json={
            "legal_entity_id": entity_id, "series_code": "INV",
            **self.correlation()}, headers=owner)
        self.assertEqual(series.status_code, 201, series.text)
        return {"billing_account_id": str(account.json()["billing_account_id"]),
                "series_id": str(series.json()["series_id"]),
                "legal_entity_id": entity_id}

    def invoice(self, tenant_id: str, billing: dict, *, amount: int = 4500,
                rate_bp: int = 1600, due_on: str = "2026-01-15") -> dict:
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Monthly membership", "quantity": 1,
                       "unit_net_minor": amount, "tax_rate_bp": rate_bp}],
            "issued_on": "2026-01-01", "due_on": due_on, "jurisdiction": "JO",
            "idempotency_key": f"inv-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(issued.status_code, 201, issued.text)
        return dict(issued.json())


class ContractAndAgreementTests(CommercialApiTestCase):
    def test_a_contract_version_is_published_in_one_command(self):
        """**Two acts by two people**, and the author is not one of them.

        The first version of this module wrote and published in one command and argued that a
        draft was dangerous because an agreement could be signed against it. That was false --
        `create_agreement` resolves only a published version -- and it bought a real cost: the
        author and the publisher were the same person by definition, on the document a member
        is held to. `mem_contract_versions_publisher_is_not_author` is the half the service
        cannot weaken, and this is the refusal the caller sees.
        """
        tenant_id = self.tenant()
        created = self.client.post("/memberships/contract-versions", json={
            "contract_key": "standard.v1", "body": "Standard terms apply.",
            "minimum_term_months": 12, "notice_days": 30,
            "cancellation_mode": "end_of_notice", "freeze_days_per_year": 30,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["version"], 1)
        self.assertEqual(created.json()["status"], "draft")
        version_id = str(created.json()["contract_version_id"])
        # The author cannot publish their own.
        refused = self.client.post(
            f"/memberships/contract-versions/{version_id}/publish",
            json=self.correlation(), headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("the_author_of_a_contract_version_does_not_publish_it", refused.text)
        # Somebody else can, and a second publication is the idempotent answer.
        published = self.publish_contract(tenant_id, version_id)
        self.assertEqual(published["status"], "published")
        self.assertFalse(published["repeated"])
        self.assertTrue(self.publish_contract(tenant_id, version_id)["repeated"])

    def test_an_agreement_resolves_only_a_published_version(self):
        """Which is why a draft needs no protecting: it is unsignable by construction."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = f"c{uuid.uuid4().hex[:8]}"
        drafted = self.client.post("/memberships/contract-versions", json={
            "contract_key": key, "body": "Draft terms.", **self.correlation()},
            headers=owner)
        self.assertEqual(drafted.status_code, 201, drafted.text)
        product_id, variant_id = self.membership_product(tenant_id)
        terms_id = self.terms(tenant_id, key, product_id)
        refused = self.client.post("/memberships/agreements", json={
            "person_id": self.person(tenant_id), "membership_terms_id": terms_id,
            "variant_id": variant_id, "amount_minor": 4500, "currency": "JOD",
            "starts_on": "2026-01-01", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("no_published_contract_version", refused.text)

    def test_versions_number_themselves_and_the_caller_cannot_choose(self):
        tenant_id = self.tenant()
        for expected in (1, 2, 3):
            created = self.client.post("/memberships/contract-versions", json={
                "contract_key": "standard", "body": f"Revision {expected}.",
                **self.correlation()}, headers=self.headers(tenant_id))
            self.assertEqual(created.status_code, 201, created.text)
            self.assertEqual(created.json()["version"], expected)

    def test_the_agreement_pins_the_version_and_the_caller_cannot_name_it(self):
        """**The authority bought with a body field, designed out.** A caller able to name the
        version could name an older one with a shorter minimum term -- the shape MOD-009,
        MOD-013, MOD-014 and MOD-016 each shipped once. The terms say which contract key
        applies and the service pins the latest published version of it.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = self.contract(tenant_id, minimum_term_months=12)
        product_id, variant_id = self.membership_product(tenant_id)
        terms_id = self.terms(tenant_id, key, product_id)
        # A second, laxer version is published after the terms were defined.
        second = self.client.post("/memberships/contract-versions", json={
            "contract_key": key, "body": "Laxer terms.", "minimum_term_months": 0,
            **self.correlation()}, headers=owner)
        self.assertEqual(second.status_code, 201, second.text)
        self.publish_contract(tenant_id, str(second.json()["contract_version_id"]))
        agreement = self.client.post("/memberships/agreements", json={
            "person_id": self.person(tenant_id), "membership_terms_id": terms_id,
            "variant_id": variant_id, "amount_minor": 4500, "currency": "JOD",
            "starts_on": "2026-01-01",
            # Not a field the body has; if it ever becomes one this test is the guard.
            "contract_version_id": str(uuid.uuid4()),
            **self.correlation()}, headers=owner)
        self.assertEqual(agreement.status_code, 201, agreement.text)
        # The latest published version wins, which is the laxer one -- so no minimum term.
        self.assertIsNone(agreement.json()["minimum_term_ends_on"])

    def test_terms_on_a_product_that_is_not_a_membership_are_refused(self):
        """A contract on a retail SKU would be an obligation nobody could fulfil, and refusing
        it here is cheaper than discovering it at the point of sale."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = self.contract(tenant_id)
        created = self.client.post("/catalog/products", json={
            "product_key": "towel", "product_type": "retail_sku",
            "variants": [{"variant_key": "one", "display_name": "Towel"}],
            **self.correlation()}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        refused = self.client.post("/memberships/terms", json={
            "product_id": created.json()["product_id"], "contract_key": key,
            "membership_kind": "recurring", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("does_not_take_membership_terms", refused.text)

    def test_an_unsigned_agreement_does_not_activate_a_membership(self):
        """The signature is what makes the contract exist; a membership activated from an
        unsigned agreement is access granted under terms nobody accepted."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = self.contract(tenant_id)
        product_id, variant_id = self.membership_product(tenant_id)
        terms_id = self.terms(tenant_id, key, product_id)
        agreement = self.client.post("/memberships/agreements", json={
            "person_id": self.person(tenant_id), "membership_terms_id": terms_id,
            "variant_id": variant_id, "amount_minor": 4500, "currency": "JOD",
            "starts_on": "2026-01-01", **self.correlation()}, headers=owner)
        self.assertEqual(agreement.status_code, 201, agreement.text)
        refused = self.client.post("/memberships", json={
            "agreement_id": agreement.json()["agreement_id"],
            "membership_number": "M-UNSIGNED",
            "idempotency_key": "act-unsigned", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("unsigned", refused.text)

    def test_an_agreement_is_signed_once(self):
        tenant_id = self.tenant()
        live = self.membership(tenant_id)
        again = self.client.post(
            f"/memberships/agreements/{live['agreement_id']}/sign", json={
                "signature_kind": "drawn", "signature_evidence_ref": "s3://second",
                "signed_by_person_id": live["person_id"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 409, again.text)


class LifecycleTests(CommercialApiTestCase):
    def test_a_freeze_past_the_contract_allowance_is_refused(self):
        """The allowance is what the member agreed to. A freeze beyond it is a commercial
        decision somebody has to make deliberately, not a longer freeze that quietly exceeds
        the contract."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 10})
        refused = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(0), "days": 11,
                "reason": "long holiday", "idempotency_key": "f-1",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("allows 10 freeze days", refused.text)

    def test_a_medical_hold_does_not_spend_the_allowance(self):
        """The ordinary commercial term, and the reason the kind exists separately."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 10})
        held = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "medical_hold", "starts_on": day(0), "days": 60,
                "reason": "knee surgery", "evidence_ref": "s3://notes/abc",
                "idempotency_key": "f-med", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(held.status_code, 201, held.text)
        self.assertFalse(held.json()["counts_against_allowance"])

    def test_a_medical_hold_without_evidence_is_refused(self):
        """It is the kind that escapes the allowance, so one with nothing behind it is the one
        a member would claim and nobody could check."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 10})
        refused = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "medical_hold", "starts_on": day(0), "days": 30,
                "reason": "unwell", "idempotency_key": "f-noev",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("medical_has_evidence", refused.text)

    def test_a_membership_is_frozen_once_at_a_time(self):
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 60})
        first = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-2), "days": 7,
                "reason": "holiday", "idempotency_key": "f-a",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(first.status_code, 201, first.text)
        second = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-1), "days": 7,
                "reason": "another holiday", "idempotency_key": "f-b",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(second.status_code, 409, second.text)

    def test_resuming_closes_the_freeze_and_extends_the_term(self):
        """COM-01-R05's expiry extension: by the days actually frozen, not the days asked
        for -- a member who resumed early did not spend the rest."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 60})
        owner = self.headers(tenant_id)
        self.assertEqual(self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-10), "days": 30,
                "reason": "holiday", "idempotency_key": "f-c",
                **self.correlation()}, headers=owner).status_code, 201)
        resumed = self.client.post(
            f"/memberships/{live['membership_id']}/resume", json={
                "reason": "back early", "idempotency_key": "r-c",
                **self.correlation()}, headers=owner)
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["status"], "active")
        self.assertIsNotNone(resumed.json()["freeze_id"])
        # Frozen from February to today, which is well past the thirty asked for -- and the
        # extension is the days actually frozen either way.
        self.assertGreater(resumed.json()["frozen_days"], 0)

    def test_a_lifecycle_command_is_idempotent_on_its_key(self):
        """A retried command must not move a membership twice."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 60})
        owner = self.headers(tenant_id)
        body = {"reason": "back", "idempotency_key": "r-dup", **self.correlation()}
        self.assertEqual(self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-2), "days": 7,
                "reason": "holiday", "idempotency_key": "f-dup",
                **self.correlation()}, headers=owner).status_code, 201)
        first = self.client.post(
            f"/memberships/{live['membership_id']}/resume", json=body, headers=owner)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["repeated"])
        again = self.client.post(
            f"/memberships/{live['membership_id']}/resume", json=body, headers=owner)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(again.json()["repeated"])

    def test_the_preview_and_the_command_agree_or_the_command_refuses(self):
        """**COM-01-R06's disclosure, made provable.** Without the comparison the preview and
        the command are two independent calculations and the member can be shown one figure and
        charged another -- which is the defect a disclosure requirement exists to prevent."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={
            "notice_days": 0, "cancellation_mode": "immediate"})
        owner = self.headers(tenant_id)
        preview = self.client.get(
            f"/memberships/{live['membership_id']}/cancellation-preview", headers=owner)
        self.assertEqual(preview.status_code, 200, preview.text)
        quoted = preview.json()["disclosed_fee_minor"]
        self.assertTrue(preview.json()["explanation"])
        wrong = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "acknowledged_fee_minor": (quoted or 0) + 1,
                "idempotency_key": "c-wrong", **self.correlation()}, headers=owner)
        self.assertEqual(wrong.status_code, 409, wrong.text)
        self.assertIn("re-read the preview", wrong.text)
        right = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "acknowledged_fee_minor": quoted,
                "idempotency_key": "c-right", **self.correlation()}, headers=owner)
        self.assertEqual(right.status_code, 200, right.text)

    def test_a_cancellation_under_notice_leaves_the_membership_active(self):
        """**Which is what a notice period is.** The history carries the decision from today,
        so the member cannot be told later that nobody cancelled -- and the status does not move
        until the notice runs out."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={
            "notice_days": 30, "cancellation_mode": "end_of_notice"})
        owner = self.headers(tenant_id)
        cancelled = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "idempotency_key": "c-notice",
                **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertFalse(cancelled.json()["takes_effect_immediately"])
        now = self.client.get(
            f"/memberships/{live['membership_id']}/as-of?moment={day(0)}",
            headers=owner)
        self.assertEqual(now.status_code, 200, now.text)
        self.assertEqual(now.json()["status_now"], "active")
        self.assertTrue(any(h["change_kind"] == "cancellation"
                            for h in now.json()["history"]))

    def test_the_as_of_read_replays_the_history_rather_than_reading_the_cache(self):
        """COM-01-R07. A cancellation decided in January and effective in March leaves the
        membership active in February, and that is the fact a dispute turns on."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 60})
        owner = self.headers(tenant_id)
        self.assertEqual(self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-2), "days": 7,
                "reason": "holiday", "idempotency_key": "f-asof",
                **self.correlation()}, headers=owner).status_code, 201)
        before = self.client.get(
            f"/memberships/{live['membership_id']}/as-of?moment={day(-5)}",
            headers=owner).json()
        after = self.client.get(
            f"/memberships/{live['membership_id']}/as-of?moment={day(0)}",
            headers=owner).json()
        self.assertEqual(before["status_as_of"], "active")
        self.assertEqual(after["status_as_of"], "frozen")

    def test_a_freeze_cannot_be_booked_for_the_future(self):
        """**Because nothing in this build would apply it when the date arrived.**

        The first version admitted ninety days ahead and wrote `status = 'frozen'` immediately,
        so a freeze booked for August made the membership read as frozen in May -- a turnstile
        asking "is this member frozen" got yes for three months while `status_as_of` correctly
        said no. Leaving the cache behind instead would need a worker to catch it up, and
        there is none: a booked freeze that never takes effect is worse than one that cannot
        be booked. The plan is still a column, because a freeze's intended end and the day it
        actually ended are two facts.
        """
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 60})
        owner = self.headers(tenant_id)
        refused = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(30), "days": 7,
                "reason": "summer", "idempotency_key": "f-future",
                **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("within_the_month_before_today", refused.text)
        backdated = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-3), "days": 7,
                "reason": "agreed on Friday, recorded on Monday",
                "idempotency_key": "f-backdated", **self.correlation()}, headers=owner)
        self.assertEqual(backdated.status_code, 201, backdated.text)
        self.assertEqual(backdated.json()["status"], "frozen")
        self.assertEqual(backdated.json()["planned_ends_on"], day(3))

    def test_a_freeze_outside_the_decision_year_is_refused(self):
        """**The allowance is counted in the contract year containing `starts_on`**, so an
        unbounded start date was a second allowance: a member who had spent all thirty days
        sent a date one day before their anniversary and got thirty more.
        """
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 30})
        owner = self.headers(tenant_id)
        refused = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-400), "days": 7,
                "reason": "last year", "idempotency_key": "f-lastyear",
                **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("within_the_month_before_today", refused.text)

    def test_a_freeze_from_a_terminal_state_is_refused(self):
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={
            "notice_days": 0, "cancellation_mode": "immediate",
            "freeze_days_per_year": 30})
        owner = self.headers(tenant_id)
        self.assertEqual(self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "done", "idempotency_key": "c-term",
                **self.correlation()}, headers=owner).status_code, 200)
        refused = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-3), "days": 7,
                "reason": "too late", "idempotency_key": "f-term",
                **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)


class EntitlementTests(CommercialApiTestCase):
    def balance(self, tenant_id: str, grant_id: str) -> dict:
        read = self.client.get(
            f"/member-entitlements/grants/{grant_id}"
            f"?correlation_id={self.correlation()['correlation_id']}",
            headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        return dict(read.json())

    def test_the_opening_balance_is_a_ledger_row_not_the_quantity_column(self):
        """**The column records what was sold; the ledger records what is left.** Writing the
        grant without its opening movement would make the balance zero on a grant that says
        ten -- which is the shape a stored-balance design produces on every edge case."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), person_id)
        body = self.balance(tenant_id, grant_id)
        self.assertEqual(body["granted_quantity"], 10)
        self.assertEqual(body["balance"], 10)
        self.assertEqual(body["held"], 0)

    def test_a_reservation_holds_quantity_and_a_consumption_moves_nothing(self):
        """The quantity left the balance when it was held; taking it again is the double-count
        the schema's `consume_is_neutral` constraint refuses."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        person_id = self.person(tenant_id)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), person_id)
        held = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 2,
            "idempotency_key": "r-1", **self.correlation()}, headers=owner)
        self.assertEqual(held.status_code, 201, held.text)
        self.assertEqual(held.json()["balance_after"], 8)
        self.assertEqual(self.balance(tenant_id, grant_id)["held"], 2)
        settled = self.client.post(
            f"/member-entitlements/reservations/{held.json()['reservation_id']}/settle",
            json={"outcome": "consumed", **self.correlation()}, headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        self.assertEqual(settled.json()["balance_after"], 8)
        self.assertEqual(self.balance(tenant_id, grant_id)["held"], 0)

    def test_a_release_gives_the_quantity_back(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), self.person(tenant_id))
        held = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 3,
            "idempotency_key": "r-rel", **self.correlation()}, headers=owner)
        self.assertEqual(held.json()["balance_after"], 7)
        released = self.client.post(
            f"/member-entitlements/reservations/{held.json()['reservation_id']}/settle",
            json={"outcome": "released", "reason": "the class was cancelled",
                  **self.correlation()}, headers=owner)
        self.assertEqual(released.status_code, 200, released.text)
        self.assertEqual(released.json()["balance_after"], 10)

    def test_a_release_without_a_reason_is_refused(self):
        """It is the direction that gives a member back something they paid for, so it says
        who did it and on what grounds."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), self.person(tenant_id))
        held = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
            "idempotency_key": "r-nore", **self.correlation()}, headers=owner)
        refused = self.client.post(
            f"/member-entitlements/reservations/{held.json()['reservation_id']}/settle",
            json={"outcome": "released", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("states_why", refused.text)

    def test_a_balance_cannot_be_spent_twice(self):
        """**The property the lock exists for.** MOD-016 shipped the count-then-insert version
        for coupons and a reviewer had four of six concurrent redemptions accepted; here the
        grant is locked before the balance is summed."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), self.person(tenant_id), quantity=2)
        for n in range(2):
            taken = self.client.post("/member-entitlements/reservations", json={
                "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
                "idempotency_key": f"r-x{n}", **self.correlation()}, headers=owner)
            self.assertEqual(taken.status_code, 201, taken.text)
        refused = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
            "idempotency_key": "r-x2", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("0 left and 1 needed", refused.text)

    def test_a_reservation_is_idempotent_on_its_key(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), self.person(tenant_id))
        body = {"grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
                "idempotency_key": "r-dup", **self.correlation()}
        first = self.client.post(
            "/member-entitlements/reservations", json=body, headers=owner)
        again = self.client.post(
            "/member-entitlements/reservations", json=body, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(
            again.json()["reservation_id"], first.json()["reservation_id"])
        self.assertEqual(self.balance(tenant_id, grant_id)["balance"], 9)

    def test_a_reservation_is_settled_once(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), self.person(tenant_id))
        held = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
            "idempotency_key": "r-once", **self.correlation()}, headers=owner)
        path = (f"/member-entitlements/reservations/"
                f"{held.json()['reservation_id']}/settle")
        self.assertEqual(self.client.post(
            path, json={"outcome": "consumed", **self.correlation()},
            headers=owner).status_code, 200)
        again = self.client.post(
            path, json={"outcome": "released", "reason": "changed my mind",
                        **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("already_consumed", again.text)

    def test_an_unlimited_grant_takes_no_quantity_and_a_counted_one_needs_it(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        person_id = self.person(tenant_id)
        unlimited = self.policy(tenant_id, is_counted=False,
                                entitlement_type="location_access")
        refused = self.client.post("/member-entitlements/grants", json={
            "person_id": person_id, "policy_id": unlimited,
            "source_kind": "goodwill", "valid_from": FROM, "quantity": 5,
            "reason": "wrong shape", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("takes_no_quantity", refused.text)
        counted = self.policy(tenant_id)
        missing = self.client.post("/member-entitlements/grants", json={
            "person_id": person_id, "policy_id": counted,
            "source_kind": "goodwill", "valid_from": FROM,
            "reason": "no quantity", **self.correlation()}, headers=owner)
        self.assertEqual(missing.status_code, 422, missing.text)
        self.assertIn("granted_in_a_quantity", missing.text)

    def test_an_off_peak_grant_with_no_local_time_is_refused(self):
        """**MOD-016's `max_per_subject` finding in this module's clothes.** Treating a missing
        local time as "any time" would turn an off-peak membership into an unlimited one by
        omitting a field."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        zone = "Asia/Amman"
        now = self.local_minute_at(zone)
        location_id, brand_id = self.location(tenant_id, timezone=zone)
        # A window around the location's own current local time, clipped to the day.
        start, end = max(now - 60, 0), min(now + 60, 1440)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), self.person(tenant_id),
            usable_from_minute=start, usable_to_minute=end)
        refused = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
            "idempotency_key": "r-nohour", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("no local time", refused.text)
        inside = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
            "location_id": location_id, "idempotency_key": "r-hour",
            **self.correlation()}, headers=owner)
        self.assertEqual(inside.status_code, 201, inside.text)

    def test_the_local_time_is_derived_from_the_location_not_the_caller(self):
        """**Derive, never accept.** `local_minute` was a body field, so an off-peak grant was
        drawn on at any hour by sending a minute inside the window -- the whole point of an
        off-peak membership being that it is cheaper. There is no field now, and the window is
        evaluated against the time of day at the location's own timezone.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        zone = "Asia/Amman"
        now = self.local_minute_at(zone)
        location_id, _ = self.location(tenant_id, timezone=zone)
        # A one-hour window that definitely does not contain the current local time.
        start = (now + 180) % 1380
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), self.person(tenant_id),
            usable_from_minute=start, usable_to_minute=start + 60)
        refused = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
            "location_id": location_id,
            # Not a field the body has; if it ever becomes one this test is the guard.
            "local_minute": start + 1,
            "idempotency_key": "r-outside", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("usable between", refused.text)

    def test_a_scoped_grant_is_refused_outside_its_scope(self):
        """**And the brand is the location's, not the caller's.** It was a body field, so a
        grant scoped to one brand was drawn on at another by sending the grant's own brand id.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        _, granted_brand = self.location(tenant_id)
        elsewhere, other_brand = self.location(tenant_id)
        self.assertNotEqual(granted_brand, other_brand)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), self.person(tenant_id),
            brand_id=granted_brand)
        refused = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
            "location_id": elsewhere,
            # Not a field the body has; the brand comes from the location above.
            "brand_id": granted_brand,
            "idempotency_key": "r-scope", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("another brand", refused.text)


class InvoiceTests(CommercialApiTestCase):
    def test_an_invoice_carries_its_lines_its_tax_and_a_fiscal_serial(self):
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        self.assertEqual(issued["net_minor"], 4500)
        self.assertEqual(issued["tax_minor"], 720)
        self.assertEqual(issued["gross_minor"], 5220)
        self.assertEqual(issued["serial"], 1)
        self.assertEqual(issued["document_number"], "INV-000001")
        read = self.client.get(
            f"/finance/invoices/{issued['invoice_id']}",
            headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(len(read.json()["lines"]), 1)
        self.assertEqual(read.json()["lines"][0]["tax_minor"], 720)

    def test_serials_run_in_order_with_no_gaps(self):
        """**A gap in a tax series is something an authority asks about**, and two invoices
        sharing a serial is a tax offence rather than a bug. A PostgreSQL sequence is
        explicitly non-transactional and leaves gaps on rollback, so the counter is a row taken
        under a lock."""
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        serials = [self.invoice(tenant_id, billing)["serial"] for _ in range(4)]
        self.assertEqual(serials, [1, 2, 3, 4])

    def test_a_rolled_back_issue_does_not_consume_a_serial(self):
        """The property a sequence could not give. An invoice refused for any reason leaves the
        counter where it was."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        self.assertEqual(self.invoice(tenant_id, billing)["serial"], 1)
        refused = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Bad", "quantity": 1,
                       "unit_net_minor": 100, "tax_rate_bp": 1600}],
            "issued_on": "2026-02-01", "due_on": "2026-01-01", "jurisdiction": "JO",
            "idempotency_key": "inv-bad", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(self.invoice(tenant_id, billing)["serial"], 2)

    def test_an_invoice_is_idempotent_on_its_key(self):
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        body = {
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Membership", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 1600}],
            "issued_on": "2026-01-01", "due_on": "2026-01-15", "jurisdiction": "JO",
            "idempotency_key": "inv-once", **self.correlation()}
        owner = self.headers(tenant_id)
        first = self.client.post("/finance/invoices", json=body, headers=owner)
        again = self.client.post("/finance/invoices", json=body, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["invoice_id"], first.json()["invoice_id"])

    def test_a_series_from_another_legal_entity_is_refused(self):
        """**COM-03-R07's per-entity uniqueness defeated from the side nobody watches**: the
        index would still hold and the number would be filed under the wrong taxpayer."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        other_entity = self.legal_entity(tenant_id)
        other_series = self.client.post("/finance/fiscal-series", json={
            "legal_entity_id": other_entity, "series_code": "OTH",
            **self.correlation()}, headers=owner)
        self.assertEqual(other_series.status_code, 201, other_series.text)
        refused = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": other_series.json()["series_id"],
            "lines": [{"description": "Membership", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 1600}],
            "issued_on": "2026-01-01", "due_on": "2026-01-15", "jurisdiction": "JO",
            "idempotency_key": "inv-wrong", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("another_legal_entity", refused.text)

    def test_the_two_statuses_move_independently(self):
        """**Paragraph 1607.** An invoice can be paid and not fiscalized, or fiscalized and
        unpaid, and a single status column would have made one of those unrepresentable."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        submitted = self.client.post(
            f"/finance/invoices/{issued['invoice_id']}/fiscalize",
            json={"target": "submitted", **self.correlation()}, headers=owner)
        self.assertEqual(submitted.status_code, 200, submitted.text)
        read = self.client.get(
            f"/finance/invoices/{issued['invoice_id']}", headers=owner).json()
        self.assertEqual(read["fiscal_status"], "submitted")
        self.assertEqual(read["payment_status"], "unpaid")

    def test_fiscal_completion_needs_the_authority_acknowledgement(self):
        """**The Jordan rule paragraph 1607 names, and the general shape besides.** Every
        invoice has a server-allocated serial, so the serial alone could never be the test:
        numbering is not filing."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        path = f"/finance/invoices/{issued['invoice_id']}/fiscalize"
        self.assertEqual(self.client.post(
            path, json={"target": "submitted", **self.correlation()},
            headers=owner).status_code, 200)
        self.assertEqual(self.client.post(
            path, json={"target": "acknowledged", **self.correlation()},
            headers=owner).status_code, 200)
        without = self.client.post(
            path, json={"target": "fiscal_complete", **self.correlation()},
            headers=owner)
        self.assertEqual(without.status_code, 409, without.text)
        self.assertIn("acknowledgement", without.text)
        with_ack = self.client.post(
            path, json={"target": "fiscal_complete", "ack_ref": "JOFOTARA-77",
                        **self.correlation()}, headers=owner)
        self.assertEqual(with_ack.status_code, 200, with_ack.text)
        self.assertTrue(with_ack.json()["acknowledged"])

    def test_a_fiscal_move_the_machine_does_not_have_is_refused(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        refused = self.client.post(
            f"/finance/invoices/{issued['invoice_id']}/fiscalize",
            json={"target": "fiscal_complete", "ack_ref": "X", **self.correlation()},
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)


class PaymentTests(CommercialApiTestCase):
    def test_a_success_records_a_payment_and_settles_the_invoice(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        intent = self.intent(tenant_id, billing, issued)
        settled = self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/settle",
            json={"outcome": "succeeded", "provider_ref": "ch_123",
                  **self.correlation()}, headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        self.assertIsNotNone(settled.json()["payment_id"])
        read = self.client.get(
            f"/finance/invoices/{issued['invoice_id']}", headers=owner).json()
        self.assertEqual(read["payment_status"], "paid")
        self.assertEqual(read["paid_minor"], 5220)

    def test_one_intent_produces_one_payment(self):
        """**A provider callback delivered twice is the ordinary case**, and the unique index is
        what makes the replay free instead of a double charge."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        intent = self.intent(tenant_id, billing)
        path = f"/finance/payment-intents/{intent['intent_id']}/settle"
        body = {"outcome": "succeeded", **self.correlation()}
        self.assertEqual(
            self.client.post(path, json=body, headers=owner).status_code, 200)
        again = self.client.post(path, json=body, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("already_succeeded", again.text)

    def test_a_part_payment_reads_as_part_paid_and_overdue_when_late(self):
        """Derived from the money *and the date*, never asserted by a caller.

        The due date matters and the first version of this test forgot it: a part payment made
        after the due date is `overdue`, not `part_paid`, which is the correct answer and the
        one a collections queue needs. So the test pins both -- one invoice due in the future
        and one already past due.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        late = self.invoice(tenant_id, billing)
        late_intent = self.intent(tenant_id, billing, late, amount_minor=1000)
        self.assertEqual(self.client.post(
            f"/finance/payment-intents/{late_intent['intent_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()},
            headers=owner).status_code, 200)
        self.assertEqual(self.client.get(
            f"/finance/invoices/{late['invoice_id']}",
            headers=owner).json()["payment_status"], "overdue")
        issued = self.invoice(tenant_id, billing, due_on="2099-01-01")
        intent = self.intent(tenant_id, billing, issued, amount_minor=1000)
        self.assertEqual(self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()},
            headers=owner).status_code, 200)
        read = self.client.get(
            f"/finance/invoices/{issued['invoice_id']}", headers=owner).json()
        self.assertEqual(read["payment_status"], "part_paid")
        self.assertEqual(read["paid_minor"], 1000)

    def test_an_unknown_provider_answer_settles_nothing(self):
        """**Paragraph 1609.** A provider that answered nothing has told us nothing; recording
        that as declined is how a member is dunned for a payment that succeeded."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        intent = self.intent(tenant_id, billing)
        unknown = self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/settle",
            json={"outcome": "unknown", "failure_detail": "gateway timeout",
                  **self.correlation()}, headers=owner)
        self.assertEqual(unknown.status_code, 200, unknown.text)
        self.assertEqual(unknown.json()["status"], "unknown")
        self.assertIn("nothing is settled", unknown.json()["reason"])
        # And it can still be settled afterwards, which is the point of leaving it open.
        later = self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()}, headers=owner)
        self.assertEqual(later.status_code, 200, later.text)

    def test_a_failure_carries_a_code_and_the_code_decides_the_retry(self):
        """**A control decided by matching words in a provider's prose is one anybody can
        change by editing a string** -- MOD-016 shipped exactly that."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        without = self.client.post(
            f"/finance/payment-intents/{self.intent(tenant_id, billing)['intent_id']}"
            "/settle",
            json={"outcome": "failed", **self.correlation()}, headers=owner)
        self.assertEqual(without.status_code, 422, without.text)
        self.assertIn("carries_a_code", without.text)
        stolen = self.client.post(
            f"/finance/payment-intents/{self.intent(tenant_id, billing)['intent_id']}"
            "/settle",
            json={"outcome": "failed", "failure_code": "card_stolen",
                  "failure_detail": "declined for card 4242 held by JANE SMITH",
                  **self.correlation()}, headers=owner)
        self.assertEqual(stolen.status_code, 200, stolen.text)
        self.assertEqual(stolen.json()["failure_class"], "permanent")

    def test_a_reconciliation_does_not_overwrite_a_settled_payment(self):
        """**Only the provider knows what it did; only a human should decide what to do when
        the two records disagree about money.**"""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        intent = self.intent(tenant_id, billing)
        self.assertEqual(self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()},
            headers=owner).status_code, 200)
        escalated = self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/reconcile",
            json={"provider_status": "failed", **self.correlation()}, headers=owner)
        self.assertEqual(escalated.status_code, 200, escalated.text)
        self.assertTrue(escalated.json()["escalated"])
        self.assertEqual(escalated.json()["status"], "succeeded")

    def test_a_reconciliation_resolves_an_unknown_payment(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        intent = self.intent(tenant_id, billing)
        self.assertEqual(self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/settle",
            json={"outcome": "unknown", **self.correlation()},
            headers=owner).status_code, 200)
        resolved = self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/reconcile",
            json={"provider_status": "succeeded", "provider_ref": "ch_late",
                  **self.correlation()}, headers=owner)
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.assertEqual(resolved.json()["status"], "succeeded")
        self.assertIsNotNone(resolved.json()["payment_id"])

    def test_an_intent_nobody_attempted_cannot_be_reconciled_into_a_payment(self):
        """**`finance.payment.take` bought with a different permission.** The settlement path
        was reachable for a `pending` intent, so a caller could create a payment for a charge
        no provider had ever been asked about -- naming the outcome itself and the
        `provider_ref` with it. Reporting a verdict on one is still a read.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        intent = self.intent(tenant_id, billing)
        refused = self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/reconcile",
            json={"provider_status": "succeeded", "provider_ref": "made-up",
                  **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("never_attempted", refused.text)
        # Marking it unknown is still allowed: that is how an intent becomes reconcilable, and
        # it creates nothing.
        held = self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/reconcile",
            json=self.correlation(), headers=owner)
        self.assertEqual(held.status_code, 200, held.text)
        self.assertEqual(held.json()["status"], "unknown")

    def test_no_provider_answer_leaves_it_unknown(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        intent = self.intent(tenant_id, billing)
        held = self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/reconcile",
            json={**self.correlation()}, headers=owner)
        self.assertEqual(held.status_code, 200, held.text)
        self.assertEqual(held.json()["reason_code"], "provider_did_not_answer")

    def test_an_invoice_in_another_currency_is_refused(self):
        """Two minor-unit counts that are equal and mean different sums of money, which is the
        comparison MOD-015's money discipline forbids."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        person_id = self.person(tenant_id)
        jod = self.billing(tenant_id, person_id)
        usd_entity = jod["legal_entity_id"]
        usd = self.client.post("/finance/accounts", json={
            "payer_person_id": person_id,
            "account_number": f"U{uuid.uuid4().hex[:8].upper()}", "currency": "USD",
            "legal_entity_id": usd_entity, **self.correlation()}, headers=owner)
        self.assertEqual(usd.status_code, 201, usd.text)
        issued = self.invoice(tenant_id, jod)
        refused = self.client.post("/finance/payment-intents", json={
            "billing_account_id": str(usd.json()["billing_account_id"]),
            "invoice_id": issued["invoice_id"], "amount_minor": 5220,
            "method": "card", "provider_key": "acme.payments",
            "idempotency_key": "pi-cross", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)


class RefundAndRecoveryTests(CommercialApiTestCase):
    def test_a_refund_needs_two_people_and_both_are_derived(self):
        """**Paragraph 1598's approval, with the separation of duties real from the start.**
        MOD-016 collapsed the two acts into one insert and all three of its reviewers approved
        their own override by typing a uuid -- there was nothing a stricter check could have
        consulted. Here the requester comes from the requesting session and is copied onto the
        approval, so the constraint compares two identities the server derived.
        """
        tenant_id = self.tenant()
        state = self.paid(tenant_id)
        requester = self.scoped(tenant_id, ["finance.refund.request"])
        asked = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 1000,
            "reason": "goodwill", **self.correlation()}, headers=requester)
        self.assertEqual(asked.status_code, 201, asked.text)
        approved = self.client.post("/finance/refunds", json={
            "request_id": asked.json()["request_id"],
            "approval_reason": "agreed at the desk",
            "idempotency_key": "rf-1", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(approved.status_code, 201, approved.text)
        self.assertNotEqual(
            approved.json()["approved_by"], approved.json()["requested_by"])
        self.assertEqual(approved.json()["status"], "pending")

    def test_the_approver_cannot_approve_the_request_they_made(self):
        tenant_id = self.tenant()
        state = self.paid(tenant_id)
        owner = self.headers(tenant_id)
        asked = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 1000,
            "reason": "mine", **self.correlation()}, headers=owner)
        self.assertEqual(asked.status_code, 201, asked.text)
        refused = self.client.post("/finance/refunds", json={
            "request_id": asked.json()["request_id"],
            "approval_reason": "mine too", "idempotency_key": "rf-self",
            **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("approver_is_not_requester", refused.text)

    def test_a_refund_cannot_exceed_what_was_paid(self):
        """Money leaving that never arrived."""
        tenant_id = self.tenant()
        state = self.paid(tenant_id)
        requester = self.scoped(tenant_id, ["finance.refund.request"])
        refused = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 99_999,
            "reason": "too much", **self.correlation()}, headers=requester)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("refundable", refused.text)

    def test_refunds_in_flight_count_against_what_is_refundable(self):
        tenant_id = self.tenant()
        state = self.paid(tenant_id)
        requester = self.scoped(tenant_id, ["finance.refund.request"])
        owner = self.headers(tenant_id)
        first = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 5000,
            "reason": "most of it", **self.correlation()}, headers=requester)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(self.client.post("/finance/refunds", json={
            "request_id": first.json()["request_id"],
            "approval_reason": "agreed", "idempotency_key": "rf-a",
            **self.correlation()}, headers=owner).status_code, 201)
        refused = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 500,
            "reason": "the rest and more", **self.correlation()}, headers=requester)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("220 of this payment is refundable", refused.text)

    def test_one_decision_per_request(self):
        tenant_id = self.tenant()
        state = self.paid(tenant_id)
        requester = self.scoped(tenant_id, ["finance.refund.request"])
        owner = self.headers(tenant_id)
        asked = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 1000,
            "reason": "goodwill", **self.correlation()}, headers=requester)
        body = {"request_id": asked.json()["request_id"],
                "approval_reason": "agreed", **self.correlation()}
        first = self.client.post(
            "/finance/refunds", json={**body, "idempotency_key": "rf-x"},
            headers=owner)
        self.assertEqual(first.status_code, 201, first.text)
        # **A second approval of a decided request is that decision, not a second refund.**
        # It answered 409, so a client whose first call timed out after the commit was told
        # the approval had failed and a second approver was asked for. One decision per
        # request is still the invariant; what changed is what a retry is told.
        again = self.client.post(
            "/finance/refunds", json={**body, "idempotency_key": "rf-y"},
            headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["refund_id"], first.json()["refund_id"])

    def test_a_refund_is_pending_until_something_sends_the_money(self):
        """**There is no provider in this build.** A refund recorded as succeeded with nothing
        having sent money would be the fabricated-evidence shape this codebase has been bitten
        by five times."""
        tenant_id = self.tenant()
        state = self.paid(tenant_id)
        requester = self.scoped(tenant_id, ["finance.refund.request"])
        owner = self.headers(tenant_id)
        asked = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 1000,
            "reason": "goodwill", **self.correlation()}, headers=requester)
        approved = self.client.post("/finance/refunds", json={
            "request_id": asked.json()["request_id"], "approval_reason": "agreed",
            "idempotency_key": "rf-p", **self.correlation()}, headers=owner)
        self.assertEqual(approved.json()["status"], "pending")
        settled = self.client.post(
            f"/finance/refunds/{approved.json()['refund_id']}/settle",
            json={"outcome": "succeeded", "provider_ref": "re_1",
                  **self.correlation()}, headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        self.assertEqual(settled.json()["status"], "succeeded")

    def test_dunning_opens_only_against_an_unpaid_invoice(self):
        """Opening a case against a paid invoice is a member dunned for money they have already
        sent -- the complaint that reaches a regulator rather than a support queue."""
        tenant_id = self.tenant()
        state = self.paid(tenant_id)
        refused = self.client.post("/finance/dunning-cases", json={
            "invoice_id": state["invoice"]["invoice_id"],
            "idempotency_key": "d-paid", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("needs_no_dunning", refused.text)

    def test_one_open_case_per_invoice(self):
        """Two would send the member two dunning journeys for one debt."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        self.assertEqual(self.client.post("/finance/dunning-cases", json={
            "invoice_id": issued["invoice_id"], "idempotency_key": "d-1",
            **self.correlation()}, headers=owner).status_code, 201)
        second = self.client.post("/finance/dunning-cases", json={
            "invoice_id": issued["invoice_id"], "idempotency_key": "d-2",
            **self.correlation()}, headers=owner)
        self.assertEqual(second.status_code, 409, second.text)

    def test_the_journey_escalates_and_the_access_consequence_is_only_recorded(self):
        """**Paragraph 1496.** A dunning case may say access should be suspended; whether it
        *is* suspended is a membership lifecycle change with its own decision and its own
        permission. The two states are related and never conflated."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        opened = self.client.post("/finance/dunning-cases", json={
            "invoice_id": issued["invoice_id"], "idempotency_key": "d-esc",
            **self.correlation()}, headers=owner)
        self.assertEqual(opened.status_code, 201, opened.text)
        self.assertEqual(opened.json()["access_recommendation"], "none")
        case_id = opened.json()["case_id"]
        seen = []
        for _ in range(4):
            advanced = self.client.post(
                f"/finance/dunning-cases/{case_id}/advance",
                json=self.correlation(), headers=owner)
            self.assertEqual(advanced.status_code, 200, advanced.text)
            seen.append(advanced.json()["access_recommendation"])
        self.assertEqual(seen, ["none", "warn", "restrict", "suspend"])
        self.assertTrue(advanced.json()["is_final"])

    def test_a_case_closes_as_recovered_when_the_invoice_is_paid(self):
        """**A control consulted once is a control with a window**, and this window is days
        long: the ordinary thing that happens between two dunning stages is that the member
        pays. Advancing without re-reading is a final notice sent to somebody who settled on
        Tuesday."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        opened = self.client.post("/finance/dunning-cases", json={
            "invoice_id": issued["invoice_id"], "idempotency_key": "d-rec",
            **self.correlation()}, headers=owner)
        self.assertEqual(opened.status_code, 201, opened.text)
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": issued["invoice_id"], "amount_minor": issued["gross_minor"],
            "method": "cash", "provider_key": "front.desk",
            "idempotency_key": "pi-rec", **self.correlation()}, headers=owner)
        self.assertEqual(self.client.post(
            f"/finance/payment-intents/{intent.json()['intent_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()},
            headers=owner).status_code, 200)
        advanced = self.client.post(
            f"/finance/dunning-cases/{opened.json()['case_id']}/advance",
            json=self.correlation(), headers=owner)
        self.assertEqual(advanced.status_code, 200, advanced.text)
        self.assertEqual(advanced.json()["status"], "recovered")


class PermissionClassTests(CommercialApiTestCase):
    def test_every_money_write_needs_a_stepped_up_session(self):
        """Every lifecycle act either changes what a member may do or changes what they owe."""
        tenant_id = self.tenant()
        headers = self.scoped(tenant_id, [
            "membership.agreement.write", "membership.agreement.activate",
            "membership.lifecycle.change", "membership.entitlement.grant",
            "finance.account.write", "finance.invoice.issue", "finance.payment.take",
            "finance.refund.approve", "finance.dunning.manage",
            "finance.fiscal.manage", "finance.payment.reconcile"])
        attempts = [
            ("/memberships/contract-versions",
             {"contract_key": "blocked", "body": "terms", **self.correlation()}),
            ("/finance/accounts",
             {"payer_person_id": str(uuid.uuid4()), "account_number": "BLOCKED-1",
              "currency": "JOD", "legal_entity_id": str(uuid.uuid4()),
              **self.correlation()}),
            ("/member-entitlements/policies",
             {"policy_key": "blocked", "display_name": "Blocked",
              "entitlement_type": "class_credit", **self.correlation()}),
        ]
        for path, body in attempts:
            response = self.client.post(path, json=body, headers=headers)
            self.assertEqual(response.status_code, 403, f"{path}: {response.text}")

    def test_the_two_reads_a_turnstile_does_are_routine(self):
        """A step-up on "may this member train" would mean nobody trains."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id)
        headers = self.scoped(tenant_id, ["membership.record.read"])
        read = self.client.get(
            f"/memberships/{live['membership_id']}/as-of?moment=2026-06-01",
            headers=headers)
        self.assertEqual(read.status_code, 200, read.text)

    def test_a_malformed_id_is_a_422_on_every_route_that_takes_one(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        corr = self.correlation()["correlation_id"]
        for path in (
            "/memberships/not-a-uuid/cancellation-preview",
            "/memberships/not-a-uuid/as-of?moment=2026-01-01",
            f"/member-entitlements/grants/not-a-uuid?correlation_id={corr}",
            "/finance/invoices/not-a-uuid",
        ):
            response = self.client.get(path, headers=owner)
            self.assertEqual(response.status_code, 422, f"{path}: {response.text}")


if __name__ == "__main__":
    unittest.main()


class ReviewRegressionTests(CommercialApiTestCase):
    """One test per review finding that no other test here already covers.

    Named for the defect rather than for the fix, which is this repository's convention since
    MOD-007: a test called `test_the_fix_works` stops meaning anything the moment somebody
    rewrites the fix.
    """

    def test_an_agreement_takes_its_price_from_the_resolution_it_cites(self):
        """**A cited authority is the authority, not decoration beside the figure.** The first
        version took the amount, the currency and the resolution id from the caller and never
        compared them, so an agreement could cite MOD-016's receipt for 45.00 and record 4.50
        -- with the resolution id on the row making the figure read as priced and approved.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = self.contract(tenant_id)
        product_id, variant_id = self.membership_product(tenant_id)
        terms_id = self.terms(tenant_id, key, product_id)
        person_id = self.person(tenant_id)
        resolved = self.client.post("/catalog/prices/resolve", json={
            "variant_id": variant_id, "currency": "JOD", "channel": "web",
            "subject_person_id": person_id, **self.correlation()}, headers=owner)
        self.assertEqual(resolved.status_code, 201, resolved.text)
        resolution_id = str(resolved.json()["resolution_id"])
        self.assertEqual(resolved.json()["final_amount_minor"], 4500)
        agreed = self.client.post("/memberships/agreements", json={
            "person_id": person_id, "membership_terms_id": terms_id,
            "variant_id": variant_id, "price_resolution_id": resolution_id,
            # A tenth of the resolved price, which is what the row would have recorded.
            "amount_minor": 450, "currency": "JOD",
            "starts_on": MEMBERSHIP_START.isoformat(), **self.correlation()},
            headers=owner)
        self.assertEqual(agreed.status_code, 201, agreed.text)
        self.assertEqual(agreed.json()["amount_minor"], 4500)
        self.assertEqual(agreed.json()["currency"], "JOD")

    def test_a_resolution_for_another_variant_is_refused(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = self.contract(tenant_id)
        product_id, variant_id = self.membership_product(tenant_id)
        other_product, other_variant = self.membership_product(tenant_id)
        terms_id = self.terms(tenant_id, key, product_id)
        person_id = self.person(tenant_id)
        resolved = self.client.post("/catalog/prices/resolve", json={
            "variant_id": other_variant, "currency": "JOD", "channel": "web",
            "subject_person_id": person_id, **self.correlation()}, headers=owner)
        self.assertEqual(resolved.status_code, 201, resolved.text)
        refused = self.client.post("/memberships/agreements", json={
            "person_id": person_id, "membership_terms_id": terms_id,
            "variant_id": variant_id,
            "price_resolution_id": str(resolved.json()["resolution_id"]),
            "amount_minor": 4500, "currency": "JOD",
            "starts_on": MEMBERSHIP_START.isoformat(), **self.correlation()},
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("another_variant", refused.text)

    def test_the_first_billing_period_tiles_with_the_second(self):
        """**One day longer than every later one.** `renewal_period` returns the period *after*
        the date it is given, and the first version kept that window's end while overriding its
        start -- so a monthly membership starting on 1 January ran to 1 February, the next
        period opened on 2 February, and the drift compounded for the life of the membership.
        """
        tenant_id = self.tenant()
        live = self.membership(tenant_id, starts_on="2026-01-01")
        self.assertEqual(live["current_period_start"], "2026-01-01")
        self.assertEqual(live["current_period_end"], "2026-01-31")

    def test_an_activation_is_idempotent_on_its_key(self):
        """A client whose request timed out after the commit was told the activation failed."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        key = self.contract(tenant_id)
        product_id, variant_id = self.membership_product(tenant_id)
        terms_id = self.terms(tenant_id, key, product_id)
        person_id = self.person(tenant_id)
        agreement = self.client.post("/memberships/agreements", json={
            "person_id": person_id, "membership_terms_id": terms_id,
            "variant_id": variant_id, "amount_minor": 4500, "currency": "JOD",
            "starts_on": MEMBERSHIP_START.isoformat(), **self.correlation()},
            headers=owner)
        agreement_id = str(agreement.json()["agreement_id"])
        self.assertEqual(self.client.post(
            f"/memberships/agreements/{agreement_id}/sign", json={
                "signature_kind": "click_through",
                "signature_evidence_ref": f"s3://signatures/{agreement_id}",
                "signed_by_person_id": person_id, **self.correlation()},
            headers=owner).status_code, 200)
        body = {"agreement_id": agreement_id, "membership_number": "M-IDEM-0001",
                "idempotency_key": "act-idem"}
        first = self.client.post(
            "/memberships", json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 201, first.text)
        again = self.client.post(
            "/memberships", json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["membership_id"], first.json()["membership_id"])

    def test_an_idempotency_key_belongs_to_one_command(self):
        """**`_recorded_change` compared the membership and not the `change_kind`.** Three
        commands consult it, so a client reusing one key across a freeze and a cancel got the
        *other* command's change back and was told its own had happened -- a cancel answered
        with a freeze reads as a cancellation that took effect, and nothing cancelled anything.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 60})
        self.assertEqual(self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-2), "days": 7,
                "reason": "holiday", "idempotency_key": "shared-key",
                **self.correlation()}, headers=owner).status_code, 201)
        confused = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "idempotency_key": "shared-key",
                **self.correlation()}, headers=owner)
        self.assertEqual(confused.status_code, 409, confused.text)
        self.assertIn("another_command", confused.text)

    def test_a_retried_cancellation_is_checked_against_the_fee_it_recorded(self):
        """**The disclosure check bypassed by retrying with the number you wanted.** The first
        version echoed the caller's acknowledged fee straight back, so a second call sending a
        different figure was told it had been accepted.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        live = self.membership(tenant_id, contract={
            "notice_days": 0, "cancellation_mode": "immediate"})
        preview = self.client.get(
            f"/memberships/{live['membership_id']}/cancellation-preview", headers=owner)
        self.assertEqual(preview.status_code, 200, preview.text)
        fee = preview.json()["disclosed_fee_minor"]
        first = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "acknowledged_fee_minor": fee,
                "idempotency_key": "c-retry", **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 200, first.text)
        refused = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "acknowledged_fee_minor": 0,
                "idempotency_key": "c-retry", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("disclosed fee", refused.text)

    def test_cancelling_a_membership_revokes_what_it_was_paying_for(self):
        """**Access nobody is paying for.** Paragraph 1496 keeps membership, billing and access
        state apart, and that is about not *conflating* them rather than leaving them
        unrelated: the first version cancelled the membership and left every grant `active`, so
        a member with twenty classes left kept all twenty and the turnstile had no reason to
        stop them.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        live = self.membership(tenant_id, contract={
            "notice_days": 0, "cancellation_mode": "immediate"})
        granted = self.client.post("/member-entitlements/grants", json={
            "person_id": live["person_id"], "policy_id": self.policy(tenant_id),
            "source_kind": "membership", "membership_id": live["membership_id"],
            "valid_from": FROM, "quantity": 20, "reason": "sold with the membership",
            **self.correlation()}, headers=owner)
        self.assertEqual(granted.status_code, 201, granted.text)
        grant_id = str(granted.json()["grant_id"])
        cancelled = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "idempotency_key": "c-revoke",
                **self.correlation()}, headers=owner)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual([r["grant_id"] for r in cancelled.json()["entitlements_revoked"]],
                         [grant_id])
        self.assertEqual(cancelled.json()["entitlements_revoked"][0]["quantity_revoked"], 20)
        balance = self.client.get(
            f"/member-entitlements/grants/{grant_id}"
            f"?correlation_id={uuid.uuid4()}", headers=owner)
        self.assertEqual(balance.status_code, 200, balance.text)
        self.assertEqual(balance.json()["status"], "revoked")
        self.assertEqual(balance.json()["balance"], 0)

    def test_a_revocation_writes_off_what_was_left_and_is_idempotent(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), self.person(tenant_id))
        revoked = self.client.post(
            f"/member-entitlements/grants/{grant_id}/revoke", json={
                "reason": "sold in error", **self.correlation()}, headers=owner)
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(revoked.json()["quantity_revoked"], 10)
        self.assertFalse(revoked.json()["repeated"])
        again = self.client.post(
            f"/member-entitlements/grants/{grant_id}/revoke", json={
                "reason": "sold in error", **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(again.json()["repeated"])
        drawn = self.client.post("/member-entitlements/reservations", json={
            "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
            "idempotency_key": "r-revoked", **self.correlation()}, headers=owner)
        self.assertEqual(drawn.status_code, 409, drawn.text)
        self.assertIn("revoked", drawn.text)

    def test_a_medical_holds_reason_is_not_readable_at_any_assurance_level(self):
        """**A health fact is a health fact whatever column it is in.** `evidence_ref` is
        constrained to a locator so a diagnosis cannot be stored there, and `reason` beside it
        is unconstrained prose the ordinary operator will use to say why. The lifecycle history
        is `membership.record.read`, which is routine and AAL 1 -- a front desk and a
        turnstile -- so it put a staged diagnosis in front of the cheapest read in the module.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 10})
        diagnosis = "stage II non-Hodgkin lymphoma, chemotherapy from March"
        self.assertEqual(self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "medical_hold", "starts_on": day(-1), "days": 60,
                "reason": diagnosis, "evidence_ref": "s3://notes/abc",
                "idempotency_key": "f-health", **self.correlation()},
            headers=owner).status_code, 201)
        read = self.client.get(
            f"/memberships/{live['membership_id']}/as-of?moment={day(0)}", headers=owner)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertNotIn("lymphoma", read.text)
        held = [h for h in read.json()["history"] if h["change_kind"] == "medical_hold"]
        self.assertEqual(len(held), 1)
        self.assertTrue(held[0]["reason_withheld"])
        # And the entry itself is still there: a hold a reader cannot see at all is a gap in a
        # dispute record, which is MOD-014's "a redacted record still exists".
        self.assertEqual(held[0]["to_status"], "frozen")

    def test_a_locator_column_refuses_something_that_is_not_a_locator(self):
        """**Paragraph 1597 quoted ten lines above a column that accepted a card number.** All
        three locators were non-blank text, which made the absence of a PAN column a naming
        convention rather than a control.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        refused = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"], "amount_minor": 4500,
            "method": "card", "provider_key": "acme.payments",
            "payment_method_ref": "4242424242424242 exp 09/29 cvv 123",
            "idempotency_key": "pi-pan", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("is_a_locator", refused.text)
        accepted = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"], "amount_minor": 4500,
            "method": "card", "provider_key": "acme.payments",
            "payment_method_ref": "vault://acme/tok_abc123",
            "idempotency_key": "pi-token", **self.correlation()}, headers=owner)
        self.assertEqual(accepted.status_code, 201, accepted.text)

    def test_a_reused_provider_reference_is_a_conflict_and_not_a_500(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        first = self.intent(tenant_id, billing)
        second = self.intent(tenant_id, billing)
        self.assertEqual(self.client.post(
            f"/finance/payment-intents/{first['intent_id']}/settle",
            json={"outcome": "succeeded", "provider_ref": "ch_shared",
                  **self.correlation()}, headers=owner).status_code, 200)
        clash = self.client.post(
            f"/finance/payment-intents/{second['intent_id']}/settle",
            json={"outcome": "succeeded", "provider_ref": "ch_shared",
                  **self.correlation()}, headers=owner)
        self.assertEqual(clash.status_code, 409, clash.text)
        self.assertIn("provider_reference", clash.text)

    def test_an_unknown_refund_counts_against_what_is_still_refundable(self):
        """**`unknown` means the provider did not answer**, so a refund that may well have left
        was treated as money still held and the same amount was approved a second time.
        Settling the first as succeeded afterwards leaves the member refunded twice, which is
        the one direction in this module no later row can correct.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        state = self.paid(tenant_id)
        gross = state["invoice"]["gross_minor"]
        requester = self.scoped(tenant_id, ["finance.refund.request"])

        def ask(amount: int) -> str:
            asked = self.client.post("/finance/refund-requests", json={
                "payment_id": state["payment_id"], "amount_minor": amount,
                "reason": "goodwill", **self.correlation()}, headers=requester)
            self.assertEqual(asked.status_code, 201, asked.text)
            return str(asked.json()["request_id"])

        approved = self.client.post("/finance/refunds", json={
            "request_id": ask(gross), "approval_reason": "agreed",
            "idempotency_key": "rf-unknown-1", **self.correlation()}, headers=owner)
        self.assertEqual(approved.status_code, 201, approved.text)
        held = self.client.post(
            f"/finance/refunds/{approved.json()['refund_id']}/settle",
            json={"outcome": "unknown", **self.correlation()}, headers=owner)
        self.assertEqual(held.status_code, 200, held.text)
        self.assertEqual(held.json()["status"], "unknown")
        # The provider has not said. Nothing of this payment is refundable again, and the
        # refusal lands at the request -- which is the earlier of the two places that count it
        # and the better one for a caller to be told.
        refused = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": gross,
            "reason": "again", **self.correlation()}, headers=requester)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("refundable", refused.text)
        read = self.client.get(
            f"/finance/payments/{state['payment_id']}/refunds", headers=owner)
        self.assertEqual(read.json()["refundable_minor"], 0)

    def test_a_refunded_invoice_stops_reading_paid(self):
        """**`_apply_to_invoice` summed payments and credit notes and never looked at the
        refunds.** So an invoice refunded in full went on reading `paid` -- the figure an
        accountant reconciles a bank statement against, and the one a dunning sweep decides not
        to chase.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        state = self.paid(tenant_id)
        invoice_id = state["invoice"]["invoice_id"]
        before = self.client.get(f"/finance/invoices/{invoice_id}", headers=owner)
        self.assertEqual(before.json()["payment_status"], "paid")
        requester = self.scoped(tenant_id, ["finance.refund.request"])
        asked = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"],
            "amount_minor": state["invoice"]["gross_minor"],
            "reason": "goodwill", **self.correlation()}, headers=requester)
        approved = self.client.post("/finance/refunds", json={
            "request_id": str(asked.json()["request_id"]), "approval_reason": "agreed",
            "idempotency_key": "rf-reflect", **self.correlation()}, headers=owner)
        self.assertEqual(approved.status_code, 201, approved.text)
        self.assertEqual(self.client.post(
            f"/finance/refunds/{approved.json()['refund_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()},
            headers=owner).status_code, 200)
        after = self.client.get(f"/finance/invoices/{invoice_id}", headers=owner)
        self.assertEqual(after.status_code, 200, after.text)
        self.assertNotEqual(after.json()["payment_status"], "paid")
        self.assertEqual(after.json()["refunded_minor"],
                         state["invoice"]["gross_minor"])

    def test_a_refund_is_readable_by_the_person_who_has_to_approve_it(self):
        """Four commands wrote a refund and nothing returned one, so the second person in the
        separation of duties approved a figure they could not see."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        state = self.paid(tenant_id)
        requester = self.scoped(tenant_id, ["finance.refund.request"])
        asked = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 1000,
            "reason": "goodwill", **self.correlation()}, headers=requester)
        self.assertEqual(asked.status_code, 201, asked.text)
        read = self.client.get(
            f"/finance/payments/{state['payment_id']}/refunds", headers=owner)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(len(read.json()["requests"]), 1)
        self.assertEqual(read.json()["requests"][0]["amount_minor"], 1000)
        self.assertEqual(read.json()["refundable_minor"],
                         state["invoice"]["gross_minor"])
        self.assertEqual(read.json()["refunds"], [])

    def test_approving_a_refund_can_name_the_figure_it_is_approving(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        state = self.paid(tenant_id)
        requester = self.scoped(tenant_id, ["finance.refund.request"])
        asked = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 1000,
            "reason": "goodwill", **self.correlation()}, headers=requester)
        refused = self.client.post("/finance/refunds", json={
            "request_id": str(asked.json()["request_id"]), "approval_reason": "agreed",
            "acknowledged_amount_minor": 5000, "idempotency_key": "rf-ack",
            **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("the approval says", refused.text)

    def test_settling_a_refund_needs_the_refund_permission(self):
        """**`finance.payment.take` is for money coming in.** A role holding only "take
        payments" could mark money going out as succeeded, which is the last state anybody
        checks."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        state = self.paid(tenant_id)
        requester = self.scoped(tenant_id, ["finance.refund.request"])
        asked = self.client.post("/finance/refund-requests", json={
            "payment_id": state["payment_id"], "amount_minor": 1000,
            "reason": "goodwill", **self.correlation()}, headers=requester)
        approved = self.client.post("/finance/refunds", json={
            "request_id": str(asked.json()["request_id"]), "approval_reason": "agreed",
            "idempotency_key": "rf-perm", **self.correlation()}, headers=owner)
        self.assertEqual(approved.status_code, 201, approved.text)
        taker = self.stepped_grant(tenant_id, ["finance.payment.take"])
        refused = self.client.post(
            f"/finance/refunds/{approved.json()['refund_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()},
            headers=self.headers(tenant_id, taker))
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_a_credit_note_is_issuable_and_reduces_what_is_owed(self):
        """**The only correction path an insert-only ledger has, and it was unreachable.**
        `credit_matches_kind` makes `document_kind = 'credit_note'` and a credited invoice the
        same fact, and `issue_invoice` never passed the column -- so a credit-note series could
        be opened and refused every document anybody tried to number from it.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        credit_series = self.client.post("/finance/fiscal-series", json={
            "legal_entity_id": billing["legal_entity_id"], "series_code": "CRN",
            "document_kind": "credit_note", **self.correlation()}, headers=owner)
        self.assertEqual(credit_series.status_code, 201, credit_series.text)
        note = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": str(credit_series.json()["series_id"]),
            "credits_invoice_id": issued["invoice_id"],
            "lines": [{"description": "Goodwill credit", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 1600}],
            "issued_on": "2026-01-05", "due_on": "2026-01-05", "jurisdiction": "JO",
            "idempotency_key": "crn-1", **self.correlation()}, headers=owner)
        self.assertEqual(note.status_code, 201, note.text)
        self.assertEqual(note.json()["document_kind"], "credit_note")
        self.assertEqual(note.json()["document_number"], "CRN-000001")
        read = self.client.get(
            f"/finance/invoices/{issued['invoice_id']}", headers=owner)
        self.assertEqual(read.json()["credited_minor"], issued["gross_minor"])
        self.assertEqual(read.json()["payment_status"], "credited")
        # And a credit beyond what the invoice came to is refused: a credit note is a
        # correction, not a way to pay somebody.
        over = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": str(credit_series.json()["series_id"]),
            "credits_invoice_id": issued["invoice_id"],
            "lines": [{"description": "More", "quantity": 1,
                       "unit_net_minor": 100, "tax_rate_bp": 0}],
            "issued_on": "2026-01-06", "due_on": "2026-01-06", "jurisdiction": "JO",
            "idempotency_key": "crn-2", **self.correlation()}, headers=owner)
        self.assertEqual(over.status_code, 409, over.text)
        self.assertIn("uncredited", over.text)

    def test_a_credit_note_needs_a_credit_note_series(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        refused = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "credits_invoice_id": issued["invoice_id"],
            "lines": [{"description": "Credit", "quantity": 1,
                       "unit_net_minor": 100, "tax_rate_bp": 0}],
            "issued_on": "2026-01-05", "due_on": "2026-01-05", "jurisdiction": "JO",
            "idempotency_key": "crn-wrong", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("credits_an_invoice", refused.text)

    def test_an_invoice_idempotency_key_belongs_to_one_billing_account(self):
        """It is unique per tenant, so a key reused across two payers returned the *other*
        payer's invoice and reported the call as a successful repeat -- the caller believes it
        has billed account B and the money is owed by account A."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        person_id = self.person(tenant_id)
        first = self.billing(tenant_id, person_id)
        second = self.client.post("/finance/accounts", json={
            "payer_person_id": self.person(tenant_id, "Other Member"),
            "account_number": f"B{uuid.uuid4().hex[:8].upper()}", "currency": "JOD",
            "legal_entity_id": first["legal_entity_id"], **self.correlation()},
            headers=owner)
        self.assertEqual(second.status_code, 201, second.text)
        body = {"series_id": first["series_id"],
                "lines": [{"description": "Membership", "quantity": 1,
                           "unit_net_minor": 4500, "tax_rate_bp": 1600}],
                "issued_on": "2026-01-01", "due_on": "2026-01-15",
                "jurisdiction": "JO", "idempotency_key": "inv-shared"}
        self.assertEqual(self.client.post("/finance/invoices", json={
            **body, "billing_account_id": first["billing_account_id"],
            **self.correlation()}, headers=owner).status_code, 201)
        confused = self.client.post("/finance/invoices", json={
            **body, "billing_account_id": str(second.json()["billing_account_id"]),
            **self.correlation()}, headers=owner)
        self.assertEqual(confused.status_code, 409, confused.text)
        self.assertIn("another_billing_account", confused.text)

    def test_fiscalizing_records_who_moved_the_state(self):
        """The act that declares a document filed with a tax authority, or declares it outside
        the regime altogether, had no name on it and published nothing."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        moved = self.client.post(
            f"/finance/invoices/{issued['invoice_id']}/fiscalize",
            json={"target": "submitted", **self.correlation()}, headers=owner)
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertFalse(moved.json()["repeated"])
        self.assertTrue(self.client.post(
            f"/finance/invoices/{issued['invoice_id']}/fiscalize",
            json={"target": "submitted", **self.correlation()},
            headers=owner).json()["repeated"])
        trace = self.client.get(
            "/events/aggregate?aggregate_type=invoice"
            f"&aggregate_id={issued['invoice_id']}", headers=owner)
        self.assertEqual(trace.status_code, 200, trace.text)
        self.assertIn("invoice.fiscalized", trace.text)

    def test_declaring_a_document_outside_the_regime_states_why(self):
        """**`not_required` is terminal, needs no acknowledgement and sidesteps the one control
        this table is proud of**, so it is the transition that most needs a reason on the row.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        refused = self.client.post(
            f"/finance/invoices/{issued['invoice_id']}/fiscalize",
            json={"target": "not_required", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("outside_the_regime_states_why", refused.text)
        accepted = self.client.post(
            f"/finance/invoices/{issued['invoice_id']}/fiscalize",
            json={"target": "not_required",
                  "exemption_reason": "zero-rated export under the 2019 regulations",
                  **self.correlation()}, headers=owner)
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_a_lapsed_hold_is_freed_even_when_the_draw_is_then_refused(self):
        """**The sweep wrote its expiries inside the transaction that then refused the draw**,
        so `tenant_scope` rolled them back -- and that is the common case rather than an edge,
        since the usual reason a member is short is holds that have lapsed. Each attempt freed
        the quantity, refused on the balance it had read before freeing it, and rolled the
        freeing back: a member with lapsed holds was refused for ever.

        **Driven through the service rather than the route**, which is the exception in this
        file and has a reason: the sweep is a function of time, the route cannot move time, and
        `mem_entitlement_reservations.expires_at` deliberately carries no UPDATE grant for any
        runtime role -- a hold whose expiry could be moved under it is the one a member loses a
        booking to. So the clock is the argument `reserve_entitlement` already takes.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        person_id = self.person(tenant_id)
        policy_id = self.policy(tenant_id, reservation_ttl_seconds=60)
        grant_id = self.entitlement_grant(tenant_id, policy_id, person_id, quantity=2)
        for n in (1, 2):
            held = self.client.post("/member-entitlements/reservations", json={
                "grant_id": grant_id, "purpose_kind": "booking", "quantity": 1,
                "idempotency_key": f"r-lapse-{n}", **self.correlation()}, headers=owner)
            self.assertEqual(held.status_code, 201, held.text)
        later = datetime.now(UTC) + timedelta(hours=1)
        actor = self.owner_identity(tenant_id)
        # An hour on, both holds have lapsed -- and this draw is still refused, because it
        # asks for three and only two came back. The freeing has to survive the refusal.
        with self.assertRaises(Conflict):
            commercial.reserve_entitlement(
                self._tenant_pool, tenant_id, grant_id=grant_id,
                purpose_kind="booking", quantity=3, idempotency_key="r-lapse-3",
                actor_id=actor, correlation_id=str(uuid.uuid4()), at=later)
        balance = self.client.get(
            f"/member-entitlements/grants/{grant_id}?correlation_id={uuid.uuid4()}",
            headers=owner)
        self.assertEqual(balance.status_code, 200, balance.text)
        self.assertEqual(balance.json()["balance"], 2)
        self.assertEqual(balance.json()["held"], 0)

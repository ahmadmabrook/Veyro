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

import json
import unittest
import uuid
from datetime import UTC, datetime, timedelta

from app.commercial import service as commercial
from app.db import tenant_scope
from app.errors import Conflict
from tests.support import GatedApiTestCase

ACTOR = "55555555-5555-4555-8555-555555555555"

FROM = "2026-01-01T00:00:00+00:00"

#: **The lifecycle dates are relative to today, not literals.** A freeze has to start inside
#: the contract year it is decided in -- that bound is what stops a member who has spent their
#: allowance reaching back into last year's -- so a suite with hard-coded 2026 dates would
#: start failing on a date nobody chose. Every membership here starts ninety days ago, which
#: puts today comfortably inside its first contract year whenever the suite is run.
#: **UTC, not the local clock.** Every service in this build takes its "today" from
#: `datetime.now(UTC)`, and a fixture using `date.today()` disagrees with it in any timezone
#: east of UTC for as long as the two dates differ -- three hours a night here. A journal
#: posted on the local date was then outside a trial balance read as of the UTC date, and
#: sixteen tests across MOD-017 and MOD-018 failed for a reason that had nothing to do with
#: either module. CI never saw it because CI runs in UTC, where the two agree. Found while
#: running the full suite at 02:00.
TODAY = datetime.now(UTC).date()
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
                rate_bp: int = 1600, due_on: str = "2026-01-15",
                membership_id: str | None = None) -> dict:
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            **({"membership_id": membership_id} if membership_id else {}),
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
    def allowance(self, tenant_id: str, membership_id: str) -> dict:
        read = self.client.get(f"/memberships/{membership_id}/freeze-allowance",
                               headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        return dict(read.json())

    def test_the_allowance_can_be_read_before_anybody_spends_it(self):
        """**`allowance_days_used_before` came back from the write and from nothing else**,
        so the only way to learn how much of a contract's allowance a member had spent was to
        spend more of it and read the answer. The seventh "a writer with no reader" in this
        build, and ADM-MSH-03 cannot be drawn without it: the canvas puts "2 of 3 freeze
        months used this year" in the consequence panel, *before* the button."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 30})
        fresh = self.allowance(tenant_id, live["membership_id"])
        self.assertEqual(30, fresh["allowance_days"])
        self.assertEqual(0, fresh["days_used"])
        self.assertEqual(30, fresh["days_remaining"])
        self.assertTrue(fresh["allows_freezing"])

    def test_the_read_counts_what_the_write_counted(self):
        """One definition, not two that agree today. MOD-018's `_expected_in_drawer` had a
        sibling thirty lines away that differed by a date bound, and one journal dated next
        year made a short till balance."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 30})
        frozen = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(0), "days": 7,
                "reason": "travel", "idempotency_key": "f-read",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(frozen.status_code, 201, frozen.text)
        self.assertEqual(0, frozen.json()["allowance_days_used_before"])

        # **While it is open the figure is what it would cost if nobody resumed it.**
        # `freeze_days_used` counts an unresumed freeze to the end of the contract year --
        # the conservative direction, because it is spending the allowance now -- so a
        # seven-day freeze taken today reads as far more than seven. That is right and it is
        # surprising, so the read says which case it is rather than leaving a consequence
        # panel to print a number nobody can reconcile against the days they asked for.
        during = self.allowance(tenant_id, live["membership_id"])
        self.assertTrue(during["counting_an_open_freeze"])
        self.assertGreater(during["days_used"], 7)
        self.assertEqual(0, during["days_remaining"])
        self.assertEqual("frozen", during["status"])

        resumed = self.client.post(
            f"/memberships/{live['membership_id']}/resume", json={
                "reason": "back early", "idempotency_key": "r-read",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(resumed.status_code, 200, resumed.text)

        # Closed, the figure is the days actually frozen -- one, since it began and ended
        # today -- and the write's own count is what the read reports.
        after = self.allowance(tenant_id, live["membership_id"])
        self.assertFalse(after["counting_an_open_freeze"])
        self.assertEqual(1, after["days_used"])
        self.assertEqual(29, after["days_remaining"])

    def test_a_medical_hold_is_absent_from_the_allowance_the_read_reports(self):
        """The kind exists precisely so it does not spend the commercial term, and a panel
        that counted it would tell a member they had used an allowance they still have."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 30})
        held = self.client.post(
            f"/memberships/{live['membership_id']}/freeze", json={
                "freeze_kind": "medical_hold", "starts_on": day(0), "days": 60,
                "reason": "knee surgery", "evidence_ref": "s3://notes/abc",
                "idempotency_key": "f-med-read", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(held.status_code, 201, held.text)
        after = self.allowance(tenant_id, live["membership_id"])
        self.assertEqual(0, after["days_used"])
        self.assertEqual(30, after["days_remaining"])

    def test_the_read_states_the_window_a_freeze_may_start_in(self):
        """A form that offered a future date would be offering a refusal: `freeze_membership`
        takes a start within the month before today and refuses anything later, because
        nothing in this build applies a booked freeze when its day arrives."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 30})
        window = self.allowance(tenant_id, live["membership_id"])["may_start_between"]
        self.assertEqual(window["to"], day(0))
        self.assertEqual(window["from"], day(-31))

    def test_a_contract_that_allows_no_freezing_says_so(self):
        """`check_freeze` refuses one outright, so a form that rendered a date picker over it
        would be a refusal with a button on it."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={"freeze_days_per_year": 0})
        body = self.allowance(tenant_id, live["membership_id"])
        self.assertFalse(body["allows_freezing"])
        self.assertEqual(0, body["days_remaining"])

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

    def test_the_preview_carries_what_the_screen_has_to_draw(self):
        """ADM-MSH-07's three facts, before the button.

        **The route existed and nothing had ever called it**, so what it returned had never
        been compared against the screen that needs it: the commitment, the fee *in parts*,
        when access ends, whether a freeze is an alternative, and whether this membership can
        be cancelled at all. Each of those is a sentence on the sheet, and a screen deriving
        any of them for itself would be a second definition of the figure a member is held
        to.
        """
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={
            "minimum_term_months": 12, "notice_days": 30,
            "cancellation_mode": "end_of_notice", "freeze_days_per_year": 30,
            "early_termination_months": 2})
        owner = self.headers(tenant_id)
        preview = self.client.get(
            f"/memberships/{live['membership_id']}/cancellation-preview", headers=owner)
        self.assertEqual(preview.status_code, 200, preview.text)
        body = preview.json()
        self.assertTrue(body["may_cancel"])
        self.assertIsNone(body["refused_because"])
        # The commitment, which is the canvas's first sentence.
        self.assertEqual(body["commitment"]["minimum_term_months"], 12)
        self.assertTrue(body["commitment"]["leaving_early"])
        self.assertTrue(body["commitment"]["may_leave_early"])
        self.assertEqual(body["commitment"]["early_termination_months"], 2)
        self.assertIsNotNone(body["commitment"]["ends_on"])
        # The money, in parts, with the buy-out at two months of the agreement amount.
        self.assertEqual(body["fee_parts"]["early_termination_minor"], 2 * 4500)
        self.assertEqual(
            body["disclosed_fee_minor"],
            body["fee_parts"]["period_minor"]
            + body["fee_parts"]["early_termination_minor"])
        self.assertEqual(body["disclosed_fee_currency"], "JOD")
        # And the two things the sheet needs that are not money: the version the form guards
        # its write with, and whether the freeze the canvas offers instead is available.
        #
        # **Compared against the membership's own read rather than against a literal**, which
        # is what the first version did -- and `1` was a coincidence of the fixture, since
        # activation bumps the row. A literal here would pass until somebody added a step to
        # the fixture, and would then fail for a reason that has nothing to do with the
        # screen.
        live_read = self.client.get(
            f"/memberships/{live['membership_id']}", headers=owner)
        self.assertEqual(live_read.status_code, 200, live_read.text)
        self.assertEqual(body["version"], live_read.json()["version"])
        self.assertTrue(body["freeze_is_an_alternative"])
        self.assertTrue(body["explanation"])

    def test_a_contract_with_no_buy_out_prices_and_dates_it_differently(self):
        """**The same read, the other product, and the difference is the point.** A contract
        that does not sell an early exit holds the member to the term: access ends then
        rather than after notice, and no buy-out arises. Both are legitimate contracts and
        the screen draws a different sentence for each, so the read has to tell them apart."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={
            "minimum_term_months": 12, "notice_days": 30,
            "cancellation_mode": "end_of_notice"})
        owner = self.headers(tenant_id)
        body = self.client.get(
            f"/memberships/{live['membership_id']}/cancellation-preview",
            headers=owner).json()
        self.assertFalse(body["commitment"]["may_leave_early"])
        self.assertIsNone(body["commitment"]["early_termination_months"])
        self.assertEqual(body["fee_parts"]["early_termination_minor"], 0)
        # Access ends at the minimum term, not after the notice.
        self.assertEqual(body["effective_on"], body["commitment"]["ends_on"])
        self.assertFalse(body["commitment"]["leaving_early"])
        # **And the commitment is still running, which is the other fact entirely.** See
        # the test below: these two disagree here and a reader of the first alone concluded
        # the term was over.
        self.assertTrue(body["commitment"]["term_is_running"])

    def test_a_running_commitment_says_so_even_where_access_does_not_end_early(self):
        """**Two questions one boolean cannot answer, and the surface read the wrong one.**

        `leaving_early` is "access ends before the term does", which is what the buy-out is
        charged on. It is false for a member held to their term, because the lifecycle pushes
        the effective date *to* the term end precisely when the contract forbids an early
        exit -- so it goes false exactly when the commitment is most firmly binding.
        ADM-MSH-07 keyed its commitment sentence and its freeze offer on it, and told a
        member nine months inside a twelve-month term that the commitment "has been served"
        while withholding the freeze offer whose whole subject is keeping one intact.

        `term_is_running` is the question a screen actually asks, and it cannot work it out:
        `today` is on no response, and a client comparing `ends_on` against its own clock
        counts days in a frame this build has three recorded defects from. So the server says
        it -- MOD-016's `in_window` and MOD-018's `admits_trade` for the same reason.

        The assertion that matters is that the two fields **disagree** on this contract.
        Equality here would mean one of them had stopped being needed."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        held = self.membership(tenant_id, contract={
            "minimum_term_months": 12, "notice_days": 30,
            "cancellation_mode": "end_of_notice"})
        body = self.client.get(
            f"/memberships/{held['membership_id']}/cancellation-preview",
            headers=owner).json()
        self.assertTrue(body["commitment"]["term_is_running"])
        self.assertFalse(body["commitment"]["leaving_early"])
        self.assertNotEqual(
            body["commitment"]["term_is_running"], body["commitment"]["leaving_early"],
            "the two fields answer different questions and this contract is where they part")

        # On a contract that sells the exit, both are true: access does end early and the
        # commitment is still running. So the distinction is not "one is always the other
        # negated" -- it is a genuine second fact.
        bought = self.membership(tenant_id, contract={
            "minimum_term_months": 12, "notice_days": 30,
            "cancellation_mode": "end_of_notice", "early_termination_months": 2})
        other = self.client.get(
            f"/memberships/{bought['membership_id']}/cancellation-preview",
            headers=owner).json()
        self.assertTrue(other["commitment"]["term_is_running"])
        self.assertTrue(other["commitment"]["leaving_early"])

    def test_a_term_that_is_not_running_says_so_whether_served_or_absent(self):
        """**Both ways a commitment is not running**, so `term_is_running` is proved in both
        directions rather than asserted true twice.

        A one-month term on a membership that started ninety days ago has been served, and
        that is the one case where "has been served" is the true sentence. A contract with no
        minimum term at all never had one -- **and that case was uncaught until a mutation
        said so.** `commitmentLine` guards on `ends_on` before it reads this field, so the
        sentence was safe either way; `freezeOffer` reads it directly, so a rolling member
        would have been told a freeze "leaves the commitment standing" about a commitment
        that does not exist, which is the defect that function's own docstring exists to
        prevent."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        served = self.membership(tenant_id, contract={
            "minimum_term_months": 1, "notice_days": 30,
            "cancellation_mode": "end_of_notice"})
        body = self.client.get(
            f"/memberships/{served['membership_id']}/cancellation-preview",
            headers=owner).json()
        self.assertIsNotNone(body["commitment"]["ends_on"])
        self.assertFalse(body["commitment"]["term_is_running"])
        self.assertFalse(body["commitment"]["leaving_early"])

        rolling = self.membership(tenant_id, contract={"notice_days": 30,
                                                       "cancellation_mode": "end_of_notice"})
        other = self.client.get(
            f"/memberships/{rolling['membership_id']}/cancellation-preview",
            headers=owner).json()
        self.assertEqual(other["commitment"]["minimum_term_months"], 0)
        self.assertIsNone(other["commitment"]["ends_on"])
        self.assertFalse(other["commitment"]["term_is_running"])
        self.assertFalse(other["commitment"]["leaving_early"])

    def test_the_buy_out_reaches_the_recorded_cancellation(self):
        """**The disclosure is only worth anything if the command charges what was quoted.**
        The preview's figure includes the buy-out, so the command must accept that figure and
        refuse the one the old arithmetic would have produced -- which is the period part
        alone. A preview and a command with two expressions agree until one of them changes,
        and this is the change that would have pulled them apart."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={
            "minimum_term_months": 12, "notice_days": 30,
            "cancellation_mode": "end_of_notice", "early_termination_months": 2})
        owner = self.headers(tenant_id)
        quoted = self.client.get(
            f"/memberships/{live['membership_id']}/cancellation-preview",
            headers=owner).json()
        period_only = quoted["fee_parts"]["period_minor"]
        self.assertNotEqual(period_only, quoted["disclosed_fee_minor"])
        stale = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "acknowledged_fee_minor": period_only,
                "idempotency_key": "c-old-arithmetic", **self.correlation()},
            headers=owner)
        self.assertEqual(stale.status_code, 409, stale.text)
        done = self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away",
                "acknowledged_fee_minor": quoted["disclosed_fee_minor"],
                "expected_version": quoted["version"],
                "idempotency_key": "c-quoted", **self.correlation()}, headers=owner)
        self.assertEqual(done.status_code, 200, done.text)
        recorded = done.json()
        self.assertEqual(recorded["fee_due_minor"], quoted["disclosed_fee_minor"])
        self.assertEqual(recorded["effective_on"], quoted["effective_on"])
        self.assertEqual(
            recorded["fee_parts"]["early_termination_minor"], 2 * 4500)
        # **The reasoning the command used to compute and throw away.** COM-01-R06 wants the
        # member to understand the consequence, and `cancellation_effective_on` returns its
        # steps for that reason; the only caller unpacked them into `_`.
        self.assertTrue(recorded["reasoning"])
        self.assertTrue(any("bought out" in step for step in recorded["reasoning"]))

    def test_a_membership_that_cannot_be_cancelled_says_so_rather_than_pricing_one(self):
        """**A figure offered for an act that cannot happen is worse than no figure.** The
        screen asks `may_cancel` the way the command asks it, so a sheet opened on an
        already-cancelled membership says what is true instead of quoting a fee and then
        being refused."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={
            "notice_days": 0, "cancellation_mode": "immediate"})
        owner = self.headers(tenant_id)
        self.assertEqual(self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "idempotency_key": "c-once",
                **self.correlation()}, headers=owner).status_code, 200)
        again = self.client.get(
            f"/memberships/{live['membership_id']}/cancellation-preview", headers=owner)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertFalse(again.json()["may_cancel"])
        self.assertIsNotNone(again.json()["refused_because"])

    def test_a_buy_out_on_a_contract_with_no_term_is_refused_at_the_boundary(self):
        """A buy-out of a term that does not exist is inert -- the agreement carries no
        `minimum_term_ends_on`, so nothing could ever charge it -- and a column implying a
        control nobody implemented is this build's most repeated finding. Refused by the
        schema, and the route answers 422 rather than 500."""
        tenant_id = self.tenant()
        refused = self.client.post("/memberships/contract-versions", json={
            "contract_key": f"c{uuid.uuid4().hex[:8]}", "body": "Rolling terms.",
            "minimum_term_months": 0, "early_termination_months": 2,
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("early_termination", refused.text)

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


class ListingReadTests(CommercialApiTestCase):
    """MOD-017's listing reads -- the routes that make the module observable.

    Until these existed every read took an id the caller already had, so nothing could answer
    "what memberships does this person have" or "what has this account been invoiced". These
    tests are written as the two things most likely to be wrong about a listing route: that it
    returns somebody else's rows, and that it returns a field it has no business returning.
    """

    def test_a_membership_appears_in_the_list_with_its_agreement_and_its_terms(self):
        tenant_id = self.tenant()
        made = self.membership(tenant_id)
        listed = self.client.get(
            "/memberships", headers=self.scoped(tenant_id, ["membership.record.read"]))
        self.assertEqual(listed.status_code, 200, listed.text)
        rows = listed.json()["memberships"]
        row = next(r for r in rows if r["membership_id"] == made["membership_id"])
        # The figures come from the agreement, which is what was actually sold.
        self.assertEqual(row["amount_minor"], 4500)
        self.assertEqual(row["currency"], "JOD")
        self.assertEqual(row["membership_kind"], "recurring")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["person_id"], made["person_id"])

    def test_the_person_filter_excludes_another_members_membership(self):
        """The filter is the whole point of the route on a member's page."""
        tenant_id = self.tenant()
        mine = self.membership(tenant_id)
        theirs = self.membership(tenant_id)
        head = self.scoped(tenant_id, ["membership.record.read"])
        listed = self.client.get(
            f"/memberships?person_id={mine['person_id']}", headers=head)
        self.assertEqual(listed.status_code, 200, listed.text)
        ids = [r["membership_id"] for r in listed.json()["memberships"]]
        self.assertIn(mine["membership_id"], ids)
        self.assertNotIn(theirs["membership_id"], ids)

    def test_no_listing_read_returns_anything_about_the_person(self):
        """A lateral read path around `people.person.read` is the shape to refuse.

        MOD-010 shipped one: a routine `events.event.read` returned another module's
        restricted fields out of the outbox, and a reviewer read consent and DSAR history with
        it after being refused by the owning routes. A membership list carrying the member's
        legal name would be the same defect, with `membership.record.read` -- which a front
        desk and a turnstile hold -- as the key.
        """
        tenant_id = self.tenant()
        name = f"Helena Kowalczyk {uuid.uuid4().hex[:6]}"
        owner = self.headers(tenant_id)
        person_id = self.person(tenant_id, name=name)
        # The person is real and the name is readable through MOD-014's own gate ...
        through_people = self.client.get(f"/people/{person_id}", headers=owner)
        self.assertEqual(through_people.status_code, 200, through_people.text)
        self.assertIn(name.split()[0], through_people.text)
        # ... and appears in none of MOD-017's reads, for anybody, at any assurance.
        billing = self.billing(tenant_id, person_id)
        self.invoice(tenant_id, billing)
        policy_id = self.policy(tenant_id)
        self.entitlement_grant(tenant_id, policy_id, person_id)
        head = self.scoped(tenant_id, [
            "membership.record.read", "finance.account.read",
            "membership.entitlement.read"])
        for path in (f"/memberships?person_id={person_id}",
                     f"/member-entitlements?person_id={person_id}",
                     f"/finance/accounts?person_id={person_id}",
                     f"/finance/invoices?person_id={person_id}"):
            answer = self.client.get(path, headers=head)
            self.assertEqual(answer.status_code, 200, answer.text)
            self.assertNotIn(name, answer.text, path)
            self.assertNotIn(name.split()[0], answer.text, path)

    def test_a_status_outside_the_domain_refuses_rather_than_returning_nothing(self):
        """`status=actve` and "no active membership" are different answers.

        A list that rendered both as an empty table would be a surface nobody can trust, and
        the typo is the realistic input -- a hand-built query string, or a client sending a
        label instead of a value.
        """
        tenant_id = self.tenant()
        head = self.scoped(tenant_id, ["membership.record.read"])
        refused = self.client.get("/memberships?status=actve", headers=head)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(refused.json()["error"], "bad_status")
        allowed = self.client.get("/memberships?status=active", headers=head)
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_an_unknown_payment_status_refuses_too(self):
        tenant_id = self.tenant()
        head = self.scoped(tenant_id, ["finance.account.read"])
        refused = self.client.get("/finance/invoices?payment_status=settled", headers=head)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(refused.json()["error"], "bad_payment_status")

    def test_a_limit_outside_the_ceiling_refuses(self):
        """Unbounded is a bulk export and a denial of service at once."""
        tenant_id = self.tenant()
        head = self.scoped(tenant_id, ["membership.record.read", "finance.account.read"])
        for path in ("/memberships?limit=0", "/memberships?limit=10000",
                     "/finance/invoices?limit=201"):
            refused = self.client.get(path, headers=head)
            self.assertEqual(refused.status_code, 422, f"{path}: {refused.text}")
            self.assertEqual(refused.json()["error"], "bad_limit", path)

    def test_a_full_page_says_it_was_truncated(self):
        """A page that fills exactly is indistinguishable from the whole answer otherwise."""
        tenant_id = self.tenant()
        self.membership(tenant_id)
        self.membership(tenant_id)
        head = self.scoped(tenant_id, ["membership.record.read"])
        one = self.client.get("/memberships?limit=1", headers=head)
        self.assertEqual(one.status_code, 200, one.text)
        self.assertEqual(one.json()["count"], 1)
        self.assertTrue(one.json()["truncated"])
        many = self.client.get("/memberships?limit=50", headers=head)
        self.assertFalse(many.json()["truncated"])

    def test_a_medical_holds_reason_is_masked_in_the_detail_read_too(self):
        """A health fact is a health fact whatever read returns it.

        `membership_as_of` masks it and this read is new, so the question is whether the mask
        travelled with the data or stayed with the function that happened to have it. The
        entry stays visible, because a hold a reader cannot see at all is a gap in a dispute
        record -- MOD-014's rule, applied here.
        """
        tenant_id = self.tenant()
        made = self.membership(tenant_id)
        owner = self.headers(tenant_id)
        frozen = self.client.post(
            f"/memberships/{made['membership_id']}/freeze", json={
                "freeze_kind": "medical_hold", "starts_on": day(-1), "days": 14,
                "reason": "chemotherapy on Tuesdays",
                # A locator, never the note: the constraint requires one for a medical hold
                # precisely so the diagnosis lives somewhere this module cannot read.
                "evidence_ref": "s3://evidence/note-1",
                "idempotency_key": f"mh-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner)
        self.assertEqual(frozen.status_code, 201, frozen.text)
        detail = self.client.get(
            f"/memberships/{made['membership_id']}",
            headers=self.scoped(tenant_id, ["membership.record.read"]))
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertNotIn("chemotherapy", detail.text)
        hold = next(h for h in detail.json()["history"]
                    if h["change_kind"] == "medical_hold")
        self.assertTrue(hold["reason_withheld"])
        self.assertIn("redacted", hold["reason"])
        self.assertEqual(hold["to_status"], "frozen")

    def test_an_invoice_list_reports_the_stored_payment_status(self):
        """Not one recomputed here: a second definition of a balance disagrees with the first.

        MOD-018 shipped exactly that pair -- `_expected_in_drawer` and `account_balance` --
        and they disagreed on any back-dated journal.
        """
        tenant_id = self.tenant()
        settled = self.paid(tenant_id)
        head = self.scoped(tenant_id, ["finance.account.read"])
        listed = self.client.get(
            f"/finance/invoices?billing_account_id={settled['billing']['billing_account_id']}",
            headers=head)
        self.assertEqual(listed.status_code, 200, listed.text)
        row = next(r for r in listed.json()["invoices"]
                   if r["invoice_id"] == settled["invoice"]["invoice_id"])
        self.assertEqual(row["payment_status"], "paid")
        self.assertEqual(row["paid_minor"], settled["invoice"]["gross_minor"])
        self.assertEqual(row["document_kind"], "invoice")
        one = self.client.get(
            f"/finance/invoices/{settled['invoice']['invoice_id']}", headers=head)
        self.assertEqual(one.json()["payment_status"], row["payment_status"])

    def test_a_grant_list_reports_the_balance_and_says_it_is_unswept(self):
        tenant_id = self.tenant()
        person_id = self.person(tenant_id)
        policy_id = self.policy(tenant_id)
        grant_id = self.entitlement_grant(tenant_id, policy_id, person_id)
        listed = self.client.get(
            f"/member-entitlements?person_id={person_id}",
            headers=self.scoped(tenant_id, ["membership.entitlement.read"]))
        self.assertEqual(listed.status_code, 200, listed.text)
        row = next(r for r in listed.json()["grants"] if r["grant_id"] == grant_id)
        self.assertEqual(row["balance"], 10)
        self.assertEqual(row["held"], 0)
        self.assertTrue(row["is_counted"])
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["entitlement_type"], "class_credit")
        # Stated rather than implied: the swept figure is `entitlement_balance`, which writes.
        self.assertTrue(listed.json()["balance_is_unswept"])

    def test_a_billing_account_list_filters_on_who_pays(self):
        tenant_id = self.tenant()
        payer = self.person(tenant_id)
        other = self.person(tenant_id)
        mine = self.billing(tenant_id, payer)
        theirs = self.billing(tenant_id, other)
        listed = self.client.get(
            f"/finance/accounts?person_id={payer}",
            headers=self.scoped(tenant_id, ["finance.account.read"]))
        self.assertEqual(listed.status_code, 200, listed.text)
        ids = [a["billing_account_id"] for a in listed.json()["accounts"]]
        self.assertIn(mine["billing_account_id"], ids)
        self.assertNotIn(theirs["billing_account_id"], ids)

    def test_the_membership_read_does_not_also_buy_the_finance_read(self):
        """Two permissions, because MOD-013 shipped one that bought its sibling's data.

        `GET /notifications/channels` was gated on `notifications.template.read`, so "see the
        templates" also read what every message costs the tenant. Here the equivalent mistake
        would let a front desk holding only the membership read see every invoice.
        """
        tenant_id = self.tenant()
        made = self.membership(tenant_id)
        head = self.scoped(tenant_id, ["membership.record.read"])
        self.assertEqual(self.client.get("/memberships", headers=head).status_code, 200)
        self.assertEqual(
            self.client.get(f"/memberships/{made['membership_id']}",
                            headers=head).status_code, 200)
        for path in ("/finance/invoices", "/finance/accounts", "/member-entitlements"):
            refused = self.client.get(path, headers=head)
            self.assertEqual(refused.status_code, 403, f"{path}: {refused.text}")

    def test_an_unknown_membership_is_a_404_and_a_malformed_id_is_a_422(self):
        tenant_id = self.tenant()
        head = self.scoped(tenant_id, ["membership.record.read"])
        missing = self.client.get(f"/memberships/{uuid.uuid4()}", headers=head)
        self.assertEqual(missing.status_code, 404, missing.text)
        malformed = self.client.get("/memberships/not-a-uuid", headers=head)
        self.assertEqual(malformed.status_code, 422, malformed.text)

class InvoiceHistoryTests(CommercialApiTestCase):
    """ADM-PAY-03's "what has happened to this invoice", composed from insert-only tables.

    The screen's own immutability note is why this can be an audit trail: "Issued invoices
    are never edited. Corrections are credit notes with their own number and a link to the
    original." So the timeline is built from the rows that were written, never from the
    invoice's cached status -- which says what is true now and nothing about how it got there.
    """

    def test_an_issued_invoice_has_one_entry_and_names_itself(self):
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        invoice = self.invoice(tenant_id, billing)
        head = self.scoped(tenant_id, ["finance.account.read"])
        history = self.client.get(
            f"/finance/invoices/{invoice['invoice_id']}/history", headers=head)
        self.assertEqual(history.status_code, 200, history.text)
        body = history.json()
        self.assertEqual([e["kind"] for e in body["events"]], ["issued"], body)
        self.assertEqual(body["document_number"], invoice["document_number"], body)
        self.assertIn("credit note", body["immutable_because"])

    def test_a_payment_joins_the_timeline_in_order(self):
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        invoice = self.invoice(tenant_id, billing)
        head = self.headers(tenant_id)
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": invoice["invoice_id"], "amount_minor": invoice["gross_minor"],
            "method": "card", "provider_key": "acme.payments",
            "idempotency_key": f"pi-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=head)
        self.assertEqual(intent.status_code, 201, intent.text)
        settled = self.client.post(
            f"/finance/payment-intents/{intent.json()['intent_id']}/settle", json={
                "outcome": "succeeded", **self.correlation()}, headers=head)
        self.assertEqual(settled.status_code, 200, settled.text)

        body = self.client.get(
            f"/finance/invoices/{invoice['invoice_id']}/history",
            headers=self.scoped(tenant_id, ["finance.account.read"])).json()
        kinds = [e["kind"] for e in body["events"]]
        self.assertIn("payment_intent", kinds, body)
        self.assertIn("payment", kinds, body)
        # Ordered by when each happened, which is the only ordering a timeline can have.
        instants = [e["at"] for e in body["events"]]
        self.assertEqual(instants, sorted(instants), body)

    def test_an_unknown_outcome_is_not_reported_as_a_failure(self):
        """`unknown` means the provider did not answer, which is not a decline.

        MOD-017 treats it as money that may well have left -- it counts against what a
        payment can still be refunded -- so a timeline that rendered it as "declined" would
        be stating the opposite of the module's own reading.
        """
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        invoice = self.invoice(tenant_id, billing)
        head = self.headers(tenant_id)
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": invoice["invoice_id"], "amount_minor": invoice["gross_minor"],
            "method": "card", "provider_key": "acme.payments",
            "idempotency_key": f"pi-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=head)
        self.client.post(
            f"/finance/payment-intents/{intent.json()['intent_id']}/settle", json={
                "outcome": "unknown", **self.correlation()}, headers=head)

        body = self.client.get(
            f"/finance/invoices/{invoice['invoice_id']}/history",
            headers=self.scoped(tenant_id, ["finance.account.read"])).json()
        intents = [e for e in body["events"] if e["kind"] == "payment_intent"]
        self.assertEqual([e["status"] for e in intents], ["unknown"], body)
        self.assertEqual([e["kind"] for e in body["events"]].count("payment"), 0, body)

    def test_an_unknown_invoice_is_a_404_and_a_malformed_one_a_422(self):
        tenant_id = self.tenant()
        head = self.scoped(tenant_id, ["finance.account.read"])
        missing = self.client.get(
            f"/finance/invoices/{uuid.uuid4()}/history", headers=head)
        self.assertEqual(missing.status_code, 404, missing.text)
        malformed = self.client.get("/finance/invoices/not-a-uuid/history", headers=head)
        self.assertEqual(malformed.status_code, 422, malformed.text)



class DisputeTests(CommercialApiTestCase):
    """The chargeback, and the table MOD-017 shipped with no writer.

    `plt01.fin_disputes` has existed since this module's migration -- forced RLS, twelve
    constraints, an isolation check and four privacy declarations -- and until ADM-PAY-03
    needed it, nothing in `app/` read or wrote it while the module's registry entry listed
    disputes among what works. A state no screen can reach is the vacuous branch this
    codebase has shipped eight times.
    """

    def paid(self, tenant_id: str) -> dict:
        """An invoice with a settled card payment against it, which is what a scheme reverses."""
        billing = self.billing(tenant_id, self.person(tenant_id))
        invoice = self.invoice(tenant_id, billing)
        head = self.headers(tenant_id)
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": invoice["invoice_id"], "amount_minor": invoice["gross_minor"],
            "method": "card", "provider_key": "acme.payments",
            "idempotency_key": f"pi-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=head)
        self.assertEqual(intent.status_code, 201, intent.text)
        settled = self.client.post(
            f"/finance/payment-intents/{intent.json()['intent_id']}/settle", json={
                "outcome": "succeeded", **self.correlation()}, headers=head)
        self.assertEqual(settled.status_code, 200, settled.text)
        return {"billing": billing, "invoice": invoice,
                "payment_id": str(settled.json()["payment_id"]),
                "amount_minor": int(invoice["gross_minor"])}

    def manager(self, tenant_id: str) -> dict[str, str]:
        """**A stepped-up session, because `finance.dispute.manage` is financial class.**

        A lost chargeback is money gone and the response window is the one chance to keep
        it, so holding the permission on a password-only session is not enough -- which is
        the catalogue's rule for every money write in this module.
        """
        return self.headers(
            tenant_id, self.stepped_grant(tenant_id, ["finance.dispute.manage"]))

    def dispute(self, tenant_id: str, paid: dict, **over: object) -> dict:
        body: dict = {
            "payment_id": paid["payment_id"],
            "provider_case_ref": f"CB-{uuid.uuid4().hex[:8].upper()}",
            "dispute_kind": "chargeback", "reason_code": "card_expired",
            "amount_minor": paid["amount_minor"], "currency": "JOD",
            "opened_on": "2026-02-01", "respond_due_on": "2026-02-15",
            "idempotency_key": f"cb-{uuid.uuid4().hex[:8]}", **self.correlation()}
        body.update(over)
        return self.client.post(
            "/finance/disputes", json=body, headers=self.manager(tenant_id))

    # ------------------------------------------------- ADM-PAY-10, the dispute listing

    def disputes(self, tenant_id, **query):
        """**Read with a routine session on purpose**, which is the permission's whole
        point: a read behind a step-up is a read nobody does until the deadline has
        passed."""
        q = "&".join(f"{k}={v}" for k, v in query.items())
        read = self.client.get(
            f"/finance/disputes{'?' + q if q else ''}",
            headers=self.scoped(tenant_id, ["finance.dispute.read"]))
        self.assertEqual(read.status_code, 200, read.text)
        return read.json()

    def test_a_dispute_can_be_listed_at_all(self):
        """The module's last writer with no reader.

        Three routes could record, answer and settle a chargeback and nothing could list
        one, so a dispute existed only for whoever had just written it -- the same shape
        closed for MOD-004's brands, MOD-017's memberships and MOD-018's chart.
        """
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        opened = self.dispute(tenant_id, paid)
        self.assertEqual(opened.status_code, 201, opened.text)
        body = self.disputes(tenant_id)
        row = next(d for d in body["disputes"]
                   if d["dispute_id"] == opened.json()["dispute_id"])
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["dispute_kind"], "chargeback")
        self.assertEqual(row["amount_minor"], paid["amount_minor"])
        # The document the dispute is against, which is what a reader recognises it by.
        self.assertEqual(
            row["document_number"], paid["invoice"]["document_number"])

    def test_the_deadline_is_computed_rather_than_left_to_the_reader(self):
        """The canvas leads with "Evidence due 26 August · 7 days".

        `collections.evidence_window` already decides it -- including letting
        `days_remaining` go negative rather than clamping, because a dispute whose window
        closed is the one somebody most needs to see. A surface subtracting two dates would
        be a second definition of the one figure the screen is about.
        """
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        self.dispute(tenant_id, paid,
                     opened_on=day(-10), respond_due_on=day(7))
        row = self.disputes(tenant_id)["disputes"][0]
        self.assertEqual(row["days_remaining"], 7)
        self.assertFalse(row["window_has_closed"])
        self.assertEqual(row["days_given"], 17)

    def test_a_closed_window_reports_a_negative_remainder(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        self.dispute(tenant_id, paid,
                     opened_on=day(-40), respond_due_on=day(-5))
        row = self.disputes(tenant_id)["disputes"][0]
        self.assertEqual(row["days_remaining"], -5)
        self.assertTrue(row["window_has_closed"])

    def test_at_stake_counts_only_the_undecided(self):
        """A dispute already won or lost is settled money, not exposure.

        Summing every dispute ever recorded would make the figure grow for ever and would
        say a tenant is at risk of money the scheme has already returned.
        """
        tenant_id = self.tenant()
        live = self.paid(tenant_id)
        self.dispute(tenant_id, live, amount_minor=2000)
        decided = self.paid(tenant_id)
        settled = self.dispute(tenant_id, decided, amount_minor=5000)
        won = self.client.post(
            f"/finance/disputes/{settled.json()['dispute_id']}/settle",
            json={"outcome": "won", **self.correlation()},
            headers=self.manager(tenant_id))
        self.assertEqual(won.status_code, 200, won.text)
        body = self.disputes(tenant_id)
        at_stake = next(a for a in body["at_stake"] if a["currency"] == "JOD")
        self.assertEqual(at_stake["amount_minor"], 2000)

    def test_the_listing_returns_no_name_and_no_card(self):
        """`payments_ledger`'s rule, applied to the same module's other read."""
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        self.dispute(tenant_id, paid)
        raw = self.client.get(
            "/finance/disputes",
            headers=self.scoped(tenant_id, ["finance.dispute.read"])).text
        self.assertNotIn("Jane Smith", raw)
        row = self.disputes(tenant_id)["disputes"][0]
        self.assertEqual(row["method"], "card")
        self.assertNotIn("payment_method_ref", row)

    def test_a_status_outside_the_vocabulary_refuses(self):
        """"status=setled" and "no dispute is in that state" are different answers, and a
        list rendering both as empty is a list nobody can trust."""
        tenant_id = self.tenant()
        answer = self.client.get(
            "/finance/disputes?status=setled",
            headers=self.scoped(tenant_id, ["finance.dispute.read"]))
        self.assertEqual(answer.status_code, 422, answer.text)

    def test_seeing_a_dispute_does_not_buy_answering_it(self):
        """The read is routine so the deadline gets noticed; the acts stay financial.

        Answering a scheme and accepting a loss are both money decisions, and the second
        is the one nobody can undo -- so a session that may look at the board may not
        settle anything on it.
        """
        tenant_id = self.tenant()
        reader = self.scoped(tenant_id, ["finance.dispute.read"])
        refused = self.client.post("/finance/disputes", json={
            "payment_id": str(uuid.uuid4()), "provider_case_ref": "X",
            "dispute_kind": "chargeback", "reason_code": "fraudulent",
            "amount_minor": 100, "currency": "JOD", "opened_on": "2026-02-01",
            "respond_due_on": "2026-02-15", "idempotency_key": "x",
            **self.correlation()}, headers=reader)
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_the_board_is_readable_without_a_step_up(self):
        """MOD-018's rule: a read behind a step-up is a read nobody does until the panic.

        A chargeback is worse than a wrong trial balance, because the window expires -- so
        a password-only session that holds the read permission sees the board.
        """
        tenant_id = self.tenant()
        read = self.client.get(
            "/finance/disputes",
            headers=self.scoped(tenant_id, ["finance.dispute.read"]))
        self.assertEqual(read.status_code, 200, read.text)

    def test_a_dispute_listing_limit_outside_the_bound_refuses(self):
        tenant_id = self.tenant()
        for query in ("limit=0", "limit=9999"):
            answer = self.client.get(
                f"/finance/disputes?{query}",
                headers=self.scoped(tenant_id, ["finance.dispute.read"]))
            self.assertEqual(answer.status_code, 422, f"{query}: {answer.text}")

    def test_a_dispute_is_recorded_against_a_payment_with_its_window(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        opened = self.dispute(tenant_id, paid)
        self.assertEqual(opened.status_code, 201, opened.text)
        body = opened.json()
        self.assertEqual(body["status"], "open")
        self.assertEqual(body["invoice_id"], paid["invoice"]["invoice_id"])
        # The scheme gave a fortnight, and the window is returned rather than left to be
        # derived from two dates.
        self.assertEqual(body["days_given"], 14)
        self.assertIn("window_has_closed", body)

    def test_the_billing_account_is_derived_from_the_payment(self):
        """Derive, never accept: a dispute must not be recordable against another payer."""
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        body = self.dispute(tenant_id, paid).json()
        self.assertEqual(
            body["billing_account_id"], paid["billing"]["billing_account_id"])

    def test_a_dispute_cannot_exceed_the_payment_it_is_against(self):
        """A scheme reverses at most what was charged; more would overstate the exposure."""
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        over = self.dispute(tenant_id, paid, amount_minor=paid["amount_minor"] + 1)
        self.assertEqual(over.status_code, 409, over.text)
        self.assertIn("exceed", over.json()["error"])

    def test_a_dispute_is_in_the_currency_of_the_payment(self):
        """MOD-016 authorised a JOD reduction in USD by comparing minor units across them."""
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        wrong = self.dispute(tenant_id, paid, currency="USD")
        self.assertEqual(wrong.status_code, 409, wrong.text)

    def test_a_deadline_before_the_opening_is_refused_at_the_boundary(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        backwards = self.dispute(
            tenant_id, paid, opened_on="2026-02-15", respond_due_on="2026-02-01")
        self.assertEqual(backwards.status_code, 422, backwards.text)

    def test_a_repeat_is_answered_from_what_was_recorded(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        key = f"cb-{uuid.uuid4().hex[:8]}"
        ref = f"CB-{uuid.uuid4().hex[:8].upper()}"
        first = self.dispute(tenant_id, paid, idempotency_key=key, provider_case_ref=ref)
        self.assertEqual(first.status_code, 201, first.text)
        again = self.dispute(tenant_id, paid, idempotency_key=key, provider_case_ref=ref)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertIs(again.json()["repeated"], True)
        self.assertEqual(again.json()["dispute_id"], first.json()["dispute_id"])

    def test_a_key_reused_for_another_case_refuses_rather_than_handing_the_first_back(self):
        """An idempotency key compared on the aggregate alone is this build's commonest defect.

        The aggregate here is the payment, and a scheme can open two cases against one
        payment -- an inquiry and then a chargeback -- so a retry naming a different case
        reference would otherwise be told the second case had been recorded when it had not.
        """
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        key = f"cb-{uuid.uuid4().hex[:8]}"
        self.assertEqual(
            self.dispute(tenant_id, paid, idempotency_key=key).status_code, 201)
        other = self.dispute(tenant_id, paid, idempotency_key=key)
        self.assertEqual(other.status_code, 409, other.text)
        self.assertIn("another_dispute", other.json()["error"])

    def test_evidence_is_recorded_and_the_dispute_can_then_be_decided(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        head = self.manager(tenant_id)
        dispute_id = self.dispute(tenant_id, paid).json()["dispute_id"]
        answered = self.client.post(
            f"/finance/disputes/{dispute_id}/respond", json={
                "response_ref": "https://provider.invalid/cases/9", **self.correlation()},
            headers=head)
        self.assertEqual(answered.status_code, 200, answered.text)
        self.assertEqual(answered.json()["status"], "responded")
        won = self.client.post(
            f"/finance/disputes/{dispute_id}/settle", json={
                "outcome": "won", **self.correlation()}, headers=head)
        self.assertEqual(won.status_code, 200, won.text)
        self.assertEqual(won.json()["outcome"], "won")

    def test_a_decided_dispute_cannot_be_answered(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        head = self.manager(tenant_id)
        dispute_id = self.dispute(tenant_id, paid).json()["dispute_id"]
        self.client.post(f"/finance/disputes/{dispute_id}/settle", json={
            "outcome": "lost", **self.correlation()}, headers=head)
        late = self.client.post(f"/finance/disputes/{dispute_id}/respond", json={
            "response_ref": "https://provider.invalid/cases/9", **self.correlation()},
            headers=head)
        self.assertEqual(late.status_code, 409, late.text)

    def test_settling_twice_with_the_same_outcome_is_idempotent(self):
        """A client whose request timed out after the commit is told what happened."""
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        head = self.manager(tenant_id)
        dispute_id = self.dispute(tenant_id, paid).json()["dispute_id"]
        for expected in (False, True):
            answer = self.client.post(f"/finance/disputes/{dispute_id}/settle", json={
                "outcome": "withdrawn", **self.correlation()}, headers=head)
            self.assertEqual(answer.status_code, 200, answer.text)
            self.assertIs(answer.json()["repeated"], expected)

    def test_a_different_outcome_afterwards_refuses(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        head = self.manager(tenant_id)
        dispute_id = self.dispute(tenant_id, paid).json()["dispute_id"]
        self.client.post(f"/finance/disputes/{dispute_id}/settle", json={
            "outcome": "won", **self.correlation()}, headers=head)
        flipped = self.client.post(f"/finance/disputes/{dispute_id}/settle", json={
            "outcome": "lost", **self.correlation()}, headers=head)
        self.assertEqual(flipped.status_code, 409, flipped.text)

    def test_a_dispute_reaches_the_invoices_timeline_with_the_schemes_deadline(self):
        """ADM-PAY-03's disputed state, and the read the banner comes from.

        A timeline built from `payment_status` could never show this: the invoice stays
        `paid` throughout a chargeback, because the money arrived and is being taken back.
        """
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        self.assertEqual(self.dispute(tenant_id, paid).status_code, 201)
        history = self.client.get(
            f"/finance/invoices/{paid['invoice']['invoice_id']}/history",
            headers=self.scoped(tenant_id, ["finance.account.read"]))
        self.assertEqual(history.status_code, 200, history.text)
        body = history.json()
        disputes = [e for e in body["events"] if e["kind"] == "dispute"]
        self.assertEqual(len(disputes), 1, body)
        self.assertEqual(disputes[0]["status"], "open")
        self.assertEqual(disputes[0]["respond_due_on"], "2026-02-15")
        self.assertEqual(body["evidence_due_on"], "2026-02-15", body)
        # And the invoice still reads paid, which is the point of the separate record.
        invoice = self.client.get(
            f"/finance/invoices/{paid['invoice']['invoice_id']}",
            headers=self.scoped(tenant_id, ["finance.account.read"])).json()
        self.assertEqual(invoice["payment_status"], "paid", invoice)

    def test_a_closed_dispute_leaves_no_deadline_outstanding(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        dispute_id = self.dispute(tenant_id, paid).json()["dispute_id"]
        self.client.post(f"/finance/disputes/{dispute_id}/settle", json={
            "outcome": "won", **self.correlation()},
            headers=self.manager(tenant_id))
        body = self.client.get(
            f"/finance/invoices/{paid['invoice']['invoice_id']}/history",
            headers=self.scoped(tenant_id, ["finance.account.read"])).json()
        self.assertIsNone(body["evidence_due_on"], body)
        self.assertEqual(
            [e["status"] for e in body["events"] if e["kind"] == "dispute"], ["won"])

    def test_recording_a_dispute_needs_its_own_permission(self):
        """`finance.account.read` is what a front desk holds and a chargeback is not a read."""
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        refused = self.client.post("/finance/disputes", json={
            "payment_id": paid["payment_id"], "provider_case_ref": "CB-NO",
            "dispute_kind": "chargeback", "reason_code": "card_expired",
            "amount_minor": 100, "currency": "JOD", "opened_on": "2026-02-01",
            "respond_due_on": "2026-02-15", "idempotency_key": "cb-no",
            **self.correlation()},
            headers=self.scoped(tenant_id, ["finance.account.read"]))
        self.assertEqual(refused.status_code, 403, refused.text)
        self.assertEqual(refused.json()["error"], "forbidden", refused.text)

    def test_the_permission_alone_is_not_enough_without_a_step_up(self):
        """Financial class. Holding it on a password-only session is the catalogue's point."""
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        weak = self.client.post("/finance/disputes", json={
            "payment_id": paid["payment_id"], "provider_case_ref": "CB-WEAK",
            "dispute_kind": "chargeback", "reason_code": "card_expired",
            "amount_minor": 100, "currency": "JOD", "opened_on": "2026-02-01",
            "respond_due_on": "2026-02-15", "idempotency_key": "cb-weak",
            **self.correlation()},
            headers=self.scoped(tenant_id, ["finance.dispute.manage"]))
        self.assertEqual(weak.status_code, 403, weak.text)
        self.assertEqual(weak.json()["error"], "step_up_required", weak.text)

    def test_an_unknown_payment_is_a_404_and_a_malformed_one_a_422(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        missing = self.dispute(tenant_id, {**paid, "payment_id": str(uuid.uuid4())})
        self.assertEqual(missing.status_code, 404, missing.text)
        malformed = self.dispute(tenant_id, {**paid, "payment_id": "not-a-uuid"})
        self.assertEqual(malformed.status_code, 422, malformed.text)


class InvoiceDetailReadTests(CommercialApiTestCase):
    """What ADM-PAY-03's header and its linked documents need, which this read did not answer.

    The asymmetry worth naming: `list_invoices` has returned `payer_person_id` and
    `credits_invoice_id` from the start, so the detail read answered *less* about an
    invoice's identity than the row that linked to it.
    """

    def test_the_payer_is_an_identifier_and_never_a_name(self):
        """So a surface can ask MOD-014 for the name through MOD-014's own gate."""
        tenant_id = self.tenant()
        person_id = self.person(tenant_id, "Ahmad Nabulsi")
        billing = self.billing(tenant_id, person_id)
        invoice = self.invoice(tenant_id, billing)
        body = self.client.get(
            f"/finance/invoices/{invoice['invoice_id']}",
            headers=self.scoped(tenant_id, ["finance.account.read"])).json()
        self.assertEqual(body["payer_person_id"], person_id, body)
        self.assertNotIn("Ahmad", json.dumps(body), body)

    def test_the_header_states_how_late_it_is_rather_than_two_dates(self):
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        # Due in the past, so the figure is a real one whenever this runs.
        invoice = self.invoice(tenant_id, billing, due_on="2026-01-15")
        body = self.client.get(
            f"/finance/invoices/{invoice['invoice_id']}",
            headers=self.scoped(tenant_id, ["finance.account.read"])).json()
        self.assertIsNotNone(body["days_late"], body)
        self.assertGreater(body["days_late"], 0, body)

    def test_a_credit_note_is_linked_by_number_and_not_only_summed(self):
        """The design: "a credit note with its own number and a link to the original"."""
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        invoice = self.invoice(tenant_id, billing)
        owner = self.headers(tenant_id)
        series = self.client.post("/finance/fiscal-series", json={
            "legal_entity_id": billing["legal_entity_id"], "series_code": "CRN",
            "document_kind": "credit_note", **self.correlation()}, headers=owner)
        self.assertEqual(series.status_code, 201, series.text)
        credited = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": str(series.json()["series_id"]),
            "credits_invoice_id": invoice["invoice_id"],
            "lines": [{"description": "Goodwill", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 1600}],
            "issued_on": "2026-01-05", "due_on": "2026-01-05", "jurisdiction": "JO",
            "idempotency_key": f"cn-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner)
        self.assertEqual(credited.status_code, 201, credited.text)

        body = self.client.get(
            f"/finance/invoices/{invoice['invoice_id']}",
            headers=self.scoped(tenant_id, ["finance.account.read"])).json()
        self.assertEqual(len(body["credit_notes"]), 1, body)
        note = body["credit_notes"][0]
        self.assertEqual(note["invoice_id"], credited.json()["invoice_id"])
        self.assertEqual(note["document_number"], credited.json()["document_number"])
        # The sum still agrees with what the notes add up to.
        self.assertEqual(body["credited_minor"], note["gross_minor"], body)
        # And a settled invoice has no lateness, however late it was settled.
        self.assertIsNone(body["days_late"], body)

    def test_an_invoice_with_no_credit_note_says_so_with_an_empty_list(self):
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        invoice = self.invoice(tenant_id, billing)
        body = self.client.get(
            f"/finance/invoices/{invoice['invoice_id']}",
            headers=self.scoped(tenant_id, ["finance.account.read"])).json()
        self.assertEqual(body["credit_notes"], [], body)
        self.assertEqual(body["credited_minor"], 0, body)
        self.assertIsNone(body["credits_invoice_id"], body)

    def test_the_fiscal_reference_is_returned_once_the_authority_answers(self):
        """"Paid -- JoFotara reference shown". A boolean cannot be shown."""
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        invoice = self.invoice(tenant_id, billing)
        read = self.scoped(tenant_id, ["finance.account.read"])
        before = self.client.get(
            f"/finance/invoices/{invoice['invoice_id']}", headers=read).json()
        self.assertIsNone(before["fiscal_ack_ref"], before)

        head = self.headers(
            tenant_id, self.stepped_grant(tenant_id, ["finance.fiscal.manage"]))
        for target, ack in (("submitted", None), ("acknowledged", "JOFOTARA-88123")):
            moved = self.client.post(
                f"/finance/invoices/{invoice['invoice_id']}/fiscalize", json={
                    "target": target, **({"ack_ref": ack} if ack else {}),
                    **self.correlation()}, headers=head)
            self.assertEqual(moved.status_code, 200, moved.text)

        after = self.client.get(
            f"/finance/invoices/{invoice['invoice_id']}", headers=read).json()
        self.assertEqual(after["fiscal_ack_ref"], "JOFOTARA-88123", after)
        self.assertIs(after["fiscal_acknowledged"], True, after)

if __name__ == "__main__":
    unittest.main()


class CommandCentreReadTests(CommercialApiTestCase):
    """ADM-CC-01's figures and its queue, over HTTP.

    These are aggregates, which is a different failure mode from a listing: a list that is
    wrong shows the wrong row, and an aggregate that is wrong shows a number nobody can
    trace. So each test here fixes the input and asserts the arithmetic, and two of them
    assert a *boundary* the design states rather than a figure -- ADM-CC-02 says in as many
    words that a club manager does not see group revenue.
    """

    def test_a_settled_payment_is_collected_this_month(self):
        tenant_id = self.tenant()
        self.paid(tenant_id)
        read = self.client.get(
            "/finance/collections",
            headers=self.scoped(tenant_id, ["finance.revenue.read"]))
        self.assertEqual(read.status_code, 200, read.text)
        body = read.json()
        jod = next(b for b in body["collected"] if b["currency"] == "JOD")
        # 4500 net at 1600bp tax = 5220 gross, settled in full.
        self.assertEqual(jod["collected_minor"], 5220)
        self.assertEqual(body["month_to_date"]["last"], TODAY.isoformat())

    def test_a_refund_is_subtracted_from_what_was_collected(self):
        """A month that took 5,220 and refunded 1,000 collected 4,220.

        MOD-011's `gross_margin` read invoices and never read credit notes, and reported a
        50% margin on a period that earned nothing. This is the same confusion one module
        over, with the sign reversed.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        paid = self.paid(tenant_id)
        requested = self.client.post("/finance/refund-requests", json={
            "payment_id": paid["payment_id"], "amount_minor": 1000,
            "reason": "goodwill", **self.correlation()}, headers=owner)
        self.assertEqual(requested.status_code, 201, requested.text)
        # Two people, which is the module's own rule: the owner asked and somebody else
        # decides. A stepped-up session, because approving a refund is financial class.
        approver = self.headers(
            tenant_id, self.stepped_grant(tenant_id, ["finance.refund.approve"]))
        approved = self.client.post("/finance/refunds", json={
            "request_id": requested.json()["request_id"],
            "approval_reason": "agreed at the desk",
            "idempotency_key": f"rf-{uuid.uuid4().hex[:8]}",
            **self.correlation()}, headers=approver)
        self.assertEqual(approved.status_code, 201, approved.text)
        settled = self.client.post(
            f"/finance/refunds/{approved.json()['refund_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()}, headers=approver)
        self.assertEqual(settled.status_code, 200, settled.text)
        read = self.client.get(
            "/finance/collections",
            headers=self.scoped(tenant_id, ["finance.revenue.read"]))
        jod = next(b for b in read.json()["collected"] if b["currency"] == "JOD")
        self.assertEqual(jod["collected_minor"], 5220 - 1000)

    def test_no_baseline_reports_null_rather_than_a_fall(self):
        """A tenant with nothing last month cannot say whether this month is down.

        `0` would render as "unchanged" and any negative number would be invented.
        """
        tenant_id = self.tenant()
        self.paid(tenant_id)
        read = self.client.get(
            "/finance/collections",
            headers=self.scoped(tenant_id, ["finance.revenue.read"]))
        jod = next(b for b in read.json()["collected"] if b["currency"] == "JOD")
        self.assertEqual(jod["previous_minor"], 0)
        self.assertIsNone(jod["change_bp"])

    def test_the_pace_is_returned_under_its_own_name_and_says_what_it_is(self):
        tenant_id = self.tenant()
        self.paid(tenant_id)
        read = self.client.get(
            "/finance/collections",
            headers=self.scoped(tenant_id, ["finance.revenue.read"]))
        body = read.json()
        jod = next(b for b in body["collected"] if b["currency"] == "JOD")
        self.assertIn("pace_minor", jod)
        self.assertNotEqual(jod["pace_minor"], jod["collected_minor"] * 0)
        self.assertIn("straight-line", body["pace_is_a_projection"])
        self.assertIn("must not be", body["pace_is_a_projection"])

    def test_exactly_one_week_bucket_is_partial_and_it_is_the_last(self):
        tenant_id = self.tenant()
        self.paid(tenant_id)
        read = self.client.get(
            "/finance/collections?weeks=6",
            headers=self.scoped(tenant_id, ["finance.revenue.read"]))
        jod = next(b for b in read.json()["collected"] if b["currency"] == "JOD")
        self.assertEqual(len(jod["by_week"]), 6)
        partial = [w["partial"] for w in jod["by_week"]]
        # The week containing today is the only one that can be partial, and it is last. It is
        # not partial when today happens to be that week's final day.
        self.assertTrue(all(p is False for p in partial[:-1]), partial)

    def test_the_breakdown_is_by_legal_entity_and_says_it_is_not_by_location(self):
        """The design's chart is by club. The money chain carries a legal entity.

        MOD-004's hierarchy puts brands and locations *under* a legal entity, so three clubs
        under one entity are one row. Relabelling it would be a confident wrong answer on a
        revenue chart.
        """
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        read = self.client.get(
            "/finance/collections",
            headers=self.scoped(tenant_id, ["finance.revenue.read"]))
        body = read.json()
        jod = next(b for b in body["collected"] if b["currency"] == "JOD")
        entities = [e["legal_entity_id"] for e in jod["by_legal_entity"]]
        self.assertIn(paid["billing"]["legal_entity_id"], entities)
        self.assertIn("legal entity", body["by_location_is_unavailable"])

    def test_group_revenue_is_a_grant_a_membership_reader_does_not_hold(self):
        """ADM-CC-02 as a product boundary: "What Ziad does not see: group revenue".

        The design says the rail "is generated from his role rather than greyed", so the
        separation is the grant and not a step-up -- an owner opens this page every morning.
        """
        tenant_id = self.tenant()
        refused = self.client.get("/finance/collections", headers=self.scoped(
            tenant_id, ["membership.record.read", "finance.account.read"]))
        self.assertEqual(refused.status_code, 403, refused.text)
        allowed = self.client.get(
            "/finance/collections",
            headers=self.scoped(tenant_id, ["finance.revenue.read"]))
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_revenue_is_readable_without_a_step_up(self):
        """Routine on purpose. A second factor every morning means nobody looks.

        `grant` issues a password-only session, so a 200 here is the assertion: a financial
        action class on this permission would refuse it and the Command Center would open
        with its first metric missing.
        """
        tenant_id = self.tenant()
        head = self.scoped(tenant_id, ["finance.revenue.read"])
        who = self.client.get("/auth/session", headers=head)
        self.assertEqual(who.status_code, 200, who.text)
        self.assertEqual(int(who.json()["aal"]), 1)
        read = self.client.get("/finance/collections", headers=head)
        self.assertEqual(read.status_code, 200, read.text)

    def test_a_bad_week_count_or_week_start_refuses(self):
        tenant_id = self.tenant()
        head = self.scoped(tenant_id, ["finance.revenue.read"])
        for query in ("weeks=0", "weeks=400", "week_start=7", "week_start=-1"):
            answer = self.client.get(f"/finance/collections?{query}", headers=head)
            self.assertEqual(answer.status_code, 422, f"{query}: {answer.text}")

    def test_a_malformed_as_of_is_refused_rather_than_answered(self):
        tenant_id = self.tenant()
        answer = self.client.get(
            "/finance/collections?as_of=19-08-2026",
            headers=self.scoped(tenant_id, ["finance.revenue.read"]))
        self.assertEqual(answer.status_code, 422, answer.text)

    # ----------------------------------------------------------- the membership figures

    def test_an_activated_membership_counts_as_joined_this_month(self):
        """Counted from the lifecycle history, not from the status column.

        That column is a cache of where a membership is now and says nothing about how it got
        there, so a net figure derived from it would count memberships that *are* active
        rather than ones that *became* active.
        """
        tenant_id = self.tenant()
        # Starting today, so the activation's `effective_on` is inside this month. The shared
        # fixture starts ninety days back on purpose -- a freeze has to fall inside the
        # contract year it is decided in -- and that puts its activation in a month this read
        # is not about.
        self.membership(tenant_id, starts_on=TODAY.isoformat())
        read = self.client.get(
            "/memberships/summary",
            headers=self.scoped(tenant_id, ["membership.record.read"]))
        self.assertEqual(read.status_code, 200, read.text)
        body = read.json()
        self.assertEqual(body["active"], 1)
        self.assertEqual(body["this_month"]["joined"], 1)
        self.assertEqual(body["this_month"]["left"], 0)
        self.assertEqual(body["this_month"]["net"], 1)
        self.assertIn("cache", body["movement_is_from_the_history"])

    def test_a_membership_ending_inside_the_window_is_expiring_with_its_value(self):
        tenant_id = self.tenant()
        self.membership(tenant_id, starts_on=TODAY.isoformat())
        read = self.client.get(
            "/memberships/summary?expiring_within_days=60",
            headers=self.scoped(tenant_id, ["membership.record.read"]))
        body = read.json()["expiring"]
        self.assertGreaterEqual(body["count"], 1)
        value = next(v for v in body["renewal_value"] if v["currency"] == "JOD")
        # The agreement's own amount, which is what the membership was sold at.
        self.assertEqual(value["amount_minor"], 4500 * body["count"])

    def test_a_membership_ending_outside_the_window_is_not_expiring(self):
        """The window is the whole point: a board that listed every future end date would be
        a list of every member rather than the ones worth a call this week."""
        tenant_id = self.tenant()
        self.membership(tenant_id, starts_on=TODAY.isoformat())
        read = self.client.get(
            "/memberships/summary?expiring_within_days=1",
            headers=self.scoped(tenant_id, ["membership.record.read"]))
        self.assertEqual(read.json()["expiring"]["count"], 0)

    def test_a_bad_expiry_window_refuses(self):
        tenant_id = self.tenant()
        head = self.scoped(tenant_id, ["membership.record.read"])
        for query in ("expiring_within_days=0", "expiring_within_days=9999"):
            answer = self.client.get(f"/memberships/summary?{query}", headers=head)
            self.assertEqual(answer.status_code, 422, f"{query}: {answer.text}")

    # ----------------------------------------------------------- the recovery queue

    def test_an_open_recovery_case_is_listed_with_what_is_still_outstanding(self):
        """`at_risk` is what is unpaid on the cited invoice, not the invoice total.

        An invoice half paid and in recovery is chasing the half, and a queue that summed
        gross would overstate the morning's problem.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing, due_on=day(-30))
        opened = self.client.post("/finance/dunning-cases", json={
            "invoice_id": issued["invoice_id"],
            "idempotency_key": f"dc-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner)
        self.assertEqual(opened.status_code, 201, opened.text)
        read = self.client.get(
            "/finance/dunning-cases",
            headers=self.scoped(tenant_id, ["finance.dunning.read"]))
        self.assertEqual(read.status_code, 200, read.text)
        body = read.json()
        case = next(c for c in body["cases"] if c["invoice_id"] == issued["invoice_id"])
        self.assertEqual(case["status"], "open")
        self.assertEqual(case["outstanding_minor"], issued["gross_minor"])
        self.assertEqual(case["attempts"], 0)
        self.assertEqual(case["document_number"], issued["document_number"])
        at_risk = next(a for a in body["at_risk"] if a["currency"] == "JOD")
        self.assertEqual(at_risk["amount_minor"], issued["gross_minor"])

    # ------------------------------------------------- ADM-PAY-05, the recovery workspace

    def recovery_case(self, tenant_id, *, failure_code="card_expired",
                      membership_id=None, charges=1, due_on=None):
        """One open dunning case with `charges` failed charges behind it.

        A retry in this build is a *new* intent -- a settled one does not settle again -- so
        presenting a card four times is four intents, which is what this loop does and what
        the workspace counts.
        """
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(
            tenant_id, billing, due_on=due_on or day(-30), membership_id=membership_id)
        for _ in range(charges):
            intent = self.intent(tenant_id, billing, issued)
            failed = self.client.post(
                f"/finance/payment-intents/{intent['intent_id']}/settle",
                json={"outcome": "failed", "failure_code": failure_code,
                      "failure_detail": "Visa 4417 expired 08/26",
                      **self.correlation()}, headers=owner)
            self.assertEqual(failed.status_code, 200, failed.text)
        opened = self.client.post("/finance/dunning-cases", json={
            "invoice_id": issued["invoice_id"],
            "idempotency_key": f"dc-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner)
        self.assertEqual(opened.status_code, 201, opened.text)
        return {"billing": billing, "invoice": issued,
                "case_id": str(opened.json()["case_id"])}

    def recovery(self, tenant_id):
        read = self.client.get(
            "/finance/recovery",
            headers=self.scoped(tenant_id, ["finance.dunning.read"]))
        self.assertEqual(read.status_code, 200, read.text)
        return read.json()

    def test_the_workspace_sorts_the_cases_by_what_each_one_wants(self):
        """"The six are one decision, not six" is only true once the set is sorted.

        A batch mixing a member who needs a new card with a member whose membership is frozen
        is six decisions wearing one button, so the read is the sort: the same failure code on
        a live membership and on a frozen one comes back as two different treatments.
        """
        tenant_id = self.tenant()
        live = self.membership(tenant_id)
        frozen = self.membership(tenant_id, contract={"freeze_days_per_year": 30})
        held = self.client.post(
            f"/memberships/{frozen['membership_id']}/freeze", json={
                "freeze_kind": "freeze", "starts_on": day(-1), "days": 30,
                "reason": "travelling", "idempotency_key": f"fz-{uuid.uuid4().hex[:8]}",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(held.status_code, 201, held.text)
        ok = self.recovery_case(
            tenant_id, membership_id=live["membership_id"], charges=1)
        review = self.recovery_case(
            tenant_id, membership_id=frozen["membership_id"], charges=1)
        body = self.recovery(tenant_id)
        by_case = {c["case_id"]: c for c in body["cases"]}
        self.assertEqual(by_case[ok["case_id"]]["treatment"], "link")
        self.assertEqual(
            by_case[ok["case_id"]]["treatment_reason"], "member_action_needed")
        self.assertEqual(by_case[review["case_id"]]["treatment"], "review")
        self.assertEqual(
            by_case[review["case_id"]]["treatment_reason"], "membership_frozen")
        self.assertEqual(by_case[review["case_id"]]["membership_status"], "frozen")
        self.assertEqual(body["by_treatment"]["link"], 1)
        self.assertEqual(body["by_treatment"]["review"], 1)
        self.assertEqual(body["by_treatment"]["retry"], 0)

    def test_the_header_sentences_are_read_off_the_set_rather_than_supplied(self):
        """"All retries exhausted · no access blocked" is derived or it is a claim.

        A caller able to pass either in could head a workspace with a sentence its own rows
        contradict -- which is MOD-013's `priority: "critical"` shape, and here it would be
        the difference between "nothing left to try" and "the system is still trying".
        """
        tenant_id = self.tenant()
        live = self.membership(tenant_id)
        # One failed charge on a retryable code: the system has three attempts left, so this
        # is nobody's decision yet.
        self.recovery_case(
            tenant_id, failure_code="insufficient_funds",
            membership_id=live["membership_id"], charges=1)
        waiting = self.recovery(tenant_id)
        self.assertFalse(waiting["all_retries_exhausted"])
        self.assertEqual(waiting["by_treatment"]["retry"], 1)
        # A second tenant, four charges presented: the budget is spent and a link is the
        # remaining move.
        other = self.tenant()
        spent_for = self.membership(other)
        self.recovery_case(
            other, failure_code="insufficient_funds",
            membership_id=spent_for["membership_id"], charges=4)
        spent = self.recovery(other)
        self.assertTrue(spent["all_retries_exhausted"])
        self.assertEqual(spent["by_treatment"]["link"], 1)
        self.assertEqual(spent["cases"][0]["charges_presented"], 4)
        self.assertEqual(spent["cases"][0]["treatment_reason"], "retries_exhausted")
        # And the access sentence: a freshly opened case is at stage 1, whose recommendation
        # is `none`, which is what "no access blocked" means.
        self.assertTrue(spent["no_access_blocked"])
        self.assertEqual(spent["access_recommendations"], ["none"])

    def test_the_membership_is_the_one_the_invoice_cites(self):
        """Never the payer's latest, which would answer about a different agreement.

        The payer here has a live membership and the invoice cites none -- a retail sale to a
        member. A read that looked the person up would call this `member_action_needed` and
        send them the ordinary notice, which is a sentence about a membership this debt has
        nothing to do with.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        live = self.membership(tenant_id)
        billing = self.billing(tenant_id, live["person_id"])
        issued = self.invoice(tenant_id, billing, due_on=day(-30))
        intent = self.intent(tenant_id, billing, issued)
        self.assertEqual(self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/settle",
            json={"outcome": "failed", "failure_code": "card_expired",
                  **self.correlation()}, headers=owner).status_code, 200)
        self.assertEqual(self.client.post("/finance/dunning-cases", json={
            "invoice_id": issued["invoice_id"],
            "idempotency_key": f"dc-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner).status_code, 201)
        case = self.recovery(tenant_id)["cases"][0]
        self.assertIsNone(case["membership_id"])
        self.assertIsNone(case["membership_status"])
        self.assertEqual(case["treatment"], "review")
        self.assertEqual(case["treatment_reason"], "no_membership_cited")

    def test_the_workspace_returns_no_name_and_no_card_detail(self):
        """`payments_ledger`'s rule, applied to the same permission's other read.

        `finance.dunning.read` is tenant-wide money, so a name here would be a lateral read
        around `people.person.read`. And the provider's own sentence stays out: it is
        unbounded free text, it adds nothing the code does not already say, and paragraph
        1597 means the card brand and last four the design draws do not exist here at all.
        """
        tenant_id = self.tenant()
        live = self.membership(tenant_id)
        self.recovery_case(tenant_id, membership_id=live["membership_id"])
        raw = self.client.get(
            "/finance/recovery",
            headers=self.scoped(tenant_id, ["finance.dunning.read"])).text
        for leaked in ("Jane Smith", "Visa", "4417", "expired 08/26"):
            self.assertNotIn(leaked, raw, f"{leaked} reached a money read")
        case = self.recovery(tenant_id)["cases"][0]
        self.assertEqual(case["failure_code"], "card_expired")
        self.assertEqual(case["method"], "card")
        self.assertNotIn("failure_detail", case)
        self.assertIn("payment_method_ref", self.recovery(tenant_id)[
            "no_card_detail_exists"])

    def test_the_stage_picks_the_message_rather_than_whoever_clicks(self):
        """The mechanism behind the design's "enforced by the system, not the sender".

        A stage carries its notification key, so which message goes out is a property of how
        far the journey has got. A workspace that let the sender choose would be MOD-013's
        `bypass_policy_ref` with no permission behind it.
        """
        tenant_id = self.tenant()
        live = self.membership(tenant_id)
        self.recovery_case(tenant_id, membership_id=live["membership_id"])
        case = self.recovery(tenant_id)["cases"][0]
        self.assertEqual(case["stage"], 1)
        self.assertEqual(case["notification_key"], "payment_failed")

    def test_a_recovery_limit_outside_the_bound_refuses(self):
        tenant_id = self.tenant()
        head = self.scoped(tenant_id, ["finance.dunning.read"])
        for query in ("limit=0", "limit=9999"):
            answer = self.client.get(f"/finance/recovery?{query}", headers=head)
            self.assertEqual(answer.status_code, 422, f"{query}: {answer.text}")

    def test_seeing_the_queue_does_not_buy_advancing_it(self):
        """A read is a read. Advancing a journey sends a notice and moves the stage."""
        tenant_id = self.tenant()
        reader = self.scoped(tenant_id, ["finance.dunning.read"])
        refused = self.client.post("/finance/dunning-cases", json={
            "invoice_id": str(uuid.uuid4()), "idempotency_key": "x",
            **self.correlation()}, headers=reader)
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_a_status_outside_the_columns_own_vocabulary_refuses(self):
        """`status=resolved` and "nobody is in recovery" are different answers, and a list
        that rendered both as an empty queue is a queue nobody can trust."""
        tenant_id = self.tenant()
        answer = self.client.get(
            "/finance/dunning-cases?status=resolved",
            headers=self.scoped(tenant_id, ["finance.dunning.read"]))
        self.assertEqual(answer.status_code, 422, answer.text)

    def test_no_command_centre_read_returns_anything_about_the_person(self):
        """The same refusal `ListingReadTests` makes, applied to the aggregates.

        `membership.record.read` is routine and a front desk holds it; a summary carrying a
        member's name would be a lateral read around `people.person.read`.
        """
        tenant_id = self.tenant()
        name = f"Marguerite Oyelaran {uuid.uuid4().hex[:6]}"
        person_id = self.person(tenant_id, name=name)
        billing = self.billing(tenant_id, person_id)
        self.invoice(tenant_id, billing, due_on=day(-30))
        head = self.scoped(tenant_id, [
            "membership.record.read", "finance.revenue.read", "finance.dunning.read"])
        for path in ("/memberships/summary", "/finance/collections",
                     "/finance/dunning-cases"):
            answer = self.client.get(path, headers=head)
            self.assertEqual(answer.status_code, 200, answer.text)
            self.assertNotIn(name.split()[0], answer.text, path)


class RevenueReportTests(CommercialApiTestCase):
    """ADM-RPT-02's read, which has to actually run against the schema.

    **Every assertion here exists because lint cannot see a column name.** `ruff` and `mypy`
    pass on a query naming a column that does not exist, and this repository has already
    shipped one -- a read against `acc_credentials.rotating_window_seconds`, a column taken
    from a module's prose rather than its migration. These tests execute the SQL, so a wrong
    name is a failure rather than a 500 somebody finds by opening a page.

    The one that matters most: `fin_payments` has no `status` column. The table has no UPDATE
    grant at all, so a row exists only because the money arrived, and the first version of
    the outstanding query filtered on `p.status = 'succeeded'`.
    """

    def report(self, tenant_id: str, **params: str) -> dict:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        read = self.client.get(
            f"/reports/revenue{'?' + query if query else ''}",
            headers=self.scoped(tenant_id, ["finance.revenue.read"]))
        self.assertEqual(read.status_code, 200, read.text)
        return dict(read.json())

    def currency_block(self, report: dict, currency: str = "JOD") -> dict:
        blocks = [b for b in report["currencies"] if b["currency"] == currency]
        self.assertTrue(blocks, f"no {currency} block in {report['currencies']}")
        return dict(blocks[0])

    #: The helper issues every invoice on 2026-01-01, and a payment's `received_at` is
    #: `now()` and not settable -- so the invoice side of this report and the collected side
    #: fall in different months, and each assertion has to ask for its own window. Reading
    #: both through one `as_of` is how a test asserts a zero and calls it agreement.
    INVOICE_MONTH = "2026-01-31"

    def test_the_query_runs_against_the_real_schema(self):
        """The whole read, end to end, on a tenant that has billed and been paid.

        The point of this one is that it executes. `fin_payments` has no `status` column and
        the first version of the outstanding query filtered on one; lint passed.
        """
        tenant_id = self.tenant()
        self.paid(tenant_id)
        report = self.report(tenant_id, as_of=self.INVOICE_MONTH)
        self.assertIn("currencies", report)
        self.assertIn("outstanding_is_a_position", report)

    def test_collected_and_invoiced_are_separate_figures(self):
        """The canvas's own reason for four columns, as arithmetic.

        An invoice raised and left unpaid moves `invoiced` and not `collected`. A report
        carrying one number labelled "revenue" cannot express that, which is the sentence the
        design puts under this table.
        """
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        self.invoice(tenant_id, billing, amount=4500, rate_bp=1600)
        block = self.currency_block(self.report(tenant_id, as_of=self.INVOICE_MONTH))
        self.assertEqual(block["collected_minor"], 0)
        self.assertGreater(block["invoiced_minor"], 0)

    def test_an_unpaid_invoice_is_outstanding_and_a_paid_one_is_not(self):
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing, amount=4500, rate_bp=1600)
        owed = self.currency_block(
            self.report(tenant_id, as_of=self.INVOICE_MONTH))["outstanding_minor"]
        self.assertEqual(owed, int(issued["gross_minor"]))

        # Paid in full: outstanding is a position, so the payment counts against the January
        # invoice whenever it landed. Collected is a flow and belongs to the month it landed
        # in, which is why that half is read through today's window.
        other = self.tenant()
        self.paid(other)
        january = self.currency_block(self.report(other, as_of=self.INVOICE_MONTH))
        self.assertEqual(january["outstanding_minor"], 0)
        self.assertGreater(self.currency_block(self.report(other))["collected_minor"], 0)

    def test_outstanding_is_floored_per_invoice_so_an_overpayment_cannot_hide_a_debt(self):
        """Summing signed differences lets an overpaid invoice cancel an unpaid one.

        A tenant with one invoice overpaid by 100 and another unpaid by 100 is owed 100, not
        nothing -- and a report saying nothing is owed is a report that stops somebody
        chasing it.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        overpaid = self.invoice(tenant_id, billing, amount=1000, rate_bp=0)
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": overpaid["invoice_id"],
            "amount_minor": int(overpaid["gross_minor"]) + 10_000,
            "method": "card", "provider_key": "acme.payments",
            "idempotency_key": f"pi-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=owner)
        self.assertEqual(intent.status_code, 201, intent.text)
        settled = self.client.post(
            f"/finance/payment-intents/{intent.json()['intent_id']}/settle",
            json={"outcome": "succeeded", **self.correlation()}, headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)

        unpaid = self.invoice(tenant_id, billing, amount=1000, rate_bp=0)
        owed = self.currency_block(
            self.report(tenant_id, as_of=self.INVOICE_MONTH))["outstanding_minor"]
        self.assertEqual(owed, int(unpaid["gross_minor"]))

    def test_a_line_with_no_variant_is_its_own_source_rather_than_being_dropped(self):
        """So the sources sum to the invoiced total.

        An invoice raised by hand is real revenue. Dropping it would make a reader's own
        addition disagree with the figure above the table, and assigning it to a product type
        would be a confident wrong answer about which part of the business earned it.
        """
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        self.invoice(tenant_id, billing, amount=4500, rate_bp=0)
        block = self.currency_block(self.report(tenant_id, as_of=self.INVOICE_MONTH))
        kinds = {row["product_type"] for row in block["by_source"]}
        self.assertEqual(kinds, {"unattributed"})
        # **Against the net, not the gross.** A source row is net of tax and
        # `invoiced_minor` is gross, so a reader adding the breakdown up finds it short by
        # the tax unless the figure it reconciles to is returned beside it. Found by
        # rendering the report and checking the column by hand: 46.50 under a headline of
        # 53.94 reads as a breakdown that lost a row.
        self.assertEqual(
            sum(row["net_minor"] for row in block["by_source"]), block["invoiced_net_minor"])

    def test_the_sources_add_up_to_the_net_and_the_net_is_below_the_gross(self):
        """The identity a reader checks a breakdown against, with tax actually charged."""
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        self.invoice(tenant_id, billing, amount=4500, rate_bp=1600)
        block = self.currency_block(self.report(tenant_id, as_of=self.INVOICE_MONTH))
        self.assertEqual(
            sum(row["net_minor"] for row in block["by_source"]), block["invoiced_net_minor"])
        self.assertLess(block["invoiced_net_minor"], block["invoiced_minor"])

    def test_a_source_row_breaks_down_by_legal_entity(self):
        tenant_id = self.tenant()
        billing = self.billing(tenant_id, self.person(tenant_id))
        self.invoice(tenant_id, billing, amount=4500, rate_bp=0)
        block = self.currency_block(self.report(tenant_id, as_of=self.INVOICE_MONTH))
        row = block["by_source"][0]
        self.assertEqual(
            [e["legal_entity_id"] for e in row["by_legal_entity"]],
            [billing["legal_entity_id"]])

    def test_the_report_needs_the_revenue_permission(self):
        tenant_id = self.tenant()
        refused = self.client.get(
            "/reports/revenue", headers=self.scoped(tenant_id, ["membership.record.read"]))
        self.assertEqual(refused.status_code, 403, refused.text)


class PaymentsLedgerTests(CommercialApiTestCase):
    """ADM-PAY-01's read: money in, money out and money contested on one axis.

    **The screen this answers did not exist, and the read did not either.** MOD-017 could say
    what one member owed and had nothing that put a tenant's payments, failed attempts,
    refunds and disputes in one list -- which is the one thing a reconciler opens every
    morning. The canvas's rule is what these tests are about: "a refund is never shown as a
    payment of a different colour -- it is a different sign on the same axis".
    """

    def ledger(self, tenant_id: str, **params: str) -> dict:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        read = self.client.get(
            f"/finance/payments{'?' + query if query else ''}",
            headers=self.scoped(tenant_id, ["finance.payment.read"]))
        self.assertEqual(read.status_code, 200, read.text)
        return dict(read.json())

    def test_a_settled_payment_is_positive_and_needs_nobody(self):
        tenant_id = self.tenant()
        paid = self.paid(tenant_id)
        rows = self.ledger(tenant_id)["entries"]
        payment = next(r for r in rows if r["kind"] == "payment")
        self.assertEqual(payment["row_id"], paid["payment_id"])
        self.assertGreater(payment["amount_minor"], 0)
        self.assertFalse(payment["needs_action"])

    def test_a_refund_is_a_negative_amount_on_the_same_axis(self):
        """The canvas's rule, as arithmetic rather than as a colour.

        A board that rendered a refund positive and coloured it would pass any assertion
        about the row existing, and would make the amount column stop adding up -- which is
        the one property a reconciler checks it against.
        """
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        paid = self.paid(tenant_id)
        requested = self.client.post("/finance/refund-requests", json={
            "payment_id": paid["payment_id"], "amount_minor": 1000,
            "reason": "charged after she froze", **self.correlation()}, headers=owner)
        self.assertEqual(requested.status_code, 201, requested.text)
        approver = self.headers(
            tenant_id, self.stepped_grant(tenant_id, ["finance.refund.approve"]))
        approved = self.client.post("/finance/refunds", json={
            "request_id": requested.json()["request_id"],
            "approval_reason": "agreed: it should not have run",
            "idempotency_key": f"rf-{uuid.uuid4().hex[:8]}",
            **self.correlation()}, headers=approver)
        self.assertEqual(approved.status_code, 201, approved.text)

        rows = self.ledger(tenant_id)["entries"]
        refund = next(r for r in rows if r["kind"] == "refund")
        self.assertEqual(refund["amount_minor"], -1000)
        # **And it names what it is about**, which is the canvas's parenthetical original: a
        # negative figure with no story is a figure nobody can check.
        self.assertEqual(refund["about_payment_id"], paid["payment_id"])
        # A refund nobody has settled is a row somebody has to act on.
        self.assertTrue(refund["needs_action"])

    def test_a_failed_charge_is_a_row_rather_than_an_absence(self):
        """A ledger of successes is a ledger that cannot be reconciled."""
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        issued = self.invoice(tenant_id, billing)
        intent = self.intent(tenant_id, billing, issued)
        self.assertEqual(self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/settle",
            json={"outcome": "failed", "failure_code": "card_expired",
                  **self.correlation()}, headers=owner).status_code, 200)

        answer = self.ledger(tenant_id)
        attempt = next(r for r in answer["entries"] if r["kind"] == "attempt")
        self.assertEqual(attempt["state"], "failed")
        self.assertTrue(attempt["needs_action"])
        self.assertEqual(answer["failed"], 1)
        # And the intent that *did* settle is not duplicated as an attempt beside its
        # payment, because a settled intent is the payment above it.
        self.assertEqual(
            [r for r in answer["entries"] if r["kind"] == "attempt"], [attempt])

    def test_an_open_dispute_is_negative_and_needs_somebody(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        paid = self.paid(tenant_id)
        opened = self.client.post("/finance/disputes", json={
            "payment_id": paid["payment_id"], "provider_case_ref": "ACME-1",
            "dispute_kind": "chargeback", "reason_code": "not_received",
            "amount_minor": 2000, "currency": "JOD",
            "opened_on": "2026-01-02", "respond_due_on": "2026-02-01",
            "idempotency_key": f"dp-{uuid.uuid4().hex[:8]}",
            **self.correlation()}, headers=owner)
        self.assertEqual(opened.status_code, 201, opened.text)
        rows = self.ledger(tenant_id, since="2026-01-01", until="2026-01-31")["entries"]
        dispute = next(r for r in rows if r["kind"] == "dispute")
        self.assertEqual(dispute["amount_minor"], -2000)
        self.assertTrue(dispute["needs_action"])
        self.assertEqual(dispute["about_payment_id"], paid["payment_id"])

    def test_the_needs_action_filter_drops_the_settled_rows(self):
        tenant_id = self.tenant()
        owner = self.headers(tenant_id)
        self.paid(tenant_id)
        billing = self.billing(tenant_id, self.person(tenant_id))
        intent = self.intent(tenant_id, billing)
        self.client.post(
            f"/finance/payment-intents/{intent['intent_id']}/settle",
            json={"outcome": "failed", "failure_code": "do_not_honour",
                  **self.correlation()}, headers=owner)
        filtered = self.ledger(tenant_id, needs_action="true")
        self.assertTrue(filtered["entries"])
        self.assertTrue(all(r["needs_action"] for r in filtered["entries"]))
        self.assertNotIn("payment", {r["kind"] for r in filtered["entries"]})

    def test_the_ledger_carries_no_name_and_no_card(self):
        """**The control is an absence**, so it is asserted as one.

        `finance.payment.read` is tenant-wide. A money permission that returned a member's
        name would be a lateral read path around `people.person.read` -- MOD-010's
        `events.event.read` finding, which this repository has paid for once.
        """
        tenant_id = self.tenant()
        self.paid(tenant_id)
        read = self.client.get(
            "/finance/payments",
            headers=self.scoped(tenant_id, ["finance.payment.read"]))
        self.assertEqual(read.status_code, 200, read.text)
        for row in read.json()["entries"]:
            self.assertNotIn("legal_name", row)
            self.assertNotIn("payer_name", row)
            self.assertNotIn("payment_method_ref", row)
            self.assertNotIn("provider_ref", row)
        self.assertNotIn("Jane", read.text)

    def test_another_tenants_money_is_not_on_this_ledger(self):
        mine = self.tenant()
        theirs = self.tenant()
        self.paid(theirs)
        self.assertEqual(self.ledger(mine)["entries"], [])

    def test_a_window_that_ends_before_it_starts_is_refused(self):
        tenant_id = self.tenant()
        read = self.client.get(
            "/finance/payments?since=2026-02-01&until=2026-01-01",
            headers=self.scoped(tenant_id, ["finance.payment.read"]))
        # 422, not 409: an `InvalidRequest` is a malformed request rather than a conflict
        # with the tenant's state, and a window that ends before it starts is the first.
        self.assertEqual(read.status_code, 422, read.text)

    def test_an_unbounded_limit_is_refused_rather_than_served(self):
        tenant_id = self.tenant()
        read = self.client.get(
            "/finance/payments?limit=100000",
            headers=self.scoped(tenant_id, ["finance.payment.read"]))
        self.assertEqual(read.status_code, 422, read.text)


class EndedMembershipGrantTests(CommercialApiTestCase):
    """The half of a future-dated cancellation that never arrived.

    `cancel_membership` revokes grants in its own transaction when the date is today or
    earlier and deliberately does not when it is later -- "the member is still paying for the
    notice period and still entitled to train". Nothing revoked them when the date came.

    **The door was never wrong and the entitlement was**, which is why this survived a review
    that found the immediate-cancellation version of it. MOD-022 reads the membership's dates
    rather than its cached status, so a turnstile refuses a row that calls itself active past
    its own `ends_on`. `entitlements.usable` sees only the grant -- its own status and its own
    `valid_to`, which is optional -- so a perpetual grant from a cancelled membership stayed
    drawable and a booking took a place somebody paying could have had.
    """

    def _ended_membership_with_a_grant(self, tenant_id: str) -> tuple[str, str]:
        """A membership whose notice ran out yesterday, still holding a live grant.

        The cancellation is driven through the route so the decision is a real one; `ends_on`
        is then moved into the past, which is what the clock would have done.
        """
        live = self.membership(tenant_id, contract={
            "notice_days": 30, "cancellation_mode": "end_of_notice"})
        membership_id = str(live["membership_id"])
        person_id = str(live["person_id"])
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), person_id,
            source_kind="membership", membership_id=membership_id)
        cancelled = self.client.post(
            f"/memberships/{membership_id}/cancel", json={
                "reason": "moving away", "idempotency_key": f"c-{uuid.uuid4().hex[:8]}",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertFalse(cancelled.json()["takes_effect_immediately"])
        # Nothing was revoked, which is the module's own decision and the thing that has to
        # be undone when the date arrives.
        self.assertEqual(cancelled.json()["entitlements_revoked"], [])
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            conn.execute(
                "UPDATE plt01.mem_memberships SET ends_on = current_date - 1,"
                " version = version + 1 WHERE membership_id = %s", (membership_id,))
        return membership_id, grant_id

    def _grant_status(self, tenant_id: str, grant_id: str) -> str:
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            row = conn.execute(
                "SELECT status FROM plt01.mem_entitlement_grants WHERE grant_id = %s",
                (grant_id,)).fetchone()
        assert row is not None
        return str(row[0])

    def test_a_grant_outlives_its_membership_until_the_sweep_runs(self):
        """The defect, stated as a test: before the sweep the grant is still active, and
        `entitlements.usable` has nothing to tell it otherwise."""
        tenant_id = self.tenant()
        membership_id, grant_id = self._ended_membership_with_a_grant(tenant_id)
        self.assertEqual(self._grant_status(tenant_id, grant_id), "active")
        done = commercial.revoke_grants_of_ended_memberships(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        self.assertEqual(done["memberships"], 1)
        self.assertEqual(done["grants_revoked"], 1)
        self.assertEqual(done["failed"], [])
        self.assertEqual(self._grant_status(tenant_id, grant_id), "revoked")

    def test_a_membership_still_inside_its_notice_keeps_its_entitlements(self):
        """**Which is what a notice period is.** Revoking at the decision rather than at the
        date would take away training the member has already paid for."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id, contract={
            "notice_days": 30, "cancellation_mode": "end_of_notice"})
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), str(live["person_id"]),
            source_kind="membership", membership_id=str(live["membership_id"]))
        self.client.post(
            f"/memberships/{live['membership_id']}/cancel", json={
                "reason": "moving away", "idempotency_key": "c-inside",
                **self.correlation()}, headers=self.headers(tenant_id))
        done = commercial.revoke_grants_of_ended_memberships(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        self.assertEqual(done["memberships"], 0)
        self.assertEqual(self._grant_status(tenant_id, grant_id), "active")

    def test_a_second_pass_revokes_nothing_because_the_grant_is_no_longer_active(self):
        """Idempotent by `_revoke_grants`' own predicate rather than by a key, which is what
        keeps the worker's disposable schedule honest with no new state."""
        tenant_id = self.tenant()
        self._ended_membership_with_a_grant(tenant_id)
        first = commercial.revoke_grants_of_ended_memberships(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        second = commercial.revoke_grants_of_ended_memberships(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        self.assertEqual(first["grants_revoked"], 1)
        self.assertEqual(second["memberships"], 0)
        self.assertEqual(second["grants_revoked"], 0)

    def test_the_balance_goes_to_zero_by_arithmetic_rather_than_by_the_status(self):
        """`_revoke_grants` writes a ledger row for what remained, which is why the balance
        and the status cannot disagree afterwards."""
        tenant_id = self.tenant()
        _, grant_id = self._ended_membership_with_a_grant(tenant_id)
        commercial.revoke_grants_of_ended_memberships(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        read = self.client.get(
            f"/member-entitlements/grants/{grant_id}"
            f"?correlation_id={self.correlation()['correlation_id']}",
            headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()["balance"], 0)

    def test_a_membership_that_simply_ended_is_swept_too_not_only_a_cancelled_one(self):
        """The predicate is `ends_on`, which is what the door judges by -- so a fixed-term
        membership that ran out is the same fact as one cancelled with notice. Keying on the
        cancellation instead would be a second definition of "this membership is over"."""
        tenant_id = self.tenant()
        live = self.membership(tenant_id)
        grant_id = self.entitlement_grant(
            tenant_id, self.policy(tenant_id), str(live["person_id"]),
            source_kind="membership", membership_id=str(live["membership_id"]))
        with tenant_scope(self._tenant_pool, tenant_id) as conn:
            conn.execute(
                "UPDATE plt01.mem_memberships SET ends_on = current_date - 1,"
                " version = version + 1 WHERE membership_id = %s",
                (str(live["membership_id"]),))
        done = commercial.revoke_grants_of_ended_memberships(
            self._tenant_pool, tenant_id, actor_id=ACTOR, correlation_id=str(uuid.uuid4()))
        self.assertEqual(done["grants_revoked"], 1)
        self.assertEqual(self._grant_status(tenant_id, grant_id), "revoked")

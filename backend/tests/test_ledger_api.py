"""MOD-018 COM-04 over HTTP, with the credentials a real caller would hold.

**Driven through the routes, not the service.** MOD-014's reviewers found four defects in its
request path that a green suite could not see, because every test reached past the gate; MOD-016
then turned out to have no test that had ever called a `/catalog` route successfully, which is
why four of its findings survived a green suite. The gate, the permission resolution and the
derived fields all live on this path.

Risk class is Restricted and Tier 1, so the tests that matter most are the ones about the
ledger's own invariants: that an unbalanced journal cannot be posted, that a closed period
refuses one, that a posted journal cannot be edited, that a wallet debit spends promotional
value before cash, and that a prepaid year is not day-one revenue.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import date, timedelta

from tests.support import GatedApiTestCase

TODAY = date.today()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def period_of(offset: int = 0) -> str:
    moment = TODAY + timedelta(days=offset)
    return f"{moment.year:04d}-{moment.month:02d}"


class LedgerApiTestCase(GatedApiTestCase):
    """Fixtures: a legal entity, a chart and the sessions the money flows need."""

    #: The brand each location this suite made belongs to, because a location-scoped account
    #: has to name one and there is no route that reads a location back.
    brands: dict[str, str]

    def setUp(self) -> None:
        super().setUp()
        self.brands = {}

    def correlation(self) -> dict[str, str]:
        return {"correlation_id": str(uuid.uuid4())}

    def person(self, tenant_id: str, name: str = "Jane Smith") -> str:
        created = self.client.post("/people", json={
            "legal_name": name, "profile_kinds": ["member"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["person_id"])

    def legal_entity(self, tenant_id: str) -> str:
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

    def location(self, tenant_id: str) -> str:
        owner = self.headers(tenant_id)
        org = self.client.post("/organizations", json={
            "legal_name": "Veyro Sites Ltd", "country_code": "JO",
            **self.correlation()}, headers=owner)
        brand = self.client.post("/brands", json={
            "organization_id": org.json()["organization_id"], "brand_name": "City"},
            headers=owner)
        self.assertEqual(brand.status_code, 201, brand.text)
        created = self.client.post("/locations", json={
            "brand_id": brand.json()["brand_id"], "location_name": "Downtown",
            "timezone": "Asia/Amman"}, headers=owner)
        self.assertEqual(created.status_code, 201, created.text)
        self.brands[str(created.json()["location_id"])] = str(brand.json()["brand_id"])
        return str(created.json()["location_id"])

    def billing(self, tenant_id: str, entity: str, person_id: str) -> dict:
        owner = self.headers(tenant_id)
        account = self.client.post("/finance/accounts", json={
            "payer_person_id": person_id,
            "account_number": f"A{uuid.uuid4().hex[:8].upper()}", "currency": "JOD",
            "legal_entity_id": entity, **self.correlation()}, headers=owner)
        self.assertEqual(account.status_code, 201, account.text)
        series = self.client.post("/finance/fiscal-series", json={
            "legal_entity_id": entity, "series_code": "INV",
            **self.correlation()}, headers=owner)
        self.assertEqual(series.status_code, 201, series.text)
        return {"billing_account_id": str(account.json()["billing_account_id"]),
                "series_id": str(series.json()["series_id"])}

    def account(self, tenant_id: str, code: str, kind: str, **kwargs) -> str:
        body = {"account_code": code, "account_kind": kind,
                "display_name": code.title(), "currency": "JOD", **self.correlation()}
        body.update(kwargs)
        created = self.client.post("/ledger/accounts", json=body,
                                   headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        return str(created.json()["account_id"])

    def chart(self, tenant_id: str, *, entity: str | None = None) -> dict[str, str]:
        """The accounts every money flow in this module needs.

        **Tenant-wide, because that is what the bridge looks up.** A till's cash account is per
        location and is named explicitly by whatever knows which till.
        """
        return {
            "cash": self.account(tenant_id, "CASH", "cash"),
            "bank": self.account(tenant_id, "BANK", "bank"),
            "receivable": self.account(tenant_id, "AR", "receivable"),
            "clearing": self.account(tenant_id, "CLEARING", "provider_clearing"),
            "tax": self.account(tenant_id, "TAX", "tax_payable"),
            "revenue": self.account(tenant_id, "REV", "revenue"),
            "contra": self.account(tenant_id, "CONTRA", "contra_revenue"),
            "unearned": self.account(tenant_id, "UNEARNED", "unearned_revenue"),
            "wallet_cash": self.account(tenant_id, "WCASH", "wallet_cash"),
            "wallet_promo": self.account(tenant_id, "WPROMO", "wallet_promotional"),
            "suspense": self.account(tenant_id, "SUSPENSE", "suspense"),
            "fee": self.account(tenant_id, "FEE", "provider_fee"),
        }

    def close_period(self, tenant_id: str, entity: str, period_key: str) -> None:
        """**Two steps, because `closing` is where the close's own work happens.**

        `open -> closed` is refused by the state machine: a period mid-close has to stop
        taking trade while still admitting the recognition and settlement entries the close
        itself produces.
        """
        for target in ("closing", "closed"):
            moved = self.client.post("/ledger/periods/close", json={
                "legal_entity_id": entity, "period_key": period_key,
                "target": target, **self.correlation()},
                headers=self.headers(tenant_id))
            self.assertEqual(moved.status_code, 200, moved.text)
            self.assertEqual(moved.json()["status"], target)

    def drawer(self, tenant_id: str, entity: str, location_id: str,
               *, float_minor: int = 5000, label: str = "front") -> dict[str, str]:
        """A till with its float posted from the safe.

        **The float is a journal, not a declaration.** Otherwise the drawer's own account
        balance is not the money in the drawer, and banking the takings drives it negative by
        exactly the float -- which is how this fixture found the defect.
        """
        till = self.account(tenant_id, f"TILL-{label.upper()}", "cash")
        safe = self.account(tenant_id, f"SAFE-{label.upper()}", "cash")
        opened = self.client.post("/ledger/cash-sessions", json={
            "location_id": location_id, "cash_account_id": till,
            "drawer_label": label, "currency": "JOD",
            "opening_float_minor": float_minor,
            "float_source_account_id": safe, "legal_entity_id": entity,
            "idempotency_key": f"t-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(opened.status_code, 201, opened.text)
        return {"session_id": str(opened.json()["session_id"]), "till": till,
                "safe": safe}

    def unearned_held(self, tenant_id: str, entity: str, chart: dict[str, str],
                      amount: int) -> None:
        """Bill `amount` to unearned revenue, so a schedule has a liability to draw down.

        **The schedule's total and the invoice's unearned part are two different figures a
        caller supplies**, and the second defaulted to zero -- so a schedule opened against an
        invoice that credited nothing to unearned revenue drove that liability negative, the
        ledger asserting that members have prepaid negative money.
        """
        posted = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": amount},
                      {"account_id": chart["unearned"], "amount_minor": -amount}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": f"prepayment {amount}",
            "description": "cash taken for a service not yet delivered",
            "idempotency_key": f"u-{uuid.uuid4().hex[:8]}", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(posted.status_code, 201, posted.text)

    def journal(self, tenant_id: str, entity: str, chart: dict[str, str],
                *, amount: int = 1000, **kwargs) -> dict:
        body = {
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": amount},
                      {"account_id": chart["revenue"], "amount_minor": -amount}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "a till sale", "description": "a till sale",
            "idempotency_key": f"j-{uuid.uuid4().hex[:8]}", **self.correlation(),
        }
        body.update(kwargs)
        posted = self.client.post("/ledger/journals", json=body,
                                  headers=self.headers(tenant_id))
        self.assertEqual(posted.status_code, 201, posted.text)
        return dict(posted.json())


class ChartTests(LedgerApiTestCase):
    def test_an_account_reports_its_class_and_its_normal_side(self):
        tenant_id = self.tenant()
        created = self.client.post("/ledger/accounts", json={
            "account_code": "WCASH", "account_kind": "wallet_cash",
            "display_name": "Member wallet", "currency": "JOD", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["account_class"], "liability")
        self.assertEqual(created.json()["normal_side"], "credit")

    def test_an_unknown_account_kind_is_refused_with_a_sentence(self):
        """The catalogue is the authority on what this software posts; a per-tenant set would
        let two tenants disagree with the code."""
        tenant_id = self.tenant()
        refused = self.client.post("/ledger/accounts", json={
            "account_code": "PIGGY", "account_kind": "piggy_bank",
            "display_name": "Piggy bank", "currency": "JOD", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("unknown_account_kind", refused.text)

    def test_a_retired_account_takes_no_postings_and_keeps_its_own(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        self.journal(tenant_id, entity, chart, amount=4000)
        retired = self.client.post(
            f"/ledger/accounts/{chart['cash']}/retire", json=self.correlation(),
            headers=self.headers(tenant_id))
        self.assertEqual(retired.status_code, 200, retired.text)
        refused = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 100},
                      {"account_id": chart["revenue"], "amount_minor": -100}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "after retirement", "description": "after retirement",
            "idempotency_key": "j-retired", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("retired", refused.text)
        # **Retired, not deleted**: the balance is a sum over postings, so deleting the
        # account would make every past journal that used it unreadable.
        balance = self.client.get(
            f"/ledger/accounts/{chart['cash']}/balance",
            headers=self.headers(tenant_id))
        self.assertEqual(balance.status_code, 200, balance.text)
        self.assertEqual(balance.json()["balance_minor"], 4000)


class JournalTests(LedgerApiTestCase):
    def test_a_balanced_journal_posts_and_reads_back_with_its_sides(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        posted = self.journal(tenant_id, entity, chart, amount=5220)
        self.assertEqual(posted["control_total_minor"], 5220)
        self.assertEqual(posted["period_key"], period_of())
        self.assertTrue(posted["period_opened"])
        read = self.client.get(f"/ledger/journals/{posted['journal_id']}",
                               headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual([p["side"] for p in read.json()["postings"]],
                         ["debit", "credit"])

    def test_an_unbalanced_journal_is_refused_before_anything_is_written(self):
        """**The decision function refuses first and the deferred trigger is the backstop.**
        Both, because the first is for the caller and the second is for the next service."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        refused = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 1000},
                      {"account_id": chart["revenue"], "amount_minor": -900}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "wrong", "description": "wrong",
            "idempotency_key": "j-unbalanced", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("sum to 100", refused.text)

    def test_a_journal_in_one_currency_cannot_touch_another_currency_s_account(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        usd = self.account(tenant_id, "USDCASH", "cash", currency="USD")
        refused = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": usd, "amount_minor": 1000},
                      {"account_id": chart["revenue"], "amount_minor": -1000}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "mixed", "description": "mixed",
            "idempotency_key": "j-mixed", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("USD", refused.text)

    def test_a_journal_is_idempotent_on_its_key_and_scoped_to_its_entity(self):
        """MOD-017's finding: a key reused across two payers returned the other payer's
        invoice and reported a successful repeat."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        other = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        first = self.journal(tenant_id, entity, chart, idempotency_key="j-shared")
        again = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 1000},
                      {"account_id": chart["revenue"], "amount_minor": -1000}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "a till sale", "description": "again",
            "idempotency_key": "j-shared", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["journal_id"], first["journal_id"])
        # **A key reused for a different movement is refused rather than answered.** The
        # repeat path compared the entity and nothing else, so a decoy journal was handed
        # back as another command's repeat and that command's own journal was never written.
        other_movement = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 1000},
                      {"account_id": chart["revenue"], "amount_minor": -1000}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "something else entirely", "description": "again",
            "idempotency_key": "j-shared", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(other_movement.status_code, 409, other_movement.text)
        self.assertIn("another_movement", other_movement.text)
        confused = self.client.post("/ledger/journals", json={
            "legal_entity_id": other,
            "lines": [{"account_id": chart["cash"], "amount_minor": 1000},
                      {"account_id": chart["revenue"], "amount_minor": -1000}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "elsewhere", "description": "elsewhere",
            "idempotency_key": "j-shared", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(confused.status_code, 409, confused.text)
        self.assertIn("another_legal_entity", confused.text)

    def test_a_posted_journal_is_corrected_and_never_edited(self):
        """Paragraph 1685's Critical Control. The original stays where it is, the reversal
        names it, and a reader asking what happened sees both."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        posted = self.journal(tenant_id, entity, chart, amount=2500)
        corrected = self.client.post(
            f"/ledger/journals/{posted['journal_id']}/correct", json={
                "reason": "posted to the wrong till", "idempotency_key": "c-1",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(corrected.status_code, 201, corrected.text)
        self.assertEqual(corrected.json()["purpose"], "correction")
        read = self.client.get(f"/ledger/journals/{posted['journal_id']}",
                               headers=self.headers(tenant_id)).json()
        self.assertEqual(read["corrected_by_journal_id"],
                         corrected.json()["journal_id"])
        reversal = self.client.get(
            f"/ledger/journals/{corrected.json()['journal_id']}",
            headers=self.headers(tenant_id)).json()
        self.assertEqual([p["amount_minor"] for p in reversal["postings"]],
                         [-2500, 2500])
        # And the account is back where it started, which is what a reversal means.
        balance = self.client.get(
            f"/ledger/accounts/{chart['cash']}/balance",
            headers=self.headers(tenant_id)).json()
        self.assertEqual(balance["balance_minor"], 0)

    def test_a_journal_is_corrected_once(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        posted = self.journal(tenant_id, entity, chart)
        self.assertEqual(self.client.post(
            f"/ledger/journals/{posted['journal_id']}/correct", json={
                "reason": "first", "idempotency_key": "c-a", **self.correlation()},
            headers=self.headers(tenant_id)).status_code, 201)
        again = self.client.post(
            f"/ledger/journals/{posted['journal_id']}/correct", json={
                "reason": "second", "idempotency_key": "c-b", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("already_been_corrected", again.text)

    def test_a_correction_is_not_itself_reversed(self):
        """Almost always somebody trying to undo an undo, which leaves three journals and no
        clear position."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        posted = self.journal(tenant_id, entity, chart)
        corrected = self.client.post(
            f"/ledger/journals/{posted['journal_id']}/correct", json={
                "reason": "wrong", "idempotency_key": "c-1", **self.correlation()},
            headers=self.headers(tenant_id))
        refused = self.client.post(
            f"/ledger/journals/{corrected.json()['journal_id']}/correct", json={
                "reason": "undo the undo", "idempotency_key": "c-2",
                **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("not_itself_reversed", refused.text)

    def test_the_trial_balance_balances(self):
        """Every journal balances, so the debits and credits of all of them are equal by
        construction -- and a trial balance where they are not is a ledger that lost rows."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        self.journal(tenant_id, entity, chart, amount=4000)
        self.journal(tenant_id, entity, chart, amount=1500)
        read = self.client.get(
            f"/ledger/trial-balance?legal_entity_id={entity}&currency=JOD",
            headers=self.headers(tenant_id))
        self.assertEqual(read.status_code, 200, read.text)
        self.assertTrue(read.json()["balanced"])
        self.assertEqual(read.json()["debit_total_minor"], 5500)
        self.assertEqual(read.json()["credit_total_minor"], 5500)


class PeriodTests(LedgerApiTestCase):
    def test_a_closed_period_refuses_a_posting(self):
        """COM-04-R06. Once finance has told an authority what a month was, a posting dated
        into it makes the statement and the filing disagree."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        self.journal(tenant_id, entity, chart)
        straight = self.client.post("/ledger/periods/close", json={
            "legal_entity_id": entity, "period_key": period_of(), "target": "closed",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(straight.status_code, 409, straight.text)
        self.assertIn("does not move from open to closed", straight.text)
        self.close_period(tenant_id, entity, period_of())
        refused = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 100},
                      {"account_id": chart["revenue"], "amount_minor": -100}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "late", "description": "late", "idempotency_key": "j-late",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("closed", refused.text)

    def test_a_closing_period_admits_the_close_s_own_work_and_no_trade(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        self.journal(tenant_id, entity, chart)
        moved = self.client.post("/ledger/periods/close", json={
            "legal_entity_id": entity, "period_key": period_of(),
            "target": "closing", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(moved.status_code, 200, moved.text)
        refused = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 100},
                      {"account_id": chart["revenue"], "amount_minor": -100}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "trade", "description": "trade",
            "idempotency_key": "j-trade", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        # **`purpose: "close"` costs the close's own permission.** With `purpose` free, the
        # identical journal went in as `settlement` after being refused as `trade`.
        accepted = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["unearned"], "amount_minor": 100},
                      {"account_id": chart["revenue"], "amount_minor": -100}],
            "posted_on": day(0), "currency": "JOD", "purpose": "close",
            "source_kind": "manual", "source_ref": "the close itself",
            "description": "an accrual at close", "idempotency_key": "j-rec",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(accepted.status_code, 201, accepted.text)
        # And a caller holding only the posting permission cannot send it.
        weak = self.headers(tenant_id, self.stepped_grant(
            tenant_id, ["finance.ledger.post"]))
        refused_close = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["unearned"], "amount_minor": 100},
                      {"account_id": chart["revenue"], "amount_minor": -100}],
            "posted_on": day(0), "currency": "JOD", "purpose": "close",
            "source_kind": "manual", "source_ref": "not mine to post",
            "description": "not mine to post", "idempotency_key": "j-weak-close",
            **self.correlation()}, headers=weak)
        self.assertEqual(refused_close.status_code, 403, refused_close.text)

    def test_reopening_a_period_states_why_and_is_its_own_permission(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        self.journal(tenant_id, entity, chart)
        self.close_period(tenant_id, entity, period_of())
        refused = self.client.post("/ledger/periods/reopen", json={
            "legal_entity_id": entity, "period_key": period_of(), "reason": "   ",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        reopened = self.client.post("/ledger/periods/reopen", json={
            "legal_entity_id": entity, "period_key": period_of(),
            "reason": "an invoice was issued against the wrong entity",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json()["status"], "reopened")
        # A reopened period admits corrections only.
        refused_trade = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 100},
                      {"account_id": chart["revenue"], "amount_minor": -100}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "trade", "description": "trade",
            "idempotency_key": "j-after-reopen", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused_trade.status_code, 409, refused_trade.text)

    def test_an_export_needs_a_closed_period(self):
        """An export of an open month is a figure that changes after it was filed."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        self.journal(tenant_id, entity, chart, amount=3000)
        refused = self.client.post("/ledger/exports", json={
            "legal_entity_id": entity, "period_key": period_of(),
            "target_system": "acme.books", "target_ref": "batch-1",
            "currency": "JOD", "idempotency_key": "e-1", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.close_period(tenant_id, entity, period_of())
        exported = self.client.post("/ledger/exports", json={
            "legal_entity_id": entity, "period_key": period_of(),
            "target_system": "acme.books", "target_ref": "batch-1",
            "currency": "JOD", "idempotency_key": "e-1", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(exported.status_code, 201, exported.text)
        self.assertEqual(exported.json()["debit_total_minor"], 3000)
        self.assertEqual(exported.json()["credit_total_minor"], 3000)


class WalletTests(LedgerApiTestCase):
    def test_a_debit_spends_promotional_value_before_cash(self):
        """**The caller does not choose.** One able to name the kind could spend the
        refundable balance first and leave the member holding value they can never get back."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        person_id = self.person(tenant_id)
        owner = self.headers(tenant_id)
        for kind, amount, counterpart in (
            ("cash", 5000, chart["cash"]),
            ("promotional", 1000, chart["contra"]),
        ):
            credited = self.client.post("/ledger/wallet-credits", json={
                "person_id": person_id, "value_kind": kind, "amount_minor": amount,
                "currency": "JOD", "legal_entity_id": entity,
                "counterpart_account_id": counterpart,
                "source_kind": "purchase" if kind == "cash" else "goodwill",
                "reason": f"{kind} in", "idempotency_key": f"w-{kind}",
                **self.correlation()}, headers=owner)
            self.assertEqual(credited.status_code, 201, credited.text)
        debited = self.client.post("/ledger/wallet-debits", json={
            "person_id": person_id, "amount_minor": 1200, "currency": "JOD",
            "legal_entity_id": entity, "counterpart_account_id": chart["revenue"],
            "reason": "a class", "idempotency_key": "w-spend", **self.correlation()},
            headers=owner)
        self.assertEqual(debited.status_code, 201, debited.text)
        self.assertEqual(debited.json()["spent"],
                         [{"value_kind": "promotional", "amount_minor": 1000},
                          {"value_kind": "cash", "amount_minor": 200}])
        statement = self.client.get(
            f"/ledger/wallets/{person_id}?currency=JOD", headers=owner)
        self.assertEqual(statement.status_code, 200, statement.text)
        self.assertEqual(statement.json()["balances"]["promotional"], 0)
        self.assertEqual(statement.json()["balances"]["cash"], 4800)
        self.assertEqual(statement.json()["refundable_minor"], 4800)
        self.assertEqual(statement.json()["spendable_minor"], 4800)

    def test_a_wallet_credit_posts_its_liability_and_the_caller_cannot_choose_it(self):
        """**The liability is derived from the value kind.** A caller able to name it could
        post a promotional credit into the refundable liability, which is the distinction
        paragraph 1686 calls a Critical Control."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        person_id = self.person(tenant_id)
        owner = self.headers(tenant_id)
        credited = self.client.post("/ledger/wallet-credits", json={
            "person_id": person_id, "value_kind": "promotional",
            "amount_minor": 2000, "currency": "JOD", "legal_entity_id": entity,
            "counterpart_account_id": chart["contra"], "source_kind": "promotion",
            "reason": "a summer offer", "idempotency_key": "w-1",
            **self.correlation()}, headers=owner)
        self.assertEqual(credited.status_code, 201, credited.text)
        journal = self.client.get(
            f"/ledger/journals/{credited.json()['journal_id']}", headers=owner).json()
        liabilities = [p["account_code"] for p in journal["postings"]
                       if p["account_kind"] == "wallet_promotional"]
        self.assertEqual(liabilities, ["WPROMO"])
        promo = self.client.get(
            f"/ledger/accounts/{chart['wallet_promo']}/balance", headers=owner).json()
        self.assertEqual(promo["balance_minor"], 2000)
        refundable = self.client.get(
            f"/ledger/accounts/{chart['wallet_cash']}/balance", headers=owner).json()
        self.assertEqual(refundable["balance_minor"], 0)

    def test_cash_wallet_value_cannot_be_given_an_expiry(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        person_id = self.person(tenant_id)
        refused = self.client.post("/ledger/wallet-credits", json={
            "person_id": person_id, "value_kind": "cash", "amount_minor": 1000,
            "currency": "JOD", "legal_entity_id": entity,
            "counterpart_account_id": chart["cash"], "source_kind": "purchase",
            "reason": "paid in", "expires_on": day(90),
            "idempotency_key": "w-expiring-cash", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("money the member paid in", refused.text)

    def test_a_debit_beyond_the_balance_is_refused(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        person_id = self.person(tenant_id)
        owner = self.headers(tenant_id)
        self.client.post("/ledger/wallet-credits", json={
            "person_id": person_id, "value_kind": "cash", "amount_minor": 500,
            "currency": "JOD", "legal_entity_id": entity,
            "counterpart_account_id": chart["cash"], "source_kind": "purchase",
            "reason": "paid in", "idempotency_key": "w-1", **self.correlation()},
            headers=owner)
        refused = self.client.post("/ledger/wallet-debits", json={
            "person_id": person_id, "amount_minor": 600, "currency": "JOD",
            "legal_entity_id": entity, "counterpart_account_id": chart["revenue"],
            "reason": "too much", "idempotency_key": "w-2", **self.correlation()},
            headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("holds 500", refused.text)

    def test_a_wallet_credit_is_idempotent_on_its_key(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        person_id = self.person(tenant_id)
        owner = self.headers(tenant_id)
        body = {"person_id": person_id, "value_kind": "cash", "amount_minor": 500,
                "currency": "JOD", "legal_entity_id": entity,
                "counterpart_account_id": chart["cash"], "source_kind": "purchase",
                "reason": "paid in", "idempotency_key": "w-same"}
        first = self.client.post("/ledger/wallet-credits",
                                 json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 201, first.text)
        again = self.client.post("/ledger/wallet-credits",
                                 json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        statement = self.client.get(
            f"/ledger/wallets/{person_id}?currency=JOD", headers=owner).json()
        self.assertEqual(statement["balances"]["cash"], 500)


class RecognitionTests(LedgerApiTestCase):
    def test_a_prepaid_year_is_not_day_one_revenue(self):
        """Paragraph 1695, end to end: the cash lands in a liability and the schedule moves it
        across as the service is delivered."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        self.unearned_held(tenant_id, entity, chart, 120000)
        opened = self.client.post("/ledger/recognition-schedules", json={
            "legal_entity_id": entity, "source_kind": "manual",
            "source_ref": "a prepaid year", "basis": "straight_line",
            "total_minor": 120000, "currency": "JOD",
            "unearned_account_id": chart["unearned"],
            "revenue_account_id": chart["revenue"],
            "starts_on": day(-30), "ends_on": day(334), **self.correlation()},
            headers=owner)
        self.assertEqual(opened.status_code, 201, opened.text)
        schedule_id = str(opened.json()["schedule_id"])
        posted = self.client.post(
            f"/ledger/recognition-schedules/{schedule_id}/post", json={
                "idempotency_key": "r-1", **self.correlation()}, headers=owner)
        self.assertEqual(posted.status_code, 200, posted.text)
        self.assertTrue(posted.json()["posted"])
        # Thirty-one days of a 365-day year, not the whole thing.
        self.assertGreater(posted.json()["amount_minor"], 0)
        self.assertLess(posted.json()["amount_minor"], 120000 // 10)
        self.assertGreater(posted.json()["remaining_minor"], 100000)

    def test_recognition_is_cumulative_so_a_second_run_posts_nothing(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        self.unearned_held(tenant_id, entity, chart, 120000)
        opened = self.client.post("/ledger/recognition-schedules", json={
            "legal_entity_id": entity, "source_kind": "manual", "source_ref": "a year",
            "basis": "straight_line", "total_minor": 120000, "currency": "JOD",
            "unearned_account_id": chart["unearned"],
            "revenue_account_id": chart["revenue"],
            "starts_on": day(-30), "ends_on": day(334), **self.correlation()},
            headers=owner)
        schedule_id = str(opened.json()["schedule_id"])
        first = self.client.post(
            f"/ledger/recognition-schedules/{schedule_id}/post", json={
                "idempotency_key": "r-1", **self.correlation()}, headers=owner)
        again = self.client.post(
            f"/ledger/recognition-schedules/{schedule_id}/post", json={
                "idempotency_key": "r-2", **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertFalse(again.json()["posted"])
        self.assertEqual(again.json()["amount_minor"], 0)
        self.assertEqual(again.json()["recognised_total_minor"],
                         first.json()["amount_minor"])

    def test_a_schedule_recognising_between_the_wrong_kinds_of_account_is_refused(self):
        """A lookup that proves an account exists does not authorise what you do next: a
        schedule moving money from one revenue account to another recognises nothing."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        refused = self.client.post("/ledger/recognition-schedules", json={
            "legal_entity_id": entity, "source_kind": "manual", "source_ref": "wrong",
            "basis": "immediate", "total_minor": 1000, "currency": "JOD",
            "unearned_account_id": chart["cash"],
            "revenue_account_id": chart["revenue"], **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("unearned_revenue", refused.text)

    def test_a_pack_earns_on_delivery_and_completes_when_it_is_used_up(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        self.unearned_held(tenant_id, entity, chart, 9000)
        opened = self.client.post("/ledger/recognition-schedules", json={
            "legal_entity_id": entity, "source_kind": "manual", "source_ref": "a pack",
            "basis": "on_delivery", "total_minor": 9000, "currency": "JOD",
            "units_total": 3, "unearned_account_id": chart["unearned"],
            "revenue_account_id": chart["revenue"], **self.correlation()},
            headers=owner)
        schedule_id = str(opened.json()["schedule_id"])
        one = self.client.post(
            f"/ledger/recognition-schedules/{schedule_id}/post", json={
                "units_delivered": 1, "idempotency_key": "p-1", **self.correlation()},
            headers=owner)
        self.assertEqual(one.json()["amount_minor"], 3000)
        all_three = self.client.post(
            f"/ledger/recognition-schedules/{schedule_id}/post", json={
                "units_delivered": 3, "idempotency_key": "p-2", **self.correlation()},
            headers=owner)
        self.assertEqual(all_three.json()["amount_minor"], 6000)
        self.assertEqual(all_three.json()["status"], "complete")
        self.assertEqual(all_three.json()["remaining_minor"], 0)

    def test_what_is_due_is_a_read_with_no_side_effect(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        self.unearned_held(tenant_id, entity, chart, 120000)
        self.client.post("/ledger/recognition-schedules", json={
            "legal_entity_id": entity, "source_kind": "manual", "source_ref": "a year",
            "basis": "straight_line", "total_minor": 120000, "currency": "JOD",
            "unearned_account_id": chart["unearned"],
            "revenue_account_id": chart["revenue"],
            "starts_on": day(-30), "ends_on": day(334), **self.correlation()},
            headers=owner)
        due = self.client.get("/ledger/recognition-due", headers=owner)
        self.assertEqual(due.status_code, 200, due.text)
        self.assertEqual(due.json()["count"], 1)
        self.assertGreater(due.json()["due"][0]["amount_due_minor"], 0)
        # Twice, because a read posts nothing.
        again = self.client.get("/ledger/recognition-due", headers=owner)
        self.assertEqual(again.json()["due"][0]["amount_due_minor"],
                         due.json()["due"][0]["amount_due_minor"])


class SettlementTests(LedgerApiTestCase):
    def test_an_unmatched_line_opens_a_case_and_a_fee_does_not(self):
        """**Nothing is absorbed silently.** A case is the unanswered question; a fee is the
        provider's own movement and a case for each would bury the lines that need somebody."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        self.chart(tenant_id)
        owner = self.headers(tenant_id)
        imported = self.client.post("/ledger/settlements", json={
            "legal_entity_id": entity, "provider_key": "acme.payments",
            "provider_batch_ref": "2026-11-14", "settled_on": day(0),
            "currency": "JOD", "claimed_total_minor": 950,
            "lines": [
                {"line_kind": "payment", "provider_ref": "ch_unknown",
                 "amount_minor": 1000},
                {"line_kind": "fee", "provider_ref": "fee_1", "amount_minor": -50},
            ],
            "idempotency_key": "s-1", **self.correlation()}, headers=owner)
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertEqual(imported.json()["outcomes"],
                         {"unmatched": 1, "not_expected": 1})
        self.assertEqual(len(imported.json()["cases_opened"]), 1)
        cases = self.client.get("/ledger/reconciliation-cases", headers=owner)
        self.assertEqual(cases.status_code, 200, cases.text)
        self.assertEqual(cases.json()["count"], 1)
        self.assertEqual(cases.json()["cases"][0]["case_kind"], "settlement_line")

    def test_a_file_whose_header_disagrees_with_its_body_opens_a_case(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        self.chart(tenant_id)
        owner = self.headers(tenant_id)
        imported = self.client.post("/ledger/settlements", json={
            "legal_entity_id": entity, "provider_key": "acme.payments",
            "provider_batch_ref": "2026-11-15", "settled_on": day(0),
            "currency": "JOD", "claimed_total_minor": 9999,
            "lines": [{"line_kind": "fee", "provider_ref": "fee_1",
                       "amount_minor": -50}],
            "idempotency_key": "s-2", **self.correlation()}, headers=owner)
        self.assertEqual(imported.status_code, 201, imported.text)
        cases = self.client.get("/ledger/reconciliation-cases", headers=owner).json()
        kinds = {case["case_kind"] for case in cases["cases"]}
        self.assertIn("settlement_total", kinds)

    def test_a_provider_batch_is_imported_once(self):
        """A file imported twice doubles every posting it makes, and a provider re-sending a
        batch is the ordinary case rather than an edge."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        self.chart(tenant_id)
        owner = self.headers(tenant_id)
        body = {"legal_entity_id": entity, "provider_key": "acme.payments",
                "provider_batch_ref": "same-batch", "settled_on": day(0),
                "currency": "JOD", "claimed_total_minor": -50,
                "lines": [{"line_kind": "fee", "provider_ref": "fee_1",
                           "amount_minor": -50}]}
        first = self.client.post("/ledger/settlements", json={
            **body, "idempotency_key": "s-a", **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 201, first.text)
        again = self.client.post("/ledger/settlements", json={
            **body, "idempotency_key": "s-b", **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("already_been_imported", again.text)

    def test_a_case_is_worked_and_written_off_with_a_name_on_it(self):
        """`written_off` is a decision about money and it says so in the status."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        self.chart(tenant_id)
        owner = self.headers(tenant_id)
        imported = self.client.post("/ledger/settlements", json={
            "legal_entity_id": entity, "provider_key": "acme.payments",
            "provider_batch_ref": "to-resolve", "settled_on": day(0),
            "currency": "JOD", "claimed_total_minor": 1000,
            "lines": [{"line_kind": "payment", "provider_ref": "ch_nothing",
                       "amount_minor": 1000}],
            "idempotency_key": "s-3", **self.correlation()}, headers=owner)
        case_id = imported.json()["cases_opened"][0]
        looking = self.client.post(
            f"/ledger/reconciliation-cases/{case_id}/resolve", json={
                "outcome": "investigating", "resolution": "asked the provider",
                **self.correlation()}, headers=owner)
        self.assertEqual(looking.status_code, 200, looking.text)
        written_off = self.client.post(
            f"/ledger/reconciliation-cases/{case_id}/resolve", json={
                "outcome": "written_off",
                "resolution": "the provider cannot trace it; under the threshold",
                **self.correlation()}, headers=owner)
        self.assertEqual(written_off.status_code, 200, written_off.text)
        self.assertEqual(written_off.json()["status"], "written_off")
        self.assertEqual(
            self.client.get("/ledger/reconciliation-cases",
                            headers=owner).json()["count"], 0)
        decided = self.client.post(
            f"/ledger/reconciliation-cases/{case_id}/resolve", json={
                "outcome": "resolved", "resolution": "changed my mind",
                **self.correlation()}, headers=owner)
        self.assertEqual(decided.status_code, 409, decided.text)


class CashTests(LedgerApiTestCase):
    def test_a_till_that_does_not_balance_posts_to_suspense_and_opens_a_case(self):
        """**Neither half is optional.** Posting it keeps the ledger's cash balance equal to
        the money that is actually there; the case is the question nobody has answered."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        location_id = self.location(tenant_id)
        owner = self.headers(tenant_id)
        drawer = self.drawer(tenant_id, entity, location_id, float_minor=5000)
        refused = self.client.post(
            f"/ledger/cash-sessions/{drawer['session_id']}/close", json={
                "counted_minor": 4800, "legal_entity_id": entity,
                "suspense_account_id": chart["suspense"], **self.correlation()},
            headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("-200", refused.text)
        closed = self.client.post(
            f"/ledger/cash-sessions/{drawer['session_id']}/close", json={
                "counted_minor": 4800, "legal_entity_id": entity,
                "suspense_account_id": chart["suspense"],
                "variance_reason": "a member was given change twice",
                **self.correlation()}, headers=owner)
        self.assertEqual(closed.status_code, 200, closed.text)
        self.assertEqual(closed.json()["expected_minor"], 5000)
        self.assertEqual(closed.json()["variance_minor"], -200)
        self.assertIsNotNone(closed.json()["case_id"])
        suspense = self.client.get(
            f"/ledger/accounts/{chart['suspense']}/balance", headers=owner).json()
        self.assertEqual(suspense["balance_minor"], 200)
        # And the drawer now reads what was counted, which is the point of posting it.
        till = self.client.get(
            f"/ledger/accounts/{drawer['till']}/balance", headers=owner).json()
        self.assertEqual(till["balance_minor"], 4800)

    def test_the_expected_count_comes_from_the_ledger_and_not_from_the_caller(self):
        """A drawer that took 1500 in sales is expected to hold its float plus the sales. No
        field on either body can lower that figure, which is what makes the variance mean
        something."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        location_id = self.location(tenant_id)
        owner = self.headers(tenant_id)
        drawer = self.drawer(tenant_id, entity, location_id, float_minor=5000)
        self.journal(tenant_id, entity, {"cash": drawer["till"],
                                         "revenue": chart["revenue"]}, amount=1500)
        closed = self.client.post(
            f"/ledger/cash-sessions/{drawer['session_id']}/close", json={
                "counted_minor": 6500, "legal_entity_id": entity,
                "suspense_account_id": chart["suspense"], **self.correlation()},
            headers=owner)
        self.assertEqual(closed.status_code, 200, closed.text)
        self.assertEqual(closed.json()["expected_minor"], 6500)
        self.assertEqual(closed.json()["variance_minor"], 0)
        self.assertIsNone(closed.json()["case_id"])

    def test_a_float_that_names_no_source_is_refused(self):
        """**An unposted float is cash the ledger does not know about**, and it made the
        drawer's own account go negative by exactly the float when the takings were banked."""
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        till = self.account(tenant_id, "TILL1", "cash")
        refused = self.client.post("/ledger/cash-sessions", json={
            "location_id": location_id, "cash_account_id": till,
            "drawer_label": "front", "currency": "JOD",
            "opening_float_minor": 5000, "idempotency_key": "t-1",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("names_the_account_it_came_from", refused.text)

    def test_a_float_does_not_come_from_the_drawer_it_opens(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        location_id = self.location(tenant_id)
        till = self.account(tenant_id, "TILL1", "cash")
        refused = self.client.post("/ledger/cash-sessions", json={
            "location_id": location_id, "cash_account_id": till,
            "drawer_label": "front", "currency": "JOD",
            "opening_float_minor": 5000, "float_source_account_id": till,
            "legal_entity_id": entity, "idempotency_key": "t-1",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("from_the_drawer_it_opens", refused.text)

    def test_one_open_session_per_drawer_is_refused_with_a_sentence(self):
        """**The unique index cannot be the refusal.** An insert names one index in its
        `ON CONFLICT` and this one already names the idempotency key, so the second open
        raised an uncaught violation and answered 500 while telling the caller to try again."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        location_id = self.location(tenant_id)
        owner = self.headers(tenant_id)
        self.drawer(tenant_id, entity, location_id, float_minor=0)
        second = self.account(tenant_id, "TILL2", "cash")
        again = self.client.post("/ledger/cash-sessions", json={
            "location_id": location_id, "cash_account_id": second,
            "drawer_label": "front", "currency": "JOD",
            "opening_float_minor": 0, "idempotency_key": "t-second",
            **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)
        self.assertIn("already_has_an_open_session", again.text)

    def test_opening_the_same_session_twice_is_idempotent(self):
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        owner = self.headers(tenant_id)
        till = self.account(tenant_id, "TILL1", "cash")
        body = {"location_id": location_id, "cash_account_id": till,
                "drawer_label": "front", "currency": "JOD",
                "opening_float_minor": 0, "idempotency_key": "t-same"}
        first = self.client.post("/ledger/cash-sessions",
                                 json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 201, first.text)
        again = self.client.post("/ledger/cash-sessions",
                                 json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["session_id"], first.json()["session_id"])

    def test_a_till_session_needs_a_cash_account(self):
        tenant_id = self.tenant()
        location_id = self.location(tenant_id)
        chart = self.chart(tenant_id)
        refused = self.client.post("/ledger/cash-sessions", json={
            "location_id": location_id, "cash_account_id": chart["revenue"],
            "drawer_label": "front", "currency": "JOD",
            "opening_float_minor": 0, "idempotency_key": "t-1",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("needs a cash account", refused.text)

    def test_a_deposit_posts_on_the_way_out_and_reconciles_when_the_bank_answers(self):
        """The money has left the premises, so the till no longer holds it -- a ledger that
        waited for the bank would show cash in a drawer that is empty."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        location_id = self.location(tenant_id)
        owner = self.headers(tenant_id)
        drawer = self.drawer(tenant_id, entity, location_id, float_minor=5000)
        self.client.post(f"/ledger/cash-sessions/{drawer['session_id']}/close", json={
            "counted_minor": 5000, "legal_entity_id": entity,
            "suspense_account_id": chart["suspense"], **self.correlation()},
            headers=owner)
        banked = self.client.post("/ledger/deposits", json={
            "location_id": location_id, "cash_account_id": drawer["till"],
            "bank_account_id": chart["bank"], "currency": "JOD",
            "declared_minor": 5000, "deposited_on": day(0),
            "session_ids": [drawer["session_id"]], "legal_entity_id": entity,
            "idempotency_key": "d-1", **self.correlation()}, headers=owner)
        self.assertEqual(banked.status_code, 201, banked.text)
        self.assertIsNone(banked.json()["case_id"])
        # **The drawer is empty and the bank holds it.** With the float merely declared on the
        # session row rather than posted, this read was -5000: the ledger thought the drawer
        # owed money it had never been given.
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{drawer['till']}/balance",
                            headers=owner).json()["balance_minor"], 0)
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{chart['bank']}/balance",
                            headers=owner).json()["balance_minor"], 5000)
        short = self.client.post(
            f"/ledger/deposits/{banked.json()['deposit_id']}/confirm", json={
                "credited_minor": 4950, "credited_on": day(2),
                "legal_entity_id": entity,
                "suspense_account_id": chart["suspense"],
                "bank_reference": "DEP-99", **self.correlation()}, headers=owner)
        self.assertEqual(short.status_code, 200, short.text)
        self.assertEqual(short.json()["status"], "short")
        self.assertEqual(short.json()["variance_minor"], -50)
        self.assertIsNotNone(short.json()["case_id"])

    def test_a_deposit_banks_closed_sessions_in_its_own_currency(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        location_id = self.location(tenant_id)
        owner = self.headers(tenant_id)
        drawer = self.drawer(tenant_id, entity, location_id, float_minor=5000)
        refused = self.client.post("/ledger/deposits", json={
            "location_id": location_id, "cash_account_id": drawer["till"],
            "bank_account_id": chart["bank"], "currency": "JOD",
            "declared_minor": 5000, "deposited_on": day(0),
            "session_ids": [drawer["session_id"]],
            "legal_entity_id": entity, "idempotency_key": "d-1",
            **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("closed sessions", refused.text)


class BridgeTests(LedgerApiTestCase):
    """**The wiring is the design.** An invoice without its receivable is a balance the ledger
    does not know about, and the only way to mean "together" is MOD-017's own transaction."""

    def test_an_issued_invoice_posts_its_receivable_in_the_same_transaction(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        self.chart(tenant_id)
        owner = self.headers(tenant_id)
        person_id = self.person(tenant_id)
        billing = self.billing(tenant_id, entity, person_id)
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Monthly membership", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 1600}],
            "issued_on": day(0), "due_on": day(14), "jurisdiction": "JO",
            "idempotency_key": "inv-1", **self.correlation()}, headers=owner)
        self.assertEqual(issued.status_code, 201, issued.text)
        self.assertTrue(issued.json()["posted"])
        journal = self.client.get(
            f"/ledger/journals/{issued.json()['ledger_journal_id']}",
            headers=owner).json()
        by_kind = {p["account_kind"]: p["amount_minor"] for p in journal["postings"]}
        self.assertEqual(by_kind["receivable"], 5220)
        self.assertEqual(by_kind["revenue"], -4500)
        self.assertEqual(by_kind["tax_payable"], -720)
        self.assertEqual(
            {p["subject_person_id"] for p in journal["postings"]}, {person_id})

    def test_a_prepaid_invoice_credits_unearned_revenue_rather_than_revenue(self):
        """Paragraph 1695 through the bridge: the caller says how much has not been delivered,
        because only the caller knows what was sold."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        self.chart(tenant_id)
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, entity, self.person(tenant_id))
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "A prepaid year", "quantity": 1,
                       "unit_net_minor": 120000, "tax_rate_bp": 0}],
            "issued_on": day(0), "due_on": day(14), "jurisdiction": "JO",
            "unearned_minor": 120000, "idempotency_key": "inv-prepaid",
            **self.correlation()}, headers=owner)
        self.assertEqual(issued.status_code, 201, issued.text)
        journal = self.client.get(
            f"/ledger/journals/{issued.json()['ledger_journal_id']}",
            headers=owner).json()
        by_kind = {p["account_kind"]: p["amount_minor"] for p in journal["postings"]}
        self.assertEqual(by_kind["unearned_revenue"], -120000)
        self.assertNotIn("revenue", by_kind)

    def test_a_payment_moves_the_receivable_into_provider_clearing(self):
        """Which is the account COM-04-R04's settlement import reconciles against, and it only
        means anything if payments land there rather than going straight to the bank."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, entity, self.person(tenant_id))
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Membership", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 1600}],
            "issued_on": day(0), "due_on": day(14), "jurisdiction": "JO",
            "idempotency_key": "inv-1", **self.correlation()}, headers=owner).json()
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": issued["invoice_id"], "amount_minor": issued["gross_minor"],
            "method": "card", "provider_key": "acme.payments",
            "idempotency_key": "pi-1", **self.correlation()}, headers=owner)
        self.assertEqual(intent.status_code, 201, intent.text)
        settled = self.client.post(
            f"/finance/payment-intents/{intent.json()['intent_id']}/settle",
            json={"outcome": "succeeded", "provider_ref": "ch_1",
                  **self.correlation()}, headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        receivable = self.client.get(
            f"/ledger/accounts/{chart['receivable']}/balance", headers=owner).json()
        self.assertEqual(receivable["balance_minor"], 0)
        clearing = self.client.get(
            f"/ledger/accounts/{chart['clearing']}/balance", headers=owner).json()
        self.assertEqual(clearing["balance_minor"], 5220)

    def test_a_cash_payment_names_its_till_and_posts_there(self):
        """**The till is per location, so only whatever took the money knows which one.**

        The first version computed the posting's verdict and discarded it, and the route had
        no field for the account at all -- so a cash payment was recorded, silently not
        posted, and the response read as an ordinary success.
        """
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        till = self.account(tenant_id, "TILL1", "cash")
        billing = self.billing(tenant_id, entity, self.person(tenant_id))
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Day pass", "quantity": 1,
                       "unit_net_minor": 1000, "tax_rate_bp": 0}],
            "issued_on": day(0), "due_on": day(0), "jurisdiction": "JO",
            "idempotency_key": "inv-1", **self.correlation()}, headers=owner).json()
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": issued["invoice_id"], "amount_minor": 1000,
            "method": "cash", "provider_key": "till",
            "idempotency_key": "pi-1", **self.correlation()}, headers=owner)
        self.assertEqual(intent.status_code, 201, intent.text)
        intent_id = str(intent.json()["intent_id"])
        # Without the till, the payment is recorded and the caller is told what was skipped.
        blind = self.client.post(
            f"/finance/payment-intents/{intent_id}/settle",
            json={"outcome": "succeeded", **self.correlation()}, headers=owner)
        self.assertEqual(blind.status_code, 200, blind.text)
        self.assertFalse(blind.json()["posted"])
        self.assertIn("till's account", blind.json()["ledger_skipped_because"])
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{till}/balance",
                            headers=owner).json()["balance_minor"], 0)
        # With it, the money lands in that drawer rather than in provider clearing.
        second = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "amount_minor": 2500, "method": "cash", "provider_key": "till",
            "idempotency_key": "pi-2", **self.correlation()}, headers=owner)
        settled = self.client.post(
            f"/finance/payment-intents/{second.json()['intent_id']}/settle",
            json={"outcome": "succeeded", "cash_account_id": till,
                  **self.correlation()}, headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        self.assertTrue(settled.json()["posted"])
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{till}/balance",
                            headers=owner).json()["balance_minor"], 2500)
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{chart['clearing']}/balance",
                            headers=owner).json()["balance_minor"], 0)

    def test_a_settlement_matches_the_payment_the_bridge_recorded(self):
        """End to end: the provider reference MOD-017 stored is what MOD-018's matcher finds."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        self.chart(tenant_id)
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, entity, self.person(tenant_id))
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Membership", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 1600}],
            "issued_on": day(0), "due_on": day(14), "jurisdiction": "JO",
            "idempotency_key": "inv-1", **self.correlation()}, headers=owner).json()
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": issued["invoice_id"], "amount_minor": issued["gross_minor"],
            "method": "card", "provider_key": "acme.payments",
            "idempotency_key": "pi-1", **self.correlation()}, headers=owner)
        self.client.post(
            f"/finance/payment-intents/{intent.json()['intent_id']}/settle",
            json={"outcome": "succeeded", "provider_ref": "ch_settled",
                  **self.correlation()}, headers=owner)
        imported = self.client.post("/ledger/settlements", json={
            "legal_entity_id": entity, "provider_key": "acme.payments",
            "provider_batch_ref": "matched-batch", "settled_on": day(0),
            "currency": "JOD", "claimed_total_minor": 5220,
            "lines": [{"line_kind": "payment", "provider_ref": "ch_settled",
                       "amount_minor": 5220}],
            "idempotency_key": "s-1", **self.correlation()}, headers=owner)
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertEqual(imported.json()["outcomes"], {"matched": 1})
        self.assertEqual(imported.json()["cases_opened"], [])

    def test_a_tenant_with_no_chart_still_gets_its_invoice_and_is_told_why(self):
        """**The chart is tenant configuration**, and a tenant mid-setup must not find its
        till has stopped working. What makes the skip honest rather than silent is that the
        caller is told."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, entity, self.person(tenant_id))
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Membership", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 1600}],
            "issued_on": day(0), "due_on": day(14), "jurisdiction": "JO",
            "idempotency_key": "inv-1", **self.correlation()}, headers=owner)
        self.assertEqual(issued.status_code, 201, issued.text)
        self.assertFalse(issued.json()["posted"])
        self.assertIn("no ledger chart", issued.json()["ledger_skipped_because"])


class PermissionClassTests(LedgerApiTestCase):
    def test_reading_the_ledger_is_routine_and_posting_is_not(self):
        """A trial balance is how somebody finds out that something is wrong, and a read that
        needed a step-up is a read nobody does until the month-end panic."""
        from app.authorization import catalog as authz_catalog
        self.assertEqual(authz_catalog.action_class("finance.ledger.read"), "routine")
        for financial in ("finance.ledger.post", "finance.ledger.correct",
                          "finance.ledger.chart", "finance.wallet.credit",
                          "finance.wallet.debit", "finance.period.close",
                          "finance.period.reopen", "finance.settlement.import",
                          "finance.recognition.manage", "finance.export.run",
                          "finance.cash.deposit"):
            self.assertEqual(authz_catalog.action_class(financial), "financial",
                             financial)
        # A front desk opens and closes a drawer every shift; a step-up per close is one
        # nobody completes. What bounds it is that the variance posts to suspense and opens a
        # case rather than disappearing.
        self.assertEqual(authz_catalog.action_class("finance.cash.session"), "routine")

    def test_posting_a_journal_needs_a_stepped_up_session(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        weak = self.headers(tenant_id, self.grant(tenant_id, ["finance.ledger.post"]))
        refused = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 100},
                      {"account_id": chart["revenue"], "amount_minor": -100}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "weak", "description": "weak", "idempotency_key": "j-weak",
            **self.correlation()}, headers=weak)
        self.assertEqual(refused.status_code, 403, refused.text)

    def test_reading_a_trial_balance_does_not(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        reader = self.headers(tenant_id, self.grant(tenant_id, ["finance.ledger.read"]))
        read = self.client.get(
            f"/ledger/trial-balance?legal_entity_id={entity}&currency=JOD",
            headers=reader)
        self.assertEqual(read.status_code, 200, read.text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class ReviewRegressionTests(LedgerApiTestCase):
    """One test per blocking finding from MOD-018's three reviews.

    Named for the attack rather than the fix, because a fix's name tells you nothing when the
    test fails two years from now. Every one of these passed a green 103-test suite.
    """

    def test_beginning_the_month_end_close_does_not_stop_the_till(self):
        """**The worst of the three reviews' findings.** `closing` is a state an accountant
        enters deliberately, and the bridge runs inside MOD-017's transaction -- so a refusal
        rolled the business write back: no invoice could be issued, no serial allocated, and a
        card the provider had already charged could not be recorded. A close begun on the 28th
        shut the till for four days.
        """
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, entity, self.person(tenant_id))
        self.journal(tenant_id, entity, chart)
        moved = self.client.post("/ledger/periods/close", json={
            "legal_entity_id": entity, "period_key": period_of(),
            "target": "closing", **self.correlation()}, headers=owner)
        self.assertEqual(moved.status_code, 200, moved.text)
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Membership", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 0}],
            "issued_on": day(0), "due_on": day(14), "jurisdiction": "JO",
            "idempotency_key": "inv-1", **self.correlation()}, headers=owner)
        self.assertEqual(issued.status_code, 201, issued.text)
        self.assertTrue(issued.json()["posted"])
        # It walked forward: the document keeps its own date and the journal says when it was
        # posted, which is what an accountant means by "it goes in the next open period".
        journal = self.client.get(
            f"/ledger/journals/{issued.json()['ledger_journal_id']}",
            headers=owner).json()
        self.assertNotEqual(journal["period_key"], period_of())
        intent = self.client.post("/finance/payment-intents", json={
            "billing_account_id": billing["billing_account_id"],
            "invoice_id": issued.json()["invoice_id"],
            "amount_minor": issued.json()["gross_minor"], "method": "card",
            "provider_key": "acme.payments", "idempotency_key": "pi-1",
            **self.correlation()}, headers=owner)
        settled = self.client.post(
            f"/finance/payment-intents/{intent.json()['intent_id']}/settle",
            json={"outcome": "succeeded", "provider_ref": "ch_1",
                  **self.correlation()}, headers=owner)
        self.assertEqual(settled.status_code, 200, settled.text)
        self.assertTrue(settled.json()["posted"])
        # A journal posted *by hand* still does not walk: somebody is there to read the
        # refusal and choose.
        refused = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 100},
                      {"account_id": chart["revenue"], "amount_minor": -100}],
            "posted_on": day(0), "currency": "JOD", "source_kind": "manual",
            "source_ref": "by hand", "description": "by hand",
            "idempotency_key": "j-hand", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_a_till_close_cannot_post_to_any_account_the_caller_names(self):
        """**The module's only routine AAL-1 permission was an unrestricted posting route.**
        `suspense_account_id` was unchecked, so a reviewer cleared a 10,000.00 receivable with
        it -- while the identical movement through `POST /ledger/journals` is refused, because
        that permission is financial and needs a step-up.
        """
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        location_id = self.location(tenant_id)
        till = self.headers(tenant_id, self.grant(tenant_id, ["finance.cash.session"]))
        drawer = self.drawer(tenant_id, entity, location_id, float_minor=0)
        for named in ("receivable", "revenue", "bank"):
            refused = self.client.post(
                f"/ledger/cash-sessions/{drawer['session_id']}/close", json={
                    "counted_minor": 500, "legal_entity_id": entity,
                    "suspense_account_id": chart[named],
                    "variance_reason": "found it", **self.correlation()},
                headers=till)
            self.assertEqual(refused.status_code, 409, refused.text)
            self.assertIn("needs suspense", refused.text)
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{chart['receivable']}/balance",
                            headers=self.headers(tenant_id)).json()["balance_minor"], 0)

    def test_a_drawer_belongs_to_the_location_it_is_opened_at(self):
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        here = self.location(tenant_id)
        owner = self.headers(tenant_id)
        elsewhere = self.account(
            tenant_id, "TILL-AIR", "cash", location_id=here,
            brand_id=self.brands[here])
        other = self.location(tenant_id)
        refused = self.client.post("/ledger/cash-sessions", json={
            "location_id": other, "cash_account_id": elsewhere,
            "drawer_label": "front", "currency": "JOD", "opening_float_minor": 0,
            "legal_entity_id": entity, "idempotency_key": "t-1",
            **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("another location", refused.text)

    def test_a_future_dated_journal_does_not_make_a_short_till_balance(self):
        """100.00 left the drawer and the close reported `variance_minor: 0`: nothing posted
        to suspense, no written reason demanded, no case. `_expected_in_drawer` summed the
        account's postings with no date bound while `account_balance` beside it had one."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        location_id = self.location(tenant_id)
        owner = self.headers(tenant_id)
        drawer = self.drawer(tenant_id, entity, location_id, float_minor=0)
        self.journal(tenant_id, entity, {"cash": drawer["till"],
                                         "revenue": chart["revenue"]}, amount=30000)
        # A journal dated well ahead, moving 100.00 out of the till.
        ahead = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["bank"], "amount_minor": 10000},
                      {"account_id": drawer["till"], "amount_minor": -10000}],
            "posted_on": day(40), "currency": "JOD", "source_kind": "manual",
            "source_ref": "a transfer booked ahead",
            "description": "a transfer booked ahead",
            "idempotency_key": "j-ahead", **self.correlation()}, headers=owner)
        self.assertEqual(ahead.status_code, 201, ahead.text)
        refused = self.client.post(
            f"/ledger/cash-sessions/{drawer['session_id']}/close", json={
                "counted_minor": 20000, "legal_entity_id": entity,
                "suspense_account_id": chart["suspense"], **self.correlation()},
            headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("-10000", refused.text)

    def test_one_till_session_is_banked_once(self):
        """Cash that exists once was banked twice: 400.00 in the bank, minus 200.00 in a
        drawer, no case -- and the clean route to pocketing the notes, since the negative
        drawer reads as a banking error."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        location_id = self.location(tenant_id)
        owner = self.headers(tenant_id)
        drawer = self.drawer(tenant_id, entity, location_id, float_minor=20000)
        self.client.post(f"/ledger/cash-sessions/{drawer['session_id']}/close", json={
            "counted_minor": 20000, "legal_entity_id": entity,
            "suspense_account_id": chart["suspense"], **self.correlation()},
            headers=owner)
        body = {"location_id": location_id, "cash_account_id": drawer["till"],
                "bank_account_id": chart["bank"], "currency": "JOD",
                "declared_minor": 20000, "deposited_on": day(0),
                "session_ids": [drawer["session_id"]], "legal_entity_id": entity}
        first = self.client.post("/ledger/deposits", json={
            **body, "idempotency_key": "d-1", **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 201, first.text)
        again = self.client.post("/ledger/deposits", json={
            **body, "idempotency_key": "d-2", **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{chart['bank']}/balance",
                            headers=owner).json()["balance_minor"], 20000)
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{drawer['till']}/balance",
                            headers=owner).json()["balance_minor"], 0)

    def test_a_trial_balance_is_for_one_entity_as_of_one_date(self):
        """Both predicates sat in the `ON` clause of a `LEFT JOIN`, where a posting whose
        journal matched neither survived with NULL journal columns and was summed anyway: a
        per-entity trial balance carried the other entity's journals, and a period-end one
        carried journals posted after the date asked for."""
        tenant_id = self.tenant()
        first = self.legal_entity(tenant_id)
        second = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        self.journal(tenant_id, second, chart, amount=90000)
        read = self.client.get(
            f"/ledger/trial-balance?legal_entity_id={first}&currency=JOD",
            headers=owner).json()
        self.assertEqual(read["debit_total_minor"], 0, read["lines"])
        self.journal(tenant_id, first, chart, amount=4000, posted_on=day(40))
        today_only = self.client.get(
            f"/ledger/trial-balance?legal_entity_id={first}&currency=JOD"
            f"&as_of={day(0)}", headers=owner).json()
        self.assertEqual(today_only["debit_total_minor"], 0)
        later = self.client.get(
            f"/ledger/trial-balance?legal_entity_id={first}&currency=JOD"
            f"&as_of={day(40)}", headers=owner).json()
        self.assertEqual(later["debit_total_minor"], 4000)
        self.assertTrue(later["balanced"])

    def test_a_bridged_posting_uses_its_own_entity_s_account(self):
        """`chart_for` filtered on neither the entity nor anything deterministic and filled a
        dict in row order, so a two-entity tenant's receivable landed in the *other* entity's
        account and which revenue account an invoice credited was the planner's choice."""
        tenant_id = self.tenant()
        mine = self.legal_entity(tenant_id)
        theirs = self.legal_entity(tenant_id)
        owner = self.headers(tenant_id)
        chart = self.chart(tenant_id)
        mine_ar = self.account(tenant_id, "AR-MINE", "receivable",
                               legal_entity_id=mine)
        self.account(tenant_id, "AR-THEIRS", "receivable", legal_entity_id=theirs)
        billing = self.billing(tenant_id, mine, self.person(tenant_id))
        issued = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Membership", "quantity": 1,
                       "unit_net_minor": 5000, "tax_rate_bp": 0}],
            "issued_on": day(0), "due_on": day(14), "jurisdiction": "JO",
            "idempotency_key": "inv-1", **self.correlation()}, headers=owner)
        self.assertEqual(issued.status_code, 201, issued.text)
        journal = self.client.get(
            f"/ledger/journals/{issued.json()['ledger_journal_id']}",
            headers=owner).json()
        codes = {p["account_code"] for p in journal["postings"]}
        self.assertIn("AR-MINE", codes)
        self.assertNotIn("AR-THEIRS", codes)
        self.assertNotIn(chart["receivable"],
                         {p["account_id"] for p in journal["postings"]})
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{mine_ar}/balance",
                            headers=owner).json()["balance_minor"], 5000)

    def test_a_reopened_period_can_be_closed_again(self):
        """The only edge out of `reopened` answered 500, so `/ledger/periods/reopen` -- the
        one act COM-04-R06 provides for correcting a filed month -- was a one-way door and the
        lock could never be re-applied."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        self.journal(tenant_id, entity, chart)
        self.close_period(tenant_id, entity, period_of())
        reopened = self.client.post("/ledger/periods/reopen", json={
            "legal_entity_id": entity, "period_key": period_of(),
            "reason": "an invoice was issued against the wrong entity",
            **self.correlation()}, headers=owner)
        self.assertEqual(reopened.status_code, 200, reopened.text)
        for target in ("closing", "closed"):
            moved = self.client.post("/ledger/periods/close", json={
                "legal_entity_id": entity, "period_key": period_of(),
                "target": target, **self.correlation()}, headers=owner)
            self.assertEqual(moved.status_code, 200, moved.text)
            self.assertEqual(moved.json()["status"], target)

    def test_an_out_of_range_date_is_refused_rather_than_answered_with_a_500(self):
        """`month_bounds` raises `LedgerError`, which is a `ValueError` and not the
        `ServiceError` the handler catches -- and this was the one of ten call sites that did
        not wrap it. A mistyped year on `/finance/invoices` answered Internal Server Error,
        and only for tenants that had set a chart up."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        billing = self.billing(tenant_id, entity, self.person(tenant_id))
        for bad in ("1999-12-31", "2101-01-01"):
            refused = self.client.post("/ledger/journals", json={
                "legal_entity_id": entity,
                "lines": [{"account_id": chart["cash"], "amount_minor": 100},
                          {"account_id": chart["revenue"], "amount_minor": -100}],
                "posted_on": bad, "currency": "JOD", "source_kind": "manual",
                "source_ref": "a mistyped year", "description": "a mistyped year",
                "idempotency_key": f"j-{bad}", **self.correlation()}, headers=owner)
            self.assertEqual(refused.status_code, 422, refused.text)
        invoiced = self.client.post("/finance/invoices", json={
            "billing_account_id": billing["billing_account_id"],
            "series_id": billing["series_id"],
            "lines": [{"description": "Membership", "quantity": 1,
                       "unit_net_minor": 4500, "tax_rate_bp": 0}],
            "issued_on": "1999-01-01", "due_on": "1999-01-14",
            "jurisdiction": "JO", "idempotency_key": "inv-old",
            **self.correlation()}, headers=owner)
        self.assertEqual(invoiced.status_code, 422, invoiced.text)

    def test_a_month_behind_a_filed_one_is_not_opened(self):
        """COM-04-R06's lock is per period *row*, and a month nobody posted into has no row
        and therefore cannot have been closed -- so a tenant whose books were filed had every
        earlier month wide open."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        self.journal(tenant_id, entity, chart)
        self.close_period(tenant_id, entity, period_of())
        refused = self.client.post("/ledger/journals", json={
            "legal_entity_id": entity,
            "lines": [{"account_id": chart["cash"], "amount_minor": 100},
                      {"account_id": chart["revenue"], "amount_minor": -100}],
            "posted_on": day(-200), "currency": "JOD", "source_kind": "manual",
            "source_ref": "last year", "description": "last year",
            "idempotency_key": "j-back", **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("never opened", refused.text)

    def test_a_wallet_counterpart_is_checked_for_what_it_is(self):
        """A promotional giveaway charged to `receivable` overstated the tenant's debtors by
        every credit ever issued, and a credit whose counterpart was the wallet liability
        itself created refundable member value with nothing on the balance sheet -- because
        `sum(amount_minor) = 0` is satisfied by +N and -N on one account."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        person_id = self.person(tenant_id)
        owner = self.headers(tenant_id)
        for named in ("receivable", "tax", "wallet_cash"):
            refused = self.client.post("/ledger/wallet-credits", json={
                "person_id": person_id, "value_kind": "promotional",
                "amount_minor": 50000, "currency": "JOD", "legal_entity_id": entity,
                "counterpart_account_id": chart[named], "source_kind": "goodwill",
                "reason": "a giveaway", "idempotency_key": f"w-{named}",
                **self.correlation()}, headers=owner)
            self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{chart['receivable']}/balance",
                            headers=owner).json()["balance_minor"], 0)

    def test_a_wallet_debit_key_is_not_a_pattern(self):
        """The key was interpolated into a `LIKE`, so a debit keyed `%` was answered 201
        `repeated: True` quoting the previous sale's figure: a till handed over 90.00 of goods
        for 1.00 of wallet value."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        person_id = self.person(tenant_id)
        owner = self.headers(tenant_id)
        self.client.post("/ledger/wallet-credits", json={
            "person_id": person_id, "value_kind": "cash", "amount_minor": 10000,
            "currency": "JOD", "legal_entity_id": entity,
            "counterpart_account_id": chart["cash"], "source_kind": "purchase",
            "reason": "paid in", "idempotency_key": "w-in", **self.correlation()},
            headers=owner)
        self.client.post("/ledger/wallet-debits", json={
            "person_id": person_id, "amount_minor": 100, "currency": "JOD",
            "legal_entity_id": entity, "counterpart_account_id": chart["revenue"],
            "reason": "a small sale", "idempotency_key": "sale-0001",
            **self.correlation()}, headers=owner)
        wild = self.client.post("/ledger/wallet-debits", json={
            "person_id": person_id, "amount_minor": 9000, "currency": "JOD",
            "legal_entity_id": entity, "counterpart_account_id": chart["revenue"],
            "reason": "a big sale", "idempotency_key": "%", **self.correlation()},
            headers=owner)
        self.assertEqual(wild.status_code, 201, wild.text)
        self.assertFalse(wild.json()["repeated"])
        self.assertEqual(wild.json()["amount_minor"], 9000)
        statement = self.client.get(
            f"/ledger/wallets/{person_id}?currency=JOD", headers=owner).json()
        self.assertEqual(statement["balances"]["cash"], 900)

    def test_recognition_does_not_believe_a_future_date(self):
        """A caller-chosen `as_of` five thousand days out turned the whole unearned liability
        into revenue in one call and marked the schedule `complete`, so the real recognition
        could never be posted -- paragraph 1695 inverted, and MOD-011's unbounded
        `observed_at` finding in a worse place."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        self.unearned_held(tenant_id, entity, chart, 120000)
        opened = self.client.post("/ledger/recognition-schedules", json={
            "legal_entity_id": entity, "source_kind": "manual", "source_ref": "a year",
            "basis": "straight_line", "total_minor": 120000, "currency": "JOD",
            "unearned_account_id": chart["unearned"],
            "revenue_account_id": chart["revenue"],
            "starts_on": day(-30), "ends_on": day(334), **self.correlation()},
            headers=owner)
        schedule_id = str(opened.json()["schedule_id"])
        refused = self.client.post(
            f"/ledger/recognition-schedules/{schedule_id}/post", json={
                "as_of": day(5000), "idempotency_key": "r-1", **self.correlation()},
            headers=owner)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("has not been earned", refused.text)

    def test_recognition_cannot_draw_down_a_liability_that_is_not_there(self):
        """`unearned_minor` on the invoice and `total_minor` on the schedule are two unrelated
        caller-supplied figures and the first defaults to zero, so a schedule drove the
        unearned liability to *minus* 500.00 -- the ledger asserting that members have prepaid
        negative money, reachable by accident on the ordinary path."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        opened = self.client.post("/ledger/recognition-schedules", json={
            "legal_entity_id": entity, "source_kind": "manual", "source_ref": "a pack",
            "basis": "on_delivery", "total_minor": 50000, "currency": "JOD",
            "units_total": 10, "unearned_account_id": chart["unearned"],
            "revenue_account_id": chart["revenue"], **self.correlation()},
            headers=owner)
        schedule_id = str(opened.json()["schedule_id"])
        refused = self.client.post(
            f"/ledger/recognition-schedules/{schedule_id}/post", json={
                "units_delivered": 10, "idempotency_key": "r-1",
                **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("billed to unearned revenue first", refused.text)
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{chart['unearned']}/balance",
                            headers=owner).json()["balance_minor"], 0)

    def test_a_settlement_fee_and_payout_move_the_clearing_balance(self):
        """`import_settlement` never called `post_journal`: `provider_clearing` was debited by
        every card payment and relieved by nothing, so it grew without bound while the module
        docstring said unmatched lines posted to suspense."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        imported = self.client.post("/ledger/settlements", json={
            "legal_entity_id": entity, "provider_key": "acme.payments",
            "provider_batch_ref": "2026-11-14", "settled_on": day(0),
            "currency": "JOD", "claimed_total_minor": 9000,
            "lines": [{"line_kind": "fee", "provider_ref": "fee_1",
                       "amount_minor": -1000},
                      {"line_kind": "payout", "provider_ref": "po_1",
                       "amount_minor": 10000}],
            "idempotency_key": "s-1", **self.correlation()}, headers=owner)
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertEqual(imported.json()["posted_lines"], 2)
        self.assertEqual(imported.json()["cases_opened"], [])
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{chart['fee']}/balance",
                            headers=owner).json()["balance_minor"], 1000)
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{chart['bank']}/balance",
                            headers=owner).json()["balance_minor"], 10000)
        # Both came out of clearing, which is the account the reconciliation reads.
        self.assertEqual(
            self.client.get(f"/ledger/accounts/{chart['clearing']}/balance",
                            headers=owner).json()["signed_minor"], -11000)

    def test_correcting_a_journal_twice_with_one_key_is_a_repeat(self):
        """The command took an idempotency key and ignored it on the repeat path, so a client
        whose request timed out after the commit was told 409 for work that had succeeded."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        posted = self.journal(tenant_id, entity, chart)
        body = {"reason": "posted to the wrong till", "idempotency_key": "c-1"}
        first = self.client.post(
            f"/ledger/journals/{posted['journal_id']}/correct",
            json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(first.status_code, 201, first.text)
        again = self.client.post(
            f"/ledger/journals/{posted['journal_id']}/correct",
            json={**body, **self.correlation()}, headers=owner)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertTrue(again.json()["repeated"])
        self.assertEqual(again.json()["journal_id"], first.json()["journal_id"])
        # A *different* key is still a refusal: that is a second correction, not a retry.
        third = self.client.post(
            f"/ledger/journals/{posted['journal_id']}/correct", json={
                "reason": "and again", "idempotency_key": "c-2",
                **self.correlation()}, headers=owner)
        self.assertEqual(third.status_code, 409, third.text)

    def test_a_case_cannot_cite_a_journal_that_is_about_something_else(self):
        """`resolution_journal_id` had a foreign key and nothing else behind it, so the row
        that *is* the audit read as though a journal had cleared a mismatch it has nothing to
        do with."""
        tenant_id = self.tenant()
        entity = self.legal_entity(tenant_id)
        chart = self.chart(tenant_id)
        owner = self.headers(tenant_id)
        unrelated = self.journal(tenant_id, entity, chart)
        imported = self.client.post("/ledger/settlements", json={
            "legal_entity_id": entity, "provider_key": "acme.payments",
            "provider_batch_ref": "to-cite", "settled_on": day(0), "currency": "JOD",
            "claimed_total_minor": 1000,
            "lines": [{"line_kind": "payment", "provider_ref": "ch_nothing",
                       "amount_minor": 1000}],
            "idempotency_key": "s-1", **self.correlation()}, headers=owner)
        case_id = imported.json()["cases_opened"][0]
        refused = self.client.post(
            f"/ledger/reconciliation-cases/{case_id}/resolve", json={
                "outcome": "resolved", "resolution": "cleared by that journal",
                "resolution_journal_id": unrelated["journal_id"],
                **self.correlation()}, headers=owner)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("is trade", refused.text)

"""MOD-026 slice 2: AUT-02-R05's delegation, and the hole it would otherwise open.

**The test that matters is `test_the_requester_cannot_approve_through_a_delegate`.** A
delegation exists to keep approvals moving while somebody is away; it also, silently, lets
the requester approve their own request by handing their authority to a colleague for an
afternoon. Separation of duties intact in the column and gone in fact. That is MOD-007's "a
remedy is new capability, so review it as such", which was learned when a recovery allowance
added to close one finding became a backdoor minting ten fresh codes with no password.

The schema refuses all of this too, and that is deliberate rather than redundant: this
build's premise is that the schema is the half that holds when the service is wrong. What the
service adds is a sentence instead of a constraint name.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

from app.authorization import service as authz
from app.authorization.service import Forbidden
from app.errors import Conflict, InvalidRequest
from tests.support import GatedApiTestCase

NOW = datetime.now(UTC)


class DelegationTestCase(GatedApiTestCase):
    def cid(self) -> str:
        return str(uuid.uuid4())

    def delegate(self, tenant_id: str, actor: str, to: str, **over: object) -> str:
        body: dict = {"starts_at": NOW - timedelta(hours=1),
                      "ends_at": NOW + timedelta(days=7), "reason": "away this week"}
        body.update(over)
        return str(authz.delegate_approvals(
            self._identity_pool, tenant_id, to_identity_id=to, actor_id=actor,
            correlation_id=self.cid(), **body)["delegation_id"])

    def request(self, tenant_id: str, requested_by: str) -> str:
        """An approval request with separation of duties on, which is the default.

        The policy is written first, because `request_approval` refuses when none applies --
        an approval nobody's policy requires is an approval queue nobody asked for.
        """
        authz.write_approval_policy(
            self._identity_pool, tenant_id, action="finance.refund.approve",
            required_permission="finance.refund.approve", correlation_id=self.cid(),
            actor_identity_id=self.owner_identity(tenant_id))
        made = authz.request_approval(
            self._identity_pool, tenant_id, action="finance.refund.approve",
            resource_type="invoice", resource_id=str(uuid.uuid4()),
            requested_by=requested_by, correlation_id=self.cid(), reason="a refund")
        return str(made["request_id"])


class DelegationTests(DelegationTestCase):
    def test_the_delegator_is_the_session_and_not_a_field(self):
        """**Derive, never accept.** A `from_identity_id` on the body would let anybody
        delegate anybody's authority to themselves -- the whole approval machinery bought
        with one uuid, which is MOD-008's own review finding in a new place."""
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        bob, _ = self.fresh_identity(tenant_id, "Bob")
        made = authz.delegate_approvals(
            self._identity_pool, tenant_id, to_identity_id=bob,
            starts_at=NOW, ends_at=NOW + timedelta(days=1), reason="holiday",
            actor_id=alice, correlation_id=self.cid())
        self.assertEqual(made["from_identity_id"], alice)
        self.assertEqual(made["to_identity_id"], bob)

    def test_a_delegation_to_yourself_is_refused(self):
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        with self.assertRaises(InvalidRequest):
            self.delegate(tenant_id, alice, alice)

    def test_a_delegation_is_not_passed_on(self):
        """A chain makes "on whose authority" unevaluable at decision time without walking
        it, and a loop if anybody closes one. The honest answer is to refuse the second hop."""
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        bob, _ = self.fresh_identity(tenant_id, "Bob")
        carol, _ = self.fresh_identity(tenant_id, "Carol")
        self.delegate(tenant_id, alice, bob)
        with self.assertRaises(Conflict) as caught:
            self.delegate(tenant_id, bob, carol)
        self.assertIn("not passed on", str(caught.exception))

    def test_somebody_who_delegated_away_cannot_hold_another(self):
        """The same chain from the far end."""
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        bob, _ = self.fresh_identity(tenant_id, "Bob")
        carol, _ = self.fresh_identity(tenant_id, "Carol")
        self.delegate(tenant_id, alice, bob)
        with self.assertRaises(Conflict) as caught:
            self.delegate(tenant_id, carol, alice)
        self.assertIn("delegated their own approvals away", str(caught.exception))

    def test_a_delegation_longer_than_ninety_days_is_refused(self):
        """An open-ended delegation is a permanent transfer of approval authority, which is a
        role assignment and already has a table. Conflating them would let a convenience for
        somebody's holiday become a standing grant nobody reviews."""
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        bob, _ = self.fresh_identity(tenant_id, "Bob")
        with self.assertRaises(InvalidRequest):
            self.delegate(tenant_id, alice, bob, ends_at=NOW + timedelta(days=200))

    def test_only_the_delegator_revokes_it(self):
        """An administrator who could revoke somebody else's delegation would be deciding who
        may approve while that person is away, which is the same power the delegation is."""
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        bob, _ = self.fresh_identity(tenant_id, "Bob")
        delegation_id = self.delegate(tenant_id, alice, bob)
        with self.assertRaises(Forbidden):
            authz.revoke_delegation(
                self._identity_pool, tenant_id, delegation_id, reason="not mine",
                actor_id=bob, correlation_id=self.cid())
        done = authz.revoke_delegation(
            self._identity_pool, tenant_id, delegation_id, reason="came back early",
            actor_id=alice, correlation_id=self.cid())
        self.assertFalse(done["repeated"])
        again = authz.revoke_delegation(
            self._identity_pool, tenant_id, delegation_id, reason="again",
            actor_id=alice, correlation_id=self.cid())
        self.assertTrue(again["repeated"])

    def test_the_listing_derives_whether_it_is_in_force(self):
        """`in_force` is two timestamps and a null, and a reader computing it gets the open
        cases wrong -- MOD-016's `in_window`, MOD-018's `admits_trade`."""
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        bob, _ = self.fresh_identity(tenant_id, "Bob")
        self.delegate(tenant_id, alice, bob)
        live = authz.list_delegations(self._identity_pool, tenant_id)
        self.assertEqual(len(live["delegations"]), 1)
        self.assertTrue(live["delegations"][0]["in_force"])


class SeparationOfDutiesTests(DelegationTestCase):
    def test_the_requester_cannot_approve_through_a_delegate(self):
        """**The hole delegation would otherwise open.**

        Alice raises a request and delegates her authority to Bob. Bob deciding it on Alice's
        authority is Alice approving her own request: the column says Bob and the fact says
        Alice. The service refuses it with a named reason and the schema refuses it too.
        """
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        bob, _ = self.fresh_identity(tenant_id, "Bob")
        self.delegate(tenant_id, alice, bob)
        request_id = self.request(tenant_id, alice)
        with self.assertRaises(Forbidden) as caught:
            authz.decide_approval(
                self._identity_pool, tenant_id, request_id=request_id, decided_by=bob,
                decision="approved", correlation_id=self.cid(), on_behalf_of=alice)
        self.assertIn("delegate", str(caught.exception))

    def test_a_cited_authority_nobody_granted_is_refused(self):
        """"A cited authority is the authority, or it is decoration beside the figure."
        Without the schema's check, `on_behalf_of` is a text field saying whatever the caller
        types, and any approver claims anybody's power."""
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        bob, _ = self.fresh_identity(tenant_id, "Bob")
        carol, _ = self.fresh_identity(tenant_id, "Carol")
        request_id = self.request(tenant_id, alice)
        # **Two controls refuse this row and the service's is first, which is worth naming
        # rather than hiding behind a blind `assertRaises`.** The policy is evaluated against
        # the *delegator's* permissions -- that is what being delegated to means -- so citing
        # somebody who holds nothing fails there before the schema is reached. The schema's
        # own refusal, for an authority that does hold the permission but granted no
        # delegation, is proved by isolation check 113's fourth probe and nine mutations.
        with self.assertRaises(Forbidden) as caught:
            authz.decide_approval(
                self._identity_pool, tenant_id, request_id=request_id, decided_by=bob,
                decision="approved", correlation_id=self.cid(), on_behalf_of=carol)
        self.assertIn("decider_lacks_permission", str(caught.exception))

    def test_acting_on_your_own_authority_is_not_a_delegation(self):
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        request_id = self.request(tenant_id, alice)
        with self.assertRaises(InvalidRequest):
            authz.decide_approval(
                self._identity_pool, tenant_id, request_id=request_id, decided_by=alice,
                decision="approved", correlation_id=self.cid(), on_behalf_of=alice)

    def test_an_ordinary_decision_still_works_and_the_requester_still_cannot(self):
        """The unchanged half, asserted so the new clause cannot be the only thing holding:
        a non-delegated self-approval is refused by the original rule."""
        tenant_id = self.tenant()
        alice = self.owner_identity(tenant_id)
        request_id = self.request(tenant_id, alice)
        with self.assertRaises(Forbidden) as caught:
            authz.decide_approval(
                self._identity_pool, tenant_id, request_id=request_id, decided_by=alice,
                decision="approved", correlation_id=self.cid())
        self.assertNotIn("delegate", str(caught.exception))


class DelegationRouteTests(DelegationTestCase):
    def test_the_body_carries_no_delegator(self):
        """A route that accepted one would be the service's own finding at the boundary."""
        tenant_id = self.tenant()
        bob, _ = self.fresh_identity(tenant_id, "Bob")
        answer = self.client.post("/authz/delegations", json={
            "to_identity_id": bob, "from_identity_id": bob,
            "starts_at": NOW.isoformat(),
            "ends_at": (NOW + timedelta(days=1)).isoformat(),
            "reason": "holiday", **self.correlation()},
            headers=self.headers(tenant_id))
        self.assertEqual(answer.status_code, 201, answer.text)
        # The field was ignored, not honoured: the delegator is the session.
        self.assertEqual(
            answer.json()["from_identity_id"], self.owner_identity(tenant_id))

    def test_a_malformed_recipient_is_a_422(self):
        tenant_id = self.tenant()
        answer = self.client.post("/authz/delegations", json={
            "to_identity_id": "not-a-uuid", "starts_at": NOW.isoformat(),
            "ends_at": (NOW + timedelta(days=1)).isoformat(), "reason": "x",
            **self.correlation()}, headers=self.headers(tenant_id))
        self.assertEqual(answer.status_code, 422, answer.text)

    def test_a_reader_without_the_role_read_is_refused_the_listing(self):
        tenant_id = self.tenant()
        nobody = self.headers(tenant_id, self.grant(tenant_id, []))
        self.assertEqual(
            self.client.get("/authz/delegations", headers=nobody).status_code, 403)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

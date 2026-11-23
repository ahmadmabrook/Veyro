"""MOD-026 slice 5: AUT-02-R05's last word, "sequential, parallel".

**The engine had no notion of a second *kind* of approver.** `required_approvals` is a quorum
of one authority, so "a club manager and then finance" was unexpressible -- and the two facts
the requirement actually carries are exactly that an approval can need more than one kind of
approver, and that sequential means the second kind cannot decide before the first has.

**The assertion that matters most is
`test_three_signatures_on_one_stage_do_not_satisfy_two`**: a staged request resolved against
the *total* would make "a manager and then finance" mean "two people", which is the whole
distinction the stages draw. The schema refuses the out-of-order and phantom-stage cases too,
and that is deliberate rather than redundant -- this build's premise is that the schema is the
half that holds when the service is wrong. What the service adds is a sentence instead of a
constraint name.
"""

from __future__ import annotations

import unittest
import uuid

from app.authorization import service as authz
from app.authorization.service import Forbidden
from app.errors import Conflict, InvalidRequest
from tests.support import GatedApiTestCase

MANAGER = "finance.refund.approve"
FINANCE = "finance.export.run"
ACTION = "finance.refund.approve"


class StageTestCase(GatedApiTestCase):
    def cid(self) -> str:
        return str(uuid.uuid4())

    def policy(self, tenant_id: str, **over: object) -> dict:
        body: dict = {
            "action": ACTION, "required_permission": MANAGER,
            "stages": [{"required_permission": MANAGER, "required_approvals": 1},
                       {"required_permission": FINANCE, "required_approvals": 1}],
            "sequential": True,
        }
        body.update(over)
        return authz.write_approval_policy(
            self._identity_pool, tenant_id, correlation_id=self.cid(),
            actor_identity_id=self.owner_identity(tenant_id), **body)

    def request(self, tenant_id: str, requested_by: str) -> dict:
        return authz.request_approval(
            self._identity_pool, tenant_id, action=ACTION, resource_type="invoice",
            resource_id=str(uuid.uuid4()), requested_by=requested_by,
            correlation_id=self.cid(), reason="a refund")

    def approver(self, tenant_id: str, permissions: list[str]) -> str:
        """An identity holding exactly these permissions.

        **Through the service layer and the owner's own gate**, which is `support.py`'s rule:
        a privilege the fixture could not obtain honestly is one these tests must not hand out.
        """
        identity_id, _ = self.fresh_identity(tenant_id, f"a{uuid.uuid4().hex[:8]}")
        self.grant_to(tenant_id, identity_id, permissions)
        return identity_id

    def grant_to(self, tenant_id: str, identity_id: str, permissions: list[str]) -> None:
        owner = self.owner_identity(tenant_id)
        role_key = f"stage_{uuid.uuid4().hex[:8]}"
        authz.create_role(
            self._identity_pool, tenant_id, role_key=role_key, display_name="Stage",
            permissions=permissions, actor_identity_id=owner, correlation_id=self.cid())
        authz.assign_role(
            self._identity_pool, tenant_id, identity_id=identity_id, role_key=role_key,
            granted_by=owner, correlation_id=self.cid())


class StagedPolicyTests(StageTestCase):
    def test_a_staged_policy_records_its_stages_and_its_order(self):
        tenant_id = self.tenant()
        written = self.policy(tenant_id)
        self.assertTrue(written["sequential"])
        self.assertEqual(
            [(s["ordinal"], s["required_permission"]) for s in written["stages"]],
            [(1, MANAGER), (2, FINANCE)])

    def test_a_single_stage_policy_cannot_be_sequential(self):
        """There is nothing to order, and a flag nothing reads is this build's most-repeated
        finding -- so it is refused rather than stored."""
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest) as refused:
            self.policy(tenant_id, stages=[], sequential=True)
        self.assertIn("no_order", str(refused.exception))

    def test_a_policy_whose_own_permission_is_no_stage_is_refused(self):
        """**An authority no stage charges is one nobody is ever asked for.** With stages the
        permission requirement is the stage's, so a `required_permission` outside the stage
        list is simply never checked -- a declared value nothing reads, caught before it is
        written rather than found later as a policy that admits anybody."""
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest) as refused:
            self.policy(tenant_id, required_permission="authz.role.write")
        self.assertIn("must_be_one_of_its_stages", str(refused.exception))

    def test_two_stages_naming_one_permission_are_refused(self):
        """Two steps for the same authority is a quorum written as two rows, and the two
        encodings would then disagree about what the count is."""
        tenant_id = self.tenant()
        with self.assertRaises(InvalidRequest):
            self.policy(tenant_id, stages=[
                {"required_permission": MANAGER, "required_approvals": 1},
                {"required_permission": MANAGER, "required_approvals": 2}])

    def test_a_contradictory_order_is_refused_when_the_policy_is_written(self):
        """**MOD-012's succession rule.** Two policies that disagree about the order of the
        same two permissions have no defensible automatic answer, and catching it where
        somebody is writing the change beats catching it when an approval is needed -- at
        which point the person waiting can do nothing about it."""
        tenant_id = self.tenant()
        self.policy(tenant_id)
        with self.assertRaises(Conflict) as refused:
            self.policy(tenant_id, threshold_minor=500, stages=[
                {"required_permission": FINANCE, "required_approvals": 1},
                {"required_permission": MANAGER, "required_approvals": 1}])
        self.assertIn("order_conflicts", str(refused.exception))

    def test_a_three_policy_cycle_is_refused_too(self):
        """**The case pairwise checking cannot see**, and the one that made the first version
        of this check wrong: each of the three agrees with the others on its one shared
        permission, and the three together cannot be satisfied at all."""
        tenant_id = self.tenant()
        third = "authz.role.write"
        self.policy(tenant_id, stages=[
            {"required_permission": MANAGER, "required_approvals": 1},
            {"required_permission": FINANCE, "required_approvals": 1}])
        self.policy(tenant_id, threshold_minor=500, required_permission=FINANCE, stages=[
            {"required_permission": FINANCE, "required_approvals": 1},
            {"required_permission": third, "required_approvals": 1}])
        with self.assertRaises(Conflict) as refused:
            self.policy(tenant_id, threshold_minor=900, required_permission=third, stages=[
                {"required_permission": third, "required_approvals": 1},
                {"required_permission": MANAGER, "required_approvals": 1}])
        self.assertIn("order_conflicts", str(refused.exception))

    def test_a_chain_of_three_policies_is_orderable_and_the_request_says_so(self):
        """The permission probe for the cycle check: a chain is not a cycle, and the combined
        order is every policy's rather than the alphabet's."""
        tenant_id = self.tenant()
        third = "authz.role.write"
        self.policy(tenant_id, stages=[
            {"required_permission": MANAGER, "required_approvals": 1},
            {"required_permission": FINANCE, "required_approvals": 1}])
        # **Both at threshold zero**, because the request carries no amount: a policy above
        # the amount does not apply at all, and the first version of this test put the third
        # stage behind a threshold of 500 and then asserted it was there. The thresholds are
        # what `policy_for` filters on and they are a different question from the order.
        self.policy(tenant_id, required_permission=FINANCE, stages=[
            {"required_permission": FINANCE, "required_approvals": 1},
            {"required_permission": third, "required_approvals": 1}])
        requester, _ = self.fresh_identity(tenant_id, "Requester")
        self.grant_to(tenant_id, requester, [ACTION])
        made = self.request(tenant_id, requester)
        self.assertEqual(
            [s["required_permission"] for s in made["stages"]], [MANAGER, FINANCE, third])

    def test_the_same_order_again_is_not_a_conflict(self):
        """The permission probe: a check that refused every second staged policy would pass
        every refusal test above and be useless."""
        tenant_id = self.tenant()
        self.policy(tenant_id)
        self.policy(tenant_id, threshold_minor=500)

    def test_a_request_snapshots_the_combined_stages(self):
        """**MOD-008's review put the snapshot there**, after re-deriving the terms let
        somebody holding `authz.policy.write` turn separation of duties off for a request
        already in flight. A stage list re-derived at decision time is the same defect with
        more surface."""
        tenant_id = self.tenant()
        self.policy(tenant_id)
        made = self.request(tenant_id, self.owner_identity(tenant_id))
        self.assertTrue(made["sequential"])
        self.assertEqual(
            [(s["ordinal"], s["required_permission"]) for s in made["stages"]],
            [(1, MANAGER), (2, FINANCE)])


class StagedDecisionTests(StageTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenant_id = self.tenant()
        self.requester, _ = self.fresh_identity(self.tenant_id, "Requester")
        self.grant_to(self.tenant_id, self.requester, [ACTION])
        self.policy(self.tenant_id)
        self.request_id = str(self.request(self.tenant_id, self.requester)["request_id"])
        self.manager = self.approver(self.tenant_id, [MANAGER])
        self.money = self.approver(self.tenant_id, [FINANCE, MANAGER])

    def decide(self, who: str, *, stage: int = 1, decision: str = "approved") -> dict:
        return authz.decide_approval(
            self._identity_pool, self.tenant_id, request_id=self.request_id,
            decided_by=who, decision=decision, correlation_id=self.cid(),
            stage_ordinal=stage)

    def test_the_second_stage_is_shut_until_the_first_is_approved(self):
        with self.assertRaises(Forbidden) as refused:
            self.decide(self.money, stage=2)
        self.assertIn("stage_not_open", str(refused.exception))

    def test_the_first_stage_opens_the_second_and_two_people_settle_it(self):
        first = self.decide(self.manager, stage=1)
        self.assertEqual(first["state"], "pending")
        self.assertEqual(
            [(s["ordinal"], s["approved"]) for s in first["stages"]], [(1, 1), (2, 0)])
        second = self.decide(self.money, stage=2)
        self.assertEqual(second["state"], "approved")

    def test_three_signatures_on_one_stage_do_not_satisfy_two(self):
        """**The defect this whole slice is written against.** Resolving a staged request
        against the total would make "a manager and then finance" mean "two people"."""
        extra = self.approver(self.tenant_id, [MANAGER])
        more = self.approver(self.tenant_id, [MANAGER])
        self.decide(self.manager, stage=1)
        self.decide(extra, stage=1)
        piled = self.decide(more, stage=1)
        self.assertEqual(piled["state"], "pending")
        self.assertEqual(piled["stages"][0]["approved"], 3)

    def test_one_person_cannot_decide_two_stages(self):
        """**`UNIQUE (tenant_id, request_id, decided_by)` is what makes a stage mean
        something**, and it is the constraint that was already there: a two-stage approval
        decided twice by one person is one approval wearing two hats."""
        self.decide(self.money, stage=1)
        with self.assertRaises(Conflict) as refused:
            self.decide(self.money, stage=2)
        self.assertIn("already_decided_by_you", str(refused.exception))

    def test_a_decider_without_the_stage_permission_is_refused(self):
        """Holding the *other* stage's authority is not holding this one's, which is what
        makes a stage a kind of approver rather than one more body."""
        self.decide(self.manager, stage=1)
        only_manager = self.approver(self.tenant_id, [MANAGER])
        with self.assertRaises(Forbidden) as refused:
            self.decide(only_manager, stage=2)
        self.assertIn("stage_permission", str(refused.exception))

    def test_a_stage_the_request_has_not_got_is_refused(self):
        with self.assertRaises(Forbidden) as refused:
            self.decide(self.manager, stage=5)
        self.assertIn("no_such_stage", str(refused.exception))

    def test_an_out_of_range_stage_is_refused_at_the_boundary(self):
        with self.assertRaises(InvalidRequest):
            self.decide(self.manager, stage=99)

    def test_a_rejection_at_either_stage_settles_the_whole_request(self):
        """A stage is a condition rather than a vote, so there is no stage to localise a
        rejection to."""
        settled = self.decide(self.manager, stage=1, decision="rejected")
        self.assertEqual(settled["state"], "rejected")
        with self.assertRaises(Conflict):
            self.decide(self.money, stage=2)

    def test_the_requester_still_cannot_decide_any_stage(self):
        """INV-AUT-02 is unmoved: stages add a second kind of approver, not a way past the
        separation of duties."""
        self.grant_to(self.tenant_id, self.requester, [MANAGER, FINANCE])
        with self.assertRaises(Forbidden) as refused:
            self.decide(self.requester, stage=1)
        self.assertIn("separation_of_duties", str(refused.exception))


class ParallelTests(StageTestCase):
    def test_a_parallel_request_takes_its_stages_in_any_order(self):
        """The whole difference between the two words R05 names: the second stage is open from
        the start, and the request is still not approved until both have their count."""
        tenant_id = self.tenant()
        requester, _ = self.fresh_identity(tenant_id, "Requester")
        self.grant_to(tenant_id, requester, [ACTION])
        self.policy(tenant_id, sequential=False)
        request_id = str(self.request(tenant_id, requester)["request_id"])
        money = self.approver(tenant_id, [FINANCE])
        manager = self.approver(tenant_id, [MANAGER])

        second_first = authz.decide_approval(
            self._identity_pool, tenant_id, request_id=request_id, decided_by=money,
            decision="approved", correlation_id=self.cid(), stage_ordinal=2)
        self.assertEqual(second_first["state"], "pending")
        done = authz.decide_approval(
            self._identity_pool, tenant_id, request_id=request_id, decided_by=manager,
            decision="approved", correlation_id=self.cid(), stage_ordinal=1)
        self.assertEqual(done["state"], "approved")


class UnstagedTests(StageTestCase):
    def test_an_unstaged_policy_and_request_behave_exactly_as_they_did(self):
        """**The absence is the existing meaning**, which is what makes `0006` a no-op for
        every policy and request already recorded."""
        tenant_id = self.tenant()
        requester, _ = self.fresh_identity(tenant_id, "Requester")
        self.grant_to(tenant_id, requester, [ACTION])
        self.policy(tenant_id, stages=[], sequential=False, required_approvals=1)
        made = self.request(tenant_id, requester)
        self.assertEqual(made["stages"], [])
        self.assertFalse(made["sequential"])
        approver = self.approver(tenant_id, [MANAGER])
        settled = authz.decide_approval(
            self._identity_pool, tenant_id, request_id=str(made["request_id"]),
            decided_by=approver, decision="approved", correlation_id=self.cid())
        self.assertEqual(settled["state"], "approved")
        self.assertEqual(settled["stage_ordinal"], 1)
        self.assertEqual(settled["stages"], [])

    def test_a_stage_other_than_one_is_refused_on_an_unstaged_request(self):
        tenant_id = self.tenant()
        requester, _ = self.fresh_identity(tenant_id, "Requester")
        self.grant_to(tenant_id, requester, [ACTION])
        self.policy(tenant_id, stages=[], sequential=False)
        made = self.request(tenant_id, requester)
        approver = self.approver(tenant_id, [MANAGER])
        with self.assertRaises(Forbidden) as refused:
            authz.decide_approval(
                self._identity_pool, tenant_id, request_id=str(made["request_id"]),
                decided_by=approver, decision="approved", correlation_id=self.cid(),
                stage_ordinal=2)
        self.assertIn("no_such_stage", str(refused.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

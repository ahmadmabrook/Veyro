"""MOD-008 IAM-03: the authorization decision, the audit chain and approvals, with no database.

IAM-03's critical controls are claims about what *cannot* happen -- default deny, least
privilege, separation of duties, an audit log that cannot be changed quietly. A test suite for
those is mostly attacks that must fail, so that is how these are written.
"""

import pathlib
import unittest
from datetime import UTC, datetime, timedelta

from app.authorization import approval, audit, gate
from app.authorization import decision as authz
from app.authorization.catalog import (
    PERMISSIONS,
    CatalogError,
    action_class,
    audit_category,
    classify_field,
    require_permission,
)

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
TENANT = "11111111-1111-4111-8111-111111111111"


def role(key="front_desk", perms=("member.profile.read",), **kw):
    return authz.Assignment(role_key=key, permissions=frozenset(perms), **kw)


class CatalogTests(unittest.TestCase):
    def test_every_permission_is_module_resource_action_with_no_wildcard(self):
        for name in PERMISSIONS:
            self.assertRegex(name, r"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$")
            self.assertNotIn("*", name)

    def test_every_permission_has_a_known_category_and_action_class(self):
        categories = {"authentication", "data_access", "configuration", "finance", "access",
                      "ai", "support"}
        classes = {"routine", "financial", "privileged", "biometric_sensitive"}
        for name, permission in PERMISSIONS.items():
            self.assertIn(permission.category, categories, name)
            self.assertIn(permission.action_class, classes, name)

    def test_an_unknown_permission_raises_rather_than_defaulting(self):
        with self.assertRaises(CatalogError):
            require_permission("billing.invoice.destroy")
        with self.assertRaises(CatalogError):
            audit_category("nope.nope.nope")

    # Reading is routine; recording a measurement is machine telemetry. Everything else under
    # finance or access is a decision somebody makes, and must cost a second factor. A new
    # permission added at `routine` under either category fails this.
    ROUTINE_BY_DESIGN = {"billing.usage.record", "privacy.incident.record",
                         "access.credential.revoke", "access.decision.evaluate",
                         "access.event.record", "access.emergency.unlock"}

    def test_money_and_access_decisions_are_not_routine(self):
        """A permission that moves money or grants access must need a second factor."""
        for name, permission in PERMISSIONS.items():
            if permission.category not in ("finance", "access"):
                continue
            if name.endswith(".read") or name in self.ROUTINE_BY_DESIGN:
                continue
            self.assertNotEqual(permission.action_class, "routine", name)

    def test_the_routine_exceptions_are_deliberate(self):
        """Stated as its own test so the exception set cannot be widened by accident.

        Every one is a write under a category whose other members all demand a second factor,
        and every one is an exception for the same reason: **the thing doing it cannot step
        up**, and refusing it has a worse failure mode than allowing it.

        `billing.usage.record` is a device emitting measurements continuously, and its reach is
        bounded -- defining what is measured and moving the quota are separate, financial-class
        permissions, which is a defect an independent review found and the gating suite now
        holds in place.

        `privacy.incident.record` is somebody writing down that something went wrong, and the
        something may be that authentication is unavailable. A step-up requirement there means
        the worst incidents are the ones with no record. The row is insert-only either way, so
        the cost of a false one is noise rather than destruction.

        The four MOD-022 entries are all a reader or an emergency:

          * `access.decision.evaluate` and `access.event.record` are what a turnstile does
            every time somebody walks up to it. There is nobody at a reader to answer a
            challenge, and a door that refuses every member until a kiosk authenticates is a
            club that does not open. Evaluating decides nothing by itself -- the policy
            does, from facts the reader never sends -- and every call leaves an
            insert-only row.
          * `access.credential.revoke` only ever closes a door. A card reported stolen at
            seven in the morning has to be killable by whoever is on the desk; re-issuing one
            is `access.credential.issue`, which is financial class. MOD-013's suppression list
            is the same asymmetry.
          * `access.emergency.unlock` is paragraph 4178's "where time permits", and a fire is
            the case where it does not. A step-up that fails during an evacuation is a door
            that stays shut. The dual approval moves to the review afterwards, which
            `acc_emergency_unlocks_reviewer_is_not_orderer` makes a second person and which
            the row stays unreviewed without.
        """
        for name in sorted(self.ROUTINE_BY_DESIGN):
            self.assertEqual(action_class(name), "routine", name)
        self.assertEqual(
            self.ROUTINE_BY_DESIGN,
            {"billing.usage.record", "privacy.incident.record",
             "access.credential.revoke", "access.decision.evaluate", "access.event.record",
             "access.emergency.unlock"})

    def test_configuration_changes_need_a_second_factor(self):
        """TSD paragraph 1020 requires change control for financial and security flag changes."""
        for name in ("config.flag.write", "config.kill_switch.engage", "config.value.publish",
                     "config.value.rollback", "config.experiment.write"):
            self.assertEqual(action_class(name), "financial", name)

    def test_the_sensitive_field_classes_cover_what_the_requirement_names(self):
        self.assertEqual(
            {classify_field(f) for f in ("iban", "biometric_template", "health_notes",
                                         "national_id", "email")},
            {"financial", "biometric", "health", "identity", "contact"},
        )
        self.assertIsNone(classify_field("display_name"))

    def test_break_glass_and_ai_need_the_strongest_assurance(self):
        self.assertEqual(action_class("support.session.start"), "privileged")
        self.assertEqual(action_class("ai.action.invoke"), "privileged")


class DefaultDenyTests(unittest.TestCase):
    def authorize(self, request, assignments=(), policies=()):
        return authz.authorize(request, list(assignments), list(policies), now=NOW)

    def test_nothing_granted_means_denied(self):
        decided = self.authorize(authz.Request("member.profile.read"))
        self.assertFalse(decided.allowed)
        self.assertEqual(decided.reason, "default_deny")

    def test_an_unknown_action_is_denied_not_passed_through(self):
        decided = self.authorize(authz.Request("member.profile.destroy"), [role()])
        self.assertFalse(decided.allowed)
        self.assertEqual(decided.reason, "unknown_action")

    def test_a_wildcard_shaped_action_is_simply_unknown(self):
        self.assertFalse(self.authorize(authz.Request("member.*")).allowed)
        self.assertFalse(self.authorize(authz.Request("member.profile.*")).allowed)

    def test_a_role_without_the_permission_grants_nothing(self):
        decided = self.authorize(authz.Request("member.profile.write"), [role()])
        self.assertEqual(decided.reason, "default_deny")

    def test_a_role_with_the_permission_grants_it(self):
        decided = self.authorize(authz.Request("member.profile.read"), [role()])
        self.assertTrue(decided.allowed)
        self.assertEqual((decided.reason, decided.matched_role), ("role:front_desk",
                                                                  "front_desk"))


class ScopeTests(unittest.TestCase):
    def authorize(self, scope, assignment_scope):
        return authz.authorize(
            authz.Request("member.profile.read", scope),
            [role(scope=assignment_scope)], [], now=NOW,
        )

    def test_a_tenant_scope_reaches_everything(self):
        for target in (authz.Scope(), authz.Scope("brand", brand_id="b1"),
                       authz.Scope("location", location_id="l1")):
            self.assertTrue(self.authorize(target, authz.Scope()).allowed)

    def test_a_brand_scope_reaches_that_brand_only(self):
        held = authz.Scope("brand", brand_id="b1")
        self.assertTrue(self.authorize(authz.Scope("brand", brand_id="b1"), held).allowed)
        self.assertFalse(self.authorize(authz.Scope("brand", brand_id="b2"), held).allowed)

    def test_a_brand_scope_reaches_a_location_only_when_its_brand_is_given(self):
        held = authz.Scope("brand", brand_id="b1")
        with_brand = authz.Scope("location", brand_id="b1", location_id="l1")
        without = authz.Scope("location", location_id="l1")
        self.assertTrue(self.authorize(with_brand, held).allowed)
        self.assertFalse(self.authorize(without, held).allowed,
                         "this module does not know the hierarchy and must not guess")

    def test_a_location_scope_reaches_that_location_only(self):
        held = authz.Scope("location", location_id="l1")
        self.assertTrue(self.authorize(authz.Scope("location", location_id="l1"), held).allowed)
        self.assertFalse(self.authorize(authz.Scope("location", location_id="l2"), held).allowed)
        self.assertFalse(self.authorize(authz.Scope("brand", brand_id="b1"), held).allowed)

    def test_an_unknown_scope_type_reaches_nothing(self):
        self.assertFalse(self.authorize(authz.Scope(), authz.Scope("region")).allowed)


class TemporaryAccessTests(unittest.TestCase):
    def authorize(self, assignment):
        return authz.authorize(authz.Request("member.profile.read"), [assignment], [], now=NOW)

    def test_an_unexpired_assignment_grants(self):
        self.assertTrue(self.authorize(role(expires_at=NOW + timedelta(hours=1))).allowed)

    def test_an_expired_assignment_grants_nothing_without_being_revoked(self):
        decided = self.authorize(role(expires_at=NOW))
        self.assertFalse(decided.allowed)
        self.assertEqual(decided.reason, "default_deny")

    def test_a_revoked_assignment_grants_nothing(self):
        self.assertFalse(self.authorize(role(revoked=True)).allowed)

    def test_a_revoked_assignment_is_dead_even_before_its_expiry(self):
        self.assertFalse(
            self.authorize(role(revoked=True, expires_at=NOW + timedelta(days=30))).allowed)


class PolicyTests(unittest.TestCase):
    def authorize(self, policies, assignments=(), attributes=None):
        return authz.authorize(
            authz.Request("member.profile.read", attributes=attributes or {}),
            list(assignments), list(policies), now=NOW,
        )

    def deny(self, **kw):
        return authz.Policy("protect_health", "deny", "member.profile.read", **kw)

    def test_a_deny_policy_beats_a_role_grant(self):
        decided = self.authorize([self.deny()], [role()])
        self.assertFalse(decided.allowed)
        self.assertEqual(decided.reason, "policy:protect_health")

    def test_a_deny_policy_beats_a_higher_priority_allow(self):
        decided = self.authorize([
            self.deny(priority=500),
            authz.Policy("override", "allow", "member.profile.read", priority=1),
        ])
        self.assertFalse(decided.allowed, "priority must not be a way around a protection")

    def test_a_deny_policy_applies_only_when_its_attributes_match(self):
        policy = self.deny(match={"record_kind": "health"})
        self.assertFalse(self.authorize([policy], [role()],
                                        {"record_kind": "health"}).allowed)
        self.assertTrue(self.authorize([policy], [role()],
                                       {"record_kind": "contact"}).allowed)

    def test_an_absent_attribute_does_not_match_a_policy_that_names_it(self):
        """Otherwise a policy for one clinician's clients applies to every forgetful caller."""
        policy = authz.Policy("assigned_only", "allow", "member.profile.read",
                              match={"assigned_to": "me"})
        self.assertFalse(self.authorize([policy]).allowed)
        self.assertTrue(self.authorize([policy], attributes={"assigned_to": "me"}).allowed)

    def test_an_allow_policy_can_grant_without_a_role(self):
        decided = self.authorize([authz.Policy("open_read", "allow", "member.profile.read")])
        self.assertTrue(decided.allowed)
        self.assertEqual(decided.reason, "policy:open_read")

    def test_a_policy_for_another_action_is_ignored(self):
        self.assertFalse(self.authorize([
            authz.Policy("other", "deny", "member.profile.write")], [role()]).allowed is False)


class MaskingTests(unittest.TestCase):
    def test_a_mask_policy_rides_along_with_an_allow(self):
        decided = authz.authorize(
            authz.Request("member.profile.read"), [role()],
            [authz.Policy("mask_health", "mask", "member.profile.read",
                          masked_fields=("health_notes", "national_id"))],
            now=NOW,
        )
        self.assertTrue(decided.allowed)
        self.assertEqual(decided.masked_fields, ("health_notes", "national_id"))

    def test_masks_from_several_policies_accumulate_without_duplicates(self):
        decided = authz.authorize(
            authz.Request("member.profile.read"), [role()],
            [authz.Policy("a", "mask", "member.profile.read", masked_fields=("health_notes",)),
             authz.Policy("b", "mask", "member.profile.read",
                          masked_fields=("health_notes", "iban"))],
            now=NOW,
        )
        self.assertEqual(decided.masked_fields, ("health_notes", "iban"))

    def test_applying_the_mask_replaces_only_the_named_fields(self):
        decided = authz.Decision(allowed=True, reason="role:x",
                                 masked_fields=("health_notes",))
        self.assertEqual(
            decided.mask({"display_name": "Ada", "health_notes": "private"}),
            {"display_name": "Ada", "health_notes": "***"},
        )

    def test_a_denied_decision_has_nothing_to_mask(self):
        with self.assertRaises(PermissionError):
            authz.Decision(allowed=False, reason="default_deny").mask({"a": 1})


class SimulatorTests(unittest.TestCase):
    def test_the_simulator_answers_from_the_same_rules_as_the_evaluator(self):
        assignments = [
            role("front_desk", ("member.profile.read",), scope=authz.Scope("brand",
                                                                           brand_id="b1")),
            role("manager", ("member.profile.write",), expires_at=NOW),
            role("auditor", ("authz.audit.read",), revoked=True),
        ]
        at_brand = authz.permissions_of(assignments, now=NOW,
                                        scope=authz.Scope("brand", brand_id="b1"))
        self.assertEqual(at_brand, frozenset({"member.profile.read"}))
        self.assertEqual(authz.permissions_of(assignments, now=NOW,
                                              scope=authz.Scope("brand", brand_id="b2")),
                         frozenset())

    def test_the_simulator_and_the_evaluator_agree_on_every_permission(self):
        assignments = [role("front_desk", ("member.profile.read", "config.flag.read"))]
        granted = authz.permissions_of(assignments, now=NOW)
        for name in PERMISSIONS:
            decided = authz.authorize(authz.Request(name), assignments, [], now=NOW)
            self.assertEqual(decided.allowed, name in granted, name)


class GateTests(unittest.TestCase):
    def gate(self, action, session_aal, perms=None):
        return gate.may(
            session_aal=session_aal, request=authz.Request(action),
            assignments=[role("r", perms or (action,))], policies=[], now=NOW,
        )

    def test_a_routine_action_passes_on_a_password_session(self):
        decided = self.gate("member.profile.read", 1)
        self.assertTrue(decided.allowed)

    def test_a_financial_action_needs_a_stepped_up_session(self):
        denied = self.gate("billing.invoice.issue", 1)
        self.assertFalse(denied.allowed)
        self.assertTrue(denied.step_up_required)
        self.assertEqual(denied.required_aal, 2)
        self.assertTrue(denied.reachable)
        self.assertTrue(self.gate("billing.invoice.issue", 2).allowed)

    def test_a_privileged_action_is_refused_as_unreachable_rather_than_as_a_step_up(self):
        """AAL-3 needs a hardware factor this build cannot verify; saying 'step up' would lie."""
        denied = self.gate("support.session.start", 2)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "unreachable_assurance")
        self.assertFalse(denied.reachable)

    def test_authorization_is_decided_before_assurance(self):
        """An unauthorized caller is told so, not sent to spend a recovery code for nothing."""
        denied = gate.may(session_aal=1, request=authz.Request("billing.invoice.issue"),
                          assignments=[], policies=[], now=NOW)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "default_deny")
        self.assertFalse(denied.step_up_required)

    def test_a_deny_policy_stops_the_gate_whatever_the_assurance(self):
        denied = gate.may(
            session_aal=3, request=authz.Request("member.profile.read"),
            assignments=[role()],
            policies=[authz.Policy("no", "deny", "member.profile.read")], now=NOW,
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "policy:no")

    def test_the_gate_carries_the_mask_through(self):
        allowed = gate.may(
            session_aal=1, request=authz.Request("member.profile.read"),
            assignments=[role()],
            policies=[authz.Policy("m", "mask", "member.profile.read",
                                   masked_fields=("health_notes",))], now=NOW,
        )
        self.assertEqual(allowed.masked_fields, ("health_notes",))

    def test_an_unknown_action_never_reaches_the_assurance_question(self):
        denied = gate.may(session_aal=3, request=authz.Request("nope.nope.nope"),
                          assignments=[role("r", ("nope.nope.nope",))], policies=[], now=NOW)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "unknown_action")


def entry(sequence, prev, *, action="role.assigned", detail=None):
    payload = {
        "category": "access", "action": action, "outcome": "recorded",
        "actor_identity_id": None, "on_behalf_of": None, "resource_type": None,
        "resource_id": None, "detail": detail or {}, "correlation_id": "c-1",
        "occurred_at": "2026-11-13T12:00:00Z",
    }
    digest = audit.entry_digest(TENANT, sequence, prev, payload)
    return audit.Entry(sequence=sequence, prev_hash=prev, entry_hash=digest, **payload)


def chain(length=3):
    entries, prev = [], audit.GENESIS
    for sequence in range(1, length + 1):
        made = entry(sequence, prev)
        entries.append(made)
        prev = made.entry_hash
    return entries


class AuditChainTests(unittest.TestCase):
    def test_a_well_formed_chain_verifies(self):
        audit.verify_chain(TENANT, chain())

    def test_the_order_entries_arrive_in_does_not_matter(self):
        audit.verify_chain(TENANT, list(reversed(chain())))

    def test_an_empty_chain_verifies_trivially(self):
        audit.verify_chain(TENANT, [])
        self.assertEqual(audit.head_of([]), (0, audit.GENESIS))

    def test_every_stored_field_is_covered_by_the_digest(self):
        """A field outside the digest is a field an administrator can edit undetected."""
        entries = chain(1)
        for field, value in (("on_behalf_of", "someone-else"), ("resource_id", "r-9"),
                             ("actor_identity_id", "a-9"), ("correlation_id", "c-9"),
                             ("outcome", "denied"), ("category", "finance")):
            tampered = audit.Entry(**{**entries[0].__dict__, field: value})
            with self.assertRaises(audit.AuditError) as caught:
                audit.verify_chain(TENANT, [tampered])
            self.assertEqual(caught.exception.code, "content_changed", field)

    def test_a_changed_payload_breaks_its_own_digest(self):
        entries = chain()
        tampered = audit.Entry(**{**entries[1].__dict__, "action": "role.revoked"})
        with self.assertRaises(audit.AuditError) as caught:
            audit.verify_chain(TENANT, [entries[0], tampered, entries[2]])
        self.assertEqual(caught.exception.code, "content_changed")
        self.assertEqual(caught.exception.at, 2)

    def test_a_deletion_from_the_middle_shows_as_a_gap(self):
        entries = chain()
        with self.assertRaises(audit.AuditError) as caught:
            audit.verify_chain(TENANT, [entries[0], entries[2]])
        self.assertEqual(caught.exception.code, "gap")

    def test_a_rewritten_link_is_caught(self):
        entries = chain()
        broken = audit.Entry(**{**entries[2].__dict__, "prev_hash": b"\x99" * 32})
        with self.assertRaises(audit.AuditError) as caught:
            audit.verify_chain(TENANT, [entries[0], entries[1], broken])
        self.assertEqual(caught.exception.code, "broken_link")

    def test_the_chain_is_anchored_so_the_first_entry_cannot_be_rewritten(self):
        entries = chain()
        loose = audit.Entry(**{**entries[0].__dict__, "prev_hash": b"\x77" * 32})
        with self.assertRaises(audit.AuditError) as caught:
            audit.verify_chain(TENANT, [loose, entries[1], entries[2]])
        self.assertEqual(caught.exception.code, "broken_link")

    def test_an_entry_cannot_be_moved_to_another_tenant(self):
        with self.assertRaises(audit.AuditError):
            audit.verify_chain("22222222-2222-4222-8222-222222222222", chain())

    def test_an_entry_cannot_be_reordered_within_a_tenant(self):
        """The sequence is inside the digest, so swapping two entries invalidates both."""
        first, second = entry(1, audit.GENESIS), entry(2, audit.GENESIS)
        self.assertNotEqual(first.entry_hash, second.entry_hash)

    def test_the_head_is_the_last_entry(self):
        entries = chain(4)
        sequence, digest = audit.head_of(entries)
        self.assertEqual((sequence, digest), (4, entries[-1].entry_hash))

    def test_canonical_form_does_not_depend_on_key_order(self):
        self.assertEqual(audit.canonical({"b": 1, "a": 2}), audit.canonical({"a": 2, "b": 1}))

    def test_a_malformed_previous_digest_is_refused(self):
        with self.assertRaises(audit.AuditError):
            audit.entry_digest(TENANT, 1, b"short", {})
        with self.assertRaises(audit.AuditError):
            audit.entry_digest(TENANT, 0, audit.GENESIS, {})


class ApprovalPolicyTests(unittest.TestCase):
    POLICIES = [
        approval.ApprovalPolicy("billing.refund.issue", threshold_minor=10_000,
                                required_permissions=frozenset({"billing.refund.approve"}),
                                required_approvals=1),
        approval.ApprovalPolicy("billing.refund.issue", threshold_minor=1_000_000,
                                required_permissions=frozenset({"billing.refund.approve"}),
                                required_approvals=2),
    ]

    def test_below_every_threshold_no_approval_is_required(self):
        self.assertFalse(approval.requires_approval(self.POLICIES, "billing.refund.issue", 500))

    def test_the_strictest_applicable_threshold_wins_not_the_first_row(self):
        small = approval.policy_for(self.POLICIES, "billing.refund.issue", 50_000)
        large = approval.policy_for(self.POLICIES, "billing.refund.issue", 5_000_000)
        self.assertEqual(small.required_approvals, 1)
        self.assertEqual(large.required_approvals, 2)

    def test_row_order_does_not_change_the_answer(self):
        self.assertEqual(
            approval.policy_for(list(reversed(self.POLICIES)), "billing.refund.issue",
                                5_000_000).required_approvals,
            2,
        )

    def test_an_action_with_no_policy_needs_no_approval(self):
        self.assertIsNone(approval.policy_for(self.POLICIES, "config.flag.write", 10**9))


class SeparationOfDutiesTests(unittest.TestCase):
    POLICY = approval.ApprovalPolicy("billing.refund.issue",
                                     required_permissions=frozenset({"billing.refund.approve"}),
                                     required_approvals=2)

    def test_the_requester_may_not_decide_their_own_request(self):
        with self.assertRaises(approval.ApprovalError) as caught:
            approval.check_decider(self.POLICY, requested_by="alice", decided_by="alice",
                                   decider_permissions=frozenset({"billing.refund.approve"}))
        self.assertEqual(caught.exception.code, "separation_of_duties")

    def test_a_decider_must_hold_every_permission_the_policies_require(self):
        """Two policies at the same strictness naming different permissions means both."""
        both = approval.ApprovalPolicy(
            "billing.refund.issue",
            required_permissions=frozenset({"billing.refund.approve", "billing.invoice.read"}),
        )
        with self.assertRaises(approval.ApprovalError):
            approval.check_decider(both, requested_by="alice", decided_by="bob",
                                   decider_permissions=frozenset({"billing.refund.approve"}))
        approval.check_decider(
            both, requested_by="alice", decided_by="bob",
            decider_permissions=frozenset({"billing.refund.approve", "billing.invoice.read"}))

    def test_a_decider_without_the_permission_is_refused(self):
        with self.assertRaises(approval.ApprovalError) as caught:
            approval.check_decider(self.POLICY, requested_by="alice", decided_by="bob",
                                   decider_permissions=frozenset())
        self.assertEqual(caught.exception.code, "decider_lacks_permission")

    def test_a_different_person_with_the_permission_may_decide(self):
        approval.check_decider(self.POLICY, requested_by="alice", decided_by="bob",
                               decider_permissions=frozenset({"billing.refund.approve"}))

    def test_separation_can_be_switched_off_for_a_policy_that_says_so(self):
        relaxed = approval.ApprovalPolicy("config.flag.write", separation_of_duties=False)
        approval.check_decider(relaxed, requested_by="alice", decided_by="alice",
                               decider_permissions=frozenset())


class ApprovalResolutionTests(unittest.TestCase):
    LATER = NOW + timedelta(days=1)

    def resolve(self, decisions, required=2, expires=None):
        return approval.resolve(required_approvals=required, decisions=decisions,
                                expires_at=expires or self.LATER, now=NOW)

    def test_too_few_approvals_stays_pending(self):
        self.assertEqual(self.resolve([approval.Decision("bob", "approved")]), "pending")

    def test_enough_approvals_from_different_people_approves(self):
        self.assertEqual(
            self.resolve([approval.Decision("bob", "approved"),
                          approval.Decision("carol", "approved")]), "approved")

    def test_one_person_cannot_make_up_the_count(self):
        self.assertEqual(
            self.resolve([approval.Decision("bob", "approved"),
                          approval.Decision("bob", "approved")]), "pending")

    def test_a_single_rejection_settles_it_over_any_number_of_approvals(self):
        self.assertEqual(
            self.resolve([approval.Decision("bob", "approved"),
                          approval.Decision("carol", "approved"),
                          approval.Decision("dave", "rejected")]), "rejected")

    def test_expiry_is_checked_before_approval(self):
        self.assertEqual(
            self.resolve([approval.Decision("bob", "approved"),
                          approval.Decision("carol", "approved")], expires=NOW), "expired")

    def test_a_rejection_outranks_expiry_so_the_reason_is_not_lost(self):
        self.assertEqual(self.resolve([approval.Decision("bob", "rejected")], expires=NOW),
                         "rejected")


if __name__ == "__main__":
    unittest.main()


class ReviewRegressionTests(unittest.TestCase):
    """One test per finding from the independent review, written as the attack that must fail."""

    def authorize(self, policies, assignments=None, attributes=None, action=None):
        return authz.authorize(
            authz.Request(action or "member.profile.read", attributes=attributes or {}),
            list(assignments if assignments is not None else [role()]),
            list(policies), now=NOW,
        )

    def test_b1_a_deny_is_not_evaded_by_omitting_the_attribute_it_names(self):
        """Leaving `is_minor` out of the request used to turn the deny off."""
        protect = authz.Policy("protect_minors", "deny", "member.profile.read",
                               match={"is_minor": "true"})
        self.assertFalse(self.authorize([protect], attributes={"is_minor": "true"}).allowed)
        self.assertFalse(self.authorize([protect], attributes={}).allowed,
                         "an unstated attribute must not excuse a deny")
        self.assertTrue(self.authorize([protect], attributes={"is_minor": "false"}).allowed,
                        "only a positive contradiction gets past it")

    def test_b1b_a_mask_is_not_evaded_by_omitting_the_attribute_it_names(self):
        mask = authz.Policy("mask_clinical", "mask", "member.profile.read",
                            match={"record_type": "clinical"},
                            masked_fields=("health_notes", "national_id"))
        with_attribute = self.authorize([mask], attributes={"record_type": "clinical"})
        without = self.authorize([mask], attributes={})
        contradicted = self.authorize([mask], attributes={"record_type": "contact"})
        self.assertEqual(with_attribute.masked_fields, ("health_notes", "national_id"))
        self.assertEqual(without.masked_fields, ("health_notes", "national_id"),
                         "an unstated attribute must not unmask")
        self.assertEqual(contradicted.masked_fields, ())

    def test_b1c_an_allow_still_needs_its_attribute_present(self):
        """The asymmetry is the point: an unknown attribute must not grant either."""
        allow = authz.Policy("assigned_only", "allow", "member.profile.read",
                             match={"assigned_to": "me"})
        self.assertFalse(self.authorize([allow], assignments=[]).allowed)
        self.assertTrue(
            self.authorize([allow], assignments=[], attributes={"assigned_to": "me"}).allowed)

    def test_b2_a_brand_scope_cannot_be_stretched_by_naming_the_wrong_brand(self):
        """`Scope.covers` is only safe because `resolve_scope` derives the brand server-side."""
        held = authz.Scope("brand", brand_id="brand-a")
        honest = authz.Scope("location", brand_id="brand-b", location_id="gym-of-b")
        self.assertFalse(held.covers(honest))
        lied = authz.Scope("location", brand_id="brand-a", location_id="gym-of-b")
        self.assertTrue(held.covers(lied),
                        "the comparison itself cannot tell -- which is why the brand must be"
                        " resolved from the location rather than supplied beside it")

    def test_b3_the_strictest_terms_govern_whatever_order_the_policies_are_in(self):
        """A lenient policy above a strict one used to silently govern the larger amount."""
        strict = approval.ApprovalPolicy("billing.refund.issue", threshold_minor=0,
                                         required_permissions=frozenset({"billing.refund.approve"}),
                                         required_approvals=2, separation_of_duties=True)
        lenient = approval.ApprovalPolicy("billing.refund.issue", threshold_minor=1,
                                          required_permissions=frozenset(
                                              {"billing.refund.approve"}),
                                          required_approvals=1, separation_of_duties=False)
        for order in ([strict, lenient], [lenient, strict]):
            combined = approval.policy_for(order, "billing.refund.issue", 1_000_000)
            self.assertEqual(combined.required_approvals, 2, order)
            self.assertTrue(combined.separation_of_duties, order)

    def test_c3_the_required_permissions_are_the_union_whatever_the_order(self):
        """A single column had to choose on a tie, and chose by row order."""
        first = approval.ApprovalPolicy(
            "billing.refund.issue", required_approvals=2,
            required_permissions=frozenset({"billing.refund.approve"}))
        second = approval.ApprovalPolicy(
            "billing.refund.issue", required_approvals=2,
            required_permissions=frozenset({"billing.invoice.read"}))
        for order in ([first, second], [second, first]):
            combined = approval.policy_for(order, "billing.refund.issue", 0)
            self.assertEqual(combined.required_permissions,
                             frozenset({"billing.refund.approve", "billing.invoice.read"}),
                             order)

    def test_b3b_separation_of_duties_survives_any_policy_that_demands_it(self):
        off = approval.ApprovalPolicy("a.b.c", separation_of_duties=False)
        on = approval.ApprovalPolicy("a.b.c", separation_of_duties=True)
        self.assertTrue(approval.policy_for([off, on], "a.b.c", 0).separation_of_duties)

    def test_b5_on_behalf_of_is_inside_the_digest(self):
        """The field recording an agent acting as a member is the one worth forging."""
        entries = chain(1)
        forged = audit.Entry(**{**entries[0].__dict__, "on_behalf_of": "the-member"})
        with self.assertRaises(audit.AuditError) as caught:
            audit.verify_chain(TENANT, [forged])
        self.assertEqual(caught.exception.code, "content_changed")


class ApprovalStageTests(unittest.TestCase):
    """AUT-02-R05's last word: "sequential, parallel".

    **The combination rule is the thing worth testing hardest.** `policy_for` combines every
    applicable policy and never chooses between them; a stage *list* reintroduces the row-order
    dependence that rule exists to remove, which is why a stage is a permission and a count
    rather than a position. Every assertion about order here is written as "the answer does not
    depend on which policy came first", because that is the property rather than a consequence
    of it.
    """

    LATER = NOW + timedelta(days=1)

    MANAGER = approval.ApprovalPolicy(
        "billing.refund.issue", threshold_minor=10_000,
        required_permissions=frozenset({"billing.refund.approve"}),
        stages=(approval.Stage(1, "billing.refund.approve", 1),), sequential=True)
    FINANCE = approval.ApprovalPolicy(
        "billing.refund.issue", threshold_minor=1_000_000,
        required_permissions=frozenset({"finance.export.run"}),
        stages=(approval.Stage(2, "finance.export.run", 1),))

    def test_unstaged_policies_combine_to_no_stages_at_all(self):
        """**"Staged" means somebody declared stages**, which is what keeps the response and
        the request's snapshot answering the question the same way -- and keeps every policy
        written before `0006` behaving exactly as it did."""
        plain = approval.ApprovalPolicy(
            "billing.refund.issue",
            required_permissions=frozenset({"billing.refund.approve"}),
            required_approvals=2)
        combined = approval.policy_for([plain], "billing.refund.issue", 50_000)
        self.assertEqual(combined.stages, ())
        self.assertEqual(combined.required_approvals, 2)
        self.assertFalse(combined.sequential)

    def test_a_policy_with_no_stages_is_a_single_stage_policy(self):
        """**The absence is the existing meaning**, which is why the migration backfills
        nothing and nothing already written changes behaviour."""
        plain = approval.ApprovalPolicy(
            "billing.refund.issue",
            required_permissions=frozenset({"billing.refund.approve"}),
            required_approvals=2)
        self.assertEqual(
            approval.stages_of(plain),
            (approval.Stage(1, "billing.refund.approve", 2),))

    def test_two_policies_combine_into_two_stages_in_either_order(self):
        forwards = approval.policy_for(
            [self.MANAGER, self.FINANCE], "billing.refund.issue", 5_000_000)
        backwards = approval.policy_for(
            [self.FINANCE, self.MANAGER], "billing.refund.issue", 5_000_000)
        self.assertEqual(forwards.stages, backwards.stages)
        self.assertEqual(
            [(s.ordinal, s.required_permission) for s in forwards.stages],
            [(1, "billing.refund.approve"), (2, "finance.export.run")])
        # `sequential` is `any()`, like separation of duties: a lenient policy must not switch
        # a strict one's sequencing off.
        self.assertTrue(forwards.sequential)
        self.assertTrue(backwards.sequential)

    def test_the_same_permission_twice_is_one_stage_at_the_larger_count(self):
        """Two policies both naming a stage for the same authority is a quorum, not two
        steps -- and two rows saying it would be two definitions of the count."""
        two = approval.ApprovalPolicy(
            "billing.refund.issue",
            required_permissions=frozenset({"billing.refund.approve"}),
            stages=(approval.Stage(1, "billing.refund.approve", 2),))
        combined = approval.policy_for(
            [self.MANAGER, two], "billing.refund.issue", 50_000)
        self.assertEqual(len(combined.stages), 1)
        # **And the count survives the collapse**, which an earlier version lost: reporting a
        # one-stage combination as unstaged read its count off `required_approvals`, which is
        # 1 on both of these policies while the stage asks for 2.
        self.assertEqual(combined.stages[0].required_approvals, 2)
        self.assertEqual(combined.required_approvals, 1)

    def test_the_ordinals_are_renumbered_so_a_gap_cannot_reach_the_request(self):
        """A policy may legitimately number its stages 1 and 5; the request's snapshot is
        1..N, because `sequential` walks "every earlier stage" and a gap would make "earlier"
        depend on how somebody numbered a row."""
        sparse = approval.ApprovalPolicy(
            "billing.refund.issue",
            required_permissions=frozenset({"finance.export.run"}),
            stages=(approval.Stage(5, "finance.export.run", 1),))
        combined = approval.policy_for(
            [self.MANAGER, sparse], "billing.refund.issue", 50_000)
        self.assertEqual([s.ordinal for s in combined.stages], [1, 2])

    def test_a_plain_policy_beside_a_staged_one_contributes_its_own_stage(self):
        plain = approval.ApprovalPolicy(
            "billing.refund.issue",
            required_permissions=frozenset({"authz.role.write"}), required_approvals=3)
        combined = approval.policy_for(
            [self.MANAGER, plain], "billing.refund.issue", 50_000)
        self.assertEqual(
            {(s.required_permission, s.required_approvals) for s in combined.stages},
            {("billing.refund.approve", 1), ("authz.role.write", 3)})

    def test_the_combined_order_respects_every_policy_rather_than_the_highest_ordinal(self):
        """**A three-policy cycle is the case no pairwise check sees.** A before B, B before C
        and C before A each agree with the others on their one shared permission -- and taking
        the highest ordinal each permission was given then makes all three equal, so the result
        falls back to the alphabet and a policy's stated order is silently violated. That is
        the row-order dependence `policy_for` exists to remove, wearing a different hat."""
        def staged(*pairs):
            return approval.ApprovalPolicy(
                "billing.refund.issue",
                required_permissions=frozenset({pairs[0][1]}),
                stages=tuple(approval.Stage(n, name, 1) for n, name in pairs))
        a, b, c = "aaa.aaa.aaa", "bbb.bbb.bbb", "ccc.ccc.ccc"
        cycle = [staged((1, a), (2, b)), staged((1, b), (2, c)), staged((1, c), (2, a))]
        self.assertIsNotNone(approval.order_conflict(cycle))
        # And a chain that *is* orderable comes out in the order every policy asked for, not
        # in the order the maxima happen to give.
        chain = [staged((1, a), (2, b)), staged((1, b), (2, c))]
        self.assertIsNone(approval.order_conflict(chain))
        combined = approval.policy_for(chain, "billing.refund.issue", 0)
        self.assertEqual([st.required_permission for st in combined.stages], [a, b, c])
        # Order-independent, which is the property rather than a consequence of it.
        self.assertEqual(
            approval.policy_for(list(reversed(chain)), "billing.refund.issue", 0).stages,
            combined.stages)

    def test_a_pair_ordered_both_ways_is_a_two_cycle_and_needs_no_second_check(self):
        """**The simple case the cycle check already answers.** An earlier version looked for
        this pair first and then for a cycle; the mutation sweep reported the pair check as
        uncaught, correctly -- a pair ordered both ways *is* a two-cycle. Deleted rather than
        tested harder, and this is the assertion that the remaining check still catches it."""
        def staged(*pairs):
            return approval.ApprovalPolicy(
                "billing.refund.issue",
                required_permissions=frozenset({pairs[0][1]}),
                stages=tuple(approval.Stage(n, name, 1) for n, name in pairs))
        a, b = "aaa.aaa.aaa", "bbb.bbb.bbb"
        self.assertEqual(
            approval.order_conflict([staged((1, a), (2, b)), staged((1, b), (2, a))]),
            (a, b))

    # ---- what a stage refuses

    def stages(self):
        return (approval.Stage(1, "billing.refund.approve", 1),
                approval.Stage(2, "finance.export.run", 1))

    def test_a_sequential_second_stage_is_shut_until_the_first_is_approved(self):
        with self.assertRaises(approval.ApprovalError) as refused:
            approval.check_stage(
                self.stages(), stage_ordinal=2, decisions=[], sequential=True,
                decider_permissions=frozenset({"finance.export.run"}))
        self.assertEqual(refused.exception.code, "stage_not_open")

    def test_a_parallel_second_stage_is_open_from_the_start(self):
        """The whole difference between the two words R05 names."""
        approval.check_stage(
            self.stages(), stage_ordinal=2, decisions=[], sequential=False,
            decider_permissions=frozenset({"finance.export.run"}))

    def test_the_second_stage_opens_once_the_first_has_its_count(self):
        approval.check_stage(
            self.stages(), stage_ordinal=2,
            decisions=[approval.Decision("bob", "approved", 1)], sequential=True,
            decider_permissions=frozenset({"finance.export.run"}))

    def test_a_decider_without_this_stage_permission_is_refused(self):
        """**What makes a stage a kind of approver rather than one more body.** `check_decider`
        charges every permission the combined policies name; this charges the one this step is
        for, and holding the other stage's is not holding this one's."""
        with self.assertRaises(approval.ApprovalError) as refused:
            approval.check_stage(
                self.stages(), stage_ordinal=2, decisions=[], sequential=False,
                decider_permissions=frozenset({"billing.refund.approve"}))
        self.assertEqual(refused.exception.code, "decider_lacks_stage_permission")

    def test_a_stage_the_request_has_not_got_is_refused(self):
        with self.assertRaises(approval.ApprovalError) as refused:
            approval.check_stage(
                self.stages(), stage_ordinal=7, decisions=[], sequential=False,
                decider_permissions=frozenset({"finance.export.run"}))
        self.assertEqual(refused.exception.code, "no_such_stage")

    def test_a_single_stage_request_admits_ordinal_one_and_nothing_else(self):
        """The one admissible absence: a policy with no stages is a single-stage policy, so a
        request carrying no stage rows has exactly stage 1."""
        approval.check_stage(
            (), stage_ordinal=1, decisions=[], sequential=False,
            decider_permissions=frozenset())
        with self.assertRaises(approval.ApprovalError) as refused:
            approval.check_stage(
                (), stage_ordinal=2, decisions=[], sequential=False,
                decider_permissions=frozenset())
        self.assertEqual(refused.exception.code, "no_such_stage")

    # ---- what a staged request resolves to

    def resolve(self, decisions, stages=(), required=2):
        return approval.resolve(required_approvals=required, decisions=decisions,
                                expires_at=self.LATER, now=NOW, stages=stages)

    def test_every_stage_has_to_have_its_count_not_the_total(self):
        """**The defect this is written against:** three signatures on stage 1 satisfying a
        two-stage approval would make "a club manager and then finance" mean "two people"."""
        stages = self.stages()
        piled = [approval.Decision("bob", "approved", 1),
                 approval.Decision("carol", "approved", 1),
                 approval.Decision("dana", "approved", 1)]
        self.assertEqual(self.resolve(piled, stages), "pending")
        self.assertEqual(
            self.resolve(piled + [approval.Decision("eve", "approved", 2)], stages),
            "approved")

    def test_a_rejection_anywhere_settles_the_whole_request(self):
        """A stage is a condition rather than a vote, so there is no stage to localise a
        rejection to."""
        self.assertEqual(
            self.resolve([approval.Decision("bob", "approved", 1),
                          approval.Decision("carol", "rejected", 2)], self.stages()),
            "rejected")

    def test_expiry_is_still_checked_before_approval(self):
        self.assertEqual(
            approval.resolve(
                required_approvals=1,
                decisions=[approval.Decision("bob", "approved", 1),
                           approval.Decision("carol", "approved", 2)],
                expires_at=NOW, now=NOW, stages=self.stages()),
            "expired")

    def test_an_unstaged_request_resolves_exactly_as_it_did(self):
        """No stages, no change -- which is what makes the migration a no-op for every request
        already recorded."""
        self.assertEqual(
            self.resolve([approval.Decision("bob", "approved"),
                          approval.Decision("carol", "approved")]),
            "approved")
        self.assertEqual(self.resolve([approval.Decision("bob", "approved")]), "pending")

    def test_the_schema_and_this_module_agree_about_the_ceiling(self):
        """A decision function and a CHECK that disagree about a bound is two encodings of one
        rule, which is MOD-020's waitlist edge."""
        migration = (pathlib.Path(__file__).resolve().parent.parent
                     / "migrations" / "product" / "0006_approval_stages.sql").read_text()
        self.assertIn(f"ordinal BETWEEN 1 AND {approval.MAX_STAGES}", migration)

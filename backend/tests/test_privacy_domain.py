"""MOD-009 pure-domain tests: classification, consent, retention and the DSAR machine.

No database. Every decision in `app/privacy/` that is not I/O is decided by one of these four
modules, and each is a function of its arguments, so these tests are the specification of what
the module believes. The integration suite proves the service writes what these decide; it does
not re-decide it.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.privacy import classification as cls
from app.privacy import consent, dsar, retention

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _version(vid="v1", definition="d1", number=1, language="en", effective=None):
    return consent.Version(
        consent_version_id=vid, definition_id=definition, version=number, language=language,
        document_hash="a" * 64, effective_from=effective or (NOW - timedelta(days=30)),
    )


def _record(action="granted", vid="v1", definition="d1", signed=None, guardian=None, rid="r1"):
    return consent.Record(
        record_id=rid, subject_id="s1", definition_id=definition, consent_version_id=vid,
        action=action, signed_at=signed or (NOW - timedelta(days=1)),
        guardian_subject_id=guardian,
    )


class ClassificationTests(unittest.TestCase):
    def test_the_four_classes_are_ordered_from_public_to_restricted(self):
        self.assertEqual(cls.CLASSES, ("public", "internal", "confidential", "restricted"))
        self.assertTrue(cls.at_least("restricted", "confidential"))
        self.assertFalse(cls.at_least("internal", "confidential"))
        self.assertTrue(cls.at_least("internal", "internal"))

    def test_an_unknown_class_raises_rather_than_comparing_false(self):
        """Returning False for a typo would silently turn a control off."""
        with self.assertRaises(ValueError):
            cls.at_least("secret", "internal")
        with self.assertRaises(ValueError):
            cls.at_least("internal", "secret")

    def test_the_sensitive_kinds_all_map_to_a_class(self):
        """The two registries must stay joined: a kind MOD-008 knows and this does not would
        silently classify a national id as ordinary."""
        from app.authorization.catalog import SENSITIVE_FIELDS

        for field, kind in SENSITIVE_FIELDS.items():
            self.assertIn(kind, cls.KIND_CLASS, f"{field} has kind {kind} with no class")

    def test_an_unclassified_field_is_internal_not_public(self):
        self.assertEqual(cls.classify_field("favourite_colour"), "internal")
        self.assertEqual(cls.classify_field("national_id"), "restricted")
        self.assertEqual(cls.classify_field("email"), "confidential")

    def test_a_record_takes_the_class_of_its_most_restricted_field(self):
        self.assertEqual(cls.classify_resource(["name", "email"]), "confidential")
        self.assertEqual(cls.classify_resource(["name", "email", "iban"]), "restricted")
        self.assertEqual(cls.classify_resource(["name"]), "internal")
        self.assertEqual(cls.classify_resource([]), "internal")

    def test_only_restricted_data_needs_a_declared_purpose(self):
        """TSD paragraph 4383: having access is insufficient without a permitted purpose."""
        self.assertTrue(cls.purpose_required("restricted"))
        self.assertFalse(cls.purpose_required("confidential"))
        self.assertFalse(cls.purpose_required("internal"))

    def test_every_registry_entry_declares_a_known_mechanism_and_a_reason(self):
        for r in cls.SUBJECT_COLUMNS:
            self.assertIn(r.mechanism, cls.MECHANISMS)
            self.assertTrue(r.reason.strip())

    def test_this_build_reports_erasure_as_incomplete(self):
        """The disclosure is a value, not a comment, so code can act on it."""
        self.assertFalse(cls.deletion_is_complete())
        self.assertTrue(cls.unreachable_columns())
        self.assertTrue(cls.reachable_columns())


class ConsentStateTests(unittest.TestCase):
    def test_no_records_is_not_granted(self):
        self.assertFalse(consent.state_of([], "d1", "v1").granted)

    def test_a_grant_is_in_force(self):
        state = consent.state_of([_record()], "d1", "v1")
        self.assertTrue(state.granted)
        self.assertFalse(state.stale)

    def test_a_withdrawal_after_a_grant_wins(self):
        records = [_record(rid="r1", signed=NOW - timedelta(days=5)),
                   _record(action="withdrawn", rid="r2", signed=NOW - timedelta(days=1))]
        self.assertFalse(consent.state_of(records, "d1", "v1").granted)

    def test_a_regrant_after_a_withdrawal_wins(self):
        records = [_record(action="withdrawn", rid="r1", signed=NOW - timedelta(days=5)),
                   _record(rid="r2", signed=NOW - timedelta(days=1))]
        self.assertTrue(consent.state_of(records, "d1", "v1").granted)

    def test_order_is_by_when_it_was_signed_not_when_it_was_written(self):
        """The paper-waiver case: a withdrawal signed on Sunday beats a grant signed Saturday,
        even though the grant's row was written later when the paper was digitised."""
        saturday = NOW - timedelta(days=3)
        sunday = NOW - timedelta(days=2)
        records = [
            consent.Record("r-withdraw", "s1", "d1", "v1", "withdrawn", sunday),
            consent.Record("r-paper", "s1", "d1", "v1", "granted", saturday),
        ]
        self.assertFalse(consent.state_of(records, "d1", "v1").granted,
                         "the later signature must win regardless of insertion order")

    def test_consent_to_an_older_version_is_stale_but_still_granted(self):
        state = consent.state_of([_record(vid="v1")], "d1", current_version_id="v2")
        self.assertTrue(state.granted, "a real agreement is not erased by republishing")
        self.assertTrue(state.stale, "but it does not extend to a document never seen")

    def test_a_withdrawal_is_never_reported_stale(self):
        state = consent.state_of([_record(action="withdrawn")], "d1", "v2")
        self.assertFalse(state.granted)
        self.assertFalse(state.stale)

    def test_records_for_another_consent_type_are_ignored(self):
        self.assertFalse(consent.state_of([_record(definition="other")], "d1", "v1").granted)


class ConsentVersionTests(unittest.TestCase):
    def test_the_highest_effective_version_is_in_force(self):
        versions = [_version("v1", number=1), _version("v2", number=2)]
        self.assertEqual(consent.current_version(versions, "d1", "en", NOW).consent_version_id,
                         "v2")

    def test_a_future_version_is_published_but_not_in_force(self):
        versions = [_version("v1", number=1),
                    _version("v2", number=2, effective=NOW + timedelta(days=7))]
        self.assertEqual(consent.current_version(versions, "d1", "en", NOW).consent_version_id,
                         "v1", "notice of a change is not the change")

    def test_languages_are_tracked_separately(self):
        versions = [_version("en1", number=1, language="en"),
                    _version("ar1", number=1, language="ar")]
        self.assertEqual(consent.current_version(versions, "d1", "ar", NOW).consent_version_id,
                         "ar1")
        self.assertIsNone(consent.current_version(versions, "d1", "fr", NOW))


class ConsentGrantTests(unittest.TestCase):
    def definition(self, **kw):
        base = dict(definition_id="d1", consent_type="health", requires_guardian=False,
                    withdrawable=True)
        base.update(kw)
        return consent.Definition(**base)

    def test_a_sound_grant_passes(self):
        consent.check_grant(self.definition(), _version(), guardian_subject_id=None,
                            subject_id="s1", signed_at=NOW - timedelta(days=1), now=NOW)

    def test_a_version_of_another_consent_type_is_refused(self):
        with self.assertRaises(consent.ConsentError) as raised:
            consent.check_grant(self.definition(), _version(definition="other"),
                                guardian_subject_id=None, subject_id="s1",
                                signed_at=NOW, now=NOW)
        self.assertEqual(str(raised.exception), "version_belongs_to_another_consent_type")

    def test_a_guardian_consent_without_a_guardian_is_refused(self):
        with self.assertRaises(consent.ConsentError) as raised:
            consent.check_grant(self.definition(requires_guardian=True), _version(),
                                guardian_subject_id=None, subject_id="s1",
                                signed_at=NOW, now=NOW)
        self.assertEqual(str(raised.exception), "guardian_required")

    def test_the_guardian_may_not_be_the_subject(self):
        with self.assertRaises(consent.ConsentError) as raised:
            consent.check_grant(self.definition(requires_guardian=True), _version(),
                                guardian_subject_id="s1", subject_id="s1",
                                signed_at=NOW, now=NOW)
        self.assertEqual(str(raised.exception), "guardian_cannot_be_the_subject")

    def test_a_signature_dated_in_the_future_is_refused(self):
        """It would outrank every real record indefinitely under the ordering rule."""
        with self.assertRaises(consent.ConsentError) as raised:
            consent.check_grant(self.definition(), _version(), guardian_subject_id=None,
                                subject_id="s1", signed_at=NOW + timedelta(days=1), now=NOW)
        self.assertEqual(str(raised.exception), "signed_in_the_future")

    def test_a_signature_before_the_document_existed_is_refused(self):
        version = _version(effective=NOW - timedelta(days=2))
        with self.assertRaises(consent.ConsentError) as raised:
            consent.check_grant(self.definition(), version, guardian_subject_id=None,
                                subject_id="s1", signed_at=NOW - timedelta(days=10), now=NOW)
        self.assertEqual(str(raised.exception), "signed_before_the_document_was_effective")

    def test_withdrawing_what_was_never_granted_is_refused(self):
        state = consent.state_of([], "d1", "v1")
        with self.assertRaises(consent.ConsentError) as raised:
            consent.check_withdrawal(self.definition(), state)
        self.assertEqual(str(raised.exception), "not_currently_granted")

    def test_a_non_withdrawable_consent_refuses_withdrawal(self):
        state = consent.state_of([_record()], "d1", "v1")
        with self.assertRaises(consent.ConsentError) as raised:
            consent.check_withdrawal(self.definition(withdrawable=False), state)
        self.assertEqual(str(raised.exception), "consent_is_not_withdrawable")


class OutstandingConsentTests(unittest.TestCase):
    def test_never_granted_and_stale_both_surface_with_their_reason(self):
        definitions = [
            consent.Definition("d1", "terms", False, False),
            consent.Definition("d2", "marketing", False, True),
        ]
        versions = [_version("v1", "d1", 1), _version("v2", "d1", 2), _version("m1", "d2", 1)]
        records = [_record(vid="v1", definition="d1")]
        rows = consent.outstanding(definitions, versions, records, language="en", now=NOW)
        by_type = {r["consent_type"]: r for r in rows}
        self.assertEqual(by_type["terms"]["reason"], "stale")
        self.assertEqual(by_type["marketing"]["reason"], "never_granted")

    def test_a_current_grant_does_not_surface(self):
        definitions = [consent.Definition("d1", "terms", False, False)]
        rows = consent.outstanding(definitions, [_version("v1", "d1", 1)],
                                   [_record(vid="v1")], language="en", now=NOW)
        self.assertEqual(rows, [])


class RetentionTests(unittest.TestCase):
    def policy(self, days=30, **kw):
        base = dict(policy_id="p1", resource_type="session_log", data_class="internal",
                    retention_days=days, legal_basis="legitimate_interest", region="jo")
        base.update(kw)
        return retention.Policy(**base)

    def hold(self, **kw):
        base = dict(hold_id="h1", subject_id=None, resource_type=None, reason="litigation",
                    reference="CASE-1")
        base.update(kw)
        return retention.Hold(**base)

    def test_a_record_inside_its_retention_period_is_kept(self):
        verdict = retention.may_delete([self.policy()], [], resource_type="session_log",
                                       region="jo", created_at=NOW - timedelta(days=5), now=NOW)
        self.assertFalse(verdict.deletable)
        self.assertEqual(verdict.reason, "within_retention")
        self.assertIsNotNone(verdict.expires_at)

    def test_a_record_past_its_retention_period_is_deletable(self):
        verdict = retention.may_delete([self.policy()], [], resource_type="session_log",
                                       region="jo", created_at=NOW - timedelta(days=31), now=NOW)
        self.assertTrue(verdict.deletable)
        self.assertEqual(verdict.reason, "retention_expired")

    def test_a_missing_policy_refuses_rather_than_assuming_either_way(self):
        verdict = retention.may_delete([], [], resource_type="session_log", region="jo",
                                       created_at=NOW - timedelta(days=9999), now=NOW)
        self.assertFalse(verdict.deletable)
        self.assertEqual(verdict.reason, "no_retention_policy")

    def test_a_retired_policy_is_not_used(self):
        verdict = retention.may_delete([self.policy(retired=True)], [],
                                       resource_type="session_log", region="jo",
                                       created_at=NOW - timedelta(days=99), now=NOW)
        self.assertEqual(verdict.reason, "no_retention_policy")

    def test_a_policy_in_another_region_does_not_apply(self):
        verdict = retention.may_delete([self.policy(region="ae")], [],
                                       resource_type="session_log", region="jo",
                                       created_at=NOW - timedelta(days=99), now=NOW)
        self.assertEqual(verdict.reason, "no_retention_policy")

    def test_a_legal_hold_outranks_an_expired_retention_period(self):
        verdict = retention.may_delete([self.policy()], [self.hold()],
                                       resource_type="session_log", region="jo",
                                       created_at=NOW - timedelta(days=999), now=NOW)
        self.assertFalse(verdict.deletable)
        self.assertEqual(verdict.reason, "legal_hold")
        self.assertEqual(verdict.blocking_hold_ids, ("h1",))

    def test_a_legal_hold_outranks_a_subject_request(self):
        """The uncomfortable case, and the correct one: erasure does not override preservation."""
        verdict = retention.may_delete([self.policy()], [self.hold()],
                                       resource_type="session_log", region="jo",
                                       created_at=NOW, now=NOW, on_request=True)
        self.assertFalse(verdict.deletable)
        self.assertEqual(verdict.reason, "legal_hold")

    def test_a_subject_request_does_not_wait_out_the_retention_period(self):
        verdict = retention.may_delete([self.policy()], [], resource_type="session_log",
                                       region="jo", created_at=NOW, now=NOW, on_request=True)
        self.assertTrue(verdict.deletable)
        self.assertEqual(verdict.reason, "subject_request")

    def test_a_released_hold_blocks_nothing(self):
        verdict = retention.may_delete([self.policy()], [self.hold(released=True)],
                                       resource_type="session_log", region="jo",
                                       created_at=NOW - timedelta(days=99), now=NOW)
        self.assertTrue(verdict.deletable)

    def test_a_hold_on_another_resource_does_not_block_this_one(self):
        verdict = retention.may_delete([self.policy()], [self.hold(resource_type="invoice")],
                                       resource_type="session_log", region="jo",
                                       created_at=NOW - timedelta(days=99), now=NOW)
        self.assertTrue(verdict.deletable)

    def test_an_unnamed_resource_matches_every_hold(self):
        """Fail closed: leaving a field out must not slip past a hold, which is the shape
        MOD-008's review found in the policy evaluator."""
        blocked = retention.blocking_holds([self.hold(resource_type="invoice")],
                                           subject_id="s1", resource_type=None)
        self.assertEqual(len(blocked), 1)

    def test_a_subject_hold_blocks_that_subject_only(self):
        holds = [self.hold(subject_id="s1")]
        self.assertFalse(retention.may_delete_subject(holds, subject_id="s1").deletable)
        self.assertTrue(retention.may_delete_subject(holds, subject_id="s2").deletable)

    def test_a_tenant_wide_hold_blocks_every_subject(self):
        holds = [self.hold(subject_id=None)]
        self.assertFalse(retention.may_delete_subject(holds, subject_id="anyone").deletable)

    def test_an_expiry_sweep_reports_the_records_it_cannot_delete(self):
        """Paragraph 4385: retention jobs do not silently ignore failures."""
        records = [("a", "session_log", NOW - timedelta(days=99)),
                   ("b", "session_log", NOW - timedelta(days=1)),
                   ("c", "unknown_kind", NOW - timedelta(days=99))]
        rows = retention.due_for_expiry([self.policy()], [], records, region="jo", now=NOW)
        self.assertEqual(len(rows), 3, "every record is reported, not only the deletable ones")
        by_id = {r["record_id"]: r for r in rows}
        self.assertTrue(by_id["a"]["deletable"])
        self.assertEqual(by_id["b"]["reason"], "within_retention")
        self.assertEqual(by_id["c"]["reason"], "no_retention_policy")


class DsarMachineTests(unittest.TestCase):
    def request(self, **kw):
        base = dict(request_id="q1", subject_id="s1", request_type="deletion", status="ready",
                    received_at=NOW - timedelta(days=1), due_at=NOW + timedelta(days=29),
                    identity_verified_at=NOW, legal_checked_at=NOW)
        base.update(kw)
        return dsar.Request(**base)

    def test_opening_computes_the_deadline_from_the_supplied_period(self):
        opened = dsar.open_request(request_type="access", received_at=NOW, response_days=30,
                                   now=NOW)
        self.assertEqual(opened["status"], "received")
        self.assertEqual(opened["due_at"], NOW + timedelta(days=30))

    def test_a_request_cannot_arrive_in_the_future(self):
        """The deadline is computed from `received_at`, so a caller that can set it freely sets
        the regulator-facing deadline and the overdue flag. A request dated forward is never
        late. Found by independent review; a paper request logged a few days after it arrived is
        the legitimate case, so the past stays allowed."""
        with self.assertRaises(dsar.DsarError) as caught:
            dsar.open_request(request_type="access", received_at=NOW + timedelta(seconds=1),
                              response_days=30, now=NOW)
        self.assertEqual(str(caught.exception), "received_in_the_future")
        backdated = dsar.open_request(request_type="access",
                                      received_at=NOW - timedelta(days=3),
                                      response_days=30, now=NOW)
        self.assertEqual(backdated["due_at"], NOW + timedelta(days=27))

    def test_no_deadline_is_defaulted(self):
        """The TSD refers to a DSAR SLA and never states one; inventing it here would make a
        legal claim this repository's sources do not support."""
        with self.assertRaises(TypeError):
            dsar.open_request(request_type="access", received_at=NOW,  # type: ignore[call-arg]
                              now=NOW)

    def test_an_implausible_or_absent_period_is_refused(self):
        for days in (0, -1, 366):
            with self.assertRaises(dsar.DsarError):
                dsar.open_request(request_type="access", received_at=NOW, response_days=days,
                                  now=NOW)

    def test_an_unknown_request_type_is_refused(self):
        with self.assertRaises(dsar.DsarError):
            dsar.open_request(request_type="forget_me", received_at=NOW, response_days=30,
                              now=NOW)

    def test_the_machine_moves_only_forward_and_only_one_step(self):
        dsar.check_transition("received", "identity_pending")
        with self.assertRaises(dsar.DsarError):
            dsar.check_transition("received", "ready")
        with self.assertRaises(dsar.DsarError):
            dsar.check_transition("identity_pending", "received")

    def test_a_terminal_state_cannot_be_left(self):
        for terminal in ("completed", "refused"):
            self.assertEqual(dsar.TRANSITIONS[terminal], ())
            with self.assertRaises(dsar.DsarError):
                dsar.check_transition(terminal, "fulfilling")

    def test_every_state_but_the_terminal_ones_can_be_refused(self):
        """A request must be refusable at any point before it is finished; a workflow that can
        only go forwards forces a bad request to be fulfilled."""
        for state, targets in dsar.TRANSITIONS.items():
            if state in ("completed", "refused"):
                continue
            self.assertIn("refused", targets, state)

    def test_fulfilment_needs_both_checks_regardless_of_the_status_column(self):
        with self.assertRaises(dsar.DsarError) as raised:
            dsar.check_ready_to_fulfil(self.request(identity_verified_at=None))
        self.assertEqual(str(raised.exception), "identity_not_verified")

        with self.assertRaises(dsar.DsarError) as raised:
            dsar.check_ready_to_fulfil(self.request(legal_checked_at=None))
        self.assertEqual(str(raised.exception), "legal_check_not_done")

    def test_a_status_set_without_the_facts_behind_it_does_not_pass(self):
        """The status is one column one UPDATE moves. The facts are what it summarises."""
        forged = self.request(status="ready", identity_verified_at=None, legal_checked_at=None)
        with self.assertRaises(dsar.DsarError):
            dsar.check_ready_to_fulfil(forged)

    def test_a_ready_request_with_both_checks_passes(self):
        dsar.check_ready_to_fulfil(self.request())

    def test_overdue_ignores_finished_requests(self):
        late = NOW + timedelta(days=60)
        self.assertTrue(dsar.overdue(self.request(), late))
        self.assertFalse(dsar.overdue(self.request(status="completed",
                                                   completed_at=NOW), late))
        self.assertFalse(dsar.overdue(self.request(), NOW))


def _target(schema: str, table: str, column: str, mechanism: str):
    """The slice of a `classification.Reachability` that `dsar.plan` reads."""
    return cls.Reachability(schema=schema, table=table, column=column,
                            mechanism=mechanism, reason="test")


class DsarPlanAndSettleTests(unittest.TestCase):
    def test_the_plan_shows_what_will_survive_the_deletion(self):
        plan = dsar.plan("deletion", [_target("iam", "devices", "identity_id", "anonymize")],
                         [_target("plt01", "bil_usage_records", "actor_id", "unreachable")])
        self.assertEqual([row["expected"] for row in plan], ["done", "blocked"])
        self.assertEqual(plan[1]["mechanism"], "pseudonymize")

    def test_the_plan_names_each_targets_own_mechanism_not_the_request_types(self):
        """It derived the mechanism from the request type, so a deletion was planned as `delete`
        for all seven reachable targets while the executor anonymized every one of them. The
        plan is what somebody reads before approving an erasure."""
        plan = dsar.plan("deletion",
                         [_target("iam", "devices", "identity_id", "anonymize"),
                          _target("iam", "role_assignments", "identity_id", "covered")],
                         [])
        self.assertEqual([row["mechanism"] for row in plan], ["anonymize", "covered"])

    def test_access_and_portability_both_export(self):
        self.assertEqual(dsar.MECHANISM_FOR["access"], "export")
        self.assertEqual(dsar.MECHANISM_FOR["portability"], "export")

    def test_a_clean_run_completes_with_no_residue(self):
        settled = dsar.settle("deletion", [dsar.Action("postgresql", "iam.devices", "delete",
                                                       "done", 3)])
        self.assertEqual(settled["status"], "completed")
        self.assertFalse(settled["has_residue"])
        self.assertIsNone(settled["residue_note"])
        self.assertEqual(settled["rows_affected"], 3)

    def test_a_blocked_target_completes_the_request_and_names_the_residue(self):
        """A subject told their data was erased, while rows naming them remain in a ledger that
        cannot be rewritten, has been told something false."""
        settled = dsar.settle("deletion", [
            dsar.Action("postgresql", "iam.devices", "delete", "done", 2),
            dsar.Action("postgresql", "plt01.bil_usage_records", "pseudonymize", "blocked", 0),
        ])
        self.assertEqual(settled["status"], "completed")
        self.assertTrue(settled["has_residue"])
        self.assertEqual(settled["targets_blocked"], ["plt01.bil_usage_records"])
        self.assertIn("insert-only", str(settled["residue_note"]))

    def test_a_failed_target_does_not_complete_the_request(self):
        """Blocked is by design; failed is something broken, and reporting a broken erasure as
        finished is how residue becomes a surprise years later."""
        settled = dsar.settle("deletion", [
            dsar.Action("postgresql", "iam.devices", "delete", "done", 2),
            dsar.Action("postgresql", "iam.sessions", "delete", "failed", 0),
        ])
        self.assertEqual(settled["status"], "fulfilling")
        self.assertFalse(settled["complete"])
        self.assertEqual(settled["targets_failed"], ["iam.sessions"])

    def test_rows_affected_counts_only_what_was_actually_done(self):
        settled = dsar.settle("deletion", [
            dsar.Action("postgresql", "a", "delete", "done", 5),
            dsar.Action("postgresql", "b", "pseudonymize", "blocked", 99),
            dsar.Action("postgresql", "c", "delete", "failed", 99),
        ])
        self.assertEqual(settled["rows_affected"], 5)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

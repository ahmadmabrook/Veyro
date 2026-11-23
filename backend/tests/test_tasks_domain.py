"""MOD-026's pure decisions, and the one test that stops them drifting from the schema.

No database. The migration holds the same vocabulary and the same status domains, and
**two encodings of one rule that agree with each other and not with the service is the defect
MOD-020 shipped**: its waitlist admitted an edge its trigger refused, and from the moment one
member failed to answer an offer nobody was promoted again while places sat free. So the
tables in `app/tasks/` are read against the CHECK text in
`migrations/tenant/0019_tasks_and_cases.sql` rather than trusted to stay in step.
"""

from __future__ import annotations

import pathlib
import re
import unittest

from app.tasks import subjects, workflow

MIGRATION = (
    pathlib.Path(__file__).resolve().parent.parent
    / "migrations" / "tenant" / "0019_tasks_and_cases.sql"
)


def values_of(constraint: str) -> set[str]:
    """The quoted literals inside one named CHECK in the migration.

    A regex over the file rather than a query, deliberately: this has to fail in CI on a
    static tree, the way `test_migration_shape.py` catches `length(btrim(x))` -- a database
    that has not been rebuilt would answer about yesterday's schema.
    """
    src = MIGRATION.read_text(encoding="utf-8")
    m = re.search(
        r"CONSTRAINT\s+" + re.escape(constraint) + r"\s+CHECK\s*\((.*?)\)\s*(?:,|\n\s*\))",
        src, re.S)
    if m is None:  # pragma: no cover - the next assertion names it better than a KeyError
        raise AssertionError(f"{constraint} is not in {MIGRATION.name}")
    return set(re.findall(r"'([a-z_]+)'", m.group(1)))


class VocabularyTests(unittest.TestCase):
    def test_the_subject_kinds_are_the_schemas(self):
        """**Both directions.** A kind in Python and not in the CHECK is a task the database
        refuses after the service accepted it; a kind in the CHECK and not in Python is one
        nothing can file, which is MOD-020's "declared state nothing writes"."""
        for constraint in ("tsk_tasks_subject_kind", "tsk_cases_subject_kind"):
            self.assertEqual(
                set(subjects.SUBJECT_KINDS), values_of(constraint),
                f"{constraint} and SUBJECT_KINDS disagree")

    def test_every_kind_is_resolvable_or_a_declared_claim(self):
        """The import-time partition, asserted rather than left to the import.

        An `AssertionError` at import is a loud failure and is invisible to a reader deciding
        whether the guard exists; MOD-022's rate-limit budget check was written the same way
        and then mutation-proven for exactly this reason."""
        for kind in subjects.SUBJECT_KINDS:
            with self.subTest(kind=kind):
                placed = (
                    kind in subjects.RESOLVABLE
                    or kind in subjects.UNRESOLVABLE
                    or kind == "tenant")
                self.assertTrue(placed, f"{kind} is neither resolvable nor a claim")

    def test_the_three_unbuilt_kinds_say_which_module_owns_them(self):
        self.assertEqual(set(subjects.UNRESOLVABLE), {"lead", "asset", "workflow"})
        self.assertIn("MOD-027", subjects.UNRESOLVABLE["lead"])
        self.assertIn("MOD-055", subjects.UNRESOLVABLE["workflow"])

    def test_a_claim_kind_has_no_table_rather_than_a_null_one(self):
        """Raising beats returning None: a caller treating None as "no check needed" would
        skip the lookup for the five kinds that have one.

        **The sentence, not the exception class.** With the claim branch removed, `table_for`
        still raises -- the catch-all below it fires and says "resolves against nothing" --
        so an `assertRaises(SubjectError)` is answered by a sibling and the branch under test
        is droppable in silence. The mutation sweep said so. This is MOD-022's probe rule in
        Python: when two controls refuse the same input, the test has to assert which one
        answered, and here the two differ in the only way a caller can see -- one names the
        module that would make the kind resolvable and the other names nothing."""
        for kind, owner in subjects.UNRESOLVABLE.items():
            with self.subTest(kind=kind):
                with self.assertRaises(subjects.SubjectError) as caught:
                    subjects.table_for(kind)
                said = str(caught.exception)
                self.assertIn("recorded claim in this build", said)
                self.assertIn(owner, said)
                self.assertNotIn(
                    "resolves against nothing", said,
                    "the catch-all answered, so the claim branch proves nothing")
        for kind in subjects.RESOLVABLE:
            self.assertTrue(subjects.table_for(kind).startswith("plt01."))

    def test_a_kind_outside_the_vocabulary_reaches_the_catch_all(self):
        """The branch the test above refuses to be answered by, exercised on its own so it is
        not itself unproven -- the other half of the same lesson."""
        with self.assertRaises(subjects.SubjectError) as caught:
            subjects.table_for("campaign")
        self.assertIn("resolves against nothing", str(caught.exception))

    def test_the_subject_id_is_decided_by_the_kind_in_both_directions(self):
        subjects.check_subject("tenant", None)
        subjects.check_subject("member", "b0a1")
        with self.assertRaises(subjects.SubjectError):
            subjects.check_subject("tenant", "b0a1")
        with self.assertRaises(subjects.SubjectError):
            subjects.check_subject("member", None)

    def test_tenant_resolves_against_nothing_and_that_is_not_a_gap(self):
        """A task about the tenant is about the row's own `tenant_id`, which the request
        carries and RLS bounds, so there is nothing to look up."""
        self.assertNotIn("tenant", subjects.RESOLVABLE)
        self.assertNotIn("tenant", subjects.UNRESOLVABLE)
        self.assertFalse(subjects.is_a_claim("tenant"))


class TransitionTests(unittest.TestCase):
    def test_the_status_domains_are_the_schemas(self):
        self.assertEqual(set(workflow.TASK_STATUSES), values_of("tsk_tasks_status"))
        self.assertEqual(set(workflow.CASE_STATUSES), values_of("tsk_cases_status"))

    def test_a_settled_task_does_not_reopen(self):
        for settled in workflow.SETTLED:
            self.assertEqual(workflow.TASK_EDGES[settled], ())
            for target in workflow.TASK_STATUSES:
                if target == settled:
                    continue
                with self.subTest(frm=settled, to=target):
                    with self.assertRaises(workflow.WorkflowError) as caught:
                        workflow.check_task_transition(settled, target)
                    self.assertIn("does not reopen", str(caught.exception))

    def test_a_case_moves_forward_only(self):
        workflow.check_case_transition("open", "resolved")
        workflow.check_case_transition("open", "closed")
        workflow.check_case_transition("resolved", "closed")
        for frm, to in (("resolved", "open"), ("closed", "open"), ("closed", "resolved")):
            with self.subTest(frm=frm, to=to):
                with self.assertRaises(workflow.WorkflowError) as caught:
                    workflow.check_case_transition(frm, to)
                self.assertIn("new case citing this one", str(caught.exception))

    def test_a_status_change_that_changes_nothing_is_refused(self):
        """It would write an attribution for a decision nobody made, which is the "evidence
        with nobody's name on it" rule from the other side."""
        with self.assertRaises(workflow.WorkflowError):
            workflow.check_task_transition("open", "open")
        with self.assertRaises(workflow.WorkflowError):
            workflow.check_case_transition("open", "open")

    def test_a_blocked_task_is_unblocked_before_it_is_finished(self):
        """Deliberate, and the reason is on the record: finishing a blocked task leaves a
        dependency that was never satisfied or removed, so R07 cannot say whether the blocker
        mattered. Cancelling is allowed, because calling off blocked work is ordinary."""
        with self.assertRaises(workflow.WorkflowError):
            workflow.check_task_transition("blocked", "done")
        workflow.check_task_transition("blocked", "cancelled")
        workflow.check_task_transition("blocked", "in_progress")

    def test_only_a_settlement_demands_a_reason(self):
        self.assertTrue(workflow.settlement_needs_a_reason("done"))
        self.assertTrue(workflow.settlement_needs_a_reason("cancelled"))
        for ordinary in ("open", "in_progress", "blocked"):
            self.assertFalse(workflow.settlement_needs_a_reason(ordinary))


class DependencyTests(unittest.TestCase):
    def test_a_cancelled_dependency_stops_blocking(self):
        """**The direction that matters.** Treating cancelled work as blocking leaves every
        downstream task stuck with no way to clear it -- MOD-016's bundle fulfilment, where a
        transient failure made an obligation permanently unsatisfiable."""
        self.assertEqual(
            workflow.blocking((("a", "done"), ("b", "cancelled"))), ())
        self.assertEqual(
            workflow.blocking((("a", "open"), ("b", "cancelled"), ("c", "blocked"))),
            ("a", "c"))

    def test_the_blockers_are_named_and_in_order(self):
        """A count is what a reader cannot act on -- MOD-005's "a rule id is not a reason"."""
        self.assertEqual(
            workflow.blocking((("z", "open"), ("y", "in_progress"))), ("z", "y"))

    def test_an_unknown_status_in_a_dependency_is_refused(self):
        with self.assertRaises(workflow.WorkflowError):
            workflow.blocking((("a", "finished"),))

    def test_a_cycle_is_refused_at_any_length(self):
        """The schema refuses a self-reference and cannot see a longer loop, so this is the
        half that has to hold. A cycle leaves every task in it blocked with nothing able to
        unblock any of them."""
        with self.assertRaises(workflow.WorkflowError):
            workflow.check_no_cycle("a", "a", ())
        # a -> b -> c, and c -> a would close it.
        edges = (("a", "b"), ("b", "c"))
        with self.assertRaises(workflow.WorkflowError) as caught:
            workflow.check_no_cycle("c", "a", edges)
        self.assertIn("close a cycle", str(caught.exception))

    def test_a_diamond_is_not_a_cycle(self):
        """Two paths converging on one task is what R03 calls a multi-step problem, and
        refusing it would make the commonest real shape unrecordable."""
        edges = (("a", "b"), ("a", "c"))
        workflow.check_no_cycle("b", "d", edges)
        workflow.check_no_cycle("c", "d", edges)

    def test_a_long_chain_does_not_exhaust_the_stack(self):
        """The walk is iterative because `edges` is caller-supplied: a recursive version
        answers 500 on input somebody can send, which is MOD-019's `str.isdigit` finding in a
        different shape."""
        edges = tuple((str(i), str(i + 1)) for i in range(5_000))
        workflow.check_no_cycle("9999999", "0", edges)
        with self.assertRaises(workflow.WorkflowError):
            workflow.check_no_cycle("5000", "0", edges)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

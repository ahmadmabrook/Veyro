"""Unit tests for the relocation-stage name closure.

These evidence the pure decision `relocation_stages` makes about one name handed to it. They
evidence no relocation, no executed stage, no transition, no freeze, no copy, no reconciliation,
no epoch rule, no database behaviour, no tenant isolation and no integration. Every refusal is
asserted by its `code`.
"""

from __future__ import annotations

import unittest

from .. import relocation_stages as rs

# Paragraph 777 of the pinned TSD, verbatim. Held as a literal because the lane performs no I/O,
# so the source cannot be read at run time; pinning the whole sentence rather than the list is
# what makes a dropped, added, reordered or misspelled stage detectable in one assertion.
PARAGRAPH_777 = (
    "Relocation stages: preflight → target provision → snapshot/copy → "
    "change-data catch-up → write freeze → final delta → "
    "integrity/financial reconciliation → route switch → "
    "cache/session invalidation → observation window → source quarantine → "
    "source deletion after retention gate."
)


class StageNameCase(unittest.TestCase):
    def refusal(self, name: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(rs.StageNameError) as caught:
            rs.validate_relocation_stage(name)
        return caught.exception.code


class TestTheStatedSequence(StageNameCase):
    def test_the_tuple_reconstructs_paragraph_777_exactly(self) -> None:
        """The strongest available pin: a round trip against the whole source sentence.

        Set membership, order, spelling, separator and the label are all asserted at once, so a
        stage dropped, added, moved or respelled fails here regardless of which. The trailing
        period belongs to the sentence and is supplied by this test, not by the twelfth name.
        """
        self.assertEqual("Relocation stages: " + " → ".join(rs.RELOCATION_STAGES) + ".",
                         PARAGRAPH_777)

    def test_the_public_constant_is_an_immutable_ordered_tuple_of_twelve(self) -> None:
        """The container type, which the round trip above cannot see and the module needs.

        `" → ".join(...)`, `len(...)` and `set(...)` are all indifferent to tuple versus
        list, so the round trip passes unchanged if the constant becomes a list. Every other test
        file in this lane asserts its public constant against a literal tuple and catches that
        incidentally; this file replaced that assertion with the round trip, which is stronger on
        membership, order, spelling, separator and label, and silently weaker here.

        It is not a style preference. The module declines to decide precedence on the ground that
        a caller can compute it from this constant, and that ground requires the order to be
        public and stable. As a list, any code in the process could append to or sort it -- the
        refusals would all still behave correctly, because `_STAGES` is frozen at import, while
        the public order a caller reads for precedence would be destroyed.
        """
        self.assertIsInstance(rs.RELOCATION_STAGES, tuple)
        self.assertEqual(len(rs.RELOCATION_STAGES), 12)
        self.assertEqual(len(set(rs.RELOCATION_STAGES)), 12)

    def test_every_stated_stage_is_admitted_and_returned_unchanged(self) -> None:
        for name in rs.RELOCATION_STAGES:
            with self.subTest(name=name):
                self.assertEqual(rs.validate_relocation_stage(name), name)

    def test_the_lookup_set_cannot_be_added_to_at_runtime(self) -> None:
        """A mutable lookup set would let any code in the process admit an unstated stage.

        That is the gap-filling this slice refuses, reached by mutating state rather than by
        editing the tuple. The lane's closure check does not cover it: it tests whether a mutated
        name is module-level in the file being checked, and does not reach state inside an
        imported module.
        """
        self.assertIsInstance(rs._STAGES, frozenset)
        with self.assertRaises(AttributeError):
            rs._STAGES.add("cutover")  # type: ignore[attr-defined]


class TestTheAdjacentParagraphTrap(StageNameCase):
    def test_cutover_is_refused_although_paragraph_778_uses_the_word(self) -> None:
        """Paragraph 778 opens "The cutover uses a relocation_epoch", and `cutover` is not one of
        the twelve. This is the single most likely wrong name, because it is the source's own
        word for the process in the paragraph immediately after the enumeration.
        """
        self.assertEqual(self.refusal("cutover"), "unstated_stage")

    def test_a_stage_name_from_the_products_own_vocabulary_is_refused(self) -> None:
        """Each occurs elsewhere in the pinned TSD -- `validation` 68 times, `rollback` 41,
        `failover` 32, `cutover` 30, `dry run` 5, `canary` 4, `backfill` once -- and none is one
        of the twelve. Counts are whole-word and whole-document, and are per name rather than a
        partition of anything.
        """
        for name in ("rollback", "validation", "failover", "dry run", "canary", "backfill"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_stage")

    def test_a_stage_name_absent_from_the_sources_entirely_is_refused(self) -> None:
        """Separated from the list above because the reason differs, not the outcome.

        `cut-over`, `switchover`, `drain`, `warm-up` and `smoke test` occur zero times in the
        whole pinned TSD, so they are not the product's vocabulary being misplaced; they are
        names a reader brings from general migration practice.
        """
        for name in ("cut-over", "switchover", "drain", "warm-up", "smoke test"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_stage")


class TestFailClosed(StageNameCase):
    def test_a_non_string_is_refused_by_its_own_code(self) -> None:
        rejected: tuple[object, ...] = (None, 1, True, 1.0, [], {}, ("preflight",), b"preflight")
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(value), "bad_stage_name_type")

    def test_a_str_subclass_is_refused_although_it_compares_equal(self) -> None:
        """`type(name) is not str`: a subclass must not reach the set or the return value."""
        class Sneaky(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __hash__(self) -> int:
                return hash("preflight")

        self.assertEqual(self.refusal(Sneaky("preflight")), "bad_stage_name_type")

    def test_the_twelfth_name_is_refused_with_the_sentences_period_attached(self) -> None:
        """The likeliest transcription error, because the source text really does end in a period.

        Paragraph 777's last six words are followed by the full stop that closes the sentence, so
        a reader copying to the end of the line takes it along.
        """
        self.assertEqual(self.refusal("source deletion after retention gate."), "unstated_stage")
        self.assertEqual(
            rs.validate_relocation_stage("source deletion after retention gate"),
            "source deletion after retention gate")

    def test_the_separator_is_not_part_of_any_name(self) -> None:
        """An arrow or its surrounding spaces absorbed into a name is refused."""
        for name in ("→ preflight", "preflight →", "preflight → target provision",
                     "preflight target provision"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_stage")

    def test_case_is_not_folded(self) -> None:
        """Paragraph 777 spells every stage in lower case."""
        for name in ("Preflight", "PREFLIGHT", "Write Freeze", "Route Switch", "ROUTE SWITCH",
                     "Target Provision", "Observation Window"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_stage")

    def test_internal_punctuation_and_spacing_are_not_rewritten(self) -> None:
        """Eleven of the twelve carry a separator a caller might normalise -- ten a space, four a
        hyphen or a solidus -- and `preflight` alone is a single bare word. The four with a
        hyphen or a solidus are the ones this test attacks hardest, because those are the
        separators a caller is most likely to rewrite as a space or drop entirely.
        """
        for name in ("snapshot copy", "snapshot-copy", "snapshot / copy",
                     "change data catch-up", "change-data catchup", "write-freeze",
                     "writefreeze", "route-switch", "cache session invalidation",
                     "integrity financial reconciliation", " preflight", "preflight "):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_stage")

    def test_an_empty_name_is_refused(self) -> None:
        self.assertEqual(self.refusal(""), "unstated_stage")

    def test_an_overlong_name_is_refused_before_the_set_lookup(self) -> None:
        """A distinct code, so a caller can tell length from absence."""
        self.assertEqual(self.refusal("a" * (rs.MAX_STAGE_NAME_LENGTH + 1)),
                         "stage_name_too_long")

    def test_the_length_bound_is_this_value_not_merely_this_symbol(self) -> None:
        self.assertEqual(rs.MAX_STAGE_NAME_LENGTH, 64)

    def test_every_stated_name_is_well_within_the_length_bound(self) -> None:
        """Otherwise the bound would refuse a name the sources state."""
        for name in rs.RELOCATION_STAGES:
            with self.subTest(name=name):
                self.assertLessEqual(len(name), rs.MAX_STAGE_NAME_LENGTH)
        self.assertEqual(max(len(n) for n in rs.RELOCATION_STAGES), 36)

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "internal unreleased stage name"
        with self.assertRaises(rs.StageNameError) as caught:
            rs.validate_relocation_stage(secret)
        self.assertEqual(str(caught.exception), "invalid relocation stage name")
        self.assertNotIn(secret, str(caught.exception))

    def test_a_non_interned_name_is_admitted_and_returned_as_given(self) -> None:
        """Set membership is by value, and the input object itself comes back.

        `"".join([...])` rather than literal concatenation because CPython folds adjacent
        literals into the interned string. The `assertIs` pins the docstring's claim that the
        name is returned unchanged: a canonicalising return of the set's own member, or of a
        freshly built equal string, is value-identical and invisible to `assertEqual`.
        """
        built = "".join(["write", " ", "freeze"])
        self.assertEqual(built, "write freeze")
        self.assertIsNot(built, "write freeze")
        self.assertEqual(rs.validate_relocation_stage(built), "write freeze")
        self.assertIs(rs.validate_relocation_stage(built), built)


if __name__ == "__main__":
    unittest.main()

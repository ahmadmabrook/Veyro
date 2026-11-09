"""Unit tests for the release-gate isolation-layer name closure.

These evidence the pure decision `isolation_layers` makes about one name handed to it. They
evidence no layer, no isolation mechanism, no release gate, no gate result, no test, no platform,
no database behaviour, no tenant isolation and no integration. In particular, that a name is
admitted is not evidence that the layer it names exists, is mapped, is tested or is evidenced:
the MOD-004 RLS Rule records only PostgreSQL as mapped in S1 and the other six as OPEN, and
nothing here changes that. Every refusal is asserted by its `code`.
"""

from __future__ import annotations

import unittest

from .. import isolation_layers as il


class LayerNameCase(unittest.TestCase):
    def refusal(self, name: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(il.LayerNameError) as caught:
            il.stated_isolation_layer(name)
        return caught.exception.code


class TestTheStatedColumn(LayerNameCase):
    def test_the_column_is_exactly_these_seven_in_this_order(self) -> None:
        """The literals, in the table's own row order from paragraph 752 to paragraph 770."""
        self.assertEqual(il.ISOLATION_LAYERS, ("PostgreSQL", "Cache", "Search", "Object storage",
                                               "Events/jobs", "Telemetry", "AI"))

    def test_the_public_constant_is_an_immutable_tuple_of_seven(self) -> None:
        """The container type, asserted on its own rather than caught incidentally.

        `len` and `set` are both indifferent to tuple versus list. This is the omission slice 10
        was corrected for, so it is here from the start.
        """
        self.assertIsInstance(il.ISOLATION_LAYERS, tuple)
        self.assertEqual(len(il.ISOLATION_LAYERS), 7)
        self.assertEqual(len(set(il.ISOLATION_LAYERS)), 7)

    def test_every_stated_name_is_admitted_and_returned_unchanged(self) -> None:
        for name in il.ISOLATION_LAYERS:
            with self.subTest(name=name):
                self.assertEqual(il.stated_isolation_layer(name), name)

    def test_the_lookup_set_cannot_be_added_to_at_runtime(self) -> None:
        """A mutable lookup set would let any code in the process admit an unstated layer.

        The lane's closure check does not cover it: it tests whether a mutated name is
        module-level in the file being checked, and does not reach state inside an imported
        module.
        """
        self.assertIsInstance(il._LAYERS, frozenset)
        with self.assertRaises(AttributeError):
            il._LAYERS.add("Analytics")  # type: ignore[attr-defined]


class TestTheModuleDocumentsOwnLabels(LayerNameCase):
    def test_a_label_from_the_mod_004_release_gate_table_is_refused(self) -> None:
        """The likeliest wrong name, because it is in the module's own document.

        MOD-004.md's release-gate table labels its seven rows PostgreSQL/RLS, Cache keys,
        Search/read models, Object storage, Events/jobs/queues, Telemetry/log correlation and
        AI/retrieval context. Six of those are not the TSD's spelling, and each of those six
        occurs zero times anywhere in the pinned TSD -- verified before being listed here. They
        are that document's descriptive expansions, which is why they are not wrong there and
        still not what this closure is over.
        """
        for name in ("PostgreSQL/RLS", "Cache keys", "Search/read models", "Events/jobs/queues",
                     "Telemetry/log correlation", "AI/retrieval context"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_layer")

    def test_the_one_label_that_matches_is_still_admitted(self) -> None:
        """`Object storage` is the only row whose two spellings agree, so it is not a near miss.

        Listing it among the refusals would have been the easy error: six of seven differ, which
        is not seven of seven.
        """
        self.assertEqual(il.stated_isolation_layer("Object storage"), "Object storage")


class TestAnUnstatedLayer(LayerNameCase):
    def test_a_plausible_layer_from_the_products_vocabulary_is_refused(self) -> None:
        """Each occurs elsewhere in the pinned TSD -- Analytics 25 times, Webhooks 14, SMS 11,
        Backup 7, Logs 4, Queue 3, Email 2, CDN 1, Metrics 1 -- and each occurs zero times in
        the table at paragraphs 749-772. Counts are whole-word and per name.
        """
        for name in ("Analytics", "Webhooks", "SMS", "Backup", "Logs", "Queue", "Email",
                     "CDN", "Metrics"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_layer")

    def test_a_neighbouring_column_heading_is_not_a_layer(self) -> None:
        """Paragraphs 749-751 head the table; only the Layer column's values are layers."""
        for name in ("Layer", "Isolation Mechanism", "Release Gate"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_layer")


class TestFailClosed(LayerNameCase):
    def test_a_non_string_is_refused_by_its_own_code(self) -> None:
        rejected: tuple[object, ...] = (None, 1, True, 1.0, [], {}, ("Cache",), b"Cache")
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(value), "bad_layer_name_type")

    def test_a_str_subclass_is_refused_although_it_compares_equal(self) -> None:
        """`type(name) is not str`: a subclass must not reach the set or the return value."""
        class Sneaky(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __hash__(self) -> int:
                return hash("Cache")

        self.assertEqual(self.refusal(Sneaky("Cache")), "bad_layer_name_type")

    def test_case_is_not_folded_and_no_rule_could_be_inferred_from_it(self) -> None:
        """The sources' capitalisation is irregular: internal capitals in "PostgreSQL", an
        acronym in "AI", first-word-only in "Object storage". There is no rule to apply, so
        folding would be guessing.
        """
        for name in ("postgresql", "POSTGRESQL", "Postgresql", "PostgreSql", "cache", "CACHE",
                     "ai", "Ai", "object storage", "Object Storage", "OBJECT STORAGE",
                     "telemetry", "events/jobs", "search"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_layer")

    def test_the_solidus_and_the_space_are_not_rewritten(self) -> None:
        """Two of the seven carry a separator a caller might normalise."""
        for name in ("Events jobs", "Events-jobs", "Events / jobs", "Eventsjobs",
                     "Events/Jobs", "Objectstorage", "Object-storage", "Object  storage",
                     " Cache", "Cache ", "Cache\n"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_layer")

    def test_an_empty_name_is_refused(self) -> None:
        """Load-bearing beyond its name, as in the role-attribute closure: a prefix matcher
        admits the empty string and little else, so this is the assertion that catches it.
        """
        self.assertEqual(self.refusal(""), "unstated_layer")

    def test_an_overlong_name_is_refused_before_the_set_lookup(self) -> None:
        """A distinct code, so a caller can tell length from absence."""
        self.assertEqual(self.refusal("a" * (il.MAX_LAYER_NAME_LENGTH + 1)),
                         "layer_name_too_long")

    def test_the_length_bound_is_this_value_not_merely_this_symbol(self) -> None:
        self.assertEqual(il.MAX_LAYER_NAME_LENGTH, 64)

    def test_every_stated_name_is_well_within_the_length_bound(self) -> None:
        """Otherwise the bound would refuse a name the sources state."""
        for name in il.ISOLATION_LAYERS:
            with self.subTest(name=name):
                self.assertLessEqual(len(name), il.MAX_LAYER_NAME_LENGTH)
        self.assertEqual(max(len(n) for n in il.ISOLATION_LAYERS), 14)

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "Internal unreleased layer"
        with self.assertRaises(il.LayerNameError) as caught:
            il.stated_isolation_layer(secret)
        self.assertEqual(str(caught.exception), "invalid isolation layer name")
        self.assertNotIn(secret, str(caught.exception))

    def test_a_non_interned_name_is_admitted_and_returned_as_given(self) -> None:
        """Set membership is by value, and the input object itself comes back.

        `"".join([...])` rather than literal concatenation because CPython folds adjacent
        literals into the interned string. The `assertIs` pins the docstring's claim that the
        name is returned unchanged: a canonicalising return of the set's own member, or of a
        freshly built equal string, is value-identical and invisible to `assertEqual`.
        """
        built = "".join(["Object", " ", "storage"])
        self.assertEqual(built, "Object storage")
        self.assertIsNot(built, "Object storage")
        self.assertEqual(il.stated_isolation_layer(built), "Object storage")
        self.assertIs(il.stated_isolation_layer(built), built)


if __name__ == "__main__":
    unittest.main()

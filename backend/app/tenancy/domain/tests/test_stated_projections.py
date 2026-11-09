"""Unit tests for the stated-projection lookup.

These evidence the pure decision `stated_projections` makes about one name handed to it. They
evidence no projection that exists, no query, no read model, no freshness metadata, no database
behaviour, no tenant isolation and no integration. Every refusal is asserted by its `code`.
"""

from __future__ import annotations

import unittest

from .. import stated_projections as sp


class ProjectionCase(unittest.TestCase):
    def refusal(self, name: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(sp.ProjectionLookupError) as caught:
            sp.stated_projection(name)
        return caught.exception.code


class TestTheStatedClause(ProjectionCase):
    def test_the_clause_names_exactly_these_four_in_this_order(self) -> None:
        """Membership and order, because paragraph 1238's first clause states both."""
        self.assertEqual(sp.PROJECTED_ENTITIES,
                         ("Tenant", "Organization", "LegalEntity", "Brand"))

    def test_each_named_entity_has_a_stated_projection(self) -> None:
        for name in sp.PROJECTED_ENTITIES:
            with self.subTest(name=name):
                self.assertEqual(sp.stated_projection(name), sp.PROJECTION_STATED)

    def test_the_clause_has_no_duplicates(self) -> None:
        self.assertEqual(len(sp.PROJECTED_ENTITIES), len(set(sp.PROJECTED_ENTITIES)))

    def test_the_two_outcomes_are_these_values_not_merely_these_symbols(self) -> None:
        """The literals, because this module's whole output is one of two strings.

        An earlier version asserted only `OUTCOMES == (PROJECTION_STATED, NO_PROJECTION_STATED)`
        and `PROJECTION_STATED != NO_PROJECTION_STATED`. Both hold after swapping the two string
        literals in the source, which inverts the module completely -- `Tenant` reports the gap
        and `CostCenter` reports a stated projection -- with the whole suite green. There is no
        dataclass and no second field for a consumer to cross-check against here, so the strings
        are the interface and have to be pinned as values.
        """
        self.assertEqual(sp.OUTCOMES, ("projection_stated", "no_projection_stated"))
        self.assertEqual(sp.PROJECTION_STATED, "projection_stated")
        self.assertEqual(sp.NO_PROJECTION_STATED, "no_projection_stated")
        self.assertNotEqual(sp.PROJECTION_STATED, sp.NO_PROJECTION_STATED)

    def test_the_lookup_set_cannot_be_added_to_at_runtime(self) -> None:
        """A mutable lookup set would let any code in the process claim an unstated projection.

        That is the gap-filling this slice refuses, reached by mutating state rather than by
        editing the tuple. The lane's closure check does not cover it: it tests whether a mutated
        name is module-level in the file being checked, and does not reach state inside an
        imported module.
        """
        self.assertIsInstance(sp._PROJECTED, frozenset)
        with self.assertRaises(AttributeError):
            sp._PROJECTED.add("CostCenter")  # type: ignore[attr-defined]


class TestTheRecordedGap(ProjectionCase):
    def test_the_five_entities_with_no_stated_projection_get_the_gap_outcome(self) -> None:
        """MOD-004.md records "paragraph 1238 covers four of nine entities" as a source gap.

        These five are authoritative entities of paragraph 1204 for which no projection is
        stated. Answering `NO_PROJECTION_STATED` reports the gap; inventing a projection for them
        would fill it.
        """
        for name in ("Region", "Location", "Department", "CostCenter", "TenantConfiguration"):
            with self.subTest(name=name):
                self.assertEqual(sp.stated_projection(name), sp.NO_PROJECTION_STATED)

    def test_the_gap_outcome_does_not_distinguish_an_entity_from_a_non_entity(self) -> None:
        """The module's own boundary, asserted rather than left to the docstring.

        `CostCenter` is an authoritative entity with no stated projection; `Franchise` is not an
        entity at all. Both get the same outcome here, because telling them apart needs paragraph
        1204, which this module does not read. A caller needing that distinction calls the entity
        closure as well.
        """
        self.assertEqual(sp.stated_projection("CostCenter"), sp.NO_PROJECTION_STATED)
        self.assertEqual(sp.stated_projection("Franchise"), sp.NO_PROJECTION_STATED)

    def test_a_command_or_event_name_is_not_a_projected_entity(self) -> None:
        """Names from the neighbouring paragraphs 1237 and 1241, which share this block."""
        for name in ("ProvisionTenant", "ActivateTenant", "tenant.provisioned", "brand.created"):
            with self.subTest(name=name):
                self.assertEqual(sp.stated_projection(name), sp.NO_PROJECTION_STATED)


class TestFailClosed(ProjectionCase):
    def test_a_non_string_is_refused_rather_than_answered(self) -> None:
        """Refusing matters more here than in a pure closure: returning the gap outcome for a
        malformed input would let a caller read a bug as an absent projection."""
        rejected: tuple[object, ...] = (None, 1, True, 1.0, [], {}, ("Tenant",), b"Tenant")
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(value), "bad_name_type")

    def test_a_str_subclass_is_refused_although_it_compares_equal(self) -> None:
        """`type(name) is not str`: a subclass must not reach the set."""
        class Sneaky(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __hash__(self) -> int:
                return hash("Tenant")

        self.assertEqual(self.refusal(Sneaky("Tenant")), "bad_name_type")

    def test_the_name_is_not_normalized(self) -> None:
        """Paragraph 1238 spells these four exactly as paragraph 1204 does."""
        for name in ("tenant", "TENANT", "brand", "legalentity", " Tenant", "Tenant ",
                     "Legal Entity", "organization"):
            with self.subTest(name=name):
                self.assertEqual(sp.stated_projection(name), sp.NO_PROJECTION_STATED)

    def test_an_empty_name_gets_the_gap_outcome_rather_than_a_refusal(self) -> None:
        """An empty string is a well-formed `str` that the clause does not name."""
        self.assertEqual(sp.stated_projection(""), sp.NO_PROJECTION_STATED)

    def test_an_overlong_name_is_refused_before_the_set_lookup(self) -> None:
        """A distinct code, so a caller can tell length from absence."""
        self.assertEqual(self.refusal("a" * (sp.MAX_NAME_LENGTH + 1)), "name_too_long")

    def test_the_length_bound_is_this_value_not_merely_this_symbol(self) -> None:
        self.assertEqual(sp.MAX_NAME_LENGTH, 64)

    def test_every_named_entity_is_within_the_length_bound(self) -> None:
        """Otherwise the bound would refuse a name the clause states."""
        for name in sp.PROJECTED_ENTITIES:
            with self.subTest(name=name):
                self.assertLessEqual(len(name), sp.MAX_NAME_LENGTH)

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "x" * (sp.MAX_NAME_LENGTH + 1)
        with self.assertRaises(sp.ProjectionLookupError) as caught:
            sp.stated_projection(secret)
        self.assertEqual(str(caught.exception), "invalid projection lookup input")
        self.assertNotIn(secret, str(caught.exception))

    def test_a_non_interned_name_is_matched_by_value(self) -> None:
        """Set membership is by value. `"".join([...])` because CPython folds adjacent literals."""
        built = "".join(["Legal", "Entity"])
        self.assertEqual(built, "LegalEntity")
        self.assertIsNot(built, "LegalEntity")
        self.assertEqual(sp.stated_projection(built), sp.PROJECTION_STATED)


if __name__ == "__main__":
    unittest.main()

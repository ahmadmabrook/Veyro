"""Unit tests for the authoritative-entity name closure.

These evidence the pure decision `authoritative_entities` makes about one name handed to it.
They evidence no table, no schema, no migration, no aggregate, no projection, no command, no
database behaviour, no tenant isolation and no integration. Every refusal is asserted by its
`code`.
"""

from __future__ import annotations

import unittest

from .. import authoritative_entities as ae


class EntityNameCase(unittest.TestCase):
    def refusal(self, name: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(ae.EntityNameError) as caught:
            ae.validate_authoritative_entity(name)
        return caught.exception.code


class TestTheStatedSet(EntityNameCase):
    def test_the_set_is_exactly_these_nine_in_this_order(self) -> None:
        """Membership and order, because paragraph 1204 and paragraph 1236 both state both."""
        self.assertEqual(ae.AUTHORITATIVE_ENTITIES, (
            "Tenant",
            "Organization",
            "LegalEntity",
            "Brand",
            "Region",
            "Location",
            "Department",
            "CostCenter",
            "TenantConfiguration",
        ))

    def test_every_stated_name_is_admitted_and_returned_unchanged(self) -> None:
        for name in ae.AUTHORITATIVE_ENTITIES:
            with self.subTest(name=name):
                self.assertEqual(ae.validate_authoritative_entity(name), name)

    def test_the_set_has_no_duplicates(self) -> None:
        self.assertEqual(len(ae.AUTHORITATIVE_ENTITIES), len(set(ae.AUTHORITATIVE_ENTITIES)))

    def test_the_lookup_set_cannot_be_added_to_at_runtime(self) -> None:
        """A mutable lookup set would let any code in the process admit an unstated name.

        That is the gap-filling this slice refuses, reached by mutating state rather than by
        editing the tuple. The lane's closure check does not cover it: it tests whether a mutated
        name is module-level in the file being checked, and does not reach state inside an
        imported module.
        """
        self.assertIsInstance(ae._AUTHORITATIVE, frozenset)
        with self.assertRaises(AttributeError):
            ae._AUTHORITATIVE.add("Franchise")  # type: ignore[attr-defined]


class TestTheTwoRecordedSourceGaps(EntityNameCase):
    def test_an_entity_invented_from_the_products_own_vocabulary_is_refused(self) -> None:
        """The first pull: four of the nine have no maintenance command in paragraph 1237.

        MOD-004.md records that absence under PLT-01-R02, so an author building the hierarchy is
        pulled toward naming something new, and these are the names the product itself supplies.
        Each occurs elsewhere in the TSD -- Member 160 times, Staff 36, Franchise 19, Chain 11,
        Facility 7, Gym 6, Club 3, Team 2 -- and each occurs zero times in the paragraph
        1194-1245 block, which is what makes it unstated here. That is what makes this list a
        real tripwire rather than a set of strawmen: every name is live vocabulary somewhere.

        The counts are case-sensitive, which is load-bearing for `Chain`: lower-case "chain"
        does occur in the block, at paragraph 1234's "A chain can manage multiple brands and
        regions", while capitalised `Chain` does not. Under this module's own semantics, where
        capitalisation is the distinction, the case-sensitive count is the one that decides --
        the same `tenant`-versus-`Tenant` split the casing test pins.
        """
        for name in ("Franchise", "Chain", "Facility", "Gym", "Club", "Member", "Staff", "Team"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_entity")

    def test_an_entity_absent_from_the_sources_entirely_is_refused(self) -> None:
        """Separated from the list above because the reason differs, not the outcome.

        `Studio`, `Branch` and `Site` occur zero times in the whole pinned TSD, case-sensitively
        and case-insensitively alike. So they are not the product's vocabulary being misplaced
        into this module; they are names a reader brings from general gym-domain usage. Both
        groups are refused, and keeping them apart is what stops the sentence above from
        over-claiming that every refused name is attested somewhere in the document.
        """
        for name in ("Studio", "Branch", "Site"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_entity")

    def test_the_five_entities_with_no_stated_projection_are_still_admitted(self) -> None:
        """The second pull, the opposite one: taking paragraph 1238's subset for the entity set.

        MOD-004.md records "Read models: paragraph 1238 covers four of nine entities", and that
        paragraph names Tenant, Organization, LegalEntity and Brand only. A closure built from it
        would silently drop these five. Missing a projection is not being unstated as an entity.
        """
        for name in ("Region", "Location", "Department", "CostCenter", "TenantConfiguration"):
            with self.subTest(name=name):
                self.assertEqual(ae.validate_authoritative_entity(name), name)

    def test_the_four_entities_with_no_maintenance_command_are_still_admitted(self) -> None:
        """Lacking a command in paragraph 1237 is not lacking entity authority in 1204/1236."""
        for name in ("LegalEntity", "Department", "CostCenter", "TenantConfiguration"):
            with self.subTest(name=name):
                self.assertEqual(ae.validate_authoritative_entity(name), name)

    def test_a_command_name_is_not_an_entity_name(self) -> None:
        """Paragraph 1237's commands share this block and are a different closure."""
        for name in ("ProvisionTenant", "ActivateTenant", "ArchiveTenant", "RelocateTenant"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_entity")


class TestFailClosed(EntityNameCase):
    def test_a_non_string_is_refused_by_its_own_code(self) -> None:
        rejected: tuple[object, ...] = (None, 1, True, 1.0, [], {}, ("Tenant",), b"Tenant")
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(value), "bad_entity_name_type")

    def test_a_str_subclass_is_refused_although_it_compares_equal(self) -> None:
        """`type(name) is not str`: a subclass must not reach the set or the return value."""
        class Sneaky(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __hash__(self) -> int:
                return hash("Tenant")

        self.assertEqual(self.refusal(Sneaky("Tenant")), "bad_entity_name_type")

    def test_the_name_is_not_normalized_and_case_is_load_bearing(self) -> None:
        """Paragraph 1204 capitalises every entity where paragraph 1206 lower-cases every event.

        The sources draw the distinction, so folding it away is not a convenience. Lower-case
        "tenant" also occurs 638 times in the TSD meaning other things -- the `tenant.` event
        prefix, "tenant-scoped", "tenant context" -- so folding would make each an entity name.
        """
        for name in ("tenant", "TENANT", "tEnant", "organization", "legalentity", "LEGALENTITY",
                     "costcenter", "Costcenter", "tenantconfiguration"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_entity")

    def test_a_padded_or_separated_name_is_refused(self) -> None:
        for name in (" Tenant", "Tenant ", "Legal Entity", "Legal_Entity", "Cost-Center",
                     "cost_center", "TenantConfiguration\n"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_entity")

    def test_an_empty_name_is_refused(self) -> None:
        self.assertEqual(self.refusal(""), "unstated_entity")

    def test_an_overlong_name_is_refused_before_the_set_lookup(self) -> None:
        """A distinct code, so a caller can tell length from absence."""
        self.assertEqual(self.refusal("a" * (ae.MAX_ENTITY_NAME_LENGTH + 1)),
                         "entity_name_too_long")

    def test_the_length_bound_is_this_value_not_merely_this_symbol(self) -> None:
        self.assertEqual(ae.MAX_ENTITY_NAME_LENGTH, 64)

    def test_every_stated_name_is_well_within_the_length_bound(self) -> None:
        """Otherwise the bound would refuse a name the sources state."""
        for name in ae.AUTHORITATIVE_ENTITIES:
            with self.subTest(name=name):
                self.assertLessEqual(len(name), ae.MAX_ENTITY_NAME_LENGTH)
        self.assertEqual(max(len(n) for n in ae.AUTHORITATIVE_ENTITIES), 19)

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "SecretInternalEntityName"
        with self.assertRaises(ae.EntityNameError) as caught:
            ae.validate_authoritative_entity(secret)
        self.assertEqual(str(caught.exception), "invalid authoritative entity name")
        self.assertNotIn(secret, str(caught.exception))

    def test_a_non_interned_name_is_admitted_and_returned_as_given(self) -> None:
        """Set membership is by value, and the input object itself comes back.

        `"".join([...])` rather than literal concatenation because CPython folds adjacent
        literals into the interned string, which would make the `assertIsNot` vacuous. The
        `assertIs` pins the module docstring's claim that the name is returned unchanged: a
        canonicalising return of the set's own member, or of a freshly built equal string, is
        value-identical and invisible to `assertEqual`.
        """
        built = "".join(["Tenant", "Configuration"])
        self.assertEqual(built, "TenantConfiguration")
        self.assertIsNot(built, "TenantConfiguration")
        self.assertEqual(ae.validate_authoritative_entity(built), "TenantConfiguration")
        self.assertIs(ae.validate_authoritative_entity(built), built)


if __name__ == "__main__":
    unittest.main()

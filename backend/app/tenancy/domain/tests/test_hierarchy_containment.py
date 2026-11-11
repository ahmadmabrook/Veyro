"""Unit tests for the hierarchy-link containment decision.

These evidence the pure decision `hierarchy_containment` makes about four tokens handed to it. They
evidence no tenant isolation -- isolation is enforced by PostgreSQL row-level security, which this
lane cannot write -- no foreign key, no uniqueness constraint, no authorization, no stored graph, no
database behaviour and no integration. Every refusal is asserted by its `code`.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from .. import hierarchy_containment as hc

T1 = "0191f1c2-3a4b-7c5d-8e6f-0a1b2c3d4e5f"
T2 = "0191f1c2-3a4b-7c5d-8e6f-0a1b2c3d4e60"


class ContainmentCase(unittest.TestCase):
    def refusal(
        self,
        child_kind: object = hc.LOCATION,
        child_tenant_id: object = T1,
        parent_kind: object = hc.BRAND,
        parent_tenant_id: object = T1,
    ) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(hc.ContainmentError) as caught:
            hc.link_is_admissible(child_kind, child_tenant_id, parent_kind, parent_tenant_id)
        return caught.exception.code

    def admit(
        self,
        child_kind: object = hc.LOCATION,
        child_tenant_id: object = T1,
        parent_kind: object = hc.BRAND,
        parent_tenant_id: object = T1,
    ) -> hc.AdmissibleLink:
        return hc.link_is_admissible(child_kind, child_tenant_id, parent_kind, parent_tenant_id)


class TestTheStatedNodeKinds(ContainmentCase):
    def test_the_kinds_are_exactly_paragraph_1223s_seven(self) -> None:
        """Membership, not only presence: an eighth kind would invent one."""
        self.assertEqual(
            hc.HIERARCHY_KINDS,
            (
                "Organization",
                "LegalEntity",
                "Brand",
                "Region",
                "Location",
                "Department",
                "CostCenter",
            ),
        )

    def test_the_two_authoritative_entities_outside_the_seven_are_named(self) -> None:
        self.assertEqual(hc.NON_HIERARCHY_ENTITIES, ("Tenant", "TenantConfiguration"))

    def test_the_seven_and_the_two_are_disjoint(self) -> None:
        self.assertEqual(set(hc.HIERARCHY_KINDS) & set(hc.NON_HIERARCHY_ENTITIES), set())

    def test_every_stated_kind_is_admissible_at_both_ends(self) -> None:
        for kind in hc.HIERARCHY_KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(self.admit(child_kind=kind).child_kind, kind)
                self.assertEqual(self.admit(parent_kind=kind).parent_kind, kind)


class TestTenantContainment(ContainmentCase):
    def test_a_link_inside_one_tenant_is_admitted(self) -> None:
        result = self.admit(child_tenant_id=T1, parent_tenant_id=T1)
        self.assertEqual(result.child_kind, hc.LOCATION)
        self.assertEqual(result.parent_kind, hc.BRAND)

    def test_a_link_across_two_tenants_is_refused(self) -> None:
        self.assertEqual(
            self.refusal(child_tenant_id=T1, parent_tenant_id=T2), "cross_tenant_link"
        )

    def test_the_refusal_is_symmetric(self) -> None:
        self.assertEqual(
            self.refusal(child_tenant_id=T2, parent_tenant_id=T1), "cross_tenant_link"
        )

    def test_two_cases_of_one_uuid_are_one_tenant(self) -> None:
        """RFC 4122 hex is case-insensitive, so these are the same tenant, not two.

        Comparing byte-exactly would emit `cross_tenant_link` for a single tenant -- a false
        positive on this module's one security-labelled verdict.
        """
        upper = "0191F1C2-3A4B-7C5D-8E6F-0A1B2C3D4E5F"
        self.assertEqual(upper.lower(), T1)
        result = self.admit(child_tenant_id=upper, parent_tenant_id=T1)
        self.assertEqual(result.child_kind, hc.LOCATION)
        swapped = self.admit(child_tenant_id=T1, parent_tenant_id=upper)
        self.assertEqual(swapped.child_kind, hc.LOCATION)

    def test_a_case_difference_does_not_hide_a_genuine_cross_tenant_link(self) -> None:
        """Case folding must not make two different UUIDs compare equal."""
        self.assertEqual(
            self.refusal(child_tenant_id=T2.upper(), parent_tenant_id=T1), "cross_tenant_link"
        )
        self.assertEqual(
            self.refusal(child_tenant_id=T1, parent_tenant_id=T2.upper()), "cross_tenant_link"
        )

    def test_the_refusal_never_carries_a_tenant_id(self) -> None:
        with self.assertRaises(hc.ContainmentError) as caught:
            hc.link_is_admissible(hc.LOCATION, T1, hc.BRAND, T2)
        self.assertNotIn(T1, str(caught.exception))
        self.assertNotIn(T1, caught.exception.code)


class TestTheTenantIdShape(ContainmentCase):
    """Section 9.3 states UUID identifiers and the RLS rule requires `tenant_id UUID NOT NULL`, so
    an arbitrary bounded token is not accepted at the boundary this module exists to guard.
    """

    def test_a_non_uuid_tenant_id_is_refused_at_each_end(self) -> None:
        for token in ("t", "0", "a b", "../etc", "9f1c-not-a-uuid", "tenant-one"):
            with self.subTest(token=token):
                self.assertEqual(
                    self.refusal(child_tenant_id=token, parent_tenant_id=token),
                    "bad_child_tenant_id",
                )
                self.assertEqual(self.refusal(parent_tenant_id=token), "bad_parent_tenant_id")

    def test_the_nil_uuid_is_refused(self) -> None:
        nil = "00000000-0000-0000-0000-000000000000"
        self.assertEqual(self.refusal(child_tenant_id=nil), "bad_child_tenant_id")

    def test_an_unhyphenated_uuid_is_refused(self) -> None:
        self.assertEqual(
            self.refusal(child_tenant_id="0191f1c23a4b7c5d8e6f0a1b2c3d4e5f"),
            "bad_child_tenant_id",
        )

    def test_a_uuid_with_trailing_text_is_refused(self) -> None:
        """A longer token is refused, by the length guard and `fullmatch` together.

        This does not isolate `fullmatch`: the length check refuses a 37-character token first,
        and for any 36-character input `match` and `fullmatch` agree, so no test can tell them
        apart while the length guard stands. Both guards are deliberate; removing both admits
        `T1 + "-EVIL"`.
        """
        self.assertEqual(self.refusal(child_tenant_id=T1 + "x"), "bad_child_tenant_id")
        self.assertEqual(self.refusal(child_tenant_id=T1 + "-EVIL"), "bad_child_tenant_id")

    def test_a_non_string_tenant_id_is_refused_at_each_end(self) -> None:
        for value in (None, 1, b"0191f1c2-3a4b-7c5d-8e6f-0a1b2c3d4e5f", [T1], object()):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(child_tenant_id=value), "bad_child_tenant_id")
                self.assertEqual(self.refusal(parent_tenant_id=value), "bad_parent_tenant_id")

    def test_a_string_subclass_cannot_smuggle_a_tenant_id_through(self) -> None:
        """The comparison at the end of the function is where a crafted `__eq__` would decide
        containment, so the `type(...) is str` test is pinned on both tenant-id ends.
        """

        class Always(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __ne__(self, other: object) -> bool:
                return False

            def __hash__(self) -> int:
                return 0

        self.assertEqual(self.refusal(child_tenant_id=Always(T1)), "bad_child_tenant_id")
        self.assertEqual(self.refusal(parent_tenant_id=Always(T1)), "bad_parent_tenant_id")

    def test_a_crafted_subclass_cannot_admit_a_cross_tenant_link(self) -> None:
        """The property B4 names: a link whose ends differ must stay refused."""

        class Always(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __ne__(self, other: object) -> bool:
                return False

            def __hash__(self) -> int:
                return 0

        with self.assertRaises(hc.ContainmentError):
            hc.link_is_admissible(hc.LOCATION, Always(T1), hc.BRAND, T2)


class TestTheShapeIsNotDecided(ContainmentCase):
    def test_every_admitted_link_says_the_shape_was_not_decided(self) -> None:
        """Cardinalities are owner-reserved; an admitted link must not read as shape approval."""
        for child in hc.HIERARCHY_KINDS:
            for parent in hc.HIERARCHY_KINDS:
                with self.subTest(child=child, parent=parent):
                    self.assertFalse(self.admit(child_kind=child, parent_kind=parent).shape_decided)

    def test_an_implausible_parentage_is_admitted_because_shape_is_not_decided(self) -> None:
        """CostCenter over Organization is almost certainly wrong, and no source says so."""
        result = self.admit(child_kind=hc.ORGANIZATION, parent_kind=hc.COST_CENTER)
        self.assertEqual(result.child_kind, hc.ORGANIZATION)
        self.assertEqual(result.parent_kind, hc.COST_CENTER)

    def test_a_kind_repeating_on_a_link_is_admitted(self) -> None:
        """Self-parenting is invisible here: the inputs are kinds, never node identities."""
        result = self.admit(child_kind=hc.BRAND, parent_kind=hc.BRAND)
        self.assertEqual(result.child_kind, hc.BRAND)
        self.assertEqual(result.parent_kind, hc.BRAND)

    def test_the_result_carries_no_shape_or_depth_field(self) -> None:
        result = self.admit()
        for absent in ("depth", "cardinality", "ordinal", "path", "root", "authorized"):
            with self.subTest(absent=absent):
                self.assertFalse(hasattr(result, absent))


class TestMalformedKindsFailClosed(ContainmentCase):
    def test_a_non_string_kind_is_refused_at_each_end(self) -> None:
        for value in (None, 1, b"Brand", ["Brand"], object()):
            with self.subTest(value=value):
                self.assertEqual(self.refusal(child_kind=value), "bad_child_kind")
                self.assertEqual(self.refusal(parent_kind=value), "bad_parent_kind")

    def test_a_string_subclass_cannot_smuggle_a_kind_through(self) -> None:
        class Sneaky(str):
            pass

        self.assertEqual(self.refusal(child_kind=Sneaky(hc.BRAND)), "bad_child_kind")
        self.assertEqual(self.refusal(parent_kind=Sneaky(hc.BRAND)), "bad_parent_kind")

    def test_an_empty_or_over_long_kind_is_refused(self) -> None:
        self.assertEqual(self.refusal(child_kind=""), "bad_child_kind")
        self.assertEqual(self.refusal(child_kind="x" * (hc.TOKEN_MAX + 1)), "bad_child_kind")

    def test_kinds_are_not_case_folded(self) -> None:
        self.assertEqual(self.refusal(child_kind="brand"), "unknown_child_kind")

    def test_a_stated_entity_outside_the_seven_gets_its_own_code(self) -> None:
        for entity in hc.NON_HIERARCHY_ENTITIES:
            with self.subTest(entity=entity):
                self.assertEqual(
                    self.refusal(child_kind=entity), "child_kind_not_a_hierarchy_node"
                )
                self.assertEqual(
                    self.refusal(parent_kind=entity), "parent_kind_not_a_hierarchy_node"
                )

    def test_an_unknown_kind_is_distinguished_from_a_malformed_token(self) -> None:
        """Separate codes, so a caller can tell a type error from a name outside the seven."""
        for token in ("Franchise", "Chain", "Facility", "Gym", "Club"):
            with self.subTest(token=token):
                self.assertEqual(self.refusal(child_kind=token), "unknown_child_kind")
                self.assertEqual(self.refusal(parent_kind=token), "unknown_parent_kind")

    def test_kinds_are_judged_before_tenant_ids(self) -> None:
        """A bad kind and a cross-tenant pair report the kind, so codes stay unambiguous."""
        self.assertEqual(
            self.refusal(child_kind="nope", child_tenant_id=T1, parent_tenant_id=T2),
            "unknown_child_kind",
        )


class TestTheResultIsAFactNotAPermission(ContainmentCase):
    def test_the_link_is_immutable(self) -> None:
        result = self.admit()
        with self.assertRaises(FrozenInstanceError):
            result.shape_decided = True  # type: ignore

    def test_the_kinds_are_returned_unchanged(self) -> None:
        result = self.admit(child_kind=hc.DEPARTMENT, parent_kind=hc.REGION)
        self.assertEqual(result.child_kind, hc.DEPARTMENT)
        self.assertEqual(result.parent_kind, hc.REGION)

    def test_the_result_carries_no_tenant_id(self) -> None:
        """Containment was decided; echoing the id back would invite it into a log."""
        result = self.admit()
        for absent in ("tenant_id", "child_tenant_id", "parent_tenant_id"):
            with self.subTest(absent=absent):
                self.assertFalse(hasattr(result, absent))

"""Unit tests for the primary-surface name closure.

These evidence the pure decision `primary_surfaces` makes about one name handed to it. They
evidence no screen, no screen identifier, no route, no owning module, no permission, no read
model, no database behaviour, no tenant isolation and no integration. Every refusal is asserted
by its `code`.
"""

from __future__ import annotations

import unittest

from .. import primary_surfaces as ps


class SurfaceNameCase(unittest.TestCase):
    def refusal(self, name: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(ps.SurfaceNameError) as caught:
            ps.validate_primary_surface(name)
        return caught.exception.code


class TestTheStatedSet(SurfaceNameCase):
    def test_the_set_is_exactly_these_three_in_this_order(self) -> None:
        """The literals, because paragraph 1200 and paragraph 1238 both state set and order."""
        self.assertEqual(ps.PRIMARY_SURFACES, ("Internal SaaS Console", "Admin Web", "APIs"))

    def test_every_stated_name_is_admitted_and_returned_unchanged(self) -> None:
        for name in ps.PRIMARY_SURFACES:
            with self.subTest(name=name):
                self.assertEqual(ps.validate_primary_surface(name), name)

    def test_the_set_has_no_duplicates(self) -> None:
        self.assertEqual(len(ps.PRIMARY_SURFACES), len(set(ps.PRIMARY_SURFACES)))

    def test_the_lookup_set_cannot_be_added_to_at_runtime(self) -> None:
        """A mutable lookup set would let any code in the process admit an unstated surface.

        That is the gap-filling this slice refuses, reached by mutating state rather than by
        editing the tuple. The lane's closure check does not cover it: it tests whether a mutated
        name is module-level in the file being checked, and does not reach state inside an
        imported module.
        """
        self.assertIsInstance(ps._PRIMARY, frozenset)
        with self.assertRaises(AttributeError):
            ps._PRIMARY.add("Member App")  # type: ignore[attr-defined]


class TestTheInferredSurfaceGap(SurfaceNameCase):
    def test_another_product_surface_is_refused(self) -> None:
        """MOD-004.md's screen mapping is "engineering decision; unreviewed", with ten
        `[INFERENCE]` markers, and names only Internal SaaS Console and Admin Web for this
        module's screens.

        Each name below is real product vocabulary -- Member App occurs 49 times in the pinned
        TSD, POS 47, Front Desk 44, Coach App 30, Kiosk 21, Staff Kiosk 2, Member Web 2, Partner
        Portal 2, Mobile App 1 -- and each occurs zero times in paragraphs 1194-1245, which is
        what makes it unstated for this module.

        Each figure is that one name's whole-word, whole-document count, and they are not
        disjoint: `Kiosk`'s 21 includes `Staff Kiosk`'s 2, so they do not sum to a total of
        anything. Whole-word matters too. In MOD-004.md a bare substring search for `POS` returns
        nine hits and the whole-word count is zero, because the nine sit inside three different
        strings -- five in "PROPOSED", three in "BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME" and one
        in "PROPOSE". Naming only the first would invite the reader to attribute all nine to it.
        """
        for name in ("Member App", "POS", "Front Desk", "Coach App", "Kiosk", "Staff Kiosk",
                     "Member Web", "Partner Portal", "Mobile App"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_surface")

    def test_a_surface_name_from_the_repositorys_own_screen_registry_is_refused(self) -> None:
        """The likeliest wrong name is not from the TSD at all, but from this repository's data.

        `contracts/ui/screen-contracts.yaml` holds 170 V1 screens under five surface values --
        `Veyro Admin` 85, `Veyro Member` 35, `Veyro Coach` 19, `Front Desk & POS` 16 and
        `Internal Console` 15 -- and not one of the five is any of the three the sources state as
        this module's primary surfaces. An author mapping a screen reads that file, so these are
        the names that would actually be copied, where the vocabulary above is what someone might
        recall. `Veyro Admin` alone covers half the V1 screens.

        `Front Desk & POS` is listed in its own right because the compound string is a different
        value from the two names the vocabulary test refuses separately. `Internal Console` is
        also in the near-miss test below, where it is reached by dropping a word from a stated
        name; it is both, and refusing it once per reason is the point.
        """
        for name in ("Veyro Admin", "Veyro Member", "Veyro Coach", "Front Desk & POS",
                     "Internal Console"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_surface")

    def test_a_near_miss_spelling_of_a_stated_surface_is_refused(self) -> None:
        """The failure mode is a plausible rewrite, not an unrelated word.

        `API` singular is not what paragraph 1200 states, and "Admin Console" and "SaaS Console"
        are the two abbreviations of "Internal SaaS Console" an author would reach for.
        """
        for name in ("API", "Apis", "Admin Console", "SaaS Console", "Console",
                     "Internal Console", "Admin", "Web"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_surface")


class TestFailClosed(SurfaceNameCase):
    def test_a_non_string_is_refused_by_its_own_code(self) -> None:
        rejected: tuple[object, ...] = (None, 1, True, 1.0, [], {}, ("APIs",), b"APIs")
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(value), "bad_surface_name_type")

    def test_a_str_subclass_is_refused_although_it_compares_equal(self) -> None:
        """`type(name) is not str`: a subclass must not reach the set or the return value."""
        class Sneaky(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __hash__(self) -> int:
                return hash("APIs")

        self.assertEqual(self.refusal(Sneaky("APIs")), "bad_surface_name_type")

    def test_case_is_not_folded_including_inside_the_acronym(self) -> None:
        """The sources spell it "SaaS"; `Saas`, `SAAS` and `saas` are all different strings."""
        for name in ("internal saas console", "INTERNAL SAAS CONSOLE", "Internal Saas Console",
                     "Internal SAAS Console", "admin web", "ADMIN WEB", "apis", "Apis", "APIS"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_surface")

    def test_internal_whitespace_is_not_collapsed_or_trimmed(self) -> None:
        """A multi-word name has failure modes a single-word one does not."""
        for name in (" Internal SaaS Console", "Internal SaaS Console ",
                     "Internal  SaaS  Console", "InternalSaaSConsole", "Internal-SaaS-Console",
                     "Admin  Web", "AdminWeb", "Admin_Web", "Internal SaaS Console\n"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_surface")

    def test_an_empty_name_is_refused(self) -> None:
        self.assertEqual(self.refusal(""), "unstated_surface")

    def test_an_overlong_name_is_refused_before_the_set_lookup(self) -> None:
        """A distinct code, so a caller can tell length from absence."""
        self.assertEqual(self.refusal("a" * (ps.MAX_SURFACE_NAME_LENGTH + 1)),
                         "surface_name_too_long")

    def test_the_length_bound_is_this_value_not_merely_this_symbol(self) -> None:
        self.assertEqual(ps.MAX_SURFACE_NAME_LENGTH, 64)

    def test_every_stated_name_is_well_within_the_length_bound(self) -> None:
        """Otherwise the bound would refuse a name the sources state."""
        for name in ps.PRIMARY_SURFACES:
            with self.subTest(name=name):
                self.assertLessEqual(len(name), ps.MAX_SURFACE_NAME_LENGTH)
        self.assertEqual(max(len(n) for n in ps.PRIMARY_SURFACES), 21)

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "Internal Unreleased Surface"
        with self.assertRaises(ps.SurfaceNameError) as caught:
            ps.validate_primary_surface(secret)
        self.assertEqual(str(caught.exception), "invalid primary surface name")
        self.assertNotIn(secret, str(caught.exception))

    def test_a_non_interned_name_is_admitted_and_returned_as_given(self) -> None:
        """Set membership is by value, and the input object itself comes back.

        `"".join([...])` rather than literal concatenation because CPython folds adjacent
        literals into the interned string. The `assertIs` pins the docstring's claim that the
        name is returned unchanged: a canonicalising return of the set's own member, or of a
        freshly built equal string, is value-identical and invisible to `assertEqual`.
        """
        built = "".join(["Admin", " ", "Web"])
        self.assertEqual(built, "Admin Web")
        self.assertIsNot(built, "Admin Web")
        self.assertEqual(ps.validate_primary_surface(built), "Admin Web")
        self.assertIs(ps.validate_primary_surface(built), built)


if __name__ == "__main__":
    unittest.main()

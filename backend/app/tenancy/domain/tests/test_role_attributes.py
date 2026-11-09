"""Unit tests for the role-attribute name closure.

These evidence the pure decision `role_attributes` makes about one name handed to it. They
evidence no role, no grant, no privilege, no policy, no RLS, no migration, no database
configuration, no tenant isolation and no integration, and they are not a step toward the
MOD-004 RLS Rule's role-privilege test, which must run as the actual runtime role against a real
database and is recorded there as an obligation with no PASS. Every refusal is asserted by its
`code`.
"""

from __future__ import annotations

import unittest

from .. import role_attributes as ra

# The attribute clause of paragraph 743 of the pinned TSD, verbatim. Held as a literal because
# the lane performs no I/O. Note the source separates the first four with commas and the last
# with " and ", which the reconstruction below reproduces rather than normalising.
PARAGRAPH_743_CLAUSE = "LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE and NOBYPASSRLS"


class AttributeNameCase(unittest.TestCase):
    def refusal(self, name: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(ra.RoleAttributeError) as caught:
            ra.stated_role_attribute(name)
        return caught.exception.code


class TestTheStatedSet(AttributeNameCase):
    def test_the_tuple_reconstructs_the_paragraph_743_clause_exactly(self) -> None:
        """Membership, order, spelling and the source's own separators in one assertion."""
        self.assertEqual(", ".join(ra.ROLE_ATTRIBUTES[:4]) + " and " + ra.ROLE_ATTRIBUTES[4],
                         PARAGRAPH_743_CLAUSE)

    def test_the_public_constant_is_an_immutable_tuple_of_five(self) -> None:
        """The container type, which the round trip above cannot see.

        `join` and `len` are both indifferent to tuple versus list, so this is asserted on its
        own rather than left to be caught incidentally -- the omission slice 10 was corrected for.
        """
        self.assertIsInstance(ra.ROLE_ATTRIBUTES, tuple)
        self.assertEqual(len(ra.ROLE_ATTRIBUTES), 5)
        self.assertEqual(len(set(ra.ROLE_ATTRIBUTES)), 5)

    def test_every_stated_name_is_admitted_and_returned_unchanged(self) -> None:
        for name in ra.ROLE_ATTRIBUTES:
            with self.subTest(name=name):
                self.assertEqual(ra.stated_role_attribute(name), name)

    def test_the_lookup_set_cannot_be_added_to_at_runtime(self) -> None:
        """A mutable lookup set would let any code in the process admit an unstated attribute.

        Named `BYPASSRLS` here rather than an arbitrary string because that is the one addition
        with a security flavour. The lane's closure check does not cover this: it tests whether a
        mutated name is module-level in the file being checked, and does not reach state inside
        an imported module.
        """
        self.assertIsInstance(ra._ATTRIBUTES, frozenset)
        with self.assertRaises(AttributeError):
            ra._ATTRIBUTES.add("BYPASSRLS")  # type: ignore[attr-defined]


class TestTheSubstringTrap(AttributeNameCase):
    def test_the_negated_forms_own_positives_are_refused(self) -> None:
        """Each of these is a substring of a stated attribute and is not itself stated.

        `SUPERUSER` sits inside `NOSUPERUSER`, `BYPASSRLS` inside `NOBYPASSRLS`, `CREATEDB`
        inside `NOCREATEDB`, `CREATEROLE` inside `NOCREATEROLE`. A loose match reports all four
        as stated; whole-word matching finds each of them zero times in paragraph 743 and zero
        across the whole pinned TSD. It is the one refusal here whose absence could propagate
        into a security-relevant claim, and `BYPASSRLS` is the sharpest, being the exact negation
        of a required attribute. The refusal is not itself a security control: anything that
        follows from it is mediated entirely by a caller, and no caller exists.
        """
        for name in ("SUPERUSER", "BYPASSRLS", "CREATEDB", "CREATEROLE"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_attribute")

    def test_each_negated_name_contains_its_own_positive_as_a_substring(self) -> None:
        """The trap asserted from the other side, so it cannot quietly stop being true.

        Named for the four names beginning `NO`, not for all five stated names: `LOGIN` contains
        no refused name as a substring, so "each stated name" would be false of one of five. An
        earlier name said exactly that, which is the same false-universal class this lane has
        blocked on in prose.

        The pairs are derived from the module's own tuple rather than listed here. An earlier
        version hardcoded them, which made the substring assertion a tautology over two strings
        the test itself supplied -- it could never fail, and it checked a restatement of the
        tuple instead of the tuple. Deriving them means the premise is checked against the real
        set.

        The containment runs both ways, and the other direction is covered elsewhere rather than
        here: `LOGIN` is a substring of `NOLOGIN`, which is refused by the unstated-attribute
        test, so a matcher asking "does the input contain a stated name" is caught too.

        This test catches no mutation on its own; every one it fires on is also caught elsewhere.
        It is kept for diagnosis: it is the only test whose name states the trap's premise, so if
        a negated name ever stopped containing its own positive, this is the failure a reader
        would understand at once.
        """
        negated = [n for n in ra.ROLE_ATTRIBUTES if n.startswith("NO")]
        self.assertEqual(len(negated), 4)
        for stated in negated:
            inner = stated[2:]
            with self.subTest(stated=stated):
                self.assertIn(inner, stated)
                self.assertEqual(self.refusal(inner), "unstated_attribute")

    def test_another_postgresql_role_attribute_is_refused(self) -> None:
        """Real attributes the source does not state. Unlike slices 7 and 10 there is no
        split between product vocabulary and names absent entirely, because every one of these
        occurs zero times in the pinned TSD -- there is no second population to separate.
        """
        for name in ("NOLOGIN", "REPLICATION", "NOREPLICATION", "INHERIT", "NOINHERIT",
                     "CREATEUSER", "NOCREATEUSER", "PASSWORD", "ENCRYPTED"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_attribute")


class TestFailClosed(AttributeNameCase):
    def test_a_non_string_is_refused_by_its_own_code(self) -> None:
        rejected: tuple[object, ...] = (None, 1, True, 1.0, [], {}, ("LOGIN",), b"LOGIN")
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(value), "bad_attribute_name_type")

    def test_a_str_subclass_is_refused_although_it_compares_equal(self) -> None:
        """`type(name) is not str`: a subclass must not reach the set or the return value."""
        class Sneaky(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __hash__(self) -> int:
                return hash("LOGIN")

        self.assertEqual(self.refusal(Sneaky("LOGIN")), "bad_attribute_name_type")

    def test_case_is_not_folded_and_login_is_the_reason_it_matters(self) -> None:
        """Lower-case "login" occurs eight times in the pinned TSD as an ordinary English word.

        Folding would turn every one of those into an occurrence of a stated role attribute, so
        the cost of case-insensitivity here is concrete rather than theoretical.
        """
        for name in ("login", "Login", "noSuperuser", "nosuperuser", "NoBypassRls",
                     "nobypassrls", "nocreatedb", "NoCreateRole"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_attribute")

    def test_separators_and_padding_are_not_rewritten(self) -> None:
        """The source writes each attribute as one unbroken token."""
        for name in (" LOGIN", "LOGIN ", "NO SUPERUSER", "NO_SUPERUSER", "NO-SUPERUSER",
                     "NOBYPASS RLS", "NOBYPASS_RLS", "LOGIN,", "LOGIN\n"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_attribute")

    def test_an_empty_name_is_refused(self) -> None:
        """Load-bearing well beyond what the name suggests: do not remove it as trivial.

        Of the four loose-match shapes this module must refuse, three fail many tests -- suffix
        matching nine, input-inside-a-stated-name nine, input-containing-a-stated-name five.
        Prefix matching fails exactly **one**, this test, because `any(a.startswith(""))` admits
        the empty string and nothing else in the suite notices. So this single line is the only
        thing between a prefix matcher and a silent pass.
        """
        self.assertEqual(self.refusal(""), "unstated_attribute")

    def test_an_overlong_name_is_refused_before_the_set_lookup(self) -> None:
        """A distinct code, so a caller can tell length from absence."""
        self.assertEqual(self.refusal("A" * (ra.MAX_ATTRIBUTE_NAME_LENGTH + 1)),
                         "attribute_name_too_long")

    def test_the_length_bound_is_this_value_not_merely_this_symbol(self) -> None:
        self.assertEqual(ra.MAX_ATTRIBUTE_NAME_LENGTH, 64)

    def test_every_stated_name_is_well_within_the_length_bound(self) -> None:
        """Otherwise the bound would refuse a name the sources state."""
        for name in ra.ROLE_ATTRIBUTES:
            with self.subTest(name=name):
                self.assertLessEqual(len(name), ra.MAX_ATTRIBUTE_NAME_LENGTH)
        self.assertEqual(max(len(n) for n in ra.ROLE_ATTRIBUTES), 12)

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "INTERNAL_UNRELEASED_ATTRIBUTE"
        with self.assertRaises(ra.RoleAttributeError) as caught:
            ra.stated_role_attribute(secret)
        self.assertEqual(str(caught.exception), "invalid role attribute name")
        self.assertNotIn(secret, str(caught.exception))

    def test_a_non_interned_name_is_admitted_and_returned_as_given(self) -> None:
        """Set membership is by value, and the input object itself comes back.

        `"".join([...])` rather than literal concatenation because CPython folds adjacent
        literals into the interned string. The `assertIs` pins the docstring's claim that the
        name is returned unchanged: a canonicalising return of the set's own member, or of a
        freshly built equal string, is value-identical and invisible to `assertEqual`.
        """
        built = "".join(["NO", "BYPASSRLS"])
        self.assertEqual(built, "NOBYPASSRLS")
        self.assertIsNot(built, "NOBYPASSRLS")
        self.assertEqual(ra.stated_role_attribute(built), "NOBYPASSRLS")
        self.assertIs(ra.stated_role_attribute(built), built)


if __name__ == "__main__":
    unittest.main()

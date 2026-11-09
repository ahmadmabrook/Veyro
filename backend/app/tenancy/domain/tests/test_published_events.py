"""Unit tests for the published-event name closure.

These evidence the pure decision `published_events` makes about one name handed to it. They
evidence no emitted event, no outbox, no delivery, no ordering, no schema, no payload, no database
behaviour, no tenant isolation and no integration. Every refusal is asserted by its `code`.
"""

from __future__ import annotations

import unittest

from .. import published_events as pe


class EventNameCase(unittest.TestCase):
    def refusal(self, name: object) -> str:
        """The `code` of the refusal, asserting that one happened at all."""
        with self.assertRaises(pe.EventNameError) as caught:
            pe.validate_published_event(name)
        return caught.exception.code


class TestTheStatedSet(EventNameCase):
    def test_the_set_is_exactly_these_six_in_this_order(self) -> None:
        """Membership and order, because paragraph 1206 and paragraph 1241 both state both."""
        self.assertEqual(pe.PUBLISHED_EVENTS, (
            "tenant.provisioned",
            "tenant.activated",
            "tenant.suspended",
            "organization.updated",
            "location.opened",
            "brand.created",
        ))

    def test_every_stated_name_is_admitted_and_returned_unchanged(self) -> None:
        for name in pe.PUBLISHED_EVENTS:
            with self.subTest(name=name):
                self.assertEqual(pe.validate_published_event(name), name)

    def test_the_set_has_no_duplicates(self) -> None:
        self.assertEqual(len(pe.PUBLISHED_EVENTS), len(set(pe.PUBLISHED_EVENTS)))

    def test_the_lookup_set_cannot_be_added_to_at_runtime(self) -> None:
        """A mutable lookup set would let any code in the process admit an unstated name.

        That is the gap-filling this slice refuses, reached by mutating state rather than by
        editing the tuple. The lane's closure check does not cover it: its module-state rule
        reaches only mutations written in the file being checked.
        """
        self.assertIsInstance(pe._PUBLISHED, frozenset)
        with self.assertRaises(AttributeError):
            pe._PUBLISHED.add("tenant.deleted")  # type: ignore[attr-defined]


class TestTheRecordedSourceGap(EventNameCase):
    def test_the_archived_and_deleted_events_are_refused(self) -> None:
        """MOD-004.md records both as absent from paragraph 1206; refusing is not filling the gap.

        These are the two an author implementing PLT-01-R01's lifecycle is pulled toward, and
        neither is stated by any pinned source.
        """
        self.assertEqual(self.refusal("tenant.archived"), "unstated_event")
        self.assertEqual(self.refusal("tenant.deleted"), "unstated_event")

    def test_other_plausible_but_unstated_names_are_refused(self) -> None:
        """Each verified absent from the pinned extract before being listed here."""
        for name in ("tenant.relocated", "brand.updated", "location.closed",
                     "organization.created", "tenant.updated", "brand.deleted"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_event")


class TestFailClosed(EventNameCase):
    def test_a_non_string_is_refused_by_its_own_code(self) -> None:
        rejected: tuple[object, ...] = (None, 1, True, 1.0, [], {}, ("tenant.activated",))
        for value in rejected:
            with self.subTest(value=value):
                self.assertEqual(self.refusal(value), "bad_event_name_type")

    def test_a_str_subclass_is_refused_although_it_compares_equal(self) -> None:
        """`type(name) is not str`: a subclass must not reach the set or the return value."""
        class Sneaky(str):
            def __eq__(self, other: object) -> bool:
                return True

            def __hash__(self) -> int:
                return hash("tenant.activated")

        self.assertEqual(self.refusal(Sneaky("tenant.activated")), "bad_event_name_type")

    def test_the_name_is_not_normalized(self) -> None:
        """Case-folding or trimming would admit spellings the sources do not state."""
        for name in ("Tenant.Activated", "TENANT.ACTIVATED", " tenant.activated",
                     "tenant.activated ", "tenant .activated", "tenant..activated"):
            with self.subTest(name=name):
                self.assertEqual(self.refusal(name), "unstated_event")

    def test_an_empty_name_is_refused(self) -> None:
        self.assertEqual(self.refusal(""), "unstated_event")

    def test_an_overlong_name_is_refused_before_the_set_lookup(self) -> None:
        """A distinct code, so a caller can tell length from absence."""
        self.assertEqual(self.refusal("a" * (pe.MAX_EVENT_NAME_LENGTH + 1)),
                         "event_name_too_long")

    def test_the_length_bound_is_this_value_not_merely_this_symbol(self) -> None:
        self.assertEqual(pe.MAX_EVENT_NAME_LENGTH, 64)

    def test_every_stated_name_is_within_the_length_bound(self) -> None:
        """Otherwise the bound would refuse a name the sources state."""
        for name in pe.PUBLISHED_EVENTS:
            with self.subTest(name=name):
                self.assertLessEqual(len(name), pe.MAX_EVENT_NAME_LENGTH)

    def test_the_refusal_message_carries_no_raw_input(self) -> None:
        secret = "tenant.secret-internal-name"
        with self.assertRaises(pe.EventNameError) as caught:
            pe.validate_published_event(secret)
        self.assertEqual(str(caught.exception), "invalid published event name")
        self.assertNotIn(secret, str(caught.exception))

    def test_a_non_interned_name_is_admitted_and_returned_as_given(self) -> None:
        """Set membership is by value, and the input object itself comes back.

        Named for what it pins rather than for a value-versus-identity distinction, which `in`
        against a frozenset does not have -- there is no identity variant of set membership to
        degrade. `"".join([...])` rather than literal concatenation because CPython folds
        adjacent literals into the interned string, which made an earlier version vacuous.
        The `assertIs` is what pins the module docstring's claim that the name is returned
        unchanged: a canonicalising return of the set's own member is value-identical and
        invisible to `assertEqual`.
        """
        built = "".join(["tenant.", "activated"])
        self.assertEqual(built, "tenant.activated")
        self.assertIsNot(built, "tenant.activated")
        self.assertEqual(pe.validate_published_event(built), "tenant.activated")
        self.assertIs(pe.validate_published_event(built), built)


if __name__ == "__main__":
    unittest.main()

"""MOD-004 S0 scenario tests (S0-01..S0-14) for the pure ProvisionTenant envelope validator.

Shape validation only. Rows stay NOT RUN/not PASS until the packet's PASS rule is met.
"""

import ast
from pathlib import Path
from types import MappingProxyType
from typing import Mapping  # noqa: UP035 (runner allowlist omits collections.abc)
from unittest import TestCase, main
from uuid import UUID

try:
    from backend.app import tenancy_s0 as s0
except ImportError:
    from app import tenancy_s0 as s0

ACTOR = "11111111-1111-4111-8111-111111111111"
CORR = "22222222-2222-4222-9222-222222222222"
IDEM = "33333333-3333-4333-a333-333333333333"
KEY = "tenant-ext_01.alpha:beta"
FIELDS = ("external_key", "actor_id", "correlation_id", "idempotency_key")

# Literal positive allowlist, equal to or stricter than the runner's S0_PRODUCT_MODULES / S0_NAMES.
PRODUCT_ALLOWED = {
    "__future__": {"annotations"},
    "re": {"compile", "ASCII"},
    "dataclasses": {"dataclass"},
}


BANNED_NAMES = {"open", "eval", "exec", "compile", "getattr", "vars", "__import__", "print"}
ABSENT = object()


def make(**changes):
    """Fresh literal envelope on every call; a value of ABSENT removes the key."""
    base = {
        "external_key": KEY,
        "actor_id": ACTOR,
        "correlation_id": CORR,
        "idempotency_key": IDEM,
    }
    for name, value in changes.items():
        if value is ABSENT:
            del base[name]
        else:
            base[name] = value
    return base


class Hostile(Mapping):
    """Custom Mapping whose methods must never be reached."""

    def __getitem__(self, key):
        raise AssertionError("hostile __getitem__ called")

    def __iter__(self):
        raise AssertionError("hostile __iter__ called")

    def __len__(self):
        raise AssertionError("hostile __len__ called")


class HostileDict(dict):
    def items(self):
        raise AssertionError("hostile items called")

    def __getitem__(self, key):
        raise AssertionError("hostile __getitem__ called")

    def __iter__(self):
        raise AssertionError("hostile __iter__ called")


class ProvisionTenantS0Tests(TestCase):
    @classmethod
    def setUpClass(cls):
        # The single bounded read: the sibling product source, for static assertions only.
        product = Path(__file__).resolve().parents[1] / "app" / "tenancy_s0.py"
        cls.product_source = product.read_text(encoding="utf-8")

    def reject(self, value, label=""):
        with self.assertNoLogs():
            with self.assertRaises(s0.EnvelopeError) as ctx:
                s0.validate_provision_tenant(value)
        exc = ctx.exception
        self.assertIsNone(exc.__cause__, label)
        self.assertIsNone(exc.__context__, label)
        self.assertEqual(exc.args, ("invalid ProvisionTenant envelope",), label)
        return exc

    def accept(self, value):
        with self.assertNoLogs():
            return s0.validate_provision_tenant(value)

    # S0-01
    def test_s0_01_valid_envelope(self):
        result = self.accept(make())
        self.assertIsInstance(result, s0.ProvisionTenantEnvelope)
        self.assertEqual(result.external_key, KEY)
        self.assertEqual(result.actor_id, ACTOR)
        self.assertEqual(result.correlation_id, CORR)
        self.assertEqual(result.idempotency_key, IDEM)
        self.assertIsNone(result.expected_version)
        self.assertEqual(
            set(s0.ProvisionTenantEnvelope.__slots__),
            {"external_key", "actor_id", "correlation_id", "idempotency_key", "expected_version"},
        )

    # S0-02
    def test_s0_02_missing_fields(self):
        for name in FIELDS:
            with self.subTest(missing=name):
                self.reject(make(**{name: ABSENT}), name)
        with self.subTest(empty=True):
            self.reject({})

    # S0-03
    def test_s0_03_extra_keys_types_and_mappings(self):
        for extra in ("tenant_id", "", "x" * 10_000, "EXTERNAL_KEY"):
            with self.subTest(extra_len=len(extra)):
                value = make()
                value[extra] = "v"
                self.reject(value)
        with self.subTest(nested_extra=True):
            value = make()
            value["extra"] = {"a": {"b": 1}}
            self.reject(value)
        for bad_key in (1, None, b"external_key", (1,), 1.5, True):
            with self.subTest(key_type=type(bad_key).__name__):
                value = make()
                value[bad_key] = "v"
                self.reject(value)
        for name in FIELDS:
            for bad in (None, 1, 1.5, True, b"x", ["a"], {"a": 1}, ("a",), object()):
                with self.subTest(field=name, value_type=type(bad).__name__):
                    self.reject(make(**{name: bad}))
        # Policy: only an exact dict is accepted; subclasses and other mappings
        # are rejected untouched.
        for label, value in (
            ("dict_subclass", HostileDict(make())),
            ("custom_mapping", Hostile()),
            ("mappingproxy", MappingProxyType(make())),
        ):
            with self.subTest(mapping=label):
                self.reject(value)
        # NOT APPLICABLE: duplicate serialized keys; the API takes in-memory
        # mappings, not JSON text.

    # S0-04
    def test_s0_04_external_key_bounds(self):
        limit = s0.EXTERNAL_KEY_MAX_LENGTH
        for label, value in (("one", "a"), ("at_bound", "a" * limit), ("punct", "a.b_c:d-e")):
            with self.subTest(accept=label):
                self.assertEqual(self.accept(make(external_key=value)).external_key, value)
        for label, value in (
            ("empty", ""),
            ("space", " "),
            ("padded", " a"),
            ("over_bound", "a" * (limit + 1)),
            ("huge", "a" * 1_000_000),
            ("bad_start", "-a"),
            ("slash", "a/b"),
            ("dotdot", "../a"),
            ("not_str", 5),
        ):
            with self.subTest(reject=label):
                self.reject(make(external_key=value))

    # S0-05
    def test_s0_05_uuid_matrix(self):
        for name in ("actor_id", "correlation_id", "idempotency_key"):
            for label, value in (
                ("empty", ""),
                ("short", ACTOR[:-1]),
                ("long", ACTOR + "0"),
                ("non_hex", "g" * 8 + ACTOR[8:]),
                ("nil", "00000000-0000-0000-0000-000000000000"),
                ("none", None),
                ("int", 1),
                ("bytes", ACTOR.encode()),
            ):
                with self.subTest(field=name, case=label):
                    self.reject(make(**{name: value}))

    # S0-06
    def test_s0_06_idempotency_is_retained_not_deduplicated(self):
        first = self.accept(make())
        second = self.accept(make())
        self.assertEqual(first.idempotency_key, IDEM)
        self.assertEqual(first, second)
        self.reject(make(idempotency_key=ABSENT))

    # S0-07
    def test_s0_07_expected_version(self):
        top = s0.EXPECTED_VERSION_MAX
        with self.subTest(absent=True):
            self.assertIsNone(self.accept(make()).expected_version)
        for label, value in (("zero", 0), ("one", 1), ("bound", top)):
            with self.subTest(accept=label):
                self.assertEqual(self.accept(make(expected_version=value)).expected_version, value)
        for label, value in (
            ("present_null", None),
            ("negative", -1),
            ("bound_plus_one", top + 1),
            ("huge", 10**100),
            ("true", True),
            ("false", False),
            ("float", 1.0),
            ("fractional", 0.5),
            ("nan", float("nan")),
            ("inf", float("inf")),
            ("neg_inf", float("-inf")),
            ("str", "1"),
            ("list", [1]),
            ("dict", {"v": 1}),
            ("tuple", (1,)),
            ("bytes", b"1"),
        ):
            with self.subTest(reject=label):
                self.reject(make(expected_version=value))
        # TSD 1237 / ADR-0002 D6.3 discrepancy stays documented, not resolved.
        self.assertIn("TSD paragraph 1237", s0.__doc__)
        self.assertIn("ADR-0002", s0.__doc__)

    # S0-08
    def test_s0_08_claims_are_not_promoted(self):
        result = self.accept(make())
        for name in ("principal", "tenant", "tenant_id", "authenticated", "authorized", "context"):
            with self.subTest(attr=name):
                self.assertFalse(hasattr(result, name))
        self.assertNotIn("tenant", " ".join(s0.ProvisionTenantEnvelope.__slots__))

    # S0-09
    def test_s0_09_import_closure(self):
        tree = ast.parse(self.product_source)
        seen = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    seen += 1
                    with self.subTest(import_name=item.name):
                        self.assertIn(item.name, PRODUCT_ALLOWED)
            elif isinstance(node, ast.ImportFrom):
                with self.subTest(import_from=node.module):
                    self.assertEqual(node.level, 0)
                    self.assertIn(node.module, PRODUCT_ALLOWED)
                    for item in node.names:
                        seen += 1
                        self.assertIn(item.name, PRODUCT_ALLOWED[node.module])
            elif isinstance(node, ast.Name):
                with self.subTest(name=node.id):
                    self.assertNotIn(node.id, BANNED_NAMES)
        self.assertGreaterEqual(seen, 3)

    # S0-10
    def test_s0_10_purity_and_immutability(self):
        source = make(expected_version=7)
        result = self.accept(source)
        self.assertEqual(source, make(expected_version=7))
        self.assertEqual(result, self.accept(make(expected_version=7)))
        source["external_key"] = "changed"
        self.assertEqual(result.external_key, KEY)
        with self.assertRaises(AttributeError):
            result.external_key = "x"
        bad = make(actor_id="nope")
        self.reject(bad)
        self.assertEqual(bad, make(actor_id="nope"))
        for _ in range(3):
            self.assertEqual(self.accept(make()), self.accept(make()))

    # S0-11
    def test_s0_11_uuid_text_forms(self):
        upper = ACTOR.upper()
        self.assertEqual(self.accept(make(actor_id=upper)).actor_id, ACTOR)
        for name, text in (
            ("actor_id", ACTOR),
            ("correlation_id", CORR),
            ("idempotency_key", IDEM),
        ):
            with self.subTest(uuid_instance=name):
                self.reject(make(**{name: UUID(text)}))
        for label, value in (
            ("braced", "{" + ACTOR + "}"),
            ("urn", "urn:uuid:" + ACTOR),
            ("hyphenless", ACTOR.replace("-", "")),
            ("leading_space", " " + ACTOR),
            ("trailing_space", ACTOR + " "),
            ("trailing_newline", ACTOR + "\n"),
            ("bad_variant", "11111111-1111-4111-c111-111111111111"),
            ("version_zero", "11111111-1111-0111-8111-111111111111"),
            ("version_nine", "11111111-1111-9111-8111-111111111111"),
            ("max_uuid", "ffffffff-ffff-ffff-ffff-ffffffffffff"),
            ("non_ascii_digit", "١" * 8 + ACTOR[8:]),
        ):
            with self.subTest(reject=label):
                self.reject(make(actor_id=value))

    # S0-12
    def test_s0_12_external_key_characters(self):
        for label, value in (
            ("non_ascii", "ténant"),
            ("nfd", "é"),
            ("nul", "a\x00b"),
            ("newline", "a\nb"),
            ("trailing_newline", "abc\n"),
            ("tab", "a\tb"),
            ("control", "a\x1fb"),
            ("del", "a\x7fb"),
            ("space_inside", "a b"),
            ("bidi_rlo", "a‮b"),
            ("bidi_isolate", "a⁦b"),
            ("zero_width", "a​b"),
            ("lone_surrogate", "a\ud800b"),
            ("fullwidth", "Ａ"),
        ):
            with self.subTest(reject=label):
                self.reject(make(external_key=value))

    # S0-13
    def test_s0_13_top_level_and_resource_bounds(self):
        for label, value in (
            ("none", None),
            ("list", [make()]),
            ("str", "{}"),
            ("bytes", b"{}"),
            ("int", 1),
            ("tuple", (make(),)),
        ):
            with self.subTest(top_level=label):
                self.reject(value)
        oversize = {f"k{i}": i for i in range(s0.MAX_FIELDS + 1)}
        with self.subTest(oversize=True):
            self.reject(oversize)
        deep = {}
        cursor = deep
        for _ in range(100_000):
            cursor["n"] = {}
            cursor = cursor["n"]
        with self.subTest(deep=True):
            value = make()
            value["extra"] = deep
            self.reject(value)
        with self.subTest(deep_in_field=True):
            self.reject(make(external_key=deep))
        cyclic = make()
        cyclic["extra"] = cyclic
        with self.subTest(cyclic_extra=True):
            self.reject(cyclic)
        cyclic_field = make()
        cyclic_field["external_key"] = cyclic_field
        with self.subTest(cyclic_field=True):
            self.reject(cyclic_field)

    # S0-14
    def test_s0_14_no_raw_input_in_errors(self):
        secret = "SECRET-opaque-key-0001"
        secret_uuid = "deadbeef-dead-4ead-8ead-deadbeef0000"
        cases = (
            ("key", make(external_key=secret + "!")),
            ("actor", make(actor_id=secret_uuid + "x")),
            ("extra", dict(make(), **{secret: secret})),
            ("version", make(expected_version=secret)),
            ("top", secret),
        )
        for label, value in cases:
            with self.subTest(case=label):
                exc = self.reject(value)
                for text in (str(exc), repr(exc), repr(exc.args)):
                    self.assertNotIn("SECRET", text)
                    self.assertNotIn("deadbeef", text)
                self.assertIsInstance(exc.code, str)
        for node in ast.walk(ast.parse(self.product_source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                with self.subTest(call=node.func.id):
                    self.assertNotEqual(node.func.id, "print")


if __name__ == "__main__":
    main()

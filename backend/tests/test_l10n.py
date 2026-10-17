import ast
import sys
import time
import unicodedata
import unittest
from pathlib import Path
from types import MappingProxyType

from app.l10n import conventions, messages
from app.l10n.conventions import (
    FSI,
    LRI,
    PDI,
    RLI,
    contrast_ratio,
    direction,
    format_integer,
    format_money,
    isolate,
    meets_aa_text,
    parse_locale,
    relative_luminance,
    sanitize_untrusted,
    shape_digits,
)
from app.l10n.fixture import render_balance_line
from app.l10n.messages import load_catalog, plural_category, qa_gaps, translate

OVERRIDES = [chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))]
# Invisible controls built from code points so this file holds no literal bidi/format chars.
RLO = chr(0x202E)
PDI_CHAR = chr(0x2069)
LRI_CHAR = chr(0x2066)
ZWJ, LRM, RLM = chr(0x200D), chr(0x200E), chr(0x200F)
L10N_DIR = Path(conventions.__file__).parent


AR_1234567 = "١٬٢٣٤٬٥٦٧"
AR_JOD_12345 = "JOD ١٢٫٣٤٥"


class LocaleTests(unittest.TestCase):
    def test_hp_supported_locales_and_direction(self):
        self.assertEqual(parse_locale("ar"), "ar")
        self.assertEqual(parse_locale("en"), "en")
        self.assertEqual(direction("ar"), "rtl")
        self.assertEqual(direction("en"), "ltr")

    def test_neg_unknown_or_malformed_tags_fail_closed(self):
        for tag in ("fr", "AR", "ar-JO", "en_US", "", " ar", "ar\n", None, 5, b"ar"):
            with self.assertRaises(ValueError, msg=repr(tag)):
                parse_locale(tag)
            with self.assertRaises(ValueError, msg=repr(tag)):
                direction(tag)


class BidiTests(unittest.TestCase):
    def test_hp_isolate_wraps_with_matching_controls(self):
        self.assertEqual(isolate("x", "rtl"), RLI + "x" + PDI)
        self.assertEqual(isolate("x", "ltr"), LRI + "x" + PDI)
        self.assertEqual(isolate("x", "auto"), FSI + "x" + PDI)

    def test_val_unknown_direction_and_non_string_rejected(self):
        with self.assertRaises(ValueError):
            isolate("x", "up")
        with self.assertRaises(TypeError):
            sanitize_untrusted(b"x")

    def test_sec_overrides_and_isolates_removed(self):
        hostile = "a" + "".join(OVERRIDES) + "b"
        self.assertEqual(sanitize_untrusted(hostile), "ab")

    def test_sec_embedded_pdi_cannot_close_isolate_early(self):
        result = isolate("pay" + PDI + RLO + "evil", "ltr")
        self.assertEqual(result, LRI + "payevil" + PDI)
        self.assertEqual(result.count(PDI), 1)

    def test_bnd_empty_combining_and_mixed_text_preserved(self):
        self.assertEqual(sanitize_untrusted(""), "")
        self.assertEqual(isolate("", "auto"), FSI + PDI)
        samples = ("é", "مَ", "أحمد Ahmed 42 ١٢", ZWJ + LRM + RLM)
        for text in samples:
            self.assertEqual(sanitize_untrusted(text), text)


class DigitTests(unittest.TestCase):
    def test_hp_shaping_both_directions_and_roundtrip(self):
        self.assertEqual(shape_digits("abc 123", "arab"), "abc ١٢٣")
        self.assertEqual(shape_digits("abc ١٢٣", "latn"), "abc 123")
        mixed = "x 0123456789 ٠٩"
        self.assertEqual(shape_digits(shape_digits(mixed, "arab"), "latn"), "x 0123456789 09")
        self.assertEqual(shape_digits("² x", "arab"), "² x")

    def test_numbering_is_explicit_and_validated(self):
        for bad in ("", "ar", "en", "LATN", None):
            with self.assertRaises(ValueError):
                shape_digits("1", bad)
            with self.assertRaises(ValueError):
                format_integer(1, bad)

    def test_hp_and_bnd_integer_grouping(self):
        self.assertEqual(format_integer(1234567, "latn"), "1,234,567")
        self.assertEqual(format_integer(1234567, "arab"), AR_1234567)
        self.assertEqual(format_integer(0, "latn"), "0")
        self.assertEqual(format_integer(0, "arab"), "٠")
        self.assertEqual(format_integer(-1234, "latn"), "-1,234")
        self.assertEqual(format_integer(1234567, "latn", grouping=False), "1234567")
        self.assertEqual(format_integer(10**30, "latn"), "1" + ",000" * 10)

    def test_neg_non_integer_input_rejected(self):
        for bad in (1.0, 1.5, True, "1", None):
            with self.assertRaises(TypeError, msg=repr(bad)):
                format_integer(bad, "latn")


class MoneyTests(unittest.TestCase):
    def test_hp_iso_code_and_minor_units(self):
        self.assertEqual(format_money(12345, "JOD", "latn", "en"), "JOD 12.345")
        self.assertEqual(format_money(5, "USD", "latn", "en"), "USD 0.05")
        self.assertEqual(format_money(7, "JOD", "latn", "en"), "JOD 0.007")

    def test_hp_arabic_text_isolates_money_ltr(self):
        self.assertEqual(format_money(12345, "JOD", "latn", "ar"), LRI + "JOD 12.345" + PDI)
        self.assertEqual(format_money(12345, "JOD", "arab", "ar"), LRI + AR_JOD_12345 + PDI)
        self.assertEqual(format_money(12345, "JOD", "arab", "en"), AR_JOD_12345)

    def test_bnd_zero_negative_and_very_large(self):
        self.assertEqual(format_money(0, "JOD", "latn", "en"), "JOD 0.000")
        self.assertEqual(format_money(-5, "USD", "latn", "en"), "USD -0.05")
        self.assertEqual(format_money(10**20, "USD", "latn", "en"), "USD 1" + ",000" * 6 + ".00")

    def test_neg_unknown_currency_and_float_amount(self):
        for code in ("EUR", "jod", "", "JOD ", "SAR"):
            with self.assertRaises(ValueError) as caught:
                format_money(1, code, "latn", "en")
            self.assertEqual(str(caught.exception), "unsupported currency")
        with self.assertRaises(TypeError):
            format_money(1.5, "JOD", "latn", "en")
        with self.assertRaises(ValueError):
            format_money(1, "JOD", "latn", "fr")

    def test_no_localized_symbols(self):
        text = format_money(100, "USD", "latn", "ar") + format_money(100, "JOD", "arab", "ar")
        for symbol in ("$", "د.أ", "دينار"):
            self.assertNotIn(symbol, text)


class MessageTests(unittest.TestCase):
    def test_hp_plain_and_plural_messages(self):
        self.assertEqual(translate("items.count", "en", {"count": "1"}, count=1).text, "1 item")
        self.assertEqual(translate("items.count", "en", {"count": "3"}, count=3).text, "3 items")
        self.assertEqual(translate("items.count", "ar", count=0).text, "لا عناصر")
        self.assertEqual(translate("items.count", "ar", count=2).text, "عنصران")
        self.assertEqual(translate("items.count", "ar", {"count": "5"}, count=5).text, "5 عناصر")
        result = translate("items.count", "ar", {"count": "5"}, count=5)
        self.assertEqual((result.locale, result.fallback), ("ar", False))

    def test_hp_cldr_plural_categories(self):
        expected_ar = {
            0: "zero", 1: "one", 2: "two", 3: "few", 10: "few", 11: "many", 99: "many",
            100: "other", 101: "other", 102: "other", 103: "few", 111: "many", 200: "other",
        }  # fmt: skip
        for count, category in expected_ar.items():
            self.assertEqual(plural_category("ar", count), category, count)
        for count, category in {0: "other", 1: "one", 2: "other", 21: "other"}.items():
            self.assertEqual(plural_category("en", count), category, count)

    def test_val_plural_count_validation(self):
        with self.assertRaises(ValueError):
            plural_category("ar", -1)
        for bad in (1.0, True, "1", None):
            with self.assertRaises(TypeError):
                plural_category("ar", bad)
        with self.assertRaises(ValueError):
            translate("items.count", "en", {"count": "1"})

    def test_neg_unknown_and_malformed_placeholders(self):
        catalogs = {"en": {"k": "hi {name} {nope}"}, "ar": {}}
        with self.assertRaises(ValueError):
            translate("k", "en", {"name": "x"}, catalogs=catalogs)
        for template in ("hi {", "hi }", "hi {Name}", "hi {}", "hi {a b}"):
            with self.assertRaises(ValueError, msg=template):
                translate("k", "en", {"a": "x", "name": "x"}, catalogs={"en": {"k": template}})
        with self.assertRaises(TypeError):
            translate("k", "en", {"name": 1}, catalogs={"en": {"k": "{name}"}})

    def test_sec_placeholder_values_are_not_reexpanded(self):
        catalogs = {"en": {"k": "hi {name}"}}
        self.assertEqual(translate("k", "en", {"name": "{k}"}, catalogs=catalogs).text, "hi {k}")

    def test_missing_ar_key_falls_back_to_en(self):
        catalogs = {"en": {"k": "hello {name}"}, "ar": {}}
        result = translate("k", "ar", {"name": "x"}, catalogs=catalogs)
        self.assertEqual((result.text, result.locale, result.fallback), ("hello x", "en", True))

    def test_incomplete_ar_plural_falls_back_to_en(self):
        catalogs = {
            "en": {"k": {"one": "one item", "other": "many items"}},
            "ar": {"k": {"one": "x", "other": "y"}},
        }
        result = translate("k", "ar", count=5, catalogs=catalogs)
        self.assertEqual((result.text, result.locale, result.fallback), ("many items", "en", True))

    def test_neg_missing_everywhere_and_bad_locale(self):
        with self.assertRaises(ValueError):
            translate("no.such.key", "ar")
        with self.assertRaises(ValueError):
            translate("balance.line", "fr", {"member": "m", "amount": "a"})

    def test_catalogs_are_immutable_views(self):
        catalog = load_catalog("en")
        self.assertIsInstance(catalog, MappingProxyType)
        with self.assertRaises(TypeError):
            catalog["x"] = "y"


class QaGateTests(unittest.TestCase):
    """R08: any localization gap fails CI."""

    def shipped(self):
        return {"ar": load_catalog("ar"), "en": load_catalog("en")}

    def test_shipped_catalogs_have_no_gaps(self):
        self.assertEqual(qa_gaps(self.shipped()), [])

    def test_key_parity(self):
        ar, en = load_catalog("ar"), load_catalog("en")
        self.assertEqual(set(ar), set(en))

    def test_placeholder_parity(self):
        ar, en = load_catalog("ar"), load_catalog("en")
        for key in en:
            self.assertEqual(
                messages.entry_placeholders(ar[key]), messages.entry_placeholders(en[key]), key
            )

    def test_ar_has_every_required_plural_category(self):
        required = {"zero", "one", "two", "few", "many", "other"}
        plurals = [e for e in load_catalog("ar").values() if not isinstance(e, str)]
        self.assertTrue(plurals)
        for entry in plurals:
            self.assertEqual(set(entry), required)

    def test_gate_detects_each_kind_of_gap(self):
        ar_plural = {c: "{n}" for c in ("zero", "one", "two", "few", "many", "other")}
        en_plural = {"one": "{n}", "other": "{n}"}
        ok = {"en": {"a": "{x}", "p": en_plural}, "ar": {"a": "{x}", "p": ar_plural}}
        self.assertEqual(qa_gaps(ok), [])
        cases = {
            "missing-ar:a": {"en": ok["en"], "ar": {"p": ar_plural}},
            "extra-ar:z": {"en": ok["en"], "ar": {**ok["ar"], "z": "z"}},
            "placeholder-mismatch:a": {"en": ok["en"], "ar": {**ok["ar"], "a": "{y}"}},
            "shape-mismatch:a": {"en": ok["en"], "ar": {**ok["ar"], "a": ar_plural}},
            "plural-categories:ar:p": {
                "en": ok["en"],
                "ar": {**ok["ar"], "p": {k: v for k, v in ar_plural.items() if k != "many"}},
            },
        }
        for expected, catalogs in cases.items():
            self.assertIn(expected, qa_gaps(catalogs), expected)


class ContrastTests(unittest.TestCase):
    def test_hp_known_wcag_values(self):
        self.assertAlmostEqual(relative_luminance("#000000"), 0.0)
        self.assertAlmostEqual(relative_luminance("#ffffff"), 1.0)
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0)
        self.assertAlmostEqual(contrast_ratio("#ffffff", "#000000"), 21.0)
        self.assertAlmostEqual(contrast_ratio("#767676", "#ffffff"), 4.54, places=2)

    def test_bnd_aa_threshold(self):
        self.assertTrue(meets_aa_text("#767676", "#ffffff"))
        self.assertFalse(meets_aa_text("#777777", "#ffffff"))
        self.assertFalse(meets_aa_text("#ffffff", "#ffffff"))

    def test_val_invalid_colors_rejected(self):
        for bad in ("red", "#fff", "#12345g", "#1234567", "", "#ffffff\n", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                relative_luminance(bad)


class FixtureTests(unittest.TestCase):
    def test_hp_english_and_arabic_lines(self):
        en = render_balance_line("en", "latn", "Sara", 1234, "JOD")
        self.assertEqual(
            en, {"lang": "en", "dir": "ltr", "text": f"Balance for {FSI}Sara{PDI}: JOD 1.234"}
        )
        ar = render_balance_line("ar", "latn", "Sara", 1234, "JOD")
        self.assertEqual(
            ar,
            {"lang": "ar", "dir": "rtl", "text": f"رصيد {FSI}Sara{PDI}: {LRI}JOD 1.234{PDI}"},
        )

    def test_hp_mixed_script_name_and_arabic_numbering(self):
        line = render_balance_line("ar", "arab", "أحمد Ahmed 42", 1234, "JOD")
        self.assertIn(f"{FSI}أحمد Ahmed 42{PDI}", line["text"])
        self.assertIn(f"{LRI}JOD ١٫٢٣٤{PDI}", line["text"])

    def test_locale_switch_changes_lang_dir_text_only(self):
        for numbering in ("latn", "arab"):
            en = render_balance_line("en", numbering, "Sara", 50, "USD")
            ar = render_balance_line("ar", numbering, "Sara", 50, "USD")
            self.assertEqual((en["lang"], en["dir"]), ("en", "ltr"))
            self.assertEqual((ar["lang"], ar["dir"]), ("ar", "rtl"))
            self.assertNotEqual(en["text"], ar["text"])

    def test_sec_bidi_override_injection_neutralized(self):
        hostile_name = "Ali" + RLO + PDI_CHAR + "evil" + LRI_CHAR
        for locale in ("ar", "en"):
            line = render_balance_line(locale, "latn", hostile_name, 1234, "JOD")
            self.assertIn(f"{FSI}Alievil{PDI}", line["text"])
            for control in OVERRIDES:
                if control not in (LRI, FSI, PDI):
                    self.assertNotIn(control, line["text"])
            opened = sum(line["text"].count(c) for c in (LRI, RLI, FSI))
            self.assertEqual(opened, line["text"].count(PDI))

    def test_val_and_neg_fail_closed_without_echoing_input(self):
        secret = "SECRET-NAME-" + RLO
        attempts = [
            ("fr", "latn", secret, 1, "JOD"),
            ("en", "xxxx", secret, 1, "JOD"),
            ("en", "latn", secret, 1, "SECRET-CCY"),
            ("en", "latn", "  ", 1, "JOD"),
            ("en", "latn", RLO + PDI_CHAR, 1, "JOD"),
            ("en", "latn", secret, 1.5, "JOD"),
        ]
        for args in attempts:
            with self.assertRaises((ValueError, TypeError)) as caught:
                render_balance_line(*args)
            text = str(caught.exception)
            self.assertNotIn("SECRET", text)
            self.assertNotIn(RLO, text)

    def test_bnd_large_negative_zero_and_combining(self):
        for amount in (0, -1, 10**40):
            for locale in ("ar", "en"):
                line = render_balance_line(locale, "latn", "é", amount, "JOD")
                self.assertIn("JOD", line["text"])

    def test_idem_same_input_same_output(self):
        for locale in ("ar", "en"):
            for numbering in ("latn", "arab"):
                args = (locale, numbering, "أحمد Ahmed", 987654321, "USD")
                self.assertEqual(render_balance_line(*args), render_balance_line(*args))
        self.assertEqual(
            translate("items.count", "ar", {"count": "7"}, count=7),
            translate("items.count", "ar", {"count": "7"}, count=7),
        )


class SourceHygieneTests(unittest.TestCase):
    FORBIDDEN = {"socket", "ssl", "urllib", "http", "logging", "subprocess", "requests", "httpx"}

    def test_sec_stdlib_only_no_network_no_logging(self):
        for path in sorted(L10N_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom):
                    roots = {(node.module or "").split(".")[0]}
                else:
                    continue
                self.assertFalse(roots & self.FORBIDDEN, path.name)
                allowed = sys.stdlib_module_names | {"app"}
                self.assertTrue(roots <= allowed, path.name)

    def test_sec_no_bidi_controls_in_shipped_source(self):
        invisible = OVERRIDES + [chr(c) for c in range(0x200C, 0x2010)]
        paths = [*L10N_DIR.glob("*.py"), *L10N_DIR.glob("catalog/*.json"), Path(__file__)]
        self.assertIn(Path(__file__), paths)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertFalse(any(c in text for c in invisible), path.name)


class PerfBaselineTests(unittest.TestCase):
    def test_perf_catalog_load_and_10k_formats(self):
        messages._read.cache_clear()
        start = time.perf_counter()
        for locale in ("ar", "en"):
            load_catalog(locale)
        load_seconds = time.perf_counter() - start

        start = time.perf_counter()
        for i in range(10_000):
            locale, numbering = ("ar", "en")[i % 2], ("latn", "arab")[i % 3 % 2]
            render_balance_line(locale, numbering, "Sara", i * 7, "JOD")
        format_seconds = time.perf_counter() - start

        print(
            f"\nPERF l10n: catalog load {load_seconds * 1000:.2f} ms, "
            f"10k formats {format_seconds:.3f} s"
        )
        self.assertLess(load_seconds, 1.0)
        self.assertLess(format_seconds, 10.0)


SEPARATORS = [chr(c) for c in (0x0A, 0x0D, 0x1C, 0x1D, 0x1E, 0x85, 0x2028, 0x2029)]
MAX_INT = 2**conventions.MAX_INTEGER_BITS - 1
NAME_MAX = conventions.MAX_UNTRUSTED_TEXT_CHARS
PLACEHOLDER_MAX = conventions.MAX_PLACEHOLDER_CHARS


class HostileControlTests(unittest.TestCase):
    def test_sec_each_paragraph_separator_rejected_with_fixed_error(self):
        for sep in SEPARATORS:
            hostile = "SECRET" + sep + "evil"
            for call in (
                lambda hostile=hostile: sanitize_untrusted(hostile),
                lambda hostile=hostile: isolate(hostile, "auto"),
                lambda hostile=hostile: render_balance_line("en", "latn", hostile, 1, "JOD"),
                lambda hostile=hostile: render_balance_line("ar", "latn", hostile, 1, "JOD"),
            ):
                with self.assertRaises(ValueError, msg=hex(ord(sep))) as caught:
                    call()
                self.assertEqual(str(caught.exception), "text contains a control character")

    def test_sec_non_separator_cc_zl_zp_rejected_with_fixed_error(self):
        # NUL, BEL, TAB, VT, FF, ESC, DEL, C1 range, plus Zl/Zp.
        controls = [chr(c) for c in (0x00, 0x07, 0x09, 0x0B, 0x0C, 0x1B, 0x1F, 0x7F, 0x80, 0x9F)]
        controls += [chr(0x2028), chr(0x2029)]
        for control in controls:
            hostile = "SECRET" + control + "evil"
            for call in (
                lambda hostile=hostile: sanitize_untrusted(hostile),
                lambda hostile=hostile: isolate(hostile, "rtl"),
                lambda hostile=hostile: render_balance_line("ar", "arab", hostile, 1, "JOD"),
            ):
                with self.assertRaises(ValueError, msg=hex(ord(control))) as caught:
                    call()
                self.assertEqual(str(caught.exception), "text contains a control character")
                self.assertNotIn("SECRET", str(caught.exception))

    def test_sec_exact_cc_boundaries(self):
        for code in range(0x00, 0xA0):
            is_cc = unicodedata.category(chr(code)) == "Cc"
            text = "a" + chr(code)
            if is_cc:
                with self.assertRaises(ValueError, msg=hex(code)):
                    sanitize_untrusted(text)
            else:
                self.assertEqual(sanitize_untrusted(text), text, hex(code))
        for code in (0xA0, 0xAD, 0x2027, 0x202F):  # NBSP, soft hyphen, neighbours of Zl/Zp
            self.assertEqual(sanitize_untrusted(chr(code)), chr(code), hex(code))

    def test_sec_control_at_exact_length_limit_rejected_not_too_long(self):
        at = "a" * (NAME_MAX - 1) + chr(0x00)
        with self.assertRaises(ValueError) as caught:
            sanitize_untrusted(at)
        self.assertEqual(str(caught.exception), "text contains a control character")
        with self.assertRaises(ValueError) as caught:
            sanitize_untrusted(at + "a")
        self.assertEqual(str(caught.exception), "text too long")
        self.assertEqual(sanitize_untrusted("a" * NAME_MAX), "a" * NAME_MAX)

    def test_bnd_ordinary_arabic_and_english_text_preserved(self):
        for text in ("سارة", "Sara Ali", "سارة Ali ١٢٣ 123", "x-y_z.@(1)", "مَّ"):
            self.assertEqual(sanitize_untrusted(text), text)
            self.assertEqual(isolate(text, "auto"), FSI + text + PDI)

    def test_sec_separator_after_bidi_control_still_rejected(self):
        for sep in SEPARATORS:
            with self.assertRaises(ValueError):
                sanitize_untrusted(RLO + sep + PDI_CHAR)

    def test_sec_isolate_output_never_contains_separator_or_stray_controls(self):
        for control in OVERRIDES:
            out = isolate("a" + control + "b", "rtl")
            self.assertEqual(out, RLI + "ab" + PDI)
            self.assertFalse(any(s in out for s in SEPARATORS))

    def test_sec_trusted_template_and_amount_remain_protected(self):
        line = render_balance_line("ar", "latn", "Sara" + RLO, 1234, "JOD")
        self.assertEqual(line["text"], f"رصيد {FSI}Sara{PDI}: {LRI}JOD 1.234{PDI}")
        self.assertEqual(format_money(1, "JOD", "latn", "ar"), LRI + "JOD 0.001" + PDI)
        template = "line1\nline2 {name}"
        out = translate("k", "en", {"name": "x"}, catalogs={"en": {"k": template}})
        self.assertEqual(out.text, "line1\nline2 x")  # trusted templates are not filtered

    def test_neg_non_string_member_rejected(self):
        with self.assertRaises(TypeError):
            render_balance_line("en", "latn", b"Sara", 1, "JOD")


class BoundsTests(unittest.TestCase):
    def test_bnd_integer_and_money_at_and_beyond_limit(self):
        limit = 2**conventions.MAX_INTEGER_BITS
        for sign in (1, -1):
            self.assertTrue(format_integer(sign * (limit - 1), "latn"))
            with self.assertRaises(ValueError) as caught:
                format_integer(sign * limit, "latn")
            self.assertEqual(str(caught.exception), "integer out of range")
            self.assertTrue(format_money(sign * (limit - 1), "JOD", "arab", "ar"))
            with self.assertRaises(ValueError) as caught:
                format_money(sign * limit, "JOD", "latn", "en")
            self.assertEqual(str(caught.exception), "integer out of range")
        self.assertGreater(limit, 10**40)

    def test_bnd_huge_integer_rejected_without_conversion(self):
        huge = 10**100000
        for call in (
            lambda: format_integer(huge, "latn"),
            lambda: format_money(huge, "USD", "latn", "en"),
            lambda: plural_category("ar", huge),
            lambda: render_balance_line("en", "latn", "Sara", huge, "JOD"),
        ):
            with self.assertRaises(ValueError):
                call()

    def test_bnd_member_name_at_and_beyond_limit(self):
        at = "a" * NAME_MAX
        line = render_balance_line("en", "latn", at, 1, "JOD")
        self.assertIn(FSI + at + PDI, line["text"])
        with self.assertRaises(ValueError) as caught:
            render_balance_line("en", "latn", at + "a", 1, "JOD")
        self.assertEqual(str(caught.exception), "text too long")
        with self.assertRaises(ValueError):
            sanitize_untrusted("a" * (NAME_MAX + 1))
        with self.assertRaises(ValueError):
            isolate("a" * (NAME_MAX + 1), "ltr")
        # length is judged on the input, so padding with strippable controls cannot bypass it
        with self.assertRaises(ValueError):
            sanitize_untrusted(RLO * (NAME_MAX + 1))

    def test_bnd_placeholder_at_and_beyond_limit(self):
        catalogs = {"en": {"k": "{v}"}}
        at = "x" * PLACEHOLDER_MAX
        self.assertEqual(translate("k", "en", {"v": at}, catalogs=catalogs).text, at)
        with self.assertRaises(ValueError) as caught:
            translate("k", "en", {"v": at + "x"}, catalogs=catalogs)
        self.assertEqual(str(caught.exception), "placeholder value too long")

    def test_bnd_plural_count_at_and_beyond_limit(self):
        self.assertEqual(plural_category("ar", MAX_INT), plural_category("ar", MAX_INT % 100))
        with self.assertRaises(ValueError) as caught:
            plural_category("ar", MAX_INT + 1)
        self.assertEqual(str(caught.exception), "count out of range")
        with self.assertRaises(ValueError):
            translate("items.count", "en", {"count": "1"}, count=MAX_INT + 1)


class WorstCaseTests(unittest.TestCase):
    """Measured worst accepted inputs; timings are printed, not asserted tightly."""

    def timed(self, label, call):
        start = time.perf_counter()
        for _ in range(100):
            result = call()
        elapsed_ms = (time.perf_counter() - start) * 10  # per call, ms
        print(f"\nPERF worst-case {label}: {elapsed_ms:.4f} ms/call")
        self.assertLess(elapsed_ms, 1000)  # generous sanity ceiling only
        return result

    def test_perf_worst_accepted_name_amount_and_plural(self):
        name = "أ" * NAME_MAX
        for locale in ("ar", "en"):
            line = self.timed(
                f"name {locale}",
                lambda locale=locale: render_balance_line(locale, "arab", name, 1, "JOD"),
            )
            self.assertIn(name, line["text"])
        line = self.timed(
            "amount", lambda: render_balance_line("ar", "arab", "Sara", MAX_INT, "JOD")
        )
        self.assertIn("JOD", line["text"])
        count_text = format_integer(MAX_INT, "arab")
        message = self.timed(
            "plural",
            lambda: translate("items.count", "ar", {"count": count_text}, count=MAX_INT),
        )
        self.assertIn(count_text, message.text)
        self.timed(
            "placeholder",
            lambda: translate(
                "items.count", "en", {"count": "9" * PLACEHOLDER_MAX}, count=MAX_INT
            ),
        )


if __name__ == "__main__":
    unittest.main()

"""Locale, bidi, numeral, money and contrast conventions. Stdlib only; errors never echo input."""

import re
from typing import Final, Literal

Locale = Literal["ar", "en"]
Direction = Literal["rtl", "ltr"]
Numbering = Literal["latn", "arab"]

LOCALES: Final[tuple[Locale, ...]] = ("ar", "en")

# ISO 4217 minor-unit exponents -- how an amount is **stored**. A JOD amount is a count of
# fils, which is a thousandth. Closed table: anything else fails closed.
CURRENCY_MINOR_UNITS: Final[dict[str, int]] = {"JOD": 3, "USD": 2}

# How many decimals an amount is **shown** with, which is a different question and is the
# design system's to answer:
#
#   "Always three-letter code plus two decimals, tabular figures, end-aligned. JOD is three
#    decimals in banking and two in retail -- Veyro is a retail product and shows two
#    everywhere, including exports, so a reconciliation never has to guess which convention a
#    column used."
#
# All 206 JOD figures drawn across the design folder use two decimals and none uses three.
# Using the storage exponent for display was the defect: every money figure on every screen
# in this product read `JOD 52.200` where the design reads `JOD 52.20`.
#
# **The two tables are separate on purpose.** Storage precision is what makes a proration
# exact and a journal balance; display precision is what a receipt and a screen agree on.
# Collapsing them in either direction loses one of those.
CURRENCY_DISPLAY_DIGITS: Final[dict[str, int]] = {"JOD": 2, "USD": 2}

LRI: Final = chr(0x2066)
RLI: Final = chr(0x2067)
FSI: Final = chr(0x2068)
PDI: Final = chr(0x2069)

_ISOLATE_OPENERS: Final[dict[str, str]] = {"rtl": RLI, "ltr": LRI, "auto": FSI}
# U+202A-202E (embeddings/overrides) and U+2066-2069 (isolates) in untrusted text.
_BIDI_CONTROLS: Final = "".join(chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))
_STRIP_BIDI: Final = str.maketrans("", "", _BIDI_CONTROLS)

# Unicode Cc (U+0000-001F, U+007F-009F), Zl (U+2028) and Zp (U+2029). This covers every bidi
# paragraph separator (LF, CR, U+001C-001E, U+0085, U+2028, U+2029), which would terminate every
# open isolate. Untrusted text containing any of them is rejected, never stripped or echoed.
_REJECTED_CONTROL_RANGES: Final = ((0x00, 0x1F), (0x7F, 0x9F), (0x2028, 0x2029))
_REJECTED_CONTROL_RE: Final = re.compile(
    "[" + "".join(f"\\u{lo:04x}-\\u{hi:04x}" for lo, hi in _REJECTED_CONTROL_RANGES) + "]"
)

# Fail-closed S1 bounds, checked in O(1) before any decimal conversion or copying.
MAX_INTEGER_BITS: Final = 256  # |value| < 2**256 (~77 decimal digits); covers 10**40 comfortably
MAX_UNTRUSTED_TEXT_CHARS: Final = 256  # member names
MAX_PLACEHOLDER_CHARS: Final = 512  # any placeholder value passed to translate()

_ARABIC_DIGITS: Final = "".join(chr(0x0660 + i) for i in range(10))
_TO_ARABIC: Final = str.maketrans("0123456789", _ARABIC_DIGITS)
_TO_LATIN: Final = str.maketrans(_ARABIC_DIGITS, "0123456789")
_ARABIC_THOUSANDS: Final = "٬"
_ARABIC_DECIMAL: Final = "٫"

_HEX_COLOR: Final = re.compile(r"#[0-9a-fA-F]{6}")
AA_TEXT_MIN_RATIO: Final = 4.5


def parse_locale(tag: object) -> Locale:
    """Accept exactly "ar" or "en"; any other tag is rejected."""
    if tag == "ar":
        return "ar"
    if tag == "en":
        return "en"
    raise ValueError("unsupported locale")


def direction(locale: str) -> Direction:
    return "rtl" if parse_locale(locale) == "ar" else "ltr"


def sanitize_untrusted(text: str) -> str:
    """Make untrusted text safe to place inside an isolate, or reject it.

    Contract: text longer than MAX_UNTRUSTED_TEXT_CHARS or containing any Unicode Cc, Zl or Zp
    control (including tab and all paragraph separators) raises ValueError (fixed message, input
    not echoed); embedding/override/isolate controls are stripped. A returned value therefore
    cannot break out of an isolate.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if len(text) > MAX_UNTRUSTED_TEXT_CHARS:
        raise ValueError("text too long")
    if _REJECTED_CONTROL_RE.search(text) is not None:
        raise ValueError("text contains a control character")
    return text.translate(_STRIP_BIDI)


def isolate(text: str, bidi_dir: str) -> str:
    """Sanitize, then wrap in RLI/LRI/FSI ... PDI for bidi_dir "rtl"/"ltr"/"auto"."""
    opener = _ISOLATE_OPENERS.get(bidi_dir)
    if opener is None:
        raise ValueError("unsupported isolate direction")
    return f"{opener}{sanitize_untrusted(text)}{PDI}"


def _check_numbering(numbering: str) -> None:
    if numbering not in ("latn", "arab"):
        raise ValueError("unsupported numbering system")


def _require_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("integer required")
    if value.bit_length() > MAX_INTEGER_BITS:
        raise ValueError("integer out of range")
    return value


def shape_digits(text: str, numbering: str) -> str:
    """Convert ASCII digits <-> U+0660-0669 for the explicitly requested numbering system."""
    _check_numbering(numbering)
    return text.translate(_TO_ARABIC if numbering == "arab" else _TO_LATIN)


def format_integer(value: int, numbering: str, grouping: bool = True) -> str:
    """Integer with optional thousands grouping. Numbering is never derived from locale."""
    _check_numbering(numbering)
    number = _require_int(value)
    body = f"{abs(number):,}" if grouping else str(abs(number))
    if numbering == "arab":
        body = shape_digits(body, "arab").replace(",", _ARABIC_THOUSANDS)
    return f"-{body}" if number < 0 else body


def format_money(amount_minor: int, currency: str, numbering: str, locale: str) -> str:
    """ISO code + amount from integer minor units; bidi-isolated (LTR) inside Arabic text.

    **Stored in minor units, shown at the display precision**, which for JOD are different:
    an amount is a count of fils and the design shows two decimals, "so a reconciliation
    never has to guess which convention a column used".

    **A stored amount finer than the display can express is rounded half away from zero**,
    which is `money.round_half_up`'s rule and therefore the only rounding rule in this build
    -- MOD-016 shipped a second one and a reviewer found it disagreeing with the first on
    ordinary inputs. Sub-display amounts are reachable: proration divides and `allocate`
    splits by largest remainder, so 999 fils exists and shows as `JOD 1.00`.

    The consequence is the ordinary one for any rounded display and is worth stating: a
    column of shown line amounts need not sum to the shown total. The minor units are the
    record; this is the rendering.
    """
    exponent = CURRENCY_MINOR_UNITS.get(currency)
    digits = CURRENCY_DISPLAY_DIGITS.get(currency)
    if exponent is None or digits is None:
        raise ValueError("unsupported currency")
    if digits > exponent:
        raise ValueError("display precision exceeds stored precision")
    _check_numbering(numbering)
    loc = parse_locale(locale)
    minor_total = _require_int(amount_minor)
    # Round on the magnitude, so the carry reaches the major part: 999 fils is 1.00, not 0.100.
    dropped = exponent - digits
    magnitude = abs(minor_total)
    if dropped:
        scale = 10**dropped
        magnitude = (magnitude + scale // 2) // scale
    major, minor = divmod(magnitude, 10**digits)
    amount = format_integer(major, numbering)
    if digits:
        separator = _ARABIC_DECIMAL if numbering == "arab" else "."
        amount += separator + shape_digits(str(minor).zfill(digits), numbering)
    sign = "-" if minor_total < 0 else ""
    text = f"{currency} {sign}{amount}"
    return isolate(text, "ltr") if loc == "ar" else text


def _parse_color(color: str) -> tuple[int, int, int]:
    if not isinstance(color, str) or _HEX_COLOR.fullmatch(color) is None:
        raise ValueError("color must be #RRGGBB")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def relative_luminance(color: str) -> float:
    """WCAG 2.x relative luminance of an sRGB #RRGGBB color."""

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _parse_color(color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    lighter, darker = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def meets_aa_text(fg: str, bg: str) -> bool:
    """WCAG AA normal-text threshold, 4.5:1 (UX G1)."""
    return contrast_ratio(fg, bg) >= AA_TEXT_MIN_RATIO

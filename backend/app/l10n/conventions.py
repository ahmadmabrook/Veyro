"""Locale, bidi, numeral, money and contrast conventions. Stdlib only; errors never echo input."""

import re
from typing import Final, Literal

Locale = Literal["ar", "en"]
Direction = Literal["rtl", "ltr"]
Numbering = Literal["latn", "arab"]

LOCALES: Final[tuple[Locale, ...]] = ("ar", "en")

# ISO 4217 minor-unit exponents. Closed table: anything else fails closed.
CURRENCY_MINOR_UNITS: Final[dict[str, int]] = {"JOD": 3, "USD": 2}

LRI: Final = chr(0x2066)
RLI: Final = chr(0x2067)
FSI: Final = chr(0x2068)
PDI: Final = chr(0x2069)

_ISOLATE_OPENERS: Final[dict[str, str]] = {"rtl": RLI, "ltr": LRI, "auto": FSI}
# U+202A-202E (embeddings/overrides) and U+2066-2069 (isolates) in untrusted text.
_BIDI_CONTROLS: Final = "".join(chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))
_STRIP_BIDI: Final = str.maketrans("", "", _BIDI_CONTROLS)

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
    """Remove bidi embedding/override/isolate controls so they cannot reorder surrounding text."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
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
    """ISO code + amount from integer minor units; bidi-isolated (LTR) inside Arabic text."""
    exponent = CURRENCY_MINOR_UNITS.get(currency)
    if exponent is None:
        raise ValueError("unsupported currency")
    _check_numbering(numbering)
    loc = parse_locale(locale)
    minor_total = _require_int(amount_minor)
    major, minor = divmod(abs(minor_total), 10**exponent)
    amount = format_integer(major, numbering)
    if exponent:
        separator = _ARABIC_DECIMAL if numbering == "arab" else "."
        amount += separator + shape_digits(str(minor).zfill(exponent), numbering)
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

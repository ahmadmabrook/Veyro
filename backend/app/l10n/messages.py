"""JSON message catalogs, {name} placeholders and CLDR plurals. Errors never echo input."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Final

from app.l10n.conventions import LOCALES, MAX_INTEGER_BITS, MAX_PLACEHOLDER_CHARS, parse_locale

Entry = str | Mapping[str, str]
Catalog = Mapping[str, Entry]

FALLBACK_LOCALE: Final = "en"
PLURAL_CATEGORIES: Final[dict[str, tuple[str, ...]]] = {
    "ar": ("zero", "one", "two", "few", "many", "other"),
    "en": ("one", "other"),
}

_CATALOG_DIR: Final = Path(__file__).parent / "catalog"
_PLACEHOLDER: Final = re.compile(r"\{([a-z][a-z0-9_]*)\}")


@dataclass(frozen=True)
class Message:
    text: str
    locale: str
    fallback: bool


def placeholders(template: str) -> frozenset[str]:
    """Names of {name} placeholders; stray braces are malformed."""
    leftover = _PLACEHOLDER.sub("", template)
    if "{" in leftover or "}" in leftover:
        raise ValueError("malformed placeholder")
    return frozenset(_PLACEHOLDER.findall(template))


def entry_placeholders(entry: Entry) -> frozenset[str]:
    if isinstance(entry, str):
        return placeholders(entry)
    names: frozenset[str] = frozenset()
    for template in entry.values():
        names |= placeholders(template)
    return names


def _validate_catalog(raw: object) -> Catalog:
    if not isinstance(raw, dict):
        raise ValueError("catalog must be an object")
    entries: dict[str, Entry] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ValueError("catalog key must be a string")
        if isinstance(value, str):
            entries[key] = value
        elif isinstance(value, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            entries[key] = MappingProxyType(dict(value))
        else:
            raise ValueError("catalog entry must be a string or a plural-category object")
    return MappingProxyType(entries)


@cache
def _read(locale: str) -> Catalog:
    text = (_CATALOG_DIR / f"{locale}.json").read_text(encoding="utf-8")
    return _validate_catalog(json.loads(text))


def load_catalog(locale: str) -> Catalog:
    """Immutable view of the shipped catalog; the file is read once per process."""
    return _read(parse_locale(locale))


def plural_category(locale: str, count: int) -> str:
    """CLDR cardinal category for a non-negative integer."""
    loc = parse_locale(locale)
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError("count must be an integer")
    if count < 0:
        raise ValueError("count must not be negative")
    if count.bit_length() > MAX_INTEGER_BITS:
        raise ValueError("count out of range")
    if loc == "ar":
        if count == 0:
            return "zero"
        if count == 1:
            return "one"
        if count == 2:
            return "two"
        remainder = count % 100
        if 3 <= remainder <= 10:
            return "few"
        if 11 <= remainder <= 99:
            return "many"
        return "other"
    return "one" if count == 1 else "other"


def _render(template: str, params: Mapping[str, str]) -> str:
    if not placeholders(template).issubset(params):
        raise ValueError("unknown placeholder")
    return _PLACEHOLDER.sub(lambda m: params[m.group(1)], template)


def _pick(entry: Entry | None, category: str | None) -> str | None:
    if entry is None or isinstance(entry, str):
        return entry
    if category is None:
        raise ValueError("count required for plural message")
    return entry.get(category)


def translate(
    key: str,
    locale: str,
    params: Mapping[str, str] | None = None,
    count: int | None = None,
    catalogs: Mapping[str, Catalog] | None = None,
) -> Message:
    """Render key in locale; a missing (or incomplete plural) ar entry falls back to en.

    Placeholder values are inserted verbatim but bounded to MAX_PLACEHOLDER_CHARS. Callers must
    sanitize/isolate untrusted values (see conventions.sanitize_untrusted and
    conventions.isolate, which reject paragraph separators) before passing them; the fixture
    does so.
    """
    loc = parse_locale(locale)
    values: Mapping[str, str] = {} if params is None else params
    if not all(isinstance(v, str) for v in values.values()):
        raise TypeError("placeholder values must be strings")
    if any(len(v) > MAX_PLACEHOLDER_CHARS for v in values.values()):
        raise ValueError("placeholder value too long")
    source = catalogs if catalogs is not None else {name: load_catalog(name) for name in LOCALES}
    for candidate in dict.fromkeys((loc, FALLBACK_LOCALE)):
        category = None if count is None else plural_category(candidate, count)
        template = _pick(source.get(candidate, {}).get(key), category)
        if template is not None:
            return Message(_render(template, values), candidate, candidate != loc)
    raise ValueError("message unavailable")


def qa_gaps(catalogs: Mapping[str, Catalog]) -> list[str]:
    """R08 gate: key parity, placeholder parity, plural completeness. Empty list means no gap."""
    en, ar = catalogs["en"], catalogs["ar"]
    gaps = [f"missing-ar:{k}" for k in sorted(en.keys() - ar.keys())]
    gaps += [f"extra-ar:{k}" for k in sorted(ar.keys() - en.keys())]
    for key in sorted(en.keys() & ar.keys()):
        if isinstance(en[key], str) != isinstance(ar[key], str):
            gaps.append(f"shape-mismatch:{key}")
        if entry_placeholders(en[key]) != entry_placeholders(ar[key]):
            gaps.append(f"placeholder-mismatch:{key}")
    for locale in ("ar", "en"):
        required = set(PLURAL_CATEGORIES[locale])
        for key, entry in sorted(catalogs[locale].items()):
            if not isinstance(entry, str) and set(entry) != required:
                gaps.append(f"plural-categories:{locale}:{key}")
    return gaps

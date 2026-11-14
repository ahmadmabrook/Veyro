"""MOD-014 PPL-01-R05: custom fields, governed by schema rather than by hope.

Paragraph 1318 asks for "tags, segments, custom fields and data-quality indicators governed by
schema and permissions". The schema half is here: a definition declares a type and a
sensitivity, and a value is refused unless it parses as that type.

**There is no `secret` type and no free-form object type.** MOD-012's definition catalogue makes
the same refusal and the reasoning carries: a type that invites a tenant to paste an API key, or
a `json` type that accepts anything, turns a column every list route reads into the place
credentials and subject identifiers end up. MOD-010's review found exactly that in
`cfg_exposures.subject_id` -- caller-chosen free text at AAL 1, with an email address, a date of
birth and a lab result in it.

**A sensitivity is declared once and cannot be changed.** `ppl_custom_field_defs` grants no
UPDATE on `value_type` or `sensitivity`, so a field collected as health data cannot later be
re-marked `none` and unmasked in bulk. Retiring it and declaring a new one is the path, and it
leaves the old values where they are with the classification they were collected under.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

#: What a value may be. Each one parses unambiguously from text, which is why the storage is
#: text: a column per type would mean five nullable columns and a constraint tying them to the
#: definition, and `jsonb` would mean no validation at all.
VALUE_TYPES = ("text", "integer", "decimal", "boolean", "date", "enum")

#: MOD-008's five classes plus `none`. A sixth invented here would be a class the masking has
#: never heard of, which reads as unmasked.
SENSITIVITIES = ("none", "contact", "identity", "financial", "health", "biometric")

#: A field key is a stable machine name: it appears in exports, integrations and read models.
KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,62}$")

#: The longest a text value may be. Long enough for an address or a short note, short enough
#: that a custom field is not where somebody keeps a document.
MAX_TEXT = 1000

#: Decimal values are stored as text and compared as text by nothing: the bound is on the shape
#: so a value that will later be read as a number cannot be `1e999`, which overflows on parse
#: and reaches a caller as a 500. MOD-011 and MOD-012 each shipped that once.
DECIMAL_RE = re.compile(r"^-?\d{1,15}(\.\d{1,6})?$")
INTEGER_RE = re.compile(r"^-?\d{1,18}$")
BOOLEANS = {"true": "true", "false": "false"}


class FieldError(ValueError):
    """A custom field definition or value this module will not accept."""


@dataclass(frozen=True)
class Definition:
    field_key: str
    display_name: str
    value_type: str
    sensitivity: str = "none"
    is_required: bool = False
    #: Only for `enum`, and required for it: an enum with no options is a field nothing can
    #: satisfy, which is worse than a text field.
    options: tuple[str, ...] = ()


def check_definition(definition: Definition) -> None:
    """Refuse a definition that cannot be satisfied or cannot be classified."""
    if not KEY_RE.fullmatch(definition.field_key):
        raise FieldError(
            "a field key is lowercase, starts with a letter and holds letters, digits, "
            "underscores, dots or hyphens"
        )
    if not definition.display_name.strip():
        raise FieldError("a field has a display name")
    if definition.value_type not in VALUE_TYPES:
        raise FieldError(f"{definition.value_type!r} is not a custom field type")
    if definition.sensitivity not in SENSITIVITIES:
        raise FieldError(f"{definition.sensitivity!r} is not a sensitivity class")
    if definition.value_type == "enum":
        if not definition.options:
            raise FieldError("an enum field declares its options")
        if len(set(definition.options)) != len(definition.options):
            raise FieldError("an enum field's options are distinct")
        for option in definition.options:
            if not option.strip():
                raise FieldError("an enum option cannot be blank")
            if len(option) > 120:
                raise FieldError("an enum option is at most 120 characters")
    elif definition.options:
        raise FieldError(f"a {definition.value_type} field takes no options")
    # A required field whose own definition is sensitive is allowed and worth noting rather than
    # refusing: a gym that must collect an emergency contact is collecting contact data, and the
    # classification is how that gets masked rather than a reason to refuse the field.


def normalize_value(definition: Definition, raw: str) -> str:
    """The value as it will be stored, or a refusal naming the type that rejected it.

    Returns a canonical form rather than the input: `TRUE`, `True` and `true` are one boolean,
    and storing three spellings would make a segment query on the value depend on who typed it.
    """
    value = raw.strip()
    if not value:
        raise FieldError(f"{definition.field_key} cannot be blank")
    if definition.value_type == "text":
        if len(value) > MAX_TEXT:
            raise FieldError(f"{definition.field_key} is at most {MAX_TEXT} characters")
        return value
    if definition.value_type == "integer":
        if not INTEGER_RE.fullmatch(value):
            raise FieldError(f"{definition.field_key} is a whole number")
        return str(int(value))
    if definition.value_type == "decimal":
        if not DECIMAL_RE.fullmatch(value):
            raise FieldError(
                f"{definition.field_key} is a decimal number with at most 15 digits before "
                f"the point and 6 after it"
            )
        return value
    if definition.value_type == "boolean":
        canonical = BOOLEANS.get(value.lower())
        if canonical is None:
            raise FieldError(f"{definition.field_key} is true or false")
        return canonical
    if definition.value_type == "date":
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise FieldError(f"{definition.field_key} is a date as YYYY-MM-DD") from None
    if definition.value_type == "enum":
        if value not in definition.options:
            raise FieldError(
                f"{definition.field_key} is one of: {', '.join(sorted(definition.options))}"
            )
        return value
    raise FieldError(f"{definition.value_type!r} is not a custom field type")


def masked_field_names(definitions: list[Definition], readable: frozenset[str]) -> tuple[str, ...]:
    """Which custom field keys this caller may not read, by the definition's own sensitivity.

    The mask MOD-008 produces is about the fields *it* knows -- `iban`, `national_id` and the
    rest of `SENSITIVE_FIELDS`. A tenant's custom field is not in that list and cannot be: the
    catalogue is code and the field is a row. So the classification travels on the definition
    and this turns it into the same shape of answer, which `visibility.apply` then applies
    alongside the gate's.
    """
    return tuple(sorted(
        d.field_key for d in definitions
        if d.sensitivity != "none" and d.sensitivity not in readable
    ))

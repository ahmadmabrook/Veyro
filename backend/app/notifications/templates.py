"""MOD-013 ENG-02: what a notification template may say, and which category it belongs to.

A template is tenant-authored content -- brand styling, localization, variables -- so it is rows
rather than code, the same call MOD-012 makes for integration definitions and for the same
reason: the set is open by design and the authority is whoever wrote the version. A published
version is immutable, and a notification snapshots the version it was rendered from, so an old
notification stays reconstructible after the template moves on.

**The category is the whole of paragraph 2463's control.** "Marketing and transactional purposes
are separated" is not a naming convention here: a template declares its category, the category
decides whether consent is required before a notification may be requested, and
`app/notifications/preferences.py` decides whether a recipient's opt-out can stop it. A
transactional receipt and a promotional campaign travel different paths from the moment the
template is written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KEY = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$", re.ASCII)
VARIABLE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$", re.ASCII)
#: BCP 47 as far as this build needs it: a language, optionally a region. Not a full parser,
#: and the shape is what `ntf_templates_locale_shape` enforces.
LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$", re.ASCII)
#: `{{ variable }}`, with the braces doubled so a literal brace in body text is unambiguous.
PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}", re.ASCII)

CHANNELS = ("email", "sms", "whatsapp", "push", "in_app")

#: Paragraph 2457's four, and the consent rule each one carries. The split is the control:
#: `marketing` needs a recorded consent before a notification may even be requested, and a
#: recipient's channel opt-out stops it; `transactional` is the receipt somebody asked for by
#: doing business, so an opt-out does not suppress it and no consent gates it.
CATEGORIES = ("transactional", "operational", "coaching", "marketing")

#: Which categories a recipient's own preference may switch off. A member who opts out of
#: coaching nudges still gets their invoice: suppressing a transactional message on a
#: preference would mean a tenant unable to tell somebody their payment failed.
OPTIONAL_CATEGORIES = ("coaching", "marketing")

#: Which categories need a live consent record (MOD-009's `sec_consent_records`) before a
#: notification may be requested at all. Consent is a stronger statement than a preference:
#: a preference is "do not send me these", and consent is "nobody ever asked".
CONSENT_REQUIRED_CATEGORIES = ("marketing",)

STATUSES = ("draft", "published", "retired")


class TemplateError(ValueError):
    """A template this build will not accept."""


@dataclass(frozen=True)
class TemplateVersion:
    template_key: str
    version: int
    category: str
    channel: str
    locale: str
    subject: str
    body: str
    variables: tuple[str, ...] = field(default_factory=tuple)

    @property
    def needs_consent(self) -> bool:
        return self.category in CONSENT_REQUIRED_CATEGORIES

    @property
    def is_suppressible_by_preference(self) -> bool:
        return self.category in OPTIONAL_CATEGORIES


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def check_version(version: TemplateVersion) -> None:
    """Everything one version has to satisfy to be stored, including its own placeholders.

    **The declared variables and the placeholders in the text are checked against each other in
    both directions.** A placeholder nobody declared renders as the literal `{{ amount }}` in a
    member's inbox -- the failure everybody has seen in a real product -- and a declared
    variable nothing uses makes a caller believe a value reached the message when it did not.
    """
    if not KEY.fullmatch(version.template_key):
        raise TemplateError("template_key_is_not_a_key")
    if version.version < 1:
        raise TemplateError("version_is_not_positive")
    if version.category not in CATEGORIES:
        raise TemplateError(f"{version.category!r} is not a notification category")
    if version.channel not in CHANNELS:
        raise TemplateError(f"{version.channel!r} is not a channel")
    if not LOCALE.fullmatch(version.locale):
        raise TemplateError(f"{version.locale!r} is not a locale")
    if not version.body.strip():
        raise TemplateError("a_template_has_a_body")
    # Only email carries a subject. An SMS with one would put it nowhere, and a template that
    # declares one is a template whose author expects it to be shown.
    if version.channel == "email" and not version.subject.strip():
        raise TemplateError("an_email_template_has_a_subject")
    if version.channel != "email" and version.subject.strip():
        raise TemplateError(f"a {version.channel} template has no subject to show")
    for name in version.variables:
        if not VARIABLE.fullmatch(name):
            raise TemplateError(f"{name!r} is not a variable name")
    if len(set(version.variables)) != len(version.variables):
        raise TemplateError("a_variable_is_declared_twice")
    used = placeholders(version.subject) | placeholders(version.body)
    declared = set(version.variables)
    undeclared = used - declared
    if undeclared:
        raise TemplateError(
            f"the text uses {sorted(undeclared)}, which the template does not declare; an "
            f"undeclared placeholder renders literally in somebody's inbox"
        )
    unused = declared - used
    if unused:
        raise TemplateError(
            f"the template declares {sorted(unused)} and the text uses none of them, so a "
            f"caller supplying those values would believe they reached the message"
        )


def check_succession(earlier: TemplateVersion, later: TemplateVersion) -> None:
    """What a later version of one template may change.

    The category may **not** change, and that is the important one: a template whose category
    moved from `transactional` to `marketing` would have notifications already sent under the
    consent rules of the old one, and a move the other way would let a campaign ride on a
    receipt's exemption from opt-out. The channel and the locale are equally fixed -- a template
    is identified by all three, and changing one silently retargets every caller.

    A later version may add a variable and may not drop one: a caller still supplying the old
    set would have its value silently ignored.
    """
    if later.template_key != earlier.template_key:
        raise TemplateError("succession_compares_one_template")
    for name, was, now in (("category", earlier.category, later.category),
                           ("channel", earlier.channel, later.channel),
                           ("locale", earlier.locale, later.locale)):
        if was != now:
            raise TemplateError(
                f"v{later.version} changes the {name} from {was!r} to {now!r}; a template is "
                f"identified by its key, category, channel and locale together"
            )
    dropped = set(earlier.variables) - set(later.variables)
    if dropped:
        raise TemplateError(
            f"v{later.version} drops {sorted(dropped)}; a caller still supplying those would "
            f"have them silently ignored"
        )


def render(version: TemplateVersion, variables: dict[str, str]) -> tuple[str, str]:
    """Substitute the declared variables, refusing anything the template did not declare.

    Returns (subject, body). The substitution is a single pass over the placeholder pattern, so
    a *value* containing `{{ other }}` is inserted literally and is never itself expanded --
    which matters because the values come from a caller and the text comes from a tenant author.
    A second pass would be a template-injection primitive.
    """
    supplied = set(variables)
    declared = set(version.variables)
    if supplied - declared:
        raise TemplateError(f"this template declares no {sorted(supplied - declared)}")
    if declared - supplied:
        raise TemplateError(f"these variables have no value: {sorted(declared - supplied)}")
    for name, value in variables.items():
        if not isinstance(value, str):
            raise TemplateError(f"the value for {name!r} is not text")

    def substitute(text: str) -> str:
        return PLACEHOLDER.sub(lambda m: variables[m.group(1)], text)

    return substitute(version.subject), substitute(version.body)

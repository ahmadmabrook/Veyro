"""ADM-SET-07's display conventions: the two keys a rendered page needs, and their defaults.

**Why this is its own read rather than a slice of `resolve_config`.** ADR-0015. A tenant's
numeral system has to reach every rendered page, and the three cheap ways in are all closed:
`GET /config/resolved` is gated on `config.definition.read`, which means "see every
configuration key" -- granting that to a receptionist so a page can choose its digits is
MOD-013's `GET /notifications/channels` finding; `/auth/session` would cost no round trip and
`veyro_iam_app` holds nothing in `plt01`, so the plane separation makes it impossible; and
`presentation()` is cookie-only with no request at all, which is why every page can call it.

**The default is Latin digits, and that is load-bearing rather than cautious.** It is what
every page in this build renders today, so a tenant that has declared nothing sees exactly what
it saw before and the grant changes what somebody *sees* rather than whether a page works --
which is ADR-0011's reasoning about the billing anchor applied to a display rule. The canvas's
own tenant is Jordanian with Arabic-Indic selected; that is a value a tenant sets, not a
default this module invents for everybody.

**A key that was never declared resolves to its default here, not to an error.** MOD-005's
definitions are rows, so a tenant has to register a key before a value can be published against
it -- and a page cannot be made to depend on that having happened. So this reads whichever of
the two are declared and fills the rest in, which means the read answers for a tenant
provisioned five minutes ago exactly as for one that has configured itself.

**The month-name set is not a key**, by ADR-0015 D5: the canvas states it ("Month names follow
the Levantine set -- آب, تموز -- because that is what Jordanian members read") rather than
drawing a control, in the same way CON-04 derives the week start from the region. It is
returned as a derived fact so a surface can render the rule it is obeying, and the client gets
it for free from the locale tag: `ar-JO` renders `٢١ آب` where plain `ar` renders `21 أغسطس`,
so both halves of "Arabic-Indic for dates" and "the Levantine set" are one tag rather than a
table this module would have to keep.
"""
from __future__ import annotations

from typing import Any

from app.db import Pool, tenant_scope

#: The numeral systems `app.l10n.conventions` implements, which is the closed set a value is
#: validated against. Both runtimes carry both -- digit shaping, the Arabic thousands separator
#: and the Arabic decimal separator -- and `conventions-parity.test.mjs` spawns Python to keep
#: them byte-identical, because ADM-SET-07 requires the rule "applied identically on screen,
#: receipt and export" and a receipt is rendered by the backend.
NUMERALS = ("latn", "arab")

#: The languages this build has message catalogues for. A tenant offers a subset; offering one
#: it has no catalogue for would be a language a reader could select and not read.
LANGUAGES = ("en", "ar")

#: `localization.numerals` -- one rule per tenant. The canvas is explicit that it is not
#: per-component: "One rule per tenant, never mixed and never decided per component."
NUMERALS_KEY = "localization.numerals"

#: `localization.languages_offered` -- a set, so the registry type is `json`.
LANGUAGES_KEY = "localization.languages_offered"

#: **Money is always Latin, and the canvas says why rather than leaving it to taste**: "Money
#: keeps Latin digits with its code -- JOD 41,280.00 -- because that is the form on your
#: invoices and JoFotara submissions. Applied identically on screen, receipt and export." A
#: member disputing a charge has to see the same string in both places. So this is returned on
#: the read as a statement rather than a setting: there is no key for it and no way to turn it
#: off, and a surface renders the rule it is obeying instead of implying a choice.
MONEY_IS_ALWAYS_LATIN = (
    "money keeps Latin digits with its currency code whatever the numeral system is, because "
    "that is the form on an invoice and on a tax submission, and a member disputing a charge "
    "has to see the same string in both places"
)

#: The month-name set, derived rather than configured -- ADR-0015 D5. Returned so a surface can
#: say which rule it is following; the client needs no table, because the regional locale tag
#: carries it.
MONTH_NAMES = "levantine"


def _declared(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    """One resolved value, narrowed to the closed set, or the fallback.

    **A stored value outside the set falls back rather than raising.** The registry validates on
    publish, so this cannot happen through a route -- and this read is on the path of every
    rendered page, so a value somebody wrote directly must not be able to take a tenant's whole
    surface down. The fallback is what the page renders today either way.
    """
    return value if isinstance(value, str) and value in allowed else fallback


def display_conventions(pool: Pool, tenant_id: str) -> dict[str, Any]:
    """The tenant's display conventions, with every key defaulted.

    One query, no scope arguments: ADM-SET-07's rule is one rule per tenant, so there is nothing
    to inherit and a brand or a location cannot differ. That is the opposite of
    `resolve_config`, which exists for the keys that *do* inherit.
    """
    with tenant_scope(pool, tenant_id) as conn:
        rows = conn.execute(
            "SELECT d.config_key, coalesce(v.value, d.default_value)"
            "  FROM plt01.cfg_definitions d"
            # The tenant-scoped value if one is published, else the definition's default. A
            # brand or location value is deliberately not consulted: see the docstring.
            "  LEFT JOIN plt01.cfg_values v"
            "    ON v.definition_id = d.definition_id AND v.scope_type = 'tenant'"
            " WHERE d.config_key = ANY(%s)"
            # Insert-only, so the newest row for a scope is the live one.
            " ORDER BY v.version DESC NULLS LAST",
            ([NUMERALS_KEY, LANGUAGES_KEY],),
        ).fetchall()
    got: dict[str, Any] = {}
    for key, value in rows:
        got.setdefault(key, value)
    languages = got.get(LANGUAGES_KEY)
    offered = tuple(
        one for one in (languages if isinstance(languages, list) else [])
        if isinstance(one, str) and one in LANGUAGES
    )
    return {
        "numerals": _declared(got.get(NUMERALS_KEY), NUMERALS, "latn"),
        # Every catalogue this build has, where a tenant has declared nothing: offering fewer
        # than it can read is a choice, and defaulting to fewer would hide a language somebody
        # is already using.
        "languages_offered": list(offered) if offered else list(LANGUAGES),
        "month_names": MONTH_NAMES,
        "money_is_always_latin": MONEY_IS_ALWAYS_LATIN,
        # Said on the read, because a tenant that has declared neither key is not a tenant that
        # chose Latin digits -- and a surface that could not tell them apart would present a
        # default as a decision.
        "declared": sorted(got),
    }

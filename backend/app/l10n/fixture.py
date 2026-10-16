"""Shared sample component: a localized balance line. Manual QA: `python -m app.l10n.fixture`."""

from typing import TypedDict

from app.l10n.conventions import (
    FSI,
    LRI,
    PDI,
    RLI,
    direction,
    format_integer,
    format_money,
    isolate,
    meets_aa_text,
    parse_locale,
    sanitize_untrusted,
)
from app.l10n.messages import plural_category, translate


class BalanceLine(TypedDict):
    lang: str
    dir: str
    text: str


def render_balance_line(
    locale: str, numbering: str, member_name: str, amount_minor: int, currency: str
) -> BalanceLine:
    """Localized line with lang/dir for the host element. The member name is untrusted."""
    loc = parse_locale(locale)
    name = sanitize_untrusted(member_name)
    if not name.strip():
        raise ValueError("member name required")
    amount = format_money(amount_minor, currency, numbering, loc)
    message = translate("balance.line", loc, {"member": isolate(name, "auto"), "amount": amount})
    return {"lang": loc, "dir": direction(loc), "text": message.text}


def _visible(text: str) -> str:
    for mark, label in ((RLI, "<RLI>"), (LRI, "<LRI>"), (FSI, "<FSI>"), (PDI, "<PDI>")):
        text = text.replace(mark, label)
    return text


def main() -> None:
    names = ("Sara", "أحمد Ahmed 42", "Ali" + chr(0x202E) + "evil" + chr(0x2069))
    for locale in ("en", "ar"):
        for numbering in ("latn", "arab"):
            for name in names:
                line = render_balance_line(locale, numbering, name, 1234567, "JOD")
                print(f"[{locale}/{numbering}] lang={line['lang']} dir={line['dir']}")
                print(f"  {line['text']}")
                print(f"  {_visible(line['text'])}")
    for count in (0, 1, 2, 5, 11, 100):
        text = translate("items.count", "ar", {"count": format_integer(count, "arab")}, count).text
        print(f"[ar plural {plural_category('ar', count)}] {text}")
    print(f"AA #767676 on #ffffff: {meets_aa_text('#767676', '#ffffff')}")
    print(f"AA #777777 on #ffffff: {meets_aa_text('#777777', '#ffffff')}")


if __name__ == "__main__":
    main()

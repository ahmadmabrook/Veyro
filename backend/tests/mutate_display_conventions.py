"""Mutations against ADR-0015's display read, one protection at a time.

What these prove is that an unconfigured tenant gets today's behaviour rather than an error,
that a declared key and a chosen value are different facts, that a value outside the closed set
cannot take a page down, and that the two statements are not settings.

Each removes one protection and nothing else; the harness compares the file's bytes before and
after, so a mutation that did not apply is reported NOT RUN rather than counted as a gap.

    VEYRO_DATABASE_URL=... python3 -m tests.mutate_display_conventions
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
DISPLAY = "app/configuration/display.py"

#: (id, file, from, to, the test that must fail)
MUTATIONS = [
    # **The default is the whole of D2.** With no fallback an unconfigured tenant gets `None`
    # for its numeral system, which every formatter then refuses -- so the read that exists to
    # be harmless becomes the one that takes a new tenant's surface down.
    ("an unconfigured tenant gets no numeral system at all",
     DISPLAY,
     '"numerals": _declared(got.get(NUMERALS_KEY), NUMERALS, "latn"),',
     '"numerals": got.get(NUMERALS_KEY),',
     "test_a_tenant_that_has_declared_nothing_gets_latin_digits_and_every_language"),
    # A stored value outside the closed set reaches the page. The registry validates on publish,
    # so this is the writer that is *not* a route -- and this read is on every rendered page.
    ("a value outside the closed set is returned as it stands",
     DISPLAY,
     "    return value if isinstance(value, str) and value in allowed else fallback",
     "    return value if isinstance(value, str) else fallback",
     "test_a_value_outside_the_closed_set_cannot_reach_a_page"),
    # **Declared and chosen are different facts.** Without `declared` a surface cannot tell a
    # tenant that picked Latin from one that has never been configured, so it would present a
    # default as a decision.
    ("a default is indistinguishable from a decision",
     DISPLAY,
     '"declared": sorted(got),',
     '"declared": [NUMERALS_KEY, LANGUAGES_KEY],',
     "test_a_tenant_that_has_declared_nothing_gets_latin_digits_and_every_language"),
    # The languages fall back to every catalogue this build has. Defaulting to fewer would hide
    # a language somebody is already reading the product in.
    ("an unconfigured tenant offers no languages",
     DISPLAY,
     "        \"languages_offered\": list(offered) if offered else list(LANGUAGES),",
     "        \"languages_offered\": list(offered),",
     "test_a_tenant_that_has_declared_nothing_gets_latin_digits_and_every_language"),
    # A language the build has no catalogue for would be selectable and unreadable.
    ("a language with no catalogue is offered",
     DISPLAY,
     "        if isinstance(one, str) and one in LANGUAGES",
     "        if isinstance(one, str)",
     "test_a_language_with_no_catalogue_is_not_offered"),
    # The tenant scope filter: without it a brand or location value wins, and ADM-SET-07's rule
    # is "one rule per tenant, never mixed and never decided per component".
    ("a brand or location value can override the tenant's one rule",
     DISPLAY,
     "AND v.scope_type = 'tenant'\"",
     "\"",
     "test_a_brand_value_does_not_override_the_tenant_s_one_rule"),
]


def run(test: str) -> bool:
    """True when the named test fails, which is what a caught mutation looks like."""
    done = subprocess.run(
        [sys.executable, "-B", "-m", "unittest",
         f"tests.test_configuration_api.DisplayConventionsTests.{test}"],
        cwd=BACKEND, capture_output=True, text=True, timeout=300)
    return done.returncode != 0


def main() -> int:
    caught, gaps, not_run = 0, [], []
    for name, rel, frm, to, test in MUTATIONS:
        path = BACKEND / rel
        original = path.read_text()
        if original.count(frm) != 1:
            not_run.append(f"{name}: the anchor appears {original.count(frm)} times")
            continue
        path.write_text(original.replace(frm, to, 1))
        try:
            # The bytes changed, or the mutation is a no-op and proves nothing.
            if path.read_text() == original:
                not_run.append(f"{name}: the file is unchanged")
                continue
            if run(test):
                caught += 1
                print(f"ok    {name} -- caught")
            else:
                gaps.append(name)
                print(f"GAP   {name} -- UNCAUGHT by {test}")
        finally:
            path.write_text(original)
    for line in not_run:
        print(f"NOT RUN  {line}")
    print(f"\n{caught}/{len(MUTATIONS)} mutations caught"
          + (f", {len(not_run)} not run" if not_run else ""))
    return 1 if gaps or not_run else 0


if __name__ == "__main__":
    raise SystemExit(main())

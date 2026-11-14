"""Static checks over the migration files, for holes no running database would show.

**One test, and it exists because of a generator bug.** MOD-017's case generator wrapped a
`'  '` literal across lines, which turned it into a newline-plus-spaces literal -- and that
*passed* the not-blank constraint it was written to violate. PostgreSQL's one-argument `btrim`
strips spaces and nothing else, so every "states a reason" and "describes what it is for"
control in this build was satisfied by a single tab or a single newline. That was 118
constraints across ten migrations, every one of them written to refuse exactly that.

The shape in use now is `x ~ '[^[:space:]]'`. Nothing in a running database would ever flag the
old one: it is valid SQL that does almost what it says, and the only way to notice is to look
for it. So this test looks for it.
"""

from __future__ import annotations

import pathlib
import re
import unittest

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "migrations"

#: `btrim(x)` with one argument. The two-argument form trims a named character set and is a
#: different, deliberate thing -- nothing in this build uses it, and if something does one day
#: it is not the hole this test is about.
ONE_ARG_BTRIM = re.compile(r"\bbtrim\(\s*[^,()]+\)")


class BlankCheckShapeTests(unittest.TestCase):
    def test_no_migration_tests_for_blankness_with_btrim(self):
        offenders: list[str] = []
        for path in sorted(MIGRATIONS.rglob("*.sql")):
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                if ONE_ARG_BTRIM.search(line):
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "`length(btrim(x)) > 0` is true for a single tab and a single newline, because "
            "PostgreSQL's one-argument btrim strips spaces only. Write "
            "`x ~ '[^[:space:]]'`, which says what was meant: the value contains at least "
            "one character that is not whitespace.")

    def test_the_replacement_shape_is_the_one_in_use(self):
        """And the test above cannot pass by there being no blankness checks at all."""
        found = sum(
            path.read_text().count("~ '[^[:space:]]'")
            for path in MIGRATIONS.rglob("*.sql"))
        self.assertGreater(found, 100, "the not-blank controls have gone missing")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

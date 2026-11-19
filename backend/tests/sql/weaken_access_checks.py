"""Emit one mutation per weakening of a MOD-022 CHECK constraint.

A drop is the obvious mutation and it is not the only one. `.claude/rules/backend/mod004-rls.md`:
"the sweep's mutations are weakenings as well as drops, one per conjunct and one per side of an
equality" -- because a case proves a constraint only in the direction it exercises. A reviewer
weakened eight of MOD-013's to one-way implications and the suite reported 60/60 every time.

Three shapes, which are the three the rules file names:

  * a top-level conjunction, with one conjunct removed. A case that violates conjunct 2 says
    nothing about conjunct 1, and a constraint of five conjuncts with one case has four
    unproven halves.
  * an equality between two boolean expressions -- the `(A) = (B)` biconditional, which is the
    commonest shape in these schemas -- replaced by each of its two implications.
  * a numeric bound, widened. The case catches this only if its row falls between the old
    bound and the new one, which is why the generated cases use bound-plus-one.
"""
import os
import re
import subprocess
import sys

PSQL = os.environ.get("PSQL", "docker exec -i veyro-verify psql -U postgres").split()


def ask(sql: str) -> list[str]:
    return subprocess.run(PSQL + ["-d", "veyro", "-tAq", "-c", sql],
                          capture_output=True, text=True).stdout.splitlines()


def unwrap(definition: str) -> str:
    """`CHECK ((expr))` -> `expr`, with one layer of redundant parentheses removed."""
    body = definition[len("CHECK "):].strip()
    while body.startswith("(") and body.endswith(")") and balanced(body[1:-1]):
        body = body[1:-1].strip()
    return body


def balanced(text: str) -> bool:
    depth = 0
    in_string = False
    for ch in text:
        if ch == "'":
            in_string = not in_string
        elif not in_string:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    return False
    return depth == 0 and not in_string


def split_top(text: str, operator: str) -> list[str]:
    """Split on a top-level operator, ignoring anything inside parentheses or a literal."""
    parts: list[str] = []
    depth = 0
    in_string = False
    i = 0
    start = 0
    pattern = f" {operator} "
    while i < len(text):
        ch = text[i]
        if ch == "'":
            in_string = not in_string
        elif not in_string:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0 and text.startswith(pattern, i):
                parts.append(text[start:i])
                i += len(pattern)
                start = i
                continue
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts]


def weakenings(body: str) -> list[tuple[str, str]]:
    """(label, weakened expression) for every weakening this module knows how to make."""
    out: list[tuple[str, str]] = []

    conjuncts = split_top(body, "AND")
    if len(conjuncts) > 1:
        for n in range(len(conjuncts)):
            kept = [c for i, c in enumerate(conjuncts) if i != n]
            out.append((f"and{n + 1}", " AND ".join(kept)))

    # `(A) = (B)` where both sides are boolean: each implication on its own. `= ANY` is a
    # set membership rather than a biconditional, and a disjunction of equalities is not one
    # either, so both are excluded.
    if len(conjuncts) == 1 and len(split_top(body, "OR")) == 1:
        sides = split_top(body, "=")
        if len(sides) == 2 and all(s.startswith("(") and s.endswith(")") for s in sides):
            left, right = sides
            out.append(("imply1", f"(NOT {left}) OR {right}"))
            out.append(("imply2", f"(NOT {right}) OR {left}"))

    # A numeric bound, widened by a million -- enough to admit any generated case's row and
    # small enough to stay inside every integer column here.
    #
    # **The integer has to be the whole literal.** The first version matched `'?-?\d+'?`,
    # which found the `'00` at the front of `'00:01:30'::interval` and produced
    # `<= 1000000:01:30'::interval` -- a statement PostgreSQL refuses, reported as a mutation
    # that did not run, which is the harness manufacturing a gap. An unquoted integer must not
    # be followed by a digit, a colon or a quote; a quoted one must have its closing quote.
    pattern = r"(<=|>=)\s*(?:'(-?\d+)'|(-?\d+)(?![\d:']))(::\w+)?"
    for n, match in enumerate(re.finditer(pattern, body), start=1):
        quoted, bare, cast = match.group(2), match.group(3), match.group(4) or ""
        literal = quoted if quoted is not None else bare
        if literal is None or len(literal) > 12:
            continue
        widened = int(literal) + (1_000_000 if match.group(1) == "<=" else -1_000_000)
        value = f"'{widened}'" if quoted is not None else str(widened)
        replacement = f"{match.group(1)} {value}{cast}"
        out.append((f"bound{n}",
                    body[:match.start()] + replacement + body[match.end():]))
    return out


def main() -> None:
    rows = ask(
        "SELECT con.conname, c.relname, pg_get_constraintdef(con.oid) "
        "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
        "WHERE c.relnamespace = 'plt01'::regnamespace AND c.relname LIKE 'acc\\_%' "
        "AND con.contype = 'c' ORDER BY 1")
    emitted = 0
    for row in rows:
        name, table, definition = row.split("|", 2)
        body = unwrap(definition)
        for label, weak in weakenings(body):
            if weak.strip() == body.strip():
                continue          # a no-op is not evidence; the rules file says so
            statement = (
                f"ALTER TABLE plt01.{table} DROP CONSTRAINT {name};\n"
                f"ALTER TABLE plt01.{table} ADD CONSTRAINT {name} CHECK ({weak});"
            )
            one_line = statement.replace("\t", "    ").replace("\n", "\x01")
            print(f"weaken\t{name}~{label}\t{table}\t{one_line}")
            emitted += 1
    print(f"{emitted} weakenings", file=sys.stderr)


main()

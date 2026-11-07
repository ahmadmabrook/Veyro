#!/usr/bin/env python3
"""Veyro MOD-004 static migration lint (Python stdlib only, no network, never writes).

  migration_lint.py lint   --track tenant|platform [--tests-root D] [--allowlist F] PATH...
  migration_lint.py corpus --root D [--allowlist F]

Exit 0 = PASS, 1 = BLOCKED (stdout JSON lists findings), 2 = malformed input/usage (fail closed).

**Scope, stated plainly: this is the static half of ADR-0002 D5 and nothing more.**
D5 requires "a Python lint over the SQL **plus live catalog assertions**". This tool is the SQL
half. It reads migration text and decides nothing about a running database: it never connects,
and it asserts nothing about `pg_roles`, `pg_class.relforcerowsecurity`, `pg_proc.prosecdef`,
`pg_auth_members`, `pg_db_role_setting`, `pg_default_acl` or `datacl` as they actually stand in a
cluster. A migration that passes here can still be applied to a cluster whose live state violates
D5. The catalog half needs the PostgreSQL capability, which is OPEN
(`BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME`), so **`BLK-SKL-MIGRATION-LINT` is not closed by this
tool existing**, and no SKL evidence ID follows from it. A passing run is not tenant-isolation
evidence, not a security pass and not a scenario PASS.

Design per ADR-0002 D5, D6.1, D6.2, D6.3 and D15.10. Each rule names its source in RULES below.

**What this tool does NOT check**, listed so a passing run is not read as D5 coverage. An earlier
revision of this list omitted most of it; the gaps below were found by an independent review that
built working evasions for sixteen of them, so treat the list as the floor of what is missing, not
the ceiling:
  * every live-state assertion -- `pg_roles` flags, `pg_class.relforcerowsecurity`, ownership,
    `pg_proc.prosecdef`, `pg_auth_members` (including transitive INHERIT and SET edges, and the
    zero-row requirement for `veyro_cp_platform`), `pg_db_role_setting`, `pg_default_acl` and
    `datacl`. This tool reads only the SQL in front of it, so it cannot see a grant made outside
    these files, a pre-existing membership, or a default set before this migration ran;
  * D5 bullet 3's second half, "any product-plane role holding CONNECT there". No source in the
    repository enumerates the product-plane roles, so the check is not implemented rather than
    implemented against a guessed list;
  * **anything inside a function body or dynamic SQL.** `_scan` blanks both dollar-quoted and
    single-quoted bodies out of the text the statement rules read, so nothing written inside one
    is linted. The lint refuses the construct instead: a `DO` block, an `EXECUTE` of an
    expression, and a body containing DDL or an `EXECUTE` are all `DYNAMIC_SQL`. **That is
    prohibition of the forms listed, not coverage of the category** -- an earlier revision claimed
    "the gap is closed by prohibition", which was false while a single-quoted body and static DDL
    inside a body were neither read nor refused. A construct that hides SQL in a way these checks
    do not recognise is still unchecked;
  * **whether a policy predicate really isolates.** `PERMISSIVE_POLICY` reads the body as a
    conjunction: a top-level `OR` is refused, at least one top-level conjunct must *be*
    `tenant_id = ... current_setting('app.tenant_id', ...)`, no conjunct may be a boolean
    constant, and `TO PUBLIC` is refused. An earlier revision asked only whether the word `true`
    appeared and whether a tenant predicate appeared somewhere; that passed
    `USING (tenant_id = ... OR 1=1)` -- `OR true` written arithmetically, a form D3 names -- while
    rejecting D3's own prescribed predicate, whose `true` is `current_setting`'s *missing_ok*
    argument. Still not decided: a conjunct that reaches other tenants through a function call or
    a subquery while matching the required shape, the policy's command coverage, and whether a
    later migration adds a second permissive policy;
  * **removal spellings `PROTECTION_REMOVED` does not enumerate.** It covers `DISABLE ROW LEVEL
    SECURITY`, `NO FORCE ROW LEVEL SECURITY`, `DROP POLICY`, dropping `tenant_id` with or without
    the optional `COLUMN` keyword, `ALTER COLUMN tenant_id DROP NOT NULL`, and `OWNER TO` a
    runtime role. Anything a `DROP TABLE`, a replacement table or a renamed column implies is not
    covered;
  * **`tenant_id` beyond `uuid` and `NOT NULL` at creation** -- no check on the foreign key, the
    policy's coverage of every command, or the column's position;
  * **privileges beyond the ones named.** The runtime-grant rule refuses TRUNCATE and REFERENCES
    to either runtime role, and additionally DELETE and TRIGGER to `veyro_cp_app` per D6.2's row
    for it. It does not implement the rest of the D6.2 matrix, so a grant that matrix bars but
    these rules do not name will pass;
  * **`NEGATIVE_TESTS` is a mention check.** It passes when a file under `--tests-root` names the
    table and a runtime role. A file whose whole content is a TODO comment naming both satisfies
    it. It is not evidence that a test exists, runs, or fails closed, and the requirement in
    `CLAUDE.md` that "negative tests must actually fail closed, not merely exist" is not met by
    this rule;
  * **`FORBIDDEN_FUNCTION_CLASS` matches words in a function's name.** It cannot see what a
    function does, so a cross-tenant list function with an innocent name passes;
  * **the platform_scope allowlist of D6 is not checked at all**, and the FORCE-RLS requirement is
    applied only to tables this tool identifies as tenant tables;
  * **the allowlist's `owner` and `execute_grantees` are never compared with the SQL.** Only
    `search_path` is, and only when the statement states one;
  * whether a `Review` id named in the SECURITY DEFINER allowlist exists or approved anything;
  * whether the SQL is valid PostgreSQL, applies cleanly, or means what it appears to mean.
    The lint is a text check, not a parser and not a planner.

**Known over-reports**, all fail-closed and all cheaper to reword than to weaken the rule. A
`COMMENT ON ... IS '... SET app. ...'` trips `SESSION_CONTEXT_SET`, and a literal naming DDL trips
`DYNAMIC_SQL`, because both scans read text with only comments removed so that
`EXECUTE 'SET app...'` cannot pass by being quoted. `CREATE TABLE ... (LIKE ... INCLUDING ALL)` and
`... PARTITION OF ...` trip the completeness rules, because there is no column list to read --
declare the table explicitly. `BRANDTHEME_OBJECT` is read wide, as its rule text says. In the
tenant track every non-platform table is treated as a tenant table and must carry the full
protections, which is a deliberate fail-closed default: an earlier revision recognised only schema
`plt01`, and a table in a third schema escaped every rule in the file.

Checking model: **per migration file.** D5's [SRC] sentence reads "A migration fails if a new
tenant table lacks ...", so a tenant table's `tenant_id`, RLS enable, RLS force, policy and
tenant-leading index must appear in the same file that creates it.

**What that reading costs, stated rather than sold as a benefit.** An earlier revision of this
paragraph claimed the per-file reading "is also the stricter one". That was wrong in the direction
that matters: the completeness rules only look at tables created in the file being linted, so they
say nothing about a table created earlier. `veyro_cp_migrator` owns the tenant tables and may
legally disable RLS, drop a policy or drop `tenant_id` in a later migration, and removal is the
realistic regression. Those four statements are therefore caught by a separate, unconditional
`PROTECTION_REMOVED` rule that does not consult the per-file bookkeeping at all. A removal spelling
that rule does not know is still invisible, which is a limit of a per-file text lint and is why the
live catalog half of D5 exists.

[ASSUMPTION], traced and not inferred silently: D6.1 item 2 puts tenant tables in schema `plt01`
and item 3 puts platform tables in `plt01_platform` and API functions in `plt01_api`. This tool
therefore treats `plt01` as the tenant schema and `plt01_platform`/`plt01_api` as platform
schemas, and treats an unqualified table name as belonging to the file's own track. D15.10's
proposed table names (`plt01_brand_appearance` and siblings) are object names, not schemas.

Tracks (D6.1 item 5): `--track tenant` is the set run as `veyro_cp_migrator`; `--track platform`
is the set run as `veyro_cp_bootstrap`. When `--track` is omitted it is inferred from a `/tenant/`
or `/platform/` path component; a path with neither is a usage error, never a default.

`--tests-root` is the runtime-role negative-test tree (ADR-0002 D5 and §5's
`backend/tests/integration/tenancy/**`). A new tenant table satisfies NEGATIVE_TESTS only when
some file under that tree names both the table and a runtime role. **A missing or absent
`--tests-root` is a finding for every new tenant table, never a skip.**

SECURITY DEFINER allowlist (`--allowlist`, default `security_definer_allowlist.json` beside this
file): `{"schema": 1, "functions": [{function, owner, search_path, execute_grantees, review_id}]}`.
D5 requires all five fields; an entry missing any of them is malformed input (exit 2), not a pass.
The allowlist is matched on the schema-qualified function name only, and **the existence of the
named review is not verified here** — the same limit `governance_check.py` records for ADR
`Review` headers.

`corpus` runs the D5 mutation corpus under `--root`. Every file under `baseline/<track>/` must
lint clean. Each mutation lives in `mutations/<EXPECTED>/<track>/*.sql`, where `<EXPECTED>` is one
or more rule names joined by `+`: the first is the rule the mutation targets, and the whole set is
the findings **each file in that directory** must produce **exactly** — no missing rule and no
extra one. Several files in one directory are several spellings of the same violation, and every
one must be caught: a directory does not qualify its rule by holding one file that happens to
fire. Everything under `nearmiss/<track>/` is a legitimate migration that must lint clean, which
is what guards against a rule firing on valid SQL. Declaring
collateral explicitly is deliberate: deleting a tenant table's `tenant_id` really does also delete
its tenant-leading index, and a corpus that demanded exactly one finding per mutation would have
to use SQL contrived to dodge that, which tests the lint less. Coverage requires every rule in
RULES to be the *target* of some mutation. A corpus whose baseline fails, whose expected set does
not match, or that leaves a rule untargeted is BLOCKED — so neither an always-failing nor an
always-passing lint can pass its own corpus.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

RUNTIME_ROLES = ("veyro_cp_app", "veyro_cp_worker")
MIGRATOR_ROLE = "veyro_cp_migrator"
PLATFORM_ROLE = "veyro_cp_platform"
BOOTSTRAP_ROLE = "veyro_cp_bootstrap"
TENANT_SCHEMA = "plt01"
PLATFORM_SCHEMAS = ("plt01_platform", "plt01_api")
TRACKS = ("tenant", "platform")
DEFAULT_ALLOWLIST = "security_definer_allowlist.json"
ALLOWLIST_SCHEMA = 1
ALLOWLIST_FIELDS = ("function", "owner", "search_path", "execute_grantees", "review_id")

# Append-only tenant tables: runtime roles hold SELECT and INSERT only (ADR-0002 D2.4, D15.9).
APPEND_ONLY_SUFFIXES = ("_history",)
APPEND_ONLY_NAMES = ("plt01_command_idempotency", "command_idempotency")
# Function name classes D6 bars from S1 outright.
FORBIDDEN_FUNCTION_WORDS = ("archive", "delete", "purge", "relocate", "remove", "destroy",
                            "cross_tenant", "list_all")

RULES = {
    # Tenant-table completeness -- D5 [SRC] sentence, D2, D3.
    "TENANT_ID_COLUMN": "new tenant table has no `tenant_id uuid NOT NULL` column (D5 [SRC]; D2.1)",
    "RLS_ENABLE": "new tenant table is not given ENABLE ROW LEVEL SECURITY (D5 [SRC]; D3)",
    "RLS_FORCE": "new tenant table is not given FORCE ROW LEVEL SECURITY (D5 [SRC]; D3)",
    "RLS_POLICY": "new tenant table has no CREATE POLICY (D5 [SRC]; D3)",
    "TENANT_LEADING_INDEX": "new tenant table has no tenant_id-leading index or primary key (D5 [SRC])",
    "NEGATIVE_TESTS": "no file under the negative-test tree names this tenant table together with a "
                      "runtime role -- a mention check, not proof that a test exists or fails closed (D5 [SRC])",
    "PERMISSIVE_POLICY": "tenant-table policy does not restrict by tenant_id, or is permissive (D3)",
    "PROTECTION_REMOVED": "migration removes a tenant table's RLS, FORCE RLS, policy, tenant_id or "
                          "its NOT NULL, or gives the table to a runtime role (D1.1; D3; D5 [SRC])",
    "DYNAMIC_SQL": "DO block or EXECUTE of dynamic SQL; the lint cannot read it and D6.3 admits none (D6.3)",
    "MIGRATION_SEARCH_PATH": "migration sets search_path, which defeats the unqualified-name track rule (D6.1)",
    # Grants -- D5 bullets 1-4, D6.2, D15.9.
    "RUNTIME_TRUNCATE_OR_REFERENCES": "TRUNCATE or REFERENCES granted to a runtime role (D5 bullet 1)",
    "DEFAULT_PRIVILEGES_GRANT": "ALTER DEFAULT PRIVILEGES grants to PUBLIC or a runtime role (D5 bullet 2)",
    "PUBLIC_GRANT": "privilege granted to PUBLIC (D5 bullet 2; D6.2)",
    "PUBLIC_DATABASE_PRIVILEGE": "CONNECT or TEMPORARY on a database granted to PUBLIC (D5 bullet 3)",
    "APPEND_ONLY_WRITE_GRANT": "UPDATE, DELETE or TRUNCATE granted on an append-only table (D2.4; D15.9)",
    # Views -- D5 bullet 4.
    "VIEW_NOT_SECURITY_INVOKER": "view is not created with security_invoker = true (D5 bullet 4)",
    "VIEW_OVER_TENANT_TABLE": "view reads a tenant table and is not on the reviewed allowlist (D5 bullet 4)",
    # SECURITY DEFINER -- D5 closing paragraphs, D6.3, D6.6 test 7.
    "SECURITY_DEFINER_UNLISTED": "SECURITY DEFINER function is not on the reviewed allowlist (D5)",
    "SECURITY_DEFINER_SEARCH_PATH": "SECURITY DEFINER function has no pinned search_path, or pg_temp precedes pg_catalog (D5; D6.6 test 7)",
    # Session-level tenant context -- D3 trust statement item (a). Scanned on text with only
    # comments removed, so the ban reaches a function body and a string literal too: D5 bans the
    # session-level set "with no exception" and D6.3 admits no dynamic SQL, so `EXECUTE 'SET
    # app...'` must not pass by being quoted. A commented-out ban is not a finding.
    "SESSION_CONTEXT_SET": "session-level app.* setting; or a set_config on an app.* name whose "
                           "third argument is not the literal true, whose name is not a literal, "
                           "or whose arity is wrong (D3 item (a))",
    # Role membership -- D6.1 item 1, D6.5.
    "ROLE_MEMBERSHIP_GRANT": "GRANT <role> TO <role> creates a membership edge (D6.1 item 1; D6.5)",
    # Tracks -- D6.1 item 5.
    "TENANT_TRACK_PLATFORM_OBJECT": "tenant-track file touches a platform schema beyond the permitted REFERENCES foreign key (D6.1 items 4-5)",
    "PLATFORM_TRACK_TENANT_TABLE": "platform-track file creates or alters a tenant table (D6.1 item 5)",
    # Scope bans.
    # Deliberately wider than D15.10's own words, which ask for "a lint check that no BrandTheme/
    # CreateBrandTheme object exists in plt01_*": this also fires on a column of that name and on
    # such a name outside plt01_*. Both are fail-closed over-reports, stated here so that a future
    # author who hits one does not narrow the rule thinking it had drifted.
    "BRANDTHEME_OBJECT": "a BrandTheme or CreateBrandTheme name in DDL -- any object, any column, "
                         "any schema, not only plt01_* (D15.10 item 1, read wide)",
    "FORBIDDEN_FUNCTION_CLASS": "function whose NAME contains an archive/delete/relocate word; a name "
                                "check only, it cannot see what a function does (D6)",
}


class Malformed(Exception):
    """Usage or input error; always exit 2, never a PASS."""


@dataclass(frozen=True)
class Finding:
    rule: str
    file: str
    statement: int
    detail: str

    def as_dict(self) -> dict:
        return {"rule": self.rule, "file": self.file, "statement": self.statement,
                "detail": self.detail, "why": RULES[self.rule]}


# --------------------------------------------------------------------------- scanning

_DOLLAR_TAG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def _scan(sql: str) -> tuple[str, str, list[str]]:
    """Return (masked, uncommented, quoted_texts).

    ``quoted_texts`` holds both dollar-quoted bodies and single-quoted string contents. A
    function body may be written either way (`AS $fn$ ... $fn$` or `AS '...'`), and collecting
    only the dollar form left the single-quoted spelling neither linted nor refused.

    ``masked`` has comments, single-quoted string bodies and dollar-quoted bodies replaced by
    spaces of the same length, so statement splitting and keyword matching never see content.
    Double-quoted identifiers are kept, because identifiers are what several rules are about.
    ``uncommented`` has only comments blanked, so a commented-out ban cannot trip a text rule
    while a ban inside a function body still can. Both strings have the same length as ``sql``,
    so one pair of offsets slices either.
    """
    masked = list(sql)
    uncommented = list(sql)
    bodies: list[str] = []
    n = len(sql)
    i = 0

    def blank(target: list[str], start: int, end: int) -> None:
        for k in range(start, end):
            if target[k] != "\n":
                target[k] = " "

    while i < n:
        ch = sql[i]
        if ch == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j < 0 else j
            blank(masked, i, j)
            blank(uncommented, i, j)
            i = j
            continue
        if ch == "/" and sql.startswith("/*", i):
            depth = 1
            j = i + 2
            while j < n and depth:
                if sql.startswith("/*", j):
                    depth += 1
                    j += 2
                elif sql.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            blank(masked, i, j)
            blank(uncommented, i, j)
            i = j
            continue
        if ch == "'":
            e_string = i > 0 and sql[i - 1] in "Ee"
            j = i + 1
            while j < n:
                if e_string and sql[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if sql[j] == "'":
                    if sql.startswith("''", j):
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            if j - 1 > i + 1:
                bodies.append(sql[i + 1:j - 1])
            blank(masked, i + 1, max(i + 1, j - 1))
            i = j
            continue
        if ch == '"':
            j = sql.find('"', i + 1)
            if j < 0:
                i = n
                continue
            # Identifier text is kept (several rules are about identifiers), but a semicolon
            # inside one must not split a statement.
            for k in range(i + 1, j):
                if masked[k] == ";":
                    masked[k] = " "
            i = j + 1
            continue
        if ch == "$":
            m = _DOLLAR_TAG.match(sql, i)
            if m:
                close = sql.find(m.group(0), m.end())
                if close < 0:
                    raise Malformed(f"unterminated dollar-quoted string at offset {i}")
                bodies.append(sql[m.end():close])
                blank(masked, m.end(), close)
                i = close + len(m.group(0))
                continue
        i += 1
    return "".join(masked), "".join(uncommented), bodies


def _statements(masked: str, uncommented: str) -> list[tuple[int, str, str]]:
    """Split into (1-based index, masked text, uncommented text) on top-level semicolons."""
    out: list[tuple[int, str, str]] = []
    start = 0
    for pos, ch in enumerate(masked):
        if ch == ";":
            if masked[start:pos].strip():
                out.append((len(out) + 1, masked[start:pos], uncommented[start:pos]))
            start = pos + 1
    if masked[start:].strip():
        out.append((len(out) + 1, masked[start:], uncommented[start:]))
    return out


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _paren_body(text: str, start: int | None = None) -> str:
    """Text inside the balanced parenthesis group opening at ``start`` (default: the first), or ''."""
    start = text.find("(") if start is None else start
    if start < 0 or start >= len(text) or text[start] != "(":
        return ""
    depth = 0
    for pos in range(start, len(text)):
        if text[pos] == "(":
            depth += 1
        elif text[pos] == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:pos]
    return ""


def _top_level_items(body: str) -> list[str]:
    """Split a parenthesised list on commas that are not nested."""
    items: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(current))
            current = []
            continue
        current.append(ch)
    if "".join(current).strip():
        items.append("".join(current))
    return items


# --------------------------------------------------------------------------- object names

_CREATE_TABLE = re.compile(
    r"^create\s+(?:unlogged\s+|foreign\s+|global\s+|local\s+|temp\s+|temporary\s+)*"
    r"table\s+(?:if\s+not\s+exists\s+)?([\w.\"]+)", re.I)
_ALTER_TABLE = re.compile(r"^alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?([\w.\"]+)", re.I)
_DROP_TABLE = re.compile(r"^drop\s+table\s+(?:if\s+exists\s+)?([\w.\"]+)", re.I)
_CREATE_INDEX = re.compile(
    r"^create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?(?:if\s+not\s+exists\s+)?"
    r"(?:[\w.\"]+\s+)?on\s+([\w.\"]+)", re.I)
_CREATE_POLICY = re.compile(r"^create\s+policy\s+[\w.\"]+\s+on\s+([\w.\"]+)", re.I)
_CREATE_VIEW = re.compile(
    r"^create\s+(?:or\s+replace\s+)?(?:materialized\s+|temp\s+|temporary\s+)?view\s+([\w.\"]+)", re.I)
_CREATE_FUNCTION = re.compile(
    r"^create\s+(?:or\s+replace\s+)?(?:function|procedure)\s+([\w.\"]+)", re.I)
_GRANT = re.compile(r"^grant\s+(.*?)\s+on\s+(.*?)\s+to\s+(.*)$", re.I | re.S)
# A role-membership grant may name several roles on either side; `([\w"]+)` could not span a
# comma, so the comma form used to fail the match and be reported as nothing at all.
_GRANT_ROLE = re.compile(
    r"^grant\s+([\w\",\s]+?)\s+to\s+([\w\",\s]+?)"
    r"(?:\s+with\s+admin\s+option|\s+with\s+inherit\s+\w+|\s+with\s+set\s+\w+"
    r"|\s+granted\s+by\s+[\w\"]+)*$", re.I | re.S)
_ALTER_FUNCTION = re.compile(
    r"^alter\s+(?:function|procedure|routine)\s+([\w.\"]+)", re.I)
_ALTER_VIEW = re.compile(r"^alter\s+(?:materialized\s+)?view\s+(?:if\s+exists\s+)?([\w.\"]+)", re.I)
_ALTER_POLICY = re.compile(r"^alter\s+policy\s+[\w.\"]+\s+on\s+([\w.\"]+)", re.I)
_DROP_POLICY = re.compile(
    r"^drop\s+policy\s+(?:if\s+exists\s+)?[\w.\"]+\s+on\s+([\w.\"]+)", re.I)
_DO_BLOCK = re.compile(r"^do\b", re.I)
# `EXECUTE` is also the name of a privilege (`GRANT EXECUTE ON FUNCTION ...`) and of a prepared
# statement form; only the dynamic-SQL sense is a finding. The platform baseline's
# `REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC` caught the first, over-broad version of this.
_EXECUTE_DYNAMIC = re.compile(
    r"\bexecute\s+(?!on\b|procedure\b|function\b|functions\b|routine\b|routines\b)(?=\S)", re.I)
_GRANT_OR_REVOKE = re.compile(r"^(?:grant|revoke|alter\s+default\s+privileges)\b", re.I)
_BODY_DDL = re.compile(
    r"\b(?:create|alter|drop)\s+(?:table|policy|view|schema|role|user|database|index|function)\b"
    r"|\b(?:grant|revoke)\s+\w+", re.I)
_SEARCH_PATH_SET = re.compile(r"^set\s+(?:session\s+|local\s+)?[\"]?search_path[\"]?\b", re.I)
_POLICY_CLAUSE = re.compile(r"\b(using|with\s+check)\s*\(", re.I)
# Anchored, and tolerant of what sits between `=` and the setting read: D3's prescribed predicate
# is `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`.
_TENANT_PREDICATE = re.compile(
    r'^"?tenant_id"?\s*=\s*[^=]*current_setting\s*\(\s*\'app\.tenant_id\'', re.I)
_REVOKE = re.compile(r"^revoke\b", re.I)
_ALTER_DEFAULT_PRIV = re.compile(r"^alter\s+default\s+privileges\b", re.I)
_ALTER_ROLE_DB_SET = re.compile(
    r"^alter\s+(?:role|user|database)\b.*?\bset\s+([\w.\"]+)", re.I | re.S)
# `([\w.]+)` could not see past a leading quote, so `SET "app"."tenant_id"` walked through. The
# parameter name is now captured loosely and normalised by _guc_name().
_SET_STMT = re.compile(r"^set\s+(?:session\s+|local\s+)?([\w.\"]+)", re.I)
_SET_CONFIG = re.compile(r"\bset_config\s*\(", re.I)
_SESSION_APP_SET = re.compile(r"\bset\s+(?:session\s+)?[\"]?app[\"]?\s*\.", re.I)


def _unquote(name: str) -> str:
    return name.replace('"', "").lower()


def _fold(part: str) -> str:
    """Fold one identifier the way PostgreSQL does: lower-case unless it was quoted.

    `plt01."T"` and `plt01.t` are two different tables. Lower-casing unconditionally merged them,
    so a file could create an unprotected `"T"` and satisfy the completeness rules by protecting
    `t`.
    """
    part = part.strip()
    if len(part) >= 2 and part.startswith('"') and part.endswith('"'):
        return part[1:-1]
    return part.lower()


def _split_name(name: str) -> tuple[str, str]:
    """(schema, object) for a possibly-qualified name; schema '' when unqualified."""
    parts = [_fold(p) for p in name.split(".")]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "", parts[-1]


def _is_platform_schema(schema: str) -> bool:
    return schema in PLATFORM_SCHEMAS


def _is_tenant_table(name: str, track: str) -> bool:
    """Whether a table must carry the tenant-table protections.

    Fail-closed in the tenant track: anything that track touches which is not in a platform
    schema is a tenant table, whatever schema it names. An earlier version recognised only schema
    `plt01` and unqualified names, so `CREATE TABLE plt01_v2.brand_appearance (...)` was neither a
    tenant table nor a platform object and escaped every rule in the file -- no RLS, no policy, no
    tenant-leading index, full DML to a runtime role, and a PASS. D6 states the invariant this
    carries: every table outside `plt01_platform` must be FORCE RLS.
    """
    schema, _ = _split_name(name)
    if _is_platform_schema(schema):
        return False
    if track == "tenant":
        return True
    return schema == TENANT_SCHEMA


def _is_append_only(obj: str) -> bool:
    return obj in APPEND_ONLY_NAMES or obj.endswith(APPEND_ONLY_SUFFIXES)


def _grantees(text: str) -> list[str]:
    """Role names a GRANT names, with the trailing option clause removed.

    `TO veyro_cp_app WITH GRANT OPTION` used to yield the single token
    `"veyro_cp_app with grant option"`, which matched no entry in RUNTIME_ROLES and was not
    `"public"` -- so one suffix defeated the TRUNCATE/REFERENCES, PUBLIC, append-only and
    default-privilege rules at once.
    """
    text = re.sub(r"\s+with\s+(?:grant|admin)\s+option\s*$", "", _norm(text), flags=re.I)
    text = re.sub(r"\s+granted\s+by\s+[\w\"]+\s*$", "", text, flags=re.I)
    out = []
    for raw in text.split(","):
        token = _unquote(raw.strip())
        token = re.sub(r"^group\s+", "", token)
        if token:
            out.append(token)
    return out


# --------------------------------------------------------------------------- allowlist

def load_allowlist(path: Path) -> tuple[dict[str, dict], set[str]]:
    """Return ({function name: entry}, {allowlisted view names}). Fails closed on any defect."""
    if not path.exists():
        raise Malformed(f"allowlist not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Malformed(f"allowlist unreadable: {exc}") from None
    if not isinstance(data, dict) or data.get("schema") != ALLOWLIST_SCHEMA:
        raise Malformed(f"allowlist schema must be {ALLOWLIST_SCHEMA}")
    functions = data.get("functions")
    views = data.get("views", [])
    if not isinstance(functions, list) or not isinstance(views, list):
        raise Malformed("allowlist 'functions' and 'views' must be lists")
    out: dict[str, dict] = {}
    for entry in functions:
        if not isinstance(entry, dict):
            raise Malformed("allowlist function entry must be an object")
        missing = [f for f in ALLOWLIST_FIELDS if not entry.get(f)]
        if missing:
            raise Malformed(f"allowlist entry missing required D5 fields: {', '.join(missing)}")
        if not isinstance(entry["execute_grantees"], list):
            raise Malformed("allowlist execute_grantees must be a list")
        schema, obj = _split_name(str(entry["function"]).split("(")[0])
        if not schema:
            raise Malformed(f"allowlist function must be schema-qualified: {entry['function']}")
        out[f"{schema}.{obj}"] = entry
    view_names = set()
    for raw in views:
        schema, obj = _split_name(str(raw))
        view_names.add(f"{schema}.{obj}" if schema else obj)
    return out, view_names


# --------------------------------------------------------------------------- the lint

def lint_file(path: Path, track: str, allowlist: dict[str, dict], view_allowlist: set[str],
              tests_root: Path | None) -> list[Finding]:
    """Lint one migration file. Returns findings; an empty list means this file passed."""
    try:
        sql = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Malformed(f"cannot read {path}: {exc}") from None
    masked, uncommented, bodies = _scan(sql)
    statements = _statements(masked, uncommented)
    name = str(path)
    findings: list[Finding] = []

    def add(rule: str, index: int, detail: str) -> None:
        findings.append(Finding(rule, name, index, detail))

    created_tables: dict[str, int] = {}
    rls_enabled: set[str] = set()
    rls_forced: set[str] = set()
    policed: set[str] = set()
    tenant_indexed: set[str] = set()

    for index, stmt, raw in statements:
        norm = _norm(stmt)
        raw_norm = _norm(raw)

        # -- session-level tenant context (D3 item (a)). Scanned on the uncommented text so a
        # -- ban inside a dollar-quoted function body is caught too.
        if _SESSION_APP_SET.search(raw_norm) and not re.search(r"\bset\s+local\s+app\.", raw_norm, re.I):
            add("SESSION_CONTEXT_SET", index, "session-level SET app.*")
        for detail in _set_config_violations(raw_norm):
            add("SESSION_CONTEXT_SET", index, detail)
        m = _ALTER_ROLE_DB_SET.match(norm)
        if m and _guc_name(m.group(1)).startswith("app."):
            add("SESSION_CONTEXT_SET", index,
                f"ALTER ... SET {_guc_name(m.group(1))} becomes a reset default")
        m = _SET_STMT.match(norm)
        if m and _guc_name(m.group(1)).startswith("app.") \
                and not re.match(r"^set\s+local\b", norm, re.I):
            add("SESSION_CONTEXT_SET", index,
                f"SET {_guc_name(m.group(1))} is not transaction-local")

        # -- dynamic SQL (D6.3 admits none). This rule is load-bearing for every other rule:
        # -- _scan blanks dollar-quoted bodies out of `masked`, so DDL routed through a DO block or
        # -- an EXECUTE of a string is invisible to the statement rules. Rather than reconstruct
        # -- the text, the lint refuses the construct.
        if _DO_BLOCK.match(norm):
            add("DYNAMIC_SQL", index, "DO block; its body is not linted")
        if not _GRANT_OR_REVOKE.match(norm) and _EXECUTE_DYNAMIC.search(norm):
            add("DYNAMIC_SQL", index, "EXECUTE of dynamic SQL; its text is not linted")

        # -- search_path (D6.1). The track rules read an unqualified name as belonging to the
        # -- file's own track; a search_path makes that false, so the statement is refused.
        if _SEARCH_PATH_SET.match(norm) \
                or re.search(r"set_config\s*\(\s*'search_path'", raw_norm, re.I) \
                or (_ALTER_ROLE_DB_SET.match(norm)
                    and _guc_name(_ALTER_ROLE_DB_SET.match(norm).group(1)) == "search_path"):
            add("MIGRATION_SEARCH_PATH", index, _norm(norm)[:120])

        # -- BrandTheme ban (D15.10 item 1). Scoped to object names and to plt01 DDL, not to any
        # -- two substrings anywhere in the statement: an INSERT of the string 'brandtheme_enabled'
        # -- is data, not an object named BrandTheme.
        for obj_name, kind in _objects_touched(norm):
            if re.search(r"brand_?theme", obj_name, re.I):
                add("BRANDTHEME_OBJECT", index, f"{kind} {obj_name}")
        if re.search(r"(?:create|alter|drop)\s[^']*brand_?theme", norm, re.I):
            add("BRANDTHEME_OBJECT", index, "BrandTheme/CreateBrandTheme name in DDL")

        # -- role membership (D6.1 item 1).
        if re.match(r"^grant\b", norm, re.I) and " on " not in f" {norm.lower()} ":
            m = _GRANT_ROLE.match(norm)
            if m:
                add("ROLE_MEMBERSHIP_GRANT", index,
                    f"GRANT {_norm(m.group(1))} TO {_norm(m.group(2))}")

        # -- tracks (D6.1 item 5). The platform track owns plt01_platform and plt01_api; every
        # -- other table it creates or alters is in the wrong track, not only a plt01-schema one,
        # -- because an unqualified or differently-prefixed schema was previously unreachable by
        # -- this rule and passed clean.
        for obj_name, kind in _objects_touched(norm):
            schema, obj = _split_name(obj_name)
            if track == "tenant" and _is_platform_schema(schema):
                if not _permitted_platform_reference(norm, schema, obj):
                    add("TENANT_TRACK_PLATFORM_OBJECT", index, f"{kind} {schema}.{obj}")
            if track == "platform" and kind in ("create table", "alter table", "drop table"):
                if not _is_platform_schema(schema):
                    add("PLATFORM_TRACK_TENANT_TABLE", index, f"{kind} {obj_name}")

        # -- grants (D5 bullets 1-3, D6.2, D2.4, D15.9).
        if re.match(r"^grant\b", norm, re.I) and " on " in f" {norm.lower()} ":
            gm = _GRANT.match(norm)
            if gm:
                privileges = gm.group(1).lower()
                target = gm.group(2)
                to_roles = _grantees(gm.group(3))
                # A column list stays glued to its privilege token unless it is stripped first:
                # `references (tenant_id)` never equalled `references`, so the column-level form
                # of every privilege rule passed clean. That spelling is the house style in the
                # corpus baseline, so it was the likeliest one to be written.
                bare = re.sub(r"\([^)]*\)", " ", privileges.replace("privileges", " "))
                priv_set = {p.strip() for p in bare.split(",") if p.strip()}
                is_all = "all" in priv_set
                schema_wide = bool(re.search(r"\ball\s+\w+\s+in\s+schema\b", norm, re.I))
                if "public" in to_roles:
                    on_database = bool(re.search(r"\bon\s+database\b", norm, re.I))
                    if on_database and (is_all or priv_set & {"connect", "temporary", "temp"}):
                        add("PUBLIC_DATABASE_PRIVILEGE", index, f"GRANT {privileges} TO PUBLIC")
                    else:
                        add("PUBLIC_GRANT", index, f"GRANT {privileges} ON {_norm(target)} TO PUBLIC")
                for role in to_roles:
                    barred = {"truncate", "references"}
                    if role == "veyro_cp_app":
                        # D6.2's row for this role: "no DELETE, TRUNCATE, REFERENCES or TRIGGER".
                        barred |= {"delete", "trigger"}
                    if role in RUNTIME_ROLES and (is_all or priv_set & barred):
                        add("RUNTIME_TRUNCATE_OR_REFERENCES", index,
                            f"GRANT {privileges} TO {role}")
                    if role in RUNTIME_ROLES and (is_all or priv_set & {"update", "delete", "truncate"}):
                        if schema_wide:
                            # One statement reaches every *_history table and the idempotency
                            # table in the schema, which the per-table name check never saw.
                            add("APPEND_ONLY_WRITE_GRANT", index,
                                f"GRANT {privileges} ON {_norm(target)} TO {role} reaches "
                                f"every append-only table in the schema")
                        for obj_name, _ in _grant_targets(target):
                            _, obj = _split_name(obj_name)
                            if _is_append_only(obj):
                                add("APPEND_ONLY_WRITE_GRANT", index,
                                    f"GRANT {privileges} ON {obj} TO {role}")
        if _ALTER_DEFAULT_PRIV.match(norm) and not re.search(r"\brevoke\b", norm, re.I):
            if re.search(r"\bgrant\b", norm, re.I):
                to_roles = _grantees(norm.lower().split(" to ")[-1]) if " to " in norm.lower() else []
                if "public" in to_roles or any(r in RUNTIME_ROLES for r in to_roles):
                    add("DEFAULT_PRIVILEGES_GRANT", index, _norm(norm)[:120])

        # -- views (D5 bullet 4).
        vm = _CREATE_VIEW.match(norm)
        if vm:
            schema, obj = _split_name(vm.group(1))
            qualified = f"{schema}.{obj}" if schema else obj
            if not re.search(r"security_invoker\s*=\s*true", norm, re.I):
                add("VIEW_NOT_SECURITY_INVOKER", index, qualified)
            if qualified not in view_allowlist and obj not in view_allowlist:
                # Every identifier in the body, not only the token after FROM/JOIN: a comma join
                # and the `AS TABLE t` form both reach a tenant table without one.
                for ref in _referenced_tables(norm):
                    if ref != qualified and _is_tenant_table(ref, track):
                        add("VIEW_OVER_TENANT_TABLE", index, f"{qualified} reads {ref}")
                        break
        avm = _ALTER_VIEW.match(norm)
        if avm and (re.search(r"security_invoker\s*=\s*(?!true)", norm, re.I)
                    or re.search(r"\breset\s*\([^)]*security_invoker", norm, re.I)):
            # RESET restores the default, which is false, so it turns the option off as surely as
            # SET ... = false. ALTER FUNCTION ... RESET search_path was already handled; this was
            # the same omission one rule over.
            add("VIEW_NOT_SECURITY_INVOKER", index,
                f"{_norm(avm.group(1))} has security_invoker turned off after creation")

        # -- SECURITY DEFINER (D5 closing paragraphs; D6.6 test 7).
        fm = _CREATE_FUNCTION.match(norm)
        if fm:
            schema, obj = _split_name(fm.group(1))
            qualified = f"{schema}.{obj}" if schema else obj
            if any(word in obj for word in FORBIDDEN_FUNCTION_WORDS):
                add("FORBIDDEN_FUNCTION_CLASS", index, qualified)
            if re.search(r"\bsecurity\s+definer\b", norm, re.I):
                findings.extend(_definer_findings(name, index, qualified, norm, allowlist))

        # ALTER FUNCTION is the natural way to make an existing function SECURITY DEFINER, or to
        # strip the pinned search_path off an allowlisted one. Both used to pass clean, because
        # every definer check sat under the CREATE FUNCTION match.
        afm = _ALTER_FUNCTION.match(norm)
        if afm:
            schema, obj = _split_name(afm.group(1).split("(")[0])
            qualified = f"{schema}.{obj}" if schema else obj
            if re.search(r"\bsecurity\s+definer\b", norm, re.I):
                findings.extend(_definer_findings(name, index, qualified, norm, allowlist))
            if re.search(r"\breset\s+(?:search_path|all)\b", norm, re.I):
                add("SECURITY_DEFINER_SEARCH_PATH", index,
                    f"{qualified} has its pinned search_path reset")
            elif re.search(r"\bset\s+search_path\b", norm, re.I):
                findings.extend(_definer_findings(name, index, qualified, norm, allowlist,
                                                  search_path_only=True))

        # -- tenant-table completeness bookkeeping.
        cm = _CREATE_TABLE.match(norm)
        if cm and _is_tenant_table(cm.group(1), track):
            _, obj = _split_name(cm.group(1))
            created_tables.setdefault(obj, index)
            columns = _top_level_items(_paren_body(stmt))
            column_names = [_norm(c).split()[0].replace('"', "").lower() for c in columns if _norm(c)]
            if "tenant_id" not in column_names:
                add("TENANT_ID_COLUMN", index, obj)
            else:
                # D2.1 is [SRC]: "Every tenant-owned table has `tenant_id UUID NOT NULL`". A
                # nullable column puts rows outside every policy comparison, and a non-uuid type
                # changes the comparison semantics; the name alone was not enough.
                decl = next(_norm(c) for c in columns
                            if _norm(c) and _norm(c).split()[0].replace('"', "").lower() == "tenant_id")
                if not re.match(r'^"?tenant_id"?\s+uuid\b', decl, re.I):
                    add("TENANT_ID_COLUMN", index, f"{obj}: tenant_id is not uuid ({decl[:60]})")
                elif not re.search(r"\bnot\s+null\b", decl, re.I) \
                        and not _tenant_leading_primary_key(columns):
                    add("TENANT_ID_COLUMN", index, f"{obj}: tenant_id is nullable ({decl[:60]})")
            for item in columns:
                item_norm = _norm(item)
                # A UNIQUE constraint creates a tenant-leading index just as a primary key does,
                # and D15.10 item 2's own proposed schema uses `UNIQUE (tenant_id, brand_id)`.
                if re.match(r"^(?:constraint\s+\S+\s+)?(?:primary\s+key|unique)\b", item_norm, re.I):
                    cols = [_unquote(c.strip()) for c in _top_level_items(_paren_body(item_norm))]
                    if cols and cols[0] == "tenant_id":
                        tenant_indexed.add(obj)
        am = _ALTER_TABLE.match(norm)
        if am and _is_tenant_table(am.group(1), track):
            _, obj = _split_name(am.group(1))
            # Removal is checked before addition and unconditionally: these statements are legal
            # for veyro_cp_migrator, which owns the tenant tables, and a later migration that
            # strips protection off a table created in an earlier file used to pass clean.
            if re.search(r"\bno\s+force\s+row\s+level\s+security\b", norm, re.I):
                add("PROTECTION_REMOVED", index, f"NO FORCE ROW LEVEL SECURITY on {obj}")
            elif re.search(r"\bforce\s+row\s+level\s+security\b", norm, re.I):
                rls_forced.add(obj)
            if re.search(r"\bdisable\s+row\s+level\s+security\b", norm, re.I):
                add("PROTECTION_REMOVED", index, f"DISABLE ROW LEVEL SECURITY on {obj}")
            elif re.search(r"\benable\s+row\s+level\s+security\b", norm, re.I):
                rls_enabled.add(obj)
            # `COLUMN` is optional in PostgreSQL, and dropping NOT NULL is the same loss by a
            # different route: the lint requires NOT NULL at creation precisely because a nullable
            # tenant_id falls outside every policy comparison.
            if re.search(r"\bdrop\s+(?:column\s+)?(?:if\s+exists\s+)?[\"]?tenant_id\b", norm, re.I):
                add("PROTECTION_REMOVED", index, f"DROP tenant_id on {obj}")
            if re.search(r"\balter\s+column\s+[\"]?tenant_id[\"]?\s+drop\s+not\s+null\b", norm, re.I):
                add("PROTECTION_REMOVED", index, f"tenant_id made nullable on {obj}")
            owner = re.search(r"\bowner\s+to\s+([\w\"]+)", norm, re.I)
            if owner and _unquote(owner.group(1)) in RUNTIME_ROLES:
                # D1.1 is [SRC]: runtime roles do not own tenant tables. An owner can disable its
                # own table's RLS, so this hands the runtime role the power to remove the very
                # protections this rule exists to keep.
                add("PROTECTION_REMOVED", index,
                    f"{obj} given to runtime role {_unquote(owner.group(1))}, which may then "
                    f"disable its own RLS")
            key = re.search(r"\badd\s+(?:constraint\s+\S+\s+)?(?:primary\s+key|unique)\b",
                            norm, re.I)
            if key:
                # Anchored to the match: _paren_body's default took the FIRST paren group, so
                # `ADD COLUMN fee numeric(10,2), ADD PRIMARY KEY (tenant_id, id)` read (10,2).
                cols = [_unquote(c.strip())
                        for c in _top_level_items(_paren_body(norm, norm.find("(", key.end())))]
                if cols and cols[0] == "tenant_id":
                    tenant_indexed.add(obj)
        pm = _CREATE_POLICY.match(norm) or _ALTER_POLICY.match(norm)
        if pm and _is_tenant_table(pm.group(1), track):
            if _CREATE_POLICY.match(norm):
                # Only a CREATE creates one. An ALTER of a policy that does not exist used to
                # satisfy RLS_POLICY for a table created in the same file.
                policed.add(_split_name(pm.group(1))[1])
            # D3: the policy must restrict by tenant_id. Presence of *a* policy is not isolation;
            # `USING (true)` ticks every D5-listed box and isolates nothing, and D6's option-B
            # rationale rests on no permissive policy existing anywhere.
            # On `raw_norm`, not `norm`: _scan blanks string literals out of the masked text, so
            # the `'app.tenant_id'` the predicate must name is not there to find and every policy
            # would read as unrestricted. The clean baseline caught this.
            for detail in _policy_predicate_violations(raw_norm):
                add("PERMISSIVE_POLICY", index, f"{_norm(pm.group(1))}: {detail}")
        dpm = _DROP_POLICY.match(norm)
        if dpm and _is_tenant_table(dpm.group(1), track):
            add("PROTECTION_REMOVED", index, f"DROP POLICY on {_norm(dpm.group(1))}")
        im = _CREATE_INDEX.match(norm)
        if im and _is_tenant_table(im.group(1), track):
            cols = [_unquote(c.strip())
                    for c in _top_level_items(_paren_body(norm, norm.find("(", im.end())))]
            if cols and cols[0].split()[0] == "tenant_id":
                tenant_indexed.add(_split_name(im.group(1))[1])

    for body in bodies:
        body_norm = _norm(body)
        if _SESSION_APP_SET.search(body_norm) and not re.search(r"\bset\s+local\s+app\.", body_norm, re.I):
            add("SESSION_CONTEXT_SET", 0, "session-level SET app.* inside a function body")
        for detail in _set_config_violations(body_norm):
            add("SESSION_CONTEXT_SET", 0, f"{detail} (inside a function body)")
        if _EXECUTE_DYNAMIC.search(body_norm):
            add("DYNAMIC_SQL", 0, "EXECUTE of dynamic SQL inside a quoted body")
        # A body is blanked out of the text the statement rules read, so DDL written inside one is
        # invisible to all of them. Refusing the construct is what makes "closed by prohibition"
        # true; without this a single-quoted body carrying `ALTER TABLE ... DISABLE ROW LEVEL
        # SECURITY` was neither linted nor refused.
        ddl = _BODY_DDL.search(body_norm)
        if ddl:
            add("DYNAMIC_SQL", 0,
                f"DDL inside a quoted body is not linted: {_norm(ddl.group(0))[:60]}")

    for obj, index in sorted(created_tables.items()):
        if obj not in rls_enabled:
            add("RLS_ENABLE", index, obj)
        if obj not in rls_forced:
            add("RLS_FORCE", index, obj)
        if obj not in policed:
            add("RLS_POLICY", index, obj)
        if obj not in tenant_indexed:
            add("TENANT_LEADING_INDEX", index, obj)
        if not _has_negative_test(tests_root, obj):
            detail = obj if tests_root and tests_root.is_dir() else f"{obj} (no --tests-root tree)"
            add("NEGATIVE_TESTS", index, detail)

    # One statement can match two spellings of the same ban (`SET app.x` is both a bare SET and a
    # session-level app setting); report it once.
    seen: set[tuple[str, int, str]] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (finding.rule, finding.statement, finding.detail)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


_OBJECT_PATTERNS = (
    (_CREATE_TABLE, "create table"),
    (_ALTER_TABLE, "alter table"),
    (_DROP_TABLE, "drop table"),
    (_CREATE_INDEX, "create index"),
    (_CREATE_POLICY, "create policy"),
    (_CREATE_VIEW, "create view"),
    (_CREATE_FUNCTION, "create function"),
)


def _objects_touched(norm: str) -> list[tuple[str, str]]:
    """(name, kind) pairs for the statement's own target, plus any platform schema it names."""
    out: list[tuple[str, str]] = []
    for pattern, kind in _OBJECT_PATTERNS:
        m = pattern.match(norm)
        if m:
            out.append((m.group(1), kind))
            break
    for schema in PLATFORM_SCHEMAS:
        for m in re.finditer(rf"\b{schema}\.([\w\"]+)", norm, re.I):
            pair = (f"{schema}.{_unquote(m.group(1))}", "reference")
            if pair not in out:
                out.append(pair)
    for m in re.finditer(r"^(?:create|alter|drop)\s+schema\s+(?:if\s+(?:not\s+)?exists\s+)?([\w\"]+)",
                         norm, re.I):
        out.append((_unquote(m.group(1)), "schema ddl"))
    return out


def _guc_name(raw: str) -> str:
    """Normalise a parameter name so a quoted spelling cannot hide it.

    `SET "app"."tenant_id"` and `SET "app.tenant_id"` both set the GUC `app.tenant_id`
    (PostgreSQL's `var_name` is `ColId | var_name '.' ColId`, and `ColId` admits a quoted
    identifier), so a check that matched the bare characters `app.` missed both.
    """
    return raw.replace('"', "").replace(" ", "").lower()


def _tenant_leading_primary_key(columns: list[str]) -> bool:
    for item in columns:
        item_norm = _norm(item)
        if re.match(r"^(?:constraint\s+\S+\s+)?primary\s+key\b", item_norm, re.I):
            cols = [_unquote(c.strip()) for c in _top_level_items(_paren_body(item_norm))]
            return bool(cols) and cols[0] == "tenant_id"
    return False


def _blank_literals(text: str) -> str:
    """Same-length copy with single-quoted string contents replaced by spaces.

    Needed wherever a structure has to be read past a literal: splitting `set_config`'s arguments
    on commas used to count a comma inside `'a,b'` as an argument separator and report wrong
    arity for valid SQL.
    """
    out = list(text)
    i = 0
    while i < len(text):
        if text[i] == "'":
            j = i + 1
            while j < len(text):
                if text[j] == "'":
                    if text.startswith("''", j):
                        j += 2
                        continue
                    break
                j += 1
            for k in range(i + 1, min(j, len(text))):
                out[k] = " "
            i = j + 1
            continue
        i += 1
    return "".join(out)


def _top_level_items_past_literals(body: str) -> list[str]:
    """Split on commas that are neither nested nor inside a string literal."""
    blanked = _blank_literals(body)
    items: list[str] = []
    depth = 0
    start = 0
    for pos, char in enumerate(blanked):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(body[start:pos])
            start = pos + 1
    if body[start:].strip():
        items.append(body[start:])
    return items


def _top_level_split(text: str, keyword: str) -> list[str]:
    """Split on a keyword appearing at paren depth zero and outside any string literal."""
    blanked = _blank_literals(text)
    pattern = re.compile(rf"\b{keyword}\b", re.I)
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(blanked):
        char = blanked[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0:
            match = pattern.match(blanked, i)
            if match:
                parts.append(text[start:i])
                start = match.end()
                i = match.end()
                continue
        i += 1
    parts.append(text[start:])
    return [part for part in parts if part.strip()]


def _strip_outer_parens(text: str) -> str:
    text = text.strip()
    while text.startswith("(") and _paren_body(text, 0) == text[1:-1]:
        text = text[1:-1].strip()
    return text


def _policy_predicate_violations(norm: str) -> list[str]:
    """ADR-0002 D3: a tenant-table policy must restrict by tenant_id and must not be permissive.

    **Structural, not existential, and that distinction is the whole rule.** An earlier version
    asked whether the word ``true`` appeared anywhere and whether a tenant predicate appeared
    somewhere. Both tests were satisfied by
    ``USING (tenant_id = current_setting('app.tenant_id', false)::uuid OR 1=1)``, which reads and
    writes every tenant's rows -- D3 names that form ("No tenant-table policy uses `OR true` ...")
    and ``OR 1=1`` is ``OR true`` written arithmetically. The same version rejected D3's own
    prescribed predicate, ``tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid``,
    because the ``true`` there is ``current_setting``'s *missing_ok* argument -- the thing that
    produces D3's fail-closed contract.

    So the body is read as a conjunction instead:

    1. A top-level ``OR`` is rejected outright. Only a disjunct can widen a predicate; ``AND``
       with anything can only narrow, so an ``OR`` nested inside a conjunct's own parentheses is
       not a finding.
    2. At least one top-level conjunct must *be* the tenant predicate -- it must start
       ``tenant_id =`` and name ``current_setting('app.tenant_id', ...)``. Appearing somewhere in
       the body is not enough.
    3. No top-level conjunct may be a bare boolean constant.
    4. A policy granted ``TO PUBLIC`` is a bypass whatever its body says.

    What this still does not decide: a conjunct that reaches other tenants through a function call
    or a subquery while matching the shape in (2), and anything about the policy's command
    coverage or about a second permissive policy added by a later migration. It is a text check
    over a conjunction, not a decision procedure, which is why D5's catalog half has to exist.
    """
    out: list[str] = []
    if re.search(r"\bto\s+public\b", _blank_literals(norm), re.I):
        out.append("granted TO PUBLIC")
    clauses = []
    for match in _POLICY_CLAUSE.finditer(_blank_literals(norm)):
        body = _paren_body(norm, norm.find("(", match.end() - 1))
        clauses.append((match.group(1).lower(), body))
    if not clauses:
        out.append("no USING or WITH CHECK predicate")
        return out
    for kind, body in clauses:
        body = _strip_outer_parens(_norm(body))
        if len(_top_level_split(body, "or")) > 1:
            out.append(f"{kind} predicate has a top-level OR, which can only widen it: "
                       f"{body[:70]}")
            continue
        conjuncts = [_strip_outer_parens(part) for part in _top_level_split(body, "and")]
        constant = next((c for c in conjuncts
                         if re.fullmatch(r"(?:true|1\s*=\s*1)", c, re.I)), None)
        if constant is not None:
            out.append(f"{kind} predicate has the constant conjunct `{constant}`")
            continue
        if not any(_TENANT_PREDICATE.match(c) for c in conjuncts):
            out.append(f"{kind} predicate has no `tenant_id = current_setting('app.tenant_id', ...)`"
                       f" conjunct: {body[:70]}")
    return out


def _definer_findings(name: str, index: int, qualified: str, norm: str,
                      allowlist: dict[str, dict], search_path_only: bool = False) -> list[Finding]:
    """SECURITY DEFINER checks, shared by CREATE FUNCTION and ALTER FUNCTION."""
    out: list[Finding] = []
    entry = allowlist.get(qualified)
    if not search_path_only and entry is None:
        out.append(Finding("SECURITY_DEFINER_UNLISTED", name, index, qualified))
    # Terminated by the next function-option keyword, not by the next semicolon: `[^;]*` swallowed
    # `AS $fn$ BEGIN ...` into the schema list, which made the comparison with the allowlisted
    # search_path below fail on a correctly pinned function.
    sp = re.search(
        r"\bset\s+search_path\s*(?:=|to)\s*(.*?)"
        r"(?=\s+(?:as|language|returns|security|strict|immutable|stable|volatile|leakproof|"
        r"called|cost|rows|parallel|support|window|set|external|transform|begin)\b|;|$)",
        norm, re.I)
    if not sp:
        if not search_path_only:
            out.append(Finding("SECURITY_DEFINER_SEARCH_PATH", name, index,
                               f"{qualified} pins no search_path"))
        return out
    schemas = [_unquote(part.strip()) for part in sp.group(1).split(",") if part.strip()]
    if "pg_catalog" not in schemas:
        out.append(Finding("SECURITY_DEFINER_SEARCH_PATH", name, index,
                           f"{qualified} search_path omits pg_catalog"))
    elif "pg_temp" in schemas and schemas.index("pg_temp") < schemas.index("pg_catalog"):
        out.append(Finding("SECURITY_DEFINER_SEARCH_PATH", name, index,
                           f"{qualified} places pg_temp before pg_catalog"))
    if entry is not None:
        expected = [_unquote(part.strip()) for part in str(entry["search_path"]).split(",")
                    if part.strip()]
        if expected and expected != schemas:
            out.append(Finding("SECURITY_DEFINER_SEARCH_PATH", name, index,
                               f"{qualified} search_path {schemas} differs from the allowlisted "
                               f"{expected}"))
    return out


def _set_config_violations(text: str) -> list[str]:
    """`set_config`'s third argument must be the literal ``true`` (the parameterized `SET LOCAL`).

    Anything else is a finding: ``false``, a cast such as ``false::boolean``, an expression such as
    ``(1=0)``, or a missing argument. The lint does not evaluate an expression to decide whether
    the tenant context escapes its transaction, so it refuses the whole class. Checked only when
    the setting name is an ``app.*`` literal, which is what ADR-0002 D3 item (a) bans; a name that
    is not a literal at all cannot be cleared, so it is a finding too.
    """
    out: list[str] = []
    for match in _SET_CONFIG.finditer(text):
        open_paren = text.find("(", match.end() - 1)
        args_text = _paren_body(text, open_paren)
        args = [_norm(a) for a in _top_level_items_past_literals(args_text)]
        if len(args) != 3:
            out.append(f"set_config takes three arguments, found {len(args)}")
            continue
        name = args[0]
        literal = re.fullmatch(r"'([^']*)'(?:::\s*text)?", name, re.I)
        if literal is None:
            out.append(f"set_config setting name {name} is not a literal, so app.* cannot be ruled out")
            continue
        if not literal.group(1).lower().startswith("app."):
            continue
        if args[2].lower() != "true":
            out.append(f"set_config('{literal.group(1)}', ..., {args[2]}) is not transaction-local")
    return out


def _permitted_platform_reference(norm: str, schema: str, obj: str) -> bool:
    """D6.1 item 4: the one allowed tenant-track reach into a platform schema."""
    if schema != "plt01_platform" or obj != "tenants":
        return False
    return bool(re.search(r"\breferences\s+plt01_platform\.tenants\b", norm, re.I))


def _grant_targets(target: str) -> list[tuple[str, str]]:
    cleaned = re.sub(r"^\s*(?:table|sequence|function|procedure|routine|schema|database|all\s+\w+\s+in\s+schema)\s+",
                     "", _norm(target), flags=re.I)
    return [(_unquote(part.strip()), "grant") for part in cleaned.split(",") if part.strip()]


_FROM_CLAUSE = re.compile(
    r"\bfrom\s+(.*?)(?=\bwhere\b|\bgroup\s+by\b|\bhaving\b|\border\s+by\b|\blimit\b"
    r"|\boffset\b|\bunion\b|\bexcept\b|\bintersect\b|\bwindow\b|\bselect\b|$)", re.I | re.S)
_JOINED = re.compile(r"\b(?:join|table)\s+([\w.\"]+)", re.I)
_QUALIFIED = re.compile(r"\b([\w\"]+\.[\w\"]+)\b")


def _referenced_tables(norm: str) -> list[str]:
    """Identifiers in a statement that could name a table.

    Three sources, because capturing only the token after FROM/JOIN missed a comma join
    (`FROM pg_catalog.pg_class c, plt01.brand_appearance b`) and the `CREATE VIEW v AS TABLE t`
    form: every schema-qualified name anywhere; the first token of each comma-separated item of
    every FROM clause, which is how an unqualified comma-joined table is reached; and the token
    after JOIN or TABLE.

    Scoped this way on purpose. An earlier version took every identifier in the statement, which in
    the tenant track made a bare column alias (`SELECT 1 AS n`) read as a tenant table, because an
    unqualified name there is treated as this track's own schema. The clean `VIEW_NOT_SECURITY_INVOKER`
    mutation caught that.
    """
    out: list[str] = []

    def push(raw: str) -> None:
        raw = raw.strip()
        if "(" in raw:
            # A set-returning function in a FROM clause is not a table. Pushing its first word
            # made `FROM generate_series(1, 3) g` read as an unqualified tenant-track table.
            return
        token = _unquote(raw)
        if token and not token.isdigit() and token not in out:
            out.append(token)

    for match in _QUALIFIED.finditer(norm):
        push(match.group(1))
    for match in _FROM_CLAUSE.finditer(norm):
        for item in _top_level_items(match.group(1)):
            words = _norm(item).split()
            if words:
                push(words[0])
    for match in _JOINED.finditer(norm):
        push(match.group(1))
    return out


def _has_negative_test(tests_root: Path | None, table: str) -> bool:
    """A negative test names both the table and a runtime role. Absent tree -> False."""
    if tests_root is None or not tests_root.is_dir():
        return False
    for candidate in sorted(tests_root.rglob("*")):
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if table in text and any(role in text for role in RUNTIME_ROLES):
            return True
    return False


# --------------------------------------------------------------------------- corpus

def run_corpus(root: Path, allowlist: dict[str, dict],
               view_allowlist: set[str]) -> list[dict[str, str]]:
    """Qualify the lint against the D5 mutation corpus.

    Returns corpus failures (not SQL findings): an empty list means the lint is qualified against
    the corpus as it stands. That is qualification of the static half only; see the module
    docstring.
    """
    if not root.is_dir():
        raise Malformed(f"corpus root not found: {root}")
    baseline = root / "baseline"
    mutations = root / "mutations"
    if not baseline.is_dir() or not mutations.is_dir():
        raise Malformed(f"corpus needs baseline/ and mutations/ under {root}")
    failures: list[dict[str, str]] = []

    def fail(what: str, detail: str) -> None:
        failures.append({"corpus_item": what, "detail": detail})

    tests_root = baseline / "tests"
    for track in TRACKS:
        track_dir = baseline / track
        if not track_dir.is_dir():
            raise Malformed(f"corpus baseline is missing {track_dir}")
        baseline_files = sorted(track_dir.glob("*.sql"))
        if not baseline_files:
            raise Malformed(f"corpus baseline {track_dir} has no .sql file")
        for sql_file in baseline_files:
            found = lint_file(sql_file, track, allowlist, view_allowlist, tests_root)
            if found:
                fail(f"baseline/{track}/{sql_file.name}",
                     f"must lint clean, got {sorted({f.rule for f in found})}")

    targeted: set[str] = set()
    for mutation_dir in sorted(p for p in mutations.iterdir() if p.is_dir()):
        expected_names = mutation_dir.name.split("+")
        unknown = [r for r in expected_names if r not in RULES]
        if unknown:
            raise Malformed(f"corpus mutation names unknown rules: {', '.join(unknown)}")
        expected = set(expected_names)
        files = 0
        mismatched = False
        for track in TRACKS:
            track_dir = mutation_dir / track
            if not track_dir.is_dir():
                continue
            for sql_file in sorted(track_dir.glob("*.sql")):
                files += 1
                # Each file is judged on its own, not OR-ed with its siblings, so a directory may
                # hold several spellings of the same violation and every one of them has to be
                # caught. Under the previous OR, one canonical spelling qualified the rule and an
                # alternative spelling the rule missed stayed invisible -- which is how sixteen
                # single-spelling holes passed qualification.
                observed = {f.rule for f in
                            lint_file(sql_file, track, allowlist, view_allowlist, tests_root)}
                if observed != expected:
                    fail(f"mutations/{mutation_dir.name}/{track}/{sql_file.name}",
                         f"expected exactly {sorted(expected)}, observed {sorted(observed)}")
                    mismatched = True
        if not files:
            raise Malformed(
                f"corpus mutation {mutation_dir.name} has no .sql file under tenant/ or platform/")
        if not mismatched:
            targeted.add(expected_names[0])

    for rule in sorted(set(RULES) - targeted):
        fail(f"rule {rule}", "no mutation targets this rule (it must lead some mutation name)")

    # Legitimate migrations that must stay clean. Without these the corpus only ever proves that
    # rules fire, never that they stay quiet on valid SQL, so every false positive is unguarded.
    nearmiss = root / "nearmiss"
    if not nearmiss.is_dir():
        raise Malformed(f"corpus needs a nearmiss/ tree under {root}")
    nearmiss_files = 0
    for track in TRACKS:
        track_dir = nearmiss / track
        if not track_dir.is_dir():
            continue
        for sql_file in sorted(track_dir.glob("*.sql")):
            nearmiss_files += 1
            found = lint_file(sql_file, track, allowlist, view_allowlist, tests_root)
            if found:
                fail(f"nearmiss/{track}/{sql_file.name}",
                     f"legitimate migration must lint clean, got {sorted({f.rule for f in found})}")
    if not nearmiss_files:
        raise Malformed(f"corpus nearmiss/ tree under {root} has no .sql file")
    return failures


# --------------------------------------------------------------------------- cli

def _infer_track(paths: list[Path]) -> str:
    tracks = set()
    for path in paths:
        parts = {p.lower() for p in path.parts}
        for track in TRACKS:
            if track in parts:
                tracks.add(track)
    if len(tracks) == 1:
        return tracks.pop()
    raise Malformed("--track is required: no single /tenant/ or /platform/ path component found")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Veyro MOD-004 static migration lint (ADR-0002 D5).")
    sub = parser.add_subparsers(dest="command", required=True)
    here = Path(__file__).resolve().parent

    p_lint = sub.add_parser("lint", help="lint migration files")
    p_lint.add_argument("paths", nargs="+")
    p_lint.add_argument("--track", choices=TRACKS)
    p_lint.add_argument("--tests-root")
    p_lint.add_argument("--allowlist", default=str(here / DEFAULT_ALLOWLIST))

    p_corpus = sub.add_parser("corpus", help="qualify the lint against the D5 mutation corpus")
    p_corpus.add_argument("--root", default=str(here / "corpus"))
    p_corpus.add_argument("--allowlist", default=str(here / DEFAULT_ALLOWLIST))

    args = parser.parse_args(argv)
    try:
        allowlist, view_allowlist = load_allowlist(Path(args.allowlist))
        if args.command == "lint":
            files: list[Path] = []
            for raw in args.paths:
                path = Path(raw)
                if path.is_dir():
                    files.extend(sorted(path.rglob("*.sql")))
                elif path.exists():
                    files.append(path)
                else:
                    raise Malformed(f"path not found: {raw}")
            if not files:
                raise Malformed("no .sql file to lint")
            track = args.track or _infer_track(files)
            tests_root = Path(args.tests_root) if args.tests_root else None
            findings: list[Finding] = []
            for path in files:
                findings.extend(lint_file(path, track, allowlist, view_allowlist, tests_root))
            result = "BLOCKED" if findings else "PASS"
            out = {"result": result, "command": "lint", "track": track,
                   "files": [str(f) for f in files],
                   "static_only": "ADR-0002 D5 live catalog assertions are NOT performed here",
                   "findings": [f.as_dict() for f in findings]}
        else:
            failures = run_corpus(Path(args.root), allowlist, view_allowlist)
            result = "BLOCKED" if failures else "PASS"
            out = {"result": result, "command": "corpus", "root": args.root,
                   "rules": len(RULES),
                   "static_only": "ADR-0002 D5 live catalog assertions are NOT performed here",
                   "findings": failures}
    except Malformed as exc:
        print(json.dumps({"result": "MALFORMED", "detail": str(exc)}, indent=1, sort_keys=True))
        return 2
    print(json.dumps(out, indent=1, sort_keys=True))
    return 1 if out["result"] == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
